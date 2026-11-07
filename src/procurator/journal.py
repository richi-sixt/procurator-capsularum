"""SQLite-Journal: History aller Läufe und Undo."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from platformdirs import user_data_path

from .fsops import execute_moves
from .i18n import tr

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    operation TEXT NOT NULL,
    params TEXT NOT NULL,
    undone INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL DEFAULT 'move'
);
CREATE TABLE IF NOT EXISTS dirs (
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS presets (
    name TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    params TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS moves (
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    seq INTEGER NOT NULL,
    src TEXT NOT NULL,
    dst TEXT NOT NULL
);
"""


def default_path() -> Path:
    env = os.environ.get("PC_JOURNAL")
    if env:
        return Path(env)
    return user_data_path("procurator-capsularum", ensure_exists=True) / "journal.db"


@dataclass
class Batch:
    id: int
    ts: str
    operation: str
    params: dict
    undone: bool
    count: int
    kind: str = "move"


class Journal:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)
            cols = {r[1] for r in db.execute("PRAGMA table_info(batches)")}
            if "kind" not in cols:  # Journal aus Phase 1/2
                db.execute("ALTER TABLE batches ADD COLUMN kind TEXT NOT NULL DEFAULT 'move'")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def record(
        self,
        operation: str,
        params: dict,
        moves: list[tuple[Path, Path]],
        kind: str = "move",
        created_dirs: list[Path] | None = None,
    ) -> int:
        with self._connect() as db:
            cur = db.execute(
                "INSERT INTO batches (ts, operation, params, kind) VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), operation,
                 json.dumps(params, default=str), kind),
            )
            batch_id = cur.lastrowid
            db.executemany(
                "INSERT INTO moves (batch_id, seq, src, dst) VALUES (?, ?, ?, ?)",
                [(batch_id, i, str(s), str(d)) for i, (s, d) in enumerate(moves)],
            )
            db.executemany(
                "INSERT INTO dirs (batch_id, path) VALUES (?, ?)",
                [(batch_id, str(d)) for d in created_dirs or []],
            )
        assert batch_id is not None
        return batch_id

    def batches(self, limit: int = 20) -> list[Batch]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT b.id, b.ts, b.operation, b.params, b.undone, "
                "(SELECT COUNT(*) FROM moves m WHERE m.batch_id = b.id), b.kind "
                "FROM batches b ORDER BY b.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [Batch(r[0], r[1], r[2], json.loads(r[3]), bool(r[4]), r[5], r[6]) for r in rows]

    def moves(self, batch_id: int) -> list[tuple[Path, Path]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT src, dst FROM moves WHERE batch_id = ? ORDER BY seq", (batch_id,)
            ).fetchall()
        return [(Path(s), Path(d)) for s, d in rows]

    def save_preset(self, name: str, operation: str, params: dict) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO presets (name, operation, params) VALUES (?, ?, ?)",
                (name, operation, json.dumps(params, default=str)),
            )

    def presets(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT name, operation, params FROM presets ORDER BY name").fetchall()
        return [{"name": n, "operation": o, "params": json.loads(p)} for n, o, p in rows]

    def delete_preset(self, name: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM presets WHERE name = ?", (name,))

    def batch_kind(self, batch_id: int) -> str | None:
        """«move» (umbenennen, verschieben) oder «convert» (neue Dateien erzeugt)."""
        with self._connect() as db:
            row = db.execute("SELECT kind FROM batches WHERE id = ?", (batch_id,)).fetchone()
        return row[0] if row else None

    def latest_undoable(self) -> int | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT id FROM batches WHERE undone = 0 ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    def undo(self, batch_id: int) -> tuple[int, list[str]]:
        """Lauf rückgängig machen. Gibt (Anzahl zurückgesetzt, Fehlermeldungen) zurück."""
        with self._connect() as db:
            row = db.execute(
                "SELECT undone, kind FROM batches WHERE id = ?", (batch_id,)
            ).fetchone()
        if row is None:
            return 0, [tr("Lauf {id} existiert nicht", id=batch_id)]
        if row[0]:
            return 0, [tr("Lauf {id} wurde schon rückgängig gemacht", id=batch_id)]

        if row[1] == "convert":
            return self._undo_convert(batch_id)

        reverse = [(dst, src) for src, dst in self.moves(batch_id)]
        errors: list[str] = []
        runnable: list[tuple[Path, Path]] = []
        for dst, src in reverse:
            if not dst.exists():
                errors.append(tr("{name}: Datei nicht mehr vorhanden", name=dst.name))
            else:
                runnable.append((dst, src))
        outcome = execute_moves(runnable)
        done, failed = outcome.done, outcome.failed
        errors += [f"{pair[0].name}: {msg}" for pair, msg in failed]
        self._remove_created_dirs(batch_id)
        if not errors:
            with self._connect() as db:
                db.execute("UPDATE batches SET undone = 1 WHERE id = ?", (batch_id,))
        return len(done), errors

    def _remove_created_dirs(self, batch_id: int) -> None:
        """Beim Lauf angelegte Ordner entfernen, aber nur wenn sie jetzt leer sind."""
        with self._connect() as db:
            rows = db.execute("SELECT path FROM dirs WHERE batch_id = ?", (batch_id,)).fetchall()
        for (path,) in sorted(rows, key=lambda r: len(Path(r[0]).parts), reverse=True):
            try:
                Path(path).rmdir()
            except OSError:  # nicht leer oder schon weg: stehen lassen
                pass

    def _undo_convert(self, batch_id: int) -> tuple[int, list[str]]:
        """Erzeugte Dateien löschen. Die Quellen wurden nie verändert."""
        removed = 0
        errors: list[str] = []
        for src, dst in self.moves(batch_id):
            if dst == src:  # Sicherung: die Quelle wird nie gelöscht
                errors.append(tr("{name}: Ziel ist die Quelle, übersprungen", name=dst.name))
                continue
            try:
                dst.unlink()
                removed += 1
            except FileNotFoundError:
                errors.append(tr("{name}: Datei nicht mehr vorhanden", name=dst.name))
            except OSError as exc:
                errors.append(f"{dst.name}: {exc}")
        if not errors:
            with self._connect() as db:
                db.execute("UPDATE batches SET undone = 1 WHERE id = ?", (batch_id,))
        return removed, errors
