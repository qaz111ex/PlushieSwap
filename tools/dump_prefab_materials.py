"""Print the shader each renderer under the BingBong prefab actually uses.

The mod's materials are created from a shader chosen by name, and the game's own
ItemCooking / BackpackOnBackVisuals write `_Tint` on whatever material an item's
renderers carry. If the chosen shader does not declare `_Tint` those writes log an
error every time a plush is equipped. So the one authoritative answer to "which
shader should the replacement use" is the shader the vanilla plush already uses.
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
TARGET = "BingBong_Prop Variant"


def main():
    env = UnityPy.load(os.path.join(GAME, "resources.assets"))
    objects = {o.path_id: o for o in env.objects}

    for o in env.objects:
        if o.type.name != "GameObject":
            continue
        try:
            d = o.read()
        except Exception:
            continue
        if d.m_Name != TARGET:
            continue
        print(f"=== {TARGET} path_id={o.path_id} ===")
        walk(objects, d, "")
        return
    print("not found")


def walk(objects, gd, indent):
    for comp in gd.m_Components:
        if comp is None:
            continue
        cr = objects.get(comp.path_id)
        if cr is None:
            continue
        if cr.type.name in ("MeshRenderer", "SkinnedMeshRenderer"):
            r = cr.read()
            print(f"{indent}[{cr.type.name}] on '{gd.m_Name}'")
            for mref in r.m_Materials:
                if mref is None:
                    continue
                mat = objects[mref.path_id].read()
                shader = mat.m_Shader.read() if mat.m_Shader is not None else None
                print(f"{indent}  material '{mat.m_Name}' shader '{getattr(shader, 'm_Name', '?')}'")
                for prop in mat.m_SavedProperties.m_TexEnvs:
                    if prop[0] in ("_BaseMap", "_MainTex", "_BaseTexture", "_Texture1",
                                   "_EmissionMap"):
                        tex = prop[1].m_Texture
                        tn = "null"
                        if tex is not None:
                            try:
                                tn = objects[tex.path_id].read().m_Name
                            except Exception as exc:
                                tn = f"<{exc}>"
                        print(f"{indent}    {prop[0]} = {tn}")
                for prop in mat.m_SavedProperties.m_Floats:
                    if prop[0] in ("_Cull", "_Surface", "_Blend", "_ZWrite", "_UseAlpha",
                                   "_VertexColorAmount", "_BaseTexAmount", "_Smoothness"):
                        print(f"{indent}    {prop[0]} = {prop[1]}")
                for prop in mat.m_SavedProperties.m_Colors:
                    if prop[0] in ("_Tint", "_BaseColor", "_Color", "_Color1"):
                        c = prop[1]
                        print(f"{indent}    {prop[0]} = ({c.r:.3f},{c.g:.3f},{c.b:.3f},{c.a:.3f})")
        if cr.type.name == "Transform":
            for ch in cr.read().m_Children:
                if ch is None:
                    continue
                cgo = ch.read()
                ref = getattr(cgo, "m_GameObject", None)
                if ref is None:
                    continue
                walk(objects, objects[ref.path_id].read(), indent + "  ")


if __name__ == "__main__":
    main()
