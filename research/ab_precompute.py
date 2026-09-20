"""Precompute the two shell variants (width map vs face deletion) as NPZ.

Blender's bundled Python has no scipy, so the geometry is computed here with the system
Python and Blender only renders it.
"""
import os
import sys

import numpy as np

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ROOT, "research", "blender")
sys.path.insert(0, os.path.join(ROOT, "tools"))

THICK = 0.0075 * 0.9635


def read(path):
    import struct
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
        v = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        nn = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        o += vc * 8 + vc * 12
        t = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3); o += ic * 4
        subs.append((colour, flags, v, nn, t))
    return subs


def main():
    import build_meshes as bm
    os.makedirs(OUT, exist_ok=True)

    for stem in ("miffy", "zichaoxiong"):
        subs = read(os.path.join(ASSETS, stem + ".psmesh"))
        solid = [s for s in subs if not (s[1] & 1)]

        bv = np.concatenate([s[2] for s in solid])
        bt = []; off = 0
        for s in solid:
            bt.append(s[4] + off); off += len(s[2])
        bt = np.concatenate(bt)

        solid4 = [(s[0], s[2], s[3], s[4]) for s in solid]
        fd, suppress = bm.find_face_features(solid4, 0.045 * 0.9635)
        down = bm.downward_face_weight(solid4, 0.55)
        enclosed = bm.inside_other_shell(solid4, 0.030 * 0.9635)

        sv, st, on, origin = bm.build_outline_normals(bv, bt)
        hidden = np.zeros(len(sv), dtype=bool)
        hidden[suppress[origin]] = True
        hidden[down[origin]] = True
        hidden[enclosed[origin]] = True
        hidden[fd[origin]] = True

        # A: keep every face, zero the hidden vertices' push
        w = np.where(hidden, 0.0, 1.0)
        shell_a = sv + on * (THICK * w)[:, None]
        mixed = (((w[st[:, 0]] > 0.5) != (w[st[:, 1]] > 0.5))
                 | ((w[st[:, 1]] > 0.5) != (w[st[:, 2]] > 0.5))
                 | ((w[st[:, 0]] > 0.5) != (w[st[:, 2]] > 0.5)))
        print(f"{stem} A width : {int(mixed.sum())} mixed faces of {len(st)}")

        # B: delete every face with a hidden corner
        keep = ~(hidden[st[:, 0]] | hidden[st[:, 1]] | hidden[st[:, 2]])
        st_b = st[keep]
        shell_b = sv + on * THICK
        print(f"{stem} B delete: removed {len(st) - len(st_b)}, left {len(st_b)}")

        np.savez_compressed(
            os.path.join(OUT, f"ab_{stem}.npz"),
            body_v=bv.astype(np.float32), body_t=bt.astype(np.int32),
            a_v=shell_a.astype(np.float32), a_t=st.astype(np.int32),
            b_v=shell_b.astype(np.float32), b_t=st_b.astype(np.int32))


if __name__ == "__main__":
    main()
