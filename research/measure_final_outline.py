"""Measure the SHIPPED outline's screen-space width per silhouette vertex.

"Uneven and broken" is a measurable claim: for a good outline every silhouette vertex
should map to the same number of screen pixels, and every shell triangle should be
visible. This projects the real shell the way the game's driver does and reports the
distribution, plus which vertices produce no visible line at all (the "broken" part).
"""
import os
import struct
import sys

import numpy as np

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
SCREEN_H = 1080.0
FOV = 50.0
WIDTH_PX = 5.0


def read(path):
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
        o += vc * 8
        o += vc * 12
        idx = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3); o += ic * 4
        subs.append((flags, verts, normals, idx))
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
    return subs, lo, hi, widths, baked


def project(v, centre, dist):
    """Camera at -dist looking +Z; returns screen x,y in pixels and depth."""
    p = v - np.array([0.0, 0.0, 0.0])
    z = p[:, 2] + dist
    f = (SCREEN_H * 0.5) / np.tan(np.radians(FOV * 0.5))
    x = (p[:, 0] / z) * f + SCREEN_H * 0.5
    y = (p[:, 1] / z) * f + SCREEN_H * 0.5
    return x, y, z


def main():
    for stem in ("miffy", "zichaoxiong"):
        subs, lo, hi, widths, baked = read(os.path.join(ASSETS, stem + ".psmesh"))
        shell = [(f, v, n, t) for f, v, n, t in subs if f & 1]
        flags, sv, sn, st = shell[0]
        centre = (lo + hi) * 0.5
        dist = 0.9

        # Recover the surface and re-extrude exactly like the game does.
        w = widths if widths is not None else np.ones(len(sv))
        surface = sv - sn * (baked * w)[:, None]

        sx, sy, sz = project(surface, centre, dist)
        nx, ny, nz = sn[:, 0], sn[:, 1], sn[:, 2]

        # Screen-space normal direction
        d = np.stack([nx, ny], axis=1)
        ln = np.linalg.norm(d, axis=1, keepdims=True)
        ln[ln < 1e-8] = 1.0
        d = d / ln

        per_pixel = (2.0 * np.tan(np.radians(FOV * 0.5))) / SCREEN_H
        scale = per_pixel * WIDTH_PX * w * sz
        # A world offset at depth z covers `world * f / z` pixels, with
        # f = (screen_h/2)/tan(fov/2). The driver's `scale` already carries the depth,
        # so the divide by z cancels it and every vertex lands on the same pixel count.
        f = (SCREEN_H * 0.5) / np.tan(np.radians(FOV * 0.5))
        pix = scale * f / sz
        ex = sx + d[:, 0] * pix
        ey = sy + d[:, 1] * pix

        # Only silhouette vertices matter: |screen normal| large, and inked.
        sil = (np.hypot(nx, ny) >= 0.35) & (w > 0)
        disp = np.hypot(ex - sx, ey - sy)[sil]

        print("=" * 70)
        print(f"{stem}: {int(sil.sum())} silhouette inked verts of {len(sv)}")
        print(f"  per-vertex screen displacement (px): "
              f"mean {disp.mean():.3f}  std {disp.std():.3f}  "
              f"p5 {np.percentile(disp,5):.3f}  p95 {np.percentile(disp,95):.3f}")
        print(f"  target was {WIDTH_PX:.1f} px  -> "
              f"ratio p95/p5 = {np.percentile(disp,95)/max(1e-9,np.percentile(disp,5)):.3f}")
        # Direction validity: vertices whose normal is nearly camera-facing produce no
        # offset (dx=dy=0), which is a genuine break in the line.
        degenerate = ((np.hypot(nx, ny) < 1e-8) & (w > 0)).sum()
        print(f"  degenerate (zero screen normal, draws no offset): {degenerate}")
        # Width steps: adjacent silhouette vertices with very different ink
        print(f"  width range on silhouette: {w[sil].min():.2f}..{w[sil].max():.2f}")


if __name__ == "__main__":
    main()
