"""A short circuit at the output of the source: current limit, pre-regulator, dissipation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.source_meter import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_SHORT = 15e-3
"""Instant of the short circuit, after the power-up run has come to rest."""

_RELEASE = 45e-3
"""Instant at which the short circuit opens again."""

_STOP = 75e-3

_SHORT_OHMS = 10e-3
"""Resistance of the short circuit itself (assumption)."""

_EDGE = 2e-6
"""Time in which the short circuit closes and opens."""

_REVERSE_LIMIT = -0.3
"""Rating of the IN pin relative to the output (LT3080 Rev. E, page 2)."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One short circuit.

    Attributes:
        name: Name of the run.
        text: What is shorted, for the labels.
        volts: Set-point.
        node: Node that is shorted to ground.
        regulator: Parameters of the regulator model that differ from the typical ones.
    """

    name: str
    text: str
    volts: float
    node: str
    regulator: tuple[tuple[str, float], ...] = ()


_CASES = (
    _Case("output-5v", "5.0 V, short at the regulator output", 5.0, "ldo_out"),
    _Case("terminal-5v", "5.0 V, short at the terminal in range 3", 5.0, "dut"),
    _Case("output-0v8", "0.8 V, short at the regulator output", 0.8, "ldo_out"),
    _Case(
        "output-5v-least",
        "5.0 V, short at the regulator output, least current limit",
        5.0,
        "ldo_out",
        tuple(common.LIMIT_CURRENT.items()),
    ),
)


def _deck(ctx: Context, case: _Case) -> str:
    overrides: dict[str, PartModel] = {}
    if case.regulator:
        overrides[common.REGULATOR] = common.part(ctx, common.REGULATOR, **dict(case.regulator))
    closed = f"0.5*(tanh((time - {_SHORT:g})/{_EDGE:g}) - tanh((time - {_RELEASE:g})/{_EDGE:g}))"
    short = (
        "* the short circuit: a conductance to ground that closes and opens again\n"
        f"Bshort {case.node} 0 I = v({case.node})/{_SHORT_OHMS:g}*{closed}\n"
    )
    return (
        common.settle_deck(
            ctx,
            f"Short circuit: {case.text}",
            case.volts,
            index=3,
            overrides=overrides,
            extra=short,
            stop=_STOP,
        )
        .replace("tran 2u", "tran 1u")
        .replace(" 0 20u", " 0 10u")
    )


def _figures(run: RunResult, case: _Case) -> list[Figure]:
    time = run.real("time")
    out = run.real("ldo_out")
    pre = run.real("v_pre")
    headroom = run.real("ldo_in") - out
    amps = run.real(f"v.x{common.REGULATOR.lower()}.vic#branch")
    watts = common.regulator_watts(run)
    rail = -run.real("vp5#branch")
    rest = measure.mean(time, out, _SHORT - 1e-3, _SHORT)
    window = (_RELEASE - 2e-3, _RELEASE - 0.1e-3)
    tag = case.name.replace("-", "_")
    least = bool(case.regulator)
    return [
        Figure(
            f"current_{tag}",
            f"{case.text}: current of the IN pin in the short circuit",
            measure.mean(time, amps, *window),
            "A",
            expected=1.1 if least else 1.4,
            low=1.0 if least else 1.1,
            high=1.2 if least else 1.6,
            source="LT3080 Rev. E, page 4: 1.4 A typical, 1.1 A at the least; the upper "
            "limit is the one of this bench",
        ),
        Figure(
            f"pre_{tag}",
            f"{case.text}: pre-regulator output in the short circuit",
            measure.mean(time, pre, *window),
            "V",
            expected=0.84,
            low=0.7,
            high=1.0,
            source="section 4.2: the pre-regulator follows down to about 0.8 V, 0.84 V "
            "simulated; the band is the one of this bench",
        ),
        Figure(
            f"watts_{tag}",
            f"{case.text}: dissipation of the regulator in the lasting short circuit",
            measure.mean(time, watts, *window),
            "W",
            expected=1.75,
            high=2.0,
            source="section 4.2 and rule F-15: 1.5 W to 2.0 W, calculated",
        ),
        Figure(
            f"peak_watts_{tag}",
            f"{case.text}: highest dissipation of the regulator",
            measure.extremes(time, watts, _SHORT, _RELEASE)[1],
            "W",
        ),
        Figure(
            f"energy_{tag}",
            f"{case.text}: energy in the regulator in the first 5 ms",
            measure.integral(time, watts, _SHORT, _SHORT + 5e-3),
            "J",
        ),
        Figure(
            f"follow_{tag}",
            f"{case.text}: pre-regulator output below 1.2 V after",
            measure.first_crossing(time, pre, 1.2, rising=False, after=_SHORT) - _SHORT,
            "s",
        ),
        Figure(
            f"returned_{tag}",
            f"{case.text}: most power returned to the 5 V rail",
            -measure.extremes(time, rail, _SHORT, _STOP)[0] * common.RAIL_5V,
            "W",
            high=0.25,
            source="section 4.2 and section 16: less than the instrument takes from the "
            "rail, for which 0.25 W is the condition",
        ),
        Figure(
            f"in_pin_{tag}",
            f"{case.text}: lowest voltage of the IN pin relative to the output",
            measure.extremes(time, headroom, _SHORT, _STOP)[0],
            "V",
            low=_REVERSE_LIMIT,
            source="LT3080 Rev. E, page 2 (D-57)",
        ),
        Figure(
            f"overshoot_{tag}",
            f"{case.text}: output above its value before the short, after the release",
            measure.extremes(time, out, _RELEASE, _STOP)[1] - rest,
            "V",
        ),
        Figure(
            f"recovery_{tag}",
            f"{case.text}: output back within 0.1 V after the release in",
            measure.settling_time(time, out, float(out[-1]), 0.1, _RELEASE, _STOP),
            "s",
        ),
    ]


def _graph(run: RunResult, case: _Case) -> Graph:
    time = run.real("time")
    shown = time >= _SHORT - 2e-3
    axis = (time[shown] - _SHORT) * 1e3
    return Graph(
        name=case.name,
        title=f"Short circuit: {case.text}",
        xlabel="Time after the short circuit (ms)",
        panels=(
            Panel("Voltage (V)"),
            Panel("Current of the IN pin (A)"),
            Panel("Dissipation of U18 (W)", marks=((2.0, "2.0 W"),)),
            Panel("Current of the 5 V rail (A)"),
        ),
        traces=(
            Trace(axis, run.real("ldo_out")[shown], "regulator output", 0),
            Trace(axis, run.real("v_pre")[shown], "pre-regulator output", 0),
            Trace(axis, run.real("trk_sense")[shown], "sense node of the tracking", 0, "--"),
            Trace(axis, run.real(f"v.x{common.REGULATOR.lower()}.vic#branch")[shown], "", 1),
            Trace(axis, np.asarray(common.regulator_watts(run)[shown]), "", 2),
            Trace(axis, -run.real("vp5#branch")[shown], "", 3),
        ),
        xmarks=((0.0, "short"), ((_RELEASE - _SHORT) * 1e3, "release")),
    )


@bench(
    "source_meter",
    "short",
    "Short circuit at the output: current limit, pre-regulator, dissipation of U18",
    "section 4.2 (short circuit, sense path of the tracking), rule F-15, decision D-55",
)
def short(ctx: Context) -> Outcome:
    """The source stands at rest without load and its output is shorted for 30 ms.

    The short circuit of 10 mohm closes at the regulator output, ahead of
    every switch, or at the terminal behind the path of range 3. Nothing
    opens a switch in these runs: the over-current trip belongs to another
    block, and the question here is what the regulator and the
    pre-regulator do while the short lasts and after it opens. The runs
    give the limited current, the voltage that the pre-regulator falls to,
    the dissipation of the regulator at the start and at rest, and what the
    5 V rail sees.
    """
    figures: list[Figure] = []
    graphs: list[Graph] = []
    kept = {"output-5v"}
    decks = {case.name: _deck(ctx, case) for case in _CASES}
    runs = {name: ctx.run(name, decks[name]) for name in kept}
    runs.update(ctx.run_many({name: deck for name, deck in decks.items() if name not in kept}))
    for case in _CASES:
        figures += _figures(runs[case.name], case)
        if not case.regulator:
            graphs.append(_graph(runs[case.name], case))
    notes = (
        "The regulator model has the typical current limit of 1.4 A, flat up to the 6 V "
        "that this circuit can put across it, and no thermal limit: a real part in a "
        "lasting short circuit heats until its own limit acts, which the datasheet "
        "allows for an indefinite time. The datasheet gives no highest value of the "
        "current limit.",
        "What the converter does when it is asked for less than a duty cycle of 20 % "
        "is not in its datasheet. The model holds 20 % while its current is below its "
        "limit, which puts about 1 V behind its switch resistance: the voltage that "
        "the pre-regulator rests at in the short circuit, and with it the dissipation "
        "of the regulator, follow from that assumption.",
        "The dissipation at the start is the full head room times the limited current "
        "until the regulator has emptied the capacitors of the pre-regulator through "
        "the short circuit; the energy of the first 5 ms states it.",
        "The rails are ideal sources. The over-current trip, the range logic and the "
        "output switch are not in these runs.",
    )
    return Outcome(tuple(figures), tuple(graphs), notes)
