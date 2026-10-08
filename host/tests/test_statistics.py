from __future__ import annotations

import pytest

from s3_power_profiler.capture.calibration import CalibrationTable, RangeCalibration
from s3_power_profiler.capture.statistics import CaptureStatistics, StatisticsAccumulator
from s3_power_profiler.protocol import RANGE_COUNT, Sample, pack_sample


def table() -> CalibrationTable:
    """One ampere per code in every range, with no offset: current equals code."""
    return CalibrationTable(ranges=(RangeCalibration(gain=1.0, offset=0.0),) * RANGE_COUNT)


def words(*samples: Sample) -> list[int]:
    return [pack_sample(sample) for sample in samples]


def test_nothing_added_gives_empty_statistics() -> None:
    assert StatisticsAccumulator(table()).result() == CaptureStatistics(
        samples=0,
        valid_samples=0,
        invalid_samples=0,
        fault_samples=0,
        range_samples=(0,) * RANGE_COUNT,
        mean_current=None,
        min_current=None,
        max_current=None,
    )


def test_mean_minimum_and_maximum_of_valid_samples() -> None:
    accumulator = StatisticsAccumulator(table())

    accumulator.add(words(Sample(10, 0), Sample(20, 1), Sample(60, 1)))

    result = accumulator.result()
    assert result.samples == 3
    assert result.valid_samples == 3
    assert result.mean_current == pytest.approx(30.0)
    assert result.min_current == 10.0
    assert result.max_current == 60.0
    assert result.range_samples == (1, 2, 0, 0)


def test_invalid_samples_are_counted_and_left_out() -> None:
    accumulator = StatisticsAccumulator(table())

    accumulator.add(
        words(
            Sample(10, 0), Sample(60000, 3, invalid=True), Sample(30, 0), Sample(0, 2, invalid=True)
        )
    )

    result = accumulator.result()
    assert result.samples == 4
    assert result.valid_samples == 2
    assert result.invalid_samples == 2
    assert result.mean_current == pytest.approx(20.0)
    assert result.min_current == 10.0
    assert result.max_current == 30.0
    assert result.range_samples == (2, 0, 0, 0)


def test_block_with_only_invalid_samples_changes_no_statistic() -> None:
    accumulator = StatisticsAccumulator(table())
    accumulator.add(words(Sample(5, 0)))

    accumulator.add(words(Sample(900, 1, invalid=True), Sample(901, 1, invalid=True)))

    result = accumulator.result()
    assert result.samples == 3
    assert result.invalid_samples == 2
    assert (result.mean_current, result.min_current, result.max_current) == (5.0, 5.0, 5.0)


def test_only_invalid_samples_give_no_current() -> None:
    accumulator = StatisticsAccumulator(table())

    accumulator.add(words(Sample(900, 1, invalid=True)))

    result = accumulator.result()
    assert result.valid_samples == 0
    assert result.mean_current is None
    assert result.min_current is None
    assert result.max_current is None


def test_samples_with_the_fault_flag_are_counted_and_kept() -> None:
    accumulator = StatisticsAccumulator(table())

    accumulator.add(
        words(Sample(10, 3, fault=True), Sample(30, 3), Sample(7, 3, invalid=True, fault=True))
    )

    result = accumulator.result()
    assert result.fault_samples == 2
    assert result.valid_samples == 2
    assert result.mean_current == pytest.approx(20.0)


def test_statistics_accumulate_over_blocks() -> None:
    accumulator = StatisticsAccumulator(table())

    accumulator.add(words(Sample(40, 0), Sample(50, 0)))
    accumulator.add(words(Sample(10, 2)))
    accumulator.add([])
    accumulator.add(words(Sample(100, 3), Sample(0, 1)))

    result = accumulator.result()
    assert result.samples == 5
    assert result.mean_current == pytest.approx(40.0)
    assert result.min_current == 0.0
    assert result.max_current == 100.0
    assert result.range_samples == (2, 1, 1, 1)


def test_calibration_is_applied_per_range() -> None:
    ranges = tuple(RangeCalibration(gain=float(index + 1), offset=10.0) for index in range(4))
    accumulator = StatisticsAccumulator(CalibrationTable(ranges=ranges))

    accumulator.add(words(Sample(20, 0), Sample(20, 3)))

    result = accumulator.result()
    assert result.min_current == pytest.approx(10.0)
    assert result.max_current == pytest.approx(40.0)
    assert result.mean_current == pytest.approx(25.0)


def test_result_can_be_read_while_adding() -> None:
    accumulator = StatisticsAccumulator(table())
    accumulator.add(words(Sample(10, 0)))
    first = accumulator.result()

    accumulator.add(words(Sample(30, 0)))

    assert first.mean_current == 10.0
    assert accumulator.result().mean_current == pytest.approx(20.0)
