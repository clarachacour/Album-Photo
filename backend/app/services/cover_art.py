"""Template logos and icons stored inside albums.

Albums keep a copy of their template's logos in their cover. They used to be
embedded images (data: URIs, up to 170 KB each), resent with every save and
with every album of the "My albums" list. They are now files served by the
site (frontend/public/cover-art); older albums get the file's address instead
of their embedded copy the first time they're read (see slim_cover).
"""
import hashlib

# sha256 of the embedded image → the same image as a file.
_BY_HASH = {
    "2718dfed1a170619e401461be320dbb072b7c33ce2ec7ffd0a8b2ec146f6d0d1": "/cover-art/rings-logo-v1.webp",
    "117f91aafdfe0d7abf561056d239d7b8f3d6c431230d7c9c15b5829a9fc92ea7": "/cover-art/heart-logo-v1.webp",
    "5a328ddff584e962594d40f8991764d2bf157a845643938358e0c3fca798689f": "/cover-art/mom-heart-logo-v1.webp",
    "3558ea8bf85e84d0b78a0ca434b98c7cc17e71c25b08c00ced9a33b09b14a9c2": "/cover-art/dad-compass-logo-v1.webp",
    "8e3420484a2738fad1e0c87b8333ce4867e0b61dcc5c8daf1799262a3ae144a4": "/cover-art/ouryear-rings-logo-v1.webp",
    "3dd5e6713f1541fddb1d08b0cdec3474853206d6db88b9e62fe1bf561fc16846": "/cover-art/travel-sicily-v1.svg",
    "73c96ea606276011019c8ea466edd283895ef66000356de102c7138066f5598a": "/cover-art/travel-hawaii-v1.svg",
    "a811a2c1633c676115bb6a67b67c3d9cd49ba01eea5a1f8f139af2c975eb234a": "/cover-art/travel-thailand-v1.svg",
    "59bb8f3cb339d47972be2170ac789fbe4bbb706d86235c84ae46772e31073298": "/cover-art/travel-paros-v1.svg",
    "a456f34469c0b024358680e1202a3aa4fd8af0fd470b9f439e16867ad618d561": "/cover-art/travel-morocco-v1.svg",
    "0ed23ddc3bb61a5bc73716f16e2a575d691414509643dce94b9788bc2c132a42": "/cover-art/travel-australia-v1.svg",
    "178e862ec3de2ea61d80d59c68f792db84b75331691ac050f3bf2eb270bc75d6": "/cover-art/travel-barcelona-v1.svg",
    "a0b750a6222294e6bdc0a7f0cfeb7b1d383da561ffff98fa098528f3a4c1057e": "/cover-art/coral-logo-v1.webp",
}

# Older versions of the spine logos, recognised by their start (the same
# list as LEGACY_SPINE_LOGOS in frontend/src/lib/coverThemes.js).
_BY_PREFIX = [
    ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGcAAABMCAYAAABwKqkMAABYGUlEQVR42k39e5RdZ3kmiD/ffe999rnU/aqqkqpkCSQQicDqxg", "/cover-art/heart-logo-v1.webp"),
    ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADoAAAA4CAYAAACsc+sjAAAf+UlEQVR42j276Y4cWZqe+ZzVNt9iZwS3JJNLbrV0t9SNqdbM/B", "/cover-art/mom-heart-logo-v1.webp"),
    ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEwAAABLCAYAAADakmGTAAA3jklEQVR42lW8Z49lV5qd+Wxz/PXh00dGpCOTSSZdsYqsYjk5SE", "/cover-art/dad-compass-logo-v1.webp"),
    ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEkAAAA6CAYAAAD8xXSzAAAg5UlEQVR42m2caZMjuXaenwMgFyb3YlX1NiNbEQ7JEf7/f0SydM", "/cover-art/ouryear-rings-logo-v1.webp"),
    ("data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%20100%20100%22%3E%3Cpath%20transform%3D%22rotate(84", "/cover-art/mom-heart-logo-v1.webp"),
]


# Files redrawn since: the old address → the new file. The travel icons were
# traced from small pictures, into straight segments on a whole-unit grid
# that looked pixelated in a zoomed PDF; v2 has the same drawing in smooth
# curves. A file is never changed in place (browsers keep it for a year).
_REDRAWN = {
    f"/cover-art/travel-{name}-v1.svg": f"/cover-art/travel-{name}-v2.svg"
    for name in ("sicily", "hawaii", "thailand", "paros", "morocco", "barcelona")
}


def _embedded_file(value):
    url = _BY_HASH.get(hashlib.sha256(value.encode()).hexdigest())
    if url:
        return url
    for prefix, url in _BY_PREFIX:
        if value.startswith(prefix):
            return url
    return value


def slim_image(value):
    """The file address for one of our embedded logos (its latest drawing);
    anything else as is."""
    if not isinstance(value, str):
        return value
    if value.startswith("data:image/"):
        value = _embedded_file(value)
    return _REDRAWN.get(value, value)


def slim_cover(cover):
    """(cover, changed): the cover with its embedded logos replaced by their
    file address — the spine logo, and every image placed on the front or
    back cover."""
    if not isinstance(cover, dict):
        return cover, False
    slim = dict(cover)
    changed = False
    if "spine_logo_image" in slim:
        new = slim_image(slim["spine_logo_image"])
        changed |= new != slim["spine_logo_image"]
        slim["spine_logo_image"] = new
    for key in ("extra_items", "back_extra_items"):
        items = slim.get(key)
        if not isinstance(items, list):
            continue
        new_items = []
        for item in items:
            if isinstance(item, dict) and "image_url" in item:
                new = slim_image(item["image_url"])
                if new != item["image_url"]:
                    item = {**item, "image_url": new}
                    changed = True
            new_items.append(item)
        slim[key] = new_items
    return (slim, True) if changed else (cover, False)
