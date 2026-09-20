"""Research-only: enumerate every Shader in the shipped PEAK build.

Dumps name, source file, pass names, keywords and properties for each shader so
we can see what is available for a custom outline (Cull mode, ZOffset, stencil).
Writes research/shader_inventory.txt and research/shader_detail.txt.

Does not touch assets/, src/ or tools/.
"""
import os
import sys
import traceback

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
OUT = r"D:\zhuanban\Plushie Swap\research"

CACHE = {}


def asset_files():
    out = []
    for n in sorted(os.listdir(GAME)):
        p = os.path.join(GAME, n)
        if not os.path.isfile(p):
            continue
        if n.endswith((".resS", ".resource", ".json", ".config")):
            continue
        out.append(n)
    return out


def props_of(pf):
    try:
        return list(pf.m_PropInfo.m_Props)
    except Exception:
        return []


def main():
    inv = []
    details = []
    seen = set()

    for fn in asset_files():
        try:
            env = UnityPy.load(os.path.join(GAME, fn))
        except Exception as e:
            print("SKIP", fn, e)
            continue
        for obj in env.objects:
            if obj.type.name != "Shader":
                continue
            try:
                d = obj.read()
            except Exception:
                continue
            pf = getattr(d, "m_ParsedForm", None)
            name = getattr(d, "m_Name", "") or (getattr(pf, "m_Name", "") if pf else "")
            if not name or name in seen:
                continue
            seen.add(name)
            passes = 0
            subshaders = 0
            if pf is not None:
                try:
                    subshaders = len(pf.m_SubShaders)
                    for ss in pf.m_SubShaders:
                        passes += len(ss.m_Passes)
                except Exception:
                    pass
            props = props_of(pf) if pf is not None else []
            propnames = [p.m_Name for p in props]
            inv.append((name, fn, obj.path_id, subshaders, passes, len(props)))

            if name in ("Universal Render Pipeline/Lit", "W/Character", "W/Peak_Standard",
                        "Universal Render Pipeline/Unlit", "Universal Render Pipeline/Simple Lit"):
                lines = [f"==== {name}  ({fn} pid={obj.path_id}) ===="]
                if pf is not None:
                    for si, ss in enumerate(pf.m_SubShaders):
                        lines.append(f"  subshader {si}: passes={len(ss.m_Passes)}")
                        for pi, pp in enumerate(ss.m_Passes):
                            lines.append(f"    pass {pi} name={pp.m_Name!r}")
                    lines.append("  properties:")
                    for p in props:
                        try:
                            lines.append(f"    {p.m_Name}  type={p.m_Type}")
                        except Exception:
                            lines.append(f"    {p}")
                details.append("\n".join(lines))

    inv.sort()
    with open(os.path.join(OUT, "shader_inventory.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"{len(inv)} shaders\n")
        fh.write(f"{'name':55s} {'file':22s} {'subsh':>5s} {'pass':>4s} {'props':>5s}\n")
        for name, fn, pid, ss, ps, pr in inv:
            fh.write(f"{name:55s} {fn:22s} {ss:5d} {ps:4d} {pr:5d}\n")

    with open(os.path.join(OUT, "shader_detail.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(details))

    print(f"{len(inv)} shaders -> research/shader_inventory.txt")
    for name, fn, pid, ss, ps, pr in inv:
        print(f"  {name:55s} {fn:22s} passes={ps} props={pr}")


if __name__ == "__main__":
    main()
