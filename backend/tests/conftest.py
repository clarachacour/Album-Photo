import os
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
