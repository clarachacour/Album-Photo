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


@pytest.fixture()
def online_payment(app, monkeypatch):
    """Card payment switched on (see services/payments.py), with a fake
    Cybersource: every card is accepted, unless the test sets
    gateway["answer"] (what authorize_and_capture returns) or
    gateway["error"] (a GatewayError it raises)."""
    from app.services import cybersource, payments

    monkeypatch.setattr(payments, "ONLINE_PAYMENT", True)
    gateway = {"contexts": [], "charges": [], "answer": None, "error": None}

    def capture_context(amount_cents, lang="en"):
        gateway["contexts"].append(amount_cents)
        return f"capture.context.{len(gateway['contexts'])}"

    def authorize_and_capture(token, amount_cents, reference, bill_to):
        gateway["charges"].append({"token": token, "amount_cents": amount_cents, "reference": reference, "bill_to": bill_to})
        if gateway["error"]:
            raise gateway["error"]
        return gateway["answer"] or {"approved": True, "status": "AUTHORIZED", "id": f"tx-{len(gateway['charges'])}",
                                     "message": "", "reason": "", "raw": {"status": "AUTHORIZED"}}

    monkeypatch.setattr(cybersource, "capture_context", capture_context)
    monkeypatch.setattr(cybersource, "authorize_and_capture", authorize_and_capture)
    return gateway


def pay_by_card(client, headers, body=None):
    """The cart's checkout paid by card, as the site does it: the card form
    opened (POST /cart/card-session), then the order placed with the token
    it gave. Returns the checkout's response (or the card session's, when
    that one is refused)."""
    body = body or {}
    session = client.post("/api/cart/card-session", json={k: v for k, v in body.items() if k in ("shipping_address", "accepted_terms_version")},
                          headers=headers)
    if session.status_code != 200:
        return session
    return client.post("/api/cart/checkout", json={**body, "payment_method": "card", "payment_id": session.json()["payment_id"],
                                                   "transient_token": "transient.token.jwt"}, headers=headers)
