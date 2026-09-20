using System;

namespace PlushieSwap
{
    /// <summary>Everything that differs between replacement variants.</summary>
    internal sealed class VariantDefinition
    {
        public PlushieVariant Variant;
        public string MeshFile;
        public string TextureFile;
        public string IconFile;
        public string DisplayNameEn;
        public string DisplayNameZh;

        public string DisplayName
        {
            get { return UiHelpers.IsChinese() ? DisplayNameZh : DisplayNameEn; }
        }
    }

    internal static class Variants
    {
        // The .psmesh pipeline authors every model directly in the game's item-local
        // space: scaled to the vanilla plush silhouette, turned to face the player,
        // and carrying its own "Hand_L" / "Hand_R" hold points. Nothing else has to be
        // configured here.
        internal static readonly VariantDefinition[] All =
        {
            new VariantDefinition
            {
                Variant = PlushieVariant.Vanilla,
                MeshFile = null,
                TextureFile = null,
                IconFile = null,
                DisplayNameEn = "Bing Bong",
                DisplayNameZh = "Bing Bong"
            },
            new VariantDefinition
            {
                Variant = PlushieVariant.Miffy,
                MeshFile = "miffy.psmesh",
                TextureFile = "miffy_shading.png",
                IconFile = "icon_miffy.png",
                DisplayNameEn = "Miffy",
                DisplayNameZh = "米菲兔"
            },
            new VariantDefinition
            {
                Variant = PlushieVariant.ZichaoXiong,
                MeshFile = "zichaoxiong.psmesh",
                TextureFile = "zichaoxiong_shading.png",
                IconFile = "icon_zichaoxiong.png",
                DisplayNameEn = "Zichao Xiong",
                DisplayNameZh = "自嘲熊"
            }
        };

        internal static VariantDefinition Get(PlushieVariant variant)
        {
            for (int i = 0; i < All.Length; i++)
            {
                if (All[i].Variant == variant)
                {
                    return All[i];
                }
            }
            return All[1];
        }

        internal static VariantDefinition Active
        {
            get { return Get(Plugin.ActiveVariant); }
        }

        internal static bool IsReplacement
        {
            get { return Plugin.ActiveVariant != PlushieVariant.Vanilla; }
        }
    }
}
