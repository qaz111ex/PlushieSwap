"""Research-only: prove the shader's "undo the baked offset" step is exact.

The outline shader does

    surfaceOS = positionOS - normalOS * _OutlineBakedThickness

If _OutlineBakedThickness equals the value the offline pipeline used
(outline_thickness * target_height), this must land back on the body surface,
otherwise the screen-space offset would be applied from the wrong place.

This checks that directly: for every shell vertex, the recovered position is
compared against the nearest real body vertex.

Also demonstrates the scale bug: the same object-space offset, at half the
object scale (backpack mode), is half the world length.

Writes research/outline_undo_check.txt
"""
import os
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from preview_mesh import read_psmesh  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\research"

# Must match tools/build_meshes.py convert(): outline_thickness * target_height
OUTLINE_THICKNESS = 0.0075
TARGET_HEIGHT = 0.9635
BAKED = OUTLINE_THICKNESS * TARGET_HEIGHT


def main():
    lines = [f"_OutlineBakedThickness = outline_thickness * target_height "
             f"= {OUTLINE_THICKNESS} * {TARGET_HEIGHT} = {BAKED!r}", ""]

    for stem in ("miffy", "zichaoxiong"):
        name, subs, lo, hi = read_psmesh(os.path.join(ASSETS, stem + ".psmesh"))
        body, sv, sn = [], [], []
        for e in subs:
            flags = e[5] if len(e) > 5 else 0
            if flags & 1:
                sv.append(e[1])
                sn.append(e[2])
            else:
                body.append(e[1])
        body = np.concatenate(body).astype(np.float64)
        sv = np.concatenate(sv).astype(np.float64)
        sn = np.concatenate(sn).astype(np.float64)

        tree = cKDTree(body)
        recovered = sv - sn * BAKED
        d_rec = tree.query(recovered, k=1, workers=-1)[0]
        d_raw = tree.query(sv, k=1, workers=-1)[0]

        lines.append(f"==== {stem} ====")
        lines.append(f"  shell vertices                : {len(sv)}")
        lines.append(f"  raw shell -> nearest body     : mean {d_raw.mean():.6f} "
                     f"p95 {np.percentile(d_raw, 95):.6f} max {d_raw.max():.6f}")
        lines.append(f"  shell - normal*BAKED -> body  : mean {d_rec.mean():.6f} "
                     f"p95 {np.percentile(d_rec, 95):.6f} max {d_rec.max():.6f}")
        lines.append(f"  => undo is {'EXACT' if d_rec.max() < 1e-6 else 'NOT exact'}")

        # Scale behaviour. The game multiplies the item by WorldScale (default 1)
        # and applies another 0.5 in backpack mode (Item.forceScale). A baked
        # object-space offset is multiplied by that too; the shader's pixel
        # offset is scale-independent.
        lines.append(f"  object-space line at localScale 1.0 : "
                     f"{BAKED:.6f} world units")
        lines.append(f"  object-space line at localScale 0.5 : "
                     f"{BAKED * 0.5:.6f} world units  <- the backpack halving")
        lines.append("  screen-space shader line            : constant, independent of scale")
        lines.append("")

    text = "\n".join(lines)
    with open(os.path.join(OUT, "outline_undo_check.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
