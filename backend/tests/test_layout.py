"""The automatic layout must never crop a photo: every frame takes the exact
proportions of its photo and stays inside the slot of the page template."""
import random

import pytest

from app.services.layout import deterministic_layout, fit_box_to_photo

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


@pytest.mark.parametrize("orientation", ["portrait", "landscape"])
def test_whole_album_layout_never_crops(orientation):
    rnd = random.Random(7)
    sizes = [(4032, 3024), (3024, 4032), (1920, 1080), (1080, 1920), (2000, 2000), (6000, 2000)]
    photos = [{"id": f"p{i}", "width": w, "height": h} for i, (w, h) in enumerate(rnd.choice(sizes) for _ in range(60))]
    by_id = {p["id"]: p for p in photos}

    pages = deterministic_layout(photos, orientation, content_pages_budget=24)

    assert len(pages) == 24
    for page in pages:
        for item in page["items"]:
            photo = by_id[item["photo_id"]]
            assert box_aspect(item, orientation) == pytest.approx(photo["width"] / photo["height"], rel=1e-6)
            slot = item["slot"]
            assert slot["x"] - 1e-9 <= item["x"] and item["x"] + item["w"] <= slot["x"] + slot["w"] + 1e-9
            assert slot["y"] - 1e-9 <= item["y"] and item["y"] + item["h"] <= slot["y"] + slot["h"] + 1e-9
