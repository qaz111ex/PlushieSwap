"""Compare outline-shell strategies by rendering each over the body.

Four candidates, all built from the same body submeshes:

  A current  : faces removed where the exact decal mask or a downward normal sits
               (what ships today) -> holes -> boundary edges -> broken line
  B uniform  : every face kept, uniform push (a closed hull)
  C widthmap : every face kept, push scaled by a smooth per-vertex width that goes to
               zero at the decals and the downward faces
  D bodyshell: only the body submeshes (decal submeshes dropped), uniform push

Renders are cropped to the head (where the decals are) and full-body, so both the
eye-ring behaviour and the silhouette can be judged.
"""
import os
import sys

import numpy as np

sys.path.insert(0, r"D:\zhuanban\Plushie Swap\tools")
import build_meshes as bm  # noqa: E402
import verify_merge as vm  # noqa: E402
from preview_mesh import sample_shading  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\research\preview"
THICK = 0.0075 * 0.9635


def boundary(t):
    if len(t) == 0:
        return 0
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    k = np.sort(e, axis=1)
    _u, c = np.unique(k, axis=0, return_counts=True)
    return int((c == 1).sum())


def concat_solid(subs):
    v, t, off = [], [], 0
    for s in subs:
        if s[5] & 1:
            continue
        v.append(s[1])
        t.append(s[4] + off)
        off += len(s[1])
    return np.concatenate(v), np.concatenate(t)


def render(body, shell_verts, shell_tris, out_path, size=640, zoom=None):
    v, t, uvs, lo, hi = body
    texture = vm.load_shading_texture(os.path.join(ASSETS, "miffy.psmesh"))
    albedo = sample_shading(texture, uvs)
    name = "x"
    merged = (name, v, np.zeros_like(v), uvs, t, lo, hi)
    # vm.render crops by extent around the bounds centre; pass zoom by shrinking extent
    vm.render(merged, texture, out_path, size=size,
              outline=(shell_verts, np.zeros_like(shell_verts), shell_tris))


def main():
    for stem in ("miffy", "zichaoxiong"):
        path = os.path.join(ASSETS, stem + ".psmesh")
        name, subs, lo, hi = vm.read_psmesh(path)
        solid = [s for s in subs if not (s[5] & 1)]
        v, t = concat_solid(subs)
        body = (v, t, np.concatenate([s[3] for s in solid]), lo, hi)
        height = float(hi[1] - lo[1])

        # masks on the solid-vertex indexing
        face_decal, grown = bm.find_face_features(
            [(None, s[1], None, s[4]) for s in solid], 0.045 * 0.9635)
        down = bm.downward_face_weight([(None, s[1], None, s[4]) for s in solid], 0.55)

        print("=" * 72)
        print(f"{stem}: {len(v)} verts, decal {int(face_decal.sum())}, "
              f"grown {int(grown.sum())}, down {int(down.sum())}")

        # hull from all solid verts
        sv, faces, on, origin = bm.build_outline_normals(v, t)

        def bake(faces_sub, width=None):
            sh = bm.build_cartoon_outline(sv, faces_sub, on, THICK,
                                          (0.085, 0.085, 0.105, 1.0), width=width)
            return sh[1], sh[4]

        # A: current — remove decal + downward faces
        keep = ~face_decal[origin]
        kf = keep[faces[:, 0]] & keep[faces[:, 1]] & keep[faces[:, 2]]
        a = faces[kf]
        pa = sv[a]
        fn = np.cross(pa[:, 1] - pa[:, 0], pa[:, 2] - pa[:, 0])
        ln = np.linalg.norm(fn, axis=1, keepdims=True); ln[ln < 1e-15] = 1
        a = a[(fn[:, 1] / ln[:, 0]) >= -0.55]
        va, ta = bake(a)
        print(f"  A current  : {len(a):>6d} tris  boundary {boundary(a):>5d}")

        # B: uniform, all faces
        vb, tb = bake(faces)
        print(f"  B uniform  : {len(faces):>6d} tris  boundary {boundary(faces):>5d}")

        # C: width map — smooth falloff from decals and downward faces
        w = np.ones(len(sv))
        w[grown[origin]] = 0.0
        w[down[origin]] = 0.0
        # smooth the width field over the hull surface so there is no step
        w = bm.smooth_scalar_over_surface(len(sv), faces, w, 3, 0.5)
        w[face_decal[origin]] = 0.0
        w[down[origin]] = 0.0
        vc, tc = bake(faces, width=w)
        print(f"  C widthmap : {len(faces):>6d} tris  boundary {boundary(faces):>5d}"
              f"  width<0.5 {int((w < 0.5).sum())}")

        # D: body-only hull (drop decal submeshes)
        body_subs = []
        off = 0
        for s in solid:
            sl = slice(off, off + len(s[1]))
            if face_decal[sl].mean() < 0.5:
                body_subs.append(s)
            off += len(s[1])
        bv, bt, boff = [], [], 0
        for s in body_subs:
            bv.append(s[1])
            bt.append(s[4] + boff)
            boff += len(s[1])
        bv, bt = np.concatenate(bv), np.concatenate(bt)
        bsv, bfaces, bon, borigin = bm.build_outline_normals(bv, bt)
        vd, td = bake(bfaces)
        print(f"  D bodyshell: {len(bfaces):>6d} tris  boundary {boundary(bfaces):>5d}")

        for tag, (vv, tt) in (("A", (va, ta)), ("B", (vb, tb)),
                              ("C", (vc, tc)), ("D", (vd, td))):
            render(body, vv, tt, os.path.join(OUT, f"cmp_{stem}_{tag}.png"))


if __name__ == "__main__":
    main()
