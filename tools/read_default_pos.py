"""Read Item.defaultPos straight from the game's serialized prefab bytes.

UnityPy cannot deserialize the MonoBehaviour scripts (they are in Assembly-CSharp, so
the typetree is absent), but the raw bytes are still there and the field offsets are
known from the class layout. This scans each BingBong prefab's MonoBehaviour stream for
the `defaultPos` / `defaultForward` vectors by looking at the serialized field layout
printed by the game's own Assembly-CSharp, so the hold position can be reasoned about
exactly instead of assumed.
"""
import os
import struct

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
TARGETS = ("BingBong", "BingBong_Prop Variant")


def main():
    env = UnityPy.load(os.path.join(GAME, "resources.assets"))
    objects = {o.path_id: o for o in env.objects}

    for target in TARGETS:
        for o in env.objects:
            if o.type.name != "GameObject":
                continue
            try:
                gd = o.read()
            except Exception:
                continue
            if gd.m_Name != target:
                continue
            print(f"=== {target} (path_id={o.path_id}) ===")
            for comp in gd.m_Components:
                if comp is None:
                    continue
                cr = objects.get(comp.path_id)
                if cr is None or cr.type.name != "MonoBehaviour":
                    continue
                raw = cr.get_raw_data()
                script = getattr(cr.read(), "m_Script", None)
                cls = "?"
                if script is not None:
                    try:
                        cls = script.read().m_ClassName
                    except Exception:
                        pass
                if cls not in ("BingBong",):
                    continue
                print(f"  script={cls} rawLen={len(raw)}")
                # GameObject reference then the fields in declaration order.
                # Item: ... then defaultPos (Vector3), defaultForward (Vector3),
                # gliderHold (bool), rightHandOnly (bool) ...
                # Print every plausible Vector3 of small magnitude in the tail.
                tail = raw[-160:]
                for off in range(0, len(tail) - 12, 4):
                    v = struct.unpack('<3f', tail[off:off + 12])
                    if all(abs(x) < 5.0 for x in v) and any(abs(x) > 1e-6 for x in v):
                        print(f"    off {off:3d}: ({v[0]:+.4f},{v[1]:+.4f},{v[2]:+.4f})")
            print()


if __name__ == "__main__":
    main()
