"""PDF rendering: fonts and the headless-browser export."""
import base64
import logging
import os
import time as _time
from urllib.parse import urlsplit
from io import BytesIO

import psutil
from playwright.sync_api import sync_playwright
from reportlab.lib import colors as rl_colors
from reportlab.lib.pagesizes import A4, A5, landscape, portrait
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.assets import cover_fonts as _cf

logger = logging.getLogger(__name__)


# Register the same fonts the web editor uses, so PDF text isn't silently
# swapped for a generic fallback (Helvetica) that looks nothing like it.
import os as _os
import tempfile as _tempfile

_FONT_DIR = _os.path.join(_tempfile.gettempdir(), "albumai_fonts")
_os.makedirs(_FONT_DIR, exist_ok=True)

_WEB_FONTS = {
    "Baloo2-ExtraBold": _cf.BALOO2_EXTRABOLD,
    "Manrope-Regular": _cf.MANROPE_REGULAR,
    "Manrope-Bold": _cf.MANROPE_BOLD,
    "CormorantGaramond-Regular": _cf.CORMORANT_REGULAR,
    "CormorantGaramond-Bold": _cf.CORMORANT_BOLD,
}
for _font_name, _font_bytes in _WEB_FONTS.items():
    _font_path = _os.path.join(_FONT_DIR, f"{_font_name}.ttf")
    # Several processes can start at once (uvicorn workers, parallel tests):
    # write to a private temp file, then rename it into place in one atomic
    # step, so no process can ever read a half-written font. A size check
    # also repairs a file left incomplete by an earlier crash.
    if not _os.path.exists(_font_path) or _os.path.getsize(_font_path) != len(_font_bytes):
        _fd, _tmp_path = _tempfile.mkstemp(dir=_FONT_DIR, suffix=".tmp")
        with _os.fdopen(_fd, "wb") as _fh:
            _fh.write(_font_bytes)
        _os.replace(_tmp_path, _font_path)
    pdfmetrics.registerFont(TTFont(_font_name, _font_path))

# The web editor renders a single book page at roughly this many CSS pixels
# wide — font sizes chosen in the editor (title_font_size, item font_size)
# are stored as raw px calibrated against that width. PDF pages are measured
# in points at their real print size, so a size stored as "48" needs scaling
# by (actual page width in points / this reference) to look the same
# proportion of the page as it did in the editor, not the same raw number.
REFERENCE_PAGE_PX = 430

def resolve_pdf_font(css_font: str, weight: str = "normal") -> str:
    """Maps a CSS font-family string (as stored on cover/text items) to the
    matching registered PDF font, falling back to Manrope if unrecognized."""
    css_font = (css_font or "").lower()
    is_bold = str(weight).lower() in ("bold", "600", "700", "800", "900") or (
        str(weight).isdigit() and int(weight) >= 600
    )
    if "baloo" in css_font:
        return "Baloo2-ExtraBold"  # only the extra-bold cut was bundled — it's the only weight used by the app
    if "cormorant" in css_font:
        return "CormorantGaramond-Bold" if is_bold else "CormorantGaramond-Regular"
    if "courier" in css_font:
        return "Courier-Bold" if is_bold else "Courier"
    if "georgia" in css_font or "helvetica" in css_font or "arial" in css_font:
        return "Helvetica-Bold" if is_bold else "Helvetica"
    # Manrope (the app's default sans-serif) and anything unrecognized
    return "Manrope-Bold" if is_bold else "Manrope-Regular"

# ---------- PDF Export ----------
def get_page_size(size: str, orientation: str):
    sizes = {"A4": A4, "A5": A5}
    base = sizes.get(size.upper(), A4)
    if orientation == "landscape":
        return landscape(base)
    return portrait(base)

def hex_to_rl_color(hex_color: str):
    try:
        return rl_colors.HexColor(hex_color)
    except Exception:
        return rl_colors.black

def decode_data_uri_image(data_uri: str):
    """Decode a `data:image/...;base64,...` string (our custom cover logos —
    heart, rings, compass — are stored this way) into an ImageReader.
    Returns None for anything else (SVG data URIs, external URLs, etc.) so
    callers can just skip drawing rather than crash."""
    try:
        if not data_uri or not data_uri.startswith("data:image/"):
            return None
        header, _, encoded = data_uri.partition(",")
        if "base64" not in header:
            return None
        if "svg" in header:
            return None  # SVG needs a separate renderer we don't have wired up
        raw = base64.b64decode(encoded)
        return ImageReader(BytesIO(raw))
    except Exception as e:
        logger.error(f"decode_data_uri_image failed: {e}")
        return None

def _render_pdf_with_page(page, print_url: str) -> bytes:
    """The actual per-URL render, taking an already-open Playwright Page —
    factored out of render_pdf_via_browser_sync so a whole order's worth
    of chunks can share one launched browser (see that function's
    docstring for why relaunching Chromium per chunk was itself a real
    chunk of the total generation time on a large album).

    Both timeouts below were raised from their original 30s/20s after a
    real generation genuinely failed under this: _deprioritize_current_
    process_tree deliberately lowers Chromium's OS scheduling priority so
    a customer actively using the editor always wins any real CPU
    contention — exactly as intended — but with a fixed 30s ceiling, that
    intentional slowdown could tip an otherwise-fine page over into an
    outright failure rather than just taking longer, on an album with
    someone actively editing throughout (auto-save alone hits this
    backend every couple of minutes). One later attempt failed at page 1
    and a different one at page 52, on the same album — no single broken
    photo could explain two different pages failing on two different
    runs, but genuine CPU contention explains both equally well. The
    per-page retries in assemble_pages are a separate safety net, not a
    substitute for giving a page enough time under lowered priority."""
    page.goto(print_url, wait_until="networkidle", timeout=120000)
    try:
        page.wait_for_selector('[data-print-ready="true"], [data-print-error="true"]', timeout=90000)
    except Exception as e:
        raise RuntimeError(f"print page never became ready — {_describe_page(page)}") from e
    error_el = page.query_selector('[data-print-error="true"]')
    if error_el:
        error_text = error_el.inner_text()
        raise RuntimeError(f"print page reported an error: {error_text}")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(500)  # extra buffer for final paint settling, on top of the 1.2s the print page itself now waits before signaling ready (see PrintAlbum.jsx)
    return page.pdf(print_background=True, prefer_css_page_size=True)

def _describe_page(page) -> str:
    """What the browser is actually showing, for error messages: a login or
    error page from the host instead of the print page, the album still
    loading, or images that never finished. The address is given without its
    query string, which holds the customer's login token."""
    try:
        info = page.evaluate("""() => ({
            text: (document.body && document.body.innerText || "").trim().replace(/\\s+/g, " ").slice(0, 160),
            pendingImages: Array.from(document.images).filter((i) => i.getAttribute("src") && !i.complete).length,
            images: document.images.length,
        })""")
        return (
            f"shown: {page.url.split('?')[0]} — title {page.title()!r} — text {info['text']!r} — "
            f"{info['pendingImages']}/{info['images']} images still loading"
        )
    except Exception as e:
        return f"page could not be inspected ({e})"


def _new_context(browser, print_url: str):
    """Browser context for the print page. When the frontend host protects its
    deployments (Vercel "Deployment Protection" on preview/branch URLs), the
    headless browser would get a login page instead of the album:
    VERCEL_PROTECTION_BYPASS_SECRET (Vercel → Settings → Deployment Protection
    → Protection Bypass for Automation) is then sent with the requests to the
    frontend only, never to the API or anywhere else."""
    context = browser.new_context()
    secret = os.environ.get("VERCEL_PROTECTION_BYPASS_SECRET")
    if secret:
        parts = urlsplit(print_url)
        origin = f"{parts.scheme}://{parts.netloc}"

        def add_bypass_header(route):
            route.continue_(headers={**route.request.headers, "x-vercel-protection-bypass": secret})

        context.route(lambda url: url.startswith(origin), add_bypass_header)
    return context


def _deprioritize_current_process_tree():
    """Lowers the OS scheduling priority (Linux 'nice' value) of every
    child process of the current one — in practice, the Chromium process
    Playwright just launched and its own sub-processes (renderer, GPU
    process, etc.). Separate executor pools (pdf_render_executor,
    r2_io_executor) only control which *Python threads* get to start
    work — they say nothing about how the underlying handful of real CPU
    cores actually get split once photo-upload processing and a Chromium
    render are BOTH genuinely running at the same time, since Chromium is
    its own OS process, entirely outside Python's own thread scheduling.
    A generation is allowed to take however long it takes — nobody's
    watching it happen. Someone actively uploading photos or waiting on
    AI curation right now IS watching, so under real contention the OS's
    own scheduler should favor them, not a PDF nobody's staring at. Never
    raises — a failure here should never be the reason a render doesn't
    happen, just means this specific optimization didn't apply."""
    try:
        proc = psutil.Process()
        for child in proc.children(recursive=True):
            try:
                child.nice(10)  # 0 is normal priority; positive is lower on Linux
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        logger.warning(f"Impossible de déprioriser le process Chromium : {e}")

def render_pdf_via_browser_sync(print_url: str, log_label: str = "") -> bytes:
    """Runs entirely with Playwright's sync API. Must be called off the main
    asyncio loop (via run_in_executor) since it blocks the calling thread —
    but that's exactly why it sidesteps the Windows subprocess/event-loop
    conflict: the sync API manages its own event loop internally, in its
    own thread, independent of whatever loop uvicorn is using.

    Single-shot version — launches its own browser for one render. Whole
    albums go through render_album_pdf_sync (one page at a time, one
    browser).

    The step-by-step logging below (log_label lets a caller tag these with the order/chunk they belong to) exists
    because a real generation once ran the full 3600s Cloud Run ceiling and
    got killed with *zero* log output in between "point de départ estimé"
    and the timeout — no chunk succeeded, none logged a failure-and-split
    either, meaning whatever hung did so somewhere between those two
    existing checkpoints with nothing in between to narrow it down. Every
    step Playwright takes before the render itself (spinning up its own
    driver process, launching Chromium, opening a page) had no logging of
    its own — any one of them could have been the actual hang, and there
    was no way to tell which from the logs alone."""
    prefix = f"{log_label} : " if log_label else ""
    logger.info(f"{prefix}ouverture de sync_playwright()")
    with sync_playwright() as p:
        logger.info(f"{prefix}sync_playwright() ouvert, lancement de Chromium…")
        browser = p.chromium.launch()
        logger.info(f"{prefix}Chromium lancé, dépriorisation du process…")
        _deprioritize_current_process_tree()
        logger.info(f"{prefix}ouverture d'une nouvelle page…")
        page = _new_context(browser, print_url).new_page()
        logger.info(f"{prefix}page ouverte, d\u00e9but du rendu…")
        pdf_bytes = _render_pdf_with_page(page, print_url)
        browser.close()
        return pdf_bytes


# ---------- Album PDF, one page at a time ----------
# Chromium's print time grows much faster than the page count when one
# document holds many large photos (measured: 3 pages 16 s, 10 pages 271 s),
# which is why whole-album renders took 20+ minutes or never finished.
# Printing each album page on its own and joining the results keeps the cost
# proportional to the page count (a 20-page album: 42 s instead of 15+ min).
# Joining copies each page as is: photos are not re-encoded.
PAGE_RENDER_ATTEMPTS = 3
# A fresh browser context now and then, so memory held by past pages can't
# build up over a long album.
PAGES_PER_BROWSER_CONTEXT = 20


def assemble_pages(render_page, page_count: int, log_label: str = "") -> bytes:
    """Calls render_page(i) for every album page i (each returns a PDF),
    retrying a failed page, and joins the results in order."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for i in range(page_count):
        for attempt in range(1, PAGE_RENDER_ATTEMPTS + 1):
            try:
                part = render_page(i)
                break
            except Exception as e:
                logger.warning(f"{log_label} page {i + 1}/{page_count}, essai {attempt}/{PAGE_RENDER_ATTEMPTS} échoué : {e}")
                if attempt == PAGE_RENDER_ATTEMPTS:
                    raise RuntimeError(f"page {i + 1} could not be rendered: {e}") from e
        for pdf_page in PdfReader(BytesIO(part)).pages:
            writer.add_page(pdf_page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def render_album_pdf_sync(print_url: str, page_count: int, log_label: str = "") -> bytes:
    """The album's print page (PrintAlbum.jsx), rendered one album page at a
    time in a single Chromium and joined into one PDF. print_url is the
    page's address without the from/to range. Blocking: run it in an
    executor."""
    if page_count <= 0:
        return render_pdf_via_browser_sync(print_url, log_label=log_label)
    sep = "&" if "?" in print_url else "?"
    t_start = _time.monotonic()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        _deprioritize_current_process_tree()
        state = {"context": None, "pages_in_context": 0}

        def fresh_context():
            if state["context"] is not None:
                try:
                    state["context"].close()
                except Exception:
                    pass
            state["context"] = _new_context(browser, print_url)
            state["pages_in_context"] = 0

        def render_page(i: int) -> bytes:
            if state["context"] is None or state["pages_in_context"] >= PAGES_PER_BROWSER_CONTEXT:
                fresh_context()
            state["pages_in_context"] += 1
            page = state["context"].new_page()
            t0 = _time.monotonic()
            try:
                pdf = _render_pdf_with_page(page, f"{print_url}{sep}from={i}&to={i}")
            except Exception:
                fresh_context()  # don't reuse a context that just failed
                raise
            finally:
                try:
                    page.close()
                except Exception:
                    pass
            logger.info(f"{log_label} page {i + 1}/{page_count} en {_time.monotonic() - t0:.1f}s ({len(pdf) / 1e6:.1f} Mo)")
            return pdf

        try:
            pdf = assemble_pages(render_page, page_count, log_label)
        finally:
            browser.close()
    logger.info(f"{log_label} PDF de {page_count} pages en {_time.monotonic() - t_start:.0f}s ({len(pdf) / 1e6:.0f} Mo)")
    return pdf
