"""Server für die Desktop-App (Tauri-Hülle in `desktop/`).

Die Hülle startet dieses Programm, liest die erste Zeile («PROCURATOR_READY http://127.0.0.1:PORT»)
und öffnet die Adresse in ihrem Fenster. Der Server hört nur auf 127.0.0.1 an einem freien Port.
Schliesst die Hülle (oder stürzt sie ab), endet der Standardeingang und der Server beendet sich selbst.
Im gebündelten Programm (PyInstaller) liegen Oberfläche und Hilfe neben dem Code.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
from pathlib import Path

import uvicorn

from .server.app import create_app

READY = "PROCURATOR_READY"


def frozen_root() -> Path | None:
    """Ordner des gebündelten Programms, sonst None."""
    return Path(sys._MEIPASS) if getattr(sys, "frozen", False) else None  # type: ignore[attr-defined]


def static_dir() -> Path:
    root = frozen_root()
    if root is not None:
        return root / "web_dist"
    return Path(__file__).resolve().parents[2] / "web" / "dist"


def bind() -> socket.socket:
    """Freier Port nur auf dem eigenen Rechner. Der Port steht fest, bevor die Hülle ihn erfährt."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(64)
    return sock


def watch_stdin(server: uvicorn.Server) -> None:
    """Endet der Standardeingang (Hülle geschlossen oder abgestürzt), beendet sich der Server."""
    try:
        while sys.stdin.buffer.read(4096):
            pass
    except (OSError, ValueError):
        pass
    server.should_exit = True


def main() -> None:
    sock = bind()
    port = sock.getsockname()[1]
    level = os.environ.get("PROCURATOR_LOG", "warning")  # zum Fehlersuchen: info zeigt jede Anfrage
    config = uvicorn.Config(create_app(static_dir=static_dir()), log_level=level)
    server = uvicorn.Server(config)
    threading.Thread(target=watch_stdin, args=(server,), daemon=True).start()
    print(f"{READY} http://127.0.0.1:{port}", flush=True)
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
