"""Album PDFs are rendered one page at a time and joined (see
app/services/pdf.py): pages must come out complete and in order, a page that
fails once is retried, and one that keeps failing stops the generation."""
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter

from app.services.pdf import PAGE_RENDER_ATTEMPTS, assemble_pages


def one_page_pdf(width: float) -> bytes:
    """A blank one-page PDF whose width identifies it."""
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=100)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def widths(pdf: bytes):
    return [float(page.mediabox.width) for page in PdfReader(BytesIO(pdf)).pages]


def test_pages_are_joined_in_order():
    pdf = assemble_pages(lambda i: one_page_pdf(100 + i), 5)
    assert widths(pdf) == [100, 101, 102, 103, 104]


def test_a_page_that_fails_once_is_retried():
    calls = []

    def render(i):
        calls.append(i)
        if i == 2 and calls.count(2) == 1:
            raise TimeoutError("slow page")
        return one_page_pdf(100 + i)

    assert widths(assemble_pages(render, 4)) == [100, 101, 102, 103]
    assert calls.count(2) == 2


def test_a_page_that_keeps_failing_stops_the_generation():
    calls = []

    def render(i):
        calls.append(i)
        if i == 1:
            raise RuntimeError("image failed to load")
        return one_page_pdf(100)

    with pytest.raises(RuntimeError, match="page 2"):
        assemble_pages(render, 3)
    assert calls.count(1) == PAGE_RENDER_ATTEMPTS
    assert 2 not in calls  # nothing rendered after the failing page
