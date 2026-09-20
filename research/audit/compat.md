# 审计 E：模组兼容性 + 参考模组逐项对比（task-5）

- 审计员：`audit-compat`
- 范围：只读。未修改 `src/`、未修改游戏目录内任何文件（含 DLL）。
- 反编译工具：`C:\Users\Administrator\.dotnet\tools\ilspycmd.exe` 11.0.0.9375
- 反编译输出目录：`C:\Users\Administrator\AppData\Local\Temp\opencode\compat-decomp\`
- 游戏模组目录：`D:\SteamLibrary\steamapps\common\PEAK\BepInEx\plugins`（21 个 DLL + `MMHOOK\` + `PlushieSwap\`）
- 游戏侧反编译参考：`D:\zhuanban\youhua\decompiled-latest\Assembly-CSharp\`
- 参考模组源码：`D:\zhuanban\Plushie Swap\ScallionMiku-main\`

---

## 结论摘要

1. **任务 1 结论：当前安装的 21 个模组，没有任何一个 patch 本模组的 9 个目标方法中的任何一个，也没有任何模组替换 BingBong 模型。零硬冲突。**
   本模组 9 个目标：`Item.Start` / `Item.OnEnable` / `Item.SetState` / `Item.HideRenderers` / `Item.GetName` / `Item.ItemUIData.GetIcon` / `InventoryItemUI.SetItem` / `ItemCooking.UpdateCookedBehavior` / `BackpackOnBackVisuals.InitRenderers`。
   全量 `[HarmonyPatch]` 提取（21 个模组，见 `任务1` 表）显示，与 `Item` 家族相关的第三方补丁只有两个：`SimpleTweaks` 的 `Item.Interact`、`SimpleTweaks` 的 `CharacterItems.OnPickupAccepted`。二者都不在 9 个目标里。

2. **参考模组 ScallionMiku 不在 `plugins` 里。** 已用三种方式确认：目录清单、`plugins` 递归文件名搜索、整个 `D:\SteamLibrary\steamapps\common\PEAK` 递归搜索 `*Miku*` / `*Scallion*` / `*Fufu*` / `*BingBong*`，结果均为空。参考源码只存在于项目目录 `ScallionMiku-main\`（且已在 `.gitignore` 中排除）。
   **但它与本模组不可共存**：两者在 **9 个目标上完全重叠**（ScallionMiku 的 `ItemPatch.cs:3949,3960,3967,3974,4007,4039,4049` + `4251` + `4290`），且都会在同一个 `Item` 下挂载替换模型 → 两个模型同时渲染、互相抢 `mainRenderer`/材质/可见性，属于**硬冲突**。若用户安装 ScallionMiku 1.0.5，必须二选一。

3. **本模组有 3 处明确可以借鉴 ScallionMiku 的具体点**（详见任务 2 与高风险项）：
   - `DisableOriginalRenderers` 额外写 `forceRenderingOff = true`（`ItemPatch.cs:1469`）——比只写 `renderer.enabled` 更抗第三方 re-enable；
   - `mainRenderer` 的**显式恢复**（`RestoreOriginalItemRendererRefs`，`ItemPatch.cs:3129-3141`）——一旦有任何东西改写了 `mainRenderer`，它能精确还原；
   - 每帧校验的**分桶降频**（`ItemPatch.cs:3512-3539`：held 每 8 帧、backpack 每 20 帧、world 每 4 帧）——本模组目前对每个被跟踪物品**每帧全量** `SyncVisual`（`PlushieModel.cs:747-760`）。

4. **本模组在 6 个方面明显优于 ScallionMiku**：手持偏移随模型与缩放自适应（vs 硬编码常量）、不重指 `mainRenderer`（避免污染 `Item.Center()` / hover / 烹饪 tint）、不 patch `GetItemName`（保留 "Cooked/Burnt" 前缀）、烹饪 tint 用 `MaterialPropertyBlock` 而非改写材质、借用游戏自身的 `Squish` 动画而非自实现挤压、拥有屏幕空间恒定像素宽的描边（ScallionMiku 完全没有描边）。

5. **⚠️ 部署的 DLL 与 `src/` 不一致（高风险，见末节 H1）。** `plugins\PlushieSwap\PlushieSwap.dll` 的 `buildinfo.txt` 写着 `commit: 59cb988`，但该 commit 的源码树里**没有** `GripInset.cs`、**没有** `Hand Inset` 配置项、**没有** 对 `CharacterItems` 的任何补丁；而部署 DLL 反编译出来这三样全都有，且**没有** `DiagnosticLog.cs`。即：**当前线上 DLL 是 59cb988 之上一个未提交（dirty）工作树构建的，比 git 历史更旧，且多 patch 了 4 个 `CharacterItems` 手部方法。** 本报告的任务 1 判定同时按「部署 DLL 实际补丁集」和「`src/` 补丁集」两个口径给出。

---

## 任务 1：逐模组兼容性表

### 1.0 提取方法与证据位置

- 全量 `[HarmonyPatch]` 属性提取：对 `compat-decomp\` 下每个模组的每个 `.cs` 逐行扫描（`Select-String '\[HarmonyPatch'`）。
- 程序化补丁（无属性）：搜索 `new HarmonyMethod` / `harmony.Patch(` / `TargetMethod()` / `MonoDetourTargets(` / `InvokeHookInitializers`。
- 已核对：PEAKLib 系列与 SoftDependencyFix **不使用 Harmony**，改用 MonoDetour（`MonoDetourManager.InvokeHookInitializers`），其目标类型见下表。

### 1.1 主表

| # | 模组（DLL） | 本模组 9 目标的交集 | 该模组的补丁目标（反编译证据） | 与 BingBong / Item 渲染的关系 | 判定 |
|---|---|---|---|---|---|
| 1 | `BetterPeakVoiceFix.dll` | **无** | `LoadBalancingClient.OnEvent`（`PeakVoiceFix.Patches\LoadBalancingClientPatch.cs:7,10`）、`MainMenuJoinRoomPage.JoinRoomAndWaitForSpawn`（`PeakVoiceFix\WaitMasterBeforeJoinPatch.cs:9`）、`SteamLobbyHandler.RequestPhotonRoomID`（`RequestRoomIDPatch.cs:5`）、`PhotonNetwork.RPC(Type[])`（`PhotonRPCFix.cs:8,11`）、`PhotonNetwork.ConnectUsingSettings()`（`ForceRegionPatch.cs:7`）、`CodeToRegionFallbackPatch.TargetMethod()` 动态（`CodeToRegionFallbackPatch.cs:12`） | 只碰 Photon/语音/大厅 | 无冲突 |
| 2 | `BetterPlayerDistance.dll` | **无** | `Character.Awake`、`Character.OnDestroy`（`BetterPlayerDistance\CharacterPatches.cs:6,9,16`） | 只读 Character | 无冲突 |
| 3 | `com.github.boxofbiscuits97.GhostPing.dll` | **无** | `PointPinger.Update`、`PointPinger.ReceivePoint_Rpc`（`GhostPing\GhostPing.cs:10,24`） | 无 | 无冲突 |
| 4 | `com.github.darmuh.PEAKTrails.dll` | **无** | `Character.Update`（`PEAKTrails\Patching.cs:57`） | 读 `item.UIData.itemName.Contains("Bing Bong")`（`Patching.cs:180`，清单见 `:243`） | **无冲突**：本模组不修改 `UIData.itemName`，其"手持 BingBong 显示足迹"触发条件保持有效 |
| 5 | `com.github.LengSword.PeakStatsEx.dll` | **无** | `GUIManager.Start`、`PlayerHandler.RegisterCharacter`、`LoadingScreenHandler.LoadSceneProcess`（`PeakStatsEx\Patches.cs:13,114,124`）；`StaminaBar.Update`、`CharacterStaminaBar.Update`、`CharacterAfflictions.AddStatus/SubtractStatus×2/SetStatus`（`StaminaInfoPatch.cs:61,92,125,193,202,218`）；`OrbFogHandler.Update/RPCA_SyncFog/RPC_InitFog/StartMovingRPC/SetFogOrigin`（`FogMovementTracker.cs:141-169`）；`LavaRising.Update/RecieveLavaData/OnDisable`（`RisingFieldMovementTracker.cs:149-163`） | 调用 `item.UIData.GetIcon()`（`InventorySlotUI.cs:92`）、`ItemCooking.GetCookColor`（`:163`） | **兼容且受益**：本模组 `GetIcon` postfix 会让它的自定义物品栏槽显示替换图标 |
| 6 | `com.github.PEAKModding.PEAKLib.Core.dll` | **无** | MonoDetour：`PlayerHandler`（`PEAKLib.Core.Hooks\CharacterRegistrationHooks.cs:8`）、`GameHandler`（`GameHandlerHooks.cs:7`）、`LoadingScreenHandler`（`LoadingScreenHandlerHooks.cs:11`）。另注册全局 `IPunPrefabPool`（`CustomPrefabPool.cs`） | 影响 `PhotonNetwork.Instantiate` 的 prefab 解析；本模组不调用它 | 无冲突 |
| 7 | `com.github.PEAKModding.PEAKLib.ModConfig.dll` | **无** | MonoDetour hook 初始化（`ModConfigPlugin.cs:84`）；无游戏方法补丁 | 在游戏设置菜单里展示本模组配置（日志 `Adding existing button Plushie Swap (ModdedTABSButton)`） | 无冲突（正向） |
| 8 | `com.github.PEAKModding.PEAKLib.UI.dll` | **无** | MonoDetour：`MainMenu`、`MainMenuSettingsPage`、`PauseMenuMainPage`、`PauseMenuSettingsMenuPage`（`PEAKLib.UI.Hooks\*.cs`） | 无 | 无冲突 |
| 9 | `com.github.PEAKModding.SoftDependencyFix.dll` | **无** | ILHook `ReflectionUtility.GetMethodsWithAttribute`、`GetClassesWithAttribute`（`SoftDependencyFix\ReflectionUtilityHooks.cs:36-55`） | 无 | 无冲突 |
| 10 | `DestinyWind.SelfResurrection.dll` | **无** | **无 Harmony 补丁**（`SelfResurrection\Plugin.cs` 直接用 `Character.Revive()` + `PhotonView.RPC("WarpPlayerRPC")`） | 无 | 无冲突 |
| 11 | `EasyBackpack.dll` | **无** | `GUIManager.CloseBackpackWheel`（`Entry.cs:14`）、`BackpackWheel.Update`（`:24`）、`CharacterBackpackHandler.AddFuelToJetpack`（`:78`）、`Player.SyncInventoryRPC`（`:169`） | 只**读** `BackpackOnBackVisuals.slotCount`（`Entry.cs:535-538`）；本模组的 `InitRenderers` prefix 只替换 renderer 列表，`slotCount` 不动 | 兼容 |
| 12 | `ItemSpawnerPremium.dll` | **无** | `GUIManager.Start`、`WarpOnThrow.OnDisable`（`ItemSpawnerEnhancement\Plugin.cs:16,36`）；反射 `CharacterItems.SpawnItemInHand`（`ItemSpawnerPremiumWindow.cs:17`） | 调用 `item.GetName()`（`ItemListView.cs:349`）与 `uiData.GetIcon()`（`:549`）；目录含 `"BingBong"`（`ItemCatalog.cs:127`） | 兼容；生成器里会显示为 Miffy/Zichao Xiong（预期行为） |
| 13 | `peak-item-tooltip.dll` | **无** | **无 Harmony 补丁**（`PeakItemTooltip\Plugin.cs` 在 `Update` 里轮询 `currentItem`） | 以 `item.UIData.itemName` 为描述字典键（`Widget.cs:67`），显示 `item.GetItemName()`（`:83`）与 `uiData.GetIcon()`（`:76`） | 兼容；本模组只改 `GetName` 不改 `UIData.itemName`，所以描述查得到、名字显示为替换名 |
| 14 | `PeakSafeOptimizer.dll` | **无** | 38 条程序化 lane（`new HarmonyMethod(...)` + `_harmony.Patch(...)`，`PatchInstaller.cs:405`）。与本模组相关的三条：`IKItemGuard` → `CharacterAnimations.ConfigureIK`（`IKItemGuardPatch.cs:56`，**默认 true**，本机 config 为 true）；`ItemScaleRedundantWrite` → `ItemScaleSyncer.Update`（`ItemScaleRedundantWritePatch.cs:89`，config true）；`RemoteClusterAnimationThrottle` → `CharacterRagdoll.FixedUpdate`（`RemoteClusterAnimationThrottlePatch.cs:89`，**本机 config 为 true**） | 见下节 1.2；另 `ItemCollisionMode` → `Item.UpdateCollisionDetectionMode`（`ItemCollisionModePatch.cs:67`） | **需要关注**（IKItemGuard 与部署 DLL 的 GripInset 同域），无直接补丁重叠 |
| 15 | `PEAKUnlimited.dll` | **无** | `NetworkingUtilities.GetMaxPlayers/HostRoomOptions`、`Campfire.OnEnable`、`PlayerConnectionLog.OnPlayerLeftRoom/OnPlayerEnteredRoom/Awake`、`AirportCheckInKiosk.StartGame/LoadIslandMaster`、`EndScreen.*`、`WaitingForPlayersUI.Update`、`PlayClicked`、`LeaveLobby`、`Spawner.TrySpawnItems`、`AudioLevels.InitNavigation`、`UIPlayerNames.Init/UpdateName/DisableName`、`PeakHandler.EndCutscene/SetCosmetics`、`CharacterVoiceHandler.Start/Update`、`PlayerHandler.AssignMixerGroup`、`SteamLobbyAPI.PlayerIsInLobby` | 调用 `value2.GetName()`（`Utility.cs:121`）与 `PhotonNetwork.Instantiate("0_Items/" + item.name)`（`:166`）；本模组不重命名 GameObject | 兼容 |
| 16 | `Piggyback.dll` | **无** | `CharacterInteractible.CanBeCarried/IsInteractible/HoverEnter/HoverExit/Interact/IsConstantlyInteractable/GetInteractTime/Interact_CastFinished`、`CharacterCarrying.Update/CarrierGone/StartCarry/RPCA_Drop`、`CharacterInput.Sample/SelectSlotWasPressed`、`MainCameraMovement.LateUpdate/HandleSpecSelection`、`CharacterAfflictions.UpdateWeight`（`Piggyback.cs:38-405`） | 均为 **Character** 侧 hover，非 `Item.HoverEnter` | 无冲突 |
| 17 | `RoomHub.dll` | **无** | `NetworkConnector.OnJoinedRoom/OnLeftRoom`、`SteamLobbyHandler.OnLobbyDataUpdate/OnLobbyEnter`、`PlayerConnectionLog.OnPlayerEnteredRoom`、`GUIManager.UpdatePaused` | `PlayerTracker.cs:201` 把玩家昵称 `"Bing Bong"` 当未知玩家占位符，与物品无关 | 无冲突 |
| 18 | `ScrapClean.dll` | **无** | `CharacterInput.Sample(bool)` postfix（程序化，`HarmonyPatches.cs:20-32`） | 见下节 1.3：会向 `Item` 子树 renderer 写 `MaterialPropertyBlock`，也会 `PhotonNetwork.Destroy` 地面物品 | **低风险交互**（见 1.3） |
| 19 | `SimpleTeleport.dll` | **无** | **无 Harmony 补丁**（`SimpleTeleport\SimpleTeleportPlugin.cs`） | 无 | 无冲突 |
| 20 | `SimpleTweaks.dll` | **无**（`Item.Interact` 不在 9 目标内） | `Item.Interact`（`BackpackSwapPatch.cs:7`）、`CharacterItems.OnPickupAccepted`（`BackpackSwapCompletePatch.cs:9`）、`CharacterAnimations.PlayEmote`（`Patch_BackflipAlwaysSucceed.cs:8`）、`Character.UpdateVariablesFixed`（`Patch_DeathRegeneration.cs:7`）、`Action_ModifyStatus.RunAction`、`Action_RestoreHunger.RunAction`、程序化 `PeakStatsExCompat` | 见 1.4：`Item.Interact` prefix 可对背包物品调 `gameObject.SetActive(false)` | **低风险**（见 1.4） |
| 21 | `youxia173.BetterPingDistance.dll` | **无** | `PointPinger.Awake/ReceivePoint_Rpc`（`PointPingerPatch.cs:7,10,20`）、`GUIManager.Start/LateUpdate/OnDestroy`（`GUIManagerPatch.cs:5,8,15,25`） | 读的是 `pinger.character.refs.mainRenderer`（`PingDistanceManager.cs:404-407`），即 **Character** 的 mainRenderer，非 `Item.mainRenderer` | 无冲突 |
| — | `MMHOOK\Managed\MMHOOK_Assembly-CSharp.dll` | — | MonoMod 自动生成的 hook 程序集，非插件、不自行打补丁 | — | 无冲突 |
| — | `PlushieSwap\PlushieSwap.dll` | 本模组自身 | 见 1.5（部署版与 `src/` 不一致） | — | — |

### 1.2 `PeakSafeOptimizer` 与本模组的关键交互（重点）

**`IKItemGuard`（默认启用，本机 config `IKItemGuard = true`）**
- 目标：`CharacterAnimations.ConfigureIK`（`IKItemGuardPatch.cs:56`）。
- 前缀逻辑（`IKItemGuardPatch.cs:66-98`）：读 `currentItem.transform.Find("Hand_L")` / `Find("Hand_R")`；`Hand_L` 缺失 → `return false`（**短路整个 ConfigureIK**）；`Hand_R` 缺失 → 只复现左手写入后 `return false`。
- 与本模组的关系：本模组（`src/`）**从不删除、也不写入** `Hand_L`/`Hand_R`（`PlushieModel.cs:1066-1070` 明确注释"anchors 保持原版值不动"）。因此两条 `Find` 都命中，IKItemGuard 返回 `true`，`ConfigureIK` 正常执行 → **无行为冲突**。
- 与**部署 DLL** 的关系：部署 DLL 额外 patch 了 `CharacterItems.GetItemPosLeft/GetItemPosRight/GetItemPosLeftWorld/GetItemPosRightWorld`（见 1.5）。调用链 `ConfigureIK → GetItemPosLeft → 本模组 postfix` 依次执行，功能上可组合。唯一可疑处：IKItemGuard 的 `ReproduceLeftHandWrites`（`:100-132`）用 `Initialize()` 时创建的委托调用 `GetItemPosLeft`；该委托是否包含 Harmony postfix 取决于 Harmony 是否重定向了 JIT 入口。该分支**只在 `Hand_R` 缺失时进入**，而本模组不会造成 `Hand_R` 缺失，所以实际不可达 → **风险可忽略，但存在顺序依赖，值得记录**。
- 若两者都启用且用户报告"手部位置抖动"，第一件事是把 `PeakSafeOptimizer` 的 `IKItemGuard` 设为 `false` 复测。

**`RemoteClusterAnimationThrottle`（本机 config 为 `true`）**
- 目标：`CharacterRagdoll.FixedUpdate`（`RemoteClusterAnimationThrottlePatch.cs:89`），其替换实现里**主动调用** `refs.animations.ConfigureIK()`（`:250`），仅对 60m 外的远程角色生效。
- 影响：它改变了 `GetItemPos*` 的**求值时机**（在手动 `FixedUpdate` 中），不影响本模组补丁的正确性；但本模组的每帧扫描（`MaintainTrackedItems`）也会处理远程角色的物品。二者叠加只是 CPU 开销，无正确性冲突。

**`ItemScaleRedundantWrite`（config true）**
- 目标：`ItemScaleSyncer.Update`（`ItemScaleRedundantWritePatch.cs:89`），读 `Item.mainRenderer`（`:64,151`）。
- 关键事实：`BingBong` / `BingBong_Prop Variant` 的组件清单里**没有 `ItemScaleSyncer`**（实测 `D:\zhuanban\youhua\item_truth.json` 的 BingBong 块：`Action_AskBingBong, BingBong, BingBongMouth, BingBongsVisuals, Item, ItemCooking, ItemImpactSFX, ItemParticles, ItemPhysicsSyncer, ItemUseFeedback, LootData, PhotonCleanupHelper, PhotonView`）。→ 该 lane 对 BingBong **永不执行** → 无冲突。

**`ItemCollisionMode`（config true）**
- 目标：`Item.UpdateCollisionDetectionMode`（`ItemCollisionModePatch.cs:67`），按 `itemState` 切换 `rig.collisionDetectionMode`。
- 本模组不碰 `item.rig`、不碰 `itemState` 之外的碰撞设置 → 无冲突。

### 1.3 `ScrapClean` 的真实交互（唯一发现"别的模组写 Item 子树 renderer 的 MaterialPropertyBlock"）

- `HighlightRenderer.Apply`（`ScrapClean\HighlightRenderer.cs:88-103`）：
  ```csharp
  renderer.GetPropertyBlock(_block);
  _block.SetFloat(InteractableId, value);   // InteractableId = Item.PROPERTY_INTERACTABLE ("_Interactable")
  renderer.SetPropertyBlock(_block);
  ```
  它通过 `CenterCache.TryGetRenderers(root)` → `GetComponentsInChildren<Renderer>(true)`（`CenterCache.cs`）收集**整棵子树**的 renderer。本模组的替换模型（`Model` + `Outline`）正是 `Item` 的子节点 → **会被一起收进高亮列表**。
- 触发条件：`TargetScanner.TryAddItem` 要求 `item.itemState == ItemState.Ground && item.rig != null`（`TargetScanner.cs:260`）。**地面上的 BingBong 满足条件**，因此清理模式下确实会把 `_Interactable` 写进本模组的 renderer。
- 冲突性质：**不是补丁冲突，而是 property block 互相覆盖**。ScrapClean 先 `GetPropertyBlock`（读到本模组写入的 `_BaseColor`/`_EmissionColor`）再加 `_Interactable` 写回，**不破坏**烹饪 tint；但本模组的 `ApplyCookTint`（`PlushieModel.cs:1313-1325`）会 `CookBlock.Clear()` 后整块覆盖 → **清掉 ScrapClean 的高亮**，ScrapClean 下一帧 `EndFrame` 再加回来。
- 实测后果：清理模式下的范围指示高亮**在替换模型上会闪/贴不住**；对原版 BingBong 无此问题（因为原版 renderer 被本模组 `enabled=false`，ScrapClean 的 `TryGetBounds` 会跳过 `!val.enabled` 的 renderer，但 `Mark` 不看 enabled）。
- 严重度：**低**（需要用户主动进入清理模式、且目标在半径内）。修复成本也低：`ApplyCookTint` 改成 `GetPropertyBlock` 后增量写而不是 `Clear()`。

### 1.4 `SimpleTweaks` 的 `SetActive(false)` 绕过路径

- `BackpackSwapPatch.Body`（`SimpleTweaks\BackpackSwapPatch.cs:58-63`）：
  ```csharp
  if (PhotonNetwork.IsMasterClient) {
      BackpackSwapLogic.DoSwapLogic(interactor, value, bpRef, b);
      BackpackSwapLogic.RefreshHandVisual(interactor, value);
      ((Component)__instance).gameObject.SetActive(false);   // ← 绕过 Item.HideRenderers
      return false;                                          // ← 同时跳过 Item.Interact 本体
  }
  ```
- 作用对象是**背包物品本体**，不是 BingBong。但背包物品被 `SetActive(false)` 后，任何挂在它子树下的物体（含被放进该背包的玩偶视觉）也会一起失效，**完全不经过 `Item.HideRenderers`**。
- 本模组的兜底：`Item.SetState` 前缀/后缀（`Patches.cs:33-55`）+ 每帧 `MaintainTrackedItems`（`PlushieModel.cs:747-760`）+ 0.5s 重扫（`:765-779`）。物品重新激活后下一轮同步即恢复 → **可自愈**。
- `BackpackSwapLogic.DoSwapLogic` 调的是 `ItemSlot.SetItem`（`BackpackSwapLogic.cs`），**不是** `InventoryItemUI.SetItem`，与本模组的 UI 补丁不同名不同类 → 无冲突。
- 严重度：**低**。

### 1.5 ⚠️ 部署 DLL 与 `src/` 的补丁集差异（本次审计最重要的兼容性事实）

| 项目 | `plugins\PlushieSwap\PlushieSwap.dll`（部署中） | `dist\PlushieSwap\PlushieSwap.dll` | `src/`（HEAD = `bc696a9`） |
|---|---|---|---|
| buildinfo commit | `59cb988` | `bc696a9` | — |
| buildinfo 时间 (UTC) | 2026-09-19T16:08:43Z | 2026-09-19T18:27:25Z | — |
| SHA256 | `724B35B5…B669B6A` | `582E1B00…3F68524` | — |
| `GripInset.cs` | **有** | 无 | 无 |
| `Hand Inset` 配置项 | **有**（默认 1.0，范围 0–1） | 无 | 无 |
| `CharacterItems.GetItemPosLeft/Right/LeftWorld/RightWorld` 补丁 | **有 4 条** | 无 | 无 |
| `DiagnosticLog.cs` / `Verbose Logging` | **无**（直接 `Log.LogInfo`） | 有 | 有 |
| `HoldOffsetFor` | `(asset, scale)`，`anchorMid - waistMid * scale` | `(asset, scale)` 同 | `(asset, scale)` 同（`PlushieModel.cs:1114-1132`） |

- 部署 DLL 的实际补丁集（反编译 `compat-decomp\__PlushieSwap_installed\`）：
  `Item.Start`、`Item.OnEnable`、`Item.SetState`(×2)、`Item.HideRenderers`、`Item.GetName`、`Item.ItemUIData.GetIcon`、`InventoryItemUI.SetItem`、`ItemCooking.UpdateCookedBehavior`、`BackpackOnBackVisuals.InitRenderers`，**外加** `CharacterItems.GetItemPosLeftWorld`、`GetItemPosRightWorld`、`GetItemPosLeft`、`GetItemPosRight`。
- 而 `59cb988` 的 git 树里 `src/` **不含** `GripInset.cs`（`git ls-tree -r --name-only 59cb988 -- src` 已验证），`git log -S "Hand Inset"` 与 `git log --all -- "*GripInset*"` 均**无结果**（该文件从未进入版本库）。
- **根因**：`build.ps1` 的 `Get-BuildInfo`（`build.ps1:39-55`）只执行 `git rev-parse --short HEAD`，**从不检查工作树是否 dirty**（全文无 `--porcelain` / `diff-index` / `dirty`）。所以"commit: 59cb988"是误导性的：它记录的是 HEAD，而不是构建所用的实际源码状态。
- **运行时证据**：`BepInEx\LogOutput.log` 里大量 `Grip inset Hand_L: anchor node x=-0.35900, authored -0.35900, corrected toward -0.35701` 与 `… Hand_R: anchor node x=0.14002, authored 0.24000 (MOVED BY THE GAME) …` —— 证实线上跑的就是带 GripInset 的旧 DLL，且游戏确实在改写手部锚点。
- 该差异**直接改变兼容性结论**：`src/` 的补丁面与 `PeakSafeOptimizer.IKItemGuard` 零重叠；部署 DLL 的补丁面则与 IKItemGuard 落在同一条 `ConfigureIK → GetItemPosLeft` 调用链上。详见末节 H1。

### 1.6 四个指定子问题的直接回答

| 问题 | 答案 | 证据 |
|---|---|---|
| 是否有别的模组也替换 BingBong 模型（硬冲突） | **当前安装：没有。** 唯一会替换的是 ScallionMiku，而它**不在 plugins 里**。若安装 ScallionMiku 1.0.5 → **硬冲突，不可共存**（9 个目标完全重叠 + 都会在 item 下挂模型） | `plugins` 目录清单（21 个 DLL）；递归搜 `*Miku*/*Scallion*/*Fufu*/*BingBong*` 于 `D:\SteamLibrary\steamapps\common\PEAK` 结果为空；ScallionMiku 补丁行 `ItemPatch.cs:3949,3960,3967,3974,4007,4039,4049,4251,4290` |
| 是否有模组读写 `Item` 的 renderer / material / MaterialPropertyBlock / `mainRenderer` | **写 property block：ScrapClean**（`_Interactable`，仅清理模式+地面物品，见 1.3）。**读 `Item.mainRenderer`：无**（PeakSafeOptimizer 读的是 `ItemScaleSyncer` 场景，而 BingBong 无该组件）。**改材质/shader：PEAKTrails** 只对 `Character` 上的 `TrailRenderer` 用 `Sprites/Default`（`Patching.cs:235`），不在 Item 子树。其余 material 写入均为 TMP/UI 字体材质 | `HighlightRenderer.cs:88-103`；`ItemScaleRedundantWritePatch.cs:64,151`；`item_truth.json` BingBong 组件表；`Patching.cs:235` |
| 是否有模组调用 `HideRenderers` / `SetActive(false)` 绕过本模组钩子链 | **无人 patch / 调用 `Item.HideRenderers`**（它是 `private`，`Item.cs:783`）。**`SimpleTweaks`** 对背包物品 `gameObject.SetActive(false)`（`BackpackSwapPatch.cs:62`）→ 绕过，作用于背包本体。**`ScrapClean`** 用 `PhotonNetwork.Destroy` 直接删除地面物品（`Cleaner.cs` `DestroyNow`）。**`PeakSafeOptimizer`** 只在 `PlayerNameUiWritesPatch.cs:108` **校验** `GameObject.SetActive` 存在，并不 patch 它 | 全量补丁提取；`Item.cs:783`；`BackpackSwapPatch.cs:62`；`Cleaner.cs`；`PlayerNameUiWritesPatch.cs:108,142` |
| 是否有模组 patch `CharacterAnimations.ConfigureIK` 或 `CharacterItems` 的手部方法 | **`ConfigureIK`：有 —— `PeakSafeOptimizer.IKItemGuardPatch`（默认启用）**，前缀读 `Hand_L`/`Hand_R`，缺失即短路。**`CharacterItems` 手部方法：第三方模组无人 patch；但本模组部署 DLL 自己 patch 了 4 个**（`src/` 已移除）。`RemoteClusterAnimationThrottle`（本机启用）会主动调用 `ConfigureIK()` | `IKItemGuardPatch.cs:56,66-98`；`__PlushieSwap_installed\PlushieSwap.Patches\GripInset.cs:131,139,147,155`；`RemoteClusterAnimationThrottlePatch.cs:250` |

---

## 任务 2：ScallionMiku 逐项深度对比

> 所有"ScallionMiku 做法"均给出 `文件:行号`；"本模组做法"均给出 `src/` 文件行号。

### 2.1 汇总表

| # | 项目 | ScallionMiku 做法（文件:行） | 本模组做法（文件:行） | 差异 | 判定 |
|---|---|---|---|---|---|
| 1 | 挂载替换模型的父节点 | `mikuObject.transform.SetParent(item.transform, false)`（`ItemPatch.cs:3679`）——父节点是 **Item 根** | `ResolveVisualParent` 优先 `item.transform.Find("Holder")`，否则回退 item 根（`PlushieModel.cs:901-914`），`SetParent(parent,false)`（`:932`） | ScallionMiku 挂 Item 根；本模组挂 `Holder` | **本模组更优**：`Holder` 是游戏 `Squish` 动画唯一驱动的节点（本模组注释 `:883-900`），挂上去才能白嫖挤压动画；ScallionMiku 因此必须自实现挤压（见 #6） |
| 2 | 局部坐标/旋转/缩放 | 硬编码常量：`BaselineMikuLocalPosition = (-0.06, -0.5, 0)`（`:480`）；`WorldMikuLocalRotation = identity`（`:482`）；`BundledWorldMikuLocalRotation = Euler(0,180,0)`（`:483`）；held 用 `Euler(10,0,0)` / `Euler(10,180,0)`（`:485-486`）；`ResolvePoseByState`（`:616-654`） | `rootObject.localPosition = zero` / `localRotation = identity` / `localScale = one`（`PlushieModel.cs:1076-1078`）；缩放按状态取 `WorldScale`/`BackpackScale`（`:1471-1489`） | ScallionMiku 用「模型局部常量 + 180° 翻转」补偿其 PMX 朝向；本模组的 `.psmesh` 管线已把模型摆到与原版一致的位置/朝向，故无需常量 | **各有取舍**：ScallionMiku 的常量是**为其单一模型**手调的（换模型即失效）；本模组的零偏移依赖构建管线保证，可复用但一旦 `.psmesh` 管线出错就无兜底 |
| 3 | 手持位置（常量偏移/数值） | 单一常量，held 与非 held 同值：`HeldMikuLocalPosition = BaselineMikuLocalPosition = (-0.06, -0.5, 0)`（`:480,484`）；`CompensateRuntimeScalePosition` 是**空实现，直接 return basePosition**（`:611-614`） | `HoldOffsetFor = anchorMid - waistMid * scale`，`anchorMid = (-0.0595, -0.1405, -0.0400)`（`PlushieModel.cs:1114-1132`），**只在 `ItemState.Held` 时施加**（`:1253-1265`） | ScallionMiku：**硬编码、与模型无关、与缩放无关、世界状态也偏移**；本模组：**从模型自身握点推导、随 scale 线性补偿、只在手持时偏移** | **本模组明显更优**。本模组注释已指出 `scale` 因子的必要性（`:1097-1099`：不加 scale，在 0.3 倍时偏移误差达模型高度的 40%）。ScallionMiku 的 `(-0.06,-0.5,0)` 中 Y=-0.5 远大于本模组的 -0.1405，是因为其 PMX 模型 pivot 不同，**不可直接照搬数值** |
| 4 | 隐藏原版模型 | `DisableOriginalRenderers`（`:1458-1472`）：`renderer.forceRenderingOff = true; renderer.enabled = false;`（排除 `IsMikuTransform`）；`EnableOriginalRenderers`（`:1474-1488`）同时清 `forceRenderingOff` 与 `enabled` | `SetVanillaRenderersEnabled`（`PlushieModel.cs:1366-1381`）：**只写 `renderer.enabled`**，不写 `forceRenderingOff` | ScallionMiku 多一层 `forceRenderingOff` 保险 | **ScallionMiku 可借鉴**（见 H3）。注意必须**成对**实现（开/关都写两个字段），否则会留下"原版网格永久不可见"的泄漏 |
| 5 | 图标与物品名 | `GetIcon` postfix：`__instance.itemName == "Bing Bong"` 时替换（`ItemPatch.cs:4039-4047`）；`GetName` postfix（`:4049-4057`）；**`GetItemName` postfix 也替换**（`:4059-4067`）；图标来自 `Plugin.MochiTexture`（`Plugin.cs:163-168`，由 `ScallionMikuUI.png` 或 bundle 内 `身体.png` 加载，`:1727`） | `GetIcon` postfix 经 `IsVanillaBingBongName` 匹配（`Patches.cs:94-113`）；`GetName` postfix（`:78-92`）；**刻意不 patch `GetItemName`**（注释 `:74-76`）；**额外** patch `InventoryItemUI.SetItem` 修复"同 prefab 短路导致图标不刷新"（`:115-165`）；图标来自嵌入/松散 PNG（`PlushieIcons.cs:14-57`） | 本模组多一条 `InventoryItemUI.SetItem` 补丁；ScallionMiku 多一条 `GetItemName` 补丁 | **本模组更优**。游戏 `Item.GetItemName`（`Item.cs:477-500`）用 `GetName()` 的返回值套进 `COOKED_COOKED/COOKED_BURNT/COOKED_INCINERATED` 模板；ScallionMiku 直接覆盖 `GetItemName` 的返回值 → **会吞掉"烤熟/烤焦"前缀**，而本模组只覆盖 `GetName`，模板拼接仍然生效。本模组注释已论证这一点（`Patches.cs:74-76`） |
| 6 | 挤压动画 | **自实现**：`MikuDeformGuard`（`ItemPatch.cs:179-321`）。`SqueezeDuration = 0.78f`（`:181`）、`SqueezeCompressPhase = 0.42f`（`:182`）、`IsHeldAndUsing` 检查 `isUsingPrimary \|\| isUsingSecondary`（`:217-222`）、`EvaluateSingleSqueezeWeight` 用 `Mathf.SmoothStep`（`:240-255`）、`GetDesiredRootScale` 缩放因子 `(1-0.14w, 1+0.11w, 1-0.14w)`（`:257-269`），并逐帧把子节点 localScale 复位（`:307-319`） | **借用游戏自身**：挂在 `Holder` 下（`PlushieModel.cs:883-914`），`Action_AskBingBong.RunAction → RPC "Ask" → squishAnim.SetTrigger("Squish")`（游戏侧 `Action_AskBingBong.cs`）驱动 `Holder.localScale` 与两个手部锚点的 `localPosition` | ScallionMiku 硬编码 0.78s/0.42/±14%/±11% 复刻观感；本模组复用 Animator clip | **本模组更优**（免维护、数值永远与游戏一致）。**但需注意一个真实的取舍**：游戏 clip 同时动画化 `Hand_L/Hand_R` 的 `localPosition`，这正是 `LogOutput.log` 里 `Hand_R … (MOVED BY THE GAME)` 的来源；ScallionMiku 挂 Item 根恰好规避了这一点（这也是它后来删掉 Hand Inset 实验的原因，见 `62724d4` 提交信息） |
| 7 | patch 了哪些游戏方法 / 是否 patch 手部锚点 | 见 2.2 全表。**不 patch 任何手部/锚点方法** | 见 2.2 全表。`src/` **也不 patch 手部/锚点**；**部署 DLL patch 了 4 个 `CharacterItems` 手部方法** | 部署版与 `src/` 不同；两者与 ScallionMiku 在这点上都不重叠 | **各有取舍**：`src/` 与 ScallionMiku 同样选择"不动锚点"，是经过验证的方案（`PlushieModel.cs:1238-1252`）；部署版的 GripInset 是已被上游删除的实验残留 |
| 8 | 背包 / 地面 / 多人同步 | 背包：`IsInBackpack`（`:525-528`）+ `ResolveScaleByState` 用 `BackpackScaleMultiplier`（`:593-599`）+ `SyncCollidersByState`（`:2827-2864`）+ `Item_PutInBackpackRPC_Postfix`（`:4025-4030`）+ `Item_ClearDataFromBackpack_Postfix`（`:4032-4037`）。**零 Photon 代码**（全库 grep `Photon|RPC|IsMasterClient|IsMine` 仅命中补丁属性名）→ 纯客户端每实例视觉 | 背包：`IsWornBackpack` 走 `BackpackReference.IsOnMyBack()`（`PlushieModel.cs:1392-1416`）；`Item.SetState` 前缀清/后缀重建（`Patches.cs:33-55`）；`Item.HideRenderers` postfix（`:57-68`）；每帧 `MaintainTrackedItems` + 0.5s 重扫（`PlushieModel.cs:725-780`）。**零 Photon 代码** | ScallionMiku 多 patch `PutInBackpackRPC` / `ClearDataFromBackpack` 两个事件点；本模组用 `SetState` + 每帧扫描覆盖同样范围 | **各有取舍**：ScallionMiku 的事件点更贴、响应更即时；本模组的每帧扫描覆盖更多"绕过事件"的路径（例如 1.4 的 `SetActive(false)`），代价是 CPU |
| 9 | 材质与 shader 方案 | 身体：`CreateRendererMaterialInstance`（`ItemPatch.cs:995-1094`）；shader 候选 `URP/Lit → Standard → W/Peak_Standard`（`:956`，`Plugin.cs:2225`）；**用 `material.color = Color.white`**（`Plugin.cs:2236`）；设 `_Tint`/`_BaseColor`/`_Color` 为保留色（`:1064-1068`）；`_Cull = Off`（`:1077`）；**关闭自发光**（`ApplyRealisticMaterialTuning`，`:947-951`）；`_Smoothness = 0.3`（`:938`） | 身体：`GetMaterial`（`PlushieModel.cs:375-459`）；shader 候选 `URP/Lit → URP/Simple Lit → W/Peak_Standard → Standard`（`:612-618`）；**刻意不用 `Material.color`**（注释 `:389-393`，因为 URP/Lit 无 `_Tint`，会刷 Unity 报错）；用调色板纹理 + 低灰自发光（`:433-450`）；`_Smoothness = 0.14`（`:423`） | 本模组多一个 shader 候选；关键差异是**属性写入方式**与**自发光策略** | **本模组更优**：`Plugin.cs:2236` 的 `material.color = Color.white` 正是本模组注释 `PlushieModel.cs:389-393` 点名会触发 `_Tint` 报错的写法；本模组用 `HasProperty` 逐项判断 + `_BaseColor`/`_EmissionColor` 组合，且自发光用调色板做 emission map（亮部提亮、暗部不发光）是 ScallionMiku 没有的效果 |
| 10 | 描边方案 | **完全没有描边**。全库 grep `outline/shell/inflate/extrude/inverted/hull/stroke` 无任何描边实现；唯一的 `_Cull` 写入全是 `CullMode.Off`（`ItemPatch.cs:1077`、`Plugin.cs:2248`、`RuntimePmxLoader.cs:2654,2696`） | 反向外壳 + 屏幕空间恒定像素宽：`GetOutlineMaterial`（`PlushieModel.cs:470-542`，`_Cull = Front` 于 `:523-524`）；`PlushieOutline.Attach`（`PlushieOutline.cs:67-120`）每帧在 CPU 重写顶点 | ScallionMiku 无此功能 | **本模组独有优势**（相对 ScallionMiku） |
| 11 | 每帧校验频率 | **分桶降频**：`ShouldRunPerFrameReplacementValidation`（`:3512-3539`）——held 每 8 帧、backpack 每 20 帧、world 每 4 帧；另有 `MikuRendererGuard` 0.1s 保活（`:328,342-392`）；`ShouldSkipVisibilitySync` 缓存上次状态跳过冗余写入（`:3461-3486`） | `MaintainTrackedItems` 对**每个**被跟踪物品**每帧**调 `SyncVisual`（`PlushieModel.cs:747-760`），另有 0.5s 全量重扫（`:68,765-779`） | 本模组每帧全量，无分桶 | **本模组有缺陷（可借鉴 ScallionMiku）**：物品多时有可测的 CPU 浪费。不过本模组内部是"廉价值比较，无事发生"（注释 `:741-746`），实际开销取决于物品数 |
| 12 | 碰撞体代理 | 为替换模型重建碰撞代理：`RebuildModelColliders`（`:2720-2772`）、`EnsureCollisionProxyRoot`（`:1773-1825`）、`SyncCollidersByState`（`:2827-2864`）、`AddConvexMeshColliderForMeshRenderer`（`:1587-1610`） | **完全不动原版碰撞体**（不改 `item.colliders`、不新增 Collider） | ScallionMiku 因为 Miku 模型与 BingBong 外形差异大才需要重建；本模组的 `.psmesh` 已归一到原版轮廓 | **各有取舍**：本模组更简单、风险更低；但若玩家把 `World Scale` 拉到 3.0，替换模型的物理体积与隐藏的原版碰撞体将不匹配（原版碰撞体不随缩放变），这一点本模组没有处理 |
| 13 | 清理替换体上的杂项组件 | `SanitizeVisualObject`（`:3204-3275`）：销毁 Collider/Rigidbody/Joint/LODGroup/MonoBehaviour（白名单见 `IsWhitelistedBehaviour` `:3192-3199`）、统一 tag/layer；`RemoveUnwantedFootAttachments`（`:3299-3331`）按名字关键词删脚部"手型"网格 | 只新建 `PlushieSwap_Visual/Model` + `Outline` 两个空 GameObject，仅挂 `MeshFilter`/`MeshRenderer`（`PlushieModel.cs:931-966`） | 本模组的替换体是"自己造的裸物体"，没有需要清理的第三方组件 | **本模组更优**（无需该逻辑；且 `.psmesh` 来源可控，不像 PMX 会带一堆脚本） |
| 14 | `Item.mainRenderer` 处理 | 两套路径：`KeepOriginalRendererRefs` 在 bundle 路径下返回 `true`（`Plugin.cs:190-193`），`EnsureItemRendererRefs` 于是**保留原版 renderer 引用**（`ItemPatch.cs:3080-3090`）；**运行时 PMX 路径下**则把 `item.mainRenderer` **改指向 Miku 的 renderer**（`:3125`）并调 `EnsureRendererMainTexCompatibility` 给它补 `_MainTex`（`:2960-3000`）；`RestoreOriginalItemRendererRefs`（`:3129-3141`）负责还原 | **刻意永不重指** `mainRenderer`，`PlushieModel.cs:968-996` 用三条理由论证：① URP/Lit 无 `_Interactable`，重指也不会高亮；② `Item.AddPropertyBlock` + `HoverEnter/Exit` 会整块覆盖 `mainRenderer` 的 property block，**打断烹饪 tint**；③ `Item.Center()` 返回 `mainRenderer.bounds.center`，被 AOE/蜂巢/岩浆/WindChill/罗盘距离等玩法读取 | ScallionMiku 在 PMX 模式下会把玩法用的 `mainRenderer` 换成视觉模型 | **本模组更优且更有意识**。实证：`Item.cs:502-511`（`AddPropertyBlock` 读 `mainRenderer`）、`:1139-1155`（`HoverEnter/Exit` 写 `mainRenderer` + `addtlRenderers`）、`:662-666`（`Center()` 读 `mainRenderer.bounds`）。另外 `ItemScaleSyncer.ApplyScale` 会写 `item.mainRenderer.transform.localScale`（`ItemScaleSyncer.cs:49`）——虽然 BingBong 没有该组件，但这说明**重指 `mainRenderer` 会把物品缩放写到错误节点上**，是本模组决策的额外佐证 |
| 15 | 配置迁移 / 兼容旧版 | `MigrateLegacyConfigIfNeeded`（`Plugin.cs:416-…`）把 `com.github.Thanks.MikuBongFix` / `com.github.FelineEntity.MikuBongFix` 的旧 cfg 迁移过来（`LegacyPluginIds`，`Plugin.cs:39-43`） | `MigrateConfigDefaults` 用带版本号的迁移表（`Plugin.cs:71-144`），并明确论证 `From` 必须是 0 而非 1（`:56-61`） | 解决的是不同问题（ScallionMiku 迁 GUID，本模组迁默认值） | **各有取舍**，无优劣 |
| 16 | 每帧"保活"守卫 | `MikuRendererGuard`（`:326-452`）：0.1s 间隔强制 `gameObject.SetActive(true)`、`forceRenderingOff=false`、`enabled=true`；**并在 `renderer.HasPropertyBlock()` 时 `renderer.SetPropertyBlock(null)`**（`:436-439`） | 无独立守卫；靠 `MaintainTrackedItems` 每帧重新 `SetVanillaRenderersEnabled(false)` + `SyncVisual` | ScallionMiku 有专门的抗干扰守卫 | **各有取舍**。⚠️ 注意：ScallionMiku 的 `SetPropertyBlock(null)`（`:438`）会**清空**渲染器上的 property block——若与本模组的 `ApplyCookTint` 同时存在会互相抹除。这也反证两者不可共存 |

### 2.2 补丁目标全表对照

| 目标方法 | ScallionMiku（`ScallionMiku-main\`） | 本模组 `src/` | 本模组部署 DLL |
|---|---|---|---|
| `Item.Start` | ✅ `ItemPatch.cs:3949` | ✅ `Patches.cs:17` | ✅ |
| `Item.OnEnable` | ✅ `ItemPatch.cs:3960` | ✅ `Patches.cs:25` | ✅ |
| `Item.SetState`（前缀+后缀） | ✅ `ItemPatch.cs:3967,3974` | ✅ `Patches.cs:33,49` | ✅ |
| `Item.Update` | ✅ `ItemPatch.cs:3981` | ❌ | ❌ |
| `Item.RequestPickup`（前缀+后缀） | ✅ `ItemPatch.cs:3993,4000` | ❌ | ❌ |
| `Item.HideRenderers` | ✅ `ItemPatch.cs:4007` | ✅ `Patches.cs:57` | ✅ |
| `Item.PutInBackpackRPC` | ✅ `ItemPatch.cs:4025` | ❌ | ❌ |
| `Item.ClearDataFromBackpack` | ✅ `ItemPatch.cs:4032` | ❌ | ❌ |
| `Item.ItemUIData.GetIcon` | ✅ `ItemPatch.cs:4039` | ✅ `Patches.cs:94` | ✅ |
| `Item.GetName` | ✅ `ItemPatch.cs:4049` | ✅ `Patches.cs:78` | ✅ |
| `Item.GetItemName` | ✅ `ItemPatch.cs:4059`（**会吞掉烤制前缀**） | ❌（刻意） | ❌ |
| `InventoryItemUI.SetItem` | ❌ | ✅ `Patches.cs:129` | ✅ |
| `ItemCooking.UpdateCookedBehavior` | ✅ `ItemPatch.cs:4290`（**完整重写，返回 false**） | ✅ `CookingPatches.cs:61`（**只填缓存，返回 true 让原逻辑继续**） | ✅ |
| `ItemCooking.CookVisually` | ✅ `ItemPatch.cs:4330` | ❌ | ❌ |
| `BackpackOnBackVisuals.InitRenderers` | ✅ `ItemPatch.cs:4251` | ✅ `CookingPatches.cs:97` | ✅ |
| `BackpackOnBackVisuals.CookVisually` | ✅ `ItemPatch.cs:4261` | ❌ | ❌ |
| `Action_AskBingBong.AskRoutine(int,bool)` | ✅ `TalkingBingBong\Patch_AskRoutine.cs:11`（**整段替换成自定义语音**） | ❌ | ❌ |
| `CharacterItems.GetItemPosLeft` | ❌ | ❌ | ✅ **`GripInset.cs:147`** |
| `CharacterItems.GetItemPosRight` | ❌ | ❌ | ✅ **`GripInset.cs:155`** |
| `CharacterItems.GetItemPosLeftWorld` | ❌ | ❌ | ✅ **`GripInset.cs:131`** |
| `CharacterItems.GetItemPosRightWorld` | ❌ | ❌ | ✅ **`GripInset.cs:139`** |
| `CharacterAnimations.ConfigureIK` | ❌ | ❌ | ❌ |
| **与 9 个目标的重叠数** | **9 / 9** | **9 / 9** | **9 / 9** |

### 2.3 烹饪 tint 处理的深入对比

| 维度 | ScallionMiku | 本模组 |
|---|---|---|
| `ItemCooking.UpdateCookedBehavior` | **前缀返回 `false`，完整复刻原方法**（`ItemPatch.cs:4290-4328`）：自己处理 `preCooked`（`:4306-4309`）、`CookVisually` 委托（`:4314`）、`ChangeStatsCooked` 循环（`:4316-4323`）、`RunAdditionalCookingBehaviors`（`:4325`）、`timesCookedLocal` 回写（`:4326`） | **前缀只填缓存并置 `setup=true`，返回 `true`**（`CookingPatches.cs:61-94`）→ 游戏原逻辑照常执行 |
| 缓存构建 | `EnsureItemCookingRendererCache`（`:4222-4249`）额外检查"缓存里是否混进了 Miku 的 renderer"并重建 | 只在 `setup == false` 时构建一次（`CookingPatches.cs:66-68`），并用 `IsPlushieTransform` 排除本模组的 renderer（`:77,84`） |
| `_Tint` 读取 | `GetSafeTint`（`:4098-4121`）依次尝试 `_Tint → _BaseColor → _Color`，避免无 `_Tint` 时 Unity 报错 | `ReadTints`（`CookingPatches.cs:129-152`）用 `material.HasProperty(TintId)` 判断，否则填 `Color.white` |
| `_Tint` 写入 | `TryApplyTint`（`:4123-4129`）写 `material.SetColor("_Tint", color)`；`renderer.material` 会实例化每渲染器材质副本，但**写入的是材质本身**，跨实例不共享靠 `material` 的隐式实例化 | **`MaterialPropertyBlock`**：`ApplyCookTint`（`PlushieModel.cs:1295-1326`）用复用的 `CookBlock`，只写 `_BaseColor` 与 `_EmissionColor`，**从不碰共享 Material** |
| 额外覆盖点 | 还 patch `ItemCooking.CookVisually`（`:4330`）与 `BackpackOnBackVisuals.CookVisually`（`:4261`），重写整段着色逻辑 | 不 patch 这两个；靠每帧读 `CookedAmount` 自行重算（`ReadCookedAmount`，`:1335-1354`） |
| 判定 | **本模组更优** | 理由：① ScallionMiku 完整复刻了 `ItemCooking` 的私有字段与调用顺序（`preCooked`/`timesCookedLocal`/`ignoreDefaultCookBehavior`/`ChangeStatsCooked`），游戏一改就崩；本模组只改"谁来发现 renderer"这一件事。② `MaterialPropertyBlock` 是 Unity 为"每渲染器覆盖"设计的机制，而 `material.SetColor` 会实例化材质（内存 + 材质泄漏风险）。③ 本模组额外把 `_EmissionColor` 一起缩放（`:1321-1323`），否则烤焦的玩偶会继续发白光；ScallionMiku 直接关掉了自发光（`:947-951`），没有这个问题但也没有亮部提亮效果 |

### 2.4 参考模组中本模组**应该**借鉴的具体点（交给 Lead 的清单）

1. **`forceRenderingOff` 双字段隐藏**（`ItemPatch.cs:1458-1488`）
   本模组 `SetVanillaRenderersEnabled`（`PlushieModel.cs:1366-1381`）只写 `enabled`。若第三方模组或游戏逻辑把原版 renderer 的 `enabled` 重新置 true，原版网格会与替换模型**同时渲染**。建议改为同时写 `forceRenderingOff`，并**务必在开启路径上把两个字段都复位**（照抄 ScallionMiku 的成对实现），否则会留下永久不可见的原版网格。
   注意：本模组在切到 `Vanilla` 变体时会走 `DestroyReplacement`（`PlushieModel.cs:1134-1181`）→ `SetVanillaRenderersEnabled(item, true)`，所以开启路径是存在的，只要一并清 `forceRenderingOff` 即可。

2. **`mainRenderer` / `addtlRenderers` 的显式快照与还原**（`ItemPatch.cs:3129-3141` + `3080-3090`）
   本模组选择**不重指** `mainRenderer`（正确），但**没有记录它原本是谁**。一旦任何第三方模组（或未来本模组自己的改动）改写了 `item.mainRenderer`，本模组无从发现、也无从还原。建议在 `PlushieItemState` 上缓存 `mainRenderer`/`addtlRenderers` 的原始引用，并在每帧同步时校验"是否被外力改写"，必要时还原。这是纯增量、零风险的加固。

3. **每帧校验的分桶降频**（`ItemPatch.cs:3512-3539`）
   本模组对每个被跟踪物品**每帧**执行 `SyncVisual`（`PlushieModel.cs:747-760`）。建议照抄分桶策略：held 每 8 帧、backpack 每 20 帧、world 每 4 帧，并保留"状态变化时立即同步"的路径（本模组已有 `marker.LastState` 比较，`PlushieModel.cs:1193`，天然支持）。ScallionMiku 另有 `ShouldSkipVisibilitySync` 的状态缓存（`:3461-3486`），本模组的 `PlushieVisualMarker`（`PlushieModel.cs:22-28`）已经等价，无需重复。

4. **（可选）`Item.PutInBackpackRPC` / `Item.ClearDataFromBackpack` 两个事件点**（`ItemPatch.cs:4025-4037`）
   本模组用 `Item.SetState` + 每帧扫描覆盖了同样的状态转换，功能上不缺。但如果 Lead 想降低"进背包瞬间"的一帧延迟，这两个补丁是现成的事件点。

### 2.5 参考模组中本模组**不应**借鉴的点

1. **`Item.GetItemName` 补丁**（`ItemPatch.cs:4059-4067`）：会吞掉 `COOKED_COOKED` / `COOKED_BURNT` / `COOKED_INCINERATED` 前缀（游戏逻辑 `Item.cs:477-500`）。本模组 `Patches.cs:74-76` 的论证是正确的，不要改。
2. **重指 `item.mainRenderer`**（`ItemPatch.cs:3125`）：会打断 `ApplyCookTint`（`Item.cs:502-511` + `1139-1155` 的 `HoverEnter/Exit` 整块覆写）、并让 `Item.Center()` 的玩法判定跟着模型缩放漂移（`Item.cs:662-666`）。本模组 `PlushieModel.cs:968-996` 的三条理由成立。
3. **完整重写 `ItemCooking.UpdateCookedBehavior`**（`ItemPatch.cs:4290-4328`）：复刻了 4 个私有字段与 3 个私有方法，游戏一改就崩。本模组 `CookingPatches.cs` 的"只改 renderer 发现"策略更稳。
4. **`MikuRendererGuard` 的 `renderer.SetPropertyBlock(null)`**（`ItemPatch.cs:436-439`）：会清空 property block，与本模组的烹饪 tint 直接冲突。本模组不应引入这种"无条件清 block"的保活逻辑。
5. **硬编码手持常量 `(-0.06, -0.5, 0)`**（`ItemPatch.cs:480,484`）：数值是为 PMX 模型的 pivot 手调的，直接照搬到 `.psmesh` 模型上会把手持位置推到错误的地方。本模组的 `HoldOffsetFor`（`PlushieModel.cs:1114-1132`）从模型自身握点推导，是更好的方案。
6. **`MikuDeformGuard` 自实现挤压**（`ItemPatch.cs:179-321`）：本模组挂在 `Holder` 下复用游戏动画，数值永远与游戏一致；自实现会随游戏版本漂移。
7. **`CustomPrefabPool` 式的全局 prefab 池**（PEAKLib，非 ScallionMiku）：与本模组无关，但提醒不要为了加载模型而接管 Photon 的 prefab 解析。
8. **`Action_AskBingBong.AskRoutine` 整段替换**（`Patch_AskRoutine.cs:11`）：ScallionMiku 借此换成自定义语音，代价是接管了游戏原版的 `UpdateAttachedItem` 循环（`Action_AskBingBong.cs` 里 `AskRoutine` 每帧调 `UpdateAttachedItem`）。本模组若不需要换语音，不应接管这个方法。

---

## 需要 Lead 注意的高风险项

### H1 ⚠️⚠️ 部署 DLL 与 `src/` 不一致，且 `buildinfo.txt` 的 commit 是误导性的

- **事实**：`plugins\PlushieSwap\PlushieSwap.dll`（SHA256 `724B35B5…B669B6A`，buildinfo `commit: 59cb988`，`built_utc: 2026-09-19T16:08:43Z`）反编译后包含 `PlushieSwap.Patches\GripInset.cs`（162 行）与 `Hand Inset` 配置项（默认 1.0），并额外 patch `CharacterItems.GetItemPosLeft/GetItemPosRight/GetItemPosLeftWorld/GetItemPosRightWorld`；而 commit `59cb988` 的 `src/` 树**没有** `GripInset.cs`（`git ls-tree -r --name-only 59cb988 -- src` 已验证），`git log --all -S "GripInset"` / `git log --all -S "Hand Inset"` **均无结果**。
- **同时**：部署 DLL **没有** `DiagnosticLog.cs`，而 `src/`（HEAD `bc696a9`）与 `dist\` 都有。
- **根因**：`build.ps1:39-55` 的 `Get-BuildInfo` 只跑 `git rev-parse --short HEAD`，**从不检查工作树是否 dirty**（`build.ps1` 全文无 `--porcelain` / `diff-index` / `dirty`）。因此"commit: 59cb988"记录的是 HEAD，不是构建源码的状态。
- **影响**：
  1. 线上跑的补丁面**比 git 历史更大**，多出 4 个 `CharacterItems` 手部方法 → 与 `PeakSafeOptimizer.IKItemGuard` 落在同一条 `ConfigureIK → GetItemPosLeft` 链上（见 H2）。
  2. 任何"按 git commit 复现/审计线上行为"的尝试都会失败。
  3. 上游 `62724d4` 已经**明确删除**了 hand-inset 实验（提交信息：*"Remove the hand-inset experiment entirely. It could not be made stable: the long-press squash … has curves bound to Hand_L.position and Hand_R.position, and the clip's own values differ from the prefab's (Hand_L.x -0.376 vs -0.359), so the game rewrites the very node a correction was measured against."*），但线上仍是带该实验的旧版。
- **运行时证据**：`BepInEx\LogOutput.log` 中大量 `Grip inset Hand_L: anchor node x=-0.35900, authored -0.35900, corrected toward -0.35701`，以及 `Grip inset Hand_R: anchor node x=0.14002, authored 0.24000 (MOVED BY THE GAME), corrected toward 0.23801` —— 直接证实线上 DLL 就是旧版，且游戏确实在改写锚点。
- **建议**：由 Lead 决定（不在本审计权限内）：① 重新构建并部署 `src/` 版本；② 给 `build.ps1` 的 `Get-BuildInfo` 增加 dirty 检测（`git status --porcelain`，非空则把 commit 记为 `<sha>-dirty` 或直接拒绝出包）。②是防止复发的根本手段。

### H2 `PeakSafeOptimizer.IKItemGuard` 与部署 DLL 的 `GripInset` 同域（中风险，仅部署版）

- `PeakSafeOptimizer` 的 `IKItemGuard` **默认启用**（`IKItemGuardPatch.cs` + `OptimizerConfig.cs:73`，本机 `com.peak.safeoptimizer.cfg` 为 `IKItemGuard = true`），它前缀 `CharacterAnimations.ConfigureIK` 并读 `currentItem.transform.Find("Hand_L"/"Hand_R")`。
- 本模组**部署版**的 `GripInset` 同时 postfix 了 `CharacterItems.GetItemPosLeft/Right`，两者在 `ConfigureIK → GetItemPosLeft` 链上先后执行。
- 本模组（`src/` 与部署版）都**不删除、不写入** `Hand_L`/`Hand_R` 节点本身（`GripInset.cs` 只读 `val.localPosition.x`，`PlushieModel.cs:1066-1070` 明确不动锚点），所以 IKItemGuard 的两条 `Find` 都命中、返回 `true`，`ConfigureIK` 正常执行 → **功能上可组合**。
- **唯一残余风险**：IKItemGuard 的 `ReproduceLeftHandWrites`（`IKItemGuardPatch.cs:100-132`）用 `Initialize()` 时创建的委托调用 `GetItemPosLeft`；该分支仅在 `Hand_R` 缺失时进入（本模组不会造成此情况），因此实际不可达。
- **处置建议**：若用户报告手部抖动/位置异常，第一步把 `PeakSafeOptimizer` 的 `IKItemGuard` 设为 `false` 复测；同时优先按 H1 把部署 DLL 换成 `src/` 版本（换掉后此风险自动消失）。

### H3 原版 renderer 只用 `enabled` 隐藏，抗第三方 re-enable 能力弱（低风险，建议加固）

- 本模组 `SetVanillaRenderersEnabled`（`PlushieModel.cs:1366-1381`）只写 `renderer.enabled`；ScallionMiku 额外写 `forceRenderingOff = true`（`ItemPatch.cs:1469`）。
- 当前安装的模组中**没有任何一个**会 re-enable Item 子树的 renderer（`PeakSafeOptimizer` 的 `MikuRendererGuard` 等价物只存在于 ScallionMiku），所以**现在不会出问题**。
- 建议按 2.4(1) 加固，但必须成对复位 `forceRenderingOff`。

### H4 `ScrapClean` 的 `_Interactable` property block 与烹饪 tint 互相覆盖（低风险，真实存在）

- `ScrapClean\HighlightRenderer.cs:88-103` 会对 `Item` 整棵子树的 renderer 做 `GetPropertyBlock → SetFloat(_Interactable) → SetPropertyBlock`，而地面上的 BingBong 是其合法清理目标（`TargetScanner.cs:260` 只要求 `itemState == Ground && rig != null`）。
- 本模组 `ApplyCookTint`（`PlushieModel.cs:1313-1325`）用 `CookBlock.Clear()` 后整块 `SetPropertyBlock` → **会抹掉 ScrapClean 的高亮**，ScrapClean 下一帧再加回来。
- 现象：清理模式下范围高亮在替换模型上闪烁/贴不住。原版 BingBong 因为 renderer 被 `enabled=false`（`CenterCache.TryGetBounds` 会跳过 disabled 的 renderer）表现不同。
- 建议：把 `ApplyCookTint` 从 `Clear()` 改为"读回现有 block → 只改 `_BaseColor`/`_EmissionColor` → 写回"，可零成本消除该交互。

### H5 `SimpleTweaks` 的 `SetActive(false)` 绕过 `HideRenderers`（低风险，可自愈）

- `SimpleTweaks\BackpackSwapPatch.cs:62` 对**背包物品本体**调 `gameObject.SetActive(false)` 并 `return false` 跳过 `Item.Interact` 本体 → 完全不经过 `Item.HideRenderers`。
- 本模组靠 `Item.SetState` 前缀/后缀（`Patches.cs:33-55`）+ 每帧同步 + 0.5s 重扫自愈（`PlushieModel.cs:725-780`）→ 不需要改动，仅记录。

### H6 `PeakSafeOptimizer.RemoteClusterAnimationThrottle` 在本机被显式开启（信息项）

- 该 lane 默认 `false`（`OptimizerConfig.cs:98`），但本机 `com.peak.safeoptimizer.cfg` 里 `RemoteClusterAnimationThrottle = true`（用户手动开启，或 `BindExperimental` 的迁移导致）。
- 它会**主动调用** `refs.animations.ConfigureIK()`（`RemoteClusterAnimationThrottlePatch.cs:250`），仅对 60m 外远程角色生效。对本模组无正确性影响，但会改变 `GetItemPos*` 的求值时机。若后续排查远程玩家身上的玩偶位置异常，这是第一个要关的开关。

### H7 若用户安装 ScallionMiku → 硬冲突（信息项）

- ScallionMiku 1.0.5 与本模组在 **9/9 目标上重叠**（2.2 表），且两者都会在 `Item` 下挂载替换模型、都会接管 `mainRenderer`/材质/可见性。
- 特别地，ScallionMiku 的 `MikuRendererGuard` 会 `renderer.SetPropertyBlock(null)`（`ItemPatch.cs:438`），与本模组的烹饪 tint 直接互删；其 `GetItemName` 补丁会与本模组的 `GetName` 补丁叠加出不可预期的名字。
- **结论：二者不可共存，必须二选一。** 当前 `plugins` 目录**没有** ScallionMiku，所以现在不存在该冲突。

---

## 附：本次审计的验证命令与产物

```powershell
# 反编译全部 21 个插件
$ilspy = "C:\Users\Administrator\.dotnet\tools\ilspycmd.exe"
$out   = "C:\Users\Administrator\AppData\Local\Temp\opencode\compat-decomp"
Get-ChildItem "D:\SteamLibrary\steamapps\common\PEAK\BepInEx\plugins" -Filter *.dll | ForEach-Object {
    & $ilspy -o (Join-Path $out $_.BaseName) -p $_.FullName
}

# 全量 Harmony 补丁目标提取（含程序化补丁）
#   [HarmonyPatch] 属性扫描 + new HarmonyMethod / harmony.Patch( / TargetMethod() / MonoDetourTargets( 扫描

# 部署 DLL 与 dist DLL 各自反编译对比
& $ilspy -o "$out\__PlushieSwap_installed" -p "D:\SteamLibrary\steamapps\common\PEAK\BepInEx\plugins\PlushieSwap\PlushieSwap.dll"
& $ilspy -o "$out\__PlushieSwap_dist"      -p "D:\zhuanban\Plushie Swap\dist\PlushieSwap\PlushieSwap.dll"

# 溯源：部署 DLL 的 GripInset 从未进入版本库
git ls-tree -r --name-only 59cb988 -- src     # 无 GripInset.cs
git log --all -S "GripInset"                  # 空
git log --all -S "Hand Inset"                 # 空
(Get-FileHash "…\plugins\PlushieSwap\PlushieSwap.dll" -Algorithm SHA256).Hash   # 724B35B5…B669B6A
```

- 反编译产物：`C:\Users\Administrator\AppData\Local\Temp\opencode\compat-decomp\`（21 个模组目录 + `__PlushieSwap_installed` + `__PlushieSwap_dist`）
- 游戏侧交叉验证源：`D:\zhuanban\youhua\decompiled-latest\Assembly-CSharp\`（`Item.cs`、`ItemCooking.cs`、`CharacterItems.cs`、`CharacterAnimations.cs`、`InventoryItemUI.cs`、`BackpackOnBackVisuals.cs`、`ItemScaleSyncer.cs`、`Action_AskBingBong.cs`、`Peak\ItemOptimizer.cs`、`Peak\ItemOptimizationManager.cs`）
- 本报告**未**修改 `src/`、**未**修改游戏目录内任何文件（含 DLL）。
