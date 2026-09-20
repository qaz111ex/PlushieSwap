"""Measure the vanilla BingBong visual height precisely, following the transform chain."""
import math
import os
import sys

import numpy as np
import UnityPy

GAME_DATA = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def mat_from_trs(pos, rot, scale):
    x, y, z, w = rot
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    m = np.array([
        [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy), pos[0]],
        [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx), pos[1]],
        [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy), pos[2]],
        [0, 0, 0, 1],
    ], dtype=np.float64)
    s = np.diag([scale[0], scale[1], scale[2], 1.0])
    return m @ s


def main():
    env = UnityPy.load(os.path.join(GAME_DATA, "resources.assets"))
    level = UnityPy.load(os.path.join(GAME_DATA, "level1"))

    # mesh bounds keyed by path id in each file
    def mesh_bounds(env_):
        out = {}
        for o in env_.objects:
            if o.type.name != "Mesh":
                continue
            try:
                d = o.read()
            except Exception:
                continue
            aabb = d.m_LocalAABB
            c = aabb.m_Center
            e = aabb.m_Extent
            out[o.path_id] = (d.m_Name, np.array([c.x, c.y, c.z]), np.array([e.x, e.y, e.z]))
        return out

    bounds = mesh_bounds(level)

    # walk the "Bing Bong Plush" hierarchy in level1 and accumulate transforms
    objs = {o.path_id: o for o in level.objects}
    root = None
    for o in level.objects:
        if o.type.name == "GameObject":
            try:
                d = o.read()
            except Exception:
                continue
            if d.m_Name == "Bing Bong Plush":
                root = o.path_id
                break
    if root is None:
        print("prefab not found")
        return

    results = []

    def walk(go_reader, mat, depth=0):
        gd = go_reader.read()
        tr = None
        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = objs.get(comp.path_id)
            if cr is None:
                continue
            if cr.type.name == "Transform":
                tr = cr.read()
            elif cr.type.name == "MeshFilter":
                mf = cr.read()
                mesh = mf.m_Mesh
                if mesh is not None and mesh.path_id in bounds:
                    name, c, e = bounds[mesh.path_id]
                    # 8 corners of the AABB in local space
                    corners = []
                    for sx in (-1, 1):
                        for sy in (-1, 1):
                            for sz in (-1, 1):
                                corners.append(c + e * np.array([sx, sy, sz]))
                    pts = np.array([mat @ np.append(p, 1.0) for p in corners])[:, :3]
                    lo = pts.min(axis=0)
                    hi = pts.max(axis=0)
                    results.append((gd.m_Name, name, lo, hi, hi - lo))

        if tr is None:
            return
        p = tr.m_LocalPosition
        q = tr.m_LocalRotation
        s = tr.m_LocalScale
        local = mat_from_trs((p.x, p.y, p.z), (q.x, q.y, q.z, q.w), (s.x, s.y, s.z))
        child = mat @ local
        for ch in tr.m_Children:
            if ch is None:
                continue
            cgo = ch.read()
            ref = getattr(cgo, "m_GameObject", None)
            if ref:
                walk(objs[ref.path_id], child, depth + 1)

    walk(objs[root], np.eye(4))
    print("mesh parts under 'Bing Bong Plush':")
    overall_lo = np.array([1e30] * 3)
    overall_hi = np.array([-1e30] * 3)
    for node, mesh, lo, hi, size in results:
        print(f"  {node:14s} mesh={mesh:12s} worldSize=({size[0]:.4f},{size[1]:.4f},{size[2]:.4f})")
        overall_lo = np.minimum(overall_lo, lo)
        overall_hi = np.maximum(overall_hi, hi)
    size = overall_hi - overall_lo
    print()
    print(f"  COMBINED world size = ({size[0]:.4f}, {size[1]:.4f}, {size[2]:.4f})")
    print(f"  world Y range = [{overall_lo[1]:.4f}, {overall_hi[1]:.4f}]")
    print(f"  -> visual HEIGHT = {size[1]:.4f} units")

    # also report the scale chain to sanity check
    print()
    print("note: this is the size at the item's own scale (item root scale = 1).")


if __name__ == "__main__":
    main()
