"""
Render a contact sheet of specific clips from an animated character blend (side view as in game).

blender -b --factory-startup -P sheet_clip.py -- <Name> <Action>[,<Action>...] [frames_per_row]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import charlib as C

args = C.script_args()
name, actions = args[0], args[1].split(",")
n = int(args[2]) if len(args) > 2 else 8
bpy.ops.wm.open_mainfile(filepath=os.path.join(C.REPO, "ArtSource", "Characters", f"{name}.blend"))
arm = bpy.data.objects["Rig"]
for o in bpy.data.objects:
    if o.name.endswith("_Knife"):
        o.hide_render = True
rows = []
for a in actions:
    act = bpy.data.actions[a]
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    rows.append((a, [round(f0 + (f1 - f0) * i / (n - 1)) for i in range(n)]))
out = os.path.join(C.REPO, "Logs", "chars", f"{name}_{'_'.join(actions)}.png")
C.contact_sheet(arm, rows, out, (-3.2, -0.5, 1.0), (0, -0.5, 0.85), size=300, lens=45)
