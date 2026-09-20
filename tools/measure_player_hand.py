"""Measure the PLAYER's hand skinned mesh relative to the player's Hand bone.

CharacterItems.AttachItem does:

    GetBodypartRig(Hand_R).transform.position = GetItemPosRightWorld(item);
    GetBodypartRig(Hand_R).transform.rotation = GetItemRotRightWorld(item);

`GetBodypartRig(Hand_R)` is the player's Hand bone. The visible hand is a
SkinnedMeshRenderer ("Chubby Hand") bound to that bone chain, so the bone is the
WRIST and the palm/fingers extend away from it along the bone's forward axis.

That offset is the whole reason "put the anchor on the waist" does not put the HAND
on the waist. This finds the player character prefab, locates the Hand bones, and
reports the hand mesh bounds in the bone's local frame so the offset can be measured
instead of guessed.
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


def scan(path):
    try:
        env = UnityPy.load(path)
    except Exception:
        return
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

    parent_of = {}
    for tid, (_go, t) in transforms.items():
        for ch in t.m_Children:
            if ch is not None:
                parent_of[ch.path_id] = tid

    go_to_transform = {go: tid for tid, (go, _t) in transforms.items()}

    # Walk up from a transform to the root GameObject name, for context.
    def path_of(tid, limit=12):
        parts = []
        cur = tid
        n = 0
        while cur is not None and n < limit:
            go, _t = transforms[cur]
            parts.append(names.get(go, "?"))
            cur = parent_of.get(cur)
            n += 1
        return "/".join(reversed(parts))

    for o in env.objects:
        if o.type.name != "SkinnedMeshRenderer":
            continue
        try:
            d = o.read()
        except Exception:
            continue
        mref = getattr(d, "m_Mesh", None)
        if mref is None:
            continue
        try:
            mesh = mref.read()
        except Exception:
            continue
        if mesh.m_Name != "Chubby Hand":
            continue

        go_ref = getattr(d, "m_GameObject", None)
        if go_ref is None:
            continue
        tid = go_to_transform.get(go_ref.path_id)
        if tid is None:
            continue

        root_bone = getattr(d, "m_RootBone", None)
        root_tid = None
        if root_bone is not None:
            root_tid = go_to_transform.get(root_bone.path_id)
        a = mesh.m_LocalAABB
        centre = np.array([a.m_Center.x, a.m_Center.y, a.m_Center.z])
        extent = np.array([a.m_Extent.x, a.m_Extent.y, a.m_Extent.z])

        print(f"=== {os.path.basename(path)} ===")
        print(f"  renderer on   : {path_of(tid)}")
        print(f"  root bone     : {names.get(root_bone.path_id) if root_bone else '?'}"
              f"  path={path_of(root_tid) if root_tid else '?'}")
        print(f"  mesh bounds centre={np.round(centre, 4)} extent={np.round(extent, 4)}")

        # Hand bone: find a descendant named Hand_L / Hand_R and express the mesh
        # bounds centre in its local frame.
        stack = [(tid, np.eye(4), 0)]
        seen = set()
        while stack:
            cur, mat, depth = stack.pop()
            if cur in seen or depth > 8:
                continue
            seen.add(cur)
            cgo, ct = transforms[cur]
            own = mat @ local_matrix(ct)
            n = names.get(cgo, "")
            if n in ("Hand_L", "Hand_R"):
                inv = np.linalg.inv(own)
                c_local = inv[:3, :3] @ centre + inv[:3, 3]
                print(f"  {n}: mesh centre in bone space = {np.round(c_local, 4)}"
                      f"  (bone path {path_of(cur)})")
            for ch in ct.m_Children:
                if ch is not None:
                    stack.append((ch.path_id, own, depth + 1))


def main():
    files = [os.path.join(GAME, "resources.assets")]
    files += sorted(glob.glob(os.path.join(GAME, "sharedassets*.assets")))
    files += sorted(glob.glob(os.path.join(GAME, "level*")))
    for f in files:
        if os.path.isfile(f):
            scan(f)


if __name__ == "__main__":
    main()
