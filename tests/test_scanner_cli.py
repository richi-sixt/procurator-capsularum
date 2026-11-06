from typer.testing import CliRunner

from procurator.cli import app
from procurator.scanner import natural_key, scan

runner = CliRunner()


def test_natural_sort():
    assert sorted(["img10", "img2", "img1"], key=natural_key) == ["img1", "img2", "img10"]


def test_scan_ignores_system_files_hidden_and_dirs(folder):
    (folder / "a.txt").write_text("x")
    (folder / ".DS_Store").write_text("x")
    (folder / "._a.txt").write_text("x")
    (folder / ".hidden").write_text("x")
    sub = folder / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("x")
    assert [i.name for i in scan(folder)] == ["a.txt"]
    assert [i.name for i in scan(folder, recursive=True)] == ["a.txt", "b.txt"]


def test_cli_preview_then_apply_then_undo(folder, tmp_path, monkeypatch):
    monkeypatch.setenv("PC_JOURNAL", str(tmp_path / "j.db"))
    (folder / "a b.txt").write_text("x")

    r = runner.invoke(app, ["rename", "replace", str(folder), "-f", " ", "-t", "_"])
    assert r.exit_code == 0 and "Nur Vorschau" in r.output
    assert (folder / "a b.txt").exists()

    r = runner.invoke(app, ["rename", "replace", str(folder), "-f", " ", "-t", "_", "--apply"])
    assert r.exit_code == 0
    assert (folder / "a_b.txt").exists()

    r = runner.invoke(app, ["undo"])
    assert r.exit_code == 0
    assert (folder / "a b.txt").exists()


def test_cli_undo_of_a_conversion_asks_first_and_says_deleted(folder, tmp_path, monkeypatch):
    import zipfile

    monkeypatch.setenv("PC_JOURNAL", str(tmp_path / "j.db"))
    with zipfile.ZipFile(folder / "a.cbr", "w") as zf:  # ein ZIP im CBR-Gewand
        zf.writestr("1.jpg", b"x")
    out = tmp_path / "ziel"
    r = runner.invoke(app, ["convert", "cbr2cbz", str(folder), "--to", str(out), "--apply"])
    assert r.exit_code == 0 and (out / "a.cbz").exists()

    r = runner.invoke(app, ["undo"], input="n\n")  # Nachfrage abgelehnt: nichts passiert
    assert r.exit_code != 0 and (out / "a.cbz").exists()

    r = runner.invoke(app, ["undo", "--yes"])
    assert r.exit_code == 0 and "erzeugte Dateien gelöscht" in r.output
    assert not (out / "a.cbz").exists() and (folder / "a.cbr").exists()


def test_cli_duplicates_move_preview_apply_and_undo(folder, tmp_path, monkeypatch):
    import os

    monkeypatch.setenv("PC_JOURNAL", str(tmp_path / "j.db"))
    for name, mt in (("a.bin", 1), ("b.bin", 2)):
        p = folder / name
        p.write_bytes(b"gleich" * 100)
        os.utime(p, ns=(mt * 10**9, mt * 10**9))
    env = {"COLUMNS": "300"}

    r = runner.invoke(app, ["duplicates", str(folder), "--move"], env=env)
    assert r.exit_code == 0 and "1 Kopie in 1 Gruppe belegen" in r.output
    assert "Nur Vorschau" in r.output and (folder / "b.bin").exists()  # nichts verändert

    r = runner.invoke(app, ["duplicates", str(folder), "--move", "--apply"], env=env)
    assert r.exit_code == 0 and "1 verschoben" in r.output
    assert (folder / "a.bin").exists() and (folder / "_Dubletten" / "b.bin").exists()

    r = runner.invoke(app, ["undo"], env=env)
    assert r.exit_code == 0 and (folder / "b.bin").exists() and not (folder / "_Dubletten").exists()


def test_cli_duplicates_keep_must_be_valid(folder):
    r = runner.invoke(app, ["duplicates", str(folder), "--move", "--keep", "zufall"])
    assert r.exit_code != 0
