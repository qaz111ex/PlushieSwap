"""Render each plush with the ACTUAL hand position marked, at several heights.

The grip anchor published by the .psmesh is not where the hand appears: the game puts
the player's hand RIG on the anchor and the hand mesh hangs off that rig, so the visible
hand sits at

    hand = anchor + anchor_rotation * hand_offset_in_anchor_space

The offset is measured from the game's own Chubby Hand mesh (solve_grips.py). Marking
the anchor alone is therefore misleading, which is exactly what made the earlier grip
choices look right on paper and wrong in game. Both are drawn here: the circle is the
hand (what the player sees) and the cross is the anchor that produces it.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_merge as vm  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\tools\preview"

# hand mesh centre in each anchor's local space, from solve_grips.py
HAND_OFFSET_L = np.array([0.00289, -0.15393, -0.00508])
HAND_OFFSET_R = np.array([-0.00289, -0.15394, -0.00508])
ROT_L = (-0.31818, 0.67636, 0.51899, -0.41466)
ROT_R = (0.25786, 0.71867, 0.55145, 0.33605)

CANDIDATES = [0.06, 0.12, 0.18, 0.24, 0.30, 0.36, 0.42, 0.48, 0.54, 0.60]


def quat_mat(q):
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    if n < 1e-12:
        return np.eye(3)
    s = 2.0 / n
    return np.array([
        [1 - s * (y * y + z * z), s * (x * y - w * z), s * (x * z + w * y)],
        [s * (x * y + w * z), 1 - s * (x * x + z * z), s * (y * z - w * x)],
        [s * (x * z - w * y), s * (y * z + w * x), 1 - s * (x * x + y * y)],
    ])


def project(points, lo, hi, size):
    centre = (lo + hi) * 0.5
    extent = float(max(hi - lo)) * 0.62
    fwd = np.array([0.0, 0.0, -1.0])
    up_in = np.array([0.0, 1.0, 0.0])
    right = np.cross(up_in, fwd)
    right /= np.linalg.norm(right)
    up = np.cross(fwd, right)
    v = points - centre
    px = ((v @ right / extent) * 0.5 + 0.5) * (size - 1)
    py = (1.0 - ((v @ up / extent) * 0.5 + 0.5)) * (size - 1)
    return np.column_stack([px, py])


def waist_anchor(subs, lo, hi, fraction, inset):
    """The anchor that puts the visible hand centre at `fraction` of the height."""
    height = float(hi[1] - lo[1])
    y = lo[1] + height * fraction
    band = height * 0.10
    xs, zs = [], []
    for s in subs:
        if s[5] & 1:
            continue
        v = s[1]
        sel = (v[:, 1] >= y - band) & (v[:, 1] <= y + band)
        if sel.any():
            xs.append(v[sel, 0])
            zs.append(v[sel, 2])
    xs = np.concatenate(xs)
    zs = np.concatenate(zs)
    z = float((zs.min() + zs.max()) * 0.5)
    left, right = float(xs.min()), float(xs.max())
    width = right - left

    hand_l = np.array([left + width * inset, y, z])
    hand_r = np.array([right - width * inset, y, z])
    anchor_l = hand_l - quat_mat(ROT_L) @ HAND_OFFSET_L
    anchor_r = hand_r - quat_mat(ROT_R) @ HAND_OFFSET_R
    return hand_l, hand_r, anchor_l, anchor_r


def main():
    for stem in ("miffy", "zichaoxiong"):
        path = os.path.join(ASSETS, stem + ".psmesh")
        name, subs, lo, hi = vm.read_psmesh(path)
        texture = vm.load_shading_texture(path)
        merged = vm.merge_like_plugin(path)

        size = 560
        tiles = []
        for frac in CANDIDATES:
            vm.render(merged, texture, os.path.join(OUT, "_tmp.png"), size=size,
                      outline=vm.outline_mesh(path))
            img = Image.open(os.path.join(OUT, "_tmp.png")).convert("RGB")
            draw = ImageDraw.Draw(img)
            hand_l, hand_r, anchor_l, anchor_r = waist_anchor(subs, lo, hi, frac, 0.20)

            for hand, anchor in ((hand_l, anchor_l), (hand_r, anchor_r)):
                hx, hy = project(hand[None, :], lo, hi, size)[0]
                ax, ay = project(anchor[None, :], lo, hi, size)[0]
                draw.line([ax, ay, hx, hy], fill=(255, 140, 0), width=3)
                r = 16
                draw.ellipse([hx - r, hy - r, hx + r, hy + r],
                             outline=(255, 0, 0), width=4)
                draw.line([ax - 10, ay, ax + 10, ay], fill=(255, 140, 0), width=3)
                draw.line([ax, ay - 10, ax, ay + 10], fill=(255, 140, 0), width=3)

            draw.text((10, 10), f"hand at height fraction {frac:.2f}",
                      fill=(255, 60, 60))
            tiles.append(img)

        cols = 5
        rows = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGB", (size * cols, size * rows), (40, 40, 40))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % cols) * size, (i // cols) * size))
        sheet.save(os.path.join(OUT, stem + "_hands.png"))
        print("wrote", stem + "_hands.png")


if __name__ == "__main__":
    main()
