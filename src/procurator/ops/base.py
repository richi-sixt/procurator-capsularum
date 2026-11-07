"""Basisklasse für Operationen: rein, ohne Seiteneffekte auf das Dateisystem."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, ClassVar

from ..model import FileItem, PlannedChange


class Operation(ABC):
    """Eine Operation berechnet pro Datei den neuen Dateinamen (oder None = kein Treffer)."""

    name: ClassVar[str]
    kind: ClassVar[str] = "move"  # "move" (umbenennen), "convert" (neue Datei erzeugen) oder "trash" (Papierkorb)
    destructive: ClassVar[bool] = False  # nicht rückgängig zu machen: die Oberfläche fragt vor dem Ausführen
    needs_analysis: ClassVar[bool] = False  # braucht einen eigenen, langsamen Vorbereitungsschritt
    sends_data: ClassVar[bool] = False  # schickt Dateiangaben an ein Sprachmodell

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

    # --- Hooks für Operationen, die mehr als eine Datei auf einmal betrachten ----------

    def prepare(self, items: list[FileItem]) -> None:
        """Wird einmal vor der Vorschau mit allen Dateien aufgerufen (schnell, nur lesen)."""
        return None

    def skip_reason(self, item: FileItem) -> str | None:
        """Eigener Grund, wenn `transform` für diese Datei None liefert."""
        return None

    def note(self, item: FileItem) -> str:
        """Kurze Begründung für eine Datei, die ausgeführt wird (erscheint in der Vorschau)."""
        return ""

    def related(self, item: FileItem) -> list[Path]:
        """Andere Dateien, die zu dieser gehören (bei Dubletten die gleichen Dateien, die behaltene zuerst)."""
        return []

    def info(self) -> dict[str, Any]:
        """Zusatzangaben zur ganzen Vorschau (zum Beispiel Anzahl Gruppen)."""
        return {}

    def analyze(
        self,
        items: list[FileItem],
        on_progress: Callable[[int, int, str], None] | None = None,
        cancel: threading.Event | None = None,
        confirmed: bool = False,
    ) -> None:
        """Langsamer Vorbereitungsschritt (nur wenn `needs_analysis`), läuft als Hintergrund-Job.

        `confirmed`: der Nutzer hat bestätigt, dass Daten den Rechner verlassen (nur Cloud).
        """
        raise NotImplementedError

    def send_preview(self, items: list[FileItem]) -> dict[str, Any] | None:
        """Was würde die Analyse an ein Modell senden? Nur für Operationen mit `sends_data`."""
        return None

    def record_decisions(self, accepted: list[PlannedChange], rejected: list[PlannedChange]) -> None:
        """Nach dem Anwenden: was übernommen und was in der Vorschau abgewählt wurde (zum Lernen)."""
        return None

    def editable_target(self, item: FileItem) -> str | None:
        """Aktuelles Ziel als Text, wenn der Nutzer es in der Vorschau von Hand ändern darf."""
        return None

    def edit_target(self, path: Path, target: str) -> None:
        """Von Hand geändertes Ziel speichern (zusammen mit `editable_target`)."""
        raise NotImplementedError

