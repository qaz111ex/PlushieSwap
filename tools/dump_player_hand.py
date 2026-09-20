"""Dump the PLAYER's own Hand_L / Hand_R bodypart rigs.

CharacterItems copies an item's `Hand_R` node rotation straight onto the player's
`Hand_R` bodypart rig:

    GetBodypartRig(Hand_R).transform.rotation = item.transform.Find("Hand_R").rotation;

so the item anchor is authored in the player rig's own local frame. To author a
sensible grip for the plush, the rig's rest pose and the hand mesh's orientation
inside it have to be known first.
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


def main():
    res = UnityPy.load(os.path.join(GAME, "resources.assets"))
    objects = {o.path_id: o for o in res.objects}

    name_of = {}
    for o in res.objects:
        if o.type.name != "GameObject":
            continue
        try:
            name_of[o.path_id] = o.read().m_Name
        except Exception:
            pass

    transform_of_go = {}
    go_of_transform = {}
    children = {}
    for o in res.objects:
        if o.type.name != "Transform":
            continue
        try:
            t = o.read()
        except Exception:
            continue
        ref = getattr(t, "m_GameObject", None)
        if ref is None:
            continue
        transform_of_go[ref.path_id] = o.path_id
        go_of_transform[o.path_id] = ref.path_id
        children[o.path_id] = [c.path_id for c in t.m_Children if c is not None]

    # the player's own rig: Hand_R whose parent is Elbow_R
    targets = []
    for go_id, name in name_of.items():
        if name not in ("Hand_L", "Hand_R"):
            continue
        tid = transform_of_go.get(go_id)
        if tid is None:
            continue
        tr = objects[tid].read()
        for ch in tr.m_Children:
            if ch is None:
                continue
            cgo = ch.read()
            cref = getattr(cgo, "m_GameObject", None)
            if cref is None:
                continue
            cname = name_of.get(cref.path_id, "?")
            if cname in ("Elbow_L", "Elbow_R"):
                targets.append((go_id, name, tid))

    for go_id, name, tid in targets:
        print(f"=== player rig {name} (gameObject path_id={go_id}) ===")
        tr = objects[tid].read()
        p, q, s = tr.m_LocalPosition, tr.m_LocalRotation, tr.m_LocalScale
        m = quat_mat((q.x, q.y, q.z, q.w))
        print(f"  localPosition=({p.x:+.5f},{p.y:+.5f},{p.z:+.5f})")
        print(f"  localRotation=({q.x:+.5f},{q.y:+.5f},{q.z:+.5f},{q.w:+.5f})")
        print(f"  localScale=({s.x:.5f},{s.y:.5f},{s.z:.5f})")
        print(f"  local axes: right={np.round(m[:,0],4)} up={np.round(m[:,1],4)} fwd={np.round(m[:,2],4)}")

        for ch in tr.m_Children:
            if ch is None:
                continue
            cgo = ch.read()
            cref = getattr(cgo, "m_GameObject", None)
            if cref is None:
                continue
            cname = name_of.get(cref.path_id, "?")
            cgd = objects[cref.path_id].read()
            ct = None
            for comp in cgd.m_Components:
                if comp is None:
                    continue
                cr = objects.get(comp.path_id)
                if cr is not None and cr.type.name == "Transform":
                    ct = cr.read()
                    break
            if ct is None:
                continue
            cp, cq, cs = ct.m_LocalPosition, ct.m_LocalRotation, ct.m_LocalScale
            print(f"  child {cname:24s} pos=({cp.x:+.4f},{cp.y:+.4f},{cp.z:+.4f}) "
                  f"rot=({cq.x:+.4f},{cq.y:+.4f},{cq.z:+.4f},{cq.w:+.4f}) "
                  f"scale=({cs.x:.4f},{cs.y:.4f},{cs.z:.4f})")
            for comp in cgd.m_Components:
                if comp is None:
                    continue
                cr = objects.get(comp.path_id)
                if cr is None or cr.type.name != "MeshFilter":
                    continue
                mf = cr.read()
                mesh_ref = mf.m_Mesh
                if mesh_ref is None:
                    continue
                mesh = mesh_ref.read()
                a = mesh.m_LocalAABB
                print(f"      mesh '{mesh.m_Name}' aabb centre="
                      f"({a.m_Center.x:+.4f},{a.m_Center.y:+.4f},{a.m_Center.z:+.4f}) "
                      f"extent=({a.m_Extent.x:.4f},{a.m_Extent.y:.4f},{a.m_Extent.z:.4f})")
        print()


if __name__ == "__main__":
    main()
