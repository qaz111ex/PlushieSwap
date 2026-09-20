"""Diagnose the shipped .psmesh: outline shell topology + body width profile.

Two questions this answers with measurements instead of guesses:

1. Does the ink shell have boundary edges (places where a stroke simply stops)?
   A closed hull has none. Every boundary edge is a spot where the outline can
   visibly break, so their count and location say whether the "broken outline"
   comes from dropped faces or from something else.

2. How wide is the plush at each height, compared with the width the game's
   vanilla hand anchors assume? The anchors are 0.6034 apart, so a plush that is
   only ~0.39 wide at the grip height leaves the hands hanging in the air.
"""
import os
import struct
import sys

import numpy as np


def read_psmesh(path):
    with open(path, "rb") as fh:
        data = fh.read()
    off = 0

    def take(n):
        nonlocal off
        v = data[off:off + n]
        off += n
        return v

    magic = take(8)
    assert magic == b"PSMESH03", magic
    (name_len,) = struct.unpack_from("<i", data, off); off += 4
    name = take(name_len).decode("utf-8")
    (sub_count,) = struct.unpack_from("<i", data, off); off += 4
    subs = []
    for _ in range(sub_count):
        col = np.frombuffer(take(16), dtype="<f4").copy()
        (flags,) = struct.unpack_from("<i", data, off); off += 4
        (vc, ic) = struct.unpack_from("<ii", data, off); off += 8
        pos = np.frombuffer(take(12 * vc), dtype="<f4").reshape(vc, 3).astype(np.float64)
        nrm = np.frombuffer(take(12 * vc), dtype="<f4").reshape(vc, 3).astype(np.float64)
        uv = np.frombuffer(take(8 * vc), dtype="<f4").reshape(vc, 2).astype(np.float64)
        cols = np.frombuffer(take(12 * vc), dtype="<f4").reshape(vc, 3).astype(np.float64)
        idx = np.frombuffer(take(4 * ic), dtype="<i4").reshape(ic // 3, 3).astype(np.int64)
        subs.append(dict(col=col, flags=int(flags), pos=pos, nrm=nrm, uv=uv,
                         cols=cols, tris=idx))
    bmin = np.frombuffer(take(12), dtype="<f4").astype(np.float64)
    bmax = np.frombuffer(take(12), dtype="<f4").astype(np.float64)
    grips = None
    (has_grips,) = struct.unpack_from("<i", data, off); off += 4
    if has_grips:
        gl = np.frombuffer(take(12), dtype="<f4").astype(np.float64)
        gr = np.frombuffer(take(12), dtype="<f4").astype(np.float64)
        lr = np.frombuffer(take(16), dtype="<f4")
        rr = np.frombuffer(take(16), dtype="<f4")
        grips = dict(left=gl, right=gr, lrot=lr, rrot=rr)
    (wob,) = struct.unpack_from("<i", data, off); off += 4
    off += wob
    (oc,) = struct.unpack_from("<i", data, off); off += 4
    widths = None
    if oc:
        off += oc * 4
        widths = np.frombuffer(take(oc), dtype=np.uint8)
    (thick,) = struct.unpack_from("<f", data, off); off += 4
    assert off == len(data), (off, len(data))
    return dict(name=name, subs=subs, bmin=bmin, bmax=bmax, grips=grips,
                widths=widths, thickness=float(thick))


def boundary_edges(tris):
    """Edges referenced by exactly one triangle."""
    edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]], axis=0)
    key = np.sort(edges, axis=1)
    uniq, counts = np.unique(key, axis=0, return_counts=True)
    return uniq[counts == 1]


def components(vert_count, tris):
    parent = np.arange(vert_count)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for t in tris:
        ra, rb, rc = find(t[0]), find(t[1]), find(t[2])
        for r in (rb, rc):
            if r != ra:
                parent[r] = ra
    roots = np.array([find(i) for i in range(vert_count)])
    return roots


def main():
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    for name in ("miffy", "zichaoxiong"):
        path = os.path.join(base, "assets", name + ".psmesh")
        mesh = read_psmesh(path)
        print(f"===== {name} ({os.path.getsize(path)/1024:.0f} KB) =====")
        print(f"  thickness={mesh['thickness']:.6f}  widths={'yes' if mesh['widths'] is not None else 'no'}")
        print(f"  bounds min={np.round(mesh['bmin'],4)} max={np.round(mesh['bmax'],4)}")
        if mesh["grips"]:
            g = mesh["grips"]
            print(f"  grip L={np.round(g['left'],4)} R={np.round(g['right'],4)}"
                  f"  sep={np.linalg.norm(g['left']-g['right']):.4f}"
                  f"  mid={np.round((g['left']+g['right'])/2,4)}")

        solid_v = 0
        solid_t = 0
        shell = None
        for i, s in enumerate(mesh["subs"]):
            kind = "OUTLINE" if (s["flags"] & 1) else "solid"
            print(f"  sub{i} [{kind}] colour=#{int(s['col'][0]*255):02X}"
                  f"{int(s['col'][1]*255):02X}{int(s['col'][2]*255):02X}"
                  f" verts={len(s['pos'])} tris={len(s['tris'])}")
            if s["flags"] & 1:
                shell = s
            else:
                solid_v += len(s["pos"])
                solid_t += len(s["tris"])

        if shell is None:
            print("  NO SHELL")
            continue

        tris = shell["tris"]
        pos = shell["pos"]
        be = boundary_edges(tris)
        roots = components(len(pos), tris)
        uniq_roots, comp_sizes = np.unique(roots, return_counts=True)
        print(f"  shell: {len(tris)} tris, {len(pos)} verts, "
              f"{len(uniq_roots)} components, {len(be)} boundary edges")
        # boundary edges per component
        for r, size in zip(uniq_roots, comp_sizes):
            mask = roots == r
            ct = tris[mask[ tris[:, 0] ]]
            cb = boundary_edges(ct)
            if len(cb) == 0:
                continue
            mid = (pos[cb[:, 0]] + pos[cb[:, 1]]) * 0.5
            print(f"    comp {r}: {size:>6d} verts, {len(ct):>6d} tris, "
                  f"{len(cb):>5d} boundary edges  "
                  f"X[{mid[:,0].min():+.3f},{mid[:,0].max():+.3f}] "
                  f"Y[{mid[:,1].min():+.3f},{mid[:,1].max():+.3f}] "
                  f"Z[{mid[:,2].min():+.3f},{mid[:,2].max():+.3f}]")

        # Width profile of the SOLID geometry per height band.
        allpos = np.concatenate([s["pos"] for s in mesh["subs"] if not (s["flags"] & 1)])
        lo = allpos.min(axis=0)
        hi = allpos.max(axis=0)
        print(f"  solid bounds X[{lo[0]:+.3f},{hi[0]:+.3f}] Y[{lo[1]:+.3f},{hi[1]:+.3f}]"
              f" Z[{lo[2]:+.3f},{hi[2]:+.3f}]")
        print("  height profile (fraction, halfwidth X, halfdepth Z, min/max x):")
        n = 20
        for k in range(n):
            y0 = lo[1] + (hi[1] - lo[1]) * k / n
            y1 = lo[1] + (hi[1] - lo[1]) * (k + 1) / n
            band = allpos[(allpos[:, 1] >= y0) & (allpos[:, 1] < y1)]
            if len(band) == 0:
                continue
            print(f"    {k/n:.2f}-{(k+1)/n:.2f} y[{y0:+.3f},{y1:+.3f}] "
                  f"x[{band[:,0].min():+.3f},{band[:,0].max():+.3f}] "
                  f"halfw={(band[:,0].max()-band[:,0].min())/2:.3f} "
                  f"z[{band[:,2].min():+.3f},{band[:,2].max():+.3f}]")


if __name__ == "__main__":
    main()
