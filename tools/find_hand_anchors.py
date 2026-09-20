"""Find every GameObject named Hand_L / Hand_R in the shipped data files.

The vanilla plush prefab's own anchor transforms are the reference for the
replacement's, so this walks the whole PEAK_Data directory and reports which
file and which parent chain each anchor lives under.
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"

TARGETS = ("Hand_L", "Hand_R")


def main():
    for root, _dirs, files in os.walk(GAME):
        for name in files:
            if not name.lower().endswith((".assets", ".unity3d", ".bundle")):
                continue
            path = os.path.join(root, name)
            try:
                env = UnityPy.load(path)
            except Exception as exc:
                print(f"[skip] {name}: {exc}")
                continue

            objects = {o.path_id: o for o in env.objects}
            hits = []
            for o in env.objects:
                if o.type.name != "GameObject":
                    continue
                try:
                    gd = o.read()
                except Exception:
                    continue
                if gd.m_Name in TARGETS:
                    hits.append((o.path_id, gd))
            if not hits:
                continue

            print(f"=== {name} ===")
            for pid, gd in hits:
                parent = "<root>"
                for o in env.objects:
                    if o.type.name != "Transform":
                        continue
                    try:
                        t = o.read()
                    except Exception:
                        continue
                    for ch in t.m_Children:
                        if ch is None:
                            continue
                        try:
                            cgo = ch.read()
                        except Exception:
                            continue
                        ref = getattr(cgo, "m_GameObject", None)
                        if ref is not None and ref.path_id == pid:
                            pgo = t.m_GameObject.read() if t.m_GameObject else None
                            parent = pgo.m_Name if pgo else "?"
                print(f"  {gd.m_Name}  path_id={pid}  parent={parent}")
            print()


if __name__ == "__main__":
    main()
