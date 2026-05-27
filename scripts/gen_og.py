"""
Generate frontend/og.png — 1200x630 OpenGraph share image for Taki.

Run-once dev tool (not part of cascade pipeline). Pillow only — no external
binaries, no SVG rasterizer. Uses macOS system fonts.

Install:  .venv/bin/pip install Pillow
Run:      .venv/bin/python scripts/gen_og.py
Output:   frontend/og.png  (1200x630 PNG)
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── paths ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "og.png"

# Mac system fonts (.ttc — collection files, index selects face)
F_CJK = "/System/Library/Fonts/Hiragino Sans GB.ttc"          # 滝 kanji
F_SERIF = "/System/Library/Fonts/Supplemental/Didot.ttc"      # wordmark
F_SANS = "/System/Library/Fonts/HelveticaNeue.ttc"            # taglines

# ── palette (matches frontend/index.html :root vars) ────────────────────
INK = (13, 14, 16)            # #0d0e10
PAPER = (241, 237, 228)        # #f1ede4
PAPER_DIM = (184, 178, 164)    # #b8b2a4
SHU = (232, 74, 58)            # #e84a3a vermillion
RULE = (42, 38, 32)            # #2a2620
GTM = (90, 214, 232)           # #5ad6e8
FINANCE = (152, 224, 138)      # #98e08a
MARKETING = (255, 133, 201)    # #ff85c9

W, H = 1200, 630


def _font(path: str, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    """Load a TTC/TTF face. Falls back to default if missing."""
    try:
        return ImageFont.truetype(path, size=size, index=index)
    except OSError:
        return ImageFont.load_default()


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def build() -> None:
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img, "RGBA")

    # ── LEFT — 滝 kanji ────────────────────────────────────────────────
    # Hiragino Sans GB index 1 = W6 (bolder); fallback to 0
    kanji_font = _font(F_CJK, 440, index=1)
    if isinstance(kanji_font, ImageFont.FreeTypeFont):
        # use anchor "mm" for true visual centering of the glyph
        d.text((250, H // 2), "滝", font=kanji_font, fill=SHU, anchor="mm")
    else:
        # extremely unlikely — only if Hiragino missing entirely
        d.text((250, H // 2), "TAKI", font=_font(F_SERIF, 100), fill=SHU, anchor="mm")

    # ── vertical rule between columns ──────────────────────────────────
    d.line([(490, 80), (490, H - 80)], fill=RULE, width=1)

    # ── RIGHT — wordmark + tagline stack ───────────────────────────────
    x = 540
    # "taki" wordmark — Didot, big and editorial
    word_font = _font(F_SERIF, 168, index=0)
    d.text((x, 110), "taki", font=word_font, fill=PAPER)

    # subtitle
    sub_font = _font(F_SANS, 36, index=2)  # Helvetica Neue Medium-ish
    d.text((x, 300), "cascading intelligence", font=sub_font, fill=PAPER_DIM)

    # vermillion accent rule (60px)
    d.line([(x, 372), (x + 60, 372)], fill=SHU, width=3)

    # one-liner pitch
    pitch_font = _font(F_SANS, 26, index=0)
    d.text(
        (x, 408),
        "agentic enterprise on live web data",
        font=pitch_font,
        fill=PAPER,
    )

    # composition line — 9 agents · 4 frameworks · one cache
    comp_font = _font(F_SANS, 22, index=0)
    d.text(
        (x, 458),
        "9 agents  ·  4 frameworks  ·  one shared Bright Data cache",
        font=comp_font,
        fill=PAPER_DIM,
    )

    # ── bottom-right credits ───────────────────────────────────────────
    credit_font = _font(F_SANS, 18, index=0)
    credit = "Bright Data  ·  LangGraph  ·  Vertex AI"
    cw = _text_w(d, credit, credit_font)
    d.text((W - 60 - cw, H - 50), credit, font=credit_font, fill=PAPER_DIM)

    # ── top-right tiny brand mark (3 vermillion strokes + droplets) ────
    mx, my = W - 100, 70
    for i, (dx, h) in enumerate([(-18, 36), (0, 42), (18, 34)]):
        d.line([(mx + dx, my), (mx + dx, my + h)], fill=SHU, width=4)
    for dx, dy, c in [(-18, 110, GTM), (0, 115, FINANCE), (18, 108, MARKETING)]:
        d.ellipse(
            (mx + dx - 4, my + dy - 4, mx + dx + 4, my + dy + 4),
            fill=c,
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT}  ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
