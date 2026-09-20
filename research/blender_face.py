"""Render the head of the unmasked hull at high resolution to look for eye rings.

The masks in the build were introduced to stop the hull drawing a ring around each
recessed eye/mouth/blush. They also cut a fifth of the silhouette away. This renders
the unmasked hull close up so the trade-off can be judged by looking at it.

Run:
    blender.exe --background --factory-startup --python research/blender_face.py
"""
import math
import os

import bpy
from mathutils import Vector

ROOT = r"D:\zhuanban\Plushie Swap"
SRC = os.path.join(ROOT, "research", "blender")
OUT = os.path.join(ROOT, "research", "preview")
RES = 900
TAGS = ("current", "nomask_blend")


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


def main():
    print("Blender", bpy.app.version_string)
    for stem in ("miffy", "zichaoxiong"):
        for tag in TAGS:
            src = os.path.join(SRC, f"var_{stem}_{tag}.obj")
            if not os.path.isfile(src):
                continue
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

            # frame the head: upper part of the body, straight on.
            #
            # obj_import converts the mesh's Y-up to Blender's Z-up, so the camera sits
            # on -Y (the same convention blender_variants2.py uses for its front view).
            allv = [v.co for v in body.data.vertices]
            lo = Vector((min(v.x for v in allv), min(v.y for v in allv), min(v.z for v in allv)))
            hi = Vector((max(v.x for v in allv), max(v.y for v in allv), max(v.z for v in allv)))
            size = max(hi - lo)
            head_z = lo.z + (hi.z - lo.z) * 0.72
            centre = Vector(((lo.x + hi.x) * 0.5, (lo.y + hi.y) * 0.5, head_z))
            head_size = size * 0.45
            dist = head_size * 2.2

            cam_data = bpy.data.cameras.new("cam")
            cam_data.lens_unit = 'FOV'
            cam_data.angle = math.radians(40.0)
            cam = bpy.data.objects.new("cam", cam_data)
            scene.collection.objects.link(cam)
            cam.location = centre + Vector((0.0, -dist, 0.0))
            cam.rotation_euler = (centre - cam.location).to_track_quat('-Z', 'Y').to_euler()
            scene.camera = cam

            w = bpy.data.worlds.new("w")
            w.use_nodes = True
            bg = w.node_tree.nodes.get("Background")
            if bg:
                bg.inputs[0].default_value = (0.16, 0.16, 0.17, 1.0)
            scene.world = w

            path = os.path.join(OUT, f"face_{stem}_{tag}.png")
            scene.render.filepath = path
            bpy.ops.render.render(write_still=True)
            print("rendered", os.path.basename(path))


if __name__ == "__main__":
    main()
