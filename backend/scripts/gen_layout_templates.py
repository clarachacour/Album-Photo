"""Generates the page templates for each orientation, drawn in millimetres on
an A4 page (A5 has the same proportions) and stored as fractions of the page,
into the two identical copies the backend and the editor read:

    python backend/scripts/gen_layout_templates.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = [ROOT / "backend/app/services/layout_templates.json", ROOT / "frontend/src/lib/layoutTemplates.json"]

MARGIN, GAP = 12.0, 6.0
P, L = 3 / 4, 4 / 3  # portrait and landscape phone photos

def build(W, H, defs):
    UW, UH = W - 2 * MARGIN, H - 2 * MARGIN
    out = {}
    for name, (fr, en, slots) in defs(UW, UH).items():
        out[name] = {
            "label_fr": fr, "label_en": en,
            "slots": [{"x": round((MARGIN + x) / W, 5), "y": round((MARGIN + y) / H, 5), "w": round(w / W, 5), "h": round(h / H, 5)} for x, y, w, h in slots],
        }
    return out

def landscape(UW, UH):
    hw = (UW - GAP) / 2
    bw = UH * P                      # tall photo on the full height
    rw = UW - bw - GAP               # the column beside it
    rh = (UH - GAP) / 2
    cw3 = (UW - 2 * GAP) / 3; ch3 = cw3 / P
    cw4 = (UW - 3 * GAP) / 4; ch4 = cw4 / P
    gh = (UH - GAP) / 2
    lh = hw / L
    return {
        "l_full": ("1 photo pleine page", "1 full-page photo", [(0, 0, UW, UH)]),
        "l_one_tall": ("1 photo verticale", "1 portrait photo", [((UW - bw) / 2, 0, bw, UH)]),
        "l_two_tall": ("2 photos verticales", "2 portrait photos", [(0, 0, hw, UH), (hw + GAP, 0, hw, UH)]),
        "l_two_wide": ("2 photos horizontales", "2 landscape photos", [(0, (UH - lh) / 2, hw, lh), (hw + GAP, (UH - lh) / 2, hw, lh)]),
        "l_tall_left_two": ("1 grande + 2 à droite", "1 large + 2 on the right", [(0, 0, bw, UH), (bw + GAP, 0, rw, rh), (bw + GAP, rh + GAP, rw, rh)]),
        "l_tall_right_two": ("1 grande + 2 à gauche", "1 large + 2 on the left", [(rw + GAP, 0, bw, UH), (0, 0, rw, rh), (0, rh + GAP, rw, rh)]),
        "l_three_tall": ("3 photos verticales", "3 portrait photos", [(i * (cw3 + GAP), (UH - ch3) / 2, cw3, ch3) for i in range(3)]),
        # 4 landscape phone photos (4:3) exactly: the block is centred.
        "l_grid": ("4 photos (grille)", "4 photos (grid)", [((UW - (2 * gh * L + GAP)) / 2 + c * (gh * L + GAP), r * (gh + GAP), gh * L, gh) for r in range(2) for c in range(2)]),
        "l_four_tall": ("4 photos verticales", "4 portrait photos", [(i * (cw4 + GAP), (UH - ch4) / 2, cw4, ch4) for i in range(4)]),
    }

def portrait(UW, UH):
    hh = (UH - GAP) / 2
    cw = (UW - GAP) / 2
    th = UW / L                      # wide photo on the full width
    bh = UH - th - GAP
    ph = cw / P
    lh3 = (UH - 2 * GAP) / 3; lw3 = lh3 * L
    lw4 = cw; lh4 = cw / L
    return {
        "p_full": ("1 photo pleine page", "1 full-page photo", [(0, 0, UW, UH)]),
        "p_one_wide": ("1 photo horizontale", "1 landscape photo", [(0, (UH - th) / 2, UW, th)]),
        "p_two_wide": ("2 photos horizontales", "2 landscape photos", [(0, 0, UW, hh), (0, hh + GAP, UW, hh)]),
        "p_two_tall": ("2 photos verticales", "2 portrait photos", [(0, (UH - ph) / 2, cw, ph), (cw + GAP, (UH - ph) / 2, cw, ph)]),
        "p_wide_top_two": ("1 grande + 2 en bas", "1 large + 2 below", [(0, 0, UW, th), (0, th + GAP, cw, bh), (cw + GAP, th + GAP, cw, bh)]),
        "p_wide_bottom_two": ("2 en haut + 1 grande", "2 above + 1 large", [(0, bh + GAP, UW, th), (0, 0, cw, bh), (cw + GAP, 0, cw, bh)]),
        "p_three_wide": ("3 photos horizontales", "3 landscape photos", [((UW - lw3) / 2, i * (lh3 + GAP), lw3, lh3) for i in range(3)]),
        # 4 portrait phone photos (3:4) exactly: the block is centred.
        "p_grid": ("4 photos (grille)", "4 photos (grid)", [(c * (cw + GAP), (UH - (2 * ph + GAP)) / 2 + r * (ph + GAP), cw, ph) for r in range(2) for c in range(2)]),
        "p_four_wide": ("4 photos horizontales", "4 landscape photos", [(c * (lw4 + GAP), (UH - 2 * lh4 - GAP) / 2 + r * (lh4 + GAP), lw4, lh4) for r in range(2) for c in range(2)]),
    }

data = {
    "_about": "Page templates for the automatic layout and the editor's layout menu, per page orientation. Generated: 12 mm margins and 6 mm gaps on an A4 page, stored as fractions of the page. Keep backend/app/services/layout_templates.json identical (a test checks it).",
    "max_crop": 0.10,
    "portrait": build(210.0, 297.0, portrait),
    "landscape": build(297.0, 210.0, landscape),
}
text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
for path in OUTPUTS:
    path.write_text(text, encoding="utf-8")
    print("written", path.relative_to(ROOT))
