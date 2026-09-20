"""Exact grip check with trimesh: is each hand anchor on, inside, or off the plush?

The sampled-distance approach gave two different answers, so this uses exact
point-to-mesh proximity plus an inside/outside test. That removes the sampling error
and settles where the grip should be.
"""
import os
import struct

import numpy as np
import trimesh

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")

ANCHOR_L = np.array([-0.3590, -0.1770, -0.0400])
ANCHOR_R = np.array([+0.2400, -0.1040, -0.0400])
ANCHOR_MID = (ANCHOR_L + ANCHOR_R) * 0.5


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
        height = hi[1] - lo[1]
        print(f"===== {stem} =====  watertight={mesh.is_watertight}")

        def report(frac, ddx=0.0):
            y_grip = lo[1] + frac * height
            band = v[np.abs(v[:, 1] - y_grip) < height * 0.02]
            mid_x = (band[:, 0].min() + band[:, 0].max()) * 0.5
            shift = np.array([ANCHOR_MID[0] - mid_x + ddx, ANCHOR_MID[1] - y_grip, 0.0])
            hl = ANCHOR_L - shift
            hr = ANCHOR_R - shift
            pl, dl, _ = trimesh.proximity.closest_point(mesh, [hl])
            pr, dr, _ = trimesh.proximity.closest_point(mesh, [hr])
            inside_l = mesh.contains([hl])[0]
            inside_r = mesh.contains([hr])[0]
            gl = -dl[0] if inside_l else dl[0]
            gr = -dr[0] if inside_r else dr[0]
            return shift, gl, gr

        best = None
        print("  frac  shiftX   shiftY   gapL     gapR    sum    verdict")
        for k in range(6, 62):
            frac = k / 100.0
            shift, gl, gr = report(frac)
            verdict = "AIR" if min(gl, gr) > 0.025 else (
                "inside" if max(gl, gr) < -0.05 else "contact")
            print(f"  {frac:.2f}  {shift[0]:+.4f}  {shift[1]:+.4f}  {gl:+.4f}  {gr:+.4f}  "
                  f"{abs(gl)+abs(gr):.4f}  {verdict}")
            if best is None or abs(gl) + abs(gr) < best[0]:
                best = (abs(gl) + abs(gr), frac, shift, gl, gr)
        print(f"  BEST frac={best[1]:.2f} shift={np.round(best[2],4)} "
              f"gaps=({best[3]:+.4f},{best[4]:+.4f})")


if __name__ == "__main__":
    main()
