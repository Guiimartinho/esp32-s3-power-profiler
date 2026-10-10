"""Figures taken from waveforms.

Every function here is pure: it takes the samples of a run as arrays and
returns a number. The time axis of a transient analysis is not evenly
spaced, so means, integrals and crossings interpolate between the samples
and weigh them by the time they stand for.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# The error of this module is part of what it offers: a bench that asks
# for a figure can catch it as measure.MeasureError.
from circuit_sim.errors import MeasureError as MeasureError

Real = NDArray[np.float64]
Complex = NDArray[np.complex128]


def _check(x: Real, y: Real) -> None:
    """Refuse axes that the functions below cannot work on."""
    if x.ndim != 1 or x.shape != y.shape or x.size < 2:
        raise MeasureError("a waveform needs two arrays of the same length with two points or more")
    if np.any(np.diff(x) < 0.0):
        raise MeasureError("the axis of a waveform must not run backward")


def value_at(x: Real, y: Real, at: float) -> float:
    """The value of a waveform at one instant, interpolated between samples.

    Raises:
        MeasureError: When the instant lies outside the waveform.
    """
    _check(x, y)
    if not x[0] <= at <= x[-1]:
        raise MeasureError(f"{at:g} lies outside the waveform ({x[0]:g} to {x[-1]:g})")
    return float(np.interp(at, x, y))


def window(x: Real, y: Real, start: float, stop: float) -> tuple[Real, Real]:
    """The part of a waveform between two instants, with interpolated ends.

    Raises:
        MeasureError: When the window is empty or leaves the waveform.
    """
    _check(x, y)
    # A simulator ends a run a rounding error before or after the time asked.
    slack = 1e-9 * float(x[-1] - x[0])
    if start < x[0] - slack or stop > x[-1] + slack or not start < stop:
        raise MeasureError(
            f"the window {start:g} to {stop:g} does not fit the waveform ({x[0]:g} to {x[-1]:g})"
        )
    start, stop = max(start, float(x[0])), min(stop, float(x[-1]))
    inside = (x > start) & (x < stop)
    xs = np.concatenate(([start], x[inside], [stop]))
    ys = np.concatenate(([np.interp(start, x, y)], y[inside], [np.interp(stop, x, y)]))
    return xs, ys


def integral(x: Real, y: Real, start: float, stop: float) -> float:
    """The integral of a waveform between two instants (trapezoids)."""
    xs, ys = window(x, y, start, stop)
    return float(np.sum(0.5 * (ys[1:] + ys[:-1]) * np.diff(xs)))


def mean(x: Real, y: Real, start: float, stop: float) -> float:
    """The mean of a waveform between two instants, weighted by time."""
    return integral(x, y, start, stop) / (stop - start)


def rms(x: Real, y: Real, start: float, stop: float) -> float:
    """The root mean square of a waveform between two instants."""
    xs, ys = window(x, y, start, stop)
    squares = ys * ys
    return float(np.sqrt(np.sum(0.5 * (squares[1:] + squares[:-1]) * np.diff(xs)) / (stop - start)))


def extremes(x: Real, y: Real, start: float, stop: float) -> tuple[float, float]:
    """The lowest and the highest value of a waveform between two instants."""
    _, ys = window(x, y, start, stop)
    return float(np.min(ys)), float(np.max(ys))


def peak_to_peak(x: Real, y: Real, start: float, stop: float) -> float:
    """The span between the lowest and the highest value in a window."""
    low, high = extremes(x, y, start, stop)
    return high - low


def crossings(x: Real, y: Real, level: float, rising: bool | None = None) -> Real:
    """The instants at which a waveform crosses a level, interpolated.

    Args:
        x: The axis.
        y: The waveform.
        level: The level to cross.
        rising: True for upward crossings only, False for downward ones,
            None for both.
    """
    _check(x, y)
    below = y < level
    change = np.flatnonzero(below[1:] != below[:-1])
    if rising is not None:
        change = change[below[change] == rising]
    x0, x1, y0, y1 = x[change], x[change + 1], y[change], y[change + 1]
    return np.asarray(x0 + (level - y0) * (x1 - x0) / (y1 - y0), dtype=np.float64)


def first_crossing(
    x: Real, y: Real, level: float, rising: bool | None = None, after: float = -np.inf
) -> float:
    """The first instant after a given one at which a waveform crosses a level.

    Raises:
        MeasureError: When the waveform never crosses the level there.
    """
    found = crossings(x, y, level, rising)
    found = found[found >= after]
    if found.size == 0:
        raise MeasureError(f"the waveform does not cross {level:g} after {after:g}")
    return float(found[0])


def settling_time(
    x: Real, y: Real, final: float, band: float, after: float, until: float | None = None
) -> float:
    """The time a waveform needs to stay within a band around its final value.

    Args:
        x: The axis.
        y: The waveform.
        final: The value the waveform settles to.
        band: Half the width of the band around it.
        after: The instant of the event that the time counts from.
        until: The end of the part that is looked at; the end of the
            waveform when left out.

    Returns:
        The time from the event to the last instant at which the waveform is
        outside the band; 0 when it never leaves it.

    Raises:
        MeasureError: When the waveform is still outside the band at the end.
    """
    _check(x, y)
    xs, ys = window(x, y, after, float(x[-1]) if until is None else until)
    outside = np.abs(ys - final) > band
    if not np.any(outside):
        return 0.0
    if outside[-1]:
        raise MeasureError(f"the waveform has not settled to {final:g} within {band:g} at its end")
    last = int(np.flatnonzero(outside)[-1])
    # The band is entered between the last sample outside and the next one.
    edge = final + band if ys[last] > final else final - band
    x0, x1, y0, y1 = xs[last], xs[last + 1], ys[last], ys[last + 1]
    entered = x0 + (edge - y0) * (x1 - x0) / (y1 - y0)
    return float(entered - after)


def overshoot(
    x: Real, y: Real, initial: float, final: float, after: float, until: float | None = None
) -> float:
    """How far a step passes its final value, as a fraction of the step.

    A step from 1 V to 2 V that peaks at 2.2 V has an overshoot of 0.2. A
    waveform that never passes the final value gives 0. The waveform is
    looked at from ``after`` to ``until``, or to its end.

    Raises:
        MeasureError: When the step has no height.
    """
    step = final - initial
    if step == 0.0:
        raise MeasureError("a step without height has no overshoot")
    _check(x, y)
    low, high = extremes(x, y, after, float(x[-1]) if until is None else until)
    beyond = high - final if step > 0.0 else final - low
    return max(0.0, beyond / abs(step))


def rise_time(x: Real, y: Real, low: float, high: float, after: float = -np.inf) -> float:
    """The time between the crossings of two levels, in either direction.

    For a rising edge the waveform crosses ``low`` and then ``high``; for a
    falling edge the other way around. The result is positive in both cases.

    Raises:
        MeasureError: When one of the levels is not crossed.
    """
    _check(x, y)
    rising = float(np.interp(max(after, float(x[0])), x, y)) < 0.5 * (low + high)
    first, second = (low, high) if rising else (high, low)
    start = first_crossing(x, y, first, rising, after)
    return first_crossing(x, y, second, rising, start) - start


def decibels(values: Real | Complex) -> Real:
    """The magnitude of a transfer function in decibels."""
    return np.asarray(20.0 * np.log10(np.abs(values)), dtype=np.float64)


def phase_degrees(values: Complex) -> Real:
    """The phase of a transfer function in degrees, without jumps of 360."""
    return np.asarray(np.degrees(np.unwrap(np.angle(values))), dtype=np.float64)


def corner_frequency(frequency: Real, response: Real | Complex, drop_db: float = 3.0) -> float:
    """The frequency at which a response has fallen below its first point.

    Args:
        frequency: The axis, rising.
        response: The transfer function along it.
        drop_db: The fall, in decibels, that marks the corner.

    Raises:
        MeasureError: When the response never falls that far.
    """
    level = decibels(response)
    _check(frequency, level)
    target = float(level[0]) - drop_db
    # Interpolate on a logarithmic axis, on which a roll-off is a straight line.
    return float(10.0 ** first_crossing(np.log10(frequency), level, target, rising=False))


def peaking_db(response: Real | Complex) -> float:
    """How far a response rises above its first point, in decibels.

    Raises:
        MeasureError: When the response is not one array with a point in it.
    """
    level = decibels(response)
    if level.ndim != 1 or level.size == 0:
        raise MeasureError("a response needs one array with one point or more")
    return float(np.max(level) - level[0])


def loop_gain(voltage_ratio: Complex, current_ratio: Complex) -> Complex:
    """The loop gain of a feedback loop from two injections at one point.

    The loop is cut nowhere. At one point of it two sides meet: the side that
    drives the point (the output of a stage, with its source impedance) and
    the side that receives the signal there (the input of what follows, with
    its load impedance). Two runs are made at that point, and each gives a
    ratio of the driving side over the receiving side, with a minus sign.
    Taken the other way around, the ratios do not give the loop gain.

    Args:
        voltage_ratio: From the run with a voltage source in series between
            the two sides: minus the voltage of the driving side over the
            voltage of the receiving side, ``-v(driving) / v(receiving)``,
            both against ground.
        current_ratio: From the run with a current source from ground into
            the point: minus the current of the driving side over the
            current of the receiving side, ``-i(driving) / i(receiving)``.
            Both currents are counted the way the signal goes: the current
            that the driving side delivers into the point, and the current
            that flows on from the point into the receiving side, which is
            the first plus the injected one.

    Returns:
        The loop gain, whatever the two impedances are (the double-injection
        method of Middlebrook). With negative feedback it is a positive
        number at low frequency: a stage of gain A behind a source impedance
        Zs that drives a load Zl and takes the voltage on that load back,
        inverted, gives A Zl / (Zs + Zl).
    """
    return np.asarray(
        (voltage_ratio * current_ratio - 1.0) / (voltage_ratio + current_ratio + 2.0),
        dtype=np.complex128,
    )


def stability_margins(frequency: Real, loop: Complex) -> tuple[float, float]:
    """The crossover frequency and the phase margin of a loop gain.

    Args:
        frequency: The axis, rising.
        loop: The loop gain. It has to be passed so that a loop with negative
            feedback is a positive number at low frequency, as
            :func:`loop_gain` gives it. Passed with the other sign it gives
            a margin that is off by 180 degrees, and nothing here tells the
            two apart: the sign is not checked.

    Returns:
        The frequency at which the magnitude falls through 1 and the phase
        margin there in degrees: 180 plus the phase at that frequency. The
        phase is followed along the axis without jumps, from its value at
        the first point, which is taken between -180 and 180 degrees.

    Raises:
        MeasureError: When the magnitude never falls through 1.
    """
    log_f = np.log10(frequency)
    crossover = first_crossing(log_f, decibels(loop), 0.0, rising=False)
    phase = phase_degrees(loop)
    return float(10.0**crossover), float(180.0 + np.interp(crossover, log_f, phase))


def integrated_noise(frequency: Real, density: Real, start: float, stop: float) -> float:
    """The noise in a band, from its spectral density.

    Args:
        frequency: The axis in hertz.
        density: The density in volts (or amperes) per root hertz.
        start: Lower edge of the band.
        stop: Upper edge of the band.

    Returns:
        The root mean square value in the band.
    """
    return float(np.sqrt(integral(frequency, density * density, start, stop)))
