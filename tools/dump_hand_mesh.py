"""Measure the player's hand mesh inside the vanilla grip anchor.

CharacterItems sets the player's hand RIG to the item anchor's position and rotation:

    GetBodypartRig(Hand_L).transform.position = Find("Hand_L").position;
    GetBodypartRig(Hand_L).transform.rotation = Find("Hand_L").rotation;

The hand model is a child of that rig, offset from the rig origin by its own local
transform, so the anchor's ROTATION swings the visible hand around the anchor point.
The anchor is therefore the wrist pivot, not the hand's centre. This prints the hand
mesh centroid expressed in the anchor's local frame — the offset a grip point has to
account for.
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


class Scene:
    def __init__(self, path):
        self.env = UnityPy.load(path)
        self.objects = {o.path_id: o for o in self.env.objects}
        self.meshes = {}
        for o in self.env.objects:
            if o.type.name != "Mesh":
                continue
            try:
                self.meshes[o.path_id] = o.read()
            except Exception:
                pass

    def game_objects(self):
        for o in self.env.objects:
            if o.type.name != "GameObject":
                continue
            try:
                yield o.path_id, o.read()
            except Exception:
                continue

    def transform_of(self, game_object_id):
        """Return (transform_id, transform)."""
        gd = self.objects[game_object_id].read()
        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = self.objects.get(comp.path_id)
            if cr is not None and cr.type.name == "Transform":
                return comp.path_id, cr.read()
        return None, None

    def children(self, transform_id):
        tr = self.objects[transform_id].read()
        out = []
        for ch in tr.m_Children:
            if ch is None:
                continue
            cgo = ch.read()
            ref = getattr(cgo, "m_GameObject", None)
            if ref is None:
                continue
            gd = self.objects[ref.path_id].read()
            ctr_id, ctr = self.transform_of(ref.path_id)
            if ctr is None:
                continue
            out.append((gd.m_Name, ctr_id, ctr, gd))
        return out


def local_matrix(tr):
    p, q, s = tr.m_LocalPosition, tr.m_LocalRotation, tr.m_LocalScale
    m = np.eye(4)
    m[:3, :3] = quat_mat((q.x, q.y, q.z, q.w)) @ np.diag([s.x, s.y, s.z])
    m[:3, 3] = [p.x, p.y, p.z]
    return m


def main():
    sc = Scene(os.path.join(GAME, "resources.assets"))

    root_id = None
    for go_id, gd in sc.game_objects():
        if gd.m_Name == "BingBong_Prop Variant":
            root_id = go_id
            break
    if root_id is None:
        print("prefab not found")
        return

    root_tr_id, root_tr = sc.transform_of(root_id)
    for name, go_id, tr, gd in sc.children(root_tr_id):
        if name not in ("Hand_L", "Hand_R"):
            continue
        print(f"=== {name} ===")
        anchor = local_matrix(tr)
        p, q = tr.m_LocalPosition, tr.m_LocalRotation
        print(f"  anchor pos=({p.x:+.5f},{p.y:+.5f},{p.z:+.5f}) "
              f"rot=({q.x:+.5f},{q.y:+.5f},{q.z:+.5f},{q.w:+.5f})")

        for cname, cgo_id, ctr, cgd in sc.children(go_id):
            child = local_matrix(ctr)
            to_anchor = np.linalg.inv(anchor) @ child
            print(f"  child '{cname}'")
            print(f"     child local matrix translation = "
                  f"{np.round(child[:3, 3], 5)}")
            print(f"     in ANCHOR space (translation)   = "
                  f"{np.round(to_anchor[:3, 3], 5)}")
            for comp in cgd.m_Components:
                if comp is None:
                    continue
                cr = sc.objects.get(comp.path_id)
                if cr is None or cr.type.name != "MeshFilter":
                    continue
                mf = cr.read()
                if mf.m_Mesh is None:
                    continue
                mesh = sc.meshes.get(mf.m_Mesh.path_id)
                if mesh is None:
                    continue
                aabb = mesh.m_LocalAABB
                centre = np.array([aabb.m_Center.x, aabb.m_Center.y, aabb.m_Center.z])
                extent = np.array([aabb.m_Extent.x, aabb.m_Extent.y, aabb.m_Extent.z])
                c_anchor = to_anchor[:3, :3] @ centre + to_anchor[:3, 3]
                print(f"     mesh '{mesh.m_Name}'")
                print(f"       aabb centre/extent (mesh space) = "
                      f"{np.round(centre, 4)} / {np.round(extent, 4)}")
                print(f"       aabb centre in ANCHOR space     = {np.round(c_anchor, 5)}")
        print()


if __name__ == "__main__":
    main()
