import re
import sys
import zipfile
from collections import Counter

path = sys.argv[1]
member = sys.argv[2]
with zipfile.ZipFile(path) as z:
    data = z.read(member).decode("utf-8", "replace")

vals = Counter(re.findall(r'paint_color="([^"]*)"', data))
print("distinct paint_color values:", len(vals))
for k, v in vals.most_common(30):
    print(repr(k), v)

print()
print("sample triangle lines with paint_color:")
n = 0
for m in re.finditer(r'<triangle[^>]*>', data):
    if "paint_color" in m.group(0):
        print(m.group(0))
        n += 1
        if n >= 8:
            break

print()
print("sample triangle lines without paint_color:")
n = 0
for m in re.finditer(r'<triangle[^>]*>', data):
    if "paint_color" not in m.group(0):
        print(m.group(0))
        n += 1
        if n >= 5:
            break
