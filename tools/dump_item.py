import os
import sys
import UnityPy

GAME_DATA = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def read_safe(reader):
    try:
        return reader.read()
    except Exception:
        return None


def dump(env, root_go_id, max_depth=12, limit_children=True):
    objs = {o.path_id: o for o in env.objects}
    go = objs[root_go_id]
    d = go.read()
    print(f"[GameObject] {d.m_Name} pid={root_go_id} active={d.m_IsActive} layer={d.m_Layer}")
    seen = set()

    def walk(go_reader, depth):
        if depth > max_depth or go_reader.path_id in seen:
            return
        seen.add(go_reader.path_id)
        pad = "  " * depth
        gd = go_reader.read()
        tr = None
        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = objs.get(comp.path_id)
            if cr is None:
                continue
            typ = cr.type.name
            cd = read_safe(cr)
            if cd is None:
                print(f"{pad}<{typ}> [unreadable]")
                continue
            nm = getattr(cd, "m_Name", "")
            extra = ""
            try:
                if typ == "MeshFilter":
                    m = cd.m_Mesh
                    extra = f" mesh={m.read().m_Name if m else None}"
                elif typ == "MeshRenderer":
                    mats = [mm.read().m_Name if mm else "None" for mm in cd.m_Materials]
                    extra = f" mats={mats} enabled={cd.m_Enabled}"
                elif typ == "SkinnedMeshRenderer":
                    m = cd.m_Mesh
                    extra = f" mesh={m.read().m_Name if m else None}"
                elif typ == "AudioSource":
                    ac = cd.m_audioClip
                    extra = f" clip={ac.read().m_Name if ac else None}"
                elif typ == "MonoBehaviour":
                    sc = cd.m_Script
                    sn = sc.read().m_ClassName if sc else "?"
                    extra = f" script={sn}"
                    for attr in ("itemID", "mass", "carryWeight", "canBackpack", "canPocket",
                                 "defaultPos", "defaultForward", "totalUses", "canUseOnFriend",
                                 "isSecretlyOtherItemPrefab", "gliderHold", "rightHandOnly"):
                        if hasattr(cd, attr):
                            extra += f" {attr}={getattr(cd, attr)}"
                elif typ == "Transform":
                    extra = f" pos={cd.m_LocalPosition} rot={cd.m_LocalRotation} scale={cd.m_LocalScale} go={gd.m_Name}"
            except Exception as e:
                extra = f" [err {e}]"
            print(f"{pad}<{typ}> {nm}{extra}")
            if typ == "Transform":
                tr = cd

        if tr is None:
            return
        kids = list(tr.m_Children)
        for ch in kids:
            if ch is None:
                continue
            cgo = read_safe(ch)
            if cgo is None:
                continue
            goref = getattr(cgo, "m_GameObject", None)
            if goref:
                walk(objs[goref.path_id], depth + 1)

    walk(go, 0)


def main():
    level = sys.argv[1]
    needle = sys.argv[2]
    env = UnityPy.load(os.path.join(GAME_DATA, level))
    cnt = 0
    for obj in env.objects:
        if obj.type.name != "GameObject":
            continue
        try:
            d = obj.read()
        except Exception:
            continue
        if d.m_Name == needle:
            print("\n" + "#" * 74)
            print(f"# {level} :: {needle}  pid={obj.path_id}")
            print("#" * 74)
            dump(env, obj.path_id)
            cnt += 1
            if cnt >= 2:
                break


if __name__ == "__main__":
    main()
