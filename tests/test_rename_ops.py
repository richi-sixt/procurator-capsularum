from datetime import date

from procurator.engine import make_plan
from procurator.model import Status
from procurator.ops import (
    Append,
    ChangeCase,
    DateStamp,
    InsertChars,
    Prepend,
    RegexReplace,
    RemoveChars,
    ReplaceText,
    Sequence,
    Wildcard,
)


def names(plan):
    return {c.src.name: (c.dst.name if c.dst else None) for c in plan.changes}


def test_replace_all_first_last(make, items):
    make("a-b-c.txt")
    assert names(make_plan(ReplaceText("-", "_", "all"), items())) == {"a-b-c.txt": "a_b_c.txt"}
    assert names(make_plan(ReplaceText("-", "_", "first"), items())) == {"a-b-c.txt": "a_b-c.txt"}
    assert names(make_plan(ReplaceText("-", "_", "last"), items())) == {"a-b-c.txt": "a-b_c.txt"}


def test_replace_ignore_case_and_extension_untouched(make, items):
    make("Foo.TXT")
    plan = make_plan(ReplaceText("txt", "x", ignore_case=True), items())
    assert plan.changes[0].status == Status.SKIP  # Endung wird nicht bearbeitet
    plan = make_plan(ReplaceText("txt", "x", ignore_case=True, keep_extension=False), items())
    assert names(plan) == {"Foo.TXT": "Foo.x"}


def test_no_match_is_skipped(make, items):
    make("a.txt")
    c = make_plan(ReplaceText("zzz", "y"), items()).changes[0]
    assert c.status == Status.SKIP


def test_wildcard(make, items):
    make("IMG_1234_final.jpg")
    assert names(make_plan(Wildcard("IMG_????_", "Foto "), items())) == {
        "IMG_1234_final.jpg": "Foto final.jpg"
    }
    assert names(make_plan(Wildcard("_*l", "!"), items())) == {"IMG_1234_final.jpg": "IMG!.jpg"}


def test_regex_backreferences(make, items):
    make("Smith, John.txt")
    plan = make_plan(RegexReplace(r"(\w+), (\w+)", "$2 $1"), items())
    assert names(plan) == {"Smith, John.txt": "John Smith.txt"}


def test_regex_invalid_pattern_is_error(make, items):
    make("a.txt")
    c = make_plan(RegexReplace("("), items()).changes[0]
    assert c.status == Status.ERROR


def test_append_prepend(make, items):
    make("a.txt")
    assert names(make_plan(Append("_x"), items())) == {"a.txt": "a_x.txt"}
    assert names(make_plan(Prepend("x_"), items())) == {"a.txt": "x_a.txt"}


def test_remove_chars(make, items):
    make("abcdef.txt", "ab.txt")
    plan = make_plan(RemoveChars(count=2, start=3), items())
    assert names(plan)["abcdef.txt"] == "abef.txt"
    assert next(c for c in plan.changes if c.src.name == "ab.txt").status == Status.SKIP  # kürzer als Start 3
    plan = make_plan(RemoveChars(count=2, mode="from_end"), items())
    assert names(plan)["abcdef.txt"] == "abcd.txt"


def test_insert_and_pad(make, items):
    make("ab.txt", "abcdef.txt")
    plan = make_plan(InsertChars("X", index=1), items())
    assert names(plan)["ab.txt"] == "aXb.txt"
    plan = make_plan(InsertChars("0", index=0, pad_to_length=5), items())
    assert names(plan) == {"ab.txt": "000ab.txt", "abcdef.txt": None}
    plan = make_plan(InsertChars("X", index=1, from_end=True), items())
    assert names(plan)["ab.txt"] == "aXb.txt"


def test_case(make, items):
    make("hello wORLD it's.txt")
    assert names(make_plan(ChangeCase("title"), items())) == {
        "hello wORLD it's.txt": "Hello World It's.txt"
    }
    assert names(make_plan(ChangeCase("upper"), items())) == {
        "hello wORLD it's.txt": "HELLO WORLD IT'S.txt"
    }


def test_sequence_natural_order_and_label(make, items):
    make("p10.jpg", "p2.jpg", "p1.jpg")
    plan = make_plan(Sequence(label="Image", digits=3, position="replace", sort="name"), items())
    assert names(plan) == {"p1.jpg": "Image-001.jpg", "p2.jpg": "Image-002.jpg",
                           "p10.jpg": "Image-003.jpg"}
    plan = make_plan(Sequence(label="Image", position="replace", label_first=False,
                              sort="name", descending=True, start=10), items())
    assert names(plan)["p10.jpg"] == "010-Image.jpg"


def test_date_custom(make, items):
    make("a.txt")
    plan = make_plan(DateStamp("custom", date(2026, 11, 6)), items())
    assert names(plan) == {"a.txt": "2026-11-06_a.txt"}
    plan = make_plan(DateStamp("custom", date(2026, 11, 6), "%Y%m%d", "replace"), items())
    assert names(plan) == {"a.txt": "20261106.txt"}
