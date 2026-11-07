"""Umbenennen-Operationen nach dem Vorbild von NameChanger.

Standardmässig wird nur der Name ohne Endung bearbeitet (`keep_extension=True`).
"""

from __future__ import annotations

import math
import re
from abc import abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import ClassVar, Literal

from ..i18n import tr
from ..meta import best_date, created_ts
from ..model import FileItem
from ..scanner import natural_key
from .base import Operation


class RenameOperation(Operation):
    """Wendet `edit` auf den Namen ohne Endung an (oder auf den ganzen Namen)."""

    keep_extension: bool = True

    def transform(self, item: FileItem, index: int) -> str | None:
        if self.keep_extension:
            new = self.edit(item.stem, item, index)
            return None if new is None else new + item.suffix
        return self.edit(item.name, item, index)

    @abstractmethod
    def edit(self, text: str, item: FileItem, index: int) -> str | None: ...


def _flags(ignore_case: bool) -> int:
    return re.IGNORECASE if ignore_case else 0


# --- Text ersetzen ---------------------------------------------------------


@dataclass
class ReplaceText(RenameOperation):
    name: ClassVar[str] = "replace"
    find: str
    replace: str = ""
    mode: Literal["first", "last", "all"] = "all"
    ignore_case: bool = False
    keep_extension: bool = True

    def edit(self, text: str, item: FileItem, index: int) -> str | None:
        if not self.find:
            return None
        rx = re.compile(re.escape(self.find), _flags(self.ignore_case))
        matches = list(rx.finditer(text))
        if not matches:
            return None
        if self.mode == "all":
            return rx.sub(lambda _m: self.replace, text)
        m = matches[0] if self.mode == "first" else matches[-1]
        return text[: m.start()] + self.replace + text[m.end() :]


@dataclass
class Wildcard(RenameOperation):
    """`*` = beliebig viele Zeichen, `?` = genau ein Zeichen. Ersetzt den ersten Treffer."""

    name: ClassVar[str] = "wildcard"
    pattern: str
    replace: str = ""
    ignore_case: bool = False
    keep_extension: bool = True

    def edit(self, text: str, item: FileItem, index: int) -> str | None:
        regex = "".join(
            ".*?" if ch == "*" else "." if ch == "?" else re.escape(ch) for ch in self.pattern
        )
        m = re.search(regex, text, _flags(self.ignore_case) | re.DOTALL) if self.pattern else None
        if not m:
            return None
        return text[: m.start()] + self.replace + text[m.end() :]


@dataclass
class RegexReplace(RenameOperation):
    """Regulärer Ausdruck, erster Treffer. `$1`, `$2` ... sind Rückverweise."""

    name: ClassVar[str] = "regex"
    pattern: str
    replace: str = ""
    ignore_case: bool = False
    keep_extension: bool = True

    def edit(self, text: str, item: FileItem, index: int) -> str | None:
        m = re.search(self.pattern, text, _flags(self.ignore_case)) if self.pattern else None
        if not m:
            return None
        template = re.sub(r"\$(\d+)", r"\\g<\1>", self.replace.replace("\\", "\\\\"))
        return text[: m.start()] + m.expand(template) + text[m.end() :]


# --- Anhängen / Voranstellen ---------------------------------------------


@dataclass
class Append(RenameOperation):
    name: ClassVar[str] = "append"
    text: str
    keep_extension: bool = True

    def edit(self, text: str, item: FileItem, index: int) -> str | None:
        return text + self.text if self.text else None


@dataclass
class Prepend(RenameOperation):
    name: ClassVar[str] = "prepend"
    text: str
    keep_extension: bool = True

    def edit(self, text: str, item: FileItem, index: int) -> str | None:
        return self.text + text if self.text else None


# --- Zeichen entfernen / einfügen -----------------------------------------


@dataclass
class RemoveChars(RenameOperation):
    """`range`: `count` Zeichen ab Position `start` (1 = erstes). `from_end`: `count` am Ende."""

    name: ClassVar[str] = "remove"
    count: int
    start: int = 1
    mode: Literal["range", "from_end"] = "range"
    keep_extension: bool = True

    def edit(self, text: str, item: FileItem, index: int) -> str | None:
        if self.count <= 0:
            return None
        if self.mode == "from_end":
            return text[: -self.count] if len(text) > self.count else ""
        begin = self.start - 1
        if begin < 0 or begin >= len(text):
            return None
        return text[:begin] + text[begin + self.count :]


@dataclass
class InsertChars(RenameOperation):
    """Text an Position `index` einfügen (0 = ganz vorn). `from_end`: Position vom Ende.

    Mit `pad_to_length` wird der Text so oft wiederholt, bis der Name die Länge erreicht;
    Namen, die schon lang genug sind, werden übersprungen.
    """

    name: ClassVar[str] = "insert"
    text: str
    index: int = 0
    from_end: bool = False
    pad_to_length: int = 0
    keep_extension: bool = True

    def edit(self, text: str, item: FileItem, index: int) -> str | None:
        if not self.text or self.index < 0 or self.index > len(text):
            return None
        insert = self.text
        if self.pad_to_length:
            missing = self.pad_to_length - len(text)
            if missing <= 0:
                return None
            insert = (self.text * math.ceil(missing / len(self.text)))[:missing]
        pos = len(text) - self.index if self.from_end else self.index
        return text[:pos] + insert + text[pos:]


# --- Gross-/Kleinschreibung -------------------------------------------------


@dataclass
class ChangeCase(RenameOperation):
    name: ClassVar[str] = "case"
    mode: Literal["title", "lower", "upper"] = "title"
    keep_extension: bool = True

    def edit(self, text: str, item: FileItem, index: int) -> str | None:
        if self.mode == "lower":
            return text.lower()
        if self.mode == "upper":
            return text.upper()
        return re.sub(r"[\w']+", lambda m: m.group(0).capitalize(), text)


# --- Sequenz ----------------------------------------------------------------


def _created(item: FileItem) -> float:
    return created_ts(item.path)


def _place(text: str, addition: str, position: str, sep: str) -> str:
    if position == "replace":
        return addition
    if position == "prepend":
        return addition + sep + text
    return text + sep + addition


@dataclass
class Sequence(RenameOperation):
    """Laufnummer anhängen, voranstellen oder den Namen ersetzen (Image-001 / 001-Image)."""

    name: ClassVar[str] = "sequence"
    label: str = ""
    digits: int = 3
    start: int = 1
    position: Literal["append", "prepend", "replace"] = "append"
    label_first: bool = True
    sep: str = "-"
    sort: Literal["custom", "name", "auto", "created", "modified"] = "custom"
    descending: bool = False
    keep_extension: bool = True

    def order(self, items: list[FileItem]) -> list[FileItem]:
        keys = {
            "name": lambda i: natural_key(i.name),
            "auto": lambda i: (best_date(i.path)[0], natural_key(i.name)),  # Aufnahmedatum, sonst ältestes
            "created": _created,
            "modified": lambda i: i.path.stat().st_mtime,
        }
        if self.sort == "custom":
            return items
        return sorted(items, key=keys[self.sort], reverse=self.descending)

    def edit(self, text: str, item: FileItem, index: int) -> str | None:
        number = str(self.start + index).zfill(self.digits)
        if not self.label:
            seq = number
        else:
            seq = f"{self.label}{self.sep}{number}" if self.label_first else (
                f"{number}{self.sep}{self.label}"
            )
        return _place(text, seq, self.position, self.sep)


# --- Datum ------------------------------------------------------------------


@dataclass
class DateStamp(RenameOperation):
    """Datum einfügen: automatisch aus den Metadaten, Erstellt, Geändert oder ein eigenes Datum.

    «auto» nimmt bei Bildern das Aufnahmedatum (EXIF), sonst das ältere von Erstellt und Geändert.
    Das Datum des Ausführungstags wird nie verwendet (siehe `meta.best_date`).
    """

    name: ClassVar[str] = "date"
    source: Literal["auto", "custom", "created", "modified"] = "auto"
    custom_date: date | None = None
    fmt: str = "%Y-%m-%d"
    position: Literal["append", "prepend", "replace"] = "prepend"
    sep: str = "_"
    keep_extension: bool = True

    def _stamp(self, item: FileItem) -> tuple[datetime, str] | None:
        """Datum und Quelle. Pro Datei einmal berechnet, die Vorschau fragt mehrfach."""
        cache: dict[Path, tuple[datetime, str] | None] = self.__dict__.setdefault("_cache", {})
        if item.path not in cache:
            if self.source == "custom":
                cache[item.path] = None if self.custom_date is None else (
                    datetime.combine(self.custom_date, datetime.min.time()), tr("Eigenes Datum"))
            elif self.source == "created":
                cache[item.path] = (datetime.fromtimestamp(_created(item)), tr("Erstellungsdatum der Datei"))
            elif self.source == "modified":
                cache[item.path] = (datetime.fromtimestamp(item.path.stat().st_mtime),
                                    tr("Änderungsdatum der Datei"))
            else:
                cache[item.path] = best_date(item.path)
        return cache[item.path]

    def note(self, item: FileItem) -> str:
        found = self._stamp(item)
        return tr("Datum aus: {source}", source=found[1]) if found and self.source == "auto" else ""

    def edit(self, text: str, item: FileItem, index: int) -> str | None:
        found = self._stamp(item)
        if found is None:
            return None
        return _place(text, found[0].strftime(self.fmt), self.position, self.sep)


# --- Name aus Vorlage -------------------------------------------------------

_TOKEN = re.compile(r"\{(\w+)(?::([^{}]*))?\}")
TEMPLATE_TOKENS = ("date", "size", "name", "ext", "n", "folder")


@dataclass
class NameTemplate(RenameOperation):
    """Neuer Name aus einer Vorlage mit Platzhaltern, zum Beispiel `{date:%Y%m%d_%H-%M-%S}_{size}`.

    Platzhalter: `{date}` oder `{date:Format}` (strftime, Quelle wie bei «Datum»), `{size}` (Byte),
    `{name}` (bisheriger Name), `{ext}` (Endung ohne Punkt), `{n}` (Laufnummer), `{folder}` (Name
    des Ordners). Bei `{size}` und `{n}` füllt `{n:3}` mit Nullen auf drei Stellen auf.
    Die Vorlage ersetzt den ganzen Namen, die Endung bleibt standardmässig unverändert.
    """

    name: ClassVar[str] = "template"
    template: str = "{date:%Y%m%d_%H-%M-%S}_{size}"
    source: Literal["auto", "created", "modified"] = "auto"
    start: int = 1
    keep_extension: bool = True

    def __post_init__(self) -> None:
        if not self.template.strip():
            raise ValueError(tr("Vorlage fehlt"))
        for m in _TOKEN.finditer(self.template):
            if m.group(1) not in TEMPLATE_TOKENS:
                raise ValueError(tr("Unbekannter Platzhalter {token}. Erlaubt: {allowed}",
                                    token="{" + m.group(1) + "}",
                                    allowed=", ".join("{" + t + "}" for t in TEMPLATE_TOKENS)))
        rest = _TOKEN.sub("", self.template)
        if "{" in rest or "}" in rest:
            raise ValueError(tr("Geschweifte Klammern nur für Platzhalter, zum Beispiel {example}", example="{size}"))
        self._dates = DateStamp(self.source)

    def order(self, items: list[FileItem]) -> list[FileItem]:
        return sorted(items, key=lambda i: natural_key(i.name))

    def note(self, item: FileItem) -> str:
        return self._dates.note(item) if "{date" in self.template else ""

    def edit(self, text: str, item: FileItem, index: int) -> str | None:
        def fill(m: re.Match[str]) -> str:
            token, spec = m.group(1), m.group(2)
            if token == "date":
                found = self._dates._stamp(item)
                assert found is not None
                return found[0].strftime(spec or "%Y-%m-%d")
            if token in ("size", "n"):
                number = item.path.stat().st_size if token == "size" else self.start + index
                width = int(spec) if spec and spec.isdigit() else 0
                return str(number).zfill(width)
            if token == "name":
                return text
            if token == "ext":
                return item.suffix.lstrip(".")
            return item.path.parent.name  # folder

        new = _TOKEN.sub(fill, self.template).strip()
        if not new:
            raise ValueError(tr("Die Vorlage ergibt einen leeren Namen"))
        return new
