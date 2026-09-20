"""Render the VANILLA plush with its own hand anchors marked.

The game snaps the hands to Hand_L / Hand_R and the mod shifts its model to meet them.
What the vanilla plush looks like under that same rule is the ground truth for where a
replacement's hands are supposed to land, so this draws it: the real prefab meshes in
item space, front view, with the two anchors as crosshairs.
"""
import os

import numpy as np
from PIL import Image
import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
OUT = r"D:\zhuanban\Plushie Swap\research\preview"
TARGET = "BingBong_Prop Variant"
RES = 900

ANCHOR_L = np.array([-0.3590, -0.1770, -0.0400])
ANCHOR_R = np.array([+0.2400, -0.1040, -0.0400])


def compose(p, q, s):
    x, y, z, w = q.x, q.y, q.z, q.w
    r = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)
    m = np.eye(4)
    m[:3, :3] = r * np.array([s.x, s.y, s.z], dtype=np.float64)[None, :]
    m[:3, 3] = [p.x, p.y, p.z]
    return m


def main():
    env = UnityPy.load(os.path.join(GAME, "resources.assets"))
    objects = {o.path_id: o for o in env.objects}

    root = None
    for o in env.objects:
        if o.type.name != "GameObject":
            continue
        d = o.read()
        if d.m_Name == TARGET:
            root = d
            break
    if root is None:
        print("not found")
        return

    verts, tris = [], []
    # The item root IS the item, so its own transform is not part of item-local space.
    # Only the transforms *below* it matter, which is why the walk starts at eye.
    root_tr = None
    for comp in root.m_Components:
        if comp is None:
            continue
        cr = objects.get(comp.path_id)
        if cr is not None and cr.type.name == "Transform":
            root_tr = cr.read()
            break
    if root_tr is None:
        print("no root transform")
        return
    for ch in root_tr.m_Children:
        if ch is None:
            continue
        cgo = ch.read()
        ref = getattr(cgo, "m_GameObject", None)
        if ref is None:
            continue
        walk(objects, objects[ref.path_id].read(), np.eye(4), verts, tris)
    v = np.concatenate(verts)
    t = []
    off = 0
    for tri in tris:
        t.append(tri + off)
        off += tri.max() + 1
    t = np.concatenate(t)
    lo, hi = v.min(axis=0), v.max(axis=0)
    print(f"vanilla plush in item space: {len(v)} verts")
    print(f"  X[{lo[0]:+.4f},{hi[0]:+.4f}] Y[{lo[1]:+.4f},{hi[1]:+.4f}] Z[{lo[2]:+.4f},{hi[2]:+.4f}]")
    print(f"  size {np.round(hi-lo,4)}")

    def band_width(y):
        b = v[np.abs(v[:, 1] - y) < 0.02]
        if len(b) == 0:
            return float("nan"), float("nan"), float("nan")
        return b[:, 0].min(), b[:, 0].max(), b[:, 0].max() - b[:, 0].min()

    for name, a in (("Hand_L", ANCHOR_L), ("Hand_R", ANCHOR_R)):
        x0, x1, w = band_width(a[1])
        print(f"  {name} y={a[1]:+.3f}  model x[{x0:+.3f},{x1:+.3f}] width={w:.4f}  "
              f"hand x={a[0]:+.3f} -> {a[0]-x0:+.3f} from left edge, {a[0]-x1:+.3f} from right")
    print(f"  anchor separation {np.linalg.norm(ANCHOR_L-ANCHOR_R):.4f}")

    print("  height profile:")
    for k in range(20):
        y0 = lo[1] + (hi[1] - lo[1]) * k / 20
        b = v[(v[:, 1] >= y0) & (v[:, 1] < y0 + (hi[1] - lo[1]) / 20)]
        if len(b) == 0:
            continue
        print(f"    {k/20:.2f} y[{y0:+.3f}] x[{b[:,0].min():+.3f},{b[:,0].max():+.3f}] "
              f"width={b[:,0].max()-b[:,0].min():.4f}")

    # rasterise front view (looking down +Z, i.e. from the player)
    scale = RES * 0.85 / 1.1
    centre = np.array([-0.0315, -0.7345 + 0.9635 * 0.5, 0.0])
    mask = np.zeros((RES, RES), dtype=bool)
    px = (v[:, 0] - centre[0]) * scale + RES * 0.5
    py = RES * 0.5 - (v[:, 1] - centre[1]) * scale
    import math
    for tri in t:
        x0, y0 = px[tri[0]], py[tri[0]]
        x1, y1 = px[tri[1]], py[tri[1]]
        x2, y2 = px[tri[2]], py[tri[2]]
        minx = max(0, int(math.floor(min(x0, x1, x2))))
        maxx = min(RES - 1, int(math.ceil(max(x0, x1, x2))))
        miny = max(0, int(math.floor(min(y0, y1, y2))))
        maxy = min(RES - 1, int(math.ceil(max(y0, y1, y2))))
        if maxx < minx or maxy < miny:
            continue
        d00, d01 = x1 - x0, y1 - y0
        d10, d11 = x2 - x0, y2 - y0
        denom = d00 * d11 - d10 * d01
        if abs(denom) < 1e-9:
            continue
        xs = np.arange(minx, maxx + 1) + 0.5
        ys = np.arange(miny, maxy + 1) + 0.5
        gx, gy = np.meshgrid(xs, ys)
        u = (d11 * (gx - x0) - d01 * (gy - y0)) / denom
        ww = (d00 * (gy - y0) - d10 * (gx - x0)) / denom
        wc = 1.0 - u - ww
        inside = (u >= -1e-6) & (ww >= -1e-6) & (wc >= -1e-6)
        if not inside.any():
            continue
        yy, xx = np.nonzero(inside)
        mask[yy + miny, xx + minx] = True

    img = np.zeros((RES, RES, 3), dtype=np.uint8)
    img[mask] = (225, 225, 220)
    for name, a in (("L", ANCHOR_L), ("R", ANCHOR_R)):
        cx = int(round((a[0] - centre[0]) * scale + RES * 0.5))
        cy = int(round(RES * 0.5 - (a[1] - centre[1]) * scale))
        col = (255, 60, 60) if name == "L" else (60, 200, 255)
        for d in range(-16, 17):
            for w in (-1, 0, 1):
                for (xx, yy) in ((cx + d, cy + w), (cx + w, cy + d)):
                    if 0 <= xx < RES and 0 <= yy < RES:
                        img[yy, xx] = col
    path = os.path.join(OUT, "vanilla_grip.png")
    Image.fromarray(img[::-1]).save(path)
    print("wrote", path)

    # side view: screen x = model Z, so the anchor depth can be read off
    mask2 = np.zeros((RES, RES), dtype=bool)
    px2 = (v[:, 2] - centre[2]) * scale + RES * 0.5
    py2 = RES * 0.5 - (v[:, 1] - centre[1]) * scale
    for tri in t:
        x0, y0 = px2[tri[0]], py2[tri[0]]
        x1, y1 = px2[tri[1]], py2[tri[1]]
        x2, y2 = px2[tri[2]], py2[tri[2]]
        minx = max(0, int(math.floor(min(x0, x1, x2))))
        maxx = min(RES - 1, int(math.ceil(max(x0, x1, x2))))
        miny = max(0, int(math.floor(min(y0, y1, y2))))
        maxy = min(RES - 1, int(math.ceil(max(y0, y1, y2))))
        if maxx < minx or maxy < miny:
            continue
        d00, d01 = x1 - x0, y1 - y0
        d10, d11 = x2 - x0, y2 - y0
        denom = d00 * d11 - d10 * d01
        if abs(denom) < 1e-9:
            continue
        xs = np.arange(minx, maxx + 1) + 0.5
        ys = np.arange(miny, maxy + 1) + 0.5
        gx, gy = np.meshgrid(xs, ys)
        u = (d11 * (gx - x0) - d01 * (gy - y0)) / denom
        ww = (d00 * (gy - y0) - d10 * (gx - x0)) / denom
        wc = 1.0 - u - ww
        inside = (u >= -1e-6) & (ww >= -1e-6) & (wc >= -1e-6)
        if not inside.any():
            continue
        yy, xx = np.nonzero(inside)
        mask2[yy + miny, xx + minx] = True
    img2 = np.zeros((RES, RES, 3), dtype=np.uint8)
    img2[mask2] = (225, 225, 220)
    for name, a in (("L", ANCHOR_L), ("R", ANCHOR_R)):
        cx = int(round((a[2] - centre[2]) * scale + RES * 0.5))
        cy = int(round(RES * 0.5 - (a[1] - centre[1]) * scale))
        col = (255, 60, 60) if name == "L" else (60, 200, 255)
        for d in range(-16, 17):
            for w in (-1, 0, 1):
                for (xx, yy) in ((cx + d, cy + w), (cx + w, cy + d)):
                    if 0 <= xx < RES and 0 <= yy < RES:
                        img2[yy, xx] = col
    path2 = os.path.join(OUT, "vanilla_grip_side.png")
    Image.fromarray(img2[::-1]).save(path2)
    print("wrote", path2)
    print("  vanilla Z range", lo[2], hi[2], "centre", centre[2])
    for name, a in (("L", ANCHOR_L), ("R", ANCHOR_R)):
        b = v[np.abs(v[:, 1] - a[1]) < 0.02]
        print(f"  {name}: anchor z={a[2]:+.3f}  body z[{b[:,2].min():+.3f},{b[:,2].max():+.3f}]  "
              f"depth frac {(a[2]-b[:,2].min())/(b[:,2].max()-b[:,2].min()):.3f}")


def walk(objects, gd, parent, verts, tris):
    local = np.eye(4)
    tr = None
    for comp in gd.m_Components:
        if comp is None:
            continue
        cr = objects.get(comp.path_id)
        if cr is None:
            continue
        if cr.type.name == "Transform":
            tr = cr.read()
            p, q, s = tr.m_LocalPosition, tr.m_LocalRotation, tr.m_LocalScale
            local = compose(p, q, s)
            break
    world = parent @ local

    for comp in gd.m_Components:
        if comp is None:
            continue
        cr = objects.get(comp.path_id)
        if cr is None or cr.type.name != "MeshFilter":
            continue
        mref = cr.read().m_Mesh
        if mref is None:
            continue
        mesh = objects[mref.path_id].read()
        h = MeshHandler(mesh)
        h.process()
        mv = np.asarray(h.m_Vertices, dtype=np.float64)[:, :3]
        if len(mv) == 0:
            continue
        idx = np.asarray(h.m_IndexBuffer, dtype=np.int64).reshape(-1, 3)
        world_pts = (world @ np.hstack([mv, np.ones((len(mv), 1))]).T).T[:, :3]
        verts.append(world_pts)
        tris.append(idx)

    if tr is None:
        return
    for ch in tr.m_Children:
        if ch is None:
            continue
        cgo = ch.read()
        ref = getattr(cgo, "m_GameObject", None)
        if ref is None:
            continue
        walk(objects, objects[ref.path_id].read(), world, verts, tris)


if __name__ == "__main__":
    main()
