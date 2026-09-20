# 审计 A2：PlushieOutline.cs + PsMeshReader.cs 深度审计

- 审计员：`audit-outline`（task-8）
- 项目：`D:\zhuanban\Plushie Swap`
- 范围：`src/PlushieOutline.cs`（339 行）、`src/PsMeshReader.cs`（272 行）
- 性质：**只读审计**，未修改 `src/` 下任何文件
- 实测脚本目录：`C:\Users\Administrator\AppData\Local\Temp\opencode\`
- 报告：`research/audit/runtime-outline.md`（本文件为本次唯一写入的文件）

## 目录

- [第 0 节 实测环境与复现命令](#第-0-节-实测环境与复现命令)
- [第 1 节 PlushieOutline.cs 发现](#第-1-节-plushieoutlinecs-发现)
- [第 2 节 PsMeshReader.cs 发现](#第-2-节-psmeshreadercs-发现)
- [第 3 节 .psmesh 实测解析结果](#第-3-节-psmesh-实测解析结果)
- [第 4 节 读写对称性交叉验证](#第-4-节-读写对称性交叉验证)
- [第 5 节 截断 / 损坏文件健壮性模拟](#第-5-节-截断--损坏文件健壮性模拟)
- [第 6 节 已验证正确的设计（非问题项）](#第-6-节-已验证正确的设计非问题项)
- [第 7 节 结论摘要](#第-7-节-结论摘要)

---

## 第 0 节 实测环境与复现命令

| 项 | 值 |
|---|---|
| Python | `C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe`（3.14.3，numpy 2.4.4，scipy 可用） |
| C# 编译器 | `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`（net472，与 `PlushieSwap.csproj` 的 TargetFramework 一致） |
| 游戏 Unity 版本 | `6000.3.15`（`UnityPlayer.dll` FileVersion = `6000.3.15.12692100`） |
| 反编译源码 | `D:\zhuanban\youhua\decompiled-latest\Assembly-CSharp\`（24578 个 .cs） |
| 被审文件长度 | `miffy.psmesh` = 2276190 B，`zichaoxiong.psmesh` = 2401250 B |

全部复现命令（脚本均位于预授权临时目录，未写入项目目录）：

```powershell
$py="C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"
$T="C:\Users\Administrator\AppData\Local\Temp\opencode"
$A="D:\zhuanban\Plushie Swap\assets"
& $py "$T\parse_psmesh.py"    "$A\miffy.psmesh" "$A\zichaoxiong.psmesh"   # 字段逐项解析
& $py "$T\verify_outline.py"  "$A\miffy.psmesh" "$A\zichaoxiong.psmesh"   # 恢复误差/宽度分布/溢出
& $py "$T\symmetry.py"        "$A\miffy.psmesh" "$A\zichaoxiong.psmesh"   # 读写逐字节对称性
& $py "$T\truncate_sim.py"    "$A\miffy.psmesh" "$A\zichaoxiong.psmesh"   # 截断分支模拟
& $py "$T\demos.py"                                                        # 正交/溢出/可选块歧义
& $py "$T\recovery_test.py"   "$A\miffy.psmesh" "$A\zichaoxiong.psmesh"   # 恢复声明判定性测试
& $py "$T\run_artifact.py"                                                 # 复跑被引用的验证产物
& $py "$T\rootcause.py"       "$A\miffy.psmesh" "$A\zichaoxiong.psmesh"   # 残差根因/冗余色块
& $py "$T\bounds_pad.py"      "$A\miffy.psmesh" "$A\zichaoxiong.psmesh"   # bounds pad 充分性
& $py "$T\verify_math.py"                                                  # 屏幕空间数学数值验证
& "$T\cs\Probe3.exe"                                                       # BinaryReader 语义实测
```

---

## 第 1 节 PlushieOutline.cs 发现

### M1（中）「恢复是精确的 / 实测 mean 和 max 误差 0.00000」与实测不符，且所引用的验证产物已失效

- **文件:行号**：`src/PlushieOutline.cs:92-95`（注释断言）、`src/PlushieOutline.cs:107`（实际公式）
- **现象**：
  注释断言：

  > Recover the true body surface by subtracting exactly the push that was baked in. … lands back on the body to float precision (**verified: mean and max error 0.00000 on both models**).

  实测（float32，与 C# 运行路径完全一致）：

  | 模型 | 残差 mean | 残差 max | 残差上界 `thickness/510` |
  |---|---|---|---|
  | miffy | 8.412e-07 | **1.389e-05** | 1.4169e-05 |
  | zichaoxiong | 6.173e-07 | **1.374e-05** | 1.4169e-05 |

  用 `F6` 格式化，`1.389e-05` 输出为 `0.000014`，**不是** `0.000000`。
- **根因**：宽度表以 **uint8 量化**写入（`tools/build_meshes.py:332` `np.round(weights*255)`），运行时再除以 255（`PsMeshReader.cs:206`）。写入端用的是 `float64` 原始宽度，运行时用的是量化后的宽度，两者最多相差 `1/510`，乘以 `bakedThickness` 即为残差上界 `0.00722625/510 = 1.4169e-05`。实测残差确实只出现在 **0<w<255 的部分着墨顶点**上，`w==0` 的顶点残差恒为 `0.000000000`（与量化模型完全吻合），证明根因就是 8 位量化，而不是矩阵/浮点问题。
- **证据**：

  ```text
  $ & $py "$T\rootcause.py" "$A\miffy.psmesh"
  --- recovery residual ---
  max residual          = 1.388788e-05
  thickness/510 bound   = 1.416912e-05
  max <= thickness/510?  True
  vertices: zero-width=4993 partial-width=1954 full-width=8578
    max residual, w==0   = 0.000000e+00
    max residual, 0<w<255= 1.388788e-05   mean=5.775422e-06
  ```

  更关键的是：**注释所引用的验证产物本身已经失效**。`research/check_outline_undo.py`（其输出 `research/outline_undo_check.txt` 记录 `mean 0.000000 … max 0.000000 / => undo is EXACT`）现在原样重跑得到：

  ```text
  $ & $py "$T\run_artifact.py"
  ==== miffy ====
    shell - normal*BAKED -> body  : mean 0.002198 p95 0.007226 max 0.007226
    => undo is NOT exact
  ==== zichaoxiong ====
    shell - normal*BAKED -> body  : mean 0.004670 p95 0.007226 max 0.007226
    => undo is NOT exact
  ```

  即该产物记录的 `0.000000` 与当前资产**不可复现**（它是用统一厚度 `BAKED` 而非逐顶点宽度、并配合最近邻查询得到的旧结论；脚本本身也与资产脱节）。
- **严重度**：**中**（对画面影响可忽略：1.4e-05 模型单位 ≈ 1 m 模型上的 0.014 mm；但这是设计文档/注释层的错误断言，且其"证据链"已失效，后续维护者会据此误判）。
- **建议修法**（只描述）：
  1. 把 `PlushieOutline.cs:92-95` 的注释改为"恢复误差被宽度表的 8 位量化限制在 `bakedThickness/510`（实测 max 1.39e-05 / 1.37e-05），`w==0` 的顶点为精确 0"。
  2. 在 `research/` 中标注 `check_outline_undo.py` 与 `outline_undo_check.txt` 已过期，或重写该脚本使其使用**逐顶点宽度 + `source[]` 索引**（本报告第 4 节的 `recovery_test.py` 变体 B/C 即为正确度量），否则该文件会持续误导。
  3. 如确实需要"精确"，可把宽度表从 uint8 改为 `float32`（每顶点 +3 字节，miffy 约 +46 KB / 2.2 MB ≈ 2%），但收益仅为 0.014 mm，**不建议**为它改动格式。

---

### M2（中，潜在）正交相机分支的 `perPixel` 量纲错误，偏差 2.7×~90×

- **文件:行号**：`src/PlushieOutline.cs:218-224`（注释 + 代码）
- **现象**：代码为

  ```csharp
  perPixel = 1f / Mathf.Max(1e-4f, camera.orthographicSize * 2f);
  ```

  注释声称"an orthographic camera has no perspective, so a pixel is simply `1/(2*size)` across at any depth"。这个式子是 **每 NDC 单位对应的世界长度**，不是**每像素**对应的世界长度——它缺少 `/ screenHeight`。
- **根因**：正交相机的视口高度为 `2*orthographicSize` 世界单位，映射到 `Screen.height` 个像素，故

  ```
  正确值 = 2 * orthographicSize / screenHeight
  ```

  代码值 = `1/(2*size)`。两者之比 `code/correct = screenHeight / (4*size²)`。
- **证据**：

  ```text
  $ & $py "$T\demos.py"     # 第 A 节
  A. ORTHOGRAPHIC perPixel  (PlushieOutline.cs:224)
  correct world-units-per-pixel = 2*orthographicSize / screenHeight
    size=  2.0 h=  1080 | code 1/(2*size)=0.250000 | correct 2*size/h=0.003704 | ratio code/correct=67.50x
    size=  5.0 h=  1080 | code 1/(2*size)=0.100000 | correct 2*size/h=0.009259 | ratio code/correct=10.80x
    size= 10.0 h=  1080 | code 1/(2*size)=0.050000 | correct 2*size/h=0.018519 | ratio code/correct=2.70x
  ```

  把该值代入整条链并真实投影，实测线宽（请求 5 px）：

  ```text
  $ & $py "$T\verify_math.py"   # 第 3 节
    size     H        code_scale   correct_scale measured_px
    2.0      1080     0.250000     0.003704     337.5000    (want 5.0)
    5.0      1080     0.100000     0.009259     54.0000     (want 5.0)
    10.0     1080     0.050000     0.018519     13.5000     (want 5.0)
  ```

  即正交下线宽会**又随分辨率又随 size 变化**，且比请求值粗 2.7~90 倍。
- **严重度**：**中（潜在）**。当前**不可触发**：游戏主相机 `MainCamera.cam` 为透视（`Assembly-CSharp\MainCamera.cs:13,37` 使用 `fieldOfView`；全工程仅 `MirrorReflection.cs:109-112` 与 `MirrorCameraScript.cs:100-101` 复制 `orthographic/orthographicSize`，而它们创建的反射相机 `reflectionCamera.enabled = false`，且 `ResolveCamera()` 会因 `isActiveAndEnabled == false` 跳过它们）。所以这是"一旦游戏启用正交相机（或其它模组引入）就立刻显形"的潜伏缺陷。
- **建议修法**（只描述）：把正交分支改为与透视分支同一量纲：

  ```
  perPixel = (2f * camera.orthographicSize) / screenHeight;
  ```

  并修正 218-220 的注释（`1/(2*size)` 是每 NDC 单位的世界长度，不是每像素）。

---

### L1（低）`bounds.Expand(0.05f)` 的固定模型空间 pad 在远距离 / 大 World Scale 下不足

- **文件:行号**：`src/PlushieOutline.cs:122-128`
- **现象**：Attach 时把 bounds 每侧扩大 `0.05` 模型单位。但每帧顶点的实际位移是

  ```
  模型空间位移 = perPixel * widthPx * ink * depth / worldScale
  ```

  其中 `perPixel = 2*tan(fov/2)/screenHeight`。pad 是**常数**，位移随**深度线性增长**、随 **World Scale 反比增长**。超过阈值后，实际绘制的顶点会落到 renderer 的 bounds 之外。
- **根因**：用固定常数去包一个随 `depth` 与 `worldScale` 变化的量。`Bounds.Expand(amount)` 是把**每侧**各扩 `amount`（Unity 文档：[Bounds.Expand](https://docs.unity3d.com/6000.5/Documentation/ScriptReference/Bounds.Expand.html)：*"Expanding the bounds symmetrically by extending each side by the given amount, resulting in a total size increase of (amount × 2) per axis"*），所以可用位移就是 0.05。
- **证据**：

  ```text
  $ & $py "$T\bounds_pad.py"
  fov=60  H=1080  perPixel=0.001069167
  scale    width    max_depth_ok   needed@10m     ok@10m
  0.3      5.0      2.81           0.1782         NO
  0.3      12.0     1.17           0.4277         NO
  1.0      5.0      9.35           0.0535         NO
  1.0      12.0     3.90           0.1283         NO
  3.0      12.0     11.69          0.0428         yes

  reachable worst case (World Scale 0.3 + Outline Width 12, both config-legal):
    needed pad at 3 m = 0.1283 model units  (pad is 0.05) -> INSUFFICIENT
  default settings (scale 1.0, width 5):
    needed pad at 3 m = 0.0160 -> sufficient
    needed pad at 10 m = 0.0535 -> INSUFFICIENT
  ```

  默认配置（`World Scale 1.0`、`Outline Width 5`）在 **约 9.35 m** 之外 pad 失效；配置合法的极端组合（`World Scale 0.3` + `Outline Width 12`，见 `Plugin.cs:187` 范围 `0.3..3.0` 与 `Plugin.cs:222` 范围 `0..12`）在 **1.17 m** 外即失效。
- **严重度**：**低**。Unity 的视锥剔除是"整个 renderer 的 bounds 与视锥完全不相交才剔除"，因此表现是"在屏幕边缘时描边比本体**略早**消失"，而不是正常距离下消失。对远景的掉落物才有可感知风险。
- **建议修法**（只描述）：把 pad 从常数改为按最坏情况推导，例如

  ```
  pad = perPixel * widthPixels / worldScale * kMaxExpectedDepth
  ```

  或在 `LateUpdate` 里按当前相机 FOV 与 `lossyScale` 动态更新 `mesh.bounds`（用与几何无关的固定膨胀即可，因为真正的 bounds 只需覆盖位移上界）。另一个更省的做法是把 outline renderer 的 `bounds` 直接设为包围整个角色的固定大盒。

---

### L2（低）`MarkDynamic()` 在顶点/索引数据已上传之后才调用，按 Unity 文档可能不生效

- **文件:行号**：`src/PlushieOutline.cs:119-120`
- **现象**：`mesh.MarkDynamic()` 在 Attach 里调用，而该 mesh 是 `Object.Instantiate(缓存的 outline mesh)` 得到的（`PlushieModel.cs:1022`），其顶点与索引在 `BuildMesh`（`PlushieModel.cs:315-319`）里早已赋值。
- **根因**：Unity 文档明确要求尽早调用。原文（[Mesh.MarkDynamic](https://docs.unity3d.com/ScriptReference/Mesh.MarkDynamic.html)）：

  > It is most effective to call `MarkDynamic` **before** you upload vertex or index data to the Mesh for the first time, or before it is first rendered. … If called after buffers already exist, the effect will apply **the next time the buffers are recreated**.

  本工程只在 `Attach` 里调用一次，此时缓冲区已存在；因此这个"动态缓冲"提示可能要到 GPU 缓冲被重建时才生效，而每帧 `mesh.vertices = _buffer`（第 295 行）正是最需要它的场景。
- **证据**：代码路径 `PlushieModel.cs:1022` `Instantiate(outline)` → `1026` `outlineFilter.sharedMesh = outlineMesh` → `1038` `PlushieOutline.Attach(...)` → `PlushieOutline.cs:120` `mesh.MarkDynamic()`；`BuildMesh` 的 `mesh.vertices`/`SetTriangles` 在 `PlushieModel.cs:315-319`。Unity 文档见上（已抓取）。
- **严重度**：**低**（纯性能提示，不影响正确性；而且 Unity 在检测到每帧写入后通常也会自行走动态路径）。
- **建议修法**（只描述）：在 `BuildMesh` 里创建 outline mesh 后、赋顶点**之前**调用 `mesh.MarkDynamic()`（或在 `Instantiate` 之后立刻调用、再重新上传一次顶点）。

---

### L3（低）`ResolveCamera()` 的退避分支返回一个已知不可用的 `_camera`

- **文件:行号**：`src/PlushieOutline.cs:298-307`
- **现象**：

  ```csharp
  if (_camera != null && _camera.isActiveAndEnabled) return _camera;   // 300-303
  if (Time.unscaledTime < _nextCameraSearch) return _camera;            // 304-307
  ```

  能走到 304 行，说明 `_camera` **已经被判定为不可用**（null / 已销毁 / 未激活未启用）。此时 306 行却把它返回。调用方 `LateUpdate:199` 只检查 `camera == null`——对**存活但未启用**的相机该检查为 false，于是会用一台 `isActiveAndEnabled == false` 的相机去算矩阵。
- **根因**：退避分支的语义应是"暂时没有可用相机"，返回 `null` 才与 300-303 的判定一致；返回 `_camera` 把"不可用"重新当成"可用"。
- **证据**：代码本身即证据（300-303 的合取取反 → 304 分支内 `_camera` 必然不满足"非空且启用"）。注意对**已销毁**的相机，Unity 重载的 `==` 使 `camera == null` 为 true，所以销毁场景被调用方兜住了；**未启用**场景则漏过。重试间隔为 `1f`（308 行），所以场景切换后最多 1 s 描边不更新。
- **严重度**：**低**。
- **建议修法**（只描述）：304-307 改为 `return null;`；或把 300-303 的判定结果缓存为 `bool usable`，退避分支在 `!usable` 时返回 `null`。

---

### L4（低）`_renderer.isVisible` 早退导致"刚生成时"首帧沿用烘焙宽度（1 帧滞后，非硬跳过）

- **文件:行号**：`src/PlushieOutline.cs:191-196`
- **现象**：`Renderer.isVisible` 由渲染/剔除阶段写入，新建 renderer 在**第一次剔除之前为 false**。因此对象创建后的第一次 `LateUpdate` 会早退，`_mesh.vertices` 仍是 `Instantiate` 过来的**烘焙世界空间挤出**几何。
- **根因**：`isVisible` 的更新时机（渲染后）晚于 `LateUpdate`，且早退时不做任何"标记待刷新"。
- **证据**：`Attach`（`PlushieModel.cs:1038`）在 `Item.Start/OnEnable` 的补丁里同步创建对象并挂组件，同一帧稍后的 `LateUpdate` 就会看到 `isVisible == false`。此时的几何是 `BuildMesh` 从 `.psmesh` 读出的、按 `bakedThickness` 挤出的壳（实测 `bakedOutlineThickness = 0.007226250`，即约 7~10 px 的固定世界长度），所以首帧是"旧式固定宽度描边"，下一帧才切到屏幕空间宽度。
- **严重度**：**低**（1 帧；且不可见时早退本身是想要的省算行为）。**不会**导致描边整体不出现——因为烘焙几何一直在 mesh 里。
- **建议修法**（只描述）：在 `Attach` 里先同步跑一次挤出（或置一个 `_needsUpdate = true` 标志，让 `LateUpdate` 忽略 `isVisible` 至少更新一次）。若想彻底避免首帧跳变，可在 `Attach` 结束时直接调用一次与 `LateUpdate` 相同的计算。

---

### L5（低，潜伏）`ink <= 0` 分支写 `_surface[i]` 是正确的（已验证，非缺陷）

- **文件:行号**：`src/PlushieOutline.cs:244-251`
- **现象**：`ink <= 0` 时写 `_buffer[i] = _surface[i]`，即把壳顶点放回本体表面。
- **根因/验证**：写入端 `build_cartoon_outline`（`tools/build_meshes.py:626`）为 `offset = verts + normals * (thickness * scale)`，且 `write_psmesh` 对权重做了 `np.clip(..., 0, 1)`（`tools/build_meshes.py:331`），因此文件里**不存在负宽度**；实测两个模型的最小小非零宽度都是 `0.349020`（量化字节 89，恰为 `0.35*255` 取整），宽度为 0 的顶点数为 4993 / 12423。所以 `ink <= 0` 实际只处理 `ink == 0`。此时壳与本体表面重合，而 outline 材质为 `Cull Front`（`PlushieModel.cs:523-524`，`_Cull = CullMode.Front`），只画壳的背面 = 本体的背面深度，被本体自己的正面深度覆盖 → 不可见。**结论：该分支正确**。
- **证据**：

  ```text
  $ & $py "$T\verify_outline.py" "$A\miffy.psmesh"
  width: zero=4993 nonzero=10532  min_nonzero=0.349020 max=1.000000
  nonzero quantised bytes: min=89 max=255
  ```

- **严重度**：无（记录为已验证正确项）。

---

### L6（低）`SetWidthOnAll` 的 `FindObjectsOfType(..., true)` 开销可接受，但依赖 Unity 6 已弃用 API

- **文件:行号**：`src/PlushieOutline.cs:168-182`
- **现象**：`FindObjectsOfType<PlushieOutline>(true)` 会扫描**所有已加载场景中的全部对象**（含未激活）。
- **根因/评估**：该函数只在配置项变更时调用一次（`Plugin.cs:245` 订阅 `OutlineWidthEntry.SettingChanged` → `Plugin.cs:317`），**不是每帧**，所以开销（毫秒级、一次性）可接受。注释"`FindObjectsOfType` skips inactive objects … `true` includes them"准确。
- **证据**：`grep -n "SetWidthOnAll" src/` → 仅 `Plugin.cs:317` 一处调用点，位于 `OnOutlineWidthChanged` 内。Unity 6 已把该 API 改名为 `FindObjectsByType`（旧名标记 Obsolete），而 `PlushieSwap.csproj` 有 `<NoWarn>$(NoWarn);CS0436;CS0618</NoWarn>`，`CS0618` 正是弃用警告——所以弃用提示被静音，未来升级时不会被提醒。
- **严重度**：**低**（提示）。
- **建议修法**（只描述）：改用 `FindObjectsByType<PlushieOutline>(FindObjectsInactive.Include, FindObjectsSortMode.None)`；若保留旧 API，可在注释里说明为何保留。

---

### L7（低）每帧重写全部顶点无脏检查；`_buffer` 复用与 `mesh.vertices = _buffer` 的分配行为是正确/无额外托管分配的

- **文件:行号**：`src/PlushieOutline.cs:52`、`116`、`235-295`
- **现象**：
  - `_buffer` 在 `Attach` 中按 `count` **一次性分配**（116 行），每帧原地覆写全部 `count` 个元素（`ink<=0` 走 249 行、否则走 292 行，**没有分支会漏写**），因此不存在脏数据。**复用正确。**
  - `mesh.vertices = _buffer`（295 行）：`Mesh.vertices` 的 setter 会**拷贝**数组内容到原生内存（Unity 文档：[Mesh.vertices](https://docs.unity3d.com/ScriptReference/Mesh-vertices.html) *"Returns a copy of the vertex positions or assigns a new vertex positions array"*），所以 `_buffer` 保持有效、可继续复用；**不产生额外的托管分配**（分配只发生在 getter 上，而 getter 只在 `Attach` 里调用一次，见 76 行）。
  - 每帧代价 = 15525（miffy）/ 16831（zichaoxiong）次 `MultiplyPoint3x4` + `MultiplyVector` + 1 次 `Sqrt` + 若干除法，外加一次 186 KB 的托管→原生拷贝与 GPU 上传。若同屏 4 个毛绒 ≈ 6.2 万顶点/帧。
  - 无脏检查：相机矩阵/变换未变时仍全量重算。
- **根因**：设计上选择了"CPU 每帧做 GPU 顶点着色器的工作"（`PlushieOutline.cs:24-28` 说明没有 Unity 编辑器、无法编译自定义 shader）。
- **证据**：Unity 文档（已抓取）确认 setter 拷贝；代码 249/292 行覆盖全部分支；`count = _surface.Length`（233 行）在运行期恒定。
- **严重度**：**低**（性能提示；当前规模可接受）。
- **建议修法**（只描述，且**不触碰外推数学核心**）：加入脏检查——当 `modelToCamera`、`perPixel`、`_widthPixels` 与上一帧全部相同（含逐顶点 `ink` 未变）时直接跳过整个循环；或仅在相机或本对象变换发生变化时重算。若要多实例共享，可考虑把屏幕空间挤出做成真正的 shader（但项目当前无编辑器）。

---

## 第 2 节 PsMeshReader.cs 发现

### M3（中）`nameLength` 无上界检查 → 单个字段即可触发约 1.5 GB 瞬时分配 / OutOfMemoryException

- **文件:行号**：`src/PsMeshReader.cs:133-134`
- **现象**：`int nameLength = reader.ReadInt32();` 之后直接 `reader.ReadBytes(nameLength)`，**没有任何**与 `stream.Length` 的比较。
- **根因**：`BinaryReader.ReadBytes(n)` 在 .NET Framework 上**先按 `n` 分配数组、再读取**。我最初以为它会先 clamp，实测证明并非如此：即使流中只剩 10 字节，分配量仍与 `n` 成 **1.00×** 比例。

  ```text
  $ & "$T\cs\Probe3.exe"
  === Definitive: does BinaryReader.ReadBytes(n) allocate n bytes up front? ===
  (measuring GC.GetAllocatedBytesForCurrentThread)
    ReadBytes(    1000000) -> len= 10  allocated=      1000520 bytes  (ratio to count = 1.00x)
    ReadBytes(   10000000) -> len= 10  allocated=     10000464 bytes  (ratio to count = 1.00x)
    ReadBytes(  100000000) -> len= 10  allocated=    100000464 bytes  (ratio to count = 1.00x)
    ReadBytes( 1000000000) -> len= 10  allocated=   1000000464 bytes  (ratio to count = 1.00x)

  === The three unguarded ReadBytes calls in PsMeshReader.cs ===
  line 134: ReadBytes(nameLength)   -- nameLength is read raw from the file, NO bound check
    nameLength=         -5 -> ArgumentOutOfRangeException
    nameLength= 1500000000 -> returned 100 bytes, allocated 1500000640 bytes
    nameLength= 2147483647 -> OutOfMemoryException
  ```

  即：一个 4 字节字段（`nameLength = 1_500_000_000`）在只读到 100 字节的情况下，会先分配 **1.5 GB**；`nameLength = int.MaxValue` 直接抛 `OutOfMemoryException`。
- **严重度**：**中**（健壮性/内存安全）。缓解因素：`PlushieModel.TryParseAsset`（`PlushieModel.cs:198-209`）用 `catch (Exception)` 兜住并回退到内嵌资产，所以**不会崩游戏**；但 1.5 GB 的瞬时分配在 PEAK 这类已占用大量内存的 Unity 进程里可能引发连锁的分配失败或长时间 GC 停顿。文件来自玩家磁盘（本模组自己也鼓励用户替换资产），属于"损坏文件"而非纯恶意场景。
- **建议修法**（只描述）：
  1. 在 134 行前加界：`if (nameLength < 0 || nameLength > 4096) throw new InvalidDataException(...)`（模型名实际只有 5 / 11 字节，见第 3 节）。
  2. 更彻底的做法：给所有 `ReadBytes` 调用统一套一个"`count <= 剩余字节`"的前置检查（可写一个 `ReadExact(reader, stream, count)` 帮助函数）。

---

### L8（低）`outlineCount * 4`（201 行）的 int32 乘法理论上可溢出，但实测不可达

- **文件:行号**：`src/PsMeshReader.cs:198`（守卫）、`201`（`ReadBytes(outlineCount * 4)`）、`202`、`203`
- **现象**：198 行守卫用 `5L`（int64），**没有溢出问题**；但 201 行的 `outlineCount * 4` 是 **int32** 乘法，理论上可回绕为负或变小。
- **根因**：混合了 int64 守卫与 int32 实参。
- **证据**（C# 实测 + Python 交叉验证）：

  ```text
  === 6. line 198 arithmetic: Position + outlineCount * 5L ===
    oc=     15525  (long)oc*5 =         77625  int oc*5 =         77625  int-overflow=False
    oc= 536870911  (long)oc*5 =    2684354555  int oc*5 =   -1610612741  int-overflow=True

  === 7. line 201 arithmetic: ReadBytes(outlineCount * 4) [int32] ===
    oc= 536870911  exact*4 =    2147483644  int32*4 =    2147483644  overflow=False
    oc= 536870912  exact*4 =    2147483648  int32*4 =   -2147483648  overflow=True
    oc=2147483647  exact*4 =    8589934588  int32*4 =            -4  overflow=True
    reaching oc=536870912 needs stream.Length >= oc*5 = 2684354560 bytes
    byte[] max length on this runtime = 2147483591
  ```

  要让 201 行溢出，需 `outlineCount >= 536870912`，而 198 行守卫要求 `stream.Length >= Position + 5L*oc >= 2684354560`（2.5 GiB）。实测本运行时 `byte[]` 最大长度为 **2147483591**（< 2.68e9），因此 `Read(byte[], label)` 这条唯一被使用的入口**永远到不了**；只有 `Read(string path)`（FileStream）能到达，而全工程无人调用它（见 I5）。
- **严重度**：**低（不可达，纵深防御）**。
- **建议修法**（只描述）：把 201 行改为 `reader.ReadBytes(checked((int)(outlineCount * 4L)))`，或直接 `outlineCount * 4` → 用 int64 变量再转；顺带让 198 行的意图（int64）在 201 行保持一致。

---

### L9（低）可选块"靠剩余长度判断是否存在"存在真实歧义：旧文件（有握点、无旋转、wobble ≥ 32 字节）会被误解析

- **文件:行号**：`src/PsMeshReader.cs:172-178`（旋转"可选"）、`182-192`（wobble）、`194-209`（outline）
- **现象**：174 行只用"剩余 ≥ 32 字节"判断旋转块是否存在：

  ```csharp
  if (stream.Position + 32 <= stream.Length) { ...读两个 Quaternion... }
  ```

  这意味着"无旋转 + 后续 wobble 载荷 ≥ 32 字节"的文件会被**误判为有旋转**，从而把 32 字节 wobble 载荷当作旋转吃掉，之后所有字段整体错位。
- **根因**：旋转块**没有版本号/标志位**，只靠长度推断，与紧随其后的 legacy wobble 块在字节层面不可区分。
- **证据**（构造忠实的最小文件：有 grips、无 rotations、wobble 载荷 64 字节）：

  ```text
  $ & $py "$T\demos.py"     # 第 D 节
  D2 LEGACY (NO rotations, wobble payload=64 bytes):
      {'p': 113, 'L': 145, 'rots': True, 'wob': 286331153,
       'oc': 286331153, 'baked': 1.1443742118159064e-28, ...}
      expected: wobbleCount=64, baked=0.00722625
      got     : wobbleCount=286331153 baked=1.1443742118159064e-28
      -> MISREAD: 32 wobble bytes eaten as rotations
  D3 LEGACY (NO rotations, wobble payload=8 bytes):
      {'rots': False, 'wob': 8, 'oc': 0, 'baked': 0.007226250134408474}   # 正确
  ```

  注意 `bakedOutlineThickness` 被读成 `1.14e-28`——因为 `BakedOutlineThickness > 0f`（`PlushieModel.cs:1011`）会**通过**这个垃圾值检查（`1.14e-28 > 0` 为真），于是会尝试建立描边驱动，只是被 `Attach` 的 `normals.Length != verts.Length` 之类校验挡下（本场景下 0 个子网格，实际会被别的检查拦掉）。
- **严重度**：**低（潜伏）**。当前写入端在有 grips 时**总是**写旋转（`tools/build_meshes.py:300-305`），且 wobble 恒为 `None` → count 0（`build_meshes.py:318`），所以现行文件不会触发。风险来自"用旧版 `build_meshes.py` 生成、且 wobble 载荷 ≥ 32 字节"的文件被新运行时读取。
- **建议修法**（只描述）：在握点块后写一个显式能力标志（例如 `int32 hasRotations`），或把格式版本从 `PSMESH03` 升级并在读取时按版本分派；不要继续用"剩余长度"推断可选块。

---

### L10（低）截断/损坏时"跳过但不消费"会静默读出垃圾值，而不是抛异常

- **文件:行号**：`src/PsMeshReader.cs:166-180`（grips）、`188-191`（wobble）
- **现象**：当长度不足时，代码**跳过**该块但**不移动流位置**，于是下一个 `ReadInt32()` 从块的载荷里读，得到看似合法的垃圾值。
- **根因**：`if (... && stream.Position + N <= stream.Length)` 失败时没有 `throw`，也没有 seek 到流尾，函数继续往下走。
- **证据**：

  ```text
  $ & $py "$T\truncate_sim.py" "$A\miffy.psmesh" "$A\zichaoxiong.psmesh"
  CASE: CORRUPT: hasGrips=1 but only 10 bytes of the 24-byte grip block  (len=2198507)
      hasGrips=1
      !! hasGrips!=0 but only 10 bytes left -> grip block SKIPPED, stream NOT advanced
      wobbleCount=-1100617016
      outlineCount=-1089645710 ; pos=2198505 ; len=2198507
      final pos=2198505 / len=2198507 ; tail=2
     => RESULT: parsed WITHOUT exception

  CASE: CORRUPT: wobbleCount=8 but payload truncated (reader does NOT consume)
      wobbleCount=8
      !! wobbleCount>0 but only 0 bytes left -> payload SKIPPED, stream NOT advanced
      outlineCount ABSENT (line 194 guard false)
      bakedOutlineThickness ABSENT -> stays 0
     => RESULT: parsed WITHOUT exception
  ```

  即"截断的握点块"会让 `wobbleCount = -1100617016`、`outlineCount = -1089645710` 这类荒谬值被**静默接受**（负数被 `> 0` 守卫挡掉，所以最终不至于构造巨型数组，但 `HasGrips` 仍可能为 true 而 `GripLeft/GripRight` 保持 `(0,0,0)`）。
- **严重度**：**低**（仅损坏文件；上层 `TryParseAsset` 只在抛异常时才回退，而这里不抛，于是可能"成功"解析出一个半垃圾资产，例如 `HasGrips == false` 时 `HoldOffsetFor` 返回零偏移，握持位置悄悄退化）。值得记录，因为它**绕过了**"损坏→回退内嵌副本"的保护。
- **建议修法**（只描述）：在这些"长度不足"的分支里改为 `throw new InvalidDataException(...)`（或至少把 `HasGrips` 复位为 false 并 seek 到流尾），让 `TryParseAsset` 能按既有设计回退到内嵌资产。

---

### L11（低）负数/极大 count → OverflowException / OutOfMemoryException（被上层 catch，但可导致内存压力）

- **文件:行号**：`src/PsMeshReader.cs:136-137`（`subMeshCount`）、`147-154`（`vertexCount` / `indexCount`）、`203`（`outlineCount`）
- **现象**：这些 count 直接来自文件且无上界检查：

  ```csharp
  asset.SubMeshes = new SubMesh[subMeshCount];                  // 137
  sub.Positions = ReadVector3Array(reader, vertexCount);        // 150 → new Vector3[count]
  sub.Indices = ReadInt32Array(reader, indexCount);             // 154 → new int[count]
  asset.OutlineWidths = new float[outlineCount];                // 203
  ```

- **证据**（Python 镜像 + C# 实测）：

  ```text
  CASE: CORRUPT: subMeshCount = -1        => OverflowException: new SubMesh[-1]
  CASE: CORRUPT: subMeshCount = 2e9       => OutOfMemoryException: new SubMesh[2000000000]
  CASE: CORRUPT: sub0 vertexCount = -3    => OverflowException: new int[-3]
  CASE: CORRUPT: sub0 vertexCount = 3e8   => OutOfMemoryException: new int[300000000]

  $ & "$T\cs\Probe2.exe"
  === A. actual array types used by PsMeshReader ===
    OutOfMemoryException Vector3[300000000]
    OutOfMemoryException int[2000000000]
  ```

  这些异常都被 `PlushieModel.TryParseAsset`（`PlushieModel.cs:198-209`）的 `catch (Exception)` 捕获 → 记日志 → 返回 null → 保留原版毛绒。**因此不是崩溃**，但 203 行的 `outlineCount` 受 198 行守卫限制（`<= Length/5`），所以真正的 OOM 向量只有 `subMeshCount` 与 `vertexCount`/`indexCount`。
- **严重度**：**低**（有兜底；主要风险是巨大分配的瞬时内存压力）。
- **建议修法**（只描述）：在读取每个 count 后加"合理性上界"检查（例如 `subMeshCount <= 64`、`vertexCount <= 5_000_000`、`indexCount <= 30_000_000`），并且最稳妥的是**先按 count 反推所需字节数并与剩余长度比较**再分配。

---

### I1（提示）死数据：`GripLeftRotation` / `GripRightRotation` 从未被读取

- **文件:行号**：`src/PsMeshReader.cs:71-78`（声明）、`176-177`（赋值）
- **现象**：`grep` 全 `src/` 后，这两个字段**只有赋值、没有任何读取方**。`PlushieModel.HoldOffsetFor`（`PlushieModel.cs:1114-1126`）只用了 `asset.GripLeft` / `asset.GripRight` 求腰中点和 `asset.HasGrips`。
- **根因**：旋转本意是"给手部姿态"（注释 71-74 声称"The game copies this straight onto the hand rig, so it *is* the hand pose"），但实际握持方案改成了"移动模型去对齐锚点"（`PlushieModel.cs:1066-1070` 注释说明写锚点会让弹簧/IK/FixedJoint 打架），旋转因此失去用途。
- **证据**：

  ```text
  $ grep -n "GripLeftRotation|GripRightRotation" src/*.cs
  src/PsMeshReader.cs:75:  public Quaternion GripLeftRotation = Quaternion.identity;
  src/PsMeshReader.cs:78:  public Quaternion GripRightRotation = Quaternion.identity;
  src/PsMeshReader.cs:176:  asset.GripLeftRotation = ReadQuaternion(reader);
  src/PsMeshReader.cs:177:  asset.GripRightRotation = ReadQuaternion(reader);
  （无其它匹配）
  ```

- **严重度**：**提示**（死代码 + 为它保留的"可选块长度推断"正是 L9 歧义的来源）。
- **建议修法**（只描述）：要么删除这两个字段与 174-178 的读取（同时移除 L9 的歧义源），要么在注释里明确"已解析但当前不使用，保留以备将来写锚点姿态"。

---

### I2（提示）死数据：`SubMesh.Colour`（统一 RGBA）从未被读取

- **文件:行号**：`src/PsMeshReader.cs:42`（声明）、`143`（赋值）
- **现象**：`SubMesh.Colour` 只有赋值；消费方读的是 `sub.Colours`（逐顶点，`PsMeshReader.cs:153` / `PlushieModel.cs:302`）。唯一相关的 `asset.Bounds` 只用在诊断日志里（`PlushieModel.cs:189`）。
- **证据**：

  ```text
  $ grep -n "\.Colour\b|sub\.Colour" src/*.cs
  src/PsMeshReader.cs:42:   public Color Colour;
  src/PsMeshReader.cs:143:  Colour = new Color(reader.ReadSingle(), ...),
  （无其它读取点）
  ```

- **严重度**：**提示**。
- **建议修法**（只描述）：删除 `SubMesh.Colour` 字段，或把它作为 `Colours` 的单一来源（见 I3）。

---

### I3（提示）逐顶点颜色块与统一色**完全相同**，占文件 17.1% / 17.5%，可被统一色替代

- **文件:行号**：`src/PsMeshReader.cs:153`、`252-260`（读取 12 B/顶点）；写入端 `tools/build_meshes.py:295`
- **现象**：写入端用 `np.tile(colour[:3], (len(verts),1))` 把**同一个统一色**复制到每个顶点。实测两个模型**每个子网格的逐顶点颜色都与统一色逐位相同**（spread = 0.000e+00）。
- **证据**：

  ```text
  $ & $py "$T\rootcause.py" "$A\miffy.psmesh"
  --- redundant per-vertex colour block ---
    sub[0] vc=  1228 uniform=(0.0, 0.0, 0.0, 1.0) per-vertex-constant=True spread=0.000e+00
    sub[1] vc=  6862 uniform=(0.0, 0.337255, 0.721569, 1.0) per-vertex-constant=True spread=0.000e+00
    sub[2] vc=  8897 uniform=(1.0, 0.984, 0.951, 1.0) per-vertex-constant=True spread=0.000e+00
    sub[3] vc= 15525 uniform=(0.085, 0.085, 0.105, 1.0) per-vertex-constant=True spread=0.000e+00
    total per-vertex colour bytes = 390144 (381.0 KB) -- all identical to the uniform colour
    file size = 2276190 bytes -> 17.1% of the file
  （zichaoxiong: 419340 B / 409.5 KB -> 17.5%）
  ```

- **严重度**：**提示**（优化机会，不是缺陷）。
- **建议修法**（只描述）：如果愿意改格式（例如升到 `PSMESH04`），可以删掉逐顶点颜色块、只保留统一色，文件体积约降 17%；代价是要同时改 `PsMeshReader`、`build_meshes.py`、`preview_mesh.py`、`embed_assets.py` 与内嵌资产（`src/EmbeddedAssets.g.cs` 有 3 MB），**收益不足以抵消风险**，因此更现实的建议是**只在注释里记录这个冗余**，不要为它动格式。

---

### I4（提示）`Read(string path)` 是死 API

- **文件:行号**：`src/PsMeshReader.cs:100-106`
- **现象**：只有 `Read(byte[], label)` 被使用；`Read(path)` 无调用点。这与 L8 的"仅 `Read(path)` 可达 2.5 GB 溢出"结论相互印证。
- **证据**：

  ```text
  $ grep -n "PsMeshReader\.Read\(" src/*.cs
  src/PlushieModel.cs:203:  return PsMeshReader.Read(bytes, fileName);
  （唯一调用点，byte[] 重载）
  ```

- **严重度**：**提示**。
- **建议修法**（只描述）：删除 `Read(string path)`，或保留但标注为"测试/调试用"。

---

## 第 3 节 .psmesh 实测解析结果

`parse_psmesh.py` 完全按 `PsMeshReader.cs` 的规则（含各可选块的判断顺序）解析，输出：

### miffy.psmesh（2276190 B）

```text
magic            = b'PSMESH03'  match=True
nameLength       = 5
name             = 'Miffy'
subMeshCount     = 4
  sub[0] colour   = (0.0, 0.0, 0.0, 1.0)          flags=0  vc=1228   ic=6462
  sub[1] colour   = (0.0, 0.337255, 0.721569, 1.0) flags=0  vc=6862   ic=41130
  sub[2] colour   = (1.0, 0.984, 0.951, 1.0)      flags=0  vc=8897   ic=48384
  sub[3] colour   = (0.085, 0.085, 0.105, 1.0)    flags=1  vc=15525  ic=95976   <- outline
boundsMin        = (-0.36269, -0.7345, -0.156162)
boundsMax        = (0.29969, 0.238106, 0.257162)
bounds center    = (-0.0315, -0.248197, 0.0505)
bounds size      = (0.66238, 0.972606, 0.413324)
pos after bounds = 2198493  remaining=77697
hasGrips         = 1
gripLeft         = (-0.224528, -0.552055, 0.049485)
gripRight        = (0.1615, -0.551634, 0.048607)
gripLeftRotation = (-0.31818, 0.67636, 0.51899, -0.41466)
gripRightRotation= (0.25786, 0.71867, 0.55145, 0.33605)
wobbleCount      = 0
outlineCount     = 15525
  outlineCount*5L = 77625 ; remaining=77629 ; fits=True
  width min/max/mean = 0.000000 / 1.000000 / 0.656220
  width==0 count = 4993
bakedOutlineThickness = 0.007226250
--- consumed 2276190 / 2276190 ; TAIL REMAINING = 0 bytes ---
```

### zichaoxiong.psmesh（2401250 B）

```text
nameLength       = 11
name             = 'ZichaoXiong'
subMeshCount     = 4
  sub[0] colour   = (0.062745, 0.058824, 0.054902, 1.0)  flags=0  vc=7604   ic=41001
  sub[1] colour   = (0.976471, 0.364706, 0.45098, 1.0)   flags=0  vc=3455   ic=15588
  sub[2] colour   = (0.993174, 0.97412, 0.945722, 1.0)   flags=0  vc=7055   ic=40821
  sub[3] colour   = (0.085, 0.085, 0.105, 1.0)           flags=1  vc=16831  ic=97410
boundsMin        = (-0.447541, -0.7345, -0.335693)
boundsMax        = (0.384541, 0.239012, 0.436693)
bounds center    = (-0.0315, -0.247744, 0.0505)
bounds size      = (0.832082, 0.973512, 0.772386)
hasGrips         = 1
gripLeft         = (-0.329156, -0.471713, 0.047187)
gripRight        = (0.265857, -0.465402, 0.04354)
gripLeftRotation = (-0.31818, 0.67636, 0.51899, -0.41466)   <- 与 miffy 相同
gripRightRotation= (0.25786, 0.71867, 0.55145, 0.33605)     <- 与 miffy 相同
wobbleCount      = 0
outlineCount     = 16831
  outlineCount*5L = 84155 ; remaining=84159 ; fits=True
  width min/max/mean = 0.000000 / 1.000000 / 0.244000
  width==0 count = 12423
bakedOutlineThickness = 0.007226250
--- consumed 2401250 / 2401250 ; TAIL REMAINING = 0 bytes ---
```

**要点**：

1. 两个文件的**尾部剩余字节数都是 0** —— 布局被完整消费，没有多余/缺失字节。
2. 两个模型的 `gripLeftRotation` / `gripRightRotation` **完全相同**（`(-0.31818,0.67636,0.51899,-0.41466)` / `(0.25786,0.71867,0.55145,0.33605)`），进一步佐证 I1：这是同一份手部姿态常量，与具体模型无关，且当前无人读取。
3. `outlineCount == 描边子网格的 vertexCount`（15525 / 16831），与设计一致：`outline_map` 为每个壳顶点记录一条宽度。
4. `outlineCount * 5L` 与剩余字节的关系：`77625` vs 剩余 `77629`（= 77625 + 4，多出的 4 正是 `bakedOutlineThickness`），`84155` vs `84159`。守卫恰好通过，**没有溢出**（见 L8）。
5. `bakedOutlineThickness` 恰为 `0.0075 * 0.9635 = 0.00722625`（`tools/build_meshes.py:1336,1719` 与 `research/outline_undo_check.txt:1`），float32 精确可表示。
6. 宽度分布：miffy 4993/15525 顶点无墨（32.2%），zichaoxiong 12423/16831 无墨（73.8%）；这与 `PlushieOutline.cs:97-102` 注释引用的"4993 和 12423"**完全一致**（该处注释是准确的）。

---

## 第 4 节 读写对称性交叉验证

**方法（最强证据）**：用 C# 的规则解析两个 `.psmesh`，再用 `tools/build_meshes.py::write_psmesh()` 的字段顺序**重新编码**，与原始文件做逐字节比较。若完全一致，则读取端与写入端在字段顺序、类型宽度、偏移上完全对称。

```text
$ & $py "$T\symmetry.py" "$A\miffy.psmesh" "$A\zichaoxiong.psmesh"
==========================================================================
D:\zhuanban\Plushie Swap\assets\miffy.psmesh
  original 2276190 bytes ; re-encoded 2276190 bytes
  BYTE-IDENTICAL: True
  all index counts are multiples of 3: True
==========================================================================
D:\zhuanban\Plushie Swap\assets\zichaoxiong.psmesh
  original 2401250 bytes ; re-encoded 2401250 bytes
  BYTE-IDENTICAL: True
  all index counts are multiples of 3: True
```

**逐字段对照**（写入端 `build_meshes.py:282-338` ↔ 读取端 `PsMeshReader.cs:120-215`）：

| 字段 | 写入端 | 读取端 | 对称 |
|---|---|---|---|
| magic | `MAGIC = b"PSMESH03"`（:43） | `Magic` 8 字节（:35） | ✅ |
| nameLength+name | `pack("<i", len(raw))` + `raw`（:285-286） | `ReadInt32` + `ReadBytes`（:133-134） | ✅ |
| subMeshCount | `pack("<i", len(submeshes))`（:287） | `ReadInt32`（:136） | ✅ |
| colour | `pack("<4f", *colour)`（:289） | 4× `ReadSingle`（:143） | ✅ |
| flags | `pack("<i", int(flags))`（:290） | `ReadInt32`（:144） | ✅ |
| vertexCount, indexCount | `pack("<ii", len(verts), len(tris)*3)`（:291） | 2× `ReadInt32`（:147-148） | ✅ |
| positions | `verts.astype("<f4")`（:292） | `ReadVector3Array` 3f/顶点（:150） | ✅ |
| normals | `normals.astype("<f4")`（:293） | 3f/顶点（:151） | ✅ |
| uvs | `uvs.astype("<f4")`（:294） | `ReadVector2Array` 2f/顶点（:152） | ✅ |
| colours | `np.tile(colour[:3])`（:295） | `ReadColorArray` 3f/顶点（:153, :257） | ✅ |
| indices | `tris.astype("<i4")`（:296） | `ReadInt32Array`（:154） | ✅ |
| boundsMin/Max | 2× `pack("<3f")`（:297-298） | 2× `ReadVector3`（:159-160） | ✅ |
| hasGrips | `pack("<i", 1/0)`（:301,307） | `ReadInt32`（:165） | ✅ |
| grips left/right | 2× `pack("<3f")`（:302-303） | 2× `ReadVector3`（:168-169） | ✅ |
| rotations | 2× `pack("<4f")`（:304-305） | 2× `ReadQuaternion`（:176-177） | ✅ |
| wobbleCount | 恒写（:314/318） | `ReadInt32`（:187） | ✅ |
| outlineCount | `pack("<i", len(source))`（:322） | `ReadInt32`（:196） | ✅ |
| source[] | `asarray(source,"<i4")`（:323） | `ReadBytes(oc*4)`（:201） | ✅ |
| width[] | `round(w*255).astype(uint8)`（:332） | `ReadBytes(oc)` ÷ 255（:202,206） | ✅ |
| baked | `pack("<f")`（:338） | `ReadSingle`（:214） | ✅ |

**关于 `vertexCount` / `indexCount` 的一个已知非对称点**：写入端 `indexCount = len(tris)*3`，读取端把它当作**裸 int32 数量**读（不做 `%3` 校验）。实测两个文件的所有 `indexCount` 都是 3 的倍数，且 `BuildMesh`（`PlushieModel.cs:319`）用 `mesh.SetTriangles(indices, 0, true)`——若某个损坏文件的 `indexCount % 3 != 0`，`SetTriangles` 会因长度不是 3 的倍数而抛异常，被上层 `catch` 兜住。**记录为非问题项**（写入端保证、读取端有兜底）。

**另一个已验证的对称性细节**：`ReadColorArray` 只读 3 个 float 并硬编码 `alpha = 1f`（`PsMeshReader.cs:257`），与写入端只写 `colour[:3]` 对称（`:295`）。正确。

---

## 第 5 节 截断 / 损坏文件健壮性模拟

`truncate_sim.py` 逐行镜像 `PsMeshReader.Read(Stream,string)` 的分支结构，并模拟 `BinaryReader` 的真实语义（`ReadBytes(n)` 返回 `min(n, 剩余)` 而不抛；`ReadInt32/ReadSingle` 在不足 4 字节时抛 `EndOfStreamException`；`new T[负数]` → `OverflowException`）。这些语义我已用 C# 实测核对（`Probe.exe`）：

```text
=== 1. ReadBytes(-1) ===
  ArgumentOutOfRangeException
=== 3. ReadBytes(n) larger than remaining (small n) ===
  ReadBytes(1000) on 10 bytes -> length 10 (no exception)
=== 4. ReadInt32 with <4 bytes remaining ===
  EndOfStreamException
=== 5. new int[neg] / new T[huge] ===
  new int[neg]        -> OverflowException
```

### 结果表（miffy，outlineCount 字段位于偏移 2198557）

| 截断/损坏输入 | C# 结果 |
|---|---|
| 完整文件（对照） | 正常解析，tail = 0 |
| 截断于 `outlineCount` 之后 | 198 行守卫为 false → outline 块**跳过**（不消费），`bakedOutlineThickness` 保持 0 → **正常返回**（无描边） |
| 截断于 source[] 中（+30000） | 同上，守卫 false → 跳过 → **正常返回** |
| 截断于 source[] 之后、width[] 之前 | 同上 → **正常返回** |
| 截断于 width[] 中 | 同上 → **正常返回** |
| 截断于 width[] 之后、baked 之前 | outline 块**完整读出**（守卫 true），`bakedOutlineThickness` 缺失 → 保持 0 → **正常返回** |
| `outlineCount = 15526`（流止于 count） | 守卫 `Position + 5L*oc <= Length` 为 false → 跳过 → **正常返回** |
| `outlineCount = 455238`（完整文件） | 守卫 false（需 2276190 ≥ 2198561+2276190）→ 跳过 → **正常返回** |
| `subMeshCount = -1` | `OverflowException: new SubMesh[-1]` |
| `subMeshCount = 2e9` | `OutOfMemoryException` |
| `nameLength = -5` | `ArgumentOutOfRangeException` |
| `nameLength = 1.5e9` | 分配 1.5 GB 后 `EndOfStreamException`（见 M3） |
| `vertexCount = -3` | `OverflowException` |
| `vertexCount = 3e8` | `OutOfMemoryException` |
| `wobbleCount = 8` 但载荷被截断 | 载荷**跳过且不消费** → 后续字段读到垃圾（见 L10） |
| `hasGrips = 1` 但握点块只剩 10 字节 | 握点块**跳过且不消费** → `wobbleCount`/`outlineCount` 读到垃圾（见 L10） |

**哪些截断点会被"误判"**：

1. **`outlineCount` 守卫（198 行）本身是安全的**——我最初怀疑它写成 `outlineCount * 5L <= stream.Length`（漏掉 `stream.Position`），实测代码里**有** `stream.Position +`，所以该守卫正确。此处特别说明，以免后续审计重复误报。
2. 真正的"误判"在 **L10**：长度不足时"跳过但不消费"，于是后续字段被静默解析为垃圾值，函数**不抛异常**，从而绕过 `TryParseAsset` 的"损坏→回退内嵌资产"机制。
3. **L9** 的歧义是另一类误判：不是截断，而是"旧文件 + 长 wobble 块"被误读为"有旋转"。

---

## 第 6 节 已验证正确的设计（非问题项）

以下项目按任务清单逐条核查，**结论是正确**，记录以免后续重复排查：

### N1 屏幕空间外推数学核心是正确的（**不建议改动**）

任务约束要求：除非有实测证据证明 `surface + cameraToModel.MultiplyVector(offsetInCamera)` 错误，否则不得建议改动。我做了决定性数值验证，**它是对的**：

- **透视链完整验证**：对 `fov ∈ {40,60,70,90}` × `screenHeight ∈ {720,1080,1440}` × `aspect ∈ {1.0,1.778,2.333,3.556}` × `depth ∈ {0.5,1,3,10,40}` × 7 个法线方向，共 **1176 组**组合，实测像素位移与请求宽度 `W` 的误差 **全部为 0**（`|measured - W| > 1e-9` 的组合数 = **0**）。

  ```text
  $ & $py "$T\verify_math.py"    # 第 1 节
  fov=60 H=1080 aspect=1.77778 depth=3 n=(1.0,0.0) W=5 -> measured_px=5.000000000
  total combinations with |measured - W| > 1e-9 : 0
  -> the perspective chain is EXACT; (nx,ny) with no aspect term is correct.
  ```

- **矩阵推导正确**：`modelToCamera = camera.worldToCameraMatrix * transform.localToWorldMatrix`（215 行）是"模型→世界→相机"的正确复合；`cameraToModel = modelToCamera.inverse`（216 行）配合 `MultiplyVector`（292 行，只作用线性部分、忽略平移）把相机空间方向变回模型空间，再叠加到同样位于模型空间的 `_surface[i]` 上——量纲与空间都自洽。且由于 `localToWorldMatrix` 含物品缩放，`cameraToModel` 会按比例放大模型空间偏移，正好抵消缩放，使世界空间位移对应恒定像素数。**这是设计要的效果**。
- **`depth = -point.z` 与 `scale *= depth` 的符号正确**：Unity 相机空间为右手系、-z 朝前，故前方点 `point.z < 0` → `depth = -point.z > 0`。284-287 行对 `depth < 0`（相机后方）钳到 0，使 `scale = 0`，避免相机后方顶点被镜像挤出。正确。
- **透视 `perPixel` 公式正确**：`(2*tan(fov/2))/screenHeight`（229 行）与独立推导逐位相等（`verify_math.py` 第 2 节：6 组全部 `equal=True`）。

**唯一例外**是正交分支（M2）——它不在"屏幕空间外推核心"内，而是 `perPixel` 的取值分支，且我有数值证据证明它错。除此之外，**核心数学不应改动**。

### N2 法线不加 aspect 的**结论**正确（但注释的**理由**错误）

- **文件:行号**：`src/PlushieOutline.cs:253-261`
- 结论 `(dx, dy) = (nx, ny)` 归一化后**不加 aspect**：**正确**（见 N1 的 1176 组验证，其中 aspect 被刻意在 1.0~3.56 之间变化）。
- 但注释给出的理由——"adding one would **tilt** the offset away from the direction the normal actually points on screen and make the line lopsided"——**不成立**。实测：加 `*aspect` 会**保持方向、只放大长度**，不会倾斜：

  ```text
  $ & $py "$T\verify_math.py"    # 第 2 节
  n=(0.6,0.8) no aspect -> pixel delta=(  3.0000,  4.0000) length=5.000000
  n=(0.6,0.8) x*aspect  -> pixel delta=(  5.3333,  7.1111) length=8.888889
  ```

  `(5.3333, 7.1111)` 的方向仍是 `(0.6, 0.8)`，长度从 5.0 变成 8.889。所以"不加 aspect"的真正理由是**投影矩阵已经含 `1/aspect`，而像素在 x 方向本就比 y 方向窄同样的比例，两者相消**（即"结论对、理由需改写"）。
- **严重度**：**提示**（注释准确性）。
- **建议修法**（只描述）：把 255-261 行注释改为"URP 投影矩阵把 x 按 `1/aspect` 缩放，而屏幕像素在 x 方向也窄 `aspect` 倍，两者相消，故相机空间方向 `(nx, ny)` 在 x/y 上每单位对应相同的像素数"；删掉"tilt/lopsided"这一错误论证。

### N3 `_buffer` 复用与 `mesh.vertices = _buffer` 无额外托管分配

见 L7。`_buffer` 一次分配、每帧全量覆写、setter 拷贝语义保证其可复用。

### N4 `ReleaseMesh` 与 `OnDestroy` 双路径**不会**重复 Destroy、**不会**漏 Destroy

- **文件:行号**：`src/PlushieOutline.cs:144-166`、`src/PlushieModel.cs:1158-1168`
- `ReleaseMesh` 在 `Destroy(_mesh)` 后立即 `_mesh = null`（148-149 行），因此第二次调用因 `if (_mesh != null)` 为假而直接返回 → **不会重复 Destroy**。
- `PlushieModel` 先对子物体调用 `ReleaseMesh()`（1164 行），随后 `Destroy(existing.gameObject)`（1168 行）在帧末触发 `OnDestroy` → `ReleaseMesh()` 再次调用 → `_mesh` 已是 null → 空操作。**不会重复 Destroy**。
- 覆盖"游戏自己销毁物品"的路径：由 `OnDestroy`（163-166 行）兜住，**不会漏 Destroy**。
- `Attach` 的所有失败点都在 `AddComponent` **之前**（71-90 行），所以不存在"组件已挂但 `_mesh` 未赋值"的孤儿；而 `PlushieModel.cs:1042-1047` 在 `Attach` 返回 null 时显式 `Destroy(outlineMesh)` + `Destroy(outlineObject)`。**生命周期完整**。
- **严重度**：无（已验证正确）。

### N5 `MarkDynamic()` 的调用本身是恰当的（只是时机偏晚，见 L2）

对"每帧改顶点的网格"调用 `MarkDynamic` 正是文档推荐的用法；问题仅在调用时机。

### N6 `SetWidthOnAll` 的开销与语义正确（见 L6）

事件驱动、非每帧；`true` 参数确实包含未激活对象，与注释一致。

### N7 屏幕高度取 `Screen.height` 而非渲染目标高度是**有意为之且正确**

- **文件:行号**：`src/PlushieOutline.cs:204-212`
- 游戏支持渲染缩放：`Assembly-CSharp\RenderScaleSetting.cs:22` 设置 `universalRenderPipelineAsset.renderScale`。注释（204-207 行）解释：除以渲染目标高度会让线宽随缩放变大。核查游戏侧确实存在 `renderScale` 设置（`RenderScaleSetting.cs`），注释成立。取 `Screen.height` 并在 `screenHeight < 2f` 时早退（209-212 行）是稳健的。

### N8 `ink <= 0` 写 `_surface[i]` 正确（见 L5）

### N9 可选块的**读取顺序**与写入端一致

grips → wobble → outline → baked，与 `write_psmesh` 的写出顺序一致；且写入端注释（`build_meshes.py:309-311`）明确指出"wobbleCount 必须始终写出，否则后续字段整体偏移 4 字节"。我用最小文件实测验证了这个论断：

```text
$ & $py "$T\demos.py"    # 第 E 节
  wobbleCount written=True  -> reader baked=0.007226250134408474 (expected 0.00722625) OK
  wobbleCount written=False -> reader baked=None (expected 0.00722625) <<< GARBAGE
```

即写入端注释的因果解释**正确**（省掉 4 字节会让 `bakedOutlineThickness` 读成垃圾）。

---

## 第 7 节 结论摘要

### 严重度分布

| 严重度 | 数量 | 条目 |
|---|---|---|
| 严重 | 0 | — |
| 中 | 3 | M1 恢复公式注释与实测不符 + 引用产物失效；M2 正交 `perPixel` 量纲错误（潜在）；M3 `nameLength` 无上界 → 1.5 GB 分配/OOM |
| 低 | 8 | L1 bounds pad 不足；L2 `MarkDynamic` 时机；L3 `ResolveCamera` 退避返回不可用相机；L4 `isVisible` 首帧沿用烘焙宽度；L5 `ink<=0` 路径（正确，仅记录）；L6 `FindObjectsOfType` 弃用 API；L7 无脏检查（性能）；L8 `outlineCount*4` int32 溢出（不可达）；L9 可选块长度歧义；L10 截断时静默垃圾值；L11 负/极大 count → 异常/OOM |
| 提示 | 4 | I1 旋转死数据；I2 `SubMesh.Colour` 死数据；I3 逐顶点颜色冗余占文件 17%；I4 `Read(path)` 死 API |
| 已验证正确 | 9 | N1~N9 |

> 注：低严重度条目中 L5 实为"记录正确项"，因在任务清单内故保留编号。

### 最需要处理的三项

1. **M1 —— 修正 `PlushieOutline.cs:92-95` 的错误断言，并处置失效的 `research/check_outline_undo.py` / `outline_undo_check.txt`。**
   这是本次审计中唯一"代码注释断言了一个可被证伪的事实"的问题，且其证据链已失效（原样重跑得到 `0.002198/0.007226`，与文件记录的 `0.000000` 不符）。对画面无实际影响，但对后续维护者误导性最强。

2. **M3 —— 给 `nameLength`（以及 `subMeshCount` / `vertexCount` / `indexCount`）加上界检查。**
   实测 `ReadBytes` 会**按 count 先分配**（1.00× 比例），一个 4 字节字段即可请求 1.5 GB。虽然被 `TryParseAsset` 兜住不会崩，但在内存紧张的 Unity 进程里是最现实的风险点，修复成本极低。

3. **M2 —— 修正正交分支的 `perPixel`（`2*orthographicSize/screenHeight`）并改写注释。**
   当前游戏主相机为透视，所以**不会立即发作**；但一旦有正交相机（其它模组、或游戏改动），描边会粗 2.7~90 倍。属于低成本、高确定性的修复。

### 关于任务约束的明确回应

- **`surface + cameraToModel.MultiplyVector(offsetInCamera)` 的屏幕空间外推数学核心经 1176 组数值验证为精确正确**（误差恒为 0），`depth = -point.z` 与 `scale *= depth` 的符号、透视 `perPixel`、矩阵复合方向均正确。**我没有提出任何修改该核心的建议**，也不建议改动。
- 唯一被我用实测证据判定为**错误**的数学是**正交分支的 `perPixel`**（`PlushieOutline.cs:224`），它与上述核心是并列的两个分支，不属于"外推数学核心"；其数值证据见 M2（`code/correct` 比值 2.7×~90×，实测线宽 337.5/54/13.5 px vs 请求 5 px）。
- 法线不加 aspect 的**结论**经 aspect 1.0~3.56 的变化验证为正确；被证伪的只是注释里"会倾斜"的**理由**（实测是等比放大而非倾斜，见 N2）。

### 未修改任何 `src/` 文件

本次审计全程只读；唯一写入的文件是本报告 `research/audit/runtime-outline.md`；所有临时脚本位于预授权的 `C:\Users\Administrator\AppData\Local\Temp\opencode\`。
