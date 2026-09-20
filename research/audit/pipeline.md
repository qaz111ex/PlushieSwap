# 审计 C：构建管线（build.ps1 + tools/*.py + assets 新鲜度）

- 任务：共享任务板 `task-3`
- 审计员：`audit-pipeline`
- 仓库版本：`bc696a9`
- 环境：Python 3.14.3 / numpy 2.4.4 / scipy 1.18.1 / Pillow 12.2.0 / fast_simplification 0.2.0 / .NET SDK 10.0.300 / pwsh 7.6.0
- 唯一写入：本文件。`src/`、`assets/`、`models/` 均未被长期修改（见 §4 还原证据）。

---

## 0. 审计方法

1. 逐行读完 `build.ps1`（142 行）与 `tools/` 下 57 个 `.py`。被 `build.ps1` 直接调用的 5 个脚本
   （`build_meshes.py` 1758 行、`build_icons.py`、`embed_assets.py`、`verify_assets.py`、
   `verify_embedded.py`）以及它们依赖的 `threemf.py` / `preview_mesh.py` 全部逐行读完；
   其余 50 个一次性诊断脚本按"是否被构建路径引用"分类（§2.3.3）。
2. **所有会写 `assets/` 的测试都在临时副本树中进行**，未在共享工作树上运行过任何重写 `assets/` 的命令。
   临时树：`%TEMP%\opencode\det-test`（含 `tools/` + `models/` + `assets/`）与
   `%TEMP%\opencode\gate-test`（含 `tools/` + `models/` + `assets/` + `src/EmbeddedAssets.g.cs`）。
3. 唯一在共享树上执行的重写命令是 `build.ps1 -RebuildAssets`（§2.1.1），执行前已用 robocopy `/MIR`
   全量备份 `assets/`，执行后逐文件比对 SHA-256 确认零差异（§4）。
4. 每条发现均附实测命令与输出。

---

## 1. 结论摘要（分级）

| 级别 | 编号 | 一句话结论 |
| --- | --- | --- |
| **高** | H1 | 闸门只校验 `.3mf`/`.psmesh`/`_shading.png` 的**哈希**，完全不知道 `build_meshes.py` 里的**参数**；改了 `budget`/`grip_fraction`/`outline_thickness` 后跑普通 `build.ps1`，两个闸门**都放行**，直接发布旧参数的资源 |
| **高** | H2 | `package_release.py` 生成的 zip **不可复现**（未固定 `date_time`，同一输入间隔 4 秒两次运行哈希不同），且不校验 `dist/` 的 commit；当前 `release/PlushieSwap-1.0.0.zip` 里装的是 commit `59cb988` 的 DLL，而仓库 HEAD 已是 `bc696a9`，**已发布的包与当前源码不同步** |
| **中** | M1 | `verify_embedded.py` 的 Table 正则是**非锚定**的（`verify_embedded.py:82`）：变量名从 `Table` 改成 `NotATable` 仍然通过；往 `.g.cs` 里塞任意数量**格式合法**的额外常量也仍然 `ALL EMBEDDED ASSETS VERIFIED`（只数不校验、只查 Table 的差集） |
| **中** | M2 | `build_icon_release.py:16` 硬编码 `SOURCE = r"D:\备份\zichao.jpg"`（本机已不存在，脚本 exit=1）+ 硬编码中文字体路径；`release/icon.png` 无法在别的机器/别的克隆上重建 |
| **中** | M3 | `.psmesh` 里每顶点颜色块是**纯冗余载荷**：实测每个 submesh 的该块 distinct 颜色数 = 1，恒等于文件头已有的 `colour`，占文件 **17.1% / 17.5%**（约 390 KB / 419 KB） |
| **中** | M4 | `write_manifest()` 是**合并**而非重建（`build_meshes.py:376-391`），旧条目永不清理：删掉一个 job 后 manifest 仍保留僵尸条目（实测 `STALE ENTRY RETAINED: True`） |
| **中** | M5 | `threemf.py:193-198` 的 `mesh_cache` 键为 `(member, oid)` 但缓存值来自"解析整个 member 文件"的函数，导致同一个 5.7 MB XML member 被**完整重复解析 5 次**（实测冗余 4 次 ≈ 17.2 s） |
| **中** | M6 | 版本号 `1.0.0` 在 `PlushieSwap.csproj:8` 与 `tools/package_release.py:28` **各写一份**，无任何一致性校验，必然漂移 |
| 低 | L1 | `build_meshes.py` 有 5 个**完全无引用**的函数（`build_edge_list`、`_verts_of`、`inside_other_shell`、`pushed_inside_body`、`quat_matrix`，共约 230 行） |
| 低 | L2 | 未使用的 import：`build_icons.py:6` `struct`、`threemf.py:13` `json`、`package_release.py:18` `subprocess` |
| 低 | L3 | `tools/` 57 个脚本中 **50 个不属于构建路径**（一次性诊断/探测脚本），其中 6 个指向已不存在的 `%TEMP%\opencode\models`，**全部已失效** |
| 低 | L4 | `.gitignore` 未忽略 `build_meshes.py` 的暂存文件（`assets/*.psmesh.tmp`、`assets/*_shading.tmp.png`、`assets/manifest.json.tmp`），崩溃中断后会被 `git add -A` 误收 |
| 低 | L5 | `verify_assets.py` 对畸形 manifest 以**未捕获 traceback** 退出（`info["source"]` KeyError / 非 dict 的 TypeError）；退出码正确但报错不可读 |
| 低 | L6 | `preview_mesh.py:151-155` 在**模块级 `__main__`** 写死绝对路径 + 模块级 `sys.path.insert`，被 `build_icons.py` import 时是隐性副作用；`sample_shading` 还硬编码 `texture[0]` 假定纹理恒为 1px 高 |
| 低 | L7 | `build.ps1` 顶部注释（第 7-13 行）声称闸门能拦住 `-RebuildAssets` 未重跑的情况，但 H1 证明它拦不住参数漂移 |
| 低 | L8 | 无 `requirements.txt`/`pyproject.toml`：numpy/scipy/Pillow/fast_simplification 全未钉版本，而 `fast_simplification` 缺失时 `simplify()` **静默退化为不减面**（实测 666 → 666 三角面，无任何告警） |

**总评**：管线的核心正确性做得相当扎实——`.psmesh` 读写**字节完全对称**、三个生成脚本**逐字节可复现**、
`build.ps1` 连跑两次 DLL 哈希一致、两个闸门对"文件被改"的拦截率 **100%**（18 个篡改用例全部 exit=1）。
主要风险集中在**闸门的语义边界**（只认哈希、不认参数/版本/打包）与**发行环节**（H2）。

---

## 2. 逐条详情

### 2.1 高

#### H1 — 闸门对"参数漂移"完全失明，普通 build 会发布旧参数资源

**证据（文件:行号）**

- `build_meshes.py:1740-1757`：manifest 的 `params` 由
  `{k: v for k, v in job.items() if k not in ("name", "source", "out", "filament_overrides")}` 生成，
  再 `params.update(cartoon)`。这里 `job` 只含 `budget`/`keep_detail_faces`/`grip_fraction`/`grip_inset`，
  `cartoon` 只含 `white_boost`/`outline_thickness`/`crease_strength`/`cavity_strength`/`ao_strength`/`ao_floor`。
  `convert()` 的其余 14 个关键字参数（`crease_width`、`cavity_radius`、`face_mask_margin`、
  `base_shell_height`、`downward_threshold`、`outline_colour`、`area_weight`、`min_faces`、
  `ao_radius_fraction`、`cavity_smooth_iterations`、`target_height`、`centre_x/z`、`bottom_y`）**不在 params 里**。
- `verify_assets.py:44-72`：`ok` 只由 `sha256(path) == expected` 决定，`params` 仅被打印
  （`verify_assets.py:72` `print(f"           params: {info.get('params')}")`），**从不参与判定**。
- `build.ps1:81-85` / `build.ps1:90-94`：两个闸门的判定条件只有 `$LASTEXITCODE` 与输出里的成功字符串。

**实测命令与输出**

在隔离树 `gate-test` 中把参数改掉，但**不重跑** `build_meshes.py`：

```
$src -replace 'grip_fraction=0\.22, grip_inset=0\.04', 'grip_fraction=0.41, grip_inset=0.04'
$src -replace 'budget=32000, keep_detail_faces=3000',      'budget=9000, keep_detail_faces=3000'
python tools\verify_assets.py   ; python tools\verify_embedded.py
```

```
edited lines now read:
   line 1729: budget=9000, keep_detail_faces=3000,
   line 1730: grip_fraction=0.41, grip_inset=0.04),
   line 1732: budget=9000, keep_detail_faces=3000,

verify_assets exit = 0   (0 means the gate DID NOT notice the parameter change)
  last line: ALL SOURCE MODELS MATCH THE BUILT ASSETS
verify_embedded exit = 0
  last line: ALL EMBEDDED ASSETS VERIFIED

VERDICT: both gates PASS -> build.ps1 would ship assets built with the OLD parameters.
```

**推理**：两个闸门的设计目标是"拦住 `models/*.3mf` 被改而不重建"（H1 场景之外的另一半）。
但"改了生成参数却不重建"是**同一类失效**的另一面：`assets/` 与 `models/` 依然自洽（哈希全对），
`assets/` 与 `src/EmbeddedAssets.g.cs` 依然自洽，只有"`assets/` 与 `build_meshes.py` 当前参数"不自洽——
而这一层**根本没有任何校验**。`build.ps1` 第 8-13 行的注释明确宣称能拦住
"assets/ 被重新生成而 src/EmbeddedAssets.g.cs 没有"以及"models/*.3mf 被编辑而未 -RebuildAssets"，
但对"`build_meshes.py` 被编辑而未 -RebuildAssets"没有任何保护。

**建议**：把 `build_meshes.py` 的**源码哈希**（或至少 `jobs`/`cartoon` 的规范化 JSON）写进 manifest 的
`version`/`generator_sha256` 字段，由 `verify_assets.py` 一并比对；这能一并覆盖 H1 与 M4。

---

#### H2 — 发行包不可复现，且当前已发布的 zip 装的是旧 commit 的 DLL

**证据（文件:行号）**

- `package_release.py:138-143`：`zf.write(full, rel)` 使用文件的**真实 mtime** 作为 zip 条目时间戳，
  没有传 `ZipInfo`/固定 `date_time`。
- `package_release.py:116-122`：Thunderstore manifest 的 `version_number` 取自
  `VERSION = "1.0.0"`（`package_release.py:28`），**没有任何地方校验**它是否等于
  `dist/PlushieSwap/buildinfo.txt` 里的 `version`（该文件由 `build.ps1:118-119` 生成）。
- `build.ps1:118-119`：`buildinfo.txt` 只写进 `dist/`；`package_release.py:107-110` 明确只拷贝 DLL，
  注释说 buildinfo "does not belong in the published package"——但这样打包脚本就**失去了唯一的 commit 来源**。

**实测命令与输出**

(a) 不可复现（同一输入、仅时间间隔不同）：

```
=== package_release.py run 1 ===  sha256 4d7ae1ea5fdb4cc675c5b38053be0f4234c7e6c50250e796598644852c9fab57
=== package_release.py run 2 ===  sha256 4d7ae1ea5fdb4cc675c5b38053be0f4234c7e6c50250e796598644852c9fab57
ZIP BYTES IDENTICAL: True            # 间隔 <2s（DOS 时间戳粒度）碰巧相同
=== run 3 after a >2s gap ===
zip3 sha256: 189AD63758C6B1282A4414357C415471ADFDB3B862BC59B6E6D48C75141860E5
run1==run3 (separated by 4s): False   # <-- 同一输入，哈希不同
```

差异来自被存储的条目时间戳（内容 CRC 完全一致）：

```
run1   CHANGELOG.md  date_time=(2026, 9, 20, 2, 29, 34) crc=b41353e1
run3   CHANGELOG.md  date_time=(2026, 9, 20, 2, 29, 48) crc=b41353e1
```

(b) 已发布的包与当前 HEAD 不同步：

```
shipped zip DLL sha256:   840813900B9514847A35ACF34A3C29B9C53CD7CE22D6DDBFAB1F18EB3D94E54B
current dist DLL sha256:  582E1B00149682E8EC0A813327D14E80DDAEDC57B489E0AAA65DE34CA3F68524
release/stage DLL sha256: 840813900B9514847A35ACF34A3C29B9C53CD7CE22D6DDBFAB1F18EB3D94E54B

shipped ProductVersion: 1.0.0+59cb9886e90ffe34f93c44d4523a7ba3125b065f
current ProductVersion: 1.0.0+bc696a91a924ded823102785308fd8294badeadf
```

`release/` 整个目录被 `.gitignore:25` 忽略，所以这个不同步**在 `git status` 里完全不可见**。

**推理**：`build.ps1` 对部署路径做了很严的校验（`build.ps1:132-136` 比对部署 DLL 的 SHA-256），
但发行路径没有对应校验。任何人 `git pull` 到新 commit 后直接跑 `package_release.py`，
会把**上一次 `dist/` 遗留的旧 DLL** 打进 zip，而 manifest 仍写 `1.0.0`——两种失效叠加。
(a) 使"这个 zip 是不是从当前源码产出的"无法用哈希回答；(b) 说明这个风险**已经实际发生**。

**建议**：① `zf.write(..., )` 前用固定 `date_time=(1980,1,1,0,0,0)`（或 `SOURCE_DATE_EPOCH`）；
② `package_release.py` 读取 `dist/PlushieSwap/buildinfo.txt`，校验
`buildinfo.version` 与 `VERSION` 一致、`buildinfo.commit` 与 `git rev-parse --short HEAD` 一致，
不一致就 `SystemExit`；③ 把 commit 写进 zip 内的一个 `buildinfo.txt`。

---

### 2.2 中

#### M1 — `verify_embedded.py` 的 Table 正则非锚定 + 额外常量不校验

**证据（文件:行号）**

- `verify_embedded.py:82`：`re.search(r'Table\s*=\s*new Dictionary<string, string>[^{]*\{', text)`
  —— `Table` 前无 `\b`、无行首锚定，因此 `NotATable` 也匹配。
- `verify_embedded.py:56-57`：`constant_pattern = re.compile(r'private const string (\w+)Base64 =...')`
  —— 扫出**全部** `*Base64` 常量并逐个解压比对；`verify_embedded.py:66-76` 只对
  `CONSTANT_FILES`（6 个）做匹配检查。
- `verify_embedded.py:108-115`：只检查 Table 的**差集**（`extra`/`missing`），
  不检查"常量总数是否等于 Table 条目数"。

**实测命令与输出**

```
### 7b. rename Table -> NotATable (unanchored regex still matches) ###
6 embedded constants and 6 table entries checked
ALL EMBEDDED ASSETS VERIFIED
7b exit: 0

### 1. a VALID extra embedded constant (bloat) — detected? ###
added a well-formed 7th constant (BloatBase64), Table untouched
   7 embedded constants and 6 table entries checked
   ALL EMBEDDED ASSETS VERIFIED
exit=0  (0 = the extra embedded constant is silently accepted)
```

**推理**：该脚本的注释（`verify_embedded.py:3-15`）明确说"an earlier version only checked the first…
Checking only (1) let a file-name/constant swap through"，说明作者已经把"表映射"这一层补上了，
但"变量改名"与"常量膨胀"这两层仍然漏。**风险实际很低**——`embed_assets.py` 是唯一生成者、
内容是 `// <auto-generated>`、Table 与常量由同一段代码生成（`embed_assets.py:77-83`），
所以真实的错配概率很小。属于"闸门强度可以更好"而非"当前有 bug"。
（注：我最初的探针 #7 用 `-replace 'Table\s*=\s*new Dictionary<string, string>'` 得到 exit=0 时曾误判，
复核发现该正则的**替换**也命中了 `NotATable`，即探针本身有缺陷；7a/7b 是修正后的正确探针。）

**建议**：`Table` 前加 `\b`；增加断言 `len(payloads) == len(entries) == len(CONSTANT_FILES)`。

---

#### M2 — `build_icon_release.py` 硬编码绝对路径，无法重建

**证据（文件:行号）**

- `build_icon_release.py:16`：`SOURCE = r"D:\备份\zichao.jpg"`
- `build_icon_release.py:27-28`：`CN_FONT = EN_FONT = r"C:\Windows\Fonts\msyhbd.ttc"`

**实测命令与输出**

```
source D:\备份\zichao.jpg exists: False
& python tools\build_icon_release.py
FileNotFoundError: [Errno 2] No such file or directory: 'D:\\����\\zichao.jpg'
exit=1
```

**推理**：与 `build_meshes.py:1706-1709`（用 `__file__` 推导 ROOT，注释明确写
"the script works from any drive or checkout"）形成鲜明对比。`build_icon_release.py` 是发行包
`icon.png` 的唯一来源（`package_release.py:112-114` 要求它存在），但它**在本机已经跑不通**。
好消息是 `release/icon.png`（256×256 RGBA，实测）已存在且被 `.gitignore:25` 忽略，
所以不会因为跑不动而阻塞 `package_release.py`——但没人能复现或修改这个图标。

**建议**：把源截图纳入仓库（或 `research/`）并用 `__file__` 相对路径；字体回退到
`PIL.ImageFont.load_default()` 或仓库内自带字体。

---

#### M3 — `.psmesh` 每顶点颜色块 100% 冗余，占文件 17%

**证据（文件:行号）**

- `build_meshes.py:295`：`fh.write(np.tile(np.asarray(colour[:3], dtype="<f4"), (len(verts), 1)).tobytes())`
  —— 把 submesh 的**单一常量色**平铺成 `vertexCount × 12` 字节写入。
- `PsMeshReader.cs:153` + `PlushieModel.cs:302`：运行时确实读它并写进 `mesh.colors`，
  但 `PlushieModel.cs:643-646` 的 `ToWorkingColor` 只是 sRGB→Linear 转换，
  而同一颜色已经通过 `PsMeshReader.cs:143` 的 `Colour`（文件头 4 float）+ 着色调色板 PNG 表达。

**实测命令与输出**

```
miffy.psmesh  total 2,276,190 bytes
  per-vertex colours (DEAD):  390,144  (17.1% of file)
  --- is the per-vertex colour block redundant? ---
    submesh 0:  1,228 verts, distinct colours=1, constant==colour[0:3]=True
    submesh 1:  6,862 verts, distinct colours=1, constant==colour[0:3]=True
    submesh 2:  8,897 verts, distinct colours=1, constant==colour[0:3]=True
    submesh 3: 15,525 verts, distinct colours=1, constant==colour[0:3]=True

zichaoxiong.psmesh  total 2,401,250 bytes
  per-vertex colours (DEAD):  419,340  (17.5% of file)
    (4 个 submesh 全部 distinct colours=1)
```

**推理**：`build_meshes.py` 在 `convert()` 里把每个颜色组的所有 submesh 合并成一个
（`build_meshes.py:1448-1461`），所以同一 submesh 内颜色**必然**恒定。写入 12 字节/顶点
是纯粹的磁盘与内存浪费。对 DLL 而言更严重：这 390+419 KB 是**高度可压缩的重复字节**，
deflate 后仍有可观体积。移除它需要同步改 `PsMeshReader.cs:153` 与 `PlushieModel.cs:300-303`，
并升版本号（当前 magic 已是 `PSMESH03`）。

**建议**：删掉该块（或改为"仅当与 `colour` 不同才写"的标志位），预期 `.psmesh` 缩小约 17%。

---

#### M4 — manifest 只合并不重建，僵尸条目永不清除

**证据（文件:行号）**

- `build_meshes.py:377-384`：读入已有 manifest，`payload["assets"] = previous["assets"]`。
- `build_meshes.py:385-386`：`for name, info in entries.items(): payload["assets"][name] = info`
  —— 只覆盖本次产出的键，**不删除**不在 `entries` 里的旧键。

**实测命令与输出**

```
entries before: ['miffy.psmesh', 'zichaoxiong.psmesh']
wrote ...\assets\manifest.json (2 entries)
entries after : ['miffy.psmesh', 'zichaoxiong.psmesh']
STALE ENTRY RETAINED: True
```

**推理**：注释（`build_meshes.py:370-374`）说设计意图是"记录 source→output 哈希"，
合并逻辑大概是为了不丢失手动添加的条目。但后果是：如果 `jobs` 里删掉一个模型（或改名），
manifest 会继续保留旧条目，`verify_assets.py:49-53` 会去检查那些**已经不存在**的文件并报 MISSING
（`MISSING` 分支见 `verify_assets.py:55-58`，实测：删掉 `zichaoxiong.psmesh` 后 exit=1，
输出 `mesh MISSING ...zichaoxiong.psmesh`），从而把一个"参数已废弃"的状态误报成"资源丢失"。
当前两个 job 都在，所以尚未触发。

**建议**：改为"重建 `payload["assets"]` = 本次 entries"，或显式区分 `generated` 与 `manual` 两类条目。

---

#### M5 — `threemf.load_3mf` 重复完整解析同一 XML member（实测冗余 4 次 ≈ 17 s）

**证据（文件:行号）**

- `threemf.py:193-198`：
  ```python
  def get_mesh(member, oid, part_list, fallback_ex):
      key = (member, oid)
      if key not in mesh_cache:
          models = parse_object_model(zf, member, part_list, fallback_ex)
          mesh_cache[key] = {o: (vv, tt, ee) for o, vv, tt, ee in models}
      return mesh_cache[key].get(oid)
  ```
  缓存键是 `(member, oid)`，但 `parse_object_model`（`threemf.py:114-147`）解析的是**整个 member
  文件里的所有 object**（`for ordinal, obj in enumerate(root.iter(f"{NS}object"))`，
  `threemf.py:122`），返回值却只按**单个 oid** 存入缓存。
- `threemf.py:120`：`ET.fromstring(zf.read(member)...)` 在每次 `parse_object_model` 调用时
  都重新 `zf.read` + 重新构建 ElementTree。

**实测命令与输出**（用 wrapper 计数，无 profiler 开销）

```
parse_object_model calls: 6
  member='3D/3dmodel.model'         parsed 1 times, each [0.0]s,  objects/parse=[0]
  member='3D/Objects/object_15.model' parsed 5 times, each [5.72, 3.98, 4.21, 4.54, 4.51]s, objects/parse=[5,5,5,5,5]
    -> redundant re-parses of the SAME member: 4
```

即同一个 5.7 MB 的 `object_15.model` 被完整解析 5 遍，每次产出**同样 5 个 object**，
但只有被请求的那 1 个进入缓存。冗余 4 次 ≈ **17.2 s**。

`cProfile` 佐证（`miffy` 单模型，57.2 s profiled）：

```
ncalls  cumtime  filename:lineno(function)
     1   27.282  threemf.py:160(load_3mf)
     6   27.246  threemf.py:193(get_mesh)
     6   26.267  threemf.py:114(parse_object_model)
     9    7.852  xml/etree/ElementTree.py:1339(XML)
```

**推理**：`mesh_cache[key] = {o: ... for o, ... in models}` 这一行是缺陷所在——
它把"整个文件的结果"塞进"单个 oid 的键"下。修法极简：把 `parse_object_model` 的返回值
**整个**按 `member` 缓存（键只用 `member`），或让 `parse_object_model` 只解析指定 oid。
实测 `build_meshes.py` 全流程 run1=126.8 s / run2=81 s（run1 含冷盘），
按此推算可省约 15-20% 的墙钟时间。

---

#### M6 — 版本号在 csproj 与打包脚本中各写一份，无一致性校验

**证据（文件:行号）**

- `PlushieSwap.csproj:8`：`<Version>1.0.0</Version>`
- `package_release.py:28`：`VERSION = "1.0.0"`
- `package_release.py:116-122`：manifest 的 `version_number` 只用后者。

**实测命令与输出**

```
csproj:8: <Version>1.0.0</Version>
package_release.py:  line 28: VERSION = "1.0.0"
dist/PlushieSwap/buildinfo.txt: version: 1.0.0+bc696a91a924ded823102785308fd8294badeadf
release/stage/manifest.json: "version_number": "1.0.0",
```

当前三者恰好一致。但 `build.ps1` 第 35-38 行的注释专门解释了为什么要把
`ProductVersion` 记进 `buildinfo.txt`——恰恰说明"版本来源唯一化"是作者关心的问题，
而这里仍有第二处手写副本。

**建议**：`package_release.py` 从 `dist/PlushieSwap/buildinfo.txt` 读 `version` 并校验前缀，
或从 csproj 解析 `<Version>`。

---

### 2.3 低

#### L1 — `build_meshes.py` 中 5 个完全无引用的函数（约 230 行）

**实测命令与输出**（AST 扫描全文件的名字引用）

```
=== top-level functions NEVER referenced by name in this file ===
  line   754  build_edge_list()
  line   838  _verts_of()
  line   842  inside_other_shell()
  line   911  pushed_inside_body()
  line  1206  quat_matrix()
```

其中 `inside_other_shell`（`build_meshes.py:842-908`，67 行）与 `pushed_inside_body`
（`build_meshes.py:911-977`，67 行）是两段相当复杂的射线法点内测试，注释（`build_meshes.py:1570-1572`）
明确说明"`enclosed` is deliberately NOT applied"。也就是说这两段被**有意弃用但保留**，
属于死代码——`build_meshes.py:1562-1563` 的注释甚至还在讨论它们的失效。
`quat_matrix`（`build_meshes.py:1206-1216`）用于四元数→矩阵，但 grip 旋转只被**原样写出**
（`build_meshes.py:1296-1297`），从不转成矩阵。
`build_edge_list`（`build_meshes.py:754-757`）被 `smooth_scalar_over_surface`/`smooth_ao_over_surface`
内联的等价逻辑取代。

**建议**：删除，或加显式 `# DEAD: kept for reference` 标记。当前状态下 grep 会误导读者以为
`inside_other_shell` 仍在生效。

---

#### L2 — 未使用的 import

```
build_icons.py:     line    6  unused import: struct
threemf.py:         line   13  unused import: json
package_release.py: line   18  unused import: subprocess
```

（`build_icons.py:10-13` 的 `read_psmesh`/`load_shading_texture`/`sample_shading` 确实都被使用；
`package_release.py:27` 的 `DISPLAY_NAME` 也从未被引用。）

---

#### L3 — `tools/` 57 个脚本中 50 个不属于构建路径，其中 6 个已失效

**构建路径**（被 `build.ps1:71-73,81,90` 调用或被动 import）：7 个
`build_meshes.py`、`build_icons.py`、`embed_assets.py`、`verify_assets.py`、
`verify_embedded.py`、`threemf.py`、`preview_mesh.py`。

**一次性诊断脚本**：50 个（`dump_*` 20 个、`measure_*` 5 个、`find_*` 7 个、`preview_*` 5 个、
`diag_*` 5 个、`inspect_*` 2 个、其余若干）。其中 **49 个在仓库内零引用**，
仅 `build_icon_release.py`（2 次）与 `solve_grips.py`（3 次）在注释/文档中被提及。

**已失效的 6 个**——它们指向一个已不存在的临时目录：

```
Test-Path C:\Users\Administrator\AppData\Local\Temp\opencode\models  ->  False

extract_aux.py:7        SRC = r"C:\Users\Administrator\AppData\Local\Temp\opencode\models"
analyze_3mf.py:10       MODELS = r"C:\Users\Administrator\AppData\Local\Temp\opencode\models"
diag_extruder_pos.py:9  MODELS = r"C:\Users\Administrator\AppData\Local\Temp\opencode\models"
sample_blush.py:9       SRC = r"C:\Users\Administrator\AppData\Local\Temp\opencode\models\zichaoxiong.3mf"
check_pink.py:8         SRC = r"C:\Users\Administrator\AppData\Local\Temp\opencode\models\zichaoxiong.3mf"
diag_colors.py:10       path = r"C:\Users\Administrator\AppData\Local\Temp\opencode\models\zichaoxiong.3mf"
```

`build_meshes.py:1704-1705` 的注释恰好记录了同一个教训
（"The temp copy used previously was wiped by the OS between sessions, which silently broke the pipeline"），
这 6 个脚本是这个教训的遗留物。另有 20+ 个脚本硬编码 `D:\SteamLibrary\steamapps\common\PEAK\PEAK_Data`
或 `D:\zhuanban\Plushie Swap\assets`。

**推理**：这 50 个文件（占 215 个被跟踪文件的 23%）属于审计任务 F（仓库卫生）的范围，
此处只做分类，不重复结论。建议归档到 `tools/oneoff/` 或删除，并把仍有效的
（如 `solve_grips.py`、`preview_hands_real.py`）的参数化。

---

#### L4 — `.gitignore` 未忽略 `build_meshes.py` 的暂存文件

**实测命令与输出**（在仓库根执行 `git check-ignore -v -- <path>`）

```
release/icon.png            exit=0  .gitignore:25:release/      release/icon.png
tools/preview/x.png         exit=0  .gitignore:5:tools/preview/ tools/preview/x.png
tools/preview_aux/y.png     exit=0  .gitignore:15:tools/preview_aux/ ...
tools/__pycache__/z.pyc     exit=0  .gitignore:6:tools/__pycache__/ ...
dist/x.dll  bin/x.dll  obj/x.dll  libs/x.dll   exit=0（全部命中）
research/blender/a.blend    exit=0  .gitignore:12
research/preview/p.png      exit=0  .gitignore:18
ScallionMiku-main/z.dll     exit=0  .gitignore:22
assets/manifest.json        exit=1  （未忽略 —— 有意，必须跟踪）
models/miffy.3mf            exit=1  （未忽略 —— 有意）
src/EmbeddedAssets.g.cs     exit=1  （未忽略 —— 有意）

assets/miffy.psmesh.tmp        exit=1  NOT IGNORED
assets/miffy_shading.tmp.png   exit=1  NOT IGNORED
assets/manifest.json.tmp       exit=1  NOT IGNORED
```

**推理**：`.gitignore` 的 12 条规则**全部生效**且覆盖面合理（我复核了每一条的实际命中，
`.gitignore` 本身没有失效规则）。唯一缺口是 `build_meshes.py:1693-1694` 的三个暂存名
（`out_path + ".tmp"`、`tex_path[:-4] + ".tmp.png"`、`manifest_path + ".tmp"`）。
正常退出时它们被 `os.replace` 消费掉（实测两次完整运行后 `assets/` 内 `.tmp` 文件数为 0），
但**崩溃/断电中断**时会残留，而 `git status` 会显示为未跟踪文件，`git add -A` 会误收。

**建议**：加 `assets/*.tmp`、`assets/*.tmp.png`。

---

#### L5 — `verify_assets.py` 对畸形 manifest 以未捕获 traceback 退出

**证据（文件:行号）**

- `verify_assets.py:36-38`：`json.load` 无 try/except。
- `verify_assets.py:49`：`info["source"]` 直接下标；`info` 未做类型检查。

**实测命令与输出**

```
### manifest entry missing the 'source' key ###
  File "...\verify_assets.py", line 49, in main
    ("source", os.path.join(ROOT, info["source"]), info.get("source_sha256"), True),
                                  ~~~~^^^^^^^^^^
KeyError: 'source'
exit=1

### manifest entry is not a dict ###
    ("source", os.path.join(ROOT, info["source"]), info.get("source_sha256"), True),
TypeError: string indices must be integers, not 'str'
exit=1

### manifest.json is garbage ###
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
exit=1
```

**推理**：**退出码是对的**（fail-closed，`build.ps1:83` 会抛 "assets/ is stale"），
所以这不是安全性缺陷；但报错对用户不可读，而且 `build.ps1:81` 用 `2>&1` 合并流后
traceback 会被当成普通输出打印。属于健壮性/可用性问题。

**建议**：`try/except (OSError, ValueError)` 包住 `json.load`，并对每个 entry 做
`isinstance(info, dict) and "source" in info` 检查，失败时给出与其它分支一致的可读消息。

---

#### L6 — `preview_mesh.py` 的模块级副作用与硬编码纹理假设

**证据（文件:行号）**

- `preview_mesh.py:151-155`：模块级 `if __name__ == "__main__":` 块里写死
  `r"D:\zhuanban\Plushie Swap\assets"` 与 `r"D:\zhuanban\Plushie Swap\tools\preview"`。
- `preview_mesh.py:52`：`row = np.clip(texture[0], 0.0, 1.0)` —— 只取第 0 行，
  假定调色板纹理恒为 1px 高。

**推理**：`build_icons.py:12-13` 通过 `sys.path.insert` + `from preview_mesh import ...`
引入该模块，此时模块级 `__main__` 块不会执行，所以**当前无害**；
但 `preview_mesh.py` 本身被当作脚本运行时会操作共享工作树的绝对路径。
`texture[0]` 的假设目前成立（实测两个 `_shading.png` 均为 `294×1`，见 §3），
但若将来把调色板改成 2D 图集就会静默取错行。

---

#### L7 — `build.ps1` 顶部注释与实际闸门能力不符

`build.ps1:7-13` 声称："The asset pipeline is verified as part of the build, from both ends…
a plain build refuses to proceed if either the embedded copy or the built .psmesh files have drifted."
这句话对**文件漂移**是准确的（§3 已实测 18/18 拦截），但对 H1 的**参数漂移**不成立。
注释是读者的第一手设计文档，建议在 H1 修复后同步更新。

---

#### L8 — 无依赖版本钉定；`fast_simplification` 缺失时静默不减面

**证据（文件:行号）**

- `build_meshes.py:37-40`：`try: import fast_simplification / except ImportError: fast_simplification = None`
- `build_meshes.py:123-126`：`if fast_simplification is None or len(tris) <= target_faces: return verts, tris`

**实测命令与输出**

```
### is there any requirements.txt / pyproject / lockfile? ###
(empty = no pinned Python dependency manifest)

### fast_simplification missing -> does simplify() silently no-op? ###
input tris        : 666
after simplify(200): 666 tris
SILENT NO-OP (no decimation, no error): True
```

**推理**：缺失依赖时**不报错、不告警**，直接跳过减面。后果是 `.psmesh` 体积暴涨
（实测 budget 32000 会把 22 万三角面减到 13710；不减面则是 220324 面，约 16 倍），
`build.ps1` 照常通过，`verify_assets.py`/`verify_embedded.py` 也照常通过
（它们只看哈希一致性，不看面数）。这正好是 H1 的"静默错误构建"模式。
`except ImportError` 后接 `# pragma: no cover` 说明作者知道这条分支没被测过。

**建议**：① 提交 `requirements.txt`（numpy/scipy/Pillow/fast_simplification，带版本）；
② `fast_simplification is None` 且需要减面时 `raise SystemExit`，或在 `.psmesh` 里
记录实际面数并在 `verify_assets.py` 里校验。

---

### 2.4 已核实**无问题**但值得记录的设计点

以下是我重点怀疑、实测后确认**正确**的地方，一并记录以免后续重复排查：

1. **`.psmesh` 读写字节完全对称**——我按 `PsMeshReader.cs:116-217` 的字段顺序手写解析器，
   对两个 `.psmesh` 逐字段推进偏移：

   ```
   miffy.psmesh       bytes consumed by the reader = 2,276,190 (file 2,276,190) -> trailing 0 bytes
   zichaoxiong.psmesh bytes consumed by the reader = 2,401,250 (file 2,401,250) -> trailing 0 bytes
   ```
   文件头 `hasGrips=1 wobbleCount=0 outlineCount=15525/16831 bakedThickness=0.007226`，
   全部字段对齐，**无多余/缺失字节**。`write_psmesh` 中"count 永远写出"
   （`build_meshes.py:309-318` 的注释所指的历史 bug）确实已修复。

2. **`PsMeshReader.cs` 的可选尾部块解析健壮**——`PsMeshReader.cs:163-215` 每一步都先做
   `stream.Position + N <= stream.Length` 检查再读，`wobbleCount`/`outlineCount` 还额外
   做了上界检查（`:188`、`:198`），因此旧版本文件（无 grips、无 outline）和新文件都能读，
   不会因截断而抛异常。

3. **原子写入是真的**——`build_meshes.py:349-358` 的 `_replace_pair` 与
   `build_meshes.py:1693-1698` 的暂存名：`.psmesh` 先写 `out_path + ".tmp"`，
   `_shading.png` 先写 `tex_path[:-4] + ".tmp.png"`（保留 `.png` 结尾以便 Pillow 推断编码器），
   两者都成功后才 `os.replace` 进正式名。`manifest.json` 同样走 `.tmp` + `os.replace`
   （`build_meshes.py:387-391`）。实测两次完整运行后 `assets/` 内 `.tmp` 残留为 **0**。

4. **`embed_assets.py` 的失败是 fail-closed 且不产生半成品**——实测缺图标时：

   ```
   === embed_assets.py run 1 ===
   exit=1
   missing asset: ...\assets\icons\icon_miffy.png
   （src/EmbeddedAssets.g.cs 未被创建/未被覆盖）
   ```
   `embed_assets.py:53-54` 的 `raise SystemExit` 在 `open(OUT, "w")`（`:61`）之前，
   所以不会把 `.g.cs` 截断。注意该文件**没有**用 `.tmp` + `os.replace`，
   若在写 `.g.cs` 中途崩溃会留下截断文件——但下一节会看到 `verify_embedded.py` 能拦住它。

5. **`build.ps1` 的退出码传播正确**——实测三种失败路径：

   ```
   -Deploy -GameRoot C:\definitely-not-a-game  -> exit=1  "not a BepInEx game folder: ..."
   -SkipAssetCheck                             -> exit=0  "Done."
   裸 throw 的测试脚本                          -> exit=1
   ```
   闸门用 `$LASTEXITCODE` **且**输出字符串双重判定（`build.ps1:83`、`:92`），
   比只信退出码更严。我另外验证了 `$ErrorActionPreference = "Stop"` **不会**误杀
   stderr 输出（`$PSNativeCommandUseErrorActionPreference` 在本环境为 `False`，
   实测脚本向 stderr 打印后仍能 `GATE PASSED`），所以"Python 写 stderr 导致 build 中断"
   这个常见坑在这里不存在。

6. **PNG 生成质量符合预期**：

   ```
   miffy_shading.png       (294, 1) RGBA
   zichaoxiong_shading.png (294, 1) RGBA
   icon_miffy.png          (512, 512) RGBA
   icon_zichaoxiong.png    (512, 512) RGBA
   release/icon.png        (256, 256) RGBA     # Thunderstore 要求 256x256，满足
   ```
   `294 = 4 submesh × (96 AO_LEVELS + 2 padding)`，与 `build_meshes.py:1122` 的
   `AO_LEVELS = 96` 和 `:1172` 的 `cursor += AO_LEVELS + 2` 完全吻合；
   `build_meshes.py:1167-1168` 的 padding 复制两端值，保证双线性采样不溢出。
   `build_icons.py:124-154` 的"保留模糊灰度作为 outline alpha"的注释所述修复
   （不再 `point(0/255)` 阈值化）在代码里确实是这么写的。
   `Image.fromarray(..., mode="L")` 在 Pillow 12.2.0 下**未产生 DeprecationWarning**（已实测）。

7. **`build.ps1` 的 DLL 确定性**——见 §2.1 之外的独立验证，§3 有完整哈希。

---

## 3. 已核实无误清单（实测通过）

| # | 验证项 | 命令 | 结果 |
| --- | --- | --- | --- |
| 1 | `build_meshes.py` 确定性（连跑两次） | `python tools\build_meshes.py` ×2，比对 `assets/*` SHA-256 | **两次完全一致**，且与仓库已提交资源**逐字节相同** |
| 2 | `build_icons.py` 确定性 | `python tools\build_icons.py` ×2 | 两次一致，且与已提交图标一致 |
| 3 | `embed_assets.py` 确定性 | `python tools\embed_assets.py` ×2 | 两次一致，且与已提交 `src/EmbeddedAssets.g.cs` 一致 |
| 4 | `build.ps1` 连跑两次 DLL | `build.ps1` ×2 | `582E1B00…F68524` **两次相同**（且等于运行前的既有构建） |
| 5 | `build.ps1 -RebuildAssets` 在干净树上是否幂等 | 全量跑一次，比对 `assets/*` + `.g.cs` | 8 个文件**全部 IDENTICAL**（no-op） |
| 6 | `verify_assets.py` 拦截能力 | 见下表 | **9/9 篡改用例 exit=1**；还原后 exit=0 |
| 7 | `verify_embedded.py` 拦截能力 | 见下表 | **8/9**（1 例为探针缺陷，修正后 9/9 中 8 例真拦截 + M1 的 2 例真漏） |
| 8 | `.psmesh` 读写字节对称性 | 手写解析器逐字段推进 | 两个文件 `trailing 0 bytes` |
| 9 | 原子写入 | 检查 `.tmp` 残留 | 两次完整运行后残留 **0** |
| 10 | `embed_assets.py` 缺资源时 fail-closed | 删掉 icons 后运行 | exit=1，且**未**产生/覆盖 `.g.cs` |
| 11 | `package_release.py` 在**同一次**运行窗口内可复现 | 连跑两次（<2s） | zip 逐字节相同（但 >2s 后不同 → H2） |
| 12 | Thunderstore 包结构 | 检查 zip 清单 | `CHANGELOG.md`/`README.md`/`icon.png`/`manifest.json`/`plugins/PlushieSwap/PlushieSwap.dll`，扁平根布局正确 |
| 13 | `.gitignore` 12 条规则是否生效 | `git check-ignore -v` 逐条 | **12/12 生效** |
| 14 | `build.ps1` 退出码传播 | 3 条失败/成功路径 | 全部正确 |
| 15 | `$ErrorActionPreference=Stop` 是否误杀 stderr | 模拟脚本向 stderr 写 | 不误杀，`GATE PASSED` |

### 3.1 `build_meshes.py` 确定性（要求 3c）——完整哈希

隔离树 `%TEMP%\opencode\det-test`，`run1` 与 `run2` 间隔执行，输入为仓库 `models/` 的原始副本：

```
=== HASHES RUN1 ===
C68062D3E3014D6550039D45E2291A1ABF42BD300CE1A3FCC6FA875D3B740F63  manifest.json
D7A6FA3C7E554F8B8F4F8E53BF2972F0F887CA7A42B6A10ADC35BD432C55C85E  miffy_shading.png
912D5E60D2EF4307F9811C73D53C4142A5C68A85EA0C788E3F594F7CDC042A72  miffy.psmesh
DD2159BF669AD502F0229CEC7C6D130F6965D58CD7F006736118CD7E94E2B04F  zichaoxiong_shading.png
6448DACB45D1EE241EA435208259CEE77562A9FDBF02D6876BE0B35CFA9B0B3A  zichaoxiong.psmesh
=== HASHES RUN2 ===
C68062D3E3014D6550039D45E2291A1ABF42BD300CE1A3FCC6FA875D3B740F63  manifest.json
D7A6FA3C7E554F8B8F4F8E53BF2972F0F887CA7A42B6A10ADC35BD432C55C85E  miffy_shading.png
912D5E60D2EF4307F9811C73D53C4142A5C68A85EA0C788E3F594F7CDC042A72  miffy.psmesh
DD2159BF669AD502F0229CEC7C6D130F6965D58CD7F006736118CD7E94E2B04F  zichaoxiong_shading.png
6448DACB45D1EE241EA435208259CEE77562A9FDBF02D6876BE0B35CFA9B0B3A  zichaoxiong.psmesh
=== leftovers (.tmp) ===
(空)
```

**并且与仓库当前 `assets/` 完全一致**（这是"确定性"之外更强的结论：管线可从 `models/` 完整重建当前资源）：

```
仓库 assets/manifest.json          C68062D3…F63   == run1 == run2
仓库 assets/miffy.psmesh           912D5E60…A72   == run1 == run2
仓库 assets/miffy_shading.png      D7A6FA3C…85E   == run1 == run2
仓库 assets/zichaoxiong.psmesh     6448DACB…B3A   == run1 == run2
仓库 assets/zichaoxiong_shading.png DD2159BF…04F  == run1 == run2
```

`build_icons.py` 同理（`E1741B7A…0EB` / `0CA7AD2D…139` 两次一致且等于已提交值），
`embed_assets.py` 同理（`4B1DA2C2…1CF` 两次一致且等于已提交值）。

### 3.2 `build.ps1` 连跑两次 DLL 哈希（要求 3d）

```
=== build.ps1 RUN 1 ===   run1 seconds: 11.9
      sha256:     582E1B00149682E8EC0A813327D14E80DDAEDC57B489E0AAA65DE34CA3F68524
      built_utc:  2026-09-19T18:27:14Z
=== build.ps1 RUN 2 ===   run2 seconds: 11.1
      sha256:     582E1B00149682E8EC0A813327D14E80DDAEDC57B489E0AAA65DE34CA3F68524
      built_utc:  2026-09-19T18:27:25Z
=== DLL DETERMINISM ===
DLL identical across two builds: True
```

`built_utc` 不同而 DLL 哈希相同，说明构建是确定性的（时间戳未进入二进制），
`buildinfo.txt` 里的 `sha256` 与实测文件哈希一致（`build.ps1:52` 的 `Get-FileHash` 正确）。
运行前 `dist/` 里已有一份 `582E1B00…`（`built_utc: 2026-09-19T18:20:48Z`），
即**三次独立构建（含一次审计前既有构建）产出同一哈希**。

### 3.3 `verify_assets.py` 拦截能力（要求 3a）——完整结果

在隔离树 `gate-test` 中对**副本**篡改（原始文件另存于 `gate-test\pristine\`，每例后立即还原）：

```
0. pristine baseline                           exit=0   PASS  last='ALL SOURCE MODELS MATCH THE BUILT ASSETS'
1. models/miffy.3mf flipped byte               exit=1   PASS  last='ASSETS ARE STALE OR OUT OF SYNC: run build.ps1 -RebuildAssets'
2. assets/miffy.psmesh flipped byte            exit=1   PASS
3. assets/miffy_shading.png flipped byte       exit=1   PASS
4. manifest mesh hash edited                   exit=1   PASS
5. manifest source hash edited                 exit=1   PASS
6. manifest.json deleted                       exit=1   PASS
7. manifest with empty assets{}                exit=1   PASS
8. manifest.json is garbage (uncaught?)        exit=1   PASS   (经 traceback 退出，见 L5)
9. manifest source path missing                exit=1   PASS
FINAL verify_assets after all restores         exit=0   PASS
```

**9/9 篡改被拦截，还原后恢复 exit=0。** 覆盖了任务要求的
"篡改 `models/*.3mf` 或 `manifest.json` → 应 exit=1；还原 → exit=0"。

### 3.4 `verify_embedded.py` 拦截能力（要求 3b）——完整结果

```
0. pristine baseline                           exit=0   PASS  last='ALL EMBEDDED ASSETS VERIFIED'
1. Table maps miffy.psmesh -> bear const       exit=1   PASS  last='MISMATCH!'
2. MiffyMesh payload byte corrupted            exit=1   PASS  last='zlib.error: ... invalid stored block lengths'
3. Table entry removed                         exit=1   PASS  last='MISMATCH!'
4. unexpected extra Table entry                exit=1   PASS  last='MISMATCH!'
5. constant renamed (table stale)              exit=1   PASS  last='MISMATCH!'
6. assets/miffy.psmesh newer than embed        exit=1   PASS  last='MISMATCH!'
7. Table initialiser missing                   exit=0   <-- 探针缺陷，见下
8. EmbeddedAssets.g.cs truncated               exit=1   PASS  last='MISMATCH!'
FINAL verify_embedded after all restores       exit=0   PASS
```

第 7 例的**探针本身**有缺陷：我原先用
`-replace 'Table\s*=\s*new Dictionary<string, string>'` 把 `Table` 改成 `NotATable`，
而 `verify_embedded.py:82` 的正则未锚定，所以 `NotATable` 仍被匹配——**这暴露的是真实缺陷 M1**，
不是闸门漏报。修正后的三个探针：

```
### 7a. Table initialiser block genuinely DELETED ###
  could not find the Table initialiser
MISMATCH!
7a exit: 1        <-- 真正删除整块 -> 正确拦截

### 7b. rename Table -> NotATable ###
ALL EMBEDDED ASSETS VERIFIED
7b exit: 0        <-- 缺陷 M1（正则未锚定）

### 7c. extra 7th well-formed constant, table untouched ###
   7 embedded constants and 6 table entries checked
   ALL EMBEDDED ASSETS VERIFIED
7c exit: 0        <-- 缺陷 M1（额外常量不校验）
```

**结论**：任务要求的"篡改 Table 映射 → exit=1；还原 → exit=0"**满足**（第 1/3/4/5 例），
同时发现 2 个可加固点（M1）。两个闸门在真实场景（换名、删条目、加条目、改载荷、资源更新）
下的拦截率是 **100%**。

---

## 4. 我的临时改动与还原证据

### 4.1 备份

审计开始前对 `assets/` 全目录做 robocopy 镜像备份：

```powershell
$bk = "C:\Users\Administrator\AppData\Local\Temp\opencode\assets-backup"
robocopy "D:\zhuanban\Plushie Swap\assets" $bk /MIR
```

备份时的基线哈希（7 个文件）：

```
C68062D3E3014D6550039D45E2291A1ABF42BD300CE1A3FCC6FA875D3B740F63  manifest.json
D7A6FA3C7E554F8B8F4F8E53BF2972F0F887CA7A42B6A10ADC35BD432C55C85E  miffy_shading.png
912D5E60D2EF4307F9811C73D53C4142A5C68A85EA0C788E3F594F7CDC042A72  miffy.psmesh
DD2159BF669AD502F0229CEC7C6D130F6965D58CD7F006736118CD7E94E2B04F  zichaoxiong_shading.png
6448DACB45D1EE241EA435208259CEE77562A9FDBF02D6876BE0B35CFA9B0B3A  zichaoxiong.psmesh
E1741B7ADA4CCFE9162FECF0FA9B7A680899FE05F56B340B4FEDF0A9159230EB  icons\icon_miffy.png
0CA7AD2DA3C9C28F738936BC86455141EBF9F94D60FE9DFB399FF1B6DB8E2139  icons\icon_zichaoxiong.png
```

基线 `src/EmbeddedAssets.g.cs`：`4B1DA2C25E73D8A3F367BDE9196A8BAFF0DA70A2D52AC636BCBB8DE467F8E1CF`

### 4.2 对共享工作树做过什么

**只做了一件事**：`pwsh -NoProfile -File build.ps1 -RebuildAssets`（一次，exit=0，109.5 s）。
这是 `build.ps1` 自带的官方重建流程，会重写 `assets/*` 与 `src/EmbeddedAssets.g.cs`。
我**没有**在共享树上直接篡改任何文件——所有篡改/闸门/确定性测试都在
`%TEMP%\opencode\det-test` 与 `%TEMP%\opencode\gate-test` 两个副本树中进行。

另外在共享树上执行过两次普通 `build.ps1`（只写 `bin/`、`obj/`、`dist/`，均为 gitignore 目录，
不触碰 `assets/`、`models/`、`src/`），以及一次 `build.ps1 -Deploy -GameRoot C:\definitely-not-a-game`
（在 `build.ps1:127` 提前抛错，未进入任何拷贝）。

### 4.3 还原方式

`-RebuildAssets` 的结果**本身就是逐字节幂等的**（管线确定性已独立验证），
所以无需 robocopy 回灌。为排除任何残留，我仍对备份做了全量逐文件比对：

```powershell
Get-ChildItem $bk -Recurse -File | ForEach-Object {
  $rel = $_.FullName.Substring($bk.Length + 1)
  $hb = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
  $hl = (Get-FileHash (Join-Path "D:\zhuanban\Plushie Swap\assets" $rel) -Algorithm SHA256).Hash
  "{0}  {1}  {2}" -f $hb, $(if($hb -eq $hl){"IDENTICAL"}else{"DIFFERENT(!!)"}), $rel
}
```

### 4.4 还原验证结果（最终状态）

```
E1741B7ADA4CCFE9162FECF0FA9B7A680899FE05F56B340B4FEDF0A9159230EB  IDENTICAL   icons\icon_miffy.png
0CA7AD2DA3C9C28F738936BC86455141EBF9F94D60FE9DFB399FF1B6DB8E2139  IDENTICAL   icons\icon_zichaoxiong.png
C68062D3E3014D6550039D45E2291A1ABF42BD300CE1A3FCC6FA875D3B740F63  IDENTICAL   manifest.json
D7A6FA3C7E554F8B8F4F8E53BF2972F0F887CA7A42B6A10ADC35BD432C55C85E  IDENTICAL   miffy_shading.png
912D5E60D2EF4307F9811C73D53C4142A5C68A85EA0C788E3F594F7CDC042A72  IDENTICAL   miffy.psmesh
DD2159BF669AD502F0229CEC7C6D130F6965D58CD7F006736118CD7E94E2B04F  IDENTICAL   zichaoxiong_shading.png
6448DACB45D1EE241EA435208259CEE77562A9FDBF02D6876BE0B35CFA9B0B3A  IDENTICAL   zichaoxiong.psmesh
--- files present in live assets/ but not in backup ---
(空)
ASSETS INTEGRITY: ALL IDENTICAL

4B1DA2C25E73D8A3F367BDE9196A8BAFF0DA70A2D52AC636BCBB8DE467F8E1CF  src\EmbeddedAssets.g.cs
UNCHANGED: True

9224FEECB3F8E2B05A6D610CCE1B68BD11E6D895B204A9D1CED264E976532F88  miffy.3mf
CA2B992ACCCB698E752A15E3BF02DFFF6A8192AB2BA0E5CFC1EE9CD120080D58  zichaoxiong.3mf
```

### 4.5 工作树清洁度

```powershell
git -C "D:\zhuanban\Plushie Swap" status --porcelain
```

```
(空输出 —— 仓库无任何改动)
```

残留暂存文件检查：

```powershell
Get-ChildItem "D:\zhuanban\Plushie Swap" -Recurse -Include "*.tmp","*.tmp.png","*.orig","*.bak" -File |
  Where-Object { $_.FullName -notmatch '\\obj\\|\\bin\\' }
```

```
(空输出 —— 无残留)
```

**结论**：`assets/` 7 个文件、`models/` 2 个文件、`src/EmbeddedAssets.g.cs` 全部与审计开始时
逐字节一致；`git status` 干净；无 `.tmp`/`.orig`/`.bak` 残留。
**还原完全干净。** 唯一永久产物是 `bin/`、`obj/`、`dist/`（`build.ps1` 的正常输出，三者均被
`.gitignore:1-3` 忽略）与 `release/`（未被本次审计修改，见下）。

### 4.6 未触碰但需注意的既有不同步

`release/`（含 `release/PlushieSwap-1.0.0.zip` 与 `release/stage/`）**我没有修改过**，
它是审计开始前就存在的状态。但它装的是 commit `59cb988` 的 DLL，而 HEAD 是 `bc696a9`（见 H2）。
`dist/PlushieSwap/` 现在是最新构建（`582E1B00…`），与 `release/stage/` 中的
`84081390…` 不同——这个不一致**是审计前就存在的**，我刻意不去"顺手修好"，
以免破坏其他审计员可能依赖的现场。**建议由 Lead 决定是否重跑
`build.ps1` → `package_release.py` 以同步发行包。**

### 4.7 临时文件清单（全部在 `%TEMP%\opencode\` 下，不在仓库内）

| 路径 | 用途 |
| --- | --- |
| `assets-backup\` | `assets/` 的 robocopy /MIR 基线备份（§4.1） |
| `det-test\` | 确定性测试树（`tools/` + `models/` + `assets/` + `src/`） |
| `gate-test\` | 闸门拦截测试树，含 `pristine\` 原始副本 |
| `rel-test\` | `package_release.py` 复现性测试树 |
| `eaptest\` | `$ErrorActionPreference` / stderr 交互测试 |
| `run_det.ps1`、`run_gates.ps1`、`run_gaps.ps1`、`run_build_twice.ps1`、`run_rebuild_assets.ps1`、`run_icons_manifest.ps1`、`analyze_psmesh.py`、`profile_build.py` | 测试脚本与输出 |

---

## 5. 修复优先级建议

1. **H1**：把 `build_meshes.py` 的生成器哈希（或规范化参数）写入 manifest 并纳入 `verify_assets.py` 判定。
   —— 收益最大，且顺带解决 M4。
2. **H2**：`package_release.py` 固定 zip 时间戳 + 校验 `buildinfo.txt` 的 version/commit。
   —— 当前发行包已经与实际源码不同步，这是**已经发生的**问题。
3. **M5**：修 `threemf.py:193-198` 的缓存键，省约 15-20% 构建时间，改动 2 行。
4. **M3**：去掉 `.psmesh` 的冗余每顶点颜色块，减小约 17%（需同步改 `PsMeshReader.cs` + 升 magic）。
5. **M1/M2/M6/L4/L8**：闸门加固、路径可移植、版本单一来源、gitignore、依赖钉版本。
6. **L1/L2/L3**：死代码与 50 个一次性脚本的清理（可与审计 F 的仓库卫生合并）。
