"""Album PDFs are rendered one page at a time and joined (see
app/services/pdf.py): pages must come out complete and in order, a page that
fails once is retried, and one that keeps failing stops the generation."""
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter

from app.services.pdf import PAGE_RENDER_ATTEMPTS, assemble_pages, trim_to_sheets


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


def _page_sizes(data):
    return [(round(float(p.mediabox.width), 2), round(float(p.mediabox.height), 2)) for p in PdfReader(BytesIO(data)).pages]


def _sized_pdf(sizes):
    writer = PdfWriter()
    for w, h in sizes:
        writer.add_blank_page(width=w, height=h)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def test_pages_rounded_up_by_the_browser_are_cut_to_their_sheet():
    a5 = (148 * 72 / 25.4, 210 * 72 / 25.4)  # 419.53 × 595.28 pt
    # Chromium's A5 portrait and landscape pages: a little too wide / too tall.
    pdf = _sized_pdf([(420, 594.96), (594.96, 420)])
    trimmed = trim_to_sheets(pdf, [a5, a5[::-1]])
    assert _page_sizes(trimmed) == [(419.53, 594.96), (594.96, 419.53)]
    # cut from the right and the bottom: the drawing starts at the top-left
    first, second = PdfReader(BytesIO(trimmed)).pages
    assert float(first.mediabox.left) == 0 and float(first.mediabox.top) == 594.96
    assert float(second.mediabox.bottom) == pytest.approx(420 - 419.53, abs=0.01)


def test_pages_far_from_their_sheet_or_miscounted_are_left_alone():
    pdf = _sized_pdf([(420, 594.96)])
    assert trim_to_sheets(pdf, [(300, 594.96)]) == pdf  # not a rounding: something else
    assert trim_to_sheets(pdf, [(419.53, 595.28), (419.53, 595.28)]) == pdf
    assert trim_to_sheets(pdf, []) == pdf
