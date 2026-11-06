import pytest

from procurator.engine import apply_plan, make_plan
from procurator.model import Status
from procurator.ops import Append, ChangeCase, RemoveChars, ReplaceText, Sequence


def test_duplicate_targets_conflict(make, items):
    make("a1.txt", "a2.txt")
    plan = make_plan(RemoveChars(count=1, start=2), items())  # beide -> a.txt
    assert [c.status for c in plan.changes] == [Status.CONFLICT, Status.CONFLICT]
    assert "Doppelter" in plan.changes[0].reason


def test_existing_target_conflict(make, items):
    make("a.txt", "b.txt")
    plan = make_plan(ReplaceText("a", "b"), items())
    a = next(c for c in plan.changes if c.src.name == "a.txt")
    assert a.status == Status.CONFLICT
    assert "existiert" in a.reason


def test_force_unique(make, items, folder):
    make("a1.txt", "a2.txt", "a.txt")
    plan = make_plan(RemoveChars(count=1, start=2), items(), force_unique=True)
    assert all(c.status == Status.OK for c in plan.changes if c.src.name != "a.txt")
    targets = sorted(c.dst.name for c in plan.changes if c.dst)
    assert targets == ["a 1.txt", "a 2.txt"]
    apply_plan(plan)
    assert sorted(p.name for p in folder.iterdir()) == ["a 1.txt", "a 2.txt", "a.txt"]


def test_rename_into_name_freed_by_other_file(make, items, folder):
    """b -> c und a -> b im selben Lauf muss gehen, weil b frei wird."""
    make("a.txt", "b.txt")
    # Sequence-Vorbereitung: eigene Op, die Namen verschiebt
    from procurator.ops.base import Operation

    class Shift(Operation):
        name = "shift"

        def transform(self, item, index):
            return {"a.txt": "b.txt", "b.txt": "c.txt"}[item.name]

    plan = make_plan(Shift(), items())
    assert [c.status for c in plan.changes] == [Status.OK, Status.OK]
    result = apply_plan(plan)
    assert not result.failed
    assert sorted(p.read_text() for p in folder.iterdir()) == ["a.txt", "b.txt"]
    assert (folder / "b.txt").read_text() == "a.txt"
    assert (folder / "c.txt").read_text() == "b.txt"


def test_swap(make, items, folder):
    make("a.txt", "b.txt")
    from procurator.ops.base import Operation

    class Swap(Operation):
        name = "swap"

        def transform(self, item, index):
            return "b.txt" if item.name == "a.txt" else "a.txt"

    result = apply_plan(make_plan(Swap(), items()))
    assert not result.failed
    assert (folder / "a.txt").read_text() == "b.txt"
    assert (folder / "b.txt").read_text() == "a.txt"


def test_case_only_rename(make, items, folder):
    make("abc.txt")
    plan = make_plan(ChangeCase("upper"), items())
    assert plan.changes[0].status == Status.OK
    apply_plan(plan)
    assert [p.name for p in folder.iterdir()] == ["ABC.txt"]


def test_unchecked_rows_are_not_applied(make, items, folder):
    make("a.txt", "b.txt")
    plan = make_plan(Append("_x"), items())
    plan.changes[0].enabled = False
    result = apply_plan(plan)
    assert len(result.done) == 1
    assert sorted(p.name for p in folder.iterdir()) == ["a.txt", "b_x.txt"]


def test_invalid_names(make, items):
    make("a.txt")
    assert make_plan(ReplaceText("a", "x/y"), items()).changes[0].status == Status.ERROR
    assert make_plan(RemoveChars(count=1, mode="from_end"), items()).changes[0].status == Status.OK
    make("b")
    plan = make_plan(RemoveChars(count=5, mode="from_end", keep_extension=False), items())
    assert any(c.status == Status.ERROR and c.reason == "Leerer Name" for c in plan.changes)


def test_plan_does_not_touch_disk(make, items, folder):
    make("a.txt")
    make_plan(Append("_x"), items())
    assert [p.name for p in folder.iterdir()] == ["a.txt"]


def test_apply_skips_target_created_after_plan(make, items, folder):
    make("a.txt")
    plan = make_plan(Append("_x"), items())
    (folder / "a_x.txt").write_text("fremd")
    result = apply_plan(plan)
    assert len(result.failed) == 1
    assert (folder / "a.txt").read_text() == "a.txt"
    assert (folder / "a_x.txt").read_text() == "fremd"


def test_undo(make, items, folder, journal):
    make("a.txt", "b.txt")
    plan = make_plan(Sequence(label="n", position="replace", sort="name"), items())
    result = apply_plan(plan, journal)
    assert sorted(p.name for p in folder.iterdir()) == ["n-001.txt", "n-002.txt"]
    assert result.batch_id is not None
    count, errors = journal.undo(result.batch_id)
    assert (count, errors) == (2, [])
    assert sorted(p.name for p in folder.iterdir()) == ["a.txt", "b.txt"]
    assert journal.batches()[0].undone
    _, errors = journal.undo(result.batch_id)
    assert errors  # zweites Undo wird abgelehnt


@pytest.mark.parametrize("count", [0])
def test_empty_plan_has_no_journal_entry(make, items, journal, count):
    make("a.txt")
    result = apply_plan(make_plan(ReplaceText("zzz", "y"), items()), journal)
    assert result.batch_id is None
    assert journal.batches() == []


def test_force_unique_numbers_duplicates_even_without_existing_target(make, items, folder):
    """Früher wurden beide Zeilen zum Konflikt, wenn am Ziel noch keine Datei lag."""
    make("a1.txt", "a2.txt")
    plan = make_plan(RemoveChars(count=1, start=2), items(), force_unique=True)
    assert all(c.status == Status.OK for c in plan.changes)
    apply_plan(plan)
    assert sorted(p.name for p in folder.iterdir()) == ["a 1.txt", "a.txt"]
