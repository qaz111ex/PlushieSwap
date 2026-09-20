"""Build the Thunderstore package icon from the supplied in-game screenshot.

The source is a 1280x720 screenshot with the bear roughly centred and the pool behind
it. The icon needs to be 256x256 and carry both the Chinese name and the mod's English
name, so the bear is cropped to a square around the head and shoulders, a scrim is laid
over the lower third for legibility, and the two lines are drawn on top.

Run:
    python tools/build_icon_release.py [--source PATH] [--out PATH] [--font PATH]

The source screenshot is NOT in the repository (it is a 1280x720 game capture), so the
default is a path inside the project that can be restored when the icon has to be
regenerated. `release/icon.png` is a shipped artifact: this script only ever writes it
when it has successfully produced a new image, so a missing source cannot destroy it.

The crop rectangle and the text below are tied to that specific screenshot. A different
image will produce a different icon, so --source exists for regenerating from a restored
copy, not for substituting arbitrary art.
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Default source: inside the project, so the script works from any checkout once the
# screenshot has been put back. It used to be an absolute path under D:\备份\, which made
# the icon impossible to regenerate on any other machine (and on this one, after the file
# was deleted).
DEFAULT_SOURCE = os.path.join(ROOT, "research", "icon_source.jpg")
OUT = os.path.join(ROOT, "release", "icon.png")

# Fonts are resolved in this order; the first that exists wins. An absolute Windows path
# used to be the only option, which made the script Windows-only and failed obscurely.
FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/PingFang.ttc",
)

# The square that frames the bear's head and shoulders in the 1280x720 screenshot.
# The head occupies roughly x 380..880, y 100..490, so a square centred on it and
# reaching down to the paws keeps the whole face clear of the text band at the bottom.
CROP = (350, 20, 910, 580)          # left, top, right, bottom  (560x560)

CHINESE = "自嘲熊"
ENGLISH = "Plushie Swap"


def resolve_font(explicit):
    """Return the first usable font path, or None to fall back to Pillow's default."""
    if explicit:
        if not os.path.isfile(explicit):
            raise SystemExit(f"font not found: {explicit}")
        return explicit
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def load_font(font_path, size):
    if font_path is None:
        # Pillow's built-in bitmap font ignores `size` and cannot render CJK, but it
        # keeps the script usable enough to produce a (degraded) icon instead of
        # crashing on a machine with no CJK font installed.
        print("WARNING: no CJK font found; falling back to Pillow's built-in font, "
              "which cannot render the Chinese name correctly", file=sys.stderr)
        return ImageFont.load_default()
    return ImageFont.truetype(font_path, size)


def fit_font(font_path, text, max_width, start_size):
    """Largest font size at which `text` still fits `max_width`."""
    size = start_size
    while size > 8:
        font = load_font(font_path, size)
        box = font.getbbox(text)
        if box[2] - box[0] <= max_width:
            return font
        size -= 2
    return load_font(font_path, 8)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default=DEFAULT_SOURCE,
                        help="1280x720 screenshot to crop the icon from "
                             f"(default: {DEFAULT_SOURCE})")
    parser.add_argument("--out", default=OUT,
                        help=f"output PNG path (default: {OUT})")
    parser.add_argument("--font", default=None,
                        help="CJK font file to use for the text "
                             "(default: first of the known system fonts)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if not os.path.isfile(args.source):
        raise SystemExit(
            f"source screenshot not found: {args.source}\n"
            "release/icon.png is a shipped artifact and has NOT been touched.\n"
            "To regenerate it, restore the 1280x720 screenshot to that path (or pass "
            "--source PATH) and run this script again.")

    font_path = resolve_font(args.font)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    image = Image.open(args.source).convert("RGB")
    image = image.crop(CROP).resize((256, 256), Image.LANCZOS)
    image = image.convert("RGBA")

    # A vertical scrim so the text stays readable over the bright body and the pool.
    scrim = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    pixels = scrim.load()
    for y in range(150, 256):
        # 0 at the top of the band, ramping to a solid foot.
        alpha = int(215 * (y - 150) / (256 - 150))
        for x in range(256):
            pixels[x, y] = (8, 10, 16, alpha)
    image = Image.alpha_composite(image, scrim)

    draw = ImageDraw.Draw(image)

    cn = fit_font(font_path, CHINESE, 210, 64)
    en = fit_font(font_path, ENGLISH, 210, 30)

    cn_box = cn.getbbox(CHINESE)
    cn_w = cn_box[2] - cn_box[0]
    cn_h = cn_box[3] - cn_box[1]
    en_box = en.getbbox(ENGLISH)
    en_w = en_box[2] - en_box[0]
    en_h = en_box[3] - en_box[1]

    gap = 6
    total = cn_h + gap + en_h
    top = 256 - 16 - total

    def blit(text, font, width, height, y, fill):
        box = font.getbbox(text)
        draw.text(((256 - width) / 2 - box[0], y - box[1]), text, font=font, fill=fill)

    # A soft shadow keeps the text off the bright bear even where the scrim is thin.
    shadow = (0, 0, 0, 170)
    blit(CHINESE, cn, cn_w, cn_h, top + 2, shadow)
    blit(ENGLISH, en, en_w, en_h, top + cn_h + gap + 2, shadow)
    blit(CHINESE, cn, cn_w, cn_h, top, (255, 255, 255, 255))
    blit(ENGLISH, en, en_w, en_h, top + cn_h + gap, (235, 240, 250, 255))

    # Written only after the image is fully built, so a failure above cannot leave a
    # truncated icon.png behind.
    image.save(args.out)
    print("wrote", args.out, image.size)


if __name__ == "__main__":
    main()
