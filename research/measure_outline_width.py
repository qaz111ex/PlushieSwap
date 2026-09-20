"""Research-only: measure how uneven the current offline outline really is.

The shipped .psmesh carries an inverted-hull shell that the Python pipeline
extruded in OBJECT space along welded normals:

    shell_vertex = body_vertex + normal * (OUTLINE_THICKNESS * target_height)

Because that offset is a fixed object-space length, its size in PIXELS varies
with camera distance, field of view and the vertex's angle to the camera. This
script quantifies that spread and compares it with a screen-space
constant-width extrusion of the same shell (what a proper outline shader does in
the vertex shader, matching the industry formula).

Metric: for silhouette vertices (those whose normal is edge-on to the camera and
so actually form the line), the on-screen (pixel) distance between the
un-inflated surface point and the inflated outline point, for a perspective
camera at several distances. Reports mean, std and spread.

Writes research/outline_width_metrics.txt
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from preview_mesh import read_psmesh  # noqa: E402

ASSETS = r"D:\zhuanban\Plushie Swap\assets"
OUT = r"D:\zhuanban\Plushie Swap\research"

# convert() calls: outline_thickness=0.0075, target_height=0.9635
OUTLINE_THICKNESS = 0.0075 * 0.9635
LINES_PER_OBJECT = 15525

RES = (1920.0, 1080.0)
FOVY_DEG = 50.0
TARGET_PX = 2.0
SILHOUETTE_CUT = 0.35   # |clip normal.xy| above which a vertex is on the silhouette


def look_at(eye, target, up):
    fwd = target - eye
    fwd = fwd / np.linalg.norm(fwd)
    right = np.cross(fwd, up)
    right = right / np.linalg.norm(right)
    camup = np.cross(right, fwd)
    view = np.eye(4)
    view[0, :3] = right
    view[1, :3] = camup
    view[2, :3] = -fwd
    view[:3, 3] = -view[:3, :3] @ eye
    return view


def perspective(fovy_deg, aspect, near, far):
    f = 1.0 / np.tan(np.radians(fovy_deg) * 0.5)
    p = np.zeros((4, 4))
    p[0, 0] = f / aspect
    p[1, 1] = f
    p[2, 2] = (far + near) / (near - far)
    p[2, 3] = (2.0 * far * near) / (near - far)
    p[3, 2] = -1.0
    return p


def to_px(clip, size):
    w = np.maximum(clip[:, 3:4], 1e-6)
    ndc = clip[:, :3] / w
    px = np.empty((len(clip), 2))
    px[:, 0] = (ndc[:, 0] * 0.5 + 0.5) * (size[0] - 1)
    px[:, 1] = (1.0 - (ndc[:, 1] * 0.5 + 0.5)) * (size[1] - 1)
    return px


def project(points, centre, view, proj):
    p = np.concatenate([points - centre, np.ones((len(points), 1))], axis=1)
    return (proj @ (view @ p.T)).T


def stats(vals):
    if len(vals) == 0:
        return (0.0, 0.0, 0.0, 0.0)
    return (float(vals.mean()), float(vals.std()),
            float(np.percentile(vals, 5)), float(np.percentile(vals, 95)))


def main():
    lines = []
    for stem in ("miffy", "zichaoxiong"):
        name, subs, lo, hi = read_psmesh(os.path.join(ASSETS, stem + ".psmesh"))
        centre = (lo + hi) * 0.5

        shell_v, shell_n = [], []
        for e in subs:
            flags = e[5] if len(e) > 5 else 0
            if not (flags & 1):
                continue
            shell_v.append(e[1])
            shell_n.append(e[2])
        sv = np.concatenate(shell_v, axis=0).astype(np.float64)
        sn = np.concatenate(shell_n, axis=0).astype(np.float64)
        body = sv - sn * OUTLINE_THICKNESS

        lines.append(f"\n==== {stem}: {len(sv)} outline verts, "
                     f"baked object thickness {OUTLINE_THICKNESS:.5f} units, "
                     f"model size {np.round(hi - lo, 3)} ====")
        lines.append(f"{'dist':>5} | {'object-space px (mean +- std, p5..p95)':>42} "
                     f"| {'screen-space px @ {:.0f}px target':>38}".format(TARGET_PX))
        lines.append("-" * 92)

        for dist in (0.35, 0.5, 1.0, 2.0, 4.0, 8.0):
            eye = centre + np.array([0.20 * dist, 0.12 * dist, -dist])
            view = look_at(eye, centre, np.array([0.0, 1.0, 0.0]))
            proj = perspective(FOVY_DEG, RES[0] / RES[1], 0.03, 200.0)

            body_clip = project(body, centre, view, proj)
            shell_clip = project(sv, centre, view, proj)
            body_px = to_px(body_clip, RES)
            shell_px = to_px(shell_clip, RES)

            m = (proj @ view)[:3, :3]
            ncs = (m @ sn.T).T
            nl = np.linalg.norm(ncs[:, :2], axis=1)
            silhouette = nl >= SILHOUETTE_CUT

            cur = np.linalg.norm(shell_px - body_px, axis=1)[silhouette]

            # shader formula: clip.xy += normalize(clipNormal.xy)/_ScreenParams
            #                  * width_px * clip.w * 2
            ndir = ncs[:, :2] / np.maximum(nl[:, None], 1e-8)
            pdir = ndir * RES
            pdir = pdir / np.maximum(np.linalg.norm(pdir, axis=1, keepdims=True), 1e-8)
            ndc_off = pdir * (2.0 * TARGET_PX) / np.array(RES)
            prop_clip = shell_clip.copy()
            prop_clip[:, :2] += ndc_off * shell_clip[:, 3:4]
            prop_px = to_px(prop_clip, RES)
            prop = np.linalg.norm(prop_px - shell_px, axis=1)[silhouette]

            cm, cs, c5, c95 = stats(cur)
            pm, ps, p5, p95 = stats(prop)
            lines.append(f"{dist:5.2f} | {cm:8.2f} +- {cs:7.2f}  p5 {c5:6.2f}  "
                         f"p95 {c95:7.2f} | {pm:8.2f} +- {ps:7.2f}  "
                         f"p5 {p5:6.2f}  p95 {p95:7.2f}")

        lines.append(f"  silhouette verts (|clipNormal.xy|>={SILHOUETTE_CUT}): "
                     f"{int(silhouette.sum())} of {len(sv)}")
        lines.append(f"  NOTE: object-space widths scale linearly with the object's "
                     f"localScale too; the game shrinks backpack items to 0.5.")

    text = "\n".join(lines)
    with open(os.path.join(OUT, "outline_width_metrics.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
