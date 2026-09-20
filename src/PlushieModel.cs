using System;
using System.Collections.Generic;
using BepInEx.Configuration;
using UnityEngine;
using UnityEngine.Rendering;
using Zorro.Core;

namespace PlushieSwap
{
    /// <summary>
    /// State that belongs to the item rather than to one built model, so it survives the
    /// visual root being destroyed and rebuilt (a variant switch destroys every root).
    ///
    /// The game hides a plush that is in a worn backpack via `Item.HideRenderers`, and a
    /// hard refresh throws the root away, so the flag has to live on the item.
    /// </summary>
    internal sealed class PlushieItemState : MonoBehaviour
    {
        public bool HiddenByGameRule;

        /// <summary>
        /// The visual root this item currently owns, so the per-frame sweep does not have
        /// to search the item's whole subtree for its marker every frame.
        ///
        /// `FindVisualRoot` has to walk every descendant (the root hangs off `Holder`, and
        /// a direct `transform.Find` could match a root that is already queued for
        /// destruction), which allocates a marker array per call. That is the right
        /// lookup when something may have changed, but doing it every frame for every
        /// plush is pure waste. This is a cache, not the source of truth: it is only
        /// trusted while the marker is alive and not being destroyed, and any miss falls
        /// straight back to `FindVisualRoot`.
        /// </summary>
        public PlushieVisualMarker Visual;
    }

    /// <summary>Marker on the replacement visual root.</summary>
    internal sealed class PlushieVisualMarker : MonoBehaviour
    {
        public PlushieVariant Variant;
        public bool VanillaRenderersHidden;
        public ItemState LastState = (ItemState)(-1);
        public float LastScale = -1f;

        /// <summary>
        /// The body renderer this marker's root owns. The cook tint is written to this
        /// one renderer only: the outline shell shares the root but must stay flat ink,
        /// whatever the plush's cook state is.
        /// </summary>
        public MeshRenderer BodyRenderer;

        /// <summary>
        /// The cook amount the property block was last written for. `int.MinValue` so the
        /// first application always happens even for an uncooked plush.
        /// </summary>
        public int LastCook = int.MinValue;

        /// <summary>
        /// Reused property block. Allocated once with the marker so a cook step does not
        /// produce garbage every time the plush browns.
        /// </summary>
        public MaterialPropertyBlock CookBlock;

        /// <summary>
        /// Set just before the root is destroyed. `Object.Destroy` is deferred to the end
        /// of the frame, so without this a lookup later in the same frame would find the
        /// doomed root, treat it as live, and skip rebuilding.
        /// </summary>
        public bool Destroying;
    }

    /// <summary>
    /// Owns everything about the runtime replacement: loading .psmesh data, building the
    /// replacement renderer, matching the item's transform per state, and hiding the
    /// vanilla renderers while the replacement is active.
    /// </summary>
    internal static class PlushieModel
    {
        private const string VisualRootName = "PlushieSwap_Visual";
        private const int VisibleLayer = 0;

        /// <summary>How often the item registry is re-scanned when nothing is tracked yet.</summary>
        private const float RescanInterval = 0.5f;

        private static readonly Dictionary<PlushieVariant, PsMeshReader.Asset> LoadedAssets =
            new Dictionary<PlushieVariant, PsMeshReader.Asset>();
        private static readonly Dictionary<PlushieVariant, Mesh> CachedMeshes =
            new Dictionary<PlushieVariant, Mesh>();
        private static readonly Dictionary<PlushieVariant, Mesh> CachedOutlines =
            new Dictionary<PlushieVariant, Mesh>();
        private static readonly Dictionary<PlushieVariant, Material> CachedMaterials =
            new Dictionary<PlushieVariant, Material>();
        private static readonly Dictionary<PlushieVariant, Material> CachedOutlineMaterials =
            new Dictionary<PlushieVariant, Material>();
        private static readonly Dictionary<PlushieVariant, Texture2D> CachedTextures =
            new Dictionary<PlushieVariant, Texture2D>();
        private static readonly HashSet<PlushieVariant> MissingTextures =
            new HashSet<PlushieVariant>();
        private static readonly List<Item> TrackedItems = new List<Item>();

        private static bool _refreshRequested;
        private static bool _hardRefresh;
        private static float _nextRescan;
        private static PlushieVariant _lastVariant = PlushieVariant.Vanilla;

        // ------------------------------------------------------------------ public
        internal static void RequestRefreshAll(bool hard = false)
        {
            _refreshRequested = true;
            _hardRefresh |= hard;
        }

        /// <summary>
        /// Forget every remembered load failure.
        ///
        /// `FailedLoads` and `MissingTextures` exist so a file that cannot be read is not
        /// retried on every single frame. Without them one transient read error (a file
        /// still being written, a disk hiccup, a loose file dropped in mid-session) would
        /// mean a request to the filesystem per frame forever.
        ///
        /// The catch is that they are one-way: nothing in the normal flow ever clears
        /// them, so a variant that failed once stayed dead for the rest of the session and
        /// the only cure was restarting the game. A hard refresh is exactly the moment the
        /// user is asking for things to be re-read (F7, a config change, the outline
        /// coming back on), so it is the right place to give a failed variant another
        /// chance. The cost of a retry is one failed read; the cost of not retrying is a
        /// permanently missing model.
        /// </summary>
        internal static void ResetLoadFailures()
        {
            if (FailedLoads.Count == 0 && MissingTextures.Count == 0)
            {
                return;
            }
            FailedLoads.Clear();
            MissingTextures.Clear();
            DiagnosticLog.Diag("Cleared the remembered load failures; retrying on the next build.");
        }

        internal static void Tick()
        {
            if (!Plugin.ConfigLoaded)
            {
                return;
            }

            if (Plugin.ActiveVariant != _lastVariant)
            {
                _lastVariant = Plugin.ActiveVariant;
                _refreshRequested = true;
                _hardRefresh = true;
            }

            if (_refreshRequested)
            {
                _refreshRequested = false;
                bool hard = _hardRefresh;
                _hardRefresh = false;
                if (hard)
                {
                    // A hard refresh is the user explicitly asking for everything to be
                    // re-read, so a variant that failed to load earlier gets another try
                    // rather than staying dead until the game restarts.
                    ResetLoadFailures();
                }
                RefreshAll(hard);
            }

            MaintainTrackedItems();
        }

        // ------------------------------------------------------------------ loading
        /// <summary>
        /// A failed load is remembered so it is not retried every frame, but only until
        /// the next successful one: a null entry must never be treated as "loaded". (An
        /// earlier version cached null and then returned it forever, so one transient
        /// read failure permanently disabled a variant — no model, and therefore no hand
        /// anchors written, which is how the hands ended up back at the vanilla spot.)
        /// </summary>
        private static readonly HashSet<PlushieVariant> FailedLoads =
            new HashSet<PlushieVariant>();

        internal static PsMeshReader.Asset GetAsset(PlushieVariant variant)
        {
            if (variant == PlushieVariant.Vanilla)
            {
                return null;
            }

            PsMeshReader.Asset asset;
            if (LoadedAssets.TryGetValue(variant, out asset) && asset != null)
            {
                return asset;
            }
            if (FailedLoads.Contains(variant))
            {
                return null;
            }

            VariantDefinition def = Variants.Get(variant);
            AssetProvider.Source source;
            byte[] bytes = AssetProvider.Read(def.MeshFile, out source);
            if (bytes == null)
            {
                DiagnosticLog.Error("Model data missing: " + def.MeshFile);
                FailedLoads.Add(variant);
                return null;
            }

            asset = TryParseAsset(def.MeshFile, bytes, source);

            // A loose file that reads fine but does not parse (truncated copy, an
            // interrupted download, a hand-edited model) must not disable the variant
            // for the rest of the session: `FailedLoads` is never cleared on its own,
            // and the embedded copy in the DLL is unaffected by whatever is wrong with
            // the file on disk. Retry it, and only give up if that also fails.
            if (asset == null && source == AssetProvider.Source.LooseFile)
            {
                byte[] embedded = AssetProvider.Read(def.MeshFile, out source, true);
                if (embedded != null)
                {
                    DiagnosticLog.Warn("Loose " + def.MeshFile
                                          + " could not be used; retrying the embedded copy.");
                    asset = TryParseAsset(def.MeshFile, embedded, source);
                }
            }

            if (asset == null)
            {
                FailedLoads.Add(variant);
                return null;
            }

            LoadedAssets[variant] = asset;
            FailedLoads.Remove(variant);
            DiagnosticLog.Diag("Loaded " + def.MeshFile + " (" + source + ", "
                               + asset.SubMeshes.Length + " parts, size "
                               + asset.Bounds.size + ", "
                               + (asset.HasGrips ? "grips ok" : "NO GRIPS") + ")");
            return asset;
        }

        /// <summary>
        /// Reads one .psmesh, reporting a corrupt file instead of throwing. Split out so
        /// GetAsset can retry the embedded copy with exactly the same parse path.
        /// </summary>
        private static PsMeshReader.Asset TryParseAsset(string fileName, byte[] bytes,
                                                        AssetProvider.Source source)
        {
            try
            {
                return PsMeshReader.Read(bytes, fileName);
            }
            catch (Exception ex)
            {
                DiagnosticLog.Error("Failed to parse " + fileName + " (" + source + "): " + ex);
                return null;
            }
        }

        /// <summary>
        /// Builds the render mesh. The .psmesh may contain an inverted-hull outline
        /// shell; that is split out into its own mesh so it can be drawn with front
        /// faces culled and its own flat ink material.
        /// </summary>
        private static Mesh GetMesh(PlushieVariant variant)
        {
            // The non-null check mirrors GetAsset: a cached null must never be treated as
            // "built". `BuildMesh` returns null when the asset has no solid parts, and
            // caching that would make every later call return null without ever retrying.
            if (CachedMeshes.TryGetValue(variant, out Mesh cached) && cached != null)
            {
                return cached;
            }

            PsMeshReader.Asset asset = GetAsset(variant);
            if (asset == null)
            {
                return null;
            }

            Mesh mesh = BuildMesh(asset, wantOutline: false);
            Mesh outline = BuildMesh(asset, wantOutline: true);

            CachedMeshes[variant] = mesh;
            CachedOutlines[variant] = outline;
            return mesh;
        }

        private static Mesh GetOutlineMesh(PlushieVariant variant)
        {
            if (!CachedOutlines.ContainsKey(variant))
            {
                GetMesh(variant);
            }
            return CachedOutlines.TryGetValue(variant, out Mesh outline) ? outline : null;
        }

        /// <summary>
        /// Concatenates either the solid parts or the outline shells into one mesh.
        ///
        /// Everything shares a single material now that colour and baked shading both
        /// come from the palette texture, so all parts are merged into one submesh. That
        /// also avoids the trap of assigning a single material to a multi-submesh mesh:
        /// Unity only draws submesh 0 in that case, which would hide every part except
        /// the first colour.
        /// </summary>
        private static Mesh BuildMesh(PsMeshReader.Asset asset, bool wantOutline)
        {
            List<PsMeshReader.SubMesh> parts = new List<PsMeshReader.SubMesh>();
            int vertexCount = 0;
            int indexCount = 0;
            for (int i = 0; i < asset.SubMeshes.Length; i++)
            {
                PsMeshReader.SubMesh sub = asset.SubMeshes[i];
                if (sub.IsOutline != wantOutline)
                {
                    continue;
                }
                parts.Add(sub);
                vertexCount += sub.Positions.Length;
                indexCount += sub.Indices.Length;
            }

            if (parts.Count == 0)
            {
                return null;
            }


            Mesh mesh = new Mesh
            {
                name = asset.Name + (wantOutline ? "_Outline" : ""),
                indexFormat = vertexCount > 65000 ? IndexFormat.UInt32 : IndexFormat.UInt16
            };

            Vector3[] positions = new Vector3[vertexCount];
            Vector3[] normals = new Vector3[vertexCount];
            Vector2[] uvs = new Vector2[vertexCount];
            Color[] colours = new Color[vertexCount];
            int[] indices = new int[indexCount];

            int vertexOffset = 0;
            int indexOffset = 0;
            for (int i = 0; i < parts.Count; i++)
            {
                PsMeshReader.SubMesh sub = parts[i];
                int count = sub.Positions.Length;
                Array.Copy(sub.Positions, 0, positions, vertexOffset, count);
                Array.Copy(sub.Normals, 0, normals, vertexOffset, count);
                Array.Copy(sub.Uvs, 0, uvs, vertexOffset, count);
                for (int k = 0; k < count; k++)
                {
                    colours[vertexOffset + k] = ToWorkingColor(sub.Colours[k]);
                }

                int[] subIndices = sub.Indices;
                for (int k = 0; k < subIndices.Length; k++)
                {
                    indices[indexOffset + k] = subIndices[k] + vertexOffset;
                }

                vertexOffset += count;
                indexOffset += subIndices.Length;
            }

            mesh.vertices = positions;
            mesh.normals = normals;
            mesh.uv = uvs;
            mesh.colors = colours;
            mesh.SetTriangles(indices, 0, true);
            mesh.RecalculateBounds();
            return mesh;
        }

        /// <summary>
        /// The baked colour + ambient-occlusion palette that ships beside each model.
        /// Sampled through the mesh UVs, it is what gives the plush its crease and
        /// contact shadows — without it the bear's paws and feet, all the same white,
        /// would merge into its body.
        /// </summary>
        private static Texture2D GetShadingTexture(PlushieVariant variant)
        {
            Texture2D cached;
            if (CachedTextures.TryGetValue(variant, out cached))
            {
                return cached;
            }
            if (MissingTextures.Contains(variant))
            {
                return null;
            }

            VariantDefinition def = Variants.Get(variant);
            AssetProvider.Source source;
            Texture2D texture = AssetProvider.ReadTexture(def.TextureFile,
                                                          "PlushieSwap_Shading_" + variant,
                                                          out source, false);

            // Same retry as GetAsset: a loose PNG that fails to decode must not poison
            // MissingTextures for the whole session while a perfectly good embedded copy
            // sits in the DLL. Only the embedded copy is retried, so a corrupt file on
            // disk cannot be re-read forever.
            if (texture == null && source == AssetProvider.Source.LooseFile)
            {
                DiagnosticLog.Warn("Loose " + def.TextureFile
                                      + " could not be used; retrying the embedded copy.");
                texture = AssetProvider.ReadTexture(def.TextureFile,
                                                    "PlushieSwap_Shading_" + variant,
                                                    out source, true);
            }

            if (texture == null)
            {
                MissingTextures.Add(variant);
                return null;
            }

            CachedTextures[variant] = texture;
            return texture;
        }

        /// <summary>
        /// One material for the whole model: the colour and the baked shading both come
        /// from the palette texture, so no per-colour materials are needed.
        /// </summary>
        private static Material GetMaterial(PlushieVariant variant)
        {
            Material cached;
            if (CachedMaterials.TryGetValue(variant, out cached))
            {
                return cached;
            }

            Shader shader = ResolveShader();
            if (shader == null)
            {
                return null;
            }

            // `Material.color` is deliberately not used: it maps onto whichever of
            // _Color / _BaseColor / _Tint the shader happens to declare, and on URP/Lit
            // it reaches for `_Tint`, which does not exist there. Unity logs an error
            // every time that happens. Setting each property only when `HasProperty`
            // confirms it exists avoids the noise entirely.
            Material material = new Material(shader)
            {
                name = "PlushieSwap_" + variant
            };

            // The albedo arrives through the texture, so every tint stays neutral.
            if (material.HasProperty("_BaseColor")) material.SetColor("_BaseColor", Color.white);
            if (material.HasProperty("_Color")) material.SetColor("_Color", Color.white);
            if (material.HasProperty("_Tint")) material.SetColor("_Tint", Color.white);

            Texture2D texture = GetShadingTexture(variant);
            if (texture != null)
            {
                if (material.HasProperty("_BaseMap"))
                {
                    material.SetTexture("_BaseMap", texture);
                    material.SetTextureScale("_BaseMap", Vector2.one);
                    material.SetTextureOffset("_BaseMap", Vector2.zero);
                }
                if (material.HasProperty("_MainTex"))
                {
                    material.SetTexture("_MainTex", texture);
                    material.SetTextureScale("_MainTex", Vector2.one);
                    material.SetTextureOffset("_MainTex", Vector2.zero);
                }
            }

            // Soft plush fabric: matte, with just enough sheen to read as a soft toy
            // rather than flat paper.
            if (material.HasProperty("_Smoothness")) material.SetFloat("_Smoothness", 0.14f);
            if (material.HasProperty("_Glossiness")) material.SetFloat("_Glossiness", 0.14f);
            if (material.HasProperty("_Metallic")) material.SetFloat("_Metallic", 0f);
            if (material.HasProperty("_BumpScale")) material.SetFloat("_BumpScale", 0f);
            if (material.HasProperty("_OcclusionStrength")) material.SetFloat("_OcclusionStrength", 0f);
            if (material.HasProperty("_EnvironmentReflections")) material.SetFloat("_EnvironmentReflections", 0f);
            if (material.HasProperty("_Surface")) material.SetFloat("_Surface", 0f);
            if (material.HasProperty("_ZWrite")) material.SetFloat("_ZWrite", 1f);
            if (material.HasProperty("_Cull")) material.SetFloat("_Cull", (float)CullMode.Back);

            // A whisper of self-illumination on the bright areas only.
            //
            // The albedo texture is the palette that carries the colour AND the baked
            // shading, so using it as the emission map makes the light parts glow while
            // the dark eyes / mouth / blush and the mid-tone dress stay unlit — the cream
            // body reads as a clean bright cream instead of a dull beige, and nothing
            // else is lifted. The colour is a low grey so it lifts without washing out.
            if (material.HasProperty("_EmissionColor"))
            {
                material.EnableKeyword("_EMISSION");
                material.SetColor("_EmissionColor", BaseEmissionColor);
                if (texture != null && material.HasProperty("_EmissionMap"))
                {
                    material.SetTexture("_EmissionMap", texture);
                    material.SetTextureScale("_EmissionMap", Vector2.one);
                    material.SetTextureOffset("_EmissionMap", Vector2.zero);
                }
            }

            material.DisableKeyword("_NORMALMAP");
            material.DisableKeyword("_METALLICSPECGLOSSMAP");
            material.DisableKeyword("_OCCLUSIONMAP");
            material.renderQueue = (int)RenderQueue.Geometry;

            CachedMaterials[variant] = material;
            return material;
        }

        /// <summary>
        /// Flat ink material for the inverted-hull outline. Front faces are culled so
        /// only the shell sticking out around the silhouette is visible.
        ///
        /// An *unlit* shader is used rather than the body's URP/Lit. Lit ink picks up the
        /// scene lighting, so a line that should be a constant dark colour brightens and
        /// dims as the player turns, which reads as a thin, patchy outline. URP/Unlit also
        /// exposes `_Cull`, which is what the inverted hull depends on.
        /// </summary>
        private static Material GetOutlineMaterial(PlushieVariant variant)
        {
            if (CachedOutlineMaterials.TryGetValue(variant, out Material cached))
            {
                return cached;
            }
            Shader shader = ResolveOutlineShader();
            if (shader == null)
            {
                return null;
            }

            Color ink = new Color(0.085f, 0.085f, 0.105f, 1f);
            // See GetMaterial: `Material.color` is not used, because it probes properties
            // such as `_Tint` that URP shaders do not declare and Unity then logs an error.
            Material material = new Material(shader)
            {
                name = "PlushieSwap_Ink_" + variant
            };

            // The whole technique depends on being able to cull front faces. If this
            // shader cannot, the shell would simply cover the plush in black, so the
            // outline is skipped entirely instead.
            bool canCull = material.HasProperty("_Cull") || material.HasProperty("_CullMode");
            if (!canCull)
            {
                UnityEngine.Object.Destroy(material);
                DiagnosticLog.Warn("Shader '" + shader.name
                                      + "' cannot cull front faces; skipping the cartoon outline.");
                CachedOutlineMaterials[variant] = null;
                return null;
            }

            if (material.HasProperty("_BaseColor")) material.SetColor("_BaseColor", ink);
            if (material.HasProperty("_Color")) material.SetColor("_Color", ink);
            if (material.HasProperty("_Tint")) material.SetColor("_Tint", ink);
            if (material.HasProperty("_BaseMap")) material.SetTexture("_BaseMap", null);
            if (material.HasProperty("_MainTex")) material.SetTexture("_MainTex", null);

            // Flat, unlit ink: no sheen at all so it reads as a drawn line.
            if (material.HasProperty("_Smoothness")) material.SetFloat("_Smoothness", 0f);
            if (material.HasProperty("_Glossiness")) material.SetFloat("_Glossiness", 0f);
            if (material.HasProperty("_Metallic")) material.SetFloat("_Metallic", 0f);
            if (material.HasProperty("_SpecularHighlights")) material.SetFloat("_SpecularHighlights", 0f);
            if (material.HasProperty("_EnvironmentReflections")) material.SetFloat("_EnvironmentReflections", 0f);
            if (material.HasProperty("_Surface")) material.SetFloat("_Surface", 0f);
            if (material.HasProperty("_Blend")) material.SetFloat("_Blend", 0f);
            if (material.HasProperty("_ZWrite")) material.SetFloat("_ZWrite", 1f);
            if (material.HasProperty("_SrcBlend")) material.SetFloat("_SrcBlend", (float)BlendMode.One);
            if (material.HasProperty("_DstBlend")) material.SetFloat("_DstBlend", (float)BlendMode.Zero);
            if (material.HasProperty("_AlphaClip")) material.SetFloat("_AlphaClip", 0f);

            // Front faces culled: this is what makes the shell an outline.
            if (material.HasProperty("_Cull")) material.SetFloat("_Cull", (float)CullMode.Front);
            if (material.HasProperty("_CullMode")) material.SetFloat("_CullMode", (float)CullMode.Front);

            if (material.HasProperty("_EmissionColor"))
            {
                material.SetColor("_EmissionColor", Color.black);
                material.DisableKeyword("_EMISSION");
            }

            material.DisableKeyword("_NORMALMAP");
            material.DisableKeyword("_METALLICSPECGLOSSMAP");
            material.DisableKeyword("_OCCLUSIONMAP");
            material.DisableKeyword("_SURFACE_TYPE_TRANSPARENT");
            material.EnableKeyword("_SURFACE_TYPE_OPAQUE");
            material.SetOverrideTag("RenderType", "Opaque");
            material.renderQueue = (int)RenderQueue.Geometry;

            CachedOutlineMaterials[variant] = material;
            return material;
        }

        /// <summary>
        /// The shader for the ink shell. Unlit first: the line must not change brightness
        /// with the lighting. Everything after it is a fallback that still exposes `_Cull`.
        /// </summary>
        private static Shader ResolveOutlineShader()
        {
            if (_outlineShader != null)
            {
                return _outlineShader;
            }

            string overrideName = Plugin.ShaderOverrideEntry != null
                ? Plugin.ShaderOverrideEntry.Value : "";
            if (!string.IsNullOrEmpty(overrideName))
            {
                Shader custom = Shader.Find(overrideName);
                if (custom != null && custom.isSupported
                    && (custom.name.IndexOf("Unlit", StringComparison.OrdinalIgnoreCase) >= 0))
                {
                    _outlineShader = custom;
                    DiagnosticLog.Diag("Using outline shader override: " + overrideName);
                    return _outlineShader;
                }
            }

            string[] candidates =
            {
                "Universal Render Pipeline/Unlit",
                "Unlit/Color",
                "Universal Render Pipeline/Lit",
                "Standard"
            };
            for (int i = 0; i < candidates.Length; i++)
            {
                Shader shader = Shader.Find(candidates[i]);
                if (shader != null && shader.isSupported)
                {
                    _outlineShader = shader;
                    DiagnosticLog.Diag("Using outline shader: " + candidates[i]);
                    return _outlineShader;
                }
            }

            DiagnosticLog.Warn("No unlit shader with _Cull found; the outline will use the "
                                  + "body shader (lit ink).");
            return ResolveShader();
        }

        private static Shader ResolveShader()
        {
            if (_shader != null)
            {
                return _shader;
            }

            string overrideName = Plugin.ShaderOverrideEntry != null ? Plugin.ShaderOverrideEntry.Value : "";
            if (!string.IsNullOrEmpty(overrideName))
            {
                Shader custom = Shader.Find(overrideName);
                if (custom != null && custom.isSupported)
                {
                    _shader = custom;
                    DiagnosticLog.Diag("Using shader override: " + overrideName);
                    return _shader;
                }
                DiagnosticLog.Warn("Shader override not usable: " + overrideName);
            }

            string[] candidates =
            {
                "Universal Render Pipeline/Lit",
                "Universal Render Pipeline/Simple Lit",
                "W/Peak_Standard",
                "Standard"
            };
            for (int i = 0; i < candidates.Length; i++)
            {
                Shader shader = Shader.Find(candidates[i]);
                if (shader != null && shader.isSupported)
                {
                    _shader = shader;
                    DiagnosticLog.Diag("Using shader: " + candidates[i]);
                    return _shader;
                }
            }

            DiagnosticLog.Error("No usable shader found; the replacement will not render.");
            return null;
        }

        private static Shader _shader;
        private static Shader _outlineShader;

        // ------------------------------------------------------------------ colour
        /// <summary>
        /// The .psmesh colours are sRGB (they come from the 3MF filament hex values).
        /// Unity wants working-space values, which differ in a Linear project, so they
        /// are converted once here instead of being fed in raw (which looks washed out).
        /// </summary>
        internal static Color ToWorkingColor(Color srgb)
        {
            return QualitySettings.activeColorSpace == ColorSpace.Linear ? srgb.linear : srgb;
        }

        // ------------------------------------------------------------------ building
        /// <summary>
        /// The replacement root under an item, wherever it was parented.
        ///
        /// A direct `transform.Find` is not enough now that the root hangs off `Holder`
        /// (see ResolveVisualParent), and the one named match may already be queued for
        /// destruction (`Object.Destroy` is deferred to the end of the frame). So every
        /// marker under the item is inspected and the first live one wins.
        ///
        /// This walks the item's entire subtree and allocates an array, so it is the
        /// authoritative-but-expensive lookup. `FindVisualRootCached` is what the
        /// per-frame sweep uses; this one remains the fallback and the repair path.
        /// </summary>
        internal static Transform FindVisualRoot(Item item)
        {
            // The gameObject check is not redundant with the null check: a destroyed Item
            // still compares equal to null through Unity's overloaded operator, but a
            // wrapper whose GameObject has already been torn down can reach here from a
            // deferred call, and the native GetComponentsInChildren on it would throw.
            // GetItemState guards the same way; the two must agree.
            if (item == null || item.gameObject == null)
            {
                return null;
            }
            PlushieVisualMarker[] markers =
                item.GetComponentsInChildren<PlushieVisualMarker>(true);
            for (int i = 0; i < markers.Length; i++)
            {
                if (markers[i] != null && !markers[i].Destroying)
                {
                    return markers[i].transform;
                }
            }
            return null;
        }

        /// <summary>
        /// `FindVisualRoot`, but it trusts the marker cached on the item's state component
        /// while that marker is still alive.
        ///
        /// The cache is invalidated whenever the root is destroyed (`DestroyReplacement`
        /// clears it and sets `Destroying`), so a hit here means "the root that was built
        /// for this item is still the one under it". Any doubt — no state component, a
        /// destroyed marker, a marker already flagged for destruction — falls through to
        /// the full search, which is the only path that can notice a root built by someone
        /// else (a Harmony hook firing on an item the tracker never saw).
        /// </summary>
        private static Transform FindVisualRootCached(Item item, PlushieItemState itemState)
        {
            if (itemState != null)
            {
                PlushieVisualMarker cached = itemState.Visual;
                if (cached != null && !cached.Destroying)
                {
                    return cached.transform;
                }
                if (cached != null)
                {
                    itemState.Visual = null;
                }
            }

            Transform root = FindVisualRoot(item);
            if (itemState != null && root != null)
            {
                PlushieVisualMarker marker = root.GetComponent<PlushieVisualMarker>();
                if (marker != null && !marker.Destroying)
                {
                    itemState.Visual = marker;
                }
            }
            return root;
        }

        internal static bool IsPlushieTransform(Transform transform)
        {
            return transform != null
                   && transform.GetComponentInParent<PlushieVisualMarker>() != null;
        }

        private static void RefreshAll(bool hard)
        {
            // Every known BingBong is swept, not just the tracked list. A root can be
            // built from a Harmony hook on an item the tracker never saw, and such a root
            // would otherwise survive a switch to Vanilla with the mod's renderers still
            // hidden and the vanilla model still off.
            //
            // The snapshot is not incidental: `AllItems()` hands back the game's own live
            // `List<Item>` when its registry is available, and the body below calls into
            // game code (Destroy, AddComponent) while iterating. Copying first means an
            // item the game removes mid-loop cannot shift the list under an index.
            IReadOnlyList<Item> items = new List<Item>(GameHelpers.AllItems());

            if (hard || !Variants.IsReplacement)
            {
                // Rebuild every instance so a variant switch is immediate. The cached
                // meshes and materials are per variant and stay valid, so they are kept.
                //
                // `items` is already a superset of `TrackedItems` — EnsureTracked only
                // ever adds items that passed IsBingBongItem — so destroying every
                // BingBong in it covers the tracked list too. DestroyReplacement is
                // idempotent, but running it twice per item is wasted subtree searching.
                for (int i = 0; i < items.Count; i++)
                {
                    if (GameHelpers.IsBingBongItem(items[i]))
                    {
                        DestroyReplacement(items[i]);
                    }
                }
                TrackedItems.Clear();
                _nextRescan = 0f;
            }

            if (!Variants.IsReplacement)
            {
                return;
            }

            for (int i = 0; i < items.Count; i++)
            {
                Item item = items[i];
                if (GameHelpers.IsBingBongItem(item))
                {
                    EnsureTracked(item);
                    ApplyToItem(item);
                }
            }
        }

        private static void MaintainTrackedItems()
        {
            if (!Variants.IsReplacement)
            {
                return;
            }

            // Photon destroys can leave dead references behind; prune them.
            for (int i = TrackedItems.Count - 1; i >= 0; i--)
            {
                if (TrackedItems[i] == null)
                {
                    TrackedItems.RemoveAt(i);
                }
            }

            // Every tracked plush is re-checked every frame: its model offset is
            // re-applied and its renderers kept off. This is the safety net that makes
            // the pose impossible to get stuck in a wrong state — the Harmony hooks only
            // fire on item events, so a state the game changes without going through a
            // patched method would otherwise never be corrected. The work itself is a
            // cheap value comparison that does nothing when everything is already right.
            for (int i = 0; i < TrackedItems.Count; i++)
            {
                Item item = TrackedItems[i];
                if (item != null)
                {
                    // Each item is isolated. This runs from `LateUpdate`, whose single
                    // try/catch covers the whole sweep, so one plush that throws every
                    // frame would otherwise stop every OTHER plush from being synced —
                    // and would write an error line per frame forever. Guarding per item
                    // keeps the damage to the item that is actually broken.
                    try
                    {
                        // The per-frame path reads the state component anyway (SyncVisual
                        // needs it), so the cached root lookup is free here: it turns the
                        // subtree search into one field read plus a liveness check.
                        PlushieItemState itemState = GetItemState(item);
                        Transform root = FindVisualRootCached(item, itemState);
                        PlushieVisualMarker marker = root != null
                            ? root.GetComponent<PlushieVisualMarker>() : null;
                        if (root != null && marker != null)
                        {
                            SyncVisual(item, root, marker);
                        }
                    }
                    catch (Exception ex)
                    {
                        DiagnosticLog.Error("SyncVisual failed for " + item.name + ": " + ex);
                    }
                }
            }

            // Rescan on a timer regardless of how many are tracked. Rescanning only when
            // the list was empty meant a plush that spawned after the first one was never
            // picked up, so it could not be cleaned up on a later switch.
            if (Time.unscaledTime < _nextRescan)
            {
                return;
            }
            _nextRescan = Time.unscaledTime + RescanInterval;

            IReadOnlyList<Item> items = GameHelpers.AllItems();
            for (int i = 0; i < items.Count; i++)
            {
                if (GameHelpers.IsBingBongItem(items[i]))
                {
                    EnsureTracked(items[i]);
                    ApplyToItem(items[i]);
                }
            }
        }

        private static void EnsureTracked(Item item)
        {
            if (!TrackedItems.Contains(item))
            {
                TrackedItems.Add(item);
            }
        }

        /// <summary>
        /// Make the item show the configured plush (or the vanilla model). Safe to call
        /// for any item: non-BingBong items are ignored, so a Harmony hook firing early
        /// can never attach a plush to the wrong object.
        /// </summary>
        internal static void ApplyToItem(Item item)
        {
            // This runs from Harmony postfixes on Item.Start / OnEnable / SetState /
            // HideRenderers, i.e. inside the game's own item logic. A throw here would
            // propagate out of e.g. CharacterItems.Equip and abort equipping, so the
            // whole body is guarded and a failure can never take the game down with it.
            try
            {
                ApplyToItemUnsafe(item);
            }
            catch (Exception ex)
            {
                if (Plugin.Log != null)
                {
                    DiagnosticLog.Error("ApplyToItem failed: " + ex);
                }
            }
        }

        private static void ApplyToItemUnsafe(Item item)
        {
            if (item == null || item.gameObject == null || !GameHelpers.IsBingBongItem(item))
            {
                return;
            }

            if (!Variants.IsReplacement)
            {
                DestroyReplacement(item);
                return;
            }

            PlushieItemState itemState = GetItemState(item);
            Transform root = FindVisualRootCached(item, itemState);
            PlushieVisualMarker marker = root != null ? root.GetComponent<PlushieVisualMarker>() : null;

            // A root without its marker is not a root this mod built (or it was damaged),
            // so it is thrown away rather than dereferenced. `marker` is read on every
            // line below, so it must never be null once `root` is non-null.
            if (root != null && marker == null)
            {
                UnityEngine.Object.Destroy(root.gameObject);
                root = null;
            }

            if (marker != null && marker.Variant != Plugin.ActiveVariant)
            {
                DestroyReplacement(item);
                root = null;
                marker = null;
            }

            if (root == null)
            {
                root = BuildVisual(item);
                if (root == null)
                {
                    return;
                }
                marker = root.GetComponent<PlushieVisualMarker>();
            }

            if (itemState != null)
            {
                itemState.Visual = marker;
            }

            SyncVisual(item, root, marker);
        }

        /// <summary>
        /// The per-item state component, created on demand. It lives on the item itself
        /// (not the visual root) so `HiddenByGameRule` survives the root being rebuilt.
        /// </summary>
        private static PlushieItemState GetItemState(Item item)
        {
            // `item == null` covers a plain null; the separate gameObject check covers a
            // destroyed-but-still-referenced Item. Unity's pseudo-null makes a destroyed
            // object compare equal to null, but a wrapper whose GameObject has already
            // been torn down can still reach here from a deferred call. AddComponent on
            // such an object throws, and this runs inside the game's own item logic, so
            // it is guarded here rather than at every call site.
            if (item == null || item.gameObject == null)
            {
                return null;
            }
            PlushieItemState state = item.GetComponent<PlushieItemState>();
            if (state == null)
            {
                state = item.gameObject.AddComponent<PlushieItemState>();
            }
            return state;
        }

        /// <summary>
        /// The node the vanilla plush mesh hangs off: `BingBong_Prop Variant/Holder`.
        ///
        /// This is what makes the game's own "Squish" animation work on the replacement
        /// with no code. Holding the plush and holding primary fire runs
        /// `Action_AskBingBong.RunAction` -> RPC `Ask` -> `squishAnim.SetTrigger("Squish")`
        /// on the item's Animator, and that controller's only animated properties are
        /// `Holder`'s localScale and the two hand anchors' localPosition. The vanilla
        /// mesh is a child of `Holder`, so it is squeezed along with the anchors.
        ///
        /// A replacement parented to the item root instead gets none of that. Parenting
        /// it here reproduces the vanilla behaviour exactly, because `Holder` sits at
        /// (0,0,0) with identity rotation and unit scale at rest — so it costs nothing
        /// while idle and inherits the squash while the animation plays.
        ///
        /// Falls back to the item itself when the node is missing (another mod, or a
        /// different item), which is the old behaviour rather than a failure.
        /// </summary>
        private const string HolderName = "Holder";

        private static Transform ResolveVisualParent(Item item)
        {
            if (item != null)
            {
                Transform holder = item.transform.Find(HolderName);
                if (holder != null)
                {
                    return holder;
                }
            }

            // Falling back to the item root is the old behaviour rather than a failure,
            // but it silently loses the game's Squish animation: that animation drives
            // `Holder.localScale` and nothing else, so a root parented anywhere else does
            // not get squeezed. It is worth one warning, because the symptom (the plush
            // stops squashing when you hold primary fire) is otherwise unattributable.
            if (item != null)
            {
                DiagnosticLog.Warn("No '" + HolderName + "' node under " + item.name
                                   + "; the plush will not inherit the game's squeeze animation.");
            }
            return item != null ? item.transform : null;
        }

        private static Transform BuildVisual(Item item)
        {
            Mesh mesh = GetMesh(Plugin.ActiveVariant);
            Material material = GetMaterial(Plugin.ActiveVariant);
            if (mesh == null || material == null)
            {
                return null;
            }

            Transform parent = ResolveVisualParent(item);
            if (parent == null)
            {
                return null;
            }

            GameObject rootObject = new GameObject(VisualRootName);
            rootObject.transform.SetParent(parent, false);
            rootObject.layer = VisibleLayer;

            PlushieVisualMarker marker = rootObject.AddComponent<PlushieVisualMarker>();
            marker.Variant = Plugin.ActiveVariant;

            GameObject part = new GameObject("Model");
            part.transform.SetParent(rootObject.transform, false);
            part.layer = VisibleLayer;

            PsMeshReader.Asset asset = GetAsset(Plugin.ActiveVariant);
            if (asset == null)
            {
                // `mesh` and `material` imply this succeeded, but the outline block below
                // reads `asset` directly, so the contract is made explicit here.
                UnityEngine.Object.Destroy(rootObject);
                return null;
            }

            // The meshes are cached per variant and shared by every plush in the scene,
            // which is fine now that nothing deforms them at runtime.
            MeshFilter filter = part.AddComponent<MeshFilter>();
            filter.sharedMesh = mesh;

            MeshRenderer renderer = part.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = ShadowCastingMode.On;
            renderer.receiveShadows = true;
            renderer.allowOcclusionWhenDynamic = false;
            renderer.lightProbeUsage = LightProbeUsage.BlendProbes;

            // The cook tint goes through this renderer's property block, so the marker
            // keeps the reference rather than searching for it every frame. The outline
            // shell below deliberately does not get one: its ink must stay black.
            marker.BodyRenderer = renderer;

            // `item.mainRenderer` is deliberately NOT re-pointed at this renderer.
            //
            // Pointing it here is the obvious way to make `Item.HoverEnter/HoverExit`
            // write `_Interactable` to the replacement, and it was evaluated against the
            // decompiled game. It is not done, for three reasons:
            //
            //   * It would not highlight anything. `ResolveShader` picks
            //     "Universal Render Pipeline/Lit", and that shader declares no
            //     `_Interactable` (the research property dump lists all 50 of its
            //     properties; only `W/Character` and the `W/Peak_*` family declare it).
            //     The write would be a silent no-op, so the change would buy risk for
            //     nothing.
            //   * It would clobber the cook tint. `Item.AddPropertyBlock` reads the
            //     vanilla renderer into `item.mpb`, and `HoverEnter/HoverExit` then write
            //     that whole block to `mainRenderer`. Pointed at this renderer, a single
            //     hover would replace the `_BaseColor` / `_EmissionColor` block that
            //     ApplyCookTint wrote with the vanilla renderer's block, and the plush
            //     would snap back to un-cooked colours until the next cook change —
            //     i.e. the fix above would be actively broken by hovering.
            //   * `Item.Center()` returns `mainRenderer.bounds.center` and feeds gameplay:
            //     AOE damage distance, Beehive, Lava burn/drown tests and cook-position,
            //     WindChillZone containment, CompassPointer distance. Today it measures
            //     the (hidden) vanilla mesh; re-pointed it would measure this model, whose
            //     bounds move with the World Scale setting and the hold offset.
            //
            // Should a hover highlight be wanted later, the safe route is a Harmony patch
            // on `Item.HoverEnter/HoverExit` that adds the highlight into this marker's own
            // property block (composing with the cook tint instead of replacing it), not a
            // pointer swap.

            // The inverted-hull outline lives on its own child so it can use a flat ink
            // material with front faces culled. It casts no shadow of its own.
            //
            // Its vertices are extruded once, in the model's own space, so the line is part
            // of the plush and scales with it (see PlushieOutline). The extrusion depends on
            // the width setting, which can change at runtime, so each instance keeps its own
            // copy of the mesh rather than sharing the cached one.
            //
            // The width is checked BEFORE anything is created. A width of 0 is documented
            // to hide the outline; creating the object anyway would leave it rendering at
            // the baked world thickness (the "0 does nothing" bug) and would also leak the
            // mesh, because `DestroyReplacement` finds outline meshes through the driver
            // component that a rejected Attach never adds.
            bool wantsOutline = Plugin.OutlineWidthPixels > 0f
                                && asset.BakedOutlineThickness > 0f;
            Mesh outline = wantsOutline ? GetOutlineMesh(Plugin.ActiveVariant) : null;
            if (outline != null)
            {
                Material inkMaterial = GetOutlineMaterial(Plugin.ActiveVariant);
                if (inkMaterial != null)
                {
                    GameObject outlineObject = new GameObject("Outline");
                    outlineObject.transform.SetParent(rootObject.transform, false);
                    outlineObject.layer = VisibleLayer;

                    Mesh outlineMesh = UnityEngine.Object.Instantiate(outline);
                    outlineMesh.name = outline.name + "_Instance";

                    MeshFilter outlineFilter = outlineObject.AddComponent<MeshFilter>();
                    outlineFilter.sharedMesh = outlineMesh;

                    MeshRenderer outlineRenderer = outlineObject.AddComponent<MeshRenderer>();
                    outlineRenderer.sharedMaterial = inkMaterial;
                    outlineRenderer.shadowCastingMode = ShadowCastingMode.Off;
                    outlineRenderer.receiveShadows = false;
                    outlineRenderer.allowOcclusionWhenDynamic = false;
                    outlineRenderer.lightProbeUsage = LightProbeUsage.Off;

                    // Model-space thickness. The shell was baked with a fixed push; the
                    // driver recovers the body surface from it and re-applies the push for
                    // the configured width, so the line stays proportional to the plush at
                    // every distance instead of holding a fixed pixel width.
                    PlushieOutline driver = PlushieOutline.Attach(
                        outlineObject, outlineMesh,
                        asset.BakedOutlineThickness, asset.OutlineWidths,
                        Plugin.OutlineWidthPixels);
                    if (driver == null)
                    {
                        // Attach rejected it after all (e.g. a malformed shell). Do not
                        // leave an undriven, un-releasable object behind.
                        UnityEngine.Object.Destroy(outlineMesh);
                        UnityEngine.Object.Destroy(outlineObject);
                        DiagnosticLog.Warn("Outline driver SKIPPED; outline object removed "
                                              + "(baked " + asset.BakedOutlineThickness.ToString("F6")
                                              + ", width " + Plugin.OutlineWidthPixels.ToString("F2")
                                              + ")");
                    }
                    else
                    {
                        DiagnosticLog.Diag("Outline driver attached (baked "
                                           + asset.BakedOutlineThickness.ToString("F6")
                                           + ", width " + Plugin.OutlineWidthPixels.ToString("F2")
                                           + ", " + outlineMesh.vertexCount + " verts, "
                                           + (asset.OutlineWidths != null
                                              ? asset.OutlineWidths.Length + " widths"
                                              : "uniform") + ")");
                    }
                }
            }

            // The item's own Hand_L / Hand_R nodes are left exactly as the vanilla prefab
            // authored them. The plush is placed in the hands by shifting the MODEL
            // instead — see SyncVisual and HoldOffsetFor. (Writing the anchors was tried
            // and makes the hands land correctly, but the game's hold spring, hand IK and
            // FixedJoints then disagree and the plush shakes.)

            // The item pivot and the model pivot already agree (the .psmesh pipeline
            // places the mesh exactly where the vanilla plush mesh sits), and the game
            // aims held items with LookRotation(lookDirection, lookDirection_Up), so the
            // model only needs identity orientation.
            rootObject.transform.localPosition = Vector3.zero;
            rootObject.transform.localRotation = Quaternion.identity;
            rootObject.transform.localScale = Vector3.one;

            rootObject.SetActive(true);
            DiagnosticLog.Diag("Built " + Variants.Active.DisplayNameEn + " for " + item.name);
            return rootObject.transform;
        }

        /// <summary>
        /// How far the model must be shifted, while held, for the vanilla hand anchors to
        /// land on the plush's waist.
        ///
        /// The anchors sit at a fixed place in the item's local space (their vanilla
        /// values, which are never changed). The .psmesh records where the waist is in
        /// model space. The model is drawn scaled about the root's origin, so a model
        /// point `p` ends up at `root.localPosition + scale * p`; the shift that puts the
        /// waist under the anchors is therefore
        ///
        ///     offset = anchorMidpoint - scale * waistMidpoint
        ///
        /// The `scale` factor is essential: without it the waist is only under the
        /// anchors at the default 1.0, and a player who raises or lowers World Scale sees
        /// the plush drift out of the hands (at 0.3 it is off by 40% of its own height).
        ///
        /// The two plushies have different waists, so this is per model. Returns zero when
        /// there is nothing to read, which leaves the plush at its authored position.
        ///
        /// This is the reference mod's scheme: one constant local offset applied while
        /// held (`(-0.06, -0.5, 0)` there), with the constant derived from this model's
        /// own waist instead of hard-coded for one model.
        ///
        /// It is deliberately NOT a fitted placement. An attempt was made to instead
        /// search for the offset that puts both hand anchors deepest inside the
        /// silhouette; that maximised contact but slid the grip up onto Miffy's
        /// outstretched arms, so the plush read as being held up by the arms. The waist
        /// is the intended hold and it is what the player sees.
        /// </summary>
        private static Vector3 HoldOffsetFor(PsMeshReader.Asset asset, float scale)
        {
            if (asset == null || !asset.HasGrips)
            {
                return Vector3.zero;
            }

            // The vanilla anchors, in item-local space, read from "BingBong_Prop Variant".
            // Kept here rather than in the .psmesh because they are a property of the GAME
            // item, not of the plush model.
            Vector3 anchorMid = new Vector3(-0.0595f, -0.1405f, -0.0400f);

            Vector3 waistMid = (asset.GripLeft + asset.GripRight) * 0.5f;
            Vector3 offset = anchorMid - waistMid * scale;

            // The model is the item's child and inherits the item's rotation, so the
            // offset is expressed in model space exactly as the grips are.
            return offset;
        }

        internal static void DestroyReplacement(Item item)
        {
            if (item == null || item.gameObject == null)
            {
                return;
            }

            // The per-frame lookup trusts the marker cached on the item state, so that
            // cache has to be dropped in the same breath as the root it points at.
            PlushieItemState itemState = item.GetComponent<PlushieItemState>();
            if (itemState != null)
            {
                itemState.Visual = null;
            }

            Transform existing = FindVisualRoot(item);
            if (existing != null)
            {
                // Mark it dead first: `Object.Destroy` is deferred to the end of the
                // frame, so a lookup later in this same frame must not treat it as live.
                PlushieVisualMarker doomed = existing.GetComponent<PlushieVisualMarker>();
                if (doomed != null)
                {
                    doomed.Destroying = true;
                }
                existing.name = VisualRootName + "_Destroying";

                // The outline mesh is a per-instance copy (its vertices change every
                // frame), so it would leak if it were only unparented. Unity does not
                // collect meshes on its own, so it is released explicitly. (The driver
                // also does this from OnDestroy, which covers the game destroying the
                // item itself.)
                PlushieOutline[] outlines =
                    existing.GetComponentsInChildren<PlushieOutline>(true);
                for (int i = 0; i < outlines.Length; i++)
                {
                    if (outlines[i] != null)
                    {
                        outlines[i].ReleaseMesh();
                    }
                }

                UnityEngine.Object.Destroy(existing.gameObject);
            }

            // Hand rendering back to the game (matters when switching to Vanilla). If the
            // game has hidden the plush for its own reason (it is in a worn backpack) the
            // renderers must stay off, or the vanilla model would pop back into view.
            // The flag lives on the item, so it survives this destroy.
            bool gameHidIt = itemState != null && itemState.HiddenByGameRule;
            if (!gameHidIt)
            {
                SetVanillaRenderersEnabled(item, true);
            }
        }

        // ------------------------------------------------------------------ state
        private static void SyncVisual(Item item, Transform root, PlushieVisualMarker marker)
        {
            if (root == null || marker == null)
            {
                return;
            }

            PlushieItemState itemState = GetItemState(item);
            ItemState state = item.itemState;
            bool stateChanged = marker.LastState != state;
            marker.LastState = state;

            // The game only hides a plush it is *wearing* on someone's back
            // (`PutInBackpackRPC` -> `HideRenderers`), and `HideRenderers` never turns
            // renderers back on. A plush inside a backpack that is lying on the ground is
            // meant to be visible, so if the hide flag is set outside that one case it
            // must be cleared — otherwise a route that keeps the same visual instance
            // alive (a third-party mod swapping backpack contents, for instance) would
            // leave the plush invisible forever.
            if (itemState != null && itemState.HiddenByGameRule && !IsWornBackpack(item))
            {
                ClearGameRuleHide(item);
            }

            bool visible = Variants.IsReplacement
                           && (itemState == null || !itemState.HiddenByGameRule);

            if (root.gameObject.activeSelf != visible)
            {
                root.gameObject.SetActive(visible);
            }

            // While this mod drives the visuals the vanilla renderers must stay off, or
            // both models would draw on top of each other.
            if (!marker.VanillaRenderersHidden || stateChanged)
            {
                marker.VanillaRenderersHidden = true;
                SetVanillaRenderersEnabled(item, false);
            }

            if (!visible)
            {
                return;
            }

            ApplyCookTint(item, marker);

            float scale = ScaleForState(item);
            if (!Mathf.Approximately(marker.LastScale, scale))
            {
                marker.LastScale = scale;
                root.localScale = Vector3.one * scale;
            }

            // The model is SHIFTED so the vanilla hand anchors land on its waist.
            //
            // The item's own Hand_L / Hand_R nodes are deliberately never touched. The
            // game holds an item with a physical spring (CharacterItems.HoldItem), places
            // the hands from those anchors (CharacterAnimations.ConfigureIK) and ties the
            // hands to the rigidbody with FixedJoints, so all three only agree while the
            // anchors keep the values the vanilla prefab authored.
            //
            // So the anchors keep their values and the MODEL moves instead, exactly what
            // the working ScallionMiku mod does for this same item. The offset is derived
            // from this model's own waist, which the .psmesh carries as its grip points.
            //
            // Only while HELD: the offset exists to meet the hand anchors, and a plush
            // lying on the ground has no hands on it, so it must sit on its own pivot
            // the way the vanilla model does.
            Vector3 localPosition = Vector3.zero;
            if (state == ItemState.Held)
            {
                localPosition = HoldOffsetFor(GetAsset(Plugin.ActiveVariant), scale);
                if (Plugin.HoldOffsetEntry != null)
                {
                    localPosition.y += Plugin.HoldOffsetEntry.Value;
                }
            }
            if ((localPosition - root.localPosition).sqrMagnitude > 1e-8f)
            {
                root.localPosition = localPosition;
            }
        }

        /// <summary>
        /// Reproduces the game's cook tint on the replacement's body.
        ///
        /// The vanilla plush browns as it cooks and turns near-black when burnt, because
        /// `ItemCooking` multiplies `_Tint` on every renderer it owns. Our replacement is
        /// deliberately excluded from that list (see CookingPatches: reading `_Tint` on a
        /// shader that does not declare it spams Unity errors), so without this the plush
        /// would look identical whether it is raw or incinerated — the visible cooking
        /// feedback would be gone.
        ///
        /// The tint must NOT go onto the shared material: `CachedMaterials` is keyed by
        /// variant, so every plush in the scene shares the same Material instance and
        /// writing `_BaseColor` there would recolour all of them at once. A
        /// `MaterialPropertyBlock` belongs to this one renderer, which is exactly the
        /// scope the game's own per-item tint has.
        ///
        /// `ItemCooking.GetCookColor` is public static, and is called rather than copied
        /// so the numbers stay the game's own (1 = `(0.66, 0.47, 0.25)`, 2 = half of that,
        /// 3+ = `BurntCookColorMultiplier` `(0.05, 0.05, 0.1)`, 0 = white).
        ///
        /// The albedo palette is the mesh's only colour, so the cook factor is applied to
        /// `_BaseColor`. The material also turns the same palette into an emission map
        /// with a low grey `_EmissionColor`; left alone, a burnt plush would keep glowing
        /// pale and read as grey-white instead of charred, so the same factor is
        /// multiplied into the emission colour. The outline lives on the same root but has
        /// its own renderer and is never touched: the ink stays black at any cook level.
        /// </summary>
        private static void ApplyCookTint(Item item, PlushieVisualMarker marker)
        {
            MeshRenderer renderer = marker.BodyRenderer;
            if (renderer == null)
            {
                return;
            }

            int cooked = ReadCookedAmount(item);
            if (marker.LastCook == cooked)
            {
                // The property block is per renderer, not per material, so skipping the
                // redundant write is the whole cost saving here — but it is also what
                // keeps this cheap enough to run from the per-frame item sweep.
                return;
            }
            marker.LastCook = cooked;

            Color cook = ItemCooking.GetCookColor(cooked);
            if (marker.CookBlock == null)
            {
                marker.CookBlock = new MaterialPropertyBlock();
            }

            // Read the renderer's current block and edit only our two keys, rather than
            // clearing it. Another mod may own other keys on this same renderer — ScrapClean
            // writes `_Interactable` to every renderer under a ground item's subtree to draw
            // its cleanup highlight, and this renderer is one of them. `Clear()` would wipe
            // that key every time the plush cooks, making the highlight flicker for the rest
            // of the session. Composing instead of replacing keeps both features working.
            renderer.GetPropertyBlock(marker.CookBlock);
            marker.CookBlock.SetColor(BaseColorId, cook);

            // The emissive term is scaled the same way. `GetCookColor` returns white for a
            // raw plush, so multiplying by it restores exactly the authored emission.
            marker.CookBlock.SetColor(EmissionColorId, BaseEmissionColor * cook);

            renderer.SetPropertyBlock(marker.CookBlock);
        }

        /// <summary>
        /// The current cook level, or 0 when the item carries none.
        ///
        /// `TryGetDataEntry` is used rather than `GetData&lt;IntItemData&gt;` on purpose.
        /// `GetData` is not a read: when the entry is absent it *registers* one
        /// (`ItemInstanceData.RegisterNewEntry`), and it runs on the per-frame item sweep,
        /// so reading the cook level would write to every plush's instance data. It would
        /// also allocate an entry for plushies that never cook. `TryGetDataEntry` is a
        /// plain lookup and reports "absent" as 0, which is the same answer the caller
        /// wants. This runs from the item sweep and a destroyed instance data would throw
        /// out of it, so the whole read is guarded and degrades to "uncooked".
        /// </summary>
        private static int ReadCookedAmount(Item item)
        {
            if (item == null || item.gameObject == null)
            {
                return 0;
            }
            try
            {
                ItemInstanceData data = item.data;
                IntItemData cooked;
                if (data != null
                    && data.TryGetDataEntry<IntItemData>(DataEntryKey.CookedAmount, out cooked)
                    && cooked != null)
                {
                    return cooked.Value;
                }
                return 0;
            }
            catch (Exception ex)
            {
                if (Plugin.Log != null)
                {
                    DiagnosticLog.Warn("Could not read CookedAmount: " + ex.Message);
                }
                return 0;
            }
        }

        /// <summary>
        /// The emission the body material is authored with. ApplyCookTint scales it by the
        /// cook factor rather than writing a second hard-coded colour, so the two cannot
        /// drift apart.
        /// </summary>
        private static readonly Color BaseEmissionColor = new Color(0.16f, 0.155f, 0.15f, 1f);
        private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        private static readonly int EmissionColorId = Shader.PropertyToID("_EmissionColor");

        /// <summary>
        /// Turn every non-replacement renderer under the item on or off.
        ///
        /// Two flags are written, not one. `renderer.enabled` is what the game itself uses
        /// (`Item.HideRenderers`), so it must be mirrored exactly; `forceRenderingOff` is a
        /// second latch that survives another mod re-enabling the renderer, which is worth
        /// having because the vanilla mesh sits behind the replacement and any stray
        /// `enabled = true` from a third-party mod would draw it through the plush. The
        /// reference mod does the same. Both are always written together — clearing only
        /// one would leave a renderer that is permanently invisible.
        /// </summary>
        private static void SetVanillaRenderersEnabled(Item item, bool enabled)
        {
            Renderer[] renderers = item.GetComponentsInChildren<Renderer>(true);
            for (int i = 0; i < renderers.Length; i++)
            {
                Renderer renderer = renderers[i];
                if (renderer == null || IsPlushieTransform(renderer.transform))
                {
                    continue;
                }
                if (renderer.enabled != enabled)
                {
                    renderer.enabled = enabled;
                }
                if (renderer.forceRenderingOff != !enabled)
                {
                    renderer.forceRenderingOff = !enabled;
                }
            }
        }

        /// <summary>
        /// True while the item sits inside a backpack that a character is WEARING, which
        /// is the one case the game hides it in.
        ///
        /// `BackpackReference.IsOnMyBack()` is false for a backpack lying on the ground,
        /// which is exactly the distinction the flag has to follow. A missing reference
        /// (or one whose photon view is gone) is treated as "not worn", because then the
        /// plush is not being carried out of sight either.
        /// </summary>
        private static bool IsWornBackpack(Item item)
        {
            if (item == null)
            {
                return false;
            }
            try
            {
                Optionable<(byte, BackpackReference)> reference = item.backpackReference;
                if (!reference.IsSome)
                {
                    return false;
                }
                BackpackReference backpack = reference.Value.Item2;
                return backpack.exists && backpack.IsOnMyBack();
            }
            catch (Exception ex)
            {
                if (Plugin.Log != null)
                {
                    DiagnosticLog.Warn("Could not read the backpack reference: " + ex.Message);
                }
                return false;
            }
        }

        internal static void HideForGameRule(Item item)
        {
            if (item == null)
            {
                return;
            }
            PlushieItemState itemState = GetItemState(item);
            if (itemState != null)
            {
                itemState.HiddenByGameRule = true;
            }
            Transform root = FindVisualRoot(item);
            if (root != null && root.gameObject.activeSelf)
            {
                root.gameObject.SetActive(false);
            }
        }

        internal static void ClearGameRuleHide(Item item)
        {
            if (item == null)
            {
                return;
            }
            PlushieItemState itemState = item.GetComponent<PlushieItemState>();
            if (itemState != null)
            {
                itemState.HiddenByGameRule = false;
            }
            Transform root = FindVisualRoot(item);
            if (root == null)
            {
                return;
            }
            if (!root.gameObject.activeSelf)
            {
                root.gameObject.SetActive(true);
            }

            // Item.HideRenderers disabled every Renderer under the item, including ours.
            // Re-enabling just the GameObject would leave the replacement invisible, so
            // every renderer under the visual root is switched back on explicitly.
            // (SetVanillaRenderersEnabled cannot do this: it deliberately skips them.)
            Renderer[] renderers = root.GetComponentsInChildren<Renderer>(true);
            for (int i = 0; i < renderers.Length; i++)
            {
                if (renderers[i] != null && !renderers[i].enabled)
                {
                    renderers[i].enabled = true;
                }
            }
        }

        private static float ScaleForState(Item item)
        {
            // The entries are bound before any patch is applied, but this runs from
            // Harmony hooks, so a missing entry must degrade to 1x rather than throw.
            float multiplier = 1f;
            ConfigEntry<float> entry = item.itemState == ItemState.InBackpack
                ? Plugin.BackpackScaleEntry
                : Plugin.WorldScaleEntry;
            if (entry != null)
            {
                multiplier = entry.Value;
            }

            // The .psmesh pipeline already normalises height to the vanilla silhouette,
            // so 1.0 is a 1:1 match. (The game itself shrinks backpack items to 0.5 via
            // Item.forceScale, and the replacement inherits that automatically because it
            // is parented to the item.)
            return Mathf.Clamp(multiplier, 0.2f, 4f);
        }

        /// <summary>
        /// Releases the per-variant meshes, materials and textures.
        ///
        /// Unity never garbage-collects these, so they live exactly as long as the
        /// references do — and these dictionaries are static, which means process
        /// lifetime. That is deliberate while the game runs (the caches are what make a
        /// variant switch instant and let every plush share one mesh), but it also means
        /// nothing would ever free them. Called once from the host's OnDestroy, which is
        /// where a plugin teardown lands; the game is going away anyway, so the point is
        /// to be correct rather than to reclaim memory that the process is about to
        /// return to the OS.
        /// </summary>
        internal static void ReleaseCaches()
        {
            DestroyAll(CachedMeshes);
            DestroyAll(CachedOutlines);
            DestroyAll(CachedMaterials);
            DestroyAll(CachedOutlineMaterials);
            DestroyAll(CachedTextures);

            LoadedAssets.Clear();
            MissingTextures.Clear();
            FailedLoads.Clear();
            TrackedItems.Clear();
        }

        private static void DestroyAll<TKey, TValue>(Dictionary<TKey, TValue> cache)
            where TValue : UnityEngine.Object
        {
            foreach (KeyValuePair<TKey, TValue> pair in cache)
            {
                if (pair.Value != null)
                {
                    UnityEngine.Object.Destroy(pair.Value);
                }
            }
            cache.Clear();
        }
    }
}
