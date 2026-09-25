"""Page layouts: the title page and the automatic photo layout."""
import uuid
from typing import Dict, List, Optional


def make_title_page(title: str, lang: str = "en") -> dict:
    """The first interior page every album starts with — right after the
    cover, always right-hand (the left page of that spread stays blank), and
    pre-filled with the album's title plus a friendly hint. The user is free
    to add or remove anything on it afterward, hint included.

    lang picks which language that hint is written in — it's the site's
    current UI language at the moment of creation (see AlbumCreate.lang),
    not something stored or revisited afterward; the person can freely
    edit or delete the hint regardless. Anything other than "fr" falls
    back to English, matching the frontend's own fallbackLng."""
    hint_text = (
        "Voici votre première page — faites-la vôtre. Ajoutez des photos, du texte, ou tout ce que vous voulez."
        if lang == "fr"
        else "This is your first page — make it yours. Add photos, text, or anything else you'd like."
    )
    return {
        "id": str(uuid.uuid4()),
        "layout": "title_page",
        "items": [
            {
                "id": str(uuid.uuid4()),
                "type": "text",
                "content": title or "Untitled",
                "x": 0.1,
                "y": 0.38,
                "w": 0.8,
                "h": 0.16,
                "font": "'Baloo 2', sans-serif",
                "font_weight": "800",
                "font_size": 36,
                "color": "#1A1A17",
            },
            {
                "id": str(uuid.uuid4()),
                "type": "text",
                "content": hint_text,
                "x": 0.15,
                "y": 0.56,
                "w": 0.7,
                "h": 0.12,
                "font": "'Manrope', sans-serif",
                "font_weight": "400",
                "font_style": "italic",
                "font_size": 14,
                "color": "#8A8A82",
                "text_align": "center",
            },
        ],
    }

LAYOUT_PATTERN = ["single_full", "dual_vertical", "hero_strip", "single_centered", "quad_grid", "triptych", "dual_horizontal"]

TEMPLATE_PHOTO_COUNT = {
    "single_full": 1, "single_centered": 1,
    "dual_vertical": 2, "dual_horizontal": 2,
    "triptych": 3,
    "quad_grid": 4, "hero_strip": 4,
}

def fit_box_to_photo(slot: dict, photo_aspect: Optional[float], page_aspect_wh: float) -> dict:
    """Largest box with the photo's own proportions that fits inside `slot`,
    centered in it. Photos are never cropped by the layout: the frame takes
    the photo's shape instead of the photo being cut to the frame's shape.

    Coordinates are fractions of the page (0-1), so a box's real aspect
    ratio is (w / h) * page_aspect_wh. Unknown photo size → slot unchanged.
    """
    if not photo_aspect or photo_aspect <= 0:
        return dict(slot)
    slot_aspect = (slot["w"] / slot["h"]) * page_aspect_wh
    if photo_aspect >= slot_aspect:
        # Wider than the slot: full slot width, less height.
        w = slot["w"]
        h = w * page_aspect_wh / photo_aspect
    else:
        # Taller than the slot: full slot height, less width.
        h = slot["h"]
        w = h * photo_aspect / page_aspect_wh
    return {
        "x": slot["x"] + (slot["w"] - w) / 2,
        "y": slot["y"] + (slot["h"] - h) / 2,
        "w": w,
        "h": h,
    }

def deterministic_layout(photos: List[dict], orientation: str, pattern_start_idx: int = 0, content_pages_budget: Optional[int] = None) -> List[dict]:
    """Distribute photos across pages with varied layouts.
    Returns a list of pages (each with items containing photo refs and positions in normalized 0-1 coordinates).

    content_pages_budget, when given, is how many content pages (not
    counting the title page) this call must land on exactly — the page
    count the person chose and is being charged for. Without it, the
    layout just cycles LAYOUT_PATTERN and produces however many pages the
    photos happen to fill at that pattern's ~2.4 photos/page average,
    which routinely undershot a much larger chosen page count with no way
    to recover afterwards. With a budget, template picks are capped page
    by page so there's always at least 1 photo left for every remaining
    page, guaranteeing the exact target whenever there are at least as
    many photos as pages to fill.
    """
    M = 0.05  # Marge globale de 5%
    usable = 1.0 - (2 * M)  # Espace utile de 0.9 (90% de la page)

    layouts = {
        "single_full": [
            {"x": M, "y": M, "w": usable, "h": usable}
        ],
        "single_centered": [
            {"x": 0.15, "y": 0.15, "w": 0.7, "h": 0.7}
        ],
        "dual_horizontal": [
            {"x": M, "y": M, "w": usable, "h": (usable - 0.04) / 2},
            {"x": M, "y": M + (usable - 0.04) / 2 + 0.04, "w": usable, "h": (usable - 0.04) / 2},
        ],
        "dual_vertical": [
            {"x": M, "y": M, "w": (usable - 0.04) / 2, "h": usable},
            {"x": M + (usable - 0.04) / 2 + 0.04, "y": M, "w": (usable - 0.04) / 2, "h": usable},
        ],
        "triptych": [
            {"x": M, "y": M, "w": usable * 0.58, "h": usable},
            {"x": M + usable * 0.58 + 0.03, "y": M, "w": usable * 0.39, "h": (usable - 0.03) / 2},
            {"x": M + usable * 0.58 + 0.03, "y": M + (usable - 0.03) / 2 + 0.03, "w": usable * 0.39, "h": (usable - 0.03) / 2},
        ],
        "quad_grid": [
            {"x": M, "y": M, "w": (usable - 0.03) / 2, "h": (usable - 0.03) / 2},
            {"x": M + (usable - 0.03) / 2 + 0.03, "y": M, "w": (usable - 0.03) / 2, "h": (usable - 0.03) / 2},
            {"x": M, "y": M + (usable - 0.03) / 2 + 0.03, "w": (usable - 0.03) / 2, "h": (usable - 0.03) / 2},
            {"x": M + (usable - 0.03) / 2 + 0.03, "y": M + (usable - 0.03) / 2 + 0.03, "w": (usable - 0.03) / 2, "h": (usable - 0.03) / 2},
        ],
        "hero_strip": [
            {"x": M, "y": M, "w": usable, "h": usable * 0.62},
            {"x": M, "y": M + usable * 0.62 + 0.03, "w": (usable - 0.06) / 3, "h": usable * 0.35},
            {"x": M + (usable - 0.06) / 3 + 0.03, "y": M + usable * 0.62 + 0.03, "w": (usable - 0.06) / 3, "h": usable * 0.35},
            {"x": M + 2 * ((usable - 0.06) / 3 + 0.03), "y": M + usable * 0.62 + 0.03, "w": (usable - 0.06) / 3, "h": usable * 0.35},
        ],
    }

    # Alternate layouts to create diversity
    pattern = LAYOUT_PATTERN

    # A4/A5 share the same aspect ratio (ISO 216) — only orientation matters here.
    page_aspect_wh = 1.4142 if orientation == "landscape" else 0.7071

    def photo_aspect(p: dict) -> float:
        w, h = p.get("width"), p.get("height")
        if w and h and h > 0:
            return w / h
        return 1.0  # unknown dimensions → treat as neutral, no strong preference

    def best_slot_assignment(slots: List[dict], candidates: List[dict]) -> Dict[int, int]:
        """Greedily pairs each slot with whichever candidate photo's aspect
        ratio fits it best (smallest log-ratio mismatch), so a portrait photo
        doesn't end up forced into a wide landscape slot (and vice versa) —
        that mismatch is what causes heavy, awkward cropping. Photos with a
        detected face (ai_has_face, see curate_photos) get an extra cost
        penalty for a poorly-matching slot — the crop can be centered on the
        face (see compute_face_focal_point), but that only helps if the
        slot's own shape isn't wildly different from the photo's to begin
        with; the slot CHOICE, not just where the crop is centered within
        it, is what determines how much of the photo (and how much risk to
        the face) has to be cropped away. This can mean a face photo "loses"
        the closest-matching slot to a non-face photo that matched it even
        better — an intentional trade, since the non-face photo has nothing
        at risk from a so-so match."""
        import math
        FACE_MISMATCH_PENALTY = 2.5
        slot_aspects = [(s["w"] / s["h"]) * page_aspect_wh for s in slots]
        remaining_slots = list(range(len(slots)))
        remaining_candidates = list(range(len(candidates)))
        assignment: Dict[int, int] = {}
        while remaining_slots and remaining_candidates:
            best = None
            for si in remaining_slots:
                for ci in remaining_candidates:
                    cost = abs(math.log(slot_aspects[si] / photo_aspect(candidates[ci])))
                    if candidates[ci].get("ai_has_face"):
                        cost *= FACE_MISMATCH_PENALTY
                    if best is None or cost < best[0]:
                        best = (cost, si, ci)
            _, si, ci = best
            assignment[si] = ci
            remaining_slots.remove(si)
            remaining_candidates.remove(ci)
        return assignment

    LOOKAHEAD_EXTRA = 4  # how many extra upcoming photos to consider per page, for better shape matches
    pages = []
    remaining = list(photos)
    p_idx = pattern_start_idx
    while remaining:
        if content_pages_budget is not None:
            remaining_budget = content_pages_budget - len(pages)
            if remaining_budget <= 0:
                break  # target already reached — leftover photos stay unused rather than overshooting
            max_template_size = max(1, len(remaining) - (remaining_budget - 1))
        else:
            max_template_size = 4

        tries = 0
        while TEMPLATE_PHOTO_COUNT[pattern[p_idx % len(pattern)]] > max_template_size and tries < len(pattern):
            p_idx += 1
            tries += 1
        layout_name = pattern[p_idx % len(pattern)]
        if TEMPLATE_PHOTO_COUNT[layout_name] > max_template_size:
            layout_name = "single_full"  # always fits — guarantees forward progress even at a 1-photo-per-page budget

        slots = layouts[layout_name]
        window_size = min(len(remaining), len(slots) + LOOKAHEAD_EXTRA)
        candidates = remaining[:window_size]
        assignment = best_slot_assignment(slots, candidates)
        if not assignment:
            break
        items = []
        for slot_idx, slot in enumerate(slots):
            if slot_idx not in assignment:
                continue
            photo = candidates[assignment[slot_idx]]
            box = fit_box_to_photo(slot, photo_aspect(photo) if photo.get("width") else None, page_aspect_wh)
            items.append({
                "id": str(uuid.uuid4()),
                "type": "photo",
                "photo_id": photo["id"],
                **box,
                # The area this frame may use: when another photo is put in
                # it later (swap, replace), the frame is refitted inside
                # this slot rather than inside its current, shrunken box.
                "slot": {k: slot[k] for k in ("x", "y", "w", "h")},
                "focal_x": photo.get("ai_focal_x", 0.5),
                "focal_y": photo.get("ai_focal_y", 0.5),
            })
        pages.append({
            "id": str(uuid.uuid4()),
            "layout": layout_name,
            "items": items,
        })
        # Drop the photos that were used (order-preserving) — the rest, including
        # any lookahead candidates that weren't picked this time, stay in the
        # queue for the next page in their original relative order.
        used_ids = {candidates[ci]["id"] for ci in assignment.values()}
        remaining = [p for p in remaining if p["id"] not in used_ids]
        p_idx += 1
    return pages
