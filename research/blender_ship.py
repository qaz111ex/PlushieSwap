"""Render the SHIPPED shell (as baked) in Blender, with and without ink.

Reads assets/<stem>.psmesh directly, so it renders exactly what the game ships: the
shell vertices are already `surface + direction * thickness * width`. Renders the body
only, and body+shell with front-face culling (the inverted hull), from the face side and
a three-quarter view.

Run:
    blender.exe --background --factory-startup --python this_file.py
"""
import math
import os
import struct

import bpy
import numpy as np
from mathutils import Vector

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ROOT, "research", "preview")
RES = 800
ANGLES = (0, 40, 90)


def clean():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def read(path):
    with open(path, "rb") as fh:
        d = fh.read()
    o = 8
    n = struct.unpack_from("<i", d, o)[0]; o += 4 + n
    count = struct.unpack_from("<i", d, o)[0]; o += 4
    subs = []
    for _ in range(count):
        colour = np.array(struct.unpack_from("<4f", d, o)); o += 16
        flags = struct.unpack_from("<i", d, o)[0]; o += 4
        vc, ic = struct.unpack_from("<ii", d, o); o += 8
        v = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        o += vc * 12 + vc * 8 + vc * 12
        t = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3); o += ic * 4
        subs.append((flags, v, t))
    return subs


def write_obj(path, groups):
    with open(path, "w", encoding="utf-8") as fh:
        base = 1
        for name, verts, tris in groups:
            fh.write(f"o {name}\n")
            for v in verts:
                fh.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
            for t in tris:
                fh.write(f"f {t[0]+base} {t[1]+base} {t[2]+base}\n")
            base += len(verts)


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

    a = math.radians(angle_deg)
    dist = size * 1.8
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
        subs = read(os.path.join(ASSETS, stem + ".psmesh"))
        solid = [s for s in subs if not (s[0] & 1)]
        shell = [s for s in subs if s[0] & 1]

        bv = np.concatenate([s[1] for s in solid])
        bt = []; off = 0
        for s in solid:
            bt.append(s[2] + off); off += len(s[1])
        bt = np.concatenate(bt)

        sv = np.concatenate([s[1] for s in shell])
        st = []; off = 0
        for s in shell:
            st.append(s[2] + off); off += len(s[1])
        st = np.concatenate(st)

        for angle in ANGLES:
            for with_ink in (False, True):
                clean()
                scene = bpy.context.scene
                scene.render.engine = 'BLENDER_EEVEE'
                scene.render.resolution_x = RES
                scene.render.resolution_y = RES
                scene.render.image_settings.file_format = 'PNG'

                obj = os.path.join(ROOT, "research", "blender",
                                   f"shipped_{stem}_{'ink' if with_ink else 'plain'}.obj")
                groups = [("body", bv, bt)]
                if with_ink:
                    groups.append(("shell", sv, st))
                write_obj(obj, groups)

                bpy.ops.wm.obj_import(filepath=obj)
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

                tag = "ink" if with_ink else "plain"
                render(scene, body, angle,
                       os.path.join(OUT, f"ship_{stem}_{tag}_{angle:03d}.png"))
                print("rendered", f"ship_{stem}_{tag}_{angle:03d}.png")


if __name__ == "__main__":
    main()
