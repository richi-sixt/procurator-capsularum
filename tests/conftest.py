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
