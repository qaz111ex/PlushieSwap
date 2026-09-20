"""Does the game's own item shader draw outlines?

`W/Peak_Standard` (and friends) declare a float property `_Outline`. M_Balloon_Blue
sets it to 1 and PEAK balloons are visibly outlined. If that property is a built-in
inverted-hull outline, the mod could stop shipping an ink shell altogether — which
would remove every masking artefact at once.

This prints, for every material that uses a `_Tint`-declaring shader, the value of
`_Outline` together with a few known-outlined / known-unoutlined objects, so the
meaning of the property can be read off the shipped data.
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def main():
    files = sorted(n for n in os.listdir(GAME) if n.endswith(".assets"))
    rows = []
    shader_names = {}
    for fname in files:
        try:
            env = UnityPy.load(os.path.join(GAME, fname))
        except Exception:
            continue
        table = {}
        for o in env.objects:
            if o.type.name != "Shader":
                continue
            try:
                d = o.read()
            except Exception:
                continue
            pf = getattr(d, "m_ParsedForm", None)
            table[o.path_id] = (pf.m_Name if pf is not None else "") or ""
        externals = [e.path for e in env.file.externals]
        for o in env.objects:
            if o.type.name != "Material":
                continue
            try:
                d = o.read()
            except Exception:
                continue
            name = "?"
            if d.m_Shader is not None:
                fid, pid = d.m_Shader.file_id, d.m_Shader.path_id
                if fid == 0:
                    name = table.get(pid, "?")
                else:
                    idx = fid - 1
                    if 0 <= idx < len(externals):
                        tgt = os.path.basename(externals[idx])
                        key = (tgt, pid)
                        if key not in shader_names:
                            try:
                                oe = UnityPy.load(os.path.join(GAME, tgt))
                                sub = {}
                                for oo in oe.objects:
                                    if oo.type.name != "Shader":
                                        continue
                                    dd = oo.read()
                                    pp = getattr(dd, "m_ParsedForm", None)
                                    sub[oo.path_id] = (pp.m_Name if pp is not None else "") or ""
                                shader_names[key] = sub.get(pid, "?")
                            except Exception:
                                shader_names[key] = "?"
                        name = shader_names[key]
            outline = None
            for p in d.m_SavedProperties.m_Floats:
                if p[0] == "_Outline":
                    outline = p[1]
                    break
            rows.append((name, d.m_Name, outline, fname))

    with_outline = [r for r in rows if r[2] is not None]
    print(f"materials with an _Outline property: {len(with_outline)} of {len(rows)}")
    nonzero = [r for r in with_outline if abs(r[2]) > 1e-6]
    print(f"  with _Outline != 0: {len(nonzero)}")
    by_shader = {}
    for name, mat, val, fname in with_outline:
        by_shader.setdefault(name, []).append((mat, val))
    for name, items in sorted(by_shader.items()):
        on = sum(1 for _, v in items if abs(v) > 1e-6)
        print(f"  {name:34s} {len(items):4d} materials, {on:4d} with _Outline on")
    print("\nexamples with _Outline on:")
    for name, mat, val, fname in nonzero[:40]:
        print(f"  {mat:40s} {name:28s} _Outline={val:.4g}  ({fname})")


if __name__ == "__main__":
    main()
