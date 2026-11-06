"""Dateien in einen anderen Ordner verschieben (Basis fürs Ordnen)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from ..model import FileItem
from .base import Operation


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
            raise ValueError("Zielordner fehlt")
        out = Path(raw).expanduser()
        if not out.is_absolute():
            raise ValueError("Zielordner muss ein absoluter Pfad sein")
        if self.keep_structure and item.root is not None:
            try:
                return out / item.path.relative_to(item.root).with_name(new_name)
            except ValueError:
                pass
        return out / new_name
