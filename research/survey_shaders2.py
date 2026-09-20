"""Catalogue every shader in the game: declared props, cull state, material type.

The replacement needs a shader that (a) declares `_Tint`, because the game's own
ItemCooking reads and writes it on every renderer under an item and logs an error
when it is missing, and (b) can be made to draw an inverted hull. This prints both
facts for every shader so the choice is made from data, not from guessing names.
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"

FILES = [n for n in os.listdir(GAME)
         if n.endswith(".assets") or n == "globalgamemanagers"]

INTEREST = ("_Tint", "_Cull", "_CullMode", "_BaseColor", "_Color", "_MainTex",
            "_BaseTexture", "_BaseMap", "_VertexColor", "_UseRawVertexColor",
            "_VertexColorAmount", "_Surface", "_Blend", "_ZWrite", "_AlphaClip",
            "_EmissionColor", "_BaseSmooth", "_Smoothness", "_UseTextureAlpha",
            "_UseSkinTone", "_Texture1")


def main():
    seen = {}
    for fname in sorted(FILES):
        path = os.path.join(GAME, fname)
        if not os.path.isfile(path):
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
            if pf is None:
                continue
            name = pf.m_Name or ""
            if name in seen:
                continue
            props = [p.m_Name for p in pf.m_PropInfo.m_Props]
            passes = []
            mat_type = ""
            if pf.m_SubShaders:
                tags = dict(pf.m_SubShaders[0].m_Tags.tags)
                mat_type = tags.get("UniversalMaterialType", tags.get("RenderType", ""))
                for p in pf.m_SubShaders[0].m_Passes:
                    st = p.m_State
                    passes.append((st.culling.val, st.zWrite.val,
                                   st.rtBlend0.srcBlend.val, st.rtBlend0.destBlend.val))
            seen[name] = (fname, props, passes, mat_type)

    print(f"{len(seen)} shaders\n")
    for name, (fname, props, passes, mat_type) in sorted(seen.items()):
        has = [p for p in INTEREST if p in props]
        if "_Tint" not in props:
            continue
        cull = ",".join(str(int(p[0])) for p in passes[:3])
        print(f"{name:52s} [{mat_type:8s}] cull={cull:8s} props={has}")

    print("\n--- shaders WITHOUT _Tint but with a _Cull property (ink candidates) ---")
    for name, (fname, props, passes, mat_type) in sorted(seen.items()):
        if "_Tint" in props:
            continue
        if "_Cull" in props or "_CullMode" in props:
            cull = ",".join(str(int(p[0])) for p in passes[:3])
            print(f"{name:52s} [{mat_type:8s}] cull={cull:8s}")


if __name__ == "__main__":
    main()
