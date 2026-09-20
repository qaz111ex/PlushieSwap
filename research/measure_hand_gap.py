"""Measure the gap between the game's hand anchors and the plush's surface.

The game holds an item by snapping the hand rigs to the item's Hand_L / Hand_R
children. Those are at fixed item-local positions (read from the vanilla prefab):
they do not move. The mod shifts the MODEL so its waist meets them. If the model is
narrower than the distance between the hands, both hands end up in mid-air — which is
exactly what "holding air" looks like.

This computes, for a candidate grip height, where the model ends up and how far each
hand is from the model's surface at the hand's own height. Positive = air gap,
negative = hand is inside the surface (which reads as a firm grip).
"""
import os
import struct
import sys

import numpy as np

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")

# The vanilla anchors, read from "BingBong_Prop Variant".
ANCHOR_L = np.array([-0.3590, -0.1770, -0.0400])
ANCHOR_R = np.array([+0.2400, -0.1040, -0.0400])
ANCHOR_MID = (ANCHOR_L + ANCHOR_R) * 0.5


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
        print(f"===== {stem} =====  height {height:.4f}  X[{lo[0]:+.3f},{hi[0]:+.3f}]")

        # hand Y in model space once the model is shifted so that the grip height
        # coincides with the anchor midpoint
        print("  frac  gripMidX  shift     handL.x  surfL.x  gapL   handR.x  surfR.x  gapR")
        for k in range(10, 61, 2):
            frac = k / 100.0
            y_grip = lo[1] + frac * height
            band = v[np.abs(v[:, 1] - y_grip) < height * 0.02]
            if len(band) == 0:
                continue
            surf_lo = band[:, 0].min()
            surf_hi = band[:, 0].max()
            grip_mid_x = (surf_lo + surf_hi) * 0.5
            shift_x = ANCHOR_MID[0] - grip_mid_x
            shift_y = ANCHOR_MID[1] - y_grip
            # where the hand is relative to the (shifted) model
            hand_l = ANCHOR_L - np.array([shift_x, shift_y, 0.0])
            hand_r = ANCHOR_R - np.array([shift_x, shift_y, 0.0])
            # model surface at each hand's own height
            bl = v[np.abs(v[:, 1] - hand_l[1]) < height * 0.02]
            br = v[np.abs(v[:, 1] - hand_r[1]) < height * 0.02]
            sl = bl[:, 0].min() if len(bl) else np.nan
            sr = br[:, 0].max() if len(br) else np.nan
            gap_l = hand_l[0] - sl
            gap_r = sr - hand_r[0]
            print(f"  {frac:.2f}  {grip_mid_x:+.4f}  {shift_x:+.4f}  {hand_l[0]:+.4f}  {sl:+.4f}  "
                  f"{gap_l:+.4f}  {hand_r[0]:+.4f}  {sr:+.4f}  {gap_r:+.4f}")


if __name__ == "__main__":
    main()
