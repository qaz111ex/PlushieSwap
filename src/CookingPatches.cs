using System;
using System.Collections.Generic;
using HarmonyLib;
using UnityEngine;

namespace PlushieSwap.Patches
{
    /// <summary>
    /// Keeps the game's cooking-tint bookkeeping away from this mod's renderers.
    ///
    /// The game bakes a cook tint by reading and writing `_Tint` on every renderer under
    /// an item:
    ///
    ///     ItemCooking.UpdateCookedBehavior -> renderers[i].material.GetColor("_Tint")
    ///     ItemCooking.CookVisually         -> ...SetColor("_Tint", tint)
    ///     BackpackOnBackVisuals.InitRenderers / CookVisually -> same
    ///
    /// `Material.GetColor` on a shader that does not declare `_Tint` logs a Unity error
    /// ("...doesn't have a color property '_Tint'") every single time. The outline shell
    /// must use a shader that culls FRONT faces, and the only shipped shaders with
    /// `_Cull` do not declare `_Tint`, so those errors were unavoidable while the mod's
    /// renderers were part of those lists.
    ///
    /// The fix is to leave them out of the lists. The list is built once per item and
    /// cached in private fields, so a single prefix per entry point is enough: it
    /// populates the cache from the item's own renderers minus this mod's, then marks the
    /// setup done so the game skips its own (error-logging) pass.
    ///
    /// This is the approach the working ScallionMiku mod uses for the same item. The
    /// cooking look is not lost by it: the item misses `_Tint` writes only, and
    /// `PlushieModel.ApplyCookTint` reproduces the same browning on the replacement's own
    /// renderer through a per-instance `MaterialPropertyBlock` (never the shared material).
    ///
    /// The other places in the game that read or write `_Tint` do not need covering.
    /// A full-tree search for the `"_Tint"` literal finds six sites; two are the item
    /// paths above, and the remaining four are:
    /// `Peak/ScoutmasterSoulPillar.cs:161-162`, `SetRockColors.cs:18`,
    /// `sc.posteffects.runtime/SCPE/RefractionRenderer.cs:40` and one in the shader
    /// property tables. Every one of them operates on a scene object or a global
    /// post-processing material, never on a renderer inside an item's subtree, so none
    /// can reach a renderer this mod created. (Checked so this is not re-investigated.)
    /// </summary>
    internal static class CookingPatches
    {
        // These field references are resolved lazily rather than in a static initializer.
        //
        // `AccessTools.FieldRefAccess<T, F>("name")` THROWS when the field is missing. In a
        // static initializer that becomes a TypeInitializationException raised on the first
        // access — which happens inside a patch body, and every patch body here is
        // `[HarmonyWrapSafe]` (Harmony wraps it in try/catch). The failure would therefore
        // be swallowed: the `_Tint` fix would silently stop working and Unity's
        // "doesn't have a color property '_Tint'" errors would come back, with nothing in
        // the log pointing at this mod. Resolving on demand lets the failure be reported.
        private static AccessTools.FieldRef<ItemCooking, Renderer[]> _itemRenderers;
        private static AccessTools.FieldRef<ItemCooking, Color[]> _itemTints;
        private static AccessTools.FieldRef<ItemCooking, bool> _itemSetup;

        private static AccessTools.FieldRef<BackpackOnBackVisuals, MeshRenderer[]> _backpackRenderers;
        private static AccessTools.FieldRef<BackpackOnBackVisuals, Color[]> _backpackTints;

        private static bool _itemRefsReady;
        private static bool _backpackRefsReady;

        private static bool TryInitItemRefs()
        {
            if (_itemRefsReady)
            {
                return _itemRenderers != null;
            }
            _itemRefsReady = true;
            try
            {
                _itemRenderers = AccessTools.FieldRefAccess<ItemCooking, Renderer[]>("renderers");
                _itemTints = AccessTools.FieldRefAccess<ItemCooking, Color[]>("defaultTints");
                _itemSetup = AccessTools.FieldRefAccess<ItemCooking, bool>("setup");
                return true;
            }
            catch (Exception ex)
            {
                DiagnosticLog.Error("CookingPatches could not resolve ItemCooking's private fields, "
                                    + "so the cook-tint fix is disabled and Unity will log '_Tint' "
                                    + "errors again: " + ex);
                _itemRenderers = null;
                _itemTints = null;
                _itemSetup = null;
                return false;
            }
        }

        private static bool TryInitBackpackRefs()
        {
            if (_backpackRefsReady)
            {
                return _backpackRenderers != null;
            }
            _backpackRefsReady = true;
            try
            {
                _backpackRenderers = AccessTools.FieldRefAccess<BackpackOnBackVisuals, MeshRenderer[]>("renderers");
                _backpackTints = AccessTools.FieldRefAccess<BackpackOnBackVisuals, Color[]>("defaultTints");
                return true;
            }
            catch (Exception ex)
            {
                DiagnosticLog.Error("CookingPatches could not resolve BackpackOnBackVisuals's private "
                                    + "fields, so the backpack cook-tint fix is disabled: " + ex);
                _backpackRenderers = null;
                _backpackTints = null;
                return false;
            }
        }

        /// <summary>
        /// Populate the item's cached renderer list once, without this mod's renderers.
        ///
        /// Setting `setup` is what matters: the base method skips its whole renderer
        /// discovery block when it is already true, which is exactly the block that reads
        /// `_Tint` and logs.
        /// </summary>
        [HarmonyPatch(typeof(ItemCooking), "UpdateCookedBehavior")]
        [HarmonyPrefix]
        [HarmonyWrapSafe]
        internal static void ItemCooking_UpdateCookedBehavior(ItemCooking __instance)
        {
            if (__instance == null || !TryInitItemRefs() || _itemSetup(__instance))
            {
                return;
            }

            Renderer[] all = __instance.GetComponentsInChildren<MeshRenderer>();
            SkinnedMeshRenderer[] skinned =
                __instance.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            List<Renderer> keep = new List<Renderer>(all.Length + skinned.Length);
            for (int i = 0; i < all.Length; i++)
            {
                if (all[i] != null && !PlushieModel.IsPlushieTransform(all[i].transform))
                {
                    keep.Add(all[i]);
                }
            }
            for (int i = 0; i < skinned.Length; i++)
            {
                if (skinned[i] != null && !PlushieModel.IsPlushieTransform(skinned[i].transform))
                {
                    keep.Add(skinned[i]);
                }
            }

            Renderer[] list = keep.ToArray();
            _itemRenderers(__instance) = list;
            _itemTints(__instance) = ReadTints(list);
            _itemSetup(__instance) = true;
        }

        /// <summary>Same for the backpack's own copy of the plush.</summary>
        [HarmonyPatch(typeof(BackpackOnBackVisuals), "InitRenderers")]
        [HarmonyPrefix]
        [HarmonyWrapSafe]
        internal static bool BackpackOnBackVisuals_InitRenderers(BackpackOnBackVisuals __instance)
        {
            if (__instance == null || !TryInitBackpackRefs())
            {
                return true;
            }

            MeshRenderer[] all = __instance.GetComponentsInChildren<MeshRenderer>();
            List<MeshRenderer> keep = new List<MeshRenderer>(all.Length);
            for (int i = 0; i < all.Length; i++)
            {
                if (all[i] != null && !PlushieModel.IsPlushieTransform(all[i].transform))
                {
                    keep.Add(all[i]);
                }
            }

            MeshRenderer[] list = keep.ToArray();
            _backpackRenderers(__instance) = list;
            _backpackTints(__instance) = ReadTints(list);
            return false;
        }

        /// <summary>
        /// Read `_Tint` where the shader actually declares it, and neutral elsewhere.
        ///
        /// The vanilla materials do declare it, so they behave exactly as before; a
        /// stray material from another mod must not be able to log an error from here.
        /// </summary>
        private static Color[] ReadTints(Renderer[] renderers)
        {
            Color[] tints = new Color[renderers.Length];
            for (int i = 0; i < renderers.Length; i++)
            {
                Renderer renderer = renderers[i];
                if (renderer == null)
                {
                    tints[i] = Color.white;
                    continue;
                }

                Material material = renderer.material;
                if (material != null && material.HasProperty(TintId))
                {
                    tints[i] = material.GetColor(TintId);
                }
                else
                {
                    tints[i] = Color.white;
                }
            }
            return tints;
        }

        private static readonly int TintId = Shader.PropertyToID("_Tint");
    }
}
