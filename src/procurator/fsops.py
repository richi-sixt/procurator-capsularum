"""Dateisystem-Zugriff: Verschieben auch über Ordner und Laufwerke, sicher und mit Rückweg."""

from __future__ import annotations

import filecmp
import os
import shutil
import uuid
from pathlib import Path
from typing import NamedTuple

Pair = tuple[Path, Path]


class MoveOutcome(NamedTuple):
    done: list[Pair]
    failed: list[tuple[Pair, str]]
    created_dirs: list[Path]  # von uns neu angelegte Ordner (oben zuerst), für Undo


def nearest_existing(path: Path) -> Path:
    while not path.exists() and path.parent != path:
        path = path.parent
    return path


def _same_device(src: Path, dst_parent: Path) -> bool:
    return os.stat(src).st_dev == os.stat(nearest_existing(dst_parent)).st_dev


def _make_dirs(path: Path) -> list[Path]:
    """Ordner anlegen und die neu entstandenen zurückgeben (oben zuerst)."""
    missing: list[Path] = []
    p = path
    while not p.exists() and p.parent != p:
        missing.append(p)
        p = p.parent
    path.mkdir(parents=True, exist_ok=True)
    return list(reversed(missing))


def _copy_verify_delete(src: Path, dst: Path) -> None:
    """Anderes Laufwerk: kopieren, Byte für Byte prüfen, erst dann das Original löschen.

    Das Original bleibt bis zum Schluss unter seinem Namen liegen; bei jedem Fehler
    wird nur die halbfertige Kopie entfernt.
    """
    part = dst.with_name(dst.name + ".part")
    try:
        shutil.copy2(src, part)
        if not filecmp.cmp(src, part, shallow=False):
            raise OSError("Kopie weicht vom Original ab")
        if os.path.lexists(dst):
            raise FileExistsError(f"Ziel existiert bereits: {dst.name}")
        os.rename(part, dst)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    try:
        src.unlink()
    except OSError as exc:
        raise OSError(f"Kopie liegt im Ziel, Original konnte nicht gelöscht werden: {exc}") from exc


def execute_moves(pairs: list[Pair]) -> MoveOutcome:
    """Alle (src, dst) verschieben. Fehlende Zielordner werden angelegt.

    Auf demselben Laufwerk in zwei Phasen: jede Quelle bekommt erst einen temporären Namen,
    dann das Ziel. So funktionieren Tausch (a -> b, b -> a) und Ketten. Auf ein anderes
    Laufwerk wird kopiert, geprüft und erst dann gelöscht. Ein vorhandenes Ziel wird nie
    überschrieben.
    """
    local: list[Pair] = []
    remote: list[Pair] = []
    failed: list[tuple[Pair, str]] = []
    for pair in pairs:
        try:
            (local if _same_device(pair[0], pair[1].parent) else remote).append(pair)
        except OSError as exc:
            failed.append((pair, str(exc)))

    created: list[Path] = []
    done: list[Pair] = []

    # Phase 1: Quellen auf temporäre Namen
    staged: list[tuple[Pair, Path]] = []
    for pair in local:
        src, _dst = pair
        tmp = src.with_name(f".pc-{uuid.uuid4().hex}.tmp")
        try:
            os.rename(src, tmp)
        except OSError as exc:
            failed.append((pair, str(exc)))
            continue
        staged.append((pair, tmp))

    # Phase 2: temporäre Namen auf die Ziele
    for pair, tmp in staged:
        src, dst = pair
        try:
            if os.path.lexists(dst):
                raise FileExistsError(f"Ziel existiert bereits: {dst.name}")
            created += _make_dirs(dst.parent)
            os.rename(tmp, dst)
            done.append(pair)
        except OSError as exc:
            failed.append((pair, str(exc)))
            try:
                os.rename(tmp, src)
            except OSError as restore_exc:  # sehr unwahrscheinlich; Datei bleibt unter tmp
                failed[-1] = (pair, f"{exc}; Wiederherstellen fehlgeschlagen: {restore_exc} ({tmp})")

    # Anderes Laufwerk
    for pair in remote:
        src, dst = pair
        try:
            created += _make_dirs(dst.parent)
            _copy_verify_delete(src, dst)
            done.append(pair)
        except OSError as exc:
            failed.append((pair, str(exc)))

    # Leere, von uns angelegte Ordner wieder entfernen, wenn nichts darin gelandet ist
    for d in sorted(created, key=lambda p: len(p.parts), reverse=True):
        if not any(d in dst.parents for _src, dst in done):
            try:
                d.rmdir()
            except OSError:
                pass
    created = [d for d in created if d.exists()]
    return MoveOutcome(done, failed, created)
