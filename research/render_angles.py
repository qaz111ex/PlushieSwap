"""Render the shipped shell from many angles at a scale where the line is visible.

The extrusion is recomputed for the render's own projection so the line is a true 5 px
in the output, matching the game at 1080p. A full yaw sweep makes any angle where the
line thins, gaps, or throws a stray spur visible.
"""
import os
import sys

import numpy as np
from PIL import Image

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\research\preview"
PIXELS = 4.0


def read_psmesh(path):
    import struct
    with open(path, "rb") as fh:
        d = fh.read()
    o = 8
    n = struct.unpack_from("<i", d, o)[0]; o += 4 + n
    count = struct.unpack_from("<i", d, o)[0]; o += 4
    subs = []
    for _ in range(count):
        o += 16
        flags = struct.unpack_from("<i", d, o)[0]; o += 4
        vc, ic = struct.unpack_from("<ii", d, o); o += 8
        verts = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        normals = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        uvs = np.frombuffer(d[o:o + vc * 8], "<f4").reshape(-1, 2); o += vc * 8
        o += vc * 12
        idx = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3); o += ic * 4
        subs.append(dict(flags=flags, v=verts, n=normals, uv=uvs, t=idx))
    lo = np.array(struct.unpack_from("<3f", d, o)); o += 12
    hi = np.array(struct.unpack_from("<3f", d, o)); o += 12
    has = struct.unpack_from("<i", d, o)[0]; o += 4
    if has:
        o += 12 + 12 + 16 + 16
    wob = struct.unpack_from("<i", d, o)[0]; o += 4 + wob
    oc = struct.unpack_from("<i", d, o)[0]; o += 4
    widths = None
    if oc:
        o += oc * 4
        widths = np.frombuffer(d[o:o + oc], np.uint8).astype(float) / 255.0
        o += oc
    baked = struct.unpack_from("<f", d, o)[0]; o += 4
    assert o == len(d)
    return subs, lo, hi, widths, baked


def render_angles(stem, angles, size=440, zoom=0.74, pixels=PIXELS, distance=0.9):
    subs, lo, hi, widths, baked = read_psmesh(os.path.join(ASSETS, stem + ".psmesh"))
    solid = [s for s in subs if not (s["flags"] & 1)]
    shell = [s for s in subs if (s["flags"] & 1)]

    bv = np.concatenate([s["v"] for s in solid])
    bt = []; off = 0
    for s in solid:
        bt.append(s["t"] + off); off += len(s["v"])
    bt = np.concatenate(bt)
    buv = np.concatenate([s["uv"] for s in solid])

    sh_v = np.concatenate([s["v"] for s in shell])
    sh_n = np.concatenate([s["n"] for s in shell])
    sh_t = []; off = 0
    for s in shell:
        sh_t.append(s["t"] + off); off += len(s["v"])
    sh_t = np.concatenate(sh_t)
    w = widths if widths is not None else np.ones(len(sh_v))

    tex = None
    p = os.path.join(ASSETS, stem + "_shading.png")
    if os.path.exists(p):
        tex = np.asarray(Image.open(p).convert("RGBA"), np.float32) / 255.0

    allv = np.concatenate([bv, sh_v])
    centre0 = (allv.min(0) + allv.max(0)) * 0.5
    height0 = float(max(allv.max(0) - allv.min(0)))

    # A real perspective camera, like the game's: at `distance` in front of the model,
    # 50 deg vertical FOV. The extrusion is computed in that camera's screen space, so
    # the line is a true `pixels` wide in the output.
    fov = 50.0
    screen_h = float(size)
    focal = (screen_h * 0.5) / np.tan(np.radians(fov * 0.5))
    per_pixel = 1.0 / focal  # world units per pixel, per unit of depth

    tiles = []
    for yaw in angles:
        ang = np.radians(yaw)
        rot = np.array([[np.cos(ang), 0, np.sin(ang)],
                        [0, 1, 0],
                        [-np.sin(ang), 0, np.cos(ang)]])
        bvr = bv @ rot.T
        svr = sh_v @ rot.T
        snr = sh_n @ rot.T
        centre = centre0 @ rot.T

        fwd = np.array([0.0, 0.0, -1.0])
        right = np.cross(np.array([0.0, 1.0, 0.0]), fwd); right /= np.linalg.norm(right)
        up = np.cross(fwd, right)

        # Camera-space point: camera sits at centre + (0,0,distance) looking -Z.
        cam_origin = centre + np.array([0.0, 0.0, distance])
        def to_cam(v):
            return v - cam_origin

        # Recover the surface, then extrude along the screen-space normal by
        # perPixel * depth * width pixels (exactly the game's formula).
        surface = svr - snr * (baked * w)[:, None]
        cams = surface - cam_origin
        depth = -cams[:, 2]                     # positive in front
        d2 = snr[:, :2]
        ln = np.linalg.norm(d2, axis=1, keepdims=True)
        ln[ln < 1e-8] = 1.0
        d2 = d2 / ln
        scale = per_pixel * pixels * w * depth
        ext = surface + np.column_stack([d2[:, 0] * scale, d2[:, 1] * scale,
                                         np.zeros(len(surface))])
        ext = np.where((w > 0)[:, None], ext, surface)

        def proj(v):
            c = v - cam_origin
            z = np.maximum(-c[:, 2], 1e-4)
            px = (c[:, 0] / z) * focal + (size - 1) * 0.5
            py = (1.0 - ((c[:, 1] / z) * focal / (size - 1) + 0.5)) * (size - 1)
            return px, py, -z

        zbuf = np.full((size, size), -1e30, np.float32)
        img = np.full((size, size, 3), 0.13, np.float32)

        def draw(verts, tris, colours, cull_front):
            px, py, pz = proj(verts)
            for k in np.argsort(pz[tris].mean(axis=1)):
                i0, i1, i2 = tris[k]
                ax, ay, az = px[i0], py[i0], pz[i0]
                bx, by, bz = px[i1], py[i1], pz[i1]
                cx, cy, cz = px[i2], py[i2], pz[i2]
                minx = max(int(min(ax, bx, cx)), 0); maxx = min(int(max(ax, bx, cx)) + 1, size - 1)
                miny = max(int(min(ay, by, cy)), 0); maxy = min(int(max(ay, by, cy)) + 1, size - 1)
                if minx > maxx or miny > maxy:
                    continue
                det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
                if abs(det) < 1e-9:
                    continue
                if cull_front and det <= 0:
                    continue
                ys, xs = np.mgrid[miny:maxy + 1, minx:maxx + 1]
                l0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / det
                l1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / det
                l2 = 1.0 - l0 - l1
                mask = (l0 >= -0.004) & (l1 >= -0.004) & (l2 >= -0.004)
                if not mask.any():
                    continue
                depth_t = l0 * az + l1 * bz + l2 * cz
                rz = zbuf[miny:maxy + 1, minx:maxx + 1]
                write = mask & (depth_t > rz)
                if not write.any():
                    continue
                col = (l0[..., None] * colours[i0] + l1[..., None] * colours[i1]
                       + l2[..., None] * colours[i2])
                region = img[miny:maxy + 1, minx:maxx + 1]
                region[write] = np.clip(col[write], 0, 1)
                rz[write] = depth_t[write]

        if tex is not None:
            x = np.clip(buv[:, 0], 0, 1) * tex.shape[1] - 0.5
            x0 = np.clip(np.floor(x).astype(int), 0, tex.shape[1] - 1)
            x1 = np.clip(x0 + 1, 0, tex.shape[1] - 1)
            fr = (x - np.floor(x))[:, None]
            bc = (tex[0][x0] * (1 - fr) + tex[0][x1] * fr)[:, :3]
        else:
            bc = np.tile(np.array([0.9, 0.9, 0.9]), (len(bvr), 1))
        draw(bvr, bt, bc, False)
        draw(ext, sh_t, np.tile(np.array([0.085, 0.085, 0.105]), (len(ext), 1)), True)
        tiles.append(Image.fromarray((np.clip(img, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)))
    return tiles


def main():
    angles = [0, 45, 90, 135, 180, 225, 270, 315]
    for stem in ("miffy", "zichaoxiong"):
        # distance 1.5 m frames the ~1 m plush at the game's 50 deg FOV; 5 px matches
        # the mod's configured outline width.
        tiles = render_angles(stem, angles, size=440, pixels=5.0, distance=1.5)
        cols = 4
        rows = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGB", (440 * cols, 440 * rows), (30, 30, 30))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % cols) * 440, (i // cols) * 440))
        sheet.save(os.path.join(OUT, f"angles_{stem}.png"))
        print("wrote", f"angles_{stem}.png")


if __name__ == "__main__":
    main()
