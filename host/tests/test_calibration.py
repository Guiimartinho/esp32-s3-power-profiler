from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from s3_power_profiler.capture.calibration import (
    ADC_CODES,
    NOMINAL_AMPLIFIER_GAIN,
    NOMINAL_PEDESTAL,
    NOMINAL_SHUNTS,
    NOMINAL_VREF,
    CalibrationTable,
    RangeCalibration,
    nominal_table,
)
from s3_power_profiler.protocol import RANGE_COUNT, Sample, pack_sample

# Full-scale current of each range in the specification, in amperes: the
# current that gives 2.0 V at the ADC on top of the pedestal.
FULL_SCALE_VOLTS = 2.0
FULL_SCALE_CURRENTS = (100e-6, 3.03e-3, 100e-3, 1.0)

samples = st.builds(
    Sample,
    adc=st.integers(min_value=0, max_value=ADC_CODES - 1),
    range_index=st.integers(min_value=0, max_value=RANGE_COUNT - 1),
    invalid=st.booleans(),
    fault=st.booleans(),
    logic=st.integers(min_value=0, max_value=0xFF),
)


def code_for(volts: float) -> int:
    return round(volts * ADC_CODES / NOMINAL_VREF)


def simple_table() -> CalibrationTable:
    """Table with a different, easy gain per range and an offset of 100 codes."""
    return CalibrationTable(
        ranges=tuple(RangeCalibration(gain=10.0**-index, offset=100.0) for index in range(4))
    )


def test_adc_field_is_16_bits() -> None:
    assert ADC_CODES == 65536


def test_range_calibration_subtracts_the_offset_then_applies_the_gain() -> None:
    calibration = RangeCalibration(gain=0.5, offset=100.0)

    assert calibration.current(100) == 0.0
    assert calibration.current(104) == 2.0
    assert calibration.current(96) == -2.0


def test_table_uses_the_calibration_of_the_range() -> None:
    table = simple_table()

    assert table.current(110, 0) == pytest.approx(10.0)
    assert table.current(110, 1) == pytest.approx(1.0)
    assert table.current(110, 3) == pytest.approx(0.01)


def test_table_is_not_nominal_unless_said_so() -> None:
    assert not simple_table().nominal


@pytest.mark.parametrize("count", [0, RANGE_COUNT - 1, RANGE_COUNT + 1])
def test_table_rejects_the_wrong_number_of_ranges(count: int) -> None:
    with pytest.raises(ValueError, match="needs 4 ranges"):
        CalibrationTable(ranges=(RangeCalibration(1.0, 0.0),) * count)


def test_table_stores_the_ranges_as_a_tuple() -> None:
    table = CalibrationTable(ranges=[RangeCalibration(1.0, 0.0)] * RANGE_COUNT)  # type: ignore[arg-type]

    assert isinstance(table.ranges, tuple)


@pytest.mark.parametrize("range_index", [-1, RANGE_COUNT])
def test_current_rejects_a_range_that_does_not_exist(range_index: int) -> None:
    with pytest.raises(ValueError, match="range"):
        simple_table().current(0, range_index)


@given(sample=samples)
def test_sample_current_matches_current_of_code_and_range(sample: Sample) -> None:
    table = simple_table()

    assert table.sample_current(sample) == table.current(sample.adc, sample.range_index)


@given(block=st.lists(samples, max_size=32))
def test_word_currents_match_sample_currents(block: list[Sample]) -> None:
    table = simple_table()

    currents = table.word_currents([pack_sample(sample) for sample in block])

    assert currents == [table.sample_current(sample) for sample in block]


def test_nominal_table_is_marked_as_design_targets() -> None:
    assert nominal_table().nominal


def test_nominal_table_has_one_entry_per_shunt() -> None:
    assert len(NOMINAL_SHUNTS) == RANGE_COUNT
    assert len(nominal_table().ranges) == RANGE_COUNT


def test_nominal_gain_follows_the_formula_of_the_specification() -> None:
    table = nominal_table()

    for calibration, shunt in zip(table.ranges, NOMINAL_SHUNTS, strict=True):
        expected = NOMINAL_VREF / (ADC_CODES * NOMINAL_AMPLIFIER_GAIN * shunt)
        assert calibration.gain == pytest.approx(expected)


def test_nominal_resolution_matches_the_specification() -> None:
    gains = [calibration.gain for calibration in nominal_table().ranges]

    # Section 4.3: one code is 1.9 nA, 58 nA, 1.9 uA and 19 uA.
    assert gains == pytest.approx([1.9e-9, 58e-9, 1.9e-6, 19e-6], rel=0.01)


def test_nominal_offset_is_the_pedestal_in_codes() -> None:
    table = nominal_table()

    assert all(
        calibration.offset == pytest.approx(NOMINAL_PEDESTAL * ADC_CODES / NOMINAL_VREF)
        for calibration in table.ranges
    )
    # Section 4.5: zero current reads about 1300 codes.
    assert table.ranges[0].offset == pytest.approx(1300, rel=0.01)


def test_nominal_table_reads_zero_at_the_pedestal() -> None:
    table = nominal_table()

    for range_index in range(RANGE_COUNT):
        current = table.current(code_for(NOMINAL_PEDESTAL), range_index)
        assert abs(current) < table.ranges[range_index].gain


@pytest.mark.parametrize(("range_index", "full_scale"), list(enumerate(FULL_SCALE_CURRENTS)))
def test_nominal_table_reads_full_scale_at_two_volts(range_index: int, full_scale: float) -> None:
    code = code_for(NOMINAL_PEDESTAL + FULL_SCALE_VOLTS)

    assert nominal_table().current(code, range_index) == pytest.approx(full_scale, rel=0.001)
