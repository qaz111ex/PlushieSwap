"""Simulate the plugin's mesh build to prove the single-submesh fix renders everything.

The bug being guarded against: assigning one material to a multi-submesh mesh makes
Unity draw only submesh 0, so only the first colour (the black eyes/mouth) appeared.
The plugin now merges every part into submesh 0.
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preview_mesh import read_psmesh, load_shading_texture  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\tools\preview"


def merge_like_plugin(path):
    """Reproduce PlushieModel.BuildMesh for the solid parts (outline excluded)."""
    name, subs, lo, hi = read_psmesh(path)
    verts, normals, uvs, idx = [], [], [], []
    offset = 0
    for entry in subs:
        colour, v, n, uv, i = entry[0], entry[1], entry[2], entry[3], entry[4]
        flags = entry[5] if len(entry) > 5 else 0
        if flags & 1:
            continue  # outline shell, handled separately
        verts.append(v)
        normals.append(n)
        uvs.append(uv)
        idx.append(i + offset)
        offset += len(v)
    return (name,
            np.concatenate(verts, axis=0),
            np.concatenate(normals, axis=0),
            np.concatenate(uvs, axis=0),
            np.concatenate(idx, axis=0),
            lo, hi)


def outline_mesh(path):
    """The inverted-hull shell, drawn with front faces culled."""
    name, subs, lo, hi = read_psmesh(path)
    verts, normals, idx = [], [], []
    offset = 0
    for entry in subs:
        flags = entry[5] if len(entry) > 5 else 0
        if not (flags & 1):
            continue
        v, n, i = entry[1], entry[2], entry[4]
        verts.append(v)
        normals.append(n)
        idx.append(i + offset)
        offset += len(v)
    if not verts:
        return None
    return (np.concatenate(verts, axis=0), np.concatenate(normals, axis=0),
            np.concatenate(idx, axis=0))


def render(merged, texture, out_path, size=420, outline=None):
    name, verts, normals, uvs, idx, lo, hi = merged
    centre = (lo + hi) * 0.5
    extent = float(max(hi - lo)) * 0.62

    fwd = np.array([0.0, 0.0, -1.0])
    up_in = np.array([0.0, 1.0, 0.0])
    right = np.cross(up_in, fwd); right /= np.linalg.norm(right)
    up = np.cross(fwd, right)

    v = verts - centre
    px = ((v @ right / extent) * 0.5 + 0.5) * (size - 1)
    py = (1.0 - ((v @ up / extent) * 0.5 + 0.5)) * (size - 1)
    pz = v @ fwd

    height, width = texture.shape[0], texture.shape[1]
    x = np.clip(uvs[:, 0], 0.0, 1.0) * width - 0.5
    x0 = np.clip(np.floor(x).astype(np.int64), 0, width - 1)
    x1 = np.clip(x0 + 1, 0, width - 1)
    frac = (x - np.floor(x))[:, None]
    albedo = texture[0][x0] * (1 - frac) + texture[0][x1] * frac
    albedo = albedo[:, :3]

    zbuf = np.full((size, size), -1e30, dtype=np.float32)
    img = np.full((size, size, 3), 0.12, dtype=np.float32)

    def draw(verts_w, tris, colours, cull_front, depth_bias=0.0):
        w = verts_w - centre
        wpx = ((w @ right / extent) * 0.5 + 0.5) * (size - 1)
        wpy = (1.0 - ((w @ up / extent) * 0.5 + 0.5)) * (size - 1)
        wpz = w @ fwd
        order = np.argsort(wpz[tris].mean(axis=1))
        for k in order:
            i0, i1, i2 = tris[k]
            ax, ay, az = wpx[i0], wpy[i0], wpz[i0]
            bx, by, bz = wpx[i1], wpy[i1], wpz[i1]
            cx, cy, cz = wpx[i2], wpy[i2], wpz[i2]
            minx = max(int(min(ax, bx, cx)), 0)
            maxx = min(int(max(ax, bx, cx)) + 1, size - 1)
            miny = max(int(min(ay, by, cy)), 0)
            maxy = min(int(max(ay, by, cy)) + 1, size - 1)
            if minx > maxx or miny > maxy:
                continue
            det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(det) < 1e-9:
                continue
            # screen-space winding tells us which side faces the camera
            if cull_front and det <= 0:
                continue
            ys, xs = np.mgrid[miny:maxy + 1, minx:maxx + 1]
            l0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / det
            l1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / det
            l2 = 1.0 - l0 - l1
            mask = (l0 >= -0.004) & (l1 >= -0.004) & (l2 >= -0.004)
            if not mask.any():
                continue
            depth = l0 * az + l1 * bz + l2 * cz + depth_bias
            rz = zbuf[miny:maxy + 1, minx:maxx + 1]
            write = mask & (depth > rz)
            if not write.any():
                continue
            col = (l0[..., None] * colours[i0] + l1[..., None] * colours[i1] + l2[..., None] * colours[i2])
            region = img[miny:maxy + 1, minx:maxx + 1]
            region[write] = np.clip(col[write], 0, 1)
            rz[write] = depth[write]

    # Draw the body first, then the ink shell. The shell is culled on front faces, so
    # what survives is the ring around the silhouette plus the crease bands where a
    # limb enters the body. A hair of depth bias keeps the ring from z-fighting with
    # the body it hugs.
    draw(verts, idx, albedo, False)
    if outline is not None:
        overts, onormals, otris = outline
        draw(overts, otris, np.tile(np.array([0.085, 0.085, 0.105]), (len(overts), 1)),
             True, depth_bias=extent * 0.004)

    out = (np.clip(img, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    Image.fromarray(out).save(out_path)
    print("wrote", out_path, " triangles:", len(idx))


if __name__ == "__main__":
    for stem in ("miffy", "zichaoxiong"):
        path = os.path.join(ASSETS, stem + ".psmesh")
        merged = merge_like_plugin(path)
        texture = load_shading_texture(path)
        render(merged, texture, os.path.join(OUT, stem + "_merged.png"),
               outline=outline_mesh(path))
