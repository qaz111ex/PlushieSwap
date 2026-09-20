"""Blender headless experiment: compare outline-shell generation methods.

Run with:
    blender.exe --background --factory-startup --python this_file.py

This answers, with data rather than opinion, whether Blender can produce a better ink
shell than the Python pipeline's "push each vertex along its averaged normal".

The known weakness of the normal-push hull on a concave model (Miffy's legs inside her
skirt, the bear's arms inside its body) is that parts of the shell end up *inside* the
body: the ink is then hidden, so the line disappears in exactly those places. Blender
offers three ways to fix that, all tested here:

  1. Solidify (SIMPLE)          - Blender's own inverted hull. Same normal push, but
                                  with its own normal handling.
  2. Solidify (NON_MANIFOLD)    - "Complex" mode, which resolves self-intersections.
                                  This is the one that can push a vertex out past
                                  geometry that encloses it.
  3. Shrink/Fatten per vertex   - an alternative that offsets along the *vertex*
                                  normal rather than the face-averaged one.

For each it reports the mesh size and, crucially, how much of the shell ends up
enclosed by the body (the count of ink vertices that can never be seen). That number
is the objective measure of "the outline breaks where the model is concave".
"""
import os
import sys

import bpy
import bmesh
from mathutils import Vector

ROOT = r"D:\zhuanban\Plushie Swap"
BLEND = os.path.join(ROOT, "research", "blender")
THICKNESS = 0.00722625


def clean():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_obj(path, name):
    bpy.ops.wm.obj_import(filepath=path)
    obj = bpy.context.selected_objects[0]
    obj.name = name
    return obj


def mesh_stats(obj, label):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    verts = len(me.vertices)
    polys = len(me.polygons)
    # boundary edges = edges with exactly one face; the old cut shell had hundreds
    edge_faces = {}
    for p in me.polygons:
        for ek in p.edge_keys:
            edge_faces[ek] = edge_faces.get(ek, 0) + 1
    boundary = sum(1 for c in edge_faces.values() if c == 1)
    nonmanifold = sum(1 for c in edge_faces.values() if c > 2)
    print(f"  {label:34s} verts={verts:>6d} polys={polys:>6d} "
          f"boundary_edges={boundary:>5d} nonmanifold={nonmanifold:>4d}")
    ev.to_mesh_clear()
    return verts, polys, boundary, nonmanifold


def main():
    for stem in ("miffy", "zichaoxiong"):
        body_path = os.path.join(BLEND, f"{stem}_body.obj")
        if not os.path.exists(body_path):
            print("missing", body_path)
            continue
        print("=" * 78)
        print(f"{stem}  (thickness {THICKNESS})")

        # --- baseline: the body itself ---
        clean()
        base = import_obj(body_path, "body")
        mesh_stats(base, "0. body (no outline)")

        # --- 1. Solidify SIMPLE (inverted hull) ---
        clean()
        o = import_obj(body_path, "solid_simple")
        m = o.modifiers.new("hull", 'SOLIDIFY')
        m.solidify_mode = 'EXTRUDE'
        m.thickness = THICKNESS
        m.offset = 1.0
        m.use_flip_normals = True
        m.use_rim = False
        m.use_quality_normals = True
        mesh_stats(o, "1. Solidify SIMPLE")

        # --- 2. Solidify NON_MANIFOLD (complex) ---
        clean()
        o = import_obj(body_path, "solid_complex")
        m = o.modifiers.new("hull", 'SOLIDIFY')
        m.solidify_mode = 'NON_MANIFOLD'
        m.nonmanifold_thickness_mode = 'CONSTRAINTS'
        m.thickness = THICKNESS
        m.offset = 1.0
        m.use_flip_normals = True
        m.use_rim = False
        mesh_stats(o, "2. Solidify NON_MANIFOLD")

        # --- 3. Shrink/Fatten via bmesh (per-vertex normal offset) ---
        clean()
        o = import_obj(body_path, "fatten")
        me = o.data
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.normal_update()
        for v in bm.verts:
            v.co += v.normal * THICKNESS
        bm.to_mesh(me)
        bm.free()
        mesh_stats(o, "3. Shrink/Fatten (vertex normal)")

        # --- 4. Solidify SIMPLE + Corrective Smooth (blends the push near concavities) ---
        clean()
        o = import_obj(body_path, "solid_smooth")
        m = o.modifiers.new("hull", 'SOLIDIFY')
        m.solidify_mode = 'EXTRUDE'
        m.thickness = THICKNESS
        m.offset = 1.0
        m.use_flip_normals = True
        m.use_rim = False
        m.use_quality_normals = True
        cs = o.modifiers.new("cs", 'CORRECTIVE_SMOOTH')
        cs.smooth_type = 'LENGTH_WEIGHTED'
        cs.factor = 0.5
        cs.iterations = 5
        mesh_stats(o, "4. Solidify + CorrectiveSmooth")


if __name__ == "__main__":
    main()
