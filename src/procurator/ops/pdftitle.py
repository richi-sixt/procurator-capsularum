"""PDF-Titel in den Metadaten durch den Dateinamen ersetzen.

Viele PDF tragen einen unbrauchbaren Titel («Microsoft Word - Dokument1», «myVBV Lernmedien»), den
Lesegeräte und Dokumentenverwaltungen statt des Dateinamens anzeigen. Die Operation erzeugt eine Kopie mit
neuem Titel im Zielordner, das Original bleibt unverändert (wie bei den anderen Konvertierungen).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from ..i18n import tr
from ..model import FileItem
from .convert import ConvertOperation, _atomic_name

_LEADING_NUMBER = re.compile(r"^\s*\d+[\s._-]+")


def read_title(path: Path) -> str:
    """Titel aus den Metadaten (leer, wenn keiner gesetzt ist)."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ValueError(tr("PDF ist verschlüsselt"))
    meta = reader.metadata
    return str(meta.title).strip() if meta is not None and meta.title else ""


@dataclass
class SetPdfTitle(ConvertOperation):
    """Setzt den Titel in den Metadaten auf den Dateinamen (ohne Endung)."""

    name: ClassVar[str] = "pdf_title"
    output_dir: str = ""
    strip_number: bool = False

    def __post_init__(self) -> None:
        self._current: dict[Path, str] = {}

    def _wanted(self, item: FileItem) -> str:
        title = item.path.stem
        if self.strip_number:
            title = _LEADING_NUMBER.sub("", title) or title
        return title.strip()

    def _title_of(self, item: FileItem) -> str:
        if item.path not in self._current:
            self._current[item.path] = read_title(item.path)
        return self._current[item.path]

    def transform(self, item: FileItem, index: int) -> str | None:
        if item.suffix.lower() != ".pdf":
            return None
        if self._title_of(item) == self._wanted(item):
            return None
        return item.name

    def skip_reason(self, item: FileItem) -> str | None:
        if item.suffix.lower() == ".pdf":
            return tr("Titel stimmt schon")
        return None

    def note(self, item: FileItem) -> str:
        old = self._current.get(item.path, "")
        return tr("Titel: «{old}» → «{new}»", old=old or tr("(leer)"), new=self._wanted(item))

    def convert(self, src: Path, dst: Path) -> str | None:
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import NameObject

        reader = PdfReader(str(src))
        if reader.is_encrypted:
            raise RuntimeError(tr("PDF ist verschlüsselt"))
        writer = PdfWriter(clone_from=reader)
        title = self._wanted(FileItem(src))
        writer.add_metadata({"/Title": title})
        root = writer._root_object  # noqa: SLF001
        if NameObject("/Metadata") in root:  # ein alter XMP-Titel würde dem neuen widersprechen
            del root[NameObject("/Metadata")]
        dst.parent.mkdir(parents=True, exist_ok=True)
        part = _atomic_name(dst)
        try:
            with open(part, "wb") as fh:
                writer.write(fh)
            os.replace(part, dst)
        finally:
            part.unlink(missing_ok=True)
        return tr("Titel gesetzt")

