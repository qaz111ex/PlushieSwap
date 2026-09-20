"""Print the resolved mesh + raw AABB for each renderer of the BingBong item prefab."""
import os

import numpy as np
import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def quat_mat(q):
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    s = 2.0 / n if n > 1e-12 else 0.0
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


env = UnityPy.load(os.path.join(GAME, "resources.assets"))
meshes = {}
for o in env.objects:
    if o.type.name == "Mesh":
        try:
            meshes[o.path_id] = o.read()
        except Exception:
            pass

print("all meshes named BingBong / Lip:")
for pid, m in meshes.items():
    if m.m_Name in ("BingBong", "Lip Top", "Lip Bottom"):
        a = m.m_LocalAABB
        print(f"   pid={pid} {m.m_Name!r} "
              f"size=({a.m_Extent.x*2:.4f},{a.m_Extent.y*2:.4f},{a.m_Extent.z*2:.4f}) "
              f"centre=({a.m_Center.x:.4f},{a.m_Center.y:.4f},{a.m_Center.z:.4f})")

objects = {o.path_id: o for o in env.objects}
root = None
for o in env.objects:
    if o.type.name != "GameObject":
        continue
    try:
        d = o.read()
    except Exception:
        continue
    if d.m_Name == "BingBong_Prop Variant":
        root = o.path_id
        break

print()
print("mesh references with resolved pid + local scale chain:")

def walk(reader, mat, scale_chain):
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
    chain = scale_chain
    if tr is not None:
        p, q, s = tr.m_LocalPosition, tr.m_LocalRotation, tr.m_LocalScale
        own = mat @ trs((p.x, p.y, p.z), (q.x, q.y, q.z, q.w), (s.x, s.y, s.z))
        chain = scale_chain + [s.x]

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
        fid = getattr(ref, "m_FileID", 0)
        mesh = meshes.get(ref.path_id)
        if mesh is None:
            print(f"   {gd.m_Name}: pid={ref.path_id} fileID={fid} -> NOT FOUND")
            continue
        a = mesh.m_LocalAABB
        c = np.array([a.m_Center.x, a.m_Center.y, a.m_Center.z])
        e = np.array([a.m_Extent.x, a.m_Extent.y, a.m_Extent.z])
        corners = np.array([(own @ np.append(c + e * np.array([sx, sy, sz]), 1.0))[:3]
                            for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
        lo, hi = corners.min(axis=0), corners.max(axis=0)
        print(f"   {gd.m_Name:8s} fileID={fid} pid={ref.path_id} mesh={mesh.m_Name!r}")
        print(f"       rawAABB size=({a.m_Extent.x*2:.3f},{a.m_Extent.y*2:.3f},{a.m_Extent.z*2:.3f}) "
              f"scaleChain={[round(x,5) for x in chain]}")
        print(f"       item-space centre=({(lo+hi)[0]/2:+.4f},{(lo+hi)[1]/2:+.4f},{(lo+hi)[2]/2:+.4f}) "
              f"size=({(hi-lo)[0]:.4f},{(hi-lo)[1]:.4f},{(hi-lo)[2]:.4f})")

    if tr is None:
        return
    for ch in tr.m_Children:
        if ch is None:
            continue
        cgo = ch.read()
        ref = getattr(cgo, "m_GameObject", None)
        if ref:
            walk(objects[ref.path_id], own, chain)

walk(objects[root], np.eye(4), [])
