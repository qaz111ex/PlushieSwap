"""Measure the vanilla BingBong visual height, using correct 4x4 transform composition."""
import os

import numpy as np
import UnityPy

GAME_DATA = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def quat_to_mat(q):
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


def trs_matrix(pos, rot, scale):
    m = np.eye(4)
    m[:3, :3] = quat_to_mat(rot) @ np.diag(scale)
    m[:3, 3] = pos
    return m


def main():
    res = UnityPy.load(os.path.join(GAME_DATA, "resources.assets"))
    lvl = UnityPy.load(os.path.join(GAME_DATA, "level1"))

    def meshes(env):
        out = {}
        for o in env.objects:
            if o.type.name != "Mesh":
                continue
            try:
                out[o.path_id] = o.read()
            except Exception:
                pass
        return out

    res_mesh = meshes(res)
    lvl_mesh = meshes(lvl)

    objects = {o.path_id: o for o in lvl.objects}
    root = next((o.path_id for o in lvl.objects
                 if o.type.name == "GameObject" and o.read().m_Name == "Bing Bong Plush"), None)
    if root is None:
        print("prefab not found")
        return

    lo = np.array([1e30] * 3)
    hi = np.array([-1e30] * 3)
    parts = []

    def walk(reader, mat, depth=0):
        nonlocal lo, hi
        gd = reader.read()

        # The node's own transform must be applied before its mesh is measured.
        tr = None
        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = objects.get(comp.path_id)
            if cr is not None and cr.type.name == "Transform":
                tr = cr.read()
                break

        own = mat
        if tr is not None:
            p = tr.m_LocalPosition
            q = tr.m_LocalRotation
            s = tr.m_LocalScale
            own = mat @ trs_matrix((p.x, p.y, p.z), (q.x, q.y, q.z, q.w), (s.x, s.y, s.z))

        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = objects.get(comp.path_id)
            if cr is None:
                continue
            if cr.type.name == "MeshFilter":
                mf = cr.read()
                ref = mf.m_Mesh
                if ref is None:
                    continue
                file_id = getattr(ref, "m_FileID", 0)
                mesh = (res_mesh if file_id not in (0, None) else lvl_mesh).get(ref.path_id)
                if mesh is None:
                    continue
                a = mesh.m_LocalAABB
                c = np.array([a.m_Center.x, a.m_Center.y, a.m_Center.z])
                e = np.array([a.m_Extent.x, a.m_Extent.y, a.m_Extent.z])
                for sx in (-1, 1):
                    for sy in (-1, 1):
                        for sz in (-1, 1):
                            pt = c + e * np.array([sx, sy, sz])
                            w = (own @ np.append(pt, 1.0))[:3]
                            lo = np.minimum(lo, w)
                            hi = np.maximum(hi, w)
                parts.append((gd.m_Name, mesh.m_Name, own))

        if tr is None:
            return
        for ch in tr.m_Children:
            if ch is None:
                continue
            cgo = ch.read()
            ref = getattr(cgo, "m_GameObject", None)
            if ref:
                walk(objects[ref.path_id], own, depth + 1)

    walk(objects[root], np.eye(4))

    size = hi - lo
    print("parts:")
    for name, mesh, _ in parts:
        print(f"   {name}  mesh={mesh!r}")
    print()
    print(f"vanilla visual size  = ({size[0]:.4f}, {size[1]:.4f}, {size[2]:.4f})")
    print(f"vanilla visual HEIGHT = {size[1]:.4f} units")
    print(f"Y range = [{lo[1]:.4f}, {hi[1]:.4f}]")


if __name__ == "__main__":
    main()
