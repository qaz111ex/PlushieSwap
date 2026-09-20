"""Build several ink-shell variants from the shipped body so Blender can compare them.

The shipped shell masks out a lot of the body: measured on Miffy, `down` (downward
facing) covers 26% of the vertices and `enclosed` (inside another shell) 9%, and half
of all faces are deleted. The arm tips survive as isolated islands, which is exactly
what a broken line at the shoulder looks like.

So this builds the same hull with progressively fewer masks, plus a completely
unmasked one, and exports each as an OBJ. Rendering them side by side answers the
only question that matters: does the plain inverted hull actually produce stray
interior lines, or is masking an over-correction?

Run:
    python research\outline_variants2.py
    blender.exe --background --factory-startup --python research\blender_variants2.py
"""
import os
import struct
import sys

import numpy as np

ROOT = r"D:\zhuanban\Plushie Swap"
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ROOT, "research", "blender")
sys.path.insert(0, os.path.join(ROOT, "tools"))

THICK = 0.0075 * 0.9635


def read(path):
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
        nn = np.frombuffer(d[o:o + vc * 12], "<f4").reshape(-1, 3).astype(np.float64); o += vc * 12
        o += vc * 8 + vc * 12
        t = np.frombuffer(d[o:o + ic * 4], "<i4").reshape(-1, 3).astype(np.int64); o += ic * 4
        subs.append((colour, flags, v, nn, t))
    return subs


def write_obj(path, groups):
    with open(path, "w", encoding="utf-8") as fh:
        base = 1
        for name, verts, tris in groups:
            fh.write(f"o {name}\n")
            for v in verts:
                fh.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
            for t in tris:
                fh.write(f"f {t[0]+base} {t[1]+base} {t[2]+base}\n")
            base += len(verts)


def main():
    import build_meshes as bm
    os.makedirs(OUT, exist_ok=True)

    for stem in ("miffy", "zichaoxiong"):
        subs = read(os.path.join(ASSETS, stem + ".psmesh"))
        solid = [s for s in subs if not (s[1] & 1)]

        bv = np.concatenate([s[2] for s in solid])
        bt = []
        off = 0
        for s in solid:
            bt.append(s[4] + off); off += len(s[2])
        bt = np.concatenate(bt)

        solid4 = [(s[0], s[2], s[3], s[4]) for s in solid]
        fd, suppress = bm.find_face_features(solid4, 0.045 * 0.9635)
        down = bm.downward_face_weight(solid4, 0.55)
        enclosed = bm.inside_other_shell(solid4, 0.030 * 0.9635)

        sv, st, on, origin = bm.build_outline_normals(bv, bt)

        centroid = sv.mean(axis=0)
        radial = sv - centroid
        radial /= np.linalg.norm(radial, axis=1, keepdims=True)
        blended = on + radial
        blended /= np.linalg.norm(blended, axis=1, keepdims=True)

        def export(tag, dirs, keep, shell_v=None):
            v = (sv if shell_v is None else shell_v) + dirs * THICK
            t = st[keep]
            used = np.unique(t)
            remap = np.full(len(v), -1, dtype=np.int64)
            remap[used] = np.arange(len(used))
            write_obj(os.path.join(OUT, f"var_{stem}_{tag}.obj"),
                      [("body", bv, bt), ("shell", v[used], remap[t])])
            print(f"{stem} {tag}: {len(t)} tris, {len(used)} verts")

        hidden = np.zeros(len(sv), dtype=bool)
        hidden[suppress[origin]] = True
        hidden[down[origin]] = True
        hidden[enclosed[origin]] = True
        hidden[fd[origin]] = True
        allfaces = np.ones(len(st), dtype=bool)

        # The per-vertex surface colour, so a measurement can tell a missing line on a
        # BRIGHT part of the plush (a real break) from one on a dark eye (which is its
        # own line already).
        bright = np.zeros(len(bv), dtype=bool)
        off = 0
        for (col, mv, nm, mt) in solid4:
            v_col = np.asarray(col, dtype=np.float64)[:3]
            bright[off:off + len(mv)] = v_col.mean() > 0.45
            off += len(mv)
        np.save(os.path.join(OUT, f"var_{stem}_bright.npy"), bright)

        export("current", blended, ~(hidden[st[:, 0]] | hidden[st[:, 1]] | hidden[st[:, 2]]))
        export("nomask_blend", blended, allfaces)
        export("nomask_normal", on, allfaces)
        only_face = np.zeros(len(sv), dtype=bool)
        only_face[suppress[origin]] = True
        only_face[fd[origin]] = True
        export("faceonly", blended, ~(only_face[st[:, 0]] | only_face[st[:, 1]] | only_face[st[:, 2]]))

        # Isolate `enclosed`: it is the one that can strand a whole limb, because a
        # vertex on an arm tip that pokes into the dress volume counts as "inside
        # another shell" and loses its ink even though the arm is plainly visible.
        no_enclosed = np.zeros(len(sv), dtype=bool)
        no_enclosed[suppress[origin]] = True
        no_enclosed[down[origin]] = True
        no_enclosed[fd[origin]] = True
        export("noenclosed", blended,
               ~(no_enclosed[st[:, 0]] | no_enclosed[st[:, 1]] | no_enclosed[st[:, 2]]))

        # and isolate `down` too, to confirm it is the one holding the hem together
        no_down = np.zeros(len(sv), dtype=bool)
        no_down[suppress[origin]] = True
        no_down[enclosed[origin]] = True
        no_down[fd[origin]] = True
        export("nodown", blended,
               ~(no_down[st[:, 0]] | no_down[st[:, 1]] | no_down[st[:, 2]]))

        # The masks' original intent, done the standard way: keep every face and scale
        # each vertex's push by a SMOOTH width in [0, 1]. The shell then sinks into the
        # body where there should be no ink instead of the topology being cut, so the
        # line cannot break at a mask boundary.
        #
        # `enclosed` is left out: a vertex on an arm tip that pokes into the dress
        # volume counts as "inside another shell" and loses its ink even though the arm
        # is plainly visible. Measured on the shipped model that one mask is what cut a
        # fifth of the silhouette away.
        fade = np.ones(len(sv), dtype=np.float64)
        fade[suppress[origin]] = 0.0
        fade[down[origin]] = 0.0
        fade[fd[origin]] = 0.0
        fade = bm.smooth_scalar_over_surface(len(sv), st, fade, 4, 0.5)
        fade[fd[origin]] = 0.0
        v = sv + blended * (THICK * fade)[:, None]
        write_obj(os.path.join(OUT, f"var_{stem}_smoothwidth.obj"),
                  [("body", bv, bt), ("shell", v, st)])
        print(f"{stem} smoothwidth: {len(st)} tris, {len(sv)} verts, "
              f"width<0.5 on {100.0*np.mean(fade < 0.5):.0f}% of verts")


if __name__ == "__main__":
    main()
