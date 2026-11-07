"""Plan berechnen (mit Konflikterkennung) und ausführen."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

from .fsops import execute_moves, nearest_existing
from .i18n import tr
from .journal import Journal
from .model import FileItem, Plan, PlannedChange, Result, Status
from .ops.base import Operation
from .privacy import SensitiveRules

MAX_NAME_BYTES = 255


def _key(path: Path) -> tuple[Path, str]:
    """Vergleichsschlüssel; casefold, weil macOS-Dateisysteme Gross/Klein meist ignorieren."""
    return path.parent, path.name.casefold()


def _invalid_name(name: str) -> str | None:
    if not name.strip():
        return tr("Leerer Name")
    if name in {".", ".."} or "/" in name or "\0" in name:
        return tr("Ungültiger Name")
    if len(name.encode()) > MAX_NAME_BYTES:
        return tr("Name zu lang")
    return None


def _unique_name(dst: Path, is_taken) -> Path:
    """`name.ext` -> `name 1.ext`, `name 2.ext` ... bis der Name frei ist."""
    n = 1
    while True:
        candidate = dst.with_name(f"{dst.stem} {n}{dst.suffix}")
        if not is_taken(candidate):
            return candidate
        n += 1


def make_plan(
    op: Operation,
    items: list[FileItem],
    *,
    force_unique: bool = False,
    sensitive: SensitiveRules | None = None,
) -> Plan:
    """Vorschau berechnen. Verändert nichts auf der Platte."""
    convert = op.kind == "convert"
    trash = op.kind == "trash"
    plan = Plan(operation=op.name, params={**op.params(), "force_unique": force_unique},
                kind=op.kind, runner=op.convert if convert or trash else None)

    op.prepare(items)

    # 1. Zielpfade berechnen
    for index, item in enumerate(op.order(items)):
        src = item.path
        if not os.path.lexists(src):
            plan.changes.append(PlannedChange(src, None, Status.ERROR, tr("Datei existiert nicht mehr")))
            continue
        if not convert and not os.access(src.parent, os.W_OK):
            plan.changes.append(PlannedChange(src, None, Status.ERROR, tr("Keine Schreibrechte im Ordner")))
            continue
        try:
            new_name = op.transform(item, index)
        except ValueError as exc:  # Meldung ist für den Nutzer gedacht (zum Beispiel unsicherer Pfad)
            plan.changes.append(PlannedChange(src, None, Status.ERROR, str(exc)))
            continue
        except Exception as exc:  # fehlerhafte Eingabe, z. B. ungültiger Regex
            plan.changes.append(PlannedChange(src, None, Status.ERROR, f"{type(exc).__name__}: {exc}"))
            continue
        if new_name is None:
            reason = op.skip_reason(item) or (
                tr("Nicht unterstützter Dateityp") if convert else tr("Kein Treffer"))
            plan.changes.append(PlannedChange(src, None, Status.SKIP, reason))
            continue
        if (problem := _invalid_name(new_name)) is not None:
            plan.changes.append(PlannedChange(src, None, Status.ERROR, problem))
            continue
        try:
            dst = op.destination(item, new_name)
        except ValueError as exc:
            plan.changes.append(PlannedChange(src, None, Status.ERROR, str(exc)))
            continue
        if not convert and dst == src:
            plan.changes.append(PlannedChange(src, None, Status.SKIP, tr("Name unverändert")))
            continue
        problem = op.check(item) if convert or trash else _target_problem(dst)
        if problem:
            plan.changes.append(PlannedChange(src, dst, Status.ERROR, problem))
        else:
            plan.changes.append(PlannedChange(src, dst, reason=op.note(item)))

    if trash:
        pass  # kein Ziel auf der Platte, es gibt nichts zu verwechseln
    elif convert:
        _resolve_convert(plan)
    else:
        _resolve_conflicts(plan, force_unique)
    plan.info = op.info()
    plan.needs_analysis = op.needs_analysis
    by_path = {item.path: item for item in items}
    for c in plan.changes:
        item = by_path.get(c.src)
        if item is not None:
            c.editable = op.editable_target(item)
            c.related = op.related(item)
    if sensitive is not None:  # nur eine Markierung, der Status bleibt unverändert
        hits = {item.path: sensitive.match(item) for item in items}
        for c in plan.changes:
            c.sensitive = hits.get(c.src, "")
    return plan


def _target_problem(dst: Path) -> str | None:
    """Zielordner prüfen (bei gleichem Ordner wie die Quelle reicht die Prüfung davor)."""
    anchor = nearest_existing(dst.parent)
    if not anchor.is_dir():
        return tr("Zielordner ist eine Datei")
    if not os.access(anchor, os.W_OK):
        return tr("Keine Schreibrechte im Zielordner")
    return None


def _resolve_convert(plan: Plan) -> None:
    """Konvertierungen: Quellen bleiben, vorhandene Ziele werden übersprungen (Fortsetzen)."""
    seen: dict[str, int] = {}
    for c in plan.changes:
        if c.status == Status.OK and c.dst is not None:
            seen[str(c.dst).casefold()] = seen.get(str(c.dst).casefold(), 0) + 1
    for c in plan.changes:
        if c.status != Status.OK or c.dst is None:
            continue
        if c.dst == c.src:
            c.status, c.reason = Status.ERROR, tr("Ziel ist die Quelle selbst")
        elif os.path.lexists(c.dst):
            c.status, c.reason = Status.SKIP, tr("Ziel existiert bereits")
        elif seen[str(c.dst).casefold()] > 1:
            c.status, c.reason = Status.CONFLICT, tr("Doppelter Zielname")
        elif not os.access(nearest_existing(c.dst.parent), os.W_OK):
            c.status, c.reason = Status.ERROR, tr("Keine Schreibrechte im Zielordner")


def _resolve_conflicts(plan: Plan, force_unique: bool) -> None:
    pending = [c for c in plan.changes if c.status == Status.OK]
    moving = {_key(c.src) for c in pending}  # diese Namen werden frei
    staying = {_key(c.src) for c in plan.changes if c.status != Status.OK}

    def on_disk_blocked(src: Path, dst: Path) -> bool:
        """Ziel existiert und gehört weder zu einer verschobenen Datei noch zur Quelle selbst."""
        if _key(dst) in moving or not os.path.lexists(dst):
            return False
        try:
            return not os.path.samefile(src, dst)
        except OSError:
            return True

    # Doppelte Zielnamen innerhalb des Plans
    counts: dict[tuple[Path, str], int] = {}
    for c in pending:
        assert c.dst is not None
        counts[_key(c.dst)] = counts.get(_key(c.dst), 0) + 1

    assigned: set[tuple[Path, str]] = set()
    for c in pending:
        assert c.dst is not None
        key = _key(c.dst)
        duplicate = counts[key] > 1 and key in assigned
        blocked = key in staying or on_disk_blocked(c.src, c.dst)

        if force_unique and (duplicate or blocked):
            c.dst = _unique_name(
                c.dst,
                lambda p, src=c.src: (
                    _key(p) in assigned or _key(p) in staying or on_disk_blocked(src, p)
                ),
            )
            c.reason = (c.reason + " · " if c.reason else "") + tr("Nummer angehängt (Force Unique)")
        elif counts[key] > 1 and not force_unique:
            c.status, c.reason = Status.CONFLICT, tr("Doppelter Zielname")
        elif blocked:
            c.status, c.reason = Status.CONFLICT, tr("Zieldatei existiert bereits")
        if c.status == Status.OK:
            assigned.add(_key(c.dst))


ProgressFn = Callable[[int, int, str], None]


def apply_plan(
    plan: Plan,
    journal: Journal | None = None,
    on_progress: ProgressFn | None = None,
    cancel: threading.Event | None = None,
) -> Result:
    """Alle ausführbaren Einträge umbenennen bzw. konvertieren und im Journal festhalten."""
    todo = [c for c in plan.changes if c.will_run]
    result = Result()
    pairs: list[tuple[Path, Path]] = []

    if plan.kind in ("convert", "trash"):
        assert plan.runner is not None
        for i, c in enumerate(todo):
            if cancel is not None and cancel.is_set():
                result.cancelled = True
                break
            if on_progress:
                on_progress(i, len(todo), c.src.name)
            assert c.dst is not None
            try:
                if plan.kind == "convert" and os.path.lexists(c.dst):
                    raise FileExistsError(tr("Ziel existiert bereits"))
                plan.runner(c.src, c.dst)
                result.done.append(c)
                pairs.append((c.src, c.dst))
            except Exception as exc:  # eine defekte Datei soll den Lauf nicht stoppen
                result.failed.append((c, str(exc)))
    else:
        by_pair = {(c.src, c.dst): c for c in todo}
        outcome = execute_moves([(c.src, c.dst) for c in todo])  # type: ignore[misc]
        result.done = [by_pair[p] for p in outcome.done]
        result.failed = [(by_pair[p], msg) for p, msg in outcome.failed]
        result.created_dirs = outcome.created_dirs
        pairs = outcome.done

    if on_progress:
        on_progress(len(todo), len(todo), "")
    if journal is not None and pairs:
        result.batch_id = journal.record(
            plan.operation, plan.params, pairs, plan.kind, result.created_dirs
        )
    return result
