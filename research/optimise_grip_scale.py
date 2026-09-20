"""Can the hands actually touch? Optimise scale + shift together.

The two hand anchors are fixed by the game, 0.6034 apart and 0.073 apart vertically.
The mod may scale and shift the model. This searches (scale, dx, dy) for the placement
that puts both anchors closest to the plush surface, using exact point-to-mesh distance,
and reports the residual gap so the best physically-achievable grip is known.
"""
import os
import struct

import numpy as np
import trimesh

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")

ANCHOR_L = np.array([-0.3590, -0.1770, -0.0400])
ANCHOR_R = np.array([+0.2400, -0.1040, -0.0400])


def read_subs(path):
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
        v = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3).astype(np.float64); o += vc * 12
        o += vc * 12 + vc * 8 + vc * 12
        t = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3).astype(np.int64); o += ic * 4
        subs.append((flags, v, t))
    return subs


def main():
    for stem in ("miffy", "zichaoxiong"):
        subs = read_subs(os.path.join(ASSETS, stem + ".psmesh"))
        solid = [s for s in subs if not (s[0] & 1)]
        v = np.concatenate([s[1] for s in solid])
        t = []
        off = 0
        for s in solid:
            t.append(s[2] + off); off += len(s[1])
        t = np.concatenate(t)
        mesh = trimesh.Trimesh(vertices=v, faces=t, process=False)
        lo, hi = v.min(axis=0), v.max(axis=0)
        centre = (lo + hi) * 0.5

        print(f"===== {stem} =====")

        def score(scale, dx, dy, dz):
            pts = (v - centre) * scale + centre + np.array([dx, dy, dz])
            m = trimesh.Trimesh(vertices=pts, faces=t, process=False)
            hl = ANCHOR_L
            hr = ANCHOR_R
            pl, dl, _ = trimesh.proximity.closest_point(m, [hl, hr])
            d = np.array(dl)
            inside = m.contains([hl, hr])
            signed = np.where(inside, -d, d)
            return signed, float(np.abs(signed).sum())

        best = None
        for scale in np.arange(0.85, 1.36, 0.05):
            for dx in np.arange(-0.10, 0.11, 0.01):
                for dy in np.arange(-0.05, 0.36, 0.01):
                    signed, s = score(scale, dx, dy, 0.0)
                    if best is None or s < best[0]:
                        best = (s, scale, dx, dy, signed)
        print(f"  best: score={best[0]:.4f} scale={best[1]:.2f} dx={best[2]:+.3f} "
              f"dy={best[3]:+.3f}  gaps=({best[4][0]:+.4f},{best[4][1]:+.4f})")

        # refine around the best
        s0, sc0, dx0, dy0 = best[0], best[1], best[2], best[3]
        for scale in np.arange(sc0 - 0.04, sc0 + 0.041, 0.01):
            for dx in np.arange(dx0 - 0.01, dx0 + 0.011, 0.005):
                for dy in np.arange(dy0 - 0.01, dy0 + 0.011, 0.005):
                    signed, s = score(scale, dx, dy, 0.0)
                    if s < best[0]:
                        best = (s, scale, dx, dy, signed)
        print(f"  refined: score={best[0]:.4f} scale={best[1]:.3f} dx={best[2]:+.4f} "
              f"dy={best[3]:+.4f}  gaps=({best[4][0]:+.4f},{best[4][1]:+.4f})")

        # How does the current shipped setting compare?  The shipped grips are the
        # waist points; the runtime offset is anchorMid - gripMid.
        import json
        pass


if __name__ == "__main__":
    main()
