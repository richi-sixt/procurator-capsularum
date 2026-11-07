"""Eine Datei im Dateimanager zeigen (Finder, Explorer, Dateiliste), damit man sie selbst prüfen kann."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def command_for(path: Path, platform: str | None = None) -> list[str]:
    """Der Befehl, der `path` im Dateimanager zeigt. Bei fehlender Datei wird der Ordner geöffnet."""
    platform = platform or sys.platform
    target = path if path.exists() else path.parent
    if platform == "darwin":
        return ["open", "-R", str(target)] if target == path else ["open", str(target)]
    if platform == "win32":
        return ["explorer", f"/select,{target}"] if target == path else ["explorer", str(target)]
    return ["xdg-open", str(target if target.is_dir() else target.parent)]


def reveal(path: Path) -> None:
    """Zeigt die Datei im Dateimanager. Wirft `OSError`, wenn nichts gezeigt werden kann."""
    if not path.exists() and not path.parent.exists():
        raise FileNotFoundError(str(path))
    subprocess.Popen(command_for(path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
