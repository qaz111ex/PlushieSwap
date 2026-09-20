using System;
using HarmonyLib;
using UnityEngine;
using UnityEngine.UI;

namespace PlushieSwap.Patches
{
    /// <summary>
    /// Hooks on Item so the replacement is (re)built whenever the game changes state,
    /// and so the vanilla renderers are hidden exactly when the game hides them.
    ///
    /// Every hook is `[HarmonyWrapSafe]`: these run inside the game's own item logic
    /// (Item.SetState is called synchronously from CharacterItems.Equip), so an escaping
    /// exception would break equipping. A failure must stay inside this mod.
    /// </summary>
    internal static class ItemPatches
    {
        [HarmonyPatch(typeof(Item), "Start")]
        [HarmonyPostfix]
        [HarmonyWrapSafe]
        internal static void Item_Start(Item __instance)
        {
            PlushieModel.ApplyToItem(__instance);
        }

        [HarmonyPatch(typeof(Item), "OnEnable")]
        [HarmonyPostfix]
        [HarmonyWrapSafe]
        internal static void Item_OnEnable(Item __instance)
        {
            PlushieModel.ApplyToItem(__instance);
        }

        [HarmonyPatch(typeof(Item), "SetState")]
        [HarmonyPrefix]
        [HarmonyWrapSafe]
        internal static void Item_SetState_Prefix(Item __instance, ItemState setState)
        {
            // The game hides a plush only while it is in a worn backpack
            // (PutInBackpackRPC -> Item.HideRenderers). Any state other than InBackpack
            // means it should be visible again, so the game-rule hide is cleared there.
            // Clearing on an InBackpack transition would undo a hide the game is about
            // to apply, and would reveal the plush on the player's back.
            if (setState != ItemState.InBackpack)
            {
                PlushieModel.ClearGameRuleHide(__instance);
            }
        }

        [HarmonyPatch(typeof(Item), "SetState")]
        [HarmonyPostfix]
        [HarmonyWrapSafe]
        internal static void Item_SetState_Postfix(Item __instance)
        {
            PlushieModel.ApplyToItem(__instance);
        }

        [HarmonyPatch(typeof(Item), "HideRenderers")]
        [HarmonyPostfix]
        [HarmonyWrapSafe]
        internal static void Item_HideRenderers(Item __instance)
        {
            if (!Variants.IsReplacement)
            {
                return;
            }
            PlushieModel.ApplyToItem(__instance);
            PlushieModel.HideForGameRule(__instance);
        }
    }

    /// <summary>Name and inventory icon replacement.</summary>
    internal static class UiPatches
    {
        // GetItemName() is deliberately NOT patched: it builds its "cooked" variants by
        // calling GetName() and inserting the result into a localized template, so
        // patching GetName alone keeps "Cooked"/"Burnt" prefixes working.

        [HarmonyPatch(typeof(Item), "GetName")]
        [HarmonyPostfix]
        [HarmonyWrapSafe]
        internal static void Item_GetName(Item __instance, ref string __result)
        {
            if (!Variants.IsReplacement || Plugin.RenameEntry == null
                || !Plugin.RenameEntry.Value)
            {
                return;
            }
            if (GameHelpers.IsBingBongItem(__instance))
            {
                __result = Variants.Active.DisplayName;
            }
        }

        [HarmonyPatch(typeof(Item.ItemUIData), "GetIcon")]
        [HarmonyPostfix]
        [HarmonyWrapSafe]
        internal static void ItemUIData_GetIcon(Item.ItemUIData __instance, ref Texture2D __result)
        {
            if (!Variants.IsReplacement || Plugin.ReplaceIconEntry == null
                || !Plugin.ReplaceIconEntry.Value || __instance == null)
            {
                return;
            }
            if (!GameHelpers.IsVanillaBingBongName(__instance.itemName))
            {
                return;
            }
            Texture2D icon = PlushieIcons.GetIcon(Plugin.ActiveVariant);
            if (icon != null)
            {
                __result = icon;
            }
        }

        /// <summary>
        /// Re-apply the icon after the inventory widget has decided to skip it.
        ///
        /// `InventoryItemUI.SetItem` short-circuits when the slot still holds the same
        /// prefab: it refreshes the name and the cook amount and then returns, leaving the
        /// icon texture it cached earlier. The icon here does not come from the prefab (it
        /// comes from the GetIcon postfix above), so after an F7 switch every visible slot
        /// kept the previous plush until its prefab happened to change — dropping the
        /// plush and picking it up again was the only thing that forced it.
        ///
        /// The postfix only touches a slot whose prefab is the plush we replace, so no
        /// other item's icon is disturbed. `icon` and `_itemPrefab` are read through
        /// FieldRefs because they are private.
        ///
        /// It reconciles the icon to whatever the current variant should show, and it does
        /// that for VANILLA too — which is the whole point. Writing a replacement over
        /// whatever was there (what this used to do) can never restore the original icon,
        /// and `SetItem`'s short-circuit never restores it either, because the icon is not
        /// part of what that branch refreshes. So switching back to vanilla brought the
        /// name back on its own but left the last plush's icon on screen.
        ///
        /// For vanilla — or with icon replacement switched off — the wanted icon is the
        /// prefab's own, read through `UIData.GetIcon()`. That is exactly the call the
        /// game's non-short-circuit path makes, and our `GetIcon` patch is inert in those
        /// states, so it returns the original texture.
        /// </summary>
        [HarmonyPatch(typeof(InventoryItemUI), "SetItem")]
        [HarmonyPostfix]
        [HarmonyWrapSafe]
        internal static void InventoryItemUI_SetItem(InventoryItemUI __instance, ItemSlot __0)
        {
            if (__instance == null || __0 == null || __0.prefab == null)
            {
                return;
            }
            if (!GameHelpers.IsBingBongItem(__0.prefab))
            {
                return;
            }
            if (!TryInitInventoryRefs())
            {
                return;
            }

            Item prefab = _inventoryPrefab(__instance);
            if (prefab != __0.prefab)
            {
                return;
            }

            RawImage image = _inventoryIcon(__instance);
            if (image == null || prefab.UIData == null)
            {
                return;
            }

            // What this variant should be showing. A replacement uses the loaded plush
            // icon; vanilla — or icon replacement switched off — uses the prefab's own,
            // which is the texture the game would show if this mod were not installed.
            Texture2D icon = null;
            if (Variants.IsReplacement
                && Plugin.ReplaceIconEntry != null && Plugin.ReplaceIconEntry.Value)
            {
                icon = PlushieIcons.GetIcon(Plugin.ActiveVariant);
            }
            if (icon == null)
            {
                icon = prefab.UIData.GetIcon();
            }
            if (icon == null)
            {
                return;
            }

            if (image.texture != icon)
            {
                image.texture = icon;
            }
            if (!image.enabled)
            {
                image.enabled = true;
            }
        }

        /// <summary>
        /// The two private widget fields, resolved on demand.
        ///
        /// `AccessTools.FieldRefAccess` throws when the field is missing, and a static
        /// initializer would turn that into a TypeInitializationException on the first
        /// patch call — where `[HarmonyWrapSafe]` swallows it. Resolving lazily means the
        /// failure can be reported once instead of silently disabling the icon refresh.
        /// </summary>
        private static AccessTools.FieldRef<InventoryItemUI, RawImage> _inventoryIcon;
        private static AccessTools.FieldRef<InventoryItemUI, Item> _inventoryPrefab;
        private static bool _inventoryRefsReady;

        private static bool TryInitInventoryRefs()
        {
            if (_inventoryRefsReady)
            {
                return _inventoryIcon != null && _inventoryPrefab != null;
            }
            _inventoryRefsReady = true;
            try
            {
                _inventoryIcon = AccessTools.FieldRefAccess<InventoryItemUI, RawImage>("icon");
                _inventoryPrefab = AccessTools.FieldRefAccess<InventoryItemUI, Item>("_itemPrefab");
                return true;
            }
            catch (Exception ex)
            {
                DiagnosticLog.Error("Could not resolve InventoryItemUI's private fields, so the "
                                    + "icon will not follow an in-game plush switch: " + ex);
                _inventoryIcon = null;
                _inventoryPrefab = null;
                return false;
            }
        }
    }
}
