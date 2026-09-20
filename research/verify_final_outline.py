"""Simulate the game's outline exactly: front-face-culled shell, no depth bias.

This reads the shipped .psmesh (including the per-vertex width map), reproduces what
PlushieOutline does on the CPU (undo the baked push, re-extrude in screen space scaled
by the width), and rasterises the result with front faces culled and ZERO depth bias —
the real game gives the ink no bias. It is the closest thing to a screenshot that can
be produced without launching PEAK.

It also measures the boundary-edge count of the shell, which is the objective test for
"is the line continuous": the old pipeline cut faces and left hundreds of boundary
edges, the new one must leave none beyond the body's own.
"""
import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, r"D:\zhuanban\Plushie Swap\tools")
from preview_mesh import sample_shading  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\research\preview"

WIDTH_PIXELS = 5.0
SCREEN_H = 1080.0
FOV = 50.0
DISTANCE = 0.9


def read_psmesh(path):
    """Full reader including grips and the outline width map."""
    with open(path, "rb") as fh:
        d = fh.read()
    o = 0
    magic = d[o:o + 8]; o += 8
    assert magic == b"PSMESH03", magic
    n = struct.unpack_from("<i", d, o)[0]; o += 4
    name = d[o:o + n].decode("utf-8"); o += n
    count = struct.unpack_from("<i", d, o)[0]; o += 4
    subs = []
    for _ in range(count):
        colour = np.array(struct.unpack_from("<4f", d, o)); o += 16
        flags = struct.unpack_from("<i", d, o)[0]; o += 4
        vc, ic = struct.unpack_from("<ii", d, o); o += 8
        verts = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        normals = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        uvs = np.frombuffer(d[o:o + vc * 8], "<f4").reshape(-1, 2); o += vc * 8
        o += vc * 12
        idx = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3); o += ic * 4
        subs.append(dict(colour=colour, flags=flags, v=verts, n=normals, uv=uvs, t=idx))
    lo = np.array(struct.unpack_from("<3f", d, o)); o += 12
    hi = np.array(struct.unpack_from("<3f", d, o)); o += 12
    has = struct.unpack_from("<i", d, o)[0]; o += 4
    grips = None
    if has:
        gl = np.array(struct.unpack_from("<3f", d, o)); o += 12
        gr = np.array(struct.unpack_from("<3f", d, o)); o += 12
        o += 32
        grips = (gl, gr)
    wob = struct.unpack_from("<i", d, o)[0]; o += 4 + wob
    oc = struct.unpack_from("<i", d, o)[0]; o += 4
    widths = None
    if oc:
        o += oc * 4
        widths = np.frombuffer(d[o:o + oc], np.uint8).astype(np.float64) / 255.0
        o += oc
    baked = struct.unpack_from("<f", d, o)[0]; o += 4
    assert o == len(d), f"{o} != {len(d)}"
    return name, subs, lo, hi, grips, widths, baked


def boundary(t):
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    k = np.sort(e, axis=1)
    _u, c = np.unique(k, axis=0, return_counts=True)
    return int((c == 1).sum())


def extrude_screen_space(shell_v, shell_n, widths, baked, size):
    """Reproduce PlushieOutline.LateUpdate for a head-on camera."""
    surface = shell_v - shell_n * (baked * (widths if widths is not None else 1.0))[:, None]
    # camera looks down +Z from -distance; model at origin
    per_pixel = (2.0 * np.tan(np.radians(FOV * 0.5))) / SCREEN_H
    out = surface.copy()
    for i in range(len(surface)):
        ink = widths[i] if widths is not None else 1.0
        if ink <= 0:
            out[i] = surface[i]
            continue
        p = surface[i] - np.array([0.0, 0.0, -DISTANCE])
        depth = p[2]
        n = shell_n[i]
        d = np.array([n[0], n[1]])
        ln = np.linalg.norm(d)
        if ln > 1e-8:
            d /= ln
        else:
            d[:] = 0
        scale = per_pixel * WIDTH_PIXELS * ink * depth
        out[i] = surface[i] + np.array([d[0] * scale, d[1] * scale, 0.0])
    return out


def render(solid, shell, size=640, zoom=0.62):
    """Painter's-algorithm rasteriser: body first, then the shell front-culled."""
    all_v = np.concatenate([solid["v"], shell["v"]])
    lo = all_v.min(0); hi = all_v.max(0)
    centre = (lo + hi) * 0.5
    extent = float(max(hi - lo)) * zoom

    fwd = np.array([0.0, 0.0, -1.0])
    right = np.cross(np.array([0.0, 1.0, 0.0]), fwd); right /= np.linalg.norm(right)
    up = np.cross(fwd, right)

    def project(v):
        w = v - centre
        px = ((w @ right / extent) * 0.5 + 0.5) * (size - 1)
        py = (1.0 - ((w @ up / extent) * 0.5 + 0.5)) * (size - 1)
        pz = w @ fwd
        return px, py, pz

    tex = None
    shading_path = os.path.join(ASSETS, stem_tex + "_shading.png")
    if os.path.exists(shading_path):
        from PIL import Image as I
        tex = np.asarray(I.open(shading_path).convert("RGBA"), np.float32) / 255.0

    zbuf = np.full((size, size), -1e30, np.float32)
    img = np.full((size, size, 3), 0.13, np.float32)

    def draw(verts, tris, colours, cull_front):
        px, py, pz = project(verts)
        order = np.argsort(pz[tris].mean(axis=1))
        for k in order:
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
            depth = l0 * az + l1 * bz + l2 * cz
            rz = zbuf[miny:maxy + 1, minx:maxx + 1]
            write = mask & (depth > rz)
            if not write.any():
                continue
            col = l0[..., None] * colours[i0] + l1[..., None] * colours[i1] + l2[..., None] * colours[i2]
            region = img[miny:maxy + 1, minx:maxx + 1]
            region[write] = np.clip(col[write], 0, 1)
            rz[write] = depth[write]

    # body
    if tex is not None:
        x = np.clip(solid["uv"][:, 0], 0, 1) * tex.shape[1] - 0.5
        x0 = np.clip(np.floor(x).astype(int), 0, tex.shape[1] - 1)
        x1 = np.clip(x0 + 1, 0, tex.shape[1] - 1)
        fr = (x - np.floor(x))[:, None]
        body_col = (tex[0][x0] * (1 - fr) + tex[0][x1] * fr)[:, :3]
    else:
        body_col = np.tile(solid["colour"][:3], (len(solid["v"]), 1))
    draw(solid["v"], solid["t"], body_col, cull_front=False)
    draw(shell["v"], shell["t"],
         np.tile(np.array([0.085, 0.085, 0.105]), (len(shell["v"]), 1)),
         cull_front=True)

    out = (np.clip(img, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    return out


def main():
    global stem_tex
    for stem in ("miffy", "zichaoxiong"):
        stem_tex = stem
        path = os.path.join(ASSETS, stem + ".psmesh")
        name, subs, lo, hi, grips, widths, baked = read_psmesh(path)
        solid = [s for s in subs if not (s["flags"] & 1)]
        shell_subs = [s for s in subs if s["flags"] & 1]

        sv = np.concatenate([s["v"] for s in solid])
        st = []; off = 0
        for s in solid:
            st.append(s["t"] + off); off += len(s["v"])
        st = np.concatenate(st)
        uvs = np.concatenate([s["uv"] for s in solid])

        sh_v = np.concatenate([s["v"] for s in shell_subs])
        sh_n = np.concatenate([s["n"] for s in shell_subs])
        sh_t = []; off = 0
        for s in shell_subs:
            sh_t.append(s["t"] + off); off += len(s["v"])
        sh_t = np.concatenate(sh_t)

        print("=" * 70)
        print(f"{stem}: body {len(sv)}v/{len(st)}t  shell {len(sh_v)}v/{len(sh_t)}t")
        print(f"  shell boundary edges: {boundary(sh_t)}  "
              f"(body's own: {boundary(st)})")
        print(f"  widths: min {widths.min():.2f} max {widths.max():.2f} "
              f"zero {int((widths <= 0).sum())}")

        ext = extrude_screen_space(sh_v, sh_n, widths, baked, 640)
        body = dict(v=sv, t=st, uv=uvs, colour=solid[0]["colour"])
        shell = dict(v=ext, t=sh_t)
        img = render(body, shell, size=640)
        Image.fromarray(img).save(os.path.join(OUT, f"final_{stem}.png"))
        print(f"  wrote final_{stem}.png")


if __name__ == "__main__":
    main()
