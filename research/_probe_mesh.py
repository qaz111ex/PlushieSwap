import os

import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
env = UnityPy.load(os.path.join(GAME, "resources.assets"))
for o in env.objects:
    if o.type.name != "Mesh":
        continue
    d = o.read()
    if d.m_Name != "BingBong":
        continue
    vd = d.m_VertexData
    print("count", vd.m_VertexCount, "dataSize", vd.m_DataSize)
    for i in range(4):
        s = getattr(vd, f"m_Streams_{i}_", None)
        print("  stream", i, type(s).__name__, len(s) if s else 0)
    break
