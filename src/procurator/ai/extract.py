"""Text-Auszug für die Datenschutzstufe 2: Anfang des Inhalts einer Datei als einfacher Text.

Unterstützt werden einfache Textdateien, PDF und die neuen Office-Formate (DOCX, XLSX, PPTX).
Alles hier ist bewusst vorsichtig: Es wird nur ein kleiner Anfang gelesen, kaputte, verschlüsselte oder
riesige Dateien liefern einen leeren Auszug statt eines Fehlers, und Office-XML wird nicht mit einem
XML-Parser geöffnet (kein Risiko durch Entitäten), sondern nur von Tags befreit.
Gescannte PDF ohne Textschicht liefern nichts (Texterkennung gibt es nicht).
"""

from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path

MAX_EXCERPT_CHARS = 600
MAX_PDF_BYTES = 30 * 1024 * 1024  # grössere PDF werden nicht geöffnet
MAX_PDF_PAGES = 3
MAX_XML_BYTES = 512 * 1024  # pro XML-Teil höchstens so viel entpacken (Schutz vor Zip-Bomben)
MAX_OFFICE_PARTS = 6
MAX_OFFICE_BYTES = 50 * 1024 * 1024

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log", ".xml", ".yml", ".yaml", ".ini",
                   ".html", ".htm", ".tex", ".rtf"}
PDF_EXTENSIONS = {".pdf"}
# Welche Teile der ZIP-Datei den Text tragen, in Lesereihenfolge.
OFFICE_PARTS = {
    ".docx": re.compile(r"^word/document\.xml$"),
    ".pptx": re.compile(r"^ppt/slides/slide\d+\.xml$"),
    ".xlsx": re.compile(r"^xl/(sharedStrings\.xml|worksheets/sheet\d+\.xml)$"),
}
EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS | set(OFFICE_PARTS)

_BLOCK_END = re.compile(r"</(?:w:p|a:p|row|si|w:tr|w:br)\s*>|<w:tab\s*/>|<w:br\s*/>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]*>")
_SPACE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _SPACE.sub(" ", text).strip()[:MAX_EXCERPT_CHARS]


def _plain(path: Path) -> str:
    with open(path, "rb") as fh:
        raw = fh.read(4096)
    return raw.decode("utf-8", errors="ignore")


def _pdf(path: Path) -> str:
    if path.stat().st_size > MAX_PDF_BYTES:
        return ""
    from pypdf import PdfReader  # erst hier: ohne die Bibliothek bleibt alles andere nutzbar

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        return ""
    chunks: list[str] = []
    length = 0
    for page in reader.pages[:MAX_PDF_PAGES]:
        chunks.append(page.extract_text() or "")
        length += len(chunks[-1])
        if length >= MAX_EXCERPT_CHARS * 2:
            break
    return " ".join(chunks)


def _xml_text(xml: str) -> str:
    return html.unescape(_TAG.sub("", _BLOCK_END.sub(" ", xml)))


def _office(path: Path, pattern: re.Pattern[str]) -> str:
    out: list[str] = []
    length = 0
    with zipfile.ZipFile(path) as zf:
        names = sorted((n for n in zf.namelist() if pattern.match(n)),
                       key=lambda n: (not n.endswith("sharedStrings.xml"),
                                      [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", n)]))
        total = 0
        for name in names[:MAX_OFFICE_PARTS]:
            info = zf.getinfo(name)
            total += info.file_size
            if total > MAX_OFFICE_BYTES:
                break
            with zf.open(name) as part:
                xml = part.read(MAX_XML_BYTES).decode("utf-8", errors="ignore")
            text = _clean(_xml_text(xml))
            if text:
                out.append(text)
                length += len(text)
            if length >= MAX_EXCERPT_CHARS:
                break
    return " ".join(out)


def excerpt(path: Path) -> str:
    """Der Anfang des Inhalts, auf einer Zeile und höchstens `MAX_EXCERPT_CHARS` lang. Leer bei Problemen."""
    ext = path.suffix.lower()
    try:
        if ext in TEXT_EXTENSIONS:
            return _clean(_plain(path))
        if ext in PDF_EXTENSIONS:
            return _clean(_pdf(path))
        if ext in OFFICE_PARTS:
            return _clean(_office(path, OFFICE_PARTS[ext]))
    except Exception:  # noqa: BLE001 - beschädigte Datei, fehlende Rechte, PDF-Eigenheiten: nie den Lauf stoppen
        return ""
    return ""
