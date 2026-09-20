"""Work out grip anchors that put the visible HAND on the plush's waist.

CharacterItems copies the item anchor's position and rotation onto the player's hand
RIG. The hand model hangs off that rig by its own transform, so the anchor sits at the
WRIST and the visible hand is a fixed offset away from it, rotated with the anchor:

    hand_centre_in_item = anchor_pos + anchor_rot * hand_offset_in_anchor_space

Placing the anchor on the waist therefore does NOT put the hand on the waist — the hand
ends up wherever that offset points. This solves for the anchor instead:

    anchor_pos = waist_point - anchor_rot * hand_offset

so the hand centre lands exactly on the chosen waist point.
"""
import os

import numpy as np
import UnityPy

GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
ASSETS = r"D:\zhuanban\Plushie Swap\assets"

# vanilla grip rotations, read from BingBong_Prop Variant (see dump_bingbong_hands.py)
ROT_L = (-0.31818, 0.67636, 0.51899, -0.41466)
ROT_R = (0.25786, 0.71867, 0.55145, 0.33605)


def quat_mat(q):
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    if n < 1e-12:
        return np.eye(3)
    s = 2.0 / n
    return np.array([
        [1 - s * (y * y + z * z), s * (x * y - w * z), s * (x * z + w * y)],
        [s * (x * y + w * z), 1 - s * (x * x + z * z), s * (y * z - w * x)],
        [s * (x * z - w * y), s * (y * z + w * x), 1 - s * (x * x + y * y)],
    ])


def hand_offsets():
    """Hand mesh centre in each anchor's local space."""
    res = UnityPy.load(os.path.join(GAME, "resources.assets"))
    objects = {o.path_id: o for o in res.objects}
    meshes = {}
    for o in res.objects:
        if o.type.name == "Mesh":
            try:
                meshes[o.path_id] = o.read()
            except Exception:
                pass

    def transform_id(go_id):
        gd = objects[go_id].read()
        for comp in gd.m_Components:
            if comp is None:
                continue
            cr = objects.get(comp.path_id)
            if cr is not None and cr.type.name == "Transform":
                return comp.path_id
        return None

    def children(tid):
        tr = objects[tid].read()
        out = []
        for ch in tr.m_Children:
            if ch is None:
                continue
            cgo = ch.read()
            ref = getattr(cgo, "m_GameObject", None)
            if ref is None:
                continue
            gd = objects[ref.path_id].read()
            out.append((gd.m_Name, ref.path_id, gd))
        return out

    root = None
    for o in res.objects:
        if o.type.name != "GameObject":
            continue
        try:
            gd = o.read()
        except Exception:
            continue
        if gd.m_Name == "BingBong_Prop Variant":
            root = o.path_id
            break

    result = {}
    for name, go_id, gd in children(transform_id(root)):
        if name not in ("Hand_L", "Hand_R"):
            continue
        tid = transform_id(go_id)
        for cname, cgo_id, cgd in children(tid):
            ctr_id = transform_id(cgo_id)
            ctr = objects[ctr_id].read()
            p, q, s = ctr.m_LocalPosition, ctr.m_LocalRotation, ctr.m_LocalScale
            # the child's frame relative to its parent (the anchor)
            m = np.eye(4)
            m[:3, :3] = quat_mat((q.x, q.y, q.z, q.w)) @ np.diag([s.x, s.y, s.z])
            m[:3, 3] = [p.x, p.y, p.z]

            for comp in cgd.m_Components:
                if comp is None:
                    continue
                cr = objects.get(comp.path_id)
                if cr is None or cr.type.name != "MeshFilter":
                    continue
                mf = cr.read()
                if mf.m_Mesh is None:
                    continue
                mesh = meshes.get(mf.m_Mesh.path_id)
                if mesh is None:
                    continue
                a = mesh.m_LocalAABB
                centre = np.array([a.m_Center.x, a.m_Center.y, a.m_Center.z])
                result[name] = m[:3, :3] @ centre + m[:3, 3]
    return result


def read_psmesh(path):
    import struct
    with open(path, "rb") as fh:
        magic = fh.read(8)
        assert magic == b"PSMESH03", magic
        n = struct.unpack("<i", fh.read(4))[0]
        fh.read(n)
        count = struct.unpack("<i", fh.read(4))[0]
        subs = []
        for _ in range(count):
            colour = np.array(struct.unpack("<4f", fh.read(16)))
            flags = struct.unpack("<i", fh.read(4))[0]
            vc, ic = struct.unpack("<ii", fh.read(8))
            verts = np.frombuffer(fh.read(vc * 12), dtype="<f4").reshape(-1, 3)
            normals = np.frombuffer(fh.read(vc * 12), dtype="<f4").reshape(-1, 3)
            uvs = np.frombuffer(fh.read(vc * 8), dtype="<f4").reshape(-1, 2)
            fh.read(vc * 12)
            idx = np.frombuffer(fh.read(ic * 4), dtype="<i4").reshape(-1, 3)
            subs.append((colour, verts, normals, uvs, idx, flags))
        lo = np.array(struct.unpack("<3f", fh.read(12)))
        hi = np.array(struct.unpack("<3f", fh.read(12)))
    return subs, lo, hi


def waist_point(subs, lo, hi, fraction, inset):
    height = float(hi[1] - lo[1])
    y = lo[1] + height * fraction
    band = height * 0.10
    xs, zs = [], []
    for s in subs:
        if s[5] & 1:
            continue
        v = s[1]
        sel = (v[:, 1] >= y - band) & (v[:, 1] <= y + band)
        if sel.any():
            xs.append(v[sel, 0])
            zs.append(v[sel, 2])
    xs = np.concatenate(xs)
    zs = np.concatenate(zs)
    z = float((zs.min() + zs.max()) * 0.5)
    left, right = float(xs.min()), float(xs.max())
    width = right - left
    return (np.array([left + width * inset, y, z]),
            np.array([right - width * inset, y, z]),
            y)


def main():
    offsets = hand_offsets()
    hl = offsets["Hand_L"]
    hr = offsets["Hand_R"]
    print("hand mesh centre in anchor space:")
    print(f"  Hand_L = {np.round(hl, 5)}")
    print(f"  Hand_R = {np.round(hr, 5)}")
    print()

    rl, rr = quat_mat(ROT_L), quat_mat(ROT_R)
    print(f"anchor_rot * hand_offset (the shift from wrist to palm):")
    print(f"  L = {np.round(rl @ hl, 5)}")
    print(f"  R = {np.round(rr @ hr, 5)}")
    print()

    for stem, inset in (("miffy", 0.20), ("zichaoxiong", 0.20)):
        subs, lo, hi = read_psmesh(os.path.join(ASSETS, stem + ".psmesh"))
        height = float(hi[1] - lo[1])
        print(f"=== {stem}  Y [{lo[1]:+.4f}, {hi[1]:+.4f}] height {height:.4f} ===")
        print(f"{'frac':>5} {'Y':>9} | {'handL':>26} | {'anchorL':>26}")
        for frac in (0.10, 0.14, 0.18, 0.22, 0.26, 0.30):
            wl, wr, y = waist_point(subs, lo, hi, frac, inset)
            pl = wl - rl @ hl
            pr = wr - rr @ hr
            print(f"{frac:5.2f} {y:+9.4f} | "
                  f"({wl[0]:+.3f},{wl[1]:+.3f},{wl[2]:+.3f}) | "
                  f"({pl[0]:+.3f},{pl[1]:+.3f},{pl[2]:+.3f})")
            print(f"{'':5} {'':9} | "
                  f"({wr[0]:+.3f},{wr[1]:+.3f},{wr[2]:+.3f}) | "
                  f"({pr[0]:+.3f},{pr[1]:+.3f},{pr[2]:+.3f})")
        print()


if __name__ == "__main__":
    main()
