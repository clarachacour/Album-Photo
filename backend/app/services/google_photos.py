"""Import from Google Photos (Photos Picker API)."""
import asyncio
import logging
from urllib.parse import urlsplit

import requests
from fastapi import HTTPException

from app.config import GOOGLE_PHOTOS_CONCURRENCY
from app.db import db
from app.services.photos import MAX_PHOTOS_PER_ALBUM, store_new_photo

logger = logging.getLogger(__name__)


def is_google_photos_url(url) -> bool:
    """The download address comes from the browser: only Google's photo
    servers are fetched, never an address of the client's choosing (which
    could reach services inside our network, and would receive the
    person's Google access token)."""
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and port in (None, 443)
        and not parts.username
        and not parts.password
        and host.endswith(".googleusercontent.com")
    )


def _download(url: str, headers: dict, max_redirects: int = 3):
    """GET that follows redirects only to other Google photo servers."""
    for _ in range(max_redirects + 1):
        resp = requests.get(url, headers=headers, timeout=20, allow_redirects=False)
        if resp.status_code not in (301, 302, 303, 307, 308):
            return resp
        url = requests.compat.urljoin(url, resp.headers.get("Location", ""))
        if not is_google_photos_url(url):
            raise ValueError("redirected outside Google")
    raise ValueError("too many redirects")


async def import_google_photos_items(album_id: str, user_id: str, items: list, access_token: str) -> tuple:
    """Downloads and stores each Google Photos item chosen in the picker
    session. Shared by both the regular (logged-in) import endpoint and the
    mobile-QR-session one — the download/store logic is identical either
    way, only how the caller is authenticated differs. Returns
    (stored, limit_reached) — same MAX_PHOTOS_PER_ALBUM enforcement as
    store_many_photos, since this is a separate path into the same
    photos collection and would otherwise bypass the cap entirely."""
    current_count = await db.photos.count_documents({"album_id": album_id, "is_deleted": False})
    if current_count >= MAX_PHOTOS_PER_ALBUM:
        raise HTTPException(status_code=400, detail=f"This album already has {current_count} photos, the maximum of {MAX_PHOTOS_PER_ALBUM} per album. Remove some before adding more.")
    room_left = MAX_PHOTOS_PER_ALBUM - current_count
    limit_reached = len(items) > room_left
    items = items[:room_left]

    headers = {"Authorization": f"Bearer {access_token}"}
    # Bounded lower than UPLOAD_CONCURRENCY (a separate constant, see
    # app/config.py) — hammering Google's own servers with many
    # simultaneous connections is what caused SSLEOFError/"Max retries
    # exceeded" drops, so Google Photos downloads specifically stay
    # bounded lower regardless of how high UPLOAD_CONCURRENCY is set for
    # the unrelated device-upload path.
    semaphore = asyncio.Semaphore(GOOGLE_PHOTOS_CONCURRENCY)
    loop = asyncio.get_event_loop()

    async def fetch_one(item):
        media_file = item.get("mediaFile", {})
        base_url = media_file.get("baseUrl")
        filename = media_file.get("filename", "photo.jpg")
        if not base_url:
            logger.warning(f"Photo Google Photos '{filename}' ignorée : aucune URL fournie par l'API")
            return None
        if not is_google_photos_url(base_url):
            logger.warning(f"Photo Google Photos '{filename}' ignorée : adresse hors de Google refusée")
            return None
        # Google's servers occasionally drop the connection under
        # concurrent load (SSLEOFError / "Max retries exceeded") — this is
        # a transient network hiccup, not a real failure, and a retry
        # almost always succeeds. The semaphore is only held during the
        # actual attempt, never during the backoff sleep, so one failing,
        # retrying photo doesn't starve every other photo waiting for that
        # slot.
        last_error = None
        for attempt in range(3):
            async with semaphore:
                try:
                    img_resp = await loop.run_in_executor(
                        None, lambda: _download(f"{base_url}=d", headers)
                    )
                    if img_resp.status_code != 200:
                        # Previously returned immediately here — no retry,
                        # no log line, just silently gone. A non-200 here
                        # (429 rate-limited, 503, a transient 5xx) is
                        # exactly the kind of thing raising concurrency
                        # makes more likely to happen occasionally, and is
                        # exactly the kind of thing a retry is likely to
                        # recover from — so it now falls through to the
                        # same backoff-and-retry the except block below
                        # uses (outside the semaphore, same as that one),
                        # instead of an instant, silent giveup.
                        last_error = f"HTTP {img_resp.status_code}"
                    else:
                        content_type = img_resp.headers.get("Content-Type", "image/jpeg")
                        return await store_new_photo(album_id, user_id, filename, content_type, img_resp.content)
                except Exception as e:
                    last_error = e
            if attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))  # 1.5s, then 3s — outside the semaphore
        logger.error(f"Échec du téléchargement d'une photo Google Photos ({filename}) après 3 tentatives : {last_error}")
        return None

    results = await asyncio.gather(*(fetch_one(it) for it in items))
    return [p for p in results if p], limit_reached
