# Plushie Swap

Replaces the **BingBong** plush in **PEAK** with a cartoon **Miffy** (米菲兔) or
**Zichao Xiong** (自嘲熊), switchable in game at any time.

Default form: **Zichao Xiong**.

中文说明见 [`README.zh-CN.md`](README.zh-CN.md)。

## Features

- **Three forms, cycled in game with `F7`**: `Vanilla` → `Miffy` → `ZichaoXiong`.
  The choice is written back to the config file.
- **Faithful model replacement**: scale, pivot and orientation are fitted to the vanilla
  plush, so holding it, dropping it and stuffing it in a backpack all behave correctly.
- **Cartoon treatment** (so it stops looking like a 3D-print photo):
  - **Hand-drawn ink outline** — a complete inverted hull with **no faces deleted**, using a
    per-vertex "ink width" to decide where no line is drawn. The line is part of the model,
    so it scales with the plush and stays proportionate at any distance.
  - **Clean cream highlights** — bright colours are pushed toward `#FFFAF2`.
  - **Soft contact shading** — a point-cloud AO bake, smoothed, so creases read without
    blocky noise.
- **Per-model grip height** — Miffy is held at the waist, Zichao Xiong on the body (to clear
  its very large head), and the grip scales with the model.
- **Item name and inventory icon** follow the selected plush.
- **Vanilla audio and gameplay are untouched** — this changes appearance, name and icon only.

## Install

1. Install **BepInEx 5.4.x** (you should see a `BepInEx` folder in the game directory).
2. Drop **`PlushieSwap.dll`** into:
   ```
   <game folder>\BepInEx\plugins\
   ```
3. Launch the game.

**One file is all you need** — the models, shading maps and icons are embedded in the DLL
(12,136,960 bytes, about 11.6 MiB).

### Optional: use a custom model without rebuilding

A loose file next to the DLL takes priority over the embedded copy. Drop a `.psmesh`,
`_shading.png` or `icon_*.png` beside the DLL to override the embedded one:

| File | Purpose |
| --- | --- |
| `miffy.psmesh` | Miffy model |
| `miffy_shading.png` | Miffy baked shading map |
| `icon_miffy.png` | Miffy icon |
| `zichaoxiong.psmesh` | Zichao Xiong model |
| `zichaoxiong_shading.png` | Zichao Xiong baked shading map |
| `icon_zichaoxiong.png` | Zichao Xiong icon |

## Configuration

Config file: `BepInEx\config\com.zhuanban.peak.plushieswap.cfg`

| Option | Default | Meaning |
| --- | --- | --- |
| `Plushie` | `ZichaoXiong` | Form: `Vanilla` / `Miffy` / `ZichaoXiong` |
| `Cycle Plush Hotkey` | `F7` | In-game cycle key (a single key, no modifier combos) |
| `World Scale` | `1.0` | Model size multiplier while held or on the ground |
| `Backpack Scale` | `1.0` | Extra size multiplier inside a backpack |
| `Hold Height Offset` | `0.0` | Extra up/down nudge while held |
| `Rename Item` | `true` | Rename the item to the chosen plush |
| `Replace Icon` | `true` | Replace the inventory icon |
| `Outline Width` | `5.0` | Ink line width as a multiple of the baked width (0.75% of the plush's height); `0` hides it |
| `Shader Override` | *(empty)* | Only needed if the model renders with wrong colours |
| `Verbose Logging` | `false` | Detailed diagnostics; off means warnings and errors only |

Changes made in the in-game mod settings apply immediately — the one exception is
`Shader Override`, which is cached per variant and needs a **restart**. Editing the config
file by hand is **not** hot-reloaded either: restart the game to pick it up. (`F7` only
cycles the form and writes the choice back; it does not re-read the file, so pressing `F7`
after hand-editing the cfg overwrites that edit.)

> `[Internal] Config Version` is a marker this mod writes to migrate old defaults
> (BepInEx does not update existing entries). It is hidden from the in-game settings.

## Adding your own model

The whole model pipeline is in `tools/build_meshes.py`. To add a third plush:

```powershell
# 1. Put your .3mf into models\
# 2. Append one convert(...) call at the bottom of tools/build_meshes.py
# 3. Generate the mesh (decimate, orient, fit to the vanilla silhouette, bake AO)
python tools\build_meshes.py

# 4. Generate the icon
python tools\build_icons.py

# 5. Compile, embed and verify
pwsh -File build.ps1 -RebuildAssets
```

You also need to add the variant to `src/Variants.cs` (file names and display names) and,
if you want it selectable, to the `Plushie` config enum. Then rebuild.

`build_meshes.py` handles: 3MF parsing (including Bambu multi-colour `paint_color`), splitting
by colour and connected component, protecting small details from decimation, area-uniform
decimation, rebuilding hard-edged smooth normals, detecting and correcting the facing
direction, normalising scale and pivot to the vanilla silhouette, baking AO into a palette
texture, generating the closed outline shell with per-vertex ink widths, and computing the
grip point.

`build.ps1` verifies the embedded assets against `assets/` before compiling and aborts on a
mismatch. This closes the project's historically worst failure mode: `assets/` regenerated
but `src/EmbeddedAssets.g.cs` not, so the runtime prefers the stale embedded copy and your
change appears to do nothing.

## Building from source

You need the .NET SDK (for `dotnet build`) and the game itself (for the reference assemblies).

`libs/` is **not** in the repository (it is gitignored). Prepare it yourself by copying these
assemblies out of the game's `PEAK_Data\Managed\`: `mscorlib.dll`, `netstandard.dll`,
`System.dll`, `System.Core.dll`, `Assembly-CSharp.dll`, `Zorro.Core.Runtime.dll`,
`UnityEngine.dll`, `UnityEngine.CoreModule.dll`, `UnityEngine.ImageConversionModule.dll`,
`UnityEngine.UI.dll`, `PhotonUnityNetworking.dll`; then copy `BepInEx.dll` and `0Harmony.dll`
from `BepInEx\core\`. Those are every `HintPath` target in `PlushieSwap.csproj`.

```powershell
pwsh -File build.ps1                  # verify assets + compile + package into dist\
pwsh -File build.ps1 -Deploy          # same, and copy into the game
pwsh -File build.ps1 -RebuildAssets   # regenerate models/icons/embeds first, then compile
```

`build.ps1` runs `tools/verify_assets.py` (source 3MFs ↔ generated assets) and
`tools/verify_embedded.py` (assets ↔ embedded copy) and aborts if either disagrees. It then
copies `bin\Release\PlushieSwap.dll` to `dist\`, checks the deployed hash, and writes
`dist\PlushieSwap\buildinfo.txt` with the commit, build time, SHA-256 and version.

To cut a Thunderstore package, run `python tools\package_release.py`. It refuses to package
a `dist/` that does not match the current commit, and the zip it writes is reproducible.

### Repository layout

| Path | Contents |
| --- | --- |
| `src/` | The plugin. `PlushieModel.cs` is the core (loading, materials, hold offset, per-frame sync). |
| `tools/` | Build pipeline and verification scripts. `build_meshes.py`, `build_icons.py`, `embed_assets.py`, `verify_assets.py`, `verify_embedded.py`, `package_release.py` are the ones the build actually runs. |
| `assets/` | Generated `.psmesh` models, shading maps and icons (committed so the build is reproducible). |
| `models/` | Source 3MF files (third-party, see credits). |
| `research/` | Experiment scripts, design notes and the outline design document. Not needed to build. |
| `shaders/` | Research-only shader source. Not compiled and not shipped. |

## How the cartoon look is done

| Element | Approach |
| --- | --- |
| **① Outline** (the key one) | Inverted hull: the body is expanded outward (**no faces deleted**) and back-face culled, so ink only shows at the silhouette edge. The thickness lives in the model's own space, so the line scales with the plush. |
| **② Clean bright blocks** | Colours with luminance > 0.55 are pushed toward cream `#FFFAF2` (more the brighter they are). |
| **③ Simple soft shading** | Point-cloud AO, upper-hemisphere occlusion only, 3 Laplacian smoothing passes plus a power curve. |
| **④ A little specular** | `_Smoothness = 0.14` for a soft cloth sheen rather than plastic. |

AO values are packed into a 1-pixel-high palette texture by colour, with vertex UVs pointing at
the right brightness slot inside their own colour block. The whole model (outline included)
therefore needs only two materials and two draw calls (body once, outline once).

### Why the outline does not delete faces

Early versions deleted the eyes, mouth, blush and every downward-facing face from the shell.
That left thousands of boundary edges, and every boundary edge is exactly where an ink line
breaks — the source of the "dashed, uneven" outline. The shell is now a **complete closed
surface** and uses a per-vertex ink width instead (0 = no line). A zero-width vertex sits on
the body surface and is naturally hidden by the body through back-face culling, so nothing has
to be deleted. Widths ship inside the `.psmesh` and are restored exactly at runtime, where the
push is re-applied in the model's own space for the configured width.

The pipeline also has an `enclosed` ("inside another shell") mask, which is **deliberately
unused**: it classifies the arm tips resting against the skirt as enclosed and cuts the
outline there (measured: that is the source of the silhouette outline dropping from 22.6% to
5.1%). Faces that genuinely sit behind another shell are invisible anyway, so nothing is saved.

## How the model is aligned

The replacement is generated directly in the item's local coordinates, with every reference
measured from the real prefab:

| Item | Value |
| --- | --- |
| Vanilla plush height | `0.9635` units |
| Vanilla Y range | `[-0.7345, +0.2290]` |
| Vanilla XZ centre (**plush body**, excluding the hands) | `X = -0.0315`, `Z = +0.0505` |
| Vanilla anchor midpoint | `(-0.0595, -0.1405, -0.0400)` — the midpoint of the `Hand_L` / `Hand_R` nodes, i.e. the **vanilla anchor** height, not the model's grip height |
| Vanilla anchor spacing | `0.5990` on X, `0.6034` in 3D |
| Held orientation | item `+Z` is the player's view direction, so the model faces `-Z` |
| Generated solid height | `0.9635` (both models; merged bounds including the outline shell are Miffy `0.9726` / bear `0.9735`) |

The pipeline automatically:

1. **Detects the model's front** — small, upper-body colour regions (eyes/mouth/blush) are
   located and rotated toward the player (Miffy needs 181°, Zichao Xiong 225°; both source
   models are skewed).
2. **Fits scale and pivot** — scaled to the vanilla height, XZ centred on the vanilla body
   centre, Y identical to vanilla; the whole thing is then re-centred once more with the
   outline included so the outer silhouette lands inside the vanilla bounds.
3. **Bakes AO** — per-vertex upper-hemisphere occlusion, smoothed and packed into a palette.
4. **Generates the outline shell** — expanded along the normals and flagged as an outline
   submesh.

Grip height is set per model (`grip_fraction` at the end of `tools/build_meshes.py`):

| Model | Grip point, as a fraction of height | Notes |
| --- | --- | --- |
| Miffy | 22% | Waist, just under her open arms |
| Zichao Xiong | 26% | Mid-body, clearing a head that is over half the total height |

**No anchor is written while held**: the item's own `Hand_L` / `Hand_R` nodes keep their vanilla
values from start to finish. The game reads those two nodes every physics frame to place the
hands (`CharacterAnimations.ConfigureIK`), so the mod instead **offsets the model itself**:
`HoldOffsetFor()` computes `anchor midpoint − grip midpoint × scale`, which puts the model's
waist directly under the hands. Switching back to vanilla needs no restoration — the vanilla
data was never modified.

> Known limitation: the vanilla anchor spacing on X is `0.5990`. Miffy's grip spacing is only
> `0.3860`, so her hands visibly stop in the air beside her body; Zichao Xiong's is `0.5950`,
> just `0.0040` short of vanilla, so it lines up almost exactly. A symmetric "pull the hands
> in" approach was tried, but the game's own squeeze animation rewrites the anchor nodes
> directly, so it could not be made reliable and was **removed entirely**.

The model is not parented to the item root but to **`item/Holder/PlushieSwap_Visual`**, in order
to inherit the game's own squeeze animation: holding primary fire triggers
`Action_AskBingBong` → `squishAnim.SetTrigger("Squish")`, and that controller drives only
`Holder.localScale` and the two anchor `localPosition`s. The vanilla plush is itself a child of
`Holder`, so parenting there gets the same squeeze for free. `Holder` is an identity transform
at rest, so it costs nothing normally.

## Credits and licensing

### Reference mod

Thanks to **[ScallionMiku](https://github.com/xiaofe12/ScallionMiku)** by
**[xiaofe12](https://github.com/xiaofe12)** (published on Thunderstore as
[Thanks/ScallionMiku](https://thunderstore.io/c/peak/p/Thanks/ScallionMiku/)). It is the only
other mod in the PEAK community that replaces the plush model, and it was the reference this
project was built against: the approach of hiding the vanilla renderers, the idea of keeping
the original `mainRenderer` intact, and the per-frame validation strategy all came from
studying it. It is licensed MIT. It is **not** bundled here — it is a hard conflict with this
mod (both replace the same item and patch the same nine game methods), so install only one.

### Models

Both replacement models are third-party 3D-printing models. They were reprocessed here
(decimated, re-oriented, fitted to the vanilla silhouette, AO baked, outline shell generated)
but they are **not original to this mod**, and all rights remain with their authors.

**Miffy (米菲兔)** — "米菲兔 经典艺术 白剪纸"
- Source: <https://makerworld.com.cn/zh/models/2032846-miffy-mi-fei-tu-jing-dian-yi-zhu-bai-jian-zhi-chi>
- Author: **再也不打没用的东西了** (MakerWorld `@user_3189506737`)
- Licence: **not stated.** The supplied 3MF has empty `Designer` / `Licence` / `Title` fields
  and the page states no licence.
- The Miffy character itself is the property of **Dick Bruna / Mercis bv**, independently of
  whoever modelled it.

**Zichao Xiong (自嘲熊)** — "坐姿自嘲熊（多色一体）"
- Source: <https://makerworld.com.cn/zh/models/2666015-zuo-zi-zi-chao-xiong-duo-se-yi-ti>
- Author: **夜夜椰子冰** (MakerWorld UID `2431656860`), per the `Designer` field embedded in
  the 3MF.
- Licence: **Standard Digital File License** (the licence selected when it was uploaded).
- The same model is also published on MakerWorld's international site
  (<https://makerworld.com/en/models/3154227>), credited there to **Lorensi**
  (UID `495168789`). Title, cover image, creation date and licence all match, so these are two
  uploads of one model; which came first could not be established, so both are listed.

This is a **non-commercial** fan project. It charges nothing and claims no rights over either
model. If you are an author or rights holder and would like the attribution changed, a licence
clarified, or your model removed, please get in touch via the release page and it will be done
in the next version — the mod will then keep only the `Vanilla` option, or ship without the
geometry and let users generate it locally.

### Code

The source code of Plushie Swap is released under the **MIT Licence**; see [`LICENSE`](LICENSE).
That licence covers this project's code only, not the third-party models under `models/`.

## Notes and known limitations

- This is a **local visual replacement**: only clients that installed the mod see it. Other
  players still see the vanilla plush.
- The vanilla hover highlight does not apply to the replacement (it uses its own materials).
- The outline is baked into the model's own space, so it scales with the plush rather than
  holding a fixed pixel width. Up close the line is a little thicker than on a distant plush;
  that is what keeps a far-away plush from wearing a disproportionately heavy border.
- The outline costs nothing per frame: the shell is extruded once when the model is built, and
  again only if the outline width setting changes.
- The mod does not modify the game's voice lines or audio, and does not change any item's
  gameplay logic — it replaces appearance, name and icon only.
