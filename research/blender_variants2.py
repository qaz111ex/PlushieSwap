"""Render every outline variant built by outline_variants2.py, from several angles.

Run:
    blender.exe --background --factory-startup --python research/blender_variants2.py
"""
import math
import os

import bpy
from mathutils import Vector

ROOT = r"D:\zhuanban\Plushie Swap"
SRC = os.path.join(ROOT, "research", "blender")
OUT = os.path.join(ROOT, "research", "preview")
RES = 800
ANGLES = (0, 40, 90)
TAGS = ("current", "nomask_blend", "smoothwidth")


def clean():
    bpy.ops.wm.read_factory_settings(use_empty=True)


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


def render(scene, ref, angle_deg, path):
    allv = [v.co for v in ref.data.vertices]
    lo = Vector((min(v.x for v in allv), min(v.y for v in allv), min(v.z for v in allv)))
    hi = Vector((max(v.x for v in allv), max(v.y for v in allv), max(v.z for v in allv)))
    centre = (lo + hi) * 0.5
    size = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)
    a = math.radians(angle_deg)
    dist = size * 1.7
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


def main():
    print("Blender", bpy.app.version_string)
    for stem in ("miffy", "zichaoxiong"):
        for tag in TAGS:
            src = os.path.join(SRC, f"var_{stem}_{tag}.obj")
            if not os.path.isfile(src):
                continue
            for angle in ANGLES:
                clean()
                scene = bpy.context.scene
                scene.render.engine = 'BLENDER_EEVEE'
                scene.render.resolution_x = RES
                scene.render.resolution_y = RES
                scene.render.image_settings.file_format = 'PNG'

                bpy.ops.wm.obj_import(filepath=src)
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
                       os.path.join(OUT, f"var_{stem}_{tag}_{angle:03d}.png"))
                print("rendered", f"var_{stem}_{tag}_{angle:03d}.png")


if __name__ == "__main__":
    main()
