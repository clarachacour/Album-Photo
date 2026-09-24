"""Fallback PDF export with ReportLab, used when the browser export fails."""
import logging
from io import BytesIO

from fastapi import Header, HTTPException, Query
from fastapi.responses import Response
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from app.assets.cover_assets import CORAL_LOGO_BYTES
from app.assets.theme_assets import (
    TRAVEL_AUSTRALIA_ICON,
    TRAVEL_BARCELONA_ICON,
    TRAVEL_HAWAII_ICON,
    TRAVEL_MOROCCO_ICON,
    TRAVEL_PAROS_ICON,
    TRAVEL_SICILY_ICON,
    TRAVEL_THAILAND_ICON,
)
from app.core.auth import decode_token
from app.db import db
from app.services.pdf import (
    REFERENCE_PAGE_PX,
    decode_data_uri_image,
    get_page_size,
    hex_to_rl_color,
    resolve_pdf_font,
)
from app.services.storage import get_object

logger = logging.getLogger(__name__)


# Images packagées avec l'application (ex: logo corail par défaut sur la couverture)
# Embarquées en base64 (voir cover_assets.py) pour ne jamais dépendre d'un fichier
# présent sur le disque — évite les soucis de fichier oublié lors d'un déploiement.
BUNDLED_ASSETS_BYTES = {
    "coral": CORAL_LOGO_BYTES,
    "travel_sicily": TRAVEL_SICILY_ICON,
    "travel_hawaii": TRAVEL_HAWAII_ICON,
    "travel_thailand": TRAVEL_THAILAND_ICON,
    "travel_paros": TRAVEL_PAROS_ICON,
    "travel_morocco": TRAVEL_MOROCCO_ICON,
    "travel_australia": TRAVEL_AUSTRALIA_ICON,
    "travel_barcelona": TRAVEL_BARCELONA_ICON,
}

async def export_pdf_reportlab_legacy(album_id: str, auth: str = Query(None), authorization: str = Header(None)):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    user_id = decode_token(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    album = await db.albums.find_one({"id": album_id, "user_id": user_id}, {"_id": 0})
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    photos = await db.photos.find({"album_id": album_id, "is_deleted": False}, {"_id": 0}).to_list(2000)
    photo_map = {p["id"]: p for p in photos}

    page_size = get_page_size(album.get("size", "A4"), album.get("orientation", "portrait"))
    pw, ph = page_size
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)

    # Default cover palette (used when the user hasn't customized colors yet)
    DEFAULT_BG = "#009BB5"
    DEFAULT_ACCENT = "#F53769"
    DEFAULT_TEXT = "#63DDE0"
    cover = album.get("cover") or {}
    bg_color = cover.get("bg_color") or DEFAULT_BG
    accent_color = cover.get("accent_color") or DEFAULT_ACCENT
    text_color = cover.get("text_color") or DEFAULT_TEXT

    def draw_text_item(item, page_w, page_h, default_color="#1A1A17"):
        """Draw a text item using the same font family and proportional size
        as the web editor."""
        weight = str(item.get("font_weight", "normal")).lower()
        style = str(item.get("font_style", "normal")).lower()
        font_name = resolve_pdf_font(item.get("font"), weight)
        # Oblique/italic isn't available for the embedded weights we bundled —
        # ReportLab's base-14 Helvetica-Oblique is the only italic we can
        # honor; anything else just skips the slant rather than crash.
        if style == "italic" and font_name in ("Helvetica", "Helvetica-Bold"):
            font_name += "-Oblique" if font_name == "Helvetica" else "Oblique"
        raw_size = float(item.get("font_size", 16))
        font_size = raw_size * (page_w / REFERENCE_PAGE_PX)
        c.setFillColor(hex_to_rl_color(item.get("color", default_color)))
        c.setFont(font_name, font_size)
        x = item["x"] * page_w
        y_top = (1 - item["y"]) * page_h
        text_align = item.get("text_align", "left")
        content = (item.get("content", "") or "")
        if item.get("role") == "subtitle":
            content = content.upper()

        # Word-wrap each manual paragraph (split on "\n") to fit the box
        # width — without this, a long line with no manual break just runs
        # off both sides of the page instead of staying inside its frame.
        box_w = item.get("w", 1) * page_w
        wrapped_lines = []
        for paragraph in content.split("\n"):
            words = paragraph.split(" ")
            cur = ""
            for w in words:
                candidate = (cur + " " + w).strip()
                if not cur or pdfmetrics.stringWidth(candidate, font_name, font_size) <= box_w:
                    cur = candidate
                else:
                    wrapped_lines.append(cur)
                    cur = w
            wrapped_lines.append(cur)

        for i, line in enumerate(wrapped_lines):
            y = y_top - font_size * (i + 1)
            if text_align == "center":
                center_x = x + item.get("w", 0) * page_w / 2
                c.drawCentredString(center_x, y, line)
            elif text_align == "right":
                right_x = x + item.get("w", 0) * page_w
                c.drawRightString(right_x, y, line)
            else:
                c.drawString(x, y, line)

    # ---- FRONT COVER PAGE ----
    c.setFillColor(hex_to_rl_color(bg_color))
    c.rect(0, 0, pw, ph, fill=1, stroke=0)
    c.setFillColor(hex_to_rl_color(text_color))
    # Title position from cover.title_x / title_y (normalized top-left)
    title_x_norm = float(cover.get("title_x", 0.08))
    title_y_norm = float(cover.get("title_y", 0.08))
    title_font_weight = str(cover.get("title_font_weight", "600"))
    title_font_name = resolve_pdf_font(cover.get("title_font"), title_font_weight)
    if cover.get("title_font_size"):
        # An explicit size was chosen in the editor (raw px, calibrated
        # against the editor's on-screen page width) — scale it so it takes
        # up the same proportion of the page here as it did there.
        title_font_size = float(cover["title_font_size"]) * (pw / REFERENCE_PAGE_PX)
    else:
        title_font_size = min(pw, ph) * 0.09
    c.setFont(title_font_name, title_font_size)
    title = album.get("title", "Album")
    title_uppercase = cover.get("title_uppercase", True)
    title_rotation = float(cover.get("title_rotation", 0))
    title_writing_mode = cover.get("title_writing_mode")
    display_title = title.upper() if title_uppercase else title
    title_box_w = float(cover.get("title_w", 0.84)) * pw
    if title_writing_mode == "vertical-rl":
        # One continuous vertical line (not wrapped per word) — matches the
        # single-flow rendering used on the web for vertical titles.
        lines = [display_title]

        # The web fits vertical titles dynamically (length from box height,
        # thickness capped by box width) instead of trusting the stored
        # static size — without this, the PDF title stays small/thin no
        # matter how generous the box actually is.
        title_box_h = float(cover.get("title_h", 0.8)) * ph
        non_space_chars = max(1, len(display_title.replace(" ", "")))
        space_count = display_title.count(" ")
        # Matches the char_h/space_h ratio used when drawing below.
        fitted_by_length = (title_box_h * 0.92) / (non_space_chars * 1.05 + space_count * 0.4)
        fitted_by_thickness = title_box_w * 0.92
        title_font_size = min(fitted_by_length, fitted_by_thickness) * float(cover.get("title_scale", 1))
        c.setFont(title_font_name, title_font_size)
    else:
        words = display_title.split()

        # Fill the box width the same way the web editor does: scale the
        # font size so the widest resulting line takes up the full box
        # width, instead of just using the stored size verbatim (which was
        # calibrated for the old, smaller static title and left a gap here).
        def wrap_at(size):
            lines_ = []
            cur_ = ""
            for w in words:
                candidate = (cur_ + " " + w).strip()
                if pdfmetrics.stringWidth(candidate, title_font_name, size) <= title_box_w:
                    cur_ = candidate
                else:
                    if cur_:
                        lines_.append(cur_)
                    cur_ = w
            if cur_:
                lines_.append(cur_)
            return lines_

        probe_lines = wrap_at(title_font_size)
        widest = max(
            (pdfmetrics.stringWidth(line, title_font_name, title_font_size) for line in probe_lines),
            default=1,
        )
        if widest > 0:
            title_font_size = title_font_size * (title_box_w * 0.96 * float(cover.get("title_scale", 1)) / widest)
            c.setFont(title_font_name, title_font_size)
        lines = wrap_at(title_font_size)
    line_h = title_font_size * 1.05
    title_top = (1 - title_y_norm) * ph
    if title_writing_mode == "vertical-rl":
        # Each word becomes its own vertical column, columns proceeding
        # right-to-left across the title box — matches the CSS vertical-rl
        # writing mode used on the web so print output stays consistent.
        col_w = title_font_size * 1.15
        char_h = title_font_size * 1.05
        space_h = title_font_size * 0.4  # a space shouldn't take a full blank character row
        right_edge = title_box_w + title_x_norm * pw
        for col_i, line in enumerate(lines):
            col_x = right_edge - col_w * (col_i + 1)
            cursor_y = title_top
            for ch in line:
                step = space_h if ch == " " else char_h
                cursor_y -= step
                if ch != " ":
                    c.drawCentredString(col_x + col_w / 2, cursor_y, ch)
    elif title_rotation:
        c.saveState()
        c.translate(title_x_norm * pw, title_top)
        c.rotate(title_rotation)
        for i, line in enumerate(lines):
            c.drawString(0, -line_h * (i + 1), line)
        c.restoreState()
    else:
        for i, line in enumerate(lines):
            c.drawString(title_x_norm * pw, title_top - line_h * (i + 1), line)

    cover_image_path = album.get("cover_image_path")
    if cover_image_path:
        try:
            data, _ = get_object(cover_image_path)
            img = ImageReader(BytesIO(data))
            cx, cy = pw * 0.5, ph * 0.35
            box_w, box_h = pw * 0.8, ph * 0.45
            c.saveState()
            p = c.beginPath()
            p.rect(cx - box_w / 2, cy - box_h / 2, box_w, box_h)
            c.clipPath(p, stroke=0, fill=0)
            iw, ih = img.getSize()
            slot_ratio = box_w / box_h
            img_ratio = iw / ih
            if img_ratio > slot_ratio:
                draw_h = box_h
                draw_w = draw_h * img_ratio
            else:
                draw_w = box_w
                draw_h = draw_w / img_ratio
            c.drawImage(img, cx - draw_w / 2, cy - draw_h / 2, width=draw_w, height=draw_h, mask='auto')
            c.restoreState()
        except Exception as e:
            logger.error(f"Cover image draw failed: {e}")

    def draw_extra_items(items, default_accent):
        """Draw text / shape / image extra items (used by both front and back cover)."""
        for item in items or []:
            it_type = item.get("type")
            if it_type == "text":
                draw_text_item(item, pw, ph, default_color=text_color)
            elif it_type == "shape":
                x = item["x"] * pw
                y_top = (1 - item["y"]) * ph
                slot_w = item["w"] * pw
                slot_h = item["h"] * ph
                y_bottom = y_top - slot_h
                c.setFillColor(hex_to_rl_color(item.get("fill_color", default_accent)))
                if item.get("shape_type") == "circle":
                    c.ellipse(x, y_bottom, x + slot_w, y_bottom + slot_h, fill=1, stroke=0)
                else:
                    c.rect(x, y_bottom, slot_w, slot_h, fill=1, stroke=0)
            elif it_type == "image":
                try:
                    data = None
                    img = None
                    if item.get("storage_path"):
                        data, _ = get_object(item["storage_path"])
                    elif item.get("asset") in BUNDLED_ASSETS_BYTES:
                        data = BUNDLED_ASSETS_BYTES[item["asset"]]
                    elif item.get("image_url"):
                        # Our custom-drawn logos (rings, heart, compass...) are
                        # stored as raw base64 data URIs, not an uploaded file
                        # or a pre-bundled asset name.
                        img = decode_data_uri_image(item["image_url"])
                    if data:
                        img = ImageReader(BytesIO(data))
                    if img:
                        x = item["x"] * pw
                        y_top = (1 - item["y"]) * ph
                        slot_w = item["w"] * pw
                        slot_h = item["h"] * ph
                        # "contain" fit (preserve aspect ratio, no crop) — this is a logo/graphic, not a photo
                        iw, ih = img.getSize()
                        ratio = min(slot_w / iw, slot_h / ih) if iw and ih else 1
                        draw_w, draw_h = iw * ratio, ih * ratio
                        cx = x + slot_w / 2
                        cy_top = y_top - slot_h / 2
                        c.drawImage(img, cx - draw_w / 2, cy_top - draw_h / 2, width=draw_w, height=draw_h, mask='auto')
                except Exception as e:
                    logger.error(f"Cover extra image draw failed: {e}")

    # Extra items on front cover (text / shape / image)
    # The subtitle sits right at the title box's real bottom edge, sized
    # proportionally to the title — matches the web editor, where both are
    # computed dynamically instead of using the template's static stored
    # values (which were calibrated for the old, smaller static title).
    title_visual_h_frac = (line_h * len(lines)) / ph if lines else 0
    front_extra_items = cover.get("extra_items", []) or []
    adjusted_extra_items = []
    for item in front_extra_items:
        if item.get("type") == "text" and item.get("role") == "subtitle":
            item = {
                **item,
                "y": title_y_norm + title_visual_h_frac,
                "font_size": title_font_size * (REFERENCE_PAGE_PX / pw) * 0.58,
            }
        adjusted_extra_items.append(item)

    draw_extra_items(adjusted_extra_items, accent_color)
    c.showPage()

    # ---- SPINE (its own narrow page, since the interior/cover pages are
    # otherwise all fixed to the same page_size — a merged single wide
    # "back+spine+front" sheet would need restructuring the whole cover
    # drawing code below, which the other cover art still depends on) ----
    num_interior_pages = len(album.get("pages", []) or [])
    spine_w = max(16, min(35, 4 + num_interior_pages * 0.12)) * 2.83465  # mm -> pt, thickness scales with page count
    c.setPageSize((spine_w, ph))
    c.setFillColor(hex_to_rl_color(bg_color))
    c.rect(0, 0, spine_w, ph, fill=1, stroke=0)

    spine_text_color = cover.get("spine_title_color") or text_color
    spine_max_font = spine_w * 0.9  # never let the text get thicker than the spine itself

    def fit_spine_font(text_str, font_name, box_h_frac):
        box_h = box_h_frac * ph
        size = 40.0
        while size > 4 and pdfmetrics.stringWidth(text_str, font_name, size) > box_h * 0.9:
            size -= 0.5
        return min(size, spine_max_font)

    # Title (mirrors the web: album title, or a spine-specific override, in
    # small caps, rotated to read top-to-bottom along the spine)
    spine_title_str = (cover.get("spine_title_text") or album.get("title", "Album")).upper()
    spine_title_font = resolve_pdf_font(cover.get("spine_title_font"), cover.get("spine_title_weight", "600"))
    title_box_y = cover.get("spine_title_y", 0.08)
    title_box_h = cover.get("spine_title_h", 0.8)
    spine_title_size = fit_spine_font(spine_title_str, spine_title_font, title_box_h)
    c.setFont(spine_title_font, spine_title_size)
    c.setFillColor(hex_to_rl_color(spine_text_color))
    c.saveState()
    title_cy = ph * (1 - title_box_y - title_box_h / 2)
    c.translate(spine_w / 2, title_cy)
    c.rotate(-90)
    c.drawCentredString(0, 0, spine_title_str)
    c.restoreState()

    # Caption (e.g. "MEMORIES") — one rotated line per manual line break
    spine_caption_str = cover.get("spine_caption")
    if spine_caption_str:
        cap_font = resolve_pdf_font(cover.get("spine_caption_font"), cover.get("spine_caption_weight", "600"))
        cap_lines = str(spine_caption_str).split("\n")
        cap_box_y = cover.get("spine_caption_y", 0.64)
        cap_box_h = cover.get("spine_caption_h", 0.24)
        cap_color = cover.get("spine_caption_color") or spine_text_color
        per_line_h = cap_box_h / max(1, len(cap_lines))
        cap_size = min(fit_spine_font(max(cap_lines, key=len), cap_font, per_line_h), spine_max_font / max(1, len(cap_lines)))
        c.setFont(cap_font, cap_size)
        c.setFillColor(hex_to_rl_color(cap_color))
        for i, line in enumerate(cap_lines):
            line_cy = ph * (1 - cap_box_y - per_line_h * (i + 0.5))
            c.saveState()
            c.translate(spine_w / 2, line_cy)
            c.rotate(-90)
            c.drawCentredString(0, 0, line.upper())
            c.restoreState()

    # Logo (heart / rings / compass...) — a plain image, only its own
    # explicit rotation (if any) applies, independent of the text rotation
    spine_logo_img = decode_data_uri_image(cover.get("spine_logo_image"))
    if spine_logo_img:
        lx = cover.get("spine_logo_x", 0.1) * spine_w
        ly_top = ph * (1 - cover.get("spine_logo_y", 0.46))
        lw = cover.get("spine_logo_w", 0.8) * spine_w
        lh = cover.get("spine_logo_h", 0.16) * ph
        iw, ih = spine_logo_img.getSize()
        ratio = min(lw / iw, lh / ih) if iw and ih else 1
        draw_w, draw_h = iw * ratio, ih * ratio
        lcx, lcy = lx + lw / 2, ly_top - lh / 2
        c.saveState()
        rot = float(cover.get("spine_logo_rotation", 0) or 0)
        if rot:
            c.translate(lcx, lcy)
            c.rotate(rot)
            c.drawImage(spine_logo_img, -draw_w / 2, -draw_h / 2, width=draw_w, height=draw_h, mask="auto")
        else:
            c.drawImage(spine_logo_img, lcx - draw_w / 2, lcy - draw_h / 2, width=draw_w, height=draw_h, mask="auto")
        c.restoreState()

    c.showPage()
    c.setPageSize((pw, ph))

    # ---- CONTENT PAGES ----
    pages = album.get("pages", []) or []
    for page in pages:
        c.setFillColor(hex_to_rl_color("#F9F8F6"))
        c.rect(0, 0, pw, ph, fill=1, stroke=0)
        items = page.get("items", [])
        for item in items:
            if item.get("type") == "photo":
                photo = photo_map.get(item.get("photo_id"))
                if not photo:
                    continue
                try:
                    data, _ = get_object(photo["storage_path"])
                    img = ImageReader(BytesIO(data))
                    x = item["x"] * pw
                    # ReportLab y-origin is bottom-left; our items use top-left origin
                    y_top = (1 - item["y"]) * ph
                    slot_w = item["w"] * pw
                    slot_h = item["h"] * ph
                    y_bottom = y_top - slot_h
                    scale = max(float(item.get("scale", 1.0)), 1.0)
                    focal_x = float(item.get("focal_x", 0.5))
                    focal_y = float(item.get("focal_y", 0.5))
                    rotation = float(item.get("rotation", 0))
                    iw, ih = img.getSize()
                    slot_ratio = slot_w / slot_h if slot_h else 1
                    img_ratio = iw / ih if ih else 1
                    # cover fit
                    if img_ratio > slot_ratio:
                        draw_h = slot_h
                        draw_w = draw_h * img_ratio
                    else:
                        draw_w = slot_w
                        draw_h = draw_w / img_ratio
                    # apply zoom
                    draw_w *= scale
                    draw_h *= scale
                    # focal offset (0..1). 0.5 = centered
                    overflow_x = draw_w - slot_w
                    overflow_y = draw_h - slot_h
                    img_x = x - overflow_x * focal_x
                    img_y_top = y_top + overflow_y * focal_y
                    img_y_bottom = img_y_top - draw_h
                    # clip
                    c.saveState()
                    p = c.beginPath()
                    p.rect(x, y_bottom, slot_w, slot_h)
                    c.clipPath(p, stroke=0, fill=0)
                    if rotation:
                        # rotate the photo around the frame's own center — the
                        # frame itself (its position/size) never changes.
                        cx, cy = x + slot_w / 2, y_bottom + slot_h / 2
                        c.translate(cx, cy)
                        c.rotate(rotation)
                        c.translate(-cx, -cy)
                    c.drawImage(img, img_x, img_y_bottom, width=draw_w, height=draw_h, mask='auto')
                    c.restoreState()
                except Exception as e:
                    logger.error(f"PDF image draw failed: {e}")
            elif item.get("type") == "text":
                draw_text_item(item, pw, ph)
        c.showPage()

    # ---- BACK COVER ----
    c.setFillColor(hex_to_rl_color(bg_color))
    c.rect(0, 0, pw, ph, fill=1, stroke=0)
    c.setFillColor(hex_to_rl_color(text_color))
    back_items = cover.get("back_extra_items", []) or []
    # Legacy fallback: older albums without back_extra_items still get the
    # fixed country/year text. New albums seed real (editable) text items instead.
    if not back_items:
        c.setFont("Helvetica", min(pw, ph) * 0.04)
        country_text = album.get("country", "") or ""
        if country_text and not cover.get("hide_back_text"):
            c.drawCentredString(pw / 2, ph * 0.5, country_text.upper())
        c.setFont("Helvetica", min(pw, ph) * 0.025)
        c.drawCentredString(pw / 2, ph * 0.1, str(album.get("year", "")))
    draw_extra_items(back_items, accent_color)
    c.showPage()

    c.save()
    buf.seek(0)
    filename = f"{album.get('title', 'album').replace(' ', '_')}.pdf"
    return Response(
        content=buf.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
