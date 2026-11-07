"""Hilfe in der App: die Seiten aus `docs/` als HTML, ohne Internet.

Die Markdown-Dateien sind die einzige Quelle. Sie werden hier gelesen, in HTML umgewandelt und über
den lokalen Server ausgeliefert. Rohes HTML in den Dateien wird nicht ausgegeben (nur Text), Verweise
auf andere Seiten und Bilder werden auf die Hilfe umgeschrieben.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from markdown_it import MarkdownIt
from markdown_it.token import Token

from .about import REPO_URL

# Reihenfolge im Menü. Seiten, die hier fehlen, erscheinen danach alphabetisch.
ORDER = ("anleitung", "entwicklung")
INDEX_PAGE = "README"  # Übersicht für GitHub, in der App nicht nötig
NAME = re.compile(r"^[a-z0-9-]+$")
IMAGE = re.compile(r"^[A-Za-z0-9._-]+\.png$")


def docs_dir() -> Path:
    """Im installierten Paket liegt `docs` neben dem Code, in einem Klon im Hauptordner."""
    here = Path(__file__).resolve().parent
    for candidate in (here / "docs", here.parents[1] / "docs"):
        if (candidate / "anleitung.md").is_file():
            return candidate
    return here.parents[1] / "docs"


@dataclass
class Page:
    name: str
    title: str
    html: str
    toc: list[dict[str, object]]


def slug(text: str) -> str:
    """Anker wie auf GitHub: klein, Leerzeichen zu «-», Satzzeichen weg, Umlaute bleiben."""
    text = re.sub(r"[^\w\s-]", "", text.lower(), flags=re.UNICODE)
    return re.sub(r"\s", "-", text.strip())


def _md() -> MarkdownIt:
    return MarkdownIt("commonmark", {"html": False}).enable("table")


def _rewrite_link(href: str) -> dict[str, str]:
    """Attribute für einen Verweis. Andere Hilfeseiten und Anker bleiben in der App."""
    if href.startswith(("http://", "https://")):
        return {"href": href, "target": "_blank", "rel": "noopener noreferrer"}
    href = unquote(href)  # markdown-it kodiert Umlaute in Ankern, die Überschriften-Ids nicht
    if href.startswith("#"):
        return {"href": href}
    path, _, anchor = href.partition("#")
    if path.startswith("../"):  # Datei ausserhalb von docs, zum Beispiel das README
        return {"href": f"{REPO_URL}/blob/main/{path[3:]}", "target": "_blank",
                "rel": "noopener noreferrer"}
    if path.endswith(".md") and NAME.match(path[:-3].lower()):
        attrs = {"href": "#", "data-help": path[:-3].lower()}
        if anchor:
            attrs["data-anchor"] = anchor
        return attrs
    return {"href": "#"}  # unbekanntes Ziel: nichts Gefährliches ausliefern


def render(markdown: str) -> tuple[str, str, list[dict[str, object]]]:
    """HTML, Titel (erste Überschrift) und Inhaltsverzeichnis (Überschriften der Ebenen 2 und 3)."""
    md = _md()
    tokens = md.parse(markdown)
    title, toc, used = "", [], set()
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            text = tokens[i + 1].content
            anchor = base = slug(text) or "abschnitt"
            n = 2
            while anchor in used:
                anchor, n = f"{base}-{n}", n + 1
            used.add(anchor)
            tok.attrSet("id", anchor)
            level = int(tok.tag[1])
            if level == 1 and not title:
                title = text
            elif level in (2, 3):
                toc.append({"level": level, "id": anchor, "text": text})
        elif tok.type == "inline" and tok.children:
            _rewrite_inline(tok.children)
    return md.renderer.render(tokens, md.options, {}), title, toc


def _rewrite_inline(children: list[Token]) -> None:
    for child in children:
        if child.type == "link_open":
            href = str(child.attrGet("href") or "")
            child.attrs = dict(_rewrite_link(href))
        elif child.type == "image":
            src = str(child.attrGet("src") or "")
            name = src.removeprefix("img/")
            child.attrSet("src", f"/api/help/img/{name}" if IMAGE.match(name) else "")
            child.attrSet("loading", "lazy")


def pages(root: Path | None = None) -> dict[str, Page]:
    """Alle Hilfeseiten, in der Reihenfolge des Menüs."""
    base = root or docs_dir()
    found: dict[str, Page] = {}
    if not base.is_dir():
        return found
    for path in sorted(base.glob("*.md")):
        name = path.stem.lower()
        if path.stem == INDEX_PAGE or not NAME.match(name):
            continue
        html, title, toc = render(path.read_text(encoding="utf-8"))
        found[name] = Page(name, title or path.stem, html, toc)
    ranked = sorted(found, key=lambda n: (ORDER.index(n) if n in ORDER else len(ORDER), n))
    return {n: found[n] for n in ranked}


def image_path(name: str, root: Path | None = None) -> Path | None:
    """Pfad eines Bildes aus `docs/img`, nur einfache PNG-Namen (kein `..`, keine Unterordner)."""
    if not IMAGE.match(name):
        return None
    path = (root or docs_dir()) / "img" / name
    return path if path.is_file() else None
