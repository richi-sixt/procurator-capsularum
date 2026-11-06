"""Datum aus Metadaten: Aufnahmedatum (EXIF) oder ältestes Dateidatum, nie der Ausführungstag."""

import os
from datetime import date, datetime
from pathlib import Path

import pytest
from PIL import Image

from procurator.engine import make_plan
from procurator.meta import best_date, exif_date
from procurator.ops import DateStamp
from procurator.ops.registry import SPECS, build

OLD = datetime(2018, 3, 1, 10, 0).timestamp()


def photo(folder: Path, name: str, *, original: str | None = None, modified: str | None = None,
          mtime: float | None = None) -> Path:
    path = folder / name
    img = Image.new("RGB", (8, 8), "white")
    exif = Image.Exif()
    if original:
        exif[0x8769] = {36867: original}
    if modified:
        exif[306] = modified
    img.save(path, exif=exif)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def plain(folder: Path, name: str, mtime: float = OLD) -> Path:
    path = folder / name
    path.write_text("x")
    os.utime(path, (mtime, mtime))
    return path


def test_exif_capture_date_beats_file_dates(folder):
    p = photo(folder, "IMG_1.jpg", original="2019:07:04 12:30:00", mtime=OLD)
    assert exif_date(p) == ("Aufnahmedatum", datetime(2019, 7, 4, 12, 30))
    stamp, source = best_date(p)
    assert stamp.date() == date(2019, 7, 4) and "EXIF" in source


def test_exif_falls_back_to_the_images_own_modified_tag(folder):
    p = photo(folder, "b.jpg", modified="2020:01:02 03:04:05")
    assert exif_date(p) == ("Änderungsdatum im Bild", datetime(2020, 1, 2, 3, 4, 5))


@pytest.mark.parametrize("raw", ["0000:00:00 00:00:00", "garbage", "1970:01:01 00:00:00",
                                 "2999:01:01 00:00:00"])
def test_implausible_exif_dates_are_ignored(folder, raw):
    p = photo(folder, "c.jpg", original=raw, mtime=OLD)
    assert exif_date(p) is None
    assert best_date(p)[0].date() == date(2018, 3, 1)


def test_file_without_exif_uses_the_older_of_created_and_modified(folder):
    p = plain(folder, "doc.txt")  # erstellt jetzt, geändert 2018: das ältere gewinnt
    stamp, source = best_date(p)
    # macOS setzt beim Zurückdatieren auch das Erstellungsdatum zurück, die Quelle kann also beides sein
    assert stamp.date() == date(2018, 3, 1) and "der Datei" in source


def test_never_the_day_of_execution(folder):
    p = plain(folder, "doc.txt")
    assert best_date(p)[0].date() != date.today()


def test_broken_image_falls_back_to_file_dates(folder):
    p = folder / "kaputt.jpg"
    p.write_bytes(b"not an image")
    os.utime(p, (OLD, OLD))
    assert exif_date(p) is None and best_date(p)[0].date() == date(2018, 3, 1)


def test_default_source_is_auto():
    assert DateStamp().source == "auto"
    spec = next(s for s in SPECS if s.name == "date")
    assert next(f for f in spec.fields if f.key == "source").default == "auto"
    assert build("date", {}).source == "auto"


def test_rename_uses_exif_date_for_photos_and_file_date_for_the_rest(folder, items):
    photo(folder, "IMG_1.jpg", original="2019:07:04 12:30:00", mtime=OLD)
    plain(folder, "notiz.txt")
    plan = make_plan(DateStamp(), items())
    names = {c.src.name: c for c in plan.changes}
    assert names["IMG_1.jpg"].dst.name == "2019-07-04_IMG_1.jpg"
    assert names["notiz.txt"].dst.name == "2018-03-01_notiz.txt"
    assert "EXIF" in names["IMG_1.jpg"].reason
    assert "der Datei" in names["notiz.txt"].reason


def test_format_and_position_still_apply(folder, items):
    photo(folder, "IMG_1.jpg", original="2019:07:04 12:30:00")
    plan = make_plan(DateStamp(fmt="%Y%m%d", position="append", sep="-"), items())
    assert plan.changes[0].dst.name == "IMG_1-20190704.jpg"


def test_explicit_sources_do_not_look_at_exif(folder, items):
    photo(folder, "IMG_1.jpg", original="2019:07:04 12:30:00", mtime=OLD)
    plan = make_plan(DateStamp(source="modified"), items())
    assert plan.changes[0].dst.name == "2018-03-01_IMG_1.jpg"
    assert plan.changes[0].reason == ""  # nur bei «auto» wird die Quelle genannt


def test_sequence_can_follow_the_capture_date(folder, items):
    from procurator.ops import Sequence

    photo(folder, "b_zuerst.jpg", original="2019:01:01 08:00:00", mtime=OLD)
    photo(folder, "a_spaeter.jpg", original="2020:01:01 08:00:00", mtime=OLD)
    plain(folder, "c_text.txt", mtime=datetime(2019, 6, 1).timestamp())
    plan = make_plan(Sequence(label="", digits=2, position="replace", sort="auto"), items())
    order = {c.src.name: c.dst.stem for c in plan.changes}
    assert order == {"b_zuerst.jpg": "01", "c_text.txt": "02", "a_spaeter.jpg": "03"}
    desc = make_plan(Sequence(label="", digits=2, position="replace", sort="auto",
                              descending=True), items())
    assert {c.src.name: c.dst.stem for c in desc.changes}["a_spaeter.jpg"] == "01"
