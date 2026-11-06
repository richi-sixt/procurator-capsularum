import shutil
from pathlib import Path

import pytest

from procurator.journal import Journal
from procurator.scanner import scan


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path_factory, monkeypatch):
    """Tests lesen und schreiben nie die echte Konfiguration oder den echten Index."""
    cfg_dir = tmp_path_factory.mktemp("cfg")
    monkeypatch.setenv("PC_CONFIG", str(cfg_dir / "config.toml"))
    monkeypatch.setenv("PC_INDEX", str(cfg_dir / "index.db"))


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    d = tmp_path / "files"
    d.mkdir()
    return d


@pytest.fixture
def make(folder: Path):
    def _make(*names: str) -> Path:
        for n in names:
            (folder / n).write_text(n)
        return folder

    return _make


@pytest.fixture
def journal(tmp_path: Path) -> Journal:
    return Journal(tmp_path / "journal.db")


@pytest.fixture
def items(folder: Path):
    return lambda **kw: scan(folder, **kw)


@pytest.fixture(autouse=True)
def _pretend_unar_is_installed(monkeypatch):
    """Tests mit einer ZIP-Datei im CBR-Gewand brauchen kein echtes `unar`, nur dass die Prüfung
    «Programm vorhanden» besteht. Ist `unar` wirklich installiert, bleibt alles echt (zum Beispiel
    in CI-Läufen auf Rechnern ohne `unar`)."""
    real = shutil.which
    if real("unar") and real("lsar"):
        return

    def which(cmd, *args, **kwargs):
        if cmd in ("unar", "lsar"):
            return f"/usr/bin/{cmd}"  # nur gemeldet, nie gestartet
        return real(cmd, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", which)
