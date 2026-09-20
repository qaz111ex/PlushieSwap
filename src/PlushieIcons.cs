using System;
using System.Collections.Generic;
using UnityEngine;

namespace PlushieSwap
{
    /// <summary>Loads the inventory icon for each plush.</summary>
    internal static class PlushieIcons
    {
        private static readonly Dictionary<PlushieVariant, Texture2D> Cache =
            new Dictionary<PlushieVariant, Texture2D>();
        private static readonly HashSet<PlushieVariant> Failed = new HashSet<PlushieVariant>();

        internal static Texture2D GetIcon(PlushieVariant variant)
        {
            if (variant == PlushieVariant.Vanilla)
            {
                return null;
            }

            Texture2D cached;
            if (Cache.TryGetValue(variant, out cached))
            {
                return cached;
            }
            if (Failed.Contains(variant))
            {
                return null;
            }

            VariantDefinition def = Variants.Get(variant);
            AssetProvider.Source source;
            Texture2D texture = AssetProvider.ReadTexture(def.IconFile,
                                                          "PlushieSwap_Icon_" + variant,
                                                          out source, false);

            // Same retry as the mesh and shading loads: a loose icon that fails to decode
            // must not poison `Failed` for the rest of the session while the embedded copy
            // in the DLL is fine. Only the embedded copy is retried.
            if (texture == null && source == AssetProvider.Source.LooseFile)
            {
                DiagnosticLog.Warn("Loose " + def.IconFile
                                  + " could not be used; retrying the embedded copy.");
                texture = AssetProvider.ReadTexture(def.IconFile,
                                                    "PlushieSwap_Icon_" + variant,
                                                    out source, true);
            }

            if (texture == null)
            {
                Failed.Add(variant);
                return null;
            }

            Cache[variant] = texture;
            return texture;
        }
    }
}
