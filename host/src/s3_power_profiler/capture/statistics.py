"""Statistics over captured samples.

Samples flagged invalid lie inside the settling window of a range change. They
are counted, and left out of every statistic.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from s3_power_profiler.capture.calibration import CalibrationTable
from s3_power_profiler.protocol import (
    RANGE_COUNT,
    SAMPLE_FAULT_MASK,
    SAMPLE_FAULT_SHIFT,
    SAMPLE_INVALID_MASK,
    SAMPLE_INVALID_SHIFT,
    SAMPLE_RANGE_MASK,
    SAMPLE_RANGE_SHIFT,
)


@dataclass(frozen=True, slots=True)
class CaptureStatistics:
    """Summary of a capture.

    Attributes:
        samples: Samples received, valid or not.
        valid_samples: Samples used for the statistics.
        invalid_samples: Samples left out because they were flagged invalid.
        fault_samples: Samples taken while the fault latch was set.
        range_samples: Valid samples in each range, R0 first.
        mean_current: Mean current in amperes, or None without valid samples.
        min_current: Lowest current in amperes, or None without valid samples.
        max_current: Highest current in amperes, or None without valid samples.
    """

    samples: int
    valid_samples: int
    invalid_samples: int
    fault_samples: int
    range_samples: tuple[int, ...]
    mean_current: float | None
    min_current: float | None
    max_current: float | None


class StatisticsAccumulator:
    """Running statistics of a capture, fed block by block.

    Args:
        table: Calibration used to turn ADC codes into current.
    """

    def __init__(self, table: CalibrationTable) -> None:
        self._table = table
        self._samples = 0
        self._fault_samples = 0
        self._range_samples = [0] * RANGE_COUNT
        self._sum = 0.0
        self._min: float | None = None
        self._max: float | None = None

    def add(self, words: Sequence[int]) -> None:
        """Add the sample words of one block."""
        self._samples += len(words)
        self._fault_samples += sum(
            1 for word in words if (word >> SAMPLE_FAULT_SHIFT) & SAMPLE_FAULT_MASK
        )
        valid = [word for word in words if not (word >> SAMPLE_INVALID_SHIFT) & SAMPLE_INVALID_MASK]
        if not valid:
            return
        for word in valid:
            self._range_samples[(word >> SAMPLE_RANGE_SHIFT) & SAMPLE_RANGE_MASK] += 1
        currents = self._table.word_currents(valid)
        self._sum += math.fsum(currents)
        lowest, highest = min(currents), max(currents)
        self._min = lowest if self._min is None else min(self._min, lowest)
        self._max = highest if self._max is None else max(self._max, highest)

    def result(self) -> CaptureStatistics:
        """Return the statistics of everything added so far."""
        valid = sum(self._range_samples)
        return CaptureStatistics(
            samples=self._samples,
            valid_samples=valid,
            invalid_samples=self._samples - valid,
            fault_samples=self._fault_samples,
            range_samples=tuple(self._range_samples),
            mean_current=self._sum / valid if valid else None,
            min_current=self._min,
            max_current=self._max,
        )
