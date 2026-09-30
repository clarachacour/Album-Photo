"""Images placed on a cover: a light copy for the screen (the full file
stays for printing), kept by the browser instead of downloaded each visit."""
from io import BytesIO

import pytest
from PIL import Image

from tests.test_api import _signup


@pytest.fixture()
def store(monkeypatch):
    from app.routers import covers
    from app.services import photos

    files = {}

    def get_object(path):
        if path not in files:
            raise FileNotFoundError(path)
        return files[path]

    def put_object(path, data, content_type=None):
        files[path] = (data, content_type)
        return {"path": path, "size": len(data)}

    for module in (covers, photos):
        monkeypatch.setattr(module, "get_object", get_object, raising=False)
    monkeypatch.setattr(photos, "put_object", put_object)
    return files


def _png(size, alpha=True):
    img = Image.new("RGBA" if alpha else "RGB", size, (200, 30, 30, 0) if alpha else (200, 30, 30))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _user_path(client, db, name):
    from app.core.auth import decode_token

    _, headers = _signup(client, db=db)
    user_id = decode_token(headers["Authorization"].split()[1])
    return f"everbook/users/{user_id}/albums/a1/cover-assets/{name}", headers


def test_a_big_cover_image_gets_a_light_copy_for_the_screen(client, db, store):
    path, headers = _user_path(client, db, "big.png")
    store[path] = (_png((3000, 2000)), "image/png")

    res = client.get("/api/cover-assets/image", params={"path": path, "variant": "medium"}, headers=headers)
    assert res.status_code == 200 and res.headers["content-type"] == "image/webp"
    assert "immutable" in res.headers["cache-control"]
    with Image.open(BytesIO(res.content)) as img:
        assert max(img.size) == 1200 and img.mode == "RGBA"  # transparency kept
    assert path.replace(".png", "_medium.webp") in store  # made once, kept

    # Printing still gets the full file.
    full = client.get("/api/cover-assets/image", params={"path": path, "variant": "original"}, headers=headers)
    with Image.open(BytesIO(full.content)) as img:
        assert img.size == (3000, 2000)


def test_a_small_cover_image_is_sent_as_is(client, db, store):
    path, headers = _user_path(client, db, "logo.png")
    store[path] = (_png((400, 200)), "image/png")
    res = client.get("/api/cover-assets/image", params={"path": path, "variant": "medium"}, headers=headers)
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert not any(k.endswith("_medium.webp") for k in store)
