"""
Isolde animation set (rapier, left-handed). Same pipeline as anim_corvin.py.

blender -b --factory-startup -P anim_isolde.py [-- --no-export]
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import charlib as C
import rigdef as R
from build_isolde import J, NAME

args = C.script_args()
MOVES = json.load(open(os.path.join(C.REPO, "Assets", "_Game", "Data", "Movesets.json")))
SPEC = next(c for c in MOVES['characters'] if c['id'] == NAME)
MOVE = {m['id']: m for m in SPEC['moves']}


def W(grip, tip, edge):
    return dict(grip=grip, tip=tip, edge=edge)


# free (right) arm raised behind for balance, classic fencing guard
FREE_ARM = dict(armR=(-10, 0, -58), foreR=(105, 0, 0), handR=(20, 0, 0), clavR=(0, 0, -10))
BASE = dict(
    hips=(0.0, 0.03, 0.87), hipsRot=(2, -40, 0),
    spine=(2, -8, 0), chest=(4, -10, 0), neck=(-4, 26, 0), head=(-2, 22, 0),
    footL=(0.12, -0.33, 0.085), footLRot=(0, -4, 0),
    footR=(-0.12, 0.27, 0.085), footRRot=(0, 70, 0),
    kneeL=(0.25, -1.0, 0.45), kneeR=(-0.5, -0.25, 0.45),
    elbowL=(0.55, 0.15, 0.95), elbowR=(-0.5, 0.3, 1.0),
    weapon=W((0.12, -0.42, 1.22), (-0.08, -0.97, 0.22), (0.25, 0.0, -0.97)),
    **FREE_ARM,
)


def clips(P):
    fps = 30
    L, H, S, A = MOVE['Light'], MOVE['Heavy'], MOVE['Special'], MOVE['Air']
    g0 = BASE['weapon']['grip']

    def idle(ph):
        s, c = math.sin(ph * 2 * math.pi), math.cos(ph * 2 * math.pi)
        return dict(hips=(0.0, 0.03, 0.87 - 0.008 * (1 - c) * 0.5), chest=(4 + 1.2 * s, -10, 0),
                    weapon=W((g0[0] + 0.01 * c, g0[1], g0[2] + 0.008 * s), (-0.08 + 0.05 * c, -0.97, 0.22 + 0.05 * s), (0.25, 0, -0.97)),
                    armR=(-10 + 3 * s, 0, -58))
    P.clip("Idle", R.loop_keys(BASE, 60, idle))

    # Fencing advance / retreat. The foot nearest the direction of travel steps first (front foot when
    # advancing, rear foot when retreating) and the other follows. Each foot is planted in the WORLD while
    # down: in root space it drifts against the travel at the walk speed, then catches up during its step.
    # Step length L = coverage * speed * T, so feet barely skate; the mean of each foot sits on its stance home.
    def ease(x):
        x = max(0.0, min(1.0, x))
        return x * x * (3 - 2 * x)

    def footwork(direction, speed, frames, coverage=0.85):
        T = frames / fps
        L = coverage * speed * T
        windows = ((0.0, 0.42), (0.4, 0.82))      # (first foot), (second foot): fractions of the cycle

        def foot_pos(home, rot, a, b, ph):
            k = ease((ph - a) / (b - a))
            s0 = L * ((a + b) / 2 - 0.5)          # centres the foot's average position on its home
            s = s0 + L * k - L * ph                # travel-axis offset in root space
            lift = math.sin(math.pi * max(0.0, min(1.0, (ph - a) / (b - a))))
            y = home[1] - direction * s
            return (home[0], y, home[2] + 0.06 * lift), lift

        def fn(ph):
            first_home, second_home = (BASE['footL'], BASE['footR']) if direction > 0 else (BASE['footR'], BASE['footL'])
            p1, l1 = foot_pos(first_home, None, *windows[0], ph)
            p2, l2 = foot_pos(second_home, None, *windows[1], ph)
            # body: surges with the first step, settles as the second foot gathers
            surge = 0.035 * math.sin(math.pi * max(0.0, min(1.0, ph / 0.6)))
            hips = (0.0, 0.03 - direction * surge, 0.87 - 0.012 * math.sin(2 * math.pi * ph) ** 2 + 0.006 * l1)
            out = dict(hips=hips, chest=(4 + 2.5 * l1, -10, 0), armR=(-10 + 4 * math.sin(2 * math.pi * ph), 0, -58))
            if direction > 0:
                # lead foot leaves toe-up and lands heel first; the rear foot rises onto its toes to push
                out.update(footL=p1, footR=p2,
                           footLRot=(-4 + 18 * l1 * (1 if ph < 0.3 else 0.6), -4, 0),
                           footRRot=(-14 * math.sin(math.pi * max(0.0, min(1.0, (ph - 0.25) / 0.3))) - 6 * l2, 70, 0))
            else:
                out.update(footR=p1, footL=p2,
                           footRRot=(-10 * l1, 70, 0),
                           footLRot=(-4 + 12 * l2, -4, 0))
            return out
        return R.loop_keys(BASE, frames, fn)
    P.clip("WalkFwd", footwork(+1, SPEC['walkSpeed'], 10))
    P.clip("WalkBack", footwork(-1, SPEC['backSpeed'], 11))

    tuck = dict(footL=(0.12, -0.2, 0.48), footR=(-0.12, 0.1, 0.4), footLRot=(-25, -4, 0), footRRot=(-10, 50, 0),
                hips=(0.0, 0.02, 0.93), chest=(10, -10, 0),
                weapon=W((0.12, -0.3, 1.38), (-0.05, -0.6, 0.8), (0.3, 0.8, 0.5)))
    P.clip("Jump", [(0, dict(hips=(0.0, 0.03, 0.8))), (4, tuck), (14, tuck),
                    (20, dict(footL=BASE['footL'], footR=BASE['footR'], footLRot=BASE['footLRot'],
                              footRRot=BASE['footRRot'], hips=(0.0, 0.03, 0.9)))])

    parry = dict(hips=(0.0, 0.07, 0.83), chest=(6, -6, 0), elbowL=(0.6, 0.1, 1.0),
                 weapon=W((0.06, -0.36, 1.3), (0.18, -0.25, 0.95), (0, -1, 0)))
    P.clip("Block", [(0, {}), (3, parry), (8, parry)])

    hit = dict(hips=(0.0, 0.13, 0.86), hipsRot=(-8, -48, 0), spine=(-12, 0, 0), chest=(-14, -4, 0), head=(-16, 20, 0),
               armR=(-10, 10, -40), foreR=(40, 0, 0),
               weapon=W((0.15, -0.3, 1.15), (0.05, -0.85, 0.52), (0.25, 0, -0.97)))
    P.clip("Hit", [(0, {}), (3, hit), (6, hit), (12, BASE)])

    fall = dict(hips=(0.0, 0.35, 0.6), hipsRot=(-50, -30, 8), spine=(-10, 0, 0), chest=(-10, 0, 0), head=(-18, 0, 0),
                footL=(0.15, -0.3, 0.25), footR=(-0.15, -0.05, 0.3), armR=(-60, 0, -40), foreR=(20, 0, 0),
                weapon=W((0.2, 0.1, 0.9), (0.4, -0.5, 0.75), (0, -0.6, -0.8)))
    down = dict(hips=(0.0, 0.42, 0.15), hipsRot=(-86, -10, 6), spine=(-4, 0, 0), chest=(-4, 0, 0), head=(-6, 20, 0),
                footL=(0.18, -0.32, 0.08), footR=(-0.16, -0.26, 0.08), footLRot=(-70, -15, 0), footRRot=(-70, 20, 0),
                kneeL=(0.4, -0.3, 1.0), kneeR=(-0.4, -0.3, 1.0), armR=(-150, 0, -30), foreR=(10, 0, 0),
                elbowL=(0.6, 0.6, 0.0),
                weapon=W((0.42, 0.3, 0.06), (0.3, -0.95, 0.0), (0, 0, 1)))
    P.clip("KO", [(0, {}), (4, fall), (12, down), (16, dict(hips=(0.0, 0.44, 0.17))), (30, down)])

    salute = dict(hips=(0.0, 0.02, 0.92), hipsRot=(0, -20, 0), chest=(0, -6, 0), neck=(0, 14, 0), head=(4, 12, 0),
                  footL=(0.1, -0.12, 0.085), footR=(-0.1, 0.12, 0.085), footRRot=(0, 40, 0),
                  armR=(-20, 0, -15), foreR=(90, 40, 0), elbowL=(0.6, -0.1, 1.1),
                  weapon=W((0.06, -0.3, 1.38), (0.0, -0.05, 1.0), (0, -1, 0)))
    lowered = dict(salute, neck=(6, 14, 0), elbowL=(0.6, 0.2, 0.9),
                   weapon=W((0.26, -0.25, 0.98), (0.45, -0.45, -0.77), (0, -0.85, 0.5)))
    P.clip("Win", [(0, {}), (12, salute), (24, salute), (34, lowered), (60, dict(lowered, chest=(2, -6, 0)))])

    # Light: quick thrust with a short advance of the lead foot
    s, a, r = L['startupF'], L['activeF'], L['recoveryF']
    thrust = dict(hips=(0.0, -0.07, 0.85), hipsRot=(4, -46, 0), chest=(8, -10, 0), footL=(0.12, -0.45, 0.085),
                  elbowL=(0.6, 0.3, 1.2),
                  weapon=W((0.06, -0.78, 1.3), (-0.03, -1.0, 0.03), (0.25, 0, -0.97)))
    P.clip("Light", [(0, {}), (s - 1, dict(weapon=W((0.13, -0.36, 1.22), (-0.08, -0.97, 0.22), (0.25, 0, -0.97)))),
                     (s, thrust), (s + a, thrust), (s + a + r, BASE)])

    # Heavy: fleche — coil, then a deep committed lunge, free arm flung back
    s, a, r = H['startupF'], H['activeF'], H['recoveryF']
    coil = dict(hips=(0.0, 0.09, 0.83), hipsRot=(0, -36, 0), chest=(0, -14, 0),
                weapon=W((0.13, -0.24, 1.26), (-0.05, -0.95, 0.3), (0.25, 0, -0.97)))
    lunge = dict(hips=(0.0, -0.22, 0.72), hipsRot=(10, -52, 0), spine=(8, 0, 0), chest=(10, -6, 0), neck=(-12, 22, 0),
                 head=(-8, 20, 0), footL=(0.12, -0.85, 0.085), footR=(-0.12, 0.32, 0.085), kneeL=(0.25, -1.4, 0.4),
                 armR=(-60, 0, -35), foreR=(10, 0, 0), elbowL=(0.6, 0.3, 1.2),
                 weapon=W((0.06, -0.96, 1.2), (-0.02, -1.0, -0.03), (0.25, 0, -0.97)))
    P.clip("Heavy", [(0, {}), (s - 2, coil), (s, lunge), (s + a, dict(lunge, hips=(0.0, -0.23, 0.71))), (s + a + r, BASE)])

    # Special: draw a knife from the baldric with the free hand and throw it
    s, a, r = S['startupF'], S['activeF'], S['recoveryF']
    reach = dict(hipsRot=(2, -30, 0), chest=(4, -2, 0), armR=(40, 0, 20), foreR=(100, 0, 0), handR=(0, 0, 0))
    wind = dict(hipsRot=(2, -24, 0), chest=(4, 8, 0), armR=(-40, 0, -60), foreR=(110, 0, 0))
    throw = dict(hipsRot=(4, -10, 0), chest=(8, 22, 0), neck=(-4, 10, 0), head=(-2, 8, 0), armR=(85, 0, -15),
                 foreR=(5, 0, 0), handR=(-10, 0, 0))
    P.clip("Special", [(0, {}), (2, reach), (s - 1, wind), (s, throw), (s + a + 2, throw), (s + a + r, BASE)])

    # Air: falling diagonal cut
    s, a, r = A['startupF'], A['activeF'], A['recoveryF']
    high = dict(tuck, weapon=W((0.12, -0.18, 1.5), (0.0, 0.1, 1.0), (0, -1, 0.1)))
    cut = dict(tuck, chest=(18, -10, 0), elbowL=(0.6, 0.2, 1.1),
               weapon=W((0.1, -0.55, 1.15), (0.02, -0.62, -0.78), (0, 0.78, -0.62)))
    P.clip("Air", [(0, tuck), (s - 1, high), (s, dict(cut, weapon=W((0.12, -0.5, 1.35), (0.0, -0.98, 0.2), (0, -0.2, -0.98)))),
                   (s + a, cut), (s + a + r, tuck)])


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
    R.add_constraints(arm, two_handed=False, main='L')
    P = R.Poser(arm, J)
    P.base = BASE
    P.apply(BASE)
    R.auto_poles(arm)
    clips(P)
    bpy.ops.object.mode_set(mode='OBJECT')
    knife = bpy.data.objects.get(f"{NAME}_Knife")
    if knife:
        knife.hide_render = True
    out = os.path.join(C.REPO, "Logs", "chars")
    order = ["Idle", "WalkFwd", "WalkBack", "Jump", "Block", "Hit", "KO", "Win", "Light", "Heavy", "Special", "Air"]
    rows = []
    for nm in order:
        act = bpy.data.actions[nm]
        f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
        rows.append((nm, [round(f0 + (f1 - f0) * i / 4) for i in range(5)]))
    C.contact_sheet(arm, rows[:6], os.path.join(out, f"{NAME}_anim_a.png"), (-3.4, -0.7, 1.1), (0, -0.7, 0.95))
    C.contact_sheet(arm, rows[6:], os.path.join(out, f"{NAME}_anim_b.png"), (-3.4, -0.7, 1.1), (0, -0.7, 0.95))
    # export from the rest pose so the FBX default (bind) pose is the A-pose, not a frame of some clip
    arm.animation_data.action = None
    P.reset_pose()
    bpy.context.scene.frame_set(0)
    C.save_blend(os.path.join(C.REPO, "ArtSource", "Characters", f"{NAME}.blend"))
    if export:
        objs = [arm] + [o for o in bpy.data.objects if o.type == 'MESH' and o.parent == arm]
        C.export_fbx(os.path.join(C.REPO, "Assets", "_Game", "Art", "Characters", NAME, f"{NAME}.fbx"), objs)
        if knife:
            knife.hide_render = False
            C.export_fbx(os.path.join(C.REPO, "Assets", "_Game", "Art", "Characters", NAME, f"{NAME}_Knife.fbx"), [knife], anim=False)


if __name__ == "__main__":
    build(export="--no-export" not in args)
