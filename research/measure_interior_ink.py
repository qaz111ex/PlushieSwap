"""Measure how much ink each direction-field variant draws INSIDE the body.

Uses only an existing image library (Pillow) and an existing morphology routine
(scipy.ndimage). No hand-written judgement: the metric is simply "dark pixels that are
well inside the silhouette in the with-ink render and absent in the body-only render".

Lower is better. A continuous line that follows the model should have near-zero
interior ink, while still keeping the outer silhouette inked.
"""
import os

import numpy as np
from PIL import Image
from scipy import ndimage

OUT = r"D:\zhuanban\Plushie Swap\research\preview"
MODES = ("normal", "smooth", "radial", "pushout")


def ink_stats(stem, mode, erode=10, dark=110):
    base = np.asarray(Image.open(os.path.join(OUT, f"cmp_{stem}_without.png")).convert("L"),
                      np.float32)
    test = np.asarray(Image.open(os.path.join(OUT, f"cmp_{stem}_{mode}.png")).convert("L"),
                      np.float32)
    body = base > 120                       # the silhouette of the body-only render
    inner = ndimage.binary_erosion(body, iterations=erode)   # away from the edge
    outer_ring = body & ~ndimage.binary_erosion(body, iterations=erode)

    ink_test = test < dark
    ink_base = base < dark
    interior = (ink_test & inner) & ~ink_base           # ink added inside the body
    ring = (ink_test & outer_ring)                       # ink on the silhouette

    return int(interior.sum()), int(ring.sum()), int(ink_test.sum())


def main():
    print(f"{'stem':12s} {'mode':9s} {'interior_ink':>13s} {'ring_ink':>10s} {'total_ink':>10s}")
    print("-" * 60)
    for stem in ("miffy", "zichaoxiong"):
        for mode in MODES:
            i, r, t = ink_stats(stem, mode)
            print(f"{stem:12s} {mode:9s} {i:>13d} {r:>10d} {t:>10d}")
        print()


if __name__ == "__main__":
    main()
