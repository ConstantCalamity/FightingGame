"""
Corvin animation set (greatsword, two-handed). Loads the baked model (or the raw model if not baked yet),
adds IK, keyframes every clip, renders contact sheets and exports the FBX.

blender -b --factory-startup -P anim_corvin.py [-- --no-export] [--sheet-only]
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector
import charlib as C
import rigdef as R
from build_corvin import J, NAME

args = C.script_args()
MOVES = json.load(open(os.path.join(C.REPO, "Assets", "_Game", "Data", "Movesets.json")))
MOVE = {m['id']: m for m in next(c for c in MOVES['characters'] if c['id'] == NAME)['moves']}
SPEC = next(c for c in MOVES['characters'] if c['id'] == NAME)


def W(grip, tip, edge):
    return dict(grip=grip, tip=tip, edge=edge)


BASE = dict(
    hips=(0.0, 0.03, 0.92), hipsRot=(4, -18, 0),
    spine=(4, -4, 0), chest=(6, -8, 0), neck=(-6, 14, 0), head=(-4, 12, 0),
    footL=(0.17, -0.27, 0.10), footLRot=(0, -8, 0),
    footR=(-0.17, 0.28, 0.10), footRRot=(0, 38, 0),
    kneeL=(0.3, -1.0, 0.5), kneeR=(-0.4, -0.6, 0.5),
    elbowL=(0.55, 0.1, 0.75), elbowR=(-0.6, 0.15, 0.75),
    weapon=W((-0.03, -0.36, 1.05), (0.04, -0.62, 0.78), (0, -0.78, -0.62)),
)


def crouch(d, **kw):
    p = dict(kw)
    h = BASE['hips']
    p['hips'] = (h[0], h[1] + 0.02, h[2] - d)
    return p


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def clips(P):
    fps = 30
    L, H, S, A = MOVE['Light'], MOVE['Heavy'], MOVE['Special'], MOVE['Air']

    # ---------------- Idle: slow heavy breathing, blade tip drifting
    def idle(ph):
        s = math.sin(ph * 2 * math.pi)
        c = math.cos(ph * 2 * math.pi)
        g = BASE['weapon']['grip']
        return dict(hips=(0.0, 0.03, 0.92 - 0.012 * (1 - c) * 0.5), chest=(6 + 1.5 * s, -8, 0),
                    head=(-4 - 1.0 * s, 12, 0),
                    weapon=W((g[0] + 0.01 * s, g[1], g[2] + 0.012 * s), (0.04 + 0.03 * c, -0.62, 0.78), (0, -0.78, -0.62)))
    P.clip("Idle", R.loop_keys(BASE, 60, idle))

    # ---------------- Walks: step-and-follow footwork, partial foot slide to keep strides compact
    def walk(direction, speed, frames):
        T = frames / fps
        D = speed * T * 0.55 * 0.75
        plant = 0.55

        def foot(home, ph):
            y0 = home[1]
            if ph < plant:
                k = ph / plant
                y = y0 - direction * (D / 2 - D * k)
                z = home[2]
            else:
                k = (ph - plant) / (1 - plant)
                y = y0 - direction * (-D / 2 + D * k)
                z = home[2] + 0.09 * math.sin(math.pi * k)
            return (home[0], y, z)

        def fn(ph):
            s = math.sin(ph * 4 * math.pi)
            return dict(footL=foot(BASE['footL'], ph), footR=foot(BASE['footR'], (ph + 0.5) % 1.0),
                        hips=(0.0, 0.03, 0.915 - 0.018 * abs(math.cos(ph * 2 * math.pi))),
                        hipsRot=(4 + 2 * direction, -18 + 4 * math.sin(ph * 2 * math.pi), 0),
                        chest=(6 + 1.5 * s, -8, 0))
        return R.loop_keys(BASE, frames, fn)
    P.clip("WalkFwd", walk(+1, SPEC['walkSpeed'], 20))
    P.clip("WalkBack", walk(-1, SPEC['backSpeed'], 22))

    # ---------------- Jump (airborne ~0.67s)
    tuck = dict(footL=(0.16, -0.18, 0.5), footR=(-0.16, 0.12, 0.42), footLRot=(-20, -8, 0), footRRot=(-10, 30, 0),
                hips=(0.0, 0.02, 0.98), chest=(10, -8, 0),
                weapon=W((-0.02, -0.3, 1.25), (0.0, 0.2, 0.98), (0, -0.98, 0.2)))
    P.clip("Jump", [(0, crouch(0.08)), (4, tuck), (14, tuck), (20, dict(footL=BASE['footL'], footR=BASE['footR'],
                                                                         footLRot=BASE['footLRot'], footRRot=BASE['footRRot'],
                                                                         hips=(0.0, 0.03, 0.95)))])

    # ---------------- Block: blade held across the body, crouched
    guard = crouch(0.1, chest=(12, 4, 0), head=(4, 6, 0),
                   elbowL=(0.6, 0.1, 0.9), elbowR=(-0.6, 0.1, 0.9),
                   weapon=W((-0.05, -0.36, 1.2), (0.12, -0.22, 0.97), (0, -1, 0)))
    P.clip("Block", [(0, {}), (4, guard), (8, guard)])

    # ---------------- Hit react
    hit = dict(hips=(0.0, 0.12, 0.9), hipsRot=(-6, -24, 0), spine=(-10, 0, 0), chest=(-14, -6, 0), head=(-18, 14, 0),
               weapon=W((-0.02, -0.25, 1.05), (0.1, -0.35, 0.93), (0, -0.93, -0.35)))
    P.clip("Hit", [(0, {}), (3, hit), (6, hit), (12, BASE)])

    # ---------------- KO: knocked flat on the back, still gripping the sword
    ko_fall = dict(hips=(0.0, 0.4, 0.62), hipsRot=(-55, -10, 0), spine=(-10, 0, 0), chest=(-10, 0, 0), head=(-20, 0, 0),
                   footL=(0.18, -0.25, 0.25), footR=(-0.18, -0.05, 0.3),
                   weapon=W((-0.1, 0.0, 0.95), (0.3, -0.6, 0.75), (0, -0.6, -0.8)))
    ko_down = dict(hips=(0.0, 0.45, 0.17), hipsRot=(-86, -4, 4), spine=(-4, 0, 0), chest=(-4, 0, 0), head=(-8, 15, 0),
                   footL=(0.22, -0.35, 0.09), footR=(-0.2, -0.28, 0.1), footLRot=(-70, -20, 0), footRRot=(-70, 25, 0),
                   kneeL=(0.4, -0.3, 1.0), kneeR=(-0.4, -0.3, 1.0),
                   elbowL=(0.6, 0.6, 0.0), elbowR=(-0.6, 0.6, 0.0),
                   weapon=W((-0.35, 0.3, 0.12), (-0.25, -0.97, 0.0), (0, 0, 1)))
    P.clip("KO", [(0, {}), (4, ko_fall), (12, ko_down), (16, dict(hips=(0.0, 0.47, 0.19))), (30, ko_down)])

    # ---------------- Win: sword planted, hands on the pommel, head bowed
    win = dict(hips=(0.0, 0.03, 0.97), hipsRot=(0, -8, 0), spine=(2, 0, 0), chest=(2, -4, 0), neck=(14, 4, 0), head=(12, 4, 0),
               footL=(0.14, -0.1, 0.10), footR=(-0.14, 0.12, 0.10), footRRot=(0, 15, 0), footLRot=(0, -5, 0),
               elbowL=(0.6, -0.2, 1.0), elbowR=(-0.6, -0.2, 1.0),
               weapon=W((0.0, -0.42, 1.36), (0, 0.04, -1), (0, -1, 0)))
    win2 = dict(win, chest=(4, -4, 0), hips=(0.0, 0.03, 0.965))
    P.clip("Win", [(0, {}), (12, win), (36, win2), (60, win)])

    # ---------------- Light: diagonal cleave from over the right shoulder down through the target
    s, a, r = L['startupF'], L['activeF'], L['recoveryF']
    P.clip("Light", [
        (0, {}),
        (s - 2, dict(hips=(0.0, 0.07, 0.93), hipsRot=(0, -30, 0), chest=(-4, -20, 0), neck=(0, 22, 0), head=(0, 20, 0),
                     elbowL=(0.6, 0.2, 1.2), elbowR=(-0.6, 0.25, 1.15),
                     weapon=W((-0.14, 0.0, 1.5), (-0.15, 0.78, 0.6), (0, -0.6, 0.78)))),
        (s, dict(hips=(0.0, -0.04, 0.88), hipsRot=(8, -12, 0), chest=(10, 4, 0), neck=(-8, 8, 0), head=(-6, 6, 0),
                 footL=(0.17, -0.4, 0.10), elbowL=(0.55, 0.05, 0.9), elbowR=(-0.6, 0.1, 0.9),
                 weapon=W((-0.05, -0.47, 1.32), (0.04, -0.98, 0.18), (0, -0.18, -0.98)))),
        (s + a, dict(hipsRot=(10, -6, 0), chest=(16, 10, 0),
                     weapon=W((-0.02, -0.5, 1.1), (0.1, -0.84, -0.53), (0, 0.53, -0.84)))),
        (s + a + 4, dict(chest=(18, 14, 0), weapon=W((0.03, -0.38, 0.95), (0.22, -0.45, -0.86), (0, 0.86, -0.45)))),
        (s + a + r, BASE),
    ])
    # ---------------- Heavy: overhead grave slam into the ground
    s, a, r = H['startupF'], H['activeF'], H['recoveryF']
    raised = dict(hips=(0.0, 0.08, 0.95), hipsRot=(-2, -10, 0), spine=(-6, 0, 0), chest=(-12, -4, 0), neck=(4, 8, 0),
                  head=(6, 6, 0), elbowL=(0.6, 0.3, 1.3), elbowR=(-0.6, 0.3, 1.3),
                  weapon=W((0.0, 0.0, 1.72), (0.0, 0.8, 0.6), (0, -0.6, 0.8)))
    slam = dict(hips=(0.0, -0.08, 0.8), hipsRot=(16, -10, 0), spine=(14, 0, 0), chest=(18, -4, 0), neck=(-14, 8, 0),
                head=(-10, 6, 0), footL=(0.18, -0.48, 0.10), kneeL=(0.3, -1.2, 0.5),
                elbowL=(0.55, 0.0, 0.7), elbowR=(-0.55, 0.0, 0.7),
                weapon=W((0.0, -0.62, 0.95), (0.0, -0.66, -0.75), (0, -0.75, 0.66)))
    P.clip("Heavy", [
        (0, {}),
        (6, dict(raised, weapon=W((0.0, -0.2, 1.55), (0.0, 0.3, 0.95), (0, -0.95, 0.3)))),
        (s - 2, raised),
        (s, dict(slam, weapon=W((0.0, -0.45, 1.4), (0.0, -0.95, 0.3), (0, -0.3, -0.95)))),
        (s + 1, slam),
        (s + a + 6, dict(slam, hips=(0.0, -0.07, 0.81))),
        (s + a + r, BASE),
    ])

    # ---------------- Special: ashen wave — sword raised then driven point-first into the ground
    s, a, r = S['startupF'], S['activeF'], S['recoveryF']
    lift = dict(hips=(0.0, 0.03, 0.96), chest=(-4, -6, 0), neck=(0, 10, 0), elbowL=(0.6, 0.0, 1.1), elbowR=(-0.6, 0.0, 1.1),
                weapon=W((0.0, -0.3, 1.5), (0.0, 0.05, 1.0), (0, -1, 0.05)))
    drive = dict(hips=(0.0, -0.02, 0.78), hipsRot=(12, -14, 0), spine=(10, 0, 0), chest=(14, -6, 0), neck=(-10, 10, 0),
                 head=(-6, 10, 0), footL=(0.18, -0.36, 0.10),
                 weapon=W((0.0, -0.55, 1.0), (0.0, -0.3, -0.95), (0, -0.95, 0.3)))
    P.clip("Special", [(0, {}), (s - 4, lift), (s - 2, dict(lift, weapon=W((0.0, -0.32, 1.6), (0.0, 0.02, 1.0), (0, -1, 0))))
                       , (s, drive), (s + a + 6, dict(drive, hips=(0.0, -0.02, 0.79))), (s + a + r, BASE)])

    # ---------------- Air: plunging strike, point down
    s, a, r = A['startupF'], A['activeF'], A['recoveryF']
    plunge = dict(tuck, hips=(0.0, 0.0, 0.98), chest=(14, -6, 0), elbowL=(0.6, 0.0, 1.3), elbowR=(-0.6, 0.0, 1.3),
                  weapon=W((0.0, -0.32, 1.12), (0.0, -0.22, -0.97), (0, -0.97, 0.22)))
    P.clip("Air", [(0, tuck), (s, plunge), (s + a, plunge), (s + a + r, tuck)])


def build(export=True):
    src = os.path.join(C.REPO, "ArtSource", "Characters", f"{NAME}_baked.blend")
    if not os.path.exists(src):
        src = os.path.join(C.REPO, "ArtSource", "Characters", f"{NAME}_model.blend")
    bpy.ops.wm.open_mainfile(filepath=src)
    bpy.context.scene.render.fps = 30
    arm = bpy.data.objects["Rig"]
    bpy.context.view_layer.objects.active = arm
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    bpy.ops.object.mode_set(mode='POSE')
    R.add_constraints(arm, two_handed=True)
    P = R.Poser(arm, J)
    P.base = BASE
    P.apply(BASE)
    R.auto_poles(arm)
    clips(P)
    bpy.ops.object.mode_set(mode='OBJECT')
    out = os.path.join(C.REPO, "Logs", "chars")
    order = ["Idle", "WalkFwd", "WalkBack", "Jump", "Block", "Hit", "KO", "Win", "Light", "Heavy", "Special", "Air"]
    rows = []
    for nm in order:
        act = bpy.data.actions[nm]
        f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
        rows.append((nm, [round(f0 + (f1 - f0) * i / 4) for i in range(5)]))
    # gameplay view: the camera sees the character's right side (Blender -X)
    C.contact_sheet(arm, rows[:6], os.path.join(out, f"{NAME}_anim_a.png"), (-3.7, -0.75, 1.15), (0, -0.75, 1.0))
    C.contact_sheet(arm, rows[6:], os.path.join(out, f"{NAME}_anim_b.png"), (-3.7, -0.75, 1.15), (0, -0.75, 1.0))
    # export from the rest pose so the FBX default (bind) pose is the A-pose, not a frame of some clip
    arm.animation_data.action = None
    P.reset_pose()
    bpy.context.scene.frame_set(0)
    C.save_blend(os.path.join(C.REPO, "ArtSource", "Characters", f"{NAME}.blend"))
    if export:
        objs = [arm] + [o for o in bpy.data.objects if o.type == 'MESH' and o.parent == arm]
        C.export_fbx(os.path.join(C.REPO, "Assets", "_Game", "Art", "Characters", NAME, f"{NAME}.fbx"), objs)


if __name__ == "__main__":
    build(export="--no-export" not in args)
