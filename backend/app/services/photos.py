"""Photo storage: validation, resizing into variants, saving."""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Optional

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

from app.config import APP_NAME, UPLOAD_CONCURRENCY
from app.core.executors import photo_processing_executor
from app.db import db
from app.services.curation import ahash_to_str, compute_ahash, extract_exif_info
from app.services.storage import get_object, put_object

logger = logging.getLogger(__name__)


try:
    import pillow_heif
    pillow_heif.register_heif_opener()  # lets Image.open() read iPhone HEIC/HEIF photos — plain Pillow can't decode them on its own
except ImportError:
    logging.getLogger(__name__).warning("pillow-heif non installé — les photos HEIC/HEIF (format par défaut iPhone) échoueront au décodage")

# ---------- Photo Upload ----------
# image/heic and image/heif were missing here despite pillow-heif being
# installed and registered specifically to decode them (see the
# register_heif_opener() call near the top of the file) — the processing
# pipeline could handle an iPhone's default photo format perfectly well,
# but every HEIC upload was being silently rejected right here, before it
# ever reached that pipeline. iPhones only produce .jpg instead of HEIC
# when "Most Compatible" is chosen in Settings > Camera > Formats, which
# isn't the default — so this was quietly failing photos from most iPhones
# on their default settings, not just an edge case.
ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic", "image/heif"}

# A phone photo is often far larger than any of our page sizes need at
# print quality (300 DPI) — even our biggest format, A3, only needs
# ~3508x4961px (see pageDimsMm equivalent on the frontend). 5000px keeps a
# comfortable margin above that while cutting the excess most cameras
# capture well beyond what a printed page can show, saving real storage
# with no visible loss at print time.
MAX_STORED_DIMENSION_PX = 5000

def store_image_with_thumbnail(path: str, data: bytes, content_type: str):
    """Uploads a print-quality (but not necessarily full-original-resolution)
    version of the image, then a best-effort 300x300 JPEG thumbnail alongside
    it (same path with _thumb.jpg instead of the original extension).
    Returns (upload_result, thumbnail_path_or_None, width_or_None,
    height_or_None). Shared by every place that stores an image + its
    thumbnail — regular photos, cover images, cover assets."""
    img_w, img_h = None, None
    thumb_path = None
    store_data, store_content_type = data, content_type
    try:
        with Image.open(BytesIO(data)) as _probe:
            # Phone cameras very often save the raw sensor pixels in one
            # orientation (frequently landscape, regardless of how the
            # phone was actually held) plus an EXIF tag saying "rotate/
            # flip this for correct display" — every viewer normally
            # applies that tag invisibly, so a photo everyone SEES as
            # portrait can have raw pixel dimensions that are actually
            # wider than they are tall, and vice versa. Every downstream
            # use of width/height (the AI layout's photo/slot aspect-ratio
            # matching in particular) was reading those raw, pre-rotation
            # dimensions — so a portrait-looking face photo could get
            # measured as landscape, get placed in a landscape-shaped
            # slot, and have the face cropped off. exif_transpose bakes
            # the rotation into the actual pixels once, here, at the
            # single shared entry point every image (photos, cover
            # images, cover assets) already goes through — so everything
            # downstream (the stored file, thumbnails, medium/print
            # variants, and the width/height recorded below) is
            # consistently already-correctly-oriented from this point on,
            # with nothing else needing its own fix.
            _probe = ImageOps.exif_transpose(_probe)
            orig_w, orig_h = _probe.size
            if max(orig_w, orig_h) > MAX_STORED_DIMENSION_PX:
                scaled = _probe.copy()
                scaled.thumbnail((MAX_STORED_DIMENSION_PX, MAX_STORED_DIMENSION_PX), Image.LANCZOS)
                out_buf = BytesIO()
                save_kwargs = {"quality": 92} if (_probe.format or "").upper() == "JPEG" else {}
                scaled.save(out_buf, format=_probe.format or "JPEG", **save_kwargs)
                store_data = out_buf.getvalue()
                img_w, img_h = scaled.size
            else:
                # Even when no resize is needed, the re-oriented pixels
                # must still replace store_data — otherwise the file
                # actually uploaded would keep its original EXIF-rotation-
                # pending orientation while img_w/img_h (used everywhere
                # else) claim the corrected one, a mismatch worse than
                # not fixing this at all.
                out_buf = BytesIO()
                save_kwargs = {"quality": 95} if (_probe.format or "").upper() == "JPEG" else {}
                _probe.save(out_buf, format=_probe.format or "JPEG", **save_kwargs)
                store_data = out_buf.getvalue()
                img_w, img_h = orig_w, orig_h
    except Exception as e:
        logger.debug(f"Impossible de redimensionner l'image à l'upload (on garde l'originale) : {e}")

    result = put_object(path, store_data, store_content_type)
    try:
        with Image.open(BytesIO(store_data)) as _probe:
            # For JPEGs, this tells the decoder to decode directly at
            # roughly this size instead of full resolution — a real
            # decode-time memory saving, not just a resize after the fact.
            # No-op (safely ignored) for PNG/WEBP.
            _probe.draft("RGB", (300, 300))
            thumb = _probe.convert("RGB") if _probe.mode not in ("RGB", "L") else _probe.copy()
            thumb.thumbnail((300, 300), Image.LANCZOS)
            thumb_buf = BytesIO()
            thumb.save(thumb_buf, format="JPEG", quality=82)
            thumb_path_candidate = path.rsplit(".", 1)[0] + "_thumb.jpg"
            put_object(thumb_path_candidate, thumb_buf.getvalue(), "image/jpeg")
            thumb_path = thumb_path_candidate
    except Exception as e:
        logger.debug(f"Impossible de générer la vignette (fallback sur l'original): {e}")
    return result, thumb_path, img_w, img_h

# Sharp enough to fill an on-screen flipbook page without looking soft,
# while staying much lighter than the up-to-5000px print original —
# generated on demand (see get_photo_image) rather than at upload time, so
# creating a big album never pays this cost for photos nobody ends up
# actually scrolling to.
MEDIUM_MAX_DIMENSION_PX = 1200

def generate_medium_variant(photo: dict):
    """Resizes a photo's already-stored print-quality version down to the
    flipbook-viewing size, uploads it to R2 alongside the original and
    thumbnail, and returns (r2_path, jpeg_bytes) so the caller can serve it
    immediately without a second round-trip to R2. Returns (None, None) on
    any failure — the caller falls back to the thumbnail rather than
    erroring the whole page."""
    try:
        data, _ = get_object(photo["storage_path"])
        with Image.open(BytesIO(data)) as img:
            img = img.convert("RGB") if img.mode not in ("RGB", "L") else img.copy()
            img.thumbnail((MEDIUM_MAX_DIMENSION_PX, MEDIUM_MAX_DIMENSION_PX), Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=88)
            medium_bytes = buf.getvalue()
        medium_path = photo["storage_path"].rsplit(".", 1)[0] + "_medium.jpg"
        put_object(medium_path, medium_bytes, "image/jpeg")
        return medium_path, medium_bytes
    except Exception as e:
        logger.error(f"Impossible de générer la variante 'medium' pour la photo {photo.get('id')}: {e}")
        return None, None

# The printing office's stated minimum is 300 ppi (360 ppi is their
# target, 300 the floor they'll actually accept). 3000px was short of that
# for a full-bleed photo on our largest actually-relevant format — a photo
# filling the full height of an A4 page (29.7cm / 11.69in) only reached
# ~256 ppi at 3000px, below their 300 floor; A4's long side needs 3508px
# to clear it. This only matters for a photo displayed large (a full-page
# "hero" photo) — the same 3508px comfortably exceeds 300 ppi for any
# photo occupying a smaller fraction of the page, e.g. one tile in a
# multi-photo grid. A raw phone/camera original is very often 6000-8000px+
# on the long side (or more), which the PDF export was previously using
# directly (variant=original) — decoding dozens of those, all at once, for
# one continuous Playwright-rendered PDF covering every page of the whole
# album, is what pushed memory usage past the Cloud Run instance's limit
# and crashed the whole export. This still cuts each photo's decoded
# memory footprint substantially versus a raw original, just less
# aggressively than the previous 3000px cap.
# Formats a browser (and so the PDF renderer) can draw as they are.
BROWSER_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}


def print_needs_conversion(photo: dict) -> bool:
    """The PDF uses each photo at the full resolution it was stored with at
    upload. Only formats a browser can't draw (HEIC from iPhones…) need a
    JPEG copy first — same pixels, nothing downscaled."""
    return (photo.get("content_type") or "").lower() not in BROWSER_IMAGE_TYPES


def generate_print_variant(photo: dict):
    """Full-resolution JPEG copy of a photo stored in a format browsers
    can't draw (see print_needs_conversion). Returns (path, bytes).

    Stored under a different key (and DB field print_full_path) than the
    former 3508px "_print.jpg" copies, which must no longer reach a PDF."""
    try:
        data, _ = get_object(photo["storage_path"])
        with Image.open(BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB") if img.mode not in ("RGB", "L") else img.copy()
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=95)
            print_bytes = buf.getvalue()
        print_path = photo["storage_path"].rsplit(".", 1)[0] + "_printfull.jpg"
        put_object(print_path, print_bytes, "image/jpeg")
        return print_path, print_bytes
    except Exception as e:
        logger.error(f"Impossible de convertir la photo {photo.get('id')} pour l'impression : {e}")
        return None, None

def _process_photo_sync(data: bytes, content_type: str, filename: str, user_id: str, album_id: str) -> dict:
    """All the CPU/disk-bound work for one photo — EXIF, thumbnail
    generation, perceptual hash, and the two disk writes. Deliberately a
    plain synchronous function (no async, no awaits) so it can run in a
    thread executor: none of this benefits from asyncio on its own, and
    running it inline on the event loop was blocking every other request
    (and every other photo in the same batch) for its entire duration."""
    ext = (filename or "img.jpg").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    photo_id = str(uuid.uuid4())
    path = f"{APP_NAME}/users/{user_id}/albums/{album_id}/{photo_id}.{ext}"
    exif_info = extract_exif_info(data)
    result, thumb_path, img_w, img_h = store_image_with_thumbnail(path, data, content_type)

    return {
        "photo_id": photo_id,
        "storage_path": result["path"],
        "thumbnail_path": thumb_path,
        "size": result.get("size", len(data)),
        "width": img_w,
        "height": img_h,
        "taken_at": exif_info["taken_at"],
        "gps_lat": exif_info["gps_lat"],
        "gps_lng": exif_info["gps_lng"],
        "phash": ahash_to_str(compute_ahash(data)),
    }

async def store_new_photo(album_id: str, user_id: str, filename: str, content_type: str, data: bytes) -> Optional[dict]:
    """Shared logic to persist one photo (bytes already in hand) as a Photo
    document — used by the normal upload endpoint, the phone QR upload, and
    the Google Photos import, so all three go through the exact same
    EXIF/hash/storage pipeline."""
    if content_type not in ALLOWED_MIME:
        # Previously a silent return — a photo rejected here (an
        # unsupported format: a GIF, a video misselected alongside real
        # photos, an unusual MIME type Google's Motion Photos sometimes
        # report) left zero trace anywhere. Someone reporting "3 of 1102
        # failed" had nothing to search the logs for — not "Échec du
        # téléchargement" (that's a Google-fetch failure), not "Upload
        # failed" (that's a processing failure after a successful
        # download) — because neither of those code paths was the one
        # that actually ran.
        logger.warning(f"Photo '{filename}' ignorée : type MIME non supporté ({content_type})")
        return None
    if len(data) == 0:
        logger.warning(f"Photo '{filename}' ignorée : fichier vide")
        return None
    loop = asyncio.get_event_loop()
    # Retried up to 3 times, same shape as the Google Photos import's own
    # retry (see import_google_photos_items) — a transient hiccup (an R2
    # write that times out under load, especially the exact CPU contention
    # this whole pool of fixes is about) is far more likely than a
    # genuinely corrupt file, and a corrupt file fails fast here (no R2
    # call even attempted) so retrying it costs almost nothing. Previously
    # any single failure here — transient or not — silently dropped that
    # one photo for good, which is very plausibly why "some photos just
    # fail" got worse specifically when a PDF generation was also
    # underway: more contention meant more of these transient failures,
    # each with no second chance.
    last_error = None
    for attempt in range(3):
        try:
            processed = await loop.run_in_executor(photo_processing_executor, _process_photo_sync, data, content_type, filename, user_id, album_id)
            break
        except Exception as e:
            last_error = e
            if attempt < 2:
                await asyncio.sleep(1.0 * (attempt + 1))  # 1s, then 2s
    else:
        logger.error(f"Upload failed for {filename} after 3 attempts: {last_error}")
        return None
    photo_doc = {
        "id": processed["photo_id"],
        "album_id": album_id,
        "user_id": user_id,
        "storage_path": processed["storage_path"],
        "thumbnail_path": processed["thumbnail_path"],
        "original_filename": filename,
        "content_type": content_type,
        "size": processed["size"],
        "width": processed["width"],
        "height": processed["height"],
        "ai_score": None,
        "ai_description": None,
        "ai_group": None,
        "ai_is_reject": False,
        "ai_focal_x": 0.5,
        "ai_focal_y": 0.5,
        "taken_at": processed["taken_at"],
        "gps_lat": processed["gps_lat"],
        "gps_lng": processed["gps_lng"],
        "phash": processed["phash"],
        "is_selected": True,
        "is_duplicate": False,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.photos.insert_one(photo_doc)
    photo_doc.pop("_id", None)
    return photo_doc

# The AI curation step (curate_photos, via run_ai_processing) queries with
# .to_list(5000) — anything beyond that was previously silently invisible
# to curation, with no indication to the person that some of what they
# uploaded would never actually be considered. Enforced here instead, at
# the point every upload path already funnels through, with a real error
# telling them the limit outright rather than a batch that "succeeds" but
# quietly does less than they asked.
MAX_PHOTOS_PER_ALBUM = 5000

async def store_many_photos(album_id: str, user_id: str, files: List[UploadFile]) -> List[dict]:
    """Reads then stores a batch of uploaded files concurrently (bounded by
    UPLOAD_CONCURRENCY), skipping any that fail validation or processing.
    Shared by every endpoint that accepts photo uploads. Files are read here
    (must happen on the main loop — UploadFile isn't safe to touch from a
    worker thread), but everything CPU/disk-bound after that runs
    concurrently, bounded so a huge batch doesn't spawn hundreds of threads
    at once.

    Raises HTTPException(400) outright if this album is already at (or this
    batch would push it past) MAX_PHOTOS_PER_ALBUM — the caller doesn't need
    its own check, and the person gets a real, specific reason rather than
    photos that silently uploaded but were never actually usable."""
    current_count = await db.photos.count_documents({"album_id": album_id, "is_deleted": False})
    if current_count >= MAX_PHOTOS_PER_ALBUM:
        raise HTTPException(status_code=400, detail=f"This album already has {current_count} photos, the maximum of {MAX_PHOTOS_PER_ALBUM} per album. Remove some before adding more.")
    room_left = MAX_PHOTOS_PER_ALBUM - current_count
    truncated = len(files) > room_left
    files = files[:room_left]

    file_bytes = [(f.filename, f.content_type or "image/jpeg", await f.read()) for f in files]
    semaphore = asyncio.Semaphore(UPLOAD_CONCURRENCY)

    async def store_one(filename, content_type, data):
        async with semaphore:
            return await store_new_photo(album_id, user_id, filename, content_type, data)

    # return_exceptions=True is the point: without it, one bad file in the
    # batch (a corrupt image, an unsupported format, a transient R2 hiccup)
    # makes gather raise immediately, discarding every other file in the
    # *same batch* that had already succeeded or was about to — the
    # opposite of what this docstring promises. A mobile upload of e.g. 29
    # photos, sent in chunks of 6, could genuinely lose an entire chunk to
    # a single bad file this way while looking like nothing went wrong.
    results = await asyncio.gather(*(store_one(fn, ct, d) for fn, ct, d in file_bytes), return_exceptions=True)
    stored = []
    for (filename, _, _), result in zip(file_bytes, results):
        if isinstance(result, Exception):
            logger.warning(f"Échec du stockage de la photo '{filename}' pour l'album {album_id}: {result}")
        elif result:
            stored.append(result)
    if truncated:
        # Not raised as an exception — this batch is a genuine partial
        # success (whatever fit under the cap really was stored), the
        # caller just needs to know so it can tell the person the rest
        # didn't make it in, and why.
        logger.warning(f"Album {album_id}: lot tronqué à {room_left} photos pour respecter la limite de {MAX_PHOTOS_PER_ALBUM}")
    return stored, truncated
