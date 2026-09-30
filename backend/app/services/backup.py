"""Daily backup of the database to R2 — a copy kept with another provider
than MongoDB Atlas, whatever the Atlas plan, so that no album, order or
account can be lost for good.

Each backup is a folder backups/<date>/ holding one gzipped JSON Lines file
per collection (MongoDB extended JSON: every value type comes back exactly)
and a manifest.json with the document counts. Backups older than
BACKUP_RETENTION_DAYS are deleted. The photos themselves are already
files in R2; the backup holds everything that points to them.

Restoring: scripts/restore_backup.py.
"""
import gzip
import json
import logging
from datetime import datetime, timedelta, timezone
from io import BytesIO

from bson import json_util

from app.config import BACKUP_RETENTION_DAYS
from app.db import db
from app.services.storage import delete_prefix, get_object, list_folders, put_object

logger = logging.getLogger(__name__)

PREFIX = "backups/"


async def backup_database(now: datetime = None) -> dict:
    """Writes today's backup; returns its folder and the document counts."""
    now = now or datetime.now(timezone.utc)
    folder = f"{PREFIX}{now.strftime('%Y-%m-%d')}/"
    counts = {}
    for name in sorted(await db.list_collection_names()):
        buf = BytesIO()
        count = 0
        with gzip.GzipFile(fileobj=buf, mode="wb") as out:
            async for doc in db[name].find({}):
                out.write(json_util.dumps(doc, json_options=json_util.CANONICAL_JSON_OPTIONS).encode() + b"\n")
                count += 1
        put_object(f"{folder}{name}.jsonl.gz", buf.getvalue(), "application/gzip")
        counts[name] = count
    manifest = {"created_at": now.isoformat(), "collections": counts}
    put_object(f"{folder}manifest.json", json.dumps(manifest, indent=2).encode(), "application/json")
    deleted = delete_old_backups(now)
    logger.info(f"Sauvegarde {folder} : {sum(counts.values())} documents dans {len(counts)} collections ; {len(deleted)} ancienne(s) supprimée(s)")
    return {"folder": folder, "collections": counts, "deleted_old": deleted}


def delete_old_backups(now: datetime) -> list:
    """Keeps the last BACKUP_RETENTION_DAYS days of backups (today's
    included) and deletes the older ones; returns their folders."""
    cutoff = (now - timedelta(days=BACKUP_RETENTION_DAYS - 1)).strftime("%Y-%m-%d")
    deleted = []
    for folder in list_folders(PREFIX):
        day = folder[len(PREFIX):].rstrip("/")
        if len(day) == 10 and day < cutoff:  # only our own YYYY-MM-DD folders
            delete_prefix(folder)
            deleted.append(folder)
    return deleted


def read_backup(day: str) -> dict:
    """{collection: [documents]} of the backup of that day (YYYY-MM-DD)."""
    folder = f"{PREFIX}{day}/"
    manifest = json.loads(get_object(f"{folder}manifest.json")[0])
    data = {}
    for name, count in manifest["collections"].items():
        raw = gzip.decompress(get_object(f"{folder}{name}.jsonl.gz")[0])
        docs = [json_util.loads(line) for line in raw.splitlines() if line.strip()]
        if len(docs) != count:
            raise ValueError(f"{name}: {len(docs)} documents in the file, {count} expected")
        data[name] = docs
    return data
