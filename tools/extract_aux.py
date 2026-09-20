import io
import os
import zipfile

from PIL import Image

SRC = r"C:\Users\Administrator\AppData\Local\Temp\opencode\models"
OUT = r"D:\zhuanban\Plushie Swap\tools\preview_aux"
os.makedirs(OUT, exist_ok=True)

for stem in ("miffy", "zichaoxiong"):
    path = os.path.join(SRC, stem + ".3mf")
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.lower().endswith((".png", ".webp", ".jpg", ".jpeg")):
                continue
            data = z.read(name)
            try:
                im = Image.open(io.BytesIO(data))
            except Exception as exc:
                print("skip", name, exc)
                continue
            safe = name.replace("/", "__").replace("\\", "__")
            safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in safe)
            out = os.path.join(OUT, f"{stem}__{safe}")
            im.save(out)
            print(f"{stem}: {name} -> {im.size} {im.mode}")
