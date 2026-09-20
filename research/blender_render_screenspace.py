"""Render the plush in Blender with the runtime's SCREEN-SPACE ink extrusion applied.

Run headless:
    blender.exe --background --factory-startup --python this_file.py

The baked shell is only the starting point: every frame the game rewrites its vertices
so the line is a constant number of screen pixels wide. This reproduces that step inside
Blender, using the actual render camera, and then renders with a real 3D renderer. The
result is what the player sees, checked by something other than the mod's own maths.

Writes research/preview/ss_<stem>_<angle>.png.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

ROOT = r"D:\zhuanban\Plushie Swap"
BLEND = os.path.join(ROOT, "research", "blender")
OUT = os.path.join(ROOT, "research", "preview")
ANGLES = [0, 45, 90, 135, 180, 225, 270, 315]
RES = 640
WIDTH_PX = 5.0


def clean():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_obj(path):
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def main():
    for stem in ("miffy", "zichaoxiong"):
        src = os.path.join(BLEND, f"{stem}_render.obj")
        if not os.path.exists(src):
            print("missing", src)
            continue

        for angle in ANGLES:
            clean()
            scene = bpy.context.scene
            scene.render.engine = 'BLENDER_EEVEE'
            scene.render.resolution_x = RES
            scene.render.resolution_y = RES
            scene.render.image_settings.file_format = 'PNG'

            objs = import_obj(src)
            body = [o for o in objs if not o.name.startswith("shell")]
            shell = [o for o in objs if o.name.startswith("shell")]

            if len(body) > 1:
                bpy.ops.object.select_all(action='DESELECT')
                for o in body:
                    o.select_set(True)
                bpy.context.view_layer.objects.active = body[0]
                bpy.ops.object.join()
                body = [bpy.context.view_layer.objects.active]
            body = body[0]

            bpy.ops.object.select_all(action='DESELECT')
            for o in shell:
                o.select_set(True)
            bpy.context.view_layer.objects.active = shell[0]
            if len(shell) > 1:
                bpy.ops.object.join()
            shell = bpy.context.view_layer.objects.active

            # Frame the model.
            allv = []
            for o in (body, shell):
                for v in o.data.vertices:
                    allv.append(o.matrix_world @ v.co)
            lo = Vector((min(v.x for v in allv), min(v.y for v in allv), min(v.z for v in allv)))
            hi = Vector((max(v.x for v in allv), max(v.y for v in allv), max(v.z for v in allv)))
            centre = (lo + hi) * 0.5
            size = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)

            a = math.radians(angle)
            dist = size * 1.9
            fov = math.radians(50.0)
            cam_data = bpy.data.cameras.new("cam")
            cam_data.lens_unit = 'FOV'
            cam_data.angle = fov
            cam = bpy.data.objects.new("cam", cam_data)
            scene.collection.objects.link(cam)
            cam.location = centre + Vector((math.sin(a) * dist, -math.cos(a) * dist, 0.0))
            cam.rotation_euler = (centre - cam.location).to_track_quat('-Z', 'Y').to_euler()
            scene.camera = cam

            # ---- the runtime's screen-space extrusion, for this camera ----
            # Recover the surface, project to camera space, then offset along the
            # screen-space normal by (perPixel * pixelWidth * depth) world units.
            mesh = shell.data
            n = len(mesh.vertices)
            co = np.empty((n, 3), dtype=np.float64)
            mesh.vertices.foreach_get("co", co.ravel())
            # vertex normals (the shell normals are the averaged ones baked in)
            no = np.empty((n, 3), dtype=np.float64)
            mesh.vertices.foreach_get("normal", no.ravel())

            # camera basis (Blender: camera looks down -Z, right = +X, up = +Y)
            cam_mat = cam.matrix_world
            cam_inv = cam_mat.inverted()
            focal = (RES * 0.5) / math.tan(fov * 0.5)

            # transform to camera space
            world = np.array([(mesh.vertices[i].co) for i in range(n)], dtype=np.float64)
            # obj has identity transform (imported), so local == world
            homog = np.concatenate([world, np.ones((n, 1))], axis=1)
            cam_inv_np = np.array(cam_inv)
            cam_co = homog @ cam_inv_np.T
            cam_co = cam_co[:, :3]
            # depth = -z (camera looks down -Z)
            depth = -cam_co[:, 2]

            # normals into camera space (rotation only)
            rot = np.array(cam_mat.to_3x3())
            rot_inv = rot.T
            cam_no = no @ rot_inv.T

            # screen-space direction
            d = cam_no[:, :2].copy()
            ln = np.linalg.norm(d, axis=1, keepdims=True)
            ln[ln < 1e-8] = 1.0
            d = d / ln

            # world units per pixel at this depth = depth / focal
            scale = (depth / focal) * WIDTH_PX

            # offset in camera space, then back to object space
            offset_cam = np.zeros((n, 3))
            offset_cam[:, 0] = d[:, 0] * scale
            offset_cam[:, 1] = d[:, 1] * scale
            offset_world = offset_cam @ rot.T

            new_world = world + offset_world
            mesh.vertices.foreach_set("co", new_world.astype(np.float32).ravel())
            mesh.update()

            # Flip normals so Blender's backface culling matches the game's front culling.
            bpy.ops.object.select_all(action='DESELECT')
            shell.select_set(True)
            bpy.context.view_layer.objects.active = shell
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.flip_normals()
            bpy.ops.object.mode_set(mode='OBJECT')

            # Flat emission materials so only the silhouette is judged.
            def flat(name, colour):
                m = bpy.data.materials.new(name)
                m.use_nodes = True
                nodes = m.node_tree.nodes
                nodes.clear()
                out_node = nodes.new("ShaderNodeOutputMaterial")
                emit = nodes.new("ShaderNodeEmission")
                emit.inputs["Color"].default_value = colour
                m.node_tree.links.new(emit.outputs["Emission"], out_node.inputs["Surface"])
                return m

            body.data.materials.clear()
            body.data.materials.append(flat("body", (0.97, 0.97, 0.96, 1.0)))
            ink = flat("ink", (0.06, 0.06, 0.08, 1.0))
            ink.use_backface_culling = True
            shell.data.materials.clear()
            shell.data.materials.append(ink)

            world_bg = bpy.data.worlds.new("w")
            world_bg.use_nodes = True
            bg = world_bg.node_tree.nodes.get("Background")
            if bg:
                bg.inputs[0].default_value = (0.16, 0.16, 0.17, 1.0)
            scene.world = world_bg

            out = os.path.join(OUT, f"ss_{stem}_{angle:03d}.png")
            scene.render.filepath = out
            bpy.ops.render.render(write_still=True)
            print("rendered", out)


if __name__ == "__main__":
    main()
