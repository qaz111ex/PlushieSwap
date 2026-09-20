"""Measure the vanilla BingBong plush mesh against its own Hand_L / Hand_R anchors.

The mod's whole grip strategy is "keep the vanilla anchors, shift the model to meet
them". Whether that can work at all depends on one measurement: how wide the vanilla
plush actually is at the height its own anchors sit. If the anchors are 0.60 apart
and the vanilla body is 0.60 wide there, then the hands press into the sides of the
toy and any replacement must be about that wide at the grip height too.
"""
import os

import numpy as np
import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
TARGET = "BingBong_Prop Variant"


def main():
    env = UnityPy.load(os.path.join(GAME, "resources.assets"))
    objects = {o.path_id: o for o in env.objects}

    root = None
    for o in env.objects:
        if o.type.name != "GameObject":
            continue
        d = o.read()
        if d.m_Name == TARGET:
            root = (o.path_id, d)
            break
    if root is None:
        print("not found")
        return

    anchors = {}
    meshes = []
    collect(objects, root[1], anchors, meshes, np.eye(4), "")

    print("=== anchors (item-local space) ===")
    for k, v in sorted(anchors.items()):
        print(f"  {k}: pos={np.round(v[0], 4)} rot={np.round(v[1], 4)}")

    print("=== meshes ===")
    for name, pos, tris in meshes:
        lo = pos.min(axis=0)
        hi = pos.max(axis=0)
        print(f"  {name}: {len(pos)} verts, {len(tris)} tris, "
              f"X[{lo[0]:+.4f},{hi[0]:+.4f}] Y[{lo[1]:+.4f},{hi[1]:+.4f}] Z[{lo[2]:+.4f},{hi[2]:+.4f}]")

    allpos = np.concatenate([p for _, p, _ in meshes], axis=0)
    lo = allpos.min(axis=0)
    hi = allpos.max(axis=0)
    print(f"combined X[{lo[0]:+.4f},{hi[0]:+.4f}] Y[{lo[1]:+.4f},{hi[1]:+.4f}] "
          f"Z[{lo[2]:+.4f},{hi[2]:+.4f}]  size={np.round(hi-lo,4)}")

    if "Hand_L" in anchors and "Hand_R" in anchors:
        l = anchors["Hand_L"][0]
        r = anchors["Hand_R"][0]
        print(f"anchor separation: {np.linalg.norm(l-r):.4f}  (X {r[0]-l[0]:.4f})")
        mid = (l + r) * 0.5
        print(f"anchor mid: {np.round(mid,4)}  height fraction "
              f"{(mid[1]-lo[1])/(hi[1]-lo[1]):.3f}")

    print("=== vanilla width profile (per 5% height band) ===")
    n = 20
    for k in range(n):
        y0 = lo[1] + (hi[1] - lo[1]) * k / n
        y1 = lo[1] + (hi[1] - lo[1]) * (k + 1) / n
        band = allpos[(allpos[:, 1] >= y0) & (allpos[:, 1] < y1)]
        if len(band) == 0:
            continue
        w = band[:, 0].max() - band[:, 0].min()
        z = band[:, 2].max() - band[:, 2].min()
        print(f"  {k/n:.2f}-{(k+1)/n:.2f} y[{y0:+.3f},{y1:+.3f}] "
              f"x[{band[:,0].min():+.3f},{band[:,0].max():+.3f}] width={w:.3f} "
              f"z[{band[:,2].min():+.3f},{band[:,2].max():+.3f}] depth={z:.3f}")


def collect(objects, gd, anchors, meshes, parent_matrix, indent):
    local = np.eye(4)
    for comp in gd.m_Components:
        if comp is None:
            continue
        cr = objects.get(comp.path_id)
        if cr is None:
            continue
        if cr.type.name == "Transform":
            t = cr.read()
            p = t.m_LocalPosition
            q = t.m_LocalRotation
            s = t.m_LocalScale
            local = compose(p, q, s)
            break

    world = parent_matrix @ local

    if gd.m_Name in ("Hand_L", "Hand_R"):
        anchors[gd.m_Name] = (np.array([local[0, 3], local[1, 3], local[2, 3]]),
                              np.array([0.0, 0.0, 0.0, 0.0]))

    for comp in gd.m_Components:
        if comp is None:
            continue
        cr = objects.get(comp.path_id)
        if cr is None:
            continue
        if cr.type.name != "MeshFilter":
            continue
        mref = cr.read().m_Mesh
        if mref is None:
            continue
        verts = mesh_vertices(objects, mref)
        if len(verts) == 0:
            continue
        # unity meshes are Y-up already
        transformed = (world @ np.hstack([verts, np.ones((len(verts), 1))]).T).T[:, :3]
        meshes.append((gd.m_Name, transformed, []))

    for comp in gd.m_Components:
        if comp is None:
            continue
        cr = objects.get(comp.path_id)
        if cr is None:
            continue
        if cr.type.name == "Transform":
            for ch in cr.read().m_Children:
                if ch is None:
                    continue
                cgo = ch.read()
                ref = getattr(cgo, "m_GameObject", None)
                if ref is None:
                    continue
                collect(objects, objects[ref.path_id].read(), anchors, meshes, world, indent + "  ")


def mesh_vertices(objects, mref):
    """UnityPy exposes mesh positions through m_VertexData; read them defensively."""
    mesh = objects[mref.path_id].read()
    vd = getattr(mesh, "m_VertexData", None)
    if vd is None:
        return np.zeros((0, 3))
    try:
        verts = vd.m_Vertices
    except Exception:
        verts = None
    if verts is None:
        try:
            verts = vd.get_vertices()
        except Exception:
            return np.zeros((0, 3))
    arr = np.asarray(verts, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 3)
    return arr[:, :3]


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


if __name__ == "__main__":
    main()
