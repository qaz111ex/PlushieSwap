"""Locate the BingBong Item MonoBehaviour and read its serialized fields via typetree."""
import os
import sys

import UnityPy
from UnityPy.helpers import TypeTreeHelper

GAME_DATA = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "Bing Bong"
    env = UnityPy.load(os.path.join(GAME_DATA, "resources.assets"))

    count = 0
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
        if item_name is None:
            continue
        if item_name != target:
            continue
        print("=" * 70)
        print("path_id", o.path_id, "itemName", item_name)
        for key in sorted(tree.keys()):
            value = tree[key]
            if isinstance(value, dict):
                inner = {k: v for k, v in value.items()
                         if isinstance(v, (int, float, str, bool)) or v is None}
                ptr = {k: v for k, v in value.items() if isinstance(v, dict) and "m_FileID" in v}
                print(f"  {key}:")
                for k, v in inner.items():
                    print(f"      {k} = {v!r}")
                for k, v in ptr.items():
                    print(f"      {k} -> file{k.get('m_FileID')} path{k.get('m_PathID')}")
            elif isinstance(value, (int, float, str, bool)) or value is None:
                print(f"  {key} = {value!r}")
        count += 1
        if count >= 3:
            break

    if count == 0:
        print("no Item with itemName", target)


if __name__ == "__main__":
    main()
