"""Render each plush with the player's ACTUAL hand meshes at candidate grip heights.

Everything before this guessed where the hand would appear. This places the game's own
"Chubby Hand" mesh using the exact transform chain the game uses:

    player hand rig  <-  item anchor position + rotation   (CharacterItems.AttachItem)
    hand mesh        <-  the rig, via the anchor's "Hand" child local matrix

so the picture is what the player actually sees. Hands are drawn in orange so they stand
out against the plush, and a height is only acceptable if they rest on the body without
sinking into it.
"""
import os

import numpy as np
import UnityPy
from PIL import Image

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\tools\preview"

ROT_L = (-0.31818, 0.67636, 0.51899, -0.41466)
ROT_R = (0.25786, 0.71867, 0.55145, 0.33605)

CANDIDATES = {
    "miffy": [0.14, 0.20, 0.26, 0.32],
    "zichaoxiong": [0.10, 0.16, 0.22, 0.28],
}

# the player's hand is a skinned mesh, so it renders at the hand bone; a small box at
# the anchor stands in for it here
HAND_HALF = np.array([0.045, 0.055, 0.045])


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


def local_matrix(t):
    p, q, s = t.m_LocalPosition, t.m_LocalRotation, t.m_LocalScale
    m = np.eye(4)
    m[:3, :3] = quat_mat((q.x, q.y, q.z, q.w)) @ np.diag([s.x, s.y, s.z])
    m[:3, 3] = [p.x, p.y, p.z]
    return m


def load_hands():
    """Return {side: (verts Nx3, tris Mx3, child_matrix 4x4)} from the item prefab."""
    env = UnityPy.load(os.path.join(GAME, "resources.assets"))
    objects = {o.path_id: o for o in env.objects}
    names = {}
    for o in env.objects:
        if o.type.name == "GameObject":
            try:
                names[o.path_id] = o.read().m_Name
            except Exception:
                pass

    transforms = {}
    for o in env.objects:
        if o.type.name != "Transform":
            continue
        try:
            t = o.read()
        except Exception:
            continue
        ref = getattr(t, "m_GameObject", None)
        if ref is not None:
            transforms[o.path_id] = (ref.path_id, t)
    go_to_transform = {go: tid for tid, (go, _t) in transforms.items()}

    root = None
    for go_id, n in names.items():
        if n == "BingBong_Prop Variant":
            root = go_to_transform.get(go_id)
            break

    out = {}
    for ch in transforms[root][1].m_Children:
        if ch is None:
            continue
        cgo = ch.read()
        ref = getattr(cgo, "m_GameObject", None)
        if ref is None:
            continue
        side = names.get(ref.path_id)
        if side not in ("Hand_L", "Hand_R"):
            continue
        tid = go_to_transform[ref.path_id]
        for gch in transforms[tid][1].m_Children:
            if gch is None:
                continue
            ggo = gch.read()
            gref = getattr(ggo, "m_GameObject", None)
            if gref is None:
                continue
            ggd = objects[gref.path_id].read()
            for comp in ggd.m_Components:
                if comp is None:
                    continue
                cr = objects.get(comp.path_id)
                if cr is None or cr.type.name != "MeshFilter":
                    continue
                d = cr.read()
                if d.m_Mesh is None:
                    continue
                mesh = d.m_Mesh.read()
                a = mesh.m_LocalAABB
                c = np.array([a.m_Center.x, a.m_Center.y, a.m_Center.z])
                e = np.array([a.m_Extent.x, a.m_Extent.y, a.m_Extent.z])
                # The hand is a skinned mesh with no CPU-side vertex array, so its
                # bounding box stands in for the shape. That is plenty to judge whether
                # the hand rests on the plush or floats beside it.
                corners = np.array([[c[0] + sx * e[0], c[1] + sy * e[1], c[2] + sz * e[2]]
                                    for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
                tris = np.array([
                    [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
                    [0, 4, 5], [0, 5, 1], [1, 5, 7], [1, 7, 3],
                    [3, 7, 6], [3, 6, 2], [2, 6, 4], [2, 4, 0],
                ], dtype=np.int64)
                out[side] = (corners, tris, local_matrix(transforms[gch.path_id][1]))
                print(f"  {side}: aabb centre {np.round(c, 4)} extent {np.round(e, 4)}")
    return out


def render(items, lo, hi, size):
    centre = (lo + hi) * 0.5
    extent = float(max(hi - lo)) * 0.62
    fwd = np.array([0.0, 0.0, -1.0])
    up_in = np.array([0.0, 1.0, 0.0])
    right = np.cross(up_in, fwd)
    right /= np.linalg.norm(right)
    up = np.cross(fwd, right)

    zbuf = np.full((size, size), -1e30, dtype=np.float32)
    img = np.full((size, size, 3), 0.12, dtype=np.float32)

    queue = []
    for verts, tris, cols in items:
        v = verts - centre
        px = ((v @ right / extent) * 0.5 + 0.5) * (size - 1)
        py = (1.0 - ((v @ up / extent) * 0.5 + 0.5)) * (size - 1)
        pz = v @ fwd
        for k in range(len(tris)):
            i0, i1, i2 = tris[k]
            queue.append((pz[i0] + pz[i1] + pz[i2],
                          px[i0], py[i0], pz[i0], px[i1], py[i1], pz[i1],
                          px[i2], py[i2], pz[i2],
                          cols[i0], cols[i1], cols[i2]))
    queue.sort(key=lambda r: r[0])

    for rec in queue:
        (_, ax, ay, az, bx, by, bz, cx, cy, cz, c0, c1, c2) = rec
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
        rz = zbuf[miny:maxy + 1, minx:maxx + 1]
        write = mask & (depth > rz)
        if not write.any():
            continue
        col = (l0[..., None] * c0 + l1[..., None] * c1 + l2[..., None] * c2)
        region = img[miny:maxy + 1, minx:maxx + 1]
        region[write] = np.clip(col[write], 0, 1)
        rz[write] = depth[write]

    return (np.clip(img, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)


def main():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import verify_merge as vm
    from preview_mesh import sample_shading

    hands = load_hands()
    print("hand meshes:", {k: (len(v[0]), len(v[1])) for k, v in hands.items()})

    for stem in ("miffy", "zichaoxiong"):
        path = os.path.join(ASSETS, stem + ".psmesh")
        _name, subs, lo, hi = vm.read_psmesh(path)
        tex = vm.load_shading_texture(path)
        height = float(hi[1] - lo[1])

        plush_verts, plush_tris, plush_cols = [], [], []
        offset = 0
        for s in subs:
            if s[5] & 1:
                continue
            v, f, uv = s[1], s[4], s[3]
            col = sample_shading(tex, uv)
            plush_verts.append(v)
            plush_tris.append(f + offset)
            plush_cols.append(col)
            offset += len(v)
        pv = np.concatenate(plush_verts)
        pt = np.concatenate(plush_tris)
        pc = np.concatenate(plush_cols)

        size = 620
        tiles = []
        for frac in CANDIDATES[stem]:
            y = lo[1] + height * frac
            band = height * 0.10
            xs = []
            for s in subs:
                if s[5] & 1:
                    continue
                v = s[1]
                sel = (v[:, 1] >= y - band) & (v[:, 1] <= y + band)
                if sel.any():
                    xs.append(v[sel, 0])
            xs = np.concatenate(xs)
            zs = []
            for s in subs:
                if s[5] & 1:
                    continue
                v = s[1]
                sel = (v[:, 1] >= y - band) & (v[:, 1] <= y + band)
                if sel.any():
                    zs.append(v[sel, 2])
            zs = np.concatenate(zs)
            cz = float((zs.min() + zs.max()) * 0.5)
            left_x, right_x = float(xs.min()), float(xs.max())
            width = right_x - left_x

            items = [(pv, pt, pc)]
            # The hand mesh is skinned to the hand bone, so it renders at the bone: the
            # anchor is the hand position, with no offset applied. The anchor's rotation
            # still spins the hand about that point, which is the pose.
            for _side, _rot, x in (
                    ("Hand_L", ROT_L, left_x + width * 0.16),
                    ("Hand_R", ROT_R, right_x - width * 0.16)):
                anchor = np.array([x, y, cz])
                hv = np.array([[anchor[0] + sx * HAND_HALF[0],
                                anchor[1] + sy * HAND_HALF[1],
                                anchor[2] + sz * HAND_HALF[2]]
                               for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
                ht = np.array([
                    [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
                    [0, 4, 5], [0, 5, 1], [1, 5, 7], [1, 7, 3],
                    [3, 7, 6], [3, 6, 2], [2, 6, 4], [2, 4, 0],
                ], dtype=np.int64)
                col = np.tile(np.array([1.0, 0.45, 0.12]), (len(hv), 1))
                items.append((hv, ht, col))

            img = render(items, lo, hi, size)
            tiles.append(Image.fromarray(img))

        cols = 2
        rows = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGB", (size * cols, size * rows), (40, 40, 40))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % cols) * size, (i // cols) * size))
        sheet.save(os.path.join(OUT, stem + "_real_hands.png"))
        print("wrote", stem + "_real_hands.png",
              "(tiles:", CANDIDATES[stem], ")")


if __name__ == "__main__":
    main()
