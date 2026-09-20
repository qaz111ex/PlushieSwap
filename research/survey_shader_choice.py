"""Which shaders can serve as the replacement's body and ink materials?

Two requirements:

  body : must declare `_Tint`, because the game's own ItemCooking reads and writes it
         on every renderer under an item and Unity logs an error when it is missing.
  ink  : must declare `_Tint` (same reason) AND be able to cull FRONT faces, because
         an inverted hull only shows the band poking out around the silhouette.

This prints every shader with its declared properties and the cull / zwrite / ztest
state of each pass, so both choices come from the shipped shaders rather than a guess.
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
WANTED = ("_Tint", "_Cull", "_CullMode", "_ZTest", "_ZWrite", "_BaseColor", "_Color",
          "_MainTex", "_BaseTexture", "_BaseMap", "_VertexColor", "_UseRawVertexColor",
          "_VertexColorAmount", "_BaseSmooth", "_Smoothness", "_AlphaClip", "_UseTextureAlpha",
          "_UseSkinTone", "_EmissionColor", "_Texture1", "_Surface", "_Blend", "_Opacity",
          "_HueStr", "_Brightness", "_StatusGlow", "_Interactable", "_INTERACTABLE")


def main():
    files = sorted(n for n in os.listdir(GAME) if n.endswith(".assets"))
    seen = {}
    for fname in files:
        try:
            env = UnityPy.load(os.path.join(GAME, fname))
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
            if pf is None or not pf.m_Name or pf.m_Name in seen:
                continue
            props = [p.m_Name for p in pf.m_PropInfo.m_Props]
            passes = []
            for ss in pf.m_SubShaders:
                for p in ss.m_Passes:
                    st = p.m_State
                    passes.append((st.culling.val, st.zWrite.val, st.zTest.val,
                                   st.rtBlend0.srcBlend.val, st.rtBlend0.destBlend.val))
            tags = dict(pf.m_SubShaders[0].m_Tags.tags) if pf.m_SubShaders else {}
            seen[pf.m_Name] = (fname, props, passes, tags)

    print("=== shaders declaring _Tint ===")
    for name, (fname, props, passes, tags) in sorted(seen.items()):
        if "_Tint" not in props:
            continue
        culls = sorted(set(int(p[0]) for p in passes))
        print(f"{name:48s} culls={culls} queue={tags.get('QUEUE','?'):12s} "
              f"type={tags.get('UniversalMaterialType','?')}")

    print("\n=== shaders with a FRONT-culling pass (cull=1) ===")
    for name, (fname, props, passes, tags) in sorted(seen.items()):
        if not any(int(p[0]) == 1 for p in passes):
            continue
        print(f"{name:48s} tint={'_Tint' in props} culls="
              f"{sorted(set(int(p[0]) for p in passes))} "
              f"props={[p for p in WANTED if p in props]}")

    print("\n=== W/Character full detail (the shader the vanilla plush uses) ===")
    name = "W/Character"
    if name in seen:
        fname, props, passes, tags = seen[name]
        print("props:", " ".join(props))
        print("tags:", tags)
        for i, p in enumerate(passes):
            print(f"  pass {i}: cull={int(p[0])} zwrite={int(p[1])} ztest={int(p[2])} "
                  f"blend=({int(p[3])},{int(p[4])})")

    print("\n=== Universal Render Pipeline/Unlit detail ===")
    name = "Universal Render Pipeline/Unlit"
    if name in seen:
        fname, props, passes, tags = seen[name]
        print("props:", " ".join(props))
        print("tags:", tags)
        for i, p in enumerate(passes):
            print(f"  pass {i}: cull={int(p[0])} zwrite={int(p[1])} ztest={int(p[2])} "
                  f"blend=({int(p[3])},{int(p[4])})")


if __name__ == "__main__":
    main()
