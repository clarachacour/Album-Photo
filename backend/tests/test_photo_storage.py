"""The copy of each photo kept for printing: its quality and format."""
import io

from PIL import Image


def _stored(monkeypatch, data, content_type):
    from app.services import photos

    saved = {}
    monkeypatch.setattr(photos, "put_object", lambda path, body, ct=None: saved.setdefault(path, body) and {"path": path, "size": len(body)})
    photos.store_image_with_thumbnail("u/a/photo.img", data, content_type)
    return saved["u/a/photo.img"]


def _jpeg(quality, orientation=None):
    buf = io.BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    Image.new("RGB", (120, 80), "teal").save(buf, "JPEG", quality=quality, exif=exif.tobytes())
    return buf.getvalue()


def _quantization_of(quality):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, "JPEG", quality=quality)
    return Image.open(buf).quantization


def test_photos_are_stored_at_quality_90(app, monkeypatch):
    from app.services.photos import STORED_IMAGE_QUALITY

    assert STORED_IMAGE_QUALITY == 90
    # With or without a rotation to apply (straightening the photo used to
    # drop the setting and store everything at quality 75).
    for orientation in (None, 6):
        stored = Image.open(io.BytesIO(_stored(monkeypatch, _jpeg(98, orientation), "image/jpeg")))
        assert stored.format == "JPEG"
        assert stored.quantization == _quantization_of(90)
    assert stored.size == (80, 120)  # rotated


def test_a_png_stays_a_png_with_its_transparency(app, monkeypatch):
    buf = io.BytesIO()
    Image.new("RGBA", (40, 40), (255, 0, 0, 0)).save(buf, "PNG")
    stored = Image.open(io.BytesIO(_stored(monkeypatch, buf.getvalue(), "image/png")))
    assert stored.format == "PNG"
    assert stored.mode == "RGBA"
