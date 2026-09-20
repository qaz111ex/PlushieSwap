"""Is the ink width ever reduced on a vertex that forms the silhouette?

The width map fades the ink to zero at the eyes/mouth/blush and on downward-facing
surfaces. That is correct for *interior* detail, but if a faded vertex also lies on the
silhouette, the outline thins or disappears there — the "broken line" the user sees.

For a set of camera angles this classifies every shell vertex as silhouette (the screen
normal points away from the view axis) or interior, and reports the ink width on the
silhouette ones. Any silhouette vertex with width well below 1 is a defect.
"""
import os
import struct
import sys

import numpy as np

ASSETS = r"D:\zhuanban\Plushie Swap\assets"


def read(path):
    with open(path, "rb") as fh:
        d = fh.read()
    o = 8
    n = struct.unpack_from("<i", d, o)[0]; o += 4 + n
    count = struct.unpack_from("<i", d, o)[0]; o += 4
    subs = []
    for _ in range(count):
        o += 16
        flags = struct.unpack_from("<i", d, o)[0]; o += 4
        vc, ic = struct.unpack_from("<ii", d, o); o += 8
        verts = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        normals = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3); o += vc * 12
        o += vc * 8 + vc * 12
        idx = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3); o += ic * 4
        subs.append((flags, verts, normals, idx))
    o += 24
    has = struct.unpack_from("<i", d, o)[0]; o += 4
    if has:
        o += 12 + 12 + 16 + 16
    wob = struct.unpack_from("<i", d, o)[0]; o += 4 + wob
    oc = struct.unpack_from("<i", d, o)[0]; o += 4
    widths = None
    if oc:
        o += oc * 4
        widths = np.frombuffer(d[o:o + oc], np.uint8).astype(float) / 255.0
        o += oc
    return subs, widths


def main():
    # camera directions: front, sides, back, and some in between
    dirs = []
    for yaw in range(0, 360, 30):
        a = np.radians(yaw)
        dirs.append(np.array([np.sin(a), 0.0, np.cos(a)]))
    # also from above and below
    dirs += [np.array([0, 1, 0.001]), np.array([0, -1, 0.001])]

    for stem in ("miffy", "zichaoxiong"):
        subs, widths = read(os.path.join(ASSETS, stem + ".psmesh"))
        shell = [(f, v, n, t) for f, v, n, t in subs if f & 1][0]
        _f, sv, sn, st = shell
        if widths is None:
            print(stem, "no widths")
            continue
        w = widths

        # A vertex is on the silhouette from a view direction when its normal is
        # perpendicular to the view ray (the dot product is near zero). Use the same
        # threshold the earlier measurement used: |screen normal| >= 0.35.
        sil_ever = np.zeros(len(sv), dtype=bool)
        thin_sil = np.zeros(len(sv), dtype=bool)
        for d in dirs:
            # screen-space normal magnitude for a head-on camera at this direction:
            # project the normal onto the plane perpendicular to the view ray
            n_dot = sn @ d
            perp = sn - n_dot[:, None] * d[None, :]
            mag = np.linalg.norm(perp, axis=1)
            sil = mag >= 0.35
            sil_ever |= sil
            thin_sil |= sil & (w < 0.6)

        print("=" * 70)
        print(f"{stem}: {len(sv)} shell verts")
        print(f"  silhouette from at least one of {len(dirs)} views: {int(sil_ever.sum())}")
        print(f"  ...of those, ink width < 0.6 (line thins/disappears): "
              f"{int(thin_sil.sum())}")
        if thin_sil.any():
            idx = np.flatnonzero(thin_sil)
            print(f"  their width values: min {w[idx].min():.2f} "
                  f"mean {w[idx].mean():.2f} max {w[idx].max():.2f}")
            # where are they? report Y as a fraction of the model height
            ys = sv[idx, 1]
            lo, hi = sv[:, 1].min(), sv[:, 1].max()
            frac = (ys - lo) / max(1e-9, hi - lo)
            print(f"  height fractions: min {frac.min():.2f} mean {frac.mean():.2f} "
                  f"max {frac.max():.2f}")
            # how many are fully zero
            print(f"  fully zero width on silhouette: {int((w[idx] <= 0).sum())}")
        else:
            print("  OK: no silhouette vertex is faded")


if __name__ == "__main__":
    main()
