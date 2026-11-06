"""Datenmodell: FileItem, PlannedChange, Plan."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Status(StrEnum):
    OK = "ok"
    SKIP = "skip"  # nichts zu tun (kein Treffer, Name unverändert)
    CONFLICT = "conflict"  # würde etwas überschreiben oder kollidieren
    ERROR = "error"  # nicht ausführbar (Rechte, Datei fehlt)


@dataclass(frozen=True)
class FileItem:
    path: Path
    root: Path | None = None  # Ordner, aus dem die Datei gescannt wurde (für Zielordner-Spiegelung)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def suffix(self) -> str:
        return self.path.suffix

    @property
    def parent(self) -> Path:
        return self.path.parent


@dataclass
class PlannedChange:
    src: Path
    dst: Path | None
    status: Status = Status.OK
    reason: str = ""
    enabled: bool = True  # Checkbox in der Vorschau
    sensitive: str = ""  # Treffer der Erkennung sensibler Dateien (leer = unauffällig)

    @property
    def will_run(self) -> bool:
        return self.enabled and self.status == Status.OK and self.dst is not None


@dataclass
class Plan:
    operation: str
    params: dict[str, Any] = field(default_factory=dict)
    changes: list[PlannedChange] = field(default_factory=list)
    kind: str = "move"  # move = umbenennen, convert = neue Datei erzeugen
    runner: Callable[[Path, Path], str | None] | None = field(default=None, repr=False)

    def counts(self) -> dict[Status, int]:
        out = dict.fromkeys(Status, 0)
        for c in self.changes:
            out[c.status] += 1
        return out


@dataclass
class Result:
    done: list[PlannedChange] = field(default_factory=list)
    failed: list[tuple[PlannedChange, str]] = field(default_factory=list)
    batch_id: int | None = None
    cancelled: bool = False
    created_dirs: list[Path] = field(default_factory=list)
