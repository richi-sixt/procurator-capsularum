"""Antworten eines Sprachmodells prüfen und bereinigen.

Ein Modell ist nicht vertrauenswürdig: Es darf nie einen Pfad ausserhalb des gewählten Ordners,
versteckte oder ungültige Namen oder eine andere Dateiendung vorschlagen. Was nicht sicher
bereinigt werden kann, wird als Fehler gespeichert und nie ausgeführt.
"""

from __future__ import annotations

import re
import unicodedata

from ..model import FileItem
from .proposals import Proposal

MAX_PART = 60
MAX_STEM = 120
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
KNOWN_EXT = {
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv", "json", "xml", "html",
    "jpg", "jpeg", "png", "gif", "webp", "heic", "tif", "tiff", "bmp", "mp3", "mp4", "mov", "zip",
    "cbz", "cbr", "epub", "odt", "ods", "rtf",
}


class ProposalError(ValueError):
    """Der Vorschlag ist unbrauchbar. Die Meldung ist für den Nutzer gedacht."""


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def clean_folder(raw: str, max_depth: int) -> str:
    """Relativer Pfad mit «/», höchstens `max_depth` Ebenen. Leer bedeutet: Datei bleibt liegen."""
    text = CONTROL.sub("", _nfc(str(raw))).replace("\\", "/").strip()
    if not text:
        return ""
    if text.startswith("/") or text.startswith("~") or re.match(r"^[A-Za-z]:", text):
        raise ProposalError("Absoluter Pfad vorgeschlagen")
    parts: list[str] = []
    for part in text.split("/"):
        part = part.strip()
        if part in ("", "."):
            continue
        if part == "..":
            raise ProposalError("Pfad mit «..» vorgeschlagen")
        if part.startswith("."):
            raise ProposalError("Versteckter Ordner vorgeschlagen")
        part = part.replace(":", "-").rstrip(". ")
        if not part:
            continue
        parts.append(part[:MAX_PART].rstrip(". "))
    return "/".join(parts[:max_depth])


def clean_name(raw: str, original: str, suffix: str) -> str:
    """Dateiname mit der Endung der Originaldatei, ohne Pfadtrenner."""
    text = CONTROL.sub("", _nfc(str(raw))).strip()
    if not text:
        return original
    text = text.replace("/", "-").replace("\\", "-").replace(":", "-").strip()
    if suffix:
        if text.lower().endswith(suffix.lower()):
            text = text[: len(text) - len(suffix)]
        else:  # das Modell hat eine andere oder keine Endung gesetzt
            m = re.search(r"\.([A-Za-z0-9]{1,5})$", text)
            if m and m.group(1).lower() in KNOWN_EXT:
                text = text[: m.start()]
    stem = text.strip(". ")[:MAX_STEM].rstrip(". ")
    if not stem or set(stem) <= {".", " ", "-", "_"}:
        return original
    return stem + suffix


def validate(raw: dict[str, object], item: FileItem, mode: str, max_depth: int, model: str) -> Proposal:
    """Eintrag des Modells in einen sicheren Vorschlag umwandeln (oder einen Fehler-Vorschlag)."""
    try:
        confidence = float(raw.get("confidence", 0.0))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    reason = CONTROL.sub("", _nfc(str(raw.get("reason", "")))).strip()[:200]
    try:
        folder = "" if mode == "names" else clean_folder(str(raw.get("folder", "")), max_depth)
        name = item.name if mode == "folders" else clean_name(
            str(raw.get("name", "")), item.name, item.suffix)
    except ProposalError as exc:
        return Proposal(reason=reason, confidence=confidence, error=str(exc), model=model)
    return Proposal(folder, name, reason, confidence, model=model)
