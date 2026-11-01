"""
Shared helpers for building, rigging, texturing and exporting characters headlessly in Blender 5.x.

Coordinate convention (see CONVENTIONS.md): metres, Z up, characters face -Y, character's left is +X.
All part meshes are built directly in rest-pose world space with identity object transforms.
"""
import bpy, bmesh, math, os, sys, json, random
import numpy as np
from mathutils import Vector, Matrix, Euler, Quaternion, noise

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
FPS = 30


def log(*a):
    print("[charlib]", *a)
    sys.stdout.flush()


def script_args():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.render.fps = FPS
    scn.unit_settings.system = 'METRIC'
    return scn


def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


# ----------------------------------------------------------------------------------------------
# Mesh construction
# ----------------------------------------------------------------------------------------------

def mesh_obj(name, verts, faces, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.validate(clean_customdata=False)
    me.update()
    if smooth:
        me.shade_smooth()
    return link(bpy.data.objects.new(name, me))


def _se(v, n):
    """Superellipse shaping of a unit cos/sin value."""
    return math.copysign(abs(v) ** (2.0 / n), v)


def loft(name, rings, segs=32, arc=None, cap0=False, cap1=False, dfn=None, smooth=True):
    """
    Loft a tube along +Z through elliptical rings.
    ring: dict z, rx, ry (front, -Y side), ryb (back), cx, cy, n (superellipse exponent, 2 = ellipse).
    arc: optional (a0, a1) in degrees for an open shell; angles from +X counter-clockwise, front (-Y) = -90.
    dfn(angle_deg, ring_index, point) -> Vector offset, for sculpting ridges and dents.
    """
    full = arc is None
    if full:
        angs = [2 * math.pi * i / segs for i in range(segs)]
    else:
        a0, a1 = math.radians(arc[0]), math.radians(arc[1])
        angs = [a0 + (a1 - a0) * i / segs for i in range(segs + 1)]
    m = len(angs)
    verts, faces = [], []
    for ri, r in enumerate(rings):
        rx = r['rx']; ry = r.get('ry', rx); ryb = r.get('ryb', ry)
        cx = r.get('cx', 0.0); cy = r.get('cy', 0.0); n = r.get('n', 2.0)
        for a in angs:
            c, s = math.cos(a), math.sin(a)
            p = Vector((cx + rx * _se(c, n), cy + (ry if s < 0 else ryb) * _se(s, n), r['z']))
            if dfn:
                p += Vector(dfn(math.degrees(a), ri, p))
            verts.append(p)
    for i in range(len(rings) - 1):
        for j in range(m if full else m - 1):
            a, b = i * m + j, i * m + (j + 1) % m
            faces.append((a, b, b + m, a + m))
    if cap0 and full:
        c0 = len(verts); verts.append(Vector((rings[0].get('cx', 0), rings[0].get('cy', 0), rings[0]['z'])))
        for j in range(m):
            faces.append((c0, (j + 1) % m, j))
    if cap1 and full:
        base = (len(rings) - 1) * m
        c1 = len(verts); verts.append(Vector((rings[-1].get('cx', 0), rings[-1].get('cy', 0), rings[-1]['z'])))
        for j in range(m):
            faces.append((c1, base + j, base + (j + 1) % m))
    return mesh_obj(name, verts, faces, smooth)


def _frames(path, up):
    """Rotation-minimising frames along a polyline."""
    n = len(path)
    tangents = []
    for i in range(n):
        if i == 0:
            t = path[1] - path[0]
        elif i == n - 1:
            t = path[-1] - path[-2]
        else:
            t = path[i + 1] - path[i - 1]
        tangents.append(t.normalized())
    up = Vector(up)
    nrm = (up - up.project(tangents[0]))
    if nrm.length < 1e-6:
        nrm = Vector((1, 0, 0)) - Vector((1, 0, 0)).project(tangents[0])
    nrm.normalize()
    frames = []
    for i in range(n):
        if i > 0:
            q = tangents[i - 1].rotation_difference(tangents[i])
            nrm = (q @ nrm)
            nrm = (nrm - nrm.project(tangents[i])).normalized()
        frames.append((tangents[i], nrm, tangents[i].cross(nrm)))
    return frames


def sweep(name, path, profile, scales=None, up=(0, 0, 1), closed_path=False, cap=True, smooth=True, twist=None):
    """
    Sweep a 2D profile [(u, v), ...] (closed loop, CCW) along a 3D path.
    u maps to the frame normal (derived from `up`), v to the binormal.
    scales: per path point float or (su, sv). twist: per-point radians.
    """
    path = [Vector(p) for p in path]
    frames = _frames(path, up)
    m = len(profile)
    verts, faces = [], []
    for i, (p, (t, nn, bb)) in enumerate(zip(path, frames)):
        s = scales[i] if scales else 1.0
        su, sv = (s, s) if not isinstance(s, (tuple, list)) else s
        tw = twist[i] if twist else 0.0
        ct, st = math.cos(tw), math.sin(tw)
        for (u, v) in profile:
            uu, vv = u * su, v * sv
            uu, vv = uu * ct - vv * st, uu * st + vv * ct
            verts.append(p + nn * uu + bb * vv)
    rows = len(path)
    for i in range(rows if closed_path else rows - 1):
        i2 = (i + 1) % rows
        for j in range(m):
            a, b = i * m + j, i * m + (j + 1) % m
            faces.append((a, b, i2 * m + (j + 1) % m, i2 * m + j))
    if cap and not closed_path:
        faces.append(tuple(range(m))[::-1])
        faces.append(tuple(range((rows - 1) * m, rows * m)))
    return mesh_obj(name, verts, faces, smooth)


def circle_profile(r, n=12, rv=None):
    rv = rv if rv is not None else r
    return [(r * math.cos(2 * math.pi * i / n), rv * math.sin(2 * math.pi * i / n)) for i in range(n)]


def rect_profile(w, h, bevel=0.0):
    if bevel <= 0:
        return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    b = bevel
    return [(-w / 2 + b, -h / 2), (w / 2 - b, -h / 2), (w / 2, -h / 2 + b), (w / 2, h / 2 - b),
            (w / 2 - b, h / 2), (-w / 2 + b, h / 2), (-w / 2, h / 2 - b), (-w / 2, -h / 2 + b)]


def arc_path(center, radius, a0, a1, n=24, axis_u=(1, 0, 0), axis_v=(0, 0, 1)):
    c, u, v = Vector(center), Vector(axis_u), Vector(axis_v)
    return [c + u * (radius * math.cos(math.radians(a0 + (a1 - a0) * i / n)))
              + v * (radius * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def bezier_path(p0, p1, p2, p3, n=20):
    p0, p1, p2, p3 = map(Vector, (p0, p1, p2, p3))
    out = []
    for i in range(n + 1):
        t = i / n
        out.append((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3)
    return out


def surface(name, fn, nu, nv, closed_u=False, keep=None, smooth=True):
    """Grid surface from fn(u, v) -> point, u,v in [0,1]. keep(u, v) -> bool drops faces (ragged edges)."""
    cols = nu if closed_u else nu + 1
    verts = []
    for j in range(nv + 1):
        for i in range(cols):
            verts.append(Vector(fn(i / nu, j / nv)))
    faces = []
    for j in range(nv):
        for i in range(nu):
            if keep and not keep((i + 0.5) / nu, (j + 0.5) / nv):
                continue
            a = j * cols + i
            b = j * cols + (i + 1) % cols
            faces.append((a, b, b + cols, a + cols))
    obj = mesh_obj(name, verts, faces, smooth)
    remove_loose(obj)
    return obj


def remove_loose(obj):
    bm = bmesh.new(); bm.from_mesh(obj.data)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(obj.data); bm.free()


def uv_sphere(name, r, center=(0, 0, 0), seg=24, rings=16, scale=(1, 1, 1)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=r)
    for v in bm.verts:
        v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2])) + Vector(center)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.shade_smooth()
    return link(bpy.data.objects.new(name, me))


def box(name, size, center=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2])) + Vector(center)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return link(bpy.data.objects.new(name, me))


def transform(obj, mat):
    obj.data.transform(mat)
    obj.data.update()
    return obj


def basis(z_dir, x_hint=(1, 0, 0)):
    """3x3 rotation whose Z axis is z_dir and X axis is as close as possible to x_hint."""
    z = Vector(z_dir).normalized()
    x = Vector(x_hint)
    x = (x - x.project(z))
    if x.length < 1e-6:
        x = Vector((0, 1, 0)) - Vector((0, 1, 0)).project(z)
    x.normalize()
    y = z.cross(x)
    return Matrix((x, y, z)).transposed()


def place(obj, origin, z_dir=(0, 0, 1), x_hint=(1, 0, 0), scale=1.0):
    """Treat the mesh as authored at the origin along +Z and move it to `origin`, oriented along z_dir."""
    m = basis(z_dir, x_hint).to_4x4()
    m = Matrix.Translation(Vector(origin)) @ m @ Matrix.Scale(scale, 4)
    return transform(obj, m)


def mirror_x(obj, name):
    """Duplicate a part mirrored across X (left <-> right), with face winding fixed."""
    me = obj.data.copy()
    me.transform(Matrix.Scale(-1, 4, (1, 0, 0)))
    me.flip_normals()
    o = link(bpy.data.objects.new(name, me))
    for k in obj.keys():
        o[k] = obj[k]
    if "bind" in o:
        o["bind"] = o["bind"].replace(".L", ".TMP").replace(".R", ".L").replace(".TMP", ".R")
    return o


# --- modifiers ---------------------------------------------------------------------------------

def solidify(obj, t, offset=-1.0, rim=True, even=True):
    """even=False for noisy organic shells (fur, cloth): even thickness spikes at folded vertices."""
    m = obj.modifiers.new("solidify", 'SOLIDIFY')
    m.thickness = t; m.offset = offset; m.use_even_offset = even; m.use_rim = rim
    m.use_quality_normals = True
    return obj


def bevel(obj, w, segs=2, angle=35):
    m = obj.modifiers.new("bevel", 'BEVEL')
    m.width = w; m.segments = segs; m.limit_method = 'ANGLE'; m.angle_limit = math.radians(angle)
    m.use_clamp_overlap = True
    return obj


def subsurf(obj, lv=2):
    m = obj.modifiers.new("subsurf", 'SUBSURF')
    m.levels = lv; m.render_levels = lv
    return obj


def boolean(obj, cutter, op='DIFFERENCE'):
    m = obj.modifiers.new("bool", 'BOOLEAN')
    m.object = cutter; m.operation = op; m.solver = 'EXACT'
    try:
        m.use_hole_tolerant = True      # plates are single-sided shells when they get cut
    except AttributeError:
        pass
    cutter.hide_render = True; cutter.hide_viewport = True
    return obj


def apply_mods(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    bpy.data.meshes.remove(old)
    return obj


def finish(obj, mat, bind, t=None, offset=-1.0, bev=None, sub=2, shade=True, even=True):
    """Common hard-surface stack: solidify -> bevel -> subsurf, then apply, assign material and binding."""
    if t:
        solidify(obj, t, offset, even=even)
    if bev:
        bevel(obj, bev[0], bev[1] if len(bev) > 1 else 2)
    if sub:
        subsurf(obj, sub)
    apply_mods(obj)
    if shade:
        obj.data.shade_smooth()
    set_mat(obj, mat)
    obj["bind"] = json.dumps(bind) if not isinstance(bind, str) else bind
    return obj


def displace(obj, strength, scale, seed=0, axis=None, falloff=None):
    """Noise displacement along vertex normals (or a fixed axis). falloff(co) -> multiplier."""
    me = obj.data
    me.update()
    off = Vector((seed * 13.1, seed * 7.7, seed * 3.3))
    for v in me.vertices:
        f = falloff(v.co) if falloff else 1.0
        if f == 0:
            continue
        n = noise.noise(v.co * scale + off)
        d = Vector(axis) if axis else v.normal
        v.co += d * (n * strength * f)
    me.update()
    return obj


def set_mat(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def join(objs, name):
    objs = [o for o in objs if o and o.type == 'MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = name; o.data.name = name
    return o


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# ----------------------------------------------------------------------------------------------
# Materials (procedural, baked to textures for Unity)
# ----------------------------------------------------------------------------------------------

class NB:
    """Tiny node-builder for readable material recipes."""

    def __init__(self, mat):
        self.mat = mat
        self.nt = mat.node_tree
        self.nodes, self.links = self.nt.nodes, self.nt.links

    def n(self, kind, name=None, **inputs):
        node = self.nodes.new(kind)
        if name:
            node.name = name; node.label = name
        for k, v in inputs.items():
            if hasattr(node, k) and not isinstance(v, (bpy.types.NodeSocket,)):
                try:
                    setattr(node, k, v)
                    continue
                except (AttributeError, TypeError):
                    pass
            self.set(node, k, v)
        return node

    def sock_in(self, node, key, typ=None):
        if isinstance(key, int):
            return node.inputs[key]
        cands = [s for s in node.inputs if s.name == key and s.enabled]
        if typ:
            cands = [s for s in cands if s.type == typ] or cands
        if not cands:
            cands = [s for s in node.inputs if s.name == key]
        return cands[0]

    def out(self, node, key=0, typ=None):
        if isinstance(key, int):
            outs = [s for s in node.outputs if s.enabled]
            return outs[key]
        cands = [s for s in node.outputs if s.name == key and s.enabled] or [s for s in node.outputs if s.name == key]
        if typ:
            cands = [s for s in cands if s.type == typ] or cands
        return cands[0]

    def set(self, node, key, v, typ=None):
        s = self.sock_in(node, key, typ)
        if isinstance(v, bpy.types.NodeSocket):
            self.links.new(v, s)
        else:
            if s.type == 'RGBA' and len(v) == 3:
                v = (*v, 1.0)
            s.default_value = v
        return s

    # --- shorthands ---
    def coords(self, kind='Object', scale=1.0):
        tc = self.n('ShaderNodeTexCoord')
        src = self.out(tc, kind)
        if scale == 1.0:
            return src
        mp = self.n('ShaderNodeMapping')
        self.set(mp, 'Vector', src)
        self.set(mp, 'Scale', (scale, scale, scale) if not isinstance(scale, tuple) else scale)
        return self.out(mp, 'Vector')

    def noise(self, vec, scale, detail=4.0, rough=0.5, out='Factor', dims='3D'):
        n = self.n('ShaderNodeTexNoise')
        n.noise_dimensions = dims
        self.set(n, 'Vector', vec); self.set(n, 'Scale', scale); self.set(n, 'Detail', detail)
        self.set(n, 'Roughness', rough)
        return self.out(n, out)

    def voronoi(self, vec, scale, feature='F1', out='Distance', rand=1.0):
        n = self.n('ShaderNodeTexVoronoi')
        n.feature = feature
        self.set(n, 'Vector', vec); self.set(n, 'Scale', scale)
        if 'Randomness' in n.inputs:
            self.set(n, 'Randomness', rand)
        return self.out(n, out)

    def wave(self, vec, scale, distortion=0.0, kind='BANDS', direction='X', profile='SIN', out='Factor', detail=2.0):
        n = self.n('ShaderNodeTexWave')
        n.wave_type = kind
        if kind == 'BANDS':
            n.bands_direction = direction
        else:
            n.rings_direction = direction
        n.wave_profile = profile
        self.set(n, 'Vector', vec); self.set(n, 'Scale', scale); self.set(n, 'Distortion', distortion)
        self.set(n, 'Detail', detail)
        return self.out(n, out)

    def ramp(self, fac, stops):
        """stops: [(pos, value_or_rgb), ...]"""
        r = self.n('ShaderNodeValToRGB')
        self.set(r, 'Factor', fac)
        cr = r.color_ramp
        while len(cr.elements) > len(stops):
            cr.elements.remove(cr.elements[-1])
        while len(cr.elements) < len(stops):
            cr.elements.new(0.5)
        for el, (pos, val) in zip(cr.elements, stops):
            el.position = pos
            if isinstance(val, (int, float)):
                val = (val, val, val)
            el.color = (*val, 1.0)
        return self.out(r, 'Color')

    def math(self, op, a, b=None, clamp=False):
        m = self.n('ShaderNodeMath')
        m.operation = op; m.use_clamp = clamp
        self.set(m, 0, a)
        if b is not None:
            self.set(m, 1, b)
        return self.out(m, 'Value')

    def mix(self, fac, a, b, blend='MIX', name=None):
        m = self.n('ShaderNodeMix', name)
        m.data_type = 'RGBA'; m.blend_type = blend
        self.set(m, 'Factor', fac, 'VALUE')
        self.set(m, 'A', a, 'RGBA'); self.set(m, 'B', b, 'RGBA')
        return self.out(m, 'Result', 'RGBA')

    def fmix(self, fac, a, b):
        m = self.n('ShaderNodeMix')
        m.data_type = 'FLOAT'
        self.set(m, 'Factor', fac, 'VALUE'); self.set(m, 'A', a, 'VALUE'); self.set(m, 'B', b, 'VALUE')
        return self.out(m, 'Result', 'VALUE')

    def bump(self, height, strength, dist=0.01, normal=None, name=None):
        b = self.n('ShaderNodeBump', name)
        self.set(b, 'Height', height); self.set(b, 'Strength', strength); self.set(b, 'Distance', dist)
        if normal is not None:
            self.set(b, 'Normal', normal)
        return self.out(b, 'Normal')

    def value(self, v, name=None):
        n = self.n('ShaderNodeValue', name)
        n.outputs[0].default_value = v
        return n.outputs[0]

    def rgb(self, c, name=None):
        n = self.n('ShaderNodeRGB', name)
        n.outputs[0].default_value = (*c, 1.0)
        return n.outputs[0]

    def pointiness(self):
        return self.out(self.n('ShaderNodeNewGeometry'), 'Pointiness')

    def ao(self, distance=0.05, samples=16):
        a = self.n('ShaderNodeAmbientOcclusion')
        a.samples = samples
        self.set(a, 'Distance', distance)
        return self.out(a, 'AO')

    def sepz(self, vec):
        s = self.n('ShaderNodeSeparateXYZ')
        self.set(s, 'Vector', vec)
        return self.out(s, 'Z')


def new_material(name):
    m = bpy.data.materials.new(name)
    if hasattr(m, "use_nodes"):
        m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    b = NB(m)
    out = b.n('ShaderNodeOutputMaterial', 'OUT')
    bsdf = b.n('ShaderNodeBsdfPrincipled', 'BSDF')
    b.links.new(bsdf.outputs[0], out.inputs['Surface'])
    return b, bsdf


def _finalize(b, bsdf, bc, rough, metal, nrm, emit=None):
    """Wire the PBR channels through named terminal nodes so the baker can find them."""
    bc_node = b.n('ShaderNodeMix', 'OUT_BC'); bc_node.data_type = 'RGBA'
    b.set(bc_node, 'Factor', 0.0, 'VALUE'); b.set(bc_node, 'A', bc, 'RGBA'); b.set(bc_node, 'B', (0, 0, 0), 'RGBA')
    e_node = b.n('ShaderNodeMix', 'OUT_E'); e_node.data_type = 'RGBA'
    b.set(e_node, 'Factor', 0.0, 'VALUE'); b.set(e_node, 'A', emit if emit is not None else (0, 0, 0), 'RGBA')
    b.set(e_node, 'B', (0, 0, 0), 'RGBA')
    if emit is not None:
        b.set(bsdf, 'Emission Color', b.out(e_node, 'Result', 'RGBA'))
        b.set(bsdf, 'Emission Strength', 4.0)
    r_node = b.n('ShaderNodeMath', 'OUT_R'); r_node.operation = 'ADD'; r_node.use_clamp = True
    b.set(r_node, 0, rough); b.set(r_node, 1, 0.0)
    m_node = b.n('ShaderNodeMath', 'OUT_M'); m_node.operation = 'ADD'; m_node.use_clamp = True
    b.set(m_node, 0, metal); b.set(m_node, 1, 0.0)
    b.set(bsdf, 'Base Color', b.out(bc_node, 'Result', 'RGBA'))
    b.set(bsdf, 'Roughness', r_node.outputs[0])
    b.set(bsdf, 'Metallic', m_node.outputs[0])
    if nrm is not None:
        b.set(bsdf, 'Normal', nrm)
    return b.mat


def mat_metal(name, base=(0.075, 0.075, 0.08), rust=0.35, wear=0.7, rough=0.42, grime=0.6,
              rust_col=(0.16, 0.065, 0.03), edge_col=(0.42, 0.41, 0.4), scale=1.0, dents=1.0, metal=1.0):
    b, bsdf = new_material(name)
    co = b.coords('Object', scale)
    big = b.noise(co, 2.5, 6, 0.55)
    rust_n = b.noise(co, 7.0, 12, 0.65)
    ao = b.ao(0.06)
    crev = b.math('SUBTRACT', 1.0, ao)                            # 1 in crevices
    rust_mask = b.math('ADD', b.ramp(rust_n, [(0.52, 0.0), (0.68, 1.0)]), b.math('MULTIPLY', crev, 1.4))
    rust_mask = b.math('MULTIPLY', rust_mask, rust, clamp=True)
    edge = b.ramp(b.pointiness(), [(0.5, 0.0), (0.545, 1.0)])
    chip = b.ramp(b.noise(co, 40.0, 3, 0.5), [(0.35, 0.0), (0.6, 1.0)])
    edge = b.math('MULTIPLY', b.math('MULTIPLY', edge, chip), wear, clamp=True)
    scr_co = b.coords('Object', (scale * 3, scale * 3, scale * 60))
    scratches = b.ramp(b.noise(scr_co, 6.0, 2, 0.5), [(0.494, 0.0), (0.5, 1.0), (0.506, 0.0)])
    scratches = b.math('MULTIPLY', scratches, b.ramp(b.noise(co, 3.0, 2), [(0.45, 0.0), (0.65, 1.0)]))
    tint = b.mix(b.math('MULTIPLY', big, 0.5), base, tuple(c * 1.6 for c in base))
    col = b.mix(edge, tint, edge_col)
    col = b.mix(b.math('MULTIPLY', scratches, 0.12), col, edge_col)
    col = b.mix(rust_mask, col, b.mix(rust_n, rust_col, tuple(c * 0.55 for c in rust_col)))
    col = b.mix(b.math('MULTIPLY', crev, grime), col, (0.01, 0.01, 0.01))
    rough_v = b.math('ADD', rough, b.math('MULTIPLY', rust_mask, 0.45))
    rough_v = b.math('SUBTRACT', rough_v, b.math('MULTIPLY', edge, 0.18))
    rough_v = b.math('ADD', rough_v, b.math('MULTIPLY', scratches, 0.12))
    metal_v = b.math('MULTIPLY', b.math('SUBTRACT', 1.0, b.math('MULTIPLY', rust_mask, 0.9)), metal)
    h = b.math('ADD', b.math('MULTIPLY', b.noise(co, 60.0, 4, 0.55), 0.06),
               b.math('MULTIPLY', rust_mask, b.noise(co, 30.0, 8, 0.7)))
    h = b.math('SUBTRACT', h, b.math('MULTIPLY', scratches, 0.08))
    dent = b.noise(co, 9.0, 2, 0.4)
    n1 = b.bump(dent, 0.12 * dents, 0.05)
    nrm = b.bump(h, 0.3, 0.004, n1)
    return _finalize(b, bsdf, col, rough_v, metal_v, nrm)


def mat_plate(name, polished=True, base=None, scale=1.0, embers=0.0, soot=0.0, rust=0.1, hammer=1.0):
    """
    Plate armour steel. polished=True: bright Milanese white harness (low roughness, smudges, fine scratches).
    polished=False: blackened, fire-scorched steel with soot, rust, chipped bright edges; embers>0 adds glowing
    ember cracks (emission), strongest where soot is heaviest.
    """
    b, bsdf = new_material(name)
    co = b.coords('Object', scale)
    ao = b.ao(0.05)
    crev = b.math('SUBTRACT', 1.0, ao)
    edge = b.ramp(b.pointiness(), [(0.5, 0.0), (0.54, 1.0)])
    big = b.noise(co, 2.0, 6, 0.55)
    smudge = b.ramp(b.noise(co, 7.0, 8, 0.65), [(0.45, 0.0), (0.75, 1.0)])
    scr_a = b.ramp(b.noise(b.coords('Object', (scale * 4, scale * 4, scale * 90)), 5.0, 2, 0.5), [(0.496, 0), (0.5, 1), (0.504, 0)])
    scr_b = b.ramp(b.noise(b.coords('Object', (scale * 90, scale * 4, scale * 4)), 5.0, 2, 0.5), [(0.496, 0), (0.5, 1), (0.504, 0)])
    scratches = b.math('MAXIMUM', scr_a, scr_b)
    scratches = b.math('MULTIPLY', scratches, b.ramp(b.noise(co, 2.5, 2), [(0.4, 0.0), (0.7, 1.0)]))
    rust_mask = b.math('MULTIPLY', b.math('ADD', b.ramp(b.noise(co, 9.0, 12, 0.65), [(0.58, 0), (0.72, 1)]),
                                          b.math('MULTIPLY', crev, 1.2)), rust, clamp=True)
    hammer_h = b.voronoi(b.coords('Object', scale * 38), 1.0, 'F1', 'Distance')
    if polished:
        base = base or (0.62, 0.63, 0.65)
        col = b.mix(b.math('MULTIPLY', big, 0.35), base, tuple(c * 0.86 for c in base))
        col = b.mix(b.math('MULTIPLY', smudge, 0.25), col, tuple(c * 0.75 for c in base))
        col = b.mix(rust_mask, col, (0.2, 0.09, 0.04))
        col = b.mix(b.math('MULTIPLY', crev, 0.55), col, (0.08, 0.075, 0.07))
        rough_v = b.math('ADD', 0.14, b.math('MULTIPLY', smudge, 0.16))
        rough_v = b.math('ADD', rough_v, b.math('MULTIPLY', scratches, 0.15))
        rough_v = b.math('ADD', rough_v, b.math('MULTIPLY', rust_mask, 0.5))
        metal_v = b.math('SUBTRACT', 1.0, b.math('MULTIPLY', rust_mask, 0.9))
        emit = None
    else:
        base = base or (0.045, 0.043, 0.042)
        soot_mask = b.math('MULTIPLY', b.ramp(b.noise(co, 3.0, 8, 0.6), [(0.35, 0.0), (0.7, 1.0)]), soot)
        heat = b.ramp(b.noise(co, 1.5, 3), [(0.3, 0.0), (0.7, 1.0)])
        col = b.mix(b.math('MULTIPLY', big, 0.5), base, tuple(c * 1.8 for c in base))
        col = b.mix(b.math('MULTIPLY', heat, 0.35), col, (0.09, 0.06, 0.1))                 # temper tint
        chip = b.ramp(b.noise(co, 45.0, 3, 0.5), [(0.4, 0.0), (0.62, 1.0)])
        worn = b.math('MULTIPLY', edge, chip, clamp=True)
        col = b.mix(worn, col, (0.36, 0.34, 0.32))
        col = b.mix(b.math('MULTIPLY', scratches, 0.25), col, (0.3, 0.29, 0.28))
        col = b.mix(rust_mask, col, b.mix(b.noise(co, 30, 4), (0.17, 0.065, 0.025), (0.08, 0.03, 0.012)))
        col = b.mix(soot_mask, col, (0.012, 0.011, 0.01))
        col = b.mix(b.math('MULTIPLY', crev, 0.75), col, (0.0, 0.0, 0.0))
        rough_v = b.math('ADD', 0.38, b.math('MULTIPLY', soot_mask, 0.45))
        rough_v = b.math('ADD', rough_v, b.math('MULTIPLY', rust_mask, 0.4))
        rough_v = b.math('SUBTRACT', rough_v, b.math('MULTIPLY', worn, 0.2))
        metal_v = b.math('SUBTRACT', 1.0, b.math('MAXIMUM', b.math('MULTIPLY', rust_mask, 0.9), b.math('MULTIPLY', soot_mask, 0.6)))
        emit = None
        if embers > 0:
            # organic crack network: voronoi edges on noise-distorted coordinates, broken up and patchy
            warp = b.n('ShaderNodeVectorMath'); warp.operation = 'MULTIPLY_ADD'
            b.links.new(b.noise(co, 3.5, 4, 0.6, out='Color'), warp.inputs[0])
            warp.inputs[1].default_value = (0.9, 0.9, 0.9)
            b.links.new(b.coords('Object', scale * 6.0), warp.inputs[2])
            cracks = b.ramp(b.voronoi(warp.outputs[0], 1.0, 'DISTANCE_TO_EDGE', 'Distance'), [(0.0, 1.0), (0.022, 0.0)])
            fine = b.ramp(b.voronoi(b.coords('Object', scale * 20), 1.0, 'DISTANCE_TO_EDGE', 'Distance'), [(0.0, 0.6), (0.018, 0.0)])
            breaks = b.ramp(b.noise(co, 16.0, 4, 0.5), [(0.42, 0.0), (0.58, 1.0)])
            where = b.ramp(b.noise(co, 1.8, 6, 0.6), [(0.56, 0.0), (0.74, 1.0)])
            lines = b.math('MULTIPLY', b.math('MAXIMUM', cracks, b.math('MULTIPLY', fine, where)), breaks)
            glow = b.math('MULTIPLY', b.math('MULTIPLY', lines, where), embers, clamp=True)
            glow = b.math('ADD', glow, b.math('MULTIPLY', b.math('MULTIPLY', crev, where), embers * 0.55), clamp=True)
            emit = b.mix(glow, (0, 0, 0), b.mix(b.noise(co, 20, 3), (1.0, 0.32, 0.05), (1.0, 0.6, 0.15)))
            col = b.mix(glow, col, (0.25, 0.06, 0.01))
    h = b.math('ADD', b.math('MULTIPLY', hammer_h, 0.08 * hammer), b.math('MULTIPLY', rust_mask, b.noise(co, 35.0, 8, 0.7)))
    h = b.math('SUBTRACT', h, b.math('MULTIPLY', scratches, 0.05))
    n1 = b.bump(b.noise(co, 6.0, 2, 0.4), 0.06 if polished else 0.14, 0.05)
    nrm = b.bump(h, 0.25, 0.004, n1)
    return _finalize(b, bsdf, col, rough_v, metal_v, nrm, emit)


def mat_cloth(name, color, dirt=0.5, weave=500.0, rough=0.9, fade=0.25, scale=1.0, pattern=None):
    b, bsdf = new_material(name)
    co = b.coords('Object', scale)
    var = b.noise(co, 4.0, 6, 0.6)
    col = b.mix(b.math('MULTIPLY', var, 0.8), tuple(c * 0.6 for c in color), color)
    faded = tuple(min(1, c * 0.55 + 0.08) for c in color)
    col = b.mix(b.math('MULTIPLY', b.ramp(b.noise(co, 2.0, 3), [(0.4, 0), (0.7, 1)]), fade), col, faded)
    z = b.sepz(b.coords('Object'))
    low = b.ramp(z, [(0.0, 1.0), (0.6, 0.0)])
    ao = b.ao(0.05)
    grime = b.math('ADD', b.math('MULTIPLY', low, dirt), b.math('MULTIPLY', b.math('SUBTRACT', 1, ao), 0.7), clamp=True)
    col = b.mix(grime, col, (0.03, 0.025, 0.02))
    if pattern is not None:
        col = pattern(b, co, col)
    wx = b.wave(b.coords('Object', scale), weave, 0.0, 'BANDS', 'X')
    wy = b.wave(b.coords('Object', scale), weave, 0.0, 'BANDS', 'Z')
    weave_h = b.math('MULTIPLY', wx, wy)
    folds = b.noise(co, 14.0, 5, 0.6)
    n1 = b.bump(folds, 0.25, 0.03)
    nrm = b.bump(weave_h, 0.18, 0.002, n1)
    return _finalize(b, bsdf, col, b.math('ADD', rough, b.math('MULTIPLY', var, 0.05)), 0.0, nrm)


def mat_leather(name, color, wear=0.6, rough=0.62, grain=140.0, scale=1.0):
    b, bsdf = new_material(name)
    co = b.coords('Object', scale)
    var = b.noise(co, 5.0, 8, 0.6)
    col = b.mix(var, tuple(c * 0.65 for c in color), color)
    edge = b.ramp(b.pointiness(), [(0.5, 0), (0.56, 1)])
    col = b.mix(b.math('MULTIPLY', edge, wear), col, tuple(min(1, c * 1.7 + 0.04) for c in color))
    ao = b.ao(0.04)
    col = b.mix(b.math('MULTIPLY', b.math('SUBTRACT', 1, ao), 0.8), col, (0.02, 0.012, 0.008))
    g = b.voronoi(co, grain, 'F1', 'Distance')
    cracks = b.ramp(b.voronoi(co, grain * 0.3, 'DISTANCE_TO_EDGE', 'Distance'), [(0.0, 1.0), (0.06, 0.0)])
    h = b.math('SUBTRACT', b.math('MULTIPLY', g, 0.6), b.math('MULTIPLY', cracks, 0.5))
    nrm = b.bump(h, 0.35, 0.002, b.bump(b.noise(co, 20, 4), 0.15, 0.02))
    rough_v = b.math('SUBTRACT', b.math('ADD', rough, b.math('MULTIPLY', var, 0.1)), b.math('MULTIPLY', edge, 0.2))
    return _finalize(b, bsdf, col, rough_v, 0.0, nrm)


def mat_chain(name, base=(0.11, 0.105, 0.1), rust=0.3, scale=1.0):
    b, bsdf = new_material(name)
    co = b.coords('Object', scale)
    # interlocking rings: distance-to-edge voronoi on a regular-ish grid gives a convincing mail pattern
    rings = b.voronoi(b.coords('Object', (scale * 260, scale * 260, scale * 260)), 1.0, 'DISTANCE_TO_EDGE', 'Distance', 0.0)
    ring = b.ramp(rings, [(0.02, 0.0), (0.1, 1.0), (0.2, 0.3)])
    rust_n = b.noise(co, 8.0, 10, 0.6)
    rust_mask = b.math('MULTIPLY', b.ramp(rust_n, [(0.5, 0), (0.7, 1)]), rust)
    col = b.mix(ring, (0.01, 0.01, 0.01), base)
    col = b.mix(rust_mask, col, (0.15, 0.06, 0.025))
    ao = b.ao(0.05)
    col = b.mix(b.math('MULTIPLY', b.math('SUBTRACT', 1, ao), 0.7), col, (0.0, 0.0, 0.0))
    nrm = b.bump(ring, 0.8, 0.003)
    metal_v = b.math('MULTIPLY', ring, b.math('SUBTRACT', 1, rust_mask))
    return _finalize(b, bsdf, col, b.math('ADD', 0.45, b.math('MULTIPLY', rust_mask, 0.4)), metal_v, nrm)


def mat_fur(name, color, tip=(0.5, 0.45, 0.4)):
    b, bsdf = new_material(name)
    strands = b.wave(b.coords('Object', (40, 40, 3)), 8.0, 12.0, 'BANDS', 'X', 'SAW')
    clumps = b.noise(b.coords('Object'), 18.0, 6, 0.7)
    h = b.math('MULTIPLY', strands, clumps)
    col = b.mix(h, tuple(c * 0.4 for c in color), color)
    col = b.mix(b.ramp(h, [(0.6, 0), (0.9, 1)]), col, tip)
    ao = b.ao(0.08)
    col = b.mix(b.math('MULTIPLY', b.math('SUBTRACT', 1, ao), 0.9), col, (0, 0, 0))
    nrm = b.bump(h, 0.9, 0.01)
    return _finalize(b, bsdf, col, 0.95, 0.0, nrm)


def mat_skin(name, color=(0.62, 0.45, 0.37)):
    b, bsdf = new_material(name)
    co = b.coords('Object')
    var = b.noise(co, 30.0, 6, 0.6)
    col = b.mix(b.math('MULTIPLY', var, 0.4), color, tuple(c * 0.85 for c in color))
    ao = b.ao(0.03)
    col = b.mix(b.math('MULTIPLY', b.math('SUBTRACT', 1, ao), 0.6), col, (0.15, 0.06, 0.05))
    nrm = b.bump(b.noise(co, 400.0, 3), 0.1, 0.001)
    return _finalize(b, bsdf, col, 0.5, 0.0, nrm)


def mat_hair(name, color=(0.05, 0.035, 0.025)):
    b, bsdf = new_material(name)
    strands = b.wave(b.coords('Object', (1, 1, 1)), 300.0, 4.0, 'BANDS', 'X', 'SIN')
    col = b.mix(b.math('MULTIPLY', strands, 0.5), color, tuple(min(1, c * 2.2) for c in color))
    nrm = b.bump(strands, 0.4, 0.002)
    return _finalize(b, bsdf, col, 0.45, 0.0, nrm)


def mat_flat(name, color, rough=0.5, metal=0.0):
    b, bsdf = new_material(name)
    return _finalize(b, bsdf, color, rough, metal, None)


# ----------------------------------------------------------------------------------------------
# Armature
# ----------------------------------------------------------------------------------------------

def build_armature(bones, name="Rig"):
    """
    bones: list of dicts {name, head, tail, parent, deform=True, z_axis=(0,-1,0)}.
    z_axis aligns the bone roll so local Z points that way (forward by default).
    """
    data = bpy.data.armatures.new(name)
    arm = link(bpy.data.objects.new(name, data))
    data.display_type = 'STICK'
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    eb = data.edit_bones
    for b in bones:
        e = eb.new(b['name'])
        e.head = Vector(b['head']); e.tail = Vector(b['tail'])
        e.use_deform = b.get('deform', True)
        e.align_roll(Vector(b.get('z_axis', (0, -1, 0))))
    for b in bones:
        if b.get('parent'):
            eb[b['name']].parent = eb[b['parent']]
            eb[b['name']].use_connect = False
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm


def bone_segments(arm, names):
    out = {}
    for n in names:
        b = arm.data.bones[n]
        out[n] = (np.array(b.head_local), np.array(b.tail_local))
    return out


def _seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / max(ab @ ab, 1e-9), 0.0, 1.0)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1)


def weight_part(obj, arm, bind):
    """
    bind modes:
      {"mode": "rigid", "bone": "chest"}
      {"mode": "fixed", "weights": {"chest": 0.6, "upperarm.L": 0.4}}
      {"mode": "smooth", "bones": [...], "power": 6, "max": 3}
    """
    me = obj.data
    n = len(me.vertices)
    if n == 0:
        return
    mode = bind['mode']
    if mode == 'rigid':
        vg = obj.vertex_groups.get(bind['bone']) or obj.vertex_groups.new(name=bind['bone'])
        vg.add(list(range(n)), 1.0, 'REPLACE')
        return
    if mode == 'fixed':
        for bn, w in bind['weights'].items():
            vg = obj.vertex_groups.get(bn) or obj.vertex_groups.new(name=bn)
            vg.add(list(range(n)), w, 'REPLACE')
        return
    names = bind['bones']
    P = np.empty(n * 3); me.vertices.foreach_get('co', P); P = P.reshape(n, 3)
    segs = bone_segments(arm, names)
    D = np.stack([_seg_dist(P, *segs[nm]) for nm in names], axis=1)  # n x B
    power = bind.get('power', 6)
    W = 1.0 / np.maximum(D, 1e-4) ** power
    k = bind.get('max', 3)
    if k < len(names):
        idx = np.argsort(-W, axis=1)[:, k:]
        np.put_along_axis(W, idx, 0.0, axis=1)
    W /= W.sum(axis=1, keepdims=True)
    for bi, nm in enumerate(names):
        vg = obj.vertex_groups.get(nm) or obj.vertex_groups.new(name=nm)
        col = W[:, bi]
        nz = np.nonzero(col > 0.004)[0]
        # group indices by quantised weight to cut down on API calls
        q = np.round(col[nz] * 200).astype(int)
        for val in np.unique(q):
            ids = nz[q == val].tolist()
            vg.add(ids, float(val) / 200.0, 'REPLACE')


def bind_all(parts, arm):
    for p in parts:
        weight_part(p, arm, json.loads(p["bind"]))


def skin_to(obj, arm):
    obj.parent = arm
    m = obj.modifiers.new("Armature", 'ARMATURE')
    m.object = arm
    return obj


# ----------------------------------------------------------------------------------------------
# Pose / animation helpers
# ----------------------------------------------------------------------------------------------

def weapon_matrix(grip, tip_dir, edge_dir):
    """Armature-space matrix for a weapon bone whose Y axis runs along the blade and Z axis along the edge."""
    y = Vector(tip_dir).normalized()
    z = Vector(edge_dir)
    z = (z - z.project(y)).normalized()
    x = y.cross(z)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(grip)
    return m


def set_bone_matrix(arm, bone, mat):
    pb = arm.pose.bones[bone]
    pb.matrix = mat
    bpy.context.view_layer.update()


def key_bone(arm, bone, frame, loc=True, rot=True):
    pb = arm.pose.bones[bone]
    if loc:
        pb.keyframe_insert("location", frame=frame)
    if rot:
        pb.keyframe_insert("rotation_quaternion" if pb.rotation_mode == 'QUATERNION' else "rotation_euler", frame=frame)


def new_action(arm, name):
    act = bpy.data.actions.get(name) or bpy.data.actions.new(name)
    act.use_fake_user = True
    arm.animation_data_create()
    arm.animation_data.action = act
    return act


# ----------------------------------------------------------------------------------------------
# Baking
# ----------------------------------------------------------------------------------------------

def setup_cycles(samples=16):
    scn = bpy.context.scene
    scn.render.engine = 'CYCLES'
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'OPTIX'
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type in ('OPTIX',)
        scn.cycles.device = 'GPU'
    except Exception as e:
        log("GPU setup failed, using CPU:", e)
    scn.cycles.samples = samples
    scn.cycles.use_denoising = False


def smart_uv(obj, margin=0.002, angle=60):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    try:
        bpy.ops.uv.pack_islands(margin=margin, rotate=True, shape_method='CONCAVE')
    except TypeError:
        bpy.ops.uv.pack_islands(margin=margin, rotate=True)
    bpy.ops.object.mode_set(mode='OBJECT')


def _bake(obj, img, btype, samples, margin=16):
    scn = bpy.context.scene
    scn.cycles.samples = samples
    for slot in obj.material_slots:
        nt = slot.material.node_tree
        node = nt.nodes.get("BAKE_TARGET") or nt.nodes.new('ShaderNodeTexImage')
        node.name = "BAKE_TARGET"; node.image = img
        nt.nodes.active = node
        node.select = True
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    kw = dict(type=btype, margin=margin, use_clear=True)
    if btype == 'NORMAL':
        kw.update(normal_space='TANGENT')
    bpy.ops.object.bake(**kw)


def _route(obj, channel):
    """Route a named channel through an Emission shader to the material output (or restore with None)."""
    for slot in obj.material_slots:
        mat = slot.material
        nt = mat.node_tree
        out = nt.nodes['OUT']
        if channel is None:
            nt.links.new(nt.nodes['BSDF'].outputs[0], out.inputs['Surface'])
            continue
        em = nt.nodes.get('BAKE_EMIT') or nt.nodes.new('ShaderNodeEmission')
        em.name = 'BAKE_EMIT'
        src = nt.nodes[channel]
        sock = [s for s in src.outputs if s.enabled][0] if channel not in ('OUT_BC', 'OUT_E') else \
            [s for s in src.outputs if s.name == 'Result' and s.type == 'RGBA'][0]
        nt.links.new(sock, em.inputs['Color'])
        em.inputs['Strength'].default_value = 1.0
        nt.links.new(em.outputs[0], out.inputs['Surface'])


def _img(name, res, non_color, alpha=False):
    img = bpy.data.images.get(name)
    if img:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, res, res, alpha=alpha, float_buffer=False)
    if non_color:
        img.colorspace_settings.name = 'Non-Color'
    return img


def _pixels(img):
    a = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(-1, 4)


def _save(img, path, data=None):
    if data is not None:
        img.pixels.foreach_set(data.astype(np.float32).ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()


def bake_textures(obj, out_dir, prefix, res=2048, ao_samples=64, ao_strength=0.55):
    """Bake albedo (with some AO multiplied in), normal, mask (R metal, A smoothness) and AO."""
    os.makedirs(out_dir, exist_ok=True)
    setup_cycles()
    bpy.context.scene.render.bake.margin = 16
    alb = _img(prefix + "_Albedo", res, False)
    _route(obj, 'OUT_BC'); _bake(obj, alb, 'EMIT', 1)
    rgh = _img(prefix + "_Rough", res, True)
    _route(obj, 'OUT_R'); _bake(obj, rgh, 'EMIT', 1)
    met = _img(prefix + "_Metal", res, True)
    _route(obj, 'OUT_M'); _bake(obj, met, 'EMIT', 1)
    emi = _img(prefix + "_Emission", res, False)
    _route(obj, 'OUT_E'); _bake(obj, emi, 'EMIT', 1)
    _route(obj, None)
    nrm = _img(prefix + "_Normal", res, True)
    _bake(obj, nrm, 'NORMAL', 4)
    ao = _img(prefix + "_AO", res, True)
    bpy.context.scene.world = bpy.context.scene.world or bpy.data.worlds.new("World")
    _bake(obj, ao, 'AO', ao_samples)

    A = _pixels(alb); R = _pixels(rgh); M = _pixels(met); O = _pixels(ao)
    occ = O[:, 0:1]
    A[:, :3] = A[:, :3] * (1.0 - ao_strength + ao_strength * occ)
    A[:, 3] = 1.0
    _save(alb, os.path.join(out_dir, f"{prefix}_Albedo.png"), A)
    mask = np.zeros_like(R)
    mask[:, 0] = M[:, 0]
    mask[:, 1] = occ[:, 0]
    mask[:, 2] = 0.0
    mask[:, 3] = 1.0 - R[:, 0]
    mimg = _img(prefix + "_Mask", res, True, alpha=True)
    _save(mimg, os.path.join(out_dir, f"{prefix}_Mask.png"), mask)
    _save(nrm, os.path.join(out_dir, f"{prefix}_Normal.png"))
    E = _pixels(emi)
    epath = os.path.join(out_dir, f"{prefix}_Emission.png")
    if E[:, :3].max() > 0.02:
        E[:, 3] = 1.0
        _save(emi, epath, E)
    elif os.path.exists(epath):
        os.remove(epath)
    _save(ao, os.path.join(out_dir, f"{prefix}_AO.png"))
    log("baked", prefix, res)
    return {k: os.path.join(out_dir, f"{prefix}_{k}.png") for k in ("Albedo", "Normal", "Mask", "AO")}


def use_baked_material(obj, name, tex):
    """Replace all slots with one material using the baked maps (for preview renders and FBX)."""
    b, bsdf = new_material(name)
    def tex_node(path, non_color):
        n = b.n('ShaderNodeTexImage')
        n.image = bpy.data.images.load(path, check_existing=True)
        if non_color:
            n.image.colorspace_settings.name = 'Non-Color'
        uv = b.n('ShaderNodeUVMap'); uv.uv_map = obj.data.uv_layers.active.name
        b.links.new(uv.outputs[0], n.inputs['Vector'])
        return n
    a = tex_node(tex['Albedo'], False)
    m = tex_node(tex['Mask'], True)
    nn = tex_node(tex['Normal'], True)
    b.set(bsdf, 'Base Color', a.outputs['Color'])
    sep = b.n('ShaderNodeSeparateColor')
    b.links.new(m.outputs['Color'], sep.inputs[0])
    b.set(bsdf, 'Metallic', sep.outputs[0])
    inv = b.math('SUBTRACT', 1.0, m.outputs['Alpha'])
    b.set(bsdf, 'Roughness', inv)
    nm = b.n('ShaderNodeNormalMap')
    b.links.new(nn.outputs['Color'], nm.inputs['Color'])
    b.set(bsdf, 'Normal', nm.outputs['Normal'])
    obj.data.materials.clear()
    obj.data.materials.append(b.mat)
    return b.mat


# ----------------------------------------------------------------------------------------------
# Rendering previews
# ----------------------------------------------------------------------------------------------

def preview_setup(engine='CYCLES', samples=64, res=(1200, 1600)):
    scn = bpy.context.scene
    if engine == 'CYCLES':
        setup_cycles(samples)
        scn.cycles.use_denoising = True
    else:
        scn.render.engine = engine
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.film_transparent = False
    world = bpy.data.worlds.new("PreviewWorld")
    scn.world = world
    if hasattr(world, "use_nodes"):
        try:
            world.use_nodes = True
        except Exception:
            pass
    if world.node_tree:
        bg = world.node_tree.nodes.get('Background')
        if bg is None:
            bg = world.node_tree.nodes.new('ShaderNodeBackground')
            out = world.node_tree.nodes.get('World Output') or world.node_tree.nodes.new('ShaderNodeOutputWorld')
            world.node_tree.links.new(bg.outputs[0], out.inputs[0])
        bg.inputs['Color'].default_value = (0.04, 0.045, 0.06, 1)
        bg.inputs['Strength'].default_value = 0.6
    try:
        scn.view_settings.view_transform = 'AgX'
        scn.view_settings.look = 'AgX - Medium High Contrast'
    except Exception:
        pass


def add_light(name, kind, loc, rot, energy, color=(1, 1, 1), size=1.0):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy; ld.color = color
    if kind == 'AREA':
        ld.size = size
    o = link(bpy.data.objects.new(name, ld))
    o.location = loc; o.rotation_euler = [math.radians(a) for a in rot]
    return o


def three_point(target_h=1.0):
    add_light("Key", 'AREA', (-2.2, -2.6, 3.0), (55, 0, -40), 170, (1.0, 0.9, 0.78), 1.5)
    add_light("Fill", 'AREA', (2.8, -2.0, 1.6), (70, 0, 50), 45, (0.7, 0.8, 1.0), 2.0)
    add_light("Rim", 'AREA', (0.5, 3.0, 2.8), (-60, 0, 180), 300, (1.0, 0.75, 0.5), 1.2)


def camera_look(name, loc, target, lens=50):
    cd = bpy.data.cameras.new(name); cd.lens = lens
    cam = link(bpy.data.objects.new(name, cd))
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = cam
    return cam


def render_to(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    log("rendered", path)


def contact_sheet(arm, rows, path, cam_loc, cam_target, size=360, lens=50):
    """
    rows: [(action_name, [frames...]), ...]. Renders each frame with Workbench and tiles them into one PNG.
    """
    scn = bpy.context.scene
    scn.render.engine = 'BLENDER_WORKBENCH'
    sh = scn.display.shading
    sh.light = 'STUDIO'; sh.color_type = 'MATERIAL'; sh.show_cavity = True; sh.show_shadows = True
    scn.render.resolution_x = scn.render.resolution_y = size
    scn.render.film_transparent = False
    camera_look("SheetCam", cam_loc, cam_target, lens)
    cols = max(len(f) for _, f in rows)
    sheet = np.zeros((len(rows) * size, cols * size, 4), dtype=np.float32)
    sheet[..., 3] = 1
    tmp = os.path.join(os.path.dirname(path), f"_tile_{os.getpid()}.png")
    for r, (act, frames) in enumerate(rows):
        arm.animation_data.action = bpy.data.actions[act]
        for c, f in enumerate(frames):
            scn.frame_set(f)
            scn.render.filepath = tmp
            bpy.ops.render.render(write_still=True)
            img = bpy.data.images.load(tmp)
            px = np.array(img.pixels[:], dtype=np.float32).reshape(size, size, 4)
            bpy.data.images.remove(img)
            y0 = (len(rows) - 1 - r) * size
            sheet[y0:y0 + size, c * size:(c + 1) * size] = px
    out = bpy.data.images.new("sheet", cols * size, len(rows) * size, alpha=True)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw = path; out.file_format = 'PNG'; out.save()
    os.remove(tmp)
    log("contact sheet", path)


def save_blend(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)


def export_fbx(path, objects, anim=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.mode_set(mode='OBJECT') if bpy.context.object and bpy.context.object.mode != 'OBJECT' else None
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        o.hide_set(False); o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={'ARMATURE', 'MESH', 'EMPTY'},
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', bake_space_transform=False,
        use_mesh_modifiers=True, mesh_smooth_type='OFF', use_tspace=True, add_leaf_bones=False,
        use_armature_deform_only=True, primary_bone_axis='Y', secondary_bone_axis='X',
        bake_anim=anim, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=anim, bake_anim_force_startend_keying=True, bake_anim_step=1.0,
        bake_anim_simplify_factor=0.0, path_mode='STRIP', embed_textures=False,
        axis_forward='-Z', axis_up='Y')
    log("exported", path)
