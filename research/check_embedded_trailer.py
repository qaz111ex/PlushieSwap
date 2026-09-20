"""Verify the DLL's embedded .psmesh data carries the correct trailer.

The plugin loads the embedded copy, not the file on disk, so regenerating assets is only
half the job. This decompresses each embedded model exactly as AssetProvider does and
walks the stream the same way PsMeshReader does, then checks the trailing baked-outline
float is sane rather than garbage. Without that check a mismatch between the writer and
the reader stays hidden.
"""
import base64
import re
import struct

SRC = r"D:\zhuanban\Plushie Swap\src\EmbeddedAssets.g.cs"

with open(SRC, encoding="utf-8") as fh:
    text = fh.read()

# Each constant is emitted as several "..." literals joined with +. Reassemble them.
blobs = []
for m in re.finditer(r"private const string (\w+)Base64\s*=\s*(.*?);", text, re.S):
    name = m.group(1) + "Base64"
    body = m.group(2)
    pieces = re.findall(r'"([^"]*)"', body)
    blobs.append((name, "".join(pieces)))
print(f"{len(blobs)} embedded constants")


def inflate(b64):
    import zlib
    raw = base64.b64decode(b64)
    return zlib.decompress(raw, -15)


def walk(data):
    off = 8
    n = struct.unpack_from("<i", data, off)[0]
    off += 4 + n
    count = struct.unpack_from("<i", data, off)[0]
    off += 4
    for _ in range(count):
        off += 20
        vc, ic = struct.unpack_from("<ii", data, off)
        off += 8
        off += vc * 12 + vc * 12 + vc * 8 + vc * 12 + ic * 4
    off += 24
    has = struct.unpack_from("<i", data, off)[0]
    off += 4
    if has:
        off += 24 + 32
    wobble = struct.unpack_from("<i", data, off)[0]
    off += 4 + wobble
    outline = struct.unpack_from("<i", data, off)[0]
    off += 4
    if outline > 0:
        off += outline * 5
    left = len(data) - off
    thickness = struct.unpack_from("<f", data, off)[0] if left >= 4 else None
    return count, wobble, outline, left, thickness


for name, b64 in blobs:
    if "Mesh" not in name:
        continue
    data = inflate(b64)
    if not data.startswith(b"PSMESH"):
        continue
    count, wobble, outline, left, thickness = walk(data)
    ok = left == 4 and thickness is not None and 0.0 < thickness < 0.1
    print(f"{name}: submeshes={count} wobble={wobble} outline={outline} "
          f"bytesLeft={left} bakedThickness={thickness} -> {'OK' if ok else 'BROKEN'}")
