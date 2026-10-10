"""Component values as the schematic writes them.

The schematic gives a value as one string with the rating beside it:
``1k 0.1% 25ppm``, ``100n 50V X7R``, ``0.47R 1% 0.25W``, ``1.5u 4.6A``. The
number is the first word, with the multiplier as a letter that may also stand
in place of the decimal point (``4R7``). The tolerance, when it is given, is
the word that ends in a percent sign.
"""

from __future__ import annotations

import re

from circuit_sim.errors import ValueFormatError

_MULTIPLIER = {
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "m": 1e-3,
    "R": 1.0,
    "": 1.0,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
}
_NUMBER = re.compile(r"^(\d+(?:\.\d+)?)([pnuµmRkKMG]?)(\d*)$")
_PERCENT = re.compile(r"^(\d+(?:\.\d+)?)%$")


def parse_value(text: str) -> float:
    """The number of a value string, in ohms, farads or henries.

    Args:
        text: The value field of a resistor, capacitor or inductor.

    Raises:
        ValueFormatError: When the first word is not a number with an
            optional multiplier.
    """
    words = text.split()
    match = _NUMBER.match(words[0]) if words else None
    if match is None:
        raise ValueFormatError(f"cannot read {text!r} as a component value")
    whole, letter, decimals = match.groups()
    if decimals and "." in whole:
        raise ValueFormatError(f"cannot read {text!r} as a component value")
    number = float(f"{whole}.{decimals}") if decimals else float(whole)
    return number * _MULTIPLIER[letter]


def parse_tolerance(text: str) -> float | None:
    """The tolerance of a value string as a fraction, or None when it gives none.

    ``1k 0.1% 25ppm`` gives 0.001.
    """
    for word in text.split()[1:]:
        match = _PERCENT.match(word)
        if match is not None:
            return float(match.group(1)) / 100.0
    return None
