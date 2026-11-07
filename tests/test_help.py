"""Hilfe in der App: Seiten aus docs/ als HTML, Verweise, Bilder, Sicherheit."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from procurator import help as helpmod
from procurator.about import REPO_URL
from procurator.help import image_path, pages, render, slug
from procurator.server import create_app

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


@pytest.fixture
def client(journal) -> TestClient:
    return TestClient(create_app(journal))


# ---------- Umwandlung ----------


def test_headings_get_github_style_anchors_and_a_toc():
    html, title, toc = render("# Titel\n\n## Datenschutz\n\n### Sensible Dateien\n\n## KI-Vorschläge\n")
    assert title == "Titel"
    assert 'id="datenschutz"' in html and 'id="ki-vorschläge"' in html
    assert [(t["level"], t["id"]) for t in toc] == [
        (2, "datenschutz"), (3, "sensible-dateien"), (2, "ki-vorschläge")]


def test_duplicate_headings_get_unique_anchors():
    html, _, toc = render("# T\n\n## Beispiel\n\n## Beispiel\n")
    assert [t["id"] for t in toc] == ["beispiel", "beispiel-2"]


@pytest.mark.parametrize("text,expected", [
    ("Datenschutz", "datenschutz"), ("KI-Vorschläge", "ki-vorschläge"),
    ("Wenn etwas nicht klappt", "wenn-etwas-nicht-klappt"),
    ("Name aus Vorlage", "name-aus-vorlage"), ("`code` & mehr", "code--mehr"),
])
def test_slug(text, expected):
    assert slug(text) == expected


def test_tables_code_and_lists_render():
    html, _, _ = render("| a | b |\n|---|---|\n| 1 | 2 |\n\n```bash\nuv run pc\n```\n\n- eins\n- zwei\n")
    assert "<table>" in html and "<th>a</th>" in html
    assert "<pre><code" in html and "uv run pc" in html and "<li>eins</li>" in html


def test_raw_html_is_escaped_never_executed():
    html, _, _ = render('# T\n\n<script>alert(1)</script> und <img src=x onerror=alert(1)>\n')
    assert "<script" not in html and "<img src=x" not in html
    assert "&lt;script&gt;" in html


def test_links_are_rewritten():
    html, _, _ = render(
        "[a](anleitung.md#datenschutz) [b](#oben) [c](https://example.org) "
        "[d](../README.md) [e](javascript:alert(1)) [f](Evil.md)")
    assert 'data-help="anleitung"' in html and 'data-anchor="datenschutz"' in html
    assert 'href="#oben"' in html
    assert 'href="https://example.org" target="_blank" rel="noopener noreferrer"' in html
    assert f'href="{REPO_URL}/blob/main/README.md"' in html
    assert 'href="javascript:' not in html  # wird gar nicht erst zum Verweis


def test_images_point_to_the_help_route_and_only_for_simple_png_names():
    html, _, _ = render("![ok](img/verlauf.png) ![x](img/../../etc/passwd) ![y](https://x.org/a.png)")
    assert 'src="/api/help/img/verlauf.png"' in html
    assert "etc/passwd" not in html and "x.org" not in html


# ---------- Seiten und Bilder ----------


def test_real_pages_are_listed_in_menu_order_without_the_index():
    found = pages()
    assert list(found) == ["anleitung", "entwicklung"]
    assert found["anleitung"].title == "Anleitung" and "readme" not in found


def test_docs_dir_finds_the_repository_docs():
    assert helpmod.docs_dir().resolve() == DOCS.resolve()


def test_missing_docs_folder_gives_no_pages(tmp_path):
    assert pages(tmp_path / "gibt-es-nicht") == {}


@pytest.mark.parametrize("name,ok", [
    ("verlauf.png", True), ("../anleitung.md", False), ("..%2Fx.png", False),
    ("a/b.png", False), ("verlauf.jpg", False), ("gibt-es-nicht.png", False), (".png", False),
])
def test_image_path_is_strict(name, ok):
    assert (image_path(name) is not None) is ok


# ---------- Server ----------


def test_server_lists_pages_and_serves_one(client):
    listing = client.get("/api/help").json()
    assert [p["name"] for p in listing] == ["anleitung", "entwicklung"]
    page = client.get("/api/help/anleitung").json()
    assert page["title"] == "Anleitung" and "<h2" in page["html"] and page["toc"]
    assert 'src="/api/help/img/vorschau-name-vorlage.png"' in page["html"]


def test_server_unknown_page_and_bad_names(client):
    assert client.get("/api/help/gibt-es-nicht").status_code == 404
    assert client.get("/api/help/README").status_code == 404  # nur die Menüseiten
    assert client.get("/api/help/..%2F..%2Fpyproject").status_code == 404


def test_server_images(client):
    r = client.get("/api/help/img/verlauf.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    for bad in ("nope.png", "verlauf.jpg", "..%2Fpyproject.toml", "%2e%2e%2fpyproject.png"):
        assert client.get(f"/api/help/img/{bad}").status_code == 404


# ---------- Die echten Seiten sind in sich stimmig ----------


def anchors(html: str) -> set[str]:
    return set(re.findall(r'id="([^"]+)"', html))


def test_every_internal_link_in_the_help_resolves():
    found = pages()
    for page in found.values():
        for target, anchor in re.findall(r'data-help="([^"]+)"(?: data-anchor="([^"]*)")?', page.html):
            assert target in found, f"{page.name}: Seite {target} gibt es nicht"
            assert not anchor or anchor in anchors(found[target].html), \
                f"{page.name}: Anker {target}#{anchor} gibt es nicht"
        for anchor in re.findall(r'href="#([^"]+)"', page.html):
            assert anchor in anchors(page.html), f"{page.name}: Anker #{anchor} gibt es nicht"


def test_every_image_in_the_help_exists():
    for page in pages().values():
        for name in re.findall(r'src="/api/help/img/([^"]+)"', page.html):
            assert image_path(name) is not None, f"{page.name}: Bild {name} fehlt"


def test_pages_use_no_raw_html():
    for path in DOCS.glob("*.md"):
        text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
        text = re.sub(r"`[^`]*`", "", text)
        assert not re.search(r"</?(script|iframe|style|details|summary)\b", text), path.name
