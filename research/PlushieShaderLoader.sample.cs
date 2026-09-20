// Research-only sample: how PlushieModel.cs would load the custom outline shader.
//
// This file is NOT compiled into the mod. It documents the exact drop-in for
// src/PlushieModel.cs so the production edit stays small and reviewable.
//
// Facts this relies on, all verified against the shipped Unity 6000.3.15f1
// player and the installed BepInEx 5.4.23.3 (Mono, not IL2CPP):
//
//   * Shader.CreateFromString does NOT exist in Unity 6. Compiled player and
//     UnityEngine.CoreModule / ShaderRuntimeModule expose only Shader.Find,
//     Shader.FindBuiltin and Shader.CreateFromCompiledData. The old
//     `new Material(shaderSource)` constructor is [Obsolete] with the message
//     "Creating materials from shader source string is no longer supported."
//     So option (c) in the brief is impossible without an editor.
//   * Shader.Find only finds shaders already in the player. A custom shader has
//     to arrive as an asset, and the only runtime-loadable asset container is an
//     AssetBundle (AssetBundle.LoadFromFile/LoadFromMemory exist and are
//     supported in the Mono player).
//   * AssetBundles are not forward/backward compatible across Unity versions.
//     It MUST be built with 6000.3.x, ideally the same 6000.3.15f1 build.
// So the recommended route is (b): ship a tiny AssetBundle next to the DLL,
// load it once, and cache the Shader. (a) is only a fallback and cannot give a
// screen-space width because no stock shader offsets along clip-space normals.

using System;
using System.IO;
using UnityEngine;

namespace PlushieSwap
{
    internal static class PlushieShaderLoader
    {
        internal const string OutlineShaderName = "PlushieSwap/Outline";
        internal const string OutlineBundleFile = "plushieoutline.bundle";

        private static Shader _outlineShader;
        private static bool _attempted;

        /// <summary>
        /// Returns the packaged outline shader, or null when the bundle is not
        /// present. Callers must keep the existing URP/Lit fallback for null.
        /// </summary>
        internal static Shader GetOutlineShader()
        {
            if (_attempted)
            {
                return _outlineShader;
            }
            _attempted = true;

            // A loose file beside the DLL wins, matching AssetProvider's rules.
            string path = Path.Combine(Plugin.AssetDirectory, OutlineBundleFile);
            AssetBundle bundle = null;
            try
            {
                if (File.Exists(path))
                {
                    bundle = AssetBundle.LoadFromFile(path);
                }
                else
                {
                    // Fallback: an AssetBundle embedded in the DLL. Ship it as an
                    // EmbeddedResource and load with LoadFromMemory, the same way
                    // the models are embedded today.
                    // byte[] bytes = EmbeddedAssets.Get(OutlineBundleFile);
                    // if (bytes != null) bundle = AssetBundle.LoadFromMemory(bytes);
                }

                if (bundle == null)
                {
                    Plugin.Log.LogWarning("Outline bundle missing (" + OutlineBundleFile
                                          + "); using the object-space fallback outline.");
                    return null;
                }

                _outlineShader = bundle.LoadAsset<Shader>(OutlineShaderName)
                                 ?? bundle.LoadAsset<Shader>("PlushieOutline");
                if (_outlineShader == null)
                {
                    // Older bundles may not carry the name; try every shader.
                    Shader[] all = bundle.LoadAllAssets<Shader>();
                    for (int i = 0; i < all.Length; i++)
                    {
                        Plugin.Log.LogInfo("Bundle shader: " + all[i].name);
                    }
                }

                if (_outlineShader == null || !_outlineShader.isSupported)
                {
                    Plugin.Log.LogWarning("Outline shader unusable; falling back.");
                    _outlineShader = null;
                    return null;
                }

                Plugin.Log.LogInfo("Loaded outline shader from " + OutlineBundleFile);
                return _outlineShader;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError("Failed to load " + OutlineBundleFile + ": " + ex);
                _outlineShader = null;
                return null;
            }
            finally
            {
                // The Shader object stays alive after the bundle is unloaded only
                // if something references it, so do NOT unload here; keep the
                // bundle alive for the process lifetime and let it be collected
                // with the plugin.
                GC.KeepAlive(bundle);
            }
        }

        /// <summary>
        /// Builds the ink material. Mirrors PlushieModel.GetOutlineMaterial but
        /// sets the screen-space width properties instead of relying on the
        /// pre-inflated shell geometry.
        /// </summary>
        internal static Material CreateOutlineMaterial(PlushieVariant variant, Color ink)
        {
            Shader shader = GetOutlineShader();

            bool screenSpace = shader != null;
            if (!screenSpace)
            {
                // Existing behaviour: URP/Lit, front-face culled, the object-space
                // shell already carries the width.
                shader = Shader.Find("Universal Render Pipeline/Lit");
                if (shader == null)
                {
                    return null;
                }
            }

            Material material = new Material(shader)
            {
                name = "PlushieSwap_Ink_" + variant
            };

            if (screenSpace)
            {
                // The bundled shader's own properties.
                material.SetColor("_OutlineColor", ink);
                material.SetFloat("_OutlineWidth", 2.5f);
                material.SetFloat("_OutlineWidthScale", 1.0f);
                // outline_thickness * target_height from tools/build_meshes.py:
                // 0.0075 * 0.9635. Regenerate this number if the pipeline changes.
                material.SetFloat("_OutlineBakedThickness", 0.0075f * 0.9635f);
                material.SetFloat("_OutlineZOffset", 0.0005f);
                material.SetFloat("_Cull", (float)CullMode.Front);
                material.renderQueue = (int)RenderQueue.Geometry;
                return material;
            }

            // ---- fallback path (unchanged from the current implementation) ----
            if (!material.HasProperty("_Cull") && !material.HasProperty("_CullMode"))
            {
                UnityEngine.Object.Destroy(material);
                return null;
            }
            if (material.HasProperty("_BaseColor")) material.SetColor("_BaseColor", ink);
            if (material.HasProperty("_Color")) material.SetColor("_Color", ink);
            if (material.HasProperty("_Smoothness")) material.SetFloat("_Smoothness", 0f);
            if (material.HasProperty("_Metallic")) material.SetFloat("_Metallic", 0f);
            if (material.HasProperty("_Cull")) material.SetFloat("_Cull", (float)CullMode.Front);
            if (material.HasProperty("_CullMode")) material.SetFloat("_CullMode", (float)CullMode.Front);
            material.renderQueue = (int)RenderQueue.Geometry;
            return material;
        }
    }
}

// ---------------------------------------------------------------------------
// How to build the bundle (do this once, on the user's machine)
// ---------------------------------------------------------------------------
//
// 1. Install Unity 6000.3.15f1 via Unity Hub (match the game exactly).
// 2. New 3D (URP) project, then copy shaders/PlushieOutline.shader into
//    Assets/PlushieOutline.shader.
// 3. Add an Editor script that builds the bundle:
//
//      [MenuItem("PlushieSwap/Build Outline Bundle")]
//      static void Build()
//      {
//          var build = new AssetBundleBuild
//          {
//              assetBundleName = "plushieoutline.bundle",
//              assetNames = new[] { "Assets/PlushieOutline.shader" },
//          };
//          BuildPipeline.BuildAssetBundles(
//              "AssetsBundles",
//              new[] { build },
//              BuildAssetBundleOptions.None,
//              BuildTarget.StandaloneWindows64);
//      }
//
// 4. Put the produced "plushieoutline.bundle" next to PlushieSwap.dll (or embed
//    it with tools/embed_assets.py).
//
// Verification inside the game:
//   BepInEx console should print "Loaded outline shader from plushieoutline.bundle".
//   At the default 2.5 px the line is visibly even at every distance, and the
//   backpack's 0.5x scale no longer halves it.
