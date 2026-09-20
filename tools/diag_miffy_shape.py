"""Profile Miffy's silhouette and the current wobble mask.

The user reports the wobble is far too weak: moving the plush only gives the ears
and paws a slight sway. This prints, for every height band, the X/Y extents and the
mean wobble weight, and then breaks the loose vertices into their connected parts
so it is clear which anatomy the mask actually covers.
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preview_mesh import read_psmesh  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"


def read_wobble(path):
    with open(path, "rb") as fh:
        magic = fh.read(8)
        n = struct.unpack("<i", fh.read(4))[0]
        fh.read(n)
        count = struct.unpack("<i", fh.read(4))[0]
        for _ in range(count):
            fh.read(16)
            fh.read(4)
            v_count, i_count = struct.unpack("<ii", fh.read(8))
            fh.read(v_count * 12 + v_count * 12 + v_count * 8 + v_count * 12 + i_count * 4)
        fh.read(24)
        has_grips = struct.unpack("<i", fh.read(4))[0]
        if has_grips:
            fh.read(24 + 32)  # two positions + two rotations
        wobble_count = struct.unpack("<i", fh.read(4))[0]
        raw = np.frombuffer(fh.read(wobble_count), dtype=np.uint8)
    return raw.astype(np.float64) / 255.0


def components(tris, count):
    parent = np.arange(count)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, c in tris:
        for u, v in ((a, b), (a, c)):
            ru, rv = find(u), find(v)
            if ru != rv:
                parent[rv] = ru
    return np.array([find(i) for i in range(count)])


def main():
    for stem in ("miffy", "zichaoxiong"):
        path = os.path.join(ASSETS, stem + ".psmesh")
        name, subs, lo, hi = read_psmesh(path)
        wobble = read_wobble(path)

        solid = [s for s in subs if not (s[5] & 1)]
        verts = np.concatenate([s[1] for s in solid], axis=0)
        tris = []
        offset = 0
        for s in solid:
            tris.append(s[4] + offset)
            offset += len(s[1])
        tris = np.concatenate(tris, axis=0)

        h = float(hi[1] - lo[1])
        print("=" * 90)
        print(f"{stem}: {len(verts)} solid verts, wobble array {len(wobble)}, "
              f"Y [{lo[1]:+.4f}, {hi[1]:+.4f}]  height {h:.4f}")
        print(f"{'band':>6} {'Y':>9} {'Xmin':>8} {'Xmax':>8} {'Zmin':>8} {'Zmax':>8} "
              f"{'wmean':>6} {'wmax':>6} {'loose':>6}")
        print("-" * 90)
        for i in range(20):
            y0 = lo[1] + (i / 20.0) * h
            y1 = lo[1] + ((i + 1) / 20.0) * h
            sel = (verts[:, 1] >= y0) & (verts[:, 1] < y1)
            if not sel.any():
                continue
            b = verts[sel]
            w = wobble[sel]
            print(f"{i*5:5.0f}% {(y0+y1)*0.5:+9.4f} {b[:,0].min():+8.3f} {b[:,0].max():+8.3f} "
                  f"{b[:,2].min():+8.3f} {b[:,2].max():+8.3f} "
                  f"{w.mean():6.3f} {w.max():6.3f} {int((w > 0.05).sum()):6d}")

        roots = components(tris, len(verts))
        print()
        print("loose parts (wobble > 0.05):")
        loose = wobble > 0.05
        for root in np.unique(roots[loose]):
            sel = (roots == root) & loose
            if sel.sum() < 12:
                continue
            b = verts[sel]
            print(f"  root {root:6d}  verts {int(sel.sum()):6d}  "
                  f"X[{b[:,0].min():+.3f},{b[:,0].max():+.3f}] "
                  f"Y[{b[:,1].min():+.3f},{b[:,1].max():+.3f}] "
                  f"Z[{b[:,2].min():+.3f},{b[:,2].max():+.3f}]  "
                  f"wmax {wobble[sel].max():.3f}")
        print()


if __name__ == "__main__":
    main()
