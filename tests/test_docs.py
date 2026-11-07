"""Die Dokumentation darf nicht hinter dem Programm zurückbleiben und nichts Privates enthalten."""

import re
from pathlib import Path

import pytest
import typer.main

from procurator.cli import app as cli_app
from procurator.ops.registry import SPECS

ROOT = Path(__file__).resolve().parent.parent
DOCS = sorted((ROOT / "docs").glob("*.md"))
GUIDE = (ROOT / "docs" / "anleitung.md").read_text(encoding="utf-8")
CORPUS = "\n".join(p.read_text(encoding="utf-8") for p in [ROOT / "README.md", *DOCS])


def test_docs_exist():
    names = {p.name for p in DOCS}
    assert {"README.md", "anleitung.md", "entwicklung.md"} <= names


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.name)
def test_every_action_is_in_the_guide(spec):
    label = spec.label.split(" (")[0]
    assert label in GUIDE, f"Aktion «{label}» fehlt in docs/anleitung.md"


def commands():
    root = typer.main.get_command(cli_app)
    for name, cmd in root.commands.items():
        subs = getattr(cmd, "commands", None)
        if subs:
            for sub in subs:
                yield f"{name} {sub}", sub
        else:
            yield name, name


@pytest.mark.parametrize("full,word", list(commands()), ids=lambda v: str(v))
def test_every_command_is_documented(full, word):
    assert re.search(rf"\bpc {re.escape(full)}\b", CORPUS) or (
        " " in full and re.search(rf"\b{re.escape(word)}\b", CORPUS)
    ), f"Befehl «pc {full}» fehlt in README oder docs/"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_links_point_to_existing_files(doc):
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", doc.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        assert (doc.parent / target).exists(), f"{doc.name}: Verweis ins Leere: {target}"


@pytest.mark.parametrize("doc", [ROOT / "README.md", *DOCS], ids=lambda p: p.name)
def test_no_private_or_forbidden_content(doc):
    text = doc.read_text(encoding="utf-8")
    assert "ß" not in text
    assert "Vision.md" not in text
    assert "/Users/" not in text
    assert not re.search(r"sk-[A-Za-z0-9]{10,}", text)


def test_images_exist_and_are_used():
    """Jedes Bild in docs/img wird in der Anleitung gezeigt, und jedes gezeigte Bild gibt es."""
    shown = set(re.findall(r"\]\(img/([^)]+)\)", GUIDE))
    present = {p.name for p in (ROOT / "docs" / "img").glob("*.png")}
    assert shown == present


def test_images_are_small_and_png():
    for p in (ROOT / "docs" / "img").glob("*"):
        assert p.suffix == ".png" and p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert p.stat().st_size < 400_000, f"{p.name} ist zu gross für das Repository"
