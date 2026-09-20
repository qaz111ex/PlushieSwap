"""Locate the outline shell's boundary edges and test a closed-shell variant.

Boundary edges are where the ink line stops. This reports where they are (by height
and by proximity to the face decals) so the cause is known rather than assumed, then
builds the candidate fix: a hull made of the whole body shells with the face-decal
shells excluded ENTIRELY (they are separate raised shells, so no hole is left) and no
downward-face removal at all.
"""
import os
import sys

import numpy as np

sys.path.insert(0, r"D:\zhuanban\Plushie Swap\tools")
import build_meshes as bm  # noqa: E402
import verify_merge as vm  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"


def boundary_edges(tris):
    edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]], axis=0)
    key = np.sort(edges, axis=1)
    _u, counts = np.unique(key, axis=0, return_counts=True)
    return int((counts == 1).sum())


def main():
    for stem in ("miffy", "zichaoxiong"):
        path = os.path.join(ASSETS, stem + ".psmesh")
        name, subs, lo, hi = vm.read_psmesh(path)
        height = float(hi[1] - lo[1])

        solid = [(i, s) for i, s in enumerate(subs) if not (s[5] & 1)]
        decal, grown = bm.find_face_features(
            [(None, s[1], None, s[4]) for _, s in solid], 0.045 * 0.9635)

        print("=" * 74)
        print(f"{stem}: height {height:.4f}  Y[{lo[1]:+.3f},{hi[1]:+.3f}]")

        # Per-submesh decal classification (find_face_features is all-or-nothing).
        off = 0
        decal_subs = []
        for idx, s in solid:
            sl = slice(off, off + len(s[1]))
            frac = float(decal[sl].mean())
            ext = s[1].max(0) - s[1].min(0)
            area = 0.5 * np.linalg.norm(
                np.cross(s[1][s[4][:, 1]] - s[1][s[4][:, 0]],
                         s[1][s[4][:, 2]] - s[1][s[4][:, 0]]), axis=1).sum()
            print(f"  sub{idx}: decal {frac*100:5.1f}%  area {area:7.4f}  ext {np.round(ext,3)}")
            if frac > 0.5:
                decal_subs.append(idx)
            off += len(s[1])
        print(f"  -> decal submeshes: {decal_subs}")

        # --- current: all solid verts, remove decal+downward faces ---
        v = np.concatenate([s[1] for _, s in solid])
        t = np.concatenate([s[4] + o for s, o in
                            zip([s for _, s in solid],
                                np.cumsum([0] + [len(s[1]) for _, s in solid])[:-1])])
        sv, faces, on, origin = bm.build_outline_normals(v, t)
        keep = ~decal[origin]
        kf = keep[faces[:, 0]] & keep[faces[:, 1]] & keep[faces[:, 2]]
        a = faces[kf]
        # add downward removal
        a2 = a.copy()
        if len(a2):
            p = sv[a2]
            fn = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
            ln = np.linalg.norm(fn, axis=1, keepdims=True); ln[ln < 1e-15] = 1
            a2 = a2[(fn[:, 1] / ln[:, 0]) >= -0.55]
        print(f"  A current (decal+down removed): {len(a2):>6d} tris, "
              f"{boundary_edges(a2):>5d} boundary edges")

        # --- candidate: exclude decal SHELLS wholly, keep every other face ---
        body = [(idx, s) for idx, s in solid if idx not in decal_subs]
        bv = np.concatenate([s[1] for _, s in body])
        bt = np.concatenate([s[4] + o for s, o in
                             zip([s for _, s in body],
                                 np.cumsum([0] + [len(s[1]) for _, s in body])[:-1])])
        bsv, bfaces, bon, borigin = bm.build_outline_normals(bv, bt)
        used = len(np.unique(bfaces))
        print(f"  B closed (decal shells dropped): {len(bfaces):>6d} tris, "
              f"{boundary_edges(bfaces):>5d} boundary edges, "
              f"{len(bsv)} verts ({len(bsv)-used} dead)")

        # Where are the current boundaries?
        if len(a2):
            e = np.concatenate([a2[:, [0, 1]], a2[:, [1, 2]], a2[:, [2, 0]]], axis=0)
            key = np.sort(e, axis=1)
            _u, counts = np.unique(key, axis=0, return_counts=True)
            bnd = _u[counts == 1]
            ys = sv[np.unique(bnd)][:, 1]
            frac = (ys - lo[1]) / height
            hist, edges = np.histogram(frac, bins=10, range=(0, 1))
            print("  current boundary edges by height fraction:")
            for h, e0 in zip(hist, edges):
                print(f"    {e0:.1f}-{e0+0.1:.1f}: {'#'*int(h)} {h}")


if __name__ == "__main__":
    main()
