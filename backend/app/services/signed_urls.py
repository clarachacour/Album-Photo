"""Temporary direct links to photos in R2 (S3 "presigned" URLs).

The browser loads each photo straight from Cloudflare instead of through
our server: faster (Cloudflare serves it from nearby, which matters on a
Lebanese connection), and the server no longer downloads and resends every
image. A link opens only its own file and stops working after
LINK_VALIDITY; it replaces the sign-in key that image addresses used to
carry.

Links are signed with a start time rounded down to the day, so the same
photo has the same address all day long and the browser's cache keeps
working. Signed here with the standard AWS signature (version 4) rather
than through boto3, which takes far too long for an album of thousands of
photos.
"""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

from app.config import R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET_NAME, R2_SECRET_ACCESS_KEY
from app.services.photos import print_needs_conversion

# 7 days is the longest a signed link can last. Since links start at the
# beginning of the day, one handed out is still good for at least 6 days.
LINK_VALIDITY = timedelta(days=7)
CACHE_CONTROL = "private, max-age=604800, immutable"
REGION = "auto"
SERVICE = "s3"


def enabled() -> bool:
    return bool(R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME)


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


_key_cache: dict = {}


def _signing_key(date: str) -> bytes:
    key = _key_cache.get(date)
    if key is None:
        key = _hmac(_hmac(_hmac(_hmac(f"AWS4{R2_SECRET_ACCESS_KEY}".encode(), date), REGION), SERVICE), "aws4_request")
        _key_cache.clear()
        _key_cache[date] = key
    return key


def _encode(value: str, safe: str = "") -> str:
    return quote(value, safe="-_.~" + safe)


def window_start(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def signed_url(path: str, start: Optional[datetime] = None) -> str:
    """A link to this R2 file, valid from `start` (default: today at
    midnight UTC) for LINK_VALIDITY."""
    start = start or window_start()
    date = start.strftime("%Y%m%d")
    amz_date = start.strftime("%Y%m%dT%H%M%SZ")
    host = f"{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    canonical_path = f"/{_encode(R2_BUCKET_NAME)}/{_encode(path, '/')}"
    scope = f"{date}/{REGION}/{SERVICE}/aws4_request"
    params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{R2_ACCESS_KEY_ID}/{scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(int(LINK_VALIDITY.total_seconds())),
        "X-Amz-SignedHeaders": "host",
        "response-cache-control": CACHE_CONTROL,
    }
    query = "&".join(f"{_encode(k)}={_encode(v)}" for k, v in sorted(params.items()))
    canonical_request = f"GET\n{canonical_path}\n{query}\nhost:{host}\n\nhost\nUNSIGNED-PAYLOAD"
    string_to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    signature = hmac.new(_signing_key(date), string_to_sign.encode(), hashlib.sha256).hexdigest()
    return f"https://{host}{canonical_path}?{query}&X-Amz-Signature={signature}"


def _print_path(photo: dict) -> Optional[str]:
    # Same choice as get_photo_image's "print" variant: the full-resolution
    # file, or its JPEG copy for formats browsers can't draw (HEIC…).
    if not print_needs_conversion(photo):
        return photo.get("storage_path")
    return photo.get("print_full_path")


def photo_urls(photo: dict, start: Optional[datetime] = None) -> Optional[dict]:
    """Direct links to the photo's sizes that already exist. A size not
    made yet (the "medium" one is made the first time it's shown) is left
    out: the page then asks our server, which makes it."""
    if not enabled():
        return None
    start = start or window_start()
    paths = {
        "thumb": photo.get("thumbnail_path"),
        "medium": photo.get("medium_path"),
        "print": _print_path(photo),
    }
    urls = {variant: signed_url(path, start) for variant, path in paths.items() if path}
    if not urls:
        return None
    urls["expires_at"] = (start + LINK_VALIDITY).isoformat()
    return urls
