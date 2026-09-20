# Outline redesign - research and plan (Plushie Swap)

> ## ⚠️ STATUS: HISTORICAL RESEARCH DOCUMENT — NOT THE SHIPPED DESIGN
>
> This document surveys the options and **recommends (b) AssetBundle + a custom
> shader**. That recommendation was **never adopted**. No AssetBundle was ever
> built (it needs the Unity editor, which is not installed), so:
>
> * `shaders/PlushieOutline.shader` and `research/PlushieShaderLoader.sample.cs`
>   are **research artefacts only** — nothing in `src/` or `tools/` references
>   them, and they are not part of the build;
> * the shipping implementation does the same maths **on the CPU, once per
>   frame**, in `src/PlushieOutline.cs` (screen-space re-extrusion of the ink
>   shell, constant pixel width);
> * the outline does **not delete any faces** — the whole solid mesh is the ink
>   shell, and a **smooth per-vertex ink width** (4 Laplacian passes) decides
>   where the line fades out, instead of a 0/1 mask or face deletion;
> * the `enclosed` mask is **deliberately not applied** (it classifies an arm
>   resting against the dress as "enclosed" and cuts the outline off there —
>   measured at 22.6% → 5.1% silhouette ink loss).
>
> The technical analysis and the references below are still valuable and are
> kept for that reason. For the real current design see `src/PlushieOutline.cs`
> (the screen-space driver) and the「卡通风格是怎么做的」section of `README.md`.

Status (as written): research only. No production file under `src/` or `tools/` was modified.
New files live in `research/` and `shaders/`.

## 1. Problem, measured

> ⚠️ The description below is the state at the time of writing. The shipped
> pipeline has since moved to a **no-deletion** shell with a **smooth per-vertex
> ink width**; see the status banner at the top.

The current outline is an offline inverted hull baked by `tools/build_meshes.py`:

```python
# build_cartoon_outline
offset = verts + normals * (thickness * scale)   # scale == 1 in our call
# convert(): outline_thickness=0.0075, target_height=0.9635
# -> OUTLINE_THICKNESS = 0.00722625 world units
```

The width is therefore a fixed **object-space length**. Its size in pixels is
not fixed: `research/measure_outline_width.py` projects the shipped shell and
measures the body-to-shell pixel distance for silhouette vertices.

`research/outline_width_metrics.txt` (1080p, 50 deg FOV, 1920x1080):

| camera distance | object-space line (current) | screen-space @ 2 px target |
|-----------------|-----------------------------|----------------------------|
| 0.35 m | 37.33 +- 30.76 px (p5 6.4, p95 95.2) | 2.00 +- 0.00 px |
| 0.50 m | 17.92 +- 8.91 px | 2.00 |
| 1.00 m | 6.85 +- 2.41 px | 2.00 |
| 2.00 m | 3.18 +- 1.05 px | 2.00 |
| 4.00 m | 1.55 +- 0.50 px | 2.00 |
| 8.00 m | 0.77 +- 0.24 px | 2.00 |

So the current line swings from ~0.8 px to ~37 px, and even at a fixed distance
it varies by ~3x across the silhouette (`p5` to `p95`). That is exactly the
"uneven and broken" report. It is intrinsic to an object-space extrusion, not a
tuning problem.

`research/preview/ss_vs_os_miffy.png` and `..._zichaoxiong.png` render the two
methods with the same camera (left = current, right = screen-space).

Two more real defects found in the shell data:

* the shell has **unused vertices** (miffy 4226 of 15525; zichaoxiong 12355 of
  16831) and **boundary edges / holes** (miffy 1377; zichaoxiong 588), from the
  deliberate face-decal and downward-face removal;
* the ink is drawn as a **separate child mesh**, not a second pass on the body.

> ⚠️ Those numbers describe the **old, face-deleting** shell that this document
> was written against. The shipped pipeline no longer deletes faces: the whole
> solid mesh is the shell, dead vertices are 0 (15525 / 16831 all used), and the
> measured boundary edges are 344 (miffy) / 1254 (zichaoxiong) — both below the
> body's own 1848 / 3498, i.e. the shell adds no new break.

The screen-space method keeps the same shell mesh, so all of that mask work is
preserved.

## 2. Industry survey and what it means here

| approach | how it works | width behaviour | verdict here |
|---|---|---|---|
| Object-space inverted hull (current) | extrude along normal in object space | varies with distance/FOV/scale | the defect |
| Clip-space inverted hull | `clip.xy += normalize(clipNormal.xy)/screen * width * clip.w * 2` | constant pixels | **recommended** |
| View-space + distance term | UTS2 `_Outline_Width * 0.001 * smoothstep(Far,Near,dist)` | approx constant, needs distance clamps | more knobs, same idea less exact |
| Depth/normal edge detect (post) | Sobel on `_CameraDepthTexture` + `_CameraNormalsTexture` | constant pixels | see below |
| Stencil two-pass (QuickOutline) | mask pass + fill pass with UV3 smooth normals | object-space unless clip-space used | adds stencil state, no gain |
| Per-object RendererFeature (Delt06) | re-draw selected layers with an inflate material | its "Fixed Screen Space Thickness" is the same clip-space trick | not needed for one item |

Confirmed references for the exact clip-space formula:

* Roystan, *Pixel-Perfect Outline Shaders for Unity* (derive `clip.w`, then
  `/ _ScreenParams.xy`, then `* 2`).
* UnityChanToonShaderVer2 / UTS2 outline (`_Outline_Width`, baked normal map,
  `_Offset_Z` applied as `pos.z += _Offset_Z * _ClipCameraPos.z`).
* MToon (`projectedNormal = normalize(clipNormal.xy); projectedNormal *=
  min(vertex.w, _OutlineScaledMaxDistance); projectedNormal.x *= aspect`).
* ChiliMilk URP toon and BernardsPersonalGit SmoothOutline
  (`normalize(normalCS.xy) / _ScreenParams.xy * _OutlineWidth * positionCS.w * 2`).
* QuickOutline: confirms the UV3 smooth-normal trick for hard-edged meshes.

**Depth/normal edge detection is rejected here.** Reasons:

1. It outlines *screen-space discontinuities of the whole frame*, so the plush
   would gain lines where it overlaps terrain, and terrain would gain lines
   where the plush crosses it. The user wants the line **on the model only**.
2. It needs a `ScriptableRendererFeature` injected at runtime. URP 17 (Unity
   6000.3) runs on **RenderGraph**; a runtime-added pass must use the
   RenderGraph API, and the game already has its own renderer data and features.
   That is a large, fragile surface for a two-item cosmetic effect.
3. Cost is per-frame full-screen; the geometric outline is per-vertex on an
   already-built shell.
4. It cannot give the clean flat-ink line on the plush's interior creases that
   the baked cavity/crease mask currently provides.

It is, however, the right tool if the goal ever becomes "outline every
interactable in the world". Recorded as a fallback, not the plan.

## 3. Custom shader delivery: the three routes

| route | feasible? | evidence |
|---|---|---|
| (a) `Shader.Find` a stock game shader and set properties | yes, but **cannot** give constant pixel width | 227 shipped shaders surveyed (`research/shader_inventory.txt`, `research/shader_properties.txt`). The only shaders exposing `_Cull` are URP Lit/Unlit/Particles. `W/Character` and `W/Peak_Standard` have no `_Cull`. No shipped shader offsets along clip-space normals (`_Outline` on Jelly/Tornado/Explosion is an unrelated dissolve, `_VertexGhost` on W/Character is a 0/1 body-hide flag set by `HideTheBody.cs`). |
| (b) AssetBundle with the compiled shader | **yes, recommended** | `AssetBundle.LoadFromFile/LoadFromMemory/LoadFromStream` all exist in the Mono player (`UnityEngine.AssetBundleModule.dll`). The game already ships AssetBundles (Addressables present). Must be built with **6000.3.x** because bundles are not cross-version compatible. |
| (c) inline shader string -> `Shader.CreateFromString` | **no longer exists** | Verified against `UnityEngine.CoreModule.dll` and `UnityEngine.ShaderRuntimeModule.dll`: only `Shader.Find`, `Shader.FindBuiltin`, `Shader.CreateFromCompiledData(byte[], Shader[])`. `UnityPlayer.dll` contains no `CreateFromString`. The old `new Material(string)` ctor is present but `[Obsolete(..., error: true)]`: "Creating materials from shader source string is no longer supported." `ShaderUtil.CreateShaderAsset` is **Editor-only** and there is no Unity Editor installed on this machine. |

Conclusion (as recommended at the time): **(b)**. Ship a small `plushieoutline.bundle`
next to `PlushieSwap.dll` (or embed it like the models). Keep the current URP/Lit
fallback when it is absent.

> ⚠️ **Not adopted.** No bundle exists and none can be built without the Unity
> editor. The shipped ink material resolves a built-in shader instead
> (`Universal Render Pipeline/Unlit`, front-face culled — see
> `PlushieModel.ResolveOutlineShader`). The CPU screen-space extrusion in
> `src/PlushieOutline.cs` is the shipping implementation of the maths below.

### The "undo the baked offset" step is exact

`research/check_outline_undo.py` (`research/outline_undo_check.txt`) verifies the
one assumption the shader makes. For every shell vertex:

```
shell - normal * (0.0075 * 0.9635)  ->  nearest body vertex
miffy       : mean 0.000000  p95 0.000000  max 0.000000   (15525 verts)
zichaoxiong : mean 0.000000  p95 0.000000  max 0.000000   (16831 verts)
```

The recovery is exact to float precision, so the screen-space offset is applied
from the true surface, not from an approximation. The same script also shows the
scale bug: at the backpack's `localScale = 0.5` the baked offset is halved,
while a pixel-space offset is unaffected.


## 4. Recommended design

> ⚠️ **Not the shipped design** (see the status banner). The equations below are
> what `src/PlushieOutline.cs` evaluates on the CPU every frame; the bundle and
> the custom material were never built.

Keep two renderers exactly as today:

* `Model` - body mesh, unchanged `Universal Render Pipeline/Lit` material with
  `_BaseMap -> <variant>_shading.png`. Untouched.
* `Outline` - the existing inverted-hull shell mesh, now with the bundled
  `PlushieSwap/Outline` material.

The shader **undoes the baked offset and re-applies a pixel-constant one**:

```hlsl
float3 surfaceOS = positionOS - normalOS * _OutlineBakedThickness;
float4 positionCS = TransformObjectToHClip(surfaceOS);
float3 normalCS   = TransformWorldToHClipDir(TransformObjectToWorldNormal(normalOS));
float2 dir = normalize(normalCS.xy);              // safe: guarded against 0
positionCS.xy += dir / _ScreenParams.xy * (_OutlineWidth * 2.0) * positionCS.w;
```

Why this shape:

* `clip.w` cancels the perspective divide, so **distance** drops out;
* `/ _ScreenParams.xy * 2` converts **pixels to NDC**, so screen size drops out;
* `_ScreenParams` (the camera's display resolution) rather than
  `_ScaledScreenParams` (the render target) means the width does not change when
  URP's `renderScale` is lowered - the game exposes 0.2-1.0 via
  `RenderScaleSetting.cs`, and with `_ScaledScreenParams` the line would grow on
  screen at low render scale;
* undoing the extrusion in **object space** makes the runtime `localScale`
  cancel, so backpack mode's built-in `0.5x` no longer halves the line;
* the same function feeds a `DepthOnly` pass so depth priming agrees;
* a small `_OutlineZOffset` in clip space removes the z-fight at the silhouette.

Full source: `shaders/PlushieOutline.shader` (⚠️ research artefact, unused).

## 5. Change list

| file | action |
|---|---|
| `shaders/PlushieOutline.shader` | **new** - the complete shader (already written) — ⚠️ **never shipped**: research artefact, not referenced by any code |
| `research/PlushieShaderLoader.sample.cs` | **new** - drop-in for `PlushieModel.cs` — ⚠️ **never adopted**: the sample was not merged into `src/` |
| `tools/build_outline_bundle.ps1` | new (optional) - drives the Unity editor build — ⚠️ **never created** (no Unity editor) |
| `src/PlushieModel.cs` | edit: `GetOutlineMaterial` tries the bundled shader first, else keeps today's URP/Lit fallback — ⚠️ **not implemented**; the shipped `GetOutlineMaterial` still resolves a built-in shader (now URP/Unlit) and never looks for a bundle |
| `src/EmbeddedAssets.g.cs` | edit only if the bundle is embedded (regenerate with `tools/embed_assets.py`) — ⚠️ no bundle to embed; **no change was made** |
| `tools/build_meshes.py` | *no change required*; the shell and its masks stay — ⚠️ partially true: the shell was **not** deleted, but the masks were converted from face deletion to a smooth per-vertex width |

`PlushieModel.GetOutlineMaterial` currently does `ResolveShader()` (URP/Lit) and
sets `_Cull = Front`. The new version is in the sample: construct the material
from `PlushieShaderLoader.CreateOutlineMaterial`, which returns the bundled
material or the exact current fallback. Nothing else in `PlushieModel` changes -
the outline GameObject, `ShadowCastingMode.Off` and parenting stay.

## 6. Verification

> ⚠️ This is the verification plan for the **bundle** route, which was never
> adopted. The shipped route is verified with `research/verify_final_outline.py`,
> `research/measure_final_outline.py` and `research/render_angles.py`; the
> in-game config entry is `Outline Width (pixels)`.

Offline, before touching the game:

1. `python research/measure_outline_width.py` - must show a flat screen-space
   column and a varying object-space column.
2. `python research/preview_outline_methods.py` - writes
   `research/preview/ss_vs_os_<stem>.png` for a visual A/B.
3. `python tools/preview_mesh.py` and `tools/verify_merge.py` still pass (they
   ignore the shell, so they must be unaffected).

In game:

4. BepInEx log shows `Loaded outline shader from plushieoutline.bundle`.
5. Hold the plush, walk from touching distance to far: the line should stay the
   same pixel width. Toggle `Plushie Width (pixels)` in a config entry if wired.
6. Put it in the backpack: the line must not shrink to half.
7. Check there is no z-fighting shimmer on the line; raise `_OutlineZOffset` if
   any appears.
8. Check the eyes/mouth/blush have no ink (the existing mask must survive - it
   is in the mesh, so it will).

## 7. Risks and rollback

> ⚠️ The rollback column assumes the bundle route. Nothing here was needed:
> the CPU implementation in `src/PlushieOutline.cs` was kept and made correct,
> and `shaders/PlushieOutline.shader` is unused.

| risk | mitigation |
|---|---|
| Bundle built with the wrong Unity version -> pink / null shader | `Shader.isSupported` check + automatic fallback to the current URP/Lit object-space outline; log a warning |
| No Unity editor available to the user | fallback path means the mod still ships and still looks like today |
| `_OutlineBakedThickness` drifts when the pipeline changes | it is one property; recompute as `outline_thickness * target_height`, and validate with `research/measure_outline_width.py` |
| Holes in the shell leave gaps at the face | those gaps are intentional; the head is a closed surface so the outer silhouette stays whole |
| Multi-camera / VR | the `UNITY_VERTEX_OUTPUT_STEREO` plumbing is in the shader |
| Rollback | keep the current `GetOutlineMaterial` body behind `if (!screenSpace)`; reverting is deleting one branch and the bundle |

## 8. Note on the "single pass with Stencil" alternative

Drawing the ink on the body mesh itself (one renderer, two passes, stencil to
keep the line behind the body) is possible and removes the second draw call, but:

* the body material is URP/Lit, and URP/Lit has no outline pass to add;
* it would require replacing the body material with a custom shader that
  reimplements URP/Lit's lighting to keep the palette shading correct;
* the current two-mesh split is what makes the face/decal mask and the welded
  outline normals possible in the first place.

Cost of the current split: one extra draw call per plush (there are 1-2 of
them), one extra mesh. That is not worth trading for the risk of breaking the
body shading. Keep the separate shell.
