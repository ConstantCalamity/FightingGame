"""Shared helpers for the headless map builders (Blender 5.x).

Used by build_cinder_cathedral.py and build_thornwall_keep.py:

    blender.exe -b --factory-startup -P build_<map>.py -- [--rebake] [--no-render] [--no-export]
                                                           [--samples=N] [--texres=N] [--game-only]

Sections
  * options / paths / colour helpers
  * seamless texture baking: procedural Cycles fields on a 4D torus -> numpy PBR composition -> PNG
  * geometry: bmesh primitives + an accumulating Builder that merges pieces into a few chunk objects
    with world-scale (metres / tiling) box-projected UVs
  * masonry: coursed block walls with pointed/round arch openings, voussoirs, tracery, broken tops
  * organic: tubes (trees), lathe, cloth, rocks
  * preview materials (Unity-like linear fog + trilight ambient), lighting, cameras, render
  * FBX / json export

Conventions follow Tools/Blender/CONVENTIONS.md (metres, Z up, Unity (x,y,z) = Blender (-x,z,-y)).
"""
import bpy
import bmesh
import math
import random
import os
import sys
import json
import time
import numpy as np
from mathutils import Vector, Matrix, Euler
from mathutils import noise as mnoise

TAU = math.tau
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
_T0 = time.time()


def log(*a):
    print('[%7.1fs]' % (time.time() - _T0), *a, flush=True)


# ----------------------------------------------------------------------------------------------
# options / paths
# ----------------------------------------------------------------------------------------------
class Opts:
    pass


def parse_args():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    o = Opts()
    o.rebake = '--rebake' in argv
    o.no_render = '--no-render' in argv
    o.no_export = '--no-export' in argv
    o.game_only = '--game-only' in argv
    o.samples = 96
    o.res = 2048
    o.only = None
    o.cams = []
    for a in argv:
        if a.startswith('--samples='):
            o.samples = int(a.split('=', 1)[1])
        elif a.startswith('--texres='):
            o.res = int(a.split('=', 1)[1])
        elif a.startswith('--rebake='):          # --rebake=M_Stone,M_Floor
            o.only = set(a.split('=', 1)[1].split(','))
            o.rebake = True
        elif a.startswith('--cam='):             # --cam=px,py,pz,tx,ty,tz,fov,name  (debug view only)
            v = a.split('=', 1)[1].split(',')
            o.cams.append(([float(x) for x in v[:3]], [float(x) for x in v[3:6]], float(v[6]), v[7]))
    return o


def map_paths(name):
    p = dict(
        art=os.path.join(REPO, 'Assets', '_Game', 'Art', 'Maps', name),
        blend=os.path.join(REPO, 'ArtSource', 'Maps', name + '.blend'),
        logs=os.path.join(REPO, 'Logs', 'maps'),
    )
    for k in ('art', 'logs'):
        os.makedirs(p[k], exist_ok=True)
    os.makedirs(os.path.dirname(p['blend']), exist_ok=True)
    return p


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def setup_cycles(scene, samples=64):
    scene.render.engine = 'CYCLES'
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'OPTIX'
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scene.cycles.device = 'GPU'
    except Exception as e:  # pragma: no cover
        log('GPU setup failed, using CPU:', e)
    scene.cycles.samples = samples


# ----------------------------------------------------------------------------------------------
# colour helpers
# ----------------------------------------------------------------------------------------------
def s2l(c):
    """sRGB (0..1) tuple -> linear tuple."""
    out = []
    for x in c:
        out.append(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def lin2srgb(a):
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1.0 / 2.4) - 0.055)


def srgb_arr(c):
    return np.array(s2l(c), np.float32)


# ----------------------------------------------------------------------------------------------
# numpy texture helpers (all wrap-around => seamless)
# ----------------------------------------------------------------------------------------------
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    if isinstance(t, np.ndarray) and t.ndim == 2 and (np.ndim(a) == 3 or np.ndim(b) == 3 or
                                                      (np.ndim(a) == 1 and len(a) == 3)):
        t = t[..., None]
    return a + (b - a) * t


def ramp(x, stops):
    """stops: [(pos, (r,g,b) sRGB)] -> linear RGB array."""
    pos = np.array([s[0] for s in stops], np.float32)
    cols = np.array([s2l(s[1]) for s in stops], np.float32)
    out = np.empty(x.shape + (3,), np.float32)
    for c in range(3):
        out[..., c] = np.interp(x, pos, cols[:, c])
    return out


def blur(a, sigma):
    """Gaussian blur with wrap-around (FFT). sigma in pixels (scalar or (sv, su))."""
    H, W = a.shape
    sv, su = (sigma, sigma) if np.isscalar(sigma) else sigma
    fy = np.fft.fftfreq(H)[:, None]
    fx = np.fft.rfftfreq(W)[None, :]
    k = np.exp(-2.0 * (np.pi ** 2) * ((su ** 2) * fx ** 2 + (sv ** 2) * fy ** 2))
    return np.fft.irfft2(np.fft.rfft2(a) * k, s=a.shape).astype(np.float32)


def normal_from_height(h, tu, tv=None, strength=1.0):
    """h in metres, tile size tu x tv metres. Returns encoded OpenGL (+Y) tangent normal (H,W,3)."""
    H, W = h.shape
    tv = tu if tv is None else tv
    pu, pv = tu / W, tv / H
    dhdu = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / (2 * pu)
    dhdv = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / (2 * pv)
    n = np.stack([-dhdu * strength, -dhdv * strength, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def ao_from_height(h, tile, radii_m=(0.01, 0.04, 0.12), depth_m=(0.004, 0.012, 0.03)):
    H, W = h.shape
    occ = np.zeros_like(h)
    for r, d in zip(radii_m, depth_m):
        s = max(0.7, r / tile * W)
        occ += np.clip((blur(h, s) - h) / d, 0, 1) / len(radii_m)
    return np.clip(1.0 - occ * 1.4, 0.0, 1.0)


def warp_coords(res, du=None, dv=None):
    u = (np.arange(res, dtype=np.float32) + 0.5) / res
    U, V = np.meshgrid(u, u)
    if du is not None:
        U = (U + du) % 1.0
    if dv is not None:
        V = (V + dv) % 1.0
    return U, V


def brick_layout(U, V, rng, rows, per_row, row_jitter=0.25, len_jitter=0.35):
    """Seamless running-bond layout. U,V in [0,1) (may be warped). Row and joint positions are
    random cuts on a circle so the layout wraps. Returns dict(du, dv, rid, row, rnd) where du/dv are
    distances (uv units) to the nearest vertical/horizontal joint, rnd a per-brick random [0,1)."""
    rb = (np.arange(rows) + 0.5 + np.array([rng.uniform(-row_jitter, row_jitter) for _ in range(rows)])) / rows
    rb = np.sort(rb % 1.0)
    idx = np.searchsorted(rb, V, side='right')            # 0..rows
    row = (idx - 1) % rows
    lo = np.where(idx == 0, rb[-1] - 1.0, rb[np.clip(idx - 1, 0, rows - 1)])
    hi = np.where(idx == rows, rb[0] + 1.0, rb[np.clip(idx, 0, rows - 1)])
    dv = np.minimum(V - lo, hi - V)
    rowh = hi - lo
    du = np.zeros_like(U)
    rid = np.zeros(U.shape, np.int32)
    for r in range(rows):
        n = per_row if isinstance(per_row, int) else rng.randint(per_row[0], per_row[1])
        base = (np.arange(n) + rng.random()) / n
        cuts = np.sort((base + np.array([rng.uniform(-len_jitter, len_jitter) / n for _ in range(n)])) % 1.0)
        m = row == r
        u = U[m]
        k = np.searchsorted(cuts, u, side='right')
        left = np.where(k == 0, cuts[-1] - 1.0, cuts[np.clip(k - 1, 0, n - 1)])
        right = np.where(k == n, cuts[0] + 1.0, cuts[np.clip(k, 0, n - 1)])
        du[m] = np.minimum(u - left, right - u)
        rid[m] = r * 1000 + ((k - 1) % n)
    rnd = np.modf(np.sin(rid.astype(np.float64) * 12.9898 + 78.233) * 43758.5453)[0]
    rnd = np.abs(rnd).astype(np.float32)
    return dict(du=du, dv=dv, rid=rid, row=row, rnd=rnd, rowh=rowh)


# ----------------------------------------------------------------------------------------------
# Cycles field baker: procedural Noise/Voronoi in 4D on a flat torus => provably seamless.
# For UV (u,v):  P = (Ru cos 2πu, Ru sin 2πu, Rv cos 2πv),  W = Rv sin 2πv,  R = features/(2π)
# ----------------------------------------------------------------------------------------------
class FieldBaker:
    def __init__(self, res, samples=4):
        self.res = res
        sc = bpy.context.scene
        setup_cycles(sc, samples)
        sc.render.bake.margin = 0
        me = bpy.data.meshes.new('_BakePlane')
        me.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new(name='UVMap')
        uv.data.foreach_set('uv', [0, 0, 1, 0, 1, 1, 0, 1])
        self.ob = bpy.data.objects.new('_BakePlane', me)
        sc.collection.objects.link(self.ob)
        self.mat = bpy.data.materials.new('_BakeMat')
        try:
            self.mat.use_nodes = True
        except Exception:
            pass
        me.materials.append(self.mat)
        self.img = bpy.data.images.new('_BakeTarget', res, res, alpha=False, float_buffer=True)
        self.img.colorspace_settings.name = 'Non-Color'

    def _m(self, op, a, b=None):
        n = self.nt.nodes.new('ShaderNodeMath')
        n.operation = op
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, bpy.types.NodeSocket):
                self.nt.links.new(v, n.inputs[i])
            else:
                n.inputs[i].default_value = v
        return n.outputs[0]

    def _field(self, uu, vv, spec, idx):
        nt = self.nt
        fu = spec.get('fu', spec.get('f', 4.0))
        fv = spec.get('fv', spec.get('f', 4.0))
        seed = spec.get('seed', idx * 7 + 3)
        Ru, Rv = fu / TAU, fv / TAU
        cu = self._m('MULTIPLY', self._m('COSINE', uu), Ru)
        su = self._m('MULTIPLY', self._m('SINE', uu), Ru)
        cv = self._m('MULTIPLY', self._m('COSINE', vv), Rv)
        sv = self._m('MULTIPLY', self._m('SINE', vv), Rv)
        r = random.Random(seed)
        off = [r.uniform(-50, 50) for _ in range(4)]
        comb = nt.nodes.new('ShaderNodeCombineXYZ')
        nt.links.new(self._m('ADD', cu, off[0]), comb.inputs[0])
        nt.links.new(self._m('ADD', su, off[1]), comb.inputs[1])
        nt.links.new(self._m('ADD', cv, off[2]), comb.inputs[2])
        w = self._m('ADD', sv, off[3])
        t = spec['type']
        if t == 'noise':
            n = nt.nodes.new('ShaderNodeTexNoise')
            n.noise_dimensions = '4D'
            n.noise_type = spec.get('ntype', 'FBM')
            try:
                n.normalize = True
            except Exception:
                pass
            n.inputs['Scale'].default_value = 1.0
            n.inputs['Detail'].default_value = spec.get('detail', 4.0)
            n.inputs['Roughness'].default_value = spec.get('rough', 0.55)
            n.inputs['Lacunarity'].default_value = spec.get('lac', 2.0)
            n.inputs['Distortion'].default_value = spec.get('dist', 0.0)
            if 'gain' in spec and 'Gain' in n.inputs:
                n.inputs['Gain'].default_value = spec['gain']
            nt.links.new(comb.outputs[0], n.inputs['Vector'])
            nt.links.new(w, n.inputs['W'])
            return n.outputs['Fac']
        if t == 'voronoi':
            n = nt.nodes.new('ShaderNodeTexVoronoi')
            n.voronoi_dimensions = '4D'
            n.feature = spec.get('feature', 'F1')
            n.distance = spec.get('metric', 'EUCLIDEAN')
            n.inputs['Scale'].default_value = 1.0
            n.inputs['Randomness'].default_value = spec.get('rand', 1.0)
            if 'Detail' in n.inputs:
                n.inputs['Detail'].default_value = spec.get('detail', 0.0)
                n.inputs['Roughness'].default_value = spec.get('rough', 0.5)
            nt.links.new(comb.outputs[0], n.inputs['Vector'])
            nt.links.new(w, n.inputs['W'])
            out = spec.get('out', 'Distance')
            if out == 'Color':
                sep = nt.nodes.new('ShaderNodeSeparateColor')
                nt.links.new(n.outputs['Color'], sep.inputs[0])
                return sep.outputs[0]
            return n.outputs[out]
        raise ValueError(t)

    def bake(self, specs):
        """specs: dict name -> field spec. Returns dict name -> float32 (res,res) array, row 0 = v=0."""
        names = list(specs.keys())
        out = {}
        for g in range(0, len(names), 3):
            grp = names[g:g + 3]
            nt = self.nt = self.mat.node_tree
            nt.nodes.clear()
            tc = nt.nodes.new('ShaderNodeTexCoord')
            sep = nt.nodes.new('ShaderNodeSeparateXYZ')
            nt.links.new(tc.outputs['UV'], sep.inputs[0])
            uu = self._m('MULTIPLY', sep.outputs[0], TAU)
            vv = self._m('MULTIPLY', sep.outputs[1], TAU)
            cc = nt.nodes.new('ShaderNodeCombineColor')
            for i, nm in enumerate(grp):
                nt.links.new(self._field(uu, vv, specs[nm], g + i), cc.inputs[i])
            em = nt.nodes.new('ShaderNodeEmission')
            em.inputs['Strength'].default_value = 1.0
            nt.links.new(cc.outputs[0], em.inputs['Color'])
            mo = nt.nodes.new('ShaderNodeOutputMaterial')
            nt.links.new(em.outputs[0], mo.inputs['Surface'])
            tex = nt.nodes.new('ShaderNodeTexImage')
            tex.image = self.img
            nt.nodes.active = tex
            for o in bpy.data.objects:
                try:
                    o.select_set(False)
                except Exception:
                    pass
            bpy.context.view_layer.objects.active = self.ob
            self.ob.select_set(True)
            bpy.ops.object.bake(type='EMIT', margin=0, use_clear=True, target='IMAGE_TEXTURES')
            px = np.empty(self.res * self.res * 4, np.float32)
            self.img.pixels.foreach_get(px)
            px = px.reshape(self.res, self.res, 4)
            for i, nm in enumerate(grp):
                a = px[..., i].copy()
                sp = specs[nm]
                if sp.get('norm', sp['type'] == 'noise'):
                    sub = a[::5, ::5]
                    lo, hi = np.percentile(sub, 0.5), np.percentile(sub, 99.5)
                    a = np.clip((a - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
                out[nm] = a
        return out

    def cleanup(self):
        bpy.data.objects.remove(self.ob)
        bpy.data.materials.remove(self.mat)
        bpy.data.images.remove(self.img)


def contact_sheet(matdefs, tex_dir, out_path, cell=384):
    """Albedo (top) + normal (bottom) thumbnails of every material, for quick review."""
    n = len(matdefs)
    sheet = np.ones((cell * 2, cell * n, 4), np.float32)
    for i, m in enumerate(matdefs):
        for row, tn in enumerate((m.tex_names()[0], m.tex_names()[1])):
            img = bpy.data.images.load(os.path.join(tex_dir, tn), check_existing=False)
            w, h = img.size
            px = np.empty(w * h * 4, np.float32)
            img.pixels.foreach_get(px)
            px = px.reshape(h, w, 4)
            f = h // cell
            px = px[:f * cell, :f * cell].reshape(cell, f, cell, f, 4).mean(axis=(1, 3))
            y0 = (1 - row) * cell
            sheet[y0:y0 + cell, i * cell:(i + 1) * cell] = px
            bpy.data.images.remove(img)
    save_png(out_path, sheet, True)


def save_png(path, arr, srgb):
    """arr (H,W,C) float 0..1, row 0 = bottom (Blender order). Values are written as-is
    (caller encodes sRGB)."""
    H, W = arr.shape[:2]
    C = 1 if arr.ndim == 2 else arr.shape[2]
    rgba = np.ones((H, W, 4), np.float32)
    if C == 1:
        rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = arr
    else:
        rgba[..., :C] = arr
    img = bpy.data.images.new('_save', W, H, alpha=(C == 4), float_buffer=False)
    img.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'
    img.alpha_mode = 'CHANNEL_PACKED'
    img.pixels.foreach_set(np.clip(rgba, 0, 1).ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    if C != 4:
        try:
            img.alpha_mode = 'NONE'
        except Exception:
            pass
    img.save()
    bpy.data.images.remove(img)


class MatDef:
    """A map material: procedural fields + numpy recipe -> PBR textures, plus Unity params."""

    def __init__(self, name, tiling, fields, recipe, tint=(1, 1, 1), emission=None, emission_intensity=0.0,
                 smoothness_scale=1.0, tile_v=None, seed=1, ao_strength=0.6, normal_strength=1.0, uv_space='metres'):
        self.name = name                      # e.g. 'M_Stone'
        self.short = name[2:] if name.startswith('M_') else name
        self.tiling = tiling                  # metres per UV unit
        self.tile_v = tile_v or tiling        # for non-square physical textures (banners)
        self.fields = fields
        self.recipe = recipe
        self.tint = tint                      # sRGB
        self.emission = emission              # sRGB or None
        self.emission_intensity = emission_intensity
        self.smoothness_scale = smoothness_scale
        self.seed = seed
        self.ao_strength = ao_strength
        self.normal_strength = normal_strength
        self.uv_space = uv_space

    def tex_names(self):
        return ('T_%s_Albedo.png' % self.short, 'T_%s_Normal.png' % self.short, 'T_%s_Mask.png' % self.short)

    def json(self):
        a, n, m = self.tex_names()
        return {"material": self.name, "albedo": a, "normal": n, "mask": m, "tiling": round(self.tiling, 4),
                "tint": [round(x, 4) for x in self.tint],
                "emission": None if self.emission is None else [round(x, 4) for x in self.emission],
                "emissionIntensity": float(self.emission_intensity), "smoothnessScale": float(self.smoothness_scale),
                "uvPrescaled": True, "uvSpace": self.uv_space,
                "emissionMap": a if self.emission is not None else None}


def bake_materials(matdefs, out_dir, res, rebake=False, only=None):
    todo = []
    for m in matdefs:
        paths = [os.path.join(out_dir, t) for t in m.tex_names()]
        force = rebake and (only is None or m.name in only)
        if force or not all(os.path.exists(p) for p in paths):
            todo.append(m)
    if not todo:
        log('textures cached (%d materials)' % len(matdefs))
        return
    baker = FieldBaker(res)
    for m in todo:
        t = time.time()
        F = baker.bake(m.fields) if m.fields else {}
        rng = random.Random(m.seed)
        r = m.recipe(F, res, m, rng)
        alb = r['albedo'].astype(np.float32)
        shp = alb.shape[:2]
        h = np.broadcast_to(np.asarray(r['height'], np.float32), shp).copy()
        rough = np.broadcast_to(np.clip(np.asarray(r['rough'], np.float32), 0.02, 1.0), shp).copy()
        metal = np.broadcast_to(np.asarray(r.get('metal', 0.0), np.float32), shp).copy()
        ao = ao_from_height(h, m.tiling) if m.ao_strength > 0 else np.ones_like(h)
        alb_out = alb * (1.0 - m.ao_strength * (1.0 - ao))[..., None]
        nrm = normal_from_height(h, m.tiling, m.tile_v, m.normal_strength)
        mask = np.stack([metal, ao, np.zeros_like(h), 1.0 - rough], -1)
        a, n, k = (os.path.join(out_dir, x) for x in m.tex_names())
        save_png(a, lin2srgb(alb_out), True)
        save_png(n, nrm, False)
        save_png(k, mask, False)
        log('baked %s in %.1fs' % (m.name, time.time() - t))
    baker.cleanup()


# ----------------------------------------------------------------------------------------------
# bmesh primitives (all built at true metric size around the local origin)
# ----------------------------------------------------------------------------------------------
def bm_box(sx, sy, sz, bevel=0.0, segs=1, z0=False):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    if z0:
        bmesh.ops.translate(bm, vec=(0, 0, sz / 2), verts=bm.verts)
    if bevel > 0:
        b = min(bevel, 0.45 * min(sx, sy, sz))
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=b, segments=segs, affect='EDGES', profile=0.5,
                        clamp_overlap=True)
    return bm


def bm_hex(p, bevel=0.0, segs=1):
    """p: 8 points; 0-3 bottom ring, 4-7 top ring (same winding)."""
    bm = bmesh.new()
    vs = [bm.verts.new(Vector(q)) for q in p]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        try:
            bm.faces.new([vs[i] for i in f])
        except ValueError:
            pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=segs, affect='EDGES', profile=0.5,
                        clamp_overlap=True)
    return bm


def bm_cyl(r1, r2, h, segs=12, caps=True, bevel=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=segs, radius1=r1, radius2=r2, depth=h)
    bmesh.ops.translate(bm, vec=(0, 0, h / 2), verts=bm.verts)
    if bevel > 0:
        edges = [e for e in bm.edges if all(len(f.verts) > 4 for f in e.link_faces) is False and
                 any(len(f.verts) > 4 for f in e.link_faces)]
        if edges:
            bmesh.ops.bevel(bm, geom=edges, offset=bevel, segments=1, affect='EDGES', clamp_overlap=True)
    return bm


def bm_sphere(r, us=12, vs=8):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=us, v_segments=vs, radius=r)
    return bm


def bm_ico(r, sub=2):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)
    return bm


def bm_prism(poly, depth, bevel=0.0, segs=1):
    """poly: list of (x,z) CCW (seen from -y). Extruded along y from -depth/2 to +depth/2."""
    bm = bmesh.new()
    n = len(poly)
    f = [bm.verts.new((x, -depth / 2, z)) for x, z in poly]
    b = [bm.verts.new((x, depth / 2, z)) for x, z in poly]
    bm.faces.new(f)
    bm.faces.new(list(reversed(b)))
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((f[i], b[i], b[j], f[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=segs, affect='EDGES', clamp_overlap=True)
    return bm


def bm_lathe(profile, segs=16, cap_bottom=True, cap_top=True, uv_tiling=None):
    """profile: [(r, z)] bottom->top. Explicit metric UVs (u around, v along profile)."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new('UVMap')
    rings = []
    for (r, z) in profile:
        rings.append([bm.verts.new((r * math.cos(TAU * i / segs), r * math.sin(TAU * i / segs), z))
                      for i in range(segs)])
    rmean = max(1e-3, sum(p[0] for p in profile) / len(profile))
    circ = TAU * rmean
    if uv_tiling:
        circ = max(1, round(circ / uv_tiling)) * uv_tiling
    vacc = [0.0]
    for k in range(1, len(profile)):
        vacc.append(vacc[-1] + math.hypot(profile[k][0] - profile[k - 1][0], profile[k][1] - profile[k - 1][1]))
    for k in range(len(profile) - 1):
        for i in range(segs):
            j = (i + 1) % segs
            f = bm.faces.new((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]))
            uvs = ((i / segs, vacc[k]), ((i + 1) / segs, vacc[k]), ((i + 1) / segs, vacc[k + 1]),
                   (i / segs, vacc[k + 1]))
            for l, (u, v) in zip(f.loops, uvs):
                l[uvl].uv = (u * circ, v)
    if cap_bottom and profile[0][0] > 1e-4:
        f = bm.faces.new(list(reversed(rings[0])))
        for l in f.loops:
            l[uvl].uv = (l.vert.co.x, l.vert.co.y)
    if cap_top and profile[-1][0] > 1e-4:
        f = bm.faces.new(rings[-1])
        for l in f.loops:
            l[uvl].uv = (l.vert.co.x, l.vert.co.y)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def bm_tube(pts, radii, segs=8, cap_start=True, cap_end=True, uv_tiling=None, lump=0.0, lump_freq=3.0,
            seed=0, uv_swap=False):
    """Generalised cylinder along a polyline (parallel-transport frames). Explicit metric UVs."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new('UVMap')
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tans = []
    for i in range(n):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == n - 1:
            t = pts[-1] - pts[-2]
        else:
            t = (pts[i + 1] - pts[i - 1])
        tans.append(t.normalized())
    up = Vector((0, 0, 1)) if abs(tans[0].z) < 0.9 else Vector((1, 0, 0))
    nrm = tans[0].cross(up).normalized()
    frames = []
    for i in range(n):
        if i > 0:
            nrm = nrm - tans[i] * nrm.dot(tans[i])
            if nrm.length < 1e-6:
                nrm = tans[i].orthogonal()
            nrm.normalize()
        frames.append((nrm.copy(), tans[i].cross(nrm).normalized()))
    rmean = sum(radii) / len(radii)
    circ = TAU * rmean
    if uv_tiling:
        circ = max(1, round(circ / uv_tiling)) * uv_tiling
    rings = []
    vlen = [0.0]
    for i in range(1, n):
        vlen.append(vlen[-1] + (pts[i] - pts[i - 1]).length)
    for i in range(n):
        a, b = frames[i]
        ring = []
        for k in range(segs):
            ang = TAU * k / segs
            d = a * math.cos(ang) + b * math.sin(ang)
            r = radii[i]
            if lump > 0:
                q = pts[i] * lump_freq + d * 0.8 + Vector((seed * 13.1, seed * 7.7, 0))
                r *= 1.0 + lump * mnoise.noise(q)
            ring.append(bm.verts.new(pts[i] + d * r))
        rings.append(ring)
    for i in range(n - 1):
        for k in range(segs):
            j = (k + 1) % segs
            f = bm.faces.new((rings[i][k], rings[i][j], rings[i + 1][j], rings[i + 1][k]))
            uvs = ((k / segs, vlen[i]), ((k + 1) / segs, vlen[i]), ((k + 1) / segs, vlen[i + 1]),
                   (k / segs, vlen[i + 1]))
            for l, (u, v) in zip(f.loops, uvs):
                l[uvl].uv = (v, u * circ) if uv_swap else (u * circ, v)
    if cap_start:
        f = bm.faces.new(list(reversed(rings[0])))
        for l in f.loops:
            l[uvl].uv = (l.vert.co.x, l.vert.co.y)
    if cap_end:
        f = bm.faces.new(rings[-1])
        for l in f.loops:
            l[uvl].uv = (l.vert.co.x, l.vert.co.z)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def bm_cut(bm, co, no):
    """Remove everything on the +no side of the plane and cap the hole."""
    co, no = Vector(co), Vector(no).normalized()
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, clear_outer=True, dist=1e-5)
    edges = [e for e in res['geom_cut'] if isinstance(e, bmesh.types.BMEdge)]
    if edges:
        try:
            bmesh.ops.holes_fill(bm, edges=edges, sides=0)
        except Exception:
            pass
    return bm


def bm_rough_cut(bm, co, no, rng, n=3, spread=0.06, tilt=0.35):
    """A jagged fracture: several slightly different planes near the same spot."""
    co, no = Vector(co), Vector(no).normalized()
    t1 = no.orthogonal().normalized()
    t2 = no.cross(t1).normalized()
    for i in range(n):
        d = no + t1 * rng.uniform(-tilt, tilt) + t2 * rng.uniform(-tilt, tilt)
        c = co + no * rng.uniform(-spread, spread) + t1 * rng.uniform(-0.1, 0.1)
        bm_cut(bm, c, d)
    return bm


def bm_chip(bm, rng, n=1, depth=(0.03, 0.09)):
    """Chip random corners of a (roughly box-shaped) piece."""
    if not bm.verts:
        return bm
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    lo = Vector((min(xs), min(ys), min(zs)))
    hi = Vector((max(xs), max(ys), max(zs)))
    c = (lo + hi) / 2
    for _ in range(n):
        corner = Vector((rng.choice((lo.x, hi.x)), rng.choice((lo.y, hi.y)), rng.choice((lo.z, hi.z))))
        d = (corner - c)
        if d.length < 1e-6:
            continue
        dn = Vector((d.x * rng.uniform(0.5, 1.5), d.y * rng.uniform(0.5, 1.5), d.z * rng.uniform(0.5, 1.5))).normalized()
        dep = rng.uniform(*depth)
        # plane through point near the corner, normal toward corner
        p = corner - dn * (dep * 1.7)
        bm_cut(bm, p, dn)
    return bm


def bm_noise(bm, amp, freq, seed=0, normal_only=False):
    off = Vector((seed * 17.31, seed * 5.13, seed * 11.7))
    for v in bm.verts:
        if normal_only:
            v.co += v.normal * amp * mnoise.noise(v.co * freq + off)
        else:
            v.co += mnoise.noise_vector(v.co * freq + off) * amp
    return bm


def bm_merge(dst, src, M=None):
    """Append src bmesh (with UV + material indices) into dst; optional transform."""
    me = bpy.data.meshes.new('_tmpmerge')
    if M is not None:
        bmesh.ops.transform(src, matrix=M, verts=src.verts)
    src.to_mesh(me)
    dst.from_mesh(me)
    bpy.data.meshes.remove(me)
    return dst


def bm_set_mat(bm, idx):
    for f in bm.faces:
        f.material_index = idx
    return bm


def rock_bm(rng, size, sub=2, flat=0.35, rough=0.25):
    bm = bm_ico(1.0, sub)
    sc = Vector((size[0], size[1], size[2]))
    seed = rng.randint(0, 9999)
    bm_noise(bm, rough, 1.4, seed, normal_only=True)
    bm_noise(bm, rough * 0.35, 4.0, seed + 1, normal_only=True)
    for v in bm.verts:
        v.co = Vector((v.co.x * sc.x, v.co.y * sc.y, v.co.z * sc.z))
    if flat > 0:
        bm_cut(bm, (0, 0, -size[2] * (1 - flat)), (0, 0, -1))
    return bm


def rubble_bm(rng, sx, sy, sz, bevel=0.025, cuts=3):
    """A broken masonry chunk: bevelled block hacked by several planes."""
    bm = bm_box(sx, sy, sz, bevel)
    c = Vector((0, 0, 0))
    for _ in range(cuts):
        d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        if d.length < 0.2:
            continue
        d.normalize()
        ext = abs(d.x) * sx / 2 + abs(d.y) * sy / 2 + abs(d.z) * sz / 2
        bm_cut(bm, c + d * ext * rng.uniform(0.45, 0.85), d)
    return bm


def mound_bm(rx, ry, h, n, rng, power=1.6, noise_amp=0.25, noise_freq=1.2, sink=0.03, flat_top=0.0, outline=0.25):
    """Elliptic heap (ash drift, earth mound) centred at the origin, base at z=-sink. World-UV it."""
    bm = bmesh.new()
    seed = rng.uniform(0, 100)
    grid = {}
    for j in range(n + 1):
        for i in range(n + 1):
            x = (i / n * 2 - 1) * rx
            y = (j / n * 2 - 1) * ry
            r = math.sqrt((x / rx) ** 2 + (y / ry) ** 2)
            # perturb radius for an irregular outline
            ang = math.atan2(y / ry, x / rx)
            rr = r * (1 + outline * mnoise.noise(Vector((math.cos(ang) * 1.3 + seed, math.sin(ang) * 1.3, seed)))
                      + outline * 0.4 * mnoise.noise(Vector((math.cos(ang) * 3.1 + seed, math.sin(ang) * 3.1, seed + 7))))
            s = max(0.0, 1 - rr * rr) ** power
            if flat_top > 0:
                s = min(1.0, s / (1 - flat_top))
            z = h * s * (1 + noise_amp * mnoise.noise(Vector((x * noise_freq + seed, y * noise_freq, seed * 0.3))))
            z = max(z, 0.0) - sink * (1 - min(1.0, s * 6))
            grid[i, j] = (bm.verts.new((x, y, z)), rr)
    for j in range(n):
        for i in range(n):
            q = [grid[i, j], grid[i + 1, j], grid[i + 1, j + 1], grid[i, j + 1]]
            if min(v[1] for v in q) > 1.0:
                continue
            bm.faces.new([v[0] for v in q])
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    return bm


def heightfield_bm(x0, x1, y0, y1, nx, ny, zf, matf=None):
    """Regular grid terrain with z = zf(x, y); matf(x, y) -> material index per face."""
    bm = bmesh.new()
    vs = []
    for j in range(ny + 1):
        y = y0 + (y1 - y0) * j / ny
        row = []
        for i in range(nx + 1):
            x = x0 + (x1 - x0) * i / nx
            row.append(bm.verts.new((x, y, zf(x, y))))
        vs.append(row)
    for j in range(ny):
        for i in range(nx):
            f = bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
            if matf:
                cx = x0 + (x1 - x0) * (i + 0.5) / nx
                cy = y0 + (y1 - y0) * (j + 0.5) / ny
                f.material_index = matf(cx, cy)
    return bm


def cloth_bm(w, h, nx, nz, rng, folds=3, fold_amp=0.05, sag=0.0, tatter=0.25, holes=0.0, thickness=0.012,
             swallow=0.0, points=0, sway=0.0, uv_norm=True, mirror_u=True):
    """Hanging cloth, top edge at z=0 spanning x in [-w/2, w/2], hanging to z=-h.
    UVs: normalised 0..1 (u across, v up) when uv_norm, else metres."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new('UVMap')
    ph = [rng.uniform(0, TAU) for _ in range(4)]
    grid = []
    for j in range(nz + 1):
        tz = j / nz
        row = []
        for i in range(nx + 1):
            tx = i / nx
            x = (tx - 0.5) * w
            z = -tz * h
            y = fold_amp * (math.sin(tx * folds * TAU + ph[0] + tz * 1.3) * (0.35 + 0.65 * tz) +
                            0.4 * math.sin(tx * folds * 2.3 * TAU + ph[1]) * tz)
            y += sway * tz * tz
            x += fold_amp * 0.3 * math.sin(tz * 5 + ph[2]) * tz
            z += sag * math.sin(tx * math.pi) * 0.0
            row.append(bm.verts.new((x, y, z)))
        grid.append(row)
    # bottom outline (swallow tail / points / tatter): per column cut-off depth
    cut = []
    for i in range(nx):
        tx = (i + 0.5) / nx
        d = 1.0
        if swallow > 0:
            d -= swallow * (1 - abs(tx - 0.5) * 2)
        if points > 0:
            d -= 0.08 * (1 - abs(math.sin(tx * points * math.pi)))
        d -= tatter * rng.random() ** 2.0
        cut.append(d)
    faces = []
    for j in range(nz):
        for i in range(nx):
            tz = (j + 1) / nz
            if tz > cut[i] + 1e-6:
                continue
            if holes > 0 and tz > 0.35 and rng.random() < holes * tz:
                continue
            f = bm.faces.new((grid[j][i], grid[j + 1][i], grid[j + 1][i + 1], grid[j][i + 1]))
            faces.append(f)
            for l in f.loops:
                ii = grid[j].index(l.vert) if l.vert in grid[j] else grid[j + 1].index(l.vert)
                jj = j if l.vert in grid[j] else j + 1
                u = ii / nx
                if mirror_u:
                    u = 1 - u
                v = 1 - jj / nz
                l[uvl].uv = (u, v) if uv_norm else (u * w, v * h)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for f in bm.faces:
        if f.normal.y < 0:
            pass
    if thickness > 0:
        bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=thickness)
    return bm


# ----------------------------------------------------------------------------------------------
# Builder: accumulate pieces into chunk objects
# ----------------------------------------------------------------------------------------------
class Chunk:
    def __init__(self, name, kind):
        self.name, self.kind = name, kind
        self.co, self.loops, self.starts, self.fmat, self.uv, self.smooth = [], [], [], [], [], []
        self.mats = []

    def mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)


def _proj(p, n):
    ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
    if az >= ax and az >= ay:
        return (p.x, p.y) if n.z >= 0 else (-p.x, p.y)
    if ax >= ay:
        return (p.y, p.z) if n.x >= 0 else (-p.y, p.z)
    return (-p.x, p.z) if n.y >= 0 else (p.x, p.z)


def _proj_grain(p, n, g):
    """Box projection where U follows the grain axis g (0=x,1=y,2=z) when it lies in the face plane."""
    ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
    if az >= ax and az >= ay:
        return (p.y, p.x) if g == 1 else (p.x, p.y)
    if ax >= ay:
        return (p.z, p.y) if g == 2 else (p.y, p.z)
    return (p.z, p.x) if g == 2 else (p.x, p.z)


class Builder:
    def __init__(self, matdefs, seed=1):
        self.tiling = {m.name: m.tiling for m in matdefs}
        self.uvnorm = {m.name for m in matdefs if m.uv_space == 'normalized'}
        self.chunks = {}
        self.rng = random.Random(seed)
        self.lights = []
        self.fx = []
        self.preview = []       # (bm, material_name, matrix) for preview-only things

    def chunk(self, name, kind='hard'):
        if name not in self.chunks:
            self.chunks[name] = Chunk(name, kind)
        return self.chunks[name]

    def add(self, cname, bm, mats, M=None, uv='local', uvoff=True, smooth=True, kind='hard', free=True,
            grain=None):
        """uv: 'local' box projection in piece space, 'world' box projection in world space,
        'explicit' use the bmesh UV layer (metres, divided by tiling; normalized materials as-is)."""
        ch = self.chunk(cname, kind)
        if isinstance(mats, str):
            mats = [mats]
        midx = [ch.mi(m) for m in mats]
        bm.verts.index_update()
        bm.normal_update()
        base = len(ch.co)
        M = Matrix.Identity(4) if M is None else M
        R = M.to_3x3().normalized()
        wco = [M @ v.co for v in bm.verts]
        ch.co.extend([(p.x, p.y, p.z) for p in wco])
        uvl = bm.loops.layers.uv.active if uv == 'explicit' else None
        if uv == 'explicit' and uvl is None:
            uv = 'local'
        ou = ov = 0.0
        if uvoff:
            ou, ov = self.rng.uniform(0, 20), self.rng.uniform(0, 20)
        nm = len(mats)
        g = None
        if grain is not None and uv == 'local' and bm.verts:
            if grain == 'auto':
                ext = [max(v.co[i] for v in bm.verts) - min(v.co[i] for v in bm.verts) for i in range(3)]
                g = ext.index(max(ext))
            else:
                g = grain
        for f in bm.faces:
            k = min(f.material_index, nm - 1)
            mname = mats[k]
            t = self.tiling.get(mname, 2.0)
            ch.starts.append(len(ch.loops))
            ch.fmat.append(midx[k])
            ch.smooth.append(smooth)
            if uv == 'explicit':
                norm = mname in self.uvnorm
                for l in f.loops:
                    ch.loops.append(base + l.vert.index)
                    u, v = l[uvl].uv
                    ch.uv.append((u, v) if norm else ((u + ou) / t, (v + ov) / t))
            else:
                n = f.normal if uv == 'local' else (R @ f.normal)
                for l in f.loops:
                    ch.loops.append(base + l.vert.index)
                    p = l.vert.co if uv == 'local' else wco[l.vert.index]
                    a, b = _proj(p, n) if g is None else _proj_grain(p, n, g)
                    ch.uv.append(((a + ou) / t, (b + ov) / t))
        if free:
            bm.free()

    def light(self, pos, color, intensity, rng_m):
        self.lights.append({"pos": [round(x, 3) for x in pos], "color": [round(c, 3) for c in color],
                            "intensity": float(intensity), "range": float(rng_m)})

    def add_fx(self, kind, pos, scale=1.0):
        self.fx.append({"type": kind, "pos": [round(x, 3) for x in pos], "scale": float(scale)})

    def tri_count(self):
        tot = 0
        per = {}
        for name, ch in self.chunks.items():
            n = 0
            starts = ch.starts + [len(ch.loops)]
            for i in range(len(ch.starts)):
                n += starts[i + 1] - starts[i] - 2
            per[name] = n
            tot += n
        return tot, per

    def finalize(self, coll, materials, sharp_deg=48.0):
        objs = []
        for name, ch in self.chunks.items():
            if not ch.starts:
                continue
            me = bpy.data.meshes.new(name)
            co = np.array(ch.co, np.float32).ravel()
            me.vertices.add(len(ch.co))
            me.vertices.foreach_set('co', co)
            me.loops.add(len(ch.loops))
            me.loops.foreach_set('vertex_index', np.array(ch.loops, np.int32))
            me.polygons.add(len(ch.starts))
            me.polygons.foreach_set('loop_start', np.array(ch.starts, np.int32))
            me.update(calc_edges=True)
            uvl = me.uv_layers.new(name='UVMap')
            uvl.data.foreach_set('uv', np.array(ch.uv, np.float32).ravel())
            for m in ch.mats:
                me.materials.append(materials[m])
            me.polygons.foreach_set('material_index', np.array(ch.fmat, np.int32))
            me.polygons.foreach_set('use_smooth', np.array(ch.smooth, bool))
            ang = {'hard': sharp_deg, 'soft': 75.0, 'flat': 1.0}.get(ch.kind, sharp_deg)
            try:
                me.set_sharp_from_angle(angle=math.radians(ang))
            except Exception as e:
                log('set_sharp_from_angle failed', e)
            me.validate(clean_customdata=False)
            ob = bpy.data.objects.new(name, me)
            coll.objects.link(ob)
            if ch.kind == 'hard':
                md = ob.modifiers.new('WeightedNormals', 'WEIGHTED_NORMAL')
                md.mode = 'FACE_AREA'
                md.weight = 50
                md.keep_sharp = True
            objs.append(ob)
        return objs


# ----------------------------------------------------------------------------------------------
# transforms
# ----------------------------------------------------------------------------------------------
def TRS(t=(0, 0, 0), r=(0, 0, 0), s=None):
    M = Matrix.Translation(Vector(t)) @ Euler(r, 'XYZ').to_matrix().to_4x4()
    if s is not None:
        M = M @ Matrix.Diagonal((s, s, s, 1)) if np.isscalar(s) else M @ Matrix.Diagonal((s[0], s[1], s[2], 1))
    return M


def rotz(a):
    return Matrix.Rotation(a, 4, 'Z')


def look_rot(direction, up=(0, 0, 1)):
    d = Vector(direction).normalized()
    return d.to_track_quat('Y', 'Z').to_matrix().to_4x4()


# ----------------------------------------------------------------------------------------------
# masonry
# ----------------------------------------------------------------------------------------------
class Opening:
    """Arched opening in a wall (local wall x). kind: 'pointed' (k = radius/span, 1 = equilateral,
    >1 lancet), 'round' (semicircle), 'rect'."""

    def __init__(self, cx, w, sill, spring, k=1.0, ring=0.32, kind='pointed', hood=True, shafts=False,
                 tracery=None, sill_stone=True, nv=None):
        self.cx, self.w, self.sill, self.spring = cx, w, sill, spring
        self.kind = kind
        self.r = w / 2 if kind == 'round' else max(k * w, w / 2)
        self.ring = ring
        self.hood, self.shafts, self.tracery = hood, shafts, tracery
        self.sill_stone = sill_stone and sill > 0.05
        self.nv = nv
        self.off = self.r - w / 2
        self.apex = spring + (math.sqrt(self.r ** 2 - self.off ** 2) if kind != 'rect' else 0)
        R = self.r + ring
        self.apex_out = spring + (math.sqrt(R ** 2 - self.off ** 2) if kind != 'rect' else ring)

    def hw(self, z):
        """Half width excluded for coursed blocks at height z (None = no exclusion)."""
        if z < self.sill - 1e-6:
            return None
        if self.kind == 'rect':
            if z <= self.spring + 1e-6:
                return self.w / 2
            if z <= self.spring + self.ring:
                return self.w / 2 + 0.25
            return None
        if z <= self.spring + 1e-6:
            return self.w / 2
        h = z - self.spring
        R = self.r + self.ring
        if h >= math.sqrt(R ** 2 - self.off ** 2) - 1e-6:
            return None
        return math.sqrt(R ** 2 - h * h) - self.off

    def inner_hw(self, z):
        if self.kind == 'rect':
            return self.w / 2
        h = z - self.spring
        if h <= 0:
            return self.w / 2
        if h >= self.apex - self.spring:
            return 0.0
        return math.sqrt(self.r ** 2 - h * h) - self.off


def arch_points(cx, spring, r, off, n, outer=0.0, side=-1):
    """Points along one side of a pointed arch (side -1 left, +1 right) from springing to apex,
    for a curve of radius r+outer around centre (cx - side*off, spring)."""
    R = r + outer
    ccx = cx - side * off
    apex_h = math.sqrt(max(R * R - off * off, 0.0))
    th_a = math.atan2(apex_h, side * off)   # angle at apex relative to centre
    th0 = 0.0 if side > 0 else math.pi
    pts = []
    for i in range(n + 1):
        th = th0 + (th_a - th0) * i / n
        pts.append((ccx + R * math.cos(th), spring + R * math.sin(th)))
    pts[-1] = (cx, spring + apex_h)
    return pts


def build_arch(B, cname, M, op, depth, y0, mat, rng, bevel=0.03, n=None, top_fn=None, ring=None,
               protrude=0.0):
    """Voussoir ring for opening op. Wall-local coordinates: x along wall, y thickness, z up.
    y0 = centre of the ring in y."""
    ring = op.ring if ring is None else ring
    if op.kind == 'rect':
        # lintel
        L = op.w + 0.5
        bm = bm_box(L, depth, ring, bevel)
        B.add(cname, bm, mat, M @ TRS((op.cx, y0, op.spring + ring / 2)))
        return
    span_len = (op.apex - op.spring) * 1.6 + op.w * 0.6
    n = n or max(3, int(round(span_len / 0.45 / 2)) + 1)
    # which voussoirs survive: a side stops at its first broken stone; if one side is broken the
    # other side can only stand up to ~60% (a half arch cannot carry its crown)
    keep = {}
    for side in (-1, 1):
        pin = arch_points(op.cx, op.spring, op.r, op.off, n, 0.0, side)
        pout = arch_points(op.cx, op.spring, op.r, op.off, n, ring, side)
        k = n
        if top_fn is not None:
            for i in range(n):
                mz = (pin[i][1] + pin[i + 1][1] + pout[i][1] + pout[i + 1][1]) / 4
                mx = (pin[i][0] + pin[i + 1][0] + pout[i][0] + pout[i + 1][0]) / 4
                if mz > top_fn(mx) - 0.1:
                    k = i
                    break
        keep[side] = k
    if min(keep.values()) < n:
        for s in keep:
            keep[s] = min(keep[s], int(n * 0.6))
    for side in (-1, 1):
        pin = arch_points(op.cx, op.spring, op.r, op.off, n, 0.0, side)
        pout = arch_points(op.cx, op.spring, op.r, op.off, n, ring, side)
        for i in range(n):
            a0, a1 = pin[i], pin[i + 1]
            b0, b1 = pout[i], pout[i + 1]
            mz = (a0[1] + a1[1] + b0[1] + b1[1]) / 4
            mx = (a0[0] + a1[0] + b0[0] + b1[0]) / 4
            if i > keep[side]:
                continue
            broken = i == keep[side]
            if broken and n - keep[side] <= 0:
                continue
            yy0, yy1 = y0 - depth / 2, y0 + depth / 2 + protrude
            q = [(a0[0], yy0, a0[1]), (b0[0], yy0, b0[1]), (b1[0], yy0, b1[1]), (a1[0], yy0, a1[1]),
                 (a0[0], yy1, a0[1]), (b0[0], yy1, b0[1]), (b1[0], yy1, b1[1]), (a1[0], yy1, a1[1])]
            # shrink slightly for joints
            cxq = sum(p[0] for p in q) / 8
            czq = sum(p[2] for p in q) / 8
            q = [(cxq + (p[0] - cxq) * 0.985, p[1], czq + (p[2] - czq) * 0.985) for p in q]
            bm = bm_hex(q, bevel)
            if broken:
                if i >= n:
                    continue
                c = Vector((mx, 0, mz))
                d = Vector((b1[0] - b0[0], 0, b1[1] - b0[1])).normalized()
                bm_rough_cut(bm, c + d * rng.uniform(-0.05, 0.1), d + Vector((0, rng.uniform(-.3, .3), 0)), rng,
                             n=2, spread=0.05, tilt=0.4)
            if rng.random() < 0.2:
                bm_chip(bm, rng, 1, (0.02, 0.05))
            B.add(cname, bm, mat, M)
    return keep, n


def build_tracery(B, cname, M, op, y0, mat, rng, top_fn=None, bar=0.13, depth=0.22, oculus=True):
    """Simple gothic tracery: central mullion + two sub-arches + oculus ring."""
    w = op.w
    # the tracery head only survives if the whole window head is intact
    tmin = min(top_fn(op.cx + t * w / 2) for t in (-1, -0.5, 0, 0.5, 1)) if top_fn is not None else 1e9
    intact = tmin > op.apex_out + 0.1
    # mullion
    zt = op.spring + 0.05
    if top_fn is None or op.sill < tmin:
        h = zt - op.sill
        if top_fn is not None:
            h = min(h, tmin - op.sill - 0.3)
        if h > 0.2:
            bm = bm_box(bar, depth, h, 0.015)
            if top_fn is not None and op.sill + h < zt:
                bm_rough_cut(bm, (0, 0, h / 2 - 0.05), (0.3, 0, 1), rng, 2)
            B.add(cname, bm, mat, M @ TRS((op.cx, y0, op.sill + h / 2)))
    # two lancet sub arches
    sw = (w - bar) / 2
    if not intact:
        return
    for s in (-1, 1):
        sub = Opening(op.cx + s * (bar / 2 + sw / 2), sw, op.sill, op.spring, k=1.0, ring=bar)
        build_arch(B, cname, M, sub, depth, y0, mat, rng, bevel=0.012, n=4, top_fn=top_fn)
    if oculus:
        cz = op.spring + (op.apex - op.spring) * 0.58 + sw * 0.25
        rr = min(sw * 0.55, (op.apex - cz) * 0.7)
        if rr > 0.15 and (top_fn is None or cz < top_fn(op.cx)):
            nseg = 12
            for i in range(nseg):
                a0, a1 = TAU * i / nseg, TAU * (i + 1) / nseg
                pts = []
                for (rad, a) in ((rr, a0), (rr + bar * 0.8, a0), (rr + bar * 0.8, a1), (rr, a1)):
                    pts.append((op.cx + rad * math.cos(a), cz + rad * math.sin(a)))
                q = [(p[0], y0 - depth / 2, p[1]) for p in pts] + [(p[0], y0 + depth / 2, p[1]) for p in pts]
                if top_fn is not None and max(p[2] for p in q) > top_fn(op.cx):
                    continue
                B.add(cname, bm_hex(q, 0.01), mat, M)


def masonry_wall(B, cname, M, length, thick, top_fn, openings=(), course=(0.32, 0.5), blen=(0.55, 1.25),
                 bevel=0.03, mat='M_Stone', rng=None, jitter=0.01, protrude=0.025, chip=0.3, z0=0.0,
                 holes=0.0, ring_mat=None, end_l=True, end_r=True, snap=(), arch_bevel=None, plinth=None):
    """Coursed ashlar wall in local frame M: x in [0,length], y in [-thick/2, thick/2], z from z0 up.
    top_fn(x) -> local ruin height. Returns list of (x, z_top) samples useful for rubble."""
    rng = rng or random.Random(1)
    ring_mat = ring_mat or mat
    # course boundaries snapped to sills / springs
    special = sorted(set([o.sill for o in openings if o.sill > z0 + 0.1] +
                         [o.spring for o in openings] + list(snap)))
    zmax = max(top_fn(x) for x in np.linspace(0, length, 64)) + 0.5
    bounds = [z0]
    z = z0
    while z < zmax:
        h = rng.uniform(*course)
        nz = z + h
        for s in special:
            if z + 0.12 < s < nz + 0.18:
                nz = s
                break
        if nz - z < 0.12:
            nz = z + 0.12
        bounds.append(nz)
        z = nz
    for ci in range(len(bounds) - 1):
        za, zb = bounds[ci], bounds[ci + 1]
        # gather cuts (x intervals blocked by openings) with bottom/top edges
        cuts = []
        for o in openings:
            hb = o.hw(za + 1e-4)
            ht = o.hw(zb - 1e-4)
            if hb is None and ht is None:
                continue
            if hb is None:
                continue
            if ht is None:
                ht = 0.0
            cuts.append((o.cx - hb, o.cx - ht, o.cx + hb, o.cx + ht))
        cuts.sort()
        segs = []
        prev = (0.0, 0.0)
        for c in cuts:
            segs.append((prev, (c[0], c[1])))
            prev = (c[2], c[3])
        segs.append((prev, (length, length)))
        for (l0, l1), (r0, r1) in segs:
            wid = min(r0, r1) - max(l0, l1)
            if wid < 0.06:
                continue
            # lay blocks along bottom edge
            stagger = rng.uniform(0.0, 0.5) if ci % 2 else rng.uniform(0.5, 1.0)
            edges_b = [l0]
            edges_t = [l1]
            xcur = max(l0, l1)
            first_len = rng.uniform(*blen) * stagger + 0.2
            xn = xcur + first_len
            right = min(r0, r1)
            while xn < right - blen[0] * 0.6:
                edges_b.append(xn)
                edges_t.append(xn)
                xn += rng.uniform(*blen)
            edges_b.append(r0)
            edges_t.append(r1)
            for k in range(len(edges_b) - 1):
                xa0, xb0 = edges_b[k], edges_b[k + 1]
                xa1, xb1 = edges_t[k], edges_t[k + 1]
                xm = (xa0 + xb0 + xa1 + xb1) / 4
                t = top_fn(xm)
                if za > t - 0.06:
                    continue
                if holes > 0 and zb > t - 1.2 and rng.random() < holes:
                    continue
                g = 0.004
                pr = rng.uniform(-protrude, protrude)
                ya, yb = -thick / 2 + rng.uniform(0, 0.015), thick / 2 + pr
                q = [(xa0 + g, ya, za + g), (xb0 - g, ya, za + g), (xb0 - g, yb, za + g), (xa0 + g, yb, za + g),
                     (xa1 + g, ya, zb - g), (xb1 - g, ya, zb - g), (xb1 - g, yb, zb - g), (xa1 + g, yb, zb - g)]
                bm = bm_hex(q, bevel * rng.uniform(0.7, 1.3))
                if zb > t:
                    bm_rough_cut(bm, (xm + rng.uniform(-0.1, 0.1), 0, t),
                                 (rng.uniform(-0.5, 0.5), rng.uniform(-0.3, 0.3), 1), rng, n=2, spread=0.05)
                elif chip > 0 and rng.random() < chip:
                    bm_chip(bm, rng, rng.randint(1, 2))
                if jitter > 0:
                    c = Vector((xm, 0, (za + zb) / 2))
                    R = Euler((rng.uniform(-jitter, jitter), rng.uniform(-jitter, jitter) * 0.5,
                               rng.uniform(-jitter, jitter) * 0.5)).to_matrix().to_4x4()
                    Mj = Matrix.Translation(c) @ R @ Matrix.Translation(-c)
                    bmesh.ops.transform(bm, matrix=Mj, verts=bm.verts)
                B.add(cname, bm, mat, M)
    # arches, hoods, shafts, sills, tracery
    for o in openings:
        if o.kind == 'rect':
            build_arch(B, cname, M, o, thick + 0.04, 0.0, ring_mat, rng, top_fn=top_fn)
            continue
        if o.spring < top_fn(o.cx) or o.spring < top_fn(o.cx - o.w / 2) or o.spring < top_fn(o.cx + o.w / 2):
            keep, nv = build_arch(B, cname, M, o, thick + 0.05, 0.0, ring_mat, rng, bevel=arch_bevel or bevel,
                                  n=o.nv, top_fn=top_fn)
            if o.hood:
                # hood mould: thin ring outside the main ring, proud of the front face
                for side in (-1, 1):
                    pin = arch_points(o.cx, o.spring, o.r, o.off, 8, o.ring - 0.02, side)
                    pout = arch_points(o.cx, o.spring, o.r, o.off, 8, o.ring + 0.12, side)
                    for i in range(8):
                        a0, a1, b0, b1 = pin[i], pin[i + 1], pout[i], pout[i + 1]
                        mx = (a0[0] + b1[0]) / 2
                        mz = (a0[1] + b1[1]) / 2
                        if mz > top_fn(mx) or (i + 1) / 8 > keep[side] / nv:
                            continue
                        y1 = thick / 2 + 0.12
                        y0 = thick / 2 - 0.05
                        q = [(a0[0], y0, a0[1]), (b0[0], y0, b0[1]), (b1[0], y0, b1[1]), (a1[0], y0, a1[1]),
                             (a0[0], y1, a0[1]), (b0[0], y1, b0[1]), (b1[0], y1, b1[1]), (a1[0], y1, a1[1])]
                        B.add(cname, bm_hex(q, 0.02), ring_mat, M)
                # label stops
                for s in (-1, 1):
                    x = o.cx + s * (o.w / 2 + o.ring + 0.05)
                    if o.spring < top_fn(x):
                        B.add(cname, bm_box(0.24, 0.2, 0.24, 0.03), ring_mat,
                              M @ TRS((x, thick / 2 + 0.06, o.spring - 0.05)))
        if o.shafts:
            for s in (-1, 1):
                x = o.cx + s * (o.w / 2 + 0.02)
                top = min(o.spring, top_fn(x))
                h = top - o.sill
                if h < 0.3:
                    continue
                for yy in (thick / 2 - 0.02, -thick / 2 + 0.02):
                    bm = bm_cyl(0.11, 0.11, h - 0.25, 10)
                    if top < o.spring:
                        bm_rough_cut(bm, (0, 0, h - 0.35), (rng.uniform(-.5, .5), 0, 1), rng, 2)
                    B.add(cname, bm, ring_mat, M @ TRS((x, yy, o.sill + 0.15)), kind='hard')
                    # base + capital
                    B.add(cname, bm_box(0.3, 0.3, 0.15, 0.03), ring_mat, M @ TRS((x, yy, o.sill + 0.075)))
                    if top >= o.spring - 0.05:
                        cap = bm_lathe([(0.12, 0), (0.13, 0.08), (0.2, 0.18), (0.22, 0.24), (0.22, 0.26)], 10)
                        B.add(cname, cap, ring_mat, M @ TRS((x, yy, o.spring - 0.26)), uv='local')
        if o.sill_stone and o.sill < top_fn(o.cx):
            bm = bm_box(o.w + 0.3, thick + 0.16, 0.14, 0.03)
            B.add(cname, bm, ring_mat, M @ TRS((o.cx, 0.04, o.sill - 0.06)))
        if o.tracery:
            build_tracery(B, cname, M, o, 0.0, ring_mat, rng, top_fn=top_fn, oculus=o.tracery == 'oculus')
    if plinth:
        ph, pd = plinth
        x = 0.0
        while x < length - 0.05:
            L = min(rng.uniform(0.8, 1.5), length - x)
            ok = True
            for o in openings:
                if o.sill < 0.05 and abs(x + L / 2 - o.cx) < o.w / 2 + L / 2:
                    ok = False
            if ok and top_fn(x + L / 2) > ph:
                bm = bm_box(L - 0.01, thick + 2 * pd, ph, bevel)
                bm_cut(bm, (0, thick / 2 + pd, ph / 2), (0, 0.6, 0.8))
                B.add(cname, bm, mat, M @ TRS((x + L / 2, 0, z0 + ph / 2)))
            x += L
    return bounds


def ring_wall(B, cname, cx, cy, r, thick, h, rng, mat, course=(0.45, 0.6), blen=1.0, z0=0.0, bevel=0.03,
              slits=(), gaps=(), protrude=0.02, chip=0.25):
    """Round tower shell of coursed curved blocks (outer radius r).
    slits: [(angle, z_bottom, z_top, half_width_m)] narrow openings; gaps: [(a0, a1)] angular ranges left open."""
    z = z0
    while z < h - 0.05:
        ch = min(rng.uniform(*course), h - z)
        if h - (z + ch) < 0.15:
            ch = h - z
        n = max(6, int(TAU * r / blen))
        off = rng.random()
        for k in range(n):
            a0 = TAU * (k + off) / n
            a1 = TAU * (k + 1 + off) / n
            am = (a0 + a1) / 2
            skip = False
            for g0, g1 in gaps:
                d0 = (am - g0) % TAU
                if d0 < (g1 - g0) % TAU:
                    skip = True
            if skip:
                continue
            spans = [(a0, a1)]
            for (sa, sz0, sz1, shw) in slits:
                if z + ch > sz0 and z < sz1:
                    da = shw / r
                    rel = (sa - a0) % TAU
                    if rel < (a1 - a0):
                        sa_abs = a0 + rel
                        spans = [(a0, sa_abs - da), (sa_abs + da, a1)]
            ro = r + rng.uniform(-protrude, protrude)
            ri = r - thick
            for (b0, b1) in spans:
                if b1 - b0 < 0.02:
                    continue
                g = 0.004 / r
                b0g, b1g = b0 + g, b1 - g
                q = []
                for zz in (z + 0.003, z + ch - 0.003):
                    q += [(cx + ri * math.cos(b0g), cy + ri * math.sin(b0g), zz),
                          (cx + ro * math.cos(b0g), cy + ro * math.sin(b0g), zz),
                          (cx + ro * math.cos(b1g), cy + ro * math.sin(b1g), zz),
                          (cx + ri * math.cos(b1g), cy + ri * math.sin(b1g), zz)]
                bm = bm_hex(q, bevel * rng.uniform(0.7, 1.3))
                if chip > 0 and rng.random() < chip:
                    bm_chip(bm, rng, 1, (0.02, 0.06))
                B.add(cname, bm, mat)
        z += ch
    return z


def ring_merlons(B, cname, cx, cy, r, thick, z, rng, mat, mw=1.0, gw=0.65, mh=1.4, base=0.5, corbel=0.0,
                 bevel=0.03):
    """Parapet + merlons around a round tower top. corbel>0 pushes the parapet outward on corbels."""
    ro = r + corbel
    if corbel > 0:
        n = max(8, int(TAU * r / 0.7))
        for k in range(n):
            a = TAU * (k + 0.5) / n
            bm = bm_box(0.35, corbel + 0.3, 0.6, 0.02)
            bm_cut(bm, (0, corbel / 2 + 0.15, -0.3), (0, 0.6, -0.8))
            B.add(cname, bm, mat, TRS((cx + (r + corbel / 2 - 0.15) * math.cos(a), cy + (r + corbel / 2 - 0.15) * math.sin(a),
                                       z - 0.3), (0, 0, a - math.pi / 2)))
    ring_wall(B, cname, cx, cy, ro, thick * 0.5 + corbel, z + base, rng, mat, course=(base, base), blen=1.2, z0=z,
              bevel=bevel, chip=0.1)
    n = max(6, int(TAU * ro / (mw + gw)))
    for k in range(n):
        a0 = TAU * k / n
        a1 = a0 + mw / ro
        q = []
        ri = ro - thick * 0.45
        for zz in (z + base, z + base + mh * rng.uniform(0.95, 1.05)):
            q += [(cx + ri * math.cos(a0), cy + ri * math.sin(a0), zz), (cx + ro * math.cos(a0), cy + ro * math.sin(a0), zz),
                  (cx + ro * math.cos(a1), cy + ro * math.sin(a1), zz), (cx + ri * math.cos(a1), cy + ri * math.sin(a1), zz)]
        bm = bm_hex(q, bevel)
        if rng.random() < 0.3:
            bm_chip(bm, rng, 1, (0.03, 0.08))
        B.add(cname, bm, mat)


def merlons(B, cname, M, length, z, thick, rng, mat, mw=1.0, gw=0.7, mh=1.4, base=0.0, bevel=0.03, y=0.0):
    """Straight crenellation along local x of M (0..length), centred at local y."""
    if base > 0:
        x = 0.0
        while x < length - 0.05:
            L = min(rng.uniform(0.8, 1.4), length - x)
            B.add(cname, bm_box(L - 0.006, thick, base, bevel), mat, M @ TRS((x + L / 2, y, z + base / 2)))
            x += L
    if mh <= 0:
        return
    n = max(1, int((length + gw) / (mw + gw)))
    pitch = length / n
    for k in range(n):
        x = (k + 0.5) * pitch
        hh = mh * rng.uniform(0.96, 1.04)
        bm = bm_box(mw, thick, hh, bevel)
        if rng.random() < 0.3:
            bm_chip(bm, rng, 1, (0.03, 0.08))
        B.add(cname, bm, mat, M @ TRS((x, y, z + base + hh / 2), (0, 0, rng.uniform(-0.01, 0.01))))


def snow_on_top(B, cname, x, y, z, sx, sy, rng, depth=0.08, mat='M_Snow', rot=0.0, overhang=0.02):
    """A soft snow pillow sitting on a flat top of size sx*sy at height z."""
    n = 8
    bm = bmesh.new()
    seed = rng.uniform(0, 100)
    vs = {}
    for j in range(n + 1):
        for i in range(n + 1):
            u, v = i / n * 2 - 1, j / n * 2 - 1
            e = max(abs(u), abs(v))
            prof = max(0.0, 1 - e ** 6)
            hz = depth * prof * (1 + 0.3 * mnoise.noise(Vector((u * 2 + seed, v * 2, seed))))
            vs[i, j] = bm.verts.new((u * (sx / 2 + overhang), v * (sy / 2 + overhang), hz))
    for j in range(n):
        for i in range(n):
            bm.faces.new((vs[i, j], vs[i + 1, j], vs[i + 1, j + 1], vs[i, j + 1]))
    B.add(cname, bm, mat, TRS((x, y, z - 0.005), (0, 0, rot)), uv='world', uvoff=False, kind='soft')


def cone_roof(B, cname, cx, cy, z, r, h, rng, mat, snow_mat=None, segs=24, overhang=0.5, finial_mat=None):
    prof = [(r + overhang, -0.1), (r + overhang, 0.0), (r * 0.72, h * 0.3), (r * 0.36, h * 0.66), (0.05, h)]
    bm = bm_lathe(prof, segs, cap_bottom=True, cap_top=False)
    B.add(cname, bm, mat, TRS((cx, cy, z)), uv='explicit', kind='soft')
    if snow_mat:
        # snow patches on the lower part of the cone
        bm = bmesh.new()
        uvl = bm.loops.layers.uv.new('UVMap')
        rows = 10
        ring = []
        for j in range(rows + 1):
            t = j / rows * 0.86
            rr = (r + overhang) * (1 - t) + 0.05 * t + 0.04
            zz = h * t + 0.04
            ring.append([bm.verts.new((cx + rr * math.cos(TAU * i / segs), cy + rr * math.sin(TAU * i / segs), z + zz))
                         for i in range(segs)])
        seed = rng.uniform(0, 50)
        for j in range(rows):
            for i in range(segs):
                a = TAU * (i + 0.5) / segs
                nz = mnoise.noise(Vector((math.cos(a) * 2.5 + seed, math.sin(a) * 2.5, j * 0.35)))
                if nz + 0.3 < 0:
                    continue
                f = bm.faces.new((ring[j][i], ring[j][(i + 1) % segs], ring[j + 1][(i + 1) % segs], ring[j + 1][i]))
                for l in f.loops:
                    l[uvl].uv = (l.vert.co.x, l.vert.co.y)
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
        if bm.faces:
            bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.06)
            B.add(cname, bm, snow_mat, uv='world', uvoff=False, kind='soft')
        else:
            bm.free()
    if finial_mat:
        B.add(cname, bm_cyl(0.05, 0.03, 1.6, 6), finial_mat, TRS((cx, cy, z + h - 0.2)), kind='soft')
        B.add(cname, bm_sphere(0.12, 8, 6), finial_mat, TRS((cx, cy, z + h + 0.3)), kind='soft')


def ruin_profile(length, base, peaks, rng, rough=0.6, seed=0):
    """Returns top_fn(x): piecewise-linear interpolation of control heights + jagged noise."""
    xs = [p[0] for p in peaks]
    hs = [p[1] for p in peaks]
    off = seed * 3.7

    def f(x):
        h = float(np.interp(x, xs, hs)) if peaks else base
        h += rough * (mnoise.noise(Vector((x * 0.9 + off, off, 0.5))) + 0.5 * mnoise.noise(Vector((x * 2.7, off, 1.5))))
        return h
    return f


def column_drums(B, cname, M, h, r, rng, mat, drum=(0.45, 0.8), segs=14, flutes=0, break_top=True, bevel=0.02,
                 entasis=0.0):
    """Stack of drums from z=0..h (broken top)."""
    z = 0.0
    while z < h - 0.05:
        dh = min(rng.uniform(*drum), h - z)
        rr0 = r * (1 - entasis * z / max(h, 1))
        rr1 = r * (1 - entasis * (z + dh) / max(h, 1))
        bm = bm_cyl(rr0, rr1, dh - 0.01, segs)
        if bevel > 0:
            ring_edges = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) < 1e-5 and
                          len(e.link_faces) == 2 and any(len(f.verts) > 4 for f in e.link_faces)]
            if ring_edges:
                bmesh.ops.bevel(bm, geom=ring_edges, offset=bevel, segments=1, affect='EDGES', clamp_overlap=True)
        last = z + dh >= h - 0.05
        if last and break_top:
            bm_rough_cut(bm, (0, 0, dh * rng.uniform(0.5, 0.85)), (rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), 1),
                         rng, n=3, spread=0.08, tilt=0.5)
        if rng.random() < 0.35:
            bm_chip(bm, rng, 1, (0.03, 0.08))
        Rz = rng.uniform(0, TAU)
        B.add(cname, bm, mat, M @ TRS((0, 0, z), (rng.uniform(-0.01, 0.01), rng.uniform(-0.01, 0.01), Rz)))
        z += dh


# ----------------------------------------------------------------------------------------------
# preview materials / world / lights / camera
# ----------------------------------------------------------------------------------------------
def make_materials(matdefs, tex_dir, fog):
    """Principled materials using the baked textures (+ Unity-like linear fog for camera rays)."""
    mats = {}
    for m in matdefs:
        mat = bpy.data.materials.get(m.name) or bpy.data.materials.new(m.name)
        try:
            mat.use_nodes = True
        except Exception:
            pass
        nt = mat.node_tree
        nt.nodes.clear()
        L = nt.links.new
        a, n, k = (os.path.join(tex_dir, x) for x in m.tex_names())
        ta = nt.nodes.new('ShaderNodeTexImage')
        ta.image = bpy.data.images.load(a, check_existing=True)
        ta.image.colorspace_settings.name = 'sRGB'
        tn = nt.nodes.new('ShaderNodeTexImage')
        tn.image = bpy.data.images.load(n, check_existing=True)
        tn.image.colorspace_settings.name = 'Non-Color'
        tk = nt.nodes.new('ShaderNodeTexImage')
        tk.image = bpy.data.images.load(k, check_existing=True)
        tk.image.colorspace_settings.name = 'Non-Color'
        tk.image.alpha_mode = 'CHANNEL_PACKED'
        bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        tint = nt.nodes.new('ShaderNodeMix')
        tint.data_type = 'RGBA'
        tint.blend_type = 'MULTIPLY'
        tint.inputs['Factor'].default_value = 1.0
        sock = {s.identifier: s for s in tint.inputs}
        L(ta.outputs['Color'], sock['A_Color'])
        sock['B_Color'].default_value = s2l(m.tint) + (1.0,)
        outc = [s for s in tint.outputs if s.identifier == 'Result_Color'][0]
        L(outc, bsdf.inputs['Base Color'])
        nm = nt.nodes.new('ShaderNodeNormalMap')
        L(tn.outputs['Color'], nm.inputs['Color'])
        L(nm.outputs['Normal'], bsdf.inputs['Normal'])
        sep = nt.nodes.new('ShaderNodeSeparateColor')
        L(tk.outputs['Color'], sep.inputs[0])
        L(sep.outputs[0], bsdf.inputs['Metallic'])
        sm = nt.nodes.new('ShaderNodeMath')
        sm.operation = 'MULTIPLY'
        L(tk.outputs['Alpha'], sm.inputs[0])
        sm.inputs[1].default_value = m.smoothness_scale
        rf = nt.nodes.new('ShaderNodeMath')
        rf.operation = 'SUBTRACT'
        rf.inputs[0].default_value = 1.0
        L(sm.outputs[0], rf.inputs[1])
        L(rf.outputs[0], bsdf.inputs['Roughness'])
        if m.emission is not None and m.emission_intensity > 0:
            em = nt.nodes.new('ShaderNodeMix')
            em.data_type = 'RGBA'
            em.blend_type = 'MULTIPLY'
            em.inputs['Factor'].default_value = 1.0
            es = {s.identifier: s for s in em.inputs}
            L(ta.outputs['Color'], es['A_Color'])
            es['B_Color'].default_value = s2l(m.emission) + (1.0,)
            L([s for s in em.outputs if s.identifier == 'Result_Color'][0], bsdf.inputs['Emission Color'])
            bsdf.inputs['Emission Strength'].default_value = m.emission_intensity
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        if fog:
            shader = fog_mix(nt, bsdf.outputs[0], fog)
            L(shader, out.inputs['Surface'])
        else:
            L(bsdf.outputs[0], out.inputs['Surface'])
        mats[m.name] = mat
    return mats


def fog_mix(nt, shader_out, fog):
    """Unity linear fog for camera rays: lerp(lit, fogColor, saturate((depth-start)/(end-start)))."""
    L = nt.links.new
    cam = nt.nodes.new('ShaderNodeCameraData')
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.clamp = True
    L(cam.outputs['View Z Depth'], mr.inputs['Value'])
    mr.inputs['From Min'].default_value = fog['start']
    mr.inputs['From Max'].default_value = fog['end']
    lp = nt.nodes.new('ShaderNodeLightPath')
    mul = nt.nodes.new('ShaderNodeMath')
    mul.operation = 'MULTIPLY'
    L(mr.outputs['Result'], mul.inputs[0])
    L(lp.outputs['Is Camera Ray'], mul.inputs[1])
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = s2l(fog['color']) + (1.0,)
    mix = nt.nodes.new('ShaderNodeMixShader')
    L(mul.outputs[0], mix.inputs[0])
    L(shader_out, mix.inputs[1])
    L(em.outputs[0], mix.inputs[2])
    return mix.outputs[0]


def emissive_material(name, color_srgb, strength, fog=None):
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = s2l(color_srgb) + (1.0,)
    em.inputs['Strength'].default_value = strength
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    if fog:
        nt.links.new(fog_mix(nt, em.outputs[0], fog), out.inputs['Surface'])
    else:
        nt.links.new(em.outputs[0], out.inputs['Surface'])
    return mat


def plain_material(name, color_srgb, rough=0.6, fog=None):
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    b.inputs['Base Color'].default_value = s2l(color_srgb) + (1.0,)
    b.inputs['Roughness'].default_value = rough
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(fog_mix(nt, b.outputs[0], fog) if fog else b.outputs[0], out.inputs['Surface'])
    return mat


def sun_vectors(pitch, yaw):
    """Unity directional light Euler (pitch about X, yaw about Y) -> travel direction in Unity and
    Blender coordinates. Unity forward = (sin(yaw)cos(pitch), -sin(pitch), cos(yaw)cos(pitch));
    Blender = (-ux, -uz, uy)."""
    p, y = math.radians(pitch), math.radians(yaw)
    u = (math.sin(y) * math.cos(p), -math.sin(p), math.cos(y) * math.cos(p))
    b = (-u[0], -u[2], u[1])
    return u, b


def setup_world_and_lights(layout, coll):
    sc = bpy.context.scene
    w = bpy.data.worlds.new('MapWorld')
    sc.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    nt.nodes.clear()
    L = nt.links.new
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    L(tc.outputs['Generated'], sep.inputs[0])
    ramp_n = nt.nodes.new('ShaderNodeValToRGB')
    amb = layout['ambient']
    cr = ramp_n.color_ramp
    cr.elements[0].position = 0.0
    cr.elements[0].color = s2l(amb['ground']) + (1,)
    cr.elements[1].position = 1.0
    cr.elements[1].color = s2l(amb['sky']) + (1,)
    e = cr.elements.new(0.5)
    e.color = s2l(amb['equator']) + (1,)
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value = -1
    mr.inputs['From Max'].default_value = 1
    L(sep.outputs[2], mr.inputs['Value'])
    L(mr.outputs['Result'], ramp_n.inputs['Fac'])
    bg_amb = nt.nodes.new('ShaderNodeBackground')
    L(ramp_n.outputs['Color'], bg_amb.inputs['Color'])
    bg_cam = nt.nodes.new('ShaderNodeBackground')
    bg_cam.inputs['Color'].default_value = s2l(layout['background']) + (1,)
    lp = nt.nodes.new('ShaderNodeLightPath')
    mix = nt.nodes.new('ShaderNodeMixShader')
    L(lp.outputs['Is Camera Ray'], mix.inputs[0])
    L(bg_amb.outputs[0], mix.inputs[1])
    L(bg_cam.outputs[0], mix.inputs[2])
    out = nt.nodes.new('ShaderNodeOutputWorld')
    L(mix.outputs[0], out.inputs['Surface'])
    # sun
    sun = layout['sun']
    _, d = sun_vectors(*sun['direction_deg'])
    ld = bpy.data.lights.new('Sun', 'SUN')
    ld.energy = math.pi * sun['intensity']
    ld.color = s2l(sun['color'])
    ld.angle = math.radians(sun.get('angle', 2.0))
    ob = bpy.data.objects.new('Sun', ld)
    ob.rotation_euler = Vector(d).to_track_quat('-Z', 'Y').to_euler()
    coll.objects.link(ob)
    for i, pl in enumerate(layout['pointLights']):
        ld = bpy.data.lights.new('PL%d' % i, 'POINT')
        ld.energy = 4 * math.pi ** 2 * pl['intensity']
        ld.color = s2l(pl['color'])
        ld.shadow_soft_size = 0.15
        ob = bpy.data.objects.new('PL%d' % i, ld)
        ob.location = pl['pos']
        coll.objects.link(ob)


def add_camera(name, pos, target, vfov_deg, coll):
    cd = bpy.data.cameras.new(name)
    cd.sensor_fit = 'VERTICAL'
    cd.angle_y = math.radians(vfov_deg)
    cd.clip_start = 0.1
    cd.clip_end = 1000
    ob = bpy.data.objects.new(name, cd)
    ob.location = pos
    d = Vector(target) - Vector(pos)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    coll.objects.link(ob)
    return ob


def render_still(cam, path, samples=96, res=(1600, 900)):
    sc = bpy.context.scene
    setup_cycles(sc, samples)
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = 'OPTIX'
    except Exception:
        pass
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 1
    sc.cycles.glossy_bounces = 2
    sc.cycles.transmission_bounces = 2
    sc.cycles.volume_bounces = 0
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.sample_clamp_indirect = 4.0
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    log('rendered %s (%.1fs)' % (os.path.basename(path), time.time() - t))


# ----------------------------------------------------------------------------------------------
# export
# ----------------------------------------------------------------------------------------------
def export_fbx(objs, path):
    bpy.context.view_layer.update()
    for o in bpy.data.objects:
        try:
            o.select_set(False)
        except Exception:
            pass
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'MESH', 'EMPTY'},
                             use_mesh_modifiers=True, mesh_smooth_type='OFF', use_tspace=False,
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
                             axis_forward='-Z', axis_up='Y', bake_space_transform=False,
                             add_leaf_bones=False, bake_anim=False, path_mode='STRIP', embed_textures=False)
    log('exported', path)


def write_json(path, data):
    with open(path, 'w', newline='\n') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
