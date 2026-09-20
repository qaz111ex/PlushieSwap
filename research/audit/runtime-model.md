# 审计 A1：`src/PlushieModel.cs` 深度审计

- 审计对象：`D:\zhuanban\Plushie Swap\src\PlushieModel.cs`（1491 行 / 66183 字符）
- 审计方式：只读。分块阅读（每块 250–350 行），逐块追加结论。
- 约束：本报告是唯一允许写入的文件；`src/`、`assets/`、`models/`、`tools/`、`build.ps1` 一律未改动。
- 严重度定义：
  - **严重** = 会导致崩溃/异常刷屏/资源泄漏累积/功能明显错误
  - **中** = 会造成持续 GC 压力、场景切换后状态残留、边界条件下行为异常
  - **低** = 代码卫生、注释不符、死代码、可读性

---

## 结论摘要

- **严重：0 项**。未发现会导致崩溃、异常刷屏或资源无界泄漏的缺陷。
- **中：4 项** —— M3-1（每帧每物品一次全子树 `GetComponentsInChildren` + 数组分配，最高优先级性能问题）、M1-1（`FailedLoads` 永不清除且注释声称的恢复路径不可达）、M2-1（`MissingTextures` 无清除点）、M5-1（`ApplyCookTint` 的早退在数据读取之后，每帧仍走 `GetData<IntItemData>`）。
- **低：27 项**（防御性不一致、冗余分配、注释措辞、内存瘦身等）。
- **信息 / 非问题：16 项**（含 5 项经反编译实测后**推翻**的初稿判定：M3-5、M5-2、M4-3、M3-2、M1-4）。
- 完整分级清单见文末 **第 12 章**。

---

## 1. 分块发现（按行号顺序，逐块追加）

### 块 1：行 1–300（文件头、两个 MonoBehaviour、加载与网格构建）

**文件结构**：同一文件内含三个类型
- `PlushieItemState : MonoBehaviour`（17–20）
- `PlushieVisualMarker : MonoBehaviour`（23–55）
- `static class PlushieModel`（62–1491）

#### M1-1（中）`FailedLoads` 一旦加入就永远无法清除，注释“only until the next successful one”与实际行为不符

- 位置：`PlushieModel.cs:131-132`、`142-149`、`168-186`
- 现象：`GetAsset` 在行 146 先判断 `FailedLoads.Contains(variant)` 并直接 `return null`；而清除 `FailedLoads` 的唯一位置是行 186（解析成功后）。也就是说**一旦某变体进入 `FailedLoads`，行 146 会永远提前返回，行 185-186 永远不可达**，该变体在本次游戏进程内被永久禁用。
- 根因：失败标记是单向的、没有 TTL、没有在“配置变更 / 场景重载 / 手动重试”时清空；`GetAsset` 的早退判断把唯一的恢复路径堵死了。
- 证据：静态阅读即可确认控制流——`FailedLoads.Add` 只出现在行 157、181；`FailedLoads.Remove` 只在行 186；行 146-149 在行 186 之前。注释 124-130 声称 “remembered … but only until the next successful one”，但“next successful one”在代码里不可达。
- 影响场景：`AssetProvider.Read` 的瞬时失败（文件被占用 / 磁盘抖动 / 首次落盘的松散文件）→ 本局游戏永久回退原版模型，玩家只能重启游戏。
- 建议修法（仅描述）：把 `FailedLoads` 从 `HashSet` 改为记录“失败时间/失败次数”，`GetAsset` 早退时判断距上次失败是否超过若干秒；或在 `RequestRefreshAll(hard:true)`（F7 热切换、配置变更）时清空 `FailedLoads`，给用户一个显式重试入口。同时修正 124-130 的注释或补齐对应代码。

#### M1-2（低）`GetMesh` 会把 `null` 缓存进 `CachedMeshes`，与同一文件里 `GetAsset` 的显式非空判断自相矛盾

- 位置：`PlushieModel.cs:217-236`（尤其 219-222、233-235）
- 现象：行 219 `if (CachedMeshes.TryGetValue(variant, out Mesh cached)) return cached;`——`TryGetValue` 只判断“键存在”。`BuildMesh` 在行 273-276 会因 `parts.Count == 0` 返回 `null`，行 233 仍把它写进字典。之后每次调用都命中缓存并返回 `null`，不会再尝试构建。
- 根因：与 `GetAsset:142`（`&& asset != null`）相比，这里漏了非空判断；而行 124-130 的注释正好在警告“不要缓存 null”这个失败模式。
- 证据：行 230-235 无任何空值检查；`CachedOutlines` 同理（234 行）。
- 严重度定为低的原因：`.psmesh` 数据在 `GetAsset` 成功后是只读的，同一份数据重复构建结果相同，缓存 null 与重试的结果一致，因此不会造成“本可恢复却永久失败”。但如果将来 `BuildMesh` 引入可恢复的失败路径（例如按需生成 outline），这里会变成和 M1-1 一样的坑。
- 建议修法（仅描述）：改为 `if (CachedMeshes.TryGetValue(variant, out Mesh cached) && cached != null) return cached;`，与 `GetAsset` 保持一致；或在 `parts.Count == 0` 时记一条 warn 日志（当前是静默返回 null）。

#### M1-3（低）静态 `Mesh` / `Material` / `Texture2D` 缓存没有进程退出时的统一释放（但有界，非泄漏）

- 位置：`PlushieModel.cs:70-83`（`CachedMeshes` / `CachedOutlines` / `CachedMaterials` / `CachedOutlineMaterials` / `CachedTextures`）
- 现象：这些字典是 `static readonly`，生命周期 = 进程生命周期；`new Mesh()`（279）、`new Material()`、`new Texture2D()` 创建的对象在 Unity 里**不参与 GC 回收**，必须显式 `Object.Destroy`。全文（含后续区块）没有任何对它们调用 `Destroy`。
- 根因：静态缓存 + 无释放钩子（没有 `OnDestroy`/`Application.quitting` 清理）。
- 证据：`grep -n "Destroy" src/PlushieModel.cs`（后续区块读完后统一核实并回填确切行号）；缓存字典声明在 70-83，均为 `static readonly`。
- 严重度：本模组每个变体只构建一次，量级为「2 变体 × (1 实体 mesh + 1 描边 mesh + 材质 + 贴图)」，**上界有限**，不构成无界增长；但有两个具体风险需要后续区块确认：
  1. 若存在“材质/贴图重建”路径（例如 `Shader Override` 变更、`World Scale` 变更导致重建），缓存是否会被覆盖而不销毁旧对象 → 真泄漏。**待后续区块确认**。
  2. `Resources.UnloadUnusedAssets`（游戏切场景时可能调用）对静态字典持有的对象无效，因此切场景后不会误回收——这反而是**需要的**行为（跨场景复用）。所以“不清理”在此处是特性而非缺陷，但必须确认没有第二处 `new Mesh` 泄漏点。
- 建议修法（仅描述）：保持静态缓存（跨场景复用是正确设计），但在 `Plugin` 的退出钩子（`Application.quitting` / BepInEx `OnDestroy`）里统一 `Destroy` 并清空字典；更重要的是确保“重建路径”先销毁旧对象再覆盖缓存。

#### M1-4（信息｜已核实为非问题）`GetAsset` 未对 `Variants.Get(variant)` 的返回值做 null 检查，但该函数**永不返回 null**

- 位置：`PlushieModel.cs:151-153`
- **核实结果**：`Variants.Get`（`src/Variants.cs:58-68`）的实现是遍历 `All` 数组匹配 `Variant` 字段，**未命中时返回 `All[1]`（Miffy）**，而不是 null：
  ```
  internal static VariantDefinition Get(PlushieVariant variant)
  {
      for (int i = 0; i < All.Length; i++)
      {
          if (All[i].Variant == variant) return All[i];
      }
      return All[1];
  }
  ```
  `All` 是 `static readonly VariantDefinition[]`，元素在静态初始化时全部 `new` 出来（`Variants.cs:27-56`），数组本身与元素都不可能为 null。
- 结论：行 153 `def.MeshFile` **不会**抛 NRE。初稿把本条列为“低风险 NRE”是**误报**，现更正为信息。
- 附带发现（属 task-2 范围，仅记录）：未命中的变体被静默当作 Miffy 处理，而不是回退到 Vanilla。由于 `PlushieVariant` 只有三个取值且全部已在 `All` 中登记，实际不可达；但若将来新增枚举值而忘记登记 `All`，会静默显示成米菲兔。建议 `Variants.Get` 对未命中情形记一条 warn。

#### M1-5（信息｜非问题）`indexFormat` 阈值 65000 与 Unity 实际边界 65535 不一致（偏保守，安全）

- 位置：`PlushieModel.cs:282`
- 现象：`vertexCount > 65000 ? UInt32 : UInt16`。Unity 的 UInt16 索引格式上限是 65535 个顶点。
- 判定：**这是安全的保守写法**（阈值更小 → 更早切 UInt32），不构成缺陷；记录在此仅为说明“看似 off-by-one 实际没问题”，避免后续审计重复怀疑。

#### M1-6（信息）`GetOutlineMesh` 依赖 `GetMesh` 的副作用建缓存

- 位置：`PlushieModel.cs:238-245`
- 现象：行 240-243 `if (!CachedOutlines.ContainsKey(variant)) GetMesh(variant);`——用 `GetMesh` 的副作用（行 233-234 同时写两个字典）来填充 `CachedOutlines`。逻辑上正确，但若将来有人把行 233-234 拆开（例如改为懒构建 outline），这里会静默返回 null。
- 判定：当前**不是缺陷**，属于脆弱耦合；建议（仅描述）在注释里显式声明该依赖，或让 `GetOutlineMesh` 自行调用 `BuildMesh`。

#### M1-7（信息｜非问题）`Tick` 用单个 bool 表示刷新请求，无法区分“软/硬刷新叠加语义”

- 位置：`PlushieModel.cs:86-121`
- 现象：`_refreshRequested` 是 bool，`_hardRefresh |= hard` 是粘性 OR。同一帧内多次 `RequestRefreshAll(hard:true)` 只执行一次（正确、也是想要的去重）；但**没有**“一次硬刷新 + 之后一次软刷新”的队列概念——后到的软请求会被同一帧的硬刷新吸收。
- 判定：对当前用途（F7 热切换、配置变更）**不构成缺陷**。记录以避免误报。

#### M1-8（信息｜非问题）`_lastVariant` 初值为 `Vanilla`，启动首帧的行为依赖 `Plugin.ActiveVariant`

- 位置：`PlushieModel.cs:89`、`105-110`
- 现象：若启动时 `Plugin.ActiveVariant != Vanilla`（README 记录默认值为 `ZichaoXiong`），首帧 `Tick` 会立即置 `_refreshRequested = true; _hardRefresh = true`。若启动时恰为 `Vanilla`，则不会触发刷新——这是正确的（原版无需替换）。
- 判定：**不是缺陷**；仅说明 `_hardRefresh = true`（行 109，赋值而非 OR）会覆盖同一帧内更早的软刷新请求为硬刷新，这是更强的刷新，无害。

### 块 2：行 301–600（网格填充收尾、贴图/材质解析）

#### M2-1（中）`MissingTextures` 与 `FailedLoads` 同病：永久污染，本局内无法恢复

- 位置：`PlushieModel.cs:337-340`、`361-365`
- 现象：`MissingTextures.Add(variant)` 之后，行 337-340 会在**每次**调用时直接 `return null`，全文没有任何 `MissingTextures.Remove(...)` 或清空点。行 348-359 的重试只覆盖“松散文件解码失败→改用内嵌副本”这一次机会；一旦两者都失败（或内嵌副本本身缺失），该变体在本次进程内永久没有阴影贴图。
- 根因：与 M1-1 完全相同的“单向失败标记”模式，两处重复实现。
- 证据：`grep -n "MissingTextures" src/PlushieModel.cs` → 仅 82-83（声明）、337、363（Add），**无 Remove**。
- 与 M1-1 的差别：`GetShadingTexture` 的早退判断在 `MissingTextures` 之前**没有**成功缓存判断（行 332-336 有 `CachedTextures.TryGetValue`），所以不存在 M1-1 那种“Remove 不可达”的死锁；这里纯粹是“没有恢复入口”。
- 影响：贴图缺失时模型仍能显示（行 404-419 只是跳过贴图绑定），表现为颜色正确但没有 AO 阴影 —— 属于视觉降级而非崩溃。
- 建议修法（仅描述）：把两个失败集合统一为“带时间戳的失败记录”，或至少在 `RequestRefreshAll(hard:true)` 时清空 `MissingTextures` 与 `FailedLoads`，让 F7 热切换 / 重载配置成为显式重试入口。

#### M2-2（低）`GetMaterial` 的着色器解析失败不缓存，失败时每次调用都重跑 `Shader.Find`

- 位置：`PlushieModel.cs:383-387`（对比 375-381 的成功路径会写 `CachedMaterials`）
- 现象：`ResolveShader()` 返回 null 时直接 `return null`，**不写 `CachedMaterials`**；且 `ResolveShader` 内部只有在找到 shader 时才给 `_shader` 赋值（行 594-597 只做读取）。于是“解析失败”这个状态**完全没有被记忆**，每次调用 `GetMaterial` 都会重新走一遍 `Plugin.ShaderOverrideEntry.Value` 读取 + `Shader.Find` 循环。
- 根因：失败路径缺少“负缓存”。
- 证据：行 383-387 无写入；`ResolveShader` 全文（592 起）无失败缓存。
- 严重度：取决于 `GetMaterial` 的调用频率。**待后续区块确认**：若它只在 `BuildVisual`（构建时）调用，则影响可忽略（每次重建最多几次 `Shader.Find`）；若存在每帧路径，则升级为性能问题。
- 建议修法（仅描述）：用 `bool _shaderResolveFailed` 做一次性负缓存（并在 `ShaderOverrideEntry` 变更时重置），或直接复用 `GetOutlineMaterial` 里 `CachedMaterials[variant] = null` 的既有模式。

#### M2-3（低）`GetOutlineMaterial` 的负缓存写法与 `GetMaterial` 不一致（此处反而正确）

- 位置：`PlushieModel.cs:493-501`
- 现象：无法剔除正面时，先 `UnityEngine.Object.Destroy(material)`（行 496，**销毁正确，无泄漏**），再 `CachedOutlineMaterials[variant] = null`（行 499）后返回 null。
- 判定：**这是正确的负缓存**（避免每帧重复 warn + 重复创建材质），但 `CachedOutlineMaterials.TryGetValue` 拿到 null 会 `return cached`（行 472-475），意味着这个变体本次进程内永久无描边。功能上是降级、不是缺陷；仅记录它与 `GetMaterial`（M2-2）的不一致。

#### M2-4（低）`ResolveOutlineShader` 的兜底分支不写 `_outlineShader`，失败日志与候选循环会重复执行

- 位置：`PlushieModel.cs:587-589`
- 现象：所有 unlit 候选都不可用时，返回 `ResolveShader()`，但**不写** `_outlineShader`（对比 563、581 两处成功路径都写了）。因此 `_outlineShader` 始终为 null，下次调用会再次走完整候选循环并再次输出 `DiagnosticLog.Warn`（行 587）。
- 影响：调用次数受 `GetOutlineMaterial` 的负缓存/正缓存限制，通常每个变体一次；若 `GetOutlineMaterial` 在每帧路径上被调用则会被放大。**待后续区块确认调用频率**。
- 建议修法（仅描述）：把兜底结果也写入 `_outlineShader`（用一个单独的 bool 标记“已解析过”），或加 `_outlineShaderResolved` 哨兵。

#### M2-5（低）`GetMaterial` 未关闭 `_SURFACE_TYPE_TRANSPARENT`，与 `GetOutlineMaterial` 不对称

- 位置：`PlushieModel.cs:429`（`_Surface = 0`）对比 `535`（显式 `DisableKeyword("_SURFACE_TYPE_TRANSPARENT")`）
- 现象：`GetMaterial` 只设置 `_Surface` 浮点值，没有动 `_SURFACE_TYPE_TRANSPARENT` / `_SURFACE_TYPE_OPAQUE` 关键字，也没有 `SetOverrideTag("RenderType", ...)`。
- 判定：**当前不是缺陷**——如果解析到的是 `Universal Render Pipeline/Lit`，其默认关键字组合就是 opaque；且 `renderQueue`（455）已被强制为 Geometry，绘制顺序正确。但如果 `Shader Override` 被用户设成一个默认透明的 shader，正文可能变成透明。属于低概率配置问题。
- 建议修法（仅描述）：与描边材质保持对称，显式关闭透明关键字。

#### M2-6（信息 / 非问题）`ToWorkingColor` 逐顶点调用不产生 GC

- 位置：`PlushieModel.cs:302`
- 现象：`Color` 是 struct，逐顶点调用只做值计算，不装箱。**无 GC 问题**。记录以避免误报（此处每顶点确实有函数调用开销，但 `BuildMesh` 只在构建时执行一次，不是热点）。

#### M2-7（低）`BuildMesh` 的顶点数用 `int` 累加，极端数据下会溢出

- 位置：`PlushieModel.cs:258-271`、`285-289`
- 现象：`vertexCount += sub.Positions.Length` 与 `indexCount += sub.Indices.Length` 都是 `int`。`new Vector3[vertexCount]` 在 `vertexCount < 0` 时抛 `OverflowException`/`OutOfMemoryException`。
- 判定：**实际不可达**。`PsMeshReader` 从内嵌/松散 `.psmesh` 读出的数据由本项目自己的构建管线生成，单变体顶点数在 1.5 万量级（README 记录“每个实例约 1.5 万个顶点”），离 `int` 上限有 5 个数量级。只有在恶意构造的 `.psmesh` 才会触发，而 `PsMeshReader` 侧本身已有长度校验（属于 task-8 范围）。
- 建议修法（仅描述）：不需要改；若想防御，可在 `PsMeshReader` 侧限制单文件总顶点数上限。

#### M2-8（信息｜非问题）`indexFormat` 在 `vertexCount > 65000` 时切 UInt32 —— 正确且保守

见 M1-5，此处补充：`BuildMesh` 对**实体网格与描边网格分别**计算 `vertexCount`（230-231 两次调用），所以两个 mesh 各自独立选择索引格式，不存在“描边顶点数没算进实体网格”的问题。

### 块 3：行 601–900（着色器解析收尾、刷新主循环、追踪列表维护）

#### M3-1（中｜最高优先级性能问题）每帧每物品一次 `GetComponentsInChildren<PlushieVisualMarker>(true)`，每次分配一个新数组

- 位置：`PlushieModel.cs:120`（`Tick` 每帧调 `MaintainTrackedItems`）→ `747-760` → `752` 调 `FindVisualRoot(item)` → `663-664` `item.GetComponentsInChildren<PlushieVisualMarker>(true)`
- 现象：`MaintainTrackedItems` 对**每个被追踪物品、每一帧**都调用一次 `FindVisualRoot`，而 `FindVisualRoot` 用 `GetComponentsInChildren<T>(true)` 在**整个 item 子树**（含背包挂点、Holder、两个锚点、视觉根、实体网格、描边网格等所有后代）上做一次全子树遍历，并分配一个 `PlushieVisualMarker[]`。
- 根因：把“查找根节点”这个本可以在构建时记住的信息，做成了每帧的组件搜索。`FindVisualRoot` 的注释（649-656）解释了**为什么需要全子树搜索**（挂在 `Holder` 下，且 `transform.Find` 会命中正在销毁的根），但没解释**为什么需要每帧做**。
- 证据：
  - `Plugin.cs:431` `PlushieModel.Tick();`（每帧）
  - `PlushieModel.cs:120` `MaintainTrackedItems();`
  - `PlushieModel.cs:752` `Transform root = FindVisualRoot(item);`
  - `PlushieModel.cs:664` `item.GetComponentsInChildren<PlushieVisualMarker>(true);`
  - 反证：`ApplyToItemUnsafe`（827）也用同一个调用，但那条路径只在事件/重扫时走，不是每帧。
- 影响：以场上 1 个 BingBong 为例，每帧 1 次子树遍历 + 1 个数组分配；`Renderer` 数较多时（原版玩偶拆成多个部件）子树规模更大。属于**持续、恒定的小额 GC 压力**，不是无界泄漏，但在长时间游戏里会稳定推高 GC 触发频率。
- 建议修法（仅描述）：把根节点引用缓存到 `PlushieVisualMarker` 自身或一个 `ConditionalWeakTable<Item, Transform>` / `Dictionary<Item, PlushieVisualMarker>` 里，每帧只做一次 `!= null && !Destroying` 校验；仅在缓存失效（null / Destroying / 变体不符）时才退回 `FindVisualRoot` 全子树搜索。注意红线：这**不触碰** `ResolveVisualParent` 的挂载逻辑，只是缓存查找结果。

#### M3-2（低｜已修正，原判“每帧”有误）`SetVanillaRenderersEnabled` 的全子树遍历被 `VanillaRenderersHidden` 闩锁挡住，**不是**每帧执行

- 位置：`PlushieModel.cs:1216-1222`（闩锁）、`1366-1381`（实现，含 1368 `item.GetComponentsInChildren<Renderer>(true)`）
- **修正说明**：本节初稿曾判定该遍历“每帧每物品一次”，经核对 `SyncVisual` 的闩锁逻辑后**推翻**。
  - 行 1218 `if (!marker.VanillaRenderersHidden || stateChanged)`：`marker.VanillaRenderersHidden` 在行 1220 被置 `true` 后，只有在 `stateChanged`（行 1193 `marker.LastState != state`，即物品状态真正切换）时才再次进入。
  - 稳态下（状态不变）该分支**被跳过**，`SetVanillaRenderersEnabled` 不会执行。
- 结论：该调用频率为“构建后首帧 + 每次状态切换”，**不是每帧**。降为低。真正的每帧成本在 M3-1 与 M5-1。
- 仍然成立的部分：每次执行时 `GetComponentsInChildren<Renderer>(true)` 会分配一个数组，且对每个 renderer 调 `IsPlushieTransform` → `GetComponentInParent<PlushieVisualMarker>()`（678）又是一次 native 查询。属于“事件频率”开销，可接受。
- 建议修法（仅描述）：无需改。若将来想省，可把 renderer 列表缓存到 `PlushieVisualMarker`。

#### M3-3（低）`RefreshAll` 的硬刷新路径对同一批物品调用两次 `DestroyReplacement`

- 位置：`PlushieModel.cs:694-705`
- 现象：行 694-697 先对 `new List<Item>(TrackedItems)` 的每个物品调 `DestroyReplacement`，行 698 `TrackedItems.Clear()`；紧接着行 699-705 又遍历 `items` 并对每个 `IsBingBongItem` 调 `DestroyReplacement`。`TrackedItems` 里的物品**必然是** BingBong（`EnsureTracked` 只在 719/776 的 `IsBingBongItem` 分支里调用），所以第二次遍历把它们又处理了一遍。
- 根因：两段清理逻辑（“清掉我追踪过的” + “清掉所有 BingBong”）叠加，缺少去重。
- 证据：行 694 的 `foreach` 遍历的是拷贝（避免遍历中修改 `TrackedItems`，写法正确）；行 699 的循环覆盖了同一集合的超集。`DestroyReplacement` 幂等（行 1141 `FindVisualRoot` 会跳过 `Destroying` 标记的根，1149 先置位），所以**不产生功能性错误**，只是重复的 `FindVisualRoot` 全子树搜索 + 一次 `new List<Item>(...)` 分配。
- 严重度：中偏低（只在硬刷新时发生：F7 切换、变体配置变更、描边 0→正数）。之所以不降到低，是因为硬刷新时物品可能较多，且 `new List<Item>` 分配可避免。
- 建议修法（仅描述）：删掉 694-698 这一段（第二段已是超集），或反过来只保留第一段 + 一次 `FindObjectsOfType` 式的兜底；若担心 `TrackedItems` 里有“已不再是 BingBong”的物品，可保留但加去重判断。

#### M3-4（低）`RefreshAll` / `MaintainTrackedItems` 在 `GameHelpers.AllItems()` 返回的**游戏自身列表**上做索引遍历

- 位置：`PlushieModel.cs:688`、`714-722`、`771-779`；实现见 `GameHelpers.cs:107-147`
- 现象：`AllItems()` 在反射字段可用时**直接返回游戏自己的 `List<Item>`**（`GameHelpers.cs:118-128` 返回 `list` 本身，不是拷贝）。`PlushieModel` 随后在循环体里调用 `ApplyToItem` → `BuildVisual` → `AddComponent` / `Object.Destroy`，即**在遍历游戏列表的同时执行可能影响该列表的游戏侧代码**。
- 根因：共享可变集合 + 循环内回调。
- 证据：`GameHelpers.cs:118-128`（`return list;`）、`PlushieModel.cs:714-722`（索引循环，非拷贝）。行 694 的 `foreach` 用了拷贝，说明作者知道这个风险，但 714/772 两处没有。
- 判定：`ApplyToItem` 不直接增删 `ALL_ITEMS`，因此**当前不可复现**；但索引循环读取 `items[i]` 时若列表被游戏收缩，会抛 `ArgumentOutOfRangeException`（行 716/774 在 try 外，`MaintainTrackedItems` 由 `Tick` 调用，`Tick` 无 try/catch → 会冒泡到 `Plugin.Update`）。定低。
- 建议修法（仅描述）：在 `PlushieModel` 侧对 `AllItems()` 结果做一次快照（`new List<Item>(...)`），或把循环体包进 try/catch。注意：快照会引入每 0.5 秒一次的分配，属于用 GC 换安全的取舍，需与 M3-1 的优化一起权衡。

#### M3-5（低｜已修正，异常有兜底）`Tick` 无 try/catch，但调用方 `Plugin.LateUpdate` 有——最坏情况是“每帧一次 Error 日志”而非崩溃

- 位置：`PlushieModel.cs:98-121`、`725-780`；调用方 `Plugin.cs:427-438`
- **修正说明**：本节初稿判定“异常会冒泡到 `Plugin.Update` 且无保护”。实测 `Plugin.cs:427-438`：
  ```
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
  ```
  即 `Tick` 每帧在 `LateUpdate` 中执行，**外层已有 try/catch**，异常不会传播到 Unity 引擎层、也不会中断游戏循环。
- 仍然成立的部分：如果异常是**持续性**的（例如某个物品的 renderer 处于异常状态导致每次 `SyncVisual` 都抛），那么每帧都会写一条 `DiagnosticLog.Error`。BepInEx 日志默认无速率限制，长时间挂机会造成日志文件快速增长（每小时 21.6 万条 @60fps）。这是**真实的**最坏情况，但比“游戏崩溃”轻得多。
- 另需注意：`Tick` 被整体包住，意味着**一个物品的异常会中止同一帧内其余所有物品的同步**（循环体在 try 外、try 是整个 `Tick`）。若该物品持续异常，其它玩偶的状态同步每帧都被跳过。
- 严重度：低。
- 建议修法（仅描述）：把 try/catch 下沉到 `MaintainTrackedItems` 的 per-item 循环体内（单个物品失败不影响其它物品），并加“同一异常类型只记一次 Error”的去重，避免日志刷屏。

#### M3-6（低）`ResolveShader` 的 shader override 解析失败不记忆，且 `ShaderOverrideEntry` 变更不会使 `_shader` / `_outlineShader` 缓存失效

- 位置：`PlushieModel.cs:592-632`、`634-635`（`_shader` / `_outlineShader` 静态字段）
- 现象：两个着色器字段一旦赋值就永不重置；`Plugin.cs` 的配置变更回调（`OnVariantChanged:289-298`、`OnScaleChanged:300-303`、`OnOutlineWidthChanged:311-325`）都**没有**调用任何“重置着色器缓存”的方法（`grep -n "ShaderOverride" src/Plugin.cs` 只命中 35、207，即声明与绑定，无变更回调）。
- 根因：静态缓存没有失效入口。
- 证据：`Plugin.cs:207` 绑定 `ShaderOverrideEntry`；`grep -n "_shader" src/Plugin.cs` 无结果，说明 Plugin 无法清理 `PlushieModel` 的着色器缓存。
- 判定：`Shader Override` 在 README（59 行）里被描述为“仅当模型颜色显示异常时才需要改”，且文档说明“直接编辑配置文件不会被热重载——需要重启游戏”。因此**“改了不生效、要重启”与文档一致**，不构成功能性缺陷；但要注意 `Plugin.cs:297/302/323` 确实存在热刷新路径，用户会误以为着色器也会热更新。定低。
- 建议修法（仅描述）：在 `PlushieModel` 暴露一个 `ResetShaderCache()`，由 `ShaderOverrideEntry` 的变更回调调用，并清空 `CachedMaterials` / `CachedOutlineMaterials`（**同时销毁旧材质**，否则就变成 M1-3 里担心的真泄漏）。

#### M3-7（信息｜非问题）`GetItemState` 的伪 null 双检查是正确的，全文最佳范例

- 位置：`PlushieModel.cs:863-881`
- 现象：行 871 `if (item == null || item.gameObject == null) return null;`，注释 865-870 解释了为什么要同时查两者（Unity 伪 null 覆盖不了“GameObject 已被拆掉但 wrapper 还在”的延迟调用场景）。
- 判定：**不是缺陷**，是全文里对 Unity 伪 null 处理得最正确的一处，可作为其他位置的对照标准。记录在此作为“看似冗余实则必要”的证据。

#### M3-8（信息）`_shader` / `_outlineShader` 声明在方法之后（行 634-635），是 C# 允许的写法

- 位置：`PlushieModel.cs:634-635`
- 判定：静态字段声明位置与 `ResolveShader`（592）之间无初始化顺序问题（静态字段默认值 null，`ResolveShader` 首次调用时读取）。**无缺陷**。

#### M3-9（低）`ToWorkingColor` 依赖 `QualitySettings.activeColorSpace` 每次调用都读一次静态属性

- 位置：`PlushieModel.cs:643-646`
- 现象：`QualitySettings.activeColorSpace` 在 `BuildMesh` 里对**每个顶点**调用一次（行 302）。Unity 的这个属性是 native 调用，逐顶点读取有实际开销。
- 判定：`BuildMesh` 只在构建时执行（每个变体一次，约 1.5 万顶点 × 2 个网格），总开销在毫秒级，**不构成性能问题**；但写法上把“整个项目只有一种色彩空间”的常量做成了逐顶点查询。定低/信息。
- 建议修法（仅描述）：把结果缓存进一个 `static readonly bool _linear = QualitySettings.activeColorSpace == ColorSpace.Linear;`（色彩空间在运行时不会改变）。

### 块 4：行 901–1200（挂载点解析、构建视觉根、握持偏移、销毁、同步入口）

#### M4-1（低｜红线相邻，仅建议加日志）`ResolveVisualParent` 在 `Holder` 缺失时静默降级为挂在 item 根，无任何日志

- 位置：`PlushieModel.cs:901-914`，调用点 `925-932`
- 现象：行 907 `item.transform.Find(HolderName)`（`HolderName = "Holder"`，901 行）找不到时，行 913 `return item != null ? item.transform : null;` 直接返回 item 根。`BuildVisual` 拿到这个 parent 后照常建根（932），**不报错、不打日志**。
- 根因：注释 898-899 明确说这是“the old behaviour rather than a failure”，即**故意**的降级；但降级后 Squish 动画（`Holder.localScale`）不再作用于替换模型，模型不会跟着挤压，同时 `SyncVisual` 的握持偏移是按“模型是 item 子节点”推导的（1129-1131），挂载层级变了但偏移公式不变。
- 证据：`PlushieModel.cs:907-913`；注释 883-899 说明为什么必须挂在 `Holder`；`grep -n "HolderName" src/PlushieModel.cs` → 仅 901（定义）与 907（使用）。
- **红线标注**：任务说明明确“不得改 `ResolveVisualParent`（挂 Holder）”。因此**本条不建议修改挂载逻辑**；建议的只是**可观测性**：在 913 的降级分支加一条 `DiagnosticLog.Warn`（说明 Holder 缺失、正在退回 item 根、挤压动画将不生效）。这条改动不触碰挂载决策本身。
- 触发场景：其它模组替换了 BingBong 的层级、或 `Item` 是某种非标准变体。属低概率但难排查。

#### M4-2（低）`BuildVisual` 为**每个实例**`Instantiate` 一份描边网格（设计必需的成本）

- 位置：`PlushieModel.cs:1022-1023`，配套 `1001-1003`（注释）与 `1134-1181`（销毁）
- 现象：行 1022 `UnityEngine.Object.Instantiate(outline)` 复制整份描边网格（约 1.5 万顶点，README 第 186 行），每生成一个替换模型就复制一份；`PlushieOutline` 每帧重写这份网格的顶点。
- 根因：描边顶点是**逐实例**变化的（屏幕空间外扩依赖该实例的相机/变换），所以无法共享 —— 这是**设计上的必然**，注释 1001-1003 已说明。
- 证据：行 1022；行 1153-1166 与 `PlushieOutline.OnDestroy` 双路径释放（注释 1153-1157 明确说明 Unity 不会自动回收 mesh）。
- 影响：4 人联机 + 地上若干玩偶时，实例数可达 5~10；每实例一份 1.5 万顶点 mesh（约 1.5 万 × (12+12+8+16) 字节 ≈ 0.7 MB，含索引后近 1 MB）→ 5~10 MB 量级的网格内存，加上每帧每实例一次顶点重算。**这是本模组最大的性能/内存成本，但它是“屏幕像素恒定宽度”这一需求的直接代价**，README 第 186-187 行也承认了。
- 建议修法（仅描述）：**不建议**去掉逐实例网格（会破坏恒定线宽）。可考虑的只有：① 对远处/不可见的实例跳过每帧重算（属于 `PlushieOutline` 的 `isVisible` 早退，见 task-8）；② 降低描边网格的顶点数（构建管线侧）。均不改本文件逻辑。

#### M4-3（信息｜已交叉验证为无问题）`driver == null` 时销毁 `outlineMesh` 与 `outlineObject` 是安全的

- 位置：`PlushieModel.cs:1038-1052`
- **交叉验证结果**：我读了 `PlushieOutline.Attach`（`PlushieOutline.cs:67-131`）的实际实现。它**所有**的 null 返回分支（71-74 参数校验、78-81 顶点/法线校验）都发生在 `host.AddComponent<PlushieOutline>()`（110 行）**之前**。也就是说：
  - `Attach` 返回 null ⟹ 组件从未被添加、`driver._mesh` 从未被赋值、`mesh.bounds` 从未被修改（126-128 在 110 之后）。
  - 因此 `PlushieModel` 在 1046-1047 销毁 `outlineMesh` / `outlineObject` 时，不存在“组件持有已销毁 mesh”或“静态列表持有悬空引用”的状态。
- 结论：注释 1044-1045 假设的 “all-or-nothing” 语义**成立**，调用方销毁是正确且必要的（否则会泄漏一份 1.5 万顶点的 per-instance mesh）。**不是缺陷。**
- 补充：`Attach` 内部对 `widths.Length != count` 的处理（84-90）是“警告并降级为均匀线宽”，不会返回 null；这是与 `PlushieModel:1059-1061` 日志相配套的正确降级。

#### M4-4（低）`BuildVisual` 里 `asset == null` 的防御分支实际不可达（死代码）

- 位置：`PlushieModel.cs:942-949`
- 现象：行 918-923 已经从 `GetMesh` / `GetMaterial` 拿到了非 null 的 mesh 与 material 才继续；而 `GetMesh`（224-228）只有在 `GetAsset(variant) == null` 时才返回 null。因此在 942 再次调用 `GetAsset` 时它必然非 null（`LoadedAssets` 已被填充）。
- 判定：**死代码**，但注释 945-946 明确说明它是“把隐含契约显式化”的防御，属于可接受的写法。定低。
- 建议修法（仅描述）：可保留；若要清理，改为 `Debug.Assert` 或直接复用 `GetMesh` 内部的 asset 引用（让 `GetMesh` 输出 asset）。

#### M4-5（信息｜非问题）`BuildVisual` 中 `part`（"Model" 子对象）在 `asset == null` 早退路径下不会被单独销毁，但会被父对象连带销毁

- 位置：`PlushieModel.cs:938-949`
- 现象：行 938-940 先建了 `part`，行 947 只 `Destroy(rootObject)`。
- 判定：`part` 是 `rootObject` 的子对象，`Destroy(rootObject)` 会连带销毁整个层级。**不是泄漏**，记录以避免误报。

#### M4-6（信息｜红线相关）`HoldOffsetFor` 公式与注释完全一致，`anchorMid` 常量与 README 数值表一致

- 位置：`PlushieModel.cs:1114-1132`（公式 1127 `anchorMid - waistMid * scale`），常量 1124 `(-0.0595f, -0.1405f, -0.0400f)`
- 核对结论：注释 1095 写的公式 `offset = anchorMidpoint - scale * waistMidpoint` 与代码 1127 **一致**（乘法交换律下等价）。常量与 `README.md:103`（`(-0.0595, -0.1405, -0.0400)`）**一致**。
- **红线标注**：任务说明“不得改 `HoldOffsetFor` 公式”。本报告**不对该公式提出任何修改建议**；仅记录核对结果。行 1116 的 `!asset.HasGrips` 早退返回 `Vector3.zero`（而非抛异常）也是正确防御。

#### M4-7（信息｜非问题）`HoldOffsetFor` 在 `scale == 0` 时退化为 `offset = anchorMid`（模型不可见，无害）

- 位置：`PlushieModel.cs:1127`
- 现象：`scale = 0` 时 `offset = anchorMid`，即把（缩放到零、不可见的）模型移到锚点中点。数学上自洽，视觉上模型本就不可见。
- 判定：**不是缺陷**。记录在“边界值”章节作为已核查项。

#### M4-8（低｜防御性不一致，未证实可复现）`FindVisualRoot` 只查 `item == null`，未像 `GetItemState` 那样同时查 `item.gameObject == null`

- 位置：`PlushieModel.cs:657-673`（尤其 659），对比 `871`（`item == null || item.gameObject == null`）；受影响的调用点 `1141`、`1429`、`1447`
- 现象：同一文件里对 Unity 伪 null 的处理有两套标准。`GetItemState`（863-881）用了双检查，`FindVisualRoot`（659）只用单检查。
- **实际可达性评估（降低严重度）**：Unity 的伪 null 语义下，**被销毁的 `Item` 组件其 `== null` 已为真**（`Destroy` 后 MonoBehaviour 的 native 指针失效）。因此行 1136 `if (item == null)`、行 750 `if (item != null)` 实际上**已经**把“GameObject 已销毁”的物品挡掉了；`GetItemState` 注释 865-870 描述的“wrapper 还在但 GameObject 已拆掉”是一个**理论上的中间态**，在 Unity 的生命周期模型里很难构造（该中间态只在 `Object.Destroy` 已调用但帧尾回收尚未执行、且组件 wrapper 尚未失效时存在）。
- 结论：这是**防御性写法不一致**，不是已证实的缺陷。定低。
- 建议修法（仅描述）：把 `FindVisualRoot` 的首行改为 `if (item == null || item.gameObject == null) return null;`，与 `GetItemState` 对齐，成本为零、可消除两个标准并存带来的维护风险。

#### M4-9（低）`DestroyReplacement` 的 `outlines` 数组每实例分配一次，且用 `GetComponentsInChildren` 而非已知的单个子对象

- 位置：`PlushieModel.cs:1158-1166`
- 现象：每个描边驱动是 `rootObject/Outline` 下的唯一组件，但仍用全子树 `GetComponentsInChildren<PlushieOutline>(true)` 查找。
- 判定：`DestroyReplacement` 只在事件/硬刷新时调用，**不是每帧**，开销可接受；用全子树查找是为了兼容层级变化，属于稳健性选择。定低。

#### M4-10（信息｜非问题）`rootObject.name` 被改成 `PlushieSwap_Visual_Destroying`（行 1151）只是诊断辅助，`FindVisualRoot` 不依赖名字

- 位置：`PlushieModel.cs:1151`
- 判定：改名配合 `Destroying` 标记（1149）一起使用；`FindVisualRoot`（663-671）靠组件而非名字查找，因此改名**不是**功能必需，但作为调试痕迹有价值。**不是缺陷**。
- 注意：改名后若同一帧内 `BuildVisual` 又建了一个新根，场景里会短暂同时存在 `PlushieSwap_Visual_Destroying` 与新根 —— 这是**有意**的（新根必须能建出来），且旧根在本帧末尾被回收。记录为“看似重复对象实则正确”。

#### M4-11（低）`SetVanillaRenderersEnabled(item, true)` 在 `DestroyReplacement` 末尾被调用，与“硬刷新时对同一物品调用两次 `DestroyReplacement`”（M3-3）叠加会重复遍历渲染器

- 位置：`PlushieModel.cs:1175-1180`，调用方 `694-705`
- 现象：硬刷新时同一物品的 `DestroyReplacement` 执行两遍（M3-3），于是 `SetVanillaRenderersEnabled`（内部 `item.GetComponentsInChildren<Renderer>(true)`，1368）也执行两遍。
- 判定：幂等、无功能错误，只是重复分配。并入 M3-3 的修法即可，不单独提修法。

### 块 5：行 1201–1491（同步状态机、烹饪着色、渲染器开关、隐藏规则、缩放）

#### M5-1（中）`SyncVisual` 每帧仍会调用 `ApplyCookTint`，其内部的 `ReadCookedAmount` 会走 `item.GetData<IntItemData>` 反射式字典查找

- 位置：`PlushieModel.cs:1229` → `1295-1326` → `1303` `ReadCookedAmount(item)` → `1335-1354` → `1343` `item.GetData<IntItemData>(DataEntryKey.CookedAmount)`
- 现象：`ApplyCookTint` 本身有早退优化（1304 `if (marker.LastCook == cooked) return;`），注释 1306-1308 明确说这是“keeps this cheap enough to run from the per-frame item sweep”。但**早退发生在读取之后**：每帧仍要调用一次 `ReadCookedAmount`，其中 `item.GetData<IntItemData>(...)`（游戏侧 `Item.cs:1217-1238`）会做 `data == null` 检查 + `TryGetDataEntry<T>(key, out value)` 泛型字典查找，且整段包在 try/catch 里（1341-1353）。
- 根因：把“是否需要重写”的判断放在了数据读取之后；真正的热路径是每帧一次泛型数据查询 + 一个 try 块。
- 证据：`PlushieModel.cs:1229`（每帧，`SyncVisual` 由 `MaintainTrackedItems:757` 每帧调用）；`PlushieModel.cs:1303-1310`；游戏侧 `Item.cs:1217-1238`（`GetData<T>` 实现，含 `TryGetDataEntry` 与 `RegisterNewEntry` 分支）；`Item.cs:38` `DefaultCookColorMultiplier = (0.66f, 0.47f, 0.25f)`（注释 1285-1286 的数值断言**正确**）。
- 严重度：中偏低。单次成本很小（一次泛型字典查找 + try 块），但它是**每帧 × 每实例**的确定性开销，且 try/catch 在没有异常时几乎零成本、有异常时成本极高。与 M3-1 合并构成每帧主要开销。
- 建议修法（仅描述）：把烹饪等级的读取也纳入“状态变化才做”的门控（例如用 `item.OnStateChange` 或降低查询频率到每 N 帧），或把 `LastCook` 的比较移到 `ReadCookedAmount` 之前的粗筛（需要另存一个不依赖 `GetData` 的信号，例如订阅 `ItemCooking` 的变更事件）。

#### M5-2（低｜已修正，原判“严重/中”过重）`IsWornBackpack` 的判据不精确，但主流取出路径由 `SetState` Prefix 兜住

- 位置：`PlushieModel.cs:1392-1416`（`IsWornBackpack`）、`1203-1206`、`1436-1469`；调用方 `Patches.cs:33-47`
- **修正说明**：本节初稿依据“游戏从不调用 `SetState(ItemState.Ground)`”推断出“取出玩偶不经过 `SetState`，会导致永久隐形”，并把严重度定到中/严重。**该推断不成立**，原因是漏看了取出路径的实际实现。
- 实测的取出路径（反编译证据）：
  - `BackpackWheel.cs:144-147`：从背包槽取出时调用 `item.Interact(...)`
  - `Item.cs:573-588` `Interact` → `view.RPC("RequestPickup", ...)`
  - `Item.cs:624-629`：`else if (backpackReference.IsSome)` 分支 → `ClearDataFromBackpack()` + `OnPickupAccepted`
  - `CharacterItems.cs:441+` `OnPickupAccepted` → `EquipSlot(...)`
  - `CharacterItems.cs:582-596` `Equip(Item item)` → **`item.SetState(ItemState.Held, character)`**
  - 于是 `Patches.cs:43-46` 的 `SetState` **Prefix** 命中（`Held != InBackpack`）→ `ClearGameRuleHide` 被调用，隐藏标记清除。
  - 另一条取出路径 `DropAllItems`/`DropItemFromSlotRPC`（`CharacterItems.cs:309-338`、`349-370`）走 `PhotonNetwork.InstantiateItemRoom(...)` **新建一个 Item 实例**，新实例上不存在旧的隐藏标记。
- 仍然成立的真实问题（降级为低）：`BackpackReference.IsOnMyBack()`（`BackpackReference.cs:84-91`）的实现是
  ```
  if (type == BackpackType.Item) return false;
  return view.IsMine;
  ```
  它**只判断引用类型与归属权，不判断背包当前是否被穿戴，也不判断玩偶是否还在该背包里**。而 `item.backpackReference` 在被写入后（`Item.cs:1295`）没有任何地方重置为 `None`（`grep` 全仓库只有 1295 一处写入；`ClearDataFromBackpack`（`Item.cs:638-658`）只清槽位数据、不动 `backpackReference`）。因此 `IsWornBackpack` 在背包被扔到地上后仍会返回 `true`。
- 实际后果：`SyncVisual:1203-1206` 的“自动解除隐藏”分支不会触发，`DestroyReplacement:1176-1180` 的 `gameHidIt` 也为真 → 切到 Vanilla 时**不会**恢复原版渲染器。但这**与游戏自身行为一致**：游戏侧 `HideRenderers`（`Item.cs:783-789`）把 `enabled = false` 后同样从不恢复，`PutInBackpackRPC` 只在 `IsOnMyBack()` 为真时隐藏（`Item.cs:1299-1302`）。所以这是“复刻游戏行为”，不是本模组引入的偏差。
- 结论：**不是缺陷**，但判据的粗糙度值得记录；`SyncVisual` 注释 1196-1202 声称的“地面背包里的玩偶应该是可见的”这一意图，与 `IsOnMyBack` 的实际语义不完全吻合（属于注释与实现之间的措辞落差，而非可复现故障）。
- 建议修法（仅描述）：若要让 1196-1202 的意图真正落地，`IsWornBackpack` 应同时校验 `item.itemState == ItemState.InBackpack` 与背包的当前穿戴状态（例如 `BackpackReference.TryGetBackpackItem` + `Backpack.IsWorn()` 之类）。**不建议**仅为消除这个落差而改动，因为当前行为与游戏一致。**红线**：本修法不触碰 `HoldOffsetFor` / `ResolveVisualParent` / `Hand_L`/`Hand_R`。
- 交叉验证请求：`item.backpackReference` 是否真的没有重置点、以及 `itemState` 的 `Ground` 值由何处写入（`grep` 显示全仓库只有 `Item.cs:730` 一处赋值），建议由 task-4（游戏侧集成事实核验）确认；若确认存在重置点，本条完全闭环。

#### M5-3（低）`SetVanillaRenderersEnabled` 与游戏 `HideRenderers` 对“子物体未激活”的处理不一致，导致隐藏后再显示时替换模型可能仍是关闭的

- 位置：`PlushieModel.cs:1366-1381`（mod 侧用 `GetComponentsInChildren<Renderer>(true)`，**包含未激活**）对比游戏侧 `Item.cs:783-789`：
  ```
  private void HideRenderers()
  {
      GetComponentsInChildren<Renderer>().ForEach(delegate(Renderer meshRenderer)
      {
          meshRenderer.enabled = false;
      });
  }
  ```
  游戏侧**不含** `includeInactive`（默认 false），只枚举**激活**的渲染器。
- 现象与判定：mod 侧的 `(true)` 是**更彻底**的做法（把未激活子物体上的渲染器也关掉），方向正确。但在“隐藏 → 恢复”的路径上，`ClearGameRuleHide`（1461）用 `root.GetComponentsInChildren<Renderer>(true)` 把根下**所有**渲染器重新 `enabled = true`，这与游戏侧的“只处理激活物体”不同——不过因为目标根在 1454 已被 `SetActive(true)`，方向一致。**未发现实际错误**，记录为“两侧语义不同但各自自洽”。
- 需要注意的真实后果：游戏的 `HideRenderers` 不会关闭**未激活**子物体上的渲染器，所以如果替换根当时是 `activeSelf == false`，游戏侧**根本没碰到**替换模型的渲染器。这正是 mod 侧必须自己管 `HiddenByGameRule` 的原因（`HideForGameRule` 1429-1433 显式 `SetActive(false)`）——逻辑是自洽的。

#### M5-4（低）`ScaleForState` 的 `Mathf.Clamp(0.2f, 4f)` 与配置项 `AcceptableValueRange(0.3f, 3f)` 不一致（代码更宽松，安全）

- 位置：`PlushieModel.cs:1488`（clamp 0.2~4）对比 `Plugin.cs:187`、`192`（`AcceptableValueRange<float>(0.3f, 3.0f)`）
- 现象：配置界面限制 0.3~3.0，而 `ScaleForState` 兜底限制 0.2~4.0。若用户**直接编辑 cfg 文件**写入 10.0（BepInEx 的 `AcceptableValueRange` 只在游戏内设置界面生效，手改文件会被读取），`ScaleForState` 会把它夹到 4.0。
- 判定：**这是正确的双层防御**（界面软限制 + 代码硬夹取），不是缺陷。记录以说明“边界值已被覆盖”。
- 补充：`HoldOffsetFor` 收到的 `scale` 也来自这里，所以 `scale ∈ [0.2, 4]`，`waistMid * scale` 不会溢出。`HoldOffsetEntry` 范围 `(-0.4, 0.4)`（`Plugin.cs:200`）是直接加在 `localPosition.y` 上的（1259），也不会造成异常数值。

#### M5-5（低）`ApplyCookTint` 写入 `_BaseColor` 与 `_EmissionColor`，但材质的 albedo 实际来自 `_BaseMap` 贴图——两者是**相乘**关系，注释未说明

- 位置：`PlushieModel.cs:1319`（`_BaseColor`）、`1323`（`_EmissionColor`）、对比 `407-419`（贴图绑定到 `_BaseMap` / `_MainTex`）
- 现象：注释 1288-1291 说“the cook factor is applied to `_BaseColor`”，逻辑上 URP/Lit 的最终 albedo 是 `_BaseColor * _BaseMap`，所以乘上 `GetCookColor` 确实能正确变暗——**行为正确**。同理 emission 是 `_EmissionColor * _EmissionMap`，注释 1321-1322 的断言也成立（`GetCookColor(0) == Color.white`，实测 `ItemCooking.cs:136-138` 确认 `cookAmount == 0` 时 `result = Color.white`）。
- 判定：**不是缺陷**。记录为“注释未点明是相乘，但结论正确”。
- 一个真实的细节风险：`marker.CookBlock.SetColor(EmissionColorId, BaseEmissionColor * cook)`（1323）写入的是 `_EmissionColor`，而**材质侧**的 `_EmissionColor` 是 `BaseEmissionColor`（443）。两者一致，因此“未烹饪时乘 1 恢复原值”成立。**核对通过**。

#### M5-6（低）`ApplyCookTint` 使用 `marker.BodyRenderer`，但 `DestroyReplacement` 后该引用可能指向已销毁对象——由 Unity 伪 null 兜住

- 位置：`PlushieModel.cs:1297-1301`
- 现象：`marker.BodyRenderer` 在 966 赋值。若视觉根被销毁（`DestroyReplacement`），`marker` 本身也随 GameObject 一起销毁，`SyncVisual` 不会再用到它（`FindVisualRoot` 会返回 null）。行 1298 `if (renderer == null) return;` 依赖 Unity 伪 null。
- 判定：**正确**。`MeshRenderer` 被销毁时 `== null` 为真。记录为伪 null 的正确用例。

#### M5-7（低）`HideForGameRule` / `ClearGameRuleHide` 在 `item == null` 时早退，但未检查 `item.gameObject == null`

- 位置：`PlushieModel.cs:1418-1434`、`1436-1469`
- 现象：两处只查 `item == null`（1420、1438），随后 `GetItemState(item)`（1424）内部有 `gameObject == null` 保护（871），所以**这条路径是安全的**；但 `FindVisualRoot(item)`（1429、1447）没有该保护（见 M4-8）。
- 判定：与 M4-8 同源，不重复计数；修法同 M4-8（把保护下沉到 `FindVisualRoot`）。

#### M5-8（低）`ClearGameRuleHide` 在 `itemState == null` 时仍继续执行，逻辑正确但注释未覆盖

- 位置：`PlushieModel.cs:1442-1455`
- 现象：`itemState` 为 null（物品上还没有 `PlushieItemState` 组件）时跳过标记清除，但仍会重新激活视觉根（1452-1455）。这是正确行为（无标记 = 未隐藏）。
- 判定：**不是缺陷**。

#### M5-9（信息）文件末尾无 `#region` / 无未闭合结构，1491 行处正常结束

- 位置：`PlushieModel.cs:1490-1491`
- 判定：`}` 关闭 `PlushieModel` 类与命名空间。结构完整。

#### M5-10（低｜冗余分配）`Asset` 的原始数组与 `Mesh` 的副本同时常驻，每个变体多占约 0.7 MB

- 位置：`PlushieModel.cs:70-81`（`LoadedAssets` 与 `CachedMeshes`/`CachedOutlines` 并存）
- 现象：`PsMeshReader.Asset.SubMeshes`（`PsMeshReader.cs:40-54`）持有 `Positions` / `Normals` / `Uvs` / `Colours` / `Indices` 原始数组；`BuildMesh`（285-289）又新建了一份同样大小的数组交给 `Mesh`。`LoadedAssets`（185）与 `CachedMeshes`（233）都长期持有，因此**每个变体的顶点数据在托管堆与 native 侧各存一份**。
- 量级：约 1.5 万顶点 × (12+12+8+16) 字节 ≈ 0.72 MB/变体，两个变体约 1.4 MB（**纯托管**，会被 GC 视为长期存活对象，推高 GC 的存活集）。
- 根因：`Asset` 被保留是为了 `HoldOffsetFor`（需要 `GripLeft`/`GripRight`/`HasGrips`）、`BakedOutlineThickness`、`OutlineWidths` 与 `SubMeshes.Length`（187-190 的日志）。**只需要少数字段，却保留了全部顶点数组。**
- 证据：`PlushieModel.cs:185`（`LoadedAssets[variant] = asset`）、`230-235`（`BuildMesh` 两次，各自分配新数组）、`PsMeshReader.cs:40-48`（SubMesh 字段）。
- 判定：低（约 1.4 MB，一次性）。但若将来支持更多变体，会线性增长。
- 建议修法（仅描述）：`BuildMesh` 完成后，把 `Asset.SubMeshes` 的 `Positions` / `Normals` / `Uvs` / `Colours` / `Indices` 置 null（保留 `GripLeft`/`GripRight`/`Bounds`/`OutlineWidths`/`BakedOutlineThickness`），或让 `Asset` 只保留元数据。注意 `OutlineWidths` 必须保留（`Attach` 用它，`PlushieOutline.cs:115`）。

#### M5-11（信息）`ToWorkingColor` 在 `BuildMesh` 中对每个顶点调用，语义正确

- 位置：`PlushieModel.cs:302`、`643-646`
- 判定：注释 638-641 说颜色来自 3MF 的 sRGB 十六进制值、需要在 Linear 空间转换。`Color.linear` 做的是 sRGB→Linear 的幂次转换，与断言一致。**正确**。仅开销问题见 M3-9。

## 2. 静态缓存与生命周期

`PlushieModel` 是一个 `static class`，全部缓存都是 `static readonly`，生命周期 = 进程生命周期。

| 缓存 | 行号 | 内容 | 有释放路径？ | 判定 |
| --- | --- | --- | --- | --- |
| `LoadedAssets` | 70-71 | `PsMeshReader.Asset`（含全部顶点数组） | 无 | 见 M5-10：与 Mesh 副本并存，每变体多占约 0.7 MB |
| `CachedMeshes` | 72-73 | 实体 `Mesh`（每变体 1 份，全场景共享） | 无 | 共享是有意设计；进程退出即随进程消失，可接受 |
| `CachedOutlines` | 74-75 | 描边模板 `Mesh`（每变体 1 份） | 无 | 同上；per-instance 副本有释放（见下） |
| `CachedMaterials` | 76-77 | 正文 `Material`（每变体 1 份） | 无 | 同上 |
| `CachedOutlineMaterials` | 78-79 | 描边 `Material`（每变体 1 份） | 无 | 同上；注意 499 行的负缓存 |
| `CachedTextures` | 80-81 | 调色板 `Texture2D`（每变体 1 份） | 无 | 同上 |
| `MissingTextures` | 82-83 | 失败标记 | **无清除点** | 见 M2-1 |
| `FailedLoads` | 131-132 | 失败标记 | 有（186）但**不可达** | 见 M1-1 |
| `TrackedItems` | 84 | `List<Item>` | 有（698 清空、733-739 剪枝） | 正确 |

**真正被释放的资源**（与上表对照，说明作者对“Unity 不 GC Mesh”是清楚的）：
- `PlushieModel.cs:496`：无法剔除正面时销毁临时材质（正确）
- `PlushieModel.cs:947`：`asset == null` 时销毁半建的根（正确）
- `PlushieModel.cs:1046-1047`：`Attach` 拒绝时销毁 per-instance 描边 mesh 与对象（正确，见 M4-3 交叉验证）
- `PlushieModel.cs:1168`：销毁视觉根 GameObject
- `PlushieOutline.cs:144-155` `ReleaseMesh` + `163-166` `OnDestroy`：**唯一**销毁 per-instance 描边 mesh 的地方，且有双路径覆盖（`DestroyReplacement` 主动调用 + 组件 `OnDestroy` 兜住“游戏自己销毁物品”）

**结论**：静态缓存**不构成无界泄漏**。每个变体最多 1 份实体 mesh + 1 份描边模板 mesh + 2 个材质 + 1 张贴图，共 2 个变体；per-instance 的描边 mesh 有明确释放路径。切场景时静态字典持有对象不被 `Resources.UnloadUnusedAssets` 回收，这正是跨场景复用**需要**的行为。唯一的建议是进程退出钩子统一释放（可选），以及 M5-10 的内存瘦身。

## 3. 每帧路径与 GC 压力

`Plugin.LateUpdate`（`Plugin.cs:427-438`）→ `PlushieModel.Tick()`（98-121）→ 每帧无条件执行 `MaintainTrackedItems()`（725-780）。

每帧、每个被追踪物品的确定性工作：

| 步骤 | 行号 | 成本 | 分配 |
| --- | --- | --- | --- |
| 剪枝 null 项 | 733-739 | 倒序索引遍历 | 无 |
| `FindVisualRoot(item)` → `GetComponentsInChildren<PlushieVisualMarker>(true)` | 752 → 663-664 | **全 item 子树遍历** | **1 个数组** ← M3-1 |
| `root.GetComponent<PlushieVisualMarker>()` | 754 | 1 次 native 查询 | 无 |
| `SyncVisual` → `GetItemState` → `GetComponent<PlushieItemState>()` | 757 → 1191 → 875 | 1 次 native 查询 | 无 |
| `SyncVisual` → `ApplyCookTint` → `ReadCookedAmount` → `GetData<IntItemData>` | 1229 → 1303 → 1343 | 泛型字典查找 + try 块 | 无 ← M5-1 |
| `ScaleForState` → 读配置项 | 1231 → 1476-1482 | 属性读取 + `Mathf.Clamp` | 无 |
| `HoldOffsetFor`（仅 Held） | 1256 | 几次向量运算 | 无 |
| `SetVanillaRenderersEnabled` | 1216-1222 | **被闩锁挡住，稳态不执行** | — ← 见 M3-2 修正 |

每 0.5 秒一次（`RescanInterval`，68 行）：`GameHelpers.AllItems()`（771）遍历游戏物品列表并对每个 BingBong 调 `EnsureTracked` + `ApplyToItem`。

**GC 压力结论**：稳态下每帧的主要分配是 `FindVisualRoot` 里的 `PlushieVisualMarker[]`（每物品 1 个）。以场上 1~2 个玩偶计，这是**小额但恒定**的分配，会持续推高 GC 触发频率，属于本文件最值得优化的每帧开销（M3-1）。其余每帧调用基本无分配。

`GameHelpers.AllItems()`（`GameHelpers.cs:107-147`）在反射字段可用时**不分配**（直接返回游戏列表）；仅在两者都失败时才走 `FindObjectsOfType<Item>()` + `new List<Item>`（130-146），属于罕见的兜底路径。

## 4. 空引用与 Unity 伪 null

文件内 `item == null` / `gameObject == null` 的检查点（实测 grep）：
`659`、`750`、`816`、`871`、`905`、`913`、`1136`、`1337`、`1394`、`1420`、`1438`

- **双检查（`item == null || item.gameObject == null`）**：816、871、1337 —— 这三处是**最规范**的写法。
- **单检查**：659（`FindVisualRoot`）、1136（`DestroyReplacement`）、1394（`IsWornBackpack`）、1420（`HideForGameRule`）、1438（`ClearGameRuleHide`）。
  - 1420 / 1438 后续调用 `GetItemState`（内部有双检查）与 `FindVisualRoot`，风险与 659 同源 → 见 M4-8。
  - 1394 `IsWornBackpack` 后续访问 `item.backpackReference`（1400），若 `item` 已销毁会抛异常，但整个方法体在 try/catch 内（1398-1415），会被吞掉并返回 false。**安全**。
- **正确的伪 null 用例**：1298 `if (renderer == null) return;`（`marker.BodyRenderer` 随根销毁而失效，见 M5-6）；750 `if (item != null)`（每帧剪枝）。
- **`item.gameObject == null` 的实际价值**：Unity 中 `Destroy` 后组件本身 `== null` 即为真，因此 1136 等单检查在实践中已能挡住“已销毁物品”。`GetItemState` 注释 865-870 描述的是一个理论中间态。结论：双检查是**更好的防御**，但未发现单检查导致的可复现空引用（M4-8）。

**未发现真正的空引用缺陷**。`GetMaterial` / `GetOutlineMaterial` / `GetMesh` / `BuildVisual` 的 null 传播链（383-387 → 920-923 → 846-854）是完整的。

## 5. 时序与帧边界

本文件对“`Object.Destroy` 延迟到帧尾”这一 Unity 语义的处理是**全文最扎实的部分**：

1. **`Destroying` 标记**（54 行，置位 1149，检查 667）：`DestroyReplacement` 在调用 `Destroy` **之前**先把标记置位，因此同一帧内后续的 `FindVisualRoot` 会跳过这个“已排队销毁但仍存在”的根，不会把它当成活的复用。注释 50-53、1144-1145 说明了理由。**正确。**
2. **改名辅助**（1151）：`PlushieSwap_Visual_Destroying`，与 1 配合。
3. **`FindVisualRoot` 用组件查找而非 `transform.Find`**（注释 652-655）：因为根挂在 `Holder` 下、且名字可能已改。**正确。**
4. **同帧重建**：`ApplyToItemUnsafe` 在发现变体不符时（839-844）先 `DestroyReplacement` 再把 `root`/`marker` 置 null，随后（846-854）立刻 `BuildVisual` 建新根。同一帧内旧根（已标记 `Destroying`）与新根**共存**，直到帧尾旧根被回收。这是**必要**的（否则要等下一帧才有模型），且因为旧根已 `SetActive` 之外的标记与改名，不会被误认为有效根。**正确。**
5. **per-instance 描边 mesh 的释放时序**（1158-1166）：在 `Destroy(existing.gameObject)`（1168）**之前**先 `ReleaseMesh()`，避免依赖 `OnDestroy` 的执行时机。同时 `PlushieOutline.OnDestroy`（163-166）提供第二道保险。**双路径，正确。**

**未发现时序缺陷。** 唯一的观察是 M3-3（硬刷新时对同一物品重复调用 `DestroyReplacement`），幂等所以无害。

## 6. 边界值

| 边界条件 | 代码位置 | 实测/推理结论 | 判定 |
| --- | --- | --- | --- |
| `World Scale` 极值 | 1488 `Mathf.Clamp(0.2f, 4f)` vs `Plugin.cs:187` 范围 `0.3~3` | 双层防御；手改 cfg 到 10.0 也会被夹到 4.0 | **安全** |
| `Backpack Scale` 极值 | 1488（同一函数）vs `Plugin.cs:192` | 同上 | **安全** |
| `Hold Height Offset` 极值 | 1259，`Plugin.cs:200` 范围 `±0.4` | 直接加在 `localPosition.y`，无异常数值 | **安全** |
| `scale == 0` | 1127 `anchorMid - waistMid * scale` | 退化为 `offset = anchorMid`，模型本就不可见 | **无害** |
| 空网格 / `parts.Count == 0` | 273-276 返回 null → 224-228 → 920-923 返回 null | `BuildVisual` 早退，不建根；但 null 会被缓存进 `CachedMeshes`（M1-2） | **可接受** |
| `asset == null` | 942-949 | 显式防御 + 销毁半建根 | **正确** |
| 缺贴图 | 361-365 → 404-419 跳过绑定 | 降级为无 AO，仍可显示 | **安全** |
| `BakedOutlineThickness == 0` | 1010-1011 `asset.BakedOutlineThickness > 0f` | 不建描边对象（正确：0 表示文件无描边） | **正确** |
| `OutlineWidthPixels == 0` | 1010 `Plugin.OutlineWidthPixels > 0f` | 不建描边对象；`Plugin.cs:311-325` 在 0→正数时触发硬重建来补建 | **正确** |
| `OutlineWidths` 长度不匹配 | `PlushieOutline.cs:84-90` | 警告 + 降级为均匀线宽，不返回 null | **正确**（M4-3 补充） |
| `OutlineWidths == null` | `PlushieOutline.cs:106` `widths != null ? widths[i] : 1f` | 兼容旧文件 | **正确** |
| `vertexCount > 65000` | 282 | 切 UInt32，阈值偏保守 | **正确**（M1-5） |
| 顶点数 `int` 溢出 | 258-271 | 需恶意构造文件才可能；内嵌资源约 1.5 万顶点 | **不可达**（M2-7） |
| 未知 `PlushieVariant` | 151-153 | 依赖 `Variants.Get` 不返回 null | **低风险**（M1-4） |
| `ShaderOverride` 指向不可用 shader | 599-610 | 记 warn 后回落候选列表 | **正确** |
| 无任何可用 shader | 630-631 | 记 Error，返回 null → `GetMaterial` 返回 null → 不建根 | **正确**（不崩溃） |
| 无可用 unlit shader | 587-589 | 回落 `ResolveShader()`（lit ink），记 warn | **正确**（但见 M2-4） |
| `Variants.Get(variant)` 返回 null | 151 | 无防御 | **低风险**（M1-4） |

## 7. 异常处理

文件内的 try/catch 分布（`grep`）：

| 位置 | 作用域 | 是否吞真错误？ | 判定 |
| --- | --- | --- | --- |
| 198-210 `TryParseAsset` | `PsMeshReader.Read` | 记 `DiagnosticLog.Error` 含完整 `ex`，**不吞** | **正确** |
| 801-812 `ApplyToItem` | 整个 `ApplyToItemUnsafe` | 记 Error 含完整 `ex`；理由（797-800）充分（在游戏 `Equip` 调用栈内） | **正确** |
| 1341-1354 `ReadCookedAmount` | `item.GetData<IntItemData>` | 记 Warn（`ex.Message`，非完整栈），降级为 0 | **正确**，但见下 |
| 1398-1416 `IsWornBackpack` | `item.backpackReference` 读取 | 记 Warn（`ex.Message`），降级为 false | **正确**，但见下 |
| `Plugin.cs:429-438` | 整个 `Tick` | 记 Error 含完整 `ex` | **正确**，见 M3-5 |

**评估**：
- 没有发现“静默吞掉异常”的 `catch { }`（唯一一个空 catch 在 `GameHelpers.cs:142-145`，属于 task-2 范围）。
- 两处只记 `ex.Message`（1350、1412）而丢掉堆栈：对**可预期**的失败（数据缺失、引用失效）这是合理取舍——避免日志噪音；但如果实际是代码 bug（例如 `GetData` 的泛型约束问题），堆栈会丢失。**定低，建议改为 `ex` 或加 `Diag` 级别输出完整异常。**
- `ApplyToItem` 的 try/catch 会吞掉一切异常并只记日志：这是**有意**的（mod 不能弄坏游戏装备流程），且记的是完整 `ex`，可接受。但要注意：如果 `ApplyToItemUnsafe` 在**建根之前**抛异常，玩家的玩偶会静默保持原版外观，只有日志里有线索 —— 这与 `VerboseLogging` 默认 false（`Plugin.cs:229-231`）叠加后，普通玩家可能什么都看不到。**建议**：把这类失败提升为无条件 Error（当前 809 已经是 `DiagnosticLog.Error`，不受 Verbose 影响，**已正确**）。

## 8. 注释与代码一致性 / 死代码

**逐条核对结论（注释断言 → 实测）**：

| 注释 | 行号 | 断言 | 核对结果 |
| --- | --- | --- | --- |
| `FailedLoads` 说明 | 124-130 | “remembered … only until the next successful one” | **不符**：Remove 不可达（M1-1） |
| `Material.color` 不用 | 389-393、483-484 | `_Tint` 在 URP/Lit 上不存在、会报错 | **成立**：代码确实全程用 `HasProperty` 门控，全文无 `.color =`（实测 grep） |
| 描边必须能剔除正面 | 490-492 | 不能剔除就跳过描边 | **与代码一致**（493-501） |
| 顶点不共享 | 1001-1003 | 每实例一份描边 mesh | **成立**（1022） |
| 宽度 0 检查在建对象之前 | 1005-1009 | 否则泄漏 mesh | **成立**（1010 在 1012/1018 之前） |
| 不改 `item.mainRenderer` 的三条理由 | 968-996 | ①URP/Lit 无 `_Interactable` ②会覆盖 cook tint ③`Item.Center()` 喂给玩法 | **成立**：实测 `Item.cs:660-667` `Center()` 确实返回 `mainRenderer.bounds.center`，`Item.cs:209/505-510` `mainRenderer` 来自 `GetComponentInChildren`；`Item.cs:1142/1152` `HoverEnter/Exit` 确实写 `mainRenderer.SetPropertyBlock(mpb)` |
| `GetCookColor` 数值 | 1285-1286 | 1=`(0.66,0.47,0.25)`、2=一半、3+=`(0.05,0.05,0.1)`、0=白 | **全部成立**：实测 `ItemCooking.cs:38` `DefaultCookColorMultiplier=(0.66,0.47,0.25)`、`BurntCookColorMultiplier=(0.05,0.05,0.1)`、`GetCookColor` 136-146 |
| `GetCookColor(0)` 为白 | 1321-1322 | 未烹饪时乘 1 恢复原值 | **成立**（`ItemCooking.cs:136-138`） |
| `Item.GetData` 永不返回 null | 1331 | 会注册默认条目 | **成立**：`Item.cs:1217-1238`，`data == null` 时新建，`TryGetDataEntry` 失败时 `RegisterNewEntry` |
| `Holder` 静止时单位变换 | 893-896 | 平时无代价 | **未独立验证**（需 prefab 实测，属 task-4） |
| 锚点常量 | 1121-1124 | 来自 `BingBong_Prop Variant` | **与 README:103 一致**；需 task-4 用 prefab 复核 |
| `HoldOffsetFor` 公式 | 1095 vs 1127 | `anchorMid - scale * waistMid` | **一致**（M4-6） |
| `IsOnMyBack` 语义 | 1387-1390 | “false for a backpack lying on the ground” | **不精确**：实测 `BackpackReference.cs:84-91` 只查 `type`/`IsMine`（M5-2） |
| `HideRenderers` 从不恢复 | 1197-1198 | 游戏从不把 renderer 打开 | **成立**：实测 `Item.cs:783-789` 只有 `= false`，全文件无 `= true` |
| `forceScale` 0.5 | 1485-1487 | 游戏把背包物品缩到 0.5 | **成立**：`Item.cs:740-743` `transform.localScale = Vector3.one * 0.5f` |
| `Destroying` 理由 | 50-53、1144-1145 | `Destroy` 延迟到帧尾 | **成立**（M5 章第 5 节） |
| 描边驱动在 `OnDestroy` 也释放 | 1156-1157 | 覆盖游戏自己销毁物品 | **成立**（`PlushieOutline.cs:163-166`） |
| `SetVanillaRenderersEnabled` 不能恢复 | 1457-1460 | 它故意跳过替换模型的 renderer | **成立**：1372 `IsPlushieTransform` 跳过 |
| `indexFormat` 阈值 | 282 | — | 保守但安全（M1-5） |

**死代码 / 冗余**：
1. **M4-4**：`PlushieModel.cs:942-949` 的 `asset == null` 分支不可达（但作为契约显式化可保留）。
2. **M1-4 相关**：无。
3. **M3-3**：`RefreshAll` 的 694-698 与 699-705 两段清理重复（第二段是超集），第一段是**冗余代码**。
4. `PlushieModel.cs:1253-1265` 的 `localPosition` 逻辑：`Vector3 localPosition = Vector3.zero;` 后仅在 `Held` 时赋值，写法清晰，非死代码。
5. **未发现**未使用的私有方法或字段。`VisualRootName`（64）、`VisibleLayer`（65）、`HolderName`（901）都被使用；`BaseEmissionColor`/`BaseColorId`/`EmissionColorId`（1361-1363）都被使用。

## 9. 性能热点

按影响排序：

| # | 位置 | 频率 | 成本 | 发现 |
| --- | --- | --- | --- | --- |
| 1 | 752 → 663-664 `FindVisualRoot` → `GetComponentsInChildren<PlushieVisualMarker>(true)` | **每帧 × 每物品** | 全 item 子树遍历 + 1 个数组分配 | **M3-1** |
| 2 | 1229 → 1303 → 1343 `ApplyCookTint` → `ReadCookedAmount` → `GetData<IntItemData>` | **每帧 × 每物品** | 泛型字典查找 + try 块 | **M5-1** |
| 3 | 1022 `Object.Instantiate(outline)` | 每实例一次 | 复制约 1.5 万顶点 mesh（~1 MB） | **M4-2** |
| 4 | `PlushieOutline.LateUpdate` 每帧重写全部顶点 | 每帧 × 每实例 | 约 1.5 万顶点 CPU 重算 + `mesh.vertices` 上传 | 属 task-8 范围，README:186 已承认 |
| 5 | 1368 `SetVanillaRenderersEnabled` | 状态切换时 | 全子树遍历 + 数组分配 | M3-2（**不是**每帧） |
| 6 | 694-705 重复 `DestroyReplacement` | 硬刷新时 | 重复全子树搜索 + `new List<Item>` | **M3-3** |
| 7 | 302 `ToWorkingColor` 逐顶点读 `QualitySettings.activeColorSpace` | 构建时 | 每顶点一次 native 属性读取 | M3-9（构建期，可忽略） |
| 8 | 592-632 `ResolveShader` 失败不缓存 | 每次 `GetMaterial` 失败时 | 候选 `Shader.Find` 循环 | M2-2 |

**未发现**无界增长的热点。热点 #1、#2 是“每帧小额、恒定”，#3、#4 是“设计必需的成本”。

## 10. 红线相关的修法约束

本报告严格遵守 README 与代码注释声明的红线。**以下修法建议已被明确排除或标注**：

| 红线 | 本报告的处置 |
| --- | --- |
| **不得改 `HoldOffsetFor` 公式**（1114-1132） | **未提出任何修改**。M4-6 仅记录“注释与代码一致、常量与 README 一致”的核对结果。M5-4 只确认其输入 `scale` 被夹在 `[0.2, 4]`。 |
| **不得改 `ResolveVisualParent`（挂 Holder）** | **未提出修改挂载决策**。M4-1 仅建议在 913 的降级分支**加一条日志**（不改挂载逻辑），且明确标注触碰红线风险，建议由用户决定是否采纳。 |
| **不得写 `Hand_L` / `Hand_R` 节点** | 全文**无任何**建议写这两个节点。M5-2、M4-6 的说明均强调“锚点保持原版数值不动”，与 1066-1070、1240-1248 的注释一致。 |
| **不得恢复任何手部收拢/锚点代码** | 全文**无任何**此类建议。 |

其它与红线相邻的建议（均**不**触碰上述四条）：
- M3-1 / M3-2：缓存根节点与 renderer 列表的**查找结果**（不改变挂载层级）。
- M4-8：给 `FindVisualRoot` 加 `item.gameObject == null` 检查（纯防御）。
- M5-2：`IsWornBackpack` 判据精确化（状态逻辑，与手部无关）。**建议先由用户确认再动**，因为当前行为与游戏一致。
- M1-1 / M2-1：失败标记的清除策略（与渲染逻辑无关）。

## 11. 看似问题但实际没问题

| 项 | 位置 | 为什么没问题 |
| --- | --- | --- |
| `indexFormat` 阈值 65000 ≠ 65535 | 282 | 偏保守，只会更早切 UInt32，**安全** |
| `GetMesh` 缓存 null | 219-235 | 数据只读，重试结果相同；不会“本可恢复却失败”（M1-2） |
| 静态缓存不清理 | 70-83 | 有界（2 变体），且**必须**跨场景存活；per-instance mesh 有释放路径 |
| `ToWorkingColor` 逐顶点调用 | 302 | `Color` 是 struct，无装箱；只在构建期执行（M2-6、M3-9） |
| `part` 子对象在早退路径未单独销毁 | 938-949 | 随父对象连带销毁（M4-5） |
| `Tick` 无 try/catch | 98-121 | 调用方 `Plugin.cs:429-438` 已有 try/catch（M3-5 修正） |
| `SetVanillaRenderersEnabled` 每帧遍历 | 1366-1381 | 被 `VanillaRenderersHidden` 闩锁挡住，稳态不执行（M3-2 修正） |
| `HoldOffsetFor` 在 `scale=0` 的行为 | 1127 | 数学自洽，模型不可见（M4-7） |
| `ApplyCookTint` 写 `_BaseColor` 而非贴图 | 1319 | URP/Lit 是 `_BaseColor * _BaseMap`，相乘语义正确（M5-5） |
| `ApplyCookTint` 写 `_EmissionColor` | 1323 | 与 443 行材质值一致，未烹饪乘 1 复原（M5-5） |
| `marker.BodyRenderer == null` 检查 | 1298 | 伪 null 正确用例（M5-6） |
| `driver == null` 时销毁 mesh/对象 | 1046-1047 | `Attach` 所有 null 返回都在 `AddComponent` 之前（M4-3 交叉验证） |
| `ScaleForState` clamp 与配置范围不一致 | 1488 vs Plugin.cs:187 | 双层防御，代码更宽松是**正确**方向（M5-4） |
| `_shader`/`_outlineShader` 声明在方法后 | 634-635 | C# 合法，静态字段无初始化顺序问题（M3-8） |
| `rootObject` 改名后同帧存在两个根 | 1151、846-854 | **有意为之**，旧根已标记 `Destroying`，帧尾回收（第 5 节） |
| `ClearGameRuleHide` 在 `itemState == null` 时继续执行 | 1442-1455 | 无标记 = 未隐藏，行为正确（M5-8） |
| `HideForGameRule`/`ClearGameRuleHide` 未查 `gameObject` | 1420、1438 | 后续 `GetItemState` 内部有双检查（M5-7） |
| `GetOutlineMesh` 依赖 `GetMesh` 副作用 | 238-245 | 当前逻辑正确（M1-6） |
| `_refreshRequested` 单 bool 语义 | 86-121 | 对当前用途（F7/配置变更）无影响（M1-7） |
| `_lastVariant` 初值 `Vanilla` | 89、105-110 | 启动为 Vanilla 时无需刷新，正确（M1-8） |
| 描边不共享、每实例一份 mesh | 1022 | 屏幕像素恒定宽度的**必需**代价（M4-2） |
| `SetVanillaRenderersEnabled` 用 `(true)` 而游戏用默认 | 1368 vs `Item.cs:785` | mod 侧更彻底，方向正确且各自自洽（M5-3） |
| `IsWornBackpack` 判据粗糙 | 1392-1416 | 与游戏自身行为一致，取出路径由 `SetState` Prefix 兜住（M5-2 修正） |

## 12. 结论摘要（分级清单）

### 严重（0 项）

**未发现严重缺陷。** 本文件的 null 传播、资源释放（尤其是 per-instance 描边 mesh 的双路径释放）与 Unity 伪 null 处理整体是扎实的。初稿中曾判定为“严重/中”的三项（`Tick` 无异常保护、背包取出永久隐形、`Attach` 部分失败）经反编译与交叉验证后**均被推翻或降级**，详见 M3-5、M5-2、M4-3。

### 中（4 项）

| ID | 标题 | 位置 | 要点 |
| --- | --- | --- | --- |
| **M3-1** | 每帧每物品一次 `GetComponentsInChildren<PlushieVisualMarker>(true)`，全子树遍历 + 数组分配 | 752 → 663-664 | **最高优先级性能问题**：每帧恒定 GC 压力 |
| **M1-1** | `FailedLoads` 一旦加入永不清除，注释声称的恢复路径不可达 | 131-132、146、186 | 瞬时读取失败 → 本局永久回退原版 |
| **M2-1** | `MissingTextures` 无清除点，本局内无法恢复 | 337-340、363 | 永久缺失 AO 阴影（视觉降级） |
| **M5-1** | `ApplyCookTint` 的早退在读取之后，每帧仍走 `GetData<IntItemData>` | 1229 → 1303 → 1343 | 每帧 × 每实例的确定性开销 |

### 低（27 项）

| ID | 标题 | 位置 |
| --- | --- | --- |
| M1-2 | `GetMesh` 缓存 null，与 `GetAsset` 的非空判断不一致 | 219-235 |
| M1-3 | 静态 Mesh/Material/Texture 缓存无进程退出统一释放（有界，非泄漏） | 70-83 |
| M2-2 | `GetMaterial` 着色器解析失败不缓存，失败时重复 `Shader.Find` | 383-387 |
| M2-3 | `GetOutlineMaterial` 负缓存与 `GetMaterial` 不一致（此处反而正确） | 493-501 |
| M2-4 | `ResolveOutlineShader` 兜底分支不写 `_outlineShader`，warn 会重复 | 587-589 |
| M2-5 | `GetMaterial` 未关 `_SURFACE_TYPE_TRANSPARENT`，与描边材质不对称 | 429 vs 535 |
| M2-7 | `BuildMesh` 顶点数 `int` 累加理论上可溢出（实际不可达） | 258-271 |
| M3-2 | （**修正后降级**）`SetVanillaRenderersEnabled` 非每帧，仍有数组分配 | 1216-1222、1368 |
| M3-3 | `RefreshAll` 对同一批物品重复调用 `DestroyReplacement` | 694-705 |
| M3-4 | 在游戏自身列表上做索引遍历（共享可变集合） | 688、714-722、771-779 |
| M3-5 | （**修正后降级**）`Tick` 无 per-item try/catch，异常会中止同帧其余物品 + 刷屏 | 98-121、725-780 |
| M3-6 | `ShaderOverride` 变更不使 `_shader`/材质缓存失效 | 592-635 |
| M3-9 | `ToWorkingColor` 逐顶点读 `QualitySettings.activeColorSpace` | 302、643-646 |
| M4-1 | `ResolveVisualParent` 的 Holder 缺失降级无日志（**红线相邻，仅建议加日志**） | 907-913 |
| M4-2 | 每实例一份描边 mesh 的内存/CPU 成本（设计必需） | 1022 |
| M4-4 | `BuildVisual` 的 `asset == null` 分支为死代码（可保留） | 942-949 |
| M4-8 | `FindVisualRoot` 未做 `gameObject == null` 双检查（防御性不一致） | 659 vs 871 |
| M4-9 | `DestroyReplacement` 用全子树 `GetComponentsInChildren<PlushieOutline>` 找唯一子对象 | 1158-1166 |
| M4-11 | 硬刷新时重复 `SetVanillaRenderersEnabled`（与 M3-3 叠加） | 1175-1180 |
| M5-2 | `IsWornBackpack` 判据不精确（与游戏行为一致，非缺陷） | 1392-1416 |
| M5-3 | mod 侧与游戏侧对“未激活子物体”的渲染器枚举语义不同（各自自洽） | 1368 vs `Item.cs:785` |
| M5-4 | `ScaleForState` clamp 与配置范围不一致（代码更宽松，安全） | 1488 |
| M5-5 | `ApplyCookTint` 写 `_BaseColor`/`_EmissionColor` 的相乘语义未在注释点明 | 1319、1323 |
| M5-6 | `marker.BodyRenderer` 失效依赖伪 null 兜住 | 1297-1301 |
| M5-7 | `HideForGameRule`/`ClearGameRuleHide` 未查 `gameObject`（与 M4-8 同源） | 1420、1438 |
| M5-8 | `ClearGameRuleHide` 在 `itemState == null` 时仍继续执行（逻辑正确） | 1442-1455 |
| M5-10 | `Asset` 原始顶点数组与 `Mesh` 副本并存，每变体多占约 0.7 MB | 70-81、285-289 |

### 信息 / 非问题（16 项，记录以免重复怀疑）

M1-4（`Variants.Get` 永不返回 null，**已核实**）、M1-5（`indexFormat` 阈值保守）、M1-6（`GetOutlineMesh` 副作用耦合）、M1-7（单 bool 刷新语义）、M1-8（`_lastVariant` 初值）、M2-6（`ToWorkingColor` 无 GC）、M2-8（`indexFormat` 正确）、M3-7（`GetItemState` 伪 null 双检查，**全文最佳范例**）、M3-8（静态字段声明位置）、M4-3（`Attach` 契约已验证）、M4-5（`part` 连带销毁）、M4-6（`HoldOffsetFor` 公式核对通过）、M4-7（`scale=0`）、M4-10（改名辅助）、M5-9（文件结构完整）、M5-11（sRGB→Linear 正确）。

### 给 lead 的交叉验证请求

1. **task-4（游戏侧集成事实核验）**：确认 `item.backpackReference` 是否存在重置为 `None` 的路径，以及 `ItemState.Ground` 由何处写入。`grep` 显示全仓库 `backpackReference` 只有 `Item.cs:1295` 一处写入、`itemState` 只有 `Item.cs:730` 一处赋值。若确认无重置点，M5-2 的“与游戏行为一致”结论成立（仍非缺陷），但值得在 README 的已知局限里提一句。
2. **task-8（`PlushieOutline` / `PsMeshReader`）**：M4-2/M4-3 已按 `PlushieOutline.cs:67-131` 验证 `Attach` 契约；M5-10 关于 `Asset` 内存瘦身的建议需要 `PsMeshReader` 侧确认哪些字段在运行时仍被读取。
3. **task-2（胶水层）**：M3-6 指出 `Plugin.cs` 没有 `ShaderOverrideEntry` 的变更回调；M3-5 依赖 `Plugin.cs:427-438` 的 `LateUpdate` try/catch（已核实）。
