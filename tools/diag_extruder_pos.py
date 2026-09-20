"""Inspect where each extruder's faces sit in space, to validate colour assignment."""
import sys

import numpy as np

sys.path.insert(0, r"D:\zhuanban\Plushie Swap\tools")
from threemf import load_3mf  # noqa: E402

MODELS = r"C:\Users\Administrator\AppData\Local\Temp\opencode\models"


def report(stem):
    verts, tris, ext, rgb, palette = load_3mf(f"{MODELS}\\{stem}.3mf")
    # slicer space is Z-up: x right, y depth, z height
    print("=" * 78)
    print(stem, "palette:")
    for i, c in enumerate(palette):
        print(f"   filament {i + 1}: #{c[0]:02X}{c[1]:02X}{c[2]:02X}")
    print()
    for filament in sorted(set(ext.tolist())):
        sel = ext == filament
        pts = verts[tris[sel]].reshape(-1, 3)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        c = pts.mean(axis=0)
        col = palette[filament - 1]
        print(f"  filament {filament} (#{col[0]:02X}{col[1]:02X}{col[2]:02X}) faces={sel.sum()}")
        print(f"      bbox  x[{lo[0]:8.2f},{hi[0]:8.2f}] y[{lo[1]:8.2f},{hi[1]:8.2f}] z[{lo[2]:8.2f},{hi[2]:8.2f}]")
        print(f"      mean  ({c[0]:7.2f},{c[1]:7.2f},{c[2]:7.2f})")

        # cluster the selected faces by connected shells to see where they live
        sub = tris[sel]
        parent = {}

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for v in np.unique(sub):
            parent[int(v)] = int(v)
        for t in sub:
            ra, rb, rc = find(t[0]), find(t[1]), find(t[2])
            if rb != ra:
                parent[rb] = ra
            if rc != ra:
                parent[rc] = ra
        groups = {}
        for t in sub:
            groups.setdefault(find(t[0]), []).append(t)
        print(f"      shells: {len(groups)}")
        for root, faces in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:8]:
            fp = verts[np.array(faces)].reshape(-1, 3)
            c2 = fp.mean(axis=0)
            lo2, hi2 = fp.min(axis=0), fp.max(axis=0)
            print(f"         shell faces={len(faces):6d} centre=({c2[0]:8.2f},{c2[1]:8.2f},{c2[2]:8.2f})"
                  f" size=({hi2[0]-lo2[0]:6.2f},{hi2[1]-lo2[1]:6.2f},{hi2[2]-lo2[2]:6.2f})")


if __name__ == "__main__":
    for s in ("zichaoxiong", "miffy"):
        report(s)
