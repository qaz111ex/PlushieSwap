"""Research-only: render the body + outline with both methods, same camera.

Reproduces, in Python, exactly what the two outline schemes project to:

  * object-space (current): use the .psmesh inverted-hull shell as shipped
  * screen-space (proposed): take the same shell's *base* vertices and normals
    and apply the shader formula
        offset = normalize(clipNormal.xy) / _ScreenParams.xy * width_px * clip.w * 2
    before rasterising.

Both are drawn with front faces culled (inverted hull) and depth tested against
the body, so the pictures show the line the game would actually draw at a close
(held-item) distance.

Writes research/preview/ss_vs_os_<stem>.png (side by side) and the individual
frames.
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from preview_mesh import read_psmesh, load_shading_texture  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\research\preview"

OUTLINE_THICKNESS = 0.0075 * 0.9635
INK = np.array([0.085, 0.085, 0.105], dtype=np.float64)
CLOSE_DIST = 1.30          # metres; a held item seen at arm's length
TARGET_PX = 2.0
SIZE = 480
FOVY = 50.0


def look_at(eye, target, up):
    fwd = target - eye
    fwd = fwd / np.linalg.norm(fwd)
    right = np.cross(fwd, up)
    right = right / np.linalg.norm(right)
    camup = np.cross(right, fwd)
    v = np.eye(4)
    v[0, :3] = right
    v[1, :3] = camup
    v[2, :3] = -fwd
    v[:3, 3] = -v[:3, :3] @ eye
    return v


def perspective(fovy, aspect, near, far):
    f = 1.0 / np.tan(np.radians(fovy) * 0.5)
    p = np.zeros((4, 4))
    p[0, 0] = f / aspect
    p[1, 1] = f
    p[2, 2] = (far + near) / (near - far)
    p[2, 3] = (2 * far * near) / (near - far)
    p[3, 2] = -1.0
    return p


def rasterize(img, zbuf, verts_ws, tris, colours, view, proj, cull_front):
    size = img.shape[0]
    p = np.concatenate([verts_ws, np.ones((len(verts_ws), 1))], axis=1)
    clip = (proj @ (view @ p.T)).T
    w = np.maximum(clip[:, 3], 1e-6)
    ndc = clip[:, :3] / w[:, None]
    px = (ndc[:, 0] * 0.5 + 0.5) * (size - 1)
    py = (1.0 - (ndc[:, 1] * 0.5 + 0.5)) * (size - 1)
    pz = w  # view-space depth (positive distance)

    for k in range(len(tris)):
        i0, i1, i2 = tris[k]
        ax, ay, az = px[i0], py[i0], pz[i0]
        bx, by, bz = px[i1], py[i1], pz[i1]
        cx, cy, cz = px[i2], py[i2], pz[i2]
        minx = max(int(min(ax, bx, cx)), 0)
        maxx = min(int(max(ax, bx, cx)) + 1, size - 1)
        miny = max(int(min(ay, by, cy)), 0)
        maxy = min(int(max(ay, by, cy)) + 1, size - 1)
        if minx > maxx or miny > maxy:
            continue
        det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(det) < 1e-9:
            continue
        if cull_front and det <= 0:
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
        write = mask & (depth < region_z)
        if not write.any():
            continue
        col = (l0[..., None] * colours[i0] + l1[..., None] * colours[i1]
               + l2[..., None] * colours[i2])
        region = img[miny:maxy + 1, minx:maxx + 1]
        region[write] = np.clip(col[write], 0, 1)
        region_z[write] = depth[write]


def build(stem):
    name, subs, lo, hi = read_psmesh(os.path.join(ASSETS, stem + ".psmesh"))
    texture = load_shading_texture(os.path.join(ASSETS, stem + ".psmesh"))
    centre = (lo + hi) * 0.5

    body_v, body_t, body_uv = [], [], []
    shell_v, shell_n, shell_t = [], [], []
    offset = 0
    for e in subs:
        flags = e[5] if len(e) > 5 else 0
        if flags & 1:
            shell_v.append(e[1].astype(np.float64))
            shell_n.append(e[2].astype(np.float64))
            shell_t.append(e[4] + offset)
            offset += len(e[1])
        else:
            body_v.append(e[1].astype(np.float64))
            body_t.append(e[4] + offset)
            body_uv.append(e[3].astype(np.float64))
            offset += len(e[1])
    # NOTE: the pipeline re-indexes the shell in its own vertex space (the C#
    # builder concatenates solid and outline submeshes separately), so the shell
    # indices are local to the shell block. Rebuild them locally here.
    off = 0
    shell_t = []
    for e in subs:
        flags = e[5] if len(e) > 5 else 0
        if flags & 1:
            shell_t.append(e[4] + off)
            off += len(e[1])
    return (name, centre, np.concatenate(body_v), np.concatenate(body_t),
            np.concatenate(body_uv), np.concatenate(shell_v),
            np.concatenate(shell_n), np.concatenate(shell_t), texture)


def albedo_of(texture, uv):
    if texture is None:
        return np.ones((len(uv), 3))
    width = texture.shape[1]
    x = np.clip(uv[:, 0], 0, 1) * width - 0.5
    x0 = np.clip(np.floor(x).astype(np.int64), 0, width - 1)
    x1 = np.clip(x0 + 1, 0, width - 1)
    frac = (x - np.floor(x))[:, None]
    return (texture[0][x0] * (1 - frac) + texture[0][x1] * frac)[:, :3]


def render(stem):
    (name, centre, bv, bt, buv, sv, sn, st, texture) = build(stem)
    albedo = np.tile(albedo_of(texture, buv), (1, 1))

    eye = centre + np.array([0.20, 0.10, -1.0]) * CLOSE_DIST
    view = look_at(eye, centre, np.array([0.0, 1.0, 0.0]))
    proj = perspective(FOVY, 1.0, 0.03, 100.0)

    results = {}
    for method in ("object-space", "screen-space"):
        img = np.full((SIZE, SIZE, 3), 0.12)
        zbuf = np.full((SIZE, SIZE), 1e30)
        rasterize(img, zbuf, bv, bt, albedo, view, proj, cull_front=False)

        if method == "object-space":
            out_v = sv.copy()
        else:
            # base body position + shader clip-space offset
            base = sv - sn * OUTLINE_THICKNESS
            m = proj @ view
            p = np.concatenate([base, np.ones((len(base), 1))], axis=1)
            clip = (m @ p.T).T
            ncs = (m[:3, :3] @ sn.T).T
            d = ncs[:, :2].copy()
            ln = np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-8)
            d = d / ln
            off = d / np.array([SIZE, SIZE]) * (TARGET_PX * 2.0) * clip[:, 3:4]
            clip[:, :2] += off
            # invert back to world so the same rasteriser can draw it
            inv = np.linalg.inv(m)
            world = (inv @ clip.T).T
            out_v = world[:, :3] / world[:, 3:4]
        rasterize(img, zbuf, out_v, st, np.tile(INK, (len(out_v), 1)),
                  view, proj, cull_front=True)
        out = (np.clip(img, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
        results[method] = out
        Image.fromarray(out).save(os.path.join(OUT, f"ss_vs_os_{stem}_{method}.png"))

    side = np.concatenate([results["object-space"], results["screen-space"]], axis=1)
    Image.fromarray(side).save(os.path.join(OUT, f"ss_vs_os_{stem}.png"))
    print("wrote", os.path.join(OUT, f"ss_vs_os_{stem}.png"),
          " (left: current object-space, right: screen-space constant width)")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for stem in ("miffy", "zichaoxiong"):
        render(stem)
