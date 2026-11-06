"""Dubletten in einen eigenen Ordner verschieben, nichts wird gelöscht."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Literal

from ..index import AnalysisState, FileIndex
from ..model import FileItem
from ..scanner import natural_key
from .base import Operation

DUP_DIR = "_Dubletten"
KEEP_LABEL = {
    "oldest": "älteste",
    "newest": "neueste",
    "shortest": "kürzester Pfad",
    "first": "erste in alphabetischer Reihenfolge",
}


def _mtime(path: Path) -> int:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return 1 << 62  # unlesbar: nie als «älteste» wählen


def _by_path(path: Path) -> tuple[int, int, list[object]]:
    return (len(path.parts), len(str(path)), natural_key(str(path)))


@dataclass
class MoveDuplicates(Operation):
    """Findet gleiche Dateien, behält pro Gruppe genau eine und verschiebt die anderen.

    Die Suche nutzt den Datei-Index. Die Vorschau liest nur aus dem Cache, das Lesen der Dateien
    ist ein eigener Schritt (`analyze`). Ohne Zielordner landen die Kopien in `_Dubletten` im
    gewählten Ordner, mit nachgebauter Ordnerstruktur, damit nichts verwechselt wird.
    """

    name: ClassVar[str] = "duplicates"
    needs_analysis: ClassVar[bool] = True

    keep: Literal["oldest", "newest", "shortest", "first"] = "oldest"
    target_dir: str = ""
    keep_structure: bool = True
    min_size_kb: int = 0

    def __post_init__(self) -> None:
        self._move: dict[Path, Path] = {}  # Kopie -> behaltene Datei
        self._keep: dict[Path, int] = {}  # behaltene Datei -> Anzahl Kopien
        self._links: set[Path] = set()  # weitere Namen der behaltenen Datei (Hardlinks)
        self._reclaimable = 0
        self._groups = 0
        self._pending = AnalysisState()
        self._excluded: set[Path] = set()  # liegt schon in einem Dubletten-Ordner

    # --- Hilfen ----------------------------------------------------------------

    def _min_bytes(self) -> int:
        return max(1, self.min_size_kb * 1024)

    def _target_root(self) -> Path | None:
        raw = self.target_dir.strip()
        return Path(raw).expanduser() if raw else None

    def _candidates(self, items: list[FileItem]) -> list[FileItem]:
        """Dateien, die schon in einem Dubletten-Ordner liegen, zählen nicht mit."""
        target = self._target_root()
        target_resolved = target.resolve() if target is not None else None
        out: list[FileItem] = []
        for item in items:
            rel_parts = item.path.parts
            if item.root is not None:
                try:
                    rel_parts = item.path.relative_to(item.root).parts
                except ValueError:
                    pass
            if DUP_DIR in rel_parts[:-1]:
                continue
            if target_resolved is not None:
                try:
                    item.path.resolve().relative_to(target_resolved)
                    continue
                except ValueError:
                    pass
            out.append(item)
        return out

    def _choose(self, files: list[Path]) -> Path:
        if self.keep == "newest":  # bei gleichem Alter der kürzere Pfad
            return max(files, key=lambda p: (_mtime(p), -len(p.parts), -len(str(p))))
        if self.keep == "shortest":
            return min(files, key=_by_path)
        if self.keep == "first":
            return min(files, key=lambda p: natural_key(str(p)))
        return min(files, key=lambda p: (_mtime(p), _by_path(p)))  # oldest

    def _rel(self, path: Path) -> str:
        item = self._items.get(path)
        if item is not None and item.root is not None:
            try:
                return str(path.relative_to(item.root))
            except ValueError:
                pass
        return str(path)

    # --- Operation -----------------------------------------------------------------

    def prepare(self, items: list[FileItem]) -> None:
        self._items = {i.path: i for i in items}
        self._move, self._keep, self._links = {}, {}, set()
        candidates = self._candidates(items)
        self._excluded = {i.path for i in items} - {c.path for c in candidates}
        groups, self._pending = FileIndex().duplicates_cached(
            candidates, min_size=self._min_bytes())
        self._groups = len(groups)
        self._reclaimable = sum(g.reclaimable for g in groups)
        for g in groups:
            keeper = self._choose(g.files)
            self._keep[keeper] = len(g.files) - 1
            self._links.update(g.hardlinks.get(keeper, []))
            for f in g.files:
                if f == keeper:
                    continue
                self._move[f] = keeper
                for extra in g.hardlinks.get(f, []):  # alle Namen derselben Kopie mitnehmen
                    self._move[extra] = keeper

    def transform(self, item: FileItem, index: int) -> str | None:
        return item.name if item.path in self._move else None

    def destination(self, item: FileItem, new_name: str) -> Path:
        target = self._target_root()
        if target is not None:
            if not target.is_absolute():
                raise ValueError("Zielordner muss ein absoluter Pfad sein")
            base = target
        else:
            base = (item.root or item.path.parent) / DUP_DIR
        if self.keep_structure and item.root is not None:
            try:
                return base / item.path.relative_to(item.root).with_name(new_name)
            except ValueError:
                pass
        return base / new_name

    def skip_reason(self, item: FileItem) -> str | None:
        p = item.path
        if p not in self._items:
            return None
        if p in self._keep:
            n = self._keep[p]
            return f"Behalten ({KEEP_LABEL[self.keep]}), {n} Kopie{'n' if n != 1 else ''} davon"
        if p in self._links:
            return "Zweiter Name derselben behaltenen Datei (Hardlink)"
        if p in self._excluded:
            return "Liegt schon in einem Dubletten-Ordner"
        return "Keine Dublette" if self._pending.complete else "Keine Dublette bekannt (Analyse unvollständig)"

    def note(self, item: FileItem) -> str:
        keeper = self._move.get(item.path)
        return f"Dublette von {self._rel(keeper)}" if keeper is not None else ""

    def info(self) -> dict[str, Any]:
        return {
            "groups": self._groups,
            "duplicates": len(self._move),
            "bytes": self._reclaimable,
            "pendingFiles": self._pending.files,
            "pendingBytes": self._pending.bytes,
            "keep": self.keep,
        }

    def analyze(
        self,
        items: list[FileItem],
        on_progress: Callable[[int, int, str], None] | None = None,
        cancel: threading.Event | None = None,
        confirmed: bool = False,
    ) -> None:
        FileIndex().duplicates(
            self._candidates(items), min_size=self._min_bytes(),
            on_progress=on_progress, cancel=cancel)
