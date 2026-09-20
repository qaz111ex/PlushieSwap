"""Check whether the declared pink filament #F95D73 appears anywhere in the slicer plate renders."""
import io
import zipfile

import numpy as np
from PIL import Image

SRC = r"C:\Users\Administrator\AppData\Local\Temp\opencode\models\zichaoxiong.3mf"
TARGETS = {
    "#F4EBEA": (244, 235, 234),
    "#FF9016": (255, 144, 22),
    "#100F0E": (16, 15, 14),
    "#F95D73": (249, 93, 115),
}

with zipfile.ZipFile(SRC) as z:
    for name in ("Metadata/plate_1.png", "Metadata/plate_no_light_1.png",
                 "Metadata/top_1.png", "Metadata/pick_1.png"):
        try:
            im = Image.open(io.BytesIO(z.read(name))).convert("RGB")
        except Exception as exc:
            print(name, "skip", exc)
            continue
        a = np.array(im).astype(int)
        print(f"--- {name} {im.size} ---")
        for label, (r, g, b) in TARGETS.items():
            dist = np.abs(a[:, :, 0] - r) + np.abs(a[:, :, 1] - g) + np.abs(a[:, :, 2] - b)
            near = (dist < 40).sum()
            print(f"    {label}: {near:>7d} px within distance 40")
