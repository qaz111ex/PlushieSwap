"""Property defaults for the two candidate shaders, plus the vanilla plush material.

The replacement needs a shader that declares `_Tint` (ItemCooking reads it) and renders
the baked palette correctly. `W/Character` is what the vanilla plush uses. To use it
without guessing, this prints:

  * every declared property of W/Character and W/Peak_Standard with its DEFAULT value,
    i.e. exactly what `new Material(shader)` starts from
  * every property M_BingBongPlush actually stores, i.e. what the game overrides
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def find_shader():
    env = UnityPy.load(os.path.join(GAME, "globalgamemanagers.assets"))
    for o in env.objects:
        if o.type.name != "Shader":
            continue
        d = o.read()
        pf = getattr(d, "m_ParsedForm", None)
        if pf is not None and pf.m_Name in ("W/Character", "W/Peak_Standard"):
            yield pf.m_Name, pf


def main():
    for name, pf in find_shader():
        print(f"===== {name} =====")
        for p in pf.m_PropInfo.m_Props:
            dv = getattr(p, "m_DefValue", None)
            dvec = getattr(p, "m_DefTexture", None)
            text = ""
            if p.m_Type in (0, 2, 3) and dv is not None:
                text = " default=[" + ", ".join(f"{v:.4g}" for v in dv[:4]) + "]"
            elif p.m_Type == 4:
                text = f" defaultTex={getattr(dvec, 'm_TextureName', None)}"
            print(f"  {p.m_Name:26s} type={p.m_Type}  {p.m_Description}{text}")
        print()

    print("===== M_BingBongPlush (the vanilla plush material) =====")
    env = UnityPy.load(os.path.join(GAME, "resources.assets"))
    objects = {o.path_id: o for o in env.objects}
    for o in env.objects:
        if o.type.name != "Material":
            continue
        d = o.read()
        if d.m_Name != "M_BingBongPlush":
            continue
        print("  floats:")
        for p in sorted(d.m_SavedProperties.m_Floats, key=lambda x: x[0]):
            print(f"    {p[0]:28s} = {p[1]:.5g}")
        print("  colors:")
        for p in sorted(d.m_SavedProperties.m_Colors, key=lambda x: x[0]):
            c = p[1]
            print(f"    {p[0]:28s} = ({c.r:.4g},{c.g:.4g},{c.b:.4g},{c.a:.4g})")
        print("  textures:")
        for p in sorted(d.m_SavedProperties.m_TexEnvs, key=lambda x: x[0]):
            tex = p[1].m_Texture
            tn = "null"
            if tex is not None:
                try:
                    tn = objects[tex.path_id].read().m_Name
                except Exception:
                    tn = "?"
            sc = p[1].m_Scale
            of = p[1].m_Offset
            print(f"    {p[0]:28s} = {tn}  scale=({sc.x:.3g},{sc.y:.3g}) "
                  f"offset=({of.x:.3g},{of.y:.3g})")
        print("  ints:", d.m_SavedProperties.m_Ints)
        print("  keywords:", list(d.m_ShaderKeywords or []))
        break


if __name__ == "__main__":
    main()
