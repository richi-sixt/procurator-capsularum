"""Basisklasse für Operationen: rein, ohne Seiteneffekte auf das Dateisystem."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, ClassVar

from ..model import FileItem


class Operation(ABC):
    """Eine Operation berechnet pro Datei den neuen Dateinamen (oder None = kein Treffer)."""

    name: ClassVar[str]
    kind: ClassVar[str] = "move"  # "move" (umbenennen) oder "convert" (neue Datei erzeugen)

    def params(self) -> dict[str, Any]:
        return asdict(self) if is_dataclass(self) else {}  # type: ignore[call-overload]

    def order(self, items: list[FileItem]) -> list[FileItem]:
        """Reihenfolge der Verarbeitung (relevant für Sequenzen)."""
        return items

    @abstractmethod
    def transform(self, item: FileItem, index: int) -> str | None:
        """Neuer vollständiger Dateiname oder None, wenn nichts zu tun ist."""

    def destination(self, item: FileItem, new_name: str) -> Path:
        """Zielpfad. Standard: gleicher Ordner. Konvertierungen können einen Zielordner nutzen."""
        return item.path.with_name(new_name)

    def check(self, item: FileItem) -> str | None:
        """Fehlermeldung, wenn die Datei nicht verarbeitet werden kann (z. B. Programm fehlt)."""
        return None

    def convert(self, src: Path, dst: Path) -> str | None:
        """Nur für kind == "convert": `dst` erzeugen, `src` nie verändern. Gibt eine Notiz zurück."""
        raise NotImplementedError
