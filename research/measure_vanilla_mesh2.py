"""Decode the vanilla BingBong mesh with UnityPy's mesh helper.

The vanilla hand anchors sit at 58% and 65% of the vanilla plush's height. If the
vanilla plush is about as wide there as the anchors are apart (0.60), then the game
holds the vanilla plush by its outstretched arms, and a replacement should be gripped
at whatever height *it* is that wide. That is the check this makes.
"""
import os

import numpy as np
import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"

ANCHOR_L = np.array([-0.3590, -0.1770, -0.0400])
ANCHOR_R = np.array([+0.2400, -0.1040, -0.0400])


def main():
    env = UnityPy.load(os.path.join(GAME, "resources.assets"))
    for o in env.objects:
        if o.type.name != "Mesh":
            continue
        d = o.read()
        if d.m_Name != "BingBong":
            continue
        h = MeshHandler(d)
        h.process()
        verts, indices = h.m_Vertices, h.m_IndexBuffer
        v = np.asarray(verts, dtype=np.float64)[:, :3]
        print(f"mesh {d.m_Name}: {len(v)} verts, {len(indices)} indices")
        lo, hi = v.min(axis=0), v.max(axis=0)
        print(f"  bounds X[{lo[0]:+.4f},{hi[0]:+.4f}] Y[{lo[1]:+.4f},{hi[1]:+.4f}] "
              f"Z[{lo[2]:+.4f},{hi[2]:+.4f}]")
        print(f"  size {np.round(hi-lo,4)}")

        for name, a in (("Hand_L", ANCHOR_L), ("Hand_R", ANCHOR_R)):
            frac = (a[1] - lo[1]) / (hi[1] - lo[1])
            band = v[np.abs(v[:, 1] - a[1]) < (hi[1] - lo[1]) * 0.02]
            w = (band[:, 0].max() - band[:, 0].min()) if len(band) else float("nan")
            print(f"  {name}: y={a[1]:+.3f} frac={frac:.3f} width_at_height={w:.4f} "
                  f"x[{band[:,0].min():+.3f},{band[:,0].max():+.3f}]")
        print(f"  anchor separation = {np.linalg.norm(ANCHOR_L-ANCHOR_R):.4f}")

        n = 24
        print("  frac  y           x range                 width")
        for k in range(n):
            y0 = lo[1] + (hi[1] - lo[1]) * k / n
            y1 = lo[1] + (hi[1] - lo[1]) * (k + 1) / n
            band = v[(v[:, 1] >= y0) & (v[:, 1] < y1)]
            if len(band) == 0:
                continue
            print(f"  {k/n:.2f}  {y0:+.3f}  [{band[:,0].min():+.3f},{band[:,0].max():+.3f}]  "
                  f"{band[:,0].max()-band[:,0].min():.4f}")
        return
    print("not found")


if __name__ == "__main__":
    main()
