"""Pick the radial/normal blend weight objectively, then stop.

The runtime extrudes the shell along its stored direction. A pure surface normal
crosses concave grooves and lands inside the body (spurious ink); a pure radial
direction never self-intersects but does not follow the surface. The direction is
therefore blended:

    dir = normalize(normal + k * radial)

and `k` is chosen as the smallest value that removes essentially all vertices whose
pushed position lands inside the body — no rendering guesswork, just a geometric count.
"""
import os
import sys

import numpy as np

sys.path.insert(0, r"D:\zhuanban\Plushie Swap\tools")
import build_meshes as bm  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
THICK = 0.0075 * 0.9635
KS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0)


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
        v = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        nn = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        o += vc * 8 + vc * 12
        t = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3); o += ic * 4
        subs.append((colour, flags, v, nn, t))
    return subs


def main():
    for stem in ("miffy", "zichaoxiong"):
        subs = read(os.path.join(ASSETS, stem + ".psmesh"))
        solid = [s for s in subs if not (s[1] & 1)]
        bv = np.concatenate([s[2] for s in solid])
        bt = []; off = 0
        for s in solid:
            bt.append(s[4] + off); off += len(s[2])
        bt = np.concatenate(bt)

        sv, st, on, origin = bm.build_outline_normals(bv, bt)
        centroid = sv.mean(axis=0)
        radial = sv - centroid
        radial /= np.linalg.norm(radial, axis=1, keepdims=True)

        print("=" * 64)
        print(f"{stem}: {len(sv)} shell verts, thickness {THICK:.5f}")
        for k in KS:
            d = on + k * radial
            d /= np.linalg.norm(d, axis=1, keepdims=True)
            pushed = sv + d * THICK
            # a vertex is "leaked" if its pushed position is inside the body
            inside = bm.pushed_inside_body(
                [(None, s[2], None, s[4]) for s in solid], pushed, 0.030 * 0.9635)
            # also measure how much the direction deviates from the true normal
            dev = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", d, on), -1, 1)))
            print(f"  k={k:>4}: leaked {int(inside.sum()):>5} / {len(sv)}   "
                  f"mean angle from normal {dev.mean():5.1f}deg  p95 {np.percentile(dev,95):5.1f}deg")


if __name__ == "__main__":
    main()
