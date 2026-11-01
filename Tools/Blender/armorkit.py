"""
High-detail plate armour kit shared by both knights.

Every plate is a lofted shell that gets: subdivision, a rolled (beaded) edge swept along its real boundary,
optional rivet rows set in from the edge, then thickness. Pieces are built for the LEFT side and mirrored.
All positions derive from the character's joint dict J so the same kit fits different proportions.
"""
import math, json
from collections import defaultdict
import bpy, bmesh
from mathutils import Vector, Matrix, noise, kdtree
import charlib as C
import rigdef as R


def V(p):
    return Vector(p)


def Mx(p):
    return Vector((-p[0], p[1], p[2]))


def rigid(b):
    return {"mode": "rigid", "bone": b}


def fixed(**w):
    return {"mode": "fixed", "weights": {k.replace("_L", ".L").replace("_R", ".R"): v for k, v in w.items()}}


def smooth(bones, power=6, mx=3):
    return {"mode": "smooth", "bones": bones, "power": power, "max": mx}


def sym(parts):
    """Mirror a list of left-side parts to the right side; returns left + right."""
    parts = parts if isinstance(parts, list) else [parts]
    out = list(parts)
    for p in parts:
        out.append(C.mirror_x(p, p.name.replace(".L", ".R") + ("" if ".L" in p.name else ".R")))
    return out


def limb(name, p0, p1, rings, segs=32, arc=None, x_hint=(1, 0, 0), cap0=False, cap1=False, dfn=None):
    p0, p1 = V(p0), V(p1)
    L = (p1 - p0).length
    rr = [dict(r, z=r['t'] * L) for r in rings]
    o = C.loft(name, rr, segs, arc=arc, cap0=cap0, cap1=cap1, dfn=dfn)
    return C.place(o, p0, p1 - p0, x_hint)


def dome(name, r, h, segs=40, n=2.0, flat=1.0, rings=10, dfn=None):
    rr = []
    for i in range(rings + 1):
        a = i / rings * math.pi / 2
        rr.append(dict(z=h * math.sin(a), rx=r * math.cos(a) + 1e-4, ry=r * flat * math.cos(a) + 1e-4, n=n))
    return C.loft(name, rr, segs, cap1=True, dfn=dfn)


# ----------------------------------------------------------------------------------------------
# Plate finishing: rolled edges and rivets
# ----------------------------------------------------------------------------------------------

def boundary_loops(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    adj = defaultdict(list)
    for e in bm.edges:
        if e.is_boundary:
            a, b = e.verts[0].index, e.verts[1].index
            adj[a].append(b); adj[b].append(a)
    co = {v.index: v.co.copy() for v in bm.verts}
    bm.free()
    seen, loops = set(), []
    starts = [v for v in adj if len(adj[v]) == 1] + list(adj.keys())
    for s in starts:
        if s in seen:
            continue
        chain, prev, cur = [s], None, s
        seen.add(s)
        while True:
            nxt = [n for n in adj[cur] if n != prev and n not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            chain.append(cur); seen.add(cur)
        closed = len(chain) > 2 and s in adj[cur]
        if len(chain) >= 3:
            loops.append(([co[i] for i in chain], closed))
    return loops


def resample(pts, closed, step):
    pts = list(pts) + ([pts[0]] if closed else [])
    out = [pts[0]]
    carry = 0.0
    for a, b in zip(pts, pts[1:]):
        seg = (b - a).length
        if seg < 1e-9:
            continue
        d = step - carry
        while d <= seg:
            out.append(a.lerp(b, d / seg))
            d += step
        carry = seg - (d - step)
    if closed and len(out) > 1 and (out[-1] - out[0]).length < step * 0.5:
        out.pop()
    elif not closed and (out[-1] - pts[-1]).length > step * 0.3:
        out.append(pts[-1])
    return out


def domes_mesh(name, centers, normals, r, height=0.45, segs=10):
    verts, faces = [], []
    rings = 3
    for c, n in zip(centers, normals):
        rot = C.basis(n, (1, 0, 0) if abs(n.x) < 0.9 else (0, 1, 0))
        base = len(verts)
        for i in range(rings):
            a = i / rings * math.pi / 2
            rr, z = r * math.cos(a), r * height * math.sin(a)
            for j in range(segs):
                t = 2 * math.pi * j / segs
                verts.append(c + rot @ Vector((rr * math.cos(t), rr * math.sin(t), z)))
        top = len(verts)
        verts.append(c + rot @ Vector((0, 0, r * height)))
        for i in range(rings - 1):
            for j in range(segs):
                a0 = base + i * segs + j; a1 = base + i * segs + (j + 1) % segs
                faces.append((a0, a1, a1 + segs, a0 + segs))
        last = base + (rings - 1) * segs
        for j in range(segs):
            faces.append((last + j, last + (j + 1) % segs, top))
    return C.mesh_obj(name, verts, faces, smooth=True)


def plate(name, obj, mat, bind, t=0.0028, roll=0.0042, sub=2, rivets=0.0, rivet_r=0.0055, rivet_mat=None,
          inset=0.013, min_loop=0.04, roll_mat=None):
    """Finish a single-sided shell into an armour plate. Returns a list of parts."""
    if sub:
        C.subsurf(obj, sub)
        C.apply_mods(obj)
    me = obj.data
    me.update()
    loops = boundary_loops(obj) if (roll or rivets) else []
    n = len(me.vertices)
    kd = kdtree.KDTree(n)
    for v in me.vertices:
        kd.insert(v.co, v.index)
    kd.balance()
    normals = [v.normal.copy() for v in me.vertices]
    centroid = sum((v.co for v in me.vertices), Vector()) / max(1, n)
    if t:
        C.solidify(obj, t, -1)
        C.apply_mods(obj)
    obj.data.shade_smooth()
    C.set_mat(obj, mat)
    obj["bind"] = json.dumps(bind)
    parts = [obj]
    centers, nrms = [], []
    for i, (pts, closed) in enumerate(loops):
        length = sum((b - a).length for a, b in zip(pts, pts[1:] + ([pts[0]] if closed else [])))
        if length < min_loop:
            continue
        if roll:
            path = resample(pts, closed, 0.005)
            if len(path) >= 3:
                tube = C.sweep(f"{name}_roll{i}", path, C.circle_profile(roll, 8), closed_path=closed, cap=not closed)
                parts.append(C.finish(tube, roll_mat or mat, bind, sub=0))
        if rivets:
            for p in resample(pts, closed, rivets)[: (None if closed else -1)]:
                _, idx, _ = kd.find(p)
                nn = normals[idx]
                inward = centroid - p
                inward = inward - inward.project(nn)
                if inward.length < 1e-6:
                    continue
                centers.append(p + inward.normalized() * inset + nn * 0.0005)
                nrms.append(nn)
    if centers:
        rv = domes_mesh(f"{name}_rivets", centers, nrms, rivet_r)
        rv.data.materials.append(rivet_mat or mat)
        rv["bind"] = json.dumps(bind)
        parts.append(rv)
    return parts


def strap(name, path, mat, bind, w=0.022, t=0.004, buckle_mat=None, buckle_at=0.5):
    parts = [C.finish(C.sweep(name, path, C.rect_profile(w, t), up=(0, 0, 1)), mat, bind, sub=1)]
    if buckle_mat is not None:
        i = int(buckle_at * (len(path) - 1))
        p = path[i]
        d = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
        frame = C.sweep(name + "_buckle", [p - d * 0.012, p + d * 0.012], C.rect_profile(w * 1.35, t * 2.2, t * 0.6), up=(0, 0, 1))
        parts.append(C.finish(frame, buckle_mat, bind, sub=1))
    return parts


# ----------------------------------------------------------------------------------------------
# The kit
# ----------------------------------------------------------------------------------------------

class Kit:
    """
    J: joint dict (left side + centre). w: girth scale. m: materials dict with keys
    plate, rivet, leather, chain, cloth, trim, brass. style: dict of switches.
    """

    def __init__(self, J, m, w=1.0, style=None):
        self.J, self.m, self.w = J, m, w
        self.s = style or {}

    def z(self, a, b, t):
        return self.J[a][2] + (self.J[b][2] - self.J[a][2]) * t

    # ---------------- underlayer ----------------
    def underbody(self, head=True):
        J, w = self.J, self.w
        verts, edges, radii = [], [], []

        def add(p, r):
            verts.append(V(p)); radii.append((r[0] * w, r[1] * w)); return len(verts) - 1

        iP = add(J['pelvis'], (0.15, 0.11)); iS = add(J['spine'], (0.135, 0.1)); iC = add(J['chest'], (0.16, 0.11))
        iN = add(J['neck'], (0.065, 0.065))
        edges += [(iP, iS), (iS, iC), (iC, iN)]
        if head:
            iH = add((0, 0.0, (J['head'][2] + J['headTop'][2]) / 2), (0.085, 0.09)); edges.append((iN, iH))
        for f in (V, Mx):
            a = add(f(J['clav']), (0.07, 0.06)); b = add(f(J['shoulder']), (0.065, 0.06))
            c = add(f(J['elbow']), (0.052, 0.05)); d = add(f(J['wrist']), (0.042, 0.038))
            edges += [(iC, a), (a, b), (b, c), (c, d)]
            h = add(f(J['hip']), (0.108, 0.105)); k = add(f(J['knee']), (0.068, 0.068))
            an = add(f(J['ankle']), (0.047, 0.05)); t = add(f(J['toe']), (0.045, 0.035))
            edges += [(iP, h), (h, k), (k, an), (an, t)]
        me = bpy.data.meshes.new("Underbody")
        me.from_pydata([tuple(v) for v in verts], edges, [])
        o = C.link(bpy.data.objects.new("Underbody", me))
        o.modifiers.new("skin", 'SKIN')
        if len(me.skin_vertices) == 0:
            me.skin_vertices.new()
        sv = me.skin_vertices[0].data
        for i, r in enumerate(radii):
            sv[i].radius = r
            sv[i].use_root = (i == iP)
        C.subsurf(o, 2)
        return [C.finish(o, self.m['chain'], smooth(R.LIMB_SMOOTH, 6, 3), sub=0)]

    # ---------------- helmets ----------------
    def _skull_rings(self, front_extra=0.0):
        J, w = self.J, self.w
        hz, tz = J['head'][2], J['headTop'][2]
        H = tz - hz
        spec = [(-0.25, .095, .105, .1), (-0.05, .118, .135, .128), (0.2, .13, .152, .14), (0.45, .138, .162, .148),
                (0.68, .136, .156, .146), (0.86, .122, .136, .132), (1.0, .096, .108, .106), (1.1, .058, .064, .064),
                (1.15, .02, .022, .022)]
        return [dict(z=hz + t * H, rx=rx * w, ry=(ry + front_extra) * w, ryb=ryb * w, cy=-0.01) for t, rx, ry, ryb in spec]

    def helm_armet(self):
        """Italian armet: skull with low comb, rounded visor with a sight slit, bevor, rondel, visor pivots."""
        J, m, w = self.J, self.m, self.w
        hz, tz = J['head'][2], J['headTop'][2]
        H = tz - hz
        parts = []

        def comb(a, ri, p):
            d = min(abs((a + 90 + 180) % 360 - 180), abs((a - 90 + 180) % 360 - 180))
            k = 0.012 * math.exp(-(d / 6.0) ** 2) * (1.0 if p.z > hz + 0.3 * H else 0.0)
            r = Vector((p.x, p.y + 0.01, 0))
            return r.normalized() * k if r.length > 1e-5 else Vector()

        skull = C.loft("Skull", self._skull_rings(), 64, cap1=True, dfn=comb)
        # open the face: remove the front lower quadrant (the visor and bevor close it)
        parts += plate("Skull", skull, m['plate'], rigid("head"), rivets=0.035, rivet_mat=m['rivet'])
        vr = [dict(z=hz + t * H, rx=(rx + 0.006) * w, ry=(ry + 0.012) * w, cy=-0.012) for t, rx, ry in
              [(0.0, .118, .14), (0.25, .132, .158), (0.5, .138, .166), (0.72, .136, .16), (0.82, .128, .15)]]

        def beak(a, ri, p):
            # sparrow-beak visor: a broad forward swell with a sharp central crease
            d = abs((a + 90 + 180) % 360 - 180)
            t = (p.z - hz) / H
            env = math.sin(max(0.0, min(1.0, t / 0.8)) * math.pi)
            return Vector((0, -(0.03 * math.exp(-(d / 24) ** 2) + 0.016 * math.exp(-(d / 5) ** 2)) * env, 0))

        visor = C.loft("Visor", vr, 40, arc=(-158, -22), dfn=beak)
        C.subsurf(visor, 2); C.apply_mods(visor)
        cut = C.box("SightCut", (0.26, 0.2, 0.016), (0, -0.17, hz + 0.6 * H))
        breaths = [C.box(f"Breath{i}", (0.006, 0.2, 0.024), (-0.03 - 0.014 * i, -0.17, hz + 0.25 * H)) for i in range(5)]
        cutter = C.join([cut] + breaths, "VisorCutter")
        C.boolean(visor, cutter); C.apply_mods(visor)
        bpy.data.objects.remove(cutter)
        parts += plate("Visor", visor, m['plate'], rigid("head"), sub=0)
        br = [dict(z=hz + t * H, rx=(rx + 0.01) * w, ry=(ry + 0.016) * w, cy=-0.01) for t, rx, ry in
              [(-0.3, .1, .115), (-0.12, .118, .138), (0.08, .128, .152), (0.18, .13, .156)]]
        parts += plate("Bevor", C.loft("Bevor", br, 40, arc=(-165, -15)), m['plate'], rigid("head"), rivets=0.03,
                       rivet_mat=m['rivet'])
        for sx in (1, -1):
            p = V((0.142 * w * sx, -0.015, hz + 0.55 * H))
            parts.append(C.finish(C.uv_sphere("Pivot", 0.011, p, 12, 8, (0.5, 1, 1)), m['rivet'], rigid("head"), sub=0))
        # rondel on a stem at the back of the neck
        rp = V((0, 0.14 * w, hz - 0.02))
        stem = C.sweep("RondelStem", [rp - V((0, 0.03, 0)), rp], C.circle_profile(0.006, 8), up=(0, 0, 1))
        parts.append(C.finish(stem, m['plate'], rigid("head"), sub=1))
        rd = dome("Rondel", 0.04, 0.008, 32)
        C.place(rd, rp, (0, 1, 0), (1, 0, 0))
        parts += plate("Rondel", rd, m['plate'], rigid("head"), sub=1, rivets=0.0)
        return parts

    def helm_crested(self):
        """Original dark-fantasy close helm: barred visor and a fan of flame-like fins along the crest."""
        J, m, w = self.J, self.m, self.w
        hz, tz = J['head'][2], J['headTop'][2]
        H = tz - hz
        parts = []
        rings = self._skull_rings(front_extra=0.008)

        def ridge(a, ri, p):
            d = abs((a + 90 + 180) % 360 - 180)
            k = 0.012 * math.exp(-(d / 9.0) ** 2) * (1.0 if p.z > hz + 0.1 * H else 0.3)
            r = Vector((p.x, p.y + 0.01, 0))
            return r.normalized() * k if r.length > 1e-5 else Vector()

        helm = C.loft("Helm", rings, 64, cap1=True, dfn=ridge)
        C.subsurf(helm, 2); C.apply_mods(helm)
        cuts = [C.box("Sight", (0.24, 0.2, 0.014), (0, -0.17, hz + 0.58 * H))]
        for i in range(7):          # vertical breathing bars below the sight
            cuts.append(C.box(f"Bar{i}", (0.008, 0.2, 0.07), (-0.06 + 0.02 * i, -0.17, hz + 0.27 * H)))
        cutter = C.join(cuts, "HelmCutter")
        C.boolean(helm, cutter); C.apply_mods(helm)
        bpy.data.objects.remove(cutter)
        parts += plate("Helm", helm, m['plate'], rigid("head"), sub=0, rivets=0.04, rivet_mat=m['rivet'])
        brow = C.sweep("Brow", C.arc_path((0, -0.012, hz + 0.66 * H), 1.0, -160, -20, 32, (0.145 * w, 0, 0), (0, 0.17 * w, 0)),
                       C.rect_profile(0.02, 0.012, 0.004), up=(0, 0, 1))
        parts.append(C.finish(brow, m['plate'], rigid("head"), sub=1))
        # fan of fins along the crest, tallest at the front
        for i in range(5):
            f = i / 4.0
            ang = math.radians(-60 + 120 * f)      # along the crest from front to back
            base = V((0, -0.01 + 0.15 * w * math.sin(ang), hz + H * 1.02 + 0.03 * math.cos(ang) - 0.02))
            hgt = (0.16 - 0.06 * f) * (1.0 if i != 1 else 1.08)
            lean = V((0, 0.4 + 0.35 * f, 1.0)).normalized()

            def fin(u, v, base=base, hgt=hgt, lean=lean, f=f):
                # flame-like: broad base, swept back, curling at the tip
                width = 0.085 * (1 - v) ** 0.7 * (1.0 - 0.3 * f)
                y = (u - 0.5) * width + 0.025 * math.sin(v * math.pi) * (1 - f)
                return base + V((0, y, 0)) + lean * (v * hgt) + V((0, 0.06 * v * v, -0.02 * v * v))

            fin_o = C.surface(f"Fin{i}", fin, 6, 10)
            parts += plate(f"Fin{i}", fin_o, m['plate'], rigid("head"), t=0.004, roll=0.0025, sub=1)
        return parts

    def gorget(self):
        J, m, w = self.J, self.m, self.w
        parts = []
        nz = J['neck'][2]
        for k, (z0, z1, r0, bind) in enumerate([(nz - 0.09, nz - 0.03, .165, fixed(chest=1.0)),
                                                (nz - 0.045, nz + 0.015, .138, fixed(chest=0.6, neck=0.4)),
                                                (nz + 0.0, nz + 0.055, .118, fixed(chest=0.3, neck=0.7))]):
            g = C.loft(f"Gorget{k}", [dict(z=z0, rx=(r0 + 0.012) * w, ry=(r0 * 0.92 + 0.012) * w, cy=0.005),
                                      dict(z=z1, rx=r0 * w, ry=r0 * 0.92 * w, cy=0.005)], 56)
            parts += plate(f"Gorget{k}", g, m['plate'], bind, sub=1, rivets=0.06 if k == 0 else 0.0, rivet_mat=m['rivet'])
        return parts

    # ---------------- torso ----------------
    def cuirass(self, keel=0.018, flutes=0, dents=0.0):
        J, m, w = self.J, self.m, self.w
        zb, zt = J['pelvis'][2] + 0.035, J['neck'][2] - 0.025
        spec = [(0.0, .15, .114, .1), (0.15, .155, .124, .104), (0.38, .176, .156, .11), (0.6, .194, .176, .117),
                (0.78, .2, .166, .119), (0.9, .188, .145, .115), (0.97, .16, .115, .1), (1.0, .132, .096, .09)]
        rr = [dict(z=zb + t * (zt - zb), rx=rx * w, ry=ry * w, ryb=ryb * w, cy=0.012, n=2.12) for t, rx, ry, ryb in spec]

        def shape(a, ri, p):
            d = abs((a + 90 + 180) % 360 - 180)
            t = (p.z - zb) / (zt - zb)
            h = max(0.0, min(1.0, t / 0.12)) * max(0.0, min(1.0, (1.0 - t) / 0.1))
            off = -keel * math.exp(-(d / 12) ** 2) * h
            if flutes:
                off -= 0.006 * h * max(0.0, math.cos(math.radians(d) * flutes * 2)) * (1 if d < 70 else 0) * (1 - t)
            if dents:
                off += dents * noise.noise(p * 9.0)
            return Vector((0, off, 0)) if d < 90 else Vector((0, 0, 0))

        cu = C.loft("Cuirass", rr, 80, dfn=shape)
        parts = plate("Cuirass", cu, m['plate'], smooth(["spine", "chest"], 4, 2), rivets=0.05, rivet_mat=m['rivet'])
        # plackart with an ogee-pointed top
        pr = [dict(z=zb - 0.005 + 0.2 * i / 7, rx=(.167 - 0.003 * i) * w, ry=(.133 + 0.004 * (i % 3 == 1)) * w, cy=0.012, n=2.12)
              for i in range(8)]

        def ogee(a, ri, p):
            d = abs((a + 90 + 180) % 360 - 180)
            return Vector((0, -0.004, -(p.z - zb) * 0.62 * min(1.0, (d / 62.0) ** 1.3)))

        parts += plate("Plackart", C.loft("Plackart", pr, 44, arc=(-158, -22), dfn=ogee), m['plate'],
                       fixed(spine=0.7, hips=0.3), rivets=0.045, rivet_mat=m['rivet'])
        # armpit gussets
        for sx in (1,):
            g = dome("Gusset.L", 0.06 * w, 0.015, 24)
            C.place(g, V((0.175 * w, -0.04, self.z('chest', 'neck', 0.55))), (0.7, -0.6, 0.2), (0, 0, 1))
            parts += sym(plate("Gusset.L", g, m['plate'], fixed(chest=0.7, clavicle_L=0.3), sub=1))
        return parts

    def faulds(self, count=3, flare=0.009, skirt_len=0.0):
        J, m, w = self.J, self.m, self.w
        zt = J['pelvis'][2] + 0.075
        parts = []
        for k in range(count):
            z0 = zt - 0.055 * k
            f = C.loft(f"Fauld{k}", [dict(z=z0, rx=(.166 + flare * k) * w, ry=(.129 + flare * k) * w, ryb=(.11 + 0.006 * k) * w, cy=0.012, n=2.1),
                                     dict(z=z0 - 0.068, rx=(.177 + flare * k) * w, ry=(.139 + flare * k) * w, ryb=(.116 + 0.006 * k) * w, cy=0.012, n=2.1)], 64,
                       arc=(-200, 20))
            parts += plate(f"Fauld{k}", f, m['plate'], rigid("hips"), rivets=0.07, rivet_mat=m['rivet'], sub=1)
        return parts

    def tassets(self, lames=3):
        J, m, w = self.J, self.m, self.w
        parts = []
        hz = J['pelvis'][2] - 0.08
        for k in range(lames):
            d0 = 0.075 * k
            t = limb(f"Tasset{k}.L", (J['hip'][0] + 0.005, -0.005, hz - d0), (J['hip'][0] + 0.015, -0.02, hz - 0.3 - d0),
                     [dict(t=0.0, rx=(.146 + .008 * k) * w, ry=(.146 + .008 * k) * w), dict(t=0.32, rx=(.153 + .008 * k) * w, ry=(.153 + .008 * k) * w)],
                     32, arc=(22, 168))
            parts += sym(plate(f"Tasset{k}.L", t, m['plate'], fixed(hips=0.35, thigh_L=0.65), rivets=0.05, rivet_mat=m['rivet'], sub=1))
        return parts

    def belt(self, mat_key='leather'):
        J, m, w = self.J, self.m, self.w
        z = J['pelvis'][2] + 0.04
        pts = [V((0.178 * w * math.cos(a), 0.012 + (0.141 if math.sin(a) < 0 else 0.12) * w * math.sin(a), z))
               for a in [2 * math.pi * i / 72 for i in range(72)]]
        parts = [C.finish(C.sweep("Belt", pts, C.rect_profile(0.045, 0.008, 0.002), closed_path=True, cap=False), m[mat_key], rigid("hips"), sub=1)]
        parts.append(C.finish(C.box("Buckle", (0.06, 0.016, 0.055), (0, -0.135 * w - 0.01, z)), m['brass'], rigid("hips"), bev=(0.006, 3), sub=1))
        return parts

    def arming_skirt(self, color_key='cloth', trim_key='trim'):
        """Pleated arming skirt below the faulds with a contrasting hem band (reference: black with gold hem)."""
        J, m, w = self.J, self.m, self.w
        z0 = J['pelvis'][2] - 0.04
        z1 = J['knee'][2] + 0.17
        rings = []
        for i in range(9):
            t = i / 8
            rings.append(dict(z=z0 + (z1 - z0) * t, rx=(0.152 + 0.115 * t) * w, ry=(0.118 + 0.1 * t) * w, ryb=(0.106 + 0.092 * t) * w, cy=0.01))

        def pleat(a, ri, p):
            t = ri / 8
            k = 0.011 * (0.1 + t) * math.sin(math.radians(a) * 22)
            r = Vector((p.x, p.y - 0.01, 0))
            return r.normalized() * k if r.length > 1e-5 else Vector()

        sk = C.loft("ArmingSkirt", rings, 132, dfn=pleat)
        parts = [C.finish(sk, m[color_key], smooth(["hips", "thigh.L", "thigh.R"], 3, 3), t=0.004, offset=0, sub=1, even=False)]
        hem = [dict(z=z1 + 0.035, rx=(0.26) * w, ry=(0.213) * w, ryb=(0.193) * w, cy=0.01), dict(z=z1 - 0.004, rx=0.267 * w, ry=0.219 * w, ryb=0.199 * w, cy=0.01)]
        h = C.loft("SkirtHem", hem, 132, dfn=lambda a, ri, p: (Vector((p.x, p.y - 0.01, 0)).normalized() *
                                                             (0.011 * 1.4 * math.sin(math.radians(a) * 22) + 0.003)))
        parts.append(C.finish(h, m[trim_key], smooth(["hips", "thigh.L", "thigh.R"], 3, 3), t=0.005, offset=0, sub=1, even=False))
        return parts

    def mail_skirt(self):
        J, m, w = self.J, self.m, self.w
        z0 = J['pelvis'][2] - 0.02
        z1 = J['knee'][2] + 0.22
        rings = [dict(z=z0 + (z1 - z0) * i / 6, rx=(0.18 + 0.065 * i / 6) * w, ry=(0.14 + 0.06 * i / 6) * w, ryb=(0.128 + 0.05 * i / 6) * w, cy=0.01)
                 for i in range(7)]

        def ragged(a, ri, p):
            return Vector((0, 0, 0.03 * noise.noise(Vector((a * 0.05, 0.3, 1.1))) if ri == 6 else 0))

        sk = C.loft("MailSkirt", rings, 96, dfn=ragged)
        return [C.finish(sk, m['chain'], smooth(["hips", "thigh.L", "thigh.R"], 3, 3), t=0.006, offset=0, sub=1, even=False)]

    # ---------------- arms ----------------
    def pauldron(self, size=1.0, lames=4, haute=True):
        J, m, w = self.J, self.m, self.w
        sh, el = V(J['shoulder']), V(J['elbow'])
        parts = []
        r = 0.17 * size * w

        def dent(a, ri, p):
            return Vector((0, 0, 0))

        # bell-shaped pauldron: a cap over the shoulder that flares down the arm, open toward the armpit
        arm_dir = (el - sh).normalized()
        axis = (arm_dir + V((0, 0, -0.35))).normalized()
        top = sh + V((0.0, 0.004, 0.085 * size))
        bell = [(0.0, .006), (0.025, .085), (0.06, .122), (0.11, .142), (0.17, .15), (0.22, .162)]
        rings = [dict(z=d * size, rx=r_ * 0.95 * size * w, ry=r_ * 1.1 * size * w) for d, r_ in bell]

        def flare(a, ri, p):
            # long lower edge at the front and back, shorter over the outside of the arm
            if ri < len(bell) - 1:
                return Vector()
            s = abs(math.sin(math.radians(a)))
            return Vector((0, 0, 0.035 * s * size))

        d = C.loft("Pauldron.L", rings, 56, arc=(-150, 150), dfn=flare)
        C.place(d, top, axis, (1, 0, 0.6))
        parts += plate("Pauldron.L", d, m['plate'], fixed(clavicle_L=0.45, upperarm_L=0.55), rivets=0.045, rivet_mat=m['rivet'])
        for k in range(lames):
            t0 = 0.16 + 0.05 * k
            l = limb(f"PauldronLame{k}.L", sh + V((0.012, 0, 0.0)), el,
                     [dict(t=t0, rx=(.108 - .006 * k) * w * size, ry=(.1 - .006 * k) * w * size),
                      dict(t=t0 + 0.2, rx=(.116 - .006 * k) * w * size, ry=(.107 - .006 * k) * w * size)], 40, arc=(-130, 210))
            parts += plate(f"PauldronLame{k}.L", l, m['plate'], rigid("upperarm.L"), rivets=0.06, rivet_mat=m['rivet'], sub=1)
        if haute:
            nz = J['neck'][2]
            hp = C.loft("Haute.L", [dict(z=nz - 0.07, rx=0.17 * w, ry=0.14 * w), dict(z=nz + 0.02, rx=0.165 * w, ry=0.135 * w)], 28,
                        arc=(-35, 50))
            parts += plate("Haute.L", hp, m['plate'], fixed(clavicle_L=0.6, chest=0.4), sub=1)
        return parts

    def rerebrace(self):
        J, m, w = self.J, self.m, self.w
        sh, el = V(J['shoulder']), V(J['elbow'])
        rb = limb("Rerebrace.L", sh, el, [dict(t=0.35, rx=.058 * w, ry=.055 * w), dict(t=0.9, rx=.052 * w, ry=.05 * w)], 36)
        return plate("Rerebrace.L", rb, self.m['plate'], rigid("upperarm.L"), sub=1)

    def couter(self):
        J, m, w = self.J, self.m, self.w
        el = V(J['elbow'])
        parts = []
        cop = dome("Couter.L", 0.068 * w, 0.054, 36)
        C.place(cop, el + V((0.012, 0.03, 0.0)), (0.35, 0.94, 0.0), (0, 0, 1))
        parts += plate("Couter.L", cop, m['plate'], fixed(upperarm_L=0.5, forearm_L=0.5), sub=1, rivets=0.0)

        def heart(a, ri, p):
            notch = 1.0 - 0.22 * math.exp(-(((a - 90 + 180) % 360 - 180) / 22.0) ** 2)
            return Vector((p.x * (notch - 1), p.y * (notch - 1), 0))

        fan = dome("CouterFan.L", 0.088 * w, 0.022, 40, 2.0, 0.85, dfn=heart)
        C.place(fan, el + V((0.05, 0.022, 0.0)), (0.95, 0.25, 0.0), (0, 0, 1))
        parts += plate("CouterFan.L", fan, m['plate'], fixed(upperarm_L=0.5, forearm_L=0.5), sub=1, rivets=0.0)
        parts.append(C.finish(C.uv_sphere("CouterBoss.L", 0.012, el + V((0.074, 0.03, 0.0)), 12, 8, (0.5, 1, 1)), m['rivet'],
                              fixed(upperarm_L=0.5, forearm_L=0.5), sub=0))
        return sym(parts)

    def vambrace(self):
        J, m, w = self.J, self.m, self.w
        el, wr = V(J['elbow']), V(J['wrist'])

        def ridge(a, ri, p):
            d = abs((a - 0 + 180) % 360 - 180)            # ridge along the outside of the forearm
            return Vector((0.006 * math.exp(-(d / 14) ** 2), 0, 0))

        vb = limb("Vambrace.L", el, wr, [dict(t=0.1, rx=.054 * w, ry=.05 * w), dict(t=0.5, rx=.05 * w, ry=.046 * w),
                                         dict(t=0.9, rx=.043 * w, ry=.039 * w)], 40, dfn=ridge)
        parts = plate("Vambrace.L", vb, m['plate'], rigid("forearm.L"), rivets=0.0, sub=1)
        # hinge rivets down the inner seam
        for t in (0.25, 0.5, 0.75):
            p = el.lerp(wr, t) + V((-0.052 * w, 0.0, 0.0))
            parts.append(C.finish(C.uv_sphere("VambRivet.L", 0.0055, p, 10, 6, (1, 0.5, 1)), m['rivet'], rigid("forearm.L"), sub=0))
        return sym(parts)

    def gauntlet(self):
        """Hourglass gauntlet: flared cuff, metacarpal lames, knuckle plate, articulated fingers curled round a grip."""
        J, m, w = self.J, self.m, self.w
        el, wr, he = V(J['elbow']), V(J['wrist']), V(J['handEnd'])
        H = (he - wr).normalized()
        G = (V((0, -1, 0)) - V((0, -1, 0)).project(H)).normalized()   # grip axis = hand bone Z (forward in rest)
        P = H.cross(G).normalized()                                      # palm normal (toward the body)
        parts = []
        cuff = limb("Cuff.L", wr + (el - wr).normalized() * 0.09, wr - H * 0.012,
                    [dict(t=0.0, rx=.052 * w, ry=.048 * w), dict(t=0.6, rx=.064 * w, ry=.058 * w), dict(t=1.0, rx=.074 * w, ry=.067 * w)], 40)
        parts += plate("Cuff.L", cuff, m['plate'], rigid("hand.L"), rivets=0.0, sub=1)
        # leather palm under the plates
        palm = C.loft("Palm.L", [dict(z=0.0, rx=.03, ry=.026, n=3), dict(z=0.03, rx=.045, ry=.028, n=3),
                                 dict(z=0.08, rx=.047, ry=.03, n=3), dict(z=0.11, rx=.042, ry=.026, n=3), dict(z=0.12, rx=.02, ry=.012, n=3)],
                      24, cap1=True)
        C.place(palm, wr + P * 0.012, H, G)
        parts.append(C.finish(palm, m['leather'], rigid("hand.L"), sub=1))
        for k in range(3):     # metacarpal lames over the back of the hand
            lam = C.loft(f"Metacarpal{k}.L", [dict(z=0.0, rx=.05, ry=.034, cy=0.008, n=2.6), dict(z=0.032, rx=.051, ry=.035, cy=0.008, n=2.6)],
                         28, arc=(-165, -15))
            C.place(lam, wr + H * (0.012 + 0.026 * k), H, G)
            parts += plate(f"Metacarpal{k}.L", lam, m['plate'], rigid("hand.L"), sub=1, roll=0.0028)
        knuckle = C.loft("Knuckle.L", [dict(z=0.0, rx=.053, ry=.036, cy=0.006, n=2.6), dict(z=0.022, rx=.052, ry=.035, cy=0.006, n=2.6)], 32,
                         arc=(-165, -15),
                         dfn=lambda a, ri, p: Vector((0, -0.004 * max(0.0, math.cos(math.radians(a) * 4.0)), 0)))
        C.place(knuckle, wr + H * 0.09, H, G)
        parts += plate("Knuckle.L", knuckle, m['plate'], rigid("hand.L"), sub=1, roll=0.0028)
        # fingers: three lames each, curled around the grip bar (index toward the blade = +G)
        bar = wr + H * 0.088 + P * 0.036
        for i, (g, scale) in enumerate(((0.032, 1.0), (0.011, 1.05), (-0.01, 1.0), (-0.03, 0.85))):
            k0 = wr + H * 0.108 + G * g - P * 0.004
            c = bar + G * g
            r0 = k0 - c
            rho = r0.length
            u = r0.normalized()
            v = H.cross(G).normalized() * -1 if False else (u.cross(G)).normalized()
            arc = []
            total = math.radians(230) * scale
            for s in range(25):
                a = total * s / 24
                arc.append(c + (u * math.cos(a) + v * math.sin(a)) * rho * (1.0 - 0.12 * s / 24))
            segs = ((0, 9), (9, 17), (17, 25))
            for j, (s0, s1) in enumerate(segs):
                sub_path = arc[s0:s1 + (1 if s1 < 25 else 0)]
                if len(sub_path) < 2:
                    continue
                fw = 0.019 * (0.85 if i == 3 else 1.0)
                fs = C.sweep(f"Finger{i}{j}.L", sub_path, C.rect_profile(fw, 0.015, 0.005), up=tuple(G),
                             scales=[1.0 - 0.08 * j] * len(sub_path))
                parts.append(C.finish(fs, m['plate'], rigid("hand.L"), sub=1))
        thumb = C.bezier_path(wr + H * 0.03 + G * 0.042 + P * 0.006, wr + H * 0.06 + G * 0.05 + P * 0.05,
                              wr + H * 0.085 + G * 0.035 + P * 0.072, wr + H * 0.1 + G * 0.012 + P * 0.068, 16)
        for j, (s0, s1) in enumerate(((0, 9), (8, 16))):
            ts = C.sweep(f"Thumb{j}.L", thumb[s0:s1 + 1], C.rect_profile(0.021, 0.017, 0.006), up=tuple(H))
            parts.append(C.finish(ts, m['plate'], rigid("hand.L"), sub=1))
        return sym(parts)

    # ---------------- legs ----------------
    def cuisse(self):
        J, m, w = self.J, self.m, self.w
        hp, kn = V(J['hip']), V(J['knee'])

        def ridge(a, ri, p):
            d = abs((a - 90 + 180) % 360 - 180)
            return Vector((0, 0.009 * math.exp(-(d / 13) ** 2), 0))

        cu = limb("Cuisse.L", hp + V((0, 0, -0.06)), kn, [dict(t=0.0, rx=.122 * w, ry=.12 * w), dict(t=0.45, rx=.112 * w, ry=.115 * w),
                                                         dict(t=0.93, rx=.084 * w, ry=.088 * w)], 44, arc=(-15, 195), dfn=ridge)
        parts = plate("Cuisse.L", cu, m['plate'], rigid("thigh.L"), rivets=0.07, rivet_mat=m['rivet'])
        back = [V((J['hip'][0] + 0.09 * w * math.cos(a), 0.0 + 0.09 * w * math.sin(a), self.z('hip', 'knee', 0.5))) for a in
                [math.radians(-10 + 200 * i / 20) for i in range(21)]]
        parts += strap("CuisseStrap.L", back, m['leather'], rigid("thigh.L"), buckle_mat=m['brass'], buckle_at=0.15)
        return sym(parts)

    def poleyn(self):
        J, m, w = self.J, self.m, self.w
        kn = V(J['knee'])
        parts = []
        # low, slightly pointed knee cop (a hemisphere reads as a ball)
        cop = dome("Poleyn.L", 0.072 * w, 0.034, 36, 2.0, 1.15,
                   dfn=lambda a, ri, p: Vector((0, 0, 0.008 * math.exp(-((p.x ** 2 + p.y ** 2) / 0.0012)))))
        C.place(cop, kn + V((0, -0.052, 0.0)), (0, -1, 0.12), (1, 0, 0))
        parts += plate("Poleyn.L", cop, m['plate'], fixed(thigh_L=0.5, shin_L=0.5), sub=1)
        for k, dz in enumerate((0.075, -0.07)):     # articulating lames above and below the cop
            lam = limb(f"PoleynLame{k}.L", kn + V((0, -0.01, dz)), kn + V((0, -0.01, dz - 0.03 * (1 if dz > 0 else -1))),
                       [dict(t=0.0, rx=.088 * w, ry=.09 * w), dict(t=1.0, rx=.086 * w, ry=.088 * w)], 32, arc=(-10, 190))
            parts += plate(f"PoleynLame{k}.L", lam, m['plate'], fixed(thigh_L=0.5 if dz > 0 else 0.2, shin_L=0.5 if dz > 0 else 0.8), sub=1, roll=0.003)

        def heart(a, ri, p):
            notch = 1.0 - 0.22 * math.exp(-(((a - 90 + 180) % 360 - 180) / 22.0) ** 2)
            return Vector((p.x * (notch - 1), p.y * (notch - 1), 0))

        fan = dome("PoleynFan.L", 0.07 * w, 0.018, 36, 2.0, 0.85, dfn=heart)
        C.place(fan, kn + V((0.07 * w, -0.02, 0.0)), (1, -0.2, 0), (0, 0, 1))
        parts += plate("PoleynFan.L", fan, m['plate'], fixed(thigh_L=0.5, shin_L=0.5), sub=1)
        return sym(parts)

    def greave(self):
        J, m, w = self.J, self.m, self.w
        kn, an = V(J['knee']), V(J['ankle'])
        rings = [dict(t=0.06, rx=.062 * w, ry=.061 * w), dict(t=0.35, rx=.07 * w, ry=.071 * w), dict(t=0.75, rx=.047 * w, ry=.048 * w),
                 dict(t=0.97, rx=.05 * w, ry=.052 * w)]

        def ridge(a, ri, p):
            d = abs((a - 90 + 180) % 360 - 180)
            return Vector((0, 0.01 * math.exp(-(d / 13) ** 2), 0))

        front = limb("GreaveFront.L", kn + V((0, 0, -0.04)), an, rings, 40, arc=(-5, 185), dfn=ridge)
        parts = plate("GreaveFront.L", front, m['plate'], rigid("shin.L"), sub=1)
        back = limb("GreaveBack.L", kn + V((0, 0, -0.04)), an, [dict(r, rx=r['rx'] + 0.004, ry=r['ry'] + 0.004) for r in rings], 40, arc=(178, 362))
        parts += plate("GreaveBack.L", back, m['plate'], rigid("shin.L"), sub=1)
        for t in (0.2, 0.5, 0.8):
            p = (kn + V((0, 0, -0.04))).lerp(an, t) + V((0.068 * w, 0.0, 0))
            parts.append(C.finish(C.uv_sphere("Hinge.L", 0.006, p, 10, 6, (0.5, 1, 1)), m['rivet'], rigid("shin.L"), sub=0))
        return sym(parts)

    def sabaton(self, pointed=False):
        J, m, w = self.J, self.m, self.w
        ax = J['ankle'][0]
        parts = []
        heel = C.loft("Heel.L", [dict(z=0, rx=.048, ry=.04, ryb=.065, cy=.045, n=2.4), dict(z=0.1, rx=.054, ry=.05, ryb=.075, cy=.05, n=2.4)],
                      32, cap0=True)
        C.place(heel, V((ax, 0.085, 0.0)), (0, -1, 0), (1, 0, 0))
        parts += plate("Heel.L", heel, m['plate'], rigid("foot.L"), sub=1, roll=0.003)
        for k in range(6):          # overlapping lames over the instep
            y = -0.005 - 0.03 * k
            hgt = 0.075 - 0.007 * k
            lam = C.loft(f"SabLame{k}.L", [dict(z=0, rx=.056, ry=hgt * 0.8, ryb=hgt * 0.8, cy=0.0, n=2.6), dict(z=0.036, rx=.055, ry=hgt * 0.78, ryb=hgt * 0.78, n=2.6)],
                         32, arc=(6, 174))
            C.place(lam, V((ax, y, 0.012)), (0, -1, 0), (1, 0, 0))
            parts += plate(f"SabLame{k}.L", lam, m['plate'], rigid("foot.L"), sub=1, roll=0.0028)
        tip_len = 0.095 if pointed else 0.05
        toe = C.loft("ToeCap.L", [dict(z=0, rx=.054, ry=0.0, ryb=.04, cy=0.012, n=2.4), dict(z=tip_len * 0.5, rx=.045, ry=0.0, ryb=.032, cy=0.012, n=2.4),
                                  dict(z=tip_len, rx=.012 if pointed else .03, ry=0.0, ryb=.012 if pointed else .02, cy=0.012, n=2.4)], 32, cap1=True)
        C.place(toe, V((ax, -0.18, 0.0)), (0, -1, 0), (1, 0, 0))
        parts += plate("ToeCap.L", toe, m['plate'], rigid("foot.L"), sub=1, roll=0.003)
        sole = C.box("Sole.L", (0.09, 0.3, 0.014), (ax, -0.06, 0.007))
        parts.append(C.finish(sole, m['leather'], rigid("foot.L"), bev=(0.008, 2), sub=1))
        return sym(parts)

    # ---------------- details ----------------
    def ribbon(self, color_key='ribbon'):
        """A small red silk bow pinned at the gorget (reference detail)."""
        J, m = self.J, self.m
        c = V((0.03, -0.15 * self.w, J['neck'][2] - 0.07))
        parts = []
        for sx in (1, -1):
            loop = C.bezier_path(c, c + V((0.03 * sx, -0.02, 0.025)), c + V((0.045 * sx, -0.015, -0.02)), c, 16)
            parts.append(C.finish(C.sweep("RibbonLoop", loop, C.rect_profile(0.018, 0.002), up=(0, -1, 0)), m[color_key],
                                  rigid("chest"), sub=1))
        for sx in (1, -1):
            tail = C.bezier_path(c, c + V((0.01 * sx, -0.01, -0.04)), c + V((0.025 * sx, -0.012, -0.08)), c + V((0.02 * sx, -0.01, -0.12)), 16)
            parts.append(C.finish(C.sweep("RibbonTail", tail, C.rect_profile(0.016, 0.002), up=(0, -1, 0)), m[color_key],
                                  rigid("chest"), sub=1))
        return parts
