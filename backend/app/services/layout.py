"""Page layouts: the title page and the automatic photo layout."""
import json
import math
import uuid
from pathlib import Path
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

# Page templates for each orientation (see layout_templates.json, made by
# scripts/gen_layout_templates.py — the editor's layout menu reads an
# identical copy): drawn for a portrait page and for a landscape page, with
# the same margins and gaps in millimetres on every side.
_TEMPLATES = json.loads((Path(__file__).with_name("layout_templates.json")).read_text(encoding="utf-8"))

# A photo may lose at most this much (fraction of its width or height) to
# fill its frame exactly; beyond that it keeps its own shape instead.
MAX_CROP = _TEMPLATES["max_crop"]
# A detected face is never cut into: its centre must stay at least this far
# (fraction of the photo) from an edge the frame cuts.
FACE_MARGIN = 0.12


def templates_for(orientation: str) -> Dict[str, dict]:
    return _TEMPLATES["landscape" if orientation == "landscape" else "portrait"]


TEMPLATE_PHOTO_COUNT = {name: len(t["slots"]) for o in ("portrait", "landscape") for name, t in _TEMPLATES[o].items()}
LAYOUT_PATTERN = list(TEMPLATE_PHOTO_COUNT)  # kept for callers that only use its length

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

def _photo_aspect(photo: dict) -> Optional[float]:
    w, h = photo.get("width"), photo.get("height")
    return w / h if w and h and h > 0 else None


def _face_safe(photo: dict, photo_aspect: float, frame_aspect: float) -> bool:
    """Whether filling a frame of frame_aspect leaves a detected face whole.
    The editor shows the photo like CSS object-position at the focal point
    (the face, see compute_face_focal_point): along the cut axis, a window
    of `kept` of the photo starting at focal * (1 - kept)."""
    if not photo.get("ai_has_face"):
        return True
    if photo_aspect >= frame_aspect:  # cut on the left and right
        kept, focal = frame_aspect / photo_aspect, photo.get("ai_focal_x", 0.5)
    else:  # cut at the top and bottom
        kept, focal = photo_aspect / frame_aspect, photo.get("ai_focal_y", 0.5)
    start = focal * (1 - kept)
    return focal - start >= FACE_MARGIN and (start + kept) - focal >= FACE_MARGIN


def frame_for(slot: dict, photo: dict, page_aspect_wh: float) -> dict:
    """The frame of a photo placed in `slot`: the whole slot when filling it
    costs at most MAX_CROP of the photo and never cuts into a detected face
    — so frames line up exactly with the template — otherwise the photo's
    own shape inside the slot (nothing cut). The photo itself is never
    altered: the editor can always show it whole again."""
    aspect = _photo_aspect(photo)
    if not aspect:
        return dict(slot)
    slot_aspect = (slot["w"] / slot["h"]) * page_aspect_wh
    cut = 1 - min(slot_aspect / aspect, aspect / slot_aspect)
    if cut <= MAX_CROP + 1e-9 and _face_safe(photo, aspect, slot_aspect):
        return {k: slot[k] for k in ("x", "y", "w", "h")}
    return fit_box_to_photo(slot, aspect, page_aspect_wh)


def deterministic_layout(photos: List[dict], orientation: str, pattern_start_idx: int = 0, content_pages_budget: Optional[int] = None) -> List[dict]:
    """Lays photos out on pages, in order, choosing for each page the
    template (for this page orientation, see layout_templates.json) that
    the next photos fill best: portrait photos go to tall frames, landscape
    ones to wide frames.

    For each page, every template that fits the remaining page budget is
    tried with the next few photos (the best-shaped ones are picked among
    them, see best_slot_assignment), and scored on:
    - how much of the page the photos actually cover (frames that would
      cut too much keep the photo's shape, leaving white around it);
    - how close its photo count is to what's needed to fill the pages left;
    - variety: a template used on the last pages scores lower.

    content_pages_budget, when given, is how many content pages (not
    counting the title page) this call must land on exactly — the page
    count the person chose and is being charged for. Template picks are
    capped page by page so there's always at least 1 photo left for every
    remaining page, guaranteeing the exact target whenever there are at
    least as many photos as pages to fill. pattern_start_idx is no longer
    used (kept for callers).
    """
    templates = templates_for(orientation)
    # A4/A5 share the same aspect ratio (ISO 216) — only orientation matters here.
    page_aspect_wh = 1.4142 if orientation == "landscape" else 0.7071

    def aspect_or_neutral(p: dict) -> float:
        return _photo_aspect(p) or 1.0  # unknown dimensions → no strong preference

    def best_slot_assignment(slots: List[dict], candidates: List[dict]) -> Dict[int, int]:
        """Greedily pairs each slot with whichever candidate photo's aspect
        ratio fits it best (smallest log-ratio mismatch), so a portrait photo
        doesn't end up in a wide frame (and vice versa). Photos with a
        detected face (ai_has_face, see curate_photos) get an extra cost
        penalty for a poorly-matching slot, since a bad match is what puts
        a face at risk."""
        FACE_MISMATCH_PENALTY = 2.5
        slot_aspects = [(s["w"] / s["h"]) * page_aspect_wh for s in slots]
        remaining_slots = list(range(len(slots)))
        remaining_candidates = list(range(len(candidates)))
        assignment: Dict[int, int] = {}
        while remaining_slots and remaining_candidates:
            best = None
            for si in remaining_slots:
                for ci in remaining_candidates:
                    cost = abs(math.log(slot_aspects[si] / aspect_or_neutral(candidates[ci])))
                    if candidates[ci].get("ai_has_face"):
                        cost *= FACE_MISMATCH_PENALTY
                    # Ties (identical shapes): keep the album's order.
                    cost += ci * 1e-6
                    if best is None or cost < best[0]:
                        best = (cost, si, ci)
            _, si, ci = best
            assignment[si] = ci
            remaining_slots.remove(si)
            remaining_candidates.remove(ci)
        return assignment

    COUNT_WEIGHT = 0.12  # per photo away from the count the remaining pages need
    REPEAT_PENALTY = {1: 0.30, 2: 0.15, 3: 0.08}  # template used 1, 2, 3 pages ago
    LOOKAHEAD_EXTRA = 4  # how many extra upcoming photos to consider per page, for better shape matches
    pages: List[dict] = []
    remaining = list(photos)
    while remaining:
        if content_pages_budget is not None:
            remaining_budget = content_pages_budget - len(pages)
            if remaining_budget <= 0:
                break  # target already reached — leftover photos stay unused rather than overshooting
            max_template_size = max(1, len(remaining) - (remaining_budget - 1))
            target_count = len(remaining) / remaining_budget
        else:
            max_template_size = 4
            target_count = 2.5

        best = None
        for name, template in templates.items():
            slots = template["slots"]
            if len(slots) > max_template_size or len(slots) > len(remaining):
                continue
            candidates = remaining[: len(slots) + LOOKAHEAD_EXTRA]
            assignment = best_slot_assignment(slots, candidates)
            frames = {si: frame_for(slots[si], candidates[ci], page_aspect_wh) for si, ci in assignment.items()}
            covered = sum(f["w"] * f["h"] for f in frames.values())
            recent = [p["layout"] for p in pages[-3:]][::-1]
            repeat = next((REPEAT_PENALTY[i + 1] for i, used in enumerate(recent) if used == name), 0)
            score = covered - COUNT_WEIGHT * abs(len(slots) - target_count) - repeat
            if best is None or score > best[0]:
                best = (score, name, slots, candidates, assignment, frames)
        if best is None:
            break
        _, layout_name, slots, candidates, assignment, frames = best

        items = []
        for slot_idx, slot in enumerate(slots):
            if slot_idx not in assignment:
                continue
            photo = candidates[assignment[slot_idx]]
            items.append({
                "id": str(uuid.uuid4()),
                "type": "photo",
                "photo_id": photo["id"],
                **frames[slot_idx],
                # The area this frame may use: when another photo is put in
                # it later (swap, replace), the frame is refitted inside
                # this slot rather than inside its current box.
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
    return pages
