"""Speicher für KI-Vorschläge (lokale SQLite-Tabelle neben dem Datei-Index).

Die Vorschau liest nur von hier, das Modell wird nie bei einer Vorschau befragt.
Ein Vorschlag gilt nur, solange Grösse und Änderungszeit der Datei gleich sind.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..index import _key, default_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    path TEXT NOT NULL,
    run_key TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    folder TEXT NOT NULL,
    name TEXT NOT NULL,
    reason TEXT NOT NULL,
    confidence REAL NOT NULL,
    edited INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL,
    PRIMARY KEY (path, run_key)
);
"""


@dataclass
class Proposal:
    folder: str = ""  # relativ zum gewählten Ordner, leer = Datei bleibt, wo sie liegt
    name: str = ""
    reason: str = ""
    confidence: float = 0.0
    edited: bool = False  # vom Nutzer korrigiert
    error: str = ""  # Vorschlag unbrauchbar (zum Beispiel unsicherer Pfad)
    model: str = ""


class ProposalStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def get_many(self, files: dict[Path, os.stat_result], run_key: str) -> dict[Path, Proposal]:
        """Gültige Vorschläge (gleiche Grösse und Zeit wie jetzt) für die angegebenen Dateien."""
        by_key = {_key(p): p for p in files}
        out: dict[Path, Proposal] = {}
        keys = list(by_key)
        with self._connect() as db:
            for start in range(0, len(keys), 500):
                chunk = keys[start:start + 500]
                marks = ",".join("?" * len(chunk))
                rows = db.execute(
                    "SELECT path, size, mtime_ns, folder, name, reason, confidence, edited, error, model "
                    f"FROM proposals WHERE run_key = ? AND path IN ({marks})",
                    [run_key, *chunk],
                ).fetchall()
                for r in rows:
                    path = by_key[r[0]]
                    st = files[path]
                    if r[1] == st.st_size and r[2] == st.st_mtime_ns:
                        out[path] = Proposal(r[3], r[4], r[5], r[6], bool(r[7]), r[8], r[9])
        return out

    def put_many(
        self, entries: list[tuple[Path, os.stat_result, Proposal]], run_key: str
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as db:
            db.executemany(
                "INSERT OR REPLACE INTO proposals (path, run_key, size, mtime_ns, folder, name, "
                "reason, confidence, edited, error, model, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(_key(p), run_key, st.st_size, st.st_mtime_ns, pr.folder, pr.name, pr.reason,
                  pr.confidence, int(pr.edited), pr.error, pr.model, now) for p, st, pr in entries],
            )

    def count(self, run_key: str | None = None) -> int:
        with self._connect() as db:
            if run_key is None:
                return int(db.execute("SELECT COUNT(*) FROM proposals").fetchone()[0])
            return int(db.execute("SELECT COUNT(*) FROM proposals WHERE run_key = ?",
                                  (run_key,)).fetchone()[0])
