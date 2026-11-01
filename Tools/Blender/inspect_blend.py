"""
Inspect a .blend (run with --disable-autoexec): objects, triangle counts, modifiers, materials, textures,
armature bones, then render a front and a side preview with its own materials.

blender -b --disable-autoexec <file.blend> -P inspect_blend.py -- <out_dir>
"""
import sys, os, math
import bpy
from mathutils import Vector

out = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out, exist_ok=True)


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


print("SCENE", bpy.context.scene.name, "fps", bpy.context.scene.render.fps, "engine", bpy.context.scene.render.engine)
total = 0
for o in bpy.data.objects:
    line = f"OBJ {o.name!r} type={o.type} parent={o.parent.name if o.parent else None}"
    if o.type == 'MESH':
        t = tris(o); total += t
        line += f" tris={t} verts={len(o.data.vertices)} mats={[s.material.name if s.material else None for s in o.material_slots]}"
        line += f" mods={[m.type for m in o.modifiers]} uv={[u.name for u in o.data.uv_layers]} vgroups={len(o.vertex_groups)}"
        line += f" shapekeys={len(o.data.shape_keys.key_blocks) if o.data.shape_keys else 0}"
    if o.type == 'ARMATURE':
        bones = [b.name for b in o.data.bones]
        line += f" bones={len(bones)} sample={bones[:40]}"
    line += f" dims={tuple(round(d, 3) for d in o.dimensions)} loc={tuple(round(v, 3) for v in o.location)} rot={tuple(round(math.degrees(r), 1) for r in o.rotation_euler)} scale={tuple(round(s, 3) for s in o.scale)}"
    print(line)
print("TOTAL_TRIS", total)
for m in bpy.data.materials:
    nodes = []
    if m.node_tree:
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image:
                nodes.append(f"{n.image.name}:{n.image.size[0]}x{n.image.size[1]}:{n.image.colorspace_settings.name}")
            elif n.type not in ('OUTPUT_MATERIAL',):
                nodes.append(n.type)
    print("MAT", repr(m.name), nodes)
for img in bpy.data.images:
    print("IMG", repr(img.name), img.size[0], img.size[1], "packed" if img.packed_file else img.filepath)
for a in bpy.data.actions:
    print("ACTION", a.name, tuple(a.frame_range))
for t in bpy.data.texts:
    print("TEXT", t.name, len(t.as_string()), "chars")

# preview renders using the file's own materials
scn = bpy.context.scene
focus = sys.argv[sys.argv.index('--') + 2] if len(sys.argv) > sys.argv.index('--') + 2 else None
meshes = [o for o in bpy.data.objects if o.type == 'MESH' and o.visible_get() and (not focus or (o.parent and o.parent.name == focus))]
for o in bpy.data.objects:
    if o.type == 'MESH' and o not in meshes:
        o.hide_render = True
mn = Vector((1e9,) * 3); mx = Vector((-1e9,) * 3)
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
center = (mn + mx) / 2
size = max(mx - mn)
print("BOUNDS", tuple(round(v, 3) for v in mn), tuple(round(v, 3) for v in mx))
scn.render.engine = 'CYCLES'
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'; prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == 'OPTIX'
    scn.cycles.device = 'GPU'
except Exception as e:
    print("gpu", e)
scn.cycles.samples = 96
scn.cycles.use_denoising = True
scn.render.resolution_x, scn.render.resolution_y = 1000, 1400
scn.render.film_transparent = False
world = scn.world or bpy.data.worlds.new("W")
scn.world = world
if world.node_tree and world.node_tree.nodes.get('Background'):
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.8
for name, loc, rot, energy in (("K", (-2, -3, 3), (55, 0, -35), 400), ("F", (3, -2, 2), (70, 0, 55), 150), ("Rm", (0, 3, 3), (-55, 0, 180), 400)):
    ld = bpy.data.lights.new(name, 'AREA'); ld.energy = energy * (size / 2) ** 2; ld.size = size
    lo = bpy.data.objects.new(name, ld); scn.collection.objects.link(lo)
    lo.location = center + Vector(loc) * size / 2; lo.rotation_euler = [math.radians(a) for a in rot]
cd = bpy.data.cameras.new("cam"); cd.lens = 50
cam = bpy.data.objects.new("cam", cd); scn.collection.objects.link(cam); scn.camera = cam
for label, d in (("front", Vector((0.35, -1, 0.15))), ("side", Vector((-1, -0.2, 0.1))), ("detail", Vector((0.3, -1, 0.35)))):
    dist = size * (1.9 if label != "detail" else 0.75)
    target = center + (Vector((0, 0, size * 0.3)) if label == "detail" else Vector())
    cam.location = target + d.normalized() * dist
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scn.render.filepath = os.path.join(out, f"ref_{label}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scn.render.filepath)
