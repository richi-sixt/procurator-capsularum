import importlib.metadata as md
import json
import re
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from procurator import about as aboutmod
from procurator.cli import app as cli_app
from procurator.server import create_app

ROOT = Path(__file__).resolve().parents[1]


# ---------- Übereinstimmung der Angaben in allen Dateien ----------


def test_author_license_and_url_agree_across_all_files():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    package = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")

    assert pyproject["license"] == aboutmod.LICENSE_ID
    assert package["license"] == aboutmod.LICENSE_ID
    assert f"license: {aboutmod.LICENSE_ID}" in cff

    assert pyproject["authors"][0]["name"] == aboutmod.AUTHOR
    assert package["author"] == aboutmod.AUTHOR
    given = re.search(r"given-names: (.+)", cff).group(1).strip()
    family = re.search(r"family-names: (.+)", cff).group(1).strip()
    assert f"{given} {family}" == aboutmod.AUTHOR

    assert aboutmod.REPO_URL in cff
    assert aboutmod.REPO_URL in (ROOT / "README.md").read_text(encoding="utf-8")


def test_license_file_is_the_agpl_text():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE")
    assert "Version 3, 19 November 2007" in text and "END OF TERMS AND CONDITIONS" in text


def test_readme_and_ui_footer_name_the_same_copyright():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    footer = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert f"Copyright © {aboutmod.YEAR} {aboutmod.AUTHOR}" in readme
    assert f"© {aboutmod.YEAR} {aboutmod.AUTHOR}" in footer


# ---------- Angaben ----------


def test_about_basics():
    a = aboutmod.about()
    assert a["name"] == "Procurator Capsularum"
    assert a["version"] == md.version("procurator-capsularum")
    assert a["copyright"] == f"© {aboutmod.YEAR} {aboutmod.AUTHOR}"
    assert a["license"]["id"] == "AGPL-3.0-or-later" and a["license"]["url"].startswith("https://")
    assert "ohne jede Gewährleistung" in a["notice"] and "Quellcode" in a["notice"]
    assert {i["name"] for i in a["inspiration"]} == {"NameChanger", "file-whisperer"}
    assert {e["name"] for e in a["external"]} == {"unar", "Ollama"}
    assert a["system"]["python"] and a["system"]["platform"]


def test_about_has_no_private_data():
    text = json.dumps(aboutmod.about(), ensure_ascii=False)
    for private in ("/Users/", "@proton", "noreply", "ANTHROPIC_API_KEY", "sk-ant"):
        assert private not in text


# ---------- Bausteine ----------


def test_python_components_are_runtime_packages_only():
    comps = {c["name"].lower(): c for c in aboutmod.python_components()}
    for needed in ("fastapi", "pillow", "typer", "platformdirs", "tomli_w", "httpx"):
        assert needed in comps, needed
    assert "httptools" in comps  # kommt über uvicorn[standard]
    for dev_only in ("pytest", "ruff", "procurator-capsularum"):
        assert dev_only not in comps
    assert all(c["license"] and c["license"] != "unbekannt" for c in comps.values())
    names = [c["name"].casefold() for c in aboutmod.python_components()]
    assert names == sorted(names)


def test_optional_claude_package_is_marked_optional():
    comps = {c["name"].lower(): c for c in aboutmod.python_components()}
    assert comps["anthropic"]["optional"] is True
    assert comps["fastapi"]["optional"] is False


@pytest.mark.parametrize("req,expected", [
    ("fastapi>=0.162.0", ("fastapi", set(), None)),
    ("uvicorn[standard]>=0.54.0", ("uvicorn", {"standard"}, None)),
    ("anthropic>=2.6.0; extra == 'claude'", ("anthropic", set(), "claude")),
    ("Typing_Extensions >=4; python_version < '3.13'", ("typing-extensions", set(), None)),
    ("httptools>=0.6.3; extra == \"standard\"", ("httptools", set(), "standard")),
    ("", ("", set(), None)),
])
def test_parse_requirement(req, expected):
    assert aboutmod._parse(req) == expected


class FakeMeta(dict):
    def get_all(self, key):
        return self.get("_all", {}).get(key)


def fake_dist(**meta):
    classifiers = meta.pop("classifiers", None)
    m = FakeMeta(meta)
    if classifiers:
        m["_all"] = {"Classifier": classifiers}
    return SimpleNamespace(metadata=m)


def test_license_of_prefers_expression_then_short_text_then_classifiers():
    assert aboutmod.license_of(fake_dist(**{"License-Expression": "MIT", "License": "x"})) == "MIT"
    assert aboutmod.license_of(fake_dist(License="BSD-3-Clause")) == "BSD-3-Clause"
    long_text = "Permission is hereby granted\nfree of charge " * 20
    got = aboutmod.license_of(fake_dist(License=long_text, classifiers=[
        "License :: OSI Approved :: MIT License", "License :: Other/Proprietary License"]))
    assert got == "MIT License; Other/Proprietary License"  # alle Einträge, ohne die Kategorie «OSI Approved»
    assert aboutmod.license_of(fake_dist(License=long_text)) == "Permission is hereby granted"
    assert aboutmod.license_of(fake_dist()) == "unbekannt"


def test_python_components_when_package_is_not_installed(monkeypatch):
    def missing(name):
        raise md.PackageNotFoundError(name)

    monkeypatch.setattr(aboutmod.md, "distribution", missing)
    assert aboutmod.python_components() == []


def test_version_is_unknown_when_not_installed(monkeypatch):
    def missing(name):
        raise md.PackageNotFoundError(name)

    monkeypatch.setattr(aboutmod.md, "version", missing)
    assert aboutmod.version() == "unbekannt"


def test_frontend_components_from_package_json(tmp_path, monkeypatch):
    web = tmp_path / "web"
    (web / "node_modules" / "react").mkdir(parents=True)
    (web / "package.json").write_text(json.dumps({"dependencies": {"react": "^19", "fehlt": "^1"}}))
    (web / "node_modules" / "react" / "package.json").write_text(
        json.dumps({"version": "19.3.1", "license": "MIT"}))
    monkeypatch.setattr(aboutmod, "WEB_DIR", web)
    assert aboutmod.frontend_components() == [
        {"name": "fehlt", "version": "^1", "license": "unbekannt", "optional": False},
        {"name": "react", "version": "19.3.1", "license": "MIT", "optional": False},
    ]


def test_frontend_components_without_package_json(tmp_path, monkeypatch):
    monkeypatch.setattr(aboutmod, "WEB_DIR", tmp_path / "gibt-es-nicht")
    assert aboutmod.frontend_components() == []


# ---------- Server und Kommandozeile ----------


def test_server_about(journal):
    client = TestClient(create_app(journal))
    data = client.get("/api/about").json()
    assert data["version"] == md.version("procurator-capsularum")
    assert data["license"]["id"] == "AGPL-3.0-or-later"
    assert any(c["name"].lower() == "fastapi" for c in data["components"]["python"])


def test_cli_version_and_about():
    runner = CliRunner()
    env = {"COLUMNS": "200"}
    r = runner.invoke(cli_app, ["--version"], env=env)
    assert r.exit_code == 0 and r.output.strip() == f"Procurator Capsularum {md.version('procurator-capsularum')}"

    r = runner.invoke(cli_app, ["about"], env=env)
    assert r.exit_code == 0
    assert "© 2026 Rüchan Sixt" in r.output and "AGPL-3.0-or-later" in r.output
    assert "ohne jede Gewährleistung" in r.output and "mit --licenses auflisten" in r.output

    r = runner.invoke(cli_app, ["about", "--licenses"], env=env)
    assert r.exit_code == 0 and "fastapi" in r.output.lower() and "MIT" in r.output
    assert "react" in r.output
