"""Kleine Vorschaubilder für die Tabelle (nur lokal, nie an ein Modell).

Gelesen wird nur, was Pillow als Bild öffnen kann und was eine Bild-Endung hat. Das Ergebnis ist immer ein
kleines JPEG. Riesige Dateien und Bilder mit absurder Pixelzahl werden abgelehnt, kaputte Dateien liefern
`None`.
"""

from __future__ import annotations

import io
from pathlib import Path

THUMB_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff", ".bmp", ".gif"}
MIN_SIZE, MAX_SIZE = 32, 1600
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_PIXELS = 120_000_000


def is_thumbable(path: Path) -> bool:
    return path.suffix.lower() in THUMB_EXTS


def clamp(size: int) -> int:
    return max(MIN_SIZE, min(MAX_SIZE, size))


def make_thumbnail(path: Path, size: int) -> bytes | None:
    """JPEG-Bytes, das längste Seitenmass höchstens `size` Pixel. `None`, wenn kein lesbares Bild."""
    size = clamp(size)
    if not is_thumbable(path):
        return None
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        from PIL import Image, ImageOps

        from .meta import _register_heif

        _register_heif()
        with Image.open(path) as img:
            if img.width * img.height > MAX_PIXELS:
                return None
            if img.format == "JPEG":
                img.draft("RGB", (size * 2, size * 2))  # schnell: beim Laden verkleinern
            img = ImageOps.exif_transpose(img)
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
    except Exception:  # noqa: BLE001 - defektes oder fremdes Bild, Pillow wirft vieles
        return None
