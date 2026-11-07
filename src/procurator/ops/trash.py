"""Dateien aus `_Dubletten`-Ordnern in den Papierkorb legen (eigene, bewusste Aktion).

Das Verschieben der Dubletten lässt sich rückgängig machen, das Leeren nicht. Deshalb ist es eine eigene
Operation mit Bestätigung. Die Dateien kommen in den Papierkorb des Systems (nicht endgültig gelöscht),
das Programm selbst kann sie danach nicht zurückholen: Zurücklegen geht im Finder («Zurücklegen»).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from ..i18n import tr
from ..model import FileItem
from .base import Operation
from .dedupe import DUP_DIR


def _in_duplicates_folder(item: FileItem) -> bool:
    """Liegt die Datei in einem Ordner namens `_Dubletten` (oder ist das gewählte Ordner selbst einer)?"""
    parts = item.path.parts[:-1]
    if item.root is not None:
        try:
            parts = (item.root.name, *item.path.relative_to(item.root).parts[:-1])
        except ValueError:
            pass
    return DUP_DIR in parts


def send_to_trash(path: Path) -> None:
    from send2trash import send2trash

    send2trash(str(path))


def prune_empty(folder: Path) -> None:
    """Leere Ordner aufräumen, von der Datei aus nach oben, bis und mit dem `_Dubletten`-Ordner."""
    current = folder
    while DUP_DIR in current.parts:
        try:
            current.rmdir()
        except OSError:  # nicht leer oder nicht erlaubt: stehen lassen
            return
        if current.name == DUP_DIR:
            return
        current = current.parent


@dataclass
class TrashDuplicates(Operation):
    """Legt alle Dateien in `_Dubletten`-Ordnern des gewählten Ordners in den Papierkorb."""

    name: ClassVar[str] = "trash_duplicates"
    kind: ClassVar[str] = "trash"
    destructive: ClassVar[bool] = True  # Die Oberfläche fragt vor dem Ausführen nach

    def __post_init__(self) -> None:
        self._count = 0
        self._bytes = 0

    def prepare(self, items: list[FileItem]) -> None:
        picked = [i for i in items if _in_duplicates_folder(i)]
        self._count = len(picked)
        self._bytes = 0
        for item in picked:
            try:
                self._bytes += item.path.stat().st_size
            except OSError:
                pass

    def transform(self, item: FileItem, index: int) -> str | None:
        return item.name if _in_duplicates_folder(item) else None

    def destination(self, item: FileItem, new_name: str) -> Path:
        return Path(tr("Papierkorb")) / new_name  # nur zur Anzeige

    def skip_reason(self, item: FileItem) -> str | None:
        return tr("Nicht in einem Dubletten-Ordner")

    def note(self, item: FileItem) -> str:
        return tr("Kommt in den Papierkorb")

    def convert(self, src: Path, dst: Path) -> str | None:
        send_to_trash(src)
        prune_empty(src.parent)
        return tr("im Papierkorb")

    def info(self) -> dict[str, Any]:
        return {"trashFiles": self._count, "trashBytes": self._bytes}
