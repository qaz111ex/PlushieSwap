"""Signed-distance (inside/outside) test for mesh points, using trimesh.

`trimesh.proximity.closest_point` gives the nearest surface point and the index of the
face it lies on; the sign of (point - closest) . face_normal says which side of the
surface the point is on. This is a robust, well-tested implementation, unlike a
hand-rolled ray cast.
"""
import numpy as np
import trimesh


def side_of_surface(mesh, points):
    """+1 outside, -1 inside, for each point. Returns (sign, distance)."""
    pts = np.asarray(points, dtype=np.float64)
    closest, dist, fid = trimesh.proximity.closest_point(mesh, pts)
    normals = mesh.face_normals[fid]
    sign = np.sign(np.einsum("ij,ij->i", pts - closest, normals))
    sign[sign == 0] = 1.0
    return sign, dist


if __name__ == "__main__":
    sphere = trimesh.creation.icosphere(radius=1.0)
    test = np.array([[0.0, 0.0, 0.5], [0.0, 0.0, 1.5], [2.0, 0.0, 0.0]])
    sign, dist = side_of_surface(sphere, test)
    for p, d, s in zip(test, dist, sign):
        print(f"point {p}  dist {d:.3f}  sign {s:+.0f} -> {'inside' if s < 0 else 'outside'}")
