"""Dump the body, the welded surface and several candidate extrusion directions.

The runtime draws the shell as `surface + screenOffset(direction)`, so the *direction
field* is what decides where the ink lands. In a concave groove the averaged normal
points across the groove and the ink lands on the far wall (a dark line inside the
model). This writes the same surface with several direction fields so a real renderer
(Blender) can be used to pick the best one instead of trusting a hand-written test.

Directions written:
  normal      welded averaged face normals (what ships today)
  smooth      normal field Laplacian-smoothed over the surface
  radial      straight out from the model centroid
  blend       smoothed normal mixed with radial
  pushout     normal, but vertices whose push lands inside the body are redirected to
              the nearest direction that leaves the body
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, r"D:\zhuanban\Plushie Swap\tools")
import build_meshes as bm  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\research\blender"
THICK = 0.0075 * 0.9635


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
        v = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        nn = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        o += vc * 8 + vc * 12
        t = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3); o += ic * 4
        subs.append(dict(colour=colour, flags=flags, v=v, n=nn, t=t))
    return subs


def smooth_field(verts, tris, vecs, iterations, blend=0.7):
    edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]], axis=0)
    edges = np.concatenate([edges, edges[:, ::-1]], axis=0)
    out = vecs.copy()
    for _ in range(iterations):
        acc = np.zeros_like(out); cnt = np.zeros(len(out))
        np.add.at(acc, edges[:, 0], out[edges[:, 1]])
        np.add.at(cnt, edges[:, 0], 1.0)
        cnt[cnt < 1] = 1.0
        out = out * (1.0 - blend) + (acc / cnt[:, None]) * blend
        ln = np.linalg.norm(out, axis=1, keepdims=True); ln[ln < 1e-12] = 1.0
        out /= ln
    return out


def ray_inside(pts, verts, tris):
    d = np.array([0.3123, 0.8231, 0.4747]); d /= np.linalg.norm(d)
    v0, v1, v2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    e1, e2 = v1 - v0, v2 - v0
    pvec = np.cross(d[None, :], e2)
    det = np.einsum("j,tj->t", d, np.cross(e1, e2))
    ok = np.abs(det) > 1e-12
    inv = np.zeros_like(det); inv[ok] = 1.0 / det[ok]
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
        smooth = smooth_field(sv, st, on, 16, 0.75)

        # Width: only the interior features are zeroed (eyes, blush, downward faces,
        # enclosed shells). The leaked vertices are NOT zeroed here — the direction
        # field is supposed to stop them leaking while keeping the line continuous.
        fade = np.ones(len(sv))
        fade[suppress[origin]] = 0.0
        fade[down[origin]] = 0.0
        fade[enclosed[origin]] = 0.0
        fade = bm.smooth_scalar_over_surface(len(sv), st, fade, 3, 0.5)
        fade[fd[origin]] = 0.0
        fade[down[origin]] = 0.0
        fade[enclosed[origin]] = 0.0

        # pushout: redirect any vertex whose push lands inside the body.
        dirs_pushout = on.copy()
        pushed = sv + dirs_pushout * THICK
        inside = ray_inside(pushed, bv, bt)
        if inside.any():
            # outward direction = away from the nearest body vertex, chosen by majority
            from scipy.spatial import cKDTree
            tree = cKDTree(bv)
            _d, idx = tree.query(sv[inside], k=8, workers=-1)
            nb = bv[idx]                       # (m, 8, 3)
            away = sv[inside][:, None, :] - nb
            ln = np.linalg.norm(away, axis=2, keepdims=True); ln[ln < 1e-12] = 1.0
            away = (away / ln).sum(axis=1)
            ln2 = np.linalg.norm(away, axis=1, keepdims=True); ln2[ln2 < 1e-12] = 1.0
            dirs_pushout[inside] = away / ln2

        np.savez_compressed(
            os.path.join(OUT, f"dirs_{stem}.npz"),
            body_v=bv.astype(np.float32), body_t=bt.astype(np.int32),
            surf=sv.astype(np.float32), shell_t=st.astype(np.int32),
            fade=fade.astype(np.float32),
            normal=on.astype(np.float32), smooth=smooth.astype(np.float32),
            radial=radial.astype(np.float32), pushout=dirs_pushout.astype(np.float32),
            thickness=np.float32(THICK))
        print(f"wrote dirs_{stem}.npz  verts {len(sv)}  leaked {int(inside.sum())}")


if __name__ == "__main__":
    main()
