using UnityEngine;

namespace PlushieSwap
{
    /// <summary>
    /// Gives the ink shell a constant screen-space width.
    ///
    /// The line used to be a fixed length in object space: the Python pipeline pushed every
    /// shell vertex out along its normal by a constant world distance. That distance is what
    /// was wrong — measured on this model it occupies 37 px at arm's length and 0.77 px from
    /// across the room, a 48-fold swing, and even at one distance the same amount of push
    /// differs roughly threefold between vertices depending on how edge-on they are. That is
    /// the "uneven and broken" look.
    ///
    /// The cure is to extrude in screen space instead, which is what an outline shader does in
    /// its vertex stage:
    ///
    ///     positionCS.xy += normalize(normalCS.xy) / _ScreenParams.xy
    ///                      * (widthPx * 2) * positionCS.w
    ///
    /// `* positionCS.w` cancels the perspective divide (so distance stops mattering) and
    /// `/ _ScreenParams.xy` converts pixels to NDC (so resolution stops mattering).
    ///
    /// A custom shader would do this on the GPU, but building one needs the Unity editor to
    /// compile it, and this project has no editor available. The same arithmetic is therefore
    /// done here, once per frame, on the shell's vertices. The shell is small (about 15k
    /// vertices) and each vertex only needs two matrix multiplies, and the result is
    /// identical because the shader and this code evaluate the same formula.
    ///
    /// The first step is to recover the surface the shell was inflated from, by subtracting
    /// exactly the push that was baked in (<see cref="PsMeshReader.Asset.BakedOutlineThickness"/>).
    /// That recovery is exact — it lands back on the body vertex to float precision — so
    /// nothing here is an approximation of the model's shape, only of the GPU doing the work.
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

        /// <summary>Scratch the deformed vertices are written into.</summary>
        private Vector3[] _buffer;

        /// <summary>
        /// The shell's bounds before any per-frame extrusion, so the padding can be
        /// recomputed each frame from the offset that was actually applied instead of
        /// relying on a fixed guess.
        /// </summary>
        private Bounds _baseBounds;

        private Mesh _mesh;
        private Renderer _renderer;
        private Camera _camera;
        private float _widthPixels;
        private float _nextCameraSearch;

        /// <summary>
        /// Attaches the driver to the outline object and recovers the body surface.
        ///
        /// Returns null when there is nothing to do, which keeps the caller's code simple:
        /// an older .psmesh without a recorded thickness, or a model with no outline at all,
        /// simply behaves as before.
        /// </summary>
        internal static PlushieOutline Attach(GameObject host, Mesh mesh, Renderer renderer,
                                              float bakedThickness, float[] widths,
                                              float widthPixels)
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
            driver._renderer = renderer;
            driver._surface = surface;
            driver._normal = normals;
            driver._width = widths;
            driver._buffer = new Vector3[count];
            driver._widthPixels = widthPixels;

            // The vertices change every frame, so tell Unity not to keep a static copy.
            // Called before the first per-frame write rather than after: Unity's docs say
            // the hint applies the next time the vertex buffers are (re)created, so
            // marking after the data has already been uploaded could miss the one upload
            // that matters.
            mesh.MarkDynamic();

            // The per-frame screen-space extrusion moves vertices outward in world space,
            // which can push the outermost ink past the baked bounds; Unity would then cull
            // the shell when the plush sits near the edge of the screen. A fixed pad cannot
            // be right, because the push grows with distance (a constant pixel width is a
            // LARGER world distance the further away the camera is): the old 0.05 pad held
            // up to roughly 9 m at the default settings and failed beyond that, and at
            // World Scale 0.3 with a 12 px line it failed past ~1.2 m. So the original
            // bounds are remembered here and re-padded every frame in LateUpdate by the
            // largest offset actually applied, which is exact at any distance and scale.
            driver._baseBounds = mesh.bounds;
            Bounds bounds = mesh.bounds;
            bounds.Expand(0.05f);
            mesh.bounds = bounds;

            return driver;
        }

        /// <summary>Width in screen pixels; 0 hides the line.</summary>
        internal float WidthPixels
        {
            get { return _widthPixels; }
            set { _widthPixels = value; }
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

        private void LateUpdate()
        {
            if (_mesh == null || _surface == null || _buffer == null)
            {
                return;
            }

            // A shell nobody can see costs nothing, which matters for dropped or distant
            // plushies.
            if (_renderer != null && !_renderer.isVisible)
            {
                return;
            }

            Camera camera = ResolveCamera();
            if (camera == null)
            {
                return;
            }

            // Screen height is taken from the display rather than the render target, so a
            // reduced render scale (the game allows 0.2..1.0) still yields the same number
            // of pixels on screen: the target is upscaled afterwards, and dividing by the
            // render height instead would make the line grow as the scale drops.
            float screenHeight = Screen.height;
            if (screenHeight < 2f)
            {
                return;
            }

            // Model -> camera -> model, in one pair of matrices for the whole mesh.
            Matrix4x4 modelToCamera = camera.worldToCameraMatrix * transform.localToWorldMatrix;
            Matrix4x4 cameraToModel = modelToCamera.inverse;

            // World units per pixel at one unit of depth. For a perspective camera a pixel
            // subtends 2*tan(fov/2)/height at unit distance. An orthographic camera has no
            // perspective: its vertical view is exactly `2 * orthographicSize` world units
            // tall, stretched over the screen's height in pixels, so a pixel is
            // `2 * size / screenHeight` across at EVERY depth. (The previous
            // `1 / (2 * size)` was dimensionally wrong — it is world units per pixel only
            // when the screen is one unit tall — and would have made the line 2.7x to 90x
            // too thick. It is unreachable today because the game's cameras are all
            // perspective, but it is fixed rather than left as a trap.)
            float perPixel;
            if (camera.orthographic)
            {
                perPixel = 2f * Mathf.Max(1e-4f, camera.orthographicSize) / screenHeight;
            }
            else
            {
                float tanHalfFov = Mathf.Tan(camera.fieldOfView * 0.5f * Mathf.Deg2Rad);
                perPixel = (2f * tanHalfFov) / screenHeight;
            }

            float width = _widthPixels;
            int count = _surface.Length;

            // The largest world-space push applied to any vertex this frame. It is used to
            // pad the mesh bounds below, so it must be the largest, not the last.
            float maxOffset = 0f;

            for (int i = 0; i < count; i++)
            {
                Vector3 point = modelToCamera.MultiplyPoint3x4(_surface[i]);
                Vector3 normal = modelToCamera.MultiplyVector(_normal[i]);

                // Per-vertex ink width. A vertex the pipeline tucked inside the body
                // (an eye, the mouth, a blush, a downward-facing surface) carries 0 or
                // less and is pushed the other way, so the body's own depth hides it.
                // The hull is never cut, so the silhouette line stays continuous.
                float ink = _width != null ? _width[i] : 1f;
                if (ink <= 0f)
                {
                    // No ink here: the vertex was baked onto the body surface, and the
                    // shell is front-face culled, so the body simply hides it.
                    _buffer[i] = _surface[i];
                    continue;
                }

                // Screen-space direction of the normal.
                //
                // The perspective matrix scales x by 1/aspect but a pixel is already
                // narrower than it is tall by that same factor, so the two cancel: a
                // camera-space direction (nx, ny) moves the point by the same number of
                // pixels per unit along both axes. The direction is therefore just
                // (nx, ny), with no aspect term. (An earlier version of this comment said
                // adding one would "tilt" the offset; that is not what happens — it scales
                // the length uniformly. The conclusion holds either way, but the reason
                // is the cancellation, not tilting.)
                float dx = normal.x;
                float dy = normal.y;
                float length = Mathf.Sqrt(dx * dx + dy * dy);
                if (length > 1e-8f)
                {
                    dx /= length;
                    dy /= length;
                }
                else
                {
                    // Dead-on to the camera, so there is no silhouette to widen. Leaving it
                    // at zero also keeps the maths away from a division by nothing.
                    dx = 0f;
                    dy = 0f;
                }

                // One pixel at this depth, times the wanted width, times this vertex's
                // share of it.
                float scale = perPixel * width * ink;
                if (!camera.orthographic)
                {
                    float depth = -point.z;
                    if (depth < 0f)
                    {
                        depth = 0f;
                    }
                    scale *= depth;
                }

                if (scale > maxOffset)
                {
                    maxOffset = scale;
                }

                Vector3 offsetInCamera = new Vector3(dx * scale, dy * scale, 0f);
                _buffer[i] = _surface[i] + cameraToModel.MultiplyVector(offsetInCamera);
            }

            _mesh.vertices = _buffer;

            // Re-pad the bounds from the offset just applied. The mesh is drawn with the
            // same transform this method measured, so the world-space push is `maxOffset`
            // in every direction (the extrusion is radial in the screen plane); a small
            // epsilon covers the vertex the extrusion moved furthest and float error.
            Bounds bounds = _baseBounds;
            bounds.Expand(maxOffset * 2f + 0.01f);
            _mesh.bounds = bounds;
        }

        private Camera ResolveCamera()
        {
            if (_camera != null && _camera.isActiveAndEnabled)
            {
                return _camera;
            }

            // Reaching here means the cached camera is gone or disabled, so there is
            // nothing usable to hand back: returning it (as this used to) let the caller
            // run a whole frame of extrusion against a disabled camera. Between searches
            // the answer is simply "no camera"; the caller already treats null as "skip
            // this frame", and the shell keeps the geometry it had.
            if (Time.unscaledTime < _nextCameraSearch)
            {
                return null;
            }
            _nextCameraSearch = Time.unscaledTime + 1f;

            // The gameplay camera. `Camera.main` needs the MainCamera tag, which this game
            // does set, but a miss should not disable the outline, so any active camera with
            // the highest depth is taken as a fallback.
            Camera best = Camera.main;
            if (best != null && best.isActiveAndEnabled)
            {
                _camera = best;
                return _camera;
            }

            best = null;
            Camera[] all = Camera.allCameras;
            float bestDepth = float.NegativeInfinity;
            for (int i = 0; i < all.Length; i++)
            {
                Camera candidate = all[i];
                if (candidate == null || !candidate.isActiveAndEnabled)
                {
                    continue;
                }
                if (candidate.depth > bestDepth)
                {
                    bestDepth = candidate.depth;
                    best = candidate;
                }
            }
            _camera = best;
            return _camera;
        }
    }
}
