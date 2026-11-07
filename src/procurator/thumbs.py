"""Kleine Vorschaubilder für die Tabelle (nur lokal, nie an ein Modell).

Gelesen wird nur, was Pillow als Bild öffnen kann (und was eine Bild-Endung hat) sowie PDF (erste Seite,
mit pdfium). Das Ergebnis ist immer ein kleines JPEG. Riesige Dateien und Bilder mit absurder Pixelzahl
werden abgelehnt, kaputte, verschlüsselte oder leere Dateien liefern `None`.
"""

from __future__ import annotations

import io
import threading
from pathlib import Path

THUMB_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff", ".bmp", ".gif", ".pdf"}
MIN_SIZE, MAX_SIZE = 32, 1600
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_PIXELS = 120_000_000
MAX_PDF_BYTES = 50 * 1024 * 1024
_PDFIUM = threading.Lock()  # pdfium ist nicht thread-sicher: immer nur eine Seite gleichzeitig


def is_thumbable(path: Path) -> bool:
    return path.suffix.lower() in THUMB_EXTS


def clamp(size: int) -> int:
    return max(MIN_SIZE, min(MAX_SIZE, size))


def _pdf_page(path: Path, size: int):  # noqa: ANN202 - PIL-Bild
    """Erste Seite eines PDF als Bild mit längster Seite `size`. `None` bei leer oder verschlüsselt."""
    if path.stat().st_size > MAX_PDF_BYTES:
        return None
    import pypdfium2 as pdfium

    with _PDFIUM:
        pdf = pdfium.PdfDocument(str(path))
        try:
            if len(pdf) == 0:
                return None
            page = pdf[0]
            width, height = page.get_size()
            if width <= 0 or height <= 0:
                return None
            return page.render(scale=size / max(width, height)).to_pil().convert("RGB")
        finally:
            pdf.close()


def make_thumbnail(path: Path, size: int) -> bytes | None:
    """JPEG-Bytes, das längste Seitenmass höchstens `size` Pixel. `None`, wenn kein lesbares Bild."""
    size = clamp(size)
    if not is_thumbable(path):
        return None
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        from PIL import Image, ImageOps

        if path.suffix.lower() == ".pdf":
            img = _pdf_page(path, size)
            if img is None:
                return None
            return _jpeg(img, size)

        from .meta import _register_heif

        _register_heif()
        with Image.open(path) as img:
            if img.width * img.height > MAX_PIXELS:
                return None
            if img.format == "JPEG":
                img.draft("RGB", (size * 2, size * 2))  # schnell: beim Laden verkleinern
            img = ImageOps.exif_transpose(img)
            return _jpeg(img, size)
    except Exception:  # noqa: BLE001 - defektes oder fremdes Bild, Pillow und pdfium werfen vieles
        return None


def _jpeg(img, size: int) -> bytes:  # noqa: ANN001
    from PIL import Image

    img.thumbnail((size, size))
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        flat = Image.new("RGB", rgba.size, "white")  # Transparenz auf Weiss, nicht Schwarz
        flat.paste(rgba, mask=rgba.getchannel("A"))
        img = flat
    else:
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, "JPEG", quality=80)
    return out.getvalue()
