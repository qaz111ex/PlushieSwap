"""Dump the W/Character materials that the game itself ships, to copy their settings.

`new Material(shader)` starts from the shader's DEFAULTS, which for a Shader Graph
shader are not the values the game uses. The materials that ship with the game show
exactly which properties matter and what they are set to, so the replacement can be
configured the same way instead of guessed.
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"

INTEREST_F = ("_UseSkinTone", "_UseRawVertexColor", "_UseTextureAlpha",
              "_Stepalphabyvertexcolor", "_VertexColor", "_HueStr", "_VertexGhost",
              "_BaseSmooth", "_Smooth1", "_Smooth2", "_Smooth3", "_Smooth4",
              "_Height1", "_Height2", "_Height3", "_Height4", "_Opacity",
              "_StatusGlow", "_PointPing", "_SpecularPower", "_AddSpecular",
              "_AlphaClip", "_MainTexMovement", "_HeightMaskSmoothness",
              "_FlipHeightMask", "_Remap1", "_Remap2", "_Remap3", "_Remap4",
              "_Triplanar1On", "_Triplanar2On", "_Triplanar3On", "_Triplanar4On",
              "_UV1", "_UV2", "_UV3", "_UV4", "_Flip1", "_Flip2", "_Flip3", "_Flip4",
              "_UseHeightMask1", "_UseHeightMask2", "_UseHeightMask3", "_UseHeightMask4")
INTEREST_C = ("_Tint", "_BaseColor", "_Color1", "_Color2", "_Color3", "_Color4",
              "_SkinColor", "_StatusColor")
INTEREST_T = ("_MainTex", "_Texture1", "_Texture2", "_Texture3", "_Texture4")


def main():
    fname = "resources.assets"
    env = UnityPy.load(os.path.join(GAME, fname))
    objects = {o.path_id: o for o in env.objects}
    externals = [e.path for e in env.file.externals]

    def shader_name(mat):
        if mat.m_Shader is None:
            return "?"
        fid = mat.m_Shader.file_id
        pid = mat.m_Shader.path_id
        table = objects
        if fid != 0:
            idx = fid - 1
            if not (0 <= idx < len(externals)):
                return "?"
            other = os.path.basename(externals[idx])
            other_env = UnityPy.load(os.path.join(GAME, other))
            table = {o.path_id: o for o in other_env.objects}
        o = table.get(pid)
        if o is None or o.type.name != "Shader":
            return "?"
        d = o.read()
        pf = getattr(d, "m_ParsedForm", None)
        return (pf.m_Name if pf is not None else "") or "?"

    shown = 0
    for o in env.objects:
        if o.type.name != "Material":
            continue
        d = o.read()
        if shader_name(d) != "W/Character":
            continue
        if shown >= 3:
            break
        shown += 1
        print(f"===== {d.m_Name} =====")
        for p in sorted(d.m_SavedProperties.m_Floats, key=lambda x: x[0]):
            if p[0] in INTEREST_F:
                print(f"   FLT {p[0]:26s} = {p[1]:.4g}")
        for p in sorted(d.m_SavedProperties.m_Colors, key=lambda x: x[0]):
            if p[0] in INTEREST_C:
                c = p[1]
                print(f"   COL {p[0]:26s} = ({c.r:.3g},{c.g:.3g},{c.b:.3g},{c.a:.3g})")
        for p in sorted(d.m_SavedProperties.m_TexEnvs, key=lambda x: x[0]):
            if p[0] not in INTEREST_T:
                continue
            tex = p[1].m_Texture
            tn = "null"
            if tex is not None:
                try:
                    tn = objects[tex.path_id].read().m_Name
                except Exception:
                    tn = "?"
            sc = p[1].m_Scale
            of = p[1].m_Offset
            print(f"   TEX {p[0]:26s} = {tn} scale=({sc.x:.3g},{sc.y:.3g}) "
                  f"offset=({of.x:.3g},{of.y:.3g})")
        print()


if __name__ == "__main__":
    main()
