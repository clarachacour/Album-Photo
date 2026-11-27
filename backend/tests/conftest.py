import asyncio
import os
import random
import sys
from pathlib import Path

import pytest

# Let tests `import app...` no matter which folder pytest is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Settings the app requires at import time. setdefault: a real value in the
# environment wins, so these never override an actual configuration.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "album_tests")
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 40)
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")


@pytest.fixture(scope="session")
def app():
    """The real FastAPI app, wired to an in-memory fake MongoDB.

    The fake client has to be swapped in *before* app.db is imported,
    because app.db creates the connection at import time.
    """
    import motor.motor_asyncio
    from mongomock_motor import AsyncMongoMockClient

    class FakeClient(AsyncMongoMockClient):
        def __init__(self, *args, tlsCAFile=None, **kwargs):
            super().__init__(*args, **kwargs)

    motor.motor_asyncio.AsyncIOMotorClient = FakeClient
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    # `with` runs the app's startup/shutdown (index creation etc.).
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db(app):
    from app.db import db as database

    return database


@pytest.fixture()
def slow_curation(monkeypatch):
    """Curation that keeps every photo and takes a moment — long enough for
    batches processed side by side to overlap, as they do for real."""
    from app.services import processing

    async def curate(photos, existing_selected=None):
        await asyncio.sleep(random.uniform(0.01, 0.05))
        return list(photos), {"total_in": len(photos)}

    monkeypatch.setattr(processing, "curate_photos", curate)

    # Real database calls take a few milliseconds: a moment between reading
    # the pages and saving them, where another batch can slip in. The
    # in-memory test database answers instantly, so it's made explicit here.
    real_trim = processing.trim_pages_to_target

    async def trim(pages, target_pages):
        await asyncio.sleep(random.uniform(0.005, 0.02))
        return await real_trim(pages, target_pages)

    monkeypatch.setattr(processing, "trim_pages_to_target", trim)


@pytest.fixture(autouse=True)
def paid_albums(request, monkeypatch):
    """Tests check the real prices: the test week (FREE_TRIAL) is switched
    off for them, unless a test is marked free_trial."""
    if request.node.get_closest_marker("free_trial"):
        yield
        return
    request.getfixturevalue("app")
    from app.services import pricing

    monkeypatch.setattr(pricing, "FREE_TRIAL", False)
    yield


@pytest.fixture(autouse=True)
def cash_on_delivery(request, monkeypatch):
    """Cash on delivery is switched off on the site (payments.CASH_ON_DELIVERY),
    but orders placed on delivery before that are still collected by the
    courier: most tests still place their printed orders that way, with it
    on. The tests of the site as it is now switch it off themselves."""
    request.getfixturevalue("app")
    from app.services import payments

    monkeypatch.setattr(payments, "CASH_ON_DELIVERY", True)
    yield


@pytest.fixture()
def online_payment(app, monkeypatch):
    """Whish Pay / card switched on: the PDF and gift cards can be ordered
    (for now they're "coming soon", see services/payments.py)."""
    from app.services import payments, whish

    monkeypatch.setattr(payments, "ONLINE_PAYMENT", True)
    fake = FakeWhish()
    monkeypatch.setattr(whish, "create_payment", fake.create_payment)
    monkeypatch.setattr(whish, "payment_status", fake.payment_status)
    return fake


class FakeWhish:
    """Whish Pay in the tests: every payment link is paid ("success") unless
    a test sets `outcome` ("pending", "failed") or `down` (unreachable)."""

    def __init__(self):
        self.outcome = "success"
        self.down = False
        self.created = []  # the payments asked for (their arguments)
        self.status_calls = 0

    def create_payment(self, **kwargs):
        from app.services.whish import WhishError

        if self.down:
            raise WhishError("unreachable")
        self.created.append(kwargs)
        return f"https://whish.example/pay/{kwargs['external_id']}"

    def payment_status(self, external_id):
        self.status_calls += 1
        return self.outcome


class _Placed:
    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body

    def json(self):
        return self._body


def checkout(client, json, headers):
    """POST /cart/checkout as the site does it — and when it gives a Whish
    payment link, the customer pays and comes back (Whish's callback, then
    the return page): the answer is then what was ordered."""
    res = client.post("/api/cart/checkout", json=json, headers=headers)
    if res.status_code != 200 or "payment" not in res.json():
        return res
    payment_id = res.json()["payment"]["id"]
    client.get(f"/api/payments/whish/callback?payment={payment_id}&outcome=success")
    back = client.get(f"/api/payments/{payment_id}", headers=headers)
    body = back.json()
    if body.get("status") != "placed":
        return _Placed(402, body)
    return _Placed(200, {"checkout_id": body["checkout_id"], "orders": body["orders"], "gift_cards": body["gift_cards"]})
