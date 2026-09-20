"""Confirm the trailing baked-thickness float lands where the C# reader expects it.

The C# PsMeshReader walks the stream by fixed-size blocks and then reads one final
float. If that offset is off by even four bytes the value comes out as garbage (or the
read is skipped as out-of-range), the outline driver sees 0, and the outline silently
falls back to the old baked world-space extrusion. This reproduces the exact walk so the
offset can be checked.
"""
import os
import struct

ASSETS = r"D:\zhuanban\Plushie Swap\assets"


def walk(path):
    data = open(path, "rb").read()
    assert data[:8] == b"PSMESH03"
    off = 8
    n = struct.unpack_from("<i", data, off)[0]
    off += 4 + n
    count = struct.unpack_from("<i", data, off)[0]
    off += 4
    for _ in range(count):
        off += 16 + 4                      # colour + flags
        vc, ic = struct.unpack_from("<ii", data, off)
        off += 8
        off += vc * 12 + vc * 12 + vc * 8 + vc * 12 + ic * 4
    off += 24                              # bounds
    has_grips = struct.unpack_from("<i", data, off)[0]
    off += 4
    if has_grips:
        off += 24
        off += 32                          # rotations
    wobble = struct.unpack_from("<i", data, off)[0]
    off += 4 + wobble
    outline = struct.unpack_from("<i", data, off)[0]
    off += 4
    if outline > 0:
        off += outline * 5
    return data, off, count, outline


for stem in ("miffy", "zichaoxiong"):
    data, off, count, outline = walk(os.path.join(ASSETS, stem + ".psmesh"))
    left = len(data) - off
    print(f"{stem}: submeshes={count} outlineCount={outline} "
          f"offset={off} size={len(data)} bytesLeft={left}")
    if left >= 4:
        baked = struct.unpack_from("<f", data, off)[0]
        print(f"   C# would read BakedOutlineThickness = {baked}")
    else:
        print("   C# would NOT read a thickness (stream ended) -> driver gets 0")
