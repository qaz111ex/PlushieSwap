"""Read the vanilla BingBong mesh's vertex colours.

That decides how W/Character treats `_UseRawVertexColor`: if the vanilla mesh carries
the plush's actual colours the shader uses vertex colour as albedo; if it is neutral
the albedo comes from _MainTex and vertex colour only modulates it.
"""
import os
import sys

import numpy as np
import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def main():
    env = UnityPy.load(os.path.join(GAME, "resources.assets"))
    for o in env.objects:
        if o.type.name != "Mesh":
            continue
        try:
            d = o.read()
        except Exception:
            continue
        if d.m_Name != "BingBong" or o.path_id != 1061:
            continue

        print("mesh:", d.m_Name, "pid", o.path_id)
        vd = d.m_VertexData
        print("vertexCount", vd.m_VertexCount)
        for ch in vd.m_Channels:
            print(f"  channel stream={ch.stream} offset={ch.offset} format={ch.format} dim={ch.dimension}")

        # channel 0 is usually position; colour is often the last channel or a named one
        raw = vd.m_Data if hasattr(vd, "m_Data") else None
        if raw is None:
            print("no raw data")
            continue
        data = bytes(raw)
        print("data bytes", len(data))

        # Try UnityPy's built-in helper if present
        try:
            verts, indices = vd.get_vertices(), None
            print("parsed positions:", len(verts))
        except Exception as e:
            print("get_vertices failed:", e)

        # Locate a colour channel by checking the attribute names UnityPy exposes
        for attr in dir(vd):
            if "olor" in attr or "olour" in attr:
                print("  attr", attr, getattr(vd, attr))

        # Fall back: decode channel 3 if it looks like a 4x float32 colour stream
        try:
            import struct
            stride = vd.m_VertexCount and (len(data) // vd.m_VertexCount)
            print("stride", stride)
        except Exception:
            pass
        break


if __name__ == "__main__":
    main()
