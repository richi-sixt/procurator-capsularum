"""KI-Vorschläge: ein Sprachmodell schlägt Ordner und Dateinamen vor, du prüfst in der Vorschau."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Literal

from .. import config as cfgmod
from ..ai.learning import Decision, DecisionStore
from ..ai.organizer import OrganizeOptions, Organizer
from ..ai.proposals import Proposal, ProposalStore
from ..ai.validate import ProposalError, clean_folder, clean_name
from ..i18n import tr
from ..model import FileItem, PlannedChange
from ..privacy import rules_from_config
from .base import Operation

MAX_EDIT_DEPTH = 6


@dataclass
class AiOrganize(Operation):
    """Die Vorschau liest nur gespeicherte Vorschläge. Das Befragen des Modells ist die «Analyse».

    Ein Vorschlag mit leerem Ordner lässt die Datei, wo sie liegt. Ein Ordner ist immer relativ
    zum gewählten Ordner. Gesendet wird nur, was die Datenschutzstufe erlaubt, sensible Dateien
    bleiben zurück (siehe `privacy.split_for_config`).
    """

    name: ClassVar[str] = "ai_organize"
    needs_analysis: ClassVar[bool] = True
    sends_data: ClassVar[bool] = True

    mode: Literal["both", "folders", "names"] = "both"
    hint: str = ""
    max_depth: int = 3
    reanalyze: bool = False

    def __post_init__(self) -> None:
        self.max_depth = max(1, min(int(self.max_depth), 5))
        self.hint = self.hint.strip()[:500]
        self._props: dict[Path, Proposal] = {}
        self._withheld: dict[Path, str] = {}
        self._pending = 0
        self._roots: set[Path] = set()
        self._cfg = cfgmod.Config()

    # --- Hilfen -------------------------------------------------------------------

    def _options(self) -> OrganizeOptions:
        return OrganizeOptions(self.mode, self.hint, self.max_depth, self.reanalyze)

    def _model(self) -> str:
        return self._cfg.ai.claude_model if self._cfg.is_cloud else self._cfg.ai.ollama_model

    def _target(self, item: FileItem, p: Proposal) -> Path:
        name = p.name or item.name
        if not p.folder or item.root is None:
            return item.path.with_name(name)
        return item.root / p.folder / name

    # --- Operation ----------------------------------------------------------------

    def prepare(self, items: list[FileItem]) -> None:
        self._cfg, _warning = cfgmod.load()
        rules = rules_from_config(self._cfg)
        allow_all = (not self._cfg.is_cloud) and self._cfg.privacy.allow_sensitive_local
        self._roots = {i.root for i in items if i.root is not None}
        stats: dict[Path, os.stat_result] = {}
        for item in items:
            try:
                stats[item.path] = os.stat(item.path)
            except OSError:
                continue
        # reanalyze betrifft nur die Analyse. Die Vorschau zeigt, was gespeichert ist.
        self._props = ProposalStore().get_many(stats, self._options().run_key())
        self._withheld = {}
        if not allow_all:
            self._withheld = {i.path: h for i in items if (h := rules.match(i))}
        allowed = [p for p in stats if p not in self._withheld]
        # «Neu berechnen» heisst: alle erlaubten Dateien gelten wieder als offen
        self._pending = len(allowed) if self.reanalyze else sum(1 for p in allowed if p not in self._props)

    def transform(self, item: FileItem, index: int) -> str | None:
        p = self._props.get(item.path)
        if p is None:
            return None
        if p.error:
            raise ValueError(tr("Unbrauchbarer Vorschlag: {error}", error=p.error))
        if self._target(item, p) == item.path:
            return None
        return p.name or item.name

    def destination(self, item: FileItem, new_name: str) -> Path:
        p = self._props[item.path]
        return self._target(item, Proposal(p.folder, new_name))

    def skip_reason(self, item: FileItem) -> str | None:
        if item.path in self._withheld:
            return tr("Sensibel ({hit}): wird nicht an das Modell gesendet", hit=self._withheld[item.path])
        p = self._props.get(item.path)
        if p is None:
            return tr("Noch nicht analysiert")
        if p.reason:
            return tr("Keine Änderung vorgeschlagen: {reason}", reason=p.reason)
        return tr("Keine Änderung vorgeschlagen")

    def note(self, item: FileItem) -> str:
        p = self._props.get(item.path)
        if p is None:
            return ""
        if p.edited:
            return tr("Von dir geändert")
        sure = tr("Sicherheit {percent} %", percent=round(p.confidence * 100))
        return f"{p.reason} ({sure})" if p.reason else sure

    def editable_target(self, item: FileItem) -> str | None:
        p = self._props.get(item.path)
        if p is None or (item.path in self._withheld):
            return None
        if p.error:
            return item.name
        return f"{p.folder}/{p.name}" if p.folder else (p.name or item.name)

    def info(self) -> dict[str, Any]:
        cfg = self._cfg
        hint = tr(
            "Das Modell ({provider}, {model}, {where}) soll für {n} Dateien Ordner und Namen vorschlagen. "
            "Dabei wird nur gesendet, was die Datenschutzstufe erlaubt.",
            provider=cfg.ai.provider, model=self._model(),
            where=tr("Cloud") if cfg.is_cloud else tr("lokal"), n=self._pending)
        return {
            "pendingFiles": self._pending, "pendingBytes": 0, "analysisHint": hint,
            "analyzed": len(self._props), "withheld": len(self._withheld),
            "provider": cfg.ai.provider, "model": self._model(), "isCloud": cfg.is_cloud,
            "requiresConfirmation": cfg.requires_confirmation,
            "privacyLevel": cfg.ai.privacy_level, "mode": self.mode,
        }

    def analyze(
        self,
        items: list[FileItem],
        on_progress: Callable[[int, int, str], None] | None = None,
        cancel: threading.Event | None = None,
        confirmed: bool = False,
    ) -> None:
        cfg, _warning = cfgmod.load()
        Organizer(cfg).analyze(items, self._options(), on_progress, cancel, confirmed)

    def send_preview(self, items: list[FileItem]) -> dict[str, Any] | None:
        cfg, _warning = cfgmod.load()
        return Organizer(cfg).preview(items, self._options())

    def _decision(self, kind: str, c: PlannedChange) -> Decision | None:
        p = self._props.get(c.src)
        if p is None or p.error or c.dst is None:
            return None
        root = next((r for r in self._roots if c.src.is_relative_to(r)), None)
        if root is None:
            return None
        try:
            from_folder = "" if c.src.parent == root else c.src.parent.relative_to(root).as_posix()
            to_folder = "" if c.dst.parent == root else c.dst.parent.relative_to(root).as_posix()
        except ValueError:
            return None
        return Decision(kind, c.src.name, c.src.suffix.lower(), from_folder, to_folder, c.dst.name)

    def record_decisions(self, accepted: list[PlannedChange], rejected: list[PlannedChange]) -> None:
        """Übernommene, korrigierte und abgewählte Vorschläge lokal merken (siehe `ai.learning`)."""
        if not self._cfg.ai.learn:
            return
        found: list[Decision] = []
        for c in accepted:
            kind = "edited" if (self._props.get(c.src) and self._props[c.src].edited) else "accepted"
            if d := self._decision(kind, c):
                found.append(d)
        for c in rejected:
            p = self._props.get(c.src)
            if p is not None and not p.edited and (d := self._decision("rejected", c)):
                found.append(d)
        DecisionStore().record(found, rules_from_config(self._cfg))

    def edit_target(self, path: Path, target: str) -> None:
        """Ziel von Hand ändern. Gleiche Sicherheitsprüfung wie bei Vorschlägen des Modells."""
        text = target.strip().replace("\\", "/")
        if not text:
            raise ValueError(tr("Ziel fehlt"))
        folder_text, _, name_text = text.rpartition("/")
        item = FileItem(path)
        try:
            folder = clean_folder(folder_text, MAX_EDIT_DEPTH) if self.mode != "names" else ""
            name = clean_name(name_text, path.name, path.suffix) if name_text else path.name
        except ProposalError as exc:
            raise ValueError(str(exc)) from exc
        if self.mode == "folders":
            name = item.name
        st = os.stat(path)
        ProposalStore().put_many(
            [(path, st, Proposal(folder, name, "", 1.0, edited=True, model="manuell"))],
            self._options().run_key())
