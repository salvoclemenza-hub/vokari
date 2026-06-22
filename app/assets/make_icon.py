"""Genera l'icona dell'app VOKARI (app/assets/vokari.png + .ico).

Icona brand: quadrato arrotondato verde azione + una 'V' bianca. Niente font esterni
(solo forme), così è riproducibile ovunque. Rigenerare con: uv run python app/assets/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
GREEN = (47, 158, 84, 255)  # verde azione VOKARI
WHITE = (255, 255, 255, 255)
RADIUS = 56


def make() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # sfondo: quadrato arrotondato verde
    d.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=RADIUS, fill=GREEN)
    # 'V' bianca spessa (top-left → bottom-center → top-right)
    w = 26
    d.line([(72, 78), (128, 188)], fill=WHITE, width=w, joint="curve")
    d.line([(128, 188), (184, 78)], fill=WHITE, width=w, joint="curve")
    # punte arrotondate
    for cx, cy in [(72, 78), (184, 78), (128, 188)]:
        d.ellipse([cx - w // 2, cy - w // 2, cx + w // 2, cy + w // 2], fill=WHITE)
    return img


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    img = make()
    img.save(out_dir / "vokari.png")
    # .ico multi-size per Windows (taskbar/titlebar)
    img.save(out_dir / "vokari.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Scritti:", out_dir / "vokari.png", "+", out_dir / "vokari.ico")


if __name__ == "__main__":
    main()
