"""Genera gli asset icona di VOKARI riproducendo l'icona 'vicon' della Brand Board.

Riproduce in PIL il simbolo SVG `#vicon` estratto da Claude design
(riferimento vettoriale: `branding/vokari-icon.svg`): tile arrotondato a gradiente
diagonale + 9 barre waveform (bianco→phosphor) che formano una V + glow al vertice
+ blocco cursore. Rasterizza a qualsiasi dimensione con supersampling — niente
dipendenze SVG (cairosvg/resvg non necessari).

Output in app/assets/:
- vokari.png         256x256  (GUI)
- vokari.ico         16/32/48/64/128/256 (taskbar/titlebar Windows)
- vokari_512.png     master alta risoluzione
- store_logo_300.png Store logo 1:1

Rigenerare con: uv run python app/assets/make_icon.py
(la geometria vive qui; per modificare lo stile edita le costanti o l'SVG di riferimento)
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ASSETS = Path(__file__).resolve().parent

VB = 120  # lato viewBox dell'icona
SS = 4  # supersampling (anti-alias)

# Gradient stops (offset, RGB) — dall'SVG #vicon
TILE_STOPS = [(0.0, (0x22, 0xA2, 0x68)), (0.5, (0x1F, 0x8F, 0x5B)), (1.0, (0x17, 0x6C, 0x45))]
BAR_STOPS = [(0.0, (255, 255, 255)), (0.5, (255, 255, 255)), (0.74, (0xA6, 0xEC, 0xC6)), (1.0, (0x5F, 0xD9, 0x8F))]
PHOS = (0x5F, 0xD9, 0x8F)

TILE = (6, 6, 108, 108)  # x, y, w, h
RX_TILE = 26
RX_BAR = 3.5
BAR_GRAD_Y0, BAR_GRAD_Y1 = 22.0, 90.0  # span verticale del barGrad (userSpaceOnUse)
BARS = [  # (x, y, w, h) in unità viewBox — altezze a V
    (24.5, 22, 7, 24),
    (32.5, 25, 7, 34),
    (40.5, 40, 7, 20),
    (48.5, 43, 7, 30),
    (56.5, 44, 7, 44),
    (64.5, 43, 7, 30),
    (72.5, 40, 7, 20),
    (80.5, 25, 7, 34),
    (88.5, 22, 7, 24),
]
CURSOR = (56, 92, 8, 9, 1.5)  # x, y, w, h, rx


def _interp(stops: list, t: np.ndarray) -> np.ndarray:
    """Interpola un gradiente di colore (offset→RGB) sull'array di parametri t∈[0,1]."""
    offs = np.array([s[0] for s in stops])
    cols = np.array([s[1] for s in stops], dtype=float)
    out = np.empty((*t.shape, 3))
    for c in range(3):
        out[..., c] = np.interp(t, offs, cols[:, c])
    return out


def _tile_mask(W: int, s: float) -> Image.Image:
    x, y, w, h = TILE
    m = Image.new("L", (W, W), 0)
    ImageDraw.Draw(m).rounded_rectangle([x * s, y * s, (x + w) * s - 1, (y + h) * s - 1], radius=RX_TILE * s, fill=255)
    return m


def render(px: int) -> Image.Image:
    s = px * SS / VB
    W = int(VB * s)
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))

    yy, xx = np.mgrid[0:W, 0:W]
    Xv, Yv = xx / s, yy / s
    tmask = _tile_mask(W, s)

    # Tile: gradiente diagonale (top-left → bottom-right)
    tx, ty, tw, th = TILE
    t_tile = np.clip((np.clip((Xv - tx) / tw, 0, 1) + np.clip((Yv - ty) / th, 0, 1)) / 2, 0, 1)
    tile_arr = np.dstack([_interp(TILE_STOPS, t_tile), np.full((W, W), 255)]).astype(np.uint8)
    img.paste(Image.fromarray(tile_arr, "RGBA"), (0, 0), tmask)

    # tileLight: velo bianco in alto (0.16 → 0.03 → 0)
    la = np.interp(np.clip((Yv - ty) / th, 0, 1), [0, 0.4, 1], [0.16, 0.03, 0.0]) * 255
    light = np.dstack([np.full((W, W), 255), np.full((W, W), 255), np.full((W, W), 255), la]).astype(np.uint8)
    lay = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    lay.paste(Image.fromarray(light, "RGBA"), (0, 0), tmask)
    img = Image.alpha_composite(img, lay)

    # Glow al vertice (dietro le barre)
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [(60 - 15) * s, (84 - 17) * s, (60 + 15) * s, (84 + 17) * s], fill=(*PHOS, int(0.55 * 255))
    )
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(4 * s)))

    # Barre waveform (gradiente verticale bianco→phosphor)
    bar_t = np.clip((Yv - BAR_GRAD_Y0) / (BAR_GRAD_Y1 - BAR_GRAD_Y0), 0, 1)
    bar_arr = np.dstack([_interp(BAR_STOPS, bar_t), np.full((W, W), 255)]).astype(np.uint8)
    bmask = Image.new("L", (W, W), 0)
    bd = ImageDraw.Draw(bmask)
    for bx, by, bw, bh in BARS:
        bd.rounded_rectangle([bx * s, by * s, (bx + bw) * s - 1, (by + bh) * s - 1], radius=RX_BAR * s, fill=255)
    barlay = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    barlay.paste(Image.fromarray(bar_arr, "RGBA"), (0, 0), bmask)
    img = Image.alpha_composite(img, barlay)

    # Cursore (glow + pieno)
    cx, cy, cw, ch, crx = CURSOR
    cur = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(cur).rounded_rectangle(
        [cx * s, cy * s, (cx + cw) * s - 1, (cy + ch) * s - 1], radius=crx * s, fill=(*PHOS, 255)
    )
    img = Image.alpha_composite(img, cur.filter(ImageFilter.GaussianBlur(4 * s)))
    img = Image.alpha_composite(img, cur)

    return img.resize((px, px), Image.LANCZOS)


def main() -> None:
    master = render(512)
    master.save(ASSETS / "vokari_512.png")
    master.resize((256, 256), Image.LANCZOS).save(ASSETS / "vokari.png")
    master.resize((300, 300), Image.LANCZOS).save(ASSETS / "store_logo_300.png")
    master.save(ASSETS / "vokari.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Scritti: vokari.png, vokari.ico, vokari_512.png, store_logo_300.png")

    # Asset MSIX (Store): stessa icona #vicon, renderizzata alle misure dichiarate in
    # packaging/msix/AppxManifest.xml. Generarli QUI è il fix del disallineamento storico
    # (build_msix copia questi PNG verbatim → senza rigenerarli il pacchetto spediva la "V"
    # piatta vecchia mentre app/assets era già passato al brand #vicon).
    msix_assets = ASSETS.parent.parent / "packaging" / "msix" / "Assets"
    if msix_assets.is_dir():
        render(50).save(msix_assets / "StoreLogo.png")
        render(150).save(msix_assets / "Square150x150Logo.png")
        render(44).save(msix_assets / "Square44x44Logo.png")
        print(f"Scritti MSIX: StoreLogo.png, Square150x150Logo.png, Square44x44Logo.png -> {msix_assets}")
    else:
        print(f"[skip] asset MSIX: {msix_assets} non trovato")


if __name__ == "__main__":
    main()
