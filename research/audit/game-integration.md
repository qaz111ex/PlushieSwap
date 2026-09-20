# 审计 D：游戏侧集成事实核验（UnityPy + 反编译）

- 审计员：`audit-game-facts`（共享任务板 **task-4**）
- 游戏目录：`D:\SteamLibrary\steamapps\common\PEAK`（数据 `PEAK_Data`）
- 反编译源码：`D:\zhuanban\youhua\decompiled-latest`
- 被审对象：`D:\zhuanban\Plushie Swap`（README.md / src/ / tools/）
- 工具：Python 3.14.3 + UnityPy 1.25.0 + TypeTreeGeneratorAPI 0.0.10 + numpy
- Unity 版本（实测）：**6000.3.15f1**
- 审计性质：**只读**。本报告是唯一写入的文件。
- 临时脚本目录：`C:\Users\Administrator\AppData\Local\Temp\gaudit\`（不在仓库内，未修改 `src/`、`tools/`、`assets/` 或游戏目录任何文件）

> 方法说明：本模组的 prefab 组件是 `Assembly-CSharp` 里的 MonoBehaviour，游戏资源里**没有**这些脚本的 TypeTree。因此本次核验用 `TypeTreeGeneratorAPI` 从 `PEAK_Data\Managed` 的 DLL 现场生成字段树，再手工拼上 MonoBehaviour 的 9 字段头（UnityPy 1.25 的 `get_nodes()` 只返回脚本字段、不含头部），然后用 `TypeTreeHelper.read_typetree` 直接读对象字节。所有字段值都来自真实资源字节，不是记忆或推断。

---

## 一、结论摘要

### 1.1 假设成立的（符合）

| # | 假设 | 出处 | 实测值 | 判定 |
|---|---|---|---|---|
| A1 | 原版玩偶高度 `0.9635` | README:100、`tools/build_meshes.py:408` | `0.963485` | ✅ 符合 |
| A2 | 原版 Y 范围 `[-0.7345, +0.2290]` | README:101、`build_meshes.py:411-412` | `[-0.734495, +0.228990]` | ✅ 符合 |
| A3 | 原版 XZ 中心 `X=-0.0315` | README:102、`build_meshes.py:409` | `-0.031508` | ✅ 符合 |
| A4 | 原版锚点中点 `(-0.0595,-0.1405,-0.0400)` | README:103、`PlushieModel.cs:1124` | `(-0.059500,-0.140499,-0.040000)` | ✅ 符合 |
| A5 | 锚点 X 间距 `0.5990` | README:104、`build_meshes.py:1196-1197` | `0.599000` | ✅ 符合 |
| A6 | 锚点 3D 间距 `0.6034` | README:104 | `0.603433` | ✅ 符合 |
| A7 | `Item.mass = 5.0` | `Item.cs:117` 默认值；三个 Item 实例实测 | `5.0`（三处全部） | ✅ 符合 |
| A8 | `Item.rightHandOnly = false` | `Item.cs:115` 默认值；实例实测 | `false`（三处全部） | ✅ 符合 |
| A9 | `Item.defaultForward = (0,0,1)`，`+Z` 是视线方向 → 模型正面朝 `-Z` | README:105 | `(0,0,1)`；`CharacterItems.GetItemHoldForward` 返回 `character.data.lookDirection` | ✅ 符合 |
| A10 | `Holder` 静止时是单位变换 | README:136 | pos `(0,0,0)`、rot 单位四元数、scale `(1,1,1)`（两个 prefab 均如此） | ✅ 符合 |
| A11 | 原版 plush 网格挂在 `BingBong_Prop Variant/Holder` 下 | `PlushieModel.cs:884,901-914` | `Holder`(T18395) → `Bing Bong Plush`(T17385, Animator) → `Lip Top`/`Lip Bottom`/`Cube`(mesh 1061) | ✅ 符合 |
| A12 | Squish 控制器只驱动 `Holder.localScale` + 两个锚点 `localPosition` | `PlushieModel.cs:889-891` | 3 条 binding：`Hand_L`@position、`Hand_R`@position、`Holder`@scale。**无其它通道** | ✅ 符合 |
| A13 | 挤压动画**确实会改写** `Hand_L`/`Hand_R.localPosition` | README:130-131 | clip 的 `m_ValueArrayDelta` 与 StreamedClip 关键帧里 `Hand_L.x` 从 `-0.376`→`-0.260`、`Hand_R.x` 从 `0.240`→`0.140` | ✅ 符合（见 §2.3 关于"永久"的保留） |
| A14 | 游戏每**物理帧**读锚点算手位（`CharacterAnimations.ConfigureIK`） | README:125 | `CharacterRagdoll.FixedUpdate():166` 调 `ConfigureIK()`；`ConfigureIK` 内 `GetItemPosLeft/Right` 读 `Hand_L/Hand_R` | ✅ 符合 |
| A15 | 模组从不写锚点 | README:124、`PlushieModel.cs:1066-1070` | `src/` 全文无任何 `Hand_L`/`Hand_R` 写入；游戏侧也**只读不写**（全树 grep 确认） | ✅ 符合 |
| A16 | `_Tint` 的**物品内**读写路径已被 `CookingPatches` 全覆盖 | `CookingPatches.cs:8-37` | `ItemCooking` 与 `BackpackOnBackVisuals` 是**唯一**两条作用于物品 renderer 的路径，两者都已 patch | ✅ 符合 |
| A17 | `ItemCooking` 无子类、`CookVisually` 无 override → 一个 prefix 就够 | `CookingPatches.cs:23-26` | 全反编译树中 `: ItemCooking` 匹配 0 条、`override ... CookVisually` 匹配 0 条 | ✅ 符合 |
| A18 | 关键方法签名与字段名与游戏一致 | 见 §2.5 全表 | 全部逐项核对通过 | ✅ 符合 |
| A19 | `Item.backpackReference` 是公开字段、类型 `Optionable<(byte,BackpackReference)>` | `PlushieModel.cs:1400` | `Item.cs:183` 完全一致 | ✅ 符合 |
| A20 | `Action_AskBingBong` 链路：`RunAction → RPC"Ask" → squishAnim.SetTrigger("Squish")` | README:134、`PlushieModel.cs:888` | 逐环节实测通过（§2.6） | ✅ 符合 |

### 1.2 **不成立的假设**（重点）

| # | 不成立的断言 | 出处 | 实测 | 严重度 |
|---|---|---|---|---|
| **X1** | **"the only GameObjects that actually carry an `Item` component are `BingBong` and `BingBong_Prop Variant`"** | `src/GameHelpers.cs:175-177` | **不符**。全游戏 .assets 扫描共 **373 个** GameObject 带 `Item` 组件（`resources.assets` 178、`level4` 150、`level3` 42、`sharedassets4.assets` 3）。**若限定为"名字以 BingBong/Bing Bong 开头的对象"则成立，且实测为 3 个**（见 §2.7） | 中（注释事实性错误；因限定于 BingBong 前缀，功能上无实际影响） |
| **X2** | **"The other two places in the game that read or write `_Tint`"**（暗示游戏侧只有另外 2 条路径） | `src/CookingPatches.cs:33-36` | **不符**。全反编译树中 `"_Tint"` 字面量共 **6 处**，除物品内 2 处外还有 **3 处**，不是 2 处：漏了 `sc.posteffects.runtime\SCPE\RefractionRenderer.cs:40` 的 `Material.SetColor("_Tint", ...)`（全局后处理材质） | 低（被漏的那条作用于全局后处理材质，永远碰不到物品 renderer；但注释的"两处"枚举是错的） |
| **X3** | README 数值表把 `XZ 中心 Z = +0.0505` 标注为**"原版 XZ 中心"**（未限定） | README:102 | **数值符合但标签不精确**。`+0.0505` 是 **Holder 子树（玩偶本体）** 的中心；**整件物品**（含两只 `Hand`）的 Z 中心是 **`-0.1391`**。X 中心两者相同（`-0.031508`）。`build_meshes.py:399` 原注释写的是"combined bounds size (0.9720, 0.9635, **0.3599**)"，Z 尺寸 `0.3599` 正是 Holder 子树值，README 转录时丢掉了限定语 | 低-中（会误导复查者按整件物品测量而得到 `-0.1391`；但对齐目标是玩偶本体，取值本身正确） |
| **X4** | README:18 **"保留原版语音与全部游戏行为：不修改任何音频和游戏逻辑"** | README:18 | **不符**（措辞层面）。本模组通过 Harmony 补丁**命中 9 个不同的游戏方法**（`src/` 里共 10 条 `[HarmonyPatch(typeof(...))]`，其中 `Item.SetState` 被 prefix + postfix 各挂一次）。其中 `CookingPatches.ItemCooking_UpdateCookedBehavior` 把 `setup` 字段**提前置 true**，导致 base 方法**首次**调用时会多执行一次 `item.WasActive()`（原版首次调用 `setup==false` 不会执行）。这是可观察的行为差异 | 低（一次额外的 `WasActive()` 只把物品加回 `ALL_ACTIVE_ITEMS` 并清零计时，无玩法后果；但"不修改任何游戏逻辑"的表述过强） |

### 1.3 需要提醒的"共用数值、不同几何"陷阱（非直接不成立，但真实存在）

`resources.assets` 里**两个** prefab 都带 `Item` 且 `UIData.itemName` 都是 `"Bing Bong"`，模组的 `GameHelpers.IsBingBongItem` 会**同时**命中它们：

| prefab | path_id | 锚点（item-local） | Holder 子树尺寸 | 整件尺寸 |
|---|---|---|---|---|
| `BingBong_Prop Variant` | 11133 | L `(-0.359,-0.177002,-0.040)` / R `(0.240,-0.103996,-0.040)` | `(0.9720, 0.9635, 0.3599)` | `(0.9720, 0.9635, 0.7392)` |
| `BingBong` | 4284 | **完全相同** | **`(1.1942, 1.1884, 0.4628)`** | `(1.1942, 1.1884, 0.8897)` |

- 锚点数值两者**逐位相同**，所以 `HoldOffsetFor()`（只用锚点中点）对两者都成立。
- 但 README 的"原版玩偶高度 0.9635 / Y 范围 / XZ 中心"**只对 `BingBong_Prop Variant` 成立**；`BingBong`(#4284) 的高度是 `1.1884`、Y 范围 `[-0.757917, +0.430445]`。
- README 与 `build_meshes.py` 的注释都没有点名是哪个 prefab。`PlushieModel.cs:1121` 的注释写了 "read from \"BingBong_Prop Variant\""（正确），但 README 的数值表没有这个限定。
- 影响：如果游戏运行时确实会用 #4284 作为可拾取物品，模组仍会替换它，而模型是按 `BingBong_Prop Variant` 的 0.9635 高度生成的 → 尺寸不匹配。**我无法判定 #4284 是否会在运行时被实例化为物品**（见 §三）。

---

## 二、逐条实测详情

### 2.0 资源文件清单与对象普查

```
$ python - <<'PY'
import UnityPy, os
GAME = r"D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data"
env = UnityPy.load(os.path.join(GAME, "resources.assets"))
c = {}
for o in env.objects: c[o.type.name] = c.get(o.type.name, 0) + 1
print(len(list(env.objects)), "objects"); print(c)
PY
```

原始输出（节选）：

```
resources.assets 对象普查：
 AnimationClip 273 / Animator 250 / AnimatorController 43 / AnimatorOverrideController 4
 GameObject 8460 / MonoBehaviour 6473 / Mesh 344 / MeshRenderer 2026 / SkinnedMeshRenderer 76
 Transform 7390 / Material 487 / Shader 51 / MonoScript 2
```

`globalgamemanagers.assets` 普查：

```
globalgamemanagers.assets object census:
   ComputeShader 18 / Material 6 / MonoBehaviour 78 / MonoScript 5879
   PreloadData 1 / Shader 146 / ShaderVariantCollection 1 / Sprite 1 / Texture2D 62
```

- **MonoScript 表**：`globalgamemanagers.assets` 里有 **5879** 个 `MonoScript`，`path_id 3020` → `m_ClassName = "Item"`。`resources.assets` 自身只有 2 个 MonoScript（`PeakBuildSettings`、`BuildConfig`）。
- 这直接证实了 `GameHelpers.cs:174-175` 注释所描述的机制（"MonoScript table in globalgamemanagers.assets"）是**真实存在且可用**的。

---

### 2.1 BingBong prefab 的完整层级、transform、组件

**实测命令**（`C:\Users\Administrator\AppData\Local\Temp\gaudit\hier.py`、`measure.py`、`desc.py`）：

```python
env = UnityPy.load(r"...\PEAK_Data\resources.assets")
transforms  = {o.path_id: o.read_typetree() for o in env.objects if o.type.name == "Transform"}
gameobjects = {o.path_id: o.read_typetree() for o in env.objects if o.type.name == "GameObject"}
# m_Father 建树，从 GameObject 11133 的 Transform 18002 递归
# MonoBehaviour 类名 = m_Script PPtr 经 externals[fileID-1] 解析到 globalgamemanagers.assets 的 MonoScript
```

#### `BingBong_Prop Variant`（resources.assets path_id **11133**，Transform 18002）

```
'BingBong_Prop Variant'  T18002 G11133
   local pos=(10.661000, 0.960000, 58.708000)
   local rot=(0.645237, 0.006340, -0.008742, 0.763906)
   local scale=(1.000000, 1.000000, 1.000000)
   comps: Transform#18002, Item#32519, Photon.Pun.PhotonView#32515, ItemParticles#31217,
          ItemPhysicsSyncer#33422, LootData#30855, ItemUseFeedback#33438, ItemImpactSFX#33480,
          BingBongsVisuals#33745, BingBong#31808, Action_AskBingBong#32706, Animator#23496,
          AudioSource#23315, BingBongMouth#33440, ItemCooking#34110, Peak.PhotonCleanupHelper#33126
  'Coll'  T12558 G9796        pos=(-0.034996, 0.087006, 0.166473)
                              rot=(-0.508347,-0.491512,-0.491512, 0.508347) scale=(0.334140,)*3
                              comps: Transform#12558, MeshCollider#23023   (mesh 1061, m_Convex=true)
  'Hand_R'  T14574 G6926      pos=(0.240000, -0.103996, -0.040000)
                              rot=(0.257860, 0.718665, 0.551452, 0.336050) scale=(1,1,1)
                              comps: Transform#14574, HandVisual#28618
    'Hand'  T13793 G5403      pos=(0,0,0) rot=(0.000000, 0.707106, 0.707107, -0.000001)
                              scale=(0.049332, 0.049332, 0.049332)
                              comps: Transform#13793, MeshFilter#21085(mesh 1215), MeshRenderer#19664
  'Hand_L'  T15491 G8523      pos=(-0.359000, -0.177002, -0.040000)
                              rot=(-0.318182, 0.676361, 0.518990, -0.414663) scale=(1,1,1)
                              comps: Transform#15491, HandVisual#30215
    'Hand'  T13410 G5741      pos=(0,0,0) rot=(-0.707107, -0.000000, -0.000000, 0.707107)
                              scale=(0.049330, -0.049330, 0.049330)
                              comps: Transform#13410, MeshFilter#20932(mesh 1215), MeshRenderer#19550
  'Particles'  T16446 G3514   pos=(0,0,0) rot=(0,0,0,1) scale=(1,1,1)  comps: Transform#16446
    'VFX_Smoke'  T13666 G5696 pos=(0,0,0.108) rot=(-0.707107,0,0,0.707107) scale=(1,1,1)
                              comps: Transform#13666, ParticleSystem#25200, ParticleSystemRenderer#25873
  'Holder'  T18395 G3568      pos=(0,0,0) rot=(-0.000000,-0.000000,-0.000000,1) scale=(1,1,1)
                              comps: Transform#18395          <-- 只有 Transform，单位变换
    'Bing Bong Plush'  T17385 G10901
                              pos=(-0.084000, -0.090000, -0.011000)
                              rot=(0.000000, 0.707107, 0.000000, 0.707107)
                              scale=(0.810767, 0.810767, 0.810767)
                              comps: Transform#17385, Animator#23399  (controller 2410 "Bing Bong Plush")
      'Lip Top'     T13648 G3039   pos=(-0.211,-0.093, 0.120) rot=(-0.707107,0,0,0.707107)
                                    scale=(0.334140,)*3  comps: MeshFilter#21851(mesh 1269), MeshRenderer#20070
      'Lip Bottom'  T13842 G5252   pos=(-0.211,-0.107, 0.120) rot=(-0.707107,0,0,0.707107)
                                    scale=(0.334140,)*3  comps: MeshFilter#21370(mesh 1310), MeshRenderer#18852
      'Cube'        T16592 G9612   pos=(-0.050241,0.050000,0.020315) rot=(-0.707107,0,0,0.707107)
                                    scale=(0.334140,)*3  comps: MeshFilter#21653(mesh 1061), MeshRenderer#20383
  <外部引用 Transform T27246>   (m_Children 里第 6 项，path_id 不在 resources.assets 内)
```

**子节点顺序**（`m_Children` 原始顺序，Unity 的 `GetComponentInChildren` 深度优先序依赖它）：
`Hand_L` → `Hand_R` → `Particles` → `Coll` → `Holder` → `<外部 T27246>`

**锚点（item-local，即根 local）**：

```
Hand_R: pos = ( 0.240000, -0.103996, -0.040000)
Hand_L: pos = (-0.359000, -0.177002, -0.040000)
X 间距  = 0.599000
3D 距离 = 0.603433
中点    = (-0.059500, -0.140499, -0.040000)
```

#### `BingBong`（resources.assets path_id **4284**，Transform 12964）

结构与组件清单**逐项相同**（同名 16 个组件），但子节点顺序不同（`Holder` → `Hand_L` → `Particles` → `Hand_R` → `Coll` → `<外部 T27551>`），且**几何不同**：

```
'BingBong'  T12964 G4284   pos=(97.019997, 66.749001, -180.779999) rot=(0,0,0,1) scale=(1,1,1)
  'Holder'  T12535 G9331   pos=(0,0,0) rot=(-0,-0,-0,1) scale=(1,1,1)   comps: Transform#12535
    'Bing Bong Plush' T11370 G4005  pos=(-0.013, 0.037003, 0.216003)
                                     rot=(-0.000000, -0.695102, -0.000000, 0.718911)
                                     scale=(1.000000, 1.000000, 1.000000)   <-- 与 variant 的 0.810767 不同
                                     comps: Transform#11370, Animator#23488 (controller 2410)
      'Cube' T14379 G3728 / 'Lip Top' T14905 G9839 / 'Lip Bottom' T15168 G8024
  'Hand_L'  T13479 G6829   pos=(-0.359000, -0.177002, -0.040000)  <-- 与 variant 相同
  'Hand_R'  T15834 G8496   pos=( 0.240000, -0.103996, -0.040000)  <-- 与 variant 相同
  'Coll' T18404 G3016 / 'Particles' T14111 G9393 / 'VFX_Smoke' T14920 G7571
```

**锚点中点与间距：与 variant 逐位相同**（`(-0.059500,-0.140499,-0.040000)`、`0.599000`、`0.603433`）。

#### `level3` path_id **6161**（场景实例）

```
GO 6161 transform: 8516   ancestors: ['BingBong_Prop Variant']
'BingBong_Prop Variant' T8516 G6161  pos=(-27.634001, 2.651000, 99.822281)
                                      rot=(-0.0088, 0.8551, 0.5183, -0.0040) scale=(1,1,1)
  comps: 8516, 21008, 17215, 19938, 21655, 19637, 21673, 21706, 21884, 20444, 21173, 11672,
         11508, 21676, 22185, 21400
  'Coll' T7023 / 'Hand_R' T7567 (0.240,-0.103996,-0.040) / 'Hand_L' T7785 (-0.359,-0.177002,-0.040)
  'Particles' T8045 / 'Holder' T8617 (0,0,0,单位变换)
    'Bing Bong Plush' T8334  pos=(-0.084000,-0.090000,-0.011000)
                             rot=(0.0000,0.7071,0.0000,0.7071) scale=(0.810767,)*3
      'Lip Top' T7313 / 'Lip Bottom' T7365 / 'Cube' T8080
```

`level3` 实例的 transform 与 `BingBong_Prop Variant` prefab **逐位一致**（`Holder` 单位变换、`Bing Bong Plush` 的 `0.810767` 缩放与 `0.7071` 旋转都相同）→ 是同一 prefab 的场景实例。

#### 材质与 `_Tint` / `_Interactable`（实测）

```
MeshRenderer#19664 GO#5403 materials=1 pids=[177]   (Hand_R/Hand)
MeshRenderer#19550 GO#5741 materials=1 pids=[177]   (Hand_L/Hand)
MeshRenderer#20070 GO#3039 materials=1 pids=[102]   (Lip Top)
MeshRenderer#18852 GO#5252 materials=1 pids=[102]   (Lip Bottom)
MeshRenderer#20383 GO#9612 materials=1 pids=[102]   (Cube = 身体, mesh 1061)

material#177 name='M_Player'          shader={'m_FileID': 1, 'm_PathID': 210}
material#102 name='M_BingBongPlush'   shader={'m_FileID': 1, 'm_PathID': 210}

material#102 'M_BingBongPlush'
   declares _Interactable: True   _Tint: True   _Cull 存在: True (值 2.0 = Back)
   m_SavedProperties.m_Colors 里 _Tint = (0.735849, 0.735849, 0.735849, 1.0)
material#177 'M_Player'
   declares _Interactable: True   _Tint: True   _Cull 存在: True (值 2.0 = Back)
```

> 注意：**每个渲染器只有 1 个材质**。`ItemCooking.CookVisually` 里 `renderers[i].materials[j]` 的内层循环因此只跑 1 次。

---

### 2.2 README / 代码声称的原版数值逐条比对

**实测命令**（`C:\Users\Administrator\AppData\Local\Temp\gaudit\bbox3.py`、`bbox4.py`）：把每个 `MeshFilter` 的网格顶点经 `m_StreamData`（`.resS`）解出，乘上从 prefab 根到该节点的世界矩阵，再左乘根矩阵的逆 → item-local 坐标；分别对"整件物品（含双手）"和"Holder 子树（玩偶本体 + 嘴唇）"统计包围盒。

顶点解码验证（`verify_mesh.py`）：用 `m_LocalAABB` 反推 stride，确认 `mesh#1061` stride=56、`mesh#1215` stride=36 时解出的 AABB 与 `m_LocalAABB` **完全吻合**（`MATCH=True`）。

**原始输出**：

```
PREFAB BingBong_Prop Variant
--- WHOLE ITEM (all MeshFilters under item) ---
    X [-0.517491, +0.454476]  size 0.971967
    Y [-0.734495, +0.228990]  size 0.963485
    Z [-0.508743, +0.230505]  size 0.739248
    centre X -0.031508  Z -0.139119
--- HOLDER SUBTREE ONLY (body + lips, no hands) ---
    nodes: ['Lip Top', 'Lip Bottom', 'Cube']
    X [-0.517491, +0.454476]  size 0.971967  centre -0.031508
    Y [-0.734495, +0.228990]  size 0.963485  centre -0.252752
    Z [-0.129438, +0.230505]  size 0.359943  centre +0.050534

PREFAB BingBong
--- WHOLE ITEM ---
    X [-0.672883, +0.521343]  size 1.194226
    Y [-0.757917, +0.430445]  size 1.188362
    Z [-0.508743, +0.380936]  size 0.889680
    centre X -0.075770  Z -0.063904
--- HOLDER SUBTREE ONLY ---
    X [-0.672883, +0.521343]  size 1.194226
    Y [-0.757917, +0.430445]  size 1.188362
    Z [-0.081851, +0.380936]  size 0.462787
```

| 项目 | 声称值 | 实测（Holder 子树 / 整件） | 判定 |
|---|---|---|---|
| 原版玩偶高度 | `0.9635` | `0.963485` / `0.963485` | ✅ 符合 |
| Y 范围 | `[-0.7345, +0.2290]` | `[-0.734495, +0.228990]` / 同 | ✅ 符合 |
| XZ 中心 X | `-0.0315` | `-0.031508` / `-0.031508` | ✅ 符合 |
| XZ 中心 Z | `+0.0505` | **`+0.050534`** / **`-0.139119`** | ⚠️ 数值符合 Holder 子树；标签见 **X3** |
| 锚点中点 | `(-0.0595,-0.1405,-0.0400)` | `(-0.059500,-0.140499,-0.040000)` | ✅ 符合 |
| 锚点 X 间距 | `0.5990` | `0.599000` | ✅ 符合 |
| 锚点 3D 间距 | `0.6034` | `0.603433` | ✅ 符合 |
| `tools/build_meshes.py:399` "combined bounds size (0.9720, 0.9635, **0.3599**)" | — | Holder 子树 `(0.971967, 0.963485, 0.359943)` | ✅ 符合（证实 "combined" = 本体+嘴唇，不含双手） |

**`Item.defaultPos` / `mass` / `rightHandOnly` / `defaultForward`（实测值）**

用生成的 TypeTree 直接读 `Item` MonoBehaviour 字节（`C:\Users\Administrator\AppData\Local\Temp\gaudit\final.py`、`gaps.py`）：

| 字段 | `BingBong_Prop Variant` #32519 | `BingBong` #30819 | `level3` 实例 #21008 |
|---|---|---|---|
| `defaultPos` | `(0.0, 0.0, 0.9)` | `(0.0, 0.0, 0.9)` | `(0.0, 0.0, 0.9)` |
| `defaultForward` | `(0.0, 0.0, 1.0)` | `(0.0, 0.0, 1.0)` | `(0.0, 0.0, 1.0)` |
| `gliderHold` | `false` | `false` | `false` |
| `rightHandOnly` | `false` | `false` | `false` |
| `mass` | `5.0` | `5.0` | `5.0` |
| `carryWeight` | `2` | `2` | `2` |
| `usingTimePrimary` | `0.25` | `0.25` | `0.25` |
| `showUseProgress` | `true` | `true` | `true` |
| `overrideJetpackFuel` | `true` | `true` | `true` |
| `itemID` | `0` | `0` | `0` |
| `forceScale` | `false` | `false` | `false` |
| `blocksSprint` | `true` | `true` | `true` |
| `UIData.itemName` | `"Bing Bong"` | `"Bing Bong"` | `"Bing Bong"` |
| `UIData.canPocket` / `canBackpack` | `false` / `false` | `true` / `true` | `false` / `false` |
| `UIData.mainInteractPrompt` | `"ask"` | `"ask"` | `"ask"` |
| `UIData.icon` | `path_id 603` | `path_id 603` | `(fileID 3) path_id 603` |

字节消耗自检（`prefix.py`）：

```
Item#32519: byte_size=460 typetree_consumed=420 gap=40
  through defaultPos        consumed= 32  value={}
  through defaultForward    consumed= 44
  through gliderHold        consumed= 60
  through rightHandOnly     consumed= 64  value=False
  through mass              consumed= 68  value=5.0
  ...
  through timeSinceWasActive consumed=420 value=0.0
```

- 40 字节的 gap 是 UnityPy 生成的 TypeTree 未包含的尾部字段（tail 全 `00`，第 16-20 字节是 `01 00 00 00`），不影响已读字段。**已读到的 `defaultPos`/`mass`/`rightHandOnly`/`defaultForward` 位置与字节消费量自洽**（`defaultPos` 在 offset 20，`defaultForward` 在 32，`gliderHold` 在 44，`rightHandOnly` 在 45，`mass` 在 46——与 `Item.cs:109-117` 的声明顺序一致）。
- 因此 `mass=5.0`、`rightHandOnly=false` 是**实测值**，且与 `Item.cs:117`（`public float mass = 5f;`）与 `Item.cs:115`（`public bool rightHandOnly;` 默认 false）**一致**。

**`Item.defaultPos` 的运行时行为**（`Item.cs:417-430`，反编译原文）：

```csharp
StartCoroutine(DefaultPosRoutine());
IEnumerator DefaultPosRoutine() {
    Vector3 cachedDefaultPos = defaultPos;                       // (0,0,0.9)
    Vector3 startingDefaultPos = new Vector3(defaultPos.x, defaultPos.y, 0.7f);
    float t = 0f;
    while (t < 1f) { t += Time.fixedDeltaTime * 5f;
        defaultPos = Vector3.Lerp(startingDefaultPos, cachedDefaultPos, t);
        yield return new WaitForFixedUpdate(); }
    defaultPos = cachedDefaultPos;                               // 回到 (0,0,0.9)
}
```

→ `defaultPos` 稳态是 `(0,0,0.9)`；`CharacterRagdoll.cs:222` 用它把 `animationItemTransform` 放在 `animationLookTransform.TransformPoint(defaultPos)`。

**`defaultForward` 的运行时用法**（`CharacterRagdoll.cs:223-237` 反编译原文）：

```csharp
Vector3 forward = character.data.lookDirection * character.data.currentItem.defaultForward.z;
forward += character.data.lookDirection_Right * character.data.currentItem.defaultForward.x;
forward += character.data.lookDirection_Up * character.data.currentItem.defaultForward.y;
...
character.refs.animationItemTransform.rotation = Quaternion.LookRotation(forward);
```

→ 当 `defaultForward = (0,0,1)` 时 `forward = lookDirection`。配合 `CharacterItems.GetItemHoldForward`（`CharacterItems.cs:701-704`，同样返回 `character.data.lookDirection`）与 `GetItemHoldRotation`（`Quaternion.LookRotation(lookDirection, lookDirection_Up)`），证实 README:105 "物品 `+Z` 是玩家视线方向，所以模型正面朝 `-Z`" —— **符合**。

---

### 2.3 `BingBong` Animator controller（path_id 2411）与 `BingBongSquish`（path_id 1442）

**实测命令**：`C:\Users\Administrator\AppData\Local\Temp\gaudit\anim.py`、`clip2.py`、`clip3.py`、`bind.py`、`hash.py`、`stream.py`

#### controller 2411

```
pid 2411 type AnimatorController byte_size 852   m_Name = "BingBong"
m_Controller.m_LayerArray: 1 层 (m_DefaultWeight 0.0, m_IKPass false)
m_StateMachineArray[0].m_StateConstantArray: 2 个 state
   [0] m_NameID=3795944341 ("New State")     m_WriteDefaultValues=true  m_Loop=true  m_Speed=1.0
   [1] m_NameID=3226939378 ("BingBongSquish") m_WriteDefaultValues=true m_Loop=true  m_Speed=1.0
       m_TransitionConstantArray[0]: m_DestinationState=0, m_ExitTime=0.959924,
                                     m_HasExitTime=true, m_TransitionDuration=0.011832
m_AnyStateTransitionConstantArray:
   [0] m_ConditionConstantArray[0]: m_ConditionMode=1, m_EventID=2750837211,
                                     m_EventThreshold=0.0, m_ExitTime=0.0
       m_DestinationState=1, m_TransitionDuration=0.0, m_HasExitTime=false
m_DefaultState = 0
m_Values.m_ValueArray: [ {m_ID: 2750837211, m_Type: 9 (=Trigger), m_Index: 0} ]
m_DefaultValues.m_BoolValues = [false]
m_TOS: (851463623,"BingBongSquish -> New State") (2105523844,"GravityWeight")
       (3226939378,"BingBongSquish") (3047116060,"Base Layer.BingBongSquish")
       (2750837211,"Squish") (0,"") (756556552,"Base Layer") (3795944341,"New State")
       (4032366518,"AnyState -> BingBongSquish") (533282942,"Base Layer.New State")
       (4065460684,"Entry -> Base Layer.BingBongSquish")
       (2859112571,"Base Layer.BingBongSquish -> Base Layer.New State")
m_AnimationClips: [ path_id 1442 ]
```

**Trigger 名验证**（`hash.py`，Unity 的 `m_EventID` 是 CRC32）：

```
crc32('Squish')        = 2750837211   == controller m_EventID   ✅
crc32('New State')     = 3795944341   == state[0] m_NameID      ✅
crc32('BingBongSquish')= 3226939378   == state[1] m_NameID      ✅
```

#### clip 1442

```
pid 1442 type AnimationClip byte_size 3536   m_Name = "BingBongSquish"
m_Legacy=False  m_Compressed=False  m_SampleRate=60.0  m_WrapMode=0
m_HasGenericRootTransform=False  m_HasMotionFloatCurves=False  m_Events=[]
m_MuscleClip.m_StartTime = 0.0
m_MuscleClip.m_StopTime  = 0.46666666865348816      <-- 时长 0.46667 s
m_MuscleClip.m_LoopTime  = True
m_IndexArray len = 200   (全部为 -1)
m_ValueArrayDelta len = 9:
  [0] start=-0.37599998712539673 stop=-0.37599998712539673
  [1] start=-0.17700199782848358 stop=-0.17700199782848358
  [2] start=-0.03999999910593033 stop=-0.03999999910593033
  [3] start= 0.23999999463558197 stop= 0.23999999463558197
  [4] start=-0.10399629920721054 stop=-0.10399629920721054
  [5] start=-0.03999999910593033 stop=-0.03999999910593033
  [6] start=1.0 stop=1.0   [7] start=1.0 stop=1.0   [8] start=1.0 stop=1.0
m_Clip.data.m_DenseClip:  FrameCount=30 CurveCount=0 SampleRate=60 BeginTime=0 SampleArray=[]
m_Clip.data.m_StreamedClip: curveCount=9 discreteCurveCount=0 data len=284
m_Clip.data.m_ConstantClip.data len = 0
m_ValueArrayReferencePose len = 0
```

**绑定通道**（`m_ClipBindingConstant.genericBindings`，3 条）：

| # | `path` | `attribute` | `typeID` | 解析 |
|---|---|---|---|---|
| 0 | `552982707` | `1` | `4` | `crc32("Hand_L")` → **position**（Transform） |
| 1 | `3673875920` | `1` | `4` | `crc32("Hand_R")` → **position**（Transform） |
| 2 | `3506728331` | `3` | `4` | `crc32("Holder")` → **scale**（Transform） |

（CRC 验证：`crc32('Hand_L')=552982707`、`crc32('Hand_R')=3673875920`、`crc32('Holder')=3506728331`，三条**全部命中**。Unity 的 `attribute`：1=position、2=rotation、3=scale、4=euler。）

**StreamedClip 关键帧解码**（`stream.py`，按 Unity 的 `index + 3 float 系数 + value` 格式逐帧解）：

```
--- frame 0: time=-3.4028e+38 (离散标记) keyCount=9
    idx=0 coeff=(0,0,0) value=-0.376000     <-- Hand_L.x
    idx=1 coeff=(0,0,0) value=-0.177002     <-- Hand_L.y
    idx=2 coeff=(0,0,0) value=-0.040000     <-- Hand_L.z
    idx=3 coeff=(0,0,0) value= 0.240000     <-- Hand_R.x
    idx=4 coeff=(0,0,0) value=-0.103996     <-- Hand_R.y
    idx=5 coeff=(0,0,0) value=-0.040000     <-- Hand_R.z
    idx=6..8 coeff=(0,0,0) value=1.000000   <-- Holder.scale xyz
--- frame 1: time=0.0        keyCount=9
    idx=0 coeff=(-463.999969, 23.199999, 2.320000) value=-0.376000
    idx=3 coeff=( 399.999969,-19.999998,-2.000000) value= 0.240000
    idx=6 coeff=(1770.879883,-88.544022,-8.854400) value=1.000000
    idx=7 coeff=(-532.491699, 26.624584, 2.662458) value=1.000000
    idx=8 coeff=(-191.999908,  9.599996, 0.960000) value=1.000000
--- frame 2: time=0.050000   keyCount=9
    idx=0 coeff=(29.460312,-12.152380,1.160000) value=-0.260000   <-- Hand_L.x 变到 -0.260
    idx=3 coeff=(-25.396820,10.476189,-1.000000) value= 0.140000  <-- Hand_R.x 变到 +0.140
    idx=6 coeff=(-112.436813,46.380188,-4.427200) value=0.557280  <-- Holder.scale.x
    idx=7 coeff=(33.808998,-13.946211,1.331229)  value=1.133123  <-- Holder.scale.y
    idx=8 coeff=(12.190470,-5.028569,0.480000)   value=1.048000  <-- Holder.scale.z
--- frame 3: time=0.200000   keyCount=9   (与 frame 2 同值)
--- frame 4: time=0.316667   keyCount=9
    idx=0 value=-0.376000   idx=3 value=0.240000   idx=6..8 value=1.0   <-- 回到原版
--- frame 5: time=0.466667   keyCount=9
    idx=0 value=-0.376000   idx=3 value=0.240000   idx=6..8 value=1.0   <-- 回到原版（末帧）
--- frame 6: time=inf keyCount=0
consumed 284 of 284
```

#### 判定："动画会永久改写 Hand_L.position"

- **"动画会改写 Hand_L/Hand_R.localPosition" → ✅ 成立**。三条 binding 与 9 个 value 通道逐位对上锚点的 x/y/z，关键帧里 `Hand_L.x` 确实在 `-0.376` ↔ `-0.260`、`Hand_R.x` 在 `0.240` ↔ `0.140` 之间变化。这解释了 compat.md 引用的运行时日志 `Hand_R: anchor node x=0.14002, authored 0.24000 (MOVED BY THE GAME)`。
- **"永久" → ⚠️ 部分成立，需限定**。序列化数据显示：
  - clip 的**末帧**（`t=0.466667`）三条通道全部回到原版数值（`-0.376/-0.177002/-0.04`、`0.24/-0.103996/-0.04`、`1/1/1`）。
  - 两个 state 的 `m_WriteDefaultValues` 都是 `true`。
  - 因此**稳态下锚点回到原版值**；真正的风险窗口是**动画播放中**（0.4667 s）与**过渡中**（`BingBongSquish → New State` 的 `m_ExitTime=0.959924`、`m_TransitionDuration=0.011832`）。
  - 也就是说：任何在动画**播放期间**读/写锚点的代码（例如"对称收拢手"这类方案）会看到被动画覆盖的值，这正是 README:130-131 说"该方案无法稳定工作"的机制。**README 的措辞"会直接改写锚点节点"是准确的**；把它读成"永久偏移"则超出序列化数据能支持的范围。
- 结论：**README 的表述符合实测**；若审计方用的是"永久改写"这一更强措辞，则**无法仅凭资源数据判定**（需要运行时观察，见 §三）。

#### controller 2410（`Bing Bong Plush` 子节点上的 Animator，非 Squish 用）

```
controller 2410 m_Name = "Bing Bong Plush"
clips: [1443, 1444, 1443, 1444]
m_TOS 含 "Mouth.Talk Blend" / "Mouth Closed" / "Mouth open" / "Mouth Blend"
clip 1443 'Mouth Closed': bindings path=crc32('Lip Top')@attr4, crc32('Lip Bottom')@attr4
clip 1444 'Mouth open'  : bindings path=crc32('Lip Bottom')@attr4, crc32('Lip Top')@attr4
```

（`crc32('Lip Top')=2970177832`、`crc32('Lip Bottom')=3406874266` 均命中 → 是嘴巴开合动画，attr 4 = euler 旋转。与 Squish 无关，`Action_AskBingBong.anim` 指向它。）

---

### 2.4 游戏侧读写 `_Tint` 的全部代码路径

**实测命令**（全反编译树穷举，含 `sc.posteffects.runtime` 等所有 assembly）：

```powershell
Get-ChildItem -Recurse -File -Filter *.cs |
  Select-String -Pattern '"_Tint"' -SimpleMatch | Select-Object Path,LineNumber,Line
Get-ChildItem -Recurse -File -Filter *.cs |
  Select-String -Pattern 'PropertyToID\("_Tint|TintId|tintID'
```

**原始输出（全部 6 处，无遗漏）**：

| # | 文件:行 | 操作 | 作用对象 | 是否在物品子树内 | 是否被 CookingPatches 覆盖 |
|---|---|---|---|---|---|
| 1 | `Assembly-CSharp\ItemCooking.cs:96` | `material.GetColor("_Tint")` | `GetComponentsInChildren<MeshRenderer>()` + `<SkinnedMeshRenderer>(true)` | **是** | ✅ `ItemCooking_UpdateCookedBehavior` prefix（`CookingPatches.cs:61-94`） |
| 2 | `Assembly-CSharp\ItemCooking.cs:131` | `materials[j].SetColor("_Tint", ...)` | 同上（`CookVisually`） | **是** | ✅ 同上（`renderers` 列表已被替换） |
| 3 | `Assembly-CSharp\BackpackOnBackVisuals.cs:58` | `material.GetColor("_Tint")` | `GetComponentsInChildren<MeshRenderer>()` | **是**（背包上的玩偶视觉） | ✅ `BackpackOnBackVisuals_InitRenderers` prefix（`CookingPatches.cs:97-121`） |
| 4 | `Assembly-CSharp\BackpackOnBackVisuals.cs:80` | `material.SetColor("_Tint", ...)` | 同上（`CookVisually`） | **是** | ✅ 同上 |
| 5 | `Assembly-CSharp\SetRockColors.cs:18` | `obj.SetColor("_Tint", tint)` | 序列化的 `public Material[] matsToEdit` | **否**（岩石材质资产） | 不需要（`CookingPatches.cs:34` 已声明） |
| 6 | `Assembly-CSharp\Peak\ScoutmasterSoulPillar.cs:161-162` | `SetColor` / `DOColor("_Tint")` | `glassShards[i].GetComponent<MeshRenderer>()` | **否**（场景对象） | 不需要（`CookingPatches.cs:35` 已声明） |
| **7** | **`sc.posteffects.runtime\SCPE\RefractionRenderer.cs:40`** | **`Material.SetColor("_Tint", volumeSettings.tint.value)`** | **全局后处理 Material** | **否** | **不需要，但 `CookingPatches.cs:33-36` 的注释漏了它（见 X2）** |

**判定**：

- ✅ **物品内两条路径（#1-4）确实已 100% 覆盖**，且由于 `ItemCooking` 无子类、`CookVisually` 无 override（实测全树 0 命中），一个 `UpdateCookedBehavior` prefix 就足够——`CookingPatches.cs:23-26` 的推理**正确**。
- ❌ `CookingPatches.cs:33-36` 的注释说 "The other two places in the game that read or write `_Tint`"（游戏侧只有另外**两**处）——**不符**，实际有**三**处（#5、#6、#7）。漏掉的是 SCPE 后处理（#7）。
  - 影响评估：**无实际功能影响**。#7 写的是全局后处理材质（`Hidden/SC Post Effects/Refraction` 的 pass material），永远不会指向物品 renderer；#5 作用于岩石材质资产；#6 作用于 `ScoutmasterSoulPillar` 的玻璃碎片（场景对象，`glassShards` 是 `Rigidbody[]`，不在任何物品子树内）。三者都无法碰到模组创建的 renderer。但注释的枚举**事实错误**，下次复查会以它为据而漏掉 SCPE。
  - 补充实测：`SetRockColors` 在游戏里共 **18** 个实例（`level4/12/13/15/17/19/20/23/24` 等），`ScoutmasterSoulPillar` 共 **22** 个实例（`level10..15` 等）；两者的 `matsToEdit`/`glassShards` 都是各自 prefab 内的 PPtr 数组，与 `BingBong` prefab 无交集。

**附带发现（死代码）**：`Item.cs:217` 声明了 `protected Color originalTint;`，**全反编译树中除该声明外没有任何读写**（`grep originalTint` 仅 1 条命中）。这不是 `_Tint` 路径，但 `Item` 类里确有一个从未使用的 `_Tint` 相关字段，容易被误当成一条路径。

**另一个附带发现（补丁引入的行为差异，见 X4）**：`CookingPatches.cs:93` 在 base 方法运行**之前**把 `setup` 置为 `true`，而 base 方法 `ItemCooking.cs:73-76` 是：

```csharp
if (setup) { item.WasActive(); }        // 前置：setup 已被模组置 true → 会执行
IntItemData data = item.GetData<IntItemData>(DataEntryKey.CookedAmount);
...
if (!setup) { setup = true; /* 发现 renderers、读 _Tint */ }
```

原版**首次**调用时 `setup==false` → **不**调 `WasActive()`；模组 patch 后首次调用时 `setup==true` → **会**调。差异是 `ALL_ACTIVE_ITEMS.Add(this)` + `timeSinceWasActive=0`（`Item.cs:1317-1325`），无玩法后果，但确实改变了游戏逻辑的执行路径。

**补丁目标真实性与签名核对**（反编译原文，逐条）：

| 补丁声明 | 游戏真实签名 | 位置 | 判定 |
|---|---|---|---|
| `ItemCooking.UpdateCookedBehavior` | `public virtual void UpdateCookedBehavior()` | `ItemCooking.cs:71` | ✅ |
| `BackpackOnBackVisuals.InitRenderers` | `private void InitRenderers()` | `BackpackOnBackVisuals.cs:52` | ✅ |
| `ItemCooking.renderers` | `private Renderer[] renderers;` | `ItemCooking.cs:32` | ✅ |
| `ItemCooking.defaultTints` | `private Color[] defaultTints;` | `ItemCooking.cs:34` | ✅ |
| `ItemCooking.setup` | `private bool setup;` | `ItemCooking.cs:36` | ✅ |
| `BackpackOnBackVisuals.renderers` | `private MeshRenderer[] renderers;` | `BackpackOnBackVisuals.cs:13` | ✅ |
| `BackpackOnBackVisuals.defaultTints` | `private Color[] defaultTints;` | `BackpackOnBackVisuals.cs:15` | ✅ |

`FieldRefAccess` 的字段名与类型**全部对上**。这些字段都是 `private` 且**未被序列化**（实测：`ItemCooking`/`BackpackOnBackVisuals` 的生成 TypeTree 里没有 `renderers`/`defaultTints`/`setup`，只有 `preCooked/disableCooking/...`），因此是纯运行时字段，`FieldRefAccess` 是唯一正确的访问方式——模组做法正确。

---

### 2.5 关键游戏方法的真实签名与字段名

全部来自 `D:\zhuanban\youhua\decompiled-latest\Assembly-CSharp\`。

#### 方法签名

| 模组引用 | 游戏真实签名 | 位置 | 判定 |
|---|---|---|---|
| `Item.Start` | `protected virtual void Start()` | `Item.cs:453` | ✅ |
| `Item.OnEnable` | `public override void OnEnable()` | `Item.cs:386` | ✅ |
| `Item.SetState` | `internal void SetState(ItemState setState, Character character = null)` | `Item.cs:728` | ✅（见下方注） |
| `Item.HideRenderers` | `private void HideRenderers()` | `Item.cs:783` | ✅ |
| `Item.GetName` | `public string GetName()`（**非 virtual**） | `Item.cs:679` | ✅ |
| `Item.ItemUIData.GetIcon` | `public Texture2D GetIcon()`（嵌套类） | `Item.cs:83` | ✅ |
| `InventoryItemUI.SetItem` | `public void SetItem(ItemSlot slot)` | `InventoryItemUI.cs:77` | ✅ |
| `ItemCooking.UpdateCookedBehavior` | `public virtual void UpdateCookedBehavior()` | `ItemCooking.cs:71` | ✅ |
| `BackpackOnBackVisuals.InitRenderers` | `private void InitRenderers()` | `BackpackOnBackVisuals.cs:52` | ✅ |
| `CharacterAnimations.ConfigureIK` | `public void ConfigureIK()` | `CharacterAnimations.cs:390` | ✅ |
| `Item.Center` | `public Vector3 Center()` | `Item.cs:660` | ✅ |
| `Item.AddPropertyBlock` | `private void AddPropertyBlock()` | `Item.cs:502` | ✅ |
| `Item.HoverEnter` | `public void HoverEnter()` | `Item.cs:1139` | ✅ |
| `Item.HoverExit` | `public void HoverExit()` | `Item.cs:1149` | ✅ |
| `ItemCooking.GetCookColor` | `public static Color GetCookColor(int cookAmount)` | `ItemCooking.cs:136` | ✅ |

> **注（`Item.SetState` 补丁签名）**：`Patches.cs:36` 的 prefix 声明为 `(Item __instance, ItemState setState)`，**未声明**第二个可选参数 `Character character`。Harmony 只绑定补丁里声明过的参数，因此可以工作；但这意味着 prefix 拿不到 `character`。若将来需要按角色区分，需要显式加参数。**这是可工作的，不是缺陷**，仅记录。

**`Item.HideRenderers` 的唯一调用点**（全树 grep 只有 2 条命中：定义 + 1 处调用）：

```csharp
// Item.cs:1291-1303
[PunRPC]
public void PutInBackpackRPC(byte slotID, BackpackReference backpackReference) {
    Transform[] backpackSlots = backpackReference.GetVisuals().backpackSlots;
    this.backpackReference = Optionable<(byte, BackpackReference)>.Some((slotID, backpackReference));
    backpackSlotTransform = backpackSlots[slotID];
    SetState(ItemState.InBackpack);
    backpackReference.GetVisuals().SetSpawnedBackpackItem(slotID, this);
    if (backpackReference.IsOnMyBack()) { HideRenderers(); }     // <-- 唯一调用点，且被 IsOnMyBack() 守卫
}
```

→ 证实 `Patches.cs:38-42` 与 `PlushieModel.cs:1196-1202` 的注释："游戏只在玩偶位于**被背在背上**的背包里时才隐藏" —— **符合**。`HideRenderers` 本身只是 `GetComponentsInChildren<Renderer>().ForEach(r => r.enabled = false)`，**从不重新打开**（`Item.cs:783-789`）——也证实了注释。

#### 字段名

| 模组引用 | 游戏真实声明 | 位置 | 判定 |
|---|---|---|---|
| `Item.ALL_ITEMS` | `public static List<Item> ALL_ITEMS = new List<Item>();` | `Item.cs:103` | ✅ |
| `Item.ALL_ACTIVE_ITEMS` | `public static List<Item> ALL_ACTIVE_ITEMS = new List<Item>();` | `Item.cs:105` | ✅ |
| `Item.backpackReference` | `public Optionable<(byte, BackpackReference)> backpackReference;` | `Item.cs:183` | ✅ |
| `Item.mainRenderer` | `public Renderer mainRenderer;` | `Item.cs:209` | ✅ |
| `Item.UIData` | `public ItemUIData UIData;` | `Item.cs:178` | ✅ |
| `Item.ItemUIData.itemName` | `public string itemName;` | `Item.cs:41` | ✅ |
| `Item.ItemUIData.icon` | `public Texture2D icon;` | `Item.cs:43` | ✅ |
| `InventoryItemUI.icon` | `public RawImage icon;` | `InventoryItemUI.cs:11` | ✅ |
| `InventoryItemUI._itemPrefab` | `private Item _itemPrefab;` | `InventoryItemUI.cs:31` | ✅ |
| `Character.refs` | `public CharacterRefs refs;` | `Character.cs:124` | ✅ |
| `Character.CharacterRefs.animationItemTransform` | `public Transform animationItemTransform;` | `Character.cs:97` | ✅ |
| `CharacterItems.character` | `private Character character;` | `CharacterItems.cs:31` | ✅（`GetField` 反射可见） |

#### 相关游戏逻辑原文（供交叉核对）

**`Item.Center()`（`Item.cs:660-667`）—— 模组"不重指 mainRenderer"的第 3 条理由成立**：

```csharp
public Vector3 Center() {
    if (!mainRenderer.UnityObjectExists()) { return transform.position; }
    return mainRenderer.bounds.center;
}
```

`Center()` 被 AOE / Beehive / Lava / WindChillZone / CompassPointer 等使用（实测调用点：`Lava.cs:128`、`WindChillZone.cs:193`、`ScoutCannon.cs:232` 等），全部是**玩法判定**。重指 `mainRenderer` 会让这些判定跟随模型缩放/持握偏移 → 模组的判断**正确**。

**`Item.AddPropertyBlock()`（`Item.cs:502-511`）—— 模组第 2 条理由成立**：

```csharp
private void AddPropertyBlock() {
    mpb = new MaterialPropertyBlock();
    mainRenderer = GetComponentInChildren<MeshRenderer>();     // <-- 深度优先，第一个命中
    if (!mainRenderer) { mainRenderer = GetComponentInChildren<SkinnedMeshRenderer>(); }
    mainRenderer.GetPropertyBlock(mpb);
}
```

实测 `GetComponentInChildren<MeshRenderer>()` 在该 prefab 上命中的是**子节点顺序中的第一个**：

```
--- BingBong_Prop Variant
   depth=2 'Hand' MeshRenderer=[19550] SkinnedMeshRenderer=[]     <-- Hand_L/Hand，不是身体！
--- BingBong
   depth=2 'Hand' MeshRenderer=[20125] SkinnedMeshRenderer=[]     <-- Hand_R/Hand
```

（因为 `m_Children` 顺序是 `Hand_L, Hand_R, Particles, Coll, Holder`；`BingBong` 的顺序不同，所以命中的是 `Hand_R/Hand`。）→ `item.mainRenderer` 指的是**一只手的渲染器**，`mpb` 里带的是手材质的属性块。这**强化**了模组的第 2 条理由：`HoverEnter/HoverExit` 会把这只手的属性块写到 `mainRenderer`；若把 `mainRenderer` 重指到替换模型的身体渲染器，一次 hover 就会用"手的属性块"覆盖 `ApplyCookTint` 写入的 `_BaseColor`/`_EmissionColor`。模组的推理**正确**。

**`Item.HoverEnter/HoverExit`（`Item.cs:1139-1157`）**：

```csharp
public void HoverEnter() {
    mpb.SetFloat(PROPERTY_INTERACTABLE, 1f);        // PROPERTY_INTERACTABLE = PropertyToID("_Interactable")
    mainRenderer.SetPropertyBlock(mpb);
    for (int i = 0; i < addtlRenderers.Length; i++) { addtlRenderers[i].SetPropertyBlock(mpb); }
}
```

→ 模组注释（`PlushieModel.cs:974-979`）说 `_Interactable` 只在 `W/Character` 与 `W/Peak_*` 系列声明，URP/Lit 不声明，所以重指也无效果。**我无法从游戏资源验证 URP/Lit 的属性表**（URP 是独立 package assembly，其 shader 资产不在被扫描的 `.assets` 里；见 §三）。但实测**原版材质** `M_BingBongPlush`(#102) 与 `M_Player`(#177) 的 `m_SavedProperties.m_Floats` **都声明了 `_Interactable`**，且 `_Tint` 与 `_Cull` 也在——所以原版确实支持 hover 高亮与 `_Tint`。

**`CharacterAnimations.ConfigureIK()`（`CharacterAnimations.cs:390-408`）**：

```csharp
public void ConfigureIK() {
    if (!(character.refs.IKHandTargetLeft == null)) {
        if ((bool)character.data.currentItem) {
            Transform iKHandTargetLeft = character.refs.IKHandTargetLeft;
            Vector3 itemPosLeft = character.refs.items.GetItemPosLeft(character.data.currentItem);
            Quaternion rotation = (character.refs.IKHandTargetLeft.rotation =
                character.refs.items.GetItemRotLeft(character.data.currentItem));
            iKHandTargetLeft.SetPositionAndRotation(itemPosLeft, rotation);
            character.refs.IKHandTargetRight.SetPositionAndRotation(
                character.refs.items.GetItemPosRight(character.data.currentItem),
                character.refs.items.GetItemRotRight(character.data.currentItem));
        } else if (ReachIK()) { ... }
    }
}
```

调用点：`CharacterRagdoll.cs:151-177` 的 `FixedUpdate()` → **每物理帧一次**（README:125 "游戏每物理帧读取这两个节点" **符合**）。

`CharacterItems` 侧（`CharacterItems.cs:864-909`）：

```csharp
internal Vector3 GetItemPosLeftWorld(Item item) { return item.transform.Find("Hand_L").position; }
internal Vector3 GetItemPosRightWorld(Item item) { return item.transform.Find("Hand_R").position; }
internal Quaternion GetItemRotLeftWorld(Item item) { return item.transform.Find("Hand_L").rotation; }
internal Quaternion GetItemRotRightWorld(Item item) { return item.transform.Find("Hand_R").rotation; }
internal Vector3 GetItemPosLeft(Item item) {
    Vector3 position = HelperFunctions.MultiplyVectors(
        item.transform.Find("Hand_L").localPosition, item.transform.lossyScale);
    return character.refs.animationItemTransform.TransformPoint(position);
}
internal Vector3 GetItemPosRight(Item item) {
    Vector3 localPosition = item.transform.Find("Hand_R").localPosition;
    return character.refs.animationItemTransform.TransformPoint(localPosition);
}
```

→ **只读锚点，从不写**。且 `GetItemPosLeft` 用 `localPosition × lossyScale`（`GetItemPosRight` 不乘，原版的不对称，与模组无关）。`animationItemTransform` 由 `Character.cs:469-470` 在运行时 `Instantiate` 出来并命名为 `"animationItem"` —— 证实 `GameHelpers.AnimationItemTransformOf` 的反射目标（`Character.refs.animationItemTransform`）真实存在。

**`Item.Update()` 与背包（`Item.cs:528-559`）** —— 证实 `PlushieModel.IsWornBackpack` 依赖的 `backpackReference` 语义：

```csharp
protected virtual void Update() {
    if (itemState == ItemState.InBackpack) {
        if (backpackSlotTransform == null || !backpackSlotTransform.UnityObjectExists())
            transform.position = new Vector3(0f, -500f, 0f);
        else { Quaternion rotation = backpackSlotTransform.rotation;
               transform.SetPositionAndRotation(backpackSlotTransform.position - rotation * centerOfMass * 0.5f, rotation); }
    } else if (itemState == ItemState.Ground && base.photonView.IsMine) { ... }
    UpdateCollisionDetectionMode();
}
```

**`backpackReference` 的赋值点（全树 grep）** —— 只有 **1 处**：

```
Item.cs:1295   this.backpackReference = Optionable<(byte, BackpackReference)>.Some((slotID, backpackReference));
```

（`BackpackWheelSlice.cs:197,211` 是 `BackpackWheelSlice` 自己的字段，不是 `Item` 的。）

→ 对 `research/audit/runtime-model.md:360` 的"必须由 task-4 交叉确认"项的答复：**`Item.backpackReference` 在全反编译树中没有任何重置为 `None` 的赋值点**。`Item.ClearDataFromBackpack()`（`Item.cs:638-658`）清的是背包**数据槽**（`backpackReference.GetData().itemSlots[b].EmptyOut()`）并 `RefreshVisuals()`，**不动 `this.backpackReference`**。
- 因此 `PlushieModel.IsWornBackpack(item)` 在玩偶被取出背包之后**仍会返回 true**（只要那个背包还背在别人/自己背上），`ClearGameRuleHide` 不会被触发。
- 不过 `SetState(ItemState.Held)` 时 `Item_SetState_Prefix`（`Patches.cs:36-47`）会因 `setState != InBackpack` 而调 `ClearGameRuleHide`，所以"手持取出"这条路径**是被覆盖的**。
- 真正的暴露路径是"从背包取出后**放回地上**"：`ItemState.Ground` 会走 `SetState(Ground)` → prefix 也会清 hide。**所以两条取出路径都被 `SetState` 覆盖。**
- 剩下的理论缺口是"物品在 `InBackpack` 状态下被移动到一个**不**背在背上的背包"——此时 `PutInBackpackRPC` 不会调 `HideRenderers`，但 `HiddenByGameRule` 也不会被设置，所以无影响。
- **判定**：`runtime-model.md:360` 的担忧在**当前代码路径下不成立**（两条取出路径都经过 `SetState`，prefix 都会清 hide）；但 `backpackReference` 确实**从不重置**，因此 `IsWornBackpack` 是一个"一旦为真就长期为真"的判据。若未来游戏版本改变取出流程（不经 `SetState`），缺口会真实出现。**建议（不属于本任务范围）**：在 `Item_HideRenderers` 之外增加一条 `Item.SetState` 之外的安全网，或改为直接判断 `backpackReference.Value.Item2.GetVisuals().IsOnMyBack()` 的同时校验 `itemState == InBackpack`（当前 `SyncVisual` 已隐含 `HiddenByGameRule && !IsWornBackpack` 的组合判断，实际是安全的）。

---

### 2.6 `Action_AskBingBong` 的完整链路

**实测命令**：`animators.py`（读 `Action_AskBingBong#32706` 的序列化字段）、反编译 `Action_AskBingBong.cs` / `ItemAction.cs` / `ItemActionBase.cs` / `Item.cs`

**环节 1：订阅**（`ItemActionBase.cs:13-23,30-42` + `ItemAction.cs:31-78`）

```csharp
// ItemActionBase
protected virtual void OnEnable() { Init(); Subscribe(); }     // Init(): item = GetComponent<Item>();
protected virtual void Start()    { Unsubscribe(); Subscribe(); }
// ItemAction
protected override void Subscribe() {
    if (OnCastFinished) { Item obj3 = item;
        obj3.OnPrimaryFinishedCast = (Action)Delegate.Combine(obj3.OnPrimaryFinishedCast, new Action(RunAction)); }
    ...
}
```

实测 `Action_AskBingBong#32706` 的 `OnCastFinished = true`（其余 `OnPressed/OnHeld/OnReleased/OnCancelled/OnSecondary*/OnConsumed` 全为 `false`）：

```
"OnPressed": false, "OnHeld": false, "OnReleased": false, "OnCastFinished": true,
"OnCancelled": false, "OnSecondaryCastFinished": false, "OnSecondaryPressed": false,
"OnSecondaryHeld": false, "OnSecondaryCancelled": false, "OnConsumed": false,
```

→ 只有 `OnPrimaryFinishedCast` 挂钩。

**环节 2：长按左键**（`CharacterItems.cs:199-215` → `Item.cs:843-910`）

```csharp
// CharacterItems.Update()
if (character.input.usePrimaryWasPressed && character.data.currentItem.CanUsePrimary())
    character.data.currentItem.StartUsePrimary();
if (character.input.usePrimaryIsPressed && character.data.currentItem.CanUsePrimary())
    character.data.currentItem.ContinueUsePrimary();
if (character.input.usePrimaryWasReleased || (...)) character.data.currentItem.CancelUsePrimary();

// Item
public void StartUsePrimary() { isUsingPrimary = true; castProgress = 0f; finishedCast = false;
    if (OnPrimaryStarted != null) OnPrimaryStarted(); }
public void ContinueUsePrimary() {
    if (usingTimePrimary > 0f) {
        castProgress += 1f / usingTimePrimary * Time.deltaTime;
        if (castProgress >= 1f) { if (OnPrimaryHeld != null) OnPrimaryHeld();
            if (!finishedCast) FinishCastPrimary(); }
    } else { if (!finishedCast) FinishCastPrimary(); if (OnPrimaryHeld != null) OnPrimaryHeld(); }
}
protected virtual void FinishCastPrimary() { ... finishedCast = true; lastFinishedCast = Time.time;
    castProgress = 0f; if (OnPrimaryFinishedCast != null) OnPrimaryFinishedCast(); }
```

实测 `usingTimePrimary = 0.25`（三处 Item 全部）。`CanUsePrimary`（`Item.cs:791-804`）在 `UIData.hasMainInteract == true` 时返回 true（实测 `hasMainInteract = true`）。

→ **"长按左键"的准确机制**：按住主开火键 **0.25 秒**（`usingTimePrimary`），`castProgress` 到达 1 → `FinishCastPrimary()` → 触发 `OnPrimaryFinishedCast` → `RunAction()`。**不是无限长按**，而是一次 0.25 s 的施法；松开则会 `CancelUsePrimary()` 打断。README:134 说"手持时按住主开火键会触发"——**符合**（0.25 s 即可）。

**环节 3：RPC**（`Action_AskBingBong.cs:55-88`）

```csharp
public override void RunAction() {
    int num = UnityEngine.Random.Range(0, responses.Length);
    if (debugCycle) { ... }
    item.photonView.RPC("Ask", RpcTarget.All, num, Time.time < lastAsked + 1f);
    if (Time.time > lastAsked + 1f) { lastAsked = Time.time; }
}

[PunRPC]
public void Ask(int index, bool spamming) {
    if (item.holderCharacter != null) {
        squishAnim.SetTrigger("Squish");                                  // <-- 挤压触发点
        SFX_Player.instance.PlaySFX(squeak, base.transform.position, base.transform);
        subtitles.gameObject.SetActive(value: false);
        if (askRoutine != null) StopCoroutine(askRoutine);
        StartCoroutine(AskRoutine(index, spamming));
    }
}
```

**环节 4：`squishAnim` 指向哪个 Animator**（实测 `Action_AskBingBong#32706` 序列化字段）

```
"squishAnim": { "m_FileID": 0, "m_PathID": 23496 }
"anim":       { "m_FileID": 0, "m_PathID": 23399 }
"source":     { "m_FileID": 0, "m_PathID": 23315 }
"subtitles":  { "m_FileID": 0, "m_PathID": 29057 }
"shake":      { "m_FileID": 0, "m_PathID": 28137 }
"squeak":     { "m_FileID": 0, "m_PathID": 27944 }
"responses":  24 项 (subtitleID BB_Yes / BB_Yeah / ... / BB_AskYourFriends)
"debugCycle": false
```

`Animator` 组件归属实测：

```
Animator#23496  GO#11133  → controller 2411 "BingBong"        <-- squishAnim = 物品根节点的 Animator
Animator#23399  GO#10901  → controller 2410 "Bing Bong Plush"  <-- anim = 子节点(嘴)的 Animator
Animator#23409  GO#4284   → controller 2411 "BingBong"
Animator#23488  GO#4005   → controller 2410 "Bing Bong Plush"
```

→ `squishAnim` 是**物品根 GameObject 上的 Animator**（`GO#11133`），controller 2411。`squishAnim.SetTrigger("Squish")` → AnyState → state 1 (`BingBongSquish`) → clip 1442 → 驱动 `Hand_L`/`Hand_R.localPosition` + `Holder.localScale`。

**完整链路（实测确认）**：

```
按住主开火键
  → CharacterItems.Update(): input.usePrimaryIsPressed → currentItem.ContinueUsePrimary()
  → Item.ContinueUsePrimary(): castProgress += 1/0.25 * dt，达到 1
  → Item.FinishCastPrimary(): OnPrimaryFinishedCast()
  → Action_AskBingBong.RunAction()                        [ItemAction.Subscribe 挂了 OnCastFinished=true]
  → item.photonView.RPC("Ask", RpcTarget.All, index, spamming)
  → Action_AskBingBong.Ask(index, spamming)  [holderCharacter != null]
  → squishAnim.SetTrigger("Squish")                       [squishAnim = 根 GO#11133 的 Animator#23496]
  → AnimatorController 2411: AnyState → BingBongSquish (m_EventID crc32("Squish")=2750837211)
  → AnimationClip 1442 "BingBongSquish" (0.46667 s)
  → 驱动 Holder.localScale (attr 3) 与 Hand_L/Hand_R.localPosition (attr 1)
```

**与模组策略的关系（实测支持）**：模组把替换模型挂在 `item/Holder/PlushieSwap_Visual`（`PlushieModel.cs:883-914, 925-932`）。由于 clip 确实驱动 `Holder.localScale`，挂在 `Holder` 下**能继承挤压**；而锚点 `Hand_L`/`Hand_R` 不是 `Holder` 的子节点，所以模型**不会**被锚点位移带走。`Holder` 静止时是单位变换（实测 `pos=(0,0,0)`、`rot` 单位、`scale=(1,1,1)`）→ 静止时零代价，**符合** `PlushieModel.cs:894-896` 的注释。

---

### 2.7 "全游戏只有 3 个 GameObject 带 Item 组件"的核实

**实测命令**（`C:\Users\Administrator\AppData\Local\Temp\gaudit\scan2.py`、`bingitems.py`、`final2.py`）：遍历 `PEAK_Data` 下全部 53 个 assets 文件（28 个 `.assets` + 25 个 `level*`），对每个 `MonoBehaviour` 用 `m_Script` PPtr 解析出类名（`fileID==0` → 本文件 MonoScript；`fileID>0` → `externals[fileID-1]`，若指向 `globalgamemanagers.assets` 则查那张 5879 条的表），类名等于 `Item` 的即计数。

**原始输出（全游戏范围）**：

```
=== Item: 373 components ===
  file=resources.assets  Mono#   28523 GO#    5384 name='Amulet_InfiniteStamina'
  ...
  file=resources.assets  Mono#   30819 GO#    4284 name='BingBong'
  ...
  file=resources.assets  Mono#   32519 GO#   11133 name='BingBong_Prop Variant'
  ...
  file=level3            Mono#   21008 GO#    6161 name='BingBong_Prop Variant'
  ...
  file=level4            Mono#  618221 GO#   70348 name='Shell Big'
  ...
  file=sharedassets4.assets Mono# 28889 GO#    7896 name='Yuzu Berry'
```

**汇总**：

```
=== (a) distinct GameObjects with an Item component, game-wide ===
  distinct (file, GameObject) pairs: 373
  per file: {'level3': 42, 'level4': 150, 'resources.assets': 178, 'sharedassets4.assets': 3}
  files containing Item components: 4
```

**限定到 "BingBong / Bing Bong" 前缀**（`bingitems.py`）：

```
scanning 53 files for BingBong-named GameObjects

--- resources.assets ---
    Item Mono#30819 GO#4284 name='BingBong'
    Item Mono#32519 GO#11133 name='BingBong_Prop Variant'
--- level3 ---
    Item Mono#21008 GO#6161 name='BingBong_Prop Variant'

TOTAL Item components on BingBong-prefixed GameObjects: 3
```

**判定**：

- ❌ **字面断言"全游戏只有 3 个 GameObject 带 Item 组件"不成立** —— 实际是 **373 个**（`resources.assets` 178、`level4` 150、`level3` 42、`sharedassets4.assets` 3）。
- ✅ **限定为"名字以 BingBong/Bing Bong 开头"时成立，且是 3 个** —— 与 `GameHelpers.cs:170-177` 注释所描述的场景一致，前缀匹配（`ObjectNamePrefix = "BingBong"`）**确实覆盖了全部 3 个**（含运行时克隆 `BingBong(Clone)`，`PhotonNetwork.Instantiate` 会产生 `(Clone)` 后缀）。
- ⚠️ `GameHelpers.cs:175-177` 的注释原文是 **"the only GameObjects that actually carry an `Item` component are `BingBong` and `BingBong_Prop Variant`"**：
  - 作为"名字清单"读：**正确**（全游戏只有这 2 个不同的 BingBong 名字带 Item）。
  - 作为"GameObject 实例清单"读：**不完整** —— 漏了 `level3` 的场景实例 `GO#6161`（名字同样是 `BingBong_Prop Variant`）。共 3 个实例。
  - 作为"全游戏 GameObject"读：**错误**（373 个）。
- **功能影响：无**。因为 `level3#6161` 的名字与 prefab 相同，前缀匹配必然覆盖它；而 `IsBingBongItem` 另有 `UIData.itemName` 含 "Bing"+"Bong" 的第二重判据（实测 `itemName = "Bing Bong"`）。`GameHelpers.cs:170-173` 列举的其它 BingBong 资产（`Bugfix_BingBong`、`Medallion_BingBong`、`BingBongMesh`、`BingBongSFX`）经实测**确实都不带 Item 组件**：

```
'Bing Bong Plush': 2 -> [4005, 10901]      (Animator only)
'Bing Bong statue': 1 -> [4006]
'BingBong': 1 -> [4284]                     (Item ✅)
'BingBongMesh': 1 -> [8811]                 (SkinnedMeshRenderer on Beetle — 不是玩偶)
'BingBong_Prop Variant': 1 -> [11133]       (Item ✅)
'Bugfix_BingBong': 1 -> [5360]              (MeshFilter + MeshRenderer)
'Medallion_BingBong': 1 -> [10102]
'SFX BingBong loop': 1 -> [5528]
```

（`BingBongMesh` 实测挂在 `Beetle → VisualParent → Beetle` 树下，是 `SkinnedMeshRenderer`，与玩偶无关——注释里的描述**正确**。）

---

### 2.8 附加实测：其它被发现的事实

**(1) `resources.assets` 里两个 prefab 都带 Item，且 UIData.itemName 都是 `"Bing Bong"`**（见 §1.3 表）。`GameHelpers.IsBingBongItem` 会同时命中 #4284 与 #11133。锚点数值相同，但几何不同。

**(2) `Holder` 是唯一带 `PlushieSwap_Visual` 父节点的候选**：实测 `Holder` 只有 `Transform` 组件（无 `MeshRenderer`），且是单位变换。`item.transform.Find("Holder")` 会命中它（`PlushieModel.cs:907`）。**符合**。

**(3) `Item.mainRenderer` 实际指向一只手的渲染器**（见 §2.5），不是身体。这对模组的"不重指"决策是**额外支持**。

**(4) `ItemCooking` 的字节 gap**：`ItemCooking#34110` `byte_size=180` 但生成 TypeTree 只消费 76 字节（gap 104）。原因是 `ItemCooking` 有 `[SerializeReference] public AdditionalCookingBehavior[] additionalCookingBehaviors;`（`ItemCooking.cs:29-30`），而 `additionalCookingBehaviors` 实测为 `[{'cookedAmountToTrigger': 1191968968, 'onlyOnce': True}]`（`level3#22185`，即托管引用注册表格式），UnityPy 的生成树无法解析这 104 字节。**已读字段（`preCooked`/`disableCooking`/`wreckWhenCooked`/`ignoreDefault*`/`explosionPrefab`）可信**，`additionalCookingBehaviors` 的具体内容不可信（见 §三）。

**(5) 全部 `Item`/`ItemCooking` 实例的对象普查结果**（供交叉核对）：

```
Item: 373 个组件
  resources.assets 178 / level4 150 / level3 42 / sharedassets4.assets 3
ItemCooking: 164 个组件
  level4 89 / resources.assets 68 / level3 6 / sharedassets4.assets 1
```

（`BingBong_Prop Variant` #11133 的 ItemCooking 是 `#34110`；`BingBong` #4284 的是 `#29518`；`level3#6161` 的是 `#22185`。）

**(6) `Item.originalTint` 是死字段**（`Item.cs:217`，全树无读写）。

**(7) `Character.refs` 是 `public`，`CharacterItems.character` 是 `private`** —— 模组用 `GetField(..., Public|NonPublic|Instance)` 两处都能拿到。`CharacterRefs.animationItemTransform` 是 `public`，且运行时由 `Character.cs:469-470` 动态 `Instantiate` 并命名 `"animationItem"` —— 证实模组的反射路径**在运行时一定存在**（不是序列化字段，是运行时代码创建的）。

---

## 三、无法判定项清单（诚实标注）

| # | 事项 | 为什么无法判定 | 已做到的程度 |
|---|---|---|---|
| U1 | **"动画会**永久**改写 `Hand_L.position`"** 中的"永久" | 序列化数据只能证明 clip **驱动**该通道，且末帧回到原版值、两个 state 的 `m_WriteDefaultValues = true`。真正是否在稳态留下偏移，取决于 Unity Animator 在 state 切换/退出时的实际求值行为，必须在运行的游戏里观察 `Hand_L.localPosition` 才能定论。**我没有运行游戏**（任务要求只读，且游戏未启动） | 已完整解码 controller 2411 的全部 state/transition/condition、clip 1442 的全部 3 条 binding 与 6 个关键帧、9 个 `m_ValueArrayDelta`。可确定"**会改写**"；"**永久**"标记为无法判定 |
| U2 | **`resources.assets` #4284 `BingBong` 是否会在运行时被实例化为可拾取物品** | 需要 `ItemDatabase` 资产的 `itemLookup` 内容（哪几个 prefab 注册了 itemID）。我尝试定位并解析 `ItemDatabase`（MonoScript pid 2211）时，UnityPy 对某个 sharedassets 文件的 typetree 返回了 `bool` 而非 dict，脚本报错；且 `ItemDatabase` 的 `Objects`/`itemLookup` 是 `ObjectDatabaseAsset<ItemDatabase, Item>` 的运行时填充字段，序列化内容里可能为空。**我没有解析成功** | 已确认：`#4284` 与 `#11133` 都是带完整 `Item` 组件的 prefab，`UIData.itemName` 都是 `"Bing Bong"`，`itemID` 都是 `0`；`level3` 场景里实际摆放的是 `#6161`（= `#11133` 的实例）。`BingBongSpawnTool.folder = "0_Items/"` 与 `ItemDatabase.Add` 用 `"0_Items/" + item.name` 实例化，所以运行时的物品名取决于 `0_Items/` 资源容器（该容器的 container 表在 `resources.assets` 里为空，可能在 `resources.resource` 或 level 文件的 `PreloadData` 里） |
| U3 | **模组所选 URP/Lit shader 是否真的不声明 `_Interactable`** | 该断言出自模组自己的 `research/shader_properties.txt`（task-3 范围）。URP 的 shader 资产在 `Unity.RenderPipelines.Universal.*` 的 package assembly 里，不在我扫描的 `PEAK_Data\*.assets` / `level*` 中；`resources.assets` 的 51 个 Shader 与 `globalgamemanagers.assets` 的 146 个 Shader 的 `m_Name` 都是空字符串，无法按名筛选。**我无法从游戏资源验证** | 已实测：**原版**材质 `M_BingBongPlush`(#102) 与 `M_Player`(#177) 的 `m_SavedProperties.m_Floats` 都声明 `_Interactable`，`m_Colors` 都声明 `_Tint`，`_Cull = 2.0`。所以原版 hover 高亮与 `_Tint` 是有效的；模组的 URP/Lit 断言未能独立核实 |
| U4 | **"在未声明 `_Tint` 的 shader 上 `Material.GetColor("_Tint")` 会每次记一条 Unity 错误日志"** | 这是 Unity 引擎行为，需要运行游戏并读 `LogOutput.log` 才能证实。**我没有运行游戏** | 已证实该断言是 `CookingPatches` 存在的**唯一动机**；如果它不成立，`CookingPatches` 的设计前提就不成立（但补丁本身仍是安全的：它只是把模组自己的 renderer 排除出列表）。建议由能跑游戏的人复核 |
| U5 | **`ItemCooking.additionalCookingBehaviors` 的真实内容** | `[SerializeReference]` 的托管引用注册表格式，UnityPy 的生成 TypeTree 只消费 76/180 字节，剩余 104 字节无法解析（实测 gap=104）。读出来的 `[{'cookedAmountToTrigger': 1191968968, 'onlyOnce': True}]` 是**错位解析**，不可信 | 已读出的 `preCooked`/`disableCooking`/`wreckWhenCooked`/`ignoreDefaultCookBehavior`/`ignoreDefaultPoisonBehavior`/`explosionPrefab` 位置与字节消费量自洽，可信 |
| U6 | **`Item` MonoBehaviour 尾部 40 字节的内容** | 生成 TypeTree 消费 420/460 字节，尾部 40 字节全 `00`（其中 offset 16-20 是 `01 00 00 00`）。可能是 UnityPy 生成树未包含的字段（例如 `ItemState itemState` 自动属性背板、或 `_tfCached`/`_tfIsCached` 等 `[NonSerialized]` 之外的私有字段） | 已确认**不影响**已读字段：`defaultPos`(offset 20)/`defaultForward`(32)/`gliderHold`(44)/`rightHandOnly`(45)/`mass`(46) 的字节位置与 `Item.cs:109-117` 的声明顺序完全一致，且 `mass=5.0` 的 float 值合理 |
| U7 | **米菲握点间距 `0.3860`（README:129）** | 这是 `.psmesh` 模型资产里的握点，不是游戏侧事实。`.psmesh` 是模组自定义格式，读取需要模组的 `PsMeshReader`。**属于 task-3/6 范围**，本任务不覆盖 | 已确认游戏侧对照值：锚点 X 间距 `0.599000`、3D 间距 `0.603433`（实测）。"比这两个玩偶都宽"这半句的方向是成立的 |
| U8 | **`Item.Center()` 的调用点是否穷尽**（模组注释列举了 AOE/Beehive/Lava/WindChillZone/CompassPointer） | 我做了 `\.Center\(\)` 的部分 grep，命中 `Lava.cs:128`、`WindChillZone.cs:193`、`ScoutCannon.cs:232` 等，但**没有做穷尽枚举**。模组注释的列举**未被完整核实** | 已核实 `Item.Center()` 的实现（`Item.cs:660-667`）与"返回 `mainRenderer.bounds.center`、喂给玩法判定"这一核心事实。注释里"重指 `mainRenderer` 会污染 `Center()`"的**结论方向正确** |

---

## 四、给 Lead 的结论清单

### 前提假设**不成立**（需修文档/注释）

1. **`src/GameHelpers.cs:175-177`**：*"the only GameObjects that actually carry an `Item` component are `BingBong` and `BingBong_Prop Variant`"* —— 实测全游戏 **373** 个 GameObject 带 `Item`；限定为 BingBong 前缀时是 **3** 个（注释只列了 2 个**名字**，漏了 `level3#6161` 这个实例）。功能无影响，但事实陈述错误。
2. **`src/CookingPatches.cs:33-36`**：*"The other two places in the game that read or write `_Tint`"* —— 实测除物品内 2 处外还有 **3** 处，漏了 `sc.posteffects.runtime\SCPE\RefractionRenderer.cs:40`。被漏的那条作用于全局后处理材质，**无功能影响**，但注释的"两处"枚举是错的。
3. **`README.md:18`**：*"不修改任何音频和游戏逻辑"* —— 模组通过 Harmony 命中 **9 个**游戏方法（10 条 patch 声明，`Item.SetState` 挂 prefix+postfix）；其中 `CookingPatches` 提前置 `setup=true`，使 `ItemCooking.UpdateCookedBehavior` 首次调用多执行一次 `item.WasActive()`。措辞过强。
4. **`README.md:102`**：*"原版 XZ 中心 `X = -0.0315`, `Z = +0.0505`"* —— `Z=+0.0505` 是 **Holder 子树（玩偶本体）** 的中心；**整件物品**（含双手）的 Z 中心是 **`-0.1391`**。数值本身对应"本体"，但标签未限定，会误导复查者。建议改为"原版**玩偶本体** XZ 中心（不含双手）"。
5. **`README.md:100-106` 的数值表整体未点名 prefab** —— 这些数值只对 `BingBong_Prop Variant`(#11133) 成立；同名的 `BingBong`(#4284) 也带 `Item` 且 `itemName` 同为 `"Bing Bong"`，其高度是 `1.1884`、Y 范围 `[-0.757917, +0.430445]`。建议在表中加"（`BingBong_Prop Variant`）"。

### 前提假设**成立**（可放心）

- 全部 6 个原版数值（高度 / Y 范围 / XZ 中心 X / 锚点中点 / 锚点 X 间距 / 锚点 3D 间距）**逐位吻合**。
- `mass = 5.0`、`rightHandOnly = false`、`defaultForward = (0,0,1)`、`defaultPos = (0,0,0.9)` **实测吻合**（README 未声称这些，代码亦未依赖；作为事实基线已建立）。
- Squish 控制器**只**驱动 `Holder.localScale` + `Hand_L`/`Hand_R.localPosition`（3 条 binding，CRC 全部命中）——`PlushieModel.cs:889-891` 的注释**完全正确**。
- 挤压动画**确实改写锚点**（README:130-131 正确）；"永久"一词超出序列化数据能支持的范围（见 U1）。
- `Holder` 静止时单位变换、挂在 `Holder` 下能白拿挤压 —— **正确**。
- `_Tint` 的**物品内**路径 100% 被 `CookingPatches` 覆盖；`ItemCooking` 无子类、`CookVisually` 无 override。
- 全部 15 个方法签名 + 13 个字段名与游戏**逐项一致**；`FieldRefAccess` 的目标字段真实存在且是未序列化的私有运行时字段。
- `Action_AskBingBong` 链路**逐环节实测通过**；"长按左键"准确说是"按住 0.25 s"。
- "BingBong 前缀匹配覆盖所有真实实例"（3 个）**成立**。
- `Item.backpackReference` **在全反编译树中没有任何重置为 `None` 的赋值点**（对 `runtime-model.md:360` 的答复）；但两条取出路径都经 `SetState` → `Item_SetState_Prefix` 会清 hide，**当前无真实缺口**。

### 交叉确认（回给 runtime-model / compat 审计员）

- **`runtime-model.md:360` 的"必须由 task-4 交叉确认"项**：`Item.backpackReference` 只有 1 个赋值点（`Item.cs:1295`，`PutInBackpackRPC` 内），**无重置点**。但 `ClearGameRuleHide` 由 `Item_SetState_Prefix` 在 `setState != InBackpack` 时调用，而"从背包取出"必然经过 `SetState(Held)` 或 `SetState(Ground)` → **会被清理**。故该担忧**在当前代码路径下不成立**，严重度应从"严重"降为"低（仅当未来游戏版本改变取出流程时才成立）"。
- **`compat.md` 引用的 `Hand_R: anchor node x=0.14002, authored 0.24000 (MOVED BY THE GAME)`**：与本次解码的 clip 关键帧 `Hand_R.x = 0.140000`（frame 2-3）**逐位吻合**，证实该日志来源就是 Squish clip，且是**动画播放中**的值，不是稳态残留。
