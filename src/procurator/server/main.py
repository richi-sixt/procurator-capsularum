"""Einstiegspunkt für uvicorn: API plus gebaute Web-UI (falls vorhanden)."""

from pathlib import Path

from .app import create_app

# Repo-Layout: <repo>/web/dist; in einer Desktop-Version wird der Pfad gebündelt.
STATIC = Path(__file__).resolve().parents[3] / "web" / "dist"

app = create_app(static_dir=STATIC)
