"""Search all assets files for an Item whose UIData/itemName mentions BingBong."""
import os
import sys

import UnityPy

GAME_DATA = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def files():
    for n in sorted(os.listdir(GAME_DATA)):
        p = os.path.join(GAME_DATA, n)
        if not os.path.isfile(p):
            continue
        if n.endswith((".resS", ".resource")):
            continue
        yield n, p


def main():
    hits = []
    for name, path in files():
        try:
            env = UnityPy.load(path)
        except Exception:
            continue
        for o in env.objects:
            if o.type.name not in ("MonoBehaviour", "GameObject"):
                continue
            try:
                tree = o.read_typetree()
            except Exception:
                continue
            if not isinstance(tree, dict):
                continue

            blob = str(tree)
            if "BingBong" not in blob and "Bing Bong" not in blob:
                continue
            ud = tree.get("UIData")
            if isinstance(ud, dict) and ud.get("itemName"):
                hits.append((name, o.path_id, tree.get("m_Name"), ud.get("itemName"),
                             tree.get("itemID"), ud.get("icon")))

    for h in hits:
        print(h)


if __name__ == "__main__":
    main()
