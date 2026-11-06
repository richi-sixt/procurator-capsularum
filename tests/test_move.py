import filecmp
import os
import stat
from pathlib import Path

import pytest

from procurator import fsops
from procurator.engine import apply_plan, make_plan
from procurator.model import Status
from procurator.ops import MoveToFolder
from procurator.scanner import scan


def tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_flat_move_creates_target_dir_and_keeps_names(folder, make, tmp_path):
    make("a.txt", "b.txt")
    out = tmp_path / "neu" / "unter"
    plan = make_plan(MoveToFolder(str(out)), scan(folder))
    assert [c.status for c in plan.changes] == [Status.OK, Status.OK]
    result = apply_plan(plan)
    assert not result.failed
    assert tree(out) == ["a.txt", "b.txt"]
    assert not (folder / "a.txt").exists()
    assert result.created_dirs == [tmp_path / "neu", out]


def test_keep_structure_mirrors_subfolders(folder, tmp_path):
    (folder / "Serie" / "Band 1").mkdir(parents=True)
    (folder / "Serie" / "Band 1" / "x.txt").write_text("x")
    (folder / "y.txt").write_text("y")
    out = tmp_path / "ziel"
    plan = make_plan(MoveToFolder(str(out), keep_structure=True), scan(folder, recursive=True))
    apply_plan(plan)
    assert tree(out) == ["Serie", "Serie/Band 1", "Serie/Band 1/x.txt", "y.txt"]


def test_flat_move_name_clash_is_conflict_and_force_unique_numbers(folder, tmp_path):
    (folder / "a").mkdir()
    (folder / "b").mkdir()
    (folder / "a" / "same.txt").write_text("1")
    (folder / "b" / "same.txt").write_text("2")
    out = tmp_path / "ziel"
    items = scan(folder, recursive=True)
    plan = make_plan(MoveToFolder(str(out)), items)
    assert [c.status for c in plan.changes] == [Status.CONFLICT, Status.CONFLICT]
    plan = make_plan(MoveToFolder(str(out)), items, force_unique=True)
    apply_plan(plan)
    assert tree(out) == ["same 1.txt", "same.txt"]


def test_existing_target_is_conflict_and_never_overwritten(folder, make, tmp_path):
    make("a.txt")
    out = tmp_path / "ziel"
    out.mkdir()
    (out / "a.txt").write_text("fremd")
    plan = make_plan(MoveToFolder(str(out)), scan(folder))
    assert plan.changes[0].status == Status.CONFLICT
    assert (out / "a.txt").read_text() == "fremd"


def test_same_folder_is_skipped(folder, make):
    make("a.txt")
    plan = make_plan(MoveToFolder(str(folder)), scan(folder))
    assert plan.changes[0].status == Status.SKIP


def test_invalid_targets(folder, make, tmp_path):
    make("a.txt")
    assert make_plan(MoveToFolder(""), scan(folder)).changes[0].status == Status.ERROR
    assert make_plan(MoveToFolder("relativ/pfad"), scan(folder)).changes[0].status == Status.ERROR
    blocker = tmp_path / "datei"
    blocker.write_text("x")
    plan = make_plan(MoveToFolder(str(blocker / "sub")), scan(folder))
    assert plan.changes[0].status == Status.ERROR
    assert "Datei" in plan.changes[0].reason


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignoriert Dateirechte")
def test_unwritable_target_is_error(folder, make, tmp_path):
    make("a.txt")
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        plan = make_plan(MoveToFolder(str(ro / "neu")), scan(folder))
        assert plan.changes[0].status == Status.ERROR
        assert "Schreibrechte" in plan.changes[0].reason
    finally:
        ro.chmod(stat.S_IRWXU)


def test_undo_restores_and_removes_created_empty_dirs(folder, make, tmp_path, journal):
    make("a.txt")
    out = tmp_path / "neu" / "unter"
    result = apply_plan(make_plan(MoveToFolder(str(out)), scan(folder)), journal)
    assert (out / "a.txt").exists()
    count, errors = journal.undo(result.batch_id)
    assert (count, errors) == (1, [])
    assert (folder / "a.txt").exists()
    assert not (tmp_path / "neu").exists()  # beide angelegten Ordner sind wieder weg


def test_undo_keeps_dirs_that_are_no_longer_empty(folder, make, tmp_path, journal):
    make("a.txt")
    out = tmp_path / "neu"
    result = apply_plan(make_plan(MoveToFolder(str(out)), scan(folder)), journal)
    (out / "fremd.txt").write_text("x")
    journal.undo(result.batch_id)
    assert (out / "fremd.txt").exists()


def test_undo_keeps_preexisting_dirs(folder, make, tmp_path, journal):
    make("a.txt")
    out = tmp_path / "schon-da"
    out.mkdir()
    result = apply_plan(make_plan(MoveToFolder(str(out)), scan(folder)), journal)
    journal.undo(result.batch_id)
    assert out.is_dir()


def test_failed_run_leaves_no_empty_created_dirs(folder, make, tmp_path):
    make("a.txt")
    out = tmp_path / "neu"
    plan = make_plan(MoveToFolder(str(out)), scan(folder))
    (folder / "a.txt").unlink()  # Quelle verschwindet nach der Vorschau
    result = apply_plan(plan)
    assert len(result.failed) == 1
    assert not out.exists()


def test_cross_device_copies_verifies_then_deletes(folder, make, tmp_path, monkeypatch):
    make("a.txt")
    monkeypatch.setattr(fsops, "_same_device", lambda *_: False)
    out = tmp_path / "ziel"
    result = apply_plan(make_plan(MoveToFolder(str(out)), scan(folder)))
    assert not result.failed
    assert (out / "a.txt").read_text() == "a.txt"
    assert not (folder / "a.txt").exists()
    assert tree(out) == ["a.txt"]  # keine .part-Reste


def test_cross_device_verify_failure_keeps_original(folder, make, tmp_path, monkeypatch):
    make("a.txt")
    monkeypatch.setattr(fsops, "_same_device", lambda *_: False)
    monkeypatch.setattr(filecmp, "cmp", lambda *a, **k: False)
    out = tmp_path / "ziel"
    result = apply_plan(make_plan(MoveToFolder(str(out)), scan(folder)))
    assert len(result.failed) == 1 and "weicht vom Original ab" in result.failed[0][1]
    assert (folder / "a.txt").read_text() == "a.txt"  # Original unversehrt
    assert not out.exists()  # kein Ziel, keine .part-Datei, kein leerer Ordner


def test_cross_device_undo_moves_back(folder, make, tmp_path, journal, monkeypatch):
    make("a.txt")
    monkeypatch.setattr(fsops, "_same_device", lambda *_: False)
    out = tmp_path / "ziel"
    result = apply_plan(make_plan(MoveToFolder(str(out)), scan(folder)), journal)
    count, errors = journal.undo(result.batch_id)
    assert (count, errors) == (1, [])
    assert (folder / "a.txt").read_text() == "a.txt" and not out.exists()


def test_swap_still_works_with_new_fsops(folder, make):
    from procurator.ops.base import Operation

    make("a.txt", "b.txt")

    class Swap(Operation):
        name = "swap"

        def transform(self, item, index):
            return "b.txt" if item.name == "a.txt" else "a.txt"

    result = apply_plan(make_plan(Swap(), scan(folder)))
    assert not result.failed
    assert (folder / "a.txt").read_text() == "b.txt"
