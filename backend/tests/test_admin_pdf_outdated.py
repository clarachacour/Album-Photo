"""The admin sees when an album was edited after its order's PDF was made
(the PDF is made once: the printer would get the old version)."""
import asyncio

from tests.test_admin_address import admin  # noqa: F401  (fixture)


def _setup(db, oid, album_edited_at, **order):
    asyncio.run(db.albums.insert_one({"id": f"alb-{oid}", "user_id": "u1", "updated_at": album_edited_at}))
    asyncio.run(db.orders.insert_one({"id": oid, "album_id": f"alb-{oid}", "user_id": "u1", "kind": "print", "status": "printing",
                                      "created_at": "2026-10-01T09:00:00+00:00", "pdf_ready": True, "pdf_path": "x.pdf", **order}))


def _flag(client, admin, oid):
    orders = client.get("/api/admin/orders", headers=admin).json()
    return next(o for o in orders if o["id"] == oid)["album_changed_since_pdf"]


def test_album_edited_after_the_pdf(client, db, admin):  # noqa: F811
    _setup(db, "pdf-1", "2026-10-02T12:00:00+00:00", pdf_generated_at="2026-10-01T10:00:00+00:00")
    assert _flag(client, admin, "pdf-1") is True


def test_pdf_made_after_the_last_edit(client, db, admin):  # noqa: F811
    _setup(db, "pdf-2", "2026-10-01T08:00:00+00:00", pdf_generated_at="2026-10-01T10:00:00+00:00")
    assert _flag(client, admin, "pdf-2") is False


def test_older_orders_use_the_move_to_printing(client, db, admin):  # noqa: F811
    _setup(db, "pdf-3", "2026-10-02T12:00:00+00:00",
           status_history=[{"status": "paid", "at": "2026-10-01T09:00:00+00:00"}, {"status": "printing", "at": "2026-10-01T10:00:00+00:00"}])
    assert _flag(client, admin, "pdf-3") is True
