"""Aktion «In Ordner nach Vorlage sortieren» (ohne KI)."""

import os
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from typer.testing import CliRunner

from procurator.cli import app as cli_app
from procurator.engine import apply_plan, make_plan
from procurator.model import Status
from procurator.ops import SortByTemplate
from procurator.ops.move import file_type
from procurator.ops.registry import ParamError, build
from procurator.scanner import scan
from procurator.server import create_app

OLD = datetime(2018, 3, 1, 10, 0).timestamp()


def make(folder: Path, rel: str, when: float = OLD) -> Path:
    p = folder / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(rel)
    os.utime(p, (when, when))
    return p


def photo(folder: Path, name: str, original: str) -> Path:
    exif = Image.Exif()
    exif[0x8769] = {36867: original}
    p = folder / name
    Image.new("RGB", (4, 4)).save(p, exif=exif)
    os.utime(p, (OLD, OLD))
    return p


def rel(plan, root: Path) -> dict[str, str]:
    return {c.src.name: (c.dst.relative_to(root).as_posix() if c.dst else c.reason)
            for c in plan.changes}


def test_type_and_year(folder, items):
    photo(folder, "IMG.jpg", "2024:07:04 12:30:00")
    make(folder, "Bericht.pdf")
    make(folder, "x.unbekannt")
    plan = make_plan(SortByTemplate(), items())
    assert rel(plan, folder) == {
        "IMG.jpg": "Bilder/2024/IMG.jpg",  # Aufnahmedatum, nicht Dateidatum 2018
        "Bericht.pdf": "Dokumente/2018/Bericht.pdf",
        "x.unbekannt": "Sonstiges/2018/x.unbekannt",
    }


def test_year_and_month_as_subfolders_and_other_placeholders(folder, items):
    make(folder, "Anna.PDF")
    plan = make_plan(SortByTemplate("{date:%Y}/{date:%m}/{ext}/{initial}"), items())
    assert rel(plan, folder) == {"Anna.PDF": "2018/03/pdf/A/Anna.PDF"}


def test_folder_placeholder_and_recursive_scan(folder):
    make(folder, "Ferien/a.txt")
    make(folder, "Ferien/b.txt")
    plan = make_plan(SortByTemplate("{folder}-{type}"), scan(folder, recursive=True))
    assert rel(plan, folder) == {"a.txt": "Ferien-Dokumente/a.txt", "b.txt": "Ferien-Dokumente/b.txt"}


def test_files_already_in_place_are_skipped_with_a_reason(folder, items):
    make(folder, "Bilder/2018/a.jpg")
    plan = make_plan(SortByTemplate(), scan(folder, recursive=True))
    [c] = plan.changes
    assert c.status == Status.SKIP and c.reason == "Liegt schon im richtigen Ordner"


def test_base_dir_elsewhere_and_apply_undo(folder, tmp_path, journal):
    make(folder, "a.pdf")
    out = tmp_path / "sortiert"
    plan = make_plan(SortByTemplate("{type}", str(out)), scan(folder))
    result = apply_plan(plan, journal)
    assert (out / "Dokumente" / "a.pdf").exists() and not (folder / "a.pdf").exists()
    journal.undo(result.batch_id)
    assert (folder / "a.pdf").exists() and not out.exists()  # angelegte Ordner werden wieder entfernt


def test_same_names_in_one_target_conflict_and_force_unique_numbers(folder):
    make(folder, "a/x.pdf")
    make(folder, "b/x.pdf")
    items = scan(folder, recursive=True)
    assert {c.status for c in make_plan(SortByTemplate("{type}"), items).changes} == {Status.CONFLICT}
    plan = make_plan(SortByTemplate("{type}"), items, force_unique=True)
    assert all(c.status == Status.OK for c in plan.changes)


def test_existing_target_file_is_never_overwritten(folder, items):
    make(folder, "Dokumente/a.pdf")
    make(folder, "a.pdf")
    plan = make_plan(SortByTemplate("{type}"), items())
    top = next(c for c in plan.changes if c.src == folder / "a.pdf")
    assert top.status == Status.CONFLICT


def test_preview_names_the_date_source(folder, items):
    photo(folder, "IMG.jpg", "2024:07:04 12:30:00")
    [c] = make_plan(SortByTemplate(), items()).changes
    assert "EXIF" in c.reason
    [c] = make_plan(SortByTemplate("{type}"), items()).changes
    assert c.reason == ""


@pytest.mark.parametrize("template,message", [
    ("{size}", "Unbekannter Platzhalter"),
    ("{type", "Geschweifte Klammern"),
    ("", "Vorlage fehlt"),
])
def test_bad_templates_are_explained(template, message):
    with pytest.raises(ValueError, match=message):
        SortByTemplate(template)
    with pytest.raises(ParamError, match=message):
        build("sort_template", {"template": template})


def test_relative_base_dir_is_rejected():
    with pytest.raises(ValueError, match="absoluter Pfad"):
        SortByTemplate("{type}", "relativ/ordner")


@pytest.mark.parametrize("template", ["../{type}", "/etc/{type}", ".versteckt/{type}"])
def test_unsafe_templates_become_error_rows(folder, items, template):
    make(folder, "a.pdf")
    [c] = make_plan(SortByTemplate(template), items()).changes
    assert c.status == Status.ERROR and c.dst is None


def test_token_values_cannot_inject_folders(folder, items):
    make(folder, "a.pdf")
    [c] = make_plan(SortByTemplate("{date:%d/%m/%Y}"), items()).changes
    assert c.dst.parent == folder / "01-03-2018"  # kein Unterordner aus dem Datumsformat


def test_file_types():
    from procurator.model import FileItem
    assert file_type(FileItem(Path("a.HEIC"))) == "Bilder"
    assert file_type(FileItem(Path("a.mkv"))) == "Videos"
    assert file_type(FileItem(Path("a"))) == "Sonstiges"


def test_server_and_cli(folder, journal):
    make(folder, "a.pdf")
    client = TestClient(create_app(journal))
    r = {"paths": [str(folder)], "operation": "sort_template", "params": {"template": "{type}"}}
    plan = client.post("/api/plan", json=r).json()
    assert plan["changes"][0]["dstFolder"] == str(folder / "Dokumente")
    bad = client.post("/api/plan", json={**r, "params": {"template": "{x}"}})
    assert bad.status_code == 422

    runner = CliRunner()
    out = runner.invoke(cli_app, ["sort", "{type}", str(folder)]).output
    assert "Dokumente" in out and (folder / "a.pdf").exists()  # nur Vorschau
    assert runner.invoke(cli_app, ["sort", "{nope}", str(folder)]).exit_code != 0
    runner.invoke(cli_app, ["sort", "{type}/{date:%Y}", str(folder), "--apply"])
    assert (folder / "Dokumente" / "2018" / "a.pdf").exists()
