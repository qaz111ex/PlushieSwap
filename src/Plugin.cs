using System;
using System.IO;
using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using HarmonyLib;
using UnityEngine;

namespace PlushieSwap
{
    /// <summary>Which model BingBong is replaced with.</summary>
    public enum PlushieVariant
    {
        Vanilla = 0,
        Miffy = 1,
        ZichaoXiong = 2
    }

    [BepInPlugin(Guid, "Plushie Swap", DisplayVersion)]
    public class Plugin : BaseUnityPlugin
    {
        public const string Guid = "com.zhuanban.peak.plushieswap";

        /// <summary>
        /// The mod's version, in one place.
        ///
        /// The BepInPlugin attribute above refers to this constant rather than repeating
        /// the literal, so the version the loader reports and the version the log prints
        /// cannot disagree. `PlushieSwap.csproj`'s &lt;Version&gt; and the Thunderstore
        /// manifest are the other two places a version appears; `tools/package_release.py`
        /// reads this constant and refuses to package when the csproj disagrees with it,
        /// which is what stops the three from drifting apart.
        /// </summary>
        public const string DisplayVersion = "1.1.1";

        internal static ManualLogSource Log;
        internal static Plugin Instance;

        internal static ConfigEntry<PlushieVariant> VariantEntry;
        internal static ConfigEntry<float> WorldScaleEntry;
        internal static ConfigEntry<float> BackpackScaleEntry;
        internal static ConfigEntry<float> HoldOffsetEntry;
        internal static ConfigEntry<bool> VerboseLogEntry;
        internal static ConfigEntry<bool> RenameEntry;
        internal static ConfigEntry<bool> ReplaceIconEntry;
        internal static ConfigEntry<string> ShaderOverrideEntry;
        internal static ConfigEntry<KeyCode> CycleHotkeyEntry;
        internal static ConfigEntry<float> OutlineWidthEntry;

        /// <summary>
        /// Marks which generation of defaults the config file was written with, so a
        /// changed default can be migrated exactly once instead of silently never
        /// applying. This is what made the outline width fix invisible: the code default
        /// became 5 px, but the file still said 2.5 and BepInEx always prefers the file.
        /// </summary>
        internal static ConfigEntry<int> ConfigVersionEntry;

        /// <summary>Bump when a default value changes in a way that should migrate.</summary>
        private const int CurrentConfigVersion = 3;

        internal static PlushieVariant ActiveVariant = PlushieVariant.ZichaoXiong;

        /// <summary>
        /// One entry per migration step. `From` is inclusive, `To` exclusive, so a step
        /// runs while `From <= recordedVersion < To`.
        ///
        /// `From` for the first step is 0, NOT 1: a config file written before the
        /// version marker existed binds `Config Version` to its default of 0 (BepInEx
        /// never re-reads a value it has already written), so 0 is the normal state of
        /// exactly the files the first migration is meant to fix. `From = 1` would skip
        /// every one of them, which is the same "changed default never reaches an
        /// existing user" trap this whole mechanism exists to close.
        ///
        /// ADDING A MIGRATION: append a new entry with `From` equal to the previous
        /// step's `To` and `To` equal to the new CurrentConfigVersion, then raise
        /// CurrentConfigVersion to match. NEVER edit or reorder an existing entry — an
        /// entry is a historical fact about what a released build wrote to the file, and
        /// changing it would either re-run a migration or skip one. Do not add a
        /// catch-all step: a version above CurrentConfigVersion means the file came from
        /// a newer build and its values must be left alone.
        /// </summary>
        private sealed class ConfigMigration
        {
            public int From;
            public int To;
            public Action Apply;
        }

        /// <summary>
        /// Applies changed defaults to an existing config file, once per entry in the
        /// migration table below.
        ///
        /// BepInEx never revisits a value already present in the file, so a default that
        /// is changed in code has no effect on anyone who has already run the mod. That
        /// is exactly how "the outline is still 2.5 px" happened after the default moved
        /// to 5. The version marker makes each migration run once and then stay quiet, and
        /// the table makes the next one a one-line append instead of a new `if`.
        /// </summary>
        private void MigrateConfigDefaults()
        {
            int version = ConfigVersionEntry.Value;
            if (version >= CurrentConfigVersion)
            {
                return;
            }

            ConfigMigration[] migrations =
            {
                // v0 -> v2 (the marker's own introduction): the old hairline default
                // (2.5 px) was mistaken for a regression, so it is moved to the intended
                // 5 px. Only the exact old default is touched; a value the player chose
                // themselves is left alone.
                new ConfigMigration
                {
                    From = 0,
                    To = 2,
                    Apply = delegate
                    {
                        if (Mathf.Approximately(OutlineWidthEntry.Value, 2.5f))
                        {
                            OutlineWidthEntry.Value = DefaultOutlinePixels;
                            DiagnosticLog.Always("Config migration: outline width 2.5 -> "
                                        + DefaultOutlinePixels.ToString("F1") + " px");
                        }
                    }
                },

                // v2 -> v3: the outline stopped being a fixed screen-pixel width and became
                // a multiple of the baked thickness, so the key was renamed to drop the
                // "(pixels)". The value is a player preference, so it is carried over rather
                // than reset — but only when it actually differs from the new default, since
                // a key that was never in the file binds to that default anyway.
                new ConfigMigration
                {
                    From = 2,
                    To = 3,
                    Apply = delegate
                    {
                        ConfigEntry<float> legacy =
                            Config.Bind("General", "Outline Width (pixels)", DefaultOutlinePixels);
                        if (!Mathf.Approximately(legacy.Value, DefaultOutlinePixels)
                            && Mathf.Approximately(OutlineWidthEntry.Value, DefaultOutlinePixels))
                        {
                            OutlineWidthEntry.Value = legacy.Value;
                            DiagnosticLog.Always("Config migration: outline width "
                                        + legacy.Value.ToString("F2") + " carried over from "
                                        + "the old \"Outline Width (pixels)\" key");
                        }
                        // Drop the legacy entry so the renamed key does not leave a second
                        // row behind in the file (and in the in-game settings panel).
                        Config.Remove(new ConfigDefinition("General", "Outline Width (pixels)"));
                    }
                }
            };

            for (int i = 0; i < migrations.Length; i++)
            {
                ConfigMigration migration = migrations[i];
                if (version < migration.From || version >= migration.To)
                {
                    // Not this step's version range: either an older file has already
                    // moved past the range, or a newer file is ahead of it. Either way it
                    // is skipped rather than applied out of order.
                    continue;
                }
                migration.Apply();
            }

            // The chosen plush is deliberately NOT migrated. It is a player preference
            // (F7 cycles it and saves), so resetting it would silently undo a deliberate
            // choice. A fresh install gets the configured default instead.

            ConfigVersionEntry.Value = CurrentConfigVersion;
            try
            {
                Config.Save();
            }
            catch (Exception ex)
            {
                DiagnosticLog.Warn("Could not save the migrated config: " + ex.Message);
            }
        }

        internal static bool ConfigLoaded;

        /// <summary>
        /// The outline width the models were last built with, so a 0 -> positive change can
        /// be told apart from an ordinary width tweak (only the former needs a rebuild).
        /// </summary>
        private static float _lastOutlineWidth;

        /// <summary>
        /// The width multiplier that means "the thickness the models were baked with".
        ///
        /// The pipeline bakes the shell with a push of 0.75% of the plush's height, which is
        /// the authored look; the config value scales that. It is no longer a pixel count,
        /// because the line is part of the model now and scales with it (see PlushieOutline).
        /// </summary>
        internal const float DefaultOutlinePixels = 5f;

        /// <summary>The outline's width multiplier, with a sane fallback.</summary>
        internal static float OutlineWidthPixels
        {
            get { return OutlineWidthEntry != null ? OutlineWidthEntry.Value : DefaultOutlinePixels; }
        }

        /// <summary>Folder that holds the DLL and all of its data files.</summary>
        internal static string AssetDirectory
        {
            get { return Path.GetDirectoryName(typeof(Plugin).Assembly.Location); }
        }

        private Harmony _harmony;

        private void Awake()
        {
            Log = Logger;
            Instance = this;

            VariantEntry = Config.Bind(
                "General", "Plushie", PlushieVariant.ZichaoXiong,
                "Which plush replaces BingBong. Vanilla restores the original model.");
            WorldScaleEntry = Config.Bind(
                "General", "World Scale", 1.0f,
                new ConfigDescription(
                    "Scale multiplier for the plush in hand and lying in the world.",
                    new AcceptableValueRange<float>(0.3f, 3.0f)));
            BackpackScaleEntry = Config.Bind(
                "General", "Backpack Scale", 1.0f,
                new ConfigDescription(
                    "Extra scale multiplier while the plush sits in a backpack.",
                    new AcceptableValueRange<float>(0.3f, 3.0f)));
            HoldOffsetEntry = Config.Bind(
                "General", "Hold Height Offset", 0.0f,
                new ConfigDescription(
                    "Extra up/down nudge for the model while it is held, added on top of the "
                    + "offset that centres the plush between the game's hand anchors. The "
                    + "anchors already put the plush where it belongs, so this can normally "
                    + "stay at 0.",
                    new AcceptableValueRange<float>(-0.4f, 0.4f)));
            RenameEntry = Config.Bind(
                "General", "Rename Item", true,
                "Rename the item from Bing Bong to the selected plush.");
            ReplaceIconEntry = Config.Bind(
                "General", "Replace Icon", true,
                "Swap the inventory icon to match the selected plush.");
            ShaderOverrideEntry = Config.Bind(
                "Advanced", "Shader Override", "",
                "Leave empty to let the mod pick. The body uses Universal Render Pipeline/Lit "
                + "when it is available (falling back to Simple Lit, W/Peak_Standard, then "
                + "Standard) and the ink outline uses Universal Render Pipeline/Unlit. Set "
                + "this only if you need a specific shader for both.");
            // A plain KeyCode rather than BepInEx's KeyboardShortcut, because the in-game
            // settings panel is built by PEAKLib.ModConfig and its type dispatch has no
            // branch for KeyboardShortcut (it handles bool/float/double/int/string/KeyCode
            // and enums, and logs "Missing SettingType" for anything else). The log proved
            // it: the hotkey row was silently skipped, so the setting could not be changed
            // in game at all. KeyCode does have a branch, so it shows up as a keybind.
            // The cost is losing modifier combinations, which this mod does not need.
            CycleHotkeyEntry = Config.Bind(
                "General", "Cycle Plush Hotkey", KeyCode.F7,
                "Optional in-game hotkey that cycles Vanilla -> Miffy -> Zichao Xiong. "
                + "The choice is saved to this config file.");
            OutlineWidthEntry = Config.Bind(
                "General", "Outline Width", DefaultOutlinePixels,
                new ConfigDescription(
                    "Thickness of the plush's ink outline, as a multiple of the width the "
                    + "models are baked with (5). The line belongs to the plush, so it "
                    + "scales with it: it gets thinner as the plush moves away instead of "
                    + "holding a fixed pixel width. 0 hides the outline.",
                    new AcceptableValueRange<float>(0f, 12f)));
            ConfigVersionEntry = Config.Bind(
                "Internal", "Config Version", 0,
                new ConfigDescription(
                    "Written by the mod. Do not edit: it tracks which defaults have "
                    + "already been migrated.",
                    null, new object[] { "Hidden" }));
            VerboseLogEntry = Config.Bind(
                "Advanced", "Verbose Logging", false,
                "Write detailed diagnostics to the BepInEx log: which shader was chosen, "
                + "how many outlines were built, every model rebuild, and the loose-file "
                + "fallbacks. Leave this off for normal play; warnings and errors are "
                + "always written either way.");

            MigrateConfigDefaults();

            ActiveVariant = VariantEntry.Value;
            _lastOutlineWidth = OutlineWidthPixels;
            ConfigLoaded = true;

            VariantEntry.SettingChanged += OnVariantChanged;
            WorldScaleEntry.SettingChanged += OnScaleChanged;
            BackpackScaleEntry.SettingChanged += OnScaleChanged;
            OutlineWidthEntry.SettingChanged += OnOutlineWidthChanged;

            GameObject host = new GameObject("PlushieSwap_Host");
            DontDestroyOnLoad(host);
            host.hideFlags = HideFlags.HideAndDontSave;
            host.AddComponent<PlushieHost>();

            _harmony = new Harmony(Guid);
            VerifyPatchTargets();
            PatchSafely(typeof(Patches.ItemPatches), "Item hooks");
            PatchSafely(typeof(Patches.UiPatches), "UI hooks");
            PatchSafely(typeof(Patches.CookingPatches), "Cooking hooks");

            DiagnosticLog.Always("Plushie Swap " + DisplayVersion + " loaded (plush: " + ActiveVariant + ")");
        }

        /// <summary>
        /// Whether the detailed diagnostics should be written.
        ///
        /// Read through the config entry rather than cached, so toggling the setting takes
        /// effect immediately. Errors and warnings never go through this gate: only the
        /// chatter that is useful while diagnosing and noise once the mod works.
        /// </summary>
        internal static bool VerboseLogging
        {
            get { return VerboseLogEntry != null && VerboseLogEntry.Value; }
        }

        /// <summary>
        /// A missing game method must never take the whole mod down, so each patch class
        /// is applied on its own and failures are reported instead of thrown.
        ///
        /// Note the granularity: Harmony resolves EVERY target in a patch class before it
        /// applies ANY of them, and throws if one is missing. So a class is all-or-nothing
        /// — one renamed game method silently disables that whole class. The full exception
        /// is logged (not just `ex.Message`) because HarmonyException carries the offending
        /// method's full name, which is the only thing that makes this diagnosable; and
        /// `VerifyPatchTargets` reports each missing target by name at startup.
        /// </summary>
        private void PatchSafely(Type patchClass, string description)
        {
            try
            {
                _harmony.PatchAll(patchClass);
                DiagnosticLog.Diag("Applied " + description + " (" + patchClass.Name + ")");
            }
            catch (Exception ex)
            {
                DiagnosticLog.Error("Failed to apply " + description + " (" + patchClass.Name
                                    + "). None of its patches are active. " + ex);
            }
        }

        /// <summary>
        /// The game methods this mod patches, resolved once at startup.
        ///
        /// `PatchSafely` can only report that a whole class failed; this names the exact
        /// missing method, so a game update that renames one is a one-line diagnosis
        /// instead of an investigation.
        ///
        /// The type is a real `typeof` rather than a string: the assembly reference makes
        /// the type itself a compile-time check, so only the method name has to be
        /// verified at runtime. Using a string for the type as well would have meant
        /// guessing the CLR spelling of the nested type (`Item+ItemUIData`, not
        /// `Item.ItemUIData`) — a guess that produced a false "type is missing" error the
        /// first time this ran.
        /// </summary>
        private static readonly (Type Type, string Method)[] PatchTargets =
        {
            (typeof(Item), "Start"),
            (typeof(Item), "OnEnable"),
            (typeof(Item), "SetState"),
            (typeof(Item), "HideRenderers"),
            (typeof(Item), "GetName"),
            (typeof(Item.ItemUIData), "GetIcon"),
            (typeof(InventoryItemUI), "SetItem"),
            (typeof(ItemCooking), "UpdateCookedBehavior"),
            (typeof(BackpackOnBackVisuals), "InitRenderers"),
        };

        /// <summary>Reports every patch target that no longer resolves, by name.</summary>
        private static void VerifyPatchTargets()
        {
            for (int i = 0; i < PatchTargets.Length; i++)
            {
                Type type = PatchTargets[i].Type;
                string methodName = PatchTargets[i].Method;
                if (AccessTools.Method(type, methodName) == null)
                {
                    DiagnosticLog.Error("Patch target method is missing: " + type.FullName + "."
                                        + methodName + " (the game changed; the related feature is off).");
                }
            }
        }

        private static void OnVariantChanged(object sender, EventArgs e)
        {
            ActiveVariant = VariantEntry.Value;
            if (Log != null)
            {
                DiagnosticLog.Diag("Plush changed to: " + ActiveVariant);
            }
            PlushieModel.RequestRefreshAll(true);
        }

        private static void OnScaleChanged(object sender, EventArgs e)
        {
            PlushieModel.RequestRefreshAll(false);
        }

        /// <summary>
        /// A width change only needs the new value pushed to the live outline drivers, which
        /// re-extrude on the spot (no per-frame work is involved). The one exception is
        /// turning the outline back ON after a 0: at width 0 no outline object is built at
        /// all, so there is no driver to push to and the models must be rebuilt to create one.
        /// </summary>
        private static void OnOutlineWidthChanged(object sender, EventArgs e)
        {
            float width = OutlineWidthPixels;
            bool wasOff = _lastOutlineWidth <= 0f;
            _lastOutlineWidth = width;

            PlushieOutline.SetWidthOnAll(width);
            if (width > 0f && wasOff)
            {
                // At width 0 no outline object is built at all, so there is no driver to
                // push the new width to and the models must be rebuilt to create one.
                // Only this 0 -> positive transition needs it; other changes are live.
                PlushieModel.RequestRefreshAll(true);
            }
        }

        /// <summary>Cycles Vanilla -> Miffy -> Zichao Xiong and saves the choice.</summary>
        internal static void CycleVariant()
        {
            PlushieVariant current = VariantEntry.Value;
            PlushieVariant next;
            switch (current)
            {
                case PlushieVariant.Vanilla:
                    next = PlushieVariant.Miffy;
                    break;
                case PlushieVariant.Miffy:
                    next = PlushieVariant.ZichaoXiong;
                    break;
                default:
                    next = PlushieVariant.Vanilla;
                    break;
            }

            VariantEntry.Value = next;
            try
            {
                Instance.Config.Save();
            }
            catch (Exception ex)
            {
                if (Log != null)
                {
                    DiagnosticLog.Warn("Could not save config: " + ex.Message);
                }
            }
        }
    }

    /// <summary>
    /// One place that decides what reaches the log.
    ///
    /// `Diag` is the chatter that is only interesting while something is being diagnosed
    /// (shader selection, outline construction, rebuilds, fallbacks); it is gated on the
    /// `Advanced/Verbose Logging` setting, which defaults to off so a normal player's log
    /// stays short. `Warn` and `Error` always go through, because those are the lines a
    /// bug report needs. `Always` is the small set of one-per-session lines that say the
    /// mod loaded and which plush is active.
    /// </summary>
    internal static class DiagnosticLog
    {
        internal static void Always(string message)
        {
            if (Plugin.Log != null)
            {
                Plugin.Log.LogInfo(message);
            }
        }

        internal static void Diag(string message)
        {
            if (Plugin.Log != null && Plugin.VerboseLogging)
            {
                Plugin.Log.LogInfo(message);
            }
        }

        internal static void Warn(string message)
        {
            if (Plugin.Log != null)
            {
                Plugin.Log.LogWarning(message);
            }
        }

        internal static void Error(string message)
        {
            if (Plugin.Log != null)
            {
                Plugin.Log.LogError(message);
            }
        }
    }

    /// <summary>Frame pump so refresh requests and the cycle hotkey run on the Unity thread.</summary>
    internal sealed class PlushieHost : MonoBehaviour
    {
        private void Update()
        {
            try
            {
                ConfigEntry<KeyCode> hotkey = Plugin.CycleHotkeyEntry;
                if (hotkey == null || hotkey.Value == KeyCode.None)
                {
                    return;
                }

                // BepInEx's input abstraction rather than UnityEngine.Input directly: it
                // resolves to the legacy or the new input system as appropriate, and it is
                // already referenced (BepInEx.dll), so no extra assembly is needed.
                if (UnityInput.Current.GetKeyDown(hotkey.Value))
                {
                    Plugin.CycleVariant();
                }
            }
            catch (Exception ex)
            {
                if (Plugin.Log != null)
                {
                    DiagnosticLog.Warn("Hotkey check failed: " + ex.Message);
                }
            }
        }

        private void LateUpdate()
        {
            try
            {
                PlushieModel.Tick();
            }
            catch (Exception ex)
            {
                if (Plugin.Log != null)
                {
                    DiagnosticLog.Error("Tick failed: " + ex);
                }
            }
        }

        /// <summary>
        /// Releases the static caches when the plugin is torn down. Unity does not
        /// garbage-collect meshes, materials or textures, so the per-variant caches have
        /// to be freed explicitly; nothing else would ever do it.
        /// </summary>
        private void OnDestroy()
        {
            try
            {
                PlushieModel.ReleaseCaches();
            }
            catch (Exception ex)
            {
                if (Plugin.Log != null)
                {
                    DiagnosticLog.Warn("Could not release the model caches: " + ex.Message);
                }
            }
        }
    }
}
