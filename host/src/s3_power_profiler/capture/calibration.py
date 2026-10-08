"""Conversion of ADC codes into current.

The instrument sends raw ADC codes together with the range that was active.
The host turns them into amperes with one gain and one offset per range::

    current = (code - offset[range]) * gain[range]

A real instrument reports its own table. Until one exists, :func:`nominal_table`
derives a table from the design targets of the specification.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from s3_power_profiler.protocol import (
    RANGE_COUNT,
    SAMPLE_ADC_MASK,
    SAMPLE_ADC_SHIFT,
    SAMPLE_RANGE_MASK,
    SAMPLE_RANGE_SHIFT,
    Sample,
)

ADC_CODES = SAMPLE_ADC_MASK + 1
"""Number of codes of the ADC field of the sample word."""

# Design targets from sections 4.3 and 4.5 of the specification. They have not
# been measured on hardware and only serve until a calibrated table exists.
NOMINAL_VREF = 2.5
"""ADC reference voltage in volts (design target)."""

NOMINAL_AMPLIFIER_GAIN = 20.0
"""Gain of the instrumentation amplifier (design target)."""

NOMINAL_SHUNTS = (1000.0, 33.0, 1.0, 0.1)
"""Shunt resistance of ranges R0 to R3 in ohms (design targets)."""

NOMINAL_PEDESTAL = 0.050
"""Voltage at the ADC with zero current, in volts (design target)."""


@dataclass(frozen=True, slots=True)
class RangeCalibration:
    """Calibration of one range.

    Attributes:
        gain: Current per ADC code, in amperes.
        offset: ADC code read at zero current.
    """

    gain: float
    offset: float

    def current(self, code: int) -> float:
        """Return the current in amperes for an ADC code."""
        return (code - self.offset) * self.gain


@dataclass(frozen=True, slots=True)
class CalibrationTable:
    """Gain and offset of every range.

    Attributes:
        ranges: Calibration of R0 to R3, in that order.
        nominal: True when the values are design targets, not measurements.

    Raises:
        ValueError: If the number of ranges is not the one of the protocol.
    """

    ranges: tuple[RangeCalibration, ...]
    nominal: bool = False

    def __post_init__(self) -> None:
        if len(self.ranges) != RANGE_COUNT:
            raise ValueError(
                f"a calibration table needs {RANGE_COUNT} ranges, got {len(self.ranges)}"
            )
        object.__setattr__(self, "ranges", tuple(self.ranges))

    def current(self, code: int, range_index: int) -> float:
        """Return the current in amperes for an ADC code read in a range.

        Raises:
            ValueError: If the range does not exist.
        """
        if not 0 <= range_index < len(self.ranges):
            raise ValueError(f"range {range_index} is outside 0 to {len(self.ranges) - 1}")
        return self.ranges[range_index].current(code)

    def sample_current(self, sample: Sample) -> float:
        """Return the current in amperes of a decoded sample."""
        return self.current(sample.adc, sample.range_index)

    def word_currents(self, words: Sequence[int]) -> list[float]:
        """Return the current in amperes of every sample word, in order.

        The flags of the words are not looked at: the caller decides what to
        do with samples flagged invalid.
        """
        gains = [entry.gain for entry in self.ranges]
        offsets = [entry.offset for entry in self.ranges]
        currents = []
        for word in words:
            range_index = (word >> SAMPLE_RANGE_SHIFT) & SAMPLE_RANGE_MASK
            code = (word >> SAMPLE_ADC_SHIFT) & SAMPLE_ADC_MASK
            currents.append((code - offsets[range_index]) * gains[range_index])
        return currents


def nominal_table() -> CalibrationTable:
    """Return the table computed from the design targets of the specification.

    The gain of a range is ``VREF / (codes * G * R)`` and the offset is the
    pedestal expressed in ADC codes. These are design targets, not measured
    values: use them for simulation and for a first look at uncalibrated data.
    """
    volts_per_code = NOMINAL_VREF / ADC_CODES
    offset = NOMINAL_PEDESTAL / volts_per_code
    return CalibrationTable(
        ranges=tuple(
            RangeCalibration(gain=volts_per_code / (NOMINAL_AMPLIFIER_GAIN * shunt), offset=offset)
            for shunt in NOMINAL_SHUNTS
        ),
        nominal=True,
    )
