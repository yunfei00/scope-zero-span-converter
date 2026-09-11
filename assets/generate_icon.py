"""Rebuild the original project icon, offline: python assets/generate_icon.py."""

from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
SIZES = [16, 24, 32, 48, 64, 128, 256]
WAVE = [(35, 152), (68, 152), (87, 91), (107, 181), (128, 63), (150, 152), (181, 152), (198, 113), (221, 113)]


def generate() -> None:
    scale = 4
    image = Image.new("RGBA", (256 * scale, 256 * scale))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8*scale, 8*scale, 248*scale, 248*scale), radius=46*scale, fill="#13283f")
    for coordinate in (64, 128, 192):
        draw.line([(coordinate*scale, 36*scale), (coordinate*scale, 220*scale)], fill="#29445d", width=2*scale)
        draw.line([(36*scale, coordinate*scale), (220*scale, coordinate*scale)], fill="#29445d", width=2*scale)
    draw.line([(x*scale, y*scale) for x, y in WAVE], fill="#46e2c0", width=10*scale, joint="curve")
    image = image.resize((256, 256), Image.Resampling.LANCZOS)
    image.save(ROOT / "app.png")
    image.save(ROOT / "app.ico", sizes=[(size, size) for size in SIZES])


if __name__ == "__main__":
    generate()
