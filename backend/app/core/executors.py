"""Thread pools used to run blocking work off the event loop."""
import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.config import MAX_CONCURRENT_PDF_GENERATIONS, UPLOAD_CONCURRENCY

# A dedicated pool for R2 (network I/O) calls, sized well above CPU count —
# see run_blocking's docstring for why this has to be separate from the
# default executor that the Playwright render and other CPU-bound work use.
# 32 concurrent R2 round-trips comfortably covers the number of photos
# Chromium requests at once for a single print page.
r2_io_executor = ThreadPoolExecutor(max_workers=32, thread_name_prefix="r2-io")

# A dedicated pool for the Chromium PDF render specifically, separate from
# the *default* executor (photo upload processing, AI curation's sharpness/
# face-detection work — see run_ai_processing) — both used to share the
# same default pool, so a PDF render in progress was competing for the
# same handful of threads a customer's own upload/curation needed to get
# back to them quickly. Generation is allowed to take however long it
# takes (nobody's watching it happen — it's not the customer waiting on
# this response, an order confirmation already went out immediately at
# checkout), but it should never be the reason someone actively using the
# editor right now waits longer than necessary. Sized directly off
# MAX_CONCURRENT_PDF_GENERATIONS (+1 for headroom) rather than a separate
# hardcoded number — raising the slot limit without also raising this
# would let more generations be "in progress" (holding a database slot)
# than the pool can actually run at once, queueing the extra ones inside
# the executor instead of anywhere visible, silently capping real
# concurrency below what the slot count implies.
pdf_render_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PDF_GENERATIONS + 1, thread_name_prefix="pdf-render")

# A dedicated pool for photo-upload processing (_process_photo_sync —
# decode, resize into variants, EXIF/hash) — separate from the default
# executor that AI curation's own sharpness/face-detection work also uses
# (see run_ai_processing), so someone uploading photos isn't waiting behind
# whatever curation work happens to be running at that moment, or vice
# versa. Sized at UPLOAD_CONCURRENCY * 2: comfortably covers every batch's
# own internal concurrency limit (see store_many_photos) with headroom
# for a couple of batches genuinely overlapping, without over-provisioning
# threads relative to the 4 real CPU cores actually available.
photo_processing_executor = ThreadPoolExecutor(max_workers=UPLOAD_CONCURRENCY * 2, thread_name_prefix="photo-proc")

def run_blocking(fn, *args):
    """Runs a blocking (sync) call — every get_object/put_object/
    delete_object below is a synchronous boto3 call — in a thread pool
    instead of directly on the asyncio event loop. Without this, a single
    R2 round-trip stalls the *entire* Uvicorn worker (there's only one,
    see Dockerfile) for its whole duration, queueing up every other
    concurrent request behind it. That's what was turning sub-second R2
    fetches into 10-90s waits under load and cascading into the PDF
    export's Page.goto networkidle timeouts. Any async endpoint calling
    get_object/put_object/delete_object should go through this.

    Deliberately runs on r2_io_executor rather than the default executor
    (the one every `loop.run_in_executor(None, ...)` call elsewhere in this
    file uses, including the multi-minute Playwright render itself). The
    default pool is sized off CPU count (min(32, cpu_count+4) — 8 threads
    on a 4-vCPU instance), which is the right size for CPU-bound work but
    starves I/O-bound R2 fetches: one thread sits occupied for the render's
    entire duration, and the handful left have to serialize the dozens of
    concurrent photo requests Chromium fires off for a single page — which
    is exactly what was still producing multi-second waits on individual
    photo fetches even after this function stopped blocking the event loop.
    I/O-bound work like a network round-trip can support far more
    concurrent threads than there are cores, since each one spends nearly
    all its time waiting rather than computing."""
    return asyncio.get_event_loop().run_in_executor(r2_io_executor, fn, *args)
