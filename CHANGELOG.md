# Changelog

## 1.1.0

### Fixed

- **The in-game plush hotkey can now actually be set in game.** It was bound as a
  BepInEx `KeyboardShortcut`, which the game's settings panel has no control for, so the
  row was silently skipped and the key could only be changed by editing the config file.
  It is a plain key now (single keys; modifier combinations are no longer accepted).
- **Switching back to the vanilla plush restores the vanilla inventory icon.** The slot
  refreshes only the name and the cook amount when it still holds the same prefab, and
  the icon was only ever overwritten with a replacement, so returning to vanilla left the
  previous plush's icon on screen until the item was dropped and picked up again. The
  icon is now reconciled to whatever the selected variant should show, vanilla included.
- **The inventory icon follows an in-game plush switch immediately.** The widget cached
  the icon and skipped refreshing it while the slot still held the same prefab, so after
  pressing F7 every visible slot kept the previous plush until the item was dropped and
  picked up again.
- **The plush name follows a language change immediately.** The Chinese/English choice
  was cached and only invalidated when cycling the plush, so switching the game language
  to Chinese left the names in English until F7 or a restart.
- **Cooking tint no longer fights other mods' highlights.** The cook colour was written
  by replacing the renderer's whole property block, which erased the cleanup highlight
  another mod writes to the same renderer; only the two cook keys are touched now.
- **The outline no longer disappears at long range.** Its mesh bounds were padded by a
  fixed amount, which was too small past roughly 9 m (and past ~1.2 m at small model
  scales); the padding is now recomputed every frame from the offset actually applied.
- **A corrupt or truncated model file now falls back to the embedded copy** instead of
  being parsed into garbage. Sizes in the file are validated before allocating, so a bad
  file can no longer request an enormous allocation.
- **A missing game method is now reported by name at startup**, instead of only a
  generic "hooks failed" line. The patch-target check names the exact method.
- **A variant that failed to load is retried on a hard refresh** rather than staying
  broken for the rest of the session.

### Changed

- The release zip is now reproducible (identical bytes for identical input), and the
  packaging step refuses to build from a `dist/` that does not match the current commit.
- The build records `-dirty` in its build info when the working tree has uncommitted
  changes, so a deployed DLL can be traced to what actually produced it.
- The asset checks now also detect a change to the generator or its parameters, not just
  to the model files.

## 1.0.0

- Initial release.
- Replaces BingBong with Miffy or Zichao Xiong, switchable in game with F7.
- Screen-space constant-width ink outline.
- Inventory name and icon follow the selected plush.
- Inherits the game's squeeze animation while held.
