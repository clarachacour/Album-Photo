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
    # The nearest tier, as the printer bills it: 28 → 24, 40 → 50.
    assert printer_tier(28) == 24 and printer_tier(40) == 50 and printer_tier(10) == 24
    # Past 100 pages, the tier reached plus a price per page.
    assert printer_tier(120) == 100 and printer_tier(160) == 150


def test_pages_past_100_are_priced_per_page(monkeypatch):
    from app.services import printer_statement as ps

    # Until Bookstop gives its price per page: "to check".
    assert ps.printer_unit_price("A4", 120) is None
    assert ps._priced_as({"tier": 100, "extra": 20, "unit": None}) == "100 pages + 20 (to check)"
    monkeypatch.setattr(ps, "PRINTER_PER_PAGE", 0.2)
    assert ps.printer_unit_price("A4", 120) == 44
    assert ps.printer_unit_price("A5", 160) == 47


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
    asyncio.run(db.orders.delete_many({}))  # only this test's orders on the statement
    _order(db, "5f4c0509-a1", "ready_for_delivery", "A4", 50, qty=2)
    _order(db, "6a1b0000-a2", "delivered", "A5", 24, printer_paid_at="2026-10-15T08:00:00+00:00")
    _order(db, "9d4e0000-a5", "printing", "A4", 50)  # still being printed: not yet
    _order(db, "7c2d0000-a3", "pending_payment")  # not sent to print yet
    _order(db, "8e3f0000-a4", "cancelled")  # sent, then cancelled: not the printer's
    token = admin["Authorization"].split(" ", 1)[1]
    res = client.get(f"/api/admin/printer-statement.xlsx?auth={token}")
    assert res.status_code == 200 and res.headers["content-type"].startswith("application/vnd.openxmlformats")
    wb, rows = _rows(res.content)
    body = [r for r in rows[1:] if r[0] and r[0].startswith("EB-")]
    assert [r[0] for r in body] == ["EB-5F4C0509", "EB-6A1B0000"]
    first, second = body
    # Unit price, envelopes (0.50 per album), total.
    assert first[7] == 33 and first[8] == 1 and first[9] == 67 and first[10] == "To pay"
    assert second[7] == 24 and second[8] == 0.5 and second[9] == 24.5 and second[10] == "Paid"
    # Nothing about the customer or what they paid.
    text = " ".join(str(c) for ws in wb for row in ws.iter_rows(values_only=True) for c in row if c is not None)
    assert "Rita" not in text and "Sioufi" not in text and "Secret title" not in text and "49" not in text and "54" not in text
    assert client.get("/api/admin/printer-statement.xlsx").status_code == 401


def test_the_printer_link_and_payment_mark(client, db, admin):  # noqa: F811
    asyncio.run(db.orders.delete_many({}))
    _order(db, "5f4c0509-b1", "ready_for_delivery", "A4", 100)
    url = client.get("/api/admin/printer-statement-link", headers=admin).json()["url"]
    assert "/everbook-statement?key=" in url  # on the site's address
    key = url.split("key=", 1)[1]
    res = client.get(f"/api/printer-statement.xlsx?key={key}")
    assert res.status_code == 200 and 'filename="Everbook statement ' in res.headers["content-disposition"]
    assert client.get("/api/printer-statement.xlsx?key=wrong").status_code == 403

    assert client.patch("/api/admin/orders/5f4c0509-b1/printer-payment", json={"paid": True}, headers=admin).json()["printer_paid_at"]
    _, rows = _rows(client.get(f"/api/printer-statement.xlsx?key={key}").content)
    assert rows[1][10] == "Paid" and rows[1][7] == 40 and rows[1][9] == 40.5
    client.patch("/api/admin/orders/5f4c0509-b1/printer-payment", json={"paid": False}, headers=admin)
    _, rows = _rows(client.get(f"/api/printer-statement.xlsx?key={key}").content)
    assert rows[1][10] == "To pay"


def test_the_summary_goes_by_the_ready_for_pickup_month(app):
    from datetime import datetime
    from openpyxl import load_workbook
    from app.services.printer_statement import build_statement_xlsx

    def row(number, sent, ready, total):
        return {"number": number, "sent": sent, "ready": ready, "format": "A4 · portrait", "pages": 50, "tier": 50,
                "quantity": 1, "unit": total, "envelope": 0.5, "total": total, "paid": False, "paid_on": None}

    rows = [
        row("EB-1", datetime(2026, 10, 30), datetime(2026, 11, 2), 33),   # sent in October, ready in November
        row("EB-2", datetime(2026, 10, 10), datetime(2026, 10, 12), 27),
    ]
    wb = load_workbook(io.BytesIO(build_statement_xlsx(rows)))
    summary = [r for r in wb["Summary"].iter_rows(values_only=True)][1:]
    assert summary[0][:3] == ("October 2026", 1, 27)
    assert summary[1][:3] == ("November 2026", 1, 33)
