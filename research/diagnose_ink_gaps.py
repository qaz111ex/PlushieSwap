"""Why does the ink stop where the arms meet the body?

Renders the front view and, for every pixel on the silhouette, reports which of the
build's masks suppressed the ink there. The masks are:

  suppress  : the face-feature padding around eyes / mouth / blush
  face_decal: the features themselves
  down      : downward-facing surfaces
  enclosed  : vertices inside another shell
  mixed     : faces dropped because not all three corners carried ink

A silhouette segment with no ink and no mask explaining it is a genuine bug in the
extrusion direction; a segment explained by `enclosed` or `down` is a mask that is
too aggressive.
"""
import os
import struct
import sys

import numpy as np

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")
sys.path.insert(0, os.path.join(ROOT, "tools"))


def read_subs(path):
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
        v = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3).astype(np.float64); o += vc * 12
        nn = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3).astype(np.float64); o += vc * 12
        o += vc * 8 + vc * 12
        t = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3).astype(np.int64); o += ic * 4
        subs.append((colour, flags, v, nn, t))
    return subs


def main():
    import build_meshes as bm

    for stem in ("miffy", "zichaoxiong"):
        subs = read_subs(os.path.join(ASSETS, stem + ".psmesh"))
        solid = [s for s in subs if not (s[1] & 1)]

        bv = np.concatenate([s[2] for s in solid])
        bt = []
        off = 0
        for s in solid:
            bt.append(s[4] + off); off += len(s[2])
        bt = np.concatenate(bt)
        print(f"===== {stem} : {len(bt)} body tris =====")

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

        keep = ~(hidden[st[:, 0]] | hidden[st[:, 1]] | hidden[st[:, 2]])
        print(f"  body verts {len(bv)}  shell verts {len(sv)}  shell tris {len(st)}")
        print(f"  mask coverage (per body vertex): suppress {suppress.mean()*100:.1f}%  "
              f"down {down.mean()*100:.1f}%  enclosed {enclosed.mean()*100:.1f}%  "
              f"face_decal {fd.mean()*100:.1f}%")
        print(f"  faces kept {keep.sum()} / {len(st)}  ({keep.mean()*100:.1f}%)")

        # where are the dropped faces?
        dropped = st[~keep]
        if len(dropped):
            dp = (sv[dropped[:, 0]] + sv[dropped[:, 1]] + sv[dropped[:, 2]]) / 3.0
            lo = bv.min(axis=0); hi = bv.max(axis=0)
            print(f"  dropped-face centroid range  "
                  f"X[{dp[:,0].min():+.3f},{dp[:,0].max():+.3f}] "
                  f"Y[{dp[:,1].min():+.3f},{dp[:,1].max():+.3f}] "
                  f"Z[{dp[:,2].min():+.3f},{dp[:,2].max():+.3f}]")
            print(f"  body bounds                  "
                  f"X[{lo[0]:+.3f},{hi[0]:+.3f}] Y[{lo[1]:+.3f},{hi[1]:+.3f}] "
                  f"Z[{lo[2]:+.3f},{hi[2]:+.3f}]")

            # How many dropped faces are dropped ONLY because of `enclosed`?
            only_enclosed = enclosed[st[:, 0]] | enclosed[st[:, 1]] | enclosed[st[:, 2]]
            only_down = down[st[:, 0]] | down[st[:, 1]] | down[st[:, 2]]
            only_suppress = suppress[st[:, 0]] | suppress[st[:, 1]] | suppress[st[:, 2]]
            only_fd = fd[st[:, 0]] | fd[st[:, 1]] | fd[st[:, 2]]
            print(f"  faces touched by enclosed : {only_enclosed.sum()}")
            print(f"  faces touched by down     : {only_down.sum()}")
            print(f"  faces touched by suppress : {only_suppress.sum()}")
            print(f"  faces touched by face_decal: {only_fd.sum()}")

        # Is the ink actually reaching the silhouette? Test: project the shell along -Z
        # (front view) and compare the outline of the kept shell with the outline of the
        # body.
        def silhouette_extent(pos, axis_keep):
            return pos[:, axis_keep]

        # front view: screen x = model x, screen y = model y, depth = z
        kept_v = np.zeros(len(sv), dtype=bool)
        kept_v[np.unique(st[keep])] = True
        body_lo = bv[:, 0].min()
        body_hi = bv[:, 0].max()
        shell_x = sv[kept_v][:, 0]
        print(f"  body X range [{body_lo:+.4f},{body_hi:+.4f}]  "
              f"kept-shell X range [{shell_x.min():+.4f},{shell_x.max():+.4f}]")

        # per height band, compare leftmost body vertex with leftmost kept shell vertex
        print("  band   bodyXmin  shellXmin   bodyXmax  shellXmax   (front view)")
        n = 24
        ylo, yhi = bv[:, 1].min(), bv[:, 1].max()
        for k in range(n):
            y0 = ylo + (yhi - ylo) * k / n
            y1 = ylo + (yhi - ylo) * (k + 1) / n
            bm_band = bv[(bv[:, 1] >= y0) & (bv[:, 1] < y1)]
            sh_band = sv[kept_v & (sv[:, 1] >= y0) & (sv[:, 1] < y1)]
            if len(bm_band) == 0:
                continue
            if len(sh_band) == 0:
                print(f"  {k/n:.2f}  {bm_band[:,0].min():+.4f}   ---- NO SHELL ----")
                continue
            print(f"  {k/n:.2f}  {bm_band[:,0].min():+.4f}  {sh_band[:,0].min():+.4f}   "
                  f"{bm_band[:,0].max():+.4f}  {sh_band[:,0].max():+.4f}")


if __name__ == "__main__":
    main()
