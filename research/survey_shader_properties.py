"""Research-only: dump every property name of every shipped shader.

Goal: find a stock shader that already supports a vertex-normal offset (an
outline width / "ghost" / "inflate" parameter) so a screen-space outline could
be driven from Unity's own shaders without shipping a compiled custom one.

Writes research/shader_properties.txt.
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
OUT = r"D:\zhuanban\Plushie Swap\research"

INTERESTING = ("outline", "width", "inflate", "extrude", "ghost", "thick",
               "shell", "rim", "fresnel", "normal", "offset", "displace",
               "vertex", "smooth", "cull", "stencil", "scale", "push")


def asset_files():
    return [n for n in sorted(os.listdir(GAME))
            if os.path.isfile(os.path.join(GAME, n))
            and not n.endswith((".resS", ".resource", ".json", ".config"))]


def main():
    rows = []
    seen = set()
    for fn in asset_files():
        try:
            env = UnityPy.load(os.path.join(GAME, fn))
        except Exception:
            continue
        for obj in env.objects:
            if obj.type.name != "Shader":
                continue
            try:
                d = obj.read()
            except Exception:
                continue
            pf = getattr(d, "m_ParsedForm", None)
            name = getattr(d, "m_Name", "") or (
                getattr(pf, "m_Name", "") if pf is not None else "")
            if not name or name in seen:
                continue
            seen.add(name)
            props = []
            if pf is not None:
                try:
                    props = [(p.m_Name, p.m_Type) for p in pf.m_PropInfo.m_Props]
                except Exception:
                    props = []
            rows.append((name, fn, props))

    rows.sort()
    with open(os.path.join(OUT, "shader_properties.txt"), "w", encoding="utf-8") as fh:
        for name, fn, props in rows:
            fh.write(f"==== {name}  [{fn}] {len(props)} props\n")
            for pn, pt in props:
                fh.write(f"    {pn}  type={pt}\n")

    print("candidate properties (name hints at vertex offset / culling):")
    for name, fn, props in rows:
        hits = [pn for pn, _ in props
                if any(k in pn.lower() for k in INTERESTING)]
        if not hits:
            continue
        interesting = [h for h in hits if any(
            k in h.lower() for k in ("outline", "inflate", "extrude", "ghost",
                                     "thick", "shell", "cull", "displace"))]
        if interesting:
            print(f"  {name:45s} {interesting}")


if __name__ == "__main__":
    main()
