"""Find which asset file holds a given shader and dump its passes/keywords."""
import os
import sys

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
TARGET = sys.argv[1] if len(sys.argv) > 1 else "W/Character"


def main():
    for fn in sorted(os.listdir(GAME)):
        path = os.path.join(GAME, fn)
        if not os.path.isfile(path) or fn.endswith((".resS", ".resource")):
            continue
        try:
            env = UnityPy.load(path)
        except Exception:
            continue
        for o in env.objects:
            if o.type.name != "Shader":
                continue
            try:
                d = o.read()
            except Exception:
                continue
            pf = getattr(d, "m_ParsedForm", None)
            if pf is None or getattr(pf, "m_Name", "") != TARGET:
                continue
            print(f"{fn}: pid={o.path_id} {TARGET!r}")
            print("  subshaders:", len(pf.m_SubShaders))
            for si, ss in enumerate(pf.m_SubShaders):
                print(f"    subshader {si}: passes={len(ss.m_Passes)}")
                for pi, pp in enumerate(ss.m_Passes):
                    names = []
                    for kw in (getattr(pp, "m_State", None),):
                        pass
                    print(f"      pass {pi} {pp.m_Name!r}")
            try:
                props = pf.m_PropInfo.m_Props
                print("  properties:", len(props))
                for p in props:
                    print(f"    {p.m_Name}  type={p.m_Type}")
            except Exception as e:
                print("  props unavailable:", e)
            return


if __name__ == "__main__":
    main()
