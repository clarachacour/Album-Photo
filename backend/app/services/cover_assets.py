"""Images added to a cover (a photo frame, a logo replaced by a photo).

They can come from the computer, from the phone that scanned the QR code,
from Google Photos or from the album's own photos: all are stored the same
way, with the album owner's files, at print quality."""
import uuid

from fastapi import HTTPException

from app.config import APP_NAME
from app.core.executors import run_blocking
from app.services.photos import ALLOWED_MIME, cover_photo_quality, guess_image_type, store_image_with_thumbnail

_EXTENSIONS = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp"}


async def store_cover_asset(album: dict, filename: str, content_type: str, data: bytes) -> dict:
    """Stores one image for the album's cover; returns what the cover item
    keeps (storage_path, thumbnail_path, photo_width, photo_height,
    brightness)."""
    # Some computers (Windows) and phones give an iPhone photo no type: its
    # file name says what it is.
    content_type = guess_image_type(filename, content_type or "")
    if content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Unsupported image format")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    # HEIC and other formats are stored as JPEG (see store_image_with_thumbnail).
    ext = _EXTENSIONS.get(content_type, "jpg")
    # Kept with the album owner's files (the admin may be adding it to a
    # customer's cover): the print page, which opens the album as its owner,
    # can then read it.
    path = f"{APP_NAME}/users/{album['user_id']}/albums/{album['id']}/cover-assets/{uuid.uuid4()}.{ext}"
    result, thumb_path, _, _ = await run_blocking(store_image_with_thumbnail, path, data, content_type)
    # Its size in pixels and how light it is, kept on the cover item: the
    # editor and the order page warn when it may print blurry or dark, as
    # for the photos inside the album.
    quality = await run_blocking(cover_photo_quality, data)
    return {"storage_path": result["path"], "thumbnail_path": thumb_path, **quality}
