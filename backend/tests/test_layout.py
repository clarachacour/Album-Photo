"""The automatic layout crops a photo by at most MAX_CROP (10 %), never into a
detected face, uses templates made for the page orientation, and keeps every
frame inside its slot."""
import json
import random
from pathlib import Path

import pytest

from app.services.layout import MAX_CROP, deterministic_layout, fit_box_to_photo, frame_for, templates_for

PAGE_ASPECT = {"portrait": 0.7071, "landscape": 1.4142}


def box_aspect(box, orientation):
    return box["w"] / box["h"] * PAGE_ASPECT[orientation]


@pytest.mark.parametrize("photo_aspect", [0.5, 0.75, 1.0, 4 / 3, 16 / 9, 3.0])
def test_fitted_box_has_the_photo_proportions_and_stays_in_the_slot(photo_aspect):
    slot = {"x": 0.05, "y": 0.05, "w": 0.43, "h": 0.9}
    box = fit_box_to_photo(slot, photo_aspect, PAGE_ASPECT["portrait"])
    assert box_aspect(box, "portrait") == pytest.approx(photo_aspect)
    assert box["x"] >= slot["x"] - 1e-9 and box["y"] >= slot["y"] - 1e-9
    assert box["x"] + box["w"] <= slot["x"] + slot["w"] + 1e-9
    assert box["y"] + box["h"] <= slot["y"] + slot["h"] + 1e-9
    # As large as possible: touches the slot on two opposite sides.
    assert box["w"] == pytest.approx(slot["w"]) or box["h"] == pytest.approx(slot["h"])


def test_unknown_photo_size_keeps_the_slot():
    slot = {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}
    assert fit_box_to_photo(slot, None, 0.7071) == slot


def cut(item, photo, orientation):
    """Fraction of the photo the frame cuts off (0 = shown whole)."""
    a, f = photo["width"] / photo["height"], box_aspect(item, orientation)
    return 1 - min(a / f, f / a)


@pytest.mark.parametrize("orientation", ["portrait", "landscape"])
def test_whole_album_layout_crops_at_most_10_percent(orientation):
    rnd = random.Random(7)
    sizes = [(4032, 3024), (3024, 4032), (1920, 1080), (1080, 1920), (2000, 2000), (6000, 2000)]
    photos = [{"id": f"p{i}", "width": w, "height": h} for i, (w, h) in enumerate(rnd.choice(sizes) for _ in range(60))]
    by_id = {p["id"]: p for p in photos}

    pages = deterministic_layout(photos, orientation, content_pages_budget=24)

    assert len(pages) == 24
    for page in pages:
        assert page["layout"] in templates_for(orientation)  # a template made for this orientation
        for item in page["items"]:
            assert cut(item, by_id[item["photo_id"]], orientation) <= MAX_CROP + 1e-6
            slot = item["slot"]
            assert slot["x"] - 1e-9 <= item["x"] and item["x"] + item["w"] <= slot["x"] + slot["w"] + 1e-9
            assert slot["y"] - 1e-9 <= item["y"] and item["y"] + item["h"] <= slot["y"] + slot["h"] + 1e-9


def test_a_photo_that_would_lose_more_than_10_percent_keeps_its_shape():
    slot = {"x": 0.05, "y": 0.05, "w": 0.9, "h": 0.4}  # very wide on a portrait page
    frame = frame_for(slot, {"width": 3000, "height": 4000}, PAGE_ASPECT["portrait"])
    assert box_aspect(frame, "portrait") == pytest.approx(0.75)


def test_a_close_shape_fills_its_frame_exactly():
    slot = {"x": 0.05, "y": 0.05, "w": 0.9, "h": 0.9}  # 0.707 on a portrait page; a 3:4 photo loses ~6 %
    assert frame_for(slot, {"width": 3000, "height": 4000}, PAGE_ASPECT["portrait"]) == slot


def test_a_face_near_the_edge_is_never_cut():
    slot = {"x": 0.05, "y": 0.05, "w": 0.9, "h": 0.9}
    # The frame (0.707) is narrower than the photo (0.75): it would cut the
    # left and right edges, and the face is against the left one.
    photo = {"width": 3000, "height": 4000, "ai_has_face": True, "ai_focal_x": 0.06, "ai_focal_y": 0.5}
    frame = frame_for(slot, photo, PAGE_ASPECT["portrait"])
    assert box_aspect(frame, "portrait") == pytest.approx(0.75)  # shown whole
    centred_face = {**photo, "ai_focal_x": 0.5}
    assert frame_for(slot, centred_face, PAGE_ASPECT["portrait"]) == slot


def test_landscape_pages_suit_portrait_phone_photos():
    """The original problem: portrait photos on a landscape album ended up
    small in wide frames. Now they fill most of the page."""
    rnd = random.Random(3)
    photos = [{"id": f"p{i}", "width": 3000, "height": 4000} if rnd.random() < 0.65 else {"id": f"p{i}", "width": 4000, "height": 3000} for i in range(48)]
    pages = deterministic_layout(photos, "landscape", content_pages_budget=20)
    coverage = [sum(it["w"] * it["h"] for it in p["items"]) for p in pages]
    assert sum(coverage) / len(coverage) > 0.6
    assert len({p["layout"] for p in pages}) >= 4  # varied pages


def test_the_editor_uses_the_same_templates():
    root = Path(__file__).resolve().parents[2]
    backend = json.loads((root / "backend/app/services/layout_templates.json").read_text(encoding="utf-8"))
    frontend = json.loads((root / "frontend/src/lib/layoutTemplates.json").read_text(encoding="utf-8"))
    assert backend == frontend
