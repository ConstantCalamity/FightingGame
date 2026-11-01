"""Shared humanoid skeleton definition, IK setup and pose helpers for both fighters."""
import bpy, math
from mathutils import Vector, Matrix
import charlib as C

BODY_BONES = ["root", "hips", "spine", "chest", "neck", "head",
              "clavicle.L", "upperarm.L", "forearm.L", "hand.L",
              "clavicle.R", "upperarm.R", "forearm.R", "hand.R",
              "thigh.L", "shin.L", "foot.L", "toe.L",
              "thigh.R", "shin.R", "foot.R", "toe.R"]
LIMB_SMOOTH = [b for b in BODY_BONES if b != "root"]


def mirror(p):
    return (-p[0], p[1], p[2])


def skeleton(J, weapon_rest, cape=None, two_handed=True):
    """
    J: joint positions for the LEFT side and centre line (Blender coords, facing -Y).
    weapon_rest: dict(grip=(x,y,z), tip=(x,y,z)) rest pose of the weapon bone (Y along blade, Z toward the edge).
    cape: optional list of points for a cape bone chain (parented to chest).
    """
    F, UP = (0, -1, 0), (0, 0, 1)
    bones = [
        dict(name="root", head=(0, 0, 0), tail=(0, 0, 0.25), z_axis=F),
        dict(name="hips", head=J['pelvis'], tail=J['spine'], parent="root", z_axis=F),
        dict(name="spine", head=J['spine'], tail=J['chest'], parent="hips", z_axis=F),
        dict(name="chest", head=J['chest'], tail=J['neck'], parent="spine", z_axis=F),
        dict(name="neck", head=J['neck'], tail=J['head'], parent="chest", z_axis=F),
        dict(name="head", head=J['head'], tail=J['headTop'], parent="neck", z_axis=F),
    ]
    for side, f in (("L", lambda p: p), ("R", mirror)):
        bones += [
            dict(name=f"clavicle.{side}", head=f(J['clav']), tail=f(J['shoulder']), parent="chest", z_axis=F),
            dict(name=f"upperarm.{side}", head=f(J['shoulder']), tail=f(J['elbow']), parent=f"clavicle.{side}", z_axis=F),
            dict(name=f"forearm.{side}", head=f(J['elbow']), tail=f(J['wrist']), parent=f"upperarm.{side}", z_axis=F),
            dict(name=f"hand.{side}", head=f(J['wrist']), tail=f(J['handEnd']), parent=f"forearm.{side}", z_axis=F),
            dict(name=f"thigh.{side}", head=f(J['hip']), tail=f(J['knee']), parent="hips", z_axis=F),
            dict(name=f"shin.{side}", head=f(J['knee']), tail=f(J['ankle']), parent=f"thigh.{side}", z_axis=F),
            dict(name=f"foot.{side}", head=f(J['ankle']), tail=f(J['toe']), parent=f"shin.{side}", z_axis=UP),
            dict(name=f"toe.{side}", head=f(J['toe']), tail=f(J['toeEnd']), parent=f"foot.{side}", z_axis=UP),
            # IK helpers (not exported)
            dict(name=f"ik_foot.{side}", head=f(J['ankle']), tail=f(J['toe']), parent="root", z_axis=UP, deform=False),
            dict(name=f"pole_knee.{side}", head=f((J['knee'][0], J['knee'][1] - 0.6, J['knee'][2])),
                 tail=f((J['knee'][0], J['knee'][1] - 0.7, J['knee'][2])), parent="root", deform=False),
            dict(name=f"pole_elbow.{side}", head=f((J['elbow'][0] + 0.25, J['elbow'][1] + 0.45, J['elbow'][2] - 0.1)),
                 tail=f((J['elbow'][0] + 0.25, J['elbow'][1] + 0.55, J['elbow'][2] - 0.1)), parent="chest", deform=False),
        ]
    g, t = Vector(weapon_rest['grip']), Vector(weapon_rest['tip'])
    blade = (t - g).normalized()
    edge = Vector(weapon_rest.get('edge', (0, -1, 0)))
    bones.append(dict(name="weapon", head=tuple(g), tail=tuple(g + blade * 0.3), parent="root", z_axis=tuple(edge)))
    bones.append(dict(name="weapon_tip", head=tuple(t), tail=tuple(t + blade * 0.08), parent="weapon", z_axis=tuple(edge)))
    # hand targets: wrist sits ~8.5 cm back from the grip point along the edge axis (knuckles toward the edge)
    main = weapon_rest.get('main', 'R')
    off = 'L' if main == 'R' else 'R'
    hand_m = g + blade * weapon_rest.get('hand_r', 0.06)
    bones.append(dict(name=f"ik_hand.{main}", head=tuple(hand_m - edge * 0.085), tail=tuple(hand_m), parent="weapon",
                      z_axis=tuple(blade), deform=False))
    if two_handed:
        hand_o = g + blade * weapon_rest.get('hand_l', -0.07)
        bones.append(dict(name=f"ik_hand.{off}", head=tuple(hand_o - edge * 0.085), tail=tuple(hand_o), parent="weapon",
                          z_axis=tuple(blade), deform=False))
    if cape:
        prev = "chest"
        for i in range(len(cape) - 1):
            nm = f"cape.{i + 1}"
            bones.append(dict(name=nm, head=cape[i], tail=cape[i + 1], parent=prev, z_axis=(0, 1, 0)))
            prev = nm
    return bones


def add_constraints(arm, two_handed=True, pole_sign=1, main='R'):
    """Leg IK to ik_foot, the main arm IK to the weapon grip, and the other arm too for two-handed weapons."""
    pb = arm.pose.bones
    for side in ("L", "R"):
        ik = pb[f"shin.{side}"].constraints.new('IK')
        ik.target = arm; ik.subtarget = f"ik_foot.{side}"
        ik.pole_target = arm; ik.pole_subtarget = f"pole_knee.{side}"
        ik.pole_angle = math.radians(-90 * pole_sign); ik.chain_count = 2
        cr = pb[f"foot.{side}"].constraints.new('COPY_ROTATION')
        cr.target = arm; cr.subtarget = f"ik_foot.{side}"
    arms = ("R", "L") if two_handed else (main,)
    for side in arms:
        ik = pb[f"forearm.{side}"].constraints.new('IK')
        ik.target = arm; ik.subtarget = f"ik_hand.{side}"
        ik.pole_target = arm; ik.pole_subtarget = f"pole_elbow.{side}"
        ik.pole_angle = math.radians(-90 * pole_sign); ik.chain_count = 2
        cr = pb[f"hand.{side}"].constraints.new('COPY_ROTATION')
        cr.target = arm; cr.subtarget = f"ik_hand.{side}"
    for b in pb:
        b.rotation_mode = 'XYZ'


def auto_poles(arm):
    """
    For every IK constraint, pick the pole angle that puts the chain's middle joint closest to its pole
    target in the current pose (the pole-angle convention depends on bone roll, so measure instead of guess).
    """
    pb = arm.pose.bones
    for owner in pb:
        for con in owner.constraints:
            if con.type != 'IK' or not con.pole_subtarget:
                continue
            best = None
            for ang in (-90, 90, 0, 180):
                con.pole_angle = math.radians(ang)
                bpy.context.view_layer.update()
                mid = arm.matrix_world @ owner.head          # e.g. knee / elbow
                pole = arm.matrix_world @ pb[con.pole_subtarget].head
                d = (mid - pole).length
                if best is None or d < best[0]:
                    best = (d, ang)
            con.pole_angle = math.radians(best[1])
            C.log("pole", owner.name, best[1])
    bpy.context.view_layer.update()


def check_knee_direction(arm):
    """Raise a foot target and confirm the knee bends forward (-Y). Returns True if pole sign is right."""
    pb = arm.pose.bones
    rest_knee = arm.data.bones["shin.L"].head_local.copy()
    pb["ik_foot.L"].location = (0, 0.25, 0)   # bone-local Y = along the foot; push it up/back a bit
    bpy.context.view_layer.update()
    pb["ik_foot.L"].matrix = Matrix.Translation((0, 0, 0.3)) @ pb["ik_foot.L"].matrix
    bpy.context.view_layer.update()
    knee = (arm.matrix_world @ pb["shin.L"].head).copy()
    pb["ik_foot.L"].location = (0, 0, 0)
    pb["ik_foot.L"].rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    return knee.y < rest_knee.y - 0.02


# ----------------------------------------------------------------------------------------------
# Pose authoring
# ----------------------------------------------------------------------------------------------
DEG = math.pi / 180


class Poser:
    """
    Builds keyframed actions from compact pose dicts, all in character (armature) space:
      hips: (x, y, z) position of the pelvis joint; hipsRot: (x, y, z) degrees (pitch, yaw, roll)
      spine/chest/neck/head: (x, y, z) degrees local rotation (x = bend forward, y = twist, z = side bend)
      footL/footR: (x, y, z) ankle position; footLRot/footRRot: degrees (x = toe up, y = yaw (twist), z = roll)
      kneeL/kneeR: pole position; elbowL/elbowR: pole position (chest space offset from rest)
      weapon: dict(grip=(x,y,z), tip=dir, edge=dir)
      armL/foreL/handL (FK left arm when not two-handed): degrees
    Missing keys inherit from the previous pose in the same clip.
    """

    def __init__(self, arm, J):
        self.arm = arm
        self.J = J
        self.rest = {b.name: b.matrix_local.copy() for b in arm.data.bones}

    def _set_world(self, bone, mat):
        C.set_bone_matrix(self.arm, bone, mat)

    def _bone_rot(self, bone, deg):
        pb = self.arm.pose.bones[bone]
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler = (deg[0] * DEG, deg[1] * DEG, deg[2] * DEG)

    def apply(self, pose):
        arm, pb, J = self.arm, self.arm.pose.bones, self.J
        # hips: position + rotation relative to rest
        rest_h = self.rest["hips"]
        hp = Vector(pose.get('hips', J['pelvis']))
        hr = pose.get('hipsRot', (0, 0, 0))
        rot = (Matrix.Rotation(hr[2] * DEG, 4, 'Y') @ Matrix.Rotation(hr[0] * DEG, 4, 'X') @
               Matrix.Rotation(hr[1] * DEG, 4, 'Z'))
        m = Matrix.Translation(hp) @ rot @ Matrix.Translation(-Vector(J['pelvis'])) @ rest_h
        self._set_world("hips", m)
        for b in ("spine", "chest", "neck", "head"):
            self._bone_rot(b, pose.get(b, (0, 0, 0)))
        bpy.context.view_layer.update()
        for side in ("L", "R"):
            rest_f = self.rest[f"ik_foot.{side}"]
            ap = Vector(pose.get(f'foot{side}', rest_f.translation))
            fr = pose.get(f'foot{side}Rot', (0, 0, 0))
            frm = (Matrix.Rotation(fr[1] * DEG, 4, 'Z') @ Matrix.Rotation(fr[0] * DEG, 4, 'X') @
                   Matrix.Rotation(fr[2] * DEG, 4, 'Y'))
            mm = frm @ rest_f.to_3x3().to_4x4()
            mm.translation = ap
            self._set_world(f"ik_foot.{side}", mm)
            kp = pose.get(f'knee{side}')
            if kp is not None:
                km = self.rest[f"pole_knee.{side}"].copy(); km.translation = Vector(kp)
                self._set_world(f"pole_knee.{side}", km)
            ep = pose.get(f'elbow{side}')
            if ep is not None:
                em = self.rest[f"pole_elbow.{side}"].copy(); em.translation = Vector(ep)
                self._set_world(f"pole_elbow.{side}", em)
        w = pose.get('weapon')
        if w:
            self._set_world("weapon", C.weapon_matrix(w['grip'], w['tip'], w['edge']))
        for k, bone in (('armL', 'upperarm.L'), ('foreL', 'forearm.L'), ('handL', 'hand.L'), ('clavL', 'clavicle.L'),
                        ('armR', 'upperarm.R'), ('foreR', 'forearm.R'), ('handR', 'hand.R'),
                        ('clavR', 'clavicle.R'), ('toeL', 'toe.L'), ('toeR', 'toe.R')):
            if k in pose:
                self._bone_rot(bone, pose[k])
        bpy.context.view_layer.update()

    KEY_BONES = ["hips", "spine", "chest", "neck", "head", "ik_foot.L", "ik_foot.R", "pole_knee.L", "pole_knee.R",
                 "pole_elbow.L", "pole_elbow.R", "weapon", "upperarm.L", "forearm.L", "hand.L", "clavicle.L",
                 "upperarm.R", "forearm.R", "hand.R", "clavicle.R", "toe.L", "toe.R"]

    def key_all(self, frame):
        for b in self.KEY_BONES:
            if b in self.arm.pose.bones:
                C.key_bone(self.arm, b, frame)

    base = {}

    def clip(self, name, keys, interp='BEZIER'):
        """keys: list of (frame, pose_dict). Poses inherit missing entries from the previous key (then from base)."""
        act = C.new_action(self.arm, name)
        self.reset_pose()
        cur = dict(self.base)
        for f, p in keys:
            cur = {**cur, **p}
            self.apply(cur)
            self.key_all(f)
        fc_list = act.fcurves if hasattr(act, "fcurves") else []
        try:
            for fc in self._fcurves(act):
                for kp in fc.keyframe_points:
                    kp.interpolation = interp
        except Exception as e:
            C.log("interp set skipped:", e)
        return act

    @staticmethod
    def _fcurves(act):
        if hasattr(act, "fcurves"):
            return list(act.fcurves)
        out = []
        for layer in act.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    out += list(bag.fcurves)
        return out

    def reset_pose(self):
        for pb in self.arm.pose.bones:
            pb.location = (0, 0, 0)
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.rotation_euler = (0, 0, 0)
            pb.scale = (1, 1, 1)
        bpy.context.view_layer.update()


def loop_keys(base, frames, fn):
    """Generate keys for a looping clip: fn(phase 0..1) -> pose overrides, last key equals first."""
    keys = []
    for i in range(frames + 1):
        ph = (i % frames) / frames
        keys.append((i, {**base, **fn(ph)}))
    return keys
