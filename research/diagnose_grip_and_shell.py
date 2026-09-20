"""Check whether the grip anchors are buried inside the model, and how holed the shell is.

The user reports two visual faults that point at geometry rather than parameters:

  * the hands vanish when holding the bear, and
  * the outline is uneven and broken.

Both have the same kind of cause: a point placed by silhouette *extent* alone can sit
inside a rounded body, and a shell that has had too many faces deleted cannot draw a
continuous line. This measures both directly.
"""
import os
import sys

import numpy as np

sys.path.insert(0, r"D:\zhuanban\Plushie Swap\tools")
from preview_mesh import read_psmesh  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"


def inside_body(point, verts, tris):
    """Odd-crossings ray test in 3D."""
    direction = np.array([0.3123, 0.8231, 0.4747])
    direction /= np.linalg.norm(direction)
    v0, v1, v2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    e1, e2 = v1 - v0, v2 - v0
    pvec = np.cross(direction[None, :], e2)
    det = np.einsum("j,tj->t", direction, np.cross(e1, e2))
    ok = np.abs(det) > 1e-12
    inv = np.zeros_like(det)
    inv[ok] = 1.0 / det[ok]
    tvec = point[None, :] - v0
    u = np.einsum("tj,tj->t", tvec, pvec) * inv
    qvec = np.cross(tvec, e1)
    v = np.einsum("tj,j->t", qvec, direction) * inv
    t = np.einsum("tj,tj->t", qvec, e2) * inv
    hit = (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (t > 1e-9)
    return int(hit.sum()) % 2 == 1


def main():
    for stem in ("miffy", "zichaoxiong"):
        name, subs, lo, hi = read_psmesh(os.path.join(ASSETS, stem + ".psmesh"))
        solid = [s for s in subs if not (s[5] & 1)]
        shell = [s for s in subs if (s[5] & 1)]
        verts = np.concatenate([s[1] for s in solid]).astype(np.float64)
        tris, off = [], 0
        for s in solid:
            tris.append(s[4] + off)
            off += len(s[1])
        tris = np.concatenate(tris)

        height = float(hi[1] - lo[1])
        print("=" * 70)
        print(f"{stem}: body {len(verts)} verts")

        # ---- grips: are they inside the body? ----
        with open(os.path.join(ASSETS, stem + ".psmesh"), "rb") as fh:
            data = fh.read()
        # read grips from the tail region by re-using the parsed stream layout
        import struct
        o = 8
        n = struct.unpack_from("<i", data, o)[0]
        o += 4 + n
        cnt = struct.unpack_from("<i", data, o)[0]
        o += 4
        for _ in range(cnt):
            o += 20
            vc, ic = struct.unpack_from("<ii", data, o)
            o += 8 + vc * 12 + vc * 12 + vc * 8 + vc * 12 + ic * 4
        o += 24
        has = struct.unpack_from("<i", data, o)[0]
        o += 4
        gl = gr = None
        if has:
            gl = np.array(struct.unpack_from("<3f", data, o))
            gr = np.array(struct.unpack_from("<3f", data, o + 12))
        print(f"  grip L anchor {np.round(gl, 4)}  -> inside body: {inside_body(gl, verts, tris)}")
        print(f"  grip R anchor {np.round(gr, 4)}  -> inside body: {inside_body(gr, verts, tris)}")

        # nearest surface distance, as a proxy for how buried it is
        from scipy.spatial import cKDTree
        tree = cKDTree(verts)
        dl, _ = tree.query(gl, k=1)
        dr, _ = tree.query(gr, k=1)
        print(f"  distance to nearest surface: L {dl:.4f}  R {dr:.4f} "
              f"(hand radius is about 0.05)")

        # ---- shell coverage: how much of the body is outlined ----
        if shell:
            sv = np.concatenate([s[1] for s in shell])
            st = np.concatenate([s[4] + (sum(len(x[1]) for x in shell[:i]))
                                 for i, s in enumerate(shell)])
            edges = np.concatenate([st[:, [0, 1]], st[:, [1, 2]], st[:, [2, 0]]], axis=0)
            key = np.sort(edges, axis=1)
            _, counts = np.unique(key, axis=0, return_counts=True)
            boundary = int((counts == 1).sum())
            used = len(np.unique(st))
            print(f"  shell: {len(sv)} verts, {len(st)} tris, {used} used verts, "
                  f"{len(sv) - used} dead, {boundary} boundary edges")
            body_area = sum(np.linalg.norm(
                np.cross(verts[t[:, 1]] - verts[t[:, 0]], verts[t[:, 2]] - verts[t[:, 0]]),
                axis=1).sum() * 0.5 for t in [tris])
            print(f"  body area {body_area:.4f}")


if __name__ == "__main__":
    main()
