# 审计 F：资源 / 发行包 / 文档 / 仓库卫生 / 模型署名

- 审计对象：`D:\zhuanban\Plushie Swap`
- 审计基线：`git HEAD = bc696a91a924ded823102785308fd8294badeadf`（"Drop the stale handoff notes the user removed"，2026-09-20 02:20:32 +0800），工作区干净（`git status --short` 无输出）
- 审计方式：只读。本报告是本次审计唯一写入的文件。所有命令为实测，所有结论附命令/输出。
- 环境：`C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe`（Pillow / UnityPy / numpy / trimesh）、pwsh、联网。

---

## 结论摘要

| 编号 | 结论 | 严重度 |
| --- | --- | --- |
| **C1** | **README.md 第 7 行「默认 **米菲兔**」是错的**。代码默认是 `ZichaoXiong`（`src/Plugin.cs:50` 与 `:181`），README 自己的配置表第 51 行也写 `ZichaoXiong`。同一文件内自相矛盾，且 `release/stage/README.md` 写的是正确的 `Zichao Xiong`。 | **高（用户可见的错误）** |
| **C2** | README 第 185 行「**不含任何第三方素材**」不成立。两个模型都来自 MakerWorld 第三方 3MF（自嘲熊为 `Standard Digital File License`，米菲兔许可未知）。这句话既是事实错误，也在许可上留下风险。 | **高（法律/事实）** |
| **C3** | **release/ 发行包已过期**：包内 DLL 的 SHA-256 与 `dist/` 当前构建不一致（`84081390…` vs `582E1B00…`，后者与 `buildinfo.txt` 一致）。且 `tools/build_icon_release.py` 的源图 `D:\备份\zichao.jpg` **已不存在**，`release/icon.png` 目前**无法重现**。 | **高（发行正确性）** |
| **C4** | **自嘲熊作者已核实**（双证据）：3MF 内嵌 `Designer=夜夜椰子冰`、`DesignerUserId=2431656860`、`License=Standard Digital File License`；国际站 API 同一模型显示 `Lorensi`。**米菲兔作者无法核实**：3MF 的 `Designer` / `License` / `Title` 字段全为空，只剩 `DesignerUserId=2755976439`；MakerWorld 页面 403 拒绝抓取。**未编造任何作者名**。 | **高（用户明确要求）** |
| **C5** | README 数值/描述有 4 处过时：奶油白阈值写 `>0.75`（实际 `>0.55`）、AO 平滑写「4 次」（实际 3 次；4 次是墨线宽度）、「三次绘制」（实际两次）、「即时生效」对 `Shader Override` 不成立。 | 中 |
| **C6** | `.gitignore` 第 18 行 `research/preview/` 与事实矛盾：该目录**已被忽略却仍有 42 个文件被跟踪**（磁盘上另有 282 个被忽略）。 | 中 |
| **C7** | 仓库卫生：215 个跟踪文件中，`tools/` 有 **48/57 个一次性诊断脚本**，`research/` 有 **81 个 .py + 42 张 preview PNG**。`models/*.3mf` 占 **13.47 MB**（全仓跟踪总量约 22.9 MB）。 | 中 |
| **C8** | 文档一致性**良好**：`OUTLINE_DESIGN.md` 有明确的「历史研究产物、未采用」横幅；`PlushieShaderLoader.sample.cs` 首行声明「NOT compiled」。但 `shaders/PlushieOutline.shader` **自身没有状态横幅**，且 `OUTLINE_DESIGN.md:23` 指向的 `REWRITE.md` 已在 `bc696a9` 被删除（悬空引用）。 | 低 |

**Thunderstore 规范结论**：`manifest.json` 五个字段**全部合规**；`icon.png` **恰好 256×256**；zip 根目录布局**完全合规**。官方要求见下文引用的 wiki 原文与链接。

---

## 一、README.md 逐句核验

核验方法：把 README 的每条断言映射到 `src/Plugin.cs`、`src/PlushieModel.cs`、`src/Variants.cs`、`src/AssetProvider.cs`、`tools/build_meshes.py`、`assets/manifest.json`，以及本审计对 `assets/*.psmesh` 的二进制实测。

### 1.1 默认形态（**错误**）

README 两处自相矛盾：

```
README.md:7   - **三种形态自由切换**：原版 / 米菲兔 / 自嘲熊，默认 **米菲兔**
README.md:51  | `Plushie` | `ZichaoXiong` | 形态：`Vanilla` / `Miffy` / `ZichaoXiong` |
```

代码实测：

```
$ Select-String -Path src\Plugin.cs -Pattern '"General", "Plushie", PlushieVariant'
src\Plugin.cs:181:                "General", "Plushie", PlushieVariant.ZichaoXiong,
```

```
$ src/Plugin.cs:50
internal static PlushieVariant ActiveVariant = PlushieVariant.ZichaoXiong;
```

旁证——发行包内的 README 是对的：

```
$ Select-String -Path release\stage\README.md -Pattern "default"
release\stage\README.md:10: (the default is Zichao Xiong).
```

**判定：第 7 行错误，第 51 行正确。** 即：文档表头与实际默认值一致，只有第 7 行是旧版残留。

### 1.2 DLL 大小

```
$ (Get-Item dist\PlushieSwap\PlushieSwap.dll).Length
12133376
```

- `12133376` 字节 = **11.5713 MiB**（1024 进制）/ **12.1334 MB**（1000 进制）。
- README 写「约 11.5 MB」。若按 MiB 读，11.5713 ≈ 11.5，**可以接受**；若按十进制 MB 读则偏低 0.6。
- 判定：**不算错误**，但建议写成精确值以免歧义。同类：`dist\PlushieSwap\` 实际有 **2 个文件**（`PlushieSwap.dll` + `buildinfo.txt`，`build.ps1:114-119`）；README 第 29 行「只需要这一个文件」在**安装**语境下成立（`buildinfo.txt` 非必需），但「资源已内嵌，所以产物只有一个文件」（第 179 行）与 `dist/` 实际内容不符，属措辞不严谨。

### 1.3 配置项表完整性（**完整，11/11 覆盖**）

逐条对照 `src/Plugin.cs` 的全部 `Config.Bind`：

| 代码位置 | Section / Key | 代码默认 | README 表 | 一致 |
| --- | --- | --- | --- | --- |
| `Plugin.cs:180-182` | General / `Plushie` | `ZichaoXiong` | `ZichaoXiong` | ✅ |
| `Plugin.cs:213-216` | General / `Cycle Plush Hotkey` | `F7` | `F7` | ✅ |
| `Plugin.cs:183-187` | General / `World Scale` | `1.0f` | `1.0` | ✅ |
| `Plugin.cs:188-192` | General / `Backpack Scale` | `1.0f` | `1.0` | ✅ |
| `Plugin.cs:193-200` | General / `Hold Height Offset` | `0.0f` | `0.0` | ✅ |
| `Plugin.cs:201-203` | General / `Rename Item` | `true` | `true` | ✅ |
| `Plugin.cs:204-206` | General / `Replace Icon` | `true` | `true` | ✅ |
| `Plugin.cs:217-222` | General / `Outline Width (pixels)` | `5f` | `5.0` | ✅ |
| `Plugin.cs:207-212` | **Advanced** / `Shader Override` | `""` | 空 | ✅ |
| `Plugin.cs:229-234` | **Advanced** / `Verbose Logging` | `false` | `false` | ✅ |
| `Plugin.cs:223-228` | **Internal** / `Config Version` | `0`（Hidden） | 正文注释说明 | ✅ |

**判定：表格完整，默认值全部正确。** 唯一遗漏是**没有标注分区**（`General` / `Advanced` / `Internal`），而 cfg 文件里是分节书写的；非错误，建议补一列。

### 1.4「即时生效」的说法（**部分错误**）

```
README.md:62  在游戏内的模组设置里改动会**即时生效**；直接编辑配置文件不会被热重载——需要**重启游戏**才会读到新值。
```

只有 4 个配置项注册了 `SettingChanged`：

```
$ Select-String -Path src\Plugin.cs -Pattern "SettingChanged \+="
Plugin.cs:242: VariantEntry.SettingChanged += OnVariantChanged;
Plugin.cs:243: WorldScaleEntry.SettingChanged += OnScaleChanged;
Plugin.cs:244: BackpackScaleEntry.SettingChanged += OnScaleChanged;
Plugin.cs:245: OutlineWidthEntry.SettingChanged += OnOutlineWidthChanged;
```

其余项的实际行为：

- `Hold Height Offset` / `Verbose Logging`：每帧/每次读取 `ConfigEntry.Value` → 实时（`PlushieModel.cs:1257-1260`、`Plugin.cs:267-270`）。
- `Rename Item` / `Replace Icon`：在 Harmony 补丁内每次读取 → 基本实时（`Patches.cs:83-84, 99-100, 134-135`）。
- **`Shader Override`：改完永远不会生效，直到重启游戏。** 它只在 `GetMaterial` / `GetOutlineMaterial` 里读取（`PlushieModel.cs:555-556, 599`），而材质被 **按变体缓存**（`CachedMaterials`，`PlushieModel.cs:76-78`），并且刷新时**故意不清缓存**：

```
$ Get-Content src\PlushieModel.cs | Select -Skip 691 -First 3
692:                 // Rebuild every instance so a variant switch is immediate. The cached
693:                 // meshes and materials are per variant and stay valid, so they are kept.
```

**判定：第 62 行需要加上 `Shader Override` 例外。**

另：「直接编辑配置文件不会被热重载」这一句我**无法用只读手段证实或证伪**——它取决于 BepInEx 5 的 `ConfigFile` 是否对磁盘文件变更建立 watcher，需要实机运行验证。**本审计不据此判定**，仅标注为待验证。

### 1.5 数值表（**全部正确**）

```
README.md:100-106
| 原版玩偶高度 | `0.9635` 单位 |
| 原版占据的 Y 范围 | `[-0.7345, +0.2290]` |
| 原版 XZ 中心 | `X = -0.0315`, `Z = +0.0505` |
| 原版锚点中点 | `(-0.0595, -0.1405, -0.0400)` |
| 原版锚点间距 | X 方向 `0.5990`，3D 距离 `0.6034` |
| 手持朝向 | 物品 `+Z` 是玩家视线方向，所以模型正面朝 `-Z` |
| 生成模型实体高度 | `0.9635`（两个模型都是；含描边壳的合并包围盒是米菲 `0.9726` / 熊 `0.9735`） |
```

代码侧：

```
tools/build_meshes.py:408-412
VANILLA_HEIGHT   = 0.9635
VANILLA_CENTRE_X = -0.0315
VANILLA_CENTRE_Z = 0.0505
VANILLA_BOTTOM_Y = -0.7345
VANILLA_TOP_Y    = 0.2290
```

```
src/PlushieModel.cs:1124
Vector3 anchorMid = new Vector3(-0.0595f, -0.1405f, -0.0400f);
```

实测（解析 `assets/*.psmesh` 二进制，只读）：

```
### miffy
  BODY      Y[-0.7326, 0.2309] height=0.9635   XZ centre=(-0.0315, 0.0505)
  COMBINED  Y[-0.7345, 0.2381] height=0.9726
  body height - 0.9635 = -0.0000
  body XZ centre vs vanilla (-0.0315, 0.0505): dx=-0.0000 dz=-0.0000
### zichaoxiong
  BODY      Y[-0.7313, 0.2322] height=0.9635   XZ centre=(-0.0315, 0.0484)
  COMBINED  Y[-0.7345, 0.2390] height=0.9735
```

- 实体高度 0.9635：**精确吻合**（误差 < 1e-4）。
- 合并包围盒 0.9726 / 0.9735：**精确吻合**。
- 锚点间距 `0.5990` / `0.6034`：README 未说明来源，实测代码里只在研究脚本中出现（`research/solve_edges.py:88` "want 0.5990"、`research/diagnose_shell.py:11` "0.6034 apart"），源自对原版 prefab 的测量。本审计**未独立复测原版 prefab**（属 task-4 范围），标注为「依赖 task-4 结论」。
- 判定：**数值表无错误**。

### 1.6 朝向角度（**正确**）

```
README.md:111  把它转到面向玩家（米菲兔需转 181°、自嘲熊需转 225°，源模型本来是歪的）
```

实测（把 `build_meshes.convert()` 跑到临时目录，未触碰仓库任何文件）：

```
[Miffy]        facing correction: +181.2 deg (face now points to -Z / the player)
[ZichaoXiong]  facing correction: +224.7 deg (face now points to -Z / the player)
```

- 181.2 → 「181°」✅；224.7 → 「225°」✅（四舍五入）。
- 顺带确认**构建可复现性**：临时目录重建的两个 `.psmesh` 与仓库内提交版 **SHA-256 逐字节相同**：

```
miffy.psmesh       regen=912d5e60d2ef4307 committed=912d5e60d2ef4307 MATCH=True
zichaoxiong.psmesh regen=6448dacb45d1ee24 committed=6448dacb45d1ee24 MATCH=True
```

### 1.7 奶油白提纯阈值（**错误**）

```
README.md:75  | **② 干净明亮的色块** | 亮度 > 0.75 的颜色向奶油白 `#FFFAF2` 提纯，避免灰扑扑的米色 |
```

代码实际阈值是 **0.55**，而且注释明确记载「曾经是 0.75」：

```
tools/build_meshes.py:1127-1147
CREAM_WHITE = np.array([1.0, 0.984, 0.951])
def apply_white_boost(colour, amount):
    """...
    The threshold used to be 0.75, which left the off-white print filament (which sits
    around 0.85-0.95) only partly corrected, so the toy still read as dull beige. The
    threshold is lower now and the blend is stronger...
    """
    ...
    if luminance <= 0.55:
        return rgb
    weight = min(1.0, amount * (luminance - 0.55) / 0.45)
```

- `#FFFAF2`：`CREAM_WHITE = [1.0, 0.984, 0.951]` → `(255, 250.9, 242.5)` = `#FFFAF2` ✅ **颜色值正确**。
- 阈值 `>0.75` ❌ **应为 `>0.55`**。
- 附带：README 第 12 行只提颜色不提阈值，**无需修改**。

### 1.8 AO 平滑次数（**错误——把两个数字弄混了**）

```
README.md:76  | **③ 简洁柔和的明暗** | 点云 AO，只取上半球遮挡量，并做 4 次拉普拉斯平滑 + 幂次曲线，保留接触阴影但不糊 |
```

实测代码：

```
tools/build_meshes.py:1109-1110
            ao = np.clip(ao / reference, 0.0, 1.0) ** 0.7
            ao = smooth_ao_over_surface(verts, tris, ao, 3, 0.5)      <- AO = 3 次
```

```
tools/build_meshes.py:1628
        fade = smooth_scalar_over_surface(len(sv), st, fade, 4, 0.5)  <- 墨线宽度 = 4 次
```

- 「只取上半球遮挡量」✅（`ao[i] = np.sum(np.maximum(facing, 0.0) * falloff)`，`build_meshes.py:1105`）。
- 「幂次曲线」✅（`** 0.7`）。
- **「4 次拉普拉斯平滑」❌ 应为 3 次**。4 次是**墨线宽度**（ink width）的平滑次数，见 `OUTLINE_DESIGN.md:16` 的「a smooth per-vertex ink width (4 Laplacian passes)」——README 把描边的数字安到了 AO 头上。

### 1.9 材质与绘制次数（**「三次绘制」错误**）

```
README.md:80  所以整个模型（含描边）只需要两个材质、三次绘制。
```

- **两个材质 ✅**：`GetMaterial`（本体）+ `GetOutlineMaterial`（墨线），各 `new Material(shader)` 一次（`PlushieModel.cs:394, 485`）。
- **三次绘制 ❌**：全模型只有 **2 个 MeshRenderer**：

```
$ Select-String -Path src\PlushieModel.cs -Pattern "AddComponent<MeshRenderer>"
PlushieModel.cs:956:  MeshRenderer renderer = part.AddComponent<MeshRenderer>();        <- 本体
PlushieModel.cs:1028: MeshRenderer outlineRenderer = outlineObject.AddComponent<MeshRenderer>();  <- 描边
```

`BuildMesh()` 把全部非描边子网格**合并进同一个 Mesh**（`PlushieModel.cs:256-322`），因此米菲的 3 个本体子网格（实测 `v=1228 / 6862 / 8897`）合并后仍是 **1 个 draw**。合计 **2 次绘制**，不是 3 次。

### 1.10 描边说明（**正确**）

```
README.md:84-92（描边为什么不删面 / enclosed 故意不用 / 22.6% → 5.1%）
```

- 「现在壳体是一个完整闭合曲面，改用逐顶点墨线宽度（0 = 不画线）」✅ 与 `build_meshes.py:1546-1572` 完全一致（`inked = fade > 0.35`，无删面）。
- 「宽度随 .psmesh 一起发布」✅ `asset.OutlineWidths`（`PsMeshReader.cs:89, 196-208`）。实测：米菲 15525 个宽度值（4993 个为 0 = 32.2%），熊 16831 个（12423 个为 0 = 73.8%）。
- 「实测这就是剪影描边缺失 22.6% → 5.1% 的来源」✅ 与 `OUTLINE_DESIGN.md:20` 及 `build_meshes.py:1560-1563` 一致（`enclosed` 把贴着裙子的手判成被包住）。
- 判定：**该节无错误。**

### 1.11 握持说明（**正确，两处精度问题**）

- 「握持时不写锚点……模组改为在持握时偏移模型本身：`HoldOffsetFor()` 计算 `锚点中点 - 握点中点 × 缩放`」✅ `PlushieModel.cs:1066-1070`（注释）、`1124-1131`（公式 `anchorMid - waistMid * scale`）、`1253-1265`（仅 `Held` 状态应用）。
- 「米菲握点间距仅 `0.3860`」✅ 实测 `grip dx: 0.386`，精确吻合。
- 「模型挂在 `item/Holder/PlushieSwap_Visual`」✅ `PlushieModel.cs:64`（`VisualRootName = "PlushieSwap_Visual"`）、`901-914`（`HolderName = "Holder"`，找不到时回退到 item 自身）。
- 「`Holder` 静止时是单位变换」✅ `PlushieModel.cs:894-896`。
- 「按住主开火键会触发 `Action_AskBingBong` → `squishAnim.SetTrigger("Squish")`」✅ `PlushieModel.cs:886-891`。

两处精度问题（非硬错误，建议补注）：

1. **握持百分比是「板层中心」，不是手实际高度。** README 表写「米菲 22% / 熊 26%」，这是 `grip_fraction` 参数（`build_meshes.py:1730, 1734`）。但 `compute_grip_points` 取的是该高度薄板内**最外侧真实顶点**的完整坐标（`build_meshes.py:1242-1268`），实测手实际高度是 **米菲 18.8% / 熊 27.0%**：

```
  grip y as fraction of height: 0.1876   (miffy)
  grip y as fraction of height: 0.2699   (zichaoxiong)
```

2. **「原版锚点 X 间距……比这两个玩偶都宽」对熊几乎不成立。** 实测熊的握点间距是 **0.5950**，与锚点 0.5990 只差 **0.0040（0.7%）**；米菲才是 0.3860（差 0.213）。所以「两只手会停在身体两侧的空中」对米菲成立、对熊几乎不成立。README 只举了米菲的数字。

### 1.12 已知局限 / 其余断言（**正确**）

| README | 核验 | 结论 |
| --- | --- | --- |
| 第 184 行「原版悬停高亮描边不会作用于替换模型」 | `PlushieModel.cs:968-996` 明确不重指 `item.mainRenderer`，且 URP/Lit 无 `_Interactable` | ✅ |
| 第 186-187 行「描边逐帧 CPU 重算，每实例约 1.5 万顶点」 | 实测米菲 15525 / 熊 16831 | ✅（「约」成立） |
| 第 33-43 行覆盖文件名表 | `Variants.cs` 的 `MeshFile`/`TextureFile`/`IconFile` 与 `AssetProvider.Read` 的「同名文件优先」逻辑 | ✅ 6 个文件名全部正确 |
| 第 155-157 行「build.ps1 校验内嵌资源与 assets/ 是否一致」 | `build.ps1:76-97` 分别跑 `verify_assets.py` / `verify_embedded.py`，失败即 `throw` | ✅ |
| 第 174-179 行 verify 脚本说明 | 同上，且 `buildinfo.txt` 字段与 `build.ps1:57-67` 一致 | ✅ |
| 第 65-66 行 `Config Version` 隐藏 | `Plugin.cs:223-228` 带 `"Hidden"` 标签 | ✅ |
| 第 185 行「不含任何第三方素材」 | **两个模型都是第三方 3MF** | ❌ **见第五节** |

---

## 二、资源与发行包

### 2.1 assets/icons/*.png 尺寸 / 模式 / alpha

```
$ python -c "<Pillow 读取 assets/icons/*.png 与 assets/*_shading.png>"
=== assets/icons ===
  .\assets\icons\icon_miffy.png
    format=PNG mode=RGBA size=(512, 512)
    alpha: min=0 max=255  0x00=187241 (71.43%) 0xFF=62711 (23.92%) non-opaque=199433 (76.08%)
    bytes on disk: 37822
  .\assets\icons\icon_zichaoxiong.png
    format=PNG mode=RGBA size=(512, 512)
    alpha: min=0 max=255  0x00=141691 (54.05%) 0xFF=107787 (41.12%) non-opaque=154357 (58.88%)
    bytes on disk: 46954
=== assets shading pngs ===
  .\assets\miffy_shading.png        format=PNG mode=RGBA size=(294, 1)  alpha 100% 0xFF  158 bytes
  .\assets\zichaoxiong_shading.png  format=PNG mode=RGBA size=(294, 1)  alpha 100% 0xFF  172 bytes
```

结论：

- 游戏内图标：**512×512 RGBA**，alpha 范围**完整覆盖 0..255**（`min=0, max=255`），且**非全透明像素占 76.08% / 58.88%**——说明边缘有大量中间 alpha 值，即**抗锯齿软边确实存在**，与 README 第 16 行「带抗锯齿的透明背景 + 黑描边」一致。生成逻辑见 `tools/build_icons.py:116-154`（保留高斯模糊灰度作为描边 alpha，而非阈值化成 0/255）。
- 调色板贴图：**294×1 RGBA，完全不透明**，与 `src/AssetProvider.cs` 注释「it is 294x1 with colour blocks only a few dozen pixels wide」及 `texture.Apply(false, true)`（禁止 mip）严格对应 ✅。
- 512×512 是游戏内图标；Thunderstore 的 `icon.png` 是另一个文件（见下）。

### 2.2 release/ 产物

```
$ Get-ChildItem -Recurse release\
d---- release\stage
-a--- release\icon.png                    76198
-a--- release\PlushieSwap-1.0.0.zip     5780284
d---- release\stage\plugins
-a--- release\stage\CHANGELOG.md           266
-a--- release\stage\icon.png             76198
-a--- release\stage\manifest.json          352
-a--- release\stage\README.md             2245
-a--- release\stage\plugins\PlushieSwap\PlushieSwap.dll  12133376
```

**icon.png 是否恰好 256×256 —— 是，三种取法都是：**

```
=== icons in zip/stage ===
  .\release\icon.png        -> (256, 256) RGBA
  .\release\stage\icon.png  -> (256, 256) RGBA
  zip icon.png              -> (256, 256) RGBA
```

alpha 实测：`min=170 max=255, 0x00=0 (0.00%), 0xFF=62379 (95.18%)`——即该图标**没有使用透明**（最小 alpha 170 来自 `build_icon_release.py:53-57` 的黑色 scrim 渐变），符合 wiki 对「使用透明时需保证任意背景可读」的提醒（本图标不透，风险为零）。

**zip 内容清单与解压后路径（`tools/package_release.py` 的输出，实测 zip == stage 逐字节一致）：**

| zip 内路径 | 字节 | stage 对应 | 一致 |
| --- | --- | --- | --- |
| `CHANGELOG.md` | 266 | ✅ | ✅ |
| `README.md` | 2245 | ✅ | ✅ |
| `icon.png` | 76198 | ✅ | ✅ |
| `manifest.json` | 352 | ✅ | ✅ |
| `plugins/PlushieSwap/PlushieSwap.dll` | 12133376 | ✅ | ✅ |

根目录平铺、`plugins/` 子目录承载 DLL——与官方要求的布局一致。

### 2.3 manifest.json 是否符合 Thunderstore 官方规范（已上网核实）

**核实来源（官方 wiki，2026 现行版）：**

- 页面：<https://wiki.thunderstore.io/mods/creating-a-package>
- Markdown 原文（GitBook 提供的纯文本版本，本审计即抓取此 URL）：<https://wiki.thunderstore.io/mods/creating-a-package.md>
- 索引：<https://wiki.thunderstore.io/llms.txt>；官方校验工具：<https://thunderstore.io/tools/manifest-v1-validator/>

官方原文（`creating-a-package.md`，逐字引用）：

> A valid Thunderstore package is a zip file which **must** contain at least the following files at the root of the zip:
>
> | Name | Description |
> | `icon.png` | PNG icon for the mod, must be 256x256 resolution. |
> | `README.md` | Readme in markdown syntax. Will be rendered on the package's page. |
> | `manifest.json` | JSON file with metadata of the package. See [Manifest](#manifest) for structure. |
>
> **File naming is case-sensitive and must match the above exactly!**

> A valid icon has to be exactly 256x256 in resolution and in PNG format.

> The file should be in standard JSON format (UTF-8 encoded) with the following contents:
> `name` — Name of the mod, no spaces. Allowed characters: `a-z A-Z 0-9 _`
> `description` — A short description of the mod, shown on the mod list. Max 250 characters.
> `version_number` — Version number of the mod, following the semantic version format Major.Minor.Patch
> `dependencies` — A list of other packages that are required for this package to function.
> `website_url` — URL of the mod's website (e.g. GitHub repo). Can be left an empty string.

> The format used by Thunderstore to refer to other packages is as follows: `{team name}-{package name}-{package version}`

**逐字段实测校验：**

```
=== manifest.json validation vs wiki spec ===
  keys: ['dependencies', 'description', 'name', 'version_number', 'website_url']
  name='PlushieSwap' len=11  allowed-chars-only=True
  description len=187  <=250: True
  version_number='1.0.0'  semver: True
  website_url='' (empty allowed)
  dependencies=['BepInEx-BepInExPack_PEAK-5.4.75301']
    dep 'BepInEx-BepInExPack_PEAK-5.4.75301' matches {team}-{name}-{version}: True
```

| 要求 | 实测 | 结论 |
| --- | --- | --- |
| 根目录有 `icon.png` / `README.md` / `manifest.json` | 三者均在 zip 根 | ✅ |
| 文件名大小写完全一致 | `icon.png`、`README.md`、`manifest.json`、`CHANGELOG.md` 全小写匹配 | ✅ |
| `icon.png` 恰好 256×256 PNG | `(256, 256)` PNG | ✅ |
| `name` 仅 `a-zA-Z0-9_`、无空格 | `PlushieSwap` | ✅ |
| `description` ≤ 250 字符 | 187 | ✅ |
| `version_number` 为 `Major.Minor.Patch` | `1.0.0` | ✅ |
| `dependencies` 为 `{team}-{name}-{version}` 列表 | `BepInEx-BepInExPack_PEAK-5.4.75301` | ✅ |
| `website_url` 即使为空也必须有该键 | `""` 存在 | ✅ |

**判定：`manifest.json` 完全合规，无任何需要修改的字段。**

可选改进（非违规）：`website_url` 为空，会失去包页面上的主页链接；建议填 GitHub 仓库或 MakerWorld 页面。

### 2.4 release/ 是否过期 —— **是，已过期且不可重现**

**（a）包内 DLL 与当前 `dist/` 构建不一致：**

```
=== DLL hashes ===
  dist            : 582E1B00149682E8EC0A813327D14E80DDAEDC57B489E0AAA65DE34CA3F68524
  release/stage   : 840813900B9514847A35ACF34A3C29B9C53CD7CE22D6DDBFAB1F18EB3D94E54B
  release/zip     : 840813900B9514847A35ACF34A3C29B9C53CD7CE22D6DDBFAB1F18EB3D94E54B
  buildinfo says  : 582E1B00149682E8EC0A813327D14E80DDAEDC57B489E0AAA65DE34CA3F68524
```

`dist\PlushieSwap\buildinfo.txt` 记录的哈希与 `dist` DLL 一致，而 `release/` 里的 DLL 是**另一个**构建（`release/stage` 与 zip 内部一致，说明 zip 本身是自洽的，只是整体落后于 `dist/`）。`buildinfo.txt` 当前内容：

```
commit:     bc696a9
version:    1.0.0+bc696a91a924ded823102785308fd8294badeadf
sha256:     582E1B00149682E8EC0A813327D14E80DDAEDC57B489E0AAA65DE34CA3F68524
built_utc:  2026-09-19T18:20:48Z
```

**（b）`release/icon.png` 无法重新生成：**

```
$ Test-Path "D:\备份\zichao.jpg"
MISSING -> build_icon_release.py cannot be re-run
```

`tools/build_icon_release.py:16` 硬编码 `SOURCE = r"D:\备份\zichao.jpg"`，该源图**已不在磁盘上**。因此 `release/icon.png` 是一次性产物，**无法复现**。

**（c）正确做法——重新生成的命令：**

```powershell
# 1. 重新构建 DLL 到 dist/（会自动跑两个校验闸门）
pwsh -File build.ps1

# 2. 重新生成 256x256 发行图标（需要先恢复 D:\备份\zichao.jpg）
python tools\build_icon_release.py

# 3. 重新打 zip（package_release.py 会校验 dist/ 与 release/icon.png 都存在）
python tools\package_release.py
```

修复建议：

1. 立刻重跑 `build.ps1` + `package_release.py`，让 release 追上 `dist`。
2. **把 `build_icon_release.py` 的源图纳入仓库**（例如 `research/icon_source.jpg`）或改为从 `assets/icons/icon_zichaoxiong.png` 派生，消除对 `D:\备份\` 的硬编码依赖。
3. 建议在 `package_release.py` 里增加一道断言：把 `dist/PlushieSwap/PlushieSwap.dll` 的 SHA-256 与 `buildinfo.txt` 比对，不一致就中止（当前只检查文件**存在**，不检查**一致**——这正是本次过期没被拦住的原因）。

---

## 三、仓库卫生

基线：`git ls-files` 共 **215** 个文件，`git status --short` 干净。

```
=== tracked files by dir ===
   91 research          (其中 42 个是 research/preview/*.png)
   57 tools
   11 src
    5 assets
    4 <root>
    2 models
    1 shaders
```

```
=== total tracked bytes by extension ===
  .3mf          2 files   14,122,232 bytes (   13.47 MB)
  .psmesh       2 files    4,677,440 bytes (    4.46 MB)
  .cs          12 files    3,180,334 bytes (    3.03 MB)
  .png         46 files    1,371,917 bytes (    1.31 MB)
  .py         138 files      658,799 bytes (    0.63 MB)
  .txt          8 files      149,358 bytes (    0.14 MB)
  .md           2 files       27,219 bytes (    0.03 MB)
  .shader       1 files       10,414 bytes (    0.01 MB)
  .ps1          1 files        6,623 bytes (    0.01 MB)
  .csproj       1 files        3,033 bytes (    0.00 MB)
  .json         1 files        1,467 bytes (    0.00 MB)
```

跟踪总量约 **22.9 MB**，其中 `models/*.3mf` 独占 **13.47 MB（59%）**。

### 3.1 一次性诊断脚本

判定「一次性」的口径：**不可从 `build.ps1` / `package_release.py` 到达**，且本身是「dump/find/inspect/diag/measure/preview/survey/score/optimise」类探索脚本。

`tools/` 的 **57** 个 `.py` 中，**只有 9 个是承重的**（被 `build.ps1` 或彼此构成构建链）：

```
=== tools/ LOAD-BEARING (reachable from build.ps1 / package_release) : 9 ===
    build_meshes.py      <- build.ps1:71（-RebuildAssets）
    threemf.py           <- build_meshes.py:import
    build_icons.py       <- build.ps1:72
    preview_mesh.py      <- build_icons.py:13
    embed_assets.py      <- build.ps1:73
    verify_assets.py     <- build.ps1:81
    verify_embedded.py   <- build.ps1:90
    package_release.py   <- 手工调用（发行打包）
    build_icon_release.py<- 手工调用（发行图标）
```

其余 **48 个**是探索/诊断脚本：

```
analyze_3mf.py  check_pink.py  diag_colors.py  diag_extruder_pos.py  diag_item_mesh.py
diag_miffy_shape.py  dump_bingbong_hands.py  dump_fields.py  dump_hand_anchors.py
dump_hand_mesh.py  dump_item_fields.py  dump_item.py  dump_player_hand.py  dump_player_rig.py
dump_plush_shader.py  dump_prefab_full.py  dump_prefab_materials.py  dump_prefab.py
extract_aux.py  find_bingbong.py  find_hand_anchors.py  find_hand_animation.py
find_item_uidata.py  find_item_uidata2.py  find_shader.py  find_waist.py  inspect_prefab.py
inspect_prefab2.py  list_items.py  list_objects.py  measure_item_space.py
measure_player_hand.py  measure_shot.py  measure_vanilla.py  measure_vanilla2.py
paint_colors.py  preview_current_grip.py  preview_grip.py  preview_hands_real.py
profile_shape.py  read_default_pos.py  read_vertex_colors.py  render_grip_guide.py
sample_blush.py  scan_assets.py  solve_grips.py  survey_hand_anchors.py  verify_merge.py
```

`research/` 的 **81** 个 `.py` 全部不参与构建（`PlushieSwap.csproj` 设了 `EnableDefaultCompileItems=false` 且只 `Compile Include="src\**\*.cs"`），其中 78 个是探索脚本（`blender_*` 15 个、`measure_*` 11 个、`dump_*` 6 个、`outline_*`/`score_*`/`solve_*`/`verify_*` 等），另 8 个 `.txt` 是 Unity 资源转储（`shader_properties.txt` 94 KB 等）。

### 3.2 过期研究产物

- **`research/preview/*.png` 共 42 个被跟踪**（1.31 MB 中的绝大部分），是描边方案 A/B/C/D 的对比渲染与 `ss_check_*` 屏幕空间宽度扫描。它们与代码里最终采用的方案**没有引用关系**，且 `.gitignore` 第 18 行本来就想忽略这个目录（见 3.4）。
- **`research/*.txt` 8 个**（`shader_properties.txt` / `shader_inventory.txt` / `shader_candidates.txt` / `shader_detail.txt` / `shader_programs.txt` / `urp_renderers.txt` / `outline_width_metrics.txt` / `outline_undo_check.txt`）是对 Unity 资源的转储。**只有 `outline_width_metrics.txt` 还有活引用**（被 `shaders/PlushieOutline.shader:14` 引用为测量依据）；其余 7 个**无任何引用**：

```
  outline_width_metrics.txt  cited by src/tools/shaders: [PlushieOutline.shader]  in README: False
  shader_properties.txt      cited by src/tools/shaders: []   in README: False
  shader_inventory.txt       cited by src/tools/shaders: []   in README: False
  shader_candidates.txt      cited by src/tools/shaders: []   in README: False
  shader_detail.txt          cited by src/tools/shaders: []   in README: False
  shader_programs.txt        cited by src/tools/shaders: []   in README: False
  urp_renderers.txt          cited by src/tools/shaders: []   in README: False
  outline_undo_check.txt     cited by src/tools/shaders: []   in README: False
```

- **悬空引用**：`research/OUTLINE_DESIGN.md:23-24` 写「For the real current design see `REWRITE.md` §1.2 and `src/PlushieOutline.cs`」，但 `REWRITE.md` 与 `HANDOFF.md` 已在 `bc696a9` 一并删除：

```
$ git log --diff-filter=D --name-only --oneline -5
bc696a9 Drop the stale handoff notes the user removed
HANDOFF.md
REWRITE.md
```

```
$ Test-Path REWRITE.md ; Test-Path research\REWRITE.md
False
False
```

### 3.3 不该跟踪的大二进制

无违规大文件（`git ls-files` 里没有 `.zip` / `.exe` / `.dll` / `.pdb` / `.jpg` / `.webp` / `.blend` / `.stl`）。但**已跟踪**的大二进制有两类：

| 文件 | 字节 | 是否必要 |
| --- | --- | --- |
| `models/zichaoxiong.3mf` | 8,514,387 | 构建源，必要（但见 3.5） |
| `models/miffy.3mf` | 5,607,845 | 构建源，必要（但见 3.5） |
| `src/EmbeddedAssets.g.cs` | 3,026,701 | 生成物，被 `verify_embedded.py` 用作校验基准，必要 |
| `assets/zichaoxiong.psmesh` | 2,401,250 | 构建产物，被 `verify_assets.py` 用作校验基准，必要 |
| `assets/miffy.psmesh` | 2,276,190 | 同上 |

注意：`assets/*.psmesh` 与 `src/EmbeddedAssets.g.cs` **都是生成物**，之所以必须跟踪，是因为两个校验脚本拿它们当「基准」比对（`build.ps1:83, 92`）。这是**有意的设计**，不建议改成忽略。

### 3.4 .gitignore 遗漏项与矛盾

当前 `.gitignore` 全文：

```
 1: bin/
 2: obj/
 3: dist/
 4: libs/
 5: tools/preview/
 6: tools/__pycache__/
 7: research/__pycache__/
 8: *.user
 9: *.pyc
10:
11: # Blender exchange files (regenerated by research/export_for_blender.py)
12: research/blender/
13:
14: # 3MF-embedded previews/thumbnails, no script reads them
15: tools/preview_aux/
16:
17: # One-off render comparisons and experiment scripts (regenerated on demand)
18: research/preview/
19:
20: # Third-party reference mod: contains someone else's binaries, audio and models
21: # under a licence that does not permit redistribution here.
22: ScallionMiku-main/
23:
24: # Thunderstore release output (regenerated by tools/package_release.py)
25: release/
```

**（a）矛盾：第 18 行 `research/preview/` 与「42 个已跟踪文件」冲突。**

```
$ git check-ignore -v --no-index -- research/preview/final_miffy.png
.gitignore:18:research/preview/	research/preview/final_miffy.png
```

即该文件**匹配忽略规则**，却**已在索引里**（`check-ignore` 不加 `--no-index` 时对已跟踪文件不报，故先前误判为 TRACKABLE）。规模：

```
  tracked in research/preview: 42
  ignored on disk in research/preview: 282
```

规则与事实矛盾（42 个是在规则生效前提交的，或曾被 `git add -f`）。两种自洽修法：把 42 个 `git rm --cached` 掉，或删掉第 18 行。**本审计只给建议，未执行。**

**（b）真正的遗漏项：**

| 缺失规则 | 理由 |
| --- | --- |
| `*.zip` / `*.7z` | 手工打的包若不放在 `release/` 下就会误提交 |
| `*.log` | 运行 BepInEx 时可能落在仓库内 |
| `.vs/` / `*.suo` | Visual Studio 用户会生成 |
| `*.binlog` | `dotnet build -bl` 的产物 |
| `research/audit/`（**待定**） | 5 份审计报告（含本文件）目前是**未跟踪且未忽略**（`?? research/audit/…`）。若希望入库，**不要**加忽略；若要忽略，需明确决定 |

`dist/`、`release/`、`libs/`、`bin/`、`obj/`、`ScallionMiku-main/`、`research/blender/`、`tools/preview_aux/` 均已覆盖 ✅。

### 3.5 models/*.3mf 共 13.47 MB 的处理建议

`models/*.3mf` = 14,122,232 字节 = **13.47 MB**，占跟踪总量 **59%**。

方案对比：

| 方案 | 做法 | 优点 | 缺点 |
| --- | --- | --- | --- |
| **A. Git LFS（推荐）** | `git lfs track "models/*.3mf"` + `.gitattributes`，迁移历史 | 仓库克隆体积从 22.9 MB 降到约 9.4 MB；仍保留完整可复现性（`verify_assets.py` 依赖 3MF 的 SHA-256） | 需要 LFS 服务端（GitHub 免费额度 1 GB 存储 / 1 GB 月流量，够用）；`verify_assets.py` 需能读到 LFS 指针解析后的真实文件 |
| **B. 移出仓库 + 下载脚本** | 3MF 放到 Release 附件/网盘，写 `tools/fetch_models.py` | 仓库最瘦 | **破坏构建可复现性**——`build.ps1 -RebuildAssets` 在离线/CI 下无法工作；`verify_assets.py` 的 `source_sha256` 失去意义 |
| **C. 保持现状** | 什么都不做 | 零风险、构建完全自包含 | 仓库持续偏大；3MF 内部含大量无用数据（见下） |
| **D. 瘦身后再提交** | 用 `tools/analyze_3mf.py` / `tools/extract_aux.py` 剥掉 3MF 里的预览图与 `project_settings.config` | 体积可显著下降 | **不可取**：会改变文件 SHA-256，导致 `assets/manifest.json` 的 `source_sha256` 失效、`verify_assets.py` 全线报警，且丢失溯源信息 |

**建议：方案 A（Git LFS）**，理由是 3MF 是构建源、必须与代码同版本，而 LFS 是唯一既瘦身又保留可复现性的做法。

补充依据——3MF 里确实塞了大量与几何无关的数据：

```
### miffy.3mf  (5,607,845 bytes)
  3D/3dmodel.model                       2,263
  3D/Objects/object_15.model        31,445,218   <- 解压后，几何本体
  Metadata/plate_1.png                  28,407
  Metadata/project_settings.config      49,783
  Metadata/top_1.png                    14,387
  Metadata/plate_1_small.png             4,073
  ...（共 14 个条目）

### zichaoxiong.3mf  (8,514,387 bytes)
  3D/Objects/object_16.model        41,383,707
  Auxiliaries/.thumbnails/thumbnail_middle.png  507,081
  Auxiliaries/Model Pictures/微信图片_*.webp      67,304 + 66,266
  Auxiliaries/Profile Pictures/微信图片_*.webp    67,304
  Metadata/project_settings.config              58,877
  Metadata/top_1.png                            43,841
  Metadata/plate_1.png                          40,784
  ...（共 21 个条目）
```

（解压后几何体 31–41 MB，靠 deflate 压到 5.6–8.5 MB。）

### 3.6 三分类清单（**仅建议，未执行任何删除**）

#### 建议删除（从索引移除；磁盘可保留）

1. **`research/preview/*.png`（42 个）** —— 与 `.gitignore:18` 直接冲突，且是方案探索期的渲染对比图，无代码引用。`git rm --cached` 后可保留本地文件。
2. **7 个无引用的 shader 转储 txt** —— `research/shader_properties.txt`、`shader_inventory.txt`、`shader_candidates.txt`、`shader_detail.txt`、`shader_programs.txt`、`urp_renderers.txt`、`outline_undo_check.txt`。已实测零引用（见 3.2）。**保留 `research/outline_width_metrics.txt`**（被 shader 引用）。
3. **`research/*.py` 中纯 Blender 探索脚本（15 个）** —— `blender_ab/below/compare/diagnose_lines/dirs/face/front/import/iso/outline_experiment/render/render_screenspace/shellonly/ship/solidify/split_shell/tool_survey/variants2.py`。它们 `import bpy`（本机无 Blender 则完全不可运行），且 `research/blender/` 已被忽略——即它们的**输出目录都不入库**，脚本本身也无引用。
4. **`research/*2.py` 这类明显被取代的版本** —— `research/measure_vanilla_mesh2.py`、`research/outline_variants2.py`、`research/survey_shaders2.py`、`tools/find_item_uidata2.py`、`tools/inspect_prefab2.py`、`tools/measure_vanilla2.py`（同名带 `2` 的后继版本并存）。

#### 建议保留

1. **9 个承重工具**（3.1 表）—— 构建链核心。
2. **`tools/verify_merge.py`** —— 虽不在 `build.ps1` 链上，但被 6 个脚本 `import`（`preview_grip.py`、`preview_current_grip.py`、`preview_hands_real.py`、`outline_compare.py`、`outline_variants.py`、`shell_topology.py`），删除会连带打断它们。
3. **`tools/preview_mesh.py`** —— 被 **15 个文件** import（含承重的 `build_icons.py`），是事实上的公共库。
4. **`research/OUTLINE_DESIGN.md`** —— 唯一的设计史文档，且已有清晰状态横幅。
5. **`research/outline_width_metrics.txt`** —— 被 `shaders/PlushieOutline.shader:14` 引为测量依据。
6. **`assets/*.psmesh`、`src/EmbeddedAssets.g.cs`、`models/*.3mf`** —— 校验基准与构建源，见 3.3。
7. **`research/audit/*.md`** —— 本批审计报告（含本文件）。

#### 建议 gitignore

1. 补 `*.zip`、`*.7z`、`*.log`、`*.binlog`、`.vs/`、`*.suo`。
2. **修正第 18 行的矛盾**（二选一：移除该行，或 `git rm --cached research/preview`）。
3. 明确 `research/audit/` 的去留（当前既未跟踪也未忽略，会一直显示为 `??`）。
4. 考虑 `research/blender_tool_survey.py` 之类若删除后，`research/blender/` 规则可保留（输出目录）。

---

## 四、文档一致性

### 4.1 是否还被代码引用 —— **全部无引用**

用 ripgrep 语义的 `Select-String` 全仓库扫描（排除 `.git` / `bin` / `obj` / `libs` / `dist` / `EmbeddedAssets.g.cs`）：

```
=== references to OUTLINE_DESIGN / PlushieOutline.shader / PlushieShaderLoader.sample ===
  .\research\OUTLINE_DESIGN.md:9   > * `shaders/PlushieOutline.shader` and `research/PlushieShaderLoader.sample.cs`
  .\research\OUTLINE_DESIGN.md:195 Full source: `shaders/PlushieOutline.shader` (⚠️ research artefact, unused).
  .\research\OUTLINE_DESIGN.md:201 | `shaders/PlushieOutline.shader` | **new** - the complete shader ... ⚠️ **never shipped**: research artefact, not referenced by any code |
  .\research\OUTLINE_DESIGN.md:202 | `research/PlushieShaderLoader.sample.cs` | **new** - drop-in for `PlushieModel.cs` — ⚠️ **never adopted**: the sample was not merged into `src/` |
  .\research\PlushieShaderLoader.sample.cs:31 internal static class PlushieShaderLoader
  .\shaders\PlushieOutline.shader:43  // research/PlushieShaderLoader.sample.cs. If the bundle is missing the
```

结论：

- **`src/` 与 `build.ps1` 对这三个文件零引用。** 唯一的匹配都在 `research/` 与 `shaders/` 内部**互相引用**。
- **编译层面已排除**：`PlushieSwap.csproj` 设 `<EnableDefaultCompileItems>false</EnableDefaultCompileItems>`，只 `<Compile Include="src\**\*.cs" />`，因此 `research/PlushieShaderLoader.sample.cs` **永远不会被编译进 DLL**。
- **运行时兜底存在**：`src/PlushieModel.cs` 走 `Shader.Find` + 内置回退链（`URP/Lit` → `Simple Lit` → `W/Peak_Standard` → `Standard`，见 `Plugin.cs:209-212` 的配置说明），不加载任何 AssetBundle。

### 4.2 三份文件是否写清了「历史研究产物、未被采用」

| 文件 | 状态声明 | 判定 |
| --- | --- | --- |
| `research/OUTLINE_DESIGN.md` | **有，且非常清晰**。第 3-24 行是加粗横幅：`> ## ⚠️ STATUS: HISTORICAL RESEARCH DOCUMENT — NOT THE SHIPPED DESIGN`，并逐条说明「recommendation was **never adopted**」「no AssetBundle was ever built」「`shaders/PlushieOutline.shader` 和 `research/PlushieShaderLoader.sample.cs` are **research artefacts only** — nothing in `src/` or `tools/` references them」 | ✅ **优秀** |
| `research/PlushieShaderLoader.sample.cs` | **有**。第 1-4 行：`// Research-only sample: how PlushieModel.cs would load the custom outline shader.` / `// This file is NOT compiled into the mod. It documents the exact drop-in for src/PlushieModel.cs` | ✅ **清晰** |
| `shaders/PlushieOutline.shader` | **无自述状态横幅**。头部 48 行是设计说明，通篇以现在时描述该 shader 的用途；只有第 42-44 行顺带提到「Build into an AssetBundle and load it from the plugin; see research/PlushieShaderLoader.sample.cs. If the bundle is missing the plugin keeps its current Universal Render Pipeline/Lit fallback.」——**读者单独打开这个文件无法得知它从未被采用** | ⚠️ **需补一行** |

**（a）`shaders/PlushieOutline.shader` 建议补的状态行**（加在第 1 行之后）：

```hlsl
// ⚠️ STATUS: HISTORICAL RESEARCH ARTEFACT — NEVER SHIPPED.
// This shader was never compiled into an AssetBundle (that needs the Unity editor,
// which this project does not have) and is not referenced by src/ or build.ps1.
// The shipping implementation does the same maths on the CPU every frame in
// src/PlushieOutline.cs. See research/OUTLINE_DESIGN.md for the full history.
```

**（b）`research/OUTLINE_DESIGN.md` 的悬空引用**（第 23-24 行）——`REWRITE.md` 已删除：

```
当前：> kept for that reason. For the real current design see `REWRITE.md` §1.2 and
      > `src/PlushieOutline.cs`.
建议：> kept for that reason. For the real current design see `src/PlushieOutline.cs`
      > (and `README.md` §「描边为什么不删面」).
```

---

## 五、模型署名（用户明确要求）

### 5.1 抓取结果

**两个目标页面均拒绝自动化访问**：

```
$ web_fetch https://makerworld.com.cn/zh/models/2032846-miffy-...
Fetched ... (HTTP 403)  ->  "请稍候…"   （Cloudflare 挑战页）

$ web_fetch https://makerworld.com.cn/zh/models/2666015-zuo-zi-zi-chao-xiong-duo-se-yi-ti
Fetched ... (HTTP 403)  ->  "请稍候…"
```

替代路径尝试与结果（均已实测）：

| 路径 | 结果 |
| --- | --- |
| `makerworld.com.cn/api/v1/design-service/design/{2032846,2666015}` | **403**（含完整浏览器头、Referer、Origin 仍 403） |
| `makerworld.com/api/v1/design-service/design/2032846` | HTTP 200 但返回**全零桩**（`id:0, title:"", creator.uid:0`）→ 该 ID 在国际站不存在 |
| `makerworld.com/api/v1/design-service/design/2666015` | HTTP 200，但内容是**完全不同的模型**（`Bürstner Brickman 20cm Figur` by `Andreas_8873`）→ **证明 .cn 与 .com 使用彼此独立的 ID 命名空间** |
| `r.jina.ai`、`api.allorigins.win`、`api.codetabs.com`、`corsproxy.io` | 连接超时 / 522 / 403 |
| `3dgo.app`（第三方镜像） | 403 |
| Bing / DuckDuckGo HTML / firecrawl 搜索 | 未命中该模型 |
| `makerworld.pro/api/search`（可用镜像） | 命中「坐姿自嘲熊（多色一体）/ Lorensi / 2026-06-25」；未命中目标米菲兔 |

**关键发现：3MF 文件内部自带作者元数据**，这成了主要证据来源（3MF 就是 zip）。

### 5.2 3MF 内部元数据（**决定性证据**）

`3D/3dmodel.model` 的 `<metadata>` 节点，按字节级解码（脚本把原始字节按 UTF-8 解码，避免控制台代码页干扰）：

```
### miffy.3mf
  key=Designer         rawbytes=b''
      utf-8      -> 
  key=License          rawbytes=b''
      utf-8      -> 
  key=Title            rawbytes=b''
      utf-8      -> 
  key=Copyright        rawbytes=b''
      utf-8      -> 
  key=DesignerUserId   rawbytes=b'2755976439'
      utf-8      -> 2755976439

### zichaoxiong.3mf
  key=Designer         rawbytes=b'\xe5\xa4\x9c\xe5\xa4\x9c\xe6\xa4\xb0\xe5\xad\x90\xe5\x86\xb0'
      utf-8      -> 夜夜椰子冰
  key=License          rawbytes=b'Standard Digital File License'
      utf-8      -> Standard Digital File License
  key=Title            rawbytes=b'\xe5\x9d\x90\xe5\xa7\xbf\xe8\x87\xaa\xe5\x98\xb2\xe7\x86\x8a\xef\xbc\x88\xe5\xa4\x9a\xe8\x89\xb2\xe4\xb8\x80\xe4\xbd\x93\xef\xbc\x89'
      utf-8      -> 坐姿自嘲熊（多色一体）
  key=ProfileUserName  rawbytes=b'\xe5\xa4\x9c\xe5\xa4\x9c\xe6\xa4\xb0\xe5\xad\x90\xe5\x86\xb0'
      utf-8      -> 夜夜椰子冰
  key=DesignerUserId   rawbytes=b'2431656860'
      utf-8      -> 2431656860
```

`zichaoxiong.3mf` 的完整元数据清单：

```
### zichaoxiong.3mf
  Application                  = 'BambuStudio-02.06.00.51'
  BambuStudio:3mfVersion       = '1'
  CreationDate                 = '2026-06-25'
  Description                  = '高10cm，多色一体打印 / 使用双头以上打印机可将黑色单独放一个打印头，防止串色'
  Designer                     = '夜夜椰子冰'
  DesignerCover                = '33906e21d7ac45f5.jpg'
  DesignerUserId               = '2431656860'
  License                      = 'Standard Digital File License'
  MakerLab                     = 'IM3Dv2'
  MakerLabRegion               = 'CN'
  ModificationDate             = '2026-06-25'
  Origin                       = 'original'
  ProfileCover                 = '33906e21d7ac45f5.jpg'
  ProfileTitle                 = '0.2mm 层高, 2 层墙, 15% 填充'
  Title                        = '坐姿自嘲熊（多色一体）'
  CopyRight                    = '[]'
  ProfileUserId                = '2431656860'
  ProfileUserName              = '夜夜椰子冰'
  DesignRegion                 = 'CN'
  DesignModelId                = 'CN7f9861bc88d732'
  DesignProfileId              = '159377481'
```

`miffy.3mf` 的完整元数据清单——**作者与许可被剥离**：

```
### miffy.3mf
  Application                  = 'BambuStudio-02.03.00.70'
  CreationDate                 = '2026-01-19'
  Description                  = ''
  Designer                     = ''          <- 空
  DesignerUserId               = '2755976439'
  License                      = ''          <- 空
  Title                        = ''          <- 空
  Copyright                    = ''          <- 空
  ModificationDate             = '2026-01-19'
  Origin                       = ''
```

`miffy.3mf` 的 zip 条目名也无中文署名线索；`zichaoxiong.3mf` 含微信图片命名：

```
    Auxiliaries/Model Pictures/微信图片_20260625192228_1021_116.webp
    Auxiliaries/Model Pictures/微信图片_20260625192227_1020_116.webp
    Auxiliaries/Profile Pictures/微信图片_20260625192227_1020_116.webp
```

### 5.3 自嘲熊 —— **已核实（双证据链）**

**证据 A：3MF 内嵌**（上表）——`Title=坐姿自嘲熊（多色一体）`、`Designer=夜夜椰子冰`、`DesignerUserId=2431656860`、`License=Standard Digital File License`、`CreationDate=2026-06-25`、`DesignerCover=33906e21d7ac45f5.jpg`、`DesignModelId=CN7f9861bc88d732`。

**证据 B：makerworld.com 国际站 API**（该 ID 可用，且内容与 3MF 完全对应）：

```
$ makerworld.com/api/v1/design-service/design/3154227
  title           : 坐姿自嘲熊（多色一体）
  titleTranslated : Sitting Self-Mocking Bear (Multi-color PIP)
  slug            : sitting-self-mocking-bear-multi-color-pip
  license         : Standard Digital File License
  modelId         : US20e4c59d756dde
  createTime      : 2026/6/25 11:33:23
  creator.name    : Lorensi
  creator.handle  : Lorensi.
  creator.uid     : 495168789
  allowReCreation : False

$ makerworld.com/api/v1/design-service/design/3154227/instances
  profileId 925588785, cover .../33906e21d7ac45f5.jpg
```

**关联依据**（把用户给的 `.cn/2666015` 链接对上国际站 `3154227`）：标题逐字相同、`License` 相同、创建日期同为 **2026-06-25**、封面图哈希同为 **`33906e21d7ac45f5.jpg`**（3MF 内 `DesignerCover`/`ProfileCover` 也是它）、描述「高10cm，多色一体打印」一致。第三方镜像独立佐证：

> [坐姿自嘲熊（多色一体） - 3D Printer File - 3D GO](https://3dgo.app/models/makerworld/3154227) — 「坐姿自嘲熊（多色一体）. Lorensi. June 25, 2026.」「高10cm，多色一体打印.」
> [3D Printer Files by Lorensi on makerworld - 3D GO](https://3dgo.app/user/makerworld/495168789) — 13 个模型，含「坐姿自嘲熊(多色一体)」

**⚠️ 无法消除的作者归属歧义（必须如实标注）：**

同一模型上出现**两个不同的 MakerWorld 账号**：

| 来源 | 账号 | UID |
| --- | --- | --- |
| 3MF 内嵌 `Designer` / `ProfileUserName` | **夜夜椰子冰** | `2431656860` |
| 国际站 API `designCreator.name` | **Lorensi** | `495168789` |

两者指向同一份模型（封面哈希、日期、标题、许可全同），但**我无法从公开渠道判定哪一个是原始发布者**（.cn 页面 403，无法读取其作者字段；国际站那条是导入/重传还是本人跨区账号，无从确认）。此外，用户给出的链接片段 `#profileId-3082645` **既不等于** 3MF 的 `DesignProfileId=159377481`，**也不等于** 国际站的 `profileId=925588785`——该锚点很可能只是用户浏览时的打印配置视图 id，但也进一步说明**该数字不能当作作者标识**。

### 5.4 米菲兔 —— **无法核实（拒绝编造）**

- **3MF 只保留了上传者 UID `2755976439`**；`Designer`、`License`、`Title`、`Copyright` **全部为空**。也就是说这个 3MF 在导出/再加工时**丢掉了作者名与许可**。
- MakerWorld `.cn` 页面（`2032846`）403，无法读取作者名与 License 字段。
- MakerWorld `.com` 的 `2032846` 返回全零桩，说明该 ID 在国际站**不存在**（ID 命名空间独立）。
- 镜像（3dgo / makerworld.pro）与搜索（Bing / DuckDuckGo / firecrawl）**均未命中**该模型。搜索到的其他「米菲兔」模型（PeterWei、Warrior10JJ、`_blank_`、Heen、dumbehard、moon_moon…）**没有一个**能对应上本项目的模型，**不能张冠李戴**。

**结论：米菲兔的作者名与许可条款，本审计无法核实。** 绝不编造。

**需要用户/Lead 做的一件事（最简单可靠）**：在浏览器里打开

`https://makerworld.com.cn/zh/models/2032846-miffy-mi-fei-tu-jing-dian-yi-zhu-bai-jian-zhi-chi`

读取页面上的 **作者昵称**（`@` 后面的名字）与 **License 字段**（页面「模型许可」处），把原文抄给 Lead。另外可顺便核对 `?from=search#profileId-2268033` 对应的打印配置归属。

### 5.5 Standard Digital File License 的实际含义（影响本项目能否分发）

自嘲熊明确是 `Standard Digital File License`，这是 MakerWorld **最严格**的许可。论坛与解读来源引用的条款原文：

> You are prohibited from sharing, sub-licensing, selling, renting, hosting, transferring, or distributing the digital file, 3D printed versions, or any other derivative works of this object in any digital or physical format, including remixes of this object.
>
> — [Standard Digital File License question — Bambu Lab Community Forum](https://forum.bambulab.com/t/standard-digital-file-license-question/103998)

> **Key Rules of the Standard Digital File License:** Personal Use Only: You may download, slice, and physically print the model strictly for your own personal use.
>
> — [MakerWorld & Creative Commons Licenses Explained](https://estimator.tryar.in/guide/licenses-explained)

而 Thunderstore 官方**全球规则**（已抓取 `https://wiki.thunderstore.io/moderation/global-rules.md`）在「Copyright and Licensing」一节规定：

> Copyright laws and code licensing must be followed where applicable.
> * Do not distribute game files such as Assembly-CSharp.dll, unless given explicit permission by the game's developers.
> * **Do not reupload packages or assets by other authors unless you have permission to redistribute them or are following their licensing.**

**这意味着：把 `zichaoxiong.3mf` 的派生几何（`.psmesh`）打包进 Thunderstore 发行包，很可能违反 `Standard Digital File License`**（该许可禁止再分发数字文件与衍生作品）。米菲兔的许可未知，风险不明。**这是发行前必须由用户决策的阻断项。**

### 5.6 README.md 里应该写的准确署名文本（建议稿，中文）

> 以下文本**只包含已核实的事实**；米菲兔部分如实标注「未能核实」。建议插入 README 的「已知说明」之前，作为独立一节。

```markdown
## 模型署名与许可

本模组的两个替换模型都来自第三方 3D 打印模型，经本项目二次加工（降面、修朝向、
对齐原版轮廓、烘焙 AO、生成描边壳）后使用，**不是本项目原创**。

### 自嘲熊（Zichao Xiong）
- 模型原名：**坐姿自嘲熊（多色一体）**
- 来源：<https://makerworld.com.cn/zh/models/2666015-zuo-zi-zi-chao-xiong-duo-se-yi-ti>
- 作者：**夜夜椰子冰**（MakerWorld UID `2431656860`，依据 3MF 内嵌的
  `Designer` / `ProfileUserName` 字段）
- 许可：**Standard Digital File License**
- 说明：该模型在 MakerWorld 国际站另有一份同名上传
  （<https://makerworld.com/en/models/3154227>），其页面显示的作者为 **Lorensi**
  （UID `495168789`）。两者标题、封面图、创建日期与许可完全一致，属同一模型的
  不同上传；本项目无法确认哪一份是最初发布者，故此处同时列出。

### 米菲兔（Miffy）
- 模型来源：<https://makerworld.com.cn/zh/models/2032846-miffy-mi-fei-tu-jing-dian-yi-zhu-bai-jian-zhi-chi>
- 作者：**未能核实**。所提供的 3MF 中作者名与许可字段均为空，只保留了上传者
  UID `2755976439`；该 MakerWorld 页面拒绝自动化访问。
- 许可：**未知**（同上，需从页面人工确认）

### 关于再分发的说明
- 上述模型的著作权归原作者所有。本项目**非商业**、无任何盈利行为。
- **自嘲熊采用 `Standard Digital File License`**，该许可禁止分享、再许可、出售、
  出租、托管、转让或**以任何数字/物理形式分发**该数字文件、其 3D 打印成品或任何
  衍生作品（含 remix）。
- 因此，**本模组不主张对这些模型几何的任何权利**。若原作者或权利人不希望其模型
  以本模组的形式被分发，请联系我们，我们将在下一个版本中**立即移除**对应模型：
  届时 `Plushie` 选项只保留 `Vanilla`，或改为**由用户自行下载原始 3MF 并本地生成**
  （`pwsh -File build.ps1 -RebuildAssets`），发行包中不再包含任何第三方几何。
- 若您是原作者并希望调整署名方式或授权条款，欢迎联系我们。
```

### 5.7 与之配套的 README 第 185 行修改

第 185 行「**不含任何第三方素材**」必须删除或改写，否则与上述署名节**直接矛盾**：

- **Before**：`- 模型由 3MF 源文件二次加工生成，不含任何第三方素材`
- **After**：`- 模型由第三方 3MF 源文件二次加工生成，著作权归原作者，详见上文「模型署名与许可」`

---

## 六、README 需要改的句子清单（精确 before / after）

文件：`D:\zhuanban\Plushie Swap\README.md`（188 行，UTF-8）

| # | 行号 | 严重度 | Before | After |
| --- | --- | --- | --- | --- |
| 1 | 7 | **高** | `- **三种形态自由切换**：原版 / 米菲兔 / 自嘲熊，默认 **米菲兔**` | `- **三种形态自由切换**：原版 / 米菲兔 / 自嘲熊，默认 **自嘲熊**（`ZichaoXiong`）` |
| 2 | 75 | 中 | `\| **② 干净明亮的色块** \| 亮度 > 0.75 的颜色向奶油白 \`#FFFAF2\` 提纯，避免灰扑扑的米色 \|` | `\| **② 干净明亮的色块** \| 亮度 > 0.55 的颜色向奶油白 \`#FFFAF2\` 提纯（越亮提纯越多），避免灰扑扑的米色 \|` |
| 3 | 76 | 中 | `\| **③ 简洁柔和的明暗** \| 点云 AO，只取上半球遮挡量，并做 4 次拉普拉斯平滑 + 幂次曲线，保留接触阴影但不糊 \|` | `\| **③ 简洁柔和的明暗** \| 点云 AO，只取上半球遮挡量，并做 3 次拉普拉斯平滑 + 幂次曲线，保留接触阴影但不糊 \|` |
| 4 | 80 | 中 | `所以整个模型（含描边）只需要两个材质、三次绘制。` | `所以整个模型（含描边）只需要两个材质、两次绘制（本体一次、描边一次）。` |
| 5 | 62 | 中 | `在游戏内的模组设置里改动会**即时生效**；直接编辑配置文件不会被热重载——需要**重启游戏**才会读到新值。` | `在游戏内的模组设置里改动会**即时生效**（唯一的例外是 `Shader Override`：材质按变体缓存，改它需要**重启游戏**）；直接编辑配置文件不会被热重载——需要**重启游戏**才会读到新值。` |
| 6 | 185 | **高** | `- 模型由 3MF 源文件二次加工生成，不含任何第三方素材` | `- 模型由第三方 3MF 源文件二次加工生成，著作权归原作者，详见上文「模型署名与许可」` |
| 7 | 29 | 低（建议） | `**只需要这一个文件**——模型、阴影贴图和图标都已压缩内嵌在 DLL 里（约 11.5 MB）。` | `**只需要这一个文件**——模型、阴影贴图和图标都已压缩内嵌在 DLL 里（12,133,376 字节，约 11.6 MiB）。` |
| 8 | 121-122 | 低（建议） | `\| 米菲兔 \| 22% \| 腰部，正好在她张开的手臂下方 \|`<br>`\| 自嘲熊 \| 26% \| 身体中部，避开占了身高一半以上的头 \|` | 建议在表下补注：`> 表中的百分比是生成时指定的"握持板层中心高度"；由于握点取该薄板内最外侧的真实顶点，实测手的高度是米菲约 18.8%、自嘲熊约 27.0%。` |
| 9 | 129 | 低（建议） | `> 已知局限：原版锚点 X 间距是 \`0.5990\`，比这两个玩偶都宽（米菲握点间距仅 \`0.3860\`），` | `> 已知局限：原版锚点 X 间距是 \`0.5990\`。米菲的握点间距只有 \`0.3860\`，两手会明显停在身体两侧；自嘲熊的握点间距是 \`0.5950\`，与原版锚点只差 \`0.0040\`，几乎贴合。` |
| 10 | 新增 | **高** | （无） | 在「已知说明」之前插入 `## 模型署名与许可` 一节（内容见 5.6） |

**无需修改**的 README 断言（已逐条核验通过）：第 3、12、14-18、33-43、47、51-60、65-66、74、77、84-92、100-106、110-115、124-127、133-136、142-162、174-179、183-184、186-187 行。

---

## 七、给 Lead 的行动清单（按优先级）

1. **[阻断发行]** 决定自嘲熊的许可处置：`Standard Digital File License` 很可能禁止再分发其衍生几何。建议先向作者 `夜夜椰子冰`（或 `Lorensi`）取得再分发许可；否则把发行包改为**不含模型几何**、由用户本地 `build.ps1 -RebuildAssets` 生成。
2. **[必做]** 人工确认米菲兔的作者名与 License：浏览器打开 `.cn/2032846` 页面读取。本审计**无法**核实，未编造。
3. **[必做]** 修 README 第 7 行的默认形态（写成 `米菲兔` 与代码和表格都矛盾）。
4. **[必做]** 改写 README 第 185 行「不含任何第三方素材」并新增「模型署名与许可」节。
5. **[必做]** 重跑发行：`pwsh -File build.ps1` → `python tools\package_release.py`，让 `release/` 追上 `dist/`（当前 DLL 哈希不一致）。
6. **[建议]** 修复 `tools/build_icon_release.py` 对 `D:\备份\zichao.jpg` 的硬编码（该文件已丢失，`release/icon.png` 目前不可重现）。
7. **[建议]** 修 README 的 4 处过时描述（阈值 0.75→0.55、AO 4→3 次、三次→两次绘制、`Shader Override` 例外）。
8. **[建议]** 清理仓库：`research/preview/*.png`（42 个，且与 `.gitignore:18` 矛盾）、7 个无引用 shader 转储 txt、15 个 Blender 探索脚本、`*2.py` 后继版本；`models/*.3mf` 上 Git LFS。
9. **[建议]** 补 `shaders/PlushieOutline.shader` 的状态横幅；修 `research/OUTLINE_DESIGN.md:23` 指向已删除 `REWRITE.md` 的悬空引用。
10. **[建议]** 给 `package_release.py` 加一道断言：比对 `dist` DLL 的 SHA-256 与 `buildinfo.txt`，不一致即中止（当前只检查文件存在，这是本次过期未被拦住的根因）。

---

## 附录 A：本次审计执行的实测命令（可复现）

```powershell
# 基线
git -C "D:\zhuanban\Plushie Swap" log -1 --format="%H %ad %s" --date=iso
git -C "D:\zhuanban\Plushie Swap" ls-files | Measure-Object          # 215
git -C "D:\zhuanban\Plushie Swap" status --short                      # 干净

# DLL 大小与哈希
(Get-Item "D:\zhuanban\Plushie Swap\dist\PlushieSwap\PlushieSwap.dll").Length   # 12133376
Get-FileHash "D:\zhuanban\Plushie Swap\dist\PlushieSwap\PlushieSwap.dll" -Algorithm SHA256
Get-FileHash "D:\zhuanban\Plushie Swap\release\stage\plugins\PlushieSwap\PlushieSwap.dll" -Algorithm SHA256

# 配置默认值
Select-String -Path "D:\zhuanban\Plushie Swap\src\Plugin.cs" -Pattern 'Config\.Bind\('
Select-String -Path "D:\zhuanban\Plushie Swap\src\Plugin.cs" -Pattern "SettingChanged \+="

# 数值常量
Select-String -Path "D:\zhuanban\Plushie Swap\tools\build_meshes.py" -Pattern "VANILLA_|CREAM_WHITE|smooth_ao_over_surface|smooth_scalar_over_surface"

# .psmesh 二进制实测（自写只读解析器，见报告正文输出）
python -c "<解析 assets/*.psmesh：子网格、顶点数、包围盒、握点、墨线宽度>"

# 图标 / 调色板
python -c "<Pillow: assets/icons/*.png, assets/*_shading.png, release/icon.png 的 size/mode/alpha 直方图>"

# 构建可复现性 + 朝向角度（输出到 %TEMP%，未触碰仓库）
python -c "<import build_meshes; convert() 到临时目录>"
#   -> [Miffy] facing correction: +181.2 deg
#   -> [ZichaoXiong] facing correction: +224.7 deg
#   -> 重建 .psmesh 与提交版 SHA-256 逐字节相同

# manifest / zip
python -c "<json + zipfile: manifest 字段校验、zip vs stage 逐字节比对、icon 尺寸>"

# 3MF 内部元数据（字节级解码）
python -c "<zipfile 读 3D/3dmodel.model，正则抓 <metadata>，按 utf-8 解码原始字节>"

# 引用搜索
Get-ChildItem -Recurse -File "D:\zhuanban\Plushie Swap" | Select-String -Pattern "OUTLINE_DESIGN|PlushieOutline\.shader|PlushieShaderLoader"

# .gitignore 矛盾
git -C "D:\zhuanban\Plushie Swap" check-ignore -v --no-index -- research/preview/final_miffy.png
git -C "D:\zhuanban\Plushie Swap" status --ignored --short
```

```powershell
# MakerWorld（.cn 全部 403；.com API 可用）
Invoke-WebRequest "https://makerworld.com/api/v1/design-service/design/3154227" -Headers @{ "User-Agent"="Mozilla/5.0 ..." }
Invoke-WebRequest "https://makerworld.com/api/v1/design-service/design/3154227/instances" -Headers @{ "User-Agent"="Mozilla/5.0 ..." }
Invoke-WebRequest "https://makerworld.pro/api/search?q=miffy" -Headers @{ "User-Agent"="Mozilla/5.0 ..." }

# Thunderstore 官方规范（GitBook 纯文本端点）
Invoke-WebRequest "https://wiki.thunderstore.io/mods/creating-a-package.md"
Invoke-WebRequest "https://wiki.thunderstore.io/moderation/global-rules.md"
```

## 附录 B：本次审计**未能**核实的事项（如实标注）

1. **米菲兔的作者名与许可条款** —— `.cn/2032846` 页面 403，3MF 内 `Designer`/`License` 为空。只掌握上传者 UID `2755976439`。**未编造。**
2. **自嘲熊的"最初发布者"** —— 3MF 内嵌 `夜夜椰子冰`(2431656860) 与国际站 `Lorensi`(495168789) 不一致，无法判定哪一个是原始作者。
3. **README 第 62 行「直接编辑配置文件不会被热重载」** —— 取决于 BepInEx 5 `ConfigFile` 是否 watch 磁盘变更，需实机运行验证，本审计不判定。
4. **原版锚点间距 `0.5990` / `0.6034` 的原始测量** —— 仅在本仓库研究脚本中找到（`research/solve_edges.py:88`、`research/diagnose_shell.py:11`），未独立复测游戏 prefab（属 task-4 范围）。
5. **`release/icon.png` 的画面内容是否仍符合预期** —— 因源图 `D:\备份\zichao.jpg` 丢失，无法重建比对，只核验了尺寸/格式/alpha。
