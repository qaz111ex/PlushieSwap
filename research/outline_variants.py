"""Compare outline-shell strategies on the real model data.

The shipped shell removes faces (face decals + downward-facing) from the inverted
hull. That leaves boundary edges, and a boundary edge is exactly where the ink line
stops — the "dashed, broken" outline the user reports.

This builds three candidates from the same body mesh and measures each:

  A. current  - faces removed (what ships today)
  B. closed   - every face kept, uniform push (a closed manifold)
  C. widthmap - every face kept, per-vertex push scaled by a mask

For each it reports boundary edges (0 is a closed surface), then renders the shell
drawn with front faces culled over the body, so the line can be judged by eye.
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


def boundary_edges(tris):
    edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]], axis=0)
    key = np.sort(edges, axis=1)
    _u, counts = np.unique(key, axis=0, return_counts=True)
    return int((counts == 1).sum()), int((counts > 2).sum())


def load_body(path):
    """Concatenated solid submeshes, welded, with shading colours, in the
    pipeline's pre-shading 6-tuple layout."""
    name, subs, lo, hi = vm.read_psmesh(path)
    verts, tris, uvs = [], [], []
    off = 0
    for s in subs:
        if s[5] & 1:
            continue
        verts.append(s[1])
        tris.append(s[4] + off)
        uvs.append(s[3])
        off += len(s[1])
    return (np.concatenate(verts), np.concatenate(tris), np.concatenate(uvs), lo, hi)


def build_shell(v, t, thickness, mask=None, downward=None):
    sv, faces, on, _origin = bm.build_outline_normals(v, t)
    if mask is not None:
        keep = mask[_origin]
        keep_faces = keep[faces[:, 0]] & keep[faces[:, 1]] & keep[faces[:, 2]]
        faces = faces[keep_faces]
    width = None
    if downward is not None:
        width = 1.0 - downward[_origin]
    shell = bm.build_cartoon_outline(sv, faces, on, thickness,
                                     (0.085, 0.085, 0.105, 1.0), width=width)
    return shell


def render_with_shell(body, shell, out_path, size=520):
    """Render the body, then the shell with front-face culling (an outline)."""
    verts, tris, uvs, lo, hi = body
    name, subs, _lo, _hi = vm.read_psmesh(os.path.join(ASSETS, "miffy.psmesh"))
    texture = vm.load_shading_texture(os.path.join(ASSETS, "miffy.psmesh"))
    albedo = sample_shading(texture, uvs)
    merged = (name, verts, np.zeros_like(verts), uvs, tris, lo, hi)
    vm.render(merged, texture, out_path, size=size,
              outline=(shell[1], shell[2], shell[4]))


def main():
    for stem in ("miffy", "zichaoxiong"):
        path = os.path.join(ASSETS, stem + ".psmesh")
        name, subs, lo, hi = vm.read_psmesh(path)
        thickness = 0.0075 * 0.9635

        v, t, uvs, lo, hi = load_body(path)
        print("=" * 72)
        print(f"{stem}: body {len(v)} verts / {len(t)} tris")

        # A: current (face removal)
        face_decal, _suppress = bm.find_face_features(
            [(None, v, None, t)], 0.045 * 0.9635)
        # The real pipeline computes this on pre-shading submeshes; approximate with
        # the body we have so the comparison is apples-to-apples.
        sv, faces, on, origin = bm.build_outline_normals(v, t)
        keep = ~face_decal[origin]
        kf = keep[faces[:, 0]] & keep[faces[:, 1]] & keep[faces[:, 2]]
        a_tris = faces[kf]
        b, n2 = boundary_edges(a_tris)
        print(f"  A current : {len(a_tris):>6d} tris, {b:>5d} boundary edges, {n2} non-manifold")

        # B: closed
        b_tris = faces
        b, n2 = boundary_edges(b_tris)
        print(f"  B closed  : {len(b_tris):>6d} tris, {b:>5d} boundary edges, {n2} non-manifold")

        # C: width map (same topology as B, push scaled)
        c_tris = faces
        b, n2 = boundary_edges(c_tris)
        print(f"  C widthmap: {len(c_tris):>6d} tris, {b:>5d} boundary edges, {n2} non-manifold")

        # Render B (closed, uniform) over the body to judge the line and the decal ring.
        shell_b = bm.build_cartoon_outline(sv, faces, on, thickness,
                                           (0.085, 0.085, 0.105, 1.0))
        render_with_shell((v, t, uvs, lo, hi), shell_b,
                          os.path.join(OUT, f"shellclosed_{stem}.png"))

        # Render A (current) for comparison.
        shell_a = bm.build_cartoon_outline(sv, a_tris, on, thickness,
                                           (0.085, 0.085, 0.105, 1.0))
        render_with_shell((v, t, uvs, lo, hi), shell_a,
                          os.path.join(OUT, f"shellcut_{stem}.png"))


if __name__ == "__main__":
    main()
