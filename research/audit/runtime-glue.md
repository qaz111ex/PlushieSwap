# 审计 B：运行时胶水层（Plugin / Patches / CookingPatches / GameHelpers / AssetProvider / Icons / Variants / csproj）

审计范围：`src/Plugin.cs`、`src/Patches.cs`、`src/CookingPatches.cs`、`src/GameHelpers.cs`、`src/AssetProvider.cs`、`src/PlushieIcons.cs`、`src/Variants.cs`、`PlushieSwap.csproj`。
（`src/EmbeddedAssets.g.cs` 作为资源加载的对手方一并核查，因为 `AssetProvider` 的回退路径完全依赖它。）

审计方式（全部为只读）：逐行阅读 + 用 `ilspycmd` 反编译 + 用 Mono.Cecil 读**权威元数据**（比反编译文本更可靠）+ 在 `%TEMP%` 里复制工程做破坏性构建实验。**未修改 `src/` 下任何文件、未修改 csproj、未修改 `libs/`。** 所有临时副本都在 `%TEMP%`。

---

## 0. 审计基线（先说清楚证据来源）

| 项 | 值 | 命令 / 出处 |
| --- | --- | --- |
| 参考程序集来源 | `libs/Assembly-CSharp.dll` 与游戏 `PEAK_Data/Managed/Assembly-CSharp.dll` **SHA-256 完全相同** | `Get-FileHash` 对比，见 §4.1 |
| `libs/` 里全部 30 个 DLL | 与运行时（`Managed\` 或 `BepInEx\core\`）**逐一哈希相同** | §4.1 表格 |
| 反编译源码目录 | `D:\zhuanban\youhua\decompiled-latest`（与 libs 同一份 DLL 的反编译结果，已抽样比对一致） | `Item.cs` / `ItemCooking.cs` 等 |
| 权威元数据工具 | `Mono.Cecil` 直接读 `libs/Assembly-CSharp.dll` 的字段/方法表 | §2.1 |
| 实机日志 | `D:\SteamLibrary\steamapps\common\PEAK\BepInEx\LogOutput.log`（2026-09-20 0:11:48） | §3.1、§5.9 |

> **重要前提（影响所有"实机验证"结论）**：当前**已部署**的 DLL 与仓库 HEAD 不是同一个构建。
> - 已部署：`commit 59cb988`，`1.0.0+59cb9886...`，12,135,936 B，**含 `Hand Inset` 与 `Grip inset` 诊断**（UTF-16 字符串命中）。
> - HEAD `bc696a9` 构建产物：`1.0.0+bc696a91...`，12,133,376 B，**不含 `Hand Inset`/`Grip inset`**。
> - 见 §5.9。所以日志里出现的 `Hand Inset`、`Grip inset` 属于旧构建，**当前源码已无此代码**（`src/` 全库 grep 为空）。任何"当前源码是否生效"的实机结论都必须先重新部署。

---

## 1. 结论摘要（按严重度分级）

### 🔴 高
**无。** 任务要求的 9 个 Harmony 补丁目标**全部存在**、可见性与签名**全部匹配**；所有反射字段名**全部与游戏真实字段一致**；csproj 引用**没有缺失**（不存在 `MissingMethodException` 风险）。逐项证据见 §2 与 §4。

### 🟡 中（3 条）

| # | 标题 | 位置 |
| --- | --- | --- |
| M-1 | `Cycle Plush Hotkey` 用了 `KeyboardShortcut`，而游戏内的模组设置面板（PEAKLib.ModConfig）不支持该类型 → **热键在游戏内完全无法配置**，与 README 承诺矛盾（实机日志已证实） | `Plugin.cs:213-216` |
| M-2 | `PatchSafely` 的容错粒度是"整个补丁类"：类内**任何一个**目标找不到，Harmony 会在打补丁前就抛异常，**该类其余全部补丁都不会生效**，且日志不指出是哪一个目标 | `Plugin.cs:276-287` + `Patches.cs:15-69` |
| M-3 | `AccessTools.FieldRefAccess<T,F>("...")` 是静态字段初始化器，字段名写错会抛 `ArgumentException`；首次调用发生在补丁体内、且被 `[HarmonyWrapSafe]` 吞掉 → **静默失效**（CookingPatches 的 `_Tint` 修复会无声退回 Unity 报错刷屏） | `CookingPatches.cs:40-52`、`Patches.cs:167-171` |

### 🟢 低（6 条）

| # | 标题 | 位置 |
| --- | --- | --- |
| L-1 | 死代码：`GameHelpers.AnimationItemTransformOf` + `CharacterOf` + 3 个字段缓存（约 36 行）零调用；`EmbeddedAssets.Has` 零调用；`PsMeshReader.Read(string path)` 零调用 | `GameHelpers.cs:14-95`、`EmbeddedAssets.g.cs:132-135`、`PsMeshReader.cs:100-106` |
| L-2 | `UiHelpers.ResetLanguageCache()` 只在"切换玩偶"时调用，触发条件语义错误 → 菜单里改语言后显示名要等按 F7 或重启才更新 | `Plugin.cs:292`、`GameHelpers.cs:296-299` |
| L-3 | `InventoryItemUI.SetItem` 的 `isBackpack` 分支直接读 `slot.prefab.UIData.icon`（第 107 行），**绕过被 patch 的 `GetIcon()`** → 该分支不享受图标替换 | 游戏 `InventoryItemUI.cs:107` vs `:140`；`Patches.cs:94-113` |
| L-4 | csproj 的 `<Reference Include="mscorlib">` **冗余**（删掉后 csc 收到的引用集合逐字节相同）；`libs/` 里另有 **17 个未被任何 `<Reference>` 引用的 DLL 副本** | `PlushieSwap.csproj:30-33` |
| L-5 | README 自相矛盾：第 7 行说默认"米菲兔"，代码默认是 `ZichaoXiong`（第 51 行的表反而写对了） | `README.md:7` vs `Plugin.cs:181` |
| L-6 | 已部署 DLL 落后 HEAD 两个提交，实机验证必须在重新部署后进行（运维项，非源码缺陷） | §5.9 |

### ⚪ 已核实无误
共 26 项，逐条列出核实方法，见 §6。

---

## 2. 逐条详情

### 2.1 前置：补丁目标与反射字段的权威元数据核验

任务要求"必须用反编译证据核实每一个 Harmony 补丁目标"。反编译文本可能被优化改写，因此我另外用 **Mono.Cecil 直接读程序集元数据表**（这是编译产物里最权威的一层），命令与输出如下。

```powershell
Add-Type -Path "D:\SteamLibrary\steamapps\common\PEAK\BepInEx\core\Mono.Cecil.dll"
$asm=[Mono.Cecil.AssemblyDefinition]::ReadAssembly("D:\zhuanban\Plushie Swap\libs\Assembly-CSharp.dll")
# 逐类型 dump 目标方法的 Attributes / 参数表，以及目标字段的 FieldType / Attributes
```

**补丁目标（元数据输出）**

```
  Item                            Start                  Family, Virtual, HideBySig, VtableLayoutMask()
  Item                            OnEnable               Public, Virtual, HideBySig()
  Item                            SetState               Assembly, HideBySig(ItemState setState, Character character)
  Item                            HideRenderers          Private, HideBySig()
  Item                            GetName                Public, Final, Virtual, HideBySig, VtableLayoutMask()
  Item/ItemUIData                 GetIcon                Public, HideBySig  ret=Texture2D
  InventoryItemUI                 SetItem                Public, HideBySig(ItemSlot slot)
  ItemCooking                     UpdateCookedBehavior   Public, Virtual, HideBySig, VtableLayoutMask()
  BackpackOnBackVisuals           InitRenderers          Private, HideBySig()
```

**反射字段（元数据输出）**

```
  Item                    ALL_ITEMS               List`1        Public, Static
  Item                    ALL_ACTIVE_ITEMS        List`1        Public, Static
  Item                    backpackReference       Optionable`1  Public
  CharacterItems          character               Character     Private
  Character               refs                    CharacterRefs Public
  Character/CharacterRefs animationItemTransform  Transform     Public
  ItemCooking             renderers               Renderer[]    Private
  ItemCooking             defaultTints            Color[]       Private
  ItemCooking             setup                   Boolean       Private
  BackpackOnBackVisuals   renderers               MeshRenderer[] Private
  BackpackOnBackVisuals   defaultTints            Color[]        Private
  InventoryItemUI         icon                    RawImage      Public
  InventoryItemUI         _itemPrefab             Item          Private
  LocalizedText           CURRENT_LANGUAGE        Language      Public, Static
```

**结论**：`src/` 里出现的每一个类型名、方法名、字段名、字段类型，都在元数据里**原样存在**。`CharacterRefs` 是 `Character` 的**嵌套类型**（`Character/CharacterRefs`），`GameHelpers.cs:49-51` 用 `_characterRefsField.FieldType.GetField("animationItemTransform", flags)` 动态取到它的类型再找字段，**写法正确**（不是写死类型名）。`ItemState` 枚举为 `{Ground=0, Held=1, InBackpack=2}`，`Patches.cs:43` 的 `setState != ItemState.InBackpack` 语义正确。

---

### M-1（中）`Cycle Plush Hotkey` 在游戏内无法配置：`KeyboardShortcut` 不被 PEAKLib.ModConfig 支持

**file:line**：`src/Plugin.cs:213-216`（绑定）、`README.md:52,62`

**现象**：README 第 62 行承诺"在游戏内的模组设置里改动会**即时生效**"。实测：热键这一项**根本不会出现在设置面板里**。

**证据（实机日志，硬证据）**：

```
LogOutput.log:202  [Warning:PEAKLib.ModConfig] Missing SettingType: [Mod: Plushie Swap] Cycle Plush Hotkey (Type: BepInEx.Configuration.KeyboardShortcut)
```

同一日志第 392 行同时有 `Adding existing button Plushie Swap (PEAKLib.ModConfig.Components.ModdedTABSButton) to tab`，说明设置页**确实挂上了**，只是这一项被跳过。

**根因（反编译证据）**：游戏侧提供设置 UI 的是 `BepInEx/plugins/com.github.PEAKModding.PEAKLib.ModConfig.dll`。反编译后逐类型分派：

```csharp
// com.github.PEAKModding.PEAKLib.ModConfig.decompiled.cs:1062-1136
if      (configEntry.SettingType == typeof(bool))   ... AddBoolToTab
else if (configEntry.SettingType == typeof(float))  ... AddFloatToTab
else if (configEntry.SettingType == typeof(double)) ... AddDoubleToTab
else if (configEntry.SettingType == typeof(int))    ... AddIntToTab
else if (configEntry.SettingType == typeof(string)) ... AddStringToTab / AddKeyPathToTab / AddEnumToTab
else if (configEntry.SettingType == typeof(KeyCode))... AddKeybindToTab     // ← 只有 KeyCode
else if (configEntry.SettingType.IsEnum)            ... AddEnumToTab
else Log.LogWarning($"Missing SettingType: [Mod: {text}] {configEntry.Definition.Key} (Type: {configEntry.SettingType})");
```

全文件 grep `KeyboardShortcut` = **0 命中**（`Select-String -Path ... -Pattern "KeyboardShortcut"` 无输出）。即：`BepInEx.Configuration.KeyboardShortcut` 这条类型**没有任何分派分支**，必然走 `LogWarning` 并被丢弃。

**为什么 `Tags("Hidden")` 那条没事**：`Config Version` 是 `int`，有分支；它靠 `Tags` 被过滤，而 `Tags` 是 ModConfig 支持的机制——

```csharp
// ModConfig.decompiled.cs:1154-1159
ConfigDescription description = item2.Description;
object[] array = description?.Tags;
if (array == null || !Enumerable.Contains(array, "Hidden")) list.Add(item2);
```

**建议修法**（不触碰任何红线）：
1. 首选：把 `CycleHotkeyEntry` 改成 `ConfigEntry<KeyCode>`（`KeyCode.F7`），ModConfig 有现成分支（`AddKeybindToTab`）。代价：失去"修饰键组合"能力。`PlushieHost.Update`（`Plugin.cs:412-416`）改成读 `KeyCode` 并用 `Input.GetKeyDown` 即可——但注意 `Input` 属 `UnityEngine.InputLegacyModule`，当前 csproj **没有**引用它，需要补 `<Reference Include="UnityEngine.InputLegacyModule">`（该 DLL 在游戏 `Managed/` 里存在）。或者用 BepInEx 的 `UnityInput.Current.GetKeyDown(key)`（`BepInEx.dll` 已引用，无需新引用）。
2. 次选：保留 `KeyboardShortcut`，但**同时**再 Bind 一个 `KeyCode` 镜像项，两者取或。缺点是配置面变复杂。
3. 无论哪种，README 第 52/62 行都要相应改写，或明确标注"热键只能在 cfg 文件里改，游戏内面板不显示"。

> **红线检查**：不涉及 README 的任何"禁止改动"条目（不改锚点、不删面、不动音频/动画/物品逻辑）。这是新增/替换一个配置项的绑定类型。

---

### M-2（中）`PatchSafely` 是"整类全有全无"，一个目标缺失会连带丢掉该类其余全部补丁

**file:line**：`src/Plugin.cs:276-287`，配合 `src/Patches.cs:15-69`

**现象**：`Plugin.cs:272-275` 的注释写：

> "A missing game method must never take the whole mod down, so each patch class is applied on its own and failures are reported instead of thrown."

这句话本身没错，但它给人的印象是"逐个补丁独立容错"。实际粒度是**每个补丁类**，而 `Patches.ItemPatches` 一个类里塞了 **5 个补丁**（`Start`/`OnEnable`/`SetState` 前后缀/`HideRenderers`），`Patches.UiPatches` 塞了 3 个。

**根因（反编译证据）**：`Harmony.PatchAll(Type)` → `CreateClassProcessor(type, allowUnannotatedType: true).Patch()`，而 `PatchClassProcessor.Patch()` 内部先调 `PatchWithAttributes`：

```csharp
// 0Harmony.decompiled.cs:3292-3310
private List<MethodInfo> PatchWithAttributes(ref MethodBase lastOriginal)
{
    PatchJobs<MethodInfo> patchJobs = new PatchJobs<MethodInfo>();
    foreach (AttributePatch patchMethod in patchMethods)          // ← 先遍历全部补丁
    {
        lastOriginal = patchMethod.info.GetOriginalMethod();
        if ((object)lastOriginal == null)
            throw new ArgumentException("Undefined target method for patch method " + patchMethod.info.method.FullDescription());
        patchJobs.GetJob(lastOriginal).AddPatch(patchMethod);
    }
    foreach (...) ProcessPatchJob(job);                          // ← 之后才开始真正打补丁
    ...
}
```

关键点：**`throw` 发生在任何补丁被应用之前**。只要有一个目标解析为 `null`（`AccessTools.Method` 找不到方法时会 log warning 并返回 null），整个类的补丁**一个都不会打上**。异常再经 `PatchClassProcessor.Patch` 的 `catch` → `ReportException` → `throw new HarmonyException(...)`（`0Harmony.decompiled.cs:3419-3423`），最终被 `Plugin.PatchSafely` 的 `catch` 捕获，只打一条：

```
Failed to apply Item hooks (ItemPatches): ...
```

**后果举例**：假设将来游戏把 `Item.HideRenderers` 改名。那么 `Item.Start`、`Item.OnEnable`、`Item.SetState` 前后缀**全部失效**——模型再也不会被构建，而日志只说"Item hooks 失败"，不说失败在 `HideRenderers`。`HarmonyException` 的消息里确实含方法全名，但 `PatchSafely` 只打印 `ex.Message`（`Plugin.cs:285`），**丢掉了最重要的定位信息**。

**建议修法**：
1. `PatchSafely` 改为打印 `ex.ToString()`（或至少 `ex.Message + "\n" + ex.StackTrace`），保留 `HarmonyException` 内部的 `### Original: <方法全名>` 段。
2. 把容错粒度降到"每个方法"：把 `Patches.ItemPatches` 里的 5 个补丁拆成 5 个类（或用 `_harmony.Patch(AccessTools.Method(...), prefix, postfix)` 逐个 try/catch），这样丢一个只丢一个。
3. 加一条启动自检：`Awake` 末尾用 `AccessTools.Method` 逐个解析 9 个目标，缺失的用 `DiagnosticLog.Error` 明确点名。

> **红线检查**：只是错误处理与日志，不改任何游戏行为，不触碰红线。

---

### M-3（中）`FieldRefAccess<T,F>("name")` 静态初始化失败会被 `HarmonyWrapSafe` 静默吞掉

**file:line**：`src/CookingPatches.cs:40-52`、`src/Patches.cs:167-171`

**现象**：这 5 个字段引用是 `static readonly` 字段初始化器：

```csharp
// CookingPatches.cs:40-52
private static readonly AccessTools.FieldRef<ItemCooking, Renderer[]> ItemRenderers =
    AccessTools.FieldRefAccess<ItemCooking, Renderer[]>("renderers");
private static readonly AccessTools.FieldRef<ItemCooking, Color[]> ItemTints =
    AccessTools.FieldRefAccess<ItemCooking, Color[]>("defaultTints");
private static readonly AccessTools.FieldRef<ItemCooking, bool> ItemSetup =
    AccessTools.FieldRefAccess<ItemCooking, bool>("setup");
private static readonly AccessTools.FieldRef<BackpackOnBackVisuals, MeshRenderer[]> BackpackRenderers = ...;
private static readonly AccessTools.FieldRef<BackpackOnBackVisuals, Color[]> BackpackTints = ...;
```

```csharp
// Patches.cs:167-171
private static readonly AccessTools.FieldRef<InventoryItemUI, RawImage> InventoryItemIcon =
    AccessTools.FieldRefAccess<InventoryItemUI, RawImage>("icon");
private static readonly AccessTools.FieldRef<InventoryItemUI, Item> InventoryItemPrefab =
    AccessTools.FieldRefAccess<InventoryItemUI, Item>("_itemPrefab");
```

**根因（反编译证据）**：`FieldRefAccess<T,F>(string)` 在找不到字段时**抛异常**，不是返回 null：

```csharp
// 0Harmony.decompiled.cs:4649-4667
public static FieldRef<T, F> FieldRefAccess<T, F>(string fieldName)
{
    ...
    try { return FieldRefAccessInternal<T, F>(GetInstanceField(typeFromHandle, fieldName), needCastclass: false); }
    catch (Exception innerException)
    {
        throw new ArgumentException($"FieldRefAccess<{typeof(T)}, {typeof(F)}> for {fieldName} caused an exception", innerException);
    }
}
```

而类型初始化器（cctor）在**首次访问该类型的任何静态成员**时运行，也就是**第一次调用补丁方法时**。补丁方法全部带 `[HarmonyWrapSafe]`（`CookingPatches.cs:63,99`、`Patches.cs:19,27,35,51,59,80,96,131`），其语义是：

```csharp
// 0Harmony.decompiled.cs:1814-1821
public class HarmonyWrapSafe : HarmonyAttribute
{
    public HarmonyWrapSafe() { info.wrapTryCatch = true; }
}
```

`wrapTryCatch` 会把补丁体包进 try/catch（`0Harmony.decompiled.cs:7845, 8301-8340`）。于是 `TypeInitializationException`（含 `ArgumentException`）被吞掉，补丁**静默不做任何事**，只在 Harmony 的 wrapped-exception 通道留一条记录。

**为什么现在没炸**：我已用 Cecil 验证这 5 个字段名全部存在（§2.1），所以**当前不会触发**。这是一条**韧性缺陷**，不是当前 bug。

**后果**：若游戏更新改了 `renderers`/`defaultTints`/`setup` 的名字，`CookingPatches` 的 `_Tint` 修复会无声失效，Unity 的 `doesn't have a color property '_Tint'` 报错会**重新开始刷屏**（`CookingPatches.cs:17-21` 注释里描述的正是这个原始症状），而日志里不会有任何一条"Plushie Swap"的明确错误。

**建议修法**：把字段引用改成惰性解析 + 显式失败日志，例如

```csharp
private static AccessTools.FieldRef<ItemCooking, Renderer[]> _itemRenderers;
private static bool TryInitRefs()
{
    if (_itemRenderers != null) return true;
    try { _itemRenderers = AccessTools.FieldRefAccess<ItemCooking, Renderer[]>("renderers"); ... }
    catch (Exception ex) { DiagnosticLog.Error("CookingPatches 无法解析游戏字段，烹饪着色修复已停用：" + ex); return false; }
    return true;
}
```
并在补丁体首行 `if (!TryInitRefs()) return;`。这样失败会**明确出现在日志里**，而不是被 WrapSafe 吞掉。

> **红线检查**：纯错误处理，不改游戏行为。

---

### L-1（低）死代码

**file:line**：`src/GameHelpers.cs:14-21, 32-95`、`src/EmbeddedAssets.g.cs:132-135`、`src/PsMeshReader.cs:100-106`

**证据**（全仓库 `src/` + `tools/` 一起 grep）：

```
$ Get-ChildItem src,tools -Recurse -File -Include *.cs,*.py | Select-String -Pattern "AnimationItemTransformOf|EmbeddedAssets\.Has|PsMeshReader\.Read"
src\GameHelpers.cs:32:        internal static Transform AnimationItemTransformOf(CharacterItems items)
src\GameHelpers.cs:194:            string itemName = TryGetItemName(item);          # ← 这是 TryGetItemName，不是上面那个
src\PsMeshReader.cs:100:        internal static Asset Read(string path)
```

- `AnimationItemTransformOf`：**定义 1 处，调用 0 处**。连带 `CharacterOf`（`:70-95`）、`_characterRefsField` / `_refsAnimationItemField` / `_characterRefsFieldSearched`（`:17,21`）也是死代码。共约 36 行 + 一段很长的注释（`:23-31`）。
- `EmbeddedAssets.Has`：**调用 0 处**（`AssetProvider.cs:65` 只调 `EmbeddedAssets.Get`）。
- `PsMeshReader.Read(string path)`：**调用 0 处**（`PlushieModel.cs:203` 走的是 `Read(byte[], string)`）。

**注意**：`CharacterRefs.animationItemTransform` 这个**字段名**本身仍然要在 §2.1 里被核实（任务要求），因为它曾经是被使用的；结论是字段名正确，但**代码已不再使用它**。

**建议修法**：删除，或若有意保留作为将来参考，在文件头注明"当前未使用，保留原因：X"。不建议在无说明的情况下留着——下一次审计会重复核验一遍。

> 注意 `PlushieModel.cs:1400` 用的 `item.backpackReference` 与 `animationItemTransform` 无关，不要误删。

---

### L-2（低）语言缓存失效的触发条件语义错误

**file:line**：`src/Plugin.cs:289-298`（`OnVariantChanged` 里调 `UiHelpers.ResetLanguageCache()`）、`src/GameHelpers.cs:269-299`

**现象**：`Variants.DisplayName` 依赖 `UiHelpers.IsChinese()`，而 `IsChinese()` 把 `LocalizedText.CURRENT_LANGUAGE` 缓存进 `_chinese`（`GameHelpers.cs:271-274`：`if (_chineseChecked) return _chinese;`）。全仓库唯一的失效点是：

```csharp
// Plugin.cs:291-292
ActiveVariant = VariantEntry.Value;
UiHelpers.ResetLanguageCache();
```

**根因**：切换玩偶**不会**改变语言。真正需要失效的时机是玩家在菜单里改语言，而那个时机没有任何钩子。于是：玩家在菜单把语言从 English 改成 简体中文 → 玩偶名仍然显示 `Miffy`/`Zichao Xiong`，直到按一次 F7（或重启）才变成 `米菲兔`/`自嘲熊`。

**证据**：`LocalizedText.cs:74` `public static Language CURRENT_LANGUAGE = Language.English;`，`Language` 枚举含 `SimplifiedChinese` / `TraditionalChinese`（`LocalizedText.cs` 枚举定义），`GameHelpers.cs:284` 用 `language.ToString().IndexOf("Chinese", ...)` 判断——**这个判断本身是对的**（枚举名里确实含 "Chinese"），问题只在缓存失效时机。

**建议修法**：三种，按侵入性排序：
1. 最简：`IsChinese()` 每次直接读反射字段（每帧只在 `DisplayName` 被访问时调用，`Item.GetName` 频率很低，开销可忽略），去掉缓存。
2. 保留缓存但加一个短周期（例如 1 秒）过期。
3. 在 `PlushieHost.Update` 里检测 `CURRENT_LANGUAGE` 变化并 `ResetLanguageCache()`。

> **红线检查**：不触碰任何红线。

---

### L-3（低）`InventoryItemUI.SetItem` 的 `isBackpack` 分支绕过被 patch 的 `GetIcon()`

**file:line**：游戏侧 `InventoryItemUI.cs:105-107`（反编译 / libs DLL 双向确认）；本模组 `src/Patches.cs:94-113`

**证据**（libs DLL 反编译，权威）：

```csharp
// InventoryItemUI.SetItem(ItemSlot slot) —— libs DLL 第 79-148 行
if (isBackpack)
{
    ...
    icon.enabled = true;
    icon.texture = slot.prefab.UIData.icon;      // ← 第 107 行：直接读字段，不走 GetIcon()
    ...
    return;
}
...
icon.texture = _itemPrefab.UIData.GetIcon();     // ← 第 140 行：走 GetIcon()，被 patch 覆盖
```

本模组的图标替换挂在 `Item.ItemUIData.GetIcon` 上（`Patches.cs:94-97`），所以**只有第 140 行那条路径**（普通物品槽）被覆盖。`isBackpack == true` 的实例（背包槽本身）读的是裸字段，不受影响。

**影响评估**：低。`isBackpack` 槽装的是背包 prefab，不是玩偶；除非有人把玩偶塞进背包槽（游戏不允许），否则观察不到。但这是**真实的机制不对称**：`BackpackWheelSlice.cs:166`、`BackpackWheel.cs:62`、`UI_UseItemProgressFriend.cs:27` 都走 `GetIcon()`（已覆盖），只有这一处例外。

**顺带核实（任务问的"图标缓存与生命周期"）**：`AssetProvider.cs:89-91` 的注释断言"`Item.ItemUIData.GetIcon` 的消费者 `InventoryItemUI.icon` 和 `BackpackWheel*` 都是 `RawImage`"——**核实为真**：
- `InventoryItemUI.cs:11` `public RawImage icon;`
- `BackpackWheel.cs:19` `public RawImage currentlyHeldItem;`
- `BackpackWheelSlice.cs:52` `public RawImage image;`
- `UI_UseItemProgressFriend.cs:11` `public RawImage icon;`
全部是 `RawImage`，所以 `Patches.cs:152,159,163` 用 `RawImage.texture` / `.enabled` 操作是**类型正确**的。

**建议修法**：如果确实想让背包槽也换图标，可以再 patch 一次 `GetIcon` 的调用点（不现实），或者接受现状并在注释里写明"背包槽分支不走 GetIcon，故不受影响"。**不建议**为此 patch `InventoryItemUI.SetItem` 的背包分支——那会引入对 `slot.prefab` 的语义假设。

---

### L-4（低）csproj 冗余引用 + `libs/` 里 17 个未引用的 DLL 副本

**file:line**：`PlushieSwap.csproj:29-82`

**证据 A：`mscorlib` 引用冗余**

在 `%TEMP%` 里做了 2×2 矩阵实验（`<Reference Include="mscorlib">` 元素保留/删除 × `libs/mscorlib.dll` 保留/删除），并从 `-v n` 的构建日志里提取 csc 实际收到的 `/reference:` 列表：

```
baseline      elem_removed=False file_removed=False exit=0  csc_mscorlib=...\libs\mscorlib.dll
noelem        elem_removed=True  file_removed=False exit=0  csc_mscorlib=...\libs\mscorlib.dll
nofile        elem_removed=False file_removed=True  exit=1  csc_mscorlib=...\microsoft.netframework.referenceassemblies.net472\...\mscorlib.dll
neither       elem_removed=True  file_removed=True  exit=1  csc_mscorlib=...\microsoft.netframework.referenceassemblies.net472\...\mscorlib.dll
```

进一步直接 diff 两次构建的完整引用集合：

```
=== reference diff (with-element vs without-element) ===
IDENTICAL reference set (13 refs)
```

**结论**：删掉 `<Reference Include="mscorlib">` 后，csc 的引用集合**逐项完全相同**——MSBuild 把 `libs/` 当作 `AssemblySearchPaths` 的一部分（因为其它 `<Reference>` 的 `HintPath` 都在那里），所以 `mscorlib` 会被隐式解析到**同一个** `libs/mscorlib.dll`。这个元素**冗余但无害**。

**证据 B：`libs/` 里有 17 个 DLL 从未被 `<Reference>` 引用**

```
$ csproj HintPath 里出现的文件名 = 13 个；libs/ 里实际有 30 个
未引用：BepInEx.Harmony.dll, Photon3Unity3D.dll, PhotonRealtime.dll, System.Drawing.dll,
        Unity.Localization.dll, Unity.TextMeshPro.dll, UnityEngine.AnimationModule.dll,
        UnityEngine.AssetBundleModule.dll, UnityEngine.AudioModule.dll,
        UnityEngine.IMGUIModule.dll, UnityEngine.JSONSerializeModule.dll,
        UnityEngine.PhysicsModule.dll, UnityEngine.TextCoreTextEngineModule.dll,
        UnityEngine.TextRenderingModule.dll, UnityEngine.UIModule.dll,
        UnityEngine.UnityWebRequestAudioModule.dll, UnityEngine.UnityWebRequestModule.dll
```

实测把这 17 个全部删掉后构建仍然成功：

```
EXIT after removing 17 unreferenced libs DLLs = 0
```

**关于"缺失引用会不会导致运行时 `MissingMethodException`"**（任务问题 6）：**不会**，理由有两条硬证据：
1. csproj 里 13 个引用**全部是必需的**——逐个删除做构建实验，除 `mscorlib` 外全部报编译错误（`netstandard` CS1705、`System` CS1069 DeflateStream、`System.Core` CS1069 HashSet、`BepInEx` CS0246、`0Harmony` CS0246、`Assembly-CSharp` CS0246、`Zorro.Core.Runtime` CS0012 Optionable、`UnityEngine` CS0012 MonoBehaviour、`UnityEngine.CoreModule` CS1069 Texture2D、`UnityEngine.ImageConversionModule` CS1061 LoadImage、`UnityEngine.UI` CS0246 RawImage、`PhotonUnityNetworking` CS0012 MonoBehaviourPunCallbacks）。**没有一个是"删了也能编过"的**，也就没有"编译期不检查、运行期炸"的漏网引用。
2. `libs/` 里 30 个 DLL **与运行时（`Managed/` 或 `BepInEx/core/`）逐一 SHA-256 相同**（§4.1），所以编译期看到的类型布局与运行期**完全一致**，不存在版本漂移导致的 `MissingMethodException`。

**注意 `libs/` 是 gitignore 的**（`.gitignore:4` `libs/`），`git ls-files libs` 返回 0 个文件；`build.ps1` **不会**创建 `libs/`（grep `libs` 无命中），README 也**没写** `libs/` 的来源。这意味着**从零克隆的仓库无法构建**——这不是本任务（运行时胶水层）的缺陷，但值得在 README 补一段"`libs/` 需要从游戏 `Managed/` 与 `BepInEx/core/` 复制哪些 DLL"（17 个未引用的 DLL 可以顺便说明"可选"或干脆不复制）。

**建议修法**：
1. 删掉 `<Reference Include="mscorlib">`（已验证无影响），或保留并加注释说明"显式声明只为可读性"。
2. 在 README 补 `libs/` 的构建前提；或把 13 个必需 DLL 的清单写进 `build.ps1` 的一个校验步骤。
3. 清理 `libs/` 里 17 个未引用副本（可选，纯卫生）。

---

### L-5（低）README 默认形态自相矛盾

**file:line**：`README.md:7`、`README.md:51`、`src/Plugin.cs:181`

- `README.md:7`：「三种形态自由切换：原版 / 米菲兔 / 自嘲熊，默认 **米菲兔**」
- `README.md:51`：`| Plushie | ZichaoXiong | ...`
- `src/Plugin.cs:180-182`：`VariantEntry = Config.Bind("General", "Plushie", PlushieVariant.ZichaoXiong, ...)`
- `Plugin.cs:50`：`internal static PlushieVariant ActiveVariant = PlushieVariant.ZichaoXiong;`
- 实机日志 `LogOutput.log:102`：`Plushie Swap 1.0.0 loaded (plush: ZichaoXiong)`

**结论**：代码与配置表（第 51 行）一致，**第 7 行错了**。这属于任务 F 的范围，但因为它直接由 `Plugin.cs` 的默认值决定，在此交叉标注。

---

### L-6（运维）已部署 DLL 落后 HEAD

**证据**：

| 路径 | 大小 | SHA-256（前 16） | ProductVersion | 含 `Hand Inset` |
| --- | --- | --- | --- | --- |
| `bin\Release\PlushieSwap.dll`（HEAD `bc696a9`） | 12,133,376 | `582E1B00149682E8` | `1.0.0+bc696a91...` | 否 |
| `dist\PlushieSwap\PlushieSwap.dll` | 12,133,376 | `582E1B00149682E8` | 同 | 否 |
| 游戏 `BepInEx\plugins\PlushieSwap\PlushieSwap.dll` | 12,135,936 | `724B35B5752C1ACC` | `1.0.0+59cb9886...` | **是** |

```
$ git log --oneline -3
bc696a9 Drop the stale handoff notes the user removed      ← HEAD
62724d4 Clean up diagnostics and hand-inset, ship a Thunderstore package
59cb988 Fix the tint errors, unbreak the outline, and inherit the game's squish   ← 已部署
```

实机配置 `BepInEx\config\com.zhuanban.peak.plushieswap.cfg` 也来自旧构建：含 `Hand Inset = 1`（当前源码已无此项）、`Plushie = Miffy`、`Outline Width (pixels) = 6.350877`、`Config Version = 2`。

**影响**：本报告中引用 `LogOutput.log` 的部分（M-1 的 `Missing SettingType` 警告、§6 里的实机佐证）都来自**旧构建**。`Missing SettingType` 这条与源码版本无关（`KeyboardShortcut` 在当前源码里同样是 `KeyboardShortcut`，`Plugin.cs:213`），所以结论成立；但其它实机结论必须重新部署后复验。

**建议**：`pwsh -File build.ps1 -Deploy`，然后再跑一次实机验证。

---

## 3. 任务问题逐条回答

### 3.1 Harmony 补丁目标（任务问题 2）

| 补丁 | 目标是否存在 | 可见性 | 签名匹配 | 补丁签名 | 结论 |
| --- | --- | --- | --- | --- | --- |
| `Patches.cs:17-23` | ✅ `Item.Start` | `protected virtual` | `void Start()` | `(Item __instance)` postfix | ✅ |
| `Patches.cs:25-31` | ✅ `Item.OnEnable` | `public override` | `void OnEnable()` | `(Item __instance)` postfix | ✅ |
| `Patches.cs:33-47` | ✅ `Item.SetState` | `internal` | `void SetState(ItemState setState, Character character = null)` | `(Item __instance, ItemState setState)` prefix | ✅ 参数名 `setState` 与原方法**同名**，按名绑定成立 |
| `Patches.cs:49-55` | ✅ 同上 | 同上 | 同上 | `(Item __instance)` postfix | ✅ |
| `Patches.cs:57-68` | ✅ `Item.HideRenderers` | `private` | `void HideRenderers()` | `(Item __instance)` postfix | ✅ Harmony 用 `all` flags 能拿到 private |
| `Patches.cs:78-92` | ✅ `Item.GetName` | `public` | `string GetName()` | `(Item __instance, ref string __result)` | ✅ 返回类型 `string` 与 `ref string` 匹配 |
| `Patches.cs:94-113` | ✅ `Item.ItemUIData.GetIcon` | `public`（嵌套类） | `Texture2D GetIcon()` | `(Item.ItemUIData __instance, ref Texture2D __result)` | ✅ |
| `Patches.cs:129-165` | ✅ `InventoryItemUI.SetItem` | `public` | `void SetItem(ItemSlot slot)` | `(InventoryItemUI __instance, ItemSlot __0)` | ✅ 见 §3.2 |
| `CookingPatches.cs:61-94` | ✅ `ItemCooking.UpdateCookedBehavior` | `public virtual` | `void UpdateCookedBehavior()` | `(ItemCooking __instance)` prefix | ✅ |
| `CookingPatches.cs:97-121` | ✅ `BackpackOnBackVisuals.InitRenderers` | `private` | `void InitRenderers()` | `(BackpackOnBackVisuals __instance)` prefix → `bool` | ✅ 返回 `false` 跳过原方法 |

**额外核实（任务没问但会咬人的）**：

1. **`Start` / `OnEnable` 是 virtual，Harmony 只 patch 基类实现**。任何子类 `override` 且**不调 `base`** 就会绕过钩子。逐个核查所有 `Item` 子类的 `Start`/`OnEnable` override：

```
Backpack.cs:236   protected override void Start()      base-call=True
MobItem.cs:22     protected override void Start()      base-call=True
Guidebook.cs:70   public override void OnEnable()      base-call=True
```
`Item` 的子类只有 `{Stone, Backpack, Guidebook, MobItem}`（Cecil `BaseType` 确认；`CursedSkullVFX : ItemVFX`、`Candle/Lantern/Snowball/Beehive/Mandrake/RopeTier : ItemComponent`、`Rope : MonoBehaviourPunCallbacks`、`FrogTongue : Mob`，**都不是 Item**）。三者**全部调用 `base`**，所以 postfix 一定执行。✅

2. **`GetName` 有没有子类 override**：全库 grep `override string GetName()` = **0 命中**。Cecil 显示 `Item.GetName` 带 `Final` 标记（它是实现 `IInteractible` 接口成员的普通方法），无重写。→ 只 patch 基类就覆盖所有 Item。✅

3. **`Item.SetState` 的调用点**（决定 prefix 的 `ClearGameRuleHide` 何时跑）：

```
CharacterItems.cs:596:  item.SetState(ItemState.Held, character);   ← 唯一传入非 InBackpack 的地方
Item.cs:1297:           SetState(ItemState.InBackpack);              ← PutInBackpackRPC
```
全库再无其它 `Item.SetState` 调用；`ItemState.Ground` **从未**被写入（`itemState` 是 `public ItemState itemState { get; set; }`，Ground 只是默认值 0）。所以 `Patches.cs:43` 的 `if (setState != ItemState.InBackpack) ClearGameRuleHide(...)` 精确对应"被拿起"这一个转换，**与 `Patches.cs:38-42` 的注释完全一致**。✅

4. **`HideRenderers` 的调用点**：只有 `Item.cs:1301`（`PutInBackpackRPC` 内，且仅当 `backpackReference.IsOnMyBack()`）。所以 `Item_HideRenderers` postfix 只会因"塞进自己背着的背包"触发，`HideForGameRule` 的语义边界正确。✅

5. **`UpdateCookedBehavior` 有没有 override**：全库 grep 只有 `ItemCooking.cs` 自己的 3 处（定义 + 2 处调用），**无任何 override**。→ patch 基类足够。✅

6. **`BackpackOnBackVisuals.InitRenderers` 是否在基类 `BackpackVisuals` 上也有**：Cecil 显示 `BackpackVisuals` **既没有 `InitRenderers` 方法，也没有 `renderers` 字段**（grep 输出为空），该私有方法**只声明在 `BackpackOnBackVisuals` 上**。而 `ItemBackpackVisuals : BackpackVisuals` 根本没有这个方法。→ patch 精确覆盖唯一需要的类，无遗漏。✅

### 3.2 `__0` 这种按位置绑定是否可靠（任务问题 2）

**可靠，且这是 HarmonyX 的正式特性。** 证据（`0Harmony.decompiled.cs`）：

```csharp
7701:  private static readonly string ParamIndexPrefix = "__";

8663:  if (item.Name.StartsWith(ParamIndexPrefix, StringComparison.Ordinal))
8665:  {
8666:      if (!int.TryParse(item.Name.Substring(ParamIndexPrefix.Length), out result))
8667:          throw new Exception("Parameter " + item.Name + " does not contain a valid index");
8669:      if (result < 0 || result >= parameters.Length)
8671:          throw new Exception($"No parameter found at index {result}");
8672:  }
8673:  else { result = patch.GetArgumentIndex(originalParameterNames, item); ... }
```

即：名字以 `__` 开头且**剩余部分是数字** → 直接当参数下标用，**先做边界检查**。`InventoryItemUI.SetItem(ItemSlot slot)` 只有一个参数，`__0` → 下标 0 → `ItemSlot`，与补丁参数类型 `ItemSlot` 一致（`8730-8755` 的类型兼容分支处理值类型/引用类型装箱，`ItemSlot` 是引用类型，走 `Ldarg` 直传）。✅

**注意**：`__instance`、`__result`、`__state`、`__args`、`__originalMethod`、`__runOriginal` 是**先于**位置前缀被匹配的保留名（`7687-7701` 定义，`8590-8661` 依次判断），所以 `__instance` 不会被当成"下标解析失败"。✅

**什么时候 `__0` 会不可靠**：原方法增删参数、或参数顺序改变。`SetItem` 是 `public void SetItem(ItemSlot slot)` 的稳定公开 API，风险低。若想更稳，可写成 `ItemSlot slot`（按原名绑定，`GetArgumentIndex` 会匹配 `originalParameterNames`）——两者都行，当前写法没问题。

### 3.3 反射字段名（任务问题 3）

全部核实一致，见 §2.1 元数据表。逐条对应：

| 代码位置 | 字段名 | 元数据 | 结论 |
| --- | --- | --- | --- |
| `GameHelpers.cs:114` | `Item.ALL_ITEMS` | `List<Item> ALL_ITEMS` Public Static | ✅ |
| `GameHelpers.cs:115` | `Item.ALL_ACTIVE_ITEMS` | `List<Item> ALL_ACTIVE_ITEMS` Public Static | ✅ |
| `GameHelpers.cs:79-81` | `CharacterItems.character` | `Character character` **Private** | ✅ 用了 `NonPublic` flags |
| `GameHelpers.cs:44` | `Character.refs` | `CharacterRefs refs` Public | ✅ |
| `GameHelpers.cs:50-51` | `CharacterRefs.animationItemTransform` | `Transform` Public（嵌套类型 `Character/CharacterRefs`） | ✅ 动态取类型，写法正确（该辅助方法本身是死代码，见 L-1） |
| `CookingPatches.cs:41` | `ItemCooking.renderers` | `Renderer[]` Private | ✅ |
| `CookingPatches.cs:43` | `ItemCooking.defaultTints` | `Color[]` Private | ✅ |
| `CookingPatches.cs:45` | `ItemCooking.setup` | `bool` Private | ✅ |
| `CookingPatches.cs:48-49` | `BackpackOnBackVisuals.renderers` | `MeshRenderer[]` Private | ✅ 注意是 `MeshRenderer[]` 不是 `Renderer[]`，代码类型参数**正确** |
| `CookingPatches.cs:51-52` | `BackpackOnBackVisuals.defaultTints` | `Color[]` Private | ✅ |
| `Patches.cs:168` | `InventoryItemUI.icon` | `RawImage` Public | ✅ |
| `Patches.cs:171` | `InventoryItemUI._itemPrefab` | `Item` Private | ✅ |
| `GameHelpers.cs:280` | `LocalizedText.CURRENT_LANGUAGE` | `Language` Public Static | ✅ |
| `PlushieModel.cs:1400` | `Item.backpackReference` | `Optionable<(byte, BackpackReference)>` Public | ✅ 元数据类型名 `Optionable\`1` |
| `PlushieModel.cs:1192` | `Item.itemState` | `ItemState`（属性 `{ get; set; }`） | ✅ 是 **property** 不是 field，代码用属性访问，正确 |
| `PlushieModel.cs:1343` | `Item.GetData<IntItemData>(DataEntryKey.CookedAmount)` | `GetData(DataEntryKey)` 存在 | ✅ |
| `PlushieModel.cs:1406` | `BackpackReference.exists` / `.IsOnMyBack()` | `exists` 是属性、`IsOnMyBack()` 是方法（`BackpackReference.cs:19,84`） | ✅ |
| `Plugin.cs:170` | `typeof(Plugin).Assembly.Location` | 标准 API | ✅ |

**`Item.itemState` 的细节**：Cecil 显示它是 **property**（`prop itemState ItemState`），不是字段；`PlushieModel.cs:1192` 和 `Patches.cs` 都按属性用，一致。同时 `Item.backpackReference` 是 **public field**（不是属性），`PlushieModel.cs:1400` 也按字段用。两者都没搞反。✅

### 3.4 配置项：默认值 / 范围 / Tags / 迁移表 / 死配置（任务问题 4）

**（a）默认值与范围逐条比对**（代码 vs README 表 vs 实机 cfg）：

| 配置项 | 代码默认 | 代码范围 | README 表 | 实机 cfg | 结论 |
| --- | --- | --- | --- | --- | --- |
| `Plushie` | `ZichaoXiong`（`Plugin.cs:181`） | — | `ZichaoXiong`（:51） | `Miffy` | ✅ 代码/表一致；README:7 错（L-5） |
| `World Scale` | `1.0f`（:184） | `[0.3, 3.0]`（:187） | `1.0`（:53） | `1` | ✅ |
| `Backpack Scale` | `1.0f`（:189） | `[0.3, 3.0]`（:192） | `1.0`（:54） | `1` | ✅ |
| `Hold Height Offset` | `0.0f`（:194） | `[-0.4, 0.4]`（:200） | `0.0`（:55） | `0` | ✅ |
| `Rename Item` | `true`（:202） | — | `true`（:56） | `true` | ✅ |
| `Replace Icon` | `true`（:205） | — | `true`（:57） | `true` | ✅ |
| `Shader Override` | `""`（:208） | — | 空（:59） | 空 | ✅ |
| `Cycle Plush Hotkey` | `new KeyboardShortcut(KeyCode.F7)`（:214） | — | `F7`（:52） | `F7` | ⚠️ 类型问题见 M-1 |
| `Outline Width (pixels)` | `5f`（`DefaultOutlinePixels`, :159, 用 :218） | `[0, 12]`（:222） | `5.0`（:58） | `6.350877` | ✅ 用户手改过，在范围内 |
| `Config Version` | `0`（:224） | — | 文档在 :65-66 | `2` | ✅ 已迁移 |
| `Verbose Logging` | `false`（:230） | — | `false`（:60） | 缺失（默认 false） | ✅ |

**（b）`Tags("Hidden")` 是否真的生效**：

```csharp
// Plugin.cs:223-228
ConfigVersionEntry = Config.Bind("Internal", "Config Version", 0,
    new ConfigDescription("Written by the mod. Do not edit: ...", null, new object[] { "Hidden" }));
```

`ConfigDescription` 的签名（`BepInEx.decompiled.cs:3539` 附近）：

```csharp
public ConfigDescription(string description, AcceptableValueBase acceptableValues = null, params object[] tags)
{ AcceptableValues = acceptableValues; Tags = tags; Description = description ?? throw ...; }
```

传 `null` 作 `acceptableValues` + `new object[]{"Hidden"}` 作 tags → `Tags = ["Hidden"]`。游戏侧消费端（`PEAKLib.ModConfig`）确认读取并过滤：

```csharp
// ModConfig.decompiled.cs:1154-1159
object[] array = description?.Tags;
if (array == null || !Enumerable.Contains(array, "Hidden")) list.Add(item2);
```

实机日志也确认设置页挂上了、且 `Config Version` 未报 `Missing SettingType`（它是 `int`，有分支）→ **`Tags("Hidden")` 生效**。✅

**（c）迁移表逻辑是否与注释一致**：

`Plugin.cs:52-70` 的注释定义契约：`From` inclusive、`To` exclusive、首步 `From=0`、不得编辑/重排已有条目、不得加 catch-all。代码（`:118-129`）：

```csharp
for (int i = 0; i < migrations.Length; i++)
{
    ConfigMigration migration = migrations[i];
    if (version < migration.From || version >= migration.To) continue;   // ← 正是 [From, To)
    migration.Apply();
}
```

`version >= CurrentConfigVersion` 时提前 return（`:91-94`）→ 来自更新版本构建的 cfg 不会被回退。表内只有一条 `{From=0, To=2}`，`CurrentConfigVersion = 2`（`:48`）。**与注释逐字一致**。✅

**（d）迁移与事件订阅的顺序**（容易出 bug 的地方，已核实正确）：

```
Plugin.cs:236   MigrateConfigDefaults();          ← 可能写 OutlineWidthEntry.Value
Plugin.cs:238   ActiveVariant = VariantEntry.Value;
Plugin.cs:239   _lastOutlineWidth = OutlineWidthPixels;   ← 读到迁移后的新值
Plugin.cs:242-245  VariantEntry.SettingChanged += ...;  OutlineWidthEntry.SettingChanged += OnOutlineWidthChanged;   ← 订阅在迁移之后
```

因为订阅在 `MigrateConfigDefaults` **之后**，迁移写入**不会**触发 `OnOutlineWidthChanged`，而 `_lastOutlineWidth` 在 239 行从迁移后的值初始化。→ `OnOutlineWidthChanged` 里"`0 → 正数` 才重建"的判定（`:314-324`）不会被迁移误触发。**顺序正确**。✅

**（e）死配置**：**没有。** 11 个 `ConfigEntry` 全部被使用：

```
VariantEntry     Plugin.cs:238,291,330,345
WorldScaleEntry  PlushieModel.cs:1478
BackpackScaleEntry PlushieModel.cs:1477
HoldOffsetEntry  PlushieModel.cs:1259
VerboseLogEntry  Plugin.cs:269
RenameEntry      Patches.cs:84
ReplaceIconEntry Patches.cs:100,135
ShaderOverrideEntry PlushieModel.cs:556,599
CycleHotkeyEntry Plugin.cs:412
OutlineWidthEntry Plugin.cs:108,110,164
ConfigVersionEntry Plugin.cs:90,135
```

**（f）`AcceptableValueRange` 会 clamp 吗**：`ConfigEntry<T>.Value` 的 setter 调 `ClampValue(value)`（`BepInEx.decompiled.cs` `ConfigEntry<T>` 定义），所以越界写入会被夹回范围。`ScaleForState`（`PlushieModel.cs:1488`）另外 `Mathf.Clamp(multiplier, 0.2f, 4f)`——比配置范围（0.3–3）更宽，**不会**与配置范围冲突。✅

### 3.5 资源加载：松散文件优先 / 内嵌回退 / 缓存 / Texture 生命周期 / 失败路径重复重试（任务问题 5）

**（a）优先级与回退链**（`AssetProvider.cs:26-73`）：

```
Read(fileName, out source, embeddedOnly)
  if (!embeddedOnly) → Path.Combine(Plugin.AssetDirectory, fileName)
                       File.Exists → File.ReadAllBytes  → source = LooseFile
  EmbeddedAssets.Get(fileName) → source = Embedded
  return null  → source = Missing
```

`Plugin.AssetDirectory` = `Path.GetDirectoryName(typeof(Plugin).Assembly.Location)`（`Plugin.cs:170`）→ DLL 所在目录。`EmbeddedAssets.Table` 是 `StringComparer.OrdinalIgnoreCase`（`EmbeddedAssets.g.cs:117-119`），所以**文件名大小写不敏感**，与松散文件的 Windows 行为一致。✅

**（b）回退重试是"仅重试内嵌一次"，不会无限重试**：

- Mesh（`PlushieModel.cs:168-177`）：松散文件读取成功但**解析失败** → `AssetProvider.Read(def.MeshFile, out source, true)`（`embeddedOnly: true`，**跳过磁盘**）→ 再解析一次 → 仍失败才 `FailedLoads.Add(variant)`。
- Shading（`PlushieModel.cs:352-359`）：同上，`embeddedOnly: true`。
- Icon（`PlushieIcons.cs:40-47`）：同上，`embeddedOnly: true`。

**关键**：三处的重试都传 `embeddedOnly: true`，所以**不会**再次读磁盘。如果重试仍失败 → 加入 `FailedLoads` / `MissingTextures` / `Failed` 集合 → **后续调用直接返回，不再重试**。✅ 这正好满足任务问的"失败路径是否会重复重试"——**不会**。

**（c）`source` 变量的语义是否可靠**：`AssetProvider.Read` 在 `embeddedOnly: true` 时**不设置** `LooseFile`，所以 `source == LooseFile` 精确表示"这次读的是磁盘"。`PlushieModel.cs:168` 和 `PlushieIcons.cs:40` 的判定成立。✅ 唯一边界：松散文件存在但 `File.ReadAllBytes` 抛异常 → `catch` 打 warning，`source` 仍是 `Missing`（不是 `LooseFile`）→ **不会**走"重试内嵌"分支，但紧接着的 `EmbeddedAssets.Get` 本来就会兜底，所以最终结果相同，只是少了一条"retrying the embedded copy"日志。✅ 无缺陷。

**（d）Texture 生命周期**（`AssetProvider.cs:96-144`）：

```csharp
texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);   // 第 4 参 = mipChain:false
if (!texture.LoadImage(bytes, false)) { ...; Object.Destroy(texture); return null; }   // 第 113 行
...
texture.Apply(false, true);   // updateMipmaps:false, makeNoLongerReadable:true
...
catch (Exception ex) { if (texture != null) Object.Destroy(texture); ... }   // 第 137-140 行
```

- `Texture2D(int, int, TextureFormat, bool mipChain)` 这个重载**存在**（Cecil dump `UnityEngine.CoreModule` 的 ctor 列表里有 `ctor(Int32 width, Int32 height, TextureFormat textureFormat, Boolean mipChain)`），所以"第 4 个参数是 `mipChain`"的注释**正确**。
- `LoadImage` 失败路径：`Destroy` 后**立即 return**，不会走到 catch 二次 destroy。✅
- catch 路径：只在 `new Texture2D` 成功之后才可能进 catch（`LoadImage` 之前的操作不会抛），`if (texture != null)` 保护到位。✅
- `makeNoLongerReadable: true` 之后不能再 `GetPixels`，但代码不需要。✅
- **无泄漏**：三条失败路径（bytes==null 早退、LoadImage false、catch）都正确处理；成功路径的纹理由 `PlushieIcons.Cache` / `PlushieModel.CachedTextures` 持有到进程结束（每变体最多 1 张，**有界**）。✅

**（e）缓存**：

| 缓存 | 位置 | 键 | 有界？ | 清空？ |
| --- | --- | --- | --- | --- |
| 内嵌解压字节 | `EmbeddedAssets.Cache`（:128-129） | 文件名（忽略大小写） | ✅ 6 项固定 | 从不清（有界，OK） |
| 图标纹理 | `PlushieIcons.Cache`（:10-11） | 变体 | ✅ 最多 2 项 | 从不清（有界，OK） |
| 着色纹理 | `PlushieModel.CachedTextures`（:80-81） | 变体 | ✅ 最多 2 项 | 从不清（有界，OK） |
| 失败标记 | `PlushieIcons.Failed`、`PlushieModel.MissingTextures`、`FailedLoads` | 变体 | ✅ 最多 2 项 | 只在成功时移除（`PlushieModel.cs:186`） |

`EmbeddedAssets` 的解压总量约 6 MB（DLL 里最大的 `MiffyMesh` 2.28 MB、`ZichaoXiongMesh` 2.40 MB），常驻托管堆，**有界**。✅

### 3.6 csproj 引用：缺失 / 多余（任务问题 6）

见 §L-4。结论：**没有缺失**（13 个引用逐个删除都会编译失败，且 30 个 DLL 与运行时哈希全同）；**1 个冗余**（`mscorlib`，删掉引用集合不变）；**17 个 `libs/` 副本未被引用**（但 `libs/` 本身被 gitignore，且 `build.ps1` 不生成它，属仓库卫生问题）。

---

## 4. 补充实验记录

### 4.1 `libs/` 与运行时程序集逐一哈希比对

```powershell
$libs="D:\zhuanban\Plushie Swap\libs"
$man="D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data\Managed"
$core="D:\SteamLibrary\steamapps\common\PEAK\BepInEx\core"
# 对 libs 下每个 DLL，在 $man 或 $core 里找同名文件并比 SHA-256
```

输出（30 行，全部 `SAME`）：

```
0Harmony.dll                    SAME  core\0Harmony.dll
Assembly-CSharp.dll             SAME  Managed\Assembly-CSharp.dll
BepInEx.dll                     SAME  core\BepInEx.dll
BepInEx.Harmony.dll             SAME  core\BepInEx.Harmony.dll
mscorlib.dll                    SAME  Managed\mscorlib.dll
netstandard.dll                 SAME  Managed\netstandard.dll
Photon3Unity3D.dll              SAME  Managed\Photon3Unity3D.dll
PhotonRealtime.dll              SAME  Managed\PhotonRealtime.dll
PhotonUnityNetworking.dll       SAME  Managed\PhotonUnityNetworking.dll
System.Core.dll                 SAME  Managed\System.Core.dll
System.dll                      SAME  Managed\System.dll
System.Drawing.dll              SAME  Managed\System.Drawing.dll
Unity.Localization.dll          SAME  Managed\Unity.Localization.dll
Unity.TextMeshPro.dll           SAME  Managed\Unity.TextMeshPro.dll
UnityEngine.AnimationModule.dll SAME  Managed\UnityEngine.AnimationModule.dll
UnityEngine.AssetBundleModule.dll SAME  Managed\UnityEngine.AssetBundleModule.dll
UnityEngine.AudioModule.dll     SAME  Managed\UnityEngine.AudioModule.dll
UnityEngine.CoreModule.dll      SAME  Managed\UnityEngine.CoreModule.dll
UnityEngine.dll                 SAME  Managed\UnityEngine.dll
UnityEngine.ImageConversionModule.dll SAME  Managed\UnityEngine.ImageConversionModule.dll
UnityEngine.IMGUIModule.dll     SAME  Managed\UnityEngine.IMGUIModule.dll
UnityEngine.JSONSerializeModule.dll SAME  Managed\UnityEngine.JSONSerializeModule.dll
UnityEngine.PhysicsModule.dll   SAME  Managed\UnityEngine.PhysicsModule.dll
UnityEngine.TextCoreTextEngineModule.dll SAME  Managed\UnityEngine.TextCoreTextEngineModule.dll
UnityEngine.TextRenderingModule.dll SAME  Managed\UnityEngine.TextRenderingModule.dll
UnityEngine.UI.dll              SAME  Managed\UnityEngine.UI.dll
UnityEngine.UIModule.dll        SAME  Managed\UnityEngine.UIModule.dll
UnityEngine.UnityWebRequestAudioModule.dll SAME  Managed\UnityEngine.UnityWebRequestAudioModule.dll
UnityEngine.UnityWebRequestModule.dll SAME  Managed\UnityEngine.UnityWebRequestModule.dll
Zorro.Core.Runtime.dll          SAME  Managed\Zorro.Core.Runtime.dll
```

**意义**：编译期类型布局 == 运行期类型布局，**排除**版本漂移导致的 `MissingMethodException` / `TypeLoadException`。

### 4.2 基线构建（`%TEMP%` 副本，不污染仓库）

```powershell
$dst="$env:TEMP\psbuild"; Copy-Item src,libs,PlushieSwap.csproj → $dst
Push-Location $dst; dotnet build -c Release -v q --nologo
```

```
已成功生成。  0 个警告  0 个错误   已用时间 00:00:03.71   EXIT=0
```

### 4.3 引用必需性逐个删除实验（12 次构建）

见 §L-4 证据 A / §3.6。除 `mscorlib` 外**全部 NEEDED**。

### 4.4 `NoWarn` 抑制了哪些警告

把 `PlushieSwap.csproj:16` 的 `<NoWarn>$(NoWarn);CS0436;CS0618</NoWarn>` 改成 `<NoWarn>$(NoWarn)</NoWarn>` 重新构建：

```
EXIT=0
warning CS0618: "Object.FindObjectsOfType<T>()" 已过时 ... （GameHelpers.cs:133）
warning CS0618: "Object.FindObjectsOfType<T>(bool)" 已过时 ... （PlushieOutline.cs:174）
```

**没有 CS0436 警告**——`CS0436`（"类型与导入类型冲突，使用定义在源中的类型"）在抑制列表里是**预防性**的，实际不触发。`CS0618` 的两处是 `FindObjectsOfType` 弃用（Unity 6 建议 `FindObjectsByType`）。**不影响正确性**，但值得知道这两个 API 在新 Unity 里更慢（`FindObjectsOfType` 会按 InstanceID 排序）。这属于 `PlushieOutline.cs` / `GameHelpers.cs` 的性能范畴（task-1 的范围），此处只记录事实。

---

## 5. 红线核查（任务要求：建议若触碰红线必须标注）

从 `README.md` 与代码注释里识别出的**用户明确禁止改动**的条目：

| 红线 | 出处 | 本报告的建议是否触碰 |
| --- | --- | --- |
| **不写 `Hand_L` / `Hand_R` 锚点**——原版数值从头到尾不动 | `README.md:124`、`PlushieModel.cs:1240-1244` | ❌ 未触碰 |
| **描边壳体不删任何面** | `README.md:74,82-88` | ❌ 未触碰 |
| **`enclosed` 遮罩"故意不使用"** | `README.md:90-92` | ❌ 未触碰 |
| **不修改游戏语音 / 动画 / 物品逻辑** | `README.md:18,188` | ❌ 未触碰（M-1 只改配置项绑定类型，M-2/M-3 只改错误处理） |
| **对称收拢手的方案"已完全移除"，不可复活** | `README.md:129-131` | ❌ 未触碰（实机日志里那个 `Hand Inset` 属于**旧构建**，当前源码已无，见 L-6） |
| **迁移表不得编辑/重排已有条目，不得加 catch-all** | `Plugin.cs:65-69` | ❌ 未触碰（§3.4(c) 只是核实其正确性） |
| **模型必须挂在 `item/Holder/PlushieSwap_Visual`** | `README.md:133-136`、`PlushieModel.cs:901,903-914` | ❌ 未触碰 |

**结论：本报告全部 9 条建议均不触碰任何红线。** 其中 M-1 的建议 1 需要新增一个 `UnityEngine.InputLegacyModule` 引用（或改用已引用的 BepInEx `UnityInput`），这是**新增**引用，不是修改游戏行为。

---

## 6. 已核实无误清单（含核实方法）

| # | 项 | 核实方法 | 结论 |
| --- | --- | --- | --- |
| 1 | 9 个补丁目标**全部存在** | Mono.Cecil 读元数据（§2.1）+ ilspycmd 反编译双向确认 | ✅ 无误 |
| 2 | 补丁方法签名与目标签名**匹配**（含 `ref string __result`、`ref Texture2D __result`、`bool` prefix 跳过原方法） | 元数据参数表 vs `Patches.cs`/`CookingPatches.cs` 签名逐条比对（§3.1） | ✅ 无误 |
| 3 | `private` / `internal` 目标（`Item.HideRenderers`、`Item.SetState`、`BackpackOnBackVisuals.InitRenderers`）能被 Harmony 打到 | `AccessTools.all = Instance\|Static\|Public\|NonPublic\|GetField\|SetField\|GetProperty\|SetProperty`（`0Harmony:4012`），`DeclaredMethod` 用 `allDeclared`（`4238`） | ✅ 无误 |
| 4 | `__0` 位置绑定可靠 | `0Harmony.decompiled.cs:7701`（前缀定义）、`8663-8672`（下标解析 + 边界检查）；`SetItem` 只有 1 个参数 | ✅ 无误 |
| 5 | `Start`/`OnEnable` 的 virtual 补丁不会被 Item 子类绕过 | Cecil 确认 Item 子类只有 `{Stone, Backpack, Guidebook, MobItem}`；逐个检查 override 是否调 `base`——全部调（§3.1） | ✅ 无误 |
| 6 | `GetName` / `UpdateCookedBehavior` 无子类 override | 全库 grep `override string GetName()` = 0；`UpdateCookedBehavior` 只有定义与调用 | ✅ 无误 |
| 7 | `BackpackOnBackVisuals.InitRenderers` 是唯一需要 patch 的实现 | Cecil：`BackpackVisuals` 既无该方法也无 `renderers` 字段；`ItemBackpackVisuals : BackpackVisuals` 也没有 | ✅ 无误 |
| 8 | 全部反射字段名与游戏一致（18 项） | Mono.Cecil 字段表（§2.1、§3.3） | ✅ 无误 |
| 9 | `CharacterRefs` 是嵌套类型，`GameHelpers` 的动态取型写法正确 | 元数据 `Character/CharacterRefs`；`FieldType.GetField(...)` 逻辑正确 | ✅ 无误 |
| 10 | `Item.itemState` 是属性、`backpackReference` 是字段，用法都没搞反 | Cecil 属性表 / 字段表 | ✅ 无误 |
| 11 | `InventoryItemUI.icon` 确为 `RawImage`，`Patches.cs:152-163` 的 `.texture`/`.enabled` 操作类型正确 | Cecil + 反编译；消费端 `BackpackWheel`/`BackpackWheelSlice`/`UI_UseItemProgressFriend` 也全是 `RawImage`（§L-3） | ✅ 无误 |
| 12 | 配置项默认值 / 范围与 README 表一致（除 README:7） | §3.4(a) 逐条表格 | ✅ 无误（1 处 README 错，见 L-5） |
| 13 | `Tags("Hidden")` 确实生效 | `ConfigDescription(string, AcceptableValueBase, params object[])` 签名；`PEAKLib.ModConfig:1154-1159` 读取并过滤 `"Hidden"`；实机日志无该项的 `Missing SettingType` | ✅ 无误 |
| 14 | 迁移表 `[From, To)` 语义与注释一致，无 catch-all，首步 `From=0` 正确 | `Plugin.cs:118-129` vs `:52-70` 注释；`version >= CurrentConfigVersion` 提前返回 | ✅ 无误 |
| 15 | 迁移在事件订阅**之前**执行，不会误触发 `OnOutlineWidthChanged` | `Plugin.cs:236`（迁移）< `:242-245`（订阅）< `:239`（`_lastOutlineWidth` 取迁移后值） | ✅ 无误 |
| 16 | **无死配置**：11 个 `ConfigEntry` 全部被读取 | 全 `src/` grep 每个 entry 的引用点（§3.4(e)） | ✅ 无误 |
| 17 | `AcceptableValueRange` 会 clamp，`ScaleForState` 的 `Clamp(0.2,4)` 与之不冲突 | `ConfigEntry<T>.Value` setter 调 `ClampValue`；`PlushieModel.cs:1488` 范围更宽 | ✅ 无误 |
| 18 | 松散文件优先 / 内嵌回退链正确，大小写不敏感 | `AssetProvider.cs:26-73`；`EmbeddedAssets.g.cs:117-119` 用 `OrdinalIgnoreCase` | ✅ 无误 |
| 19 | 失败路径**不会**重复重试（三处都传 `embeddedOnly: true`，失败进集合后不再重试） | `PlushieModel.cs:168-177,352-359`、`PlushieIcons.cs:40-47` | ✅ 无误 |
| 20 | Texture 三条失败路径均正确 `Destroy`，无双重 destroy、无泄漏 | `AssetProvider.cs:106-143` 控制流；`Texture2D(int,int,TextureFormat,bool mipChain)` 重载存在 | ✅ 无误 |
| 21 | 所有缓存都有界（每变体最多 1 项） | §3.5(e) 表 | ✅ 无误 |
| 22 | `CookingPatches` 的 `setup=true` 不会破坏 `item.WasActive()` 语义 | `ItemCooking.cs:71-98`：`if (setup) item.WasActive();` 在 `if (!setup) { ...发现块... }` 之前，prefix 置 `setup=true` 后 base 仍会调 `WasActive()` | ✅ 无误 |
| 23 | `ReadTints` 的 `Color.white` 兜底与游戏行为等价（对原版材质） | 原版材质都声明 `_Tint`（游戏自己就 `GetColor("_Tint")`），走 `HasProperty` 真分支 | ✅ 无误 |
| 24 | `_Tint` 只在这 4 处物品相关代码里被读写，`CookingPatches` 覆盖完整 | 全反编译库 grep `"_Tint"`：`ItemCooking.cs:96,131`、`BackpackOnBackVisuals.cs:58,80`（覆盖）+ `SetRockColors.cs:18`、`Peak/ScoutmasterSoulPillar.cs:161-162`、`sc.posteffects.runtime/RefractionRenderer.cs:40`（都是场景对象/后效，不在物品子树内）→ `CookingPatches.cs:33-36` 注释的断言**为真** | ✅ 无误 |
| 25 | 实机无 `ApplyToItem failed` / `Tick failed` / `Hotkey check failed` / `Failed to apply` | grep `LogOutput.log` = 0 命中 | ✅ 无误 |
| 26 | `libs/` 30 个 DLL 与运行时哈希全同 → 无版本漂移 | §4.1 | ✅ 无误 |

---

## 7. 给 Lead 的行动建议（按优先级）

1. **先重新部署再验证**（L-6）：`pwsh -File build.ps1 -Deploy`。当前实机跑的是落后两个提交的构建。
2. **修 M-1**：把 `Cycle Plush Hotkey` 从 `KeyboardShortcut` 换成 `KeyCode`（或加 `KeyCode` 镜像项），并同步 README:52/62。这是唯一一条**用户可感知**的功能缺陷（热键在游戏内不可配置），且有实机日志硬证据。
3. **修 M-2 + M-3**（两者都是"静默失效"类韧性缺陷，同一类修法）：`PatchSafely` 打完整异常 + 逐方法容错 + 启动自检；`FieldRefAccess` 惰性初始化并显式报错。
4. **清理 L-1 死代码**（36 行 + 2 个无调用 API）。
5. **修 L-2**（语言缓存触发条件）与 **L-5**（README:7 默认值）。
6. **可选**：L-3（背包槽图标分支，影响极低）、L-4（csproj 冗余 + `libs/` 卫生 + README 补构建前提）。

---

*审计员：audit-runtime-glue（共享任务 task-2）。只读审计，未修改 `src/` 与 `PlushieSwap.csproj`；唯一写入文件为本报告。所有破坏性实验均在 `%TEMP%` 副本中进行。*
