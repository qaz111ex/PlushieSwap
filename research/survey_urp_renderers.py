"""Research-only: enumerate the game's URP renderer assets and their features.

This decides whether a runtime-added ScriptableRendererFeature (screen-space
edge detection) is even feasible, and shows which features already run.

Writes research/urp_renderers.txt
"""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
OUT = r"D:\zhuanban\Plushie Swap\research"


def asset_files():
    return [n for n in sorted(os.listdir(GAME))
            if os.path.isfile(os.path.join(GAME, n))
            and not n.endswith((".resS", ".resource", ".json", ".config"))]


def main():
    lines = []
    for fn in asset_files():
        try:
            env = UnityPy.load(os.path.join(GAME, fn))
        except Exception:
            continue
        for obj in env.objects:
            tname = obj.type.name
            if tname not in ("UniversalRendererData", "UniversalRenderPipelineAsset",
                             "MonoBehaviour", "ScriptableRendererData"):
                continue
            try:
                d = obj.read()
            except Exception:
                continue
            # MonoBehaviour assets: read script name via typetree
            cls = type(d).__name__
            name = getattr(d, "m_Name", "") or ""
            interesting = False
            blob = ""
            for attr in ("rendererFeatures", "m_RendererFeatures"):
                v = getattr(d, attr, None)
                if v:
                    interesting = True
                    blob += f"    {attr}: {len(v)} features\n"
                    for f in v:
                        fname = getattr(f, "m_Name", "") or ""
                        ftype = type(f).__name__
                        # script type name lives in m_Script
                        scr = getattr(f, "m_Script", None)
                        sname = getattr(scr, "m_Name", "") if scr else ""
                        blob += f"      - {fname!r} type={ftype} script={sname!r}\n"
            if "rendererDataList" in dir(d) or hasattr(d, "m_RendererDataList"):
                v = getattr(d, "m_RendererDataList", None)
                if v:
                    interesting = True
                    blob += f"    rendererDataList: {len(v)}\n"
            if interesting:
                lines.append(f"{fn}\t{tname}\tpid={obj.path_id}\t{cls}\t{name!r}\n{blob}")

    with open(os.path.join(OUT, "urp_renderers.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines) or "nothing found")


if __name__ == "__main__":
    main()
