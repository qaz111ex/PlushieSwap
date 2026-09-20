"""Measure where the player's hands sit on each plush, from an in-game screenshot.

Guessing at the grip has failed repeatedly, so this reads the evidence instead: it finds
the hands (the player's teal gloves) and the plush's silhouette, and reports the height
of each hand as a fraction of the plush. That fraction can then be compared against what
the .psmesh was built with, which says definitively whether the published anchors are
being used or ignored.
"""
import os

import numpy as np
from PIL import Image

SHOTS = [
    (r"C:\Users\Administrator\Pictures\新建文件夹\20260917211143_1.jpg", "miffy"),
    (r"C:\Users\Administrator\Pictures\新建文件夹\20260917211139_1.jpg", "bear"),
]

for path, name in SHOTS:
    if not os.path.exists(path):
        print("missing", path)
        continue
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.int16)
    h, w, _ = a.shape
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    print("=" * 60)
    print(name, im.size)

    region = np.zeros((h, w), dtype=bool)
    region[120:min(h, 960), 420:min(w, 1500)] = True

    teal = (g > 100) & (b > 100) & (r < g - 40) & (r < b - 30) & (np.abs(g - b) < 70)
    teal &= region
    ys, xs = np.nonzero(teal)
    print("  teal pixels:", len(ys))
    hands = []
    if len(ys) > 100:
        mid = (xs.min() + xs.max()) // 2
        for side, sel in (("L", xs < mid), ("R", xs >= mid)):
            if sel.sum() > 100:
                hands.append((side, float(xs[sel].mean()), float(ys[sel].mean())))
                print(f"  hand {side}: centre=({xs[sel].mean():.0f},{ys[sel].mean():.0f}) "
                      f"x[{xs[sel].min()},{xs[sel].max()}] "
                      f"y[{ys[sel].min()},{ys[sel].max()}] n={int(sel.sum())}")

    bright = np.minimum(np.minimum(r, g), b) > 175
    blue = (b > 140) & (b > r + 40)
    plush = (bright | blue) & region
    ys2, xs2 = np.nonzero(plush)
    if len(ys2):
        top, bot = int(ys2.min()), int(ys2.max())
        print(f"  plush silhouette x[{xs2.min()},{xs2.max()}] "
              f"y[{top},{bot}] height={bot - top}")
        print("  row profile (bright px per 20 rows):")
        for y0 in range(120, min(h, 960), 20):
            n = int(plush[y0:y0 + 20].sum())
            if n:
                print(f"    y{y0:4d} {'#' * min(60, n // 200)} {n}")
        for side, cx, cy in hands:
            print(f"  -> hand {side} at height fraction "
                  f"{(bot - cy) / float(bot - top):.3f} of the plush")
