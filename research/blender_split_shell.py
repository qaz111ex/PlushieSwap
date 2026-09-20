"""Render the ink shell split by source submesh, each in a distinct colour.

The screen-space render showed the shell drawing dark pixels *inside* the body at a
concave region (the muzzle / paw area). This colours each solid submesh's ink
differently so the culprit is identifiable by eye instead of guessed at.
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
ANGLE = 135

COLOURS = [
    (0.9, 0.1, 0.1, 1.0),   # submesh 0 (dark face)
    (0.1, 0.8, 0.1, 1.0),   # submesh 1 (blush)
    (0.1, 0.2, 0.9, 1.0),   # submesh 2 (body)
    (0.9, 0.8, 0.1, 1.0),
]


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
    clean()
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = RES
    scene.render.resolution_y = RES
    scene.render.image_settings.file_format = 'PNG'

    objs = import_obj(os.path.join(BLEND, f"{STEM}_render.obj"))
    body = [o for o in objs if not o.name.startswith("shell")]
    shell = [o for o in objs if o.name.startswith("shell")]
    body.sort(key=lambda o: o.name)
    shell.sort(key=lambda o: o.name)
    print("body objs:", [o.name for o in body])
    print("shell objs:", [o.name for o in shell])

    # Frame using the body.
    allv = []
    for o in body:
        for v in o.data.vertices:
            allv.append(v.co)
    lo = Vector((min(v.x for v in allv), min(v.y for v in allv), min(v.z for v in allv)))
    hi = Vector((max(v.x for v in allv), max(v.y for v in allv), max(v.z for v in allv)))
    centre = (lo + hi) * 0.5
    size = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)

    a = math.radians(ANGLE)
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
    focal = (RES * 0.5) / math.tan(fov * 0.5)
    rot = np.array(cam.matrix_world.to_3x3())
    cam_inv = np.array(cam.matrix_world.inverted())

    # Body: flat white.
    for o in body:
        o.data.materials.clear()
        o.data.materials.append(flat("b" + o.name, (0.97, 0.97, 0.96, 1.0)))

    # Shell: screen-space extrusion, one colour per source submesh.
    for i, o in enumerate(shell):
        mesh = o.data
        n = len(mesh.vertices)
        co = np.empty((n, 3)); mesh.vertices.foreach_get("co", co.ravel())
        no = np.empty((n, 3)); mesh.vertices.foreach_get("normal", no.ravel())
        homog = np.concatenate([co, np.ones((n, 1))], axis=1)
        cam_co = homog @ cam_inv.T
        depth = -cam_co[:, 2]
        cam_no = no @ rot.T
        d = cam_no[:, :2].copy()
        ln = np.linalg.norm(d, axis=1, keepdims=True); ln[ln < 1e-8] = 1.0
        d = d / ln
        scale = (depth / focal) * WIDTH_PX
        off = np.zeros((n, 3)); off[:, 0] = d[:, 0] * scale; off[:, 1] = d[:, 1] * scale
        mesh.vertices.foreach_set("co", (co + off @ rot.T).astype(np.float32).ravel())
        mesh.update()

        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.flip_normals()
        bpy.ops.object.mode_set(mode='OBJECT')

        col = COLOURS[i % len(COLOURS)]
        o.data.materials.clear()
        o.data.materials.append(flat(f"ink{i}", col, cull=True))

    world_bg = bpy.data.worlds.new("w")
    world_bg.use_nodes = True
    bg = world_bg.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.16, 0.16, 0.17, 1.0)
    scene.world = world_bg

    out = os.path.join(OUT, f"split_{STEM}_{ANGLE:03d}.png")
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("rendered", out)


if __name__ == "__main__":
    main()
