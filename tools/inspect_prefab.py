import re
import sys
import UnityPy

GAME_DATA = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
TARGET = "Bing Bong Plush"


def dump_tree(env, go_path_id, max_depth=6):
    objs = {o.path_id: o for o in env.objects}
    go = objs.get(go_path_id)
    data = go.read()

    print("=" * 70)
    print("ROOT GameObject:", data.m_Name, "path_id:", go_path_id)
    print("=" * 70)

    def walk(obj, depth):
        if depth > max_depth:
            return
        d = obj.read()
        typ = obj.type.name
        nm = getattr(d, "m_Name", "")
        pad = "  " * depth
        extra = ""
        if typ == "MeshFilter":
            mesh = d.m_Mesh
            mn = ""
            if mesh:
                try:
                    mn = mesh.read().m_Name
                except Exception:
                    mn = "?"
            extra = f" mesh={mn} ({mesh.path_id if mesh else None})"
        elif typ == "MeshRenderer":
            mats = d.m_Materials
            names = []
            for m in mats:
                if m:
                    try:
                        names.append(m.read().m_Name)
                    except Exception:
                        names.append("?")
                else:
                    names.append("None")
            extra = f" materials={names} enabled={d.m_Enabled}"
        elif typ == "AudioSource":
            ac = d.m_audioClip
            an = ""
            if ac:
                try:
                    an = ac.read().m_Name
                except Exception:
                    an = "?"
            extra = f" clip={an} vol={d.m_Volume} loop={d.m_Loop} playOnAwake={d.m_PlayOnAwake}"
        elif typ == "BoxCollider":
            extra = f" size={d.m_Size} center={d.m_Center}"
        elif typ == "SphereCollider":
            extra = f" radius={d.m_Radius} center={d.m_Center}"
        elif typ == "CapsuleCollider":
            extra = f" radius={d.m_Radius} height={d.m_Height} center={d.m_Center} dir={d.m_Direction}"
        elif typ == "SkinnedMeshRenderer":
            extra = f" mesh={d.m_Mesh.path_id if d.m_Mesh else None} roots={[r.path_id for r in (d.m_RootBones or [])]}"
        print(f"{pad}[{typ}] {nm}{extra}")

        # children
        if typ == "GameObject":
            for comp in d.m_Components:
                if comp is None:
                    continue
                c = comp.read() if comp.path_id in objs else None
                if c is None:
                    continue
                walk(objs[comp.path_id], depth + 1)
        elif typ == "Transform":
            walk_child = d.m_Children
            for ch in walk_child:
                if ch:
                    go2 = ch.read()
                    if hasattr(go2, "m_GameObject"):
                        walk(objs[go2.m_GameObject.path_id], depth + 1)

    # root may be GameObject
    d = go.read()
    print(f"[GameObject] {d.m_Name} active={d.m_IsActive} layer={d.m_Layer} tag={d.m_Tag}")
    walk(go, 0)


def main():
    needle = sys.argv[1] if len(sys.argv) > 1 else TARGET
    env = UnityPy.load(r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data\level1")
    for obj in env.objects:
        if obj.type.name != "GameObject":
            continue
        d = obj.read()
        if d.m_Name == needle:
            print("### Found in level1:", obj.path_id)
            dump_tree(env, obj.path_id)
            break


if __name__ == "__main__":
    main()
