"""Build the ink shell with Blender's Solidify, measure and render it.

The inverted-hull shell is a copy of the body pushed out along its normals. On a
concave surface that push crosses the groove and lands on the far wall, so the ink is
drawn inside the model. Blender's Solidify has a dedicated "Complex" (non-manifold)
mode whose stated purpose is to resolve exactly that, rather than a hand-written vertex
offset.

For each body this:
  1. builds the shell with Solidify SIMPLE and with Solidify COMPLEX,
  2. counts self-intersecting faces using Blender's own mesh.intersect operator,
  3. renders both with backface culling (the inverted hull) for visual comparison.

Run:
    blender.exe --background --factory-startup --python this_file.py
"""
import math
import os

import bpy
import bmesh
import numpy as np
from mathutils import Vector

ROOT = r"D:\zhuanban\Plushie Swap"
BLEND = os.path.join(ROOT, "research", "blender")
OUT = os.path.join(ROOT, "research", "preview")
THICK = 0.0075 * 0.9635
RES = 700
ANGLE = 135


def clean():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_obj(path):
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def join(objs):
    if len(objs) == 1:
        return objs[0]
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def count_intersections(obj):
    """Self-intersecting face count, using Blender's own intersect operator."""
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_mode(type='FACE')
    try:
        bpy.ops.mesh.intersect(mode='SELECT', separate_mode='ALL', threshold=1e-6)
        selected = 0
        bm = bmesh.from_edit_mesh(obj.data)
        for f in bm.faces:
            if f.select:
                selected += 1
        bpy.ops.object.mode_set(mode='OBJECT')
        return selected
    except Exception as e:
        print("   intersect failed:", e)
        bpy.ops.object.mode_set(mode='OBJECT')
        return -1


def build_shell(body, mode):
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.duplicate()
    shell = bpy.context.view_layer.objects.active
    shell.name = f"shell_{mode}"

    m = shell.modifiers.new("hull", 'SOLIDIFY')
    m.thickness = THICK
    m.offset = 1.0
    m.use_rim = False
    m.use_flip_normals = True
    if mode == "simple":
        m.solidify_mode = 'EXTRUDE'
        m.use_quality_normals = True
    else:
        m.solidify_mode = 'NON_MANIFOLD'
        m.nonmanifold_thickness_mode = 'CONSTRAINTS'
        m.nonmanifold_boundary_mode = 'NONE'
    bpy.ops.object.modifier_apply(modifier="hull")
    return shell


def flat_material(name, colour, cull):
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


def render(body, shell, path, angle_deg):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = RES
    scene.render.resolution_y = RES
    scene.render.image_settings.file_format = 'PNG'

    allv = [v.co for v in body.data.vertices]
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
    cam.rotation_euler = (centre - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam

    body.data.materials.clear()
    body.data.materials.append(flat_material("body", (0.97, 0.97, 0.96, 1.0), False))
    shell.data.materials.clear()
    # The shell from Solidify is a double surface. Rendering it with backface culling
    # is the inverted hull: only the ring where the offset surface wraps the silhouette
    # survives.
    shell.data.materials.append(flat_material("ink", (0.05, 0.05, 0.07, 1.0), True))

    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.16, 0.16, 0.17, 1.0)
    scene.world = w

    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def main():
    print("Blender", bpy.app.version_string)
    for stem in ("miffy", "zichaoxiong"):
        src = os.path.join(BLEND, f"{stem}_body.obj")
        if not os.path.exists(src):
            print("missing", src)
            continue
        print("=" * 70)
        print(stem)
        for mode in ("simple", "complex"):
            clean()
            body = join(import_obj(src))
            shell = build_shell(body, mode)
            print(f"  {mode}: shell verts {len(shell.data.vertices)} "
                  f"faces {len(shell.data.polygons)}")
            print(f"  {mode}: self-intersecting faces = {count_intersections(shell)}")
            render(body, shell, os.path.join(OUT, f"solid_{stem}_{mode}.png"), ANGLE)


if __name__ == "__main__":
    main()
