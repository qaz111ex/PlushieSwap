"""Measure the PLAYER's hand mesh relative to the player's Hand_L / Hand_R rigs.

CharacterItems does this when an item is equipped:

    character.GetBodypartRig(BodypartType.Hand_R).transform.position = Find("Hand_R").position;
    character.GetBodypartRig(BodypartType.Hand_R).transform.rotation = Find("Hand_R").rotation;

So the item anchor drives the player's hand RIG. The visible hand is a child of that rig,
and its offset is what decides where the hand actually appears. An earlier attempt
measured the offset from the *item's* own dummy "Hand" child instead, which is a
different object entirely — that is why the grips kept landing in the wrong place.

This finds the player rig by looking for a Hand_R whose parent is an Elbow_R, and prints
the hand mesh centre in the rig's local frame.
"""
import glob
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


def local_matrix(t):
    p, q, s = t.m_LocalPosition, t.m_LocalRotation, t.m_LocalScale
    m = np.eye(4)
    m[:3, :3] = quat_mat((q.x, q.y, q.z, q.w)) @ np.diag([s.x, s.y, s.z])
    m[:3, 3] = [p.x, p.y, p.z]
    return m


def main():
    for path in [os.path.join(GAME, "resources.assets")] + sorted(
            glob.glob(os.path.join(GAME, "sharedassets*.assets"))):
        try:
            env = UnityPy.load(path)
        except Exception:
            continue

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

        # parent lookup
        parent_of = {}
        for tid, (go, t) in transforms.items():
            for ch in t.m_Children:
                if ch is not None:
                    parent_of[ch.path_id] = tid

        go_to_transform = {go: tid for tid, (go, _t) in transforms.items()}

        for go_id, name in list(names.items()):
            if name not in ("Hand_L", "Hand_R"):
                continue
            tid = go_to_transform.get(go_id)
            if tid is None:
                continue
            parent = parent_of.get(tid)
            if parent is None:
                continue
            pgo, _pt = transforms[parent]
            if names.get(pgo) not in ("Elbow_L", "Elbow_R"):
                continue

            print(f"=== PLAYER {name} (go {go_id}) in {os.path.basename(path)} ===")
            t = transforms[tid][1]
            p, q, s = t.m_LocalPosition, t.m_LocalRotation, t.m_LocalScale
            print(f"  rig localPos=({p.x:+.4f},{p.y:+.4f},{p.z:+.4f}) "
                  f"rot=({q.x:+.4f},{q.y:+.4f},{q.z:+.4f},{q.w:+.4f}) "
                  f"scale=({s.x:.4f},{s.y:.4f},{s.z:.4f})")

            stack = [(tid, np.eye(4), 0)]
            seen = set()
            while stack:
                cur, mat, depth = stack.pop()
                if cur in seen or depth > 6:
                    continue
                seen.add(cur)
                cgo, ct = transforms[cur]
                own = mat @ local_matrix(ct)

                gd = objects[cgo].read()
                for comp in gd.m_Components:
                    if comp is None:
                        continue
                    cr = objects.get(comp.path_id)
                    if cr is None or cr.type.name != "SkinnedMeshRenderer":
                        continue
                    d = cr.read()
                    mref = getattr(d, "m_Mesh", None)
                    if mref is None:
                        continue
                    mesh = mref.read()
                    a = mesh.m_LocalAABB
                    c = np.array([a.m_Center.x, a.m_Center.y, a.m_Center.z])
                    e = np.array([a.m_Extent.x, a.m_Extent.y, a.m_Extent.z])
                    oc = own[:3, :3] @ c + own[:3, 3]
                    print(f"    [{depth}] '{names[cgo]}' SkinnedMesh '{mesh.m_Name}'")
                    print(f"        centre in rig space = {np.round(oc, 5)}")
                    print(f"        extent              = {np.round(e, 4)}")

                for ch in ct.m_Children:
                    if ch is not None:
                        stack.append((ch.path_id, own, depth + 1))
            print()


if __name__ == "__main__":
    main()
