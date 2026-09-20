"""Render inventory icons from .psmesh, matching the game's BingBong icon look.

The game icon is 512x512, 3/4 view, thick black outline, plain white background.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageChops, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preview_mesh import read_psmesh, load_shading_texture, sample_shading  # noqa: E402

# Project root is the parent of tools/, so the script works from any drive or checkout.
ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def render_icon(path, out_path, size=512, margin=0.10, outline_px=8,
                yaw_deg=-28.0, pitch_deg=12.0):
    name, subs, lo, hi = read_psmesh(path)
    texture = load_shading_texture(path)

    # The .psmesh already carries an inverted-hull ink shell, but for a flat icon it is
    # cleaner to draw the outline as a 2D stroke around the silhouette, so the baked
    # shell is skipped here.
    body = []
    for entry in subs:
        colour, verts, normals, uvs, idx = entry[0], entry[1], entry[2], entry[3], entry[4]
        flags = entry[5] if len(entry) > 5 else 0
        if flags & 1:
            continue
        baked = sample_shading(texture, uvs)
        albedo = baked if baked is not None else np.tile(colour[:3], (len(verts), 1))
        body.append((albedo, verts, normals, idx))

    centre = (lo + hi) * 0.5

    yaw = np.radians(yaw_deg)
    pitch = np.radians(pitch_deg)
    fwd = np.array([np.sin(yaw) * np.cos(pitch), np.sin(pitch), np.cos(yaw) * np.cos(pitch)])
    fwd /= np.linalg.norm(fwd)
    right = np.cross(np.array([0.0, 1.0, 0.0]), fwd)
    right /= np.linalg.norm(right)
    up = np.cross(fwd, right)

    # The models face -Z (toward the player), so the icon camera sits on that side.
    fwd = -fwd
    right = np.cross(np.array([0.0, 1.0, 0.0]), fwd)
    right /= np.linalg.norm(right)
    up = np.cross(fwd, right)

    # project everything to find the tight extent, then scale to fit with margin
    all_pts = np.concatenate([b[1] - centre for b in body], axis=0)
    xs = all_pts @ right
    ys = all_pts @ up
    span = max(xs.max() - xs.min(), ys.max() - ys.min())
    scale = (size * (1.0 - 2 * margin)) / span

    ss = 3  # supersample
    big = size * ss
    zbuf = np.full((big, big), -1e30, dtype=np.float32)
    img = np.ones((big, big, 3), dtype=np.float32)
    covered = np.zeros((big, big), dtype=bool)

    cx = (xs.max() + xs.min()) * 0.5
    cy = (ys.max() + ys.min()) * 0.5

    for albedo, verts, normals, idx in body:
        v = verts - centre
        px = ((v @ right - cx) * scale) * ss + big * 0.5
        py = big * 0.5 - ((v @ up - cy) * scale) * ss
        pz = v @ fwd

        tri_depth = pz[idx].mean(axis=1)
        tri = idx[np.argsort(tri_depth)]

        for k in range(len(tri)):
            a, b, c = tri[k]
            ax, ay, az = px[a], py[a], pz[a]
            bx, by, bz = px[b], py[b], pz[b]
            cx2, cy2, cz2 = px[c], py[c], pz[c]
            minx = max(int(min(ax, bx, cx2)), 0)
            maxx = min(int(max(ax, bx, cx2)) + 1, big - 1)
            miny = max(int(min(ay, by, cy2)), 0)
            maxy = min(int(max(ay, by, cy2)) + 1, big - 1)
            if minx > maxx or miny > maxy:
                continue
            det = (by - cy2) * (ax - cx2) + (cx2 - bx) * (ay - cy2)
            if abs(det) < 1e-9:
                continue
            ys_g, xs_g = np.mgrid[miny:maxy + 1, minx:maxx + 1]
            l0 = ((by - cy2) * (xs_g - cx2) + (cx2 - bx) * (ys_g - cy2)) / det
            l1 = ((cy2 - ay) * (xs_g - cx2) + (ax - cx2) * (ys_g - cy2)) / det
            l2 = 1.0 - l0 - l1
            mask = (l0 >= -0.004) & (l1 >= -0.004) & (l2 >= -0.004)
            if not mask.any():
                continue
            depth = l0 * az + l1 * bz + l2 * cz2
            region_z = zbuf[miny:maxy + 1, minx:maxx + 1]
            write = mask & (depth > region_z + 1e-3)
            if not write.any():
                continue
            col = (l0[..., None] * albedo[a] + l1[..., None] * albedo[b] + l2[..., None] * albedo[c])
            region = img[miny:maxy + 1, minx:maxx + 1]
            region[write] = np.clip(col[write], 0, 1)
            region_z[write] = depth[write]
            covered[miny:maxy + 1, minx:maxx + 1][write] = True

    alpha = Image.fromarray((covered * 255).astype(np.uint8), mode="L")
    alpha = alpha.resize((size, size), Image.LANCZOS)

    image = Image.fromarray((np.clip(img, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8))
    image = image.resize((size, size), Image.LANCZOS)

    # Thick black outline like the game icon.
    #
    # The outline is where the icon's outer edge actually is, so the anti-aliasing has
    # to survive HERE. Thresholding the blurred mask to 0/255 (which an earlier version
    # did) throws the grey ramp away and leaves a hard, visibly jagged rim; the vanilla
    # icons have a soft rim. The blur is therefore kept as the outline's alpha, and the
    # coverage mask is unioned in so a body pixel can never be more transparent than the
    # body itself.
    mask = alpha.point(lambda v: 255 if v > 96 else 0)
    grow = outline_px * 2 + 1
    outline = mask.filter(ImageFilter.MaxFilter(grow if grow % 2 else grow + 1))
    outline = outline.filter(ImageFilter.GaussianBlur(outline_px * 0.22))
    outline = ImageChops.lighter(outline, alpha)

    # The game's own item icons are RGBA with a fully transparent background behind a
    # thick black outline, so the cut-out must match or a white box shows up in the UI.
    #
    # The two layers are composited by hand from their alpha masks instead of with
    # `Image.paste`. Pasting an RGB image onto an RGBA canvas through a soft mask makes
    # Pillow take a different conversion path that drops the mask's grey levels, which
    # flattened the LANCZOS anti-aliasing on every edge into hard 0/255 steps — the
    # icons came out visibly jagged next to the game's own.
    # Composite the black outline BEHIND the body, both with their soft alpha.
    #
    # `a_line` is a dilated superset of the body (the outline rings it and covers it), so
    # the body has to be laid OVER the line rather than multiplied by `1 - a_line`: the
    # line is the backdrop, not a hole cut out of the body.
    rgb = np.asarray(image, dtype=np.float32)
    a_main = np.asarray(alpha, dtype=np.float32)[..., None] / 255.0
    a_line = np.asarray(outline, dtype=np.float32)[..., None] / 255.0

    out_a = a_main + a_line * (1.0 - a_main)
    safe = np.maximum(out_a, 1e-6)
    # The line is pure black, so only the body contributes colour.
    out_rgb = rgb * a_main / safe

    canvas = Image.fromarray(
        np.dstack([out_rgb, out_a[..., 0] * 255.0]).clip(0, 255).astype(np.uint8),
        mode="RGBA")

    canvas.save(out_path)
    print("wrote", out_path)


if __name__ == "__main__":
    out_dir = os.path.join(ASSETS, "icons")
    os.makedirs(out_dir, exist_ok=True)
    render_icon(os.path.join(ASSETS, "miffy.psmesh"),
                os.path.join(out_dir, "icon_miffy.png"),
                yaw_deg=-30, pitch_deg=10)
    render_icon(os.path.join(ASSETS, "zichaoxiong.psmesh"),
                os.path.join(out_dir, "icon_zichaoxiong.png"),
                yaw_deg=-30, pitch_deg=10)
