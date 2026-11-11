"""The printer's file format, chosen in the admin: the original layout by
default, or the one-sheet hardcover format — with the cut and the bleed
written in the PDF for the printer's software."""
from io import BytesIO

from tests.test_api import _signup


def test_the_admin_chooses_the_format(client, db, monkeypatch):
    from app.core import auth

    email, admin = _signup(client, db=db)
    monkeypatch.setattr(auth, "ADMIN_EMAIL", email)
    _, someone = _signup(client, db=db)
    assert client.get("/api/admin/print-format", headers=someone).status_code == 403
    assert client.get("/api/admin/print-format", headers=admin).json()["format"] == "bookstop"
    assert client.put("/api/admin/print-format", json={"format": "hardcover"}, headers=admin).json()["format"] == "hardcover"
    assert client.get("/api/admin/print-format", headers=admin).json()["format"] == "hardcover"
    assert client.put("/api/admin/print-format", json={"format": "other"}, headers=admin).status_code == 400
    client.put("/api/admin/print-format", json={"format": "bookstop"}, headers=admin)


def test_the_print_page_is_asked_for_that_format():
    from app.services.print_format import print_url_suffix

    assert print_url_suffix("bookstop", False) == ""
    assert print_url_suffix("hardcover", False) == "&format=hardcover"
    assert print_url_suffix("hardcover", True) == "&digital=1"  # a PDF to download stays the reader's


def test_the_pdf_says_where_to_cut():
    from pypdf import PdfReader, PdfWriter

    from app.services.pdf import MM_TO_PT, trim_to_sheets

    writer = PdfWriter()
    writer.add_blank_page(width=164 * MM_TO_PT, height=226 * MM_TO_PT)  # an A5 page's sheet
    buf = BytesIO()
    writer.write(buf)
    sheets = [[164 * MM_TO_PT, 226 * MM_TO_PT, "8,8,148,210", "3"]]
    page = PdfReader(BytesIO(trim_to_sheets(buf.getvalue(), sheets))).pages[0]
    mm = lambda box: [round(float(v) / MM_TO_PT, 1) for v in box]  # noqa: E731
    assert mm(page.trimbox) == [8.0, 8.0, 156.0, 218.0]
    assert mm(page.bleedbox) == [5.0, 5.0, 159.0, 221.0]
