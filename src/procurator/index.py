"""Datei-Index: Grösse, Zeitstempel und Inhalts-Hashes in einer lokalen SQLite-Datenbank.

Zweck: Dubletten finden und wissen, welche Dateien schon bekannt sind, ohne jedes Mal alles
neu zu lesen. Gespeichert werden nur Metadaten und Hashes, nie Dateiinhalte.

Gehasht wird so wenig wie möglich: Zuerst zählt die Grösse (verschiedene Grösse = verschiedener
Inhalt), dann ein Hash der ersten 64 KB, erst danach der volle SHA-256 der verbleibenden
Kandidaten. Eine Datei mit gleicher Grösse und gleichem Zeitstempel wie beim letzten Mal wird
nicht erneut gelesen.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from platformdirs import user_data_path

from .model import FileItem
from .scanner import natural_key

PARTIAL_BYTES = 64 * 1024
COMMIT_EVERY = 500

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    dev INTEGER NOT NULL,
    inode INTEGER NOT NULL,
    partial TEXT,
    sha256 TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS files_size ON files(size);
CREATE INDEX IF NOT EXISTS files_sha ON files(sha256);
"""

ProgressFn = Callable[[int, int, str], None]


def default_path() -> Path:
    env = os.environ.get("PC_INDEX")
    if env:
        return Path(env)
    return user_data_path("procurator-capsularum", ensure_exists=True) / "index.db"


def _key(path: Path) -> str:
    return os.path.realpath(path)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class RefreshResult:
    seen: int = 0
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    hashed: int = 0  # volle Hashes, die in diesem Lauf berechnet wurden
    skipped_links: int = 0
    errors: list[tuple[Path, str]] = field(default_factory=list)
    cancelled: bool = False


@dataclass
class DuplicateGroup:
    sha256: str
    size: int
    files: list[Path]  # gleicher Inhalt, jede physische Datei einmal
    hardlinks: dict[Path, list[Path]] = field(default_factory=dict)  # Datei -> weitere Namen

    @property
    def reclaimable(self) -> int:
        """Platz, den man gewinnt, wenn nur eine Datei bleibt."""
        return self.size * (len(self.files) - 1)


def _full_hash(path: Path) -> str:
    with open(path, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def _partial_hash(path: Path) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read(PARTIAL_BYTES)).hexdigest()


class FileIndex:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    # --- Metadaten aktualisieren ---------------------------------------------

    def refresh(
        self,
        items: Iterable[FileItem],
        *,
        hash_all: bool = False,
        on_progress: ProgressFn | None = None,
        cancel: threading.Event | None = None,
    ) -> RefreshResult:
        """Grösse und Zeitstempel erfassen. Mit `hash_all` auch den vollen Hash jeder Datei."""
        items = list(items)
        result = RefreshResult()
        db = self._connect()
        try:
            for i, item in enumerate(items):
                if cancel is not None and cancel.is_set():
                    result.cancelled = True
                    break
                if on_progress:
                    on_progress(i, len(items), item.name)
                self._refresh_one(db, item, hash_all, result)
                if i % COMMIT_EVERY == COMMIT_EVERY - 1:
                    db.commit()
            db.commit()
        finally:
            db.close()
        if on_progress and not result.cancelled:
            on_progress(len(items), len(items), "")
        return result

    def _refresh_one(
        self, db: sqlite3.Connection, item: FileItem, hash_all: bool, result: RefreshResult
    ) -> None:
        if item.path.is_symlink():  # ein Link ist keine zweite Kopie
            result.skipped_links += 1
            return
        try:
            st = os.stat(item.path)
        except OSError as exc:
            result.errors.append((item.path, str(exc)))
            return
        key = _key(item.path)
        result.seen += 1
        row = db.execute(
            "SELECT size, mtime_ns, sha256 FROM files WHERE path = ?", (key,)
        ).fetchone()
        now = _now()
        if row is not None and row[0] == st.st_size and row[1] == st.st_mtime_ns:
            result.unchanged += 1
            db.execute("UPDATE files SET last_seen = ?, dev = ?, inode = ? WHERE path = ?",
                       (now, st.st_dev, st.st_ino, key))
            have_hash = row[2] is not None
        else:
            if row is None:
                result.new += 1
                db.execute(
                    "INSERT INTO files (path, size, mtime_ns, dev, inode, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (key, st.st_size, st.st_mtime_ns, st.st_dev, st.st_ino, now, now),
                )
            else:  # geändert: alte Hashes sind ungültig, first_seen bleibt
                result.changed += 1
                db.execute(
                    "UPDATE files SET size = ?, mtime_ns = ?, dev = ?, inode = ?, partial = NULL, "
                    "sha256 = NULL, last_seen = ? WHERE path = ?",
                    (st.st_size, st.st_mtime_ns, st.st_dev, st.st_ino, now, key),
                )
            have_hash = False
        if hash_all and not have_hash:
            self._store_full_hash(db, item.path, key, st, result)

    def _store_full_hash(
        self, db: sqlite3.Connection, path: Path, key: str, st: os.stat_result,
        result: RefreshResult,
    ) -> str | None:
        try:
            digest = _full_hash(path)
            after = os.stat(path)
        except OSError as exc:
            result.errors.append((path, str(exc)))
            return None
        if after.st_size != st.st_size or after.st_mtime_ns != st.st_mtime_ns:
            result.errors.append((path, "Datei hat sich während des Lesens geändert"))
            return None
        db.execute("UPDATE files SET sha256 = ? WHERE path = ?", (digest, key))
        result.hashed += 1
        return digest

    # --- Dubletten -----------------------------------------------------------------

    def duplicates(
        self,
        items: Iterable[FileItem],
        *,
        min_size: int = 1,
        on_progress: ProgressFn | None = None,
        cancel: threading.Event | None = None,
    ) -> tuple[list[DuplicateGroup], RefreshResult]:
        """Gruppen gleicher Dateien unter `items`. Liest nur, was nötig ist (siehe Modul-Text)."""
        items = [i for i in items if not i.path.is_symlink()]
        by_key = {_key(i.path): i.path for i in items}
        result = self.refresh(items, on_progress=on_progress, cancel=cancel)
        if result.cancelled:
            return [], result

        db = self._connect()
        try:
            rows = self._rows(db, list(by_key))
            by_size: dict[int, list[str]] = defaultdict(list)
            for key, r in rows.items():
                if r["size"] >= max(min_size, 1):
                    by_size[r["size"]].append(key)
            # Phase 1: Teil-Hash nur für Dateien, deren Grösse mehrfach vorkommt
            todo = [k for ks in by_size.values() if len(ks) > 1 for k in ks if rows[k]["partial"] is None]
            for n, key in enumerate(todo):
                if cancel is not None and cancel.is_set():
                    result.cancelled = True
                    return [], result
                if on_progress:
                    on_progress(n, len(todo), f"Anfang lesen: {Path(key).name}")
                try:
                    rows[key]["partial"] = _partial_hash(Path(key))
                except OSError as exc:
                    result.errors.append((by_key[key], str(exc)))
                    continue
                db.execute("UPDATE files SET partial = ? WHERE path = ?", (rows[key]["partial"], key))
            db.commit()

            # Phase 2: voller Hash nur für Dateien mit gleicher Grösse und gleichem Anfang
            by_partial: dict[tuple[int, str], list[str]] = defaultdict(list)
            for ks in by_size.values():
                if len(ks) > 1:
                    for k in ks:
                        if rows[k]["partial"] is not None:
                            by_partial[(rows[k]["size"], rows[k]["partial"])].append(k)
            need_full = [k for ks in by_partial.values() if len(ks) > 1 for k in ks
                         if rows[k]["sha256"] is None]
            for n, key in enumerate(need_full):
                if cancel is not None and cancel.is_set():
                    result.cancelled = True
                    return [], result
                if on_progress:
                    on_progress(n, len(need_full), f"Vergleichen: {Path(key).name}")
                try:
                    st = os.stat(key)
                except OSError as exc:
                    result.errors.append((by_key[key], str(exc)))
                    continue
                rows[key]["sha256"] = self._store_full_hash(db, Path(key), key, st, result)
            db.commit()
        finally:
            db.close()

        groups: dict[str, list[str]] = defaultdict(list)
        for ks in by_partial.values():
            for k in ks:
                if rows[k]["sha256"]:
                    groups[rows[k]["sha256"]].append(k)
        return self._build_groups(groups, rows, by_key), result

    def _build_groups(
        self, groups: dict[str, list[str]], rows: dict[str, dict[str, Any]], by_key: dict[str, Path]
    ) -> list[DuplicateGroup]:
        out: list[DuplicateGroup] = []
        for digest, keys in groups.items():
            physical: dict[tuple[int, int], list[str]] = defaultdict(list)
            for k in keys:  # Hardlinks (gleicher Inode) sind eine physische Datei
                physical[(rows[k]["dev"], rows[k]["inode"])].append(k)
            if len(physical) < 2:
                continue
            files: list[Path] = []
            links: dict[Path, list[Path]] = {}
            for ks in physical.values():
                ks.sort(key=lambda k: natural_key(k))
                main = by_key[ks[0]]
                files.append(main)
                if len(ks) > 1:
                    links[main] = [by_key[k] for k in ks[1:]]
            files.sort(key=lambda p: natural_key(str(p)))
            out.append(DuplicateGroup(digest, rows[keys[0]]["size"], files, links))
        out.sort(key=lambda g: (-g.reclaimable, natural_key(str(g.files[0]))))
        return out

    @staticmethod
    def _rows(db: sqlite3.Connection, keys: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for start in range(0, len(keys), 500):
            chunk = keys[start:start + 500]
            marks = ",".join("?" * len(chunk))
            for r in db.execute(
                f"SELECT path, size, dev, inode, partial, sha256 FROM files WHERE path IN ({marks})",
                chunk,
            ):
                out[r[0]] = {"size": r[1], "dev": r[2], "inode": r[3], "partial": r[4], "sha256": r[5]}
        return out

    # --- Abfragen und Pflege -------------------------------------------------------

    def lookup(self, path: Path) -> dict[str, Any] | None:
        """Gespeicherte Angaben zu einer Datei (oder None, wenn unbekannt)."""
        with self._connect() as db:
            r = db.execute(
                "SELECT size, mtime_ns, partial, sha256, first_seen, last_seen "
                "FROM files WHERE path = ?", (_key(path),)
            ).fetchone()
        if r is None:
            return None
        return {"size": r[0], "mtime_ns": r[1], "partial": r[2], "sha256": r[3],
                "first_seen": r[4], "last_seen": r[5]}

    def paths_with_hash(self, sha256: str) -> list[Path]:
        """Alle bekannten Dateien mit diesem Inhalt («Hey, die kenne ich schon!»)."""
        with self._connect() as db:
            rows = db.execute("SELECT path FROM files WHERE sha256 = ? ORDER BY path",
                              (sha256,)).fetchall()
        return [Path(r[0]) for r in rows]

    def prune(self, roots: Iterable[Path]) -> int:
        """Einträge unterhalb von `roots` löschen, deren Datei nicht mehr existiert."""
        removed = 0
        with self._connect() as db:
            for root in roots:
                prefix = _key(root).rstrip("/") + "/"
                gone = [p for (p,) in db.execute(
                    "SELECT path FROM files WHERE substr(path, 1, ?) = ?", (len(prefix), prefix)
                ).fetchall() if not os.path.lexists(p)]
                db.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in gone])
                removed += len(gone)
        return removed

    def forget(self, path: Path) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM files WHERE path = ?", (_key(path),))

    def stats(self) -> dict[str, Any]:
        with self._connect() as db:
            n, hashed, total = db.execute(
                "SELECT COUNT(*), COUNT(sha256), COALESCE(SUM(size), 0) FROM files"
            ).fetchone()
        return {"files": n, "hashed": hashed, "bytes": total, "path": str(self.path),
                "dbBytes": self.path.stat().st_size if self.path.exists() else 0}
