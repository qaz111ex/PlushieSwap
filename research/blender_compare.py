"""Render each direction-field variant at the angle where the leak is visible.

Camera and angle are copied from blender_diagnose_lines.py, which demonstrably showed
the bear's face and the spurious ink on it, so the view is known-good.

For each stem and each direction field this renders:
    with_<mode>.png   body + ink shell
    without.png       body only (the baseline that defines "inside the body")

so the two can be compared pixel by pixel by an existing image tool.

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
ANGLE = 135
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


def setup_and_render(scene, body, shell, path):
    allv = [v.co for v in body.data.vertices]
    lo = Vector((min(v.x for v in allv), min(v.y for v in allv), min(v.z for v in allv)))
    hi = Vector((max(v.x for v in allv), max(v.y for v in allv), max(v.z for v in allv)))
    centre = (lo + hi) * 0.5
    size = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)

    a = math.radians(ANGLE)
    dist = size * 1.7
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens_unit = 'FOV'
    cam_data.angle = math.radians(50.0)
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = centre + Vector((math.sin(a) * dist, -math.cos(a) * dist, 0.0))
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


def main():
    print("Blender", bpy.app.version_string)
    for stem in ("miffy", "zichaoxiong"):
        data = np.load(os.path.join(BLEND, f"dirs_{stem}.npz"))
        bv = data["body_v"]; bt = data["body_t"]
        sv = data["surf"]; st = data["shell_t"]
        fade = data["fade"]; thick = float(data["thickness"])

        # baseline: body only
        clean()
        scene = bpy.context.scene
        scene.render.engine = 'BLENDER_EEVEE'
        scene.render.resolution_x = RES
        scene.render.resolution_y = RES
        body = make_mesh("body", bv, bt)
        body.data.materials.append(flat("b", (0.97, 0.97, 0.96, 1.0), False))
        setup_and_render(scene, body, None, os.path.join(OUT, f"cmp_{stem}_without.png"))
        print("rendered", f"cmp_{stem}_without.png")

        for mode in MODES:
            clean()
            scene = bpy.context.scene
            scene.render.engine = 'BLENDER_EEVEE'
            scene.render.resolution_x = RES
            scene.render.resolution_y = RES
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

            setup_and_render(scene, body, shell,
                             os.path.join(OUT, f"cmp_{stem}_{mode}.png"))
            print("rendered", f"cmp_{stem}_{mode}.png")


if __name__ == "__main__":
    main()
