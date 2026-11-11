"""Which file the printer gets (chosen in the admin):

- "bookstop": the original layout — spine and front cover on the first
  sheet, the pages, the back cover on the last sheet.
- "hardcover": the one-sheet hardcover format (Template_A4_1-50pgs, for
  every format and page count) — the cover on one sheet with its wrap and
  crop marks, then each page with a bleed and crop marks, on white.

The print page draws either (PrintAlbum.jsx, ?format=hardcover)."""
from app.db import db

FORMATS = ("bookstop", "hardcover")
DEFAULT_FORMAT = "bookstop"


async def get_print_format() -> str:
    doc = await db.app_state.find_one({"id": "print_format"}, {"_id": 0, "value": 1})
    value = (doc or {}).get("value")
    return value if value in FORMATS else DEFAULT_FORMAT


async def set_print_format(value: str) -> str:
    if value not in FORMATS:
        raise ValueError(value)
    await db.app_state.update_one({"id": "print_format"}, {"$set": {"id": "print_format", "value": value}}, upsert=True)
    return value


def print_url_suffix(print_format: str, digital: bool) -> str:
    """What the print page's address gets for this format."""
    if digital:
        return "&digital=1"
    return "&format=hardcover" if print_format == "hardcover" else ""
