from io import BytesIO

from PIL import Image

def _jpeg(original, modified, gps=None):
    img = Image.new("RGB", (8, 8))
    exif = Image.Exif()
    exif[0x0132] = modified  # DateTime: last change
    exif.get_ifd(0x8769)[0x9003] = original  # DateTimeOriginal: taken
    if gps:
        exif.get_ifd(0x8825).update(gps)
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def test_uses_the_date_taken_not_the_date_last_changed(app):
    from app.services.curation import extract_exif_info

    info = extract_exif_info(_jpeg("2025:07:14 18:30:00", "2026:01:02 09:00:00"))
    assert info["taken_at"] == "2025-07-14T18:30:00"


def test_reads_the_location(app):
    from app.services.curation import extract_exif_info

    gps = {1: "N", 2: (33.0, 53.0, 0.0), 3: "E", 4: (35.0, 30.0, 0.0)}
    info = extract_exif_info(_jpeg("2025:07:14 18:30:00", "2025:07:14 18:30:00", gps))
    assert round(info["gps_lat"], 3) == 33.883 and round(info["gps_lng"], 3) == 35.5
