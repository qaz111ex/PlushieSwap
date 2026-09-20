import os
import sys
import UnityPy

GAME_DATA = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def iter_env():
    for name in sorted(os.listdir(GAME_DATA)):
        path = os.path.join(GAME_DATA, name)
        if not os.path.isfile(path):
            continue
        if name.endswith(".resS") or name.endswith(".resource"):
            continue
        if not (name.startswith("level") or name.startswith("sharedassets") or
                name.startswith("resources") or name.startswith("globalgamemanagers")):
            continue
        if name.endswith(".assets"):
            pass
        try:
            yield name, UnityPy.load(path)
        except Exception as e:
            print("SKIP", name, e)


def main():
    needle = "bingbong"
    for name, env in iter_env():
        for obj in env.objects:
            if obj.type.name not in ("GameObject", "MonoBehaviour", "Texture2D", "AudioClip", "Mesh"):
                continue
            try:
                data = obj.read()
            except Exception:
                continue
            obj_name = getattr(data, "m_Name", None) or getattr(data, "name", None) or ""
            if needle in str(obj_name).lower().replace(" ", ""):
                print(f"{name}\t{obj.type.name}\tpath_id={obj.path_id}\tname={obj_name}")


if __name__ == "__main__":
    main()
