using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace PlushieSwap
{
    /// <summary>
    /// Reflection helpers so the plugin keeps working if a field is renamed,
    /// plus the one place that decides what counts as "the BingBong item".
    /// </summary>
    internal static class GameHelpers
    {
        private static FieldInfo _allItemsField;
        private static FieldInfo _activeItemsField;
        private static bool _itemsFieldsSearched;

        /// <summary>
        /// Every live Item in the scene.
        ///
        /// `Item.ALL_ITEMS` is the registry that matters: it is appended in Awake and
        /// removed in OnDestroy, so it holds *every* item for its whole life. The
        /// `ALL_ACTIVE_ITEMS` list the game also keeps drops items after 30 seconds of
        /// inactivity (Item.UpdateEntryInActiveList), so a plush lying on the ground
        /// would disappear from it — and a replacement built for that plush could then
        /// never be found and cleaned up. `ALL_ACTIVE_ITEMS` is only a fallback.
        ///
        /// `ALL_ITEMS` is cleared by `GameHandler.OnSceneLoaded` when the loaded scene is
        /// not a gameplay scene (GameHandler.cs:197-200), so "for its whole life" is true
        /// per gameplay scene rather than per process. That is why the third fallback
        /// exists: between a scene clear and the first item's Awake the two lists are
        /// empty, and a scan of the live objects is the only thing that still finds them.
        /// </summary>
        internal static IReadOnlyList<Item> AllItems()
        {
            if (!_itemsFieldsSearched)
            {
                _itemsFieldsSearched = true;
                const BindingFlags flags = BindingFlags.Static | BindingFlags.Public
                                           | BindingFlags.NonPublic;
                _allItemsField = typeof(Item).GetField("ALL_ITEMS", flags);
                _activeItemsField = typeof(Item).GetField("ALL_ACTIVE_ITEMS", flags);
            }

            List<Item> list = ReadItemList(_allItemsField);
            if (list != null && list.Count > 0)
            {
                return list;
            }

            list = ReadItemList(_activeItemsField);
            if (list != null && list.Count > 0)
            {
                return list;
            }

            List<Item> scan = new List<Item>();
            try
            {
                Item[] found = UnityEngine.Object.FindObjectsOfType<Item>();
                for (int i = 0; i < found.Length; i++)
                {
                    if (found[i] != null)
                    {
                        scan.Add(found[i]);
                    }
                }
            }
            catch
            {
                // ignore
            }
            return scan;
        }

        private static List<Item> ReadItemList(FieldInfo field)
        {
            if (field == null)
            {
                return null;
            }
            try
            {
                return field.GetValue(null) as List<Item>;
            }
            catch
            {
                return null;
            }
        }

        /// <summary>
        /// Identify the BingBong plush. Its GameObject is named "BingBong" and the item
        /// name shown in the UI is "Bing Bong"; both are checked so a rename by another
        /// mod cannot silently disable this one.
        ///
        /// The object name must START with "BingBong", not merely contain it. The game
        /// ships several other BingBong assets — `Bugfix_BingBong` (a decoration mesh),
        /// `Medallion_BingBong`, `BingBongMesh`, `BingBongSFX`-style audio holders — and a
        /// contains-check would claim any of them the moment they gained an Item. A
        /// full-asset scan (MonoBehaviour m_Script pointers resolved against the
        /// MonoScript table in globalgamemanagers.assets) finds 373 GameObjects carrying
        /// an `Item` component across the whole game, of which exactly three are BingBong:
        /// "BingBong" (resources.assets 4284), "BingBong_Prop Variant"
        /// (resources.assets 11133) and the level3 scene instance (path_id 6161). The
        /// prefix keeps every real one, including the runtime clone "BingBong(Clone)".
        ///
        /// Note that the two resources.assets prefabs are NOT the same size — `BingBong`
        /// is 1.1884 tall while `BingBong_Prop Variant` is 0.9635, the height this mod's
        /// models are built to. Both share the same hand anchors, so the hold offset is
        /// correct for either; only the silhouette match is approximate for the former.
        /// </summary>
        internal static bool IsBingBongItem(Item item)
        {
            if (item == null || item.gameObject == null)
            {
                return false;
            }

            string objectName = item.gameObject.name;
            if (!string.IsNullOrEmpty(objectName)
                && (objectName.StartsWith(ObjectNamePrefix, StringComparison.OrdinalIgnoreCase)
                    || objectName.StartsWith(SpacedObjectNamePrefix, StringComparison.OrdinalIgnoreCase)))
            {
                return true;
            }

            string itemName = TryGetItemName(item);
            if (!string.IsNullOrEmpty(itemName)
                && itemName.IndexOf("Bing", StringComparison.OrdinalIgnoreCase) >= 0
                && itemName.IndexOf("Bong", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return true;
            }

            return false;
        }

        /// <summary>The name every BingBong prefab and its Photon clone start with.</summary>
        private const string ObjectNamePrefix = "BingBong";

        /// <summary>
        /// The spaced spelling, kept for a prefab renamed by another mod. It starts the
        /// name for the same reason: it must not match `Medallion_Bing Bong`.
        /// </summary>
        private const string SpacedObjectNamePrefix = "Bing Bong";

        /// <summary>Read the item's display name without triggering localization.</summary>
        internal static string TryGetItemName(Item item)
        {
            if (item == null)
            {
                return null;
            }

            try
            {
                Item.ItemUIData ui = item.UIData;
                if (ui != null && !string.IsNullOrEmpty(ui.itemName))
                {
                    return ui.itemName;
                }
            }
            catch
            {
                // ignore
            }
            return null;
        }

        /// <summary>
        /// Matches the vanilla plush's raw UIData.itemName. The game builds the
        /// localization key as "NAME_" + itemName, so this is the unprefixed key.
        /// </summary>
        internal static bool IsVanillaBingBongName(string key)
        {
            if (string.IsNullOrEmpty(key))
            {
                return false;
            }

            string compact = key.Replace(" ", string.Empty);
            if (compact.Equals("BingBong", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }

            // Tolerate a "Bing Bong" / "bing bong" spelling without matching unrelated items.
            return key.IndexOf("Bing", StringComparison.OrdinalIgnoreCase) >= 0
                   && key.IndexOf("Bong", StringComparison.OrdinalIgnoreCase) >= 0;
        }
    }

    internal static class UiHelpers
    {
        private static FieldInfo _languageField;
        private static bool _languageFieldSearched;

        /// <summary>
        /// True when the game runs with a Chinese UI language.
        ///
        /// The value is read live rather than cached. It used to be cached and only
        /// invalidated when the player cycled the plush with F7 — but cycling the plush
        /// does not change the language, and changing the language in the menu had no hook
        /// at all, so a player who switched to Chinese kept seeing "Miffy" / "Zichao Xiong"
        /// until they happened to press F7 or restarted. The read is one cached reflection
        /// field lookup plus a short string comparison, and it only happens when a display
        /// name is actually produced (Item.GetName, which is not a per-frame path), so the
        /// cost of not caching is negligible next to being wrong.
        /// </summary>
        internal static bool IsChinese()
        {
            try
            {
                if (!_languageFieldSearched)
                {
                    _languageFieldSearched = true;
                    _languageField = typeof(LocalizedText).GetField(
                        "CURRENT_LANGUAGE",
                        BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
                }

                object language = _languageField != null ? _languageField.GetValue(null) : null;
                if (language == null)
                {
                    return false;
                }
                return language.ToString().IndexOf("Chinese", StringComparison.OrdinalIgnoreCase) >= 0;
            }
            catch
            {
                return false;
            }
        }
    }
}
