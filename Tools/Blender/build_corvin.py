"""
CORVIN, the Ashbound Knight — dark fantasy greatsword fighter (original design in the spirit of grim
souls-like games): blackened, fire-scorched plate with glowing ember cracks, a crested close helm with a
barred visor, mail skirt, layered ragged tabard and a long torn cape.

Builds the model, materials, skeleton and skin weights, saves ArtSource/Characters/Corvin_model.blend
and renders preview images to Logs/chars/.

blender -b --factory-startup -P build_corvin.py [-- --no-render]
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector, Matrix, noise
import charlib as C
import rigdef as R
from armorkit import Kit, V, Mx, rigid, fixed, smooth, sym, limb, dome, plate

NAME = "Corvin"
J = dict(
    pelvis=(0, 0.0, 1.00), spine=(0, 0.0, 1.12), chest=(0, 0.01, 1.30), neck=(0, 0.02, 1.53),
    head=(0, 0.0, 1.62), headTop=(0, 0.0, 1.88),
    clav=(0.04, 0.0, 1.48), shoulder=(0.215, 0.01, 1.47), elbow=(0.385, 0.04, 1.215),
    wrist=(0.53, 0.0, 0.995), handEnd=(0.6, -0.03, 0.89),
    hip=(0.11, 0.0, 0.97), knee=(0.125, -0.025, 0.53), ankle=(0.13, 0.02, 0.10),
    toe=(0.135, -0.11, 0.035), toeEnd=(0.14, -0.22, 0.03),
)
GRIP = Vector((0, -0.55, 1.0))
WEAPON = dict(grip=tuple(GRIP), tip=tuple(GRIP + Vector((0, 0, 1.47))), edge=(0, -1, 0), hand_r=0.075, hand_l=-0.075)
CAPE = [(0, 0.17, 1.47), (0, 0.21, 1.12), (0, 0.245, 0.78), (0, 0.275, 0.45), (0, 0.30, 0.13)]


def materials():
    return dict(
        plate=C.mat_plate("Corvin_Plate", polished=False, embers=1.0, soot=0.8, rust=0.35),
        rivet=C.mat_plate("Corvin_Rivet", polished=False, soot=0.3, rust=0.5),
        brass=C.mat_metal("Corvin_Brass", base=(0.16, 0.1, 0.04), rust=0.3, wear=0.6, rough=0.5,
                          rust_col=(0.04, 0.06, 0.04), edge_col=(0.45, 0.33, 0.15)),
        blade=C.mat_metal("Corvin_Blade", base=(0.09, 0.09, 0.095), rust=0.3, wear=1.0, rough=0.32,
                          edge_col=(0.6, 0.6, 0.6), dents=0.4),
        dark=C.mat_plate("Corvin_Hilt", polished=False, soot=0.5, rust=0.4),
        chain=C.mat_chain("Corvin_Chain", base=(0.08, 0.078, 0.075), rust=0.45),
        tabard=C.mat_cloth("Corvin_Tabard", (0.07, 0.065, 0.06), dirt=0.7, fade=0.2, pattern=_ember_band),
        cape=C.mat_cloth("Corvin_Cape", (0.05, 0.045, 0.042), dirt=0.6, fade=0.35),
        leather=C.mat_leather("Corvin_Leather", (0.09, 0.06, 0.04)),
        grip=C.mat_leather("Corvin_Grip", (0.05, 0.035, 0.025), grain=320, wear=0.3),
    )


def _ember_band(b, co, col):
    """Faded ember-red band down the centre of the tabard, with charred edges."""
    x = b.n('ShaderNodeSeparateXYZ')
    b.set(x, 'Vector', b.coords('Object'))
    ax = b.math('ABSOLUTE', b.out(x, 'X'))
    band = b.ramp(ax, [(0.05, 1.0), (0.06, 0.0)])
    wear = b.ramp(b.noise(co, 9.0, 6, 0.6), [(0.3, 0.3), (0.7, 1.0)])
    col = b.mix(b.math('MULTIPLY', band, wear), col, (0.15, 0.025, 0.01))
    char = b.ramp(b.noise(co, 14.0, 8, 0.7), [(0.6, 0.0), (0.75, 1.0)])
    return b.mix(char, col, (0.008, 0.006, 0.005))


def cloth(m):
    parts = []
    # ragged cloth mantle wrapped around the neck and shoulders
    rr = [dict(z=1.4, rx=.3, ry=.215, ryb=.25, cy=0.02), dict(z=1.46, rx=.285, ry=.2, ryb=.235, cy=0.02),
          dict(z=1.52, rx=.24, ry=.17, ryb=.2, cy=0.022), dict(z=1.57, rx=.17, ry=.135, ryb=.15, cy=0.022),
          dict(z=1.6, rx=.13, ry=.11, ryb=.12, cy=0.02)]

    def ragged(a, ri, p):
        # deep vertical folds that grow toward the hem, plus a torn, uneven hem
        k = (4 - ri) / 4.0
        fold = 0.03 * k * math.sin(math.radians(a) * 11 + 0.6 * math.sin(math.radians(a) * 3))
        radial = Vector((p.x, p.y - 0.02, 0))
        radial = radial.normalized() * fold if radial.length > 1e-5 else Vector()
        drop = 0.0
        if ri == 0:
            drop = 0.09 * max(0.0, noise.noise(Vector((a * 0.07, 0.2, 7.0)))) + 0.05 * max(0.0, math.sin(math.radians(a) * 7))
        return radial + Vector((0, 0, -drop))

    rr = [dict(r, z=r['z'] - (0.06 if i == 0 else 0.0)) for i, r in enumerate(rr)]
    mantle = C.loft("Mantle", rr, 160, arc=(-62, 242), dfn=ragged)
    C.subsurf(mantle, 2); C.apply_mods(mantle)
    C.displace(mantle, 0.018, 9.0, seed=21)
    C.displace(mantle, 0.006, 30.0, seed=22)
    parts.append(C.finish(mantle, m['tabard'], fixed(chest=0.85, neck=0.15), t=0.012, offset=1, sub=1, even=False))
    # layered ragged tabard: a long front/back panel plus shorter side flaps
    for side, y0, flare, length, width in (("Front", -0.152, -1, 0.66, 0.3), ("Back", 0.13, 1, 0.7, 0.32),
                                           ("FlapL", -0.1, -1, 0.42, 0.14), ("FlapR", -0.1, -1, 0.38, 0.14)):
        xoff = 0.13 if side == "FlapL" else -0.13 if side == "FlapR" else 0.0

        def fn(u, v, y0=y0, flare=flare, length=length, width=width, xoff=xoff):
            w = width + 0.12 * v
            x = xoff + (u - 0.5) * w
            z = 1.07 - v * length
            y = y0 + flare * (0.045 * v + 0.014 * math.sin(u * math.pi)) \
                + flare * 0.014 * math.sin(u * math.pi * 6 + v * 1.7) * v + 0.008 * noise.noise(Vector((u * 4, v * 4, 1.3 + xoff)))
            if xoff:
                y += 0.06 * abs(xoff) / 0.13 * flare * 0.3
                x += math.copysign(0.03 * v, xoff)
            return (x, y, z)

        def keep(u, v, xoff=xoff):
            hem = 0.86 + 0.13 * noise.noise(Vector((u * 11.0, 0.3, 2.1 + xoff)))
            hole = v > 0.45 and noise.noise(Vector((u * 7, v * 7, 5.5 + xoff))) > 0.38
            return v < hem and not hole

        tb = C.surface(f"Tabard{side}", fn, 36, 50, keep=keep)
        parts.append(C.finish(tb, m['tabard'], smooth(["hips", "thigh.L", "thigh.R"], 3, 3), t=0.004, offset=0, sub=1, even=False))

    def cape_fn(u, v):
        w = 0.44 + 0.34 * v
        x = (u - 0.5) * w
        z = 1.5 - v * 1.4
        top = max(0.0, 1.0 - v / 0.08)
        y = 0.165 + 0.085 * v + 0.034 * math.sin(u * math.pi * 7 + 0.4) * (0.25 + v) \
            + 0.012 * noise.noise(Vector((u * 5, v * 5, 0.7))) - top * 0.02 * math.cos((u - 0.5) * math.pi)
        x *= 1.0 + 0.25 * top
        return (x, y, z)

    def cape_keep(u, v):
        hem = 0.84 + 0.16 * noise.noise(Vector((u * 13.0, 0.5, 3.3)))
        slit = v > 0.45 and (abs(u - 0.32 - 0.02 * math.sin(v * 9)) < 0.008 or abs(u - 0.7 + 0.015 * math.sin(v * 7)) < 0.006)
        hole = v > 0.4 and noise.noise(Vector((u * 6, v * 6, 9.1))) > 0.4
        return v < hem and not slit and not hole

    cape = C.surface("Cape", cape_fn, 56, 90, keep=cape_keep)
    parts.append(C.finish(cape, m['cape'], smooth(["chest", "cape.1", "cape.2", "cape.3", "cape.4"], 4, 2),
                          t=0.005, offset=0, sub=1, even=False))
    # rope belt over the tabard
    pts = [V((0.185 * math.cos(a), 0.012 + (0.165 if math.sin(a) < 0 else 0.14) * math.sin(a), 1.035 + 0.01 * math.sin(a * 3)))
           for a in [2 * math.pi * i / 80 for i in range(80)]]
    rope = C.sweep("Rope", pts, C.circle_profile(0.011, 8), closed_path=True, cap=False,
                   twist=[i * 0.9 for i in range(80)])
    parts.append(C.finish(rope, m['leather'], rigid("hips"), sub=1))
    return parts


def sword(m):
    parts = []
    G = GRIP

    def at(o):
        return C.transform(o, Matrix.Translation(G))

    # faceted wheel pommel
    pom = C.loft("Pommel", [dict(z=-0.215, rx=.02, ry=.015), dict(z=-0.206, rx=.042, ry=.026, n=8), dict(z=-0.185, rx=.052, ry=.032, n=8),
                            dict(z=-0.163, rx=.047, ry=.03, n=8), dict(z=-0.15, rx=.028, ry=.02), dict(z=-0.14, rx=.018, ry=.018)],
                 8, cap0=True, cap1=True)
    parts.append(C.finish(at(pom), m['dark'], rigid("weapon"), bev=(0.003, 2), sub=1))
    grip = C.loft("Grip", [dict(z=-0.14, rx=.019), dict(z=-0.1, rx=.021), dict(z=0.0, rx=.023), dict(z=0.1, rx=.021), dict(z=0.15, rx=.019)], 24)
    parts.append(C.finish(at(grip), m['grip'], rigid("weapon"), sub=1))
    # raised leather wrap ridges (helix) and ferrules
    helix = [V((0.0225 * math.cos(a), 0.0225 * math.sin(a), -0.13 + 0.27 * a / (2 * math.pi * 9))) for a in
             [2 * math.pi * 9 * i / 360 for i in range(361)]]
    parts.append(C.finish(at(C.sweep("Wrap", helix, C.rect_profile(0.008, 0.003, 0.001), up=(0, 0, 1))), m['grip'], rigid("weapon"), sub=0))
    for z in (-0.135, 0.145):
        fer = C.loft("Ferrule", [dict(z=z - 0.012, rx=.025), dict(z=z + 0.012, rx=.025)], 24)
        parts.append(C.finish(at(fer), m['dark'], rigid("weapon"), bev=(0.002, 2), sub=1))
    # crossguard with flared, scrolled ends
    gpath = [Vector((0, y, 0.168 + 0.35 * (abs(y) ** 2))) for y in [-0.23 + 0.46 * i / 30 for i in range(31)]]
    guard = C.sweep("Guard", gpath, C.rect_profile(0.03, 0.026, 0.007), up=(1, 0, 0),
                    scales=[(0.72 + 0.28 * math.cos((i / 30 - 0.5) * math.pi), 1.0 + 0.4 * (abs(i / 30 - 0.5) * 2) ** 4) for i in range(31)])
    parts.append(C.finish(at(guard), m['dark'], rigid("weapon"), bev=(0.002, 2), sub=1))
    for y in (-0.235, 0.235):
        scroll = C.arc_path((0, y * 1.02, 0.2), 0.016, 0, 300, 18, (0, 1 if y > 0 else -1, 0), (0, 0, 1))
        parts.append(C.finish(at(C.sweep("Scroll", scroll, C.circle_profile(0.0075, 10), up=(1, 0, 0))), m['dark'], rigid("weapon"), sub=1))
    blk = C.box("GuardBlock", (0.042, 0.08, 0.055), (0, 0, 0.17))
    parts.append(C.finish(at(blk), m['dark'], rigid("weapon"), bev=(0.009, 3), sub=1))
    # ricasso with parrying lugs
    ric = C.box("Ricasso", (0.016, 0.07, 0.12), (0, 0, 0.255))
    parts.append(C.finish(at(ric), m['blade'], rigid("weapon"), bev=(0.003, 2), sub=1))
    for s in (1, -1):
        lug = C.bezier_path((0, s * 0.033, 0.31), (0, s * 0.07, 0.315), (0, s * 0.075, 0.29), (0, s * 0.058, 0.275), 12)
        parts.append(C.finish(at(C.sweep("Lug", lug, C.rect_profile(0.012, 0.012, 0.003), up=(1, 0, 0),
                                         scales=[1.0 - 0.5 * i / 12 for i in range(13)])), m['blade'], rigid("weapon"), sub=1))
    # blade: diamond section with a fuller, chipped edges
    w, t = 0.043, 0.012
    prof = [(0, -w), (t * 0.55, -w * 0.55), (t * 0.32, -w * 0.12), (t * 0.32, w * 0.12), (t * 0.55, w * 0.55), (0, w),
            (-t * 0.55, w * 0.55), (-t * 0.32, w * 0.12), (-t * 0.32, -w * 0.12), (-t * 0.55, -w * 0.55)]
    n = 60
    path = [Vector((0, 0, 0.31 + 1.16 * i / n)) for i in range(n + 1)]
    sc = []
    for i in range(n + 1):
        f = i / n
        s = 1.0 - 0.33 * f ** 1.3 if f < 0.86 else (1.0 - 0.33 * 0.86 ** 1.3) * max(0.03, (1.0 - f) / 0.14)
        sc.append((max(0.25, s) if f < 0.98 else 0.25, s))
    bl = C.sweep("Blade", path, prof, scales=sc, up=(1, 0, 0))
    for v in bl.data.vertices:
        if abs(v.co.y) > 0.6 * w * 0.3 and abs(v.co.x) < 1e-4:
            chip = max(0.0, noise.noise(Vector((v.co.z * 18.0, v.co.y * 5, 0.4))) - 0.15) * 0.01
            v.co.y -= math.copysign(chip, v.co.y)
    bl.data.update()
    C.bevel(bl, 0.0012, 1, 50); C.apply_mods(bl)
    bl.data.shade_smooth()
    try:
        bl.data.set_sharp_from_angle(angle=math.radians(35))
    except Exception:
        pass
    parts.append(C.finish(at(bl), m['blade'], rigid("weapon"), sub=0, shade=False))
    for p in parts:
        p["weapon"] = True
    return parts


def build(render=True):
    C.reset_scene()
    m = materials()
    kit = Kit(J, m, w=1.0)
    steps = [
        ("underbody", lambda: kit.underbody(head=True)),
        ("helm", kit.helm_crested),
        ("gorget", kit.gorget),
        ("cuirass", lambda: kit.cuirass(keel=0.02, dents=0.0025)),
        ("faulds", lambda: kit.faulds(3)),
        ("tassets", lambda: kit.tassets(3)),
        ("mail", kit.mail_skirt),
        ("pauldrons", lambda: sym(kit.pauldron(size=1.05, lames=4, haute=False))),
        ("rerebrace", lambda: sym(kit.rerebrace())),
        ("couters", kit.couter),
        ("vambraces", kit.vambrace),
        ("gauntlets", kit.gauntlet),
        ("cuisses", kit.cuisse),
        ("poleyns", kit.poleyn),
        ("greaves", kit.greave),
        ("sabatons", lambda: kit.sabaton(pointed=False)),
        ("cloth", lambda: cloth(m)),
        ("sword", lambda: sword(m)),
    ]
    parts = []
    for label, fn in steps:
        new = fn()
        C.log(label, len(new), "parts")
        parts += new
    for p in parts:
        co = [v.co for v in p.data.vertices]
        if co:
            ext = max(max(c[i] for c in co) - min(c[i] for c in co) for i in range(3))
            if ext > (1.8 if p.get("weapon") or p.name.startswith("Cape") else 0.95) and p.name != "Underbody":
                C.log("OVERSIZED", p.name, round(ext, 2))
    arm = C.build_armature(R.skeleton(J, WEAPON, CAPE, two_handed=True))
    C.bind_all(parts, arm)
    body_parts = [p for p in parts if not p.get("weapon")]
    weapon_parts = [p for p in parts if p.get("weapon")]
    body = C.join(body_parts, f"{NAME}_Body")
    blade = C.join(weapon_parts, f"{NAME}_Sword")
    for o in (body, blade):
        C.skin_to(o, arm)
    C.log("tris body", C.tri_count(body), "sword", C.tri_count(blade))
    C.save_blend(os.path.join(C.REPO, "ArtSource", "Characters", f"{NAME}_model.blend"))
    if render:
        preview(NAME)
    return arm, body, blade


def preview(name, suffix="", head_z=1.75):
    C.preview_setup('CYCLES', 128)
    C.three_point()
    floor = C.box("Floor", (8, 8, 0.02), (0, 0, -0.01))
    floor.data.materials.append(C.mat_flat("FloorMat", (0.05, 0.05, 0.055), 0.8))
    out = os.path.join(C.REPO, "Logs", "chars")
    C.camera_look("CamF", (1.7, -3.3, 1.45), (0, -0.1, 1.05), 50)
    C.render_to(os.path.join(out, f"{name}{suffix}_front.png"))
    C.camera_look("CamB", (-1.9, 3.1, 1.6), (0, 0, 1.05), 50)
    C.render_to(os.path.join(out, f"{name}{suffix}_back.png"))
    C.camera_look("CamH", (0.55, -1.05, head_z + 0.05), (0, -0.05, head_z - 0.12), 50)
    C.render_to(os.path.join(out, f"{name}{suffix}_head.png"))
    C.camera_look("CamG", (0.25, -0.62, 1.0), (0.42, -0.35, 0.95), 50)    # gauntlet + hilt close-up
    C.render_to(os.path.join(out, f"{name}{suffix}_hand.png"))


if __name__ == "__main__":
    build(render="--no-render" not in C.script_args())
