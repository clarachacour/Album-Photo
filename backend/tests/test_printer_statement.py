"""The printer's statement: the printer's prices (not the customer's),
one line per album sent to print, paid or not, and the two ways in."""
import asyncio
import io

from openpyxl import load_workbook

from tests.test_admin_address import admin  # noqa: F401  (fixture)


def test_price_tiers():
    from app.services.printer_statement import printer_tier, printer_unit_price

    assert printer_unit_price("A5", 24) == 24 and printer_unit_price("A4", 24) == 27
    assert printer_unit_price("A4", 50) == 33 and printer_unit_price("A5", 100) == 37
    assert printer_unit_price("A4", 150) == 55
    assert printer_tier(35) == 50 and printer_tier(10) == 24
    assert printer_unit_price("A4", 151) is None


def _order(db, oid, status, size="A4", page_count=50, qty=1, **extra):
    history = [{"status": "pending_payment", "at": "2026-10-10T09:00:00+00:00"}]
    if status != "pending_payment":
        history.append({"status": "printing", "at": "2026-10-12T10:00:00+00:00"})
    if status in ("ready_for_delivery", "delivered"):
        history.append({"status": "ready_for_delivery", "at": "2026-10-14T10:00:00+00:00"})
    asyncio.run(db.orders.insert_one({
        "id": oid, "album_id": f"alb-{oid}", "user_id": "u1", "kind": "print", "status": status, "size": size,
        "orientation": "portrait", "quantity": qty, "page_count": page_count, "status_history": history,
        "unit_price_cents": 4900, "total_price_cents": 5400, "album_title": "Secret title",
        "shipping_address": {"full_name": "Rita Haddad", "phone": "70123456", "street": "Rue Sioufi", "city": "Beirut"}, **extra,
    }))


def _rows(content):
    wb = load_workbook(io.BytesIO(content))
    return wb, [list(r) for r in wb["Albums"].iter_rows(values_only=True)]


def test_the_admin_downloads_the_statement(client, db, admin):  # noqa: F811
    _order(db, "5f4c0509-a1", "ready_for_delivery", "A4", 50, qty=2)
    _order(db, "6a1b0000-a2", "printing", "A5", 24, printer_paid_at="2026-10-15T08:00:00+00:00")
    _order(db, "7c2d0000-a3", "pending_payment")  # not sent to print yet
    token = admin["Authorization"].split(" ", 1)[1]
    res = client.get(f"/api/admin/printer-statement.xlsx?auth={token}")
    assert res.status_code == 200 and res.headers["content-type"].startswith("application/vnd.openxmlformats")
    wb, rows = _rows(res.content)
    body = [r for r in rows[1:] if r[0] and r[0].startswith("EB-")]
    assert [r[0] for r in body] == ["EB-5F4C0509", "EB-6A1B0000"]
    first, second = body
    assert first[7] == 33 and first[8] == 66 and first[9] == "To pay"
    assert second[7] == 24 and second[9] == "Paid"
    # Nothing about the customer or what they paid.
    text = " ".join(str(c) for ws in wb for row in ws.iter_rows(values_only=True) for c in row if c is not None)
    assert "Rita" not in text and "Sioufi" not in text and "Secret title" not in text and "49" not in text and "54" not in text
    assert client.get("/api/admin/printer-statement.xlsx").status_code == 401


def test_the_printer_link_and_payment_mark(client, db, admin):  # noqa: F811
    _order(db, "5f4c0509-b1", "printing", "A4", 100)
    url = client.get("/api/admin/printer-statement-link", headers=admin).json()["url"]
    key = url.split("key=", 1)[1]
    assert client.get(f"/api/printer-statement.xlsx?key={key}").status_code == 200
    assert client.get("/api/printer-statement.xlsx?key=wrong").status_code == 403

    assert client.patch("/api/admin/orders/5f4c0509-b1/printer-payment", json={"paid": True}, headers=admin).json()["printer_paid_at"]
    _, rows = _rows(client.get(f"/api/printer-statement.xlsx?key={key}").content)
    assert rows[1][9] == "Paid" and rows[1][7] == 40
    client.patch("/api/admin/orders/5f4c0509-b1/printer-payment", json={"paid": False}, headers=admin)
    _, rows = _rows(client.get(f"/api/printer-statement.xlsx?key={key}").content)
    assert rows[1][9] == "To pay"
