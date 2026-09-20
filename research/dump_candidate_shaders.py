"""Research-only: deep-dump candidate shaders (pass render state + bytecode).

Looks at shaders whose property list hints at a vertex-space offset
(_Outline, _VertexGhost, _Displacement) to decide whether any stock shader can
already act as an outline shell, and dumps the URP Lit pass state for reference.

Writes research/shader_candidates.txt
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
OUT = r"D:\zhuanban\Plushie Swap\research"

TARGETS = {
    "Explosion", "Jelly", "Tornado", "W/Character", "W/Peak_Mirage",
    "GD/CharacterBadges",
}

ASSET = "globalgamemanagers.assets"
ASSET2 = "resources.assets"


def dump_state(pp):
    st = getattr(pp, "m_State", None)
    if st is None:
        return "    <no state>"
    out = []
    names = [
        ("culling", "m_CullingMode"), ("zwrite", "m_ZWrite"), ("ztest", "m_ZTest"),
        ("blend0", "m_Blend0"), ("blend1", "m_Blend1"), ("blendOp", "m_BlendOp"),
        ("colormask", "m_ColorMask"), ("offset", "m_OffsetFactor"),
        ("alphatocoverage", "m_AlphaToMask"), ("srcblend", "m_SrcBlend"),
        ("dstblend", "m_DstBlend"), ("sepscale", "m_SeparateBlend"),
    ]
    for label, attr in names:
        v = getattr(st, attr, "<missing>")
        out.append(f"      {label}={v}")
    return "\n".join(out)


def dump_shader(d, obj, fn, fh):
    pf = getattr(d, "m_ParsedForm", None)
    if pf is None:
        return
    name = getattr(pf, "m_Name", "")
    fh.write(f"\n==== {name}  [{fn} pid={obj.path_id}] ====\n")
    props = []
    try:
        props = [(p.m_Name, p.m_Type) for p in pf.m_PropInfo.m_Props]
    except Exception:
        pass
    fh.write("  properties: " + ", ".join(n for n, _ in props) + "\n")
    try:
        subshaders = pf.m_SubShaders
    except Exception as e:
        fh.write(f"  subshaders unavailable: {e}\n")
        return
    for si, ss in enumerate(subshaders):
        fh.write(f"  --- subshader {si}  passes={len(ss.m_Passes)}\n")
        # subshader-level tags
        try:
            for t in ss.m_Tags:
                fh.write(f"      tag {t.Key}={t.Value}\n")
        except Exception:
            pass
        for pi, pp in enumerate(ss.m_Passes):
            ptype = getattr(pp, "m_PassType", getattr(pp, "m_Type", "?"))
            fh.write(f"    pass {pi} name={pp.m_Name!r} type={ptype}\n")
            try:
                for t in pp.m_Tags:
                    fh.write(f"      tag {t.Key}={t.Value}\n")
            except Exception:
                pass
            fh.write(dump_state(pp) + "\n")
            for progname in ("m_ProgVertex", "m_ProgFragment", "m_ProgGeometry"):
                pr = getattr(pp, progname, None)
                if pr is None:
                    continue
                code = getattr(pr, "m_ShaderCode", b"") or b""
                text = code.decode("utf-8", "replace") if isinstance(code, bytes) else str(code)
                fh.write(f"      {progname} len={len(text)}\n")
                for line in text.splitlines()[:12]:
                    fh.write(f"        | {line}\n")


def main():
    found = set()
    with open(os.path.join(OUT, "shader_candidates.txt"), "w", encoding="utf-8") as fh:
        for fn in (ASSET, ASSET2):
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
                name = getattr(pf, "m_Name", "") if pf else ""
                if name in TARGETS and name not in found:
                    found.add(name)
                    dump_shader(d, obj, fn, fh)
                    print("dumped", name)
    print("done")


if __name__ == "__main__":
    main()
