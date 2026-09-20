"""Render the direction-field variants from the FRONT (the face side).

The model is Unity Y-up; OBJ import keeps Y as the up axis in Blender, so the face
(the -Z side of the item) is seen from Blender -Z. Orbiting must therefore be about the
Blender Y axis, not Z — an earlier version orbited about Z and photographed the model
lying on its side, which made every variant look the same.

For each stem and direction field this renders the body + ink shell from the front and
from a three-quarter view, plus one body-only baseline.

Run:
    blender.exe --background --factory-startup --python this_file.py
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
# orbit about the model's up axis (Blender Y). 0 = straight at the face.
ANGLES = (0, 40)
MODES = ("normal", "smooth", "radial", "pushout")


def clean():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_mesh(name, verts, tris):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(t) for t in tris])
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


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


def render(scene, body, angle_deg, path):
    allv = [v.co for v in body.data.vertices]
    lo = Vector((min(v.x for v in allv), min(v.y for v in allv), min(v.z for v in allv)))
    hi = Vector((max(v.x for v in allv), max(v.y for v in allv), max(v.z for v in allv)))
    centre = (lo + hi) * 0.5
    size = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)

    # orbit about Y (up); start in front of the face at -Z
    a = math.radians(angle_deg)
    dist = size * 1.8
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens_unit = 'FOV'
    cam_data.angle = math.radians(50.0)
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = centre + Vector((math.sin(a) * dist, 0.0, -math.cos(a) * dist))
    cam.rotation_euler = (centre - cam.location).to_track_quat('-Z', 'Y').to_euler()
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

        for angle in ANGLES:
            clean()
            scene = bpy.context.scene
            prep(scene)
            body = make_mesh("body", bv, bt)
            body.data.materials.append(flat("b", (0.97, 0.97, 0.96, 1.0), False))
            render(scene, body, angle, os.path.join(OUT, f"front_{stem}_without_{angle:03d}.png"))
            print("rendered", f"front_{stem}_without_{angle:03d}.png")

            for mode in MODES:
                clean()
                scene = bpy.context.scene
                prep(scene)
                d = data[mode]
                shell_v = sv + d * (thick * fade)[:, None]
                body = make_mesh("body", bv, bt)
                shell = make_mesh("shell", shell_v, st)
                body.data.materials.append(flat("b", (0.97, 0.97, 0.96, 1.0), False))

                bpy.ops.object.select_all(action='DESELECT')
                shell.select_set(True)
                bpy.context.view_layer.objects.active = shell
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.flip_normals()
                bpy.ops.object.mode_set(mode='OBJECT')
                shell.data.materials.append(flat("i", (0.05, 0.05, 0.07, 1.0), True))

                render(scene, body, angle,
                       os.path.join(OUT, f"front_{stem}_{mode}_{angle:03d}.png"))
                print("rendered", f"front_{stem}_{mode}_{angle:03d}.png")


if __name__ == "__main__":
    main()
