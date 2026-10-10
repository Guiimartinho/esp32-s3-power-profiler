"""The boost converter with a voltage detector at its enable pin (position U9)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.analog_rails import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.engine import RunResult

_SHORT_DELAY = 3e-3
"""Time-out of the detector in the cycle-by-cycle runs.

The part waits 0.24 s. After 3 ms the rail stands at 5 V and +13V5 one
diode drop below it, as after 0.24 s, so the first attempt is the same.
"""

_STOP = 8.5e-3
"""Length of a cycle-by-cycle run: the first attempt on every source, and the
second one that a detector with the short time-out makes."""

_LONG_STOP = 1.1
"""Length of a run with the averaged model: four time-outs of the detector."""

_HIGHEST_THRESHOLD = 3.13
"""Highest threshold of the detector (datasheet): above it no part stops the converter."""

_LOWEST_THRESHOLD = 3.04
"""Lowest threshold of the detector (datasheet): below it every part stops the converter."""

_START_VOLTS = 4.6
"""Level of +13V5 before the converter is enabled: the rail less the diode."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One first attempt.

    Attributes:
        key: Part of the file name and of the figure keys.
        label: Name of the case in the report.
        limit: Current limit of the source.
        params: Parameters of the converter model, empty for the model as it is.
    """

    key: str
    label: str
    limit: float
    params: str


_CASES = (
    _Case("0p67a", "source limited to 0.67 A", 0.67, ""),
    _Case("0p76a", "source limited to 0.76 A", 0.76, ""),
    _Case("0p85a", "source limited to 0.85 A", 0.85, ""),
    _Case(
        "mild",
        "0.85 A, gentle amplifier and least current limit",
        0.85,
        f"{common.GENTLE_AMPLIFIER} {common.LEAST_LIMIT}",
    ),
    _Case("usbc", "source limited to 2.0 A", 2.0, ""),
)
"""The limits of the input of the controller module, the corner that is
kindest to the source, and the USB-C input."""

_LOADS = {"1ma": ("1 mA", common.CONTROL_AMPS), "0p1ma": ("0.1 mA", 0.1e-3)}
"""Load on +13V5 while the detector waits, beside the 0.09 mA of the feedback divider."""


def _first_deck(ctx: Context, case: _Case) -> str:
    overrides = {"U9": common.detector(_SHORT_DELAY)}
    if case.params:
        overrides["U10"] = common.with_params(common.SWITCHING_BOOST, case.params)
    return ctx.deck(
        f"Boost converter with a detector at U9, first attempt, {case.label}",
        common.boost_circuit(ctx, overrides, start=_START_VOLTS),
        common.boost_stimulus(case.limit),
        control=[
            "save p5v p13v5 ldo_in src en_boost i(Vsrc) @l.xl1.l1[i]",
            f"tran 5n {_STOP:g} 0 20n",
        ],
    )


def _averaged_first_deck(ctx: Context, limit: float) -> str:
    overrides = {
        "U9": common.detector(_SHORT_DELAY),
        "U10": common.AVERAGED_BOOST,
        "L1": common.SKIP,
    }
    return ctx.deck(
        f"Boost converter with a detector at U9, first attempt, averaged model, {limit:g} A",
        common.boost_circuit(ctx, overrides, start=_START_VOLTS),
        common.boost_stimulus(limit),
        control=["save p5v p13v5 ldo_in src en_boost i(Vsrc)", f"tran 1u {_STOP:g} 0 1u"],
        options=("method=gear",),
    )


def _long_deck(ctx: Context, limit: float, load: float) -> str:
    overrides = {"U9": common.detector(), "U10": common.AVERAGED_BOOST, "L1": common.SKIP}
    return ctx.deck(
        f"Boost converter with a detector at U9, averaged model, {limit:g} A, "
        f"{load * 1e3:g} mA on +13V5",
        common.boost_circuit(ctx, overrides, start=_START_VOLTS),
        common.boost_stimulus(limit, load),
        control=[
            "save p5v p13v5 ldo_in src en_boost i(Vsrc)",
            f"tran 20u {_LONG_STOP:g} 0 20u",
        ],
        options=("method=gear",),
    )


def _attempt(run: RunResult) -> tuple[float, float, float, float]:
    """The first attempt of a run.

    Returns:
        The instant the converter is enabled, the lowest 5 V rail after it,
        the time from there to the instant the detector stops the converter
        (NaN when it does not), and +13V5 at that instant or, without a
        stop, at the end of the run.
    """
    time = run.real("time")
    enable = run.real("en_boost")
    enabled = common.crossing_after(time, enable, 1.0, True, 0.0)
    if not np.isfinite(enabled):
        return float("nan"), float("nan"), float("nan"), float("nan")
    stopped = common.crossing_after(time, enable, 1.0, False, enabled)
    end = stopped + 0.1e-3 if np.isfinite(stopped) else float(time[-1])
    during = (time >= enabled) & (time <= end)
    lowest = float(np.min(run.real("p5v")[during]))
    boost = run.real("p13v5")
    reached = float(np.interp(stopped, time, boost)) if np.isfinite(stopped) else float(boost[-1])
    return enabled, lowest, stopped - enabled, reached


def _first_figures(case: _Case, run: RunResult) -> list[Figure]:
    _, lowest, lasted, reached = _attempt(run)
    figures = [
        Figure(
            f"rail_low_{case.key}",
            f"First attempt, {case.label}: lowest 5 V rail",
            lowest,
            "V",
            low=_HIGHEST_THRESHOLD,
            source="datasheet of the detector: it stops the converter at 3.04 V to 3.13 V; "
            "a rail that stays above 3.13 V is a start in one go",
        ),
        Figure(
            f"reached_{case.key}",
            f"First attempt, {case.label}: +13V5 when the detector stops the converter"
            if np.isfinite(lasted)
            else f"First attempt, {case.label}: +13V5 at the end of the run",
            reached,
            "V",
        ),
    ]
    if np.isfinite(lasted):
        figures.append(
            Figure(
                f"lasted_{case.key}",
                f"First attempt, {case.label}: time from the enable to the stop",
                lasted,
                "s",
            )
        )
    return figures


def _long_figures(key: str, label: str, run: RunResult) -> list[Figure]:
    time = run.real("time")
    starts = measure.crossings(time, run.real("en_boost"), 1.0, rising=True)
    reached = common.crossing_after(time, run.real("p13v5"), 13.0, True, 0.0)
    return [
        Figure(
            f"starts_{key}",
            f"0.76 A, {label} on +13V5: number of starts of the converter in 1.1 s",
            float(starts.size),
            "",
            high=1.0,
            source="decision D-84: the detector is the remedy for a start that hangs or repeats",
        ),
        Figure(
            f"charged_{key}",
            f"0.76 A, {label} on +13V5: +13V5 above 13.0 V after the source starts",
            reached - common.RAMP_START,
            "s",
            high=0.46,
            source="section 3, step 8: PWR_GOOD at the latest 0.46 s after power",
        ),
        Figure(
            f"kept_{key}",
            f"0.76 A, {label} on +13V5: +13V5 just before the second start",
            float(np.interp(starts[1] - 1e-3, time, run.real("p13v5")))
            if starts.size > 1
            else float("nan"),
            "V",
        ),
    ]


@bench(
    "analog_rails",
    "boost-detector",
    "Boost converter with the voltage detector of decision D-84 fitted at U9",
    "section 4.1 (the detector is the remedy if the converter does not start cleanly), "
    "requirement R-14, decision D-84, the risk register",
)
def boost_detector(ctx: Context) -> Outcome:
    """A detector of 3.08 V holds the converter off until the 5 V rail has stood for a while.

    The position U9 is empty on the board. Here it carries an 803-type
    detector: its output holds the enable pin of the converter low until the
    rail has been above 3.08 V for the time-out of the part, and pulls it
    low again 20 us after the rail has fallen below. The converter then
    starts on a rail that already stands at 5 V, with +13V5 at 4.6 V.

    The first attempt is taken cycle by cycle on the three limits of the
    input of the controller module, on the corner that is kindest to the
    source, and on the USB-C input. Two runs of 1.1 s with the averaged
    model and the real time-out of 0.24 s then show what follows a failed
    attempt, with 1 mA and with 0.1 mA drawn from +13V5 in between.
    """
    decks = {case.key: _first_deck(ctx, case) for case in _CASES}
    decks["averaged"] = _averaged_first_deck(ctx, 0.76)
    for key, (_, load) in _LOADS.items():
        decks[f"long-{key}"] = _long_deck(ctx, 0.76, load)
    runs = ctx.run_many(decks)
    ctx.kept[f"{ctx.prefix}.first-0p76.cir"] = decks["0p76a"]
    ctx.kept[f"{ctx.prefix}.long-1ma.cir"] = decks["long-1ma"]
    figures: list[Figure] = []
    traces: list[Trace] = []
    for case in _CASES:
        run = runs[case.key]
        figures += _first_figures(case, run)
        enabled = _attempt(run)[0]
        time = run.real("time")
        shown = (time >= enabled - 0.1e-3) & (time <= enabled + 1.0e-3)
        pick = np.flatnonzero(shown)[::10]
        milli = (time[pick] - enabled) * 1e3
        traces += [
            Trace(milli, run.real("p5v")[pick], case.label, 0),
            Trace(milli, run.real("p13v5")[pick], case.label, 1),
            Trace(milli, -run.real("vsrc#branch")[pick], case.label, 2),
        ]
    figures.append(
        near(
            "model_agreement",
            "First attempt, 0.76 A: lowest 5 V rail, averaged model",
            _attempt(runs["averaged"])[1],
            "V",
            _attempt(runs["0p76a"])[1],
            0.05,
            "the cycle-by-cycle model in the same circuit (check of the averaged model)",
        )
    )
    short = runs["0p76a"]
    enabled = _attempt(short)[0]
    again = measure.crossings(short.real("time"), short.real("en_boost"), 1.0, rising=True)
    done = common.crossing_after(short.real("time"), short.real("p13v5"), 13.0, True, enabled)
    figures += [
        Figure(
            "short_attempts",
            "0.76 A, a detector with a time-out of 3 ms: attempts until +13V5 is charged",
            float(again.size),
            "",
        ),
        Figure(
            "short_done",
            "0.76 A, a detector with a time-out of 3 ms: +13V5 above 13.0 V after the first enable",
            done - enabled,
            "s",
        ),
    ]
    later: list[Trace] = []
    for key, (label, _) in _LOADS.items():
        run = runs[f"long-{key}"]
        figures += _long_figures(key, label, run)
        step = slice(None, None, 10)
        seconds = run.real("time")[step]
        later += [
            Trace(seconds, run.real("p5v")[step], f"{label} on +13V5", 0),
            Trace(seconds, run.real("p13v5")[step], f"{label} on +13V5", 1),
            Trace(seconds, run.real("en_boost")[step], f"{label} on +13V5", 2),
        ]
    first = Graph(
        name="attempt",
        title="Detector at U9: the first attempt of the converter on a rail at 5 V",
        xlabel="Time after the converter is enabled (ms)",
        panels=(
            Panel(
                "5 V rail (V)",
                marks=(
                    (_HIGHEST_THRESHOLD, "detector, 3.04 V to 3.13 V"),
                    (_LOWEST_THRESHOLD, ""),
                ),
            ),
            Panel("+13V5 (V)", marks=((13.0, "13.0 V"),)),
            Panel("Current of the source (A)"),
        ),
        traces=tuple(traces),
    )
    second = Graph(
        name="repeat",
        title="Detector at U9 with its time-out of 0.24 s, 0.76 A source, averaged model",
        xlabel="Time (s)",
        panels=(
            Panel("5 V rail (V)"),
            Panel("+13V5 (V)", marks=((13.0, "13.0 V"),)),
            Panel("Enable pin of the converter (V)"),
        ),
        traces=tuple(later),
    )
    notes = (
        "The detector carries the figures of the APX803S-31: 3.08 V, 20 us to answer, "
        '0.24 s of time-out. The schematic names the position "803 type, 3.08 V" '
        "without a part number.",
        "The source is a voltage behind 0.2 ohm with a flat current limit and no path "
        "back; a limiter that folds back or switches off while it limits makes the "
        "attempt harder, not easier.",
        "With the detector the converter starts on a rail at 5 V. There it takes more "
        "than twice what the input of the controller module gives, the capacitors of "
        "the rail make up the difference, and the rail reaches the detector before "
        "+13V5 is charged. The detector then stops the converter for 0.24 s. Whether a "
        "later attempt ends depends on what +13V5 keeps in between: with 1 mA drawn "
        "from it nothing is left and every attempt is the first one again.",
        "The cycle-by-cycle runs wait 3 ms where the part waits 0.24 s, and they go on "
        "to the second attempt of such a detector: in 3 ms +13V5 keeps its charge and "
        "the second attempt ends. A detector with a short time-out, or anything else "
        "that keeps +13V5 from emptying between two attempts, charges the rail in two "
        "steps; the part of the schematic does not.",
        "The load on +13V5 while the detector waits is an assumption: 1 mA for the "
        "control pin of the source regulator, whose datasheet gives it only under load, "
        "beside the 0.09 mA of the feedback divider, which is in the netlist.",
        "The converter model takes its current limit from the typical curve of the "
        "datasheet and holds the full current until the output is within 1 V. The "
        'case "gentle amplifier and least current limit" takes both the other way '
        "and is the kindest corner for the source that the datasheet allows.",
        "The ceramic capacitors are linear in every run: those of +13V5 take the value "
        "that needs the energy of the real charge from 4.6 V to 13.5 V, those of the "
        "5 V rail the value they have at 5 V, which is less than they have while the "
        "rail is lower.",
    )
    return Outcome(tuple(figures), (first, second), notes)
