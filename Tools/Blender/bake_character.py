"""
Decimate, UV-unwrap and bake a character built by build_<name>.py into game textures.
Reads ArtSource/Characters/<Name>_model.blend, writes ArtSource/Characters/<Name>_baked.blend and
textures into Assets/_Game/Art/Characters/<Name>/.

blender -b --factory-startup -P bake_character.py -- <Name> [--res 4096] [--weapon-res 2048] [--ratio 0.5]
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import charlib as C

args = C.script_args()
name = args[0]


def opt(flag, default, cast=float):
    return cast(args[args.index(flag) + 1]) if flag in args else default


res = opt("--res", 4096, int)
wres = opt("--weapon-res", 2048, int)
ratio = opt("--ratio", 0.5)

src = os.path.join(C.REPO, "ArtSource", "Characters", f"{name}_model.blend")
bpy.ops.wm.open_mainfile(filepath=src)
out_dir = os.path.join(C.REPO, "Assets", "_Game", "Art", "Characters", name)

meshes = [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith(name + "_")]
for o in meshes:
    before = C.tri_count(o)
    is_weapon = not o.name.endswith("_Body")
    r = 1.0 if is_weapon else ratio
    if r < 0.999:
        # keep the armature modifier out of the way while decimating
        arm_mods = [m for m in o.modifiers if m.type == 'ARMATURE']
        for m in arm_mods:
            m.show_viewport = False
        d = o.modifiers.new("decimate", 'DECIMATE')
        d.ratio = r
        d.use_collapse_triangulate = False
        d.vertex_group_factor = 1.0
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=d.name)
        for m in arm_mods:
            m.show_viewport = True
    C.log(o.name, "tris", before, "->", C.tri_count(o))
    C.smart_uv(o, margin=0.0015 if not is_weapon else 0.003, angle=62)
    part = o.name.split("_", 1)[1]
    suffix = "Weapon" if part in ("Sword", "Rapier") else part
    tex = C.bake_textures(o, out_dir, f"T_{name}_{suffix}", res=(512 if suffix == "Knife" else wres) if is_weapon else res)
    C.use_baked_material(o, f"M_{name}_{suffix}", tex)

C.save_blend(os.path.join(C.REPO, "ArtSource", "Characters", f"{name}_baked.blend"))
C.log("done", name)
