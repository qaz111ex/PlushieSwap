"""Sample the real blush colour from the 3MF auxiliary reference photos."""
import io
import os
import zipfile

import numpy as np
from PIL import Image

SRC = r"C:\Users\Administrator\AppData\Local\Temp\opencode\models\zichaoxiong.3mf"

with zipfile.ZipFile(SRC) as z:
    for name in z.namelist():
        if not name.lower().endswith((".png", ".webp")):
            continue
        if "thumbnail_small" in name or "pick" in name:
            continue
        try:
            im = Image.open(io.BytesIO(z.read(name))).convert("RGB")
        except Exception:
            continue
        a = np.array(im).astype(int)
        r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
        # blush: clearly reddish, saturated, brighter than the dark stripes
        blush = (r > 150) & (r - g > 40) & (r - b > 20) & (g > 60)
        if blush.sum() < 50:
            continue
        px = a[blush]
        med = np.median(px, axis=0).astype(int)
        print(f"{os.path.basename(name)}: {blush.sum()} blush px, median=#{med[0]:02X}{med[1]:02X}{med[2]:02X}")

print()
print("3MF palette (declared):")
import re
txt = zipfile.ZipFile(SRC).read("Metadata/project_settings.config").decode("utf-8", "replace")
m = re.search(r'"filament_colour"\s*:\s*\[([^\]]*)\]', txt)
for i, c in enumerate(re.findall(r'"([^"]*)"', m.group(1))):
    print(f"  filament {i + 1}: {c}")
