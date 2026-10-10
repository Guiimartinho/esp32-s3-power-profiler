from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest

from circuit_sim import measure
from circuit_sim.errors import MeasureError
from circuit_sim.measure import Complex, Real

TAU = 1e-3
HALF_POWER = 10.0 * np.log10(2.0)


def uneven(start: float, stop: float, points: int, seed: int = 20261010) -> Real:
    """An axis whose steps differ by up to a factor of nine, as a simulator leaves it."""
    steps = np.random.default_rng(seed).uniform(0.2, 1.8, points - 1)
    travelled = np.concatenate(([0.0], np.cumsum(steps))) / float(np.sum(steps))
    axis = start + (stop - start) * travelled
    axis[-1] = stop
    return np.asarray(axis, dtype=np.float64)


def with_points(axis: Real, *points: float) -> Real:
    """An axis with some instants added, so that a corner of a waveform is a sample."""
    return np.asarray(np.union1d(axis, np.array(points)), dtype=np.float64)


def triangle(time: Real) -> Real:
    """A triangle between 0 and 1 with a period of 2: at 0 on even and at 1 on odd instants."""
    return np.asarray(1.0 - np.abs(np.mod(time, 2.0) - 1.0), dtype=np.float64)


def two_pole_step(time: Real, damping: float, omega: float) -> Real:
    """The step of two complex poles from 0 to 1."""
    root = np.sqrt(1.0 - damping**2)
    ringing = np.sin(omega * root * time + np.arccos(damping))
    return np.asarray(1.0 - np.exp(-damping * omega * time) * ringing / root, dtype=np.float64)


def first_peak(damping: float, omega: float) -> tuple[float, float]:
    """The instant of the first peak of that step and how far it passes 1."""
    root = float(np.sqrt(1.0 - damping**2))
    return float(np.pi / (omega * root)), float(np.exp(-np.pi * damping / root))


def as_complex(values: object) -> Complex:
    return np.asarray(values, dtype=np.complex128)


def one_pole(frequency: Real, corner: float) -> Complex:
    return as_complex(1.0 / (1.0 + 1j * frequency / corner))


def log_axis(low: float, high: float, points: int) -> Real:
    return np.asarray(10.0 ** uneven(np.log10(low), np.log10(high), points), dtype=np.float64)


def test_a_value_between_two_samples_is_interpolated() -> None:
    time = np.array([0.0, 1.0, 4.0])
    volts = np.array([0.0, 2.0, 8.0])

    assert measure.value_at(time, volts, 2.5) == pytest.approx(5.0)
    assert measure.value_at(time, volts, 0.0) == 0.0
    assert measure.value_at(time, volts, 4.0) == 8.0


@pytest.mark.parametrize("instant", [-0.1, 4.1, float("nan")])
def test_an_instant_outside_the_waveform_has_no_value(instant: float) -> None:
    time = np.array([0.0, 1.0, 4.0])

    with pytest.raises(MeasureError, match=r"lies outside the waveform \(0 to 4\)"):
        measure.value_at(time, time, instant)


def test_a_window_starts_and_ends_on_interpolated_points() -> None:
    time = np.array([0.0, 1.0, 2.0, 4.0])
    volts = np.array([0.0, 10.0, 20.0, 40.0])

    inside_time, inside_volts = measure.window(time, volts, 0.5, 3.0)

    assert inside_time.tolist() == [0.5, 1.0, 2.0, 3.0]
    assert inside_volts.tolist() == [5.0, 10.0, 20.0, 30.0]


def test_a_window_edge_on_a_sample_does_not_repeat_the_sample() -> None:
    time = np.array([0.0, 1.0, 2.0, 4.0])
    volts = np.array([0.0, 10.0, 20.0, 40.0])

    inside_time, inside_volts = measure.window(time, volts, 1.0, 2.0)
    whole_time, whole_volts = measure.window(time, volts, 0.0, 4.0)

    assert inside_time.tolist() == [1.0, 2.0]
    assert inside_volts.tolist() == [10.0, 20.0]
    assert whole_time.tolist() == time.tolist()
    assert whole_volts.tolist() == volts.tolist()


def test_an_end_a_rounding_error_outside_the_waveform_is_taken_as_the_end() -> None:
    time = uneven(0.0, 230e-6, 50)
    volts = 3.0 * time

    inside_time, inside_volts = measure.window(time, volts, -1e-18, 230e-6 * (1.0 + 1e-12))

    assert inside_time[0] == 0.0
    assert inside_time[-1] == time[-1]
    assert inside_volts[-1] == volts[-1]
    assert measure.mean(time, volts, 0.0, 230e-6 * (1.0 + 1e-12)) == pytest.approx(1.5 * 230e-6)


@pytest.mark.parametrize(
    ("start", "stop"),
    [(-0.1, 1.0), (0.0, 4.1), (2.0, 2.0), (3.0, 1.0), (-1e-6, 1.0), (1.0, 4.00001)],
)
def test_a_window_must_lie_inside_the_waveform_and_have_a_length(start: float, stop: float) -> None:
    time = np.array([0.0, 1.0, 2.0, 4.0])

    with pytest.raises(MeasureError, match=r"does not fit the waveform \(0 to 4\)"):
        measure.window(time, time, start, stop)


def test_the_integral_of_a_ramp_is_exact_on_an_uneven_axis() -> None:
    time = uneven(0.0, 10.0, 50)
    volts = 2.0 + 3.0 * time

    area = measure.integral(time, volts, 1.3, 7.9)

    assert area == pytest.approx(2.0 * (7.9 - 1.3) + 1.5 * (7.9**2 - 1.3**2), rel=1e-12)


def test_the_integral_of_an_exponential() -> None:
    time = uneven(0.0, 10.0 * TAU, 4001)
    volts = np.exp(-time / TAU)

    area = measure.integral(time, volts, 0.0, 5.0 * TAU)

    assert area == pytest.approx(TAU * (1.0 - np.exp(-5.0)), rel=1e-6)


def test_the_mean_weighs_each_sample_by_the_time_it_stands_for() -> None:
    # Nine seconds at 1 V, then a step to 5 V for one second: four samples
    # whose plain average would be 3 V.
    time = np.array([0.0, 9.0, 9.0, 10.0])
    volts = np.array([1.0, 1.0, 5.0, 5.0])

    assert measure.mean(time, volts, 0.0, 10.0) == pytest.approx(1.4)
    assert measure.integral(time, volts, 0.0, 10.0) == pytest.approx(14.0)


def test_the_mean_of_a_sine_over_whole_periods_is_its_offset() -> None:
    time = uneven(0.0, 3.5e-3, 6001)
    volts = 0.7 + 2.0 * np.sin(2.0 * np.pi * 1e3 * time)

    assert measure.mean(time, volts, 0.25e-3, 3.25e-3) == pytest.approx(0.7, abs=1e-6)


def test_the_mean_of_an_exponential() -> None:
    time = uneven(0.0, 6.0 * TAU, 4001)
    volts = np.exp(-time / TAU)

    average = measure.mean(time, volts, TAU, 4.0 * TAU)

    assert average == pytest.approx((np.exp(-1.0) - np.exp(-4.0)) / 3.0, rel=1e-6)


def test_the_rms_of_a_sine_is_its_amplitude_over_root_two() -> None:
    time = uneven(0.0, 3.5e-3, 6001)
    wave = 2.0 * np.sin(2.0 * np.pi * 1e3 * time)

    assert measure.rms(time, wave, 0.25e-3, 3.25e-3) == pytest.approx(np.sqrt(2.0), rel=1e-6)
    assert measure.rms(time, wave + 0.7, 0.25e-3, 3.25e-3) == pytest.approx(
        np.sqrt(0.7**2 + 2.0), rel=1e-6
    )


def test_the_rms_of_a_ramp_from_zero_is_its_end_over_root_three() -> None:
    time = uneven(0.0, 2.0, 4001)
    volts = 5.0 * time

    assert measure.rms(time, volts, 0.0, 2.0) == pytest.approx(10.0 / np.sqrt(3.0), rel=1e-6)


def test_the_extremes_of_a_damped_sine() -> None:
    decay, omega = 400.0, 2.0 * np.pi * 1e3
    crest = float(np.arctan(omega / decay) / omega)
    trough = crest + float(np.pi / omega)
    time = with_points(uneven(0.0, 4e-3, 4001), crest, trough)
    volts = np.exp(-decay * time) * np.sin(omega * time)
    height = omega / np.hypot(decay, omega)

    low, high = measure.extremes(time, volts, 0.0, 4e-3)

    assert high == pytest.approx(np.exp(-decay * crest) * height, rel=1e-12)
    assert low == pytest.approx(-np.exp(-decay * trough) * height, rel=1e-12)
    assert measure.peak_to_peak(time, volts, 0.0, 4e-3) == pytest.approx(high - low, rel=1e-12)
    # After the first trough the largest swing is the second crest.
    later_low, later_high = measure.extremes(time, volts, trough, 4e-3)
    assert later_low == pytest.approx(low, rel=1e-12)
    assert later_high == pytest.approx(np.exp(-decay * (crest + 1e-3)) * height, rel=1e-5)


def test_the_extremes_count_the_interpolated_ends_of_the_window() -> None:
    time = np.arange(11.0)

    assert measure.extremes(time, time, 2.5, 7.25) == (2.5, 7.25)
    assert measure.peak_to_peak(time, time, 2.5, 7.25) == pytest.approx(4.75)


def test_the_crossings_of_a_triangle_are_exact_on_an_uneven_axis() -> None:
    time = with_points(uneven(0.0, 6.0, 40), 1.0, 2.0, 3.0, 4.0, 5.0)
    wave = triangle(time)

    upward = measure.crossings(time, wave, 0.25, rising=True)
    downward = measure.crossings(time, wave, 0.25, rising=False)
    both = measure.crossings(time, wave, 0.25)

    assert upward == pytest.approx([0.25, 2.25, 4.25], abs=1e-12)
    assert downward == pytest.approx([1.75, 3.75, 5.75], abs=1e-12)
    assert both == pytest.approx([0.25, 1.75, 2.25, 3.75, 4.25, 5.75], abs=1e-12)


def test_the_crossings_of_a_sine() -> None:
    time = uneven(0.0, 3e-3, 6001)
    omega = 2.0 * np.pi * 1e3
    wave = 2.0 * np.sin(omega * time)
    angle = np.arcsin(0.5 / 2.0)

    upward = measure.crossings(time, wave, 0.5, rising=True)
    downward = measure.crossings(time, wave, 0.5, rising=False)

    assert upward == pytest.approx(
        [(angle + 2.0 * np.pi * turn) / omega for turn in range(3)], abs=2e-10
    )
    assert downward == pytest.approx(
        [(np.pi - angle + 2.0 * np.pi * turn) / omega for turn in range(3)], abs=2e-10
    )


def test_a_waveform_that_stays_on_one_side_of_the_level_has_no_crossing() -> None:
    time = uneven(0.0, 6.0, 40)

    found = measure.crossings(time, triangle(time), 1.5)

    assert found.size == 0
    assert found.dtype == np.float64


def test_a_sample_on_the_level_counts_as_above_it() -> None:
    time = np.array([0.0, 1.0, 2.0])

    # Reached from below, the level is crossed upward and downward at once ...
    assert measure.crossings(time, np.array([0.0, 1.0, 0.0]), 1.0).tolist() == [1.0, 1.0]
    # ... and reached from above it is not crossed at all.
    assert measure.crossings(time, np.array([2.0, 1.0, 2.0]), 1.0).size == 0
    assert measure.crossings(time, np.array([1.0, 1.0, 0.0]), 1.0, rising=False).tolist() == [1.0]


def test_a_vertical_edge_is_crossed_at_its_instant() -> None:
    time = np.array([0.0, 1.0, 1.0, 2.0])
    volts = np.array([0.0, 0.0, 5.0, 5.0])

    assert measure.crossings(time, volts, 2.5).tolist() == [1.0]
    assert measure.first_crossing(time, volts, 2.5, rising=True) == 1.0


def test_the_first_crossing_after_an_instant() -> None:
    time = with_points(uneven(0.0, 6.0, 40), 1.0, 2.0, 3.0, 4.0, 5.0)
    wave = triangle(time)

    assert measure.first_crossing(time, wave, 0.25) == pytest.approx(0.25, abs=1e-12)
    assert measure.first_crossing(time, wave, 0.25, after=1.0) == pytest.approx(1.75, abs=1e-12)
    assert measure.first_crossing(time, wave, 0.25, rising=True, after=1.0) == pytest.approx(
        2.25, abs=1e-12
    )
    assert measure.first_crossing(time, wave, 0.25, rising=False, after=4.0) == pytest.approx(
        5.75, abs=1e-12
    )


def test_a_level_that_is_not_crossed_after_the_instant_is_an_error() -> None:
    time = with_points(uneven(0.0, 6.0, 40), 1.0, 2.0, 3.0, 4.0, 5.0)
    wave = triangle(time)

    with pytest.raises(MeasureError, match=r"does not cross 0\.25 after 5\.8"):
        measure.first_crossing(time, wave, 0.25, after=5.8)
    with pytest.raises(MeasureError, match=r"does not cross 1\.5 after -inf"):
        measure.first_crossing(time, wave, 1.5)


@pytest.mark.parametrize("start", [0.0, 2.5])
def test_the_settling_time_of_an_exponential(start: float) -> None:
    # A step from 0 V to 1.2 V with a time constant of 1 ms is within 1 % of
    # its end after ln(100) time constants.
    time = with_points(uneven(0.0, 12.0 * TAU, 6001), 2.0 * TAU)
    event = 2.0 * TAU
    volts = np.where(time < event, start, 1.2 + (start - 1.2) * np.exp(-(time - event) / TAU))

    settled = measure.settling_time(time, volts, final=1.2, band=0.012, after=event)

    assert settled == pytest.approx(TAU * np.log(abs(start - 1.2) / 0.012), rel=1e-5)


def test_the_settling_time_of_a_two_pole_step_is_its_last_way_into_the_band() -> None:
    damping, omega, band = 0.2, 2.0 * np.pi * 1e3, 0.05
    time = uneven(0.0, 8e-3, 20001)
    volts = two_pole_step(time, damping, omega)
    # The swings shrink by 0.527 each: the fourth is 7.7 % and the fifth 4.1 %,
    # so the band is entered for good between the fourth swing and the next
    # passage through the final value. The instant is found by halving.
    root = float(np.sqrt(1.0 - damping**2))
    outside = 4.0 * np.pi / (omega * root)
    inside = (5.0 * np.pi - np.arccos(damping)) / (omega * root)
    for _ in range(80):
        middle = 0.5 * (outside + inside)
        swing = abs(float(two_pole_step(np.array([middle]), damping, omega)[0]) - 1.0)
        outside, inside = (middle, inside) if swing > band else (outside, middle)

    settled = measure.settling_time(time, volts, final=1.0, band=band, after=0.0)

    assert 4.0 * np.pi / (omega * root) < inside < 5.0 * np.pi / (omega * root)
    assert settled == pytest.approx(inside, rel=1e-6)


def test_a_waveform_that_never_leaves_the_band_has_settled_at_once() -> None:
    time = uneven(0.0, 6.0, 40)

    assert measure.settling_time(time, 2.0 + 0.01 * triangle(time), 2.0, 0.02, after=1.0) == 0.0


def test_a_waveform_outside_the_band_at_its_end_has_not_settled() -> None:
    time = uneven(0.0, 3.0 * TAU, 400)
    volts = 1.0 - np.exp(-time / TAU)

    with pytest.raises(MeasureError, match=r"has not settled to 1 within 0\.01 at its end"):
        measure.settling_time(time, volts, final=1.0, band=0.01, after=0.0)


def test_the_part_after_the_end_asked_for_does_not_count() -> None:
    # Settled within a millivolt after 3 s, disturbed again at 6 s.
    time = np.array([0.0, 1.0, 4.0, 6.0, 6.0, 8.0, 9.0])
    volts = np.array([0.0, 0.0, 3.0, 3.0, 4.0, 3.0, 3.0])

    first = measure.settling_time(time, volts, final=3.0, band=0.001, after=1.0, until=5.0)
    whole = measure.settling_time(time, volts, final=3.0, band=0.001, after=1.0)

    assert first == pytest.approx(2.999)
    assert whole == pytest.approx(6.998)
    with pytest.raises(MeasureError, match="has not settled"):
        measure.settling_time(time, volts, final=3.0, band=0.001, after=1.0, until=7.0)


def test_the_overshoot_of_a_two_pole_step() -> None:
    damping, omega = 0.2, 2.0 * np.pi * 1e3
    crest, beyond = first_peak(damping, omega)
    time = with_points(uneven(0.0, 8e-3, 4001), crest)
    rising = 1.0 + two_pole_step(time, damping, omega)
    falling = 2.0 - two_pole_step(time, damping, omega)

    assert beyond == pytest.approx(0.5266, abs=1e-4)
    assert measure.overshoot(time, rising, 1.0, 2.0, after=0.0) == pytest.approx(beyond, rel=1e-12)
    assert measure.overshoot(time, falling, 2.0, 1.0, after=0.0) == pytest.approx(beyond, rel=1e-12)
    assert measure.overshoot(time, 3.0 * rising, 3.0, 6.0, after=0.0) == pytest.approx(
        beyond, rel=1e-12
    )


def test_the_overshoot_is_looked_for_between_two_instants() -> None:
    # A step from 1 V to 2 V that peaks at 2.2 V.
    time = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    volts = np.array([1.0, 1.0, 2.2, 1.9, 2.0])

    assert measure.overshoot(time, volts, 1.0, 2.0, after=0.0) == pytest.approx(0.2)
    assert measure.overshoot(time, volts, 1.0, 2.0, after=0.0, until=1.75) == pytest.approx(0.0)
    assert measure.overshoot(time, volts, 1.0, 2.0, after=0.0, until=1.875) == pytest.approx(0.05)
    assert measure.overshoot(time, volts, 1.0, 2.0, after=2.5) == pytest.approx(0.05)


def test_a_step_that_never_passes_its_final_value_has_no_overshoot() -> None:
    time = uneven(0.0, 8.0 * TAU, 400)

    assert measure.overshoot(time, 1.0 - np.exp(-time / TAU), 0.0, 1.0, after=0.0) == 0.0
    assert measure.overshoot(time, np.exp(-time / TAU), 1.0, 0.0, after=0.0) == 0.0


def test_a_step_without_height_has_no_overshoot() -> None:
    time = uneven(0.0, 1.0, 10)

    with pytest.raises(MeasureError, match="a step without height has no overshoot"):
        measure.overshoot(time, time, 2.0, 2.0, after=0.0)


def test_the_rise_time_of_an_exponential_is_its_time_constant_times_the_logarithm_of_nine() -> None:
    time = uneven(0.0, 10.0 * TAU, 6001)
    rising = 1.0 - np.exp(-time / TAU)
    falling = np.exp(-time / TAU)

    assert measure.rise_time(time, rising, 0.1, 0.9) == pytest.approx(TAU * np.log(9.0), rel=1e-6)
    assert measure.rise_time(time, falling, 0.1, 0.9) == pytest.approx(TAU * np.log(9.0), rel=1e-6)
    assert measure.rise_time(time, 3.3 * rising, 0.33, 2.97) == pytest.approx(
        TAU * np.log(9.0), rel=1e-6
    )


def test_the_rise_time_of_a_ramp_is_exact_on_an_uneven_axis() -> None:
    # 0 V until 1 s, 1 V from 3 s on, and back between 5 s and 9 s.
    time = with_points(uneven(0.0, 10.0, 60), 1.0, 3.0, 5.0, 9.0)
    volts = np.interp(time, [0.0, 1.0, 3.0, 5.0, 9.0, 10.0], [0.0, 0.0, 1.0, 1.0, 0.0, 0.0])

    assert measure.rise_time(time, volts, 0.1, 0.9) == pytest.approx(1.6, rel=1e-12)
    assert measure.rise_time(time, volts, 0.1, 0.9, after=4.0) == pytest.approx(3.2, rel=1e-12)
    assert measure.rise_time(time, volts, 0.2, 0.6, after=4.0) == pytest.approx(1.6, rel=1e-12)


def test_a_level_that_an_edge_does_not_reach_is_an_error() -> None:
    time = uneven(0.0, 10.0 * TAU, 400)
    volts = 0.8 * (1.0 - np.exp(-time / TAU))

    with pytest.raises(MeasureError, match=r"does not cross 0\.9"):
        measure.rise_time(time, volts, 0.1, 0.9)
    # Past the edge the waveform is above both levels: it counts as an edge
    # that falls, and it does not come down again.
    with pytest.raises(MeasureError, match=r"does not cross 0\.7 after 0\.005"):
        measure.rise_time(time, volts, 0.1, 0.7, after=5.0 * TAU)


def test_decibels_of_a_magnitude() -> None:
    levels = measure.decibels(np.array([1.0, 10.0, 0.1, -100.0]))
    complex_levels = measure.decibels(np.array([3.0 + 4.0j, -1.0j]))

    assert levels == pytest.approx([0.0, 20.0, -20.0, 40.0])
    assert complex_levels == pytest.approx([20.0 * np.log10(5.0), 0.0])
    assert levels.dtype == np.float64


def test_the_phase_of_a_delay_falls_in_a_straight_line_without_jumps() -> None:
    frequency = uneven(10.0, 5e3, 400)
    delay = 1e-3

    phase = measure.phase_degrees(np.exp(-2j * np.pi * frequency * delay))

    assert phase == pytest.approx(-360.0 * frequency * delay, abs=1e-9)
    assert phase[-1] == pytest.approx(-1800.0)


def test_the_corner_of_one_pole() -> None:
    corner = 1591.5
    frequency = log_axis(corner / 100.0, corner * 100.0, 2001)
    response = one_pole(frequency, corner)
    start = (frequency[0] / corner) ** 2

    half_power = measure.corner_frequency(frequency, response, drop_db=HALF_POWER)
    three_db = measure.corner_frequency(frequency, response)
    twenty_db = measure.corner_frequency(frequency, np.abs(response), drop_db=20.0)

    # The fall is counted from the first point, which is not quite at 0 dB.
    # Between two samples the response is taken as a straight line in
    # decibels over the logarithm of the frequency, which it is not quite.
    assert half_power == pytest.approx(corner * np.sqrt(2.0 * (1.0 + start) - 1.0), rel=2e-5)
    assert three_db == pytest.approx(corner * np.sqrt(10.0**0.3 * (1.0 + start) - 1.0), rel=2e-5)
    assert twenty_db == pytest.approx(corner * np.sqrt(100.0 * (1.0 + start) - 1.0), rel=2e-5)
    assert three_db < half_power < corner * 1.0001


def test_the_corner_of_two_equal_poles() -> None:
    corner = 250e3
    frequency = log_axis(corner / 1000.0, corner * 10.0, 2001)
    response = one_pole(frequency, corner) ** 2
    start = (frequency[0] / corner) ** 2

    found = measure.corner_frequency(frequency, response, drop_db=HALF_POWER)

    assert found == pytest.approx(corner * np.sqrt(np.sqrt(2.0) * (1.0 + start) - 1.0), rel=2e-5)
    assert found == pytest.approx(0.6436 * corner, rel=1e-4)


def test_a_response_that_never_falls_that_far_has_no_corner() -> None:
    frequency = log_axis(10.0, 1e3, 200)

    with pytest.raises(MeasureError, match="does not cross"):
        measure.corner_frequency(frequency, one_pole(frequency, 1e4))


def test_the_peaking_of_two_complex_poles() -> None:
    quality, resonance = 5.0, 40e3
    crest = resonance * np.sqrt(1.0 - 1.0 / (2.0 * quality**2))
    frequency = with_points(log_axis(resonance / 1000.0, resonance * 10.0, 801), float(crest))
    ratio = frequency / resonance
    response = 1.0 / (1.0 - ratio**2 + 1j * ratio / quality)
    height = quality / np.sqrt(1.0 - 1.0 / (4.0 * quality**2))

    peaking = measure.peaking_db(response)

    assert peaking == pytest.approx(20.0 * np.log10(height / abs(response[0])), rel=1e-12)
    assert peaking == pytest.approx(14.02, abs=0.01)
    assert measure.peaking_db(np.abs(response)) == pytest.approx(peaking, rel=1e-12)


def test_a_response_that_only_falls_has_no_peaking() -> None:
    frequency = log_axis(10.0, 1e6, 200)

    assert measure.peaking_db(one_pole(frequency, 1e3)) == 0.0


def test_the_loop_gain_does_not_depend_on_the_impedances_at_the_injection_point() -> None:
    frequency = log_axis(10.0, 1e7, 300)
    loop = 1e5 * one_pole(frequency, 100.0) * one_pole(frequency, 2e6)
    for impedance_ratio in (
        np.full(frequency.shape, 1e-6 + 0j),
        np.full(frequency.shape, 3.0 + 0j),
        (50.0 + 2j * np.pi * frequency * 1e-6) * (1e-4 + 2j * np.pi * frequency * 1e-10),
    ):
        # What the two injections read at a point where the driving side has
        # an impedance of that ratio to the impedance it drives.
        voltage_ratio = as_complex(loop * (1.0 + impedance_ratio) + impedance_ratio)
        current_ratio = as_complex(loop * (1.0 + 1.0 / impedance_ratio) + 1.0 / impedance_ratio)

        found = measure.loop_gain(voltage_ratio, current_ratio)

        assert found == pytest.approx(loop, rel=1e-9)
        assert found.dtype == np.complex128


def injections(gain: complex, source: complex, load: complex) -> tuple[complex, complex]:
    """The two ratios read at the point between a stage and its load, at one frequency.

    The stage is a source of minus ``gain`` times the voltage on the load
    behind the impedance ``source``: the side that drives the point. The
    impedance ``load`` to ground is the side that receives. The two circuits
    are solved from their equations, as a simulator solves them.
    """
    # A source of 1 V in series between the driving side, at v_x, and the
    # receiving side, at v_y; the current i flows from the one into the other.
    #   v_y - v_x = 1                 the injected voltage
    #   v_x + gain v_y + source i = 0 the stage behind its impedance
    #   v_y - load i = 0              the load
    series = np.array([[-1.0, 1.0, 0.0], [1.0, gain, source], [0.0, 1.0, -load]], dtype=complex)
    v_x, v_y, _ = np.linalg.solve(series, np.array([1.0, 0.0, 0.0], dtype=complex))
    # A source of 1 A from ground into the point, at v; the stage delivers
    # i_x into the point, and i_y flows on into the load.
    #   i_x + 1 = i_y                      what enters the point leaves it
    #   (1 + gain) v + source i_x = 0      the stage behind its impedance
    #   v - load i_y = 0                   the load
    shunt = np.array(
        [[0.0, 1.0, -1.0], [1.0 + gain, source, 0.0], [1.0, 0.0, -load]], dtype=complex
    )
    _, i_x, i_y = np.linalg.solve(shunt, np.array([-1.0, 0.0, 0.0], dtype=complex))
    return complex(-v_x / v_y), complex(-i_x / i_y)


def test_the_loop_gain_of_a_stage_and_its_load_is_found_from_the_two_injections() -> None:
    # An amplifier of gain A with 30 ohm and 20 uH behind it drives 2 kohm
    # beside 100 nF and takes the voltage on that load back, inverted. Around
    # the loop the gain is A times the divider of the two impedances.
    frequency = log_axis(1.0, 1e7, 240)
    omega = 2j * np.pi * frequency
    gain = 2e5 * one_pole(frequency, 5.0) * one_pole(frequency, 3e6)
    source = as_complex(30.0 + omega * 20e-6)
    load = as_complex(1.0 / (1.0 / 2e3 + omega * 100e-9))
    expected = as_complex(gain * load / (source + load))

    ratios = [injections(*point) for point in zip(gain, source, load, strict=True)]
    voltage_ratio = as_complex([voltage for voltage, _ in ratios])
    current_ratio = as_complex([current for _, current in ratios])
    found = measure.loop_gain(voltage_ratio, current_ratio)

    assert found == pytest.approx(expected, rel=1e-8)
    # With negative feedback the loop gain is a positive number at low frequency.
    assert found[0].real > 1.5e5
    assert abs(float(measure.phase_degrees(found)[0])) < 15.0
    # Neither injection alone gives it: the first reads A plus the ratio of
    # the impedances, the second (1 + A) over that ratio.
    assert voltage_ratio == pytest.approx(gain + source / load, rel=1e-8)
    assert current_ratio == pytest.approx((1.0 + gain) * load / source, rel=1e-8)
    assert abs(voltage_ratio[-1] / expected[-1]) > 100.0


def test_the_two_ratios_of_a_loop_gain_are_the_driving_side_over_the_receiving_side() -> None:
    # Taken the other way around, as the receiving side over the driving
    # side, the ratios give a number that is not the loop gain.
    voltage_ratio, current_ratio = injections(gain=1000.0, source=50.0, load=150.0)
    forward = as_complex([voltage_ratio])
    current = as_complex([current_ratio])

    right = measure.loop_gain(forward, current)
    upside_down = measure.loop_gain(as_complex(1.0 / forward), as_complex(1.0 / current))

    assert right == pytest.approx([1000.0 * 150.0 / 200.0], rel=1e-9)
    assert abs(upside_down[0]) < 1.0


def test_the_margin_of_an_integrator_with_one_more_pole() -> None:
    # With the unity-gain frequency of the integrator at root two times the
    # pole, the gain is 1 exactly at the pole, where the pole has turned the
    # phase by 45 degrees: the margin is 45 degrees.
    pole = 120e3
    frequency = log_axis(pole / 1000.0, pole * 100.0, 4001)
    loop = as_complex(np.sqrt(2.0) * pole / (1j * frequency) * one_pole(frequency, pole))

    crossover, margin = measure.stability_margins(frequency, loop)

    assert crossover == pytest.approx(pole, rel=1e-6)
    assert margin == pytest.approx(45.0, abs=1e-4)


@pytest.mark.parametrize(("start", "phase_there"), [(1.0, -0.6), (1e4, -100.7)])
def test_the_margin_of_two_poles(start: float, phase_there: float) -> None:
    # The margin does not depend on where the axis starts: on the flat part
    # below the first pole, or above it, where the loop has turned by more
    # than a quarter and the phase alone no longer shows the sign of the loop.
    gain, first, second = 1000.0, 100.0, 50e3
    frequency = log_axis(start, 1e7, 4001)
    loop = as_complex(gain * one_pole(frequency, first) * one_pole(frequency, second))
    assert measure.phase_degrees(loop)[0] == pytest.approx(phase_there, abs=0.1)
    # The gain is 1 where (1 + f2/first2)(1 + f2/second2) = gain2: a quadratic in f2.
    lead = 1.0 / (first * second) ** 2
    middle = 1.0 / first**2 + 1.0 / second**2
    square = (-middle + np.sqrt(middle**2 + 4.0 * lead * (gain**2 - 1.0))) / (2.0 * lead)
    expected = float(np.sqrt(square))

    crossover, margin = measure.stability_margins(frequency, loop)

    assert crossover == pytest.approx(expected, rel=1e-6)
    assert margin == pytest.approx(
        180.0 - np.degrees(np.arctan(expected / first) + np.arctan(expected / second)), abs=1e-4
    )
    assert 38.0 < margin < 39.0


def test_a_delay_can_take_the_phase_past_half_a_turn_before_the_crossover() -> None:
    # An integrator with a delay: the gain is 1 at the unity-gain frequency
    # whatever the delay is, and the delay takes 110 degrees there.
    unity = 20e3
    delay = 110.0 / (360.0 * unity)
    frequency = log_axis(unity / 1000.0, unity * 3.0, 4001)
    loop = as_complex(unity / (1j * frequency) * np.exp(-2j * np.pi * frequency * delay))

    crossover, margin = measure.stability_margins(frequency, loop)

    assert crossover == pytest.approx(unity, rel=1e-9)
    assert margin == pytest.approx(-20.0, abs=1e-4)


def test_a_loop_that_never_falls_through_one_has_no_margin() -> None:
    frequency = log_axis(1.0, 1e3, 200)

    with pytest.raises(MeasureError, match="does not cross 0"):
        measure.stability_margins(frequency, 1000.0 * one_pole(frequency, 100.0))


def test_white_noise_grows_with_the_root_of_the_band() -> None:
    frequency = uneven(1.0, 1e5, 300)
    density = np.full(frequency.shape, 4.07e-9)

    noise = measure.integrated_noise(frequency, density, 10.0, 80e3)

    assert noise == pytest.approx(4.07e-9 * np.sqrt(80e3 - 10.0), rel=1e-12)


def test_flicker_noise_grows_with_the_logarithm_of_the_band() -> None:
    frequency = log_axis(0.1, 1e3, 4001)
    density = 50e-9 / np.sqrt(frequency)

    noise = measure.integrated_noise(frequency, density, 0.1, 10.0)

    assert noise == pytest.approx(50e-9 * np.sqrt(np.log(100.0)), rel=1e-6)


def test_the_noise_behind_one_pole() -> None:
    corner = 1e3
    frequency = log_axis(0.01, 1e7, 8001)
    density = 10e-9 * np.abs(one_pole(frequency, corner))

    band = measure.integrated_noise(frequency, density, 100.0, 5e3)
    whole = measure.integrated_noise(frequency, density, 0.01, 1e7)

    assert band == pytest.approx(
        10e-9 * np.sqrt(corner * (np.arctan(5.0) - np.arctan(0.1))), rel=1e-6
    )
    # Over the whole axis the band of the noise is pi / 2 times the corner.
    assert whole == pytest.approx(10e-9 * np.sqrt(0.5 * np.pi * corner), rel=1e-3)


FIGURES: dict[str, Callable[[Real, Real], object]] = {
    "value_at": lambda x, y: measure.value_at(x, y, 1.5),
    "window": lambda x, y: measure.window(x, y, 1.2, 1.8),
    "integral": lambda x, y: measure.integral(x, y, 1.2, 1.8),
    "mean": lambda x, y: measure.mean(x, y, 1.2, 1.8),
    "rms": lambda x, y: measure.rms(x, y, 1.2, 1.8),
    "extremes": lambda x, y: measure.extremes(x, y, 1.2, 1.8),
    "peak_to_peak": lambda x, y: measure.peak_to_peak(x, y, 1.2, 1.8),
    "crossings": lambda x, y: measure.crossings(x, y, 1.5),
    "first_crossing": lambda x, y: measure.first_crossing(x, y, 1.5),
    "settling_time": lambda x, y: measure.settling_time(x, y, 2.0, 0.1, after=1.2),
    "settling_time with an end": lambda x, y: measure.settling_time(x, y, 2.0, 0.1, 1.2, 1.8),
    "overshoot": lambda x, y: measure.overshoot(x, y, 1.0, 2.0, after=1.2),
    "overshoot with an end": lambda x, y: measure.overshoot(x, y, 1.0, 2.0, 1.2, 1.8),
    "rise_time": lambda x, y: measure.rise_time(x, y, 1.2, 1.8),
    "corner_frequency": lambda x, y: measure.corner_frequency(x, y),
    "stability_margins": lambda x, y: measure.stability_margins(x, y.astype(np.complex128)),
    "integrated_noise": lambda x, y: measure.integrated_noise(x, y, 1.2, 1.8),
}

MALFORMED = "two arrays of the same length with two points or more"
BAD_AXES: dict[str, tuple[Real, Real, str]] = {
    "of different lengths": (np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0]), MALFORMED),
    "with one point": (np.array([1.0]), np.array([2.0]), MALFORMED),
    "without a point": (np.array([]), np.array([]), MALFORMED),
    "with two dimensions": (
        np.array([[1.0, 2.0], [3.0, 4.0]]),
        np.array([[1.0, 2.0], [3.0, 4.0]]),
        MALFORMED,
    ),
    "running backward": (
        np.array([1.0, 3.0, 2.0]),
        np.array([1.0, 2.0, 3.0]),
        "must not run backward",
    ),
}


@pytest.mark.parametrize("figure", FIGURES.values(), ids=FIGURES)
@pytest.mark.parametrize("axes", BAD_AXES.values(), ids=BAD_AXES)
def test_every_figure_refuses_axes_it_cannot_work_on(
    figure: Callable[[Real, Real], object], axes: tuple[Real, Real, str]
) -> None:
    x, y, reason = axes

    with pytest.raises(MeasureError, match=reason):
        figure(x, y)


@pytest.mark.parametrize("response", [np.array([]), np.array([[1.0, 2.0], [3.0, 4.0]])])
def test_the_peaking_of_a_response_without_an_axis_is_refused(response: Real) -> None:
    with pytest.raises(MeasureError, match="a response needs one array with one point or more"):
        measure.peaking_db(response)


def test_an_axis_may_stand_still() -> None:
    # Two samples at one instant are a vertical edge, not an axis running backward.
    time = np.array([0.0, 1.0, 1.0, 2.0])
    volts = np.array([0.0, 0.0, 4.0, 4.0])

    assert measure.integral(time, volts, 0.0, 2.0) == pytest.approx(4.0)
    assert measure.extremes(time, volts, 0.5, 1.5) == (0.0, 4.0)


def test_the_error_of_a_figure_can_be_caught_under_the_name_of_the_module() -> None:
    time = np.array([0.0, 1.0, 2.0])

    assert measure.MeasureError is MeasureError
    with pytest.raises(measure.MeasureError, match="does not cross 5"):
        measure.first_crossing(time, time, 5.0)
