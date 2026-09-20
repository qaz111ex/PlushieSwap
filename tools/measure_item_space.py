"""Compute where each vanilla plush part sits in ITEM-ROOT space.

Uses the real item prefab (BingBong_Prop Variant) hierarchy from resources.assets so
the replacement can be aligned to the same pivot, facing and grip point.
"""
import os

import numpy as np
import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


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


def trs(pos, rot, scale):
    m = np.eye(4)
    m[:3, :3] = quat_mat(rot) @ np.diag(scale)
    m[:3, 3] = pos
    return m


def main():
    res = UnityPy.load(os.path.join(GAME, "resources.assets"))
    meshes = {}
    for o in res.objects:
        if o.type.name != "Mesh":
            continue
        try:
            meshes[o.path_id] = o.read()
        except Exception:
            pass

    objects = {o.path_id: o for o in res.objects}
    root_id = None
    for o in res.objects:
        if o.type.name != "GameObject":
            continue
        try:
            d = o.read()
        except Exception:
            continue
        if d.m_Name == "Holder":
            root_id = o.path_id
            break
    if root_id is None:
        print("prefab not found")
        return

    print("part centres in ITEM-ROOT space (x, y, z) and world sizes")
    print("-" * 72)
    rows = []

    def walk(reader, mat, path):
        gd = reader.read()
        tr = None
        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = objects.get(comp.path_id)
            if cr is None:
                continue
            if cr.type.name == "Transform":
                tr = cr.read()
                break

        own = mat
        if tr is not None:
            p, q, s = tr.m_LocalPosition, tr.m_LocalRotation, tr.m_LocalScale
            own = mat @ trs((p.x, p.y, p.z), (q.x, q.y, q.z, q.w), (s.x, s.y, s.z))

        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = objects.get(comp.path_id)
            if cr is None or cr.type.name != "MeshFilter":
                continue
            mf = cr.read()
            ref = mf.m_Mesh
            if ref is None:
                continue
            mesh = meshes.get(ref.path_id)
            if mesh is None:
                continue
            a = mesh.m_LocalAABB
            c = np.array([a.m_Center.x, a.m_Center.y, a.m_Center.z])
            e = np.array([a.m_Extent.x, a.m_Extent.y, a.m_Extent.z])
            corners = np.array([(own @ np.append(c + e * np.array([sx, sy, sz]), 1.0))[:3]
                                for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
            lo, hi = corners.min(axis=0), corners.max(axis=0)
            centre = (lo + hi) * 0.5
            size = hi - lo
            rows.append((g2 := gd.m_Name, mesh.m_Name, centre, size, path))
            print(f"  {gd.m_Name:16s} mesh={mesh.m_Name:12s} "
                  f"centre=({centre[0]:+.4f},{centre[1]:+.4f},{centre[2]:+.4f}) "
                  f"size=({size[0]:.4f},{size[1]:.4f},{size[2]:.4f})")

        if tr is None:
            return
        for ch in tr.m_Children:
            if ch is None:
                continue
            cgo = ch.read()
            ref = getattr(cgo, "m_GameObject", None)
            if ref:
                walk(objects[ref.path_id], own, path + "/" + gd.m_Name)

    walk(objects[root_id], np.eye(4), "")

    if rows:
        allc = np.array([r[2] for r in rows])
        alls = np.array([r[3] for r in rows])
        lo = (allc - alls * 0.5).min(axis=0)
        hi = (allc + alls * 0.5).max(axis=0)
        print("-" * 72)
        print(f"  COMBINED centre=({(lo+hi)[0]/2:+.4f},{(lo+hi)[1]/2:+.4f},{(lo+hi)[2]/2:+.4f})"
              f" size=({(hi-lo)[0]:.4f},{(hi-lo)[1]:.4f},{(hi-lo)[2]:.4f})")
        print(f"  Y range [{lo[1]:+.4f}, {hi[1]:+.4f}]")
        print()
        # Lip Top marks the face, so its Z tells us which way the plush looks.
        for name, mesh, centre, size, _ in rows:
            if name in ("Lip Top", "Lip Bottom"):
                print(f"  face marker '{name}' is at Z={centre[2]:+.4f}"
                      f"  -> plush looks toward {'+Z' if centre[2] > 0 else '-Z'}")


if __name__ == "__main__":
    main()
