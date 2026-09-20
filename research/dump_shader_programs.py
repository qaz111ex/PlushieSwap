"""Research-only: dump the raw program text of outline-ish shaders.

Looks for a stock shader that already offsets vertices along the normal (which
would let a screen-space outline be driven without shipping a custom shader):
_Outline on Jelly/Tornado/Explosion, _VertexGhost on W/Character,
_Displacement on W/Peak_Mirage.

Writes research/shader_programs.txt
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
OUT = r"D:\zhuanban\Plushie Swap\research"

TARGETS = ["Universal Render Pipeline/Lit", "W/Character", "Jelly", "Tornado",
           "Explosion", "W/Peak_Mirage", "GD/CharacterBadges"]


def programs_of(pp):
    out = {}
    for key in ("progVertex", "progFragment", "progGeometry", "progHull"):
        pr = getattr(pp, key, None)
        if pr is None:
            continue
        code = getattr(pr, "m_ShaderCode", None)
        if code is None:
            continue
        if isinstance(code, bytes):
            try:
                text = code.decode("utf-8")
            except UnicodeDecodeError:
                text = code.decode("utf-8", "replace")
        else:
            text = str(code)
        out[key] = text
    return out


def state_of(pp):
    st = getattr(pp, "m_State", None)
    if st is None:
        return {}
    return {
        "pass": getattr(st, "m_Name", "?"),
        "cull": getattr(getattr(st, "culling", None), "val", "?"),
        "zwrite": getattr(getattr(st, "zWrite", None), "val", "?"),
        "ztest": getattr(getattr(st, "zTest", None), "val", "?"),
        "offsetFactor": getattr(getattr(st, "offsetFactor", None), "val", "?"),
        "offsetUnits": getattr(getattr(st, "offsetUnits", None), "val", "?"),
        "tags": [tuple(t) for t in getattr(getattr(st, "m_Tags", None), "tags", [])],
    }


def main():
    seen = set()
    with open(os.path.join(OUT, "shader_programs.txt"), "w", encoding="utf-8") as fh:
        for fn in sorted(os.listdir(GAME)):
            p = os.path.join(GAME, fn)
            if not os.path.isfile(p) or fn.endswith((".resS", ".resource", ".json", ".config")):
                continue
            try:
                env = UnityPy.load(p)
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
                name = getattr(pf, "m_Name", "") if pf else ""
                if name not in TARGETS or name in seen:
                    continue
                seen.add(name)
                fh.write(f"\n\n######## {name}  [{fn}] ########\n")
                for si, ss in enumerate(pf.m_SubShaders):
                    fh.write(f"--- subshader {si}: {len(ss.m_Passes)} passes\n")
                    for pi, pp in enumerate(ss.m_Passes):
                        stt = state_of(pp)
                        fh.write(f"  pass {pi}: {stt}\n")
                        progs = programs_of(pp)
                        fh.write(f"    programs: {list(progs)}\n")
                        for key, text in progs.items():
                            fh.write(f"    ---- {key} ({len(text)} chars) ----\n")
                            fh.write(text)
                            fh.write("\n")
                print("dumped", name)
    print("done")


if __name__ == "__main__":
    main()
