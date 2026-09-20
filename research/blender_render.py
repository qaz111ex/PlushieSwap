"""Render the plush and its ink shell in Blender (a real 3D renderer).

Run headless:
    blender.exe --background --factory-startup --python this_file.py

The shell is drawn as the game draws it: a second mesh offset outward, with front-face
culling and a flat dark material, so only the silhouette ring shows. This is the closest
offline equivalent of an in-game screenshot, and unlike a hand-written rasteriser it
gives real perspective, depth and anti-aliasing.

Writes research/preview/blender_<stem>_<angle>.png.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = r"D:\zhuanban\Plushie Swap"
BLEND = os.path.join(ROOT, "research", "blender")
OUT = os.path.join(ROOT, "research", "preview")
ANGLES = [0, 45, 90, 135, 180, 225, 270, 315]
RES = 480


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
            scene.render.film_transparent = False
            scene.render.image_settings.file_format = 'PNG'

            objs = import_obj(src)
            body = [o for o in objs if not o.name.startswith("shell")]
            shell = [o for o in objs if o.name.startswith("shell")]

            # Merge body parts.
            if len(body) > 1:
                bpy.ops.object.select_all(action='DESELECT')
                for o in body:
                    o.select_set(True)
                bpy.context.view_layer.objects.active = body[0]
                bpy.ops.object.join()
                body = [bpy.context.view_layer.objects.active]
            body = body[0]

            # Flat emission materials: the question is whether the ink line is
            # continuous and even, not how the surface lights. Emission removes lighting
            # from the equation so the silhouette can be judged unambiguously.
            mat = bpy.data.materials.new("body")
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            nodes.clear()
            out_node = nodes.new("ShaderNodeOutputMaterial")
            emit = nodes.new("ShaderNodeEmission")
            emit.inputs["Color"].default_value = (0.97, 0.97, 0.96, 1.0)
            emit.inputs["Strength"].default_value = 1.0
            mat.node_tree.links.new(emit.outputs["Emission"], out_node.inputs["Surface"])
            body.data.materials.clear()
            body.data.materials.append(mat)

            # Shell: flat ink, front faces culled (the game's inverted hull).
            if shell:
                bpy.ops.object.select_all(action='DESELECT')
                for o in shell:
                    o.select_set(True)
                bpy.context.view_layer.objects.active = shell[0]
                if len(shell) > 1:
                    bpy.ops.object.join()
                shell = bpy.context.view_layer.objects.active

                # The game culls FRONT faces (_Cull = Front). Blender's
                # `use_backface_culling` culls BACK faces, so the shell's normals are
                # flipped first: that turns the game's front faces into Blender's back
                # faces, and the cull then removes exactly the same triangles.
                bpy.ops.object.select_all(action='DESELECT')
                shell.select_set(True)
                bpy.context.view_layer.objects.active = shell
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.flip_normals()
                bpy.ops.object.mode_set(mode='OBJECT')

                ink = bpy.data.materials.new("ink")
                ink.use_nodes = True
                nodes = ink.node_tree.nodes
                nodes.clear()
                out_node = nodes.new("ShaderNodeOutputMaterial")
                emit = nodes.new("ShaderNodeEmission")
                emit.inputs["Color"].default_value = (0.06, 0.06, 0.08, 1.0)
                emit.inputs["Strength"].default_value = 1.0
                ink.node_tree.links.new(emit.outputs["Emission"], out_node.inputs["Surface"])
                ink.use_backface_culling = True   # <-- the inverted hull
                shell.data.materials.clear()
                shell.data.materials.append(ink)

            # Frame the model.
            allv = []
            for o in bpy.data.objects:
                if o.type == 'MESH':
                    for v in o.data.vertices:
                        allv.append(o.matrix_world @ v.co)
            lo = Vector((min(v.x for v in allv), min(v.y for v in allv), min(v.z for v in allv)))
            hi = Vector((max(v.x for v in allv), max(v.y for v in allv), max(v.z for v in allv)))
            centre = (lo + hi) * 0.5
            size = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)

            # Camera: perspective, at the game's FOV, orbiting about Z (Blender up = Z).
            a = math.radians(angle)
            dist = size * 1.9
            cam_data = bpy.data.cameras.new("cam")
            cam_data.lens_unit = 'FOV'
            cam_data.angle = math.radians(50.0)
            cam = bpy.data.objects.new("cam", cam_data)
            scene.collection.objects.link(cam)
            cam.location = centre + Vector((math.sin(a) * dist, -math.cos(a) * dist, 0.0))
            direction = centre - cam.location
            cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
            scene.camera = cam

            # Lighting: a key + fill so the white body reads.
            for pos, energy in (((3, -4, 5), 1200), ((-4, -2, 2), 400)):
                light_data = bpy.data.lights.new("l", type='POINT')
                light_data.energy = energy
                light = bpy.data.objects.new("l", light_data)
                scene.collection.objects.link(light)
                light.location = centre + Vector(pos)

            # Neutral background.
            world = bpy.data.worlds.new("w")
            world.use_nodes = True
            bg = world.node_tree.nodes.get("Background")
            if bg:
                bg.inputs[0].default_value = (0.16, 0.16, 0.17, 1.0)
            scene.world = world

            out = os.path.join(OUT, f"blender_{stem}_{angle:03d}.png")
            scene.render.filepath = out
            bpy.ops.render.render(write_still=True)
            print("rendered", out)


if __name__ == "__main__":
    main()
