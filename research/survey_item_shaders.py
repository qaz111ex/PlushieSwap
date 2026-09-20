"""Which shader do item materials use?

`ItemCooking` reads and writes `_Tint` on every renderer under an item, so whatever
shader an item's materials use must declare `_Tint`. This resolves the shader of every
material in the game across asset files so the answer comes from data.
"""
import os
from collections import Counter

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def main():
    files = [n for n in os.listdir(GAME) if n.endswith(".assets")]
    # path_id -> shader name, built per file; PPtr file_id indexes that file's externals
    shader_by_file = {}
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
            table[o.path_id] = (pf.m_Name if pf is not None else getattr(d, "m_Name", "")) or ""
        shader_by_file[fname] = (env, table)

    counter = Counter()
    examples = {}
    for fname, (env, table) in shader_by_file.items():
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
                fid = d.m_Shader.file_id
                pid = d.m_Shader.path_id
                if fid == 0:
                    name = table.get(pid, "?")
                else:
                    idx = fid - 1
                    if 0 <= idx < len(externals):
                        tgt = os.path.basename(externals[idx])
                        sub = shader_by_file.get(tgt)
                        name = (sub[1].get(pid, "?") if sub else "?") or "?"
            if not name:
                name = "?"
            counter[name] += 1
            examples.setdefault(name, (fname, d.m_Name))

    for name, count in counter.most_common(40):
        ex = examples[name]
        print(f"{count:4d}  {name:32s} e.g. {ex[1]} ({ex[0]})")


if __name__ == "__main__":
    main()
