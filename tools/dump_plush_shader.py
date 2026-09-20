"""Resolve the shader name behind M_BingBongPlush, the material the vanilla plush uses."""
import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def shader_name(objects, ref):
    if ref is None:
        return "<none>"
    path_id = ref.path_id
    if path_id not in objects:
        return f"<external fileID={ref.file_id} path_id={path_id}>"
    obj = objects[path_id]
    d = obj.read()
    for attr in ("m_Name", "m_ParsedForm"):
        v = getattr(d, attr, None)
        if attr == "m_ParsedForm" and v is not None:
            nm = getattr(v, "m_Name", None)
            if nm:
                return f"{obj.type.name}:{nm}"
        if isinstance(v, str) and v:
            return f"{obj.type.name}:{v}"
    return f"{obj.type.name}:<empty>"


def main():
    for fname in ("resources.assets", "sharedassets1.assets", "sharedassets2.assets",
                  "sharedassets3.assets", "sharedassets4.assets", "globalgamemanagers.assets"):
        path = os.path.join(GAME, fname)
        if not os.path.isfile(path):
            continue
        env = UnityPy.load(path)
        objects = {o.path_id: o for o in env.objects}
        for o in env.objects:
            if o.type.name != "Material":
                continue
            d = o.read()
            if d.m_Name not in ("M_BingBongPlush", "M_Player"):
                continue
            print(f"{fname}: {d.m_Name} -> shader {shader_name(objects, d.m_Shader)}")
            print("   keywords:", list(d.m_ShaderKeywords or []))
            print("   props:", sorted(p[0] for p in d.m_SavedProperties.m_Floats))
            print("   texes:", sorted(p[0] for p in d.m_SavedProperties.m_TexEnvs))


if __name__ == "__main__":
    main()
