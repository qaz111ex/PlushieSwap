"""Full component dump of the BingBong item prefab.

Guessing at the grip has failed repeatedly, so this prints everything the prefab
actually contains: every GameObject, its components by type and name, and the local
transform of each. That answers the questions that matter — which object the Item
component lives on, whether Hand_L / Hand_R carry scripts of their own, and what the
real transform chain from the item root down to the plush mesh is.
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
TARGET = "BingBong_Prop Variant"


def fmt(v):
    return f"({v.x:+.4f},{v.y:+.4f},{v.z:+.4f})"


def main():
    env = UnityPy.load(os.path.join(GAME, "resources.assets"))
    objects = {o.path_id: o for o in env.objects}

    go = None
    for o in env.objects:
        if o.type.name != "GameObject":
            continue
        try:
            d = o.read()
        except Exception:
            continue
        if d.m_Name == TARGET:
            go = (o.path_id, d)
            break
    if go is None:
        print("not found")
        return
    root_id, root = go
    print(f"=== {TARGET} (path_id={root_id}) ===")
    print(f"components on the root:")
    dump_components(objects, root, "  ")

    # root's own transform (the prefab root rotation)
    for comp in root.m_Components:
        if comp is None:
            continue
        cr = objects.get(comp.path_id)
        if cr is not None and cr.type.name == "Transform":
            t = cr.read()
            print(f"  root transform: pos={fmt(t.m_LocalPosition)} "
                  f"rot=({t.m_LocalRotation.x:+.4f},{t.m_LocalRotation.y:+.4f},"
                  f"{t.m_LocalRotation.z:+.4f},{t.m_LocalRotation.w:+.4f}) "
                  f"scale={fmt(t.m_LocalScale)}")
            walk(objects, t, depth=1, limit=4)

    # what else references a Hand_L / Hand_R named object?
    print()
    print("=== objects whose name is Hand_L / Hand_R in this file ===")
    for o in env.objects:
        if o.type.name != "GameObject":
            continue
        try:
            d = o.read()
        except Exception:
            continue
        if d.m_Name in ("Hand_L", "Hand_R"):
            print(f"  {d.m_Name} path_id={o.path_id}")
            dump_components(objects, d, "    ")


def dump_components(objects, gd, indent):
    for comp in gd.m_Components:
        if comp is None:
            continue
        cr = objects.get(comp.path_id)
        if cr is None:
            continue
        try:
            d = cr.read()
        except Exception as exc:
            print(f"{indent}{cr.type.name}: <unreadable {exc}>")
            continue
        name = getattr(d, "m_Name", "")
        extra = ""
        if cr.type.name == "MonoBehaviour":
            script = getattr(d, "m_Script", None)
            cls = ""
            if script is not None:
                try:
                    cls = script.read().m_ClassName
                except Exception:
                    cls = "?"
            extra = f" script={cls}"
        if cr.type.name == "MeshFilter" and getattr(d, "m_Mesh", None) is not None:
            try:
                extra = f" mesh={d.m_Mesh.read().m_Name}"
            except Exception:
                pass
        print(f"{indent}{cr.type.name}: '{name}'{extra}")


def walk(objects, t, depth, limit):
    if depth > limit:
        return
    for ch in t.m_Children:
        if ch is None:
            continue
        cgo = ch.read()
        ref = getattr(cgo, "m_GameObject", None)
        if ref is None:
            continue
        gd = objects[ref.path_id].read()
        ct = None
        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = objects.get(comp.path_id)
            if cr is not None and cr.type.name == "Transform":
                ct = cr.read()
                break
        indent = "  " * depth
        p, q, s = ct.m_LocalPosition, ct.m_LocalRotation, ct.m_LocalScale
        print(f"{indent}{gd.m_Name}")
        print(f"{indent}  pos={fmt(p)} rot=({q.x:+.4f},{q.y:+.4f},{q.z:+.4f},{q.w:+.4f}) "
              f"scale=({s.x:.4f},{s.y:.4f},{s.z:.4f})")
        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = objects.get(comp.path_id)
            if cr is None:
                continue
            if cr.type.name == "Transform":
                continue
            try:
                d = cr.read()
            except Exception:
                continue
            name = getattr(d, "m_Name", "")
            extra = ""
            if cr.type.name == "MonoBehaviour":
                script = getattr(d, "m_Script", None)
                if script is not None:
                    try:
                        extra = f" script={script.read().m_ClassName}"
                    except Exception:
                        pass
            print(f"{indent}    [{cr.type.name}] {name}{extra}")
        walk(objects, ct, depth + 1, limit)


if __name__ == "__main__":
    main()
