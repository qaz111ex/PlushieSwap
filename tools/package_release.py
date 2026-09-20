"""Assemble the Thunderstore release package.

Thunderstore expects a flat zip whose root holds the mod's `plugins/` folder plus
`manifest.json`, `README.md`, an optional `CHANGELOG.md` and a 256x256 `icon.png`.
The layout and the manifest keys were checked against the Thunderstore wiki's
"Creating a package" page; the BepInEx dependency string is the one the PEAK community
uses (`BepInEx-BepInExPack_PEAK-5.4.75301`, which is BepInEx 5.4.23.3, the version this
mod is built against).

Run after `build.ps1` has produced `dist/`:

    python tools/package_release.py

The package is reproducible: the same `dist/` DLL, the same `release/icon.png` and the
same sources always produce a byte-identical zip. That is what makes "which commit is in
this zip?" answerable by hashing it. Two things had to change for that to hold:

  * every zip entry gets a fixed timestamp (the file mtime used to be stored, so two runs
    minutes apart produced different bytes from identical input);
  * the entry order is sorted, instead of following whatever os.walk happened to return.

The commit and version are also *verified*, not just recorded: a stale `dist/` (built
before the current sources) used to be packaged silently, which is how the published
1.0.0 zip came to contain a DLL from an older commit than the repository.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist", "PlushieSwap")
RELEASE = os.path.join(ROOT, "release")
STAGE = os.path.join(RELEASE, "stage")

NAME = "PlushieSwap"
DISPLAY_NAME = "Plushie Swap"
# The version is read from PlushieSwap.csproj at run time; see read_csproj_version().
DEPENDENCIES = ["BepInEx-BepInExPack_PEAK-5.4.75301"]

# The public source repository, also written into the package's manifest.json so the
# Thunderstore page links back to the code and to the model pipeline.
WEBSITE_URL = "https://github.com/qaz111ex/PlushieSwap"

# Fixed timestamp for every zip entry. 1980-01-01 is the earliest value the MS-DOS
# timestamp in a zip can represent, so it is always encodable.
FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)

DESCRIPTION = (
    "Replaces the BingBong plush with a cartoon Miffy or Zichao Xiong. Switch between "
    "the vanilla bear and both replacements in game with F7. Models, shading and icons "
    "are embedded in the DLL."
)

README = """# Plushie Swap

Replaces the **BingBong** plush in PEAK with a cartoon **Miffy** (米菲兔) or
**Zichao Xiong** (自嘲熊), and lets you switch between those and the original bear at
any time.

## Features

- Three forms, cycled in game with **F7**: `Vanilla` -> `Miffy` -> `ZichaoXiong`
  (the default is Zichao Xiong).
- The plush keeps its **screen-space constant-width ink outline**, drawn from the
  model itself, so the line stays crisp at any distance.
- Name and inventory icon follow the chosen plush.
- The model inherits the game's own squeeze animation when you hold primary fire.
- Models, baked shading and icons are embedded in the DLL: one file, no loose assets.

## Configuration

`BepInEx\\config\\com.zhuanban.peak.plushieswap.cfg`

| Option | Default | Meaning |
| --- | --- | --- |
| `Plushie` | `ZichaoXiong` | Which form to use: `Vanilla`, `Miffy` or `ZichaoXiong` |
| `Cycle Plush Hotkey` | `F7` | In-game hotkey that cycles the forms (a single key, no modifiers) |
| `World Scale` | `1.0` | Size multiplier while held or lying in the world |
| `Backpack Scale` | `1.0` | Extra size multiplier while inside a backpack |
| `Hold Height Offset` | `0.0` | Extra up/down nudge while held |
| `Rename Item` | `true` | Rename the item to match the chosen plush |
| `Replace Icon` | `true` | Replace the inventory icon |
| `Outline Width (pixels)` | `5.0` | Ink line width in screen pixels; `0` hides it |
| `Shader Override` | *(empty)* | Only needed if the model renders with wrong colours (needs a restart) |
| `Verbose Logging` | `false` | Write detailed diagnostics to the BepInEx log |

Changes made in the in-game mod settings apply immediately (the one exception is
`Shader Override`, which is cached per variant and needs a restart). Editing the config
file by hand is **not** hot-reloaded: restart the game to pick it up.

## Installing

1. Install [BepInExPack PEAK](https://thunderstore.io/c/peak/p/BepInEx/BepInExPack_PEAK/)
   if you have not already.
2. Drop this package in with your mod manager, or unzip it so that
   `plugins/PlushieSwap/PlushieSwap.dll` lands inside the game's `BepInEx` folder.

## Credits and licensing

Thanks to **[ScallionMiku](https://github.com/xiaofe12/ScallionMiku)** by
**[xiaofe12](https://github.com/xiaofe12)** (published on Thunderstore as
[Thanks/ScallionMiku](https://thunderstore.io/c/peak/p/Thanks/ScallionMiku/)), the only other
mod in the PEAK community that replaces the plush model. It was the reference this mod was
built against: hiding the vanilla renderers, leaving the original `mainRenderer` alone, and
validating the vanilla visibility every frame all came from studying it. It is not bundled
here, and the two mods cannot be installed together (they patch the same nine game methods).

Source code: <https://github.com/qaz111ex/PlushieSwap> (MIT).

Both replacement models are third-party 3D printing models. They were reprocessed here
(decimated, re-oriented, fitted to the vanilla silhouette, baked shading, generated
outline shell) but they are **not** original to this mod, and all rights remain with
their authors.

**Zichao Xiong (自嘲熊)** — "坐姿自嘲熊（多色一体）"
- Source: <https://makerworld.com.cn/zh/models/2666015-zuo-zi-zi-chao-xiong-duo-se-yi-ti>
- Author: **夜夜椰子冰** (MakerWorld UID `2431656860`), per the `Designer` field embedded
  in the 3MF.
- Licence: **Standard Digital File License** (the licence selected when it was uploaded).
- The same model is also published on MakerWorld's international site
  (<https://makerworld.com/en/models/3154227>), credited there to **Lorensi**
  (UID `495168789`). Title, cover image, creation date and licence all match, so these
  are two uploads of one model; which came first could not be established, so both are
  listed.

**Miffy (米菲兔)** — "米菲兔 经典艺术 白剪纸"
- Source: <https://makerworld.com.cn/zh/models/2032846-miffy-mi-fei-tu-jing-dian-yi-zhu-bai-jian-zhi-chi>
- Author: **再也不打没用的东西了** (MakerWorld `@user_3189506737`)
- Licence: **not stated.** The supplied 3MF has empty `Designer` / `Licence` / `Title`
  fields and the page states no licence.

This is a **non-commercial** fan project. It charges nothing and claims no rights over
either model. The Miffy character itself is the property of Dick Bruna / Mercis bv,
independently of whoever modelled it. If you are an author or rights holder and would
like the attribution changed, a licence clarified, or your model removed, please get in
touch via the release page and it will be done in the next version — the mod will then
keep only the `Vanilla` option, or ship without the geometry and let users generate it
locally.
"""

def read_changelog():
    """The changelog, read from the repository's CHANGELOG.md.

    Keeping a second copy here is how a package ends up shipping notes that do not match
    the repository, so there is deliberately no CHANGELOG literal in this file.
    """
    path = os.path.join(ROOT, "CHANGELOG.md")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}")



def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args):
    """Run a git command in the project root; return stdout, or None on any failure."""
    try:
        proc = subprocess.run(["git", "-C", ROOT] + list(args),
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def read_csproj_version():
    """The single source of truth for the version: PlushieSwap.csproj.

    Keeping a second hand-written copy here is how the DLL and the Thunderstore manifest
    drift apart, so there is deliberately no VERSION constant in this file.
    """
    path = os.path.join(ROOT, "PlushieSwap.csproj")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}")
    match = re.search(r"<Version>\s*([^<\s]+)\s*</Version>", text)
    if not match:
        raise SystemExit(f"no <Version> element in {path}")
    return match.group(1)


def read_buildinfo():
    """Parse dist/PlushieSwap/buildinfo.txt into a dict.

    build.ps1 writes it next to the DLL it describes, which makes it the only record of
    which commit the DLL in dist/ actually came from.
    """
    path = os.path.join(DIST, "buildinfo.txt")
    if not os.path.isfile(path):
        raise SystemExit(
            f"{path} is missing; run build.ps1 first (it records the commit, version "
            "and DLL hash that this script verifies against)")
    info = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            key, sep, value = line.partition(":")
            if sep:
                info[key.strip()] = value.strip()
    return info


def read_cs_source_version():
    """The version as compiled into the DLL, from Plugin.DisplayVersion.

    The BepInPlugin attribute and the log line both use this constant, so it and the
    csproj <Version> are the two places a version is written by hand. They must agree, or
    the version the game reports would differ from the one Thunderstore sees. Rather than
    trusting that, this reads the constant and `main` compares the two.
    """
    path = os.path.join(ROOT, "src", "Plugin.cs")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}")
    match = re.search(r'DisplayVersion\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit(f"no DisplayVersion constant in {path}")
    return match.group(1)


def verify_dist(dll_path, version):
    """Refuse to package a dist/ that does not match its own record or the current HEAD.

    Every check here exists because its absence shipped a stale package: the zip that was
    published as 1.0.0 carried a DLL from an older commit than the repository, and nothing
    in the pipeline noticed.
    """
    info = read_buildinfo()
    missing = [k for k in ("commit", "version", "sha256") if k not in info]
    if missing:
        raise SystemExit(f"{DIST}{os.sep}buildinfo.txt is missing field(s): "
                         f"{', '.join(missing)}; rerun build.ps1")

    # 1. the DLL on disk is the one buildinfo.txt describes
    actual_hash = sha256_file(dll_path)
    if actual_hash.lower() != info["sha256"].lower():
        raise SystemExit(
            "dist/PlushieSwap/PlushieSwap.dll does not match the hash recorded in "
            f"buildinfo.txt:\n  recorded {info['sha256']}\n  actual   {actual_hash}\n"
            "The DLL was replaced or the buildinfo is stale; rerun build.ps1.")

    # 2. the version the DLL was built as matches the csproj
    built_version = info["version"].split("+", 1)[0]
    if built_version != version:
        raise SystemExit(
            f"dist/ was built as version {built_version} but PlushieSwap.csproj says "
            f"{version}; rerun build.ps1 before packaging.")

    # 3. the commit the DLL was built from is the current HEAD
    head = git("rev-parse", "--short", "HEAD")
    recorded_commit = info["commit"]
    dirty_built = recorded_commit.endswith("-dirty")
    recorded_sha = recorded_commit[:-len("-dirty")] if dirty_built else recorded_commit
    if head is None:
        print("WARNING: could not read the git HEAD; skipping the commit checks")
        return info, None, False
    if recorded_sha != head:
        raise SystemExit(
            f"dist/ was built from commit {recorded_sha} but HEAD is {head}.\n"
            "The package would ship code that is not the current checkout; "
            "rerun build.ps1.")

    # 4. the dirty state the DLL was built in matches the tree now. A DLL built from a
    #    clean tree cannot be trusted once the tree has uncommitted edits, and vice versa.
    status = git("status", "--porcelain")
    if status is not None:
        dirty_now = bool(status)
        if dirty_now != dirty_built:
            state_now = "dirty" if dirty_now else "clean"
            state_built = "dirty" if dirty_built else "clean"
            raise SystemExit(
                f"dist/ was built from a {state_built} tree but the working tree is now "
                f"{state_now};\nrerun build.ps1 so the recorded commit describes the "
                "source actually being packaged.")
    else:
        dirty_now = dirty_built

    return info, head, dirty_now


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def add_file(zf, full, rel):
    """Add one file with a fixed timestamp and mode, so the zip is reproducible."""
    info = zipfile.ZipInfo(rel, date_time=FIXED_DATE_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    # A constant mode keeps the external attributes identical across runs and machines.
    info.external_attr = 0o644 << 16
    with open(full, "rb") as fh:
        zf.writestr(info, fh.read())


def main():
    version = read_csproj_version()

    # The version exists in the csproj and in Plugin.DisplayVersion; both are hand-written,
    # so they are compared rather than assumed equal. A mismatch would ship a package whose
    # manifest version disagrees with the version the game reports for itself.
    source_version = read_cs_source_version()
    if source_version != version:
        raise SystemExit(
            f"version mismatch: PlushieSwap.csproj says {version} but "
            f"Plugin.DisplayVersion says {source_version}; make them agree.")

    dll_path = os.path.join(DIST, "PlushieSwap.dll")
    if not os.path.isfile(dll_path):
        raise SystemExit("dist/PlushieSwap/PlushieSwap.dll is missing; run build.ps1 first")

    buildinfo, head, dirty = verify_dist(dll_path, version)

    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE)
    os.makedirs(os.path.join(STAGE, "plugins", NAME))

    # The DLL is the whole mod. The audit-only buildinfo.txt from dist/ is not copied
    # verbatim; a trimmed one is written into the package root below, so the shipped zip
    # can be traced back to a commit without carrying anything machine-local.
    shutil.copy2(dll_path, os.path.join(STAGE, "plugins", NAME, "PlushieSwap.dll"))

    icon_src = os.path.join(RELEASE, "icon.png")
    if not os.path.isfile(icon_src):
        raise SystemExit("release/icon.png is missing; run tools/build_icon_release.py")

    manifest = {
        "name": NAME,
        "version_number": version,
        "website_url": WEBSITE_URL,
        "description": DESCRIPTION,
        "dependencies": DEPENDENCIES,
    }

    write(os.path.join(STAGE, "manifest.json"),
          json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    write(os.path.join(STAGE, "README.md"), README)
    write(os.path.join(STAGE, "CHANGELOG.md"), read_changelog())
    shutil.copy2(icon_src, os.path.join(STAGE, "icon.png"))

    # Provenance for the shipped artifact, written from the verified buildinfo so it
    # cannot disagree with the DLL in the same zip.
    write(os.path.join(STAGE, "buildinfo.txt"),
          "".join(f"{key}: {buildinfo[key]}\n"
                  for key in ("commit", "version", "sha256", "built_utc")
                  if key in buildinfo))

    out = os.path.join(RELEASE, f"{NAME}-{version}.zip")
    if os.path.exists(out):
        os.remove(out)

    # Sorted by relative path so the entry order does not depend on os.walk's order.
    members = []
    for folder, _, files in os.walk(STAGE):
        for name in files:
            full = os.path.join(folder, name)
            rel = os.path.relpath(full, STAGE).replace(os.sep, "/")
            members.append((rel, full))
    members.sort()

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, full in members:
            add_file(zf, full, rel)

    print(f"packaged {NAME} {version} from commit {buildinfo['commit']}"
          + (" (working tree dirty)" if dirty else ""))
    print(f"wrote {out} ({os.path.getsize(out) / 1024 / 1024:.1f} MB)")
    with zipfile.ZipFile(out) as zf:
        for info in zf.infolist():
            print(f"  {info.filename:44s} {info.file_size:>9d} bytes")
    print(f"  sha256 {sha256_file(out)}")


if __name__ == "__main__":
    main()
