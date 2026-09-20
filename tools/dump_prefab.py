import os
import sys
import UnityPy

GAME_DATA = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def read_safe(reader):
    try:
        return reader.read()
    except Exception as e:
        return None


def dump(env, root_go_id, max_depth=10, out=None):
    objs = {o.path_id: o for o in env.objects}
    go = objs[root_go_id]
    d = go.read()
    print(f"[GameObject] {d.m_Name} pid={root_go_id} active={d.m_IsActive} layer={d.m_Layer}",
          file=out)
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
                print(f"{pad}<{typ}> [unreadable]", file=out)
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
                    extra = f" mesh={m.read().m_Name if m else None} enabled={cd.m_Enabled}"
                elif typ == "AudioSource":
                    ac = cd.m_audioClip
                    extra = (f" clip={ac.read().m_Name if ac else None} vol={cd.m_Volume} "
                             f"loop={cd.m_Loop} awake={cd.m_PlayOnAwake} spatial={cd.m_SpatialBlend} "
                             f"min={cd.m_MinDistance} max={cd.m_MaxDistance} pitch={cd.m_Pitch}")
                elif typ == "BoxCollider":
                    extra = f" size={cd.m_Size} center={cd.m_Center} enabled={cd.m_Enabled} layer={gd.m_Layer}"
                elif typ == "SphereCollider":
                    extra = f" radius={cd.m_Radius} center={cd.m_Center} enabled={cd.m_Enabled}"
                elif typ == "CapsuleCollider":
                    extra = (f" radius={cd.m_Radius} height={cd.m_Height} center={cd.m_Center} "
                             f"dir={cd.m_Direction} enabled={cd.m_Enabled}")
                elif typ == "MonoBehaviour":
                    sc = cd.m_Script
                    sn = sc.read().m_ClassName if sc else "?"
                    extra = f" script={sn}"
                    if sn in ("Item",):
                        extra += f" itemID={getattr(cd,'itemID',None)} mass={getattr(cd,'mass',None)}"
            except Exception as e:
                extra = f" [extra-err {e}]"
            print(f"{pad}<{typ}> {nm}{extra}", file=out)

            if typ == "Transform":
                tr = cd

        if tr is None:
            return
        for ch in tr.m_Children:
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
    needles = sys.argv[2:]
    env = UnityPy.load(os.path.join(GAME_DATA, level))
    for needle in needles:
        print("\n" + "#" * 74)
        print("# " + level + " :: " + needle)
        print("#" * 74)
        cnt = 0
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
                cnt += 1
                if cnt >= 3:
                    break


if __name__ == "__main__":
    main()
