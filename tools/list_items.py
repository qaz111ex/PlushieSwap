"""List every Item UIData found across all asset files."""
import os
import re

import UnityPy

GAME_DATA = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def files():
    for n in sorted(os.listdir(GAME_DATA)):
        p = os.path.join(GAME_DATA, n)
        if os.path.isfile(p) and not n.endswith((".resS", ".resource")):
            yield n, p


found = {}
for name, path in files():
    try:
        env = UnityPy.load(path)
    except Exception:
        continue
    for o in env.objects:
        if o.type.name != "MonoBehaviour":
            continue
        try:
            tree = o.read_typetree()
        except Exception:
            continue
        if not isinstance(tree, dict):
            continue
        ud = tree.get("UIData")
        if not isinstance(ud, dict):
            continue
        item_name = ud.get("itemName")
        if not item_name:
            continue
        found.setdefault(item_name, []).append((name, o.path_id))

for key in sorted(found):
    if re.search(r"bong|bong", key, re.I) or "BONG" in key.upper():
        print("MATCH", repr(key), found[key][:4])

print()
print("total distinct item names:", len(found))
for key in sorted(found):
    print("  ", repr(key))
