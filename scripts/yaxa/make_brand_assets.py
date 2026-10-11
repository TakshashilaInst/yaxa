"""Generate Yaxa placeholder brand images (icon, wordmark, favicons).

Placeholder until a designed Yaxa logo exists. Output goes to web/public/yaxa-*.png
as NEW files, so upstream DeepTutor image updates never conflict with ours.

Run from repo root (needs Pillow; macOS Georgia font, else a bundled default):
    python scripts/yaxa/make_brand_assets.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PUBLIC = Path(__file__).resolve().parents[2] / "web" / "public"
INK = (31, 58, 77, 255)        # deep slate-blue
ACCENT = (196, 120, 64, 255)   # warm terracotta
FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def icon(size: int) -> Image.Image:
    """Rounded square in INK with a serif 'Y' and an accent dot."""
    s = size * 4  # draw large, downsample for smooth edges
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s // 5, fill=INK)
    f = font(int(s * 0.72))
    box = d.textbbox((0, 0), "Y", font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((s - w) / 2 - box[0], (s - h) / 2 - box[1] - s * 0.02), "Y", font=f, fill="white")
    r = s * 0.07
    d.ellipse([s * 0.74 - r, s * 0.24 - r, s * 0.74 + r, s * 0.24 + r], fill=ACCENT)
    return img.resize((size, size), Image.LANCZOS)


def wordmark() -> Image.Image:
    """'Yaxa' in INK on transparent, same 897x236 frame as upstream banner.png."""
    W, H = 897, 236
    img = Image.new("RGBA", (W * 2, H * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(int(H * 2 * 0.78))
    box = d.textbbox((0, 0), "Yaxa", font=f)
    d.text((0 - box[0], (H * 2 - (box[3] - box[1])) / 2 - box[1]), "Yaxa", font=f, fill=INK)
    img = img.crop(img.getbbox())  # trim to the text
    img.thumbnail((W, H), Image.LANCZOS)
    return img


if __name__ == "__main__":
    icon(512).save(PUBLIC / "yaxa-logo.png")
    icon(180).save(PUBLIC / "yaxa-apple-touch-icon.png")
    icon(32).save(PUBLIC / "yaxa-favicon-32x32.png")
    icon(16).save(PUBLIC / "yaxa-favicon-16x16.png")
    wordmark().save(PUBLIC / "yaxa-banner.png")
    print("wrote yaxa-*.png to", PUBLIC)
