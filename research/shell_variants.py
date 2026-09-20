"""Build ink-shell direction variants as NPZ, for a Blender A/B.

The runtime does NOT draw the baked shell directly. Every frame it does:

    surface = shell - normal * thickness * width     (recover the body surface)
    draw at surface + screenOffset(normal, width)    (extrude in screen space)

so the *stored normal* is what decides where the line goes. In a concave groove the
normal points across the groove, the screen offset carries the vertex into the far
wall, and a dark line appears inside the body.

The fix is therefore a better **direction field**, not deleting vertices (deleting
breaks the line). Variants built here:

  normal       welded averaged face normals (ships today)
  smooth       normal field Laplacian-smoothed over the surface (standard toon fix)
  radial       straight out from the model centroid
  smooth_rad   smoothed normal blended with radial
  pushout      normal, but any vertex whose pushed position lands inside the body is
               redirected to the nearest direction that leaves the body

Each NPZ holds the body, the shell surface vertices, the direction field and the width.
"""
import os
import sys

import numpy as np

sys.path.insert(0, r"D:\zhuanban\Plushie Swap\tools")
import build_meshes as bm  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\research\blender"
THICK = 0.0075 * 0.9635
MODES = ("normal", "smooth", "radial", "smooth_rad", "pushout")


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
        verts = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        normals = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        o += vc * 8 + vc * 12
        idx = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3); o += ic * 4
        subs.append(dict(colour=colour, flags=flags, v=verts, n=normals, t=idx))
    return subs


def smooth_field(verts, tris, vecs, iterations, blend=0.7):
    edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]], axis=0)
    edges = np.concatenate([edges, edges[:, ::-1]], axis=0)
    result = vecs.copy()
    for _ in range(iterations):
        acc = np.zeros_like(result)
        cnt = np.zeros(len(result))
        np.add.at(acc, edges[:, 0], result[edges[:, 1]])
        np.add.at(cnt, edges[:, 0], 1.0)
        cnt[cnt < 1] = 1.0
        result = result * (1.0 - blend) + (acc / cnt[:, None]) * blend
        ln = np.linalg.norm(result, axis=1, keepdims=True)
        ln[ln < 1e-12] = 1.0
        result /= ln
    return result


def inside_test(pts, verts, tris, direction=(0.3123, 0.8231, 0.4747)):
    """Ray-parity inside test (no extra dependencies)."""
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    v0, v1, v2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    e1, e2 = v1 - v0, v2 - v0
    pvec = np.cross(d[None, :], e2)
    det = np.einsum("j,tj->t", d, np.cross(e1, e2))
    ok = np.abs(det) > 1e-12
    inv = np.zeros_like(det)
    inv[ok] = 1.0 / det[ok]
    res = np.zeros(len(pts), dtype=bool)
    for s in range(0, len(pts), 256):
        ch = pts[s:s + 256]
        tv = ch[:, None, :] - v0[None, :, :]
        u = np.einsum("ctj,tj->ct", tv, pvec) * inv[None, :]
        qv = np.cross(tv, e1[None, :, :])
        vv = np.einsum("ctj,j->ct", qv, d) * inv[None, :]
        tt = np.einsum("ctj,tj->ct", qv, e2) * inv[None, :]
        hit = ((u >= -1e-9) & (u <= 1 + 1e-9) & (vv >= -1e-9)
               & (u + vv <= 1 + 1e-9) & (tt > 1e-9))
        res[s:s + 256] = (hit.sum(axis=1) % 2) == 1
    return res


def nearest_surface(pts, verts, tris):
    """Nearest triangle centroid + face normal, via a KD-tree over face centroids.

    Good enough to pick an outward direction for a vertex that landed inside: the face
    centroid is within one triangle of the true nearest point, and only the *direction*
    away from the body is needed.
    """
    from scipy.spatial import cKDTree
    centroids = verts[tris].mean(axis=1)
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    fn = np.cross(b - a, c - a)
    ln = np.linalg.norm(fn, axis=1, keepdims=True)
    ln[ln < 1e-15] = 1.0
    fn = fn / ln
    _d, idx = cKDTree(centroids).query(pts, k=1, workers=-1)
    return centroids[idx], fn[idx]


def main():
    os.makedirs(OUT, exist_ok=True)
    for stem in ("miffy", "zichaoxiong"):
        subs = read(os.path.join(ASSETS, stem + ".psmesh"))
        solid = [s for s in subs if not (s["flags"] & 1)]

        bv = np.concatenate([s["v"] for s in solid])
        bt = []; off = 0
        for s in solid:
            bt.append(s["t"] + off); off += len(s["v"])
        bt = np.concatenate(bt)

        solid4 = [(s["colour"], s["v"], s["n"], s["t"]) for s in solid]
        fd, suppress = bm.find_face_features(solid4, 0.045 * 0.9635)
        down = bm.downward_face_weight(solid4, 0.55)
        enclosed = bm.inside_other_shell(solid4, 0.030 * 0.9635)

        sv, st, on, origin = bm.build_outline_normals(bv, bt)
        centroid = sv.mean(axis=0)
        radial = sv - centroid
        radial /= np.linalg.norm(radial, axis=1, keepdims=True)

        # Interior features keep zero width; the leaked (self-intersecting) vertices are
        # deliberately NOT zeroed — each variant is meant to stop them leaking by its
        # direction, so the line stays continuous.
        fade = np.ones(len(sv))
        fade[suppress[origin]] = 0.0
        fade[down[origin]] = 0.0
        fade[enclosed[origin]] = 0.0
        fade = bm.smooth_scalar_over_surface(len(sv), st, fade, 3, 0.5)
        fade[fd[origin]] = 0.0
        fade[down[origin]] = 0.0
        fade[enclosed[origin]] = 0.0

        smooth = smooth_field(sv, st, on, 14, 0.7)

        for mode in MODES:
            if mode == "normal":
                dirs = on
            elif mode == "smooth":
                dirs = smooth
            elif mode == "radial":
                dirs = radial
            elif mode == "smooth_rad":
                d = smooth + 0.8 * radial
                dirs = d / np.linalg.norm(d, axis=1, keepdims=True)
            else:  # pushout
                dirs = on.copy()
                pushed = sv + dirs * THICK
                inside = inside_test(pushed, bv, bt)
                if inside.any():
                    cents, fns = nearest_surface(pushed[inside], bv, bt)
                    target = cents + fns * (THICK * 0.5)
                    d = target - sv[inside]
                    ln = np.linalg.norm(d, axis=1, keepdims=True)
                    ln[ln < 1e-12] = 1.0
                    dirs[inside] = d / ln

            np.savez_compressed(
                os.path.join(OUT, f"v_{stem}_{mode}.npz"),
                body_v=bv.astype(np.float32), body_t=bt.astype(np.int32),
                surf=sv.astype(np.float32), shell_t=st.astype(np.int32),
                dirs=dirs.astype(np.float32), fade=fade.astype(np.float32),
                thickness=np.float32(THICK))
            print(f"wrote v_{stem}_{mode}.npz  dirs {dirs.shape}")


if __name__ == "__main__":
    main()
