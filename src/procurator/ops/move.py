"""Dateien in einen anderen Ordner verschieben (Basis fürs Ordnen)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

from ..ai.validate import ProposalError, clean_folder
from ..i18n import tr
from ..model import FileItem
from .base import Operation
from .rename import _TOKEN, DateStamp

MAX_DEPTH = 6


@dataclass
class MoveToFolder(Operation):
    """Verschiebt Dateien in `target_dir`. Der Name bleibt gleich.

    Mit `keep_structure` wird die Ordnerstruktur unterhalb des gescannten Ordners nachgebaut,
    sonst landen alle Dateien direkt im Zielordner (gleiche Namen kollidieren dann).
    """

    name: ClassVar[str] = "move"
    target_dir: str
    keep_structure: bool = False

    def transform(self, item: FileItem, index: int) -> str | None:
        return item.name

    def destination(self, item: FileItem, new_name: str) -> Path:
        raw = self.target_dir.strip()
        if not raw:
            raise ValueError(tr("Zielordner fehlt"))
        out = Path(raw).expanduser()
        if not out.is_absolute():
            raise ValueError(tr("Zielordner muss ein absoluter Pfad sein"))
        if self.keep_structure and item.root is not None:
            try:
                return out / item.path.relative_to(item.root).with_name(new_name)
            except ValueError:
                pass
        return out / new_name


# --- Ordner nach Vorlage -------------------------------------------------------

TYPE_BY_EXT: dict[str, str] = {}
for _label, _exts in {
    "Bilder": "jpg jpeg png gif webp heic heif tif tiff bmp svg raw cr2 nef dng arw",
    "Videos": "mp4 mov mkv avi webm m4v mpg mpeg",
    "Audio": "mp3 m4a flac wav ogg aac aiff",
    "Dokumente": "pdf doc docx odt txt md rtf pages epub",
    "Tabellen": "xls xlsx csv ods numbers",
    "Präsentationen": "ppt pptx key odp",
    "Archive": "zip rar 7z tar gz cbz cbr",
}.items():
    TYPE_BY_EXT.update(dict.fromkeys(_exts.split(), _label))
FOLDER_TOKENS = ("date", "type", "ext", "initial", "folder")


def file_type(item: FileItem) -> str:
    return TYPE_BY_EXT.get(item.suffix.lower().lstrip("."), "Sonstiges")


@dataclass
class SortByTemplate(Operation):
    """Sortiert Dateien in Ordner, deren Name aus einer Vorlage entsteht. Der Dateiname bleibt.

    Platzhalter: `{date}` oder `{date:Format}` (strftime, zum Beispiel `{date:%Y}/{date:%m}`),
    `{type}` (Bilder, Videos, Audio, Dokumente, Tabellen, Präsentationen, Archive, Sonstiges),
    `{ext}` (Endung klein, ohne Punkt), `{initial}` (Anfangsbuchstabe des Namens, gross) und
    `{folder}` (Name des Ordners, in dem die Datei jetzt liegt). Ein `/` in der Vorlage ergibt
    Unterordner. Ohne `base_dir` wird im gewählten Ordner sortiert.
    """

    name: ClassVar[str] = "sort_template"
    template: str = "{type}/{date:%Y}"
    base_dir: str = ""
    source: Literal["auto", "created", "modified"] = "auto"

    def __post_init__(self) -> None:
        self.template = self.template.strip()
        if not self.template:
            raise ValueError(tr("Vorlage fehlt"))
        for m in _TOKEN.finditer(self.template):
            if m.group(1) not in FOLDER_TOKENS:
                raise ValueError(tr("Unbekannter Platzhalter {token}. Erlaubt: {allowed}",
                                    token="{" + m.group(1) + "}",
                                    allowed=", ".join("{" + t + "}" for t in FOLDER_TOKENS)))
        if "{" in _TOKEN.sub("", self.template) or "}" in _TOKEN.sub("", self.template):
            raise ValueError(tr("Geschweifte Klammern nur für Platzhalter, zum Beispiel {example}", example="{type}"))
        if self.base_dir.strip() and not Path(self.base_dir.strip()).expanduser().is_absolute():
            raise ValueError(tr("Zielordner muss ein absoluter Pfad sein"))
        self._dates = DateStamp(self.source)

    def _folder(self, item: FileItem) -> str:
        def fill(m: re.Match[str]) -> str:
            token, spec = m.group(1), m.group(2)
            if token == "date":
                found = self._dates._stamp(item)
                assert found is not None
                value = found[0].strftime(spec or "%Y-%m-%d")
            elif token == "type":
                value = file_type(item)
            elif token == "ext":
                value = item.suffix.lower().lstrip(".") or "ohne Endung"
            elif token == "initial":
                first = item.stem[:1].upper()
                value = first if first.isalnum() else "#"
            else:
                value = item.path.parent.name
            return value.replace("/", "-").replace("\\", "-")

        try:
            return clean_folder(_TOKEN.sub(fill, self.template), MAX_DEPTH)
        except ProposalError as exc:
            raise ValueError(str(exc)) from exc

    def _target_dir(self, item: FileItem) -> Path:
        base = Path(self.base_dir.strip()).expanduser() if self.base_dir.strip() else (
            item.root or item.path.parent)
        folder = self._folder(item)
        return base / folder if folder else base

    def transform(self, item: FileItem, index: int) -> str | None:
        return None if self._target_dir(item) == item.path.parent else item.name

    def skip_reason(self, item: FileItem) -> str | None:
        return tr("Liegt schon im richtigen Ordner")

    def destination(self, item: FileItem, new_name: str) -> Path:
        return self._target_dir(item) / new_name

    def note(self, item: FileItem) -> str:
        return self._dates.note(item) if "{date" in self.template else ""
