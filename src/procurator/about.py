"""Angaben zum Programm: Version, Autorin, Lizenz und die Lizenzen der verwendeten Bausteine.

Die Liste der Bausteine wird zur Laufzeit aus den installierten Paketen gelesen, damit sie nie
veraltet. Dazu zählen nur Pakete, die das Programm wirklich braucht (keine Entwicklungswerkzeuge).
"""

from __future__ import annotations

import importlib.metadata as md
import json
import os
import platform
import re
import sys
from pathlib import Path
from typing import Any

from .i18n import tr

NAME = "Procurator Capsularum"
AUTHOR = "Rüchan Sixt"
YEAR = 2026
REPO_URL = "https://github.com/richi-sixt/procurator-capsularum"
LICENSE_ID = "AGPL-3.0-or-later"
LICENSE_NAME = "GNU Affero General Public License, Version 3 oder neuer"
LICENSE_URL = "https://www.gnu.org/licenses/agpl-3.0.html"
DIST_NAME = "procurator-capsularum"
# Gebündelt (Desktop-App) liegt die Oberfläche neben dem Code, sonst im Repository.
WEB_DIR = (Path(sys._MEIPASS) / "web" if getattr(sys, "frozen", False)  # type: ignore[attr-defined]
           else Path(__file__).resolve().parents[2] / "web")

NOTICE = (
    "Dieses Programm ist freie Software. Du darfst es unter den Bedingungen der GNU Affero General "
    "Public License, Version 3 oder neuer, weitergeben und ändern. Es wird ohne jede Gewährleistung "
    "angeboten, auch ohne die stillschweigende Zusicherung der Marktgängigkeit oder der Eignung für "
    "einen bestimmten Zweck. Wer eine geänderte Version weitergibt oder als Dienst über ein Netzwerk "
    "anbietet, muss den Quellcode der Änderungen unter derselben Lizenz zugänglich machen."
)

# Ideen, die in das Programm eingeflossen sind. Es wurde kein Code übernommen.
INSPIRATION = [
    {"name": "NameChanger", "note": "Vorbild für die Umbenennen-Funktionen und die Vorschau-Tabelle"},
    {"name": "file-whisperer", "url": "https://github.com/zeeshansayyed/file-whisperer",
     "note": "Idee: scannen, prüfen, anwenden und Ordnen mit einem Sprachmodell (nur das Konzept)"},
]

# Programme, die das Programm aufruft, aber nicht mitliefert. Für sie gelten eigene Lizenzen.
EXTERNAL = [
    {"name": "unar", "url": "https://theunarchiver.com/command-line",
     "note": "Entpacken von CBR/RAR, separat installiert"},
    {"name": "Ollama", "url": "https://ollama.com/",
     "note": "Lokale Sprachmodelle für die KI-Vorschläge, separat installiert"},
]

# Nur in der Desktop-App: Programme, die mitgeliefert werden (die Hülle setzt PROCURATOR_DESKTOP).
BUNDLED = [
    {"name": "Tauri", "url": "https://tauri.app/",
     "note": "Fenster der Desktop-App (MIT oder Apache-2.0), mitgeliefert"},
    {"name": "PyInstaller", "url": "https://pyinstaller.org/",
     "note": "Bündelt Python und den Server (GPL-2.0 mit Ausnahme für gebündelte Programme), mitgeliefert"},
]


def _localized(entry: dict[str, str]) -> dict[str, str]:
    """Ein Eintrag mit übersetztem Hinweis."""
    return {**entry, "note": tr(entry["note"])} if "note" in entry else dict(entry)


def external() -> list[dict[str, str]]:
    return EXTERNAL + BUNDLED if os.environ.get("PROCURATOR_DESKTOP") else EXTERNAL


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse(req: str) -> tuple[str, set[str], str | None]:
    """Name, angeforderte Extras und die `extra == "…"`-Bedingung einer Abhängigkeit."""
    base, _, marker = req.partition(";")
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?", base)
    if not m:
        return "", set(), None
    extras = {e.strip() for e in (m.group(2) or "").split(",") if e.strip()}
    cond = re.search(r"extra\s*==\s*['\"]([^'\"]+)['\"]", marker)
    return _norm(m.group(1)), extras, cond.group(1) if cond else None


def license_of(dist: md.Distribution) -> str:
    meta = dist.metadata
    expr = (meta.get("License-Expression") or "").strip()
    if expr:
        return expr
    lic = (meta.get("License") or "").strip()
    if lic and "\n" not in lic and len(lic) <= 80:
        return lic
    classes = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or []
               if c.startswith("License ::") and "OSI Approved" not in c.split("::")[-1]]
    if classes:
        return "; ".join(classes)
    return lic.splitlines()[0][:60] if lic else "unbekannt"


def python_components() -> list[dict[str, Any]]:
    """Alle installierten Pakete, die das Programm zur Laufzeit braucht, mit Version und Lizenz."""
    try:
        root = md.distribution(DIST_NAME)
    except md.PackageNotFoundError:
        return []
    found: dict[str, dict[str, Any]] = {}

    def visit(name: str, extras: set[str], optional: bool) -> None:
        key = _norm(name)
        try:
            dist = md.distribution(key)
        except md.PackageNotFoundError:
            return  # nicht installiert (zum Beispiel nur auf anderen Systemen nötig)
        known = found.get(key)
        if known is not None and extras <= known["_extras"]:
            return
        entry = known or {"name": dist.metadata["Name"] or name, "version": dist.version,
                          "license": license_of(dist), "optional": optional, "_extras": set()}
        entry["_extras"] |= extras
        entry["optional"] = entry["optional"] and optional
        found[key] = entry
        for req in dist.requires or []:
            child, child_extras, cond = _parse(req)
            if child and (cond is None or cond in extras):
                visit(child, child_extras, optional)

    for req in root.requires or []:
        child, child_extras, cond = _parse(req)
        if child:  # «extra == claude» im Projekt selbst: nur anzeigen, wenn installiert
            visit(child, child_extras, optional=cond is not None)

    out = [{k: v for k, v in e.items() if k != "_extras"} for e in found.values()]
    return sorted(out, key=lambda e: e["name"].casefold())


def frontend_components() -> list[dict[str, Any]]:
    """Pakete, die in der gebauten Oberfläche stecken (`dependencies` in web/package.json)."""
    try:
        deps = json.loads((WEB_DIR / "package.json").read_text(encoding="utf-8")).get("dependencies", {})
    except (OSError, ValueError):
        return []
    out: list[dict[str, Any]] = []
    for name, spec in sorted(deps.items()):
        try:
            meta = json.loads((WEB_DIR / "node_modules" / name / "package.json").read_text(encoding="utf-8"))
            out.append({"name": name, "version": meta.get("version", spec),
                        "license": str(meta.get("license", "unbekannt")), "optional": False})
        except (OSError, ValueError):
            out.append({"name": name, "version": spec, "license": "unbekannt", "optional": False})
    return out


def version() -> str:
    try:
        return md.version(DIST_NAME)
    except md.PackageNotFoundError:
        return "unbekannt"


def about() -> dict[str, Any]:
    return {
        "name": NAME,
        "version": version(),
        "author": AUTHOR,
        "copyright": f"© {YEAR} {AUTHOR}",
        "license": {"id": LICENSE_ID, "name": tr(LICENSE_NAME), "url": LICENSE_URL},
        "notice": tr(NOTICE),
        "repository": REPO_URL,
        "inspiration": [_localized(x) for x in INSPIRATION],
        "external": [_localized(x) for x in external()],
        "components": {"python": python_components(), "frontend": frontend_components()},
        "system": {"python": platform.python_version(), "platform": platform.platform()},
    }
