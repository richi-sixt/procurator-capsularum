"""Server-Meldungen auf Englisch: Vollständigkeit des Katalogs und Verhalten von `tr`."""

import ast
import string
from pathlib import Path

import pytest

from procurator import i18n
from procurator.locale_en import EN

SRC = Path(__file__).resolve().parents[1] / "src" / "procurator"


def fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def used_keys() -> set[str]:
    keys: set[str] = set()
    for path in SRC.rglob("*.py"):
        if path.name == "locale_en.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    keys.add(first.value)
                elif isinstance(first, ast.IfExp):  # tr("a" if x else "b")
                    keys |= {c.value for c in (first.body, first.orelse)
                             if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    return keys


def test_every_translated_call_has_an_english_text():
    missing = sorted(k for k in used_keys() if k not in EN)
    assert not missing, f"Englisch fehlt für: {missing}"


def test_placeholders_match_between_german_and_english():
    for de, en in EN.items():
        assert fields(de) == fields(en), f"Platzhalter weichen ab: {de!r}"


def test_registry_texts_are_translated():
    from procurator.ops.registry import SPECS

    neutral = {"JPG", "PNG", "WebP", "Wildcard", "Name", "Text", "Position", "Format (strftime)",
               "Name (optional)", "CBR → CBZ"}
    texts: set[str] = set()
    for s in SPECS:
        texts |= {s.label, s.group, s.description}
        for f in s.fields:
            texts |= {f.label, f.help} | {label for _, label in f.options}
    missing = sorted(t for t in texts if t and t not in EN and t not in neutral)
    assert not missing, f"Englisch fehlt in der Aktionsliste: {missing}"


def test_catalog_has_no_unused_entries():
    source = "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.py") if p.name != "locale_en.py")
    stale = [k for k in EN if k not in used_keys() and k.split("{")[0][:25] not in source]
    assert not stale, f"Nicht mehr verwendet: {stale}"


@pytest.fixture(autouse=True)
def _reset_language():
    token = i18n.set_language(None)
    yield
    i18n._lang.reset(token)


def test_tr_defaults_to_german_and_formats():
    assert i18n.tr("Dublette von {name}", name="a.jpg") == "Dublette von a.jpg"


def test_tr_gives_english_and_falls_back_to_german():
    i18n.set_language("en")
    assert i18n.tr("Dublette von {name}", name="a.jpg") == "Duplicate of a.jpg"
    assert i18n.tr("Dieser Text ist unbekannt {x}", x=1) == "Dieser Text ist unbekannt 1"


def test_normalize_handles_accept_language_headers():
    assert i18n.normalize("en-US,en;q=0.9,de;q=0.8") == "en"
    assert i18n.normalize("de-CH") == "de"
    assert i18n.normalize("fr") == "de" and i18n.normalize(None) == "de"


def test_plan_reasons_follow_the_request_language(folder):
    from fastapi.testclient import TestClient

    from procurator.journal import Journal
    from procurator.server import create_app

    (folder / "a.txt").write_text("x")
    client = TestClient(create_app(Journal(folder.parent / "j.db")))
    body = {"paths": [str(folder)], "operation": "replace", "params": {"find": "zzz", "replace": "y"},
            "show": True}
    de = client.post("/api/plan", json=body).json()["changes"][0]["reason"]
    en = client.post("/api/plan", json=body, headers={"X-Lang": "en"}).json()["changes"][0]["reason"]
    assert (de, en) == ("Kein Treffer", "No match")
    ops = client.get("/api/operations", headers={"X-Lang": "en"}).json()
    assert ops[0]["label"] == "Replace text" and ops[0]["group"] == "Text"
    err = client.post("/api/plan", json={**body, "params": {}}, headers={"X-Lang": "en"})
    assert err.status_code == 422 and "is missing" in err.json()["detail"]
