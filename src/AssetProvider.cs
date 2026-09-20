using System;
using System.IO;
using UnityEngine;

namespace PlushieSwap
{
    /// <summary>
    /// Resolves the mod's data files.
    ///
    /// The model, shading and icon files are embedded in the DLL, so the mod ships as a
    /// single file and nothing has to be unpacked at runtime. If a file with the same
    /// name sits next to the DLL it wins, which lets a custom model be dropped in
    /// without rebuilding the plugin.
    /// </summary>
    internal static class AssetProvider
    {
        /// <summary>Where the file came from, for logging.</summary>
        internal enum Source
        {
            Missing,
            LooseFile,
            Embedded
        }

        /// <summary>Reads a data file, preferring a loose file over the embedded copy.</summary>
        internal static byte[] Read(string fileName, out Source source)
        {
            return Read(fileName, out source, false);
        }

        /// <summary>
        /// Reads a data file, preferring a loose file over the embedded copy.
        ///
        /// `embeddedOnly` skips the loose file on disk. That is what a caller uses to
        /// retry a file that turned out to be corrupt: the embedded copy is the
        /// known-good fallback, and without the retry a bad loose file would disable a
        /// variant until the game is restarted, because the per-variant "failed" caches
        /// are never expiring.
        /// </summary>
        internal static byte[] Read(string fileName, out Source source, bool embeddedOnly)
        {
            source = Source.Missing;
            if (string.IsNullOrEmpty(fileName))
            {
                return null;
            }

            if (!embeddedOnly)
            {
                try
                {
                    string path = Path.Combine(Plugin.AssetDirectory, fileName);
                    if (File.Exists(path))
                    {
                        source = Source.LooseFile;
                        return File.ReadAllBytes(path);
                    }
                }
                catch (Exception ex)
                {
                    DiagnosticLog.Warn("Could not read " + fileName + " from disk: " + ex.Message);
                }
            }

            byte[] embedded = EmbeddedAssets.Get(fileName);
            if (embedded != null)
            {
                source = Source.Embedded;
                return embedded;
            }

            return null;
        }

        /// <summary>
        /// Decodes a PNG into a texture, optionally from the embedded copy only.
        ///
        /// The texture is created with `new Texture2D(2, 2, TextureFormat.RGBA32, false)`:
        /// the fourth argument is `mipChain`, so passing false is what gives the type no
        /// mip levels at all. `Apply(updateMipmaps: false, makeNoLongerReadable: true)`
        /// then uploads the single full-resolution level and releases the CPU-side copy,
        /// so Unity can never generate a chain for it later (a quality change or a
        /// readback would otherwise trigger exactly that).
        ///
        /// That matters for the shipped shading palette: it is 294x1 with colour blocks
        /// only a few dozen pixels wide, so any mip level would average the cream body,
        /// the dress and the eyes into a dirty grey-brown, which is the "goes muddy in
        /// the distance" artifact. The 512x512 icons are drawn by a `RawImage` (verified
        /// in `Item.ItemUIData.GetIcon`'s consumers: `InventoryItemUI.icon` and
        /// `BackpackWheel*` are all `RawImage`), which also wants the crisp
        /// full-resolution level, never a mip.
        ///
        /// `filterMode = FilterMode.Bilinear` is set for the same reason: the palette is
        /// sampled with a smooth gradient along its axis, so point sampling would band it.
        /// </summary>
        internal static Texture2D ReadTexture(string fileName, string textureName,
                                              out Source source, bool embeddedOnly)
        {
            byte[] bytes = Read(fileName, out source, embeddedOnly);
            if (bytes == null)
            {
                DiagnosticLog.Warn("Texture not found: " + fileName);
                return null;
            }

            Texture2D texture = null;
            try
            {
                texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                if (!texture.LoadImage(bytes, false))
                {
                    DiagnosticLog.Warn("Failed to decode texture: " + fileName);
                    UnityEngine.Object.Destroy(texture);
                    return null;
                }

                texture.name = textureName;
                texture.wrapMode = TextureWrapMode.Clamp;
                texture.filterMode = FilterMode.Bilinear;
                texture.anisoLevel = 0;

                // The palette is sampled along a 294 pixel axis; without this a distance
                // mip chain would blend the cream body, the dress and the eyes into a
                // dirty average. updateMipmaps:false keeps the single full-res level,
                // makeNoLongerReadable:true frees the CPU-side copy Unity would otherwise
                // keep around and, on a quality change, use to build mips.
                texture.Apply(false, true);

                DiagnosticLog.Diag("Loaded " + fileName + " (" + source + ", "
                                   + texture.width + "x" + texture.height + ")");
                return texture;
            }
            catch (Exception ex)
            {
                // A partially created texture would otherwise leak: Unity never collects
                // Texture2D objects on its own.
                if (texture != null)
                {
                    UnityEngine.Object.Destroy(texture);
                }
                DiagnosticLog.Warn("Failed to decode " + fileName + ": " + ex.Message);
                return null;
            }
        }
    }
}
