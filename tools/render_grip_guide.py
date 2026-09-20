"""Render a front view with a labelled height ruler, to pick the grip fraction."""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preview_mesh import read_psmesh  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\tools\preview"


def render(path, out_path, size=760, hand_y=-0.140, lift=0.0):
    name, subs, lo, hi = read_psmesh(path)
    lo = lo.copy(); hi = hi.copy()
    lo[1] += lift; hi[1] += lift          # the plugin lifts the model while held
    subs = [(c, v + np.array([0.0, lift, 0.0]), n, u, i) for c, v, n, u, i in subs]
    centre = (lo + hi) * 0.5
    extent = float(max(hi - lo)) * 0.78

    fwd = np.array([0.0, 0.0, -1.0])   # camera in front of the model (-Z side = the face)
    up_in = np.array([0.0, 1.0, 0.0])
    right = np.cross(up_in, fwd)
    right /= np.linalg.norm(right)
    up = np.cross(fwd, right)

    lights = [np.array([0.30, 0.80, -0.52]), np.array([-0.55, 0.25, -0.6])]
    lights = [v / np.linalg.norm(v) for v in lights]

    ss = 2
    big = size * ss
    zbuf = np.full((big, big), -1e30, dtype=np.float32)
    img = np.full((big, big, 3), 0.12, dtype=np.float32)

    for colour, verts, normals, uvs, idx in subs:
        base = colour[:3]
        v = verts - centre
        px = (v @ right / extent * 0.5 + 0.5) * (big - 1)
        py = (1.0 - (v @ up / extent * 0.5 + 0.5)) * (big - 1)
        pz = v @ fwd

        shade = np.full(len(v), 0.30, dtype=np.float32)
        for L in lights:
            shade += 0.35 * np.clip(normals @ L, 0.0, 1.0)

        tri = idx[np.argsort(pz[idx].mean(axis=1))]
        for k in range(len(tri)):
            a, b, c = tri[k]
            ax, ay, az = px[a], py[a], pz[a]
            bx, by, bz = px[b], py[b], pz[b]
            cx, cy, cz = px[c], py[c], pz[c]
            minx = max(int(min(ax, bx, cx)), 0)
            maxx = min(int(max(ax, bx, cx)) + 1, big - 1)
            miny = max(int(min(ay, by, cy)), 0)
            maxy = min(int(max(ay, by, cy)) + 1, big - 1)
            if minx > maxx or miny > maxy:
                continue
            det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(det) < 1e-9:
                continue
            ys, xs = np.mgrid[miny:maxy + 1, minx:maxx + 1]
            l0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / det
            l1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / det
            l2 = 1.0 - l0 - l1
            mask = (l0 >= -0.004) & (l1 >= -0.004) & (l2 >= -0.004)
            if not mask.any():
                continue
            depth = l0 * az + l1 * bz + l2 * cz
            region_z = zbuf[miny:maxy + 1, minx:maxx + 1]
            write = depth > region_z
            if not write.any():
                continue
            s = l0 * shade[a] + l1 * shade[b] + l2 * shade[c]
            col = np.clip(base[None, None, :] * s[..., None], 0, 1)
            region = img[miny:maxy + 1, minx:maxx + 1]
            region[write] = col[write]
            region_z[write] = depth[write]

    out = (np.clip(img, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    image = Image.fromarray(out).resize((size, size), Image.LANCZOS)
    draw = ImageDraw.Draw(image)

    height = float(hi[1] - lo[1])

    def y_to_px(y):
        rel = y - centre[1]
        return (1.0 - (rel / extent * 0.5 + 0.5)) * (size - 1)

    for pct in range(0, 101, 10):
        y = lo[1] + pct / 100.0 * height
        py = y_to_px(y)
        if 0 <= py < size:
            draw.line([(0, py), (size, py)], fill=(70, 90, 120), width=1)
            draw.text((4, py + 1), f"{pct}%  y={y:+.3f}", fill=(150, 190, 240))

    # where the player's hand actually is while holding
    hp = y_to_px(hand_y)
    draw.line([(0, hp), (size, hp)], fill=(255, 90, 90), width=2)
    draw.text((4, hp - 12), f"HAND  y={hand_y:+.3f}", fill=(255, 120, 120))

    image.save(out_path)
    print("wrote", out_path, " height", round(height, 4),
          " grip fraction", round((hand_y - lo[1]) / height, 3))


if __name__ == "__main__":
    for stem, lift in (("miffy", 0.190), ("zichaoxiong", 0.325)):
        render(os.path.join(ASSETS, stem + ".psmesh"),
               os.path.join(OUT, stem + "_grip.png"), lift=lift)
