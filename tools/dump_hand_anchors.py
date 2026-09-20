"""Dump the vanilla BingBong prefab's Hand_L / Hand_R anchor transforms.

CharacterItems.AttachItem snaps the player's hand rigs to

    item.transform.Find("Hand_R").position / .rotation

so the replacement's anchors must reproduce not just the position but the
rotation of the vanilla ones. This prints both, in item-root space.
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

    found = []

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
        local = None
        if tr is not None:
            p, q, s = tr.m_LocalPosition, tr.m_LocalRotation, tr.m_LocalScale
            local = ((p.x, p.y, p.z), (q.x, q.y, q.z, q.w), (s.x, s.y, s.z))
            own = mat @ trs(local[0], local[1], local[2])

        if gd.m_Name in ("Hand_L", "Hand_R"):
            found.append((gd.m_Name, local, own, path))

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

    if not found:
        print("no Hand_L / Hand_R nodes in this prefab")
    for name, local, own, path in found:
        (p, q, s) = local
        print(f"{name}  path={path}")
        print(f"   localPosition = ({p[0]:+.5f}, {p[1]:+.5f}, {p[2]:+.5f})")
        print(f"   localRotation = ({q[0]:+.5f}, {q[1]:+.5f}, {q[2]:+.5f}, {q[3]:+.5f})")
        print(f"   localScale    = ({s[0]:+.5f}, {s[1]:+.5f}, {s[2]:+.5f})")
        euler = np.degrees(np.array([
            np.arctan2(own[2, 1], own[2, 2]),
            np.arctan2(-own[2, 0], np.hypot(own[2, 1], own[2, 2])),
            np.arctan2(own[1, 0], own[0, 0]),
        ]))
        print(f"   root-space euler (deg) = ({euler[0]:+.2f}, {euler[1]:+.2f}, {euler[2]:+.2f})")
        print(f"   root-space position    = ({own[0,3]:+.5f}, {own[1,3]:+.5f}, {own[2,3]:+.5f})")
        print(f"   root-space forward     = ({own[0,2]:+.4f}, {own[1,2]:+.4f}, {own[2,2]:+.4f})")
        print(f"   root-space up          = ({own[0,1]:+.4f}, {own[1,1]:+.4f}, {own[2,1]:+.4f})")
        print()


if __name__ == "__main__":
    main()
