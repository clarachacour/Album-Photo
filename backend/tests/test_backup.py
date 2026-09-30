"""Daily database backup to R2, and reading it back."""
import asyncio
from datetime import datetime, timezone

import pytest


@pytest.fixture()
def fake_r2(monkeypatch):
    """R2 kept in a dict, for the backup module."""
    from app.services import backup

    files = {}

    def put_object(path, data, content_type=None):
        files[path] = bytes(data)
        return {"path": path, "size": len(data)}

    def get_object(path):
        return files[path], "application/octet-stream"

    def list_folders(prefix):
        return sorted({prefix + k[len(prefix):].split("/")[0] + "/" for k in files if k.startswith(prefix) and "/" in k[len(prefix):]})

    def delete_prefix(prefix):
        gone = [k for k in files if k.startswith(prefix)]
        for k in gone:
            del files[k]
        return len(gone)

    for name, fn in (("put_object", put_object), ("get_object", get_object), ("list_folders", list_folders), ("delete_prefix", delete_prefix)):
        monkeypatch.setattr(backup, name, fn)
    return files


def test_backup_then_read_back_gives_the_same_documents(client, db, fake_r2):
    from app.services.backup import backup_database, read_backup

    when = datetime(2026, 9, 30, 3, 0, tzinfo=timezone.utc)
    asyncio.run(db.orders.insert_one({"id": "o1", "total_price_cents": 4000, "created_at": when, "shipping_address": {"city": "Beyrouth"}, "tags": ["a", "é"]}))
    asyncio.run(db.albums.insert_one({"id": "a1", "pages": [{"items": [{"x": 0.25, "photo_id": None}]}]}))

    result = asyncio.run(backup_database(now=when))
    assert result["folder"] == "backups/2026-09-30/"
    assert "backups/2026-09-30/manifest.json" in fake_r2

    data = read_backup("2026-09-30")
    for name in ("orders", "albums"):
        original = asyncio.run(db[name].find({}).to_list(None))
        assert data[name] == original  # same values, _id and dates included
        assert result["collections"][name] == len(original)
    order = next(o for o in data["orders"] if o["id"] == "o1")
    assert order["created_at"].replace(tzinfo=timezone.utc) == when


def test_only_the_last_30_days_are_kept(client, db, fake_r2):
    from app.services.backup import backup_database

    for day in ("2026-08-15", "2026-08-31", "2026-09-01", "2026-09-29"):
        fake_r2[f"backups/{day}/manifest.json"] = b"{}"
    fake_r2["backups/notes.txt"] = b"not a backup"
    result = asyncio.run(backup_database(now=datetime(2026, 9, 30, tzinfo=timezone.utc)))
    assert sorted(result["deleted_old"]) == ["backups/2026-08-15/", "backups/2026-08-31/"]
    days = {k.split("/")[1] for k in fake_r2 if k.startswith("backups/") and k.count("/") == 2}
    assert days == {"2026-09-01", "2026-09-29", "2026-09-30"}
    assert "backups/notes.txt" in fake_r2


def test_backup_endpoint_needs_the_secret(client, monkeypatch, fake_r2):
    from app.routers import internal

    monkeypatch.setattr(internal, "CLEANUP_SECRET", "s3cret")
    assert client.post("/api/internal/backup").status_code == 401
    assert client.post("/api/internal/backup", headers={"X-Cleanup-Secret": "wrong"}).status_code == 401
    res = client.post("/api/internal/backup", headers={"X-Cleanup-Secret": "s3cret"})
    assert res.status_code == 200, res.text
    assert res.json()["folder"].startswith("backups/")
