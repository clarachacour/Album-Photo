"""Photo analysis and curation: EXIF, duplicates, sharpness, faces."""
import asyncio
import base64
import json
import logging
import math
import threading
import time as _time
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional

import numpy as np
import requests
from PIL import ExifTags, Image

from app.config import BASE_DIR, GEMINI_API_KEY, GEMINI_CONCURRENCY, GEMINI_MODEL
from app.core.executors import r2_io_executor
from app.db import db
from app.services.storage import get_object

logger = logging.getLogger(__name__)


# ---------- AI Processing ----------
def _rational_to_float(r):
    # A GPS EXIF rational with a zero denominator (some phones write this
    # for an undefined/unlocked GPS component, e.g. altitude) doesn't raise
    # here — float division by zero returns inf/nan silently in Python
    # rather than throwing, so the except branch below never catches it.
    # That poisoned inf/nan then flows straight through the lat/lng
    # calculation into the stored photo doc, and later blows up
    # `json.dumps` ("Out of range float values are not JSON compliant")
    # the next time that photo is serialized in an API response — which
    # is nearly always on a phone-camera photo specifically, since those
    # are the ones far more likely to carry live GPS EXIF at all.
    try:
        val = float(r)
    except Exception:
        try:
            val = 0.0 if r[1] == 0 else r[0] / r[1]
        except Exception:
            return 0.0
    return val if math.isfinite(val) else 0.0


def extract_exif_info(data: bytes) -> dict:
    """Best-effort extraction of capture date and GPS coordinates from EXIF.
    Returns {"taken_at": iso_str|None, "gps_lat": float|None, "gps_lng": float|None}.
    Missing/corrupt EXIF is common (screenshots, edited photos) — fails silently."""
    info = {"taken_at": None, "gps_lat": None, "gps_lng": None}
    try:
        img = Image.open(BytesIO(data))
        exif = img.getexif()
        if not exif:
            return info
        tags = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
        exif_ifd = exif.get_ifd(0x8769) if hasattr(exif, "get_ifd") else {}
        exif_ifd_tags = {ExifTags.TAGS.get(k, k): v for k, v in (exif_ifd or {}).items()}
        raw_dt = tags.get("DateTime") or exif_ifd_tags.get("DateTimeOriginal") or exif_ifd_tags.get("DateTimeDigitized")
        if raw_dt:
            try:
                info["taken_at"] = datetime.strptime(raw_dt, "%Y:%m:%d %H:%M:%S").isoformat()
            except Exception:
                pass
        gps_ifd = exif.get_ifd(0x8825) if hasattr(exif, "get_ifd") else {}
        if gps_ifd:
            gps = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
            lat, lat_ref = gps.get("GPSLatitude"), gps.get("GPSLatitudeRef")
            lng, lng_ref = gps.get("GPSLongitude"), gps.get("GPSLongitudeRef")
            if lat and lng:
                lat_val = _rational_to_float(lat[0]) + _rational_to_float(lat[1]) / 60 + _rational_to_float(lat[2]) / 3600
                lng_val = _rational_to_float(lng[0]) + _rational_to_float(lng[1]) / 60 + _rational_to_float(lng[2]) / 3600
                if lat_ref == "S":
                    lat_val = -lat_val
                if lng_ref == "W":
                    lng_val = -lng_val
                # Belt and suspenders on top of _rational_to_float's own
                # finiteness check — nothing non-finite should ever reach
                # json.dumps from here.
                if math.isfinite(lat_val) and math.isfinite(lng_val):
                    info["gps_lat"] = round(lat_val, 6)
                    info["gps_lng"] = round(lng_val, 6)
    except Exception as e:
        logger.debug(f"EXIF extraction failed: {e}")
    return info


def compute_ahash(data: bytes) -> Optional[int]:
    """64-bit average hash (aHash) for near-duplicate detection. Two photos
    with a small Hamming distance between hashes are visually near-identical
    (same burst, same framing) — used to find real duplicates deterministically,
    on top of what the AI itself flags."""
    try:
        img = Image.open(BytesIO(data))
        img.draft("L", (32, 32))  # decode near the target size directly, not full-resolution
        img = img.convert("L").resize((8, 8), Image.LANCZOS)
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p >= avg else "0" for p in pixels)
        return int(bits, 2)
    except Exception as e:
        logger.debug(f"Hash computation failed: {e}")
        return None


def ahash_to_str(h: Optional[int]) -> Optional[str]:
    """MongoDB/BSON only supports signed 64-bit ints — our 64-bit average
    hash is unsigned and can exceed that range, so it's stored as a fixed
    16-char hex string instead."""
    return f"{h:016x}" if h is not None else None


def compute_sharpness(data: bytes) -> float:
    """Cheap, no-AI focus/sharpness estimate (Laplacian variance on a small
    grayscale version) — used to pick the best frame out of a burst/cluster
    of near-duplicates cheaply and locally, no external service call needed.
    Higher = sharper. Purely classical image processing, near-instant."""
    try:
        with Image.open(BytesIO(data)) as img:
            img.draft("L", (256, 256))
            small = img.convert("L").resize((256, 256), Image.LANCZOS)
            arr = np.asarray(small, dtype=np.float64)
            # Simple discrete Laplacian kernel (edge/detail response)
            lap = (
                -4 * arr
                + np.roll(arr, 1, axis=0) + np.roll(arr, -1, axis=0)
                + np.roll(arr, 1, axis=1) + np.roll(arr, -1, axis=1)
            )
            result = float(lap.var())
            if not math.isfinite(result):
                return 0.0
            return result
    except Exception:
        return 0.0

# Loaded once at first use, not per-photo — cv2's model loading has real
# overhead, and this module-level cache means every subsequent photo just
# reuses the already-loaded network. None means "not yet attempted";
# False means "attempted and failed" (e.g. the model file is missing),
# so we don't keep retrying a load that's never going to succeed.
_face_detector = None
_face_detector_load_failed = False
# OpenCV's DNN backend (which FaceDetectorYN uses under the hood) is NOT
# safe to call concurrently from multiple threads on the same network
# object — doing so anyway (photos were being face-detected several at a
# time via asyncio.gather + run_in_executor, i.e. real OS threads, all
# sharing the one _face_detector instance above) caused a native memory
# corruption crash ("double free or corruption", SIGABRT) that took down
# the entire server process, not just the one request — a plain Python
# try/except can't catch or contain that, since it happens below the
# Python interpreter entirely. This lock serializes every detect() call
# so only one ever runs at a time; YuNet is fast enough (milliseconds per
# photo) that this isn't a meaningful bottleneck even for a large album.
_face_detector_lock = threading.Lock()

def _get_face_detector():
    global _face_detector, _face_detector_load_failed
    if _face_detector is not None or _face_detector_load_failed:
        return _face_detector
    try:
        import cv2
        model_path = str(BASE_DIR / "face_detection_yunet.onnx")
        # input size is set per-image in compute_face_focal_point (it must
        # match the actual decoded image dimensions), (0, 0) here is just a
        # placeholder until the first real call.
        _face_detector = cv2.FaceDetectorYN.create(model_path, "", (0, 0), score_threshold=0.7)
    except Exception as e:
        logger.warning(f"Détecteur de visages indisponible (le recadrage se rabattra sur le centre de l'image) : {e}")
        _face_detector_load_failed = True
    return _face_detector

def compute_face_focal_point(data: bytes):
    """Finds faces in a photo and returns a (focal_x, focal_y) point — in
    the same 0-1, top-left-origin coordinate space the layout already uses
    for ai_focal_x/ai_focal_y — positioned so a crop centered on it keeps
    every detected face inside frame, rather than the raw geometric center
    of the photo (which is what got people's heads cropped off when they
    weren't centered in the original shot). Runs entirely locally via
    OpenCV's YuNet model — no photo or photo data is sent anywhere outside
    this server for this. Returns None (caller falls back to center) if no
    faces are found, or if the model isn't available for any reason."""
    detector = _get_face_detector()
    if detector is None:
        return None
    try:
        import cv2
        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        if h == 0 or w == 0:
            return None
        # YuNet's accuracy/speed trade-off is tuned around a few hundred
        # pixels on the long side — shrinking a large original down to that
        # before detection costs nothing in the result (faces are still
        # easily resolvable) and meaningfully cuts inference time.
        MAX_DETECT_SIDE = 640
        scale = min(1.0, MAX_DETECT_SIDE / max(h, w))
        detect_img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale)))) if scale < 1.0 else img
        dh, dw = detect_img.shape[:2]
        with _face_detector_lock:
            detector.setInputSize((dw, dh))
            _, faces = detector.detect(detect_img)
        if faces is None or len(faces) == 0:
            return None
        # Bounding-box centroid of every detected face, weighted by each
        # face's own area — a large, close/prominent face pulls the focal
        # point more than a tiny, distant one in the background, which is
        # usually the more important one to keep fully in frame.
        total_weight = 0.0
        sum_x, sum_y = 0.0, 0.0
        for f in faces:
            fx, fy, fw, fh = f[0], f[1], f[2], f[3]
            cx, cy = fx + fw / 2, fy + fh / 2
            weight = max(1.0, fw * fh)
            sum_x += cx * weight
            sum_y += cy * weight
            total_weight += weight
        if total_weight <= 0:
            return None
        # OpenCV's detection results are numpy scalars (np.float32), not
        # plain Python floats — MongoDB's BSON encoder has no idea how to
        # store those and raises on the very first save, which was
        # crashing the whole AI processing step (and leaving the album
        # with no pages at all) any time a face was actually detected.
        focal_x = float(min(1.0, max(0.0, (sum_x / total_weight) / dw)))
        focal_y = float(min(1.0, max(0.0, (sum_y / total_weight) / dh)))
        return (focal_x, focal_y)
    except Exception as e:
        logger.debug(f"Détection de visages échouée pour une photo (on garde le centre par défaut) : {e}")
        return None

def hamming_distance(a, b) -> int:
    if a is None or b is None:
        return 64  # unknown hash → treat as "not the same photo"
    ai = int(a, 16) if isinstance(a, str) else a
    bi = int(b, 16) if isinstance(b, str) else b
    return bin(ai ^ bi).count("1")


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two GPS points, in kilometers."""
    from math import atan2, cos, radians, sin, sqrt
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def cluster_by_location(photos: List[dict], threshold_km: float = 1.5) -> List[List[dict]]:
    """Greedily groups photos taken close to each other (same venue / same
    stop on the trip) using their GPS coordinates. Each photo must already
    have gps_lat/gps_lng set."""
    clusters: List[dict] = []  # {"lat": float, "lng": float, "photos": [...]}
    for p in photos:
        placed = False
        for c in clusters:
            if haversine_km(p["gps_lat"], p["gps_lng"], c["lat"], c["lng"]) <= threshold_km:
                n = len(c["photos"]) + 1
                c["lat"] = (c["lat"] * (n - 1) + p["gps_lat"]) / n
                c["lng"] = (c["lng"] * (n - 1) + p["gps_lng"]) / n
                c["photos"].append(p)
                placed = True
                break
        if not placed:
            clusters.append({"lat": p["gps_lat"], "lng": p["gps_lng"], "photos": [p]})
    return [c["photos"] for c in clusters]

AMBIGUOUS_CLUSTER_MIN_SIZE = 2  # even a 2-photo cluster is worth a check — low-detail scenes (water, sky, sunsets) can hash close enough to merge as "duplicates" while being genuinely different photos
AMBIGUOUS_MAX_DISTANCE_FOR_CONFIDENT_MATCH = 2  # only near-pixel-identical skips the AI call now — 4 was letting genuinely-different low-detail scenes (water, sky) through as "obviously the same" unchecked

async def _resolve_ambiguous_cluster_with_ai(cluster: List[dict]) -> List[List[dict]]:
    """Asks Gemini whether the photos in a classically-merged cluster are
    really the same photographed moment, or different photos that just
    look similar to a crude pixel-hash — exactly where average-hash
    comparison struggles: a wide sky, open sea, or a sunset can produce
    near-identical hashes across genuinely different shots, since the hash
    only sees a coarse 8x8 grayscale gradient, not color or real content.

    Returns a list of sub-groups (each a list of photos to treat as one
    duplicate cluster) — the classical cluster is split according to the
    AI's grouping, so multiple representatives can survive out of what
    classical matching treated as a single duplicate group. On any
    failure (no API key, network error, malformed response), returns the
    cluster unchanged as a single group — nothing about the classical
    result depends on this succeeding."""
    if not GEMINI_API_KEY or len(cluster) < 2:
        return [cluster]
    try:
        loop = asyncio.get_event_loop()
        parts = []
        for p in cluster:
            read_path = p.get("thumbnail_path") or p["storage_path"]
            data, _ = await loop.run_in_executor(r2_io_executor, get_object, read_path)
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(data).decode("ascii")}})
        prompt = (
            f"These are {len(cluster)} photos, numbered 0 to {len(cluster) - 1} in the order given. "
            "A simple image-similarity check flagged them as possible duplicates of each other. "
            "Some may genuinely be near-identical shots of the exact same moment (e.g. burst-mode "
            "frames, or the same subject photographed seconds apart). Others may just be visually "
            "similar in a generic way — for example several different sunsets, or different patches "
            "of open water or sky — without being the same photographed moment. "
            "Group the photo numbers so photos in the same group are the same shot/moment, and "
            "photos in different groups are genuinely different photos. "
            "Respond with ONLY a JSON array of arrays of integers (every number 0.."
            f"{len(cluster) - 1} must appear exactly once), e.g. [[0,1],[2],[3,4]]. No other text."
        )
        parts.append({"text": prompt})
        resp = await loop.run_in_executor(
            None,
            lambda: requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json"}},
                timeout=30,
            ),
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        # json.loads(text) was failing on roughly 6% of real calls with
        # "Extra data" — despite responseMimeType already asking Gemini for
        # strict JSON, it still occasionally appends something after the
        # actual array (whitespace-only trailing content was never the
        # issue; json.loads already tolerates that fine). raw_decode reads
        # just the first valid JSON value and hands back where it stopped,
        # instead of treating anything left over as an error — the
        # validation right below (every index present exactly once, etc.)
        # still catches a genuinely malformed or incomplete response either
        # way, so this only recovers the specific case where the real
        # answer was fine and something harmless came after it.
        groups_idx, _ = json.JSONDecoder().raw_decode(text.strip())

        seen = set()
        groups: List[List[dict]] = []
        for g in groups_idx:
            sub = []
            for idx in g:
                if not isinstance(idx, int) or idx < 0 or idx >= len(cluster) or idx in seen:
                    raise ValueError(f"Indice invalide ou dupliqué dans la réponse Gemini : {idx}")
                seen.add(idx)
                sub.append(cluster[idx])
            if sub:
                groups.append(sub)
        if seen != set(range(len(cluster))):
            raise ValueError("La réponse Gemini ne couvre pas toutes les photos du groupe")
        return groups
    except Exception as e:
        logger.warning(f"Résolution IA d'un groupe ambigu échouée (on garde le regroupement classique) : {e}")
        return [cluster]

async def curate_photos(new_photos: List[dict], existing_selected: Optional[List[dict]] = None) -> List[dict]:
    """Real duplicate/burst detection, fast local best-of-cluster selection,
    a classical sharpness quality gate on the survivors, and
    group/date/location sorting. When `existing_selected` is given
    (already-placed photos elsewhere in the album), new photos are also
    checked for duplicates against them — a new photo that matches
    something already in the album is dropped, and the pre-existing photo
    is left untouched either way. Returns (selected, stats) — selected is
    the final ordered list of NEW photos to lay out (existing photos are
    never included), stats is a dict of counts (total_in,
    duplicates_removed, low_sharpness_removed, selected) for diagnosing a
    surprising outcome after the fact."""
    existing_selected = existing_selected or []
    existing_ids = {e["id"] for e in existing_selected}
    # Phase timings, logged at the end alongside the existing counts — added
    # after a 1006-photo Google Photos import measured curation at 5m36s
    # with nothing in the logs breaking down *where* that time actually
    # went, which meant the R2-executor fix below could only be a
    # reasoned guess, not something confirmed by real data. This settles
    # that for every run from now on instead of needing to re-read code
    # and re-guess the next time something looks slow.
    _t0 = _time.monotonic()
    _phase_times: Dict[str, float] = {}

    # ---- 1. Real duplicate/burst detection (new photos vs each other AND
    # vs what's already in the album) — done BEFORE any AI call, using only
    # cheap local signals: perceptual similarity (phash) and how close
    # together in time the shots were taken. Photos taken close together in
    # time are almost certainly the same moment even if the framing/angle
    # drifted a bit (someone stepping sideways, a slightly different crop of
    # the same scene), so those get a looser similarity threshold; photos
    # with no timing signal (or taken far apart) need to look genuinely
    # closer to each other to be treated as the same shot.
    #
    # NOTE: curation_stats from a real 796-photo batch showed this step
    # responsible for 564 of 566 total removals (nearly all of them) —
    # BURST_HASH_THRESHOLD=20 on a 64-bit hash means up to 31% of the hash
    # could differ and two photos taken within 45s still got merged as
    # "the same shot", which is loose enough to catch genuinely different
    # framings/subjects photographed close together in time, not just true
    # bursts. Tightened on both axes (hash distance and time window)
    # pending a before/after comparison from curation_stats on the next
    # real batch. ----
    HASH_THRESHOLD = 8
    BURST_HASH_THRESHOLD = 12
    BURST_SECONDS = 20
    # ~50m — "standing in the same spot", a much tighter radius than
    # cluster_by_location's 1.5km (which groups whole album SECTIONS, not
    # individual shots) — used as a second anchor for the loose burst
    # threshold when two photos have GPS but no usable timestamp gap.
    MOMENT_GPS_KM = 0.05

    # Parsed once per photo up front, not on every pairwise comparison —
    # _is_match previously called datetime.fromisoformat (via
    # _parse_taken_at) twice per comparison, and the comparison count
    # itself grows with the square of the photo count (see the clustering
    # loop below), so for a large, mostly-unique batch (a well-shot travel
    # album, few real duplicates) that parsing was being redone millions
    # of times over on the exact same, unchanging string. Doesn't change
    # which photos are considered a match — same parsed value either way —
    # purely removes redundant repeated work.
    def _parse_taken_at(p):
        ts = p.get("taken_at")
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None

    taken_at_cache: Dict[str, Optional[datetime]] = {
        p["id"]: _parse_taken_at(p) for p in list(existing_selected) + list(new_photos)
    }

    def _same_spot(p, other, radius_km):
        lat1, lng1 = p.get("gps_lat"), p.get("gps_lng")
        lat2, lng2 = other.get("gps_lat"), other.get("gps_lng")
        if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
            return False
        return haversine_km(lat1, lng1, lat2, lng2) <= radius_km

    def _is_match(p, other):
        dist = hamming_distance(p.get("phash"), other.get("phash"))
        t1, t2 = taken_at_cache.get(p["id"]), taken_at_cache.get(other["id"])
        if t1 and t2 and abs((t1 - t2).total_seconds()) <= BURST_SECONDS:
            return dist <= BURST_HASH_THRESHOLD
        # No usable timestamp gap (one or both missing, or too far apart) —
        # GPS is the next-best anchor: photographed from the same spot is
        # almost as strong a same-subject signal as taken moments apart.
        if _same_spot(p, other, MOMENT_GPS_KM):
            return dist <= BURST_HASH_THRESHOLD
        return dist <= HASH_THRESHOLD

    clusters: List[List[dict]] = [[e] for e in existing_selected]
    for p in new_photos:
        placed = False
        for cluster in clusters:
            # Compare against every photo already in the cluster, not just
            # the first one added — a burst sequence can drift gradually
            # frame to frame, so the closest match may be a later member.
            if any(_is_match(p, member) for member in cluster):
                cluster.append(p)
                placed = True
                break
        if not placed:
            clusters.append([p])

    # ---- 1b. AI-assisted resolution for ambiguous clusters — targeted,
    # not universal. Only clusters where classical matching is genuinely
    # uncertain (several photos merged, without being near-pixel-identical)
    # get a single Gemini call each, asking specifically whether they're
    # really the same shot or just visually similar in a generic way. Small
    # clusters and confidently-identical ones are skipped entirely, so a
    # 795-photo album gets a handful of AI calls, not one per photo — and
    # with no GEMINI_API_KEY set, this whole step is a no-op and curation
    # stays 100% classical, same as before. Only clusters made entirely of
    # NEW photos are eligible — a cluster anchored by an already-existing
    # photo (the incremental "add more photos" case) is left as-is, since
    # splitting it would need re-deciding which split points to the
    # existing anchor, which isn't worth the complexity for that rarer
    # path. ----
    ai_clusters_resolved = 0
    ai_photos_recovered = 0
    ai_calls_attempted = 0
    if GEMINI_API_KEY:
        # Two passes instead of one: first decide, for every cluster and
        # with no awaiting at all, whether it actually needs a Gemini call
        # (cheap, local hamming-distance check) or not — then fire every
        # call that's actually needed at once, bounded by GEMINI_CONCURRENCY,
        # instead of the previous single for-loop that awaited each
        # cluster's Gemini call before even looking at the next cluster.
        # This turned out to be the real dominant cost in curation once
        # the sharpness/face-detection steps were fixed to use the R2 I/O
        # pool: measured on a real 1006-photo batch, 125 ambiguous
        # clusters took 222.6s of the 246.6s total — sequential Gemini
        # calls, each paying its own full round-trip one after another.
        needs_ai: List[List[dict]] = []
        passthrough: List[List[dict]] = []
        for cluster in clusters:
            new_in_cluster = [c for c in cluster if c["id"] not in existing_ids]
            if cluster[0]["id"] in existing_ids or len(new_in_cluster) < AMBIGUOUS_CLUSTER_MIN_SIZE:
                passthrough.append(cluster)
                continue
            max_dist = max(
                (hamming_distance(a.get("phash"), b.get("phash"))
                 for i, a in enumerate(new_in_cluster) for b in new_in_cluster[i + 1:]),
                default=0,
            )
            if max_dist <= AMBIGUOUS_MAX_DISTANCE_FOR_CONFIDENT_MATCH:
                passthrough.append(cluster)
                continue
            needs_ai.append(cluster)

        gemini_semaphore = asyncio.Semaphore(GEMINI_CONCURRENCY)

        async def _resolve_bounded(cluster):
            new_in_cluster = [c for c in cluster if c["id"] not in existing_ids]
            async with gemini_semaphore:
                return await _resolve_ambiguous_cluster_with_ai(new_in_cluster)

        all_sub_groups = await asyncio.gather(*(_resolve_bounded(c) for c in needs_ai))

        expanded_clusters: List[List[dict]] = list(passthrough)
        for sub_groups in all_sub_groups:
            ai_calls_attempted += 1
            if len(sub_groups) > 1:
                ai_clusters_resolved += 1
                ai_photos_recovered += len(sub_groups) - 1
                # Step 3b (below) re-checks visual similarity with its own,
                # cruder classical threshold — without this tag it would
                # routinely re-merge exactly what the AI just spent a call
                # confirming were genuinely different photos (e.g. two
                # different sunsets), silently undoing the AI's judgment.
                # Two photos only skip step 3b's check when they were both
                # examined in *this* AI call but landed in *different*
                # sub-groups — an AI call resolving some OTHER cluster
                # doesn't affect them.
                resolution_id = ai_calls_attempted
                for group_idx, sg in enumerate(sub_groups):
                    for p in sg:
                        p["_ai_group"] = (resolution_id, group_idx)
            expanded_clusters.extend(sub_groups)
        clusters = expanded_clusters

    _phase_times["clustering"] = _time.monotonic() - _t0

    # Diagnostic counters — surfaced via curation_stats on the album, so a
    # surprising outcome (a lot of photos going in, few pages coming out)
    # can be traced to "mostly duplicates" vs "mostly failed the sharpness
    # gate" instead of guessing.
    duplicates_removed = 0
    low_sharpness_removed = 0

    # ---- 2. Pick a representative per cluster using a fast, local,
    # no-AI sharpness check — this is what lets us skip sending every burst
    # frame locally, no external AI call needed. ----
    loop = asyncio.get_event_loop()

    async def _sharpness_of(p):
        try:
            read_path = p.get("thumbnail_path") or p["storage_path"]
            # r2_io_executor (32 workers), not the default pool — this is
            # a network fetch, mostly spent waiting, not computing; parking
            # it on the small ~8-thread default pool (shared with the CPU-
            # bound sharpness computation right below, and with face
            # detection's own fetch further down) meant the fetches
            # themselves were still the bottleneck even after parallelizing
            # this step across every cluster — same underlying pool, same
            # ~8-way ceiling regardless. Measured on a real 1006-photo
            # Google Photos import: curation alone took 5m36s with this
            # still on the default pool.
            data, _ = await loop.run_in_executor(r2_io_executor, get_object, read_path)
            return await loop.run_in_executor(None, compute_sharpness, data)
        except Exception:
            return 0.0

    representatives: List[dict] = []  # one per cluster that has at least one new photo
    rep_sharpness: Dict[str, float] = {}
    # Split first, so scoring can run across *every* cluster that needs it
    # at once — the previous version processed one cluster fully (R2 fetch
    # + sharpness compute for its photos) before even starting the next,
    # which for a large, mostly-unique batch (mostly one photo per
    # cluster) meant doing a genuinely parallelizable network+CPU workload
    # entirely sequentially. This was consistently the single largest
    # contributor to how long a big upload took to finish curating —
    # bigger than the O(n²) clustering step above it. Doesn't change which
    # photo wins each cluster or which get marked duplicate — same
    # per-cluster comparison, same result, just no longer waiting on
    # cluster A to finish before cluster B's fetch even starts.
    anchored_duplicate_ids: List[str] = []
    scoring_clusters: List[List[dict]] = []
    for cluster in clusters:
        new_in_cluster = [c for c in cluster if c["id"] not in existing_ids]
        if not new_in_cluster:
            continue  # cluster made only of pre-existing photos — nothing new here
        if cluster[0]["id"] in existing_ids:
            # An existing photo anchors this cluster — every new photo here
            # is a duplicate of it, so none of them need scoring at all.
            anchored_duplicate_ids.extend(d["id"] for d in new_in_cluster)
            duplicates_removed += len(new_in_cluster)
        else:
            scoring_clusters.append(new_in_cluster)

    if anchored_duplicate_ids:
        await db.photos.update_many({"id": {"$in": anchored_duplicate_ids}}, {"$set": {"is_duplicate": True, "is_selected": False}})

    all_candidates = [p for cluster in scoring_clusters for p in cluster]
    all_scores = await asyncio.gather(*(_sharpness_of(p) for p in all_candidates))
    score_by_id = dict(zip((p["id"] for p in all_candidates), all_scores))

    duplicate_ids_to_mark: List[str] = []
    for new_in_cluster in scoring_clusters:
        scores = [score_by_id[p["id"]] for p in new_in_cluster]
        rep, rep_score = max(zip(new_in_cluster, scores), key=lambda x: x[1])
        for d, score in zip(new_in_cluster, scores):
            if d["id"] != rep["id"]:
                duplicate_ids_to_mark.append(d["id"])
        duplicates_removed += len(new_in_cluster) - 1
        representatives.append(rep)
        rep_sharpness[rep["id"]] = rep_score

    if duplicate_ids_to_mark:
        await db.photos.update_many({"id": {"$in": duplicate_ids_to_mark}}, {"$set": {"is_duplicate": True, "is_selected": False}})

    # ---- 3. Quality gate — classical, no AI call. A genuinely broken shot
    # (severe motion blur, a finger over the lens, camera-shake) scores
    # dramatically lower on the same sharpness metric than a normal in-focus
    # photo, even accounting for scene-to-scene variation (a plain sky vs. a
    # detailed street scene) — this catches the clear failures without
    # needing semantic judgment of composition/expression, which is the
    # trade-off of not calling an AI model here. Deliberately conservative
    # (low threshold) so it only screens out unambiguous misses rather than
    # trying to rank "good" vs "great".
    #
    # NOTE: this fixed number was never calibrated against a real batch of
    # photos — a scene with naturally low local contrast (sky, water, flat
    # backgrounds) can score low on this metric even in perfect focus, so a
    # value this high risks rejecting plenty of genuinely fine photos, not
    # just broken ones. Lowered from 15.0 pending real before/after data
    # from curation_stats. ----
    SHARPNESS_FLOOR = 8.0
    selected = []
    passing_reps = []
    for rep in representatives:
        score = rep_sharpness.get(rep["id"], 0.0)
        is_reject = score < SHARPNESS_FLOOR
        rep["ai_score"] = score
        if is_reject:
            await db.photos.update_one({"id": rep["id"]}, {"$set": {"ai_score": score, "ai_is_reject": True, "is_duplicate": True, "is_selected": False}})
            low_sharpness_removed += 1
        else:
            passing_reps.append(rep)

    _phase_times["sharpness"] = _time.monotonic() - _t0 - _phase_times["clustering"]

    # Face-aware focal point — finds where any people actually are in the
    # photo (fully locally, via the OpenCV/YuNet model — nothing about the
    # photo is sent anywhere for this) so the layout can center its crop on
    # them instead of the raw geometric middle of the frame, which is what
    # was cropping people out when they weren't centered in the original
    # shot. Only computed for photos that passed the sharpness gate above —
    # no point spending the time on ones that won't be used anyway. Falls
    # back to dead center (the previous, only, behavior) for any photo with
    # no detected face — a landscape or an object shot, say.
    async def _focal_point_of(p):
        try:
            read_path = p.get("thumbnail_path") or p["storage_path"]
            # Same reasoning as _sharpness_of's fetch above.
            data, _ = await loop.run_in_executor(r2_io_executor, get_object, read_path)
            return await loop.run_in_executor(None, compute_face_focal_point, data)
        except Exception:
            return None

    focal_points = await asyncio.gather(*(_focal_point_of(p) for p in passing_reps))
    faces_detected_count = sum(1 for f in focal_points if f)
    _phase_times["face_detection"] = _time.monotonic() - _t0 - _phase_times["clustering"] - _phase_times["sharpness"]

    for rep, focal in zip(passing_reps, focal_points):
        focal_x, focal_y = focal if focal else (0.5, 0.5)
        update = {
            "ai_score": rep["ai_score"],
            "ai_is_reject": False,
            "ai_focal_x": focal_x,
            "ai_focal_y": focal_y,
            # Separate explicit flag rather than inferring "has a face" from
            # the coordinates themselves — a genuinely centered face would
            # also land on (0.5, 0.5) and be indistinguishable from "no
            # face found" if we didn't. The layout step (deterministic_layout,
            # see best_slot_assignment) uses this to prefer a well-matching
            # slot for a photo with a face over a badly-mismatched one, since
            # the slot choice itself — not just where within it the crop is
            # centered — is what determines how much has to be cropped away.
            "ai_has_face": bool(focal),
        }
        await db.photos.update_one({"id": rep["id"]}, {"$set": {**update, "is_duplicate": False, "is_selected": True}})
        rep.update(update)
        selected.append(rep)

    # ---- 3b. Visual diversity cap — catches near-identical FRAMING of the
    # same subject that step 1's stricter duplicate check correctly leaves
    # as distinct photos (different enough pixel-for-pixel to not be flagged
    # as the "same shot"), but that still reads as repetitive to a person —
    # e.g. several photos of the same wide view taken a few minutes apart
    # while wandering around one spot. Only the sharpest photo per "moment"
    # survives (MAX_PER_MOMENT=1) — the rest are dropped outright, not
    # spread elsewhere in the album, so the final album doesn't carry
    # several near-identical frames of the same subject. This also frees up
    # page space for photos from OTHER moments that would otherwise have
    # been squeezed out once the page budget ran low.
    #
    # Matching cascades through whatever signal two photos actually share —
    # date, then GPS, then visual similarity alone — instead of requiring a
    # date on both sides (the original version of this step did, which
    # meant it silently did nothing at all for photos without EXIF dates,
    # exactly the photos this cap most needed to cover). ----
    MOMENT_HASH_THRESHOLD = 16
    MOMENT_SECONDS = 300
    MOMENT_HASH_THRESHOLD_NO_ANCHOR = 10  # tighter than MOMENT_HASH_THRESHOLD — no date or GPS to corroborate, so demand a closer visual match before treating two photos as the same moment
    MAX_PER_MOMENT = 1
    redundant_removed = 0

    def _moment_match(p, other):
        # The AI already looked at these two together and explicitly said
        # "different photos" — don't let this cruder classical check
        # silently re-merge them regardless of how visually similar they
        # look.
        p_group, o_group = p.get("_ai_group"), other.get("_ai_group")
        if p_group and o_group and p_group[0] == o_group[0] and p_group[1] != o_group[1]:
            return False
        dist = hamming_distance(p.get("phash"), other.get("phash"))
        if dist > MOMENT_HASH_THRESHOLD:
            return False
        t1, t2 = _parse_taken_at(p), _parse_taken_at(other)
        if t1 and t2:
            return abs((t1 - t2).total_seconds()) <= MOMENT_SECONDS
        if _same_spot(p, other, MOMENT_GPS_KM):
            return True
        # Neither a shared date nor GPS to anchor on — fall back to visual
        # similarity alone, at a tighter threshold since there's nothing
        # else corroborating that these are really the same moment.
        return dist <= MOMENT_HASH_THRESHOLD_NO_ANCHOR

    if selected:
        moment_clusters: List[List[dict]] = []
        for p in selected:
            placed = False
            for mc in moment_clusters:
                if any(_moment_match(p, m) for m in mc):
                    mc.append(p)
                    placed = True
                    break
            if not placed:
                moment_clusters.append([p])

        thinned = []
        for mc in moment_clusters:
            if len(mc) <= MAX_PER_MOMENT:
                thinned.extend(mc)
                continue
            mc_sorted = sorted(mc, key=lambda x: -(x.get("ai_score") or 0))
            keep, drop = mc_sorted[:MAX_PER_MOMENT], mc_sorted[MAX_PER_MOMENT:]
            for d in drop:
                await db.photos.update_one({"id": d["id"]}, {"$set": {"is_duplicate": True, "is_selected": False}})
            redundant_removed += len(drop)
            thinned.extend(keep)
        selected = thinned

    # ---- 4. Group & sort (place / date priority, same rules as the initial pass) ----
    with_gps = [p for p in selected if p.get("gps_lat") is not None and p.get("gps_lng") is not None]
    with_gps_ids = {p["id"] for p in with_gps}
    without_gps = [p for p in selected if p["id"] not in with_gps_ids]

    if len(with_gps) >= max(2, len(selected) * 0.3):
        location_groups = cluster_by_location(with_gps)
        for group in location_groups:
            group.sort(key=lambda x: x.get("taken_at") or "9999-12-31")

        def group_sort_key(group):
            dated = [p.get("taken_at") for p in group if p.get("taken_at")]
            return min(dated) if dated else "9999-12-31"

        location_groups.sort(key=group_sort_key)
        selected = [p for group in location_groups for p in group]
        without_gps.sort(key=lambda x: x.get("taken_at") or "9999-12-31")
        selected.extend(without_gps)
    else:
        dated = [p for p in selected if p.get("taken_at")]
        if len(dated) >= max(1, len(selected) * 0.5):
            selected.sort(key=lambda x: x.get("taken_at") or "9999-12-31")
        else:
            selected.sort(key=lambda x: (x.get("ai_group", "zzz"), -(x.get("ai_score") or 0)))

    _phase_times["sorting_and_rest"] = _time.monotonic() - _t0 - sum(_phase_times.values())
    stats = {
        "total_in": len(new_photos),
        "duplicates_removed": duplicates_removed,
        "low_sharpness_removed": low_sharpness_removed,
        "redundant_removed": redundant_removed,
        "ai_clusters_resolved": ai_clusters_resolved,
        "ai_calls_attempted": ai_calls_attempted,
        "ai_photos_recovered": ai_photos_recovered,
        "faces_detected": faces_detected_count,
        "selected": len(selected),
        "phase_seconds": {k: round(v, 1) for k, v in _phase_times.items()},
    }
    logger.info(
        f"Curation de {len(new_photos)} photos en {_time.monotonic() - _t0:.1f}s — "
        f"clustering: {_phase_times['clustering']:.1f}s, "
        f"netteté: {_phase_times['sharpness']:.1f}s, "
        f"détection visages: {_phase_times['face_detection']:.1f}s, "
        f"reste: {_phase_times['sorting_and_rest']:.1f}s"
    )
    return selected, stats
