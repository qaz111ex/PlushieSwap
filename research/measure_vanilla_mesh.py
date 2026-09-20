"""Decode the vanilla BingBong mesh and compare it with its own hand anchors.

The mod keeps the vanilla hand anchors and shifts the model to meet them. Whether the
hands then touch the plush depends entirely on how wide the vanilla plush is at the
anchor height. This decodes the vanilla mesh vertices (Unity stores them in a
VertexData blob) and prints the width profile against the anchor Y values, so the
grip height is chosen from the real item instead of from an assumption.
"""
import os

import numpy as np
import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"


def decode_positions(mesh):
    vd = mesh.m_VertexData
    count = vd.m_VertexCount
    streams = []
    for i in range(4):
        s = getattr(vd, f"m_Streams_{i}_", None)
        streams.append(bytes(s) if s else b"")

    # channel 0 is position (dimension 3, float32)
    pos_ch = vd.m_Channels[0]
    if pos_ch.dimension != 3:
        return np.zeros((0, 3))

    stream = streams[pos_ch.stream]
    stride = len(stream) // max(1, count)
    out = np.zeros((count, 3), dtype=np.float64)
    for i in range(count):
        off = i * stride + pos_ch.offset
        out[i] = np.frombuffer(stream, "<f4", 3, off).astype(np.float64)
    return out


def main():
    env = UnityPy.load(os.path.join(GAME, "resources.assets"))
    objects = {o.path_id: o for o in env.objects}

    for o in env.objects:
        if o.type.name != "Mesh":
            continue
        d = o.read()
        if d.m_Name != "BingBong":
            continue
        pos = decode_positions(d)
        print(f"mesh {d.m_Name}: {len(pos)} verts")
        if len(pos) == 0:
            continue
        lo, hi = pos.min(axis=0), pos.max(axis=0)
        print(f"  bounds X[{lo[0]:+.4f},{hi[0]:+.4f}] Y[{lo[1]:+.4f},{hi[1]:+.4f}] "
              f"Z[{lo[2]:+.4f},{hi[2]:+.4f}]")
        print(f"  size {np.round(hi-lo,4)}")
        print("  channel attributes:", sorted(set(ch.attribute for ch in d.m_VertexData.m_Channels)))

        # anchors from the prefab dump
        anchors = {"Hand_L": np.array([-0.359, -0.177, -0.040]),
                   "Hand_R": np.array([0.240, -0.104, -0.040])}
        for k, a in anchors.items():
            frac = (a[1] - lo[1]) / (hi[1] - lo[1])
            print(f"  {k} at y={a[1]:+.3f} -> height fraction {frac:.3f}")

        n = 24
        print("  band  y range            x range                 halfw  full  ")
        for k in range(n):
            y0 = lo[1] + (hi[1] - lo[1]) * k / n
            y1 = lo[1] + (hi[1] - lo[1]) * (k + 1) / n
            band = pos[(pos[:, 1] >= y0) & (pos[:, 1] < y1)]
            if len(band) == 0:
                continue
            halfw = (band[:, 0].max() - band[:, 0].min()) * 0.5
            print(f"  {k/n:.2f}  [{y0:+.3f},{y1:+.3f}]  "
                  f"[{band[:,0].min():+.3f},{band[:,0].max():+.3f}]  "
                  f"{halfw:.3f}  {2*halfw:.3f}")


if __name__ == "__main__":
    main()
