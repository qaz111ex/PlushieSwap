"""Profile each model's silhouette by height so the grip point can be placed anatomically.

Prints, for each 5% height band, the horizontal radius — the narrow bands are the
neck and waist, which is where a hand naturally holds a doll.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preview_mesh import read_psmesh  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"


def profile(path):
    name, subs, lo, hi = read_psmesh(path)
    verts = np.concatenate([s[1] for s in subs], axis=0)
    h = float(hi[1] - lo[1])
    print("=" * 76)
    print(f"{name}: height {h:.4f}, Y [{lo[1]:+.4f}, {hi[1]:+.4f}]")
    print(f"{'band':>6} {'Y':>9} {'radius':>8}  silhouette")
    print("-" * 76)

    # The player's hands sit at y = -0.14 in item space (Hand_L / Hand_R).
    grip_y = -0.140

    for i in range(20):
        f0, f1 = i / 20.0, (i + 1) / 20.0
        y0 = lo[1] + f0 * h
        y1 = lo[1] + f1 * h
        sel = (verts[:, 1] >= y0) & (verts[:, 1] < y1)
        if not sel.any():
            continue
        band = verts[sel]
        cx = band[:, 0].mean()
        cz = band[:, 2].mean()
        r = np.sqrt((band[:, 0] - cx) ** 2 + (band[:, 2] - cz) ** 2)
        radius = float(np.percentile(r, 90))
        frac = (y0 + y1) * 0.5
        frac_norm = (frac - lo[1]) / h
        marker = "  <== grip" if y0 <= grip_y < y1 else ""
        bar = "#" * int(radius * 40)
        print(f"{f0*100:5.0f}% {frac:+9.4f} {radius:8.4f}  {bar}{marker}")


if __name__ == "__main__":
    for stem in ("miffy", "zichaoxiong"):
        profile(os.path.join(ASSETS, stem + ".psmesh"))
    print()
    print("current models are baked with bottom_y = -0.7345 (vanilla exact);")
    print("the plugin lifts them while held by Hold Height Offset.")
