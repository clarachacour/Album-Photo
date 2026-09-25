"""Step 4: order PDFs through the Cloud Tasks queue, and the print page's
album-only key."""
import asyncio

import pytest

from tests.test_api import _signup

ADDRESS = {"full_name": "A", "phone": "1", "street": "S", "city": "C"}


def _album_with_pages(client, db, headers, pages=3):
    album_id = client.post("/api/albums", json={"title": "Trip"}, headers=headers).json()["id"]
    asyncio.run(db.albums.update_one({"id": album_id}, {"$set": {"pages": [{"id": str(i), "items": []} for i in range(pages)], "status": "ready"}}))
    return album_id


def _user_id(db, headers):
    from app.core.auth import decode_token

    return decode_token(headers["Authorization"].split()[1])


# ---------- Print key ----------
def test_print_key_opens_only_its_album(client, db):
    from app.core.auth import create_print_token

    _, headers = _signup(client, db=db)
    user_id = _user_id(db, headers)
    album_id = _album_with_pages(client, db, headers)
    other_album = _album_with_pages(client, db, headers)
    asyncio.run(db.photos.insert_many([
        {"id": "ph-in", "album_id": album_id, "user_id": user_id, "is_deleted": False, "storage_path": "x"},
        {"id": "ph-out", "album_id": other_album, "user_id": user_id, "is_deleted": False, "storage_path": "y"},
    ]))
    key = create_print_token(user_id, album_id)
    auth = {"Authorization": f"Bearer {key}"}

    assert client.get(f"/api/albums/{album_id}", headers=auth).status_code == 200
    assert client.get(f"/api/albums/{other_album}", headers=auth).status_code == 401
    # Not a login: no other endpoint accepts it.
    assert client.get("/api/albums", headers=auth).status_code == 401
    assert client.get("/api/auth/me", headers=auth).status_code == 401
    assert client.get(f"/api/photos/ph-out/image?auth={key}").status_code == 404
    assert client.get(f"/api/albums/{other_album}/cover-image?auth={key}").status_code == 401
    # The customer's own login still works everywhere.
    assert client.get(f"/api/albums/{other_album}", headers=headers).status_code == 200


def test_print_key_expires():
    import jwt

    from app.config import JWT_ALGORITHM, JWT_SECRET
    from app.core.auth import PRINT_TOKEN_HOURS, create_print_token

    payload = jwt.decode(create_print_token("u", "a"), JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert payload["exp"] - payload["iat"] == PRINT_TOKEN_HOURS * 3600


# ---------- Queue ----------
@pytest.fixture()
def queue(monkeypatch):
    """Cloud Tasks configured, with the Google call replaced by a recorder."""
    from app.services import orders as order_service

    queued, generated = [], []

    async def fake_generate(order_id, album_id, user_id, final_attempt=True):
        generated.append(order_id)
        return True

    monkeypatch.setattr(order_service, "pdf_tasks_enabled", lambda: True)
    monkeypatch.setattr(order_service, "enqueue_order_pdf", queued.append)
    monkeypatch.setattr(order_service, "generate_order_pdf", fake_generate)
    monkeypatch.setattr("app.routers.orders.send_order_confirmation_email", lambda *a, **k: None)
    return queued, generated


def test_order_is_confirmed_at_once_and_pdf_queued(client, db, queue):
    queued, generated = queue
    _, headers = _signup(client, db=db)
    album_id = _album_with_pages(client, db, headers)
    res = client.post("/api/orders", json={"album_id": album_id, "shipping_address": ADDRESS}, headers=headers)
    assert res.status_code == 200, res.text
    order = res.json()
    assert queued == [order["id"]]
    assert generated == []  # not generated during the customer's request
    assert order["pdf_queued_at"]


def test_unreachable_queue_falls_back_to_generating_now(client, db, queue, monkeypatch):
    from app.services import orders as order_service

    _, generated = queue

    def broken(order_id):
        raise RuntimeError("queue down")

    monkeypatch.setattr(order_service, "enqueue_order_pdf", broken)
    _, headers = _signup(client, db=db)
    album_id = _album_with_pages(client, db, headers)
    res = client.post("/api/orders", json={"album_id": album_id, "shipping_address": ADDRESS}, headers=headers)
    assert res.status_code == 200, res.text
    assert generated == [res.json()["id"]]


# ---------- Endpoint called by the queue ----------
SECRET = "test-cleanup-secret"


@pytest.fixture()
def task_endpoint(monkeypatch, db):
    from app.routers import internal

    monkeypatch.setattr(internal, "CLEANUP_SECRET", SECRET)
    monkeypatch.setattr(internal, "PDF_TASK_MAX_ATTEMPTS", 3)
    calls = []
    outcome = {"ok": False}

    async def fake_generate(order_id, album_id, user_id, final_attempt=True):
        calls.append(final_attempt)
        return outcome["ok"]

    monkeypatch.setattr(internal, "generate_order_pdf", fake_generate)
    order_id = f"order-{len(asyncio.run(db.orders.find({}).to_list(1000)))}"
    asyncio.run(db.orders.insert_one({"id": order_id, "album_id": f"album-{order_id}", "user_id": "u", "pdf_ready": False}))
    return f"/api/internal/orders/{order_id}/generate-pdf", calls, outcome, order_id


def test_task_endpoint_needs_the_secret(client, task_endpoint):
    url, calls, _, _ = task_endpoint
    assert client.post(url).status_code == 401
    assert client.post(url, headers={"X-Cleanup-Secret": "wrong"}).status_code == 401
    assert calls == []


def test_failed_attempt_is_retried_and_only_the_last_one_is_final(client, task_endpoint):
    url, calls, _, _ = task_endpoint
    first = client.post(url, headers={"X-Cleanup-Secret": SECRET, "X-CloudTasks-TaskRetryCount": "0"})
    assert first.status_code == 500  # the queue will try again
    last = client.post(url, headers={"X-Cleanup-Secret": SECRET, "X-CloudTasks-TaskRetryCount": "2"})
    assert last.status_code == 200  # nothing left to retry: the admin was emailed
    assert calls == [False, True]


def test_ready_pdf_is_not_generated_again(client, db, task_endpoint):
    url, calls, _, order_id = task_endpoint
    asyncio.run(db.orders.update_one({"id": order_id}, {"$set": {"pdf_ready": True}}))
    res = client.post(url, headers={"X-Cleanup-Secret": SECRET})
    assert res.status_code == 200 and res.json()["skipped"]
    assert calls == []


def test_attempt_waits_while_another_is_rendering(client, db, task_endpoint):
    from datetime import datetime, timezone

    url, calls, _, order_id = task_endpoint
    asyncio.run(db.pdf_generation_slots.insert_one({"order_id": order_id, "started_at": datetime.now(timezone.utc).isoformat()}))
    assert client.post(url, headers={"X-Cleanup-Secret": SECRET}).status_code == 409
    assert calls == []
