from __future__ import annotations

import pytest

from board_figures._fields import Record
from board_figures.errors import DefinitionError, DumpError


def record(data: object) -> Record:
    return Record(data, "file", DumpError)


def test_fields_come_back_with_their_type() -> None:
    table = record(
        {
            "name": "GND",
            "width": 2,
            "count": 3,
            "on": True,
            "tags": ["a", "b"],
            "box": [1, 2.5],
            "inner": {"x": 1.5},
            "rows": [{"x": 1}, {"x": 2}],
        }
    )

    assert table.text("name") == "GND"
    assert table.number("width") == 2.0
    assert isinstance(table.number("width"), float)
    assert table.integer("count") == 3
    assert table.flag("on") is True
    assert table.texts("tags") == ("a", "b")
    assert table.numbers("box") == (1.0, 2.5)
    assert table.numbers("box", count=2) == (1.0, 2.5)
    assert table.record("inner").number("x") == 1.5
    assert [row.integer("x") for row in table.records("rows")] == [1, 2]
    assert table.items("tags") == ("a", "b")
    assert table.names()[:2] == ("name", "width")


def test_where_follows_the_nesting() -> None:
    table = record({"inner": {}, "rows": [{}, {}]})

    assert table.where == "file"
    assert table.record("inner").where == "file.inner"
    assert table.records("rows")[1].where == "file.rows[1]"


def test_has_is_false_for_a_missing_or_null_field() -> None:
    table = record({"present": 0, "empty": None})

    assert table.has("present")
    assert not table.has("empty")
    assert not table.has("absent")


def test_a_table_must_be_a_mapping() -> None:
    with pytest.raises(DumpError, match="file: expected a table, found list"):
        record([])
    with pytest.raises(DumpError, match="found null"):
        record(None)


def test_a_missing_field_is_named_with_its_place() -> None:
    with pytest.raises(DumpError, match="file: the field 'net' is missing"):
        record({}).text("net")


@pytest.mark.parametrize(
    ("method", "value", "expected"),
    [
        ("text", 5, "a string, found int"),
        ("number", "5", "a number, found str"),
        ("number", True, "a number, found bool"),
        ("integer", 1.5, "an integer, found float"),
        ("integer", False, "an integer, found bool"),
        ("flag", 1, "true or false, found int"),
        ("items", "abc", "a list, found str"),
        ("items", 7, "a list, found int"),
        ("texts", ["a", 1], "a list of strings, found int"),
        ("numbers", [1, "b"], "a number, found str"),
    ],
)
def test_a_value_of_the_wrong_kind_is_rejected(method: str, value: object, expected: str) -> None:
    with pytest.raises(DumpError, match=f"the field 'key' must be {expected}"):
        getattr(record({"key": value}), method)("key")


def test_a_list_of_numbers_can_have_a_fixed_length() -> None:
    with pytest.raises(DumpError, match="the field 'box' needs 4 numbers, found 2"):
        record({"box": [1, 2]}).numbers("box", count=4)


def test_the_error_type_of_the_file_is_raised() -> None:
    table = Record({"inner": 3}, "definition", DefinitionError)

    with pytest.raises(DefinitionError, match=r"definition.inner: expected a table"):
        table.record("inner")
