"""Find each plush's waist: the narrowest point of the torso.

"Hold it by the waist" means the hands go where the body pinches in, so the natural
place to grab a doll. This measures the horizontal half-width band by band and reports
the local minimum, which is the waist, plus the surrounding profile so the answer can be
sanity-checked against the model's anatomy.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preview_mesh import read_psmesh  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"

# the hand mesh centre sits this far from the grip anchor, in anchor space
# (measured by solve_grips.py from the game's own Chubby Hand mesh)
HAND_OFFSET_Y = -0.0446
HAND_OFFSET_Z = -0.1474


def main():
    for stem in ("miffy", "zichaoxiong"):
        _name, subs, lo, hi = read_psmesh(os.path.join(ASSETS, stem + ".psmesh"))
        verts = np.concatenate([s[1] for s in subs if not (s[5] & 1)], axis=0)
        height = float(hi[1] - lo[1])
        print("=" * 78)
        print(f"{stem}: Y [{lo[1]:+.4f}, {hi[1]:+.4f}] height {height:.4f}")
        print(f"{'frac':>6} {'Y':>9} {'halfwidth':>10}  profile")
        print("-" * 78)

        profile = []
        for i in range(40):
            y0 = lo[1] + (i / 40.0) * height
            y1 = lo[1] + ((i + 1) / 40.0) * height
            sel = (verts[:, 1] >= y0) & (verts[:, 1] < y1)
            if not sel.any():
                continue
            band = verts[sel]
            half = float((band[:, 0].max() - band[:, 0].min()) * 0.5)
            profile.append(((y0 + y1) * 0.5, half))
            frac = (y0 + y1) * 0.5
            frac_n = (frac - lo[1]) / height
            bar = "#" * int(half * 60)
            print(f"{frac_n:6.3f} {frac:+9.4f} {half:10.4f}  {bar}")

        # the waist is the narrowest band in the middle of the model, away from the
        # head (top) and the feet (bottom)
        mid = [(y, h) for y, h in profile
               if lo[1] + height * 0.20 <= y <= lo[1] + height * 0.65]
        if mid:
            wy, wh = min(mid, key=lambda t: t[1])
            frac = (wy - lo[1]) / height
            print(f"  -> waist at fraction {frac:.3f} (Y {wy:+.4f}, half-width {wh:.4f})")
            hand_y = wy + HAND_OFFSET_Y
            print(f"     hand centre would sit at Y {hand_y:+.4f} "
                  f"(fraction {(hand_y - lo[1]) / height:.3f})")
        print()


if __name__ == "__main__":
    main()
