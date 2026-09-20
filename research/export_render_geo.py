"""Export the shipped body + ink shell to OBJ for a Blender render.

The shell is exported exactly as it is baked (per-vertex width already applied), which
is the geometry the runtime starts from. Rendering it in Blender with backface culling
turned on reproduces the game's inverted-hull draw, so a real 3D renderer can be used to
check the line is continuous and even rather than trusting a hand-written rasteriser.
"""
import os
import struct
import sys

import numpy as np

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\research\blender"


def read(path):
    with open(path, "rb") as fh:
        d = fh.read()
    o = 8
    n = struct.unpack_from("<i", d, o)[0]; o += 4 + n
    count = struct.unpack_from("<i", d, o)[0]; o += 4
    subs = []
    for _ in range(count):
        colour = np.array(struct.unpack_from("<4f", d, o)); o += 16
        flags = struct.unpack_from("<i", d, o)[0]; o += 4
        vc, ic = struct.unpack_from("<ii", d, o); o += 8
        verts = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        o += vc * 12 + vc * 8 + vc * 12
        idx = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3); o += ic * 4
        subs.append((colour, flags, verts, idx))
    return subs


def write_obj(path, groups):
    """groups: list of (name, verts, tris)."""
    with open(path, "w", encoding="utf-8") as fh:
        base = 1
        for name, verts, tris in groups:
            fh.write(f"o {name}\n")
            for v in verts:
                fh.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
            for t in tris:
                fh.write(f"f {t[0]+base} {t[1]+base} {t[2]+base}\n")
            base += len(verts)
    print("wrote", path)


def main():
    os.makedirs(OUT, exist_ok=True)
    for stem in ("miffy", "zichaoxiong"):
        subs = read(os.path.join(ASSETS, stem + ".psmesh"))
        groups = []
        for i, (colour, flags, verts, idx) in enumerate(subs):
            name = ("shell" if flags & 1 else f"body{i}")
            groups.append((name, verts, idx))
        write_obj(os.path.join(OUT, f"{stem}_render.obj"), groups)


if __name__ == "__main__":
    main()
