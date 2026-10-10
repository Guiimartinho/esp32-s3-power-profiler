"""Checked access to the fields of parsed JSON and TOML.

Both the board dump and the board definition arrive as nested dictionaries
and lists of unknown content. :class:`Record` wraps one dictionary and hands
out its fields with the type the caller asks for; a missing field or a value
of another kind raises the error type of the file, with the place of the
field in the message, so that a broken file is reported by name and not by
a ``KeyError`` deep inside a calculation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from board_figures.errors import BoardFiguresError


class Record:
    """One table of a parsed file, with checked access to its fields.

    Args:
        data: The parsed value; anything but a mapping raises ``error``.
        where: Place of the table in its file, used in error messages.
        error: Exception type raised for every problem found.
    """

    def __init__(self, data: object, where: str, error: type[BoardFiguresError]) -> None:
        if not isinstance(data, Mapping):
            raise error(f"{where}: expected a table, found {_kind(data)}")
        self._data: Mapping[str, object] = data
        self._where = where
        self._error = error

    @property
    def where(self) -> str:
        """Place of this table in its file."""
        return self._where

    def names(self) -> tuple[str, ...]:
        """Names of the fields, in the order of the file."""
        return tuple(self._data)

    def has(self, key: str) -> bool:
        """Whether the field is present and not null."""
        return self._data.get(key) is not None

    def text(self, key: str) -> str:
        """A field that holds a string."""
        value = self._value(key)
        if not isinstance(value, str):
            raise self._wrong(key, "a string", value)
        return value

    def number(self, key: str) -> float:
        """A field that holds an integer or a real number."""
        return self._number(self._value(key), key)

    def integer(self, key: str) -> int:
        """A field that holds an integer."""
        value = self._value(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise self._wrong(key, "an integer", value)
        return value

    def flag(self, key: str) -> bool:
        """A field that holds true or false."""
        value = self._value(key)
        if not isinstance(value, bool):
            raise self._wrong(key, "true or false", value)
        return value

    def items(self, key: str) -> tuple[object, ...]:
        """A field that holds a list, with unchecked elements."""
        value = self._value(key)
        if isinstance(value, str) or not isinstance(value, Sequence):
            raise self._wrong(key, "a list", value)
        return tuple(value)

    def texts(self, key: str) -> tuple[str, ...]:
        """A field that holds a list of strings."""
        values = self.items(key)
        for value in values:
            if not isinstance(value, str):
                raise self._wrong(key, "a list of strings", value)
        return tuple(str(value) for value in values)

    def numbers(self, key: str, count: int | None = None) -> tuple[float, ...]:
        """A field that holds a list of numbers, optionally of a fixed length."""
        values = tuple(self._number(value, key) for value in self.items(key))
        if count is not None and len(values) != count:
            raise self._error(
                f"{self._where}: the field '{key}' needs {count} numbers, found {len(values)}"
            )
        return values

    def record(self, key: str) -> Record:
        """A field that holds a table."""
        return Record(self._value(key), f"{self._where}.{key}", self._error)

    def records(self, key: str) -> tuple[Record, ...]:
        """A field that holds a list of tables."""
        return tuple(
            Record(value, f"{self._where}.{key}[{index}]", self._error)
            for index, value in enumerate(self.items(key))
        )

    def _value(self, key: str) -> object:
        if key not in self._data:
            raise self._error(f"{self._where}: the field '{key}' is missing")
        return self._data[key]

    def _number(self, value: object, key: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise self._wrong(key, "a number", value)
        return float(value)

    def _wrong(self, key: str, expected: str, value: object) -> BoardFiguresError:
        return self._error(
            f"{self._where}: the field '{key}' must be {expected}, found {_kind(value)}"
        )


def _kind(value: object) -> str:
    return "null" if value is None else type(value).__name__
