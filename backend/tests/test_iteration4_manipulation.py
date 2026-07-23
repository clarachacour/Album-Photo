"""
Backend tests specifically for Iteration 4:
- PATCH /api/albums/{id} accepts `cover` dict and persists it
- PATCH /api/albums/{id} accepts pages[].items[] with font_weight / font_style
- PDF export still returns 200 application/pdf after cover.bg_color, title_x/y, extra_items (text+shape), and text item font_weight=bold
"""
import io
import os
import time
import uuid

import pytest
import requests
from PIL import Image, ImageDraw

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://album-ai-studio-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def make_test_image(color=(30, 90, 160), size=(400, 300), text="Test") -> bytes:
    img = Image.new("RGB", size, color)
    d = ImageDraw.Draw(img)
    for i in range(0, size[0], 40):
        d.line([(i, 0), (i, size[1])], fill=(255, 255, 255), width=1)
    d.rectangle([40, 40, size[0]-40, size[1]-40], outline=(255, 255, 0), width=4)
    d.text((60, 60), text, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


@pytest.fixture(scope="module")
def session():
    return requests.Session()


@pytest.fixture(scope="module")
def user(session):
    creds = {
        "name": "Iter4 Tester",
        "email": f"TEST_iter4_{uuid.uuid4().hex[:8]}@fable.studio",
        "password": "Test1234!",
    }
    r = session.post(f"{API}/auth/signup", json=creds, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    return {"token": data["token"], "creds": creds, "headers": {"Authorization": f"Bearer {data['token']}"}}


@pytest.fixture(scope="module")
def album_with_content(session, user):
    # Create album
    r = session.post(f"{API}/albums", json={
        "title": "TEST Iter4",
        "country": "Portugal",
        "year": 2026,
        "cover_template_id": "teal-coral",
        "size": "A4",
        "orientation": "portrait",
    }, headers=user["headers"], timeout=15)
    assert r.status_code == 200
    aid = r.json()["id"]

    # Upload 2 photos
    files = [
        ("files", ("a.jpg", make_test_image((30, 90, 160), (400, 300), "A"), "image/jpeg")),
        ("files", ("b.jpg", make_test_image((180, 60, 40), (300, 400), "B"), "image/jpeg")),
    ]
    r2 = session.post(f"{API}/albums/{aid}/photos", files=files,
                      headers={"Authorization": f"Bearer {user['token']}"}, timeout=60)
    assert r2.status_code == 200

    # AI process
    r3 = session.post(f"{API}/albums/{aid}/process", headers=user["headers"], timeout=30)
    assert r3.status_code == 200

    # Poll
    deadline = time.time() + 180
    final = None
    while time.time() < deadline:
        time.sleep(4)
        try:
            rs = session.get(f"{API}/albums/{aid}/status", headers=user["headers"], timeout=30)
            st = rs.json().get("status")
            if st in ("ready", "error"):
                final = st
                break
        except requests.exceptions.RequestException:
            continue
    assert final == "ready"

    yield aid
    # cleanup
    try:
        session.delete(f"{API}/albums/{aid}", headers=user["headers"], timeout=15)
    except Exception:
        pass


class TestCoverPersistence:
    def test_patch_cover_field_persists(self, session, user, album_with_content):
        aid = album_with_content
        cover_payload = {
            "bg_color": "#123456",
            "accent_color": "#abcdef",
            "text_color": "#000000",
            "title_x": 0.2,
            "title_y": 0.15,
            "title_font_size": 60,
            "title_font_weight": "bold",
            "extra_items": [
                {
                    "id": "x1",
                    "type": "text",
                    "x": 0.1, "y": 0.5, "w": 0.5, "h": 0.08,
                    "content": "Hello",
                    "font_size": 24,
                    "color": "#ffffff",
                    "font_weight": "bold",
                },
                {
                    "id": "s1",
                    "type": "shape",
                    "shape_type": "rect",
                    "x": 0.3, "y": 0.7, "w": 0.2, "h": 0.1,
                    "fill_color": "#ff00ff",
                },
            ],
        }
        r = session.patch(f"{API}/albums/{aid}", json={"cover": cover_payload},
                          headers=user["headers"], timeout=15)
        assert r.status_code == 200, r.text

        # verify via GET
        r2 = session.get(f"{API}/albums/{aid}", headers=user["headers"], timeout=15)
        assert r2.status_code == 200
        got_cover = r2.json().get("cover")
        assert got_cover is not None
        assert got_cover["bg_color"] == "#123456"
        assert got_cover["accent_color"] == "#abcdef"
        assert got_cover["text_color"] == "#000000"
        assert got_cover["title_x"] == 0.2
        assert got_cover["title_y"] == 0.15
        assert got_cover["title_font_size"] == 60
        assert got_cover["title_font_weight"] == "bold"
        extras = got_cover.get("extra_items") or []
        assert len(extras) == 2
        text_item = next((x for x in extras if x["type"] == "text"), None)
        assert text_item is not None
        assert text_item["content"] == "Hello"
        assert text_item["font_weight"] == "bold"
        shape_item = next((x for x in extras if x["type"] == "shape"), None)
        assert shape_item is not None
        assert shape_item["shape_type"] == "rect"
        assert shape_item["fill_color"] == "#ff00ff"


class TestPageItemFontWeightStyle:
    def test_patch_page_text_item_font_weight_and_style_persist(self, session, user, album_with_content):
        aid = album_with_content
        # Get album
        r = session.get(f"{API}/albums/{aid}", headers=user["headers"], timeout=15)
        alb = r.json()
        pages = alb.get("pages") or []
        assert len(pages) >= 1
        # Add a text item on first page with bold + italic
        new_text = {
            "id": f"text-{uuid.uuid4().hex[:8]}",
            "type": "text",
            "content": "Bold Italic",
            "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.08,
            "font": "'Manrope', sans-serif",
            "color": "#1A1A17",
            "font_size": 20,
            "font_weight": "bold",
            "font_style": "italic",
        }
        pages[0]["items"] = list(pages[0]["items"]) + [new_text]

        r2 = session.patch(f"{API}/albums/{aid}", json={"pages": pages},
                           headers=user["headers"], timeout=15)
        assert r2.status_code == 200

        # Verify persistence
        r3 = session.get(f"{API}/albums/{aid}", headers=user["headers"], timeout=15)
        got_pages = r3.json().get("pages") or []
        found = None
        for pg in got_pages:
            for it in pg.get("items", []):
                if it.get("id") == new_text["id"]:
                    found = it
                    break
        assert found is not None
        assert found.get("font_weight") == "bold"
        assert found.get("font_style") == "italic"


class TestPdfExportWithCoverAndBoldText:
    def test_pdf_export_after_cover_and_bold_text_updates(self, session, user, album_with_content):
        aid = album_with_content
        # Set cover with bg_color, title_x/y, extra text+shape
        cover_payload = {
            "bg_color": "#402080",
            "title_x": 0.3,
            "title_y": 0.2,
            "title_font_weight": "bold",
            "extra_items": [
                {"id": "et1", "type": "text", "x": 0.1, "y": 0.6, "w": 0.5, "h": 0.08,
                 "content": "Extra Cover Text", "font_size": 24, "color": "#ffffff", "font_weight": "bold"},
                {"id": "es1", "type": "shape", "shape_type": "circle", "x": 0.6, "y": 0.7, "w": 0.15, "h": 0.15,
                 "fill_color": "#ff9900"},
            ],
        }
        # add a bold text item on page
        r = session.get(f"{API}/albums/{aid}", headers=user["headers"], timeout=15)
        pages = r.json().get("pages") or []
        pages[0]["items"] = list(pages[0]["items"]) + [{
            "id": f"boldtxt-{uuid.uuid4().hex[:6]}",
            "type": "text", "content": "Bold Line", "x": 0.1, "y": 0.8,
            "w": 0.6, "h": 0.08, "font_size": 22, "color": "#111111",
            "font_weight": "bold", "font_style": "normal",
        }]

        r2 = session.patch(f"{API}/albums/{aid}", json={"cover": cover_payload, "pages": pages},
                           headers=user["headers"], timeout=15)
        assert r2.status_code == 200

        # Export
        r3 = session.get(f"{API}/albums/{aid}/export",
                         params={"auth": user["token"]}, timeout=90)
        assert r3.status_code == 200, r3.text[:300]
        assert r3.headers.get("Content-Type", "").startswith("application/pdf")
        assert r3.content.startswith(b"%PDF")
        assert len(r3.content) > 1000
