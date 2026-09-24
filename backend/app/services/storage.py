"""File storage on Cloudflare R2 (S3-compatible)."""
import logging
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from fastapi import HTTPException

from app.config import (
    R2_ACCESS_KEY_ID,
    R2_ACCOUNT_ID,
    R2_BUCKET_NAME,
    R2_SECRET_ACCESS_KEY,
)

logger = logging.getLogger(__name__)


# --------- Storage helpers (Cloudflare R2 — S3-compatible object storage) ----------
# Files never live on the app server's own disk: uploads/thumbnails/PDFs go
# straight to R2, which is durable, cheap, and independent of whichever
# machine happens to be running the backend at any given moment (important
# since Render's free/starter instances don't guarantee the same disk
# across redeploys or restarts).

_r2_client = None

def get_r2_client():
    global _r2_client
    if _r2_client is None:
        if not (R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY):
            raise RuntimeError(
                "R2 storage is not configured — set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME in the environment."
            )
        _r2_client = boto3.client(
            "s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            # max_pool_connections defaults to 10, but r2_io_executor (see
            # below) runs up to 32 R2 calls concurrently — past 10 at once,
            # urllib3 was opening a fresh connection per call and
            # discarding it right after ("Connection pool is full,
            # discarding connection" in the logs) instead of reusing a
            # pooled one, paying a new TCP/TLS handshake every time for no
            # reason. Not a functional bug — every request still completed
            # — just wasted latency under real concurrent load (e.g. a
            # large album's chunk render fetching many photos at once).
            config=BotoConfig(signature_version="s3v4", max_pool_connections=32),
            region_name="auto",
        )
    return _r2_client

def init_storage() -> Optional[str]:
    """Verifies R2 is reachable and the bucket exists at startup, so a
    misconfiguration is caught immediately in the logs rather than on the
    first photo upload."""
    try:
        get_r2_client().head_bucket(Bucket=R2_BUCKET_NAME)
        return "r2_storage_active"
    except Exception as e:
        logger.error(f"R2 storage is not reachable at startup: {e}")
        return None

def put_object(path, data, content_type=None):
    """Uploads bytes to R2 and returns a dict with the path and size —
    same shape as the old local-disk version, so every caller is unaffected."""
    get_r2_client().put_object(
        Bucket=R2_BUCKET_NAME,
        Key=path,
        Body=data,
        ContentType=content_type or "application/octet-stream",
    )
    return {"path": path, "size": len(data)}

def get_object(path: str) -> tuple:
    """Downloads bytes from R2 — same (content, content_type) return shape
    as the old local-disk version."""
    try:
        resp = get_r2_client().get_object(Bucket=R2_BUCKET_NAME, Key=path)
    except Exception:
        raise HTTPException(status_code=404, detail="Image non trouvée")
    content = resp["Body"].read()
    content_type = resp.get("ContentType") or "image/jpeg"
    return content, content_type

def delete_object(path: str) -> None:
    """Deletes one object from R2. Never raises — a missing/already-deleted
    object is not an error for a cleanup operation, and callers (order-time
    cleanup, the 30-day draft purge) run in bulk and shouldn't abort the
    whole batch over one object that's already gone."""
    if not path:
        return
    try:
        get_r2_client().delete_object(Bucket=R2_BUCKET_NAME, Key=path)
    except Exception as e:
        logger.debug(f"Impossible de supprimer {path} de R2 (probablement déjà supprimé) : {e}")
