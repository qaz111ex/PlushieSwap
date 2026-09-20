"""Check that assets/*.psmesh still match the source 3MF, the parameters and the code
that produced them.

build.ps1 without -RebuildAssets never runs the Python pipeline. Editing models/*.3mf and
then running a plain build therefore used to publish the OLD models silently. This gate
reads assets/manifest.json (written by build_meshes.py) and refuses with exit 1 when:

  * a source .3mf hash no longer matches the manifest (the model was edited);
  * a .psmesh or palette PNG hash no longer matches the manifest (assets were replaced);
  * build_meshes.py / threemf.py changed since the assets were built (the generator was
    edited);
  * the parameters in build_meshes.py no longer match the ones recorded in the manifest.

The last two are the half the file hashes cannot see. Editing a parameter (or the
generator itself) leaves the existing assets perfectly self-consistent: they still match
the old 3MF and the old manifest, so every file check passes while the assets on disk
were produced by code that no longer exists. The generator hash and the recorded
canonical parameters are what close that hole.

The fix in every case is `pwsh -File build.ps1 -RebuildAssets`.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MANIFEST = os.path.join(ROOT, "assets", "manifest.json")

# Manifest format version that carries the `generator` block. A manifest without it
# predates the generator/parameter check, so it cannot be trusted to describe the
# current code and is treated as stale.
MANIFEST_VERSION = 2

# The scripts whose source decides what the built assets look like. Kept in sync with
# build_meshes.generator_hashes() by hand: if this list and the generator's disagree, the
# check would silently skip a file, which is exactly the failure being prevented.
GENERATOR_FILES = ("build_meshes.py", "threemf.py")

REBUILD = "Run build.ps1 -RebuildAssets to regenerate the models and the manifest."


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_generator(generator):
    """Compare the recorded generator hashes against the scripts on disk.

    Returns True when they agree. A missing or unknown file is a failure: a manifest that
    does not describe the current generator cannot prove the assets are current.
    """
    print("generator:")
    if not isinstance(generator, dict):
        print("  the manifest has no generator block (written before the generator "
              "check existed)")
        return False

    recorded = generator.get("files") if "files" in generator else generator
    if not isinstance(recorded, dict):
        print(f"  unreadable generator block: {recorded!r}")
        return False

    ok = True
    for name in GENERATOR_FILES:
        path = os.path.join(HERE, name)
        expected = recorded.get(name)
        if expected is None:
            print(f"  {name:20s} NOT RECORDED in the manifest")
            ok = False
            continue
        if not os.path.exists(path):
            print(f"  {name:20s} MISSING {path}")
            ok = False
            continue
        actual = sha256(path)
        same = actual == expected
        ok = ok and same
        print(f"  {name:20s} match={same}")
        if not same:
            print(f"       {name} changed since the assets were built"
                  f" (recorded {expected[:16]}..., now {actual[:16]}...)")

    unknown = sorted(set(recorded) - set(GENERATOR_FILES))
    if unknown:
        # Not fatal on its own, but it means this checker does not know about a file the
        # generator hashed, so the check is incomplete.
        print(f"  generator hashed files this checker does not verify: {unknown}")
        ok = False
    return ok


def check_entry(name, info, current_params):
    """Verify one asset entry. Returns True when every check passes."""
    print(f"{name}:")
    if not isinstance(info, dict):
        print(f"  malformed manifest entry (expected an object, found "
              f"{type(info).__name__})")
        return False

    missing_keys = [k for k in ("source", "shading_png") if k not in info]
    if missing_keys:
        print(f"  malformed manifest entry: missing key(s) {', '.join(missing_keys)}")
        return False

    checks = [
        ("source", os.path.join(ROOT, info["source"]), info.get("source_sha256"), True),
        ("mesh", os.path.join(ROOT, "assets", name), info.get("mesh_sha256"), False),
        ("shading", os.path.join(ROOT, "assets", info["shading_png"]),
         info.get("shading_sha256"), False),
    ]
    ok = True
    for label, path, expected, is_source in checks:
        if not os.path.exists(path):
            print(f"  {label:8s} MISSING {path}")
            ok = False
            continue
        actual = sha256(path)
        same = actual == expected
        ok = ok and same
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        print(f"  {label:8s} {rel:34s} match={same}")
        if not same:
            if is_source:
                print(f"           the source model changed since {name} was built;"
                      " the pipeline was NOT rerun")
            else:
                print(f"           {name} does not match the manifest;"
                      " assets were edited or replaced by hand")
        elif is_source:
            print(f"           params: {info.get('params')}")

    # The parameters that produced this asset, as recorded at build time.
    recorded_params = info.get("params_canonical")
    if recorded_params is None:
        print("  params   NOT RECORDED (manifest written before the parameter check)")
        return False

    current = current_params.get(name)
    if current is None:
        print(f"  params   no job in build_meshes.py produces {name}")
        return False
    same = current == recorded_params
    ok = ok and same
    print(f"  params   match={same}")
    if not same:
        print("           the parameters in build_meshes.py changed since these assets"
              " were built; the pipeline was NOT rerun")
        print(f"           recorded: {recorded_params}")
        print(f"           current : {current}")
    return ok


def load_current_params():
    """Canonical params per asset, as build_meshes.py would produce them right now.

    Imported lazily so a broken build_meshes.py reports as a failed check rather than
    crashing the gate before it prints anything useful. build_meshes.py's `__main__` block
    is guarded, so importing it is side-effect free.
    """
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import build_meshes
        return build_meshes.job_params()
    except Exception as exc:  # noqa: BLE001 - any failure means "cannot verify"
        print(f"could not read the current parameters from build_meshes.py: "
              f"{type(exc).__name__}: {exc}")
        print(REBUILD)
        return None


def main():
    if not os.path.exists(MANIFEST):
        print(f"missing {MANIFEST}")
        print(REBUILD)
        return 1

    try:
        with open(MANIFEST, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError) as exc:
        # A truncated or hand-edited manifest used to escape as a raw traceback, which
        # build.ps1 then printed as if it were normal output.
        print(f"{MANIFEST} is not readable JSON: {type(exc).__name__}: {exc}")
        print(REBUILD)
        return 1

    if not isinstance(payload, dict):
        print(f"{MANIFEST} is not a JSON object")
        print(REBUILD)
        return 1

    version = payload.get("version")
    if version != MANIFEST_VERSION:
        print(f"manifest version {version!r} is not the expected {MANIFEST_VERSION}; "
              "it was written before the generator/parameter checks")
        print(REBUILD)
        return 1

    assets = payload.get("assets")
    if not isinstance(assets, dict) or not assets:
        print("manifest has no asset entries")
        print(REBUILD)
        return 1

    ok = check_generator(payload.get("generator"))
    print()

    current_params = load_current_params()
    if current_params is None:
        return 1

    for name in sorted(assets):
        ok = check_entry(name, assets[name], current_params) and ok

    print()
    if ok:
        print("ALL SOURCE MODELS MATCH THE BUILT ASSETS")
        return 0
    print("ASSETS ARE STALE OR OUT OF SYNC: run build.ps1 -RebuildAssets")
    return 1


if __name__ == "__main__":
    sys.exit(main())
