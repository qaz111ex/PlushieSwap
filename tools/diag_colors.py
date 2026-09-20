import re
import sys
import zipfile
from collections import Counter

import numpy as np

sys.path.insert(0, r"D:\zhuanban\Plushie Swap\tools")

path = r"C:\Users\Administrator\AppData\Local\Temp\opencode\models\zichaoxiong.3mf"
z = zipfile.ZipFile(path)

print("=== names ===")
for n in z.namelist():
    print("  ", n)

print()
print("=== filament_sequence.json ===")
try:
    print(z.read("Metadata/filament_sequence.json").decode("utf-8", "replace"))
except KeyError:
    print("  (absent)")

print()
print("=== project_settings filament arrays ===")
txt = z.read("Metadata/project_settings.config").decode("utf-8", "replace")
for key in ("filament_colour", "filament_type", "filament_ids", "filament_settings_id",
            "filament_multi_colour", "extruder_colour", "filament_map", "filament_maps"):
    m = re.search(r'"' + key + r'"\s*:\s*\[([^\]]*)\]', txt)
    if m:
        print("  ", key, "=", re.findall(r'"?([^",\s]+)"?', m.group(1)))

print()
print("=== model_settings.config ===")
print(z.read("Metadata/model_settings.config").decode("utf-8", "replace"))

print()
print("=== paint_color histogram ===")
data = z.read("3D/Objects/object_16.model").decode("utf-8", "replace")
codes = re.findall(r'paint_color="([^"]*)"', data)
hist = Counter(codes)
print("  distinct:", len(hist))
for k, v in hist.most_common(40):
    print(f"   {k!r:40s} {v}")
