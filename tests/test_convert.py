import os
import shutil
import threading
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from procurator.engine import apply_plan, make_plan
from procurator.model import Status
from procurator.ops.convert import CbrToCbz, ConvertImages
from procurator.scanner import scan

needs_unar = pytest.mark.skipif(shutil.which("unar") is None or shutil.which("lsar") is None,
                                reason="unar nicht installiert")


def make_zip(path: Path, pages: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for n, data in pages.items():
            zf.writestr(n, data)


def test_cbr_plan_maps_names_and_skips_other_types(folder, make):
    (folder / "a.cbr").write_bytes(b"x")
    make("note.txt")
    plan = make_plan(CbrToCbz(), scan(folder))
    by = {c.src.name: c for c in plan.changes}
    assert by["a.cbr"].dst == folder / "a.cbz"
    assert by["note.txt"].status == Status.SKIP
    assert plan.kind == "convert"


def test_output_dir_mirrors_structure(folder, tmp_path):
    sub = folder / "Serie" / "Band 1"
    sub.mkdir(parents=True)
    (sub / "a.cbr").write_bytes(b"x")
    out = tmp_path / "ziel"
    plan = make_plan(CbrToCbz(output_dir=str(out)), scan(folder, recursive=True))
    assert plan.changes[0].dst == out.resolve() / "Serie" / "Band 1" / "a.cbz"


def test_output_dir_inside_source_is_error(folder):
    (folder / "a.cbr").write_bytes(b"x")
    plan = make_plan(CbrToCbz(output_dir=str(folder / "out")), scan(folder))
    assert plan.changes[0].status == Status.ERROR
    assert "ausserhalb" in plan.changes[0].reason


def test_existing_target_is_skipped_for_resume(folder):
    (folder / "a.cbr").write_bytes(b"x")
    (folder / "a.cbz").write_bytes(b"y")
    plan = make_plan(CbrToCbz(), scan(folder))
    c = next(c for c in plan.changes if c.src.name == "a.cbr")
    assert c.status == Status.SKIP and "existiert" in c.reason


def test_copy_options_need_output_dir(folder, tmp_path):
    (folder / "b.cbz").write_bytes(b"z")
    (folder / "c.pdf").write_bytes(b"p")
    p1 = make_plan(CbrToCbz(copy_cbz=True, copy_pdf=True), scan(folder))
    assert all(c.status == Status.SKIP for c in p1.changes)
    p2 = make_plan(CbrToCbz(output_dir=str(tmp_path / "o"), copy_cbz=True, copy_pdf=True),
                   scan(folder))
    assert sorted(c.dst.name for c in p2.changes) == ["b.cbz", "c.pdf"]
    apply_plan(p2)
    assert (tmp_path / "o" / "b.cbz").read_bytes() == b"z"
    assert (folder / "b.cbz").exists()  # Quelle bleibt


def test_cbr_that_is_really_a_zip(folder, tmp_path, journal):
    make_zip(folder / "a.cbr", {"1.jpg": b"jpg"})
    out = tmp_path / "ziel"
    plan = make_plan(CbrToCbz(output_dir=str(out)), scan(folder))
    result = apply_plan(plan, journal)
    assert not result.failed
    assert zipfile.ZipFile(out / "a.cbz").namelist() == ["1.jpg"]
    assert (folder / "a.cbr").exists()


def test_unknown_format_fails_without_leftovers(folder, tmp_path):
    (folder / "a.cbr").write_bytes(b"kein archiv")
    out = tmp_path / "ziel"
    result = apply_plan(make_plan(CbrToCbz(output_dir=str(out)), scan(folder)))
    assert len(result.failed) == 1 and "Weder RAR noch ZIP" in result.failed[0][1]
    assert list(out.rglob("*")) == [] or all(p.is_dir() for p in out.rglob("*"))


@needs_unar
def test_real_rar_roundtrip(folder, tmp_path):
    """Echtes RAR: braucht ein rar-Programm zum Erzeugen, sonst übersprungen."""
    rar = shutil.which("rar")
    if rar is None:
        pytest.skip("rar nicht installiert, kann kein Test-RAR erzeugen")
    pages = tmp_path / "pages"
    pages.mkdir()
    for i in (1, 2, 10):
        (pages / f"p{i}.jpg").write_bytes(f"jpg{i}".encode())
    os.system(f"cd {pages} && {rar} a -ep ../book.rar . >/dev/null")  # noqa: S605
    shutil.copy(tmp_path / "book.rar", folder / "book.cbr")
    out = tmp_path / "ziel"
    result = apply_plan(make_plan(CbrToCbz(output_dir=str(out)), scan(folder)))
    assert not result.failed
    assert zipfile.ZipFile(out / "book.cbz").namelist() == ["p1.jpg", "p2.jpg", "p10.jpg"]


def test_undo_deletes_created_files_but_never_sources(folder, tmp_path, journal):
    make_zip(folder / "a.cbr", {"1.jpg": b"x"})
    out = tmp_path / "ziel"
    result = apply_plan(make_plan(CbrToCbz(output_dir=str(out)), scan(folder)), journal)
    assert (out / "a.cbz").exists()
    count, errors = journal.undo(result.batch_id)
    assert (count, errors) == (1, [])
    assert not (out / "a.cbz").exists()
    assert (folder / "a.cbr").exists()
    assert journal.batches()[0].kind == "convert" and journal.batches()[0].undone


def test_cancel_stops_before_next_file(folder, tmp_path):
    for n in ("a", "b", "c"):
        make_zip(folder / f"{n}.cbr", {"1.jpg": b"x"})
    cancel = threading.Event()
    seen = []

    def progress(done, total, name):
        seen.append(name)
        if name == "a.cbr":
            cancel.set()

    plan = make_plan(CbrToCbz(output_dir=str(tmp_path / "o")), scan(folder))
    result = apply_plan(plan, on_progress=progress, cancel=cancel)
    assert result.cancelled and len(result.done) == 1


def test_images_convert_resize_and_formats(folder, tmp_path):
    Image.new("RGBA", (400, 200), (255, 0, 0, 128)).save(folder / "a.png")
    Image.new("RGB", (100, 100), "blue").save(folder / "b.jpg")
    out = tmp_path / "o"
    plan = make_plan(ConvertImages(output_dir=str(out), format="jpg", max_edge=100), scan(folder))
    names = {c.src.name: c.dst.name for c in plan.changes if c.dst}
    assert names == {"a.png": "a.jpg"}  # b.jpg ist schon JPG und nicht grösser: nichts zu tun
    result = apply_plan(plan)
    assert not result.failed
    with Image.open(out / "a.jpg") as im:
        assert im.format == "JPEG" and im.size == (100, 50) and im.mode == "RGB"


def test_images_webp_without_resize(folder, tmp_path):
    Image.new("RGB", (64, 64), "green").save(folder / "x.png")
    plan = make_plan(ConvertImages(output_dir=str(tmp_path / "o"), format="webp"), scan(folder))
    apply_plan(plan)
    with Image.open(tmp_path / "o" / "x.webp") as im:
        assert im.format == "WEBP"


def test_duplicate_targets_conflict(folder):
    Image.new("RGB", (10, 10)).save(folder / "a.png")
    Image.new("RGB", (10, 10)).save(folder / "a.bmp")
    plan = make_plan(ConvertImages(format="jpg"), scan(folder))
    assert [c.status for c in plan.changes] == [Status.CONFLICT, Status.CONFLICT]


def test_missing_unar_marks_error(folder, monkeypatch):
    (folder / "a.cbr").write_bytes(b"x")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    plan = make_plan(CbrToCbz(), scan(folder))
    assert plan.changes[0].status == Status.ERROR and "unar" in plan.changes[0].reason
