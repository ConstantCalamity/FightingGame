"""
ISOLDE, the Thornwall Blade — grounded-medieval knight in bright polished plate (after the user's reference):
armet with visor, bevor and rondel, Milanese pauldrons with a haute-piece, black pleated arming skirt with a
gold hem, red silk bow at the gorget, pointed sabatons. Fights left-handed with a ring-hilted sword.

blender -b --factory-startup -P build_isolde.py [-- --no-render]
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector, Matrix, noise
import charlib as C
import rigdef as R
from armorkit import Kit, V, sym, rigid
from build_corvin import preview

NAME = "Isolde"
J = dict(
    pelvis=(0, 0.0, 0.94), spine=(0, 0.0, 1.04), chest=(0, 0.01, 1.2), neck=(0, 0.02, 1.41),
    head=(0, 0.005, 1.49), headTop=(0, 0.0, 1.7),
    clav=(0.03, 0.0, 1.37), shoulder=(0.165, 0.01, 1.37), elbow=(0.3, 0.035, 1.135),
    wrist=(0.415, 0.005, 0.93), handEnd=(0.47, -0.015, 0.845),
    hip=(0.09, 0.0, 0.91), knee=(0.1, -0.02, 0.49), ankle=(0.105, 0.02, 0.085),
    toe=(0.11, -0.095, 0.03), toeEnd=(0.115, -0.185, 0.025),
)
GRIP = Vector((0, -0.5, 0.95))
WEAPON = dict(grip=tuple(GRIP), tip=tuple(GRIP + Vector((0, 0, 1.09))), edge=(0, -1, 0), hand_r=-0.03, main='L')
CAPE = None


def materials():
    return dict(
        plate=C.mat_plate("Isolde_Plate", polished=True, rust=0.06),
        rivet=C.mat_plate("Isolde_Rivet", polished=True, base=(0.5, 0.5, 0.52), rust=0.15),
        brass=C.mat_metal("Isolde_Brass", base=(0.3, 0.2, 0.07), rust=0.1, wear=0.6, rough=0.35,
                          rust_col=(0.04, 0.07, 0.05), edge_col=(0.65, 0.5, 0.25)),
        leather=C.mat_leather("Isolde_Leather", (0.09, 0.05, 0.03), wear=0.5),
        chain=C.mat_chain("Isolde_Chain", base=(0.22, 0.215, 0.21), rust=0.12),
        cloth=C.mat_cloth("Isolde_Skirt", (0.018, 0.018, 0.02), dirt=0.25, fade=0.15, weave=650),
        trim=C.mat_cloth("Isolde_Trim", (0.5, 0.33, 0.08), dirt=0.2, fade=0.1, weave=900, rough=0.6),
        ribbon=C.mat_cloth("Isolde_Ribbon", (0.45, 0.02, 0.025), dirt=0.05, fade=0.05, weave=1200, rough=0.45),
        steel=C.mat_metal("Isolde_Steel", base=(0.22, 0.22, 0.23), rust=0.05, wear=0.6, rough=0.18,
                          edge_col=(0.75, 0.75, 0.75), dents=0.2),
        hilt=C.mat_plate("Isolde_Hilt", polished=True, base=(0.45, 0.45, 0.47), rust=0.1),
    )


def knife_mesh(m, name, scale=1.0):
    """Throwing knife along +Z from the pommel (z=0): 9 cm handle, 13 cm blade."""
    s = scale
    w, t = 0.012 * s, 0.003 * s
    prof = [(0, -w), (t, 0), (0, w), (-t, 0)]
    blade = C.sweep(name + "Blade", [V((0, 0, (0.09 + 0.13 * i / 12) * s)) for i in range(13)], prof,
                    scales=[max(0.04, 1.0 - (i / 12) ** 1.6) for i in range(13)], up=(1, 0, 0))
    handle = C.loft(name + "Handle", [dict(z=0.0, rx=.009 * s, ry=.006 * s), dict(z=0.085 * s, rx=.008 * s, ry=.005 * s)],
                    12, cap0=True, cap1=True)
    guard = C.box(name + "Guard", (0.008 * s, 0.035 * s, 0.008 * s), (0, 0, 0.088 * s))
    for o, mat in ((blade, m['steel']), (handle, m['leather']), (guard, m['brass'])):
        C.set_mat(o, mat)
    return C.join([blade, handle, guard], name)


def sword(m):
    """Ring-hilted sword: knuckle bow, long quillons, side ring and swept bars, wire-bound grip, broad-ish blade."""
    parts = []
    G = GRIP

    def at(o):
        return C.transform(o, Matrix.Translation(G))

    pom = C.loft("Pommel", [dict(z=-0.15, rx=.006), dict(z=-0.142, rx=.02, n=8), dict(z=-0.128, rx=.026, n=8),
                            dict(z=-0.112, rx=.021, n=8), dict(z=-0.1, rx=.01)], 8, cap0=True, cap1=True)
    parts.append(C.finish(at(pom), m['hilt'], rigid("weapon"), bev=(0.002, 2), sub=1))
    grip = C.loft("Grip", [dict(z=-0.1, rx=.012), dict(z=-0.04, rx=.015), dict(z=0.03, rx=.012)], 20)
    parts.append(C.finish(at(grip), m['leather'], rigid("weapon"), sub=1))
    helix = [V((0.0138 * math.cos(a), 0.0138 * math.sin(a), -0.095 + 0.12 * a / (2 * math.pi * 16)))
             for a in [2 * math.pi * 16 * i / 400 for i in range(401)]]
    parts.append(C.finish(at(C.sweep("Wire", helix, C.circle_profile(0.0016, 6), up=(0, 0, 1))), m['brass'], rigid("weapon"), sub=0))
    q = [V((0.006 * math.sin(y * 20), y, 0.04 + 0.08 * y * y * (1 if y > 0 else -1))) for y in [-0.14 + 0.28 * i / 28 for i in range(29)]]
    parts.append(C.finish(at(C.sweep("Quillons", q, C.circle_profile(0.006, 12), up=(1, 0, 0),
                                     scales=[1.0 + 0.3 * (abs(i / 28 - 0.5) * 2) ** 3 for i in range(29)])), m['hilt'], rigid("weapon"), sub=1))
    for p in (q[0], q[-1]):
        parts.append(C.finish(at(C.uv_sphere("QKnob", 0.011, p, 14, 10)), m['hilt'], rigid("weapon"), sub=0))
    parts.append(C.finish(at(C.box("Block", (0.022, 0.032, 0.032), (0, 0, 0.04))), m['hilt'], rigid("weapon"), bev=(0.005, 2), sub=1))
    kb = C.bezier_path((0, -0.105, 0.035), (0, -0.17, -0.0), (0, -0.12, -0.13), (0, -0.01, -0.125), 30)
    parts.append(C.finish(at(C.sweep("KnuckleBow", kb, C.circle_profile(0.0055, 10), up=(1, 0, 0))), m['hilt'], rigid("weapon"), sub=1))
    ring = C.arc_path((0.048, 0.0, 0.03), 0.042, 0, 360, 48, (1, 0, 0), (0, 1, 0))[:-1]
    parts.append(C.finish(at(C.sweep("SideRing", ring, C.circle_profile(0.0045, 10), closed_path=True, cap=False, up=(0, 0, 1))),
                          m['hilt'], rigid("weapon"), sub=1))
    for sgn in (1, -1):
        bar = C.bezier_path((0.0, sgn * 0.012, 0.045), (0.05, sgn * 0.05, 0.02), (0.06, sgn * 0.09, -0.06), (0.0, -0.13 if sgn > 0 else -0.05, -0.1), 24)
        parts.append(C.finish(at(C.sweep("SweptBar", bar, C.circle_profile(0.004, 8), up=(1, 0, 0))), m['hilt'], rigid("weapon"), sub=1))
    ric = C.box("Ricasso", (0.008, 0.024, 0.08), (0, 0, 0.095))
    parts.append(C.finish(at(ric), m['steel'], rigid("weapon"), bev=(0.0015, 1), sub=0))
    w, t = 0.018, 0.0048
    prof = [(0, -w), (t * 0.6, -w * 0.5), (t, -w * 0.1), (t, w * 0.1), (t * 0.6, w * 0.5), (0, w),
            (-t * 0.6, w * 0.5), (-t, w * 0.1), (-t, -w * 0.1), (-t * 0.6, -w * 0.5)]
    n = 50
    path = [V((0, 0, 0.13 + 0.96 * i / n)) for i in range(n + 1)]
    sc = [max(0.04, 1.0 - 0.5 * (i / n) - (0.45 * ((i / n - 0.85) / 0.15) if i / n > 0.85 else 0)) for i in range(n + 1)]
    bl = C.sweep("Blade", path, prof, scales=[(max(0.4, s), s) for s in sc], up=(1, 0, 0))
    bl.data.shade_smooth()
    try:
        bl.data.set_sharp_from_angle(angle=math.radians(35))
    except Exception:
        pass
    parts.append(C.finish(at(bl), m['steel'], rigid("weapon"), sub=0, shade=False))
    for p in parts:
        p["weapon"] = True
    return parts


def build(render=True):
    C.reset_scene()
    m = materials()
    kit = Kit(J, m, w=0.9)
    steps = [
        ("underbody", lambda: kit.underbody(head=True)),
        ("helm", kit.helm_armet),
        ("gorget", kit.gorget),
        ("cuirass", lambda: kit.cuirass(keel=0.012)),
        ("faulds", lambda: kit.faulds(3)),
        ("tassets", lambda: kit.tassets(2)),
        ("skirt", kit.arming_skirt),
        ("belt", kit.belt),
        ("pauldrons", lambda: sym(kit.pauldron(size=0.95, lames=3, haute=True))),
        ("rerebrace", lambda: sym(kit.rerebrace())),
        ("couters", kit.couter),
        ("vambraces", kit.vambrace),
        ("gauntlets", kit.gauntlet),
        ("cuisses", kit.cuisse),
        ("poleyns", kit.poleyn),
        ("greaves", kit.greave),
        ("sabatons", lambda: kit.sabaton(pointed=True)),
        ("ribbon", kit.ribbon),
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
            if ext > (1.3 if p.get("weapon") else 0.95) and p.name != "Underbody":
                C.log("OVERSIZED", p.name, round(ext, 2))
    arm = C.build_armature(R.skeleton(J, WEAPON, CAPE, two_handed=False))
    C.bind_all(parts, arm)
    body_parts = [p for p in parts if not p.get("weapon")]
    weapon_parts = [p for p in parts if p.get("weapon")]
    body = C.join(body_parts, f"{NAME}_Body")
    blade = C.join(weapon_parts, f"{NAME}_Rapier")
    for o in (body, blade):
        C.skin_to(o, arm)
    kn = knife_mesh(m, f"{NAME}_Knife")
    kn["projectile"] = True
    C.log("tris body", C.tri_count(body), "sword", C.tri_count(blade))
    C.save_blend(os.path.join(C.REPO, "ArtSource", "Characters", f"{NAME}_model.blend"))
    if render:
        kn.hide_render = True
        preview(NAME, head_z=1.62)


if __name__ == "__main__":
    build(render="--no-render" not in C.script_args())
