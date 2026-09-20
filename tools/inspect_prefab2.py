import sys
import UnityPy

GAME_DATA = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
LEVEL = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data\level1"

INTERESTING = {
    "MeshFilter", "MeshRenderer", "SkinnedMeshRenderer", "AudioSource",
    "BoxCollider", "SphereCollider", "CapsuleCollider", "MeshCollider",
    "MonoBehaviour", "Animator", "Rigidbody",
}


def obj_name(reader):
    try:
        d = reader.read()
    except Exception:
        return None, None
    return reader.type.name, d


def dump(env, root_go_id, max_depth=8):
    objs = {o.path_id: o for o in env.objects}
    go = objs[root_go_id]
    d = go.read()
    print(f"[GameObject] {d.m_Name} path_id={root_go_id} active={d.m_IsActive} layer={d.m_Layer}")

    seen = set()

    def walk_go(go_reader, depth):
        if depth > max_depth or go_reader.path_id in seen:
            return
        seen.add(go_reader.path_id)
        pad = "  " * depth
        gd = go_reader.read()
        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = objs.get(comp.path_id)
            if cr is None:
                continue
            typ = cr.type.name
            cd = cr.read()
            nm = getattr(cd, "m_Name", "")
            extra = ""
            if typ == "MeshFilter":
                m = cd.m_Mesh
                mn = m.read().m_Name if m else None
                extra = f" mesh={mn}"
            elif typ == "MeshRenderer":
                mats = []
                for mm in cd.m_Materials:
                    mats.append(mm.read().m_Name if mm else "None")
                extra = f" mats={mats} enabled={cd.m_Enabled}"
            elif typ == "SkinnedMeshRenderer":
                m = cd.m_Mesh
                extra = f" mesh={m.read().m_Name if m else None} enabled={cd.m_Enabled}"
            elif typ == "AudioSource":
                ac = cd.m_audioClip
                extra = (f" clip={ac.read().m_Name if ac else None} vol={cd.m_Volume} "
                         f"loop={cd.m_Loop} awake={cd.m_PlayOnAwake} spatial={cd.m_SpatialBlend} "
                         f"min={cd.m_MinDistance} max={cd.m_MaxDistance}")
            elif typ in ("BoxCollider", "SphereCollider", "CapsuleCollider"):
                extra = " collider"
            elif typ == "MonoBehaviour":
                sc = cd.m_Script
                sn = sc.read().m_ClassName if sc else "?"
                extra = f" script={sn}"
            print(f"{pad}<{typ}> {nm}{extra}")

        # recurse children
        tr = None
        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = objs.get(comp.path_id)
            if cr is None or cr.type.name != "Transform":
                continue
            tr = cr.read()
            break
        if tr is None:
            return
        for ch in tr.m_Children:
            if ch is None:
                continue
            chgo = ch.read()
            if hasattr(chgo, "m_GameObject") and chgo.m_GameObject:
                walk_go(objs[chgo.m_GameObject.path_id], depth + 1)

    walk_go(go, 0)


def main():
    env = UnityPy.load(LEVEL)
    for needle in sys.argv[1:]:
        print("\n" + "#" * 72)
        print("# SEARCH:", needle)
        print("#" * 72)
        found = 0
        for obj in env.objects:
            if obj.type.name != "GameObject":
                continue
            try:
                d = obj.read()
            except Exception:
                continue
            if d.m_Name == needle:
                dump(env, obj.path_id)
                print()
                found += 1
                if found >= 4:
                    break


if __name__ == "__main__":
    main()
