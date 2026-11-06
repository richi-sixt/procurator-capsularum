"""Datum einer Datei aus ihren Metadaten: Aufnahmedatum (EXIF) oder Dateidatum.

Das Erstellungs- und Änderungsdatum einer Datei ist oft nur der Tag, an dem sie heruntergeladen
oder kopiert wurde. Deshalb gilt: Bei Bildern zuerst das Aufnahmedatum aus den EXIF-Angaben,
sonst das ältere von Erstellt und Geändert (eine Kopie ist nie älter als das Original).
Es wird nie das Datum des Ausführungstags verwendet.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff"}
# EXIF: DateTimeOriginal, DateTimeDigitized (im Unterverzeichnis 0x8769), DateTime (Hauptverzeichnis)
_EXIF_IFD = 0x8769
_TAGS = (("Aufnahmedatum", 36867), ("Digitalisierungsdatum", 36868))
_TAG_MODIFIED = 306
MIN_YEAR = 1990


def created_ts(path: Path) -> float:
    st = os.stat(path)
    return getattr(st, "st_birthtime", st.st_ctime) if sys.platform == "darwin" else st.st_ctime


def _parse(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip().replace("\x00", "")
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d"):
        try:
            stamp = datetime.strptime(text[:19] if "%H" in fmt else text[:10], fmt)
        except ValueError:
            continue
        if stamp.year < MIN_YEAR or stamp > datetime.now() + timedelta(days=1):
            return None  # 0000:00:00 oder eine Kamera mit falscher Uhr
        return stamp
    return None


def _register_heif() -> None:
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        pass


def exif_date(path: Path) -> tuple[str, datetime] | None:
    """(Bezeichnung, Zeitpunkt) aus den EXIF-Angaben eines Bildes oder None."""
    if path.suffix.lower() not in IMAGE_EXTS:
        return None
    try:
        from PIL import Image

        _register_heif()
        with Image.open(path) as img:
            exif = img.getexif()
            sub = exif.get_ifd(_EXIF_IFD)
            for label, tag in _TAGS:
                if (stamp := _parse(sub.get(tag) or exif.get(tag))) is not None:
                    return label, stamp
            if (stamp := _parse(exif.get(_TAG_MODIFIED))) is not None:
                return "Änderungsdatum im Bild", stamp
    except Exception:  # defektes oder fremdes Bild: dann gilt das Dateidatum
        return None
    return None


def best_date(path: Path) -> tuple[datetime, str]:
    """Das Datum, das am ehesten das echte Datum der Datei ist, mit Angabe der Quelle."""
    if (found := exif_date(path)) is not None:
        label, stamp = found
        return stamp, f"{label} (EXIF)"
    created, modified = created_ts(path), os.stat(path).st_mtime
    if created <= modified:
        return datetime.fromtimestamp(created), "Erstellungsdatum der Datei"
    return datetime.fromtimestamp(modified), "Änderungsdatum der Datei"
