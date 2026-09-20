import os
import sys
import UnityPy

GAME_DATA = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
CACHE = {}


def load(name):
    if name not in CACHE:
        CACHE[name] = UnityPy.load(os.path.join(GAME_DATA, name))
    return CACHE[name]


def scan_files():
    names = []
    for n in sorted(os.listdir(GAME_DATA)):
        p = os.path.join(GAME_DATA, n)
        if not os.path.isfile(p):
            continue
        if n.endswith(".resS") or n.endswith(".resource"):
            continue
        names.append(n)
    return names


def main():
    needle = sys.argv[1] if len(sys.argv) > 1 else "bingbong"
    typ_filter = sys.argv[2] if len(sys.argv) > 2 else None
    for fn in scan_files():
        try:
            env = load(fn)
        except Exception as e:
            print("SKIP", fn, e)
            continue
        for obj in env.objects:
            if typ_filter and obj.type.name != typ_filter:
                continue
            if not typ_filter and obj.type.name not in ("AudioClip", "Texture2D", "Material", "Mesh"):
                continue
            try:
                d = obj.read()
            except Exception:
                continue
            nm = str(getattr(d, "m_Name", "") or "")
            if needle in nm.lower().replace(" ", ""):
                extra = ""
                if obj.type.name == "AudioClip":
                    extra = f" len={d.m_Length:.3f}s freq={d.m_Frequency} ch={d.m_Channels}"
                if obj.type.name == "Texture2D":
                    extra = f" {d.m_Width}x{d.m_Height} fmt={d.m_TextureFormat}"
                print(f"{fn}\t{obj.type.name}\tpid={obj.path_id}\t{nm}{extra}")


if __name__ == "__main__":
    main()
