"""Dump the full transform hierarchy of the vanilla BingBong prefab.

The replacement plush must publish the same Hand_L / Hand_R anchors the vanilla
model does, because CharacterItems snaps the player's hand rigs to them:

    character.GetBodypartRig(Hand_R).transform.position = GetItemPosRightWorld(item);
    character.GetBodypartRig(Hand_R).transform.rotation = GetItemRotRightWorld(item);

and both read straight off `item.transform.Find("Hand_R")`.
"""
import os

import numpy as np
import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
WANTED = ("BingBong", "BingBong_Prop Variant")


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
    objects = {o.path_id: o for o in res.objects}

    # map transform -> owning GameObject
    owner = {}
    for o in res.objects:
        if o.type.name != "Transform":
            continue
        try:
            t = o.read()
        except Exception:
            continue
        ref = getattr(t, "m_GameObject", None)
        if ref is not None:
            owner[o.path_id] = ref.path_id

    roots = []
    for o in res.objects:
        if o.type.name != "GameObject":
            continue
        try:
            gd = o.read()
        except Exception:
            continue
        if gd.m_Name in WANTED:
            roots.append((o.path_id, gd.m_Name))

    for pid, name in roots:
        print(f"=== root candidate: {name} (path_id={pid}) ===")

    for pid, name in roots:
        go = objects[pid].read()
        tr = None
        for comp in go.m_Components:
            if comp is None:
                continue
            cr = objects.get(comp.path_id)
            if cr is not None and cr.type.name == "Transform":
                tr = cr.read()
                break
        if tr is None:
            print(f"{name}: no transform")
            continue

        print(f"--- {name} (path_id={pid}) children of the item root ---")
        for ch in tr.m_Children:
            if ch is None:
                continue
            cgo = ch.read()
            ref = getattr(cgo, "m_GameObject", None)
            if ref is None:
                continue
            gd = objects[ref.path_id].read()
            ctr = None
            for comp in gd.m_Components:
                if comp is None:
                    continue
                cr = objects.get(comp.path_id)
                if cr is not None and cr.type.name == "Transform":
                    ctr = cr.read()
                    break
            if ctr is None:
                continue
            p, q, s = ctr.m_LocalPosition, ctr.m_LocalRotation, ctr.m_LocalScale
            print(f"  child {gd.m_Name:20s} localPos=({p.x:+.5f},{p.y:+.5f},{p.z:+.5f}) "
                  f"localRot=({q.x:+.5f},{q.y:+.5f},{q.z:+.5f},{q.w:+.5f}) "
                  f"scale=({s.x:.4f},{s.y:.4f},{s.z:.4f})")
            for gch in ctr.m_Children:
                if gch is None:
                    continue
                gg = gch.read()
                gref = getattr(gg, "m_GameObject", None)
                if gref is None:
                    continue
                ggd = objects[gref.path_id].read()
                gct = None
                for comp in ggd.m_Components:
                    if comp is None:
                        continue
                    cr = objects.get(comp.path_id)
                    if cr is not None and cr.type.name == "Transform":
                        gct = cr.read()
                        break
                if gct is None:
                    continue
                gp, gq, gs = gct.m_LocalPosition, gct.m_LocalRotation, gct.m_LocalScale
                print(f"    grandchild {ggd.m_Name:20s} localPos=({gp.x:+.5f},{gp.y:+.5f},{gp.z:+.5f}) "
                      f"localRot=({gq.x:+.5f},{gq.y:+.5f},{gq.z:+.5f},{gq.w:+.5f}) "
                      f"scale=({gs.x:.4f},{gs.y:.4f},{gs.z:.4f})")

                # third level, where Hand_L / Hand_R sit
                for g3 in gct.m_Children:
                    if g3 is None:
                        continue
                    r3 = g3.read()
                    ref3 = getattr(r3, "m_GameObject", None)
                    if ref3 is None:
                        continue
                    g3d = objects[ref3.path_id].read()
                    t3 = None
                    for comp in g3d.m_Components:
                        if comp is None:
                            continue
                        cr = objects.get(comp.path_id)
                        if cr is not None and cr.type.name == "Transform":
                            t3 = cr.read()
                            break
                    if t3 is None:
                        continue
                    p3, q3, s3 = t3.m_LocalPosition, t3.m_LocalRotation, t3.m_LocalScale
                    print(f"      L3 {g3d.m_Name:20s} localPos=({p3.x:+.5f},{p3.y:+.5f},{p3.z:+.5f}) "
                          f"localRot=({q3.x:+.5f},{q3.y:+.5f},{q3.z:+.5f},{q3.w:+.5f}) "
                          f"scale=({s3.x:.4f},{s3.y:.4f},{s3.z:.4f})")
        print()


if __name__ == "__main__":
    main()
