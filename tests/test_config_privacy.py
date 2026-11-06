import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from procurator import config as cfgmod
from procurator.cli import app as cli_app
from procurator.model import FileItem
from procurator.privacy import SensitiveRules, rules_from_config, split_for_ai, split_for_config
from procurator.scanner import scan
from procurator.server import create_app

# ---------- Config ----------


def test_defaults_when_file_missing(tmp_path):
    cfg, warning = cfgmod.load(tmp_path / "gibt-es-nicht.toml")
    assert warning is None
    assert cfg.ai.provider == "ollama" and cfg.ai.privacy_level == 0
    assert "steuer" in cfg.privacy.sensitive_keywords


def test_roundtrip_and_atomic_file(tmp_path):
    p = tmp_path / "c.toml"
    cfg = cfgmod.parse({"ai": {"privacy_level": 1, "ollama_model": "qwen3:8b"},
                        "privacy": {"sensitive_keywords": ["Steuer", " Pass ", "steuer"]}})
    cfgmod.save(cfg, p)
    loaded, warning = cfgmod.load(p)
    assert warning is None
    assert loaded.ai.privacy_level == 1 and loaded.ai.ollama_model == "qwen3:8b"
    assert loaded.privacy.sensitive_keywords == ["steuer", "pass"]  # normalisiert, ohne Doppelte
    assert [f.name for f in tmp_path.iterdir()] == ["c.toml"]  # keine temporären Reste


@pytest.mark.parametrize("bad", [
    {"ai": {"provider": "openai"}},
    {"ai": {"privacy_level": 3}},
    {"ai": {"privacy_level": True}},
    {"ai": {"ollama_model": "  "}},
    {"ai": {"ollama_host": "http://192.168.1.5:11434"}},
    {"ai": {"ollama_host": "ftp://localhost"}},
    {"privacy": {"sensitive_keywords": "steuer"}},
    {"privacy": {"sensitive_keywords": ["x" * 80]}},
])
def test_invalid_values_rejected(bad):
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.parse(bad)


def test_api_key_cannot_be_pasted_into_env_name_field():
    for secret in ("sk-ant-api03-abcdef", "meinGeheimerKey123", "x y"):
        with pytest.raises(cfgmod.ConfigError, match="Name der Umgebungsvariable"):
            cfgmod.parse({"ai": {"api_key_env": secret}})
    assert cfgmod.parse({"ai": {"api_key_env": "MY_KEY"}}).ai.api_key_env == "MY_KEY"


def test_corrupt_file_falls_back_with_warning(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("das ist [kein toml")
    cfg, warning = cfgmod.load(p)
    assert cfg.ai.provider == "ollama" and "nicht lesbar" in warning
    p.write_text('[ai]\nprovider = "evil"\n')
    assert "Anbieter" in cfgmod.load(p)[1]


def test_saved_file_never_contains_a_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-GEHEIMER-WERT")
    p = tmp_path / "c.toml"
    cfgmod.save(cfgmod.Config(), p)
    assert "GEHEIMER" not in p.read_text()
    assert cfgmod.api_key_present(cfgmod.Config()) is True


# ---------- Erkennung sensibler Dateien ----------


def item(folder: Path, rel: str, root: Path | None = None) -> FileItem:
    return FileItem(folder / rel, root if root is not None else folder)


RULES = SensitiveRules(("pass", "steuer", "konto", "visa"), (".pem", ".key"))


@pytest.mark.parametrize("name,hit", [
    ("Steuererklärung 2024.pdf", "steuer"),
    ("STEUER.pdf", "steuer"),
    ("meine_Passwoerter.txt", "pass"),
    ("Pass-Kopie.jpg", "pass"),
    ("Kontoauszug_März.pdf", "konto"),
    ("Visa application.pdf", "visa"),
    ("server.pem", ".pem"),
    ("id.KEY", ".key"),
])
def test_sensitive_matches(folder, name, hit):
    assert RULES.match(item(folder, name)) == hit


@pytest.mark.parametrize("name", ["Compass.txt", "bypass.log", "Urlaub.jpg", "mitpass.txt",
                                  "Katalog.pdf", "Rechnung.pdf"])
def test_not_sensitive(folder, name):
    assert RULES.match(item(folder, name)) == ""


def test_folder_names_below_root_count_but_not_above(tmp_path):
    root = tmp_path / "Steuern 2024"  # der gewählte Ordner selbst
    (root / "Belege").mkdir(parents=True)
    f1 = root / "Belege" / "scan1.pdf"
    f1.write_text("x")
    assert RULES.match(FileItem(f1, root)) == "steuer"

    other = tmp_path / "Fotos" / "Konto-Ordner"  # Unterordner zählt
    other.mkdir(parents=True)
    f2 = other / "a.jpg"
    f2.write_text("x")
    assert RULES.match(FileItem(f2, tmp_path / "Fotos")) == "konto"

    above = tmp_path / "Steuern" / "Urlaub"  # Ordner oberhalb des gewählten zählt nicht
    above.mkdir(parents=True)
    f3 = above / "a.jpg"
    f3.write_text("x")
    assert RULES.match(FileItem(f3, above)) == ""


def test_empty_rules_match_nothing(folder):
    assert SensitiveRules().match(item(folder, "Steuer.pdf")) == ""


def test_default_rules_flag_typical_private_files(folder):
    rules = rules_from_config(cfgmod.Config())
    for name in ("Reisepass.jpg", "Versicherungspolice 2023.pdf", "Lohnabrechnung.pdf",
                 "Krankenkasse.pdf", "private.key"):
        assert rules.match(item(folder, name)), name


def test_split_for_ai_never_lets_sensitive_files_through(folder, make):
    make("Steuer 2024.pdf", "Urlaub.jpg", "Reisepass.png", "notiz.txt", "id.pem")
    rules = rules_from_config(cfgmod.Config())
    for cloud in (False, True):  # Standard: auch beim lokalen Modell zurückgehalten
        allowed, withheld = split_for_ai(scan(folder), rules, cloud=cloud)
        assert sorted(i.name for i in allowed) == ["Urlaub.jpg", "notiz.txt"]
        assert sorted(i.name for i in withheld) == ["Reisepass.png", "Steuer 2024.pdf", "id.pem"]
        sent = json.dumps([i.name for i in allowed])  # so sähe eine Anfrage an ein Modell aus
        for secret in ("Steuer", "Reisepass", "id.pem"):
            assert secret not in sent


def test_local_model_may_get_sensitive_files_only_when_enabled(folder, make):
    make("Steuer 2024.pdf", "Urlaub.jpg")
    rules = rules_from_config(cfgmod.Config())
    allowed, withheld = split_for_ai(scan(folder), rules, cloud=False, allow_sensitive_local=True)
    assert len(allowed) == 2 and withheld == {}


def test_cloud_never_gets_sensitive_files_even_if_local_option_is_on(folder, make):
    """Die Option gilt nur für ein lokales Modell, bei Cloud bleibt die Sperre."""
    make("Steuer 2024.pdf", "Urlaub.jpg")
    cfg = cfgmod.parse({"ai": {"provider": "claude"}, "privacy": {"allow_sensitive_local": True}})
    allowed, withheld = split_for_config(scan(folder), cfg)
    assert [i.name for i in allowed] == ["Urlaub.jpg"]
    assert [i.name for i in withheld] == ["Steuer 2024.pdf"]
    local = cfgmod.parse({"privacy": {"allow_sensitive_local": True}})
    assert len(split_for_config(scan(folder), local)[0]) == 2


def test_confirmation_is_required_only_for_cloud():
    assert cfgmod.Config().requires_confirmation is False
    assert cfgmod.parse({"ai": {"provider": "claude"}}).requires_confirmation is True


def test_allow_sensitive_local_must_be_bool():
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.parse({"privacy": {"allow_sensitive_local": "ja"}})


# ---------- Server ----------


@pytest.fixture
def client(journal):
    return TestClient(create_app(journal))


def test_plan_and_scan_flag_sensitive_files(client, make, folder):
    make("Steuer 2024.pdf", "Urlaub.jpg")
    scan_res = client.post("/api/scan", json={"paths": [str(folder)]}).json()
    assert {f["srcName"]: f["sensitive"] for f in scan_res} == {"Steuer 2024.pdf": "steuer",
                                                                "Urlaub.jpg": ""}
    body = {"paths": [str(folder)], "operation": "append", "params": {"text": "_x"}}
    plan = client.post("/api/plan", json=body).json()
    assert plan["sensitiveCount"] == 1
    by = {c["srcName"]: c for c in plan["changes"]}
    assert by["Steuer 2024.pdf"]["sensitive"] == "steuer"
    assert by["Steuer 2024.pdf"]["status"] == "ok"  # nur Markierung, lokal weiter möglich


def test_config_get_put_roundtrip(client):
    got = client.get("/api/config").json()
    assert got["config"]["ai"]["provider"] == "ollama" and got["isCloud"] is False
    assert got["requiresConfirmation"] is False and got["config"]["privacy"]["allow_sensitive_local"] is False
    new = {"ai": {"privacy_level": 2, "provider": "claude"}, "privacy": {"sensitive_keywords": ["abc"]}}
    put = client.put("/api/config", json=new)
    assert put.status_code == 200 and put.json()["isCloud"] is True
    assert put.json()["requiresConfirmation"] is True
    again = client.get("/api/config").json()
    assert again["config"]["ai"]["privacy_level"] == 2
    assert again["config"]["privacy"]["sensitive_keywords"] == ["abc"]


def test_config_put_validates(client):
    r = client.put("/api/config", json={"ai": {"api_key_env": "sk-ant-api03-xyz"}})
    assert r.status_code == 422 and "Umgebungsvariable" in r.json()["detail"]
    assert client.put("/api/config", json={"ai": {"privacy_level": 9}}).status_code == 422
    assert client.get("/api/config").json()["config"]["ai"]["privacy_level"] == 0  # nichts gespeichert


def test_config_response_never_contains_the_key(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-GEHEIMER-WERT")
    r = client.get("/api/config")
    assert r.json()["apiKeyPresent"] is True
    assert "GEHEIMER" not in r.text
    assert "GEHEIMER" not in client.post("/api/config/test", json={"ai": {"provider": "claude"}}).text


def test_connection_test_ollama(client, monkeypatch):
    import httpx

    def fake_get(url, timeout):
        assert url == "http://localhost:11434/api/tags"
        return httpx.Response(200, json={"models": [{"name": "gemma4:e2b"}]},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr("procurator.ai.probe.httpx.get", fake_get)
    r = client.post("/api/config/test", json={}).json()
    assert r["ok"] and r["models"] == ["gemma4:e2b"] and "geladen" in r["message"]

    r = client.post("/api/config/test", json={"ai": {"ollama_model": "fehlt:1b"}}).json()
    assert not r["ok"] and "ollama pull fehlt:1b" in r["message"]


def test_connection_test_when_ollama_is_down(client, monkeypatch):
    import httpx

    def boom(url, timeout):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr("procurator.ai.probe.httpx.get", boom)
    r = client.post("/api/config/test", json={}).json()
    assert not r["ok"] and "ollama serve" in r["message"]


def test_connection_test_claude_makes_no_network_call(client, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("keine Anfrage an die Cloud erlaubt")

    monkeypatch.setattr("procurator.ai.probe.httpx.get", forbidden)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/api/config/test", json={"ai": {"provider": "claude"}}).json()
    assert not r["ok"] and "nicht gesetzt" in r["message"]


def test_connection_test_rejects_remote_host(client):
    r = client.post("/api/config/test", json={"ai": {"ollama_host": "http://evil.example"}})
    assert r.status_code == 422


# ---------- CLI ----------


def test_cli_sensitive_lists_hits(folder, make):
    from typer.testing import CliRunner

    make("Steuer.pdf", "Urlaub.jpg")
    out = CliRunner().invoke(cli_app, ["sensitive", str(folder)], env={"COLUMNS": "400"}).output
    assert "Steuer.pdf" in out and "Urlaub.jpg" not in out and "1 von 2" in out


def test_cli_config_shows_defaults():
    from typer.testing import CliRunner

    out = CliRunner().invoke(cli_app, ["config"]).output
    assert "ollama" in out and "Datenschutzstufe 0" in out
