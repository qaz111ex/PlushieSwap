"""Render the bear at high resolution WITH and WITHOUT the ink shell.

If an internal line disappears when the shell is removed, it is an ink artefact (the
shell poking through at a concavity). If it stays, it is the baked cavity/crease shading
in the body texture, which is intentional. This separates "the outline is wrong" from
"the drawing has crease lines", which look similar but are different things.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

ROOT = r"D:\zhuanban\Plushie Swap"
BLEND = os.path.join(ROOT, "research", "blender")
OUT = os.path.join(ROOT, "research", "preview")
RES = 900
WIDTH_PX = 5.0
STEM = "zichaoxiong"
ANGLES = [0, 135]


def clean():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_obj(path):
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def flat(name, colour, cull=False):
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
    src = os.path.join(BLEND, f"{STEM}_render.obj")
    for angle in ANGLES:
        for with_shell in (True, False):
            clean()
            scene = bpy.context.scene
            scene.render.engine = 'BLENDER_EEVEE'
            scene.render.resolution_x = RES
            scene.render.resolution_y = RES
            scene.render.image_settings.file_format = 'PNG'

            objs = import_obj(src)
            body = [o for o in objs if not o.name.startswith("shell")]
            shell = [o for o in objs if o.name.startswith("shell")]

            bpy.ops.object.select_all(action='DESELECT')
            for o in body:
                o.select_set(True)
            bpy.context.view_layer.objects.active = body[0]
            if len(body) > 1:
                bpy.ops.object.join()
            body = bpy.context.view_layer.objects.active

            bpy.ops.object.select_all(action='DESELECT')
            for o in shell:
                o.select_set(True)
            bpy.context.view_layer.objects.active = shell[0]
            if len(shell) > 1:
                bpy.ops.object.join()
            shell = bpy.context.view_layer.objects.active

            allv = []
            for o in (body, shell):
                for v in o.data.vertices:
                    allv.append(v.co)
            lo = Vector((min(v.x for v in allv), min(v.y for v in allv), min(v.z for v in allv)))
            hi = Vector((max(v.x for v in allv), max(v.y for v in allv), max(v.z for v in allv)))
            centre = (lo + hi) * 0.5
            size = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)

            a = math.radians(angle)
            dist = size * 1.7
            fov = math.radians(50.0)
            cam_data = bpy.data.cameras.new("cam")
            cam_data.lens_unit = 'FOV'
            cam_data.angle = fov
            cam = bpy.data.objects.new("cam", cam_data)
            scene.collection.objects.link(cam)
            cam.location = centre + Vector((math.sin(a) * dist, -math.cos(a) * dist, 0.0))
            cam.rotation_euler = (centre - cam.location).to_track_quat('-Z', 'Y').to_euler()
            scene.camera = cam

            if with_shell:
                mesh = shell.data
                n = len(mesh.vertices)
                co = np.empty((n, 3)); mesh.vertices.foreach_get("co", co.ravel())
                no = np.empty((n, 3)); mesh.vertices.foreach_get("normal", no.ravel())
                cam_inv = np.array(cam.matrix_world.inverted())
                homog = np.concatenate([co, np.ones((n, 1))], axis=1)
                cam_co = homog @ cam_inv.T
                depth = -cam_co[:, 2]
                rot = np.array(cam.matrix_world.to_3x3())
                cam_no = no @ rot.T
                d = cam_no[:, :2].copy()
                ln = np.linalg.norm(d, axis=1, keepdims=True); ln[ln < 1e-8] = 1.0
                d = d / ln
                focal = (RES * 0.5) / math.tan(fov * 0.5)
                scale = (depth / focal) * WIDTH_PX
                off = np.zeros((n, 3)); off[:, 0] = d[:, 0] * scale; off[:, 1] = d[:, 1] * scale
                mesh.vertices.foreach_set("co", (co + off @ rot.T).astype(np.float32).ravel())
                mesh.update()

                bpy.ops.object.select_all(action='DESELECT')
                shell.select_set(True)
                bpy.context.view_layer.objects.active = shell
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.flip_normals()
                bpy.ops.object.mode_set(mode='OBJECT')
                shell.data.materials.clear()
                shell.data.materials.append(flat("ink", (0.05, 0.05, 0.07, 1.0), cull=True))
            else:
                shell.hide_render = True

            body.data.materials.clear()
            body.data.materials.append(flat("body", (0.97, 0.97, 0.96, 1.0)))

            world_bg = bpy.data.worlds.new("w")
            world_bg.use_nodes = True
            bg = world_bg.node_tree.nodes.get("Background")
            if bg:
                bg.inputs[0].default_value = (0.16, 0.16, 0.17, 1.0)
            scene.world = world_bg

            tag = "with" if with_shell else "without"
            out = os.path.join(OUT, f"diag_{STEM}_{angle:03d}_{tag}.png")
            scene.render.filepath = out
            bpy.ops.render.render(write_still=True)
            print("rendered", out)


if __name__ == "__main__":
    main()
