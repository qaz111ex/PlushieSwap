"""Render the grips that are actually stored in the .psmesh right now.

Shows where the player's hands will really appear (circle) and where the anchor that
produces it sits (cross), so the current build can be judged without launching the game.
"""
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_merge as vm  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\tools\preview"

HAND_OFFSET_L = np.array([0.00289, -0.15393, -0.00508])
HAND_OFFSET_R = np.array([-0.00289, -0.15394, -0.00508])


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


def read_grips(path):
    with open(path, "rb") as fh:
        fh.read(8)
        n = struct.unpack("<i", fh.read(4))[0]
        fh.read(n)
        count = struct.unpack("<i", fh.read(4))[0]
        for _ in range(count):
            fh.read(16 + 4)
            vc, ic = struct.unpack("<ii", fh.read(8))
            fh.read(vc * 12 + vc * 12 + vc * 8 + vc * 12 + ic * 4)
        fh.read(24)
        assert struct.unpack("<i", fh.read(4))[0] == 1
        left = np.array(struct.unpack("<3f", fh.read(12)))
        right = np.array(struct.unpack("<3f", fh.read(12)))
        left_rot = np.array(struct.unpack("<4f", fh.read(16)))
        right_rot = np.array(struct.unpack("<4f", fh.read(16)))
    return left, right, left_rot, right_rot


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


def main():
    for stem in ("miffy", "zichaoxiong"):
        path = os.path.join(ASSETS, stem + ".psmesh")
        name, subs, lo, hi = vm.read_psmesh(path)
        texture = vm.load_shading_texture(path)
        merged = vm.merge_like_plugin(path)
        left, right, lrot, rrot = read_grips(path)

        # The player's hand is a skinned mesh driven by the hand bone, so it renders at
        # the bone: the anchor IS the hand. Nothing is added to it.
        hand_l = left
        hand_r = right
        height = float(hi[1] - lo[1])
        fl = (hand_l[1] - lo[1]) / height
        fr = (hand_r[1] - lo[1]) / height

        size = 900
        vm.render(merged, texture, os.path.join(OUT, "_tmp.png"), size=size,
                  outline=vm.outline_mesh(path))
        img = Image.open(os.path.join(OUT, "_tmp.png")).convert("RGB")
        draw = ImageDraw.Draw(img)
        for hand, anchor in ((hand_l, left), (hand_r, right)):
            hx, hy = project(hand[None, :], lo, hi, size)[0]
            ax, ay = project(anchor[None, :], lo, hi, size)[0]
            draw.line([ax, ay, hx, hy], fill=(255, 140, 0), width=4)
            r = 22
            draw.ellipse([hx - r, hy - r, hx + r, hy + r], outline=(255, 0, 0), width=5)
            draw.line([ax - 14, ay, ax + 14, ay], fill=(255, 140, 0), width=4)
            draw.line([ax, ay - 14, ax, ay + 14], fill=(255, 140, 0), width=4)

        draw.text((12, 12), f"{stem}: hand at height fraction "
                            f"L {fl:.3f} / R {fr:.3f}", fill=(255, 60, 60))
        img.save(os.path.join(OUT, stem + "_current_grip.png"))
        print(f"{stem}: anchorL={np.round(left, 4)} anchorR={np.round(right, 4)}")
        print(f"        handL={np.round(hand_l, 4)} (frac {fl:.3f})")
        print(f"        handR={np.round(hand_r, 4)} (frac {fr:.3f})")


if __name__ == "__main__":
    main()
