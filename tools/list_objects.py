import re
import sys
import zipfile

p = sys.argv[1]
z = zipfile.ZipFile(p)
for name in z.namelist():
    if not (name.startswith("3D/") and name.endswith(".model")):
        continue
    data = z.read(name).decode("utf-8", "replace")
    ids = re.findall(r'<object id="(\d+)"', data)
    print(f"{name}: object ids = {ids}  len={len(data)}")
    for m in re.finditer(r'<object id="(\d+)"[^>]*>', data):
        print("   ", m.group(0), "@", m.start())
