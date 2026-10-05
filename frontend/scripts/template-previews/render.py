"""Makes the template pictures of the home page and of "Choose a template"
(public/theme-covers/<template id>.webp) from the real templates: each cover
is drawn by the site itself (the PDF's print page), then its spine and front
are laid out the same way for every template — same book size, same place,
same shadow.

    cd frontend
    npm run build
    node scripts/template-previews/templates.mjs > /tmp/templates.json
    python scripts/template-previews/render.py /tmp/templates.json

Photo frames of a template are filled with the free photos in photos/ (see
photos/CREDITS.md), in the order photos.json gives for that template.
Needs Python's playwright and Pillow, and Google Fonts reachable (CHROMIUM=
<path> picks the browser).
"""
import io
import os
import json
import mimetypes
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FRONTEND = HERE.parents[1]
BUILD = FRONTEND / "build"
OUT = FRONTEND / "public" / "theme-covers"
PHOTOS = HERE / "photos"
ORIGIN = "http://preview.local"

# The picture: 3:4, shown at up to 192 px wide (×2 for sharp screens, ×1.25 spare).
W, H = 480, 640
SCALE = 2  # rendered at twice the size, then reduced: smoother edges
BOOK_H = 0.72  # the front cover's height, share of the picture's
GAP = 0.025  # between spine and front, share of the picture's width
PAGES = 40  # page count the spine width is based on


def album_for(t, photo_files):
    cover = json.loads(json.dumps(t["cover"]))
    slots = [it for it in cover["extra_items"] if it.get("is_photo")]
    for it, name in zip(slots, photo_files):
        it["image_url"] = f"/preview-photos/{name}"
        with Image.open(PHOTOS / name) as im:
            it["photo_aspect"] = im.width / im.height
    return {
        "id": "preview",
        "user_id": "preview",
        "title": t["title"],
        "cover_template_id": t["id"],
        "size": "A4",
        "orientation": "portrait",
        "status": "ready",
        "version": 0,
        "country": "",
        "cover": cover,
        "pages": [{"id": f"p{i}", "layout": "single_full", "items": []} for i in range(PAGES)],
        "photos": [],
    }


def serve(route, album):
    path = route.request.url.split(ORIGIN, 1)[-1].split("?")[0] if route.request.url.startswith(ORIGIN) else None
    url = route.request.url
    if "/api/albums/preview" in url:
        return route.fulfill(json=album)
    if "/api/" in url:
        return route.fulfill(json={})
    if path is None:
        # Google Fonts, fetched here rather than by the browser (which can't
        # always get through a proxy); same browser name, for woff2 files.
        req = urllib.request.Request(url, headers={"User-Agent": route.request.headers.get("user-agent", "")})
        with urllib.request.urlopen(req, timeout=30) as res:
            return route.fulfill(status=res.status, body=res.read(), content_type=res.headers.get("Content-Type"), headers={"Access-Control-Allow-Origin": "*"})
    if path.startswith("/preview-photos/"):
        f = PHOTOS / path.rsplit("/", 1)[1]
    else:
        f = BUILD / path.lstrip("/")
        if not f.is_file():
            f = BUILD / "app.html"
    route.fulfill(body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or "text/html")


def handler(album):
    return lambda route: serve(route, album)


def shot(locator):
    return Image.open(io.BytesIO(locator.screenshot(animations="disabled"))).convert("RGB")


def shade(img, profile):
    """Darkens img across its width: profile(t) is the brightness (0–1) at
    t, 0 on the left edge, 1 on the right."""
    w, h = img.size
    row = Image.new("L", (w, 1))
    row.putdata([round(255 * profile(x / max(1, w - 1))) for x in range(w)])
    mask = row.resize((w, h)).convert("RGB")
    return ImageChops.multiply(img, mask)


def compose(spine, front):
    cw, ch = W * SCALE, H * SCALE
    fh = round(ch * BOOK_H)
    fw = round(front.width * fh / front.height)
    sw = max(1, round(spine.width * fh / spine.height))
    gap = round(cw * GAP)
    x0 = (cw - (sw + gap + fw)) // 2
    y0 = (ch - fh) // 2
    canvas = Image.new("RGB", (cw, ch), "white")
    # soft shadow under each piece, a little to the right and down
    shadow = Image.new("L", (cw, ch), 0)
    for x, w in ((x0, sw), (x0 + sw + gap, fw)):
        shadow.paste(80, (x + 6 * SCALE, y0 + 8 * SCALE, x + w + 6 * SCALE, y0 + fh + 8 * SCALE))
    shadow = shadow.filter(ImageFilter.GaussianBlur(9 * SCALE))
    canvas.paste((60, 50, 40), (0, 0), shadow)
    # a rounded spine (darker at its edges) and the cover's hinge, so the
    # flat covers read as a book
    spine = shade(spine.resize((sw, fh), Image.LANCZOS), lambda t: 0.8 + 0.2 * (1 - (2 * t - 1) ** 2))
    front = shade(front.resize((fw, fh), Image.LANCZOS), lambda t: 1 - 0.12 * max(0.0, 1 - t / 0.035) - 0.05 * max(0.0, 1 - abs(t - 0.05) / 0.015))
    canvas.paste(spine, (x0, y0))
    canvas.paste(front, (x0 + sw + gap, y0))
    return canvas.resize((W, H), Image.LANCZOS)


def main(templates_json):
    templates = json.loads(Path(templates_json).read_text())
    photo_plan = json.loads((HERE / "photos.json").read_text()) if (HERE / "photos.json").is_file() else {}
    only = set(sys.argv[2:])
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
        page = browser.new_page(viewport={"width": 1400, "height": 1000}, device_scale_factor=SCALE)
        for t in templates:
            if only and t["id"] not in only:
                continue
            album = album_for(t, photo_plan.get(t["id"], []))
            page.unroute("**/*")
            page.route("**/*", handler(album))
            page.goto(f"{ORIGIN}/print/preview?auth=preview", wait_until="load")
            page.locator('[data-print-ready="true"]').wait_for(state="attached", timeout=60000)
            sheet = page.locator(".cover-sheet").first
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(1500)  # titles fit themselves to their box
            parts = sheet.locator(":scope > div")
            out = compose(shot(parts.nth(0)), shot(parts.nth(2)))
            out.save(OUT / f"{t['id']}.webp", "WEBP", quality=88, method=6)
            print("made", t["id"])
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1])
