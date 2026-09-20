"""Parse Bambu Studio 3MF into a merged mesh with per-triangle filament colours.

Bambu stores multi-colour data as a per-triangle `paint_color` attribute holding a
nibble-packed recursive triangle-subdivision tree, plus per-part `extruder` metadata
in Metadata/model_settings.config.  Filament colours live in
Metadata/project_settings.config -> filament_colour.

paint_color nibble layout (read the hex string right-to-left):
    bit 0..1  (yy) == 0  -> leaf triangle
    bit 2..3  (xx)       -> 0 = inherit, 1..2 = extruder, 3 = extended (read next nibble, +3)
    yy != 0              -> subdivided into yy child triangles (recurse)
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter

import numpy as np

NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
NSP = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"


def _hex_to_rgb(text):
    text = text.strip().lstrip("#")
    if len(text) >= 8:
        text = text[:6]
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    return np.array([int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)], dtype=np.uint8)


def read_filament_colours(zf):
    txt = zf.read("Metadata/project_settings.config").decode("utf-8", "replace")
    match = re.search(r'"filament_colour"\s*:\s*\[([^\]]*)\]', txt)
    if not match:
        return [np.array([255, 255, 255], dtype=np.uint8)]
    colours = [_hex_to_rgb(m) for m in re.findall(r'"([^"]*)"', match.group(1))]
    if not colours:
        # A slicer can emit `"filament_colour": []`. An empty palette then indexes out
        # of bounds when a face's extruder is resolved, so a neutral white is used
        # instead of crashing.
        return [np.array([255, 255, 255], dtype=np.uint8)]
    return colours


def read_part_extruders(zf):
    """Return (parts_by_object, extruders_by_object).

    parts_by_object maps root object id -> ordered list of part extruders, where the
    list index corresponds to the component ordinal inside that object.
    """
    parts, objects = {}, {}
    try:
        txt = zf.read("Metadata/model_settings.config").decode("utf-8", "replace")
    except KeyError:
        return parts, objects
    root = ET.fromstring(txt)
    for obj in root.iter("object"):
        oid = obj.get("id")
        for meta in obj.findall("metadata"):
            if meta.get("key") == "extruder":
                objects[oid] = int(meta.get("value"))
        ordered = []
        for part in obj.iter("part"):
            ex = None
            for meta in part.findall("metadata"):
                if meta.get("key") == "extruder":
                    ex = int(meta.get("value"))
            ordered.append(ex)
        if ordered:
            parts[oid] = ordered
    return parts, objects


def decode_paint_state(code):
    """Return the dominant extruder index (1-based) encoded in a paint_color string, or None."""
    nibbles = [int(c, 16) for c in reversed(code)]

    def read_state(pos):
        if pos >= len(nibbles):
            return 0, pos
        value = nibbles[pos]
        pos += 1
        yy = value & 0b11
        xx = (value >> 2) & 0b11
        if yy != 0:
            # Subdivided: collect states from all children, keep the most common painted one.
            votes = Counter()
            for _ in range(yy):
                state, pos = read_state(pos)
                votes[state] += 1
            painted = {s: c for s, c in votes.items() if s != 0}
            if not painted:
                return 0, pos
            return max(painted.items(), key=lambda kv: kv[1])[0], pos
        if xx < 3:
            return xx, pos
        # Extended encoding: 3, 8, 13, ... until a non-15 terminator is read.
        extra = 0
        while True:
            nxt = nibbles[pos] if pos < len(nibbles) else 0
            pos += 1
            if nxt == 15:
                extra += 1
                continue
            return nxt + 3 + 12 * extra, pos

    state, _ = read_state(0)
    return state if state > 0 else None


def parse_member(zf, member):
    """Parse every mesh object in one `.model` member, once.

    Returns a list of (ordinal, object_id, verts, tris, tri_state) for the objects that
    carry geometry. `ordinal` is the object's position in the member's FULL `<object>`
    list, including the empty objects that are dropped here: the caller indexes the
    per-part extruder list by that position, so renumbering the surviving objects would
    silently pick the wrong filament.

    This is the expensive half of the work (unzip + ElementTree + every vertex and
    triangle). It depends only on `member`, so it is cached per member by
    `parse_object_model`; the cheap per-object extruder resolution stays there.
    """
    root = ET.fromstring(zf.read(member).decode("utf-8", "replace"))
    results = []
    for ordinal, obj in enumerate(root.iter(f"{NS}object")):
        oid = obj.get("id")
        verts, tris, tri_state = [], [], []
        for mesh in obj.iter(f"{NS}mesh"):
            # Each `<mesh>` numbers its own vertices from zero. When an object holds more
            # than one mesh the triangles of the second mesh would silently point at the
            # first mesh's vertices, so the base offset is recorded and applied.
            base = len(verts)
            for v in mesh.iter(f"{NS}vertex"):
                verts.append((float(v.get("x")), float(v.get("y")), float(v.get("z"))))
            for t in mesh.iter(f"{NS}triangle"):
                tris.append((int(t.get("v1")) + base,
                             int(t.get("v2")) + base,
                             int(t.get("v3")) + base))
                code = t.get("paint_color")
                tri_state.append(decode_paint_state(code) if code else None)
        if not verts and not tris:
            continue
        results.append((ordinal, oid,
                        np.array(verts, dtype=np.float64),
                        np.array(tris, dtype=np.int64),
                        tri_state))
    return results


def parse_object_model(zf, member, object_extruders, fallback_extruder=None,
                       member_cache=None):
    """Return list of (object_id, vertices, triangles, extruder_per_triangle).

    object_extruders maps an ordered part list for the parent object; the part ordinal
    of each mesh object in this file selects the default filament for its unpainted faces.

    `member_cache` is an optional dict mapping member name -> `parse_member` result. The
    XML and the geometry are identical for every object in a member, so without it a
    caller resolving five objects out of the same 5 MB member re-parses the whole file
    five times (measured: 4 redundant parses, ~17 s on miffy.3mf).
    """
    if member_cache is not None and member in member_cache:
        parsed = member_cache[member]
    else:
        parsed = parse_member(zf, member)
        if member_cache is not None:
            member_cache[member] = parsed

    results = []
    for ordinal, oid, verts, tris, tri_state in parsed:
        default_ex = 1
        if object_extruders and ordinal < len(object_extruders) and object_extruders[ordinal]:
            default_ex = object_extruders[ordinal]
        elif fallback_extruder:
            default_ex = fallback_extruder
        resolved = np.array([s if s else default_ex for s in tri_state], dtype=np.int32)
        results.append((oid, verts, tris, resolved))
    return results


def _mat4x3(values):
    if not values:
        return np.eye(4)
    m = np.eye(4)
    a = np.array(values, dtype=np.float64).reshape(4, 3)
    m[:3, :3] = a[:3].T
    m[:3, 3] = a[3]
    return m


def load_3mf(path):
    """Return merged (verts, tris, tri_extruder), plus filament colours."""
    with zipfile.ZipFile(path) as zf:
        colours = read_filament_colours(zf)
        part_ex, obj_ex = read_part_extruders(zf)

        root_member = "3D/3dmodel.model"
        root = ET.fromstring(zf.read(root_member).decode("utf-8", "replace"))

        member_cache = {}

        def member_objects(member):
            if member not in member_cache:
                tree = ET.fromstring(zf.read(member).decode("utf-8", "replace"))
                by_id = {}
                for ordinal, obj in enumerate(tree.iter(f"{NS}object")):
                    by_id[obj.get("id")] = (ordinal, obj)
                member_cache[member] = by_id
            return member_cache[member]

        mesh_cache = {}
        # member name -> parse_member() result. See get_mesh() for why this is separate.
        parsed_members = {}
        all_v, all_t, all_e = [], [], []
        state = {"offset": 0}

        def add_mesh(verts, tris, tri_ex, matrix):
            if len(verts) == 0:
                return
            v = verts @ matrix[:3, :3].T + matrix[:3, 3]
            all_v.append(v.astype(np.float32))
            all_t.append(tris + state["offset"])
            all_e.append(tri_ex)
            state["offset"] += len(v)

        def get_mesh(member, oid, part_list, fallback_ex):
            # Two caches, deliberately:
            #
            #   `parsed_members` holds the expensive per-member parse (unzip +
            #   ElementTree + every vertex/triangle) and is keyed by member alone,
            #   because that result does not depend on which object is being asked for.
            #
            #   `mesh_cache` keeps the original `(member, oid)` -> first-call-wins
            #   semantics so the resolved per-face extruders are byte-for-byte what
            #   this function produced before; only the redundant re-parsing is gone.
            key = (member, oid)
            if key not in mesh_cache:
                models = parse_object_model(zf, member, part_list, fallback_ex,
                                            parsed_members)
                mesh_cache[key] = {o: (vv, tt, ee) for o, vv, tt, ee in models}
            return mesh_cache[key].get(oid)

        def resolve(oid, matrix, member, part_list, depth=0):
            if depth > 8:
                return
            entry = get_mesh(member, oid, part_list, obj_ex.get(oid))
            if entry is not None:
                add_mesh(*entry, matrix)
                return
            by_id = member_objects(member)
            found = by_id.get(oid)
            if found is None:
                return
            _, obj = found
            for index, comp in enumerate(obj.iter(f"{NS}component")):
                child_member = comp.get(f"{NSP}path", member).lstrip("/")
                child_oid = comp.get("objectid")
                child_ex = part_list[index] if part_list and index < len(part_list) else None
                transform = comp.get("transform")
                resolve(child_oid, matrix @ _mat4x3(
                    [float(x) for x in transform.split()] if transform else None
                ), child_member, part_list, depth + 1)

        build = root.find(f"{NS}build")
        for item in build.iter(f"{NS}item"):
            root_oid = item.get("objectid")
            transform = item.get("transform")
            resolve(root_oid, _mat4x3(
                [float(x) for x in transform.split()] if transform else None
            ), root_member, part_ex.get(root_oid))

        if not all_v:
            raise RuntimeError("no geometry found in " + path)

        verts = np.concatenate(all_v, axis=0)
        tris = np.concatenate(all_t, axis=0)
        ext = np.concatenate(all_e, axis=0)

    pal = np.zeros((len(colours), 3), dtype=np.float32)
    for i, c in enumerate(colours):
        pal[i] = c.astype(np.float32) / 255.0
    rgb = pal[np.clip(ext - 1, 0, len(colours) - 1)]
    return verts, tris, ext, rgb, colours


def write_ply(path, verts, tris, rgb, tri_rgb=None):
    """Write an ASCII/binary little-endian PLY with per-vertex colours."""
    vcol = rgb
    if tri_rgb is not None:
        vcol = tri_rgb
    colours8 = np.clip(np.round(vcol * 255.0), 0, 255).astype(np.uint8)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {len(verts)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        f"element face {len(tris)}\n"
        "property list uchar int vertex_indices\n"
        "end_header\n"
    ).encode("ascii")
    with open(path, "wb") as fh:
        fh.write(header)
        rec = np.empty(len(verts), dtype=np.dtype([
            ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
            ("r", "u1"), ("g", "u1"), ("b", "u1")]))
        rec["x"], rec["y"], rec["z"] = verts[:, 0], verts[:, 1], verts[:, 2]
        rec["r"], rec["g"], rec["b"] = colours8[:, 0], colours8[:, 1], colours8[:, 2]
        fh.write(rec.tobytes())
        frec = np.empty(len(tris), dtype=np.dtype([("n", "u1"), ("a", "<i4"), ("b", "<i4"), ("c", "<i4")]))
        frec["n"] = 3
        frec["a"], frec["b"], frec["c"] = tris[:, 0], tris[:, 1], tris[:, 2]
        fh.write(frec.tobytes())
