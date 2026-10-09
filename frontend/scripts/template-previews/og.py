"""Makes public/og-image.jpg, the picture shown when the site's link is
shared (WhatsApp, Facebook, Instagram…), from three of the template
pictures render.py made. Run it again after them:

    python scripts/template-previews/og.py

then raise the ?v= of og-image.jpg in index.html: WhatsApp and Facebook
keep a shared picture as long as its address doesn't change.
"""
from pathlib import Path

from PIL import Image, ImageFilter

FRONTEND = Path(__file__).resolve().parents[2]
COVERS = FRONTEND / "public" / "theme-covers"
OUT = FRONTEND / "public" / "og-image.jpg"

TEMPLATES = ["family-mom", "couple-notre-rencontre", "travel-hawaii"]
W, H = 1200, 630
BACKGROUND = (249, 248, 246)  # the site's paper colour
CARD_H = 500
GAP = 30


def main():
    cards = [Image.open(COVERS / f"{name}.webp").convert("RGB") for name in TEMPLATES]
    card_w = round(cards[0].width * CARD_H / cards[0].height)
    x0 = (W - (len(cards) * card_w + (len(cards) - 1) * GAP)) // 2
    y0 = (H - CARD_H) // 2
    canvas = Image.new("RGB", (W, H), BACKGROUND)
    shadow = Image.new("L", (W, H), 0)
    for i in range(len(cards)):
        x = x0 + i * (card_w + GAP)
        shadow.paste(40, (x + 4, y0 + 10, x + card_w + 4, y0 + CARD_H + 10))
    canvas.paste((60, 50, 40), (0, 0), shadow.filter(ImageFilter.GaussianBlur(14)))
    for i, card in enumerate(cards):
        canvas.paste(card.resize((card_w, CARD_H), Image.LANCZOS), (x0 + i * (card_w + GAP), y0))
    canvas.save(OUT, "JPEG", quality=88, optimize=True, progressive=True)
    print("made", OUT.relative_to(FRONTEND))


if __name__ == "__main__":
    main()
