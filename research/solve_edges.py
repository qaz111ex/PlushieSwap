"""Solve for the model shift that puts both hand anchors exactly on the silhouette.

The vanilla prefab shows the rule: Hand_L and Hand_R sit ON the vanilla plush's outer
surface, 0.6034 apart horizontally and 0.073 apart vertically. A replacement should be
held the same way.

With the model shifted by (dx, dy), the anchors land at model coordinates

    yL = -0.177 - dy      xL = -0.359 - dx
    yR = -0.104 - dy      xR = +0.240 - dx

so the requirement is

    left_edge(yL)  = xL        right_edge(yR) = xR

Two equations, two unknowns. The first line is solved by scanning dy for the height at
which the model is 0.599 wide between yL and yR; dx then follows from the left edge.
"""
import os
import struct

import numpy as np

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")

ANCHOR_L = np.array([-0.3590, -0.1770, -0.0400])
ANCHOR_R = np.array([+0.2400, -0.1040, -0.0400])


def read_subs(path):
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
        v = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3).astype(np.float64); o += vc * 12
        o += vc * 12 + vc * 8 + vc * 12
        t = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3).astype(np.int64); o += ic * 4
        subs.append((flags, v, t))
    return subs


def main():
    for stem in ("miffy", "zichaoxiong"):
        subs = read_subs(os.path.join(ASSETS, stem + ".psmesh"))
        solid = [s for s in subs if not (s[0] & 1)]
        v = np.concatenate([s[1] for s in solid])
        lo, hi = v.min(axis=0), v.max(axis=0)
        height = hi[1] - lo[1]
        print(f"===== {stem} =====  height {height:.4f}")

        # a small band around a height; the extremes over the band, not a single slice
        band = height * 0.012

        def left_edge(y):
            b = v[np.abs(v[:, 1] - y) <= band]
            return b[:, 0].min() if len(b) else np.nan

        def right_edge(y):
            b = np.abs(v[:, 1] - y) <= band
            return v[b][:, 0].max() if b.any() else np.nan

        print("  dy      yL      yR      L(yL)    R(yR)   width   err")
        best = None
        for dy in np.arange(-0.10, 0.46, 0.002):
            yL = ANCHOR_L[1] - dy
            yR = ANCHOR_R[1] - dy
            if yL < lo[1] or yR > hi[1]:
                continue
            l = left_edge(yL)
            r = right_edge(yR)
            if np.isnan(l) or np.isnan(r):
                continue
            width = r - l
            err = abs(width - (ANCHOR_R[0] - ANCHOR_L[0]))
            if best is None or err < best[0]:
                best = (err, dy, yL, yR, l, r, width)
        err, dy, yL, yR, l, r, width = best
        dx = ANCHOR_L[0] - l
        print(f"  BEST dy={dy:+.4f}  yL={yL:+.4f} (frac {(yL-lo[1])/height:.3f})  "
              f"yR={yR:+.4f} (frac {(yR-lo[1])/height:.3f})")
        print(f"       L={l:+.4f} R={r:+.4f} width={width:.4f} (want 0.5990, err {err:.4f})")
        print(f"       dx={dx:+.4f}  shift=({dx:+.4f},{dy:+.4f})")
        print(f"       -> grip fraction for the build: {(yL-lo[1])/height:.4f} "
              f"(model bottom lands at {lo[1]+dy:+.4f})")

        # Sanity: where does the hand end up vertically on the model, and how wide is
        # the model at the hand's own height?
        for name, a, y in (("L", ANCHOR_L, yL), ("R", ANCHOR_R, yR)):
            b = v[np.abs(v[:, 1] - y) <= band]
            print(f"       {name}: hand x={a[0]-dx:+.4f}  model x[{b[:,0].min():+.4f},"
                  f"{b[:,0].max():+.4f}]  gap from edge="
                  f"{a[0]-dx-b[:,0].min():+.4f}")


if __name__ == "__main__":
    main()
