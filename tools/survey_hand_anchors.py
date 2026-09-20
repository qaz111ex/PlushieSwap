"""Survey every Hand_L / Hand_R anchor in the game data.

CharacterItems snaps the player's hand rigs onto these nodes, position AND
rotation:

    GetBodypartRig(Hand_R).transform.position = item.transform.Find("Hand_R").position;
    GetBodypartRig(Hand_R).transform.rotation = item.transform.Find("Hand_R").rotation;

So the anchor rotation *is* the hand pose, expressed in item space. Dumping many
items side by side reveals the convention: which local axis the fingers, the palm
and the knuckles follow for a left hand and for a right hand.
"""
import os

import numpy as np
import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
TARGETS = ("Hand_L", "Hand_R")


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

    # child transform -> parent GameObject name
    parent_name = {}
    transform_of_go = {}
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
        for ch in t.m_Children:
            if ch is None:
                continue
            try:
                cgo = ch.read()
            except Exception:
                continue
            cref = getattr(cgo, "m_GameObject", None)
            if cref is not None:
                parent_name[cref.path_id] = name_of.get(ref.path_id, "?")

    items = {}
    for go_id, name in name_of.items():
        if name not in TARGETS:
            continue
        tid = transform_of_go.get(go_id)
        if tid is None:
            continue
        tr = objects[tid].read()
        p, q = tr.m_LocalPosition, tr.m_LocalRotation
        items.setdefault(parent_name.get(go_id, "?"), {})[name] = (
            np.array([p.x, p.y, p.z]), np.array([q.x, q.y, q.z, q.w]))

    both = {k: v for k, v in items.items() if len(v) == 2}
    print(f"{len(items)} items with a hand anchor, {len(both)} of them with both\n")

    for item in sorted(both):
        L = both[item]["Hand_L"]
        R = both[item]["Hand_R"]
        print(f"{item}")
        for tag, (pos, quat) in (("L", L), ("R", R)):
            m = quat_mat(quat)
            print(f"  Hand_{tag} pos=({pos[0]:+.4f},{pos[1]:+.4f},{pos[2]:+.4f})")
            print(f"         right={np.round(m[:, 0], 3)}")
            print(f"         up   ={np.round(m[:, 1], 3)}")
            print(f"         fwd  ={np.round(m[:, 2], 3)}")


if __name__ == "__main__":
    main()
