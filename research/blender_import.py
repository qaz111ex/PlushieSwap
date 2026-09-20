"""Render direction variants using Blender's official OBJ import and camera math.

The model is Unity Y-up. Building the mesh with `from_pydata` skips the importer's
axis conversion, so an earlier version photographed it lying on its side and every
variant looked identical. This uses `bpy.ops.wm.obj_import` (which applies the correct
Y-up -> Z-up conversion) and places the camera on the face side afterwards.

Writes research/blender/imported_<stem>_<mode>.obj then renders each from the front.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

ROOT = r"D:\zhuanban\Plushie Swap"
BLEND = os.path.join(ROOT, "research", "blender")
OUT = os.path.join(ROOT, "research", "preview")
RES = 800
ANGLES = (0, 40)
MODES = ("normal", "smooth", "radial", "pushout")


def clean():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def write_obj(path, groups):
    with open(path, "w", encoding="utf-8") as fh:
        base = 1
        for name, verts, tris in groups:
            fh.write(f"o {name}\n")
            for v in verts:
                fh.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
            for t in tris:
                fh.write(f"f {t[0]+base} {t[1]+base} {t[2]+base}\n")
            base += len(verts)


def flat(name, colour, cull):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nodes = m.node_tree.nodes
    nodes.clear()
    out_node = nodes.new("ShaderNodeOutputMaterial")
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = colour
    m.node_tree.links.new(emit.outputs["Emission"], out_node.inputs["Surface"])
    m.use_backface_culling = cull
    return m


def render(scene, body, angle_deg, path, spin=0.0):
    allv = [v.co for v in body.data.vertices]
    lo = Vector((min(v.x for v in allv), min(v.y for v in allv), min(v.z for v in allv)))
    hi = Vector((max(v.x for v in allv), max(v.y for v in allv), max(v.z for v in allv)))
    centre = (lo + hi) * 0.5
    size = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)

    # After OBJ import the model is Z-up. The face (Unity -Z) ends up on Blender -Y.
    # Orbit about Z and start in front of the face.
    a = math.radians(angle_deg) + spin
    dist = size * 1.8
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens_unit = 'FOV'
    cam_data.angle = math.radians(50.0)
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = centre + Vector((math.sin(a) * dist, -math.cos(a) * dist, 0.0))
    cam.rotation_euler = (centre - cam.location).to_track_quat('-Z', 'Z').to_euler()
    scene.camera = cam

    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.16, 0.16, 0.17, 1.0)
    scene.world = w

    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def prep(scene):
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = RES
    scene.render.resolution_y = RES
    scene.render.image_settings.file_format = 'PNG'


def main():
    print("Blender", bpy.app.version_string)
    for stem in ("miffy", "zichaoxiong"):
        data = np.load(os.path.join(BLEND, f"dirs_{stem}.npz"))
        bv = data["body_v"]; bt = data["body_t"]
        sv = data["surf"]; st = data["shell_t"]
        fade = data["fade"]; thick = float(data["thickness"])

        for mode in ("none",) + MODES:
            obj = os.path.join(BLEND, f"imp_{stem}_{mode}.obj")
            if mode == "none":
                write_obj(obj, [("body", bv, bt)])
            else:
                d = data[mode]
                shell_v = sv + d * (thick * fade)[:, None]
                write_obj(obj, [("body", bv, bt), ("shell", shell_v, st)])

            for angle in ANGLES:
                clean()
                scene = bpy.context.scene
                prep(scene)
                bpy.ops.wm.obj_import(filepath=obj)
                objs = list(bpy.context.selected_objects)
                body = [o for o in objs if not o.name.startswith("shell")][0]
                body.data.materials.append(flat("b", (0.97, 0.97, 0.96, 1.0), False))
                for o in objs:
                    if o.name.startswith("shell"):
                        bpy.ops.object.select_all(action='DESELECT')
                        o.select_set(True)
                        bpy.context.view_layer.objects.active = o
                        bpy.ops.object.mode_set(mode='EDIT')
                        bpy.ops.mesh.select_all(action='SELECT')
                        bpy.ops.mesh.flip_normals()
                        bpy.ops.object.mode_set(mode='OBJECT')
                        o.data.materials.append(flat("i", (0.05, 0.05, 0.07, 1.0), True))
                render(scene, body, angle,
                       os.path.join(OUT, f"imp_{stem}_{mode}_{angle:03d}.png"))
                print("rendered", f"imp_{stem}_{mode}_{angle:03d}.png")


if __name__ == "__main__":
    main()
