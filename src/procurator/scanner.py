"""Ordner einlesen: optional rekursiv, natürlich sortiert, ohne Systemdateien."""

from __future__ import annotations

import re
from pathlib import Path

from .model import FileItem

IGNORED = {".DS_Store", "Thumbs.db", "desktop.ini"}


def natural_key(text: str) -> list[object]:
    """Sortierschlüssel, der Zahlen als Zahlen vergleicht (img2 vor img10)."""
    return [int(p) if p.isdigit() else p.casefold() for p in re.split(r"(\d+)", text)]


def scan(
    paths: list[Path] | Path,
    *,
    recursive: bool = False,
    include_hidden: bool = False,
) -> list[FileItem]:
    """Dateien aus Ordnern und Einzeldateien sammeln. Ordner selbst werden nie aufgenommen."""
    roots = [paths] if isinstance(paths, Path) else list(paths)
    found: dict[Path, FileItem] = {}
    for root in roots:
        root = root.expanduser()
        if root.is_file():
            found[root] = FileItem(root, root.parent)
            continue
        walker = root.rglob("*") if recursive else root.iterdir()
        for p in walker:
            if not p.is_file() or p.name in IGNORED or p.name.startswith("._"):
                continue
            if not include_hidden and any(
                part.startswith(".") for part in p.relative_to(root).parts
            ):
                continue
            found[p] = FileItem(p, root)
    return sorted(found.values(), key=lambda i: natural_key(str(i.path)))
