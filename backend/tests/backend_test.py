"""
Backend tests for Album AI Studio.
Covers: health, cover-templates, auth (signup/login/me), albums CRUD,
photo upload, photo image serving, AI processing (poll), PDF export, delete.
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


# ---------- helpers ----------
def make_test_image(color=(200, 60, 80), size=(320, 240), text="Test") -> bytes:
    img = Image.new("RGB", size, color)
    d = ImageDraw.Draw(img)
    # add some visible content so AI has something to look at
    for i in range(0, size[0], 40):
        d.line([(i, 0), (i, size[1])], fill=(255, 255, 255), width=1)
    for j in range(0, size[1], 40):
        d.line([(0, j), (size[0], j)], fill=(255, 255, 255), width=1)
    d.rectangle([40, 40, size[0]-40, size[1]-40], outline=(255, 255, 0), width=4)
    d.text((60, 60), text, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    return s


@pytest.fixture(scope="session")
def user_creds():
    # unique per run to avoid collisions with previous data
    unique = uuid.uuid4().hex[:8]
    return {
        "name": "Test User",
        "email": f"TEST_{unique}@fable.studio",
        "password": "Test1234!",
    }


@pytest.fixture(scope="session")
def auth(session, user_creds):
    """Signup a new user for this test session."""
    r = session.post(f"{API}/auth/signup", json=user_creds, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"signup failed: {r.status_code} {r.text}")
    data = r.json()
    return {"token": data["token"], "user": data["user"], "creds": user_creds}


@pytest.fixture(scope="session")
def auth_headers(auth):
    return {"Authorization": f"Bearer {auth['token']}"}


# ---------- health ----------
class TestHealth:
    def test_root(self, session):
        r = session.get(f"{API}/", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"

    def test_cover_templates(self, session):
        r = session.get(f"{API}/cover-templates", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 6
        for t in data:
            for k in ("id", "name", "bg", "accent", "text", "illustration"):
                assert k in t, f"missing key {k} in template {t}"


# ---------- auth ----------
class TestAuth:
    def test_signup_and_me(self, auth, auth_headers, session):
        assert auth["user"]["email"].lower() == auth["creds"]["email"].lower()
        r = session.get(f"{API}/auth/me", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        u = r.json()
        assert u["email"].lower() == auth["creds"]["email"].lower()
        assert u["name"] == auth["creds"]["name"]

    def test_signup_duplicate_email(self, session, auth):
        r = session.post(f"{API}/auth/signup", json=auth["creds"], timeout=15)
        assert r.status_code == 400

    def test_login_success(self, session, auth):
        r = session.post(f"{API}/auth/login", json={
            "email": auth["creds"]["email"], "password": auth["creds"]["password"]
        }, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "token" in data and data["token"]
        assert data["user"]["email"].lower() == auth["creds"]["email"].lower()

    def test_login_wrong_password(self, session, auth):
        r = session.post(f"{API}/auth/login", json={
            "email": auth["creds"]["email"], "password": "WrongPass!"
        }, timeout=15)
        assert r.status_code == 401

    def test_me_without_token(self, session):
        r = session.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401


# ---------- albums CRUD, photos, AI, PDF ----------
class TestAlbumFlow:
    album_id = None

    def test_create_album(self, session, auth_headers):
        payload = {
            "title": "TEST Voyage",
            "country": "Islande",
            "year": 2025,
            "cover_template_id": "sand-forest",
            "size": "A5",
            "orientation": "landscape",
        }
        r = session.post(f"{API}/albums", json=payload, headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["title"] == "TEST Voyage"
        assert a["status"] == "draft"
        assert a["cover_template_id"] == "sand-forest"
        assert a["size"] == "A5"
        assert a["orientation"] == "landscape"
        assert "id" in a
        TestAlbumFlow.album_id = a["id"]

    def test_list_albums(self, session, auth_headers):
        r = session.get(f"{API}/albums", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        lst = r.json()
        assert isinstance(lst, list)
        assert any(a["id"] == TestAlbumFlow.album_id for a in lst)

    def test_get_album(self, session, auth_headers):
        r = session.get(f"{API}/albums/{TestAlbumFlow.album_id}", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        a = r.json()
        assert a["id"] == TestAlbumFlow.album_id
        assert "photos" in a
        assert isinstance(a["photos"], list)

    def test_patch_album(self, session, auth_headers):
        r = session.patch(
            f"{API}/albums/{TestAlbumFlow.album_id}",
            json={"title": "TEST Voyage Updated"},
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["title"] == "TEST Voyage Updated"
        # verify persistence
        r2 = session.get(f"{API}/albums/{TestAlbumFlow.album_id}", headers=auth_headers, timeout=15)
        assert r2.json()["title"] == "TEST Voyage Updated"

    def test_upload_photos(self, session, auth_headers, auth):
        files = [
            ("files", ("landscape.jpg", make_test_image((30, 90, 160), (400, 300), "Landscape"), "image/jpeg")),
            ("files", ("portrait.jpg", make_test_image((180, 60, 40), (300, 400), "Portrait"), "image/jpeg")),
            ("files", ("food.jpg", make_test_image((220, 160, 40), (350, 280), "Food"), "image/jpeg")),
        ]
        # requests requires no Content-Type header on multipart
        headers = {"Authorization": f"Bearer {auth['token']}"}
        r = session.post(
            f"{API}/albums/{TestAlbumFlow.album_id}/photos",
            files=files,
            headers=headers,
            timeout=120,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["uploaded"] == 3
        assert len(data["photos"]) == 3
        TestAlbumFlow.photo_id = data["photos"][0]["id"]

    def test_photo_image_with_query_auth(self, session, auth):
        pid = TestAlbumFlow.photo_id
        r = session.get(f"{API}/photos/{pid}/image", params={"auth": auth["token"]}, timeout=30)
        assert r.status_code == 200
        assert r.headers.get("Content-Type", "").startswith("image/")
        assert len(r.content) > 100

    def test_photo_image_without_auth(self, session):
        pid = TestAlbumFlow.photo_id
        r = session.get(f"{API}/photos/{pid}/image", timeout=15)
        assert r.status_code == 401

    def test_process_and_poll_status(self, session, auth_headers):
        r = session.post(
            f"{API}/albums/{TestAlbumFlow.album_id}/process",
            headers=auth_headers, timeout=30,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "processing"

        # Poll status for up to ~120s
        deadline = time.time() + 150
        final_status = None
        while time.time() < deadline:
            time.sleep(4)
            rs = session.get(
                f"{API}/albums/{TestAlbumFlow.album_id}/status",
                headers=auth_headers, timeout=15,
            )
            assert rs.status_code == 200
            st = rs.json()["status"]
            if st in ("ready", "error"):
                final_status = st
                break
        assert final_status == "ready", f"final status was {final_status}"

        # Album should have pages populated
        ra = session.get(f"{API}/albums/{TestAlbumFlow.album_id}", headers=auth_headers, timeout=15)
        assert ra.status_code == 200
        alb = ra.json()
        assert isinstance(alb.get("pages"), list)
        assert len(alb["pages"]) >= 1
        first_page = alb["pages"][0]
        assert "items" in first_page
        assert any(it.get("type") == "photo" and "photo_id" in it for it in first_page["items"])

    def test_export_pdf(self, session, auth):
        r = session.get(
            f"{API}/albums/{TestAlbumFlow.album_id}/export",
            params={"auth": auth["token"]},
            timeout=60,
        )
        assert r.status_code == 200
        assert r.headers.get("Content-Type", "").startswith("application/pdf")
        assert r.content.startswith(b"%PDF"), "response body is not a PDF"
        assert len(r.content) > 1000

    def test_export_pdf_without_auth(self, session):
        r = session.get(f"{API}/albums/{TestAlbumFlow.album_id}/export", timeout=15)
        assert r.status_code == 401

    def test_delete_album(self, session, auth_headers):
        r = session.delete(f"{API}/albums/{TestAlbumFlow.album_id}", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("deleted") == 1
        # verify gone
        r2 = session.get(f"{API}/albums/{TestAlbumFlow.album_id}", headers=auth_headers, timeout=15)
        assert r2.status_code == 404


# ---------- non-image file skipping ----------
class TestNonImageSkipped:
    def test_upload_skips_non_image(self, session, auth_headers, auth):
        # Create a fresh album
        r = session.post(f"{API}/albums", json={"title": "TEST NonImg"}, headers=auth_headers, timeout=15)
        assert r.status_code == 200
        aid = r.json()["id"]
        files = [
            ("files", ("note.txt", b"just some text", "text/plain")),
            ("files", ("ok.jpg", make_test_image(), "image/jpeg")),
        ]
        headers = {"Authorization": f"Bearer {auth['token']}"}
        r2 = session.post(f"{API}/albums/{aid}/photos", files=files, headers=headers, timeout=60)
        assert r2.status_code == 200
        assert r2.json()["uploaded"] == 1
        # cleanup
        session.delete(f"{API}/albums/{aid}", headers=auth_headers, timeout=15)
