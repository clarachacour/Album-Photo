"""PDF rendering: fonts and the headless-browser export."""
import base64
import logging
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
    recursive split-and-retry in _render_all_chunks is a different
    safety net — for a chunk that's too heavy to fit under the string-
    length ceiling — not a substitute for giving a single ordinary page
    enough real time to finish under deliberately-lowered priority."""
    page.goto(print_url, wait_until="networkidle", timeout=120000)
    page.wait_for_selector('[data-print-ready="true"], [data-print-error="true"]', timeout=90000)
    error_el = page.query_selector('[data-print-error="true"]')
    if error_el:
        error_text = error_el.inner_text()
        raise RuntimeError(f"print page reported an error: {error_text}")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(500)  # extra buffer for final paint settling, on top of the 1.2s the print page itself now waits before signaling ready (see PrintAlbum.jsx)
    return page.pdf(print_background=True, prefer_css_page_size=True)

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

    Single-shot version — launches its own browser for one render. For a
    whole order's worth of chunked renders, see _render_all_chunks below,
    which reuses one browser across every chunk instead of paying
    Chromium's ~1-2s launch cost per chunk (which alone added tens of
    seconds on a large, many-chunk album).

    The step-by-step logging below (log_label lets a caller like
    render_recursive tag these with the order/chunk they belong to) exists
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
        page = browser.new_page()
        logger.info(f"{prefix}page ouverte, d\u00e9but du rendu…")
        pdf_bytes = _render_pdf_with_page(page, print_url)
        browser.close()
        return pdf_bytes
