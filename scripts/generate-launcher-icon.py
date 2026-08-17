from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "launcher" / "assets" / "my-c-pop-working.ico"
CANVAS_SIZE = 1024


def interpolate(start: int, end: int, ratio: float) -> int:
    return round(start + (end - start) * ratio)


def draw_icon() -> Image.Image:
    image = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.ellipse((116, 136, 908, 928), fill=(5, 12, 18, 120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(34))
    image.alpha_composite(shadow)

    draw = ImageDraw.Draw(image)
    disc_bounds = (104, 104, 920, 920)
    draw.ellipse(disc_bounds, fill=(16, 19, 24, 255), outline=(60, 66, 72, 255), width=8)

    for radius in range(394, 116, -18):
        shade = 30 + radius % 17
        draw.ellipse(
            (512 - radius, 512 - radius, 512 + radius, 512 + radius),
            outline=(shade, shade + 3, shade + 7, 210),
            width=3,
        )

    for radius in range(158, 55, -1):
        ratio = (158 - radius) / 103
        color = (
            interpolate(250, 215, ratio),
            interpolate(94, 183, ratio),
            interpolate(76, 82, ratio),
            255,
        )
        draw.ellipse(
            (512 - radius, 512 - radius, 512 + radius, 512 + radius),
            fill=color,
        )

    draw.arc((150, 150, 874, 874), 205, 286, fill=(255, 255, 255, 74), width=16)
    draw.arc((184, 184, 840, 840), 24, 76, fill=(85, 226, 206, 90), width=9)
    draw.ellipse((475, 475, 549, 549), fill=(22, 26, 31, 255))
    draw.ellipse((493, 493, 531, 531), fill=(242, 223, 174, 255))
    draw.ellipse((503, 503, 521, 521), fill=(17, 20, 24, 255))
    return image


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    icon = draw_icon()
    icon.save(
        OUTPUT,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
