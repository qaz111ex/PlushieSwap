"""Render a wide, high-contrast version of the screen-space outline check.

Diagnostic only: the same maths as verify_screenspace_outline, but with a thick line and
a tight crop, so the shape of the line (even, unbroken) can be inspected by eye.
"""
import io
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, r"D:\zhuanban\Plushie Swap\research")
sys.path.insert(0, r"D:\zhuanban\Plushie Swap\tools")

SRC = r"D:\zhuanban\Plushie Swap\research\verify_screenspace_outline.py"

with io.open(SRC, encoding="utf-8") as fh:
    code = fh.read().replace("if __name__ == '__main__':", "if False:")
ns = {"__file__": SRC}
exec(compile(code, "verify", "exec"), ns)

ns["WIDTH_PX"] = 5.0
ns["RES"] = (900, 900)

import contextlib  # noqa: E402
with contextlib.redirect_stdout(io.StringIO()):
    ns["main"]()

for stem in ("miffy", "zichaoxiong"):
    src = rf"D:\zhuanban\Plushie Swap\research\preview\ss_check_{stem}_1.8.png"
    dst = rf"D:\zhuanban\Plushie Swap\research\preview\wide_{stem}.png"
    Image.open(src).crop((330, 170, 580, 630)).resize((500, 920), Image.NEAREST).save(dst)
    print("wrote", dst)
