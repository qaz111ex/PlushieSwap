using UnityEngine;

namespace PlushieSwap
{
    /// <summary>
    /// Sets the ink shell's thickness as a property of the model, not of the screen.
    ///
    /// The shell ships as `body + normal * bakedThickness * width`, i.e. already pushed out
    /// by a fixed distance in the model's own space. That is the behaviour an outline should
    /// have: the line belongs to the plush, so it shrinks with the plush as it moves away,
    /// grows with it as it comes closer, and follows `World Scale` for free.
    ///
    /// An earlier version re-extruded the shell every frame in screen space, holding the line
    /// at a constant number of pixels at any distance (`scale *= depth`, the `positionCS.w`
    /// trick an outline shader uses). For a plush that is visibly wrong in one direction: the
    /// plush shrinks with distance while the line does not, so a plush across the room ends up
    /// wearing a proportionally far fatter outline than the one in your hands. It also cost a
    /// full rewrite of roughly 15k vertices per instance per frame, which is measurable with a
    /// dozen plushies in the scene.
    ///
    /// The extrusion is therefore done here, once, in the model's own space, and the shell is
    /// then left alone: nothing runs per frame at all. The config value only scales the baked
    /// thickness.
    ///
    /// The body surface the shell was inflated from is recovered by subtracting exactly the
    /// push that was baked in (<see cref="PsMeshReader.Asset.BakedOutlineThickness"/>), so the
    /// extrusion can be recomputed for any width without accumulating error.
    /// </summary>
    internal sealed class PlushieOutline : MonoBehaviour
    {
        /// <summary>Local positions with the baked push removed: the real surface.</summary>
        private Vector3[] _surface;

        /// <summary>The shell's own normals; the extrusion direction.</summary>
        private Vector3[] _normal;

        /// <summary>
        /// Per-vertex ink width. +1 is a full outward line; 0 means the vertex sits on
        /// the body (the eyes, mouth, blush and downward-facing surfaces) and draws no
        /// ink. The whole shell is still one closed surface, which is what keeps the
        /// silhouette line unbroken.
        /// </summary>
        private float[] _width;

        /// <summary>Scratch the extruded vertices are written into.</summary>
        private Vector3[] _buffer;

        /// <summary>
        /// The shell's bounds before the extrusion applied here, so the padding can be
        /// recomputed from the offset actually used instead of a fixed guess.
        /// </summary>
        private Bounds _baseBounds;

        private Mesh _mesh;

        /// <summary>The push that is baked into the shipped shell, in local units.</summary>
        private float _bakedThickness;

        private float _widthPixels;

        /// <summary>
        /// Attaches the driver to the outline object and recovers the body surface.
        ///
        /// Returns null when there is nothing to do, which keeps the caller's code simple:
        /// an older .psmesh without a recorded thickness, or a model with no outline at all,
        /// simply behaves as before.
        /// </summary>
        internal static PlushieOutline Attach(GameObject host, Mesh mesh, float bakedThickness,
                                              float[] widths, float widthPixels)
        {
            if (host == null || mesh == null || bakedThickness <= 0f || widthPixels <= 0f)
            {
                return null;
            }

            Vector3[] verts = mesh.vertices;
            Vector3[] normals = mesh.normals;
            if (verts.Length == 0 || normals.Length != verts.Length)
            {
                return null;
            }

            int count = verts.Length;
            if (widths != null && widths.Length != count)
            {
                DiagnosticLog.Warn("Outline width count " + widths.Length
                                  + " does not match the shell's " + count
                                  + " vertices; using a uniform line.");
                widths = null;
            }

            // Recover the true body surface by subtracting exactly the push that was
            // baked in. The shell is `surface + normal * thickness * width`, so removing
            // `normal * thickness * width` lands back on the body.
            //
            // The recovery is exact for every vertex whose width is 0 or 1, because those
            // pushes are `0` and `thickness` and both are representable. Vertices in
            // between carry a width that was quantised to a byte on the way into the file
            // (`build_meshes.py` writes `round(width * 255)`), so the subtraction can miss
            // by up to half a quantisation step: measured max residual is 1.39e-05 on
            // miffy and 1.37e-05 on zichaoxiong, matching the predicted bound of
            // `thickness / 510` = 1.42e-05 exactly. That is about 0.014 mm on a 96 cm
            // model, i.e. far below a pixel, so it does not matter visually — but the
            // earlier claim of "mean and max error 0.00000" was wrong, and the script it
            // cited no longer reproduces it. Do not restate it.
            //
            // The shipped files DO carry the per-vertex width table: the runtime log
            // reports "15525 widths" for miffy and "16831 widths" for zichaoxiong, and the
            // width is what marks the vertices that draw no ink (4993 and 12423 of them
            // are 0 respectively). So this is the live path, not a fallback — the
            // `widths == null` branch below only covers a file written before the table
            // existed, where every shell vertex is a full outward line.
            Vector3[] surface = new Vector3[count];
            for (int i = 0; i < count; i++)
            {
                float w = widths != null ? widths[i] : 1f;
                surface[i] = verts[i] - normals[i] * (bakedThickness * w);
            }

            PlushieOutline driver = host.AddComponent<PlushieOutline>();
            driver._mesh = mesh;
            driver._surface = surface;
            driver._normal = normals;
            driver._width = widths;
            driver._buffer = new Vector3[count];
            driver._bakedThickness = bakedThickness;
            driver._widthPixels = widthPixels;

            // The vertices change whenever the width setting does, so tell Unity not to
            // keep a static copy. Called before the first write rather than after: the
            // hint applies the next time the vertex buffers are (re)created, so marking
            // after the data has already been uploaded could miss that upload.
            mesh.MarkDynamic();

            driver._baseBounds = mesh.bounds;
            driver.Extrude();

            return driver;
        }

        /// <summary>Width multiplier for the line; 0 hides it.</summary>
        internal float WidthPixels
        {
            get { return _widthPixels; }
            set
            {
                if (Mathf.Approximately(_widthPixels, value))
                {
                    return;
                }
                _widthPixels = value;
                if (_mesh == null)
                {
                    return;
                }

                // A width of 0 means "no line". Collapsing the shell onto the body would
                // leave two coincident surfaces fighting over the same depth, so the outline
                // object is switched off instead. `SetWidthOnAll` still finds it — the search
                // is done with `includeInactive: true` — so a later non-zero width turns it
                // back on.
                bool on = value > 0f;
                if (gameObject.activeSelf != on)
                {
                    gameObject.SetActive(on);
                }
                if (on)
                {
                    Extrude();
                }
            }
        }

        /// <summary>
        /// Rebuilds the shell's vertices for the current width.
        ///
        /// Runs on attach and whenever the config changes — never per frame. The offset is
        /// `normal * bakedThickness * ink * (width / reference)`, in the model's own space,
        /// so the result is independent of the camera, the distance and the resolution.
        /// </summary>
        private void Extrude()
        {
            if (_mesh == null || _surface == null || _normal == null || _buffer == null)
            {
                return;
            }

            float scale = _bakedThickness * (_widthPixels / Plugin.DefaultOutlinePixels);
            int count = _surface.Length;
            float maxOffset = 0f;

            for (int i = 0; i < count; i++)
            {
                // Per-vertex ink width. A vertex the pipeline tucked inside the body
                // (an eye, the mouth, a blush, a downward-facing surface) carries 0 or
                // less and is left exactly on the body surface, so the body's own depth
                // hides it. The hull is never cut, so the silhouette line stays
                // continuous.
                float ink = _width != null ? _width[i] : 1f;
                if (ink <= 0f)
                {
                    _buffer[i] = _surface[i];
                    continue;
                }

                float push = scale * ink;
                if (push > maxOffset)
                {
                    maxOffset = push;
                }
                _buffer[i] = _surface[i] + _normal[i] * push;
            }

            _mesh.vertices = _buffer;

            // The extrusion moves vertices outward in the model's own space, which can push
            // the outermost ink past the baked bounds; Unity would then cull the shell when
            // the plush sits near the edge of the screen. The padding is recomputed from the
            // largest push actually applied rather than guessed, so it is right at any width
            // and any World Scale (the scale is part of the transform, so it needs no term
            // here).
            Bounds bounds = _baseBounds;
            bounds.Expand(maxOffset * 2f + 0.01f);
            _mesh.bounds = bounds;
        }

        /// <summary>
        /// Destroys the per-instance mesh. Unity never garbage-collects meshes, so a
        /// rebuilt plush would otherwise leave its old copy behind on every switch.
        /// </summary>
        internal void ReleaseMesh()
        {
            if (_mesh != null)
            {
                UnityEngine.Object.Destroy(_mesh);
                _mesh = null;
            }
            _surface = null;
            _normal = null;
            _width = null;
            _buffer = null;
        }

        /// <summary>
        /// The mesh is a per-instance copy created by this component's owner, so it must
        /// die with the component. This covers the game destroying the item itself
        /// (pickup, throw, consume, scene unload), where `DestroyReplacement` never runs
        /// and the mesh would otherwise leak.
        /// </summary>
        private void OnDestroy()
        {
            ReleaseMesh();
        }

        /// <summary>Pushes a new width to every live outline, for the config entry.</summary>
        internal static void SetWidthOnAll(float widthPixels)
        {
            // `FindObjectsOfType` skips inactive objects, so a plush hidden in a backpack
            // would keep the old width. `true` includes them.
            PlushieOutline[] all =
                UnityEngine.Object.FindObjectsOfType<PlushieOutline>(true);
            for (int i = 0; i < all.Length; i++)
            {
                if (all[i] != null)
                {
                    all[i].WidthPixels = widthPixels;
                }
            }
        }
    }
}
