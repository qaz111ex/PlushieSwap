"""Full anatomy of the game's own plush shader, W/Character.

The vanilla BingBong plush is drawn with it, it declares `_Tint` (which ItemCooking
writes), and it declares `_Outline`. If it already draws an outline, the mod does not
need its own hull at all — which would remove every masking artefact at once.
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def main():
    env = UnityPy.load(os.path.join(GAME, "globalgamemanagers.assets"))
    objs = {o.path_id: o for o in env.objects}

    target = None
    for o in env.objects:
        if o.type.name != "Shader":
            continue
        d = o.read()
        pf = getattr(d, "m_ParsedForm", None)
        if pf is not None and pf.m_Name == "W/Character":
            target = (o.path_id, pf)
            break
    if target is None:
        print("not found")
        return

    pid, pf = target
    print(f"=== W/Character (path_id={pid}) ===")
    print(f"customEditor={pf.m_CustomEditorName}  fallback={pf.m_FallbackName}")
    print(f"props ({len(pf.m_PropInfo.m_Props)}):")
    for p in pf.m_PropInfo.m_Props:
        desc = getattr(p, "m_Description", "") or ""
        vals = getattr(p, "m_Attributes", None)
        extra = ""
        if p.m_Type == 0 and vals is not None:
            try:
                extra = "  default=" + str(vals)
            except Exception:
                pass
        print(f"   {p.m_Name:26s} type={p.m_Type}  {desc}{extra}")

    print(f"\nsubshaders: {len(pf.m_SubShaders)}")
    for si, ss in enumerate(pf.m_SubShaders):
        print(f"  SUB {si} tags: {ss.m_Tags.tags}")
        for pi, p in enumerate(ss.m_Passes):
            st = p.m_State
            print(f"    PASS {pi} name={p.m_Name!r} tags={p.m_Tags.tags}")
            print(f"      cull={st.culling.val} zWrite={st.zWrite.val} zTest={st.zTest.val} "
                  f"blend=({st.rtBlend0.srcBlend.val},{st.rtBlend0.destBlend.val}) "
                  f"alphaToMask={st.alphaToMask.val} lighting={st.lighting}")
            print(f"      gpuProgramID={st.gpuProgramID} lod={st.m_LOD}")
            for t in p.m_Tags.tags:
                pass


if __name__ == "__main__":
    main()
