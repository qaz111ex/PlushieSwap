"""Convert Bambu Studio 3MF -> compact runtime mesh for Plushie Swap.

Quality strategy
----------------
Bambu multi-colour prints are built from several *separate solid shells*, one per
filament (eyes, blush, stripes, dress ...).  Those shells overlap the body surface
instead of sharing edges with it.  That means:

  * colour regions never share geometry, so they can be simplified independently
    without ever opening a seam / crack,
  * small shells (eyes, blush, stripes, mouth) stay at full resolution so the face
    keeps every detail,
  * only the big smooth shells (body, head, dress) get decimated.

Normals are rebuilt from scratch with a smoothing-angle split, so soft plush
surfaces stay smooth while sharp rims stay sharp.

Colour overrides
----------------
The source 3MF declares filament 4 as pink #F95D73 but paints the blush with
filament 2 (orange).  The blush shells are the only geometry using filament 2, so
the override below simply restores the intended pink.

Output: .psmesh (see write_psmesh for the binary layout).
"""
import hashlib
import json
import os
import struct
import sys
from collections import defaultdict

import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from threemf import load_3mf  # noqa: E402

try:
    import fast_simplification
except ImportError:  # pragma: no cover
    fast_simplification = None

# Silence used to be the failure mode here: without the decimator, simplify() returns
# its input unchanged, the model ships at full resolution (measured: 220324 faces
# instead of 13710, ~16x the .psmesh), and every gate still passed because they only
# compare hashes against whatever was built. Warn loudly at import time; simplify()
# warns again per shell so the message is impossible to miss in a build log.
if fast_simplification is None:  # pragma: no cover
    print("WARNING: fast_simplification is not installed - meshes will NOT be "
          "decimated and the .psmesh files will be far larger than intended.\n"
          "         Install it with: python -m pip install -r requirements.txt",
          file=sys.stderr)


MAGIC = b"PSMESH03"


# ------------------------------------------------------------------ utilities
def _hex_to_unit(text):
    text = text.strip().lstrip("#")
    if len(text) == 8:
        text = text[:6]
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    return (int(text[0:2], 16) / 255.0, int(text[2:4], 16) / 255.0, int(text[4:6], 16) / 255.0)


def _packed_colour(verts, tris, rgb):
    """Quantise per-face rgb to a packed int per vertex (majority vote)."""
    keys = np.round(rgb * 255.0).astype(np.int64)
    packed = keys[:, 0] * 65536 + keys[:, 1] * 256 + keys[:, 2]
    return packed


def connected_components(vert_count, tris):
    """Union-find over shared vertex indices."""
    parent = np.arange(vert_count, dtype=np.int64)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for t in tris:
        ra, rb, rc = find(t[0]), find(t[1]), find(t[2])
        if rb != ra:
            parent[rb] = ra
        if rc != ra:
            parent[rc] = ra
    roots = np.array([find(i) for i in range(vert_count)], dtype=np.int64)
    return roots


def split_faces_by_vertex_root(roots, tris):
    """Group face indices by the connected component their first vertex belongs to."""
    face_root = roots[tris[:, 0]]
    order = np.argsort(face_root, kind="stable")
    sorted_roots = face_root[order]
    uniq, starts = np.unique(sorted_roots, return_index=True)
    groups = []
    for i, root in enumerate(uniq):
        lo = starts[i]
        hi = starts[i + 1] if i + 1 < len(starts) else len(sorted_roots)
        groups.append((int(root), order[lo:hi]))
    return groups


def submesh_from_faces(verts, tris, face_idx):
    sub = tris[face_idx]
    used, inverse = np.unique(sub.reshape(-1), return_inverse=True)
    return verts[used], inverse.reshape(-1, 3).astype(np.int64)


def remap_tris(verts, tris):
    """Re-index a triangle soup so every vertex is used at least once."""
    if len(tris) == 0:
        return verts, tris
    used, inverse = np.unique(tris.reshape(-1), return_inverse=True)
    return verts[used], inverse.reshape(-1, 3).astype(np.int64)


def compact(verts, tris):
    """Drop unused vertices and degenerate faces."""
    if len(tris) == 0:
        return verts, tris
    keep = (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])
    tris = tris[keep]
    if len(tris) == 0:
        return verts, tris
    used, inverse = np.unique(tris.reshape(-1), return_inverse=True)
    return verts[used], inverse.reshape(-1, 3).astype(np.int64)


def simplify(verts, tris, target_faces):
    """Decimate with fast_simplification; it marks collapsed faces with -1."""
    if len(tris) <= target_faces:
        return verts, tris
    if fast_simplification is None:
        # Refusing to decimate is a size regression, not a correctness one, so this
        # stays a warning rather than an exception: the build still produces a usable
        # model. It must not be silent, though — that is what made the missing
        # dependency invisible for so long.
        print(f"WARNING: not decimating {len(tris)} -> {target_faces} faces: "
              "fast_simplification is not installed", file=sys.stderr)
        return verts, tris
    ratio = float(target_faces) / float(len(tris))
    ratio = max(0.002, min(1.0, ratio))
    v, f = fast_simplification.simplify(
        np.ascontiguousarray(verts, dtype=np.float32),
        np.ascontiguousarray(tris, dtype=np.int32),
        target_reduction=1.0 - ratio)
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    if f.ndim != 2 or len(f) == 0:
        return verts, tris
    f = f[(f >= 0).all(axis=1)]
    if len(f) == 0:
        return verts, tris
    used, inverse = np.unique(f, return_inverse=True)
    return v[used], inverse.reshape(-1, 3).astype(np.int64)


def triangle_area_sum(verts, tris):
    a = verts[tris[:, 0]]
    b = verts[tris[:, 1]]
    c = verts[tris[:, 2]]
    return float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() * 0.5)


def weld(verts, tris, eps=1e-5):
    """Merge coincident vertices."""
    key = np.round(verts / eps).astype(np.int64)
    _, index, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    new_verts = verts[index]
    new_tris = inverse[tris]
    keep = (new_tris[:, 0] != new_tris[:, 1]) & (new_tris[:, 1] != new_tris[:, 2]) & (new_tris[:, 0] != new_tris[:, 2])
    return new_verts, new_tris[keep]


# ------------------------------------------------------------------- normals
def build_normals_with_sharp_edges(verts, tris, angle_deg=62.0):
    """Split vertices across sharp edges and return smooth-shaded normals.

    Returns (verts, tris, normals); vertices may have been duplicated.
    """
    if len(tris) == 0:
        return verts, tris, np.zeros_like(verts)

    a = verts[tris[:, 0]]
    b = verts[tris[:, 1]]
    c = verts[tris[:, 2]]
    face_n = np.cross(b - a, c - a)
    length = np.linalg.norm(face_n, axis=1, keepdims=True)
    length[length < 1e-15] = 1.0
    face_n = face_n / length

    threshold = float(np.cos(np.radians(angle_deg)))
    face_count = len(tris)

    # corner index -> (face, vertex)
    corner_face = np.repeat(np.arange(face_count, dtype=np.int64), 3)
    corner_vert = tris.reshape(-1).astype(np.int64)
    order = np.argsort(corner_vert, kind="stable")
    sorted_vert = corner_vert[order]
    uniq_verts, starts = np.unique(sorted_vert, return_index=True)
    ends = np.append(starts[1:], len(sorted_vert))

    out_positions = []
    out_normals = []
    out_tris = np.empty_like(tris)
    next_index = 0

    for vi, lo, hi in zip(uniq_verts.tolist(), starts.tolist(), ends.tolist()):
        corners = order[lo:hi]
        faces = corner_face[corners]
        n_faces = len(faces)

        if n_faces == 1:
            norm = np.linalg.norm(face_n[faces[0]])
            out_positions.append(verts[vi])
            out_normals.append(face_n[faces[0]] if norm > 1e-12 else np.array([0.0, 1.0, 0.0]))
            out_tris[faces[0], np.where(tris[faces[0]] == vi)[0]] = next_index
            next_index += 1
            continue

        # union-find over the faces touching this vertex
        parent = np.arange(n_faces, dtype=np.int64)

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        # faces sharing the same neighbour vertex lie in one smooth patch
        neighbour = {}
        for slot, fi in enumerate(faces.tolist()):
            row = tris[fi]
            for v in row.tolist():
                if v == vi:
                    continue
                neighbour.setdefault(v, []).append(slot)
        for slots in neighbour.values():
            base = slots[0]
            for other in slots[1:]:
                if float(np.dot(face_n[faces[base]], face_n[faces[other]])) >= threshold:
                    ra, rb = find(base), find(other)
                    if ra != rb:
                        parent[rb] = ra

        buckets = {}
        for slot, fi in enumerate(faces.tolist()):
            buckets.setdefault(find(slot), []).append(fi)

        for cluster in buckets.values():
            acc = np.zeros(3)
            for fi in cluster:
                acc += face_n[fi]
            norm = float(np.linalg.norm(acc))
            normal = acc / norm if norm > 1e-12 else face_n[cluster[0]]
            local = np.where(np.isin(faces, cluster))[0]
            out_positions.append(verts[vi])
            out_normals.append(normal)
            for slot in local.tolist():
                fi = int(faces[slot])
                out_tris[fi, np.where(tris[fi] == vi)[0]] = next_index
            next_index += 1

    return (np.asarray(out_positions, dtype=np.float64),
            out_tris,
            np.asarray(out_normals, dtype=np.float64))


# -------------------------------------------------------------------- writer
# Submesh flag bits shared with the C# reader.
FLAG_OUTLINE = 1  # inverted hull: draw with front faces culled


def write_psmesh(path, name, submeshes, bounds, grips=None, wobble=None,
                 outline_map=None, baked_outline_thickness=0.0):
    """submeshes: list of (rgba, verts Nx3, normals Nx3, uvs Nx2, tris Mx3, flags)

    `grips` is an optional dict with the item-local positions and rotations of the two
    hand hold points. The game places the player's hands at the "Hand_L" / "Hand_R"
    children of the item, position AND rotation, so publishing both here is what lets
    the plush be held properly instead of the hands floating in the air beside it.

    `wobble` is an optional per-vertex weight (0 = rigid, 1 = fully loose) that drives
    the soft-body wobble on the floppy parts.

    `outline_map` is an optional per-vertex weight for the ink shell, listing the source
    vertex of every outline vertex (index into the concatenated solid vertices) plus the
    weight that vertex wobbles by. It is what keeps the ink glued to the floppy parts
    while they move.

    `baked_outline_thickness` records how far the ink shell was pushed out along its
    normals when it was built. The runtime subtracts exactly that much and re-extrudes in
    screen space, which is what turns the line into a constant pixel width instead of a
    constant world length that balloons up close and vanishes far away.
    """
    with open(path, "wb") as fh:
        fh.write(MAGIC)
        raw = name.encode("utf-8")
        fh.write(struct.pack("<i", len(raw)))
        fh.write(raw)
        fh.write(struct.pack("<i", len(submeshes)))
        for colour, verts, normals, uvs, tris, flags in submeshes:
            fh.write(struct.pack("<4f", *colour))
            fh.write(struct.pack("<i", int(flags)))
            fh.write(struct.pack("<ii", len(verts), len(tris) * 3))
            fh.write(verts.astype("<f4").tobytes())
            fh.write(normals.astype("<f4").tobytes())
            fh.write(uvs.astype("<f4").tobytes())
            fh.write(np.tile(np.asarray(colour[:3], dtype="<f4"), (len(verts), 1)).tobytes())
            fh.write(tris.astype("<i4").tobytes())
        fh.write(struct.pack("<3f", *bounds[0]))
        fh.write(struct.pack("<3f", *bounds[1]))

        if grips:
            fh.write(struct.pack("<i", 1))
            fh.write(struct.pack("<3f", *grips["left"]))
            fh.write(struct.pack("<3f", *grips["right"]))
            fh.write(struct.pack("<4f", *grips["left_rot"]))
            fh.write(struct.pack("<4f", *grips["right_rot"]))
        else:
            fh.write(struct.pack("<i", 0))

        # The count is ALWAYS written, even when there is no data. The reader reads it
        # unconditionally, so omitting it (as an earlier version did) shifts every later
        # field by four bytes and the baked-thickness float comes back as garbage.
        if wobble is not None and len(wobble) > 0:
            weights = np.clip(np.asarray(wobble, dtype=np.float64), 0.0, 1.0)
            fh.write(struct.pack("<i", len(weights)))
            # quantised to bytes: the weight is a soft falloff, 1/255 is plenty
            fh.write(np.round(weights * 255.0).astype(np.uint8).tobytes())
        else:
            fh.write(struct.pack("<i", 0))

        if outline_map is not None and len(outline_map[0]) > 0:
            source, weights = outline_map
            fh.write(struct.pack("<i", len(source)))
            fh.write(np.asarray(source, dtype="<i4").tobytes())
            # Per-shell-vertex outline width in [0, 1], quantised to a byte. The shell
            # geometry is baked as `surface + normal * thickness * width`, so the runtime
            # undoes exactly that and re-extrudes in screen space scaled by the same
            # width. Zero means "no ink here": the shell sits on the body and, since it
            # is drawn with front faces culled, the body hides it — which is how the
            # eyes, mouth and blush stay un-inked without cutting any faces. Cutting
            # faces is what tore the line into disconnected strokes.
            weights = np.clip(np.asarray(weights, dtype=np.float64), 0.0, 1.0)
            fh.write(np.round(weights * 255.0).astype(np.uint8).tobytes())
        else:
            fh.write(struct.pack("<i", 0))

        # Baked ink-shell extrusion, so the runtime can undo it exactly and re-extrude
        # in screen space. Zero means "no outline" (or an older file).
        fh.write(struct.pack("<f", float(baked_outline_thickness)))


def write_shading_png(path, image):
    """Write the 1-pixel-tall shading palette as an uncompressed-safe PNG."""
    from PIL import Image
    rgba = np.clip(np.round(image * 255.0), 0, 255).astype(np.uint8)
    Image.fromarray(rgba, mode="RGBA").save(path)
    return rgba.shape[1]


def _replace_pair(mesh_tmp, mesh_path, png_tmp, png_path, image):
    """Publish a staged (.psmesh, palette PNG) pair with two renames.

    The two files must always describe the same build; a fresh PNG beside a stale mesh
    samples the wrong texels. Both are written to temp names first, so the only failure
    mode left is a crash between the two renames, which cannot corrupt either file.
    """
    write_shading_png(png_tmp, image)
    os.replace(mesh_tmp, mesh_path)
    os.replace(png_tmp, png_path)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def generator_hashes():
    """sha256 of every script whose source decides what the built assets look like.

    These are what let verify_assets.py catch the second half of the stale-asset trap.
    Hashing the 3MF catches "the model was edited but the pipeline was not rerun";
    hashing the generator catches "the pipeline's own parameters were edited but the
    pipeline was not rerun", which the file hashes alone can never see — the old
    assets still match the old 3MF, so every file check passes while the assets on
    disk were produced by code that no longer exists.

    threemf.py is included because it decides the vertex data itself (colour decoding,
    transforms, extruder resolution): editing it changes the .psmesh without touching
    build_meshes.py.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return {name: _sha256(os.path.join(here, name))
            for name in ("build_meshes.py", "threemf.py")}


def canonical_params(params):
    """Stable JSON text for a params dict, so it can be compared as a plain string.

    sort_keys + fixed separators make the text depend only on the values, not on dict
    insertion order or json's default whitespace, so a comparison cannot fail for a
    reason that has nothing to do with the build.
    """
    return json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def write_manifest(manifest_path, entries, generator=None):
    """Record source->output hashes so a stale asset cannot be silently shipped.

    `entries` maps a .psmesh name to the source .3mf plus the parameters that produced
    it. verify_assets.py checks the source hash before a plain build and refuses to
    continue when a 3MF changed without -RebuildAssets.

    The assets dict is REBUILT from `entries`, never merged into the previous manifest.
    Merging used to keep the entries of jobs that no longer run, and verify_assets.py
    then reported those deleted files as MISSING — turning "this job was removed" into
    a misleading "the assets are corrupt" failure that -RebuildAssets could not clear.

    The top-level `generator` block carries the hashes and the canonical parameters, so
    verify_assets.py can gate on the code that produced the assets as well as on the
    files themselves. Older manifests have no such block; verify_assets.py treats that
    as "regenerate", which is the correct fix for a manifest written before this check.
    """
    payload = {
        "version": 2,
        "generator": generator if generator is not None else generator_hashes(),
        "assets": dict(entries),
    }
    tmp = manifest_path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, manifest_path)
    print(f"wrote {manifest_path} ({len(payload['assets'])} entries)")


# -------------------------------------------------------------------- convert
# Reference geometry measured from the real item prefab (BingBong_Prop Variant ->
# Holder -> Bing Bong Plush), expressed in item-root space:
#
#   combined bounds   size (0.9720, 0.9635, 0.3599)
#   combined centre   X = -0.0315, Z = +0.0505
#   Y range           [-0.7345, +0.2290]
#   face              +Z when held (the item's +Z is the player's look direction)
#   hand grip         Hand_L / Hand_R sit at y = -0.177 / -0.104
#
# A held item is aimed with LookRotation(lookDirection, lookDirection_Up), so the
# item's +Z points away from the player. The plush therefore has to face -Z for the
# player to see its front.
VANILLA_HEIGHT = 0.9635
VANILLA_CENTRE_X = -0.0315
VANILLA_CENTRE_Z = 0.0505
VANILLA_BOTTOM_Y = -0.7345
VANILLA_TOP_Y = 0.2290


def rot_y(points, degrees):
    """Rotate points about the Y axis (Unity's up) by the given angle."""
    theta = np.radians(degrees)
    c, s = np.cos(theta), np.sin(theta)
    out = points.copy()
    out[:, 0] = points[:, 0] * c + points[:, 2] * s
    out[:, 2] = -points[:, 0] * s + points[:, 2] * c
    return out


def detect_facing_yaw(submeshes):
    """Return the yaw (deg) that turns the model's face toward -Z.

    The face is found from the colour regions that are both *small* and located in the
    upper half of the model. That combination isolates the eyes / mouth / blush decals
    on the head and excludes the two things that would otherwise fool it: limbs (small
    but mid-height) and the print base (small but at the bottom). The facing is then
    the direction from the model's centre to those decals.
    """
    areas = [triangle_area_sum(sv, st) for _, sv, st in submeshes]
    largest = max(areas) if areas else 0.0
    if largest <= 0.0:
        return 180.0

    all_v = np.concatenate([sv for _, sv, _ in submeshes], axis=0)
    lo = all_v.min(axis=0)
    hi = all_v.max(axis=0)
    centre = (lo + hi) * 0.5
    mid_height = (lo[1] + hi[1]) * 0.5

    acc = np.zeros(3)
    weight = 0.0
    for (col, sv, st), area in zip(submeshes, areas):
        if area > largest * 0.25:
            continue  # bodies and other big shells are not face decals
        centroid = sv.mean(axis=0)
        if centroid[1] < mid_height:
            continue  # limbs and the print base live below the head
        acc += centroid * area
        weight += area

    if weight <= 0.0:
        return 180.0  # cannot tell; default to facing the player

    decal_centre = acc / weight
    direction = np.array([decal_centre[0] - centre[0], 0.0, decal_centre[2] - centre[2]])
    if float(np.linalg.norm(direction)) < 1e-6:
        return 180.0

    current = np.degrees(np.arctan2(direction[0], direction[2]))  # 0 deg == +Z
    return 180.0 - current  # -Z is 180 deg


def normals_for_ao(verts, tris):
    """Area-weighted smooth vertex normals, used by the occlusion bake."""
    a = verts[tris[:, 0]]
    b = verts[tris[:, 1]]
    c = verts[tris[:, 2]]
    face = np.cross(b - a, c - a)
    normals = np.zeros_like(verts)
    for k in range(3):
        np.add.at(normals, tris[:, k], face)
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    length[length < 1e-15] = 1.0
    return normals / length


def downward_face_weight(submeshes, threshold=0.55):
    """Mark the vertices whose surrounding surface points steeply downward.

    Such a surface can never be seen from a normal viewing angle, and it is exactly the
    one whose extruded ink shell fringes out from underneath as a sawtooth. Miffy's
    skirt is a closed volume, so its underside is a flat disc sitting right at the hem;
    that disc is what was drawing the ragged fringe across her legs.

    A vertex counts as downward when the area-weighted normal of its adjacent faces
    points down by more than `threshold`. Requiring the *average* rather than any single
    face keeps the hem rim — whose vertices are shared with the vertical skirt wall —
    fully inked, and only kills the interior of the disc.
    """
    total = sum(len(s[1]) for s in submeshes)
    mask = np.zeros(total, dtype=bool)
    if total == 0:
        return mask

    offset = 0
    for s in submeshes:
        verts = s[1]
        tris = _tris_of(s)
        sl = slice(offset, offset + len(verts))
        offset += len(verts)
        if len(tris) == 0:
            continue

        a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
        face = np.cross(b - a, c - a)
        area = np.linalg.norm(face, axis=1)
        keep = area > 1e-15
        if not keep.any():
            continue

        normal_y = np.zeros(len(area), dtype=np.float64)
        normal_y[keep] = face[keep, 1] / area[keep]

        acc = np.zeros(len(verts), dtype=np.float64)
        weight = np.zeros(len(verts), dtype=np.float64)
        for k in range(3):
            np.add.at(acc, tris[:, k], normal_y * area)
            np.add.at(weight, tris[:, k], area)

        weight[weight < 1e-15] = 1.0
        mask[sl] = (acc / weight) < -threshold

    return mask


def build_outline_normals(verts, tris, eps=1e-5):
    """The averaged ("smooth") normals the ink shell must be pushed along.

    This is the fix for the broken, uneven outline. Extruding along the *shading*
    normals fails wherever the mesh has hard edges: those vertices are duplicated, so
    each copy is pushed along a different direction and the shell tears open at every
    edge — the pen-runs-dry look. It is the single best documented failure mode of the
    inverted-hull technique, and every reference implementation (Unity Toon Shader's
    baked normal map, DELTation's outline normals utility, JasonMa0012's
    OutlineNormalSmoother, the AquaSmoothNormals repository) solves it the same way:
    weld the vertices by position, average the face normals of everything that lands on
    one position, and extrude along that shared normal instead.

    The shell therefore closes over sharp edges and the ink line keeps an even width
    all the way around the silhouette.

    Returns (verts, tris, normals, origin). `origin[i]` is the index of the input vertex
    the welded vertex i came from, which lets the caller carry the per-vertex wobble
    weight and the face mask across to the shell.
    """
    if len(tris) == 0:
        return verts, tris, np.zeros_like(verts), np.arange(len(verts), dtype=np.int64)

    face = np.cross(verts[tris[:, 1]] - verts[tris[:, 0]],
                    verts[tris[:, 2]] - verts[tris[:, 0]])
    key = np.round(verts / eps).astype(np.int64)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)

    merged = np.zeros((len(first), 3), dtype=np.float64)
    for k in range(3):
        np.add.at(merged, inverse[tris[:, k]], face)

    length = np.linalg.norm(merged, axis=1, keepdims=True)

    # A welded position can have a near-zero summed normal where opposing faces
    # cancel out (overlapping decals) or where the faces around it are degenerate.
    # Dividing that by 1 leaves a zero-length normal, and a shell vertex with no
    # direction is never pushed out — it pinches the ink into a hole. Those
    # positions fall back to a real face normal taken from one of their triangles,
    # which always points somewhere usable.
    degenerate = length[:, 0] < 1e-12
    if degenerate.any():
        # area-weighted fallback: accumulate each face normal onto all three of its
        # welded corners, but only read it back for the degenerate ones
        fallback = np.zeros_like(merged)
        face_len = np.linalg.norm(face, axis=1, keepdims=True)
        face_len[face_len < 1e-15] = 1.0
        unit_face = face / face_len
        for k in range(3):
            np.add.at(fallback, inverse[tris[:, k]], unit_face)
        fb_len = np.linalg.norm(fallback, axis=1, keepdims=True)
        usable = (fb_len[:, 0] > 1e-12) & degenerate
        merged[usable] = fallback[usable] / fb_len[usable]
        # anything still without a direction gets an arbitrary unit vector, so the
        # runtime can never divide by (or extrude along) a zero vector
        still = degenerate & ~usable
        if still.any():
            merged[still] = np.array([0.0, 1.0, 0.0])
        length = np.linalg.norm(merged, axis=1, keepdims=True)

    length[length < 1e-15] = 1.0
    merged /= length

    welded_tris = inverse[tris].reshape(-1, 3)
    keep = ((welded_tris[:, 0] != welded_tris[:, 1])
            & (welded_tris[:, 1] != welded_tris[:, 2])
            & (welded_tris[:, 0] != welded_tris[:, 2]))

    return (verts[first],
            welded_tris[keep],
            merged,
            first.astype(np.int64))


def build_cartoon_outline(verts, tris, normals, thickness, colour=(0.10, 0.10, 0.12, 1.0),
                          width=None):
    """Classic inverted-hull outline.

    The mesh is pushed outward along its (averaged) normals and drawn with front faces
    culled, so only the shell that pokes out around the silhouette is visible. That is
    what gives the plush a hand-drawn ink line and makes it read as a cartoon instead of
    a photographed 3D print.

    `width` is an optional per-vertex weight in [0, 1] that scales the push. A vertex
    with weight 0 is not pushed at all, so the shell sinks inside the body there and
    nothing is drawn — the standard "outline width map" control from Unity Toon Shader.
    Shrinking the push is used instead of deleting the faces around the eyes and blush,
    because deleting faces is exactly what breaks a hull into disconnected strokes.
    """
    scale = np.ones((len(verts), 1), dtype=np.float64)
    if width is not None:
        # negative is allowed: it pulls the shell inward, which is how a feature is
        # tucked inside the body instead of being outlined
        scale = np.asarray(width, dtype=np.float64)[:, None]

    offset = verts + normals * (thickness * scale)
    shell = (np.asarray(colour, dtype=np.float64),
             offset,
             normals,
             np.zeros((len(offset), 2), dtype=np.float64),
             tris,
             FLAG_OUTLINE)
    return shell


def smooth_scalar_over_surface(vert_count, tris, values, iterations=2, blend=0.5):
    """Laplacian smoothing of any per-vertex scalar field.

    Used on the cavity field before it is turned into ink. The raw field is noisy
    because it is sampled per vertex, which is what made some lines look like a pen
    running out of ink: patchy, uneven thickness, and broken in places.
    """
    if vert_count == 0 or iterations <= 0:
        return values

    edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]], axis=0)
    edges = np.concatenate([edges, edges[:, ::-1]], axis=0)

    result = values.astype(np.float64).copy()
    for _ in range(iterations):
        sums = np.zeros(vert_count, dtype=np.float64)
        counts = np.zeros(vert_count, dtype=np.float64)
        np.add.at(sums, edges[:, 0], result[edges[:, 1]])
        np.add.at(counts, edges[:, 0], 1.0)
        counts[counts < 1e-9] = 1.0
        result = result * (1.0 - blend) + (sums / counts) * blend
    return result


def smooth_ao_over_surface(verts, tris, ao, iterations=3, blend=0.6):
    """Laplacian smoothing of the occlusion values across the mesh surface.

    The raw bake is per-vertex, so on a coarse mesh it can band into visible blocks
    (the "mosaic" look in tight crevices). Averaging each vertex with its edge
    neighbours turns those blocks into the soft gradients a cartoon wants.
    """
    if len(ao) == 0 or iterations <= 0:
        return ao

    edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]], axis=0)
    edges = np.concatenate([edges, edges[:, ::-1]], axis=0)

    result = ao.astype(np.float64).copy()
    for _ in range(iterations):
        sums = np.zeros(len(result), dtype=np.float64)
        counts = np.zeros(len(result), dtype=np.float64)
        np.add.at(sums, edges[:, 0], result[edges[:, 1]])
        np.add.at(counts, edges[:, 0], 1.0)
        counts[counts < 1e-9] = 1.0
        average = sums / counts
        result = result * (1.0 - blend) + average * blend
    return result


def smoothstep(edge0, edge1, x):
    """Hermite ramp; returns 0 at edge0 and 1 at edge1."""
    if edge1 - edge0 < 1e-12:
        return np.where(x < edge0, 0.0, 1.0)
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def analyse_components(submeshes):
    """Split the model into connected shells and measure inter-shell proximity.

    Returns (component id per input vertex, distance from each vertex to the nearest
    vertex belonging to a different shell).

    The distance field is the key to cartoon interior lines: along the curve where a
    limb enters the body the distance drops to zero, so a thin band of it becomes a
    clean, even crease line — which an inverted hull alone can never draw, because
    there the shell is buried inside the body.

    Two details matter for correctness:

    * Vertices are welded by position first. The smooth-normal pass duplicates vertices
      along sharp edges, which would otherwise chop every shell into fragments and
      misclassify most of the body as "flat decal".
    * Each shell is queried against a tree built from every OTHER shell. A single
      global tree would not work: on a dense decal the nearest neighbours are all from
      the decal itself, so the cross-shell distance would never be found.
    """
    from scipy.spatial import cKDTree

    all_verts = []
    all_tris = []
    offset = 0
    for _, mv, _, mt in submeshes:
        all_verts.append(mv)
        all_tris.append(mt + offset)
        offset += len(mv)

    verts = np.concatenate(all_verts, axis=0)
    tris = np.concatenate(all_tris, axis=0)

    # Weld coincident vertices so sharp-edge splits do not break connectivity.
    key = np.round(verts / 1e-5).astype(np.int64)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    welded_verts = verts[first]
    welded_tris = inverse[tris].reshape(-1, 3)

    roots = connected_components(len(welded_verts), welded_tris)
    _, welded_component = np.unique(roots, return_inverse=True)

    welded_distance = np.full(len(welded_verts), np.inf, dtype=np.float64)
    welded_nearest = np.full(len(welded_verts), -1, dtype=np.int64)
    for cid in np.unique(welded_component):
        mine = welded_component == cid
        others = ~mine
        if not others.any():
            continue
        other_components = welded_component[others]
        tree = cKDTree(welded_verts[others])
        found, index = tree.query(welded_verts[mine], k=1, workers=-1)
        welded_distance[mine] = found
        welded_nearest[mine] = other_components[index]

    welded_distance[~np.isfinite(welded_distance)] = 1e9
    return (welded_component[inverse],
            welded_distance[inverse],
            welded_nearest[inverse])


def find_face_features(submeshes, margin):
    """Return (decal, grown): the face features themselves, and a padded ring around them.

    `decal` is exactly the shells that are eyes / mouth / blush, used to keep the ink off
    them. `grown` additionally covers the head surface next to them, which the cavity
    field would otherwise shade with a grey halo.

    Colour is the only reliable signal here. These models are not built from separate
    parts: the bear's eyes and blush are welded into the same mesh as its body, so
    shell-based detection sees one single surface and cannot tell them apart.

    The rule is the same one used for facing detection: a colour region that is small,
    sits in the upper half of the model, and is geometrically thin (a decal hugging
    the head, not a limb) is a face feature. Those vertices must never receive ink —
    drawing a line along an eye or a blush reads as a grey halo around the feature
    instead of a drawn edge.
    """
    from scipy.spatial import cKDTree

    total = sum(len(s[1]) for s in submeshes)
    mask = np.zeros(total, dtype=bool)
    if total == 0:
        return mask, mask

    areas = [triangle_area_sum(s[1], s[3]) for s in submeshes]
    largest = max(areas) if areas else 0.0
    if largest <= 0.0:
        # Every shell is degenerate (all faces have zero area), so there is nothing that
        # can be a face feature. Returning the same shape as the normal path matters:
        # the caller unpacks the tuple, and an ndarray here crashed the whole build.
        return mask, mask

    all_verts = np.concatenate([s[1] for s in submeshes], axis=0)
    lo = all_verts.min(axis=0)
    hi = all_verts.max(axis=0)
    height = float(hi[1] - lo[1])
    # The features sit on the head, so they are in the upper part of the model — but
    # the threshold has to be low enough to catch a mouth that sits just under the
    # midline (Miffy's is at 49% of her height, and missing it left a grey halo).
    feature_height = lo[1] + height * 0.30

    offset = 0
    for (col, mv, nm, mt), area in zip(submeshes, areas):
        sl = slice(offset, offset + len(mv))
        offset += len(mv)
        if area > largest * 0.25:
            continue
        if float(mv.mean(axis=0)[1]) < feature_height:
            continue
        # a decal is geometrically thin; a limb or a dress panel is not
        depth = float(min(mv[:, 0].max() - mv[:, 0].min(),
                          mv[:, 2].max() - mv[:, 2].min()))
        if depth > height * 0.25:
            continue
        mask[sl] = True

    if not mask.any() or margin <= 0.0:
        return mask, mask

    # The features are raised discs, so the cavity field also fires on the ring of
    # head surface right around them and paints a grey blob beside an eye. Growing the
    # mask by a small radius clears that ring. A large radius must not be used: the
    # bear's features carry most of its vertices, and a wide mask would swallow the
    # whole face and kill the outline.
    tree = cKDTree(all_verts[mask])
    grown = mask.copy()
    for i, hits in enumerate(tree.query_ball_point(all_verts, margin, workers=-1)):
        if hits:
            grown[i] = True
    return mask, grown


def _tris_of(submesh):
    """The triangle list of a submesh, which sits at a different slot before and
    after the shading UVs are baked in (4-tuple vs 6-tuple)."""
    return submesh[3] if len(submesh) == 4 else submesh[4]


def inside_other_shell(submeshes, max_distance):
    """Mark the vertices that lie *inside* one of the other closed shells.

    NOT called by this module any more: `enclosed` is deliberately unused (see the note
    in convert()). It is kept because the one-off experiments under research/ still call
    it through `bm.inside_other_shell` — ab_precompute.py, diagnose_ink_gaps.py,
    dump_directions.py, iso_precompute.py, outline_variants2.py, shell_variants.py —
    and they are the record of why the mask was dropped.

    A surface enclosed by another shell can never be seen, yet the inverted hull still
    pushes it outward along its normal — and that is how Miffy's legs, standing inside
    her skirt, end up with their ink poking out through the skirt as a ragged fringe
    along the hem.

    Membership is decided by a ray cast: a point is inside when a ray from it crosses
    the shell an odd number of times. This is the standard point-in-polygon test lifted
    to 3D, and unlike a nearest-normal sign test it is not fooled by the thin raised
    decals these models are full of — a decal has no enclosed volume to be inside of.
    """
    total = sum(len(s[1]) for s in submeshes)
    inside = np.zeros(total, dtype=bool)
    if total == 0:
        return inside

    # a fixed, deliberately irrational direction so the ray almost never grazes an edge
    direction = np.array([0.3123, 0.8231, 0.4747])
    direction /= np.linalg.norm(direction)

    offset = 0
    spans = []
    for s in submeshes:
        spans.append(slice(offset, offset + len(s[1])))
        offset += len(s[1])

    for i, s in enumerate(submeshes):
        others = [submeshes[j] for j in range(len(submeshes)) if j != i]
        if not others:
            continue

        # only vertices near another shell can possibly be inside it
        other_verts = np.concatenate([o[1] for o in others], axis=0)
        from scipy.spatial import cKDTree
        near, _ = cKDTree(other_verts).query(s[1], k=1, workers=-1)
        candidates = np.flatnonzero(near < max_distance)
        if len(candidates) == 0:
            continue

        for other in others:
            verts, tris = other[1], _tris_of(other)
            if len(tris) == 0:
                continue
            v0, v1, v2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
            e1, e2 = v1 - v0, v2 - v0
            pvec = np.cross(direction[None, :], e2)
            det = np.einsum("j,tj->t", direction, np.cross(e1, e2))
            ok = np.abs(det) > 1e-12
            inv = np.zeros_like(det)
            inv[ok] = 1.0 / det[ok]

            for start in range(0, len(candidates), 256):
                chunk = candidates[start:start + 256]
                tvec = s[1][chunk][:, None, :] - v0[None, :, :]
                u = np.einsum("ctj,tj->ct", tvec, pvec) * inv[None, :]
                qvec = np.cross(tvec, e1[None, :, :])
                v = np.einsum("ctj,j->ct", qvec, direction) * inv[None, :]
                t = np.einsum("ctj,tj->ct", qvec, e2) * inv[None, :]
                hit = ((u >= -1e-9) & (u <= 1.0 + 1e-9)
                       & (v >= -1e-9) & (u + v <= 1.0 + 1e-9) & (t > 1e-9))
                odd = (hit.sum(axis=1) % 2) == 1
                if odd.any():
                    inside[chunk[odd]] = True

    return inside


def pushed_inside_body(submeshes, shell_verts, max_distance):
    """Mark the ink-shell vertices whose *pushed* position lies inside the body.

    NOT called by this module any more; kept for the research/ experiments that still
    use it through `bm.pushed_inside_body` (scan_blend.py). See inside_other_shell.

    This is the precise fix for ink leaking through the model. The shell is the body
    pushed outward along its normals, but on a concave surface the outward push can land
    *inside* a different part of the body: the bear's muzzle groove, the crease between
    an arm and the torso, the underside of a paw. The ink is then drawn on geometry the
    camera cannot see, and it shows up as a dark line across the body — the "the line
    does not follow the model" artefact.

    A nearest-surface test cannot see this (the point is close to the surface, just on
    the wrong side), so membership is decided by a ray cast: a point is inside when a
    ray from it crosses the surface an odd number of times. Only shell vertices near the
    body are tested, which keeps it fast.

    Returns a bool array aligned with `shell_verts`.
    """
    from scipy.spatial import cKDTree

    inside = np.zeros(len(shell_verts), dtype=bool)
    if len(shell_verts) == 0:
        return inside

    body_verts = np.concatenate([s[1] for s in submeshes], axis=0)
    body_tris = []
    offset = 0
    for s in submeshes:
        body_tris.append(_tris_of(s) + offset)
        offset += len(s[1])
    if not body_tris:
        return inside
    body_tris = np.concatenate(body_tris, axis=0)
    if len(body_tris) == 0:
        return inside

    # only the shell vertices close to the body can be inside it
    near, _ = cKDTree(body_verts).query(shell_verts, k=1, workers=-1)
    candidates = np.flatnonzero(near < max_distance)
    if len(candidates) == 0:
        return inside

    direction = np.array([0.3123, 0.8231, 0.4747])
    direction /= np.linalg.norm(direction)

    v0, v1, v2 = (body_verts[body_tris[:, 0]], body_verts[body_tris[:, 1]],
                  body_verts[body_tris[:, 2]])
    e1, e2 = v1 - v0, v2 - v0
    pvec = np.cross(direction[None, :], e2)
    det = np.einsum("j,tj->t", direction, np.cross(e1, e2))
    ok = np.abs(det) > 1e-12
    inv = np.zeros_like(det)
    inv[ok] = 1.0 / det[ok]

    for start in range(0, len(candidates), 256):
        chunk = candidates[start:start + 256]
        tvec = shell_verts[chunk][:, None, :] - v0[None, :, :]
        u = np.einsum("ctj,tj->ct", tvec, pvec) * inv[None, :]
        qvec = np.cross(tvec, e1[None, :, :])
        v = np.einsum("ctj,j->ct", qvec, direction) * inv[None, :]
        t = np.einsum("ctj,tj->ct", qvec, e2) * inv[None, :]
        hit = ((u >= -1e-9) & (u <= 1.0 + 1e-9)
               & (v >= -1e-9) & (u + v <= 1.0 + 1e-9) & (t > 1e-9))
        odd = (hit.sum(axis=1) % 2) == 1
        if odd.any():
            inside[chunk[odd]] = True

    return inside


def find_base_shells(submeshes, height_fraction):
    """Mark the shells that form the flat print base sitting on the ground.

    The bear is printed with a thin disc under its feet. That disc touches the body
    everywhere along its rim, so the cavity field draws a dark ring around it — the
    "wheel track" artefact. It is a support surface that is never really visible, so
    it is excluded from inking entirely.
    """
    total = sum(len(s[1]) for s in submeshes)
    mask = np.zeros(total, dtype=bool)
    if total == 0:
        return mask

    all_verts = np.concatenate([s[1] for s in submeshes], axis=0)
    lo = all_verts.min(axis=0)
    hi = all_verts.max(axis=0)
    height = float(hi[1] - lo[1])

    areas = [triangle_area_sum(s[1], s[3]) for s in submeshes]
    largest = max(areas) if areas else 0.0

    offset = 0
    for (col, mv, nm, mt), area in zip(submeshes, areas):
        sl = slice(offset, offset + len(mv))
        offset += len(mv)
        if largest <= 0.0 or area > largest * 0.25:
            continue
        # the base is the small shell hugging the very bottom of the model
        if float(mv[:, 1].max()) > lo[1] + height * height_fraction:
            continue
        mask[sl] = True

    return mask


def compute_cavity_field(verts, tris, radius):
    """Measure how concave the surface is at each vertex, in [0, 1].

    For every vertex the neighbours inside `radius` are averaged by how far they sit
    on the vertex's own normal side. A flat or convex surface scores ~0; a crevice
    scores high. This is the standard "cavity map" used when baking stylised shading.

    This is what draws the interior ink lines. Shell-based tricks cannot do it here,
    because the models are not built from separate parts — the bear's paws, feet and
    body are one welded mesh, and so are Miffy's head and dress. Sampling the surface
    directly works regardless of how the mesh is authored.

    The radius controls which creases are found: small values catch only the tight
    valleys where a limb meets the body, which is exactly the line a cartoon needs.
    """
    from scipy.spatial import cKDTree

    if len(verts) == 0:
        return np.zeros(0)

    normals = normals_for_ao(verts, tris)
    tree = cKDTree(verts)
    cavity = np.zeros(len(verts), dtype=np.float64)

    for i, idx in enumerate(tree.query_ball_point(verts, radius, workers=-1)):
        if len(idx) < 4:
            continue
        delta = verts[idx] - verts[i]
        dist = np.linalg.norm(delta, axis=1)
        keep = (dist > 1e-6) & (dist <= radius)
        if keep.sum() < 3:
            continue
        dist = dist[keep]
        directions = delta[keep] / dist[:, None]
        falloff = (1.0 - dist / radius) ** 2
        facing = directions @ normals[i]
        weight = falloff.sum()
        if weight <= 1e-9:
            continue
        cavity[i] = float(np.sum(np.maximum(facing, 0.0) * falloff) / weight)

    return cavity


def bake_cartoon_shading(verts, tris, distance, nearest, suppress, component,
                         line_width, line_strength,
                         ao_radius, ao_strength, ao_floor,
                         cavity=None, cavity_line_strength=0.0):
    """Build the per-vertex shading: drawn ink lines plus a whisper of contact AO.

    Cartoon shading wants flat, bright surfaces with a drawn line where parts meet.
    A broad smooth occlusion gradient — what this used to do — just greys the whole
    toy out, which is exactly what made it look dull.

    `suppress` marks the vertices that must never receive ink: the eyes, mouth and
    blush decals, and the surface right around them. Drawing a line there produced
    the grey halos that were ringing the features.
    """
    from scipy.spatial import cKDTree

    # 1. the crease line from the inter-shell distance field: this catches the contact
    #    between genuinely separate shells (Miffy's hands against her dress).
    line = 1.0 - smoothstep(line_width * 0.30, line_width, distance)

    # 2. the interior line from the cavity field: this is what draws the crease where
    #    a limb meets the body when both belong to the same mesh.
    if cavity is not None and cavity_line_strength > 0.0:
        interior = smoothstep(0.22, 0.75, cavity)
        line = np.maximum(line, interior * cavity_line_strength)

    if suppress is not None:
        line[suppress] = 0.0

    # 3. a very light contact shading so the form does not read as paper flat
    ao = np.zeros(len(verts), dtype=np.float64)
    if ao_strength > 0.0 and ao_radius > 0.0:
        normals = normals_for_ao(verts, tris)
        tree = cKDTree(verts)
        for i, idx in enumerate(tree.query_ball_point(verts, ao_radius, workers=-1)):
            if len(idx) < 3:
                continue
            delta = verts[idx] - verts[i]
            dist = np.linalg.norm(delta, axis=1)
            keep = dist > 1e-6
            if not keep.any():
                continue
            dist = dist[keep]
            directions = delta[keep] / dist[:, None]
            facing = directions @ normals[i]
            falloff = (1.0 - dist / ao_radius) ** 2
            ao[i] = np.sum(np.maximum(facing, 0.0) * falloff)

        reference = float(np.percentile(ao, 99.0))
        if reference > 1e-9:
            ao = np.clip(ao / reference, 0.0, 1.0) ** 0.7
            ao = smooth_ao_over_surface(verts, tris, ao, 3, 0.5)
        else:
            ao = np.zeros(len(verts), dtype=np.float64)

    shade = (1.0 - ao_strength * ao) * (1.0 - line_strength * line)
    floor = min(ao_floor, 1.0 - line_strength)
    return np.clip(shade, floor, 1.0), line


# The occlusion is baked into one tiny palette texture: the colour index picks the
# block, the shading level picks the texel. Vertices are given UVs into their block,
# so the whole model can be a single material and still carry both colour and shading.
AO_LEVELS = 96


# Cartoon plush look: the light parts are pushed toward a warm "cream white" so the
# toy reads as a clean stylised object instead of a photographed grey-beige print.
CREAM_WHITE = np.array([1.0, 0.984, 0.951])


def apply_white_boost(colour, amount):
    """Push bright colours hard toward cream white; leave mid and dark colours alone.

    The threshold used to be 0.75, which left the off-white print filament (which sits
    around 0.85-0.95) only partly corrected, so the toy still read as dull beige. The
    threshold is lower now and the blend is stronger, so the body becomes a clean cream
    while the dark eyes / mouth / blush and the mid-tone dress keep their own colour.
    """
    if amount <= 0.0:
        return np.asarray(colour, dtype=np.float64)

    rgb = np.asarray(colour[:3], dtype=np.float64)
    luminance = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    if luminance <= 0.55:
        return rgb

    weight = min(1.0, amount * (luminance - 0.55) / 0.45)
    return rgb * (1.0 - weight) + CREAM_WHITE * weight


def build_shading_texture(submeshes, ao_maps, ao_floor):
    """Return (rgba float image array, per-submesh texel ranges).

    Texel k of a colour's block holds that colour multiplied by the matching shading
    level. The ramp spans exactly the AO range the bake produces (floor .. 1), so a
    vertex's UV is a plain linear remap of its AO value — the shading is applied once,
    not twice.
    """
    blocks = []
    ranges = []
    cursor = 0
    for (colour, _, _, _), ao in zip(submeshes, ao_maps):
        rgb = np.asarray(colour[:3], dtype=np.float64)
        block = np.zeros((AO_LEVELS + 2, 4), dtype=np.float64)
        for k in range(AO_LEVELS):
            shade = ao_floor + (1.0 - ao_floor) * (k / float(AO_LEVELS - 1))
            block[k + 1, :3] = np.clip(rgb * shade, 0.0, 1.0)
        block[0] = block[1]                       # padding copies the ramp ends so that
        block[AO_LEVELS + 1] = block[AO_LEVELS]   # bilinear filtering never bleeds
        block[:, 3] = 1.0
        blocks.append(block)
        ranges.append((cursor + 1, cursor + AO_LEVELS))
        cursor += AO_LEVELS + 2

    texels = np.concatenate(blocks, axis=0)
    image = np.zeros((1, len(texels), 4), dtype=np.float64)
    image[0] = texels
    return image, ranges


# The vanilla plush's own grip anchors, read straight out of the shipped prefab
# (resources.assets, "BingBong_Prop Variant"). CharacterItems copies BOTH the
# position and the rotation of these nodes onto the player's hand rigs:
#
#     GetBodypartRig(Hand_R).transform.position = GetItemPosRightWorld(item);  // Find("Hand_R").position
#     GetBodypartRig(Hand_R).transform.rotation = GetItemRotRightWorld(item);  // Find("Hand_R").rotation
#
# so the rotation is not decoration: it is the hand pose. Authoring it as identity
# (an earlier attempt) rolled both hands a long way off.
VANILLA_GRIP_ROT_L = (-0.31818, 0.67636, 0.51899, -0.41466)
VANILLA_GRIP_ROT_R = (0.25786, 0.71867, 0.55145, 0.33605)

# The vanilla prefab's own anchor POSITIONS, also read from "BingBong_Prop Variant".
# They are published unchanged so the game's hold spring, hand IK and FixedJoints all
# keep working exactly as they do for the vanilla plush; the model is shifted to meet
# them instead. See the note in compute_grip_points.
VANILLA_GRIP_L = (-0.3590, -0.1770, -0.0400)
VANILLA_GRIP_R = (0.2400, -0.1040, -0.0400)

# NOTE: the player's hand is a *skinned* mesh driven by the hand bone, so it renders
# right at the bone — the anchor position IS where the hand appears. An earlier attempt
# offset it by the item prefab's dummy "Hand" child (0.154 down, 0.147 forward), which
# belongs to a completely different object; that is what pushed the grips up and made
# the plush look like it was being held by the head. No compensation is applied.


def compute_grip_points(submeshes, bounds, grip_fraction, inset):
    """Find the hand anchors that put the player's HANDS on the plush's waist.

    `CharacterItems.AttachItem` copies an item anchor's position and rotation onto the
    player's hand rig, and the hand mesh hangs off that rig by a fixed local transform.
    So the visible hand is at

        hand = anchor + anchor_rotation * HAND_OFFSET

    and the anchor that lands the hand on a chosen point p is therefore

        anchor = p - anchor_rotation * HAND_OFFSET

    Solving for the anchor this way is what makes "hold it by the waist" actually put the
    hands on the waist. The rotation is still the vanilla one, so the palm keeps the
    natural grip pose.

    Returns a dict with 'left'/'right' anchor positions and rotations.
    """
    lo, hi = bounds
    height = float(hi[1] - lo[1])
    y = lo[1] + height * grip_fraction

    # The two outermost vertices of a thin slab at grip height. Their FULL positions are
    # used, not just their X.
    #
    # Taking the slab's X extremes but then placing the hand at the slab's centre height
    # and depth puts it somewhere no vertex actually is. On the bear the outermost vertex
    # sits 0.095 higher and 0.08 further forward than that centre, so the hand ended up
    # buried inside the belly and the whole arm disappeared behind it.
    #
    # The slab is kept thin so it really is a horizontal ring at one height: a wide band
    # catches vertices from the head or the feet and reports their X as the waist.
    band = height * 0.035
    best_left = None
    best_right = None
    for s in submeshes:
        if s[-1] & FLAG_OUTLINE:
            continue
        mv = s[1]
        sel = (mv[:, 1] >= y - band) & (mv[:, 1] <= y + band)
        if not sel.any():
            continue
        ring = mv[sel]
        low = ring[np.argmin(ring[:, 0])]
        high = ring[np.argmax(ring[:, 0])]
        if best_left is None or low[0] < best_left[0]:
            best_left = low
        if best_right is None or high[0] > best_right[0]:
            best_right = high

    if best_left is not None and best_right is not None:
        # Pull each hand in from the silhouette so it rests on the surface rather than
        # hanging beside it. The pull is along X only; height and depth stay on the real
        # surface point so the hand cannot sink into the body.
        width = float(best_right[0] - best_left[0])
        hand_l = best_left.copy()
        hand_r = best_right.copy()
        hand_l[0] += width * inset
        hand_r[0] -= width * inset
    else:
        centre_x = float((lo[0] + hi[0]) * 0.5)
        centre_z = float((lo[2] + hi[2]) * 0.5)
        half_width = float(hi[0] - lo[0]) * 0.5
        hand_l = np.array([centre_x - half_width * (1.0 - inset), y, centre_z])
        hand_r = np.array([centre_x + half_width * (1.0 - inset), y, centre_z])

    # The anchor IS the hand position: the game copies it straight onto the player's
    # hand rig, and the hand is a skinned mesh that renders at that bone. So the point
    # chosen here is exactly where the hands appear — no offset is applied.
    #
    # These are the WAIST points, in model-local space, and they are published as-is.
    # The runtime does NOT write them onto the item's Hand_L / Hand_R nodes: doing that
    # made the hands land correctly but the plush shook, because the game's hold spring,
    # hand IK and FixedJoints only agree when the anchors keep their vanilla values.
    # Instead the runtime shifts the MODEL so these points meet the vanilla anchors.
    # See PlushieModel.SyncVisual for that step.
    rot_l = np.array(VANILLA_GRIP_ROT_L)
    rot_r = np.array(VANILLA_GRIP_ROT_R)

    return {
        "left": hand_l,
        "right": hand_r,
        "left_rot": rot_l,
        "right_rot": rot_r,
        "hand_left": hand_l,
        "hand_right": hand_r,
    }


def convert(path, out_path, name, budget=20000, keep_detail_faces=8000,
            filament_overrides=None, min_faces=24,
            target_height=VANILLA_HEIGHT,
            centre_x=VANILLA_CENTRE_X, centre_z=VANILLA_CENTRE_Z,
            bottom_y=VANILLA_BOTTOM_Y,
            face_player=True, area_weight=1.0,
            # how many rings of neighbours around the face features are also kept
            # ink-free, so no line creeps up against an eye or a blush
            face_mask_margin=0.045,
            # the drawn crease line where genuinely separate shells meet
            crease_width=0.055, crease_strength=0.60,
            # the interior line where a limb meets the body inside one mesh
            cavity_radius=0.055, cavity_strength=0.70, cavity_smooth_iterations=3,
            # shells hugging the very bottom of the model are print supports
            base_shell_height=0.12,
            # where the player's hands hold the plush, as a fraction of its height.
            # None means "find the waist automatically"; `grip_inset` pulls each hand
            # in from the silhouette so it wraps the body instead of hovering beside it.
            #
            # Keep this small. The player's hand is about 0.05 units across, so an inset
            # that pulls further than that leaves the hand floating beside the plush with
            # a visible gap — which reads as holding thin air. 0.04 puts it 0.02 inside
            # the surface, so it presses against the body the way a real grip would.
            grip_fraction=None, grip_inset=0.04,
            # a whisper of contact shading so the surface is not perfectly flat
            ao_radius_fraction=0.045, ao_strength=0.20, ao_floor=0.84,
            white_boost=0.0,
            outline_thickness=0.0075,
            # a surface whose area-weighted normal points down more steeply than this
            # can never face the camera, so it gets no ink (0 disables the test).
            # Miffy's skirt underside is such a disc, sitting right at the hem, and
            # without it the hull drew a sawtooth fringe across her legs.
            downward_threshold=0.55,

            outline_colour=(0.085, 0.085, 0.105, 1.0)):
    """Convert a Bambu 3MF into a compact runtime mesh ready for the game prefab.

    Face budget is shared between the large shells proportionally to their surface
    area (not their face count), which equalises triangle density across the model.
    Small shells keep full resolution so facial detail survives untouched.

    The result is authored directly in the game's item-local space: scaled to the
    vanilla plush height, turned to face the player, and carrying the waist hold
    points the runtime uses to place the model in the hands.
    """
    verts, tris, ext, rgb, palette = load_3mf(path)
    print(f"[{name}] source: {len(verts)} verts / {len(tris)} tris, {len(palette)} filaments")

    tex_path = os.path.splitext(out_path)[0] + "_shading.png"

    if filament_overrides:
        for filament, hex_colour in filament_overrides.items():
            mask = ext == filament
            rgb[mask] = np.array(_hex_to_unit(hex_colour), dtype=np.float32)
            print(f"[{name}]   filament {filament} -> #{hex_colour.lstrip('#')}"
                  f" ({int(mask.sum())} faces)")

    verts = np.ascontiguousarray(verts, dtype=np.float64)
    tris = np.ascontiguousarray(tris, dtype=np.int64)

    # 3MF / slicer space is Z-up.  Unity is Y-up: rotate -90 degrees about X.
    verts = np.column_stack([verts[:, 0], verts[:, 2], -verts[:, 1]])

    face_colour = _packed_colour(verts, tris, rgb)

    # Group faces by colour first.  Bambu "Merged Parts" models weld every colour
    # into one shared vertex pool, so connectivity must be rebuilt *inside* each
    # colour group (by welding positions) before shells can be told apart.
    groups = {}
    for value in np.unique(face_colour):
        groups[int(value)] = tris[face_colour == value]
    print(f"[{name}] colour groups: {len(groups)}")

    work = []
    for packed, group_faces in groups.items():
        gv, gt = remap_tris(verts, group_faces)
        gv, gt = weld(gv, gt)
        gv, gt = compact(gv, gt)
        if len(gt) == 0:
            continue
        roots = connected_components(len(gv), gt)
        for _, face_idx in split_faces_by_vertex_root(roots, gt):
            sv, st = submesh_from_faces(gv, gt, face_idx)
            sv, st = compact(sv, st)
            if len(st) < min_faces:
                continue
            work.append(dict(packed=packed, verts=sv, tris=st, faces=len(st),
                             area=triangle_area_sum(sv, st)))

    detail = [it for it in work if it["faces"] <= keep_detail_faces]
    heavy = [it for it in work if it["faces"] > keep_detail_faces]

    detail_faces = sum(it["faces"] for it in detail)
    remaining = max(3000, budget - detail_faces)
    heavy_area = sum(it["area"] for it in heavy) or 1.0
    print(f"[{name}]   shells total: {len(work)}"
          f"  (detail {len(detail)} keeping {detail_faces} faces, heavy {len(heavy)})")
    print(f"[{name}]   heavy surface area: {heavy_area:.0f} -> {remaining} face budget")

    # equalise triangle density: quota proportional to surface area
    for item in heavy:
        share = (item["area"] / heavy_area) ** area_weight
        item["quota"] = max(256, int(round(remaining * share)))

    total_quota = sum(it["quota"] for it in heavy)
    if total_quota > remaining:
        scale = remaining / float(total_quota)
        for item in heavy:
            item["quota"] = max(256, int(item["quota"] * scale))

    # Decimate first, so the facing probe runs on the final geometry.
    built = []
    for item in detail + heavy:
        sv, st = item["verts"], item["tris"]
        if "quota" in item and len(st) > item["quota"]:
            sv, st = simplify(sv, st, item["quota"])
            sv, st = compact(sv, st)
        if len(st) < min_faces:
            continue
        packed = item["packed"]
        col = np.array([(packed >> 16) & 255, (packed >> 8) & 255, packed & 255], dtype=np.float64) / 255.0
        built.append((col, sv, st))
        print(f"       #{packed:06X}: {item['faces']:>7d} -> {len(st):>6d} tris, {len(sv):>6d} verts")

    # Turn the model so its face looks at the player (-Z in item-local space).
    yaw = detect_facing_yaw(built) if face_player else 0.0
    if abs(yaw) > 0.001:
        for i, (col, sv, st) in enumerate(built):
            built[i] = (col, rot_y(sv, yaw), st)
    print(f"[{name}]   facing correction: {yaw:+.1f} deg (face now points to -Z / the player)")

    per_colour = defaultdict(list)
    for col, sv, st in built:
        col = apply_white_boost(col, white_boost)
        per_colour[tuple(np.round(col, 6))].append((col, sv, st))

    submeshes = []
    lo = np.array([1e30] * 3)
    hi = np.array([-1e30] * 3)
    for _, members in per_colour.items():
        col = members[0][0]
        parts_v, parts_t = [], []
        offset = 0
        for _, sv, st in members:
            parts_v.append(sv)
            parts_t.append(st + offset)
            offset += len(sv)
        mv = np.concatenate(parts_v, axis=0)
        mt = np.concatenate(parts_t, axis=0)
        mv, mt, normals = build_normals_with_sharp_edges(mv, mt)
        lo = np.minimum(lo, mv.min(axis=0))
        hi = np.maximum(hi, mv.max(axis=0))
        submeshes.append((np.concatenate([col, [1.0]]), mv, normals, mt))

    # Normalise to the vanilla silhouette and place it on the same pivot: uniform
    # scale to the vanilla height, XZ centred where the vanilla body sits, and the
    # vertical range shifted so the hand grips the plush around its middle.
    height = float(hi[1] - lo[1])
    factor = target_height / max(height, 1e-9)
    src_centre_x = float((lo[0] + hi[0]) * 0.5)
    src_centre_z = float((lo[2] + hi[2]) * 0.5)

    for i, (col, mv, nm, mt) in enumerate(submeshes):
        out = mv.copy()
        out[:, 0] = (out[:, 0] - src_centre_x) * factor + centre_x
        out[:, 2] = (out[:, 2] - src_centre_z) * factor + centre_z
        out[:, 1] = (out[:, 1] - lo[1]) * factor + bottom_y
        submeshes[i] = (col, out, nm, mt)

    # ------------------------------------------------------------------ shading
    # Cartoon look: flat bright surfaces, a drawn crease line where shells meet, and
    # only a whisper of contact shading. Broad smooth occlusion greys the toy out,
    # which is what made it look dull, so the AO contribution is kept very small.
    ao_maps = []
    component, distance, nearest = analyse_components(submeshes)
    face_decal, suppress = find_face_features(submeshes, face_mask_margin * target_height)
    # The print base touches the body all along its rim, which the cavity field turns
    # into a dark ring — the "wheel track" artefact. It is a support surface that is
    # never really visible, so it gets no ink at all.
    suppress |= find_base_shells(submeshes, base_shell_height)

    # The cavity field is measured on the whole model at once so the crease between
    # two parts of the same shell (bear's paws against its body) is found as well.
    all_verts = np.concatenate([s[1] for s in submeshes], axis=0)
    all_tris = []
    offset = 0
    for s in submeshes:
        all_tris.append(s[3] + offset)
        offset += len(s[1])
    all_tris = np.concatenate(all_tris, axis=0)
    cavity = compute_cavity_field(all_verts, all_tris, cavity_radius * target_height)
    # Smoothing is what turns the patchy per-vertex field into a line of even weight;
    # unsmoothed it reads as a pen that keeps running dry.
    cavity = smooth_scalar_over_surface(len(all_verts), all_tris, cavity,
                                        cavity_smooth_iterations, 0.55)

    offset = 0
    slices = []
    for col, mv, nm, mt in submeshes:
        slices.append(slice(offset, offset + len(mv)))
        offset += len(mv)

    ink_off = suppress
    for (col, mv, nm, mt), sl in zip(submeshes, slices):
        shade, _ = bake_cartoon_shading(mv, mt, distance[sl], nearest[sl], ink_off[sl],
                                        component[sl],
                                        crease_width * target_height, crease_strength,
                                        ao_radius_fraction * target_height,
                                        ao_strength, ao_floor,
                                        cavity=cavity[sl],
                                        cavity_line_strength=cavity_strength)
        ao_maps.append(shade)

    image, ranges = build_shading_texture(submeshes, ao_maps, ao_floor)
    textured = []
    for (col, mv, nm, mt), shade, (start, end) in zip(submeshes, ao_maps, ranges):
        level = (shade - ao_floor) / max(1e-6, 1.0 - ao_floor)
        texel = start + np.clip(level, 0.0, 1.0) * (AO_LEVELS - 1)
        uv = np.zeros((len(mv), 2), dtype=np.float64)
        uv[:, 0] = (texel + 0.5) / image.shape[1]
        uv[:, 1] = 0.5
        textured.append((col, mv, nm, uv, mt, 0))
    submeshes = textured
    # The palette PNG is written at the very END, after the .psmesh, because the two are
    # a pair: a fresh PNG next to a stale mesh (or the reverse) makes the model sample the
    # wrong texels. Both files are staged to a temp name and only renamed into place when
    # every step has succeeded, so a crash in the outline stage below cannot leave a
    # mismatched pair on disk.
    all_shade = np.concatenate(ao_maps)
    print(f"[{name}]   cartoon shading -> {os.path.basename(tex_path)} "
          f"({image.shape[1]}x1 px, darkest {all_shade.min():.2f}, "
          f"inked verts {100.0 * np.mean(all_shade < 0.95):.0f}%, "
          f"face-mask verts {100.0 * np.mean(suppress):.0f}%)")

    # ------------------------------------------------------------------ outline
    # The whole solid mesh becomes the ink shell: NO faces are removed, so the hull
    # stays one closed surface and the silhouette never breaks. Width is therefore
    # controlled per vertex instead of by deletion — a smooth `fade` field decides how
    # far each shell vertex is pushed, and a vertex faded to zero sits on the body and
    # draws no ink.
    #
    # Getting here took two wrong turns, both measured:
    #
    #   1. A per-vertex 0/1 WIDTH MAP (the Unity Toon Shader "outline width map").
    #      On a connected mesh any 0/1 mask leaves "mixed" faces along every boundary:
    #      one corner is pushed out, two sit on the body, so the triangle becomes a
    #      sliver that crosses the surface and draws a stray stroke. Miffy had ~4900 of
    #      those (15% of her shell).
    #
    #   2. DELETING those mixed faces. That kills the slivers, but every deleted face
    #      leaves a boundary edge, and an edge where the hull simply stops is a place
    #      the ink stops. Measured against the body silhouette it removed 22.6% of
    #      Miffy's outline and 29.9% of the bear's — the "broken outline" the user
    #      reported. The arm tips were worst: `inside_other_shell` classified a hand
    #      resting against the dress as "enclosed", so whole fingertips lost their ink.
    #
    # The masks themselves are not useless — they stop the hull drawing a ring around a
    # recessed eye and a sawtooth fringe under Miffy's skirt — so they are kept, but as
    # a SMOOTH width instead of a delete. The shell still closes over the region (so the
    # silhouette never breaks) while the ink fades out there.
    #
    # `enclosed` is deliberately NOT applied. It is the mask that cut the fingertips
    # off, and a surface inside another shell is already hidden by that shell, so its
    # ink cannot be seen anyway.
    #
    # The push direction is the position-averaged normal, not the shading normal:
    # extruding along split normals is the documented cause of outlines that break
    # apart at every hard edge.
    outline_map = None
    if outline_thickness > 0.0:
        sv = np.concatenate([s[1] for s in submeshes], axis=0)
        st = []
        offset = 0
        for s in submeshes:
            st.append(s[-2] + offset)
            offset += len(s[1])
        st = np.concatenate(st, axis=0)

        sv, st, on, origin = build_outline_normals(sv, st)

        # ------------------------------------------------------------------ direction
        # The shell is extruded along a direction field, and the runtime re-extrudes
        # along the *stored* direction every frame in screen space. So this field decides
        # where the ink lands.
        #
        # A pure surface normal is wrong on a concave surface: inside a groove the normal
        # points across the groove, the pushed vertex lands on the far wall, and the ink
        # is drawn inside the body — the "line does not follow the model" artefact. A pure
        # radial direction (straight out from the model centre) can never do that on a
        # roughly star-shaped model, but it does not follow the surface either, so the
        # line stops hugging the silhouette.
        #
        # The direction is therefore blended: `normal + k * radial`. The radial term
        # dominates exactly where the normal would cross a groove (the two disagree
        # strongly there) and barely matters on a smooth convex surface (where they
        # already agree), which removes the leak while keeping the line on the surface.
        centroid = sv.mean(axis=0)
        radial = sv - centroid
        radial /= np.linalg.norm(radial, axis=1, keepdims=True)
        direction = on + radial
        direction /= np.linalg.norm(direction, axis=1, keepdims=True)

        # The eyes, mouth and blush are raised discs recessed into the head, so the hull
        # follows that groove and its far wall shows through as a thick ring drawn
        # around each feature. They get no ink, and neither does a small ring of head
        # around them (the padded `suppress` mask), because the cavity field fires there.
        #
        # Downward-facing surfaces are seen edge-on from every angle and can never form
        # a silhouette. Miffy's skirt is a closed volume whose underside is a flat disc
        # at the hem, which drew a sawtooth fringe across her legs.
        down = (downward_face_weight(submeshes, downward_threshold)
                if downward_threshold > 0.0 else np.zeros(len(sv), dtype=bool))

        fade = np.ones(len(sv), dtype=np.float64)
        fade[suppress[origin]] = 0.0
        fade[down[origin]] = 0.0

        # Ramp the width in over the surface so the hidden region blends into the line
        # instead of ending at a hard step (a step reads as a stray spur).
        fade = smooth_scalar_over_surface(len(sv), st, fade, 4, 0.5)

        # Pin the features fully out after smoothing, so no ink creeps onto an eye.
        fade[face_decal[origin]] = 0.0

        # Which shell vertices are allowed to draw. Everything with a non-trivial width,
        # and no faces are removed, so the hull stays one closed surface.
        inked = fade > 0.35
        fade[~inked] = 0.0

        print(f"[{name}]   outline shell: {len(st)} tris, {len(sv)} verts "
              f"({int((~inked).sum())} of {len(sv)} verts carry no ink)")

        shell = build_cartoon_outline(sv, st, direction,
                                      outline_thickness * target_height,
                                      outline_colour, width=fade)
        submeshes = submeshes + [shell]

        # The per-vertex width is written so the runtime can undo exactly this push
        # (`surface = shell - normal * thickness * width`).
        outline_map = (origin, fade)

        g_lo = np.array([min(s[1][:, k].min() for s in submeshes) for k in range(3)])
        g_hi = np.array([max(s[1][:, k].max() for s in submeshes) for k in range(3)])
        shift = np.array([
            centre_x - (g_lo[0] + g_hi[0]) * 0.5,
            bottom_y - g_lo[1],
            centre_z - (g_lo[2] + g_hi[2]) * 0.5,
        ])
        if np.any(np.abs(shift) > 1e-9):
            submeshes = [(c, mv + shift, nm, uv, mt, fl)
                         for c, mv, nm, uv, mt, fl in submeshes]

        print(f"[{name}]   cartoon outline shell (thickness "
              f"{outline_thickness * target_height:.4f} units, realigned by {np.round(shift, 4)})")

    b_lo = np.array([min(s[1][:, k].min() for s in submeshes) for k in range(3)])
    b_hi = np.array([max(s[1][:, k].max() for s in submeshes) for k in range(3)])

    total = sum(len(s[4]) for s in submeshes)
    total_v = sum(len(s[1]) for s in submeshes)
    print(f"[{name}] final: {len(submeshes)} submeshes, {total} tris, {total_v} verts")
    print(f"[{name}]   scale factor {factor:.6f}, size (X,Y,Z) {np.round(b_hi - b_lo, 4)}")
    print(f"[{name}]   bounds X[{b_lo[0]:+.4f},{b_hi[0]:+.4f}] "
          f"Y[{b_lo[1]:+.4f},{b_hi[1]:+.4f}] Z[{b_lo[2]:+.4f},{b_hi[2]:+.4f}]")
    print(f"[{name}]   colours: " + ", ".join(f"#{int(c[0]*255):02X}{int(c[1]*255):02X}{int(c[2]*255):02X}"
                                              for c, *_ in submeshes))

    # Where the player's hands hold the plush. The game snaps the hand rigs to the
    # item's "Hand_L" / "Hand_R" children, so these points are what decide the pose.
    # Every caller pins the height explicitly: an automatic "narrowest torso band"
    # search used to be the fallback, but it picked a different waist for each model
    # than the heights the user confirmed, so it was removed.
    if grip_fraction is None:
        raise ValueError("grip_fraction must be given: the hand height is part of the look")
    grips = compute_grip_points(submeshes, (b_lo, b_hi), grip_fraction, grip_inset)
    print(f"[{name}]   hands land at L {np.round(grips['hand_left'], 3)}  "
          f"R {np.round(grips['hand_right'], 3)} (height {grip_fraction * 100:.0f}%)")
    print(f"[{name}]   anchors       L {np.round(grips['left'], 3)}  "
          f"R {np.round(grips['right'], 3)}")

    # The .psmesh is written first (to a temp name), then the palette PNG, then both are
    # renamed into place. Publishing the pair this way means neither file can ever be
    # newer than the other on disk. The PNG keeps a `.png` ending on the staging name
    # because Pillow infers the writer from the extension.
    mesh_tmp = out_path + ".tmp"
    png_tmp = tex_path[:-len(".png")] + ".tmp.png"
    write_psmesh(mesh_tmp, name, submeshes, (b_lo, b_hi), grips, None, outline_map,
                 baked_outline_thickness=outline_thickness * target_height
                 if outline_thickness > 0.0 else 0.0)
    _replace_pair(mesh_tmp, out_path, png_tmp, tex_path, image)
    print(f"[{name}] wrote {out_path} ({os.path.getsize(out_path) / 1024:.0f} KB)")
    return submeshes


# -------------------------------------------------------------------- build jobs
# Cartoon treatment shared by both plushies: a single outer ink outline, a whisper of
# contact AO (kept light so the toy does not go grey), and the bright parts pushed hard
# toward cream white.
#
# The interior crease/cavity lines are disabled (strength 0): the user wants ONE line
# around the whole silhouette and nothing drawn on the surface itself. Those two fields
# were what produced the "messy, tangled" lines across the model.
CARTOON = dict(white_boost=1.0, outline_thickness=0.0075,
               crease_strength=0.0, cavity_strength=0.0,
               ao_strength=0.10, ao_floor=0.92)

# The hands go on the waist. Miffy's is at 0.22 of her height (the middle of her dress);
# the barrel-shaped bear needs 0.26 to land on its lower body. `grip_inset` pulls each
# hand in from the silhouette so it rests on the surface instead of clipping through it.
JOBS = [
    dict(name="Miffy", source="miffy.3mf", out="miffy.psmesh",
         budget=32000, keep_detail_faces=3000,
         grip_fraction=0.22, grip_inset=0.04),
    dict(name="ZichaoXiong", source="zichaoxiong.3mf", out="zichaoxiong.psmesh",
         budget=32000, keep_detail_faces=3000,
         filament_overrides={2: "#F95D73"},
         grip_fraction=0.26, grip_inset=0.04),
]


def params_for_job(job):
    """The full keyword-argument set `convert` is called with for one job."""
    params = {key: value for key, value in job.items()
              if key not in ("name", "source", "out", "filament_overrides")}
    params.update(CARTOON)
    return params


def canonical_params_for_job(job):
    """The canonical string recorded in the manifest for one job.

    Folds in `filament_overrides`, which repaints whole shells but is not part of the
    keyword arguments, so a change to it has to invalidate the manifest too.
    """
    effective = params_for_job(job)
    effective["filament_overrides"] = {
        str(k): v for k, v in sorted((job.get("filament_overrides") or {}).items())
    }
    return canonical_params(effective)


def job_params():
    """Map output .psmesh name -> canonical parameter string, for verify_assets.py.

    verify_assets.py imports this instead of re-deriving the parameters, so the build
    and the check can never disagree about what "the current parameters" are.
    """
    return {job["out"]: canonical_params_for_job(job) for job in JOBS}


if __name__ == "__main__":
    # Source models live beside the project. The temp copy used previously was wiped by
    # the OS between sessions, which silently broke the pipeline.
    HERE = os.path.dirname(os.path.abspath(__file__))
    MODELS = os.path.join(os.path.dirname(HERE), "models")
    OUT = os.path.join(os.path.dirname(HERE), "assets")
    MANIFEST = os.path.join(OUT, "manifest.json")
    os.makedirs(OUT, exist_ok=True)

    # `jobs` and `cartoon` are module-level so verify_assets.py can recompute the exact
    # same parameter set instead of keeping a second copy that could drift.
    generator = generator_hashes()
    entries = {}
    for job in JOBS:
        source_path = os.path.join(MODELS, job["source"])
        out_path = os.path.join(OUT, job["out"])
        params = params_for_job(job)
        convert(source_path, out_path, job["name"],
                filament_overrides=job.get("filament_overrides"), **params)
        shading_name = os.path.splitext(job["out"])[0] + "_shading.png"
        entries[job["out"]] = {
            "source": "models/" + job["source"],
            "source_sha256": _sha256(source_path),
            "mesh_sha256": _sha256(out_path),
            "shading_png": shading_name,
            "shading_sha256": _sha256(os.path.join(OUT, shading_name)),
            "params": params,
            "params_canonical": canonical_params_for_job(job),
        }
    write_manifest(MANIFEST, entries, generator)
