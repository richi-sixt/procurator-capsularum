"""O-10: Dateien aus _Dubletten-Ordnern in den Papierkorb legen (der Papierkorb selbst wird ersetzt)."""

from pathlib import Path

import pytest

from procurator.engine import apply_plan, make_plan
from procurator.model import Status
from procurator.ops import MoveDuplicates, TrashDuplicates
from procurator.ops import trash as trashmod
from procurator.scanner import scan


@pytest.fixture
def trashed(monkeypatch):
    """Statt in den Papierkorb zu legen, wird die Datei in eine Liste notiert und gelöscht."""
    seen: list[Path] = []

    def fake(path: Path) -> None:
        seen.append(path)
        path.unlink()

    monkeypatch.setattr(trashmod, "send_to_trash", fake)
    return seen


def write(folder: Path, rel: str, data: bytes = b"inhalt") -> Path:
    p = folder / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def plan_for(folder: Path):
    return make_plan(TrashDuplicates(), scan(folder, recursive=True))


def test_only_files_in_duplicate_folders_are_planned(folder):
    write(folder, "foto.jpg")
    write(folder, "_Dubletten/kopie.jpg")
    write(folder, "_Dubletten/unter/ordner/tief.jpg")
    write(folder, "andere/nicht.jpg")
    plan = plan_for(folder)
    rows = {c.src.name: c for c in plan.changes}
    assert rows["kopie.jpg"].status == Status.OK and rows["tief.jpg"].status == Status.OK
    assert rows["foto.jpg"].status == Status.SKIP and rows["nicht.jpg"].status == Status.SKIP
    assert rows["foto.jpg"].reason == "Nicht in einem Dubletten-Ordner"
    assert plan.kind == "trash" and plan.info == {"trashFiles": 2, "trashBytes": 12}


def test_the_chosen_folder_may_itself_be_a_duplicates_folder(tmp_path):
    root = tmp_path / "_Dubletten"
    write(root, "a.jpg")
    plan = make_plan(TrashDuplicates(), scan(root, recursive=True))
    assert [c.status for c in plan.changes] == [Status.OK]


def test_same_names_in_different_folders_are_not_a_conflict(folder):
    write(folder, "_Dubletten/a/x.jpg")
    write(folder, "_Dubletten/b/x.jpg")
    assert [c.status for c in plan_for(folder).changes] == [Status.OK, Status.OK]


def test_apply_trashes_files_and_removes_emptied_folders(folder, trashed, journal):
    write(folder, "foto.jpg")
    write(folder, "_Dubletten/a/kopie.jpg")
    write(folder, "_Dubletten/b/kopie2.jpg")
    result = apply_plan(plan_for(folder), journal)
    assert len(result.done) == 2 and not result.failed
    assert sorted(p.name for p in trashed) == ["kopie.jpg", "kopie2.jpg"]
    assert (folder / "foto.jpg").exists()
    assert not (folder / "_Dubletten").exists()  # leere Ordner sind aufgeräumt


def test_folders_with_other_content_are_left_alone(folder, trashed):
    write(folder, "_Dubletten/a/kopie.jpg")
    write(folder, "_Dubletten/a/fremd.txt")  # steht nicht im Plan? doch: auch das ist eine Datei im Ordner
    plan = plan_for(folder)
    plan.changes = [c for c in plan.changes if c.src.name == "kopie.jpg"]  # nur eine Datei ausgewählt
    apply_plan(plan)
    assert (folder / "_Dubletten/a/fremd.txt").exists() and (folder / "_Dubletten/a").is_dir()


def test_prune_never_walks_above_the_duplicates_folder(folder):
    (folder / "aussen").mkdir()
    deep = folder / "aussen" / "_Dubletten" / "x"
    deep.mkdir(parents=True)
    trashmod.prune_empty(deep)
    assert (folder / "aussen").is_dir() and not (folder / "aussen" / "_Dubletten").exists()


def test_a_failing_trash_is_reported_and_does_not_stop_the_run(folder, monkeypatch):
    write(folder, "_Dubletten/a.jpg")
    write(folder, "_Dubletten/b.jpg")

    def broken(path: Path) -> None:
        if path.name == "a.jpg":
            raise OSError("Papierkorb nicht erreichbar")
        path.unlink()

    monkeypatch.setattr(trashmod, "send_to_trash", broken)
    result = apply_plan(plan_for(folder))
    assert [c.src.name for c in result.done] == ["b.jpg"]
    assert result.failed[0][0].src.name == "a.jpg" and "nicht erreichbar" in result.failed[0][1]
    assert (folder / "_Dubletten/a.jpg").exists()


def test_history_records_the_run_but_it_cannot_be_undone(folder, trashed, journal):
    write(folder, "_Dubletten/kopie.jpg")
    result = apply_plan(plan_for(folder), journal)
    assert journal.batch_kind(result.batch_id) == "trash"
    restored, errors = journal.undo(result.batch_id)
    assert restored == 0 and "Papierkorb" in errors[0]
    assert not journal.batches(5)[0].undone  # bleibt als nicht rückgängig gemacht stehen


def test_duplicates_then_trash_end_to_end(folder, trashed):
    write(folder, "a/foto.jpg", b"gleich" * 100)
    write(folder, "b/kopie.jpg", b"gleich" * 100)
    op = MoveDuplicates()
    items = scan(folder, recursive=True)
    op.analyze(items)
    apply_plan(make_plan(op, items))
    assert (folder / "_Dubletten").is_dir()
    apply_plan(plan_for(folder))
    assert not (folder / "_Dubletten").exists() and len(trashed) == 1


def test_the_operation_is_listed_as_destructive():
    from procurator.ops.registry import SPECS

    spec = {s.name: s.to_dict() for s in SPECS}["trash_duplicates"]
    assert spec["destructive"] is True and spec["kind"] == "trash" and spec["fields"] == []
    assert not any(s.to_dict()["destructive"] for s in SPECS if s.name != "trash_duplicates")


def test_the_real_trash_function_calls_send2trash(tmp_path, monkeypatch):
    import send2trash

    called = []
    monkeypatch.setattr(send2trash, "send2trash", lambda p: called.append(p))
    trashmod.send_to_trash(tmp_path / "x.jpg")
    assert called == [str(tmp_path / "x.jpg")]
