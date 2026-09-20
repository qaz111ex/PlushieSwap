"""Verify the screen-space outline the C# driver applies at runtime.

`PlushieOutline.cs` recovers the body surface from the baked shell and re-extrudes each
vertex in screen space. This reproduces that arithmetic exactly — same matrices, same
normal direction, same depth scaling — so the result can be judged offline before the
game is launched. It renders the same model at three camera distances and measures the
line width in pixels at each, which is the whole point of the change.

Writes research/preview/ss_check_*.png and prints the measured widths.
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

from preview_mesh import read_psmesh, load_shading_texture, sample_shading  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\research\preview"

BAKED = 0.0075 * 0.9635
WIDTH_PX = 2.5
RES = (900, 900)
FOVY = 50.0


def look_at(eye, target, up):
    fwd = target - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, up)
    right /= np.linalg.norm(right)
    camup = np.cross(right, fwd)
    view = np.eye(4)
    view[0, :3] = right
    view[1, :3] = camup
    view[2, :3] = -fwd
    view[:3, 3] = -view[:3, :3] @ eye
    return view


def cam_to_px(cam, w, h, fovy):
    """Camera space -> pixel coords. Camera looks down -z."""
    tan_half = np.tan(np.radians(fovy) * 0.5)
    safe_z = np.where(np.abs(cam[:, 2]) < 1e-6, -1e-6, cam[:, 2])
    ndc_x = (cam[:, 0] / (-safe_z)) / (tan_half * (w / h))
    ndc_y = (cam[:, 1] / (-safe_z)) / tan_half
    px = (ndc_x * 0.5 + 0.5) * (w - 1)
    py = (1.0 - (ndc_y * 0.5 + 0.5)) * (h - 1)
    return np.column_stack([px, py])


def project(points, centre, view, w, h, fovy):
    """Model space -> (pixel coords, camera-space points)."""
    p = np.concatenate([points - centre, np.ones((len(points), 1))], axis=1)
    cam = (view @ p.T).T
    return cam_to_px(cam, w, h, fovy), cam


def render(body_px, body_depth, body_t, body_c, shell_px, shell_depth, shell_t,
           out_path, size):
    zbuf = np.full((size, size), -1e30, dtype=np.float32)
    img = np.full((size, size, 3), 0.13, dtype=np.float32)

    def draw(verts_px, depth, colours, tris, cull_front):
        order = np.argsort(depth[tris].mean(axis=1))
        for k in order:
            i0, i1, i2 = tris[k]
            ax, ay = verts_px[i0]
            bx, by = verts_px[i1]
            cx, cy = verts_px[i2]
            minx = max(int(min(ax, bx, cx)), 0)
            maxx = min(int(max(ax, bx, cx)) + 1, size - 1)
            miny = max(int(min(ay, by, cy)), 0)
            maxy = min(int(max(ay, by, cy)) + 1, size - 1)
            if minx > maxx or miny > maxy:
                continue
            det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(det) < 1e-9:
                continue
            # Camera looks down -z, so a triangle facing the camera has a NEGATIVE
            # screen-space winding here. "Cull front" therefore drops det < 0.
            if cull_front and det <= 0:
                continue
            ys, xs = np.mgrid[miny:maxy + 1, minx:maxx + 1]
            l0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / det
            l1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / det
            l2 = 1.0 - l0 - l1
            mask = (l0 >= -0.004) & (l1 >= -0.004) & (l2 >= -0.004)
            if not mask.any():
                continue
            depth_tri = l0 * depth[i0] + l1 * depth[i1] + l2 * depth[i2]
            rz = zbuf[miny:maxy + 1, minx:maxx + 1]
            write = mask & (depth_tri > rz)
            if not write.any():
                continue
            col = (l0[..., None] * colours[i0] + l1[..., None] * colours[i1]
                   + l2[..., None] * colours[i2])
            region = img[miny:maxy + 1, minx:maxx + 1]
            region[write] = np.clip(col[write], 0, 1)
            rz[write] = depth_tri[write]

    draw(body_px, body_depth, body_c, body_t, False)
    draw(shell_px, shell_depth,
         np.tile(np.array([0.085, 0.085, 0.105]), (len(shell_px), 1)), shell_t, True)

    out = (np.clip(img, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    Image.fromarray(out).save(out_path)


def main():
    for stem in ("miffy", "zichaoxiong"):
        name, subs, lo, hi = read_psmesh(os.path.join(ASSETS, stem + ".psmesh"))
        centre = (lo + hi) * 0.5
        height = float(max(hi - lo))

        tex = load_shading_texture(os.path.join(ASSETS, stem + ".psmesh"))
        body_v, body_t, body_c = [], [], []
        shell_v, shell_n, shell_t = [], [], []
        off = 0
        for e in subs:
            flags = e[5] if len(e) > 5 else 0
            if flags & 1:
                shell_v.append(e[1] - e[2] * BAKED)     # undo the baked push -> surface
                shell_n.append(e[2])
                shell_t.append(e[4] + sum(len(x) for x in shell_v[:-1]))
            else:
                body_v.append(e[1])
                body_t.append(e[4] + off)
                body_c.append(sample_shading(tex, e[3]))
                off += len(e[1])
        bv = np.concatenate(body_v).astype(np.float64)
        bt = np.concatenate(body_t)
        bc = np.concatenate(body_c)
        sv = np.concatenate(shell_v).astype(np.float64)
        sn = np.concatenate(shell_n).astype(np.float64)
        st = np.concatenate(shell_t)

        print(f"==== {stem}: {len(sv)} shell verts, target {WIDTH_PX} px ====")
        for dist in (1.8, 3.0, 5.0, 8.0):
            size = 900
            eye = centre + np.array([0.0, height * 0.10, -dist])
            view = look_at(eye, centre, np.array([0.0, 1.0, 0.0]))

            body_px, body_cam = project(bv, centre, view, size, size, FOVY)
            surf_px, cam = project(sv, centre, view, size, size, FOVY)

            # Exact C# arithmetic. The offset is applied in CAMERA space and the moved
            # point is then projected, which is what the driver does (it maps the camera
            # offset back through the inverse model-view matrix before writing vertices).
            n_cam = (view[:3, :3] @ sn.T).T
            length = np.linalg.norm(n_cam[:, :2], axis=1, keepdims=True)
            dirxy = n_cam[:, :2] / np.maximum(length, 1e-8)
            depth = np.maximum(-cam[:, 2], 0.0)
            per_pixel = (2.0 * np.tan(np.radians(FOVY) * 0.5)) / size
            scale = per_pixel * depth * WIDTH_PX
            offset = np.column_stack([dirxy[:, 0] * scale, dirxy[:, 1] * scale,
                                      np.zeros_like(scale)])

            shell_px = cam_to_px(cam[:, :3] + offset, size, size, FOVY)
            depth_far = cam[:, 2] - 1e-3

            render(body_px, body_cam[:, 2], bt, bc, shell_px, depth_far, st,
                   os.path.join(OUT, f"ss_check_{stem}_{dist:.1f}.png"), size)

            # measure: silhouette verts only (normal strongly edge-on)
            sil = length[:, 0] >= 0.35
            # Measured on screen, which is the number that matters.
            widths = np.linalg.norm(shell_px[sil] - surf_px[sil], axis=1)
            print(f"  dist {dist:4.1f}  silhouette verts {int(sil.sum()):6d}  "
                  f"line {widths.mean():6.3f} +- {widths.std():5.3f} px  "
                  f"p5 {np.percentile(widths, 5):5.3f}  p95 {np.percentile(widths, 95):5.3f}")
        print()


if __name__ == "__main__":
    main()
