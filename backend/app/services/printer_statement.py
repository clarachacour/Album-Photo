"""The printer's statement: every album sent to the printer, what it costs
Everbook (the printer's price list, not the customer's price), and whether
it's been paid to the printer. Built as an Excel file whenever it's asked
for, so it's always up to date (admin download, or the printer's own link)."""
from collections import OrderedDict
from datetime import datetime
from io import BytesIO
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.core.order_number import order_number
from app.core.signed_links import sign_order_action, verify_order_action
from app.services.pricing import nearest_tier

# What the printer charges per copy, in dollars, by page tier and format.
# 150 pages is the most an album can have.
PRINTER_PRICES = OrderedDict([
    (24, {"A5": 24, "A4": 27}),
    (50, {"A5": 30, "A4": 33}),
    (100, {"A5": 37, "A4": 40}),
    (150, {"A5": 45, "A4": 55}),
])

# The envelope the printer packs each album in, in dollars, per album.
ENVELOPE_PRICE = 0.5

# Statuses of an order whose book the printer has finished.
PRINTED = ("ready_for_delivery", "shipped", "delivered")

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def printer_tier(pages: int) -> Optional[int]:
    """The price tier the printer bills an album of `pages` pages at: the
    nearest one (15 → 24, 28 → 24, 40 → 50, 160 → 150), as for our prices."""
    return nearest_tier(pages, list(PRINTER_PRICES))


def printer_unit_price(size: str, pages: int) -> Optional[int]:
    tier = printer_tier(pages)
    if tier is None:
        return None
    return PRINTER_PRICES[tier].get(size if size in ("A4", "A5") else "A4")


def _history_time(order: dict, status: str) -> Optional[str]:
    times = [h["at"] for h in order.get("status_history") or [] if h.get("status") == status]
    return times[0] if times else None


def _date(iso: Optional[str]):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def statement_rows(orders: list, page_counts: dict) -> list:
    """One row per printed order, oldest first. page_counts: album id →
    page count, for orders from before the page count was kept on them."""
    rows = []
    for o in orders:
        if o.get("kind", "print") != "print":
            continue
        # Only books the printer has finished (not those still being
        # printed, nor cancelled orders).
        if o.get("status") not in PRINTED:
            continue
        sent = _history_time(o, "printing")
        # Ready for pickup; an order moved on by hand without that step
        # takes the date of the next one.
        ready = next((t for t in (_history_time(o, st) for st in PRINTED) if t), None)
        pages = o.get("page_count") or page_counts.get(o.get("album_id")) or 0
        unit = printer_unit_price(o.get("size"), pages)
        qty = int(o.get("quantity") or 1)
        rows.append({
            "number": order_number(o),
            "sent": _date(sent or o.get("created_at")),
            "ready": _date(ready or o.get("updated_at")),
            "format": f"{o.get('size', 'A4')} · {'landscape' if o.get('orientation') == 'landscape' else 'portrait'}",
            "pages": pages,
            "tier": printer_tier(pages),
            "quantity": qty,
            "unit": unit,
            "envelope": ENVELOPE_PRICE * qty,
            "total": (unit + ENVELOPE_PRICE) * qty if unit is not None else None,
            "paid": bool(o.get("printer_paid_at")),
            "paid_on": _date(o.get("printer_paid_at")),
        })
    # In the order the books were ready for pickup.
    rows.sort(key=lambda r: (r["ready"] or datetime.min, r["sent"] or datetime.min))
    return rows


HEADER_FILL = PatternFill("solid", fgColor="1A1A17")
HEADER_FONT = Font(bold=True, color="F9F8F6")
DATE_FMT = "dd/mm/yyyy"
MONEY_FMT = '#,##0.00 "$"'


def _header(ws, titles, widths):
    ws.append(titles)
    for i, w in enumerate(widths, start=1):
        cell = ws.cell(row=1, column=i)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"


def build_statement_xlsx(rows: list) -> bytes:
    wb = Workbook()

    ws = wb.active
    ws.title = "Albums"
    _header(ws, ["Order number", "Sent to printer", "Ready for pickup", "Format", "Pages", "Priced as", "Quantity",
                 "Unit price", "Envelopes", "Total", "Payment", "Paid on"],
            [16, 14, 16, 16, 8, 11, 10, 12, 11, 12, 12, 12])
    for r in rows:
        status = "Paid" if r["paid"] else "To pay"
        ws.append([r["number"], r["sent"], r["ready"], r["format"], r["pages"],
                   f"{r['tier']} pages" if r["tier"] else "to check", r["quantity"],
                   r["unit"], r["envelope"], r["total"], status, r["paid_on"]])
        row = ws.max_row
        for col in (2, 3, 12):
            ws.cell(row=row, column=col).number_format = DATE_FMT
        for col in (8, 9, 10):
            ws.cell(row=row, column=col).number_format = MONEY_FMT
        ws.cell(row=row, column=11).font = Font(bold=True, color="2E7D32" if r["paid"] else "B42727")
    if rows:
        last = ws.max_row
        ws.append(["Total", None, None, None, None, None, f"=SUM(G2:G{last})", None, f"=SUM(I2:I{last})", f"=SUM(J2:J{last})"])
        total_row = ws.max_row
        for col in range(1, 13):
            ws.cell(row=total_row, column=col).font = Font(bold=True)
        for col in (9, 10):
            ws.cell(row=total_row, column=col).number_format = MONEY_FMT

    # Month by month: what was printed, paid, and still to pay.
    rs = wb.create_sheet("Summary")
    _header(rs, ["Month", "Albums", "Total", "Paid", "Left to pay"], [18, 10, 12, 12, 14])
    # By the month the printer had the book ready for pickup.
    months = OrderedDict()
    for r in sorted(rows, key=lambda r: r["ready"] or datetime.min):
        if not r["ready"]:
            continue
        key = (r["ready"].year, r["ready"].month)
        m = months.setdefault(key, {"albums": 0, "total": 0, "paid": 0})
        m["albums"] += r["quantity"]
        m["total"] += r["total"] or 0
        m["paid"] += (r["total"] or 0) if r["paid"] else 0
    for (y, mo), m in months.items():
        rs.append([f"{MONTHS[mo - 1]} {y}", m["albums"], m["total"], m["paid"], m["total"] - m["paid"]])
        for col in (3, 4, 5):
            rs.cell(row=rs.max_row, column=col).number_format = MONEY_FMT
    if months:
        last = rs.max_row
        rs.append(["Total", f"=SUM(B2:B{last})", f"=SUM(C2:C{last})", f"=SUM(D2:D{last})", f"=SUM(E2:E{last})"])
        for col in range(1, 6):
            rs.cell(row=rs.max_row, column=col).font = Font(bold=True)
        for col in (3, 4, 5):
            rs.cell(row=rs.max_row, column=col).number_format = MONEY_FMT

    ts = wb.create_sheet("Prices")
    _header(ts, ["Pages", "A5 (per album)", "A4 (per album)"], [12, 16, 16])
    for tier, prices in PRINTER_PRICES.items():
        ts.append([f"{tier} pages", prices["A5"], prices["A4"]])
        for col in (2, 3):
            ts.cell(row=ts.max_row, column=col).number_format = MONEY_FMT
    ts.append(["Envelope", ENVELOPE_PRICE, ENVELOPE_PRICE])
    for col in (2, 3):
        ts.cell(row=ts.max_row, column=col).number_format = MONEY_FMT
    ts.append([])
    ts.append(["An album between two tiers is priced at the next tier up (e.g. 35 pages: the 50-page price)."])

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# The printer's own link: the same statement, behind a fixed secret key.
STATEMENT_KEY_SUBJECT = "printer-statement"


def statement_key() -> str:
    return sign_order_action(STATEMENT_KEY_SUBJECT, "view")


def valid_statement_key(key: Optional[str]) -> bool:
    return verify_order_action(STATEMENT_KEY_SUBJECT, "view", key)
