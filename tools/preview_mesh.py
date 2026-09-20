"""Render previews of a .psmesh file (flat-shaded rasteriser, reads stored normals)."""
import os
import struct
import sys

import numpy as np
from PIL import Image


def read_psmesh(path):
    with open(path, "rb") as fh:
        magic = fh.read(8)
        assert magic in (b"PSMESH01", b"PSMESH02", b"PSMESH03"), magic
        n = struct.unpack("<i", fh.read(4))[0]
        name = fh.read(n).decode("utf-8")
        count = struct.unpack("<i", fh.read(4))[0]
        subs = []
        for _ in range(count):
            colour = np.array(struct.unpack("<4f", fh.read(16)))
            flags = struct.unpack("<i", fh.read(4))[0] if magic != b"PSMESH01" else 0
            v_count, i_count = struct.unpack("<ii", fh.read(8))
            verts = np.frombuffer(fh.read(v_count * 12), dtype="<f4").reshape(-1, 3)
            normals = np.frombuffer(fh.read(v_count * 12), dtype="<f4").reshape(-1, 3)
            uvs = np.frombuffer(fh.read(v_count * 8), dtype="<f4").reshape(-1, 2)
            fh.read(v_count * 12)
            idx = np.frombuffer(fh.read(i_count * 4), dtype="<i4").reshape(-1, 3)
            subs.append((colour, verts, normals, uvs, idx, flags))
        lo = np.array(struct.unpack("<3f", fh.read(12)))
        hi = np.array(struct.unpack("<3f", fh.read(12)))
    return name, subs, lo, hi


def load_shading_texture(psmesh_path):
    """Load the baked colour+AO palette that sits next to the .psmesh."""
    from PIL import Image
    tex = os.path.splitext(psmesh_path)[0] + "_shading.png"
    if not os.path.exists(tex):
        return None
    return np.asarray(Image.open(tex).convert("RGBA"), dtype=np.float32) / 255.0


def sample_shading(texture, uv):
    """Nearest/bilinear sample of the 1-pixel-tall palette."""
    if texture is None:
        return None
    height, width = texture.shape[0], texture.shape[1]
    x = np.clip(uv[:, 0], 0.0, 1.0) * width - 0.5
    x0 = np.floor(x).astype(np.int64)
    frac = (x - x0)[:, None]
    x0 = np.clip(x0, 0, width - 1)
    x1 = np.clip(x0 + 1, 0, width - 1)
    row = np.clip(texture[0], 0.0, 1.0)
    rgba = row[x0] * (1.0 - frac) + row[x1] * frac
    return rgba[:, :3]


def render(path, prefix, size=768, bg=0.10):
    name, subs, lo, hi = read_psmesh(path)
    texture = load_shading_texture(path)
    centre = (lo + hi) * 0.5
    extent = float(max(hi - lo)) * 0.60

    lights = [np.array([0.5, 0.8, 0.6]), np.array([-0.6, 0.3, 0.4]), np.array([0.0, -0.4, -0.8])]
    lights = [v / np.linalg.norm(v) for v in lights]

    views = {
        "front": (np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0])),
        "back": (np.array([0.0, 0.0, -1.0]), np.array([0.0, 1.0, 0.0])),
        "side": (np.array([-1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])),
        "three_quarter": (np.array([0.72, 0.05, 0.69]), np.array([0.0, 1.0, 0.0])),
    }

    for view_name, (fwd, up_in) in views.items():
        fwd = fwd / np.linalg.norm(fwd)
        right = np.cross(up_in, fwd)
        right /= np.linalg.norm(right)
        up = np.cross(fwd, right)

        zbuf = np.full((size, size), -1e30, dtype=np.float32)
        img = np.full((size, size, 3), bg, dtype=np.float32)

        for entry in subs:
            colour, verts, normals, uvs, idx = entry[0], entry[1], entry[2], entry[3], entry[4]
            flags = entry[5] if len(entry) > 5 else 0
            if flags & 1:
                continue  # inverted-hull outline, drawn separately by the game
            baked = sample_shading(texture, uvs)
            base = baked if baked is not None else np.tile(colour[:3], (len(verts), 1))
            v = verts - centre
            x, y, z = v @ right, v @ up, v @ fwd
            px = ((x / extent) * 0.5 + 0.5) * (size - 1)
            py = (1.0 - ((y / extent) * 0.5 + 0.5)) * (size - 1)

            shade = np.full(len(v), 0.22, dtype=np.float32)
            if texture is None:
                for L in lights:
                    # two-sided lighting so backfaces stay readable
                    shade += 0.32 * np.abs(normals @ L)
            else:
                # the shading is already baked into the albedo; keep the view flat so the
                # bake can be judged on its own
                shade[:] = 1.0

            tri = idx
            x0, y0, z0 = px[tri[:, 0]], py[tri[:, 0]], z[tri[:, 0]]
            x1, y1, z1 = px[tri[:, 1]], py[tri[:, 1]], z[tri[:, 1]]
            x2, y2, z2 = px[tri[:, 2]], py[tri[:, 2]], z[tri[:, 2]]
            s0, s1, s2 = shade[tri[:, 0]], shade[tri[:, 1]], shade[tri[:, 2]]

            for k in range(len(tri)):
                i0, i1, i2 = tri[k]
                ax, ay, az = x0[k], y0[k], z0[k]
                bx, by, bz = x1[k], y1[k], z1[k]
                cx, cy, cz = x2[k], y2[k], z2[k]
                minx = max(int(min(ax, bx, cx)), 0)
                maxx = min(int(max(ax, bx, cx)) + 1, size - 1)
                miny = max(int(min(ay, by, cy)), 0)
                maxy = min(int(max(ay, by, cy)) + 1, size - 1)
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
                write = mask & (depth > region_z)
                if not write.any():
                    continue
                s = l0 * s0[k] + l1 * s1[k] + l2 * s2[k]
                albedo = (l0[..., None] * base[i0]
                          + l1[..., None] * base[i1]
                          + l2[..., None] * base[i2])
                col = np.clip(albedo * s[..., None], 0, 1)
                region = img[miny:maxy + 1, minx:maxx + 1]
                region[write] = col[write]
                region_z[write] = depth[write]

        out = (np.clip(img, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
        Image.fromarray(out).save(f"{prefix}_{view_name}.png")
        print("wrote", f"{prefix}_{view_name}.png")


if __name__ == "__main__":
    asset_dir = r"D:\zhuanban\Plushie Swap\assets"
    out_dir = r"D:\zhuanban\Plushie Swap\tools\preview"
    os.makedirs(out_dir, exist_ok=True)
    for stem in ("miffy", "zichaoxiong"):
        render(os.path.join(asset_dir, stem + ".psmesh"), os.path.join(out_dir, stem), size=420)
