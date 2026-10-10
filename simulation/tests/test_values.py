from __future__ import annotations

import pytest

from circuit_sim.errors import ValueFormatError
from circuit_sim.values import parse_tolerance, parse_value


@pytest.mark.parametrize(
    ("text", "number"),
    [
        ("1k 0.1% 25ppm", 1e3),
        ("100n 50V X7R", 100e-9),
        ("0.47R 1% 0.25W", 0.47),
        ("1.5u 4.6A", 1.5e-6),
        ("0.1R 0.25% 50ppm", 0.1),
        ("2.2M 1%", 2.2e6),
        ("33R", 33.0),
        ("0R", 0.0),
        ("47", 47.0),
        ("2.00k", 2e3),
        ("10p 50V C0G", 10e-12),
        ("3m", 3e-3),
        ("1G", 1e9),
        ("15K", 15e3),
        ("22µ", 22e-6),
        ("  10k  ", 10e3),
    ],
)
def test_a_value_is_its_first_word_with_the_multiplier(text: str, number: float) -> None:
    assert parse_value(text) == pytest.approx(number, rel=1e-12)


@pytest.mark.parametrize(
    ("text", "number"),
    [
        ("4R7", 4.7),
        ("4k7", 4.7e3),
        ("1M5", 1.5e6),
        ("2u2", 2.2e-6),
        ("0R05", 0.05),
        ("3n3 X7R", 3.3e-9),
    ],
)
def test_the_multiplier_can_stand_in_place_of_the_decimal_point(text: str, number: float) -> None:
    assert parse_value(text) == pytest.approx(number, rel=1e-12)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "TestPoint",
        "k1",
        "R47",
        "1.5k5",
        "1e3",
        "-10k",
        "10kOhm",
        "4A fast 32V",
        "50R@100MHz",
        "5%",
    ],
)
def test_a_first_word_that_is_no_number_is_refused(text: str) -> None:
    with pytest.raises(ValueFormatError, match=r"cannot read .* as a component value"):
        parse_value(text)


def test_the_error_names_the_whole_value() -> None:
    with pytest.raises(ValueFormatError, match="cannot read 'DNP 0603' as a component value"):
        parse_value("DNP 0603")


@pytest.mark.parametrize(
    ("text", "fraction"),
    [
        ("1k 0.1% 25ppm", 0.001),
        ("0.1R 0.25% 50ppm", 0.0025),
        ("220R 5%", 0.05),
        ("100n 50V 10% X7R", 0.10),
        ("10k 1% 0.5%", 0.01),
    ],
)
def test_the_tolerance_is_the_word_with_the_percent_sign(text: str, fraction: float) -> None:
    assert parse_tolerance(text) == pytest.approx(fraction, rel=1e-12)


@pytest.mark.parametrize(
    "text", ["100n 50V X7R", "2.2k", "", "5%", "1k +-1%", "1k 1 %", "1k 25ppm"]
)
def test_a_value_without_such_a_word_has_no_tolerance(text: str) -> None:
    assert parse_tolerance(text) is None
