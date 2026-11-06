"""Aktion «Name aus Vorlage» mit Platzhaltern."""

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
from procurator.ops import NameTemplate
from procurator.ops.registry import ParamError, build
from procurator.server import create_app

WHEN = datetime(2018, 3, 1, 10, 5, 9).timestamp()


def pic(folder: Path, name: str, original: str | None, pad: int = 0) -> Path:
    path = folder / name
    exif = Image.Exif()
    if original:
        exif[0x8769] = {36867: original}
    Image.new("RGB", (8 + pad, 8), "white").save(path, exif=exif)
    os.utime(path, (WHEN, WHEN))
    return path


def names(plan) -> dict[str, str]:
    return {c.src.name: (c.dst.name if c.dst else c.reason) for c in plan.changes}


def test_date_time_and_size_like_namechanger(folder, items):
    a = pic(folder, "IMG_0001.jpg", "2024:07:04 12:30:00")
    plan = make_plan(NameTemplate(), items())
    assert names(plan) == {"IMG_0001.jpg": f"20240704_12-30-00_{a.stat().st_size}.jpg"}


def test_same_second_from_two_devices_stays_apart_by_size(folder, items):
    a = pic(folder, "iphone.jpg", "2024:07:04 12:30:00")
    b = pic(folder, "pixel.jpg", "2024:07:04 12:30:00", pad=40)
    assert a.stat().st_size != b.stat().st_size
    plan = make_plan(NameTemplate(), items())
    assert len({c.dst for c in plan.changes}) == 2
    assert all(c.status == Status.OK for c in plan.changes)


def test_real_duplicates_conflict_and_force_unique_numbers_them(folder, items):
    pic(folder, "a.jpg", "2024:07:04 12:30:00")
    pic(folder, "b.jpg", "2024:07:04 12:30:00")  # gleicher Inhalt, gleiche Grösse
    assert {c.status for c in make_plan(NameTemplate(), items()).changes} == {Status.CONFLICT}
    plan = make_plan(NameTemplate(), items(), force_unique=True)
    assert all(c.status == Status.OK for c in plan.changes)


def test_all_placeholders(folder, items):
    (folder / "x").mkdir()
    p = folder / "x" / "Bericht.txt"
    p.write_text("12345")
    os.utime(p, (WHEN, WHEN))
    op = NameTemplate("{folder}-{name}-{n:3}-{size:6}-{ext}-{date}", start=7)
    plan = make_plan(op, items(recursive=True))
    assert plan.changes[0].dst.name == "x-Bericht-007-000005-txt-2018-03-01.txt"


def test_keep_extension_off_replaces_the_whole_name(folder, items):
    (folder / "a.txt").write_text("1")
    plan = make_plan(NameTemplate("{name}.bak", keep_extension=False), items())
    assert plan.changes[0].dst.name == "a.txt.bak"


def test_sequence_follows_natural_name_order(folder, items):
    for n in ("f10.txt", "f2.txt", "f1.txt"):
        (folder / n).write_text(n)
    plan = make_plan(NameTemplate("{n:2}_{name}"), items())
    assert names(plan) == {"f1.txt": "01_f1.txt", "f2.txt": "02_f2.txt", "f10.txt": "03_f10.txt"}


def test_preview_names_the_date_source(folder, items):
    pic(folder, "IMG.jpg", "2024:07:04 12:30:00")
    (folder / "n.txt").write_text("x")
    reasons = {c.src.name: c.reason for c in make_plan(NameTemplate(), items()).changes}
    assert "EXIF" in reasons["IMG.jpg"] and "der Datei" in reasons["n.txt"]
    plain = make_plan(NameTemplate("{name}_{size}"), items())
    assert all(c.reason == "" for c in plain.changes)


@pytest.mark.parametrize("template,message", [
    ("{wrong}", "Unbekannter Platzhalter"),
    ("{size", "Geschweifte Klammern"),
    ("a}b", "Geschweifte Klammern"),
    ("   ", "Vorlage fehlt"),
])
def test_bad_templates_are_explained(template, message):
    with pytest.raises(ValueError, match=message):
        NameTemplate(template)
    with pytest.raises(ParamError, match=message):
        build("template", {"template": template})


def test_slash_in_result_is_an_error_row_not_a_folder(folder, items):
    (folder / "a.txt").write_text("1")
    plan = make_plan(NameTemplate("{date:%d/%m/%Y}"), items())
    assert plan.changes[0].status == Status.ERROR


def test_apply_and_undo(folder, items, journal):
    pic(folder, "IMG.jpg", "2024:07:04 12:30:00")
    plan = make_plan(NameTemplate("{date:%Y%m%d_%H-%M-%S}"), items())
    result = apply_plan(plan, journal)
    assert (folder / "20240704_12-30-00.jpg").exists() and not (folder / "IMG.jpg").exists()
    journal.undo(result.batch_id)
    assert (folder / "IMG.jpg").exists()


def test_server_and_registry(folder, journal):
    pic(folder, "IMG.jpg", "2024:07:04 12:30:00")
    client = TestClient(create_app(journal))
    spec = next(s for s in client.get("/api/operations").json() if s["name"] == "template")
    assert spec["group"] == "Nummer & Datum" and spec["fields"][0]["key"] == "template"
    r = {"paths": [str(folder)], "operation": "template", "params": {"template": "{date:%Y%m%d}"}}
    assert client.post("/api/plan", json=r).json()["changes"][0]["dstName"] == "20240704.jpg"
    bad = client.post("/api/plan", json={**r, "params": {"template": "{x}"}})
    assert bad.status_code == 422 and "Unbekannter Platzhalter" in bad.json()["detail"]


def test_cli(folder):
    pic(folder, "IMG.jpg", "2024:07:04 12:30:00")
    runner = CliRunner()
    out = runner.invoke(cli_app, ["rename", "template", "{date:%Y%m%d}_{n:2}", str(folder)]).output
    assert "20240704_01.jpg" in out
    assert (folder / "IMG.jpg").exists()  # nur Vorschau
    bad = runner.invoke(cli_app, ["rename", "template", "{nope}", str(folder)])
    assert bad.exit_code != 0
    runner.invoke(cli_app, ["rename", "template", "{date:%Y%m%d}", str(folder), "--apply"])
    assert (folder / "20240704.jpg").exists()
