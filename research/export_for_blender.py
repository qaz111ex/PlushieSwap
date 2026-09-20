"""Export a .psmesh's solid parts to OBJ (and the shipped shell to OBJ), so Blender can
be used to compare its own inverted-hull (Solidify) against the pipeline's.
"""
import os
import struct
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ROOT, "research", "blender")


def read(path):
    with open(path, "rb") as fh:
        d = fh.read()
    o = 8
    n = struct.unpack_from("<i", d, o)[0]; o += 4 + n
    count = struct.unpack_from("<i", d, o)[0]; o += 4
    subs = []
    for _ in range(count):
        o += 16
        flags = struct.unpack_from("<i", d, o)[0]; o += 4
        vc, ic = struct.unpack_from("<ii", d, o); o += 8
        verts = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        o += vc * 12 + vc * 8 + vc * 12
        idx = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3); o += ic * 4
        subs.append((flags, verts, idx))
    return subs


def write_obj(path, verts, tris, name):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# {name}\n")
        for v in verts:
            fh.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for t in tris:
            fh.write(f"f {t[0]+1} {t[1]+1} {t[2]+1}\n")
    print("wrote", path, len(verts), "verts", len(tris), "tris")


def main():
    os.makedirs(OUT, exist_ok=True)
    for stem in ("miffy", "zichaoxiong"):
        subs = read(os.path.join(ASSETS, stem + ".psmesh"))
        solid = [s for s in subs if not (s[0] & 1)]
        shell = [s for s in subs if s[0] & 1]

        v = np.concatenate([s[1] for s in solid])
        t = []; off = 0
        for s in solid:
            t.append(s[2] + off); off += len(s[1])
        t = np.concatenate(t)
        write_obj(os.path.join(OUT, f"{stem}_body.obj"), v, t, f"{stem}_body")

        if shell:
            sv = shell[0][1]
            st = shell[0][2]
            write_obj(os.path.join(OUT, f"{stem}_shell_shipped.obj"), sv, st,
                      f"{stem}_shell_shipped")


if __name__ == "__main__":
    main()
