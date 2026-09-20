"""Verify that the embedded base64 in EmbeddedAssets.g.cs matches the assets/ folder.

Two things have to hold, and an earlier version only checked the first:

  1. every constant's bytes decompress back to the file it claims to carry;
  2. the runtime `Table` maps each file name to the RIGHT constant.

Checking only (1) let a file-name/constant swap through: pointing
`{ "miffy.psmesh", ... }` at the bear's constant still printed "ALL EMBEDDED ASSETS
VERIFIED" while the game would have loaded the wrong model. The table is parsed here
and each entry is resolved through its constant name to an expected source file.

A third, earlier-in-the-chain mistake is checked by tools/verify_assets.py: a source
3MF edited without rerunning build_meshes.py. build.ps1 runs that script before this
one, so the whole chain (3MF -> assets -> embedded) is gated.

The payload is deflate-compressed (raw deflate, no zlib wrapper), so it is inflated
again before comparing against the source files.
"""
import base64
import hashlib
import os
import re
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "EmbeddedAssets.g.cs")

# Constant name -> source file. The constants are what the generator emits; the table
# below is what the runtime actually looks files up by, so both directions are checked.
CONSTANT_FILES = {
    "MiffyMesh": os.path.join(ROOT, "assets", "miffy.psmesh"),
    "MiffyShading": os.path.join(ROOT, "assets", "miffy_shading.png"),
    "MiffyIcon": os.path.join(ROOT, "assets", "icons", "icon_miffy.png"),
    "ZichaoXiongMesh": os.path.join(ROOT, "assets", "zichaoxiong.psmesh"),
    "ZichaoXiongShading": os.path.join(ROOT, "assets", "zichaoxiong_shading.png"),
    "ZichaoXiongIcon": os.path.join(ROOT, "assets", "icons", "icon_zichaoxiong.png"),
}

# Runtime file name -> the constant it must resolve to. Kept independently of the
# generator so a mistake in the generator cannot satisfy this check by construction.
TABLE_EXPECTED = {
    "miffy.psmesh": "MiffyMesh",
    "miffy_shading.png": "MiffyShading",
    "icon_miffy.png": "MiffyIcon",
    "zichaoxiong.psmesh": "ZichaoXiongMesh",
    "zichaoxiong_shading.png": "ZichaoXiongShading",
    "icon_zichaoxiong.png": "ZichaoXiongIcon",
}

text = open(SRC, encoding="utf-8").read()
ok = True

# ---------------------------------------------------------------- 1. payload bytes
constant_pattern = re.compile(
    r'private const string (\w+)Base64 =\s*((?:"[^"]*"\s*\+?\s*)+);')
payloads = {}
for match in constant_pattern.finditer(text):
    name = match.group(1)
    b64 = "".join(re.findall(r'"([^"]*)"', match.group(2)))
    packed = base64.b64decode(b64)
    # re-add the zlib header/trailer that the generator strips
    payloads[name] = zlib.decompress(packed, -15)

print("constants:")
for name in sorted(CONSTANT_FILES):
    if name not in payloads:
        print(f"  {name:22s} MISSING FROM EmbeddedAssets.g.cs")
        ok = False
        continue
    data = payloads[name]
    ref = open(CONSTANT_FILES[name], "rb").read()
    same = hashlib.sha256(data).hexdigest() == hashlib.sha256(ref).hexdigest()
    ok = ok and same
    print(f"  {name:22s} {len(data):>9d} bytes  match={same}")

# ---------------------------------------------------------------- 2. table mapping
# The initialiser body itself contains `{ "name", Constant }` pairs, so the block is
# sliced out by bracket matching rather than by a non-greedy regex.
print("table:")
entries = {}
# `\b` matters: without it `NotATable = new Dictionary<...>` also matches, so renaming
# the field silently skipped this whole check instead of failing it.
table_start = re.search(r'\bTable\s*=\s*new Dictionary<string, string>[^{]*\{', text)
if table_start is None:
    print("  could not find the Table initialiser")
    ok = False
else:
    depth = 0
    end = table_start.end() - 1
    for i in range(end, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i
                break
    body = text[table_start.end():end]
    entries = dict(re.findall(r'\{\s*"([^"]+)"\s*,\s*(\w+)\s*\}', body))
    for file_name, expected in sorted(TABLE_EXPECTED.items()):
        actual = entries.get(file_name)
        # The generator writes the constant name with its `Base64` suffix; the suffix is
        # not part of the identity being checked.
        normalised = actual[:-len("Base64")] if actual and actual.endswith("Base64") else actual
        good = normalised == expected
        ok = ok and good
        print(f"  {file_name:24s} -> {actual or 'MISSING'}"
              + ("" if good else f"  (expected {expected}Base64)"))
    extra = sorted(set(entries) - set(TABLE_EXPECTED))
    if extra:
        print(f"  unexpected entries: {extra}")
        ok = False
    missing = sorted(set(TABLE_EXPECTED) - set(entries))
    if missing:
        print(f"  missing entries: {missing}")
        ok = False

# ------------------------------------------------------- 3. nothing but the six
# The checks above are all "for each thing I know about, is it right?". None of them
# notices a payload that was ADDED: a constant the table never points at still decodes
# fine and simply inflates the DLL, so the build stays green while shipping bytes the
# runtime can never reach. The counts pin that down, and also catch a generator that
# dropped or renamed a constant.
print("counts:")
unexpected_constants = sorted(set(payloads) - set(CONSTANT_FILES))
if unexpected_constants:
    print(f"  embedded constants with no expected source file: {unexpected_constants}")
    ok = False
print(f"  embedded constants   {len(payloads)} (expected {len(CONSTANT_FILES)})")
print(f"  table entries        {len(entries)} (expected {len(TABLE_EXPECTED)})")
if len(payloads) != len(CONSTANT_FILES) or len(entries) != len(TABLE_EXPECTED):
    ok = False

print()
print(f"{len(payloads)} embedded constants and "
      f"{len(TABLE_EXPECTED)} table entries checked")
print("ALL EMBEDDED ASSETS VERIFIED" if ok else "MISMATCH!")
# A non-zero exit lets build.ps1 gate the build on this, so a stale embedded copy can
# never be deployed again (the historical silent failure).
sys.exit(0 if ok else 1)
