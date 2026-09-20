"""Pick the grip height by how deep the hands sit in the model.

The two hand anchors are fixed in item-local space (from the vanilla prefab). The mod
chooses where the model sits relative to them. For a given vertical placement (dy) the
horizontal placement (dx) that centres the model between the hands is forced, and so is
how deep each hand sits inside the silhouette:

    insetL = xL - left_edge(yL)        insetR = right_edge(yR) - xR
    insetL - insetR = -(anchorL.x + anchorR.x) - (left + right)   (independent of dx)

so dx = (anchorL.x + anchorR.x - left - right) / 2 makes them equal. Maximising that
common inset puts the model where it is widest across the hand span — the firmest,
most natural grip the geometry allows. A negative inset means the hands are in the air.
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
        band = height * 0.010
        print(f"===== {stem} =====")

        def left(y):
            b = v[np.abs(v[:, 1] - y) <= band]
            return b[:, 0].min() if len(b) else np.nan

        def right(y):
            b = np.abs(v[:, 1] - y) <= band
            return v[b][:, 0].max() if b.any() else np.nan

        rows = []
        for dy in np.arange(-0.25, 0.62, 0.002):
            yL = ANCHOR_L[1] - dy
            yR = ANCHOR_R[1] - dy
            if yL < lo[1] + 0.005 or yR > hi[1] - 0.005:
                continue
            l = left(yL)
            r = right(yR)
            if np.isnan(l) or np.isnan(r):
                continue
            dx = (ANCHOR_L[0] + ANCHOR_R[0] - l - r) * 0.5
            inset = ANCHOR_R[0] - dx - r
            rows.append((inset, dy, dx, yL, yR, l, r))

        rows.sort(key=lambda x: -x[0])
        print("  best by inset:")
        for row in rows[:5]:
            inset, dy, dx, yL, yR, l, r = row
            print(f"    inset={inset:+.4f} dy={dy:+.4f} dx={dx:+.4f} "
                  f"yL={yL:+.3f}({(yL-lo[1])/height:.2f}) yR={yR:+.3f}({(yR-lo[1])/height:.2f})")

        inset, dy, dx, yL, yR, l, r = rows[0]
        print(f"  chosen: dy={dy:+.4f} dx={dx:+.4f} inset={inset:+.4f} "
              f"grip frac L={(yL-lo[1])/height:.3f} R={(yR-lo[1])/height:.3f}")

        # Also show the inset profile so the shape of the trade-off is visible.
        print("  inset vs dy (every 0.05):")
        for dy in np.arange(-0.20, 0.61, 0.05):
            yL = ANCHOR_L[1] - dy
            yR = ANCHOR_R[1] - dy
            if yL < lo[1] or yR > hi[1]:
                continue
            l = left(yL)
            r = right(yR)
            if np.isnan(l) or np.isnan(r):
                continue
            dxv = (ANCHOR_L[0] + ANCHOR_R[0] - l - r) * 0.5
            print(f"    dy={dy:+.2f} yL={(yL-lo[1])/height:.2f} inset={ANCHOR_R[0]-dxv-r:+.4f}")


if __name__ == "__main__":
    main()
