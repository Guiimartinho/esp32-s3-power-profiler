from __future__ import annotations

import pytest

from circuit_sim._worker import _word


@pytest.mark.parametrize(
    "name",
    [
        "ranges.r0-5v.cir",
        "E:/KiCAD/lib/ngspice/analog.cm",
        "/usr/lib/x86_64-linux-gnu/ngspice/digital.cm",
        "",
    ],
)
def test_a_file_name_without_a_blank_is_a_word_of_a_command_as_it_is(name: str) -> None:
    assert _word(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "divider at rest.cir",
        "C:/Program Files/KiCad/10.0/lib/ngspice/analog.cm",
        "a\ttab.cir",
    ],
)
def test_a_file_name_with_a_blank_goes_in_single_quotes(name: str) -> None:
    # The library takes a name in double quotes with its quotes, and a blank
    # with a backslash in front as the end of the word.
    assert _word(name) == f"'{name}'"
