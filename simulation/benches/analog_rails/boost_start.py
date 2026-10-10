"""The start of the boost converter, as drawn, on a 5 V rail whose source is limited."""

from __future__ import annotations

import numpy as np

from benches.analog_rails import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.engine import RunResult

_LIMITS = {"0.67 A": 0.67, "0.76 A": 0.76, "0.85 A": 0.85, "2.0 A": 2.0}
"""Current limit of the source: the input of the controller module (least,
nominal, most) and the USB-C input (section 4.1)."""

_VARIANTS = {
    "gentle": ("gentle amplifier", common.GENTLE_AMPLIFIER),
    "weak": ("least current limit of the datasheet", common.LEAST_LIMIT),
    "late": ("converter working from 2.7 V only", "vmin=2.7"),
}
"""Other assumptions about the converter, each run on the 0.76 A source."""

_NOMINAL = 0.76
"""Nominal current limit of the input of the controller module."""

_STOP = 4e-3
"""Length of a cycle-by-cycle run."""

_LONG_STOP = 1.1
"""Length of the run with the averaged model."""

_RELEASE_LEVEL = 4.12
"""Highest level at which the supervisor starts its release delay (section 4.1)."""

_TRIP_LEVEL = 4.00
"""Highest level at which the supervisor trips (section 4.1)."""

_SATURATION = 5.95
"""Current at which the inductor has lost 30 % of its inductance (datasheet)."""


def _tag(name: str) -> str:
    """A limit as a part of a file name and of a figure key."""
    return name.replace(" ", "").replace(".", "p").lower()


def _switching_deck(ctx: Context, limit: float, params: str = "", note: str = "") -> str:
    overrides = None
    if params:
        overrides = {"U10": common.with_params(common.SWITCHING_BOOST, params)}
    return ctx.deck(
        f"Start of the boost converter as drawn, source limited to {limit:g} A{note}",
        common.boost_circuit(ctx, overrides),
        common.boost_stimulus(limit),
        control=[
            "save p5v p13v5 ldo_in src en_boost i(Vsrc) @l.xl1.l1[i]",
            f"tran 5n {_STOP:g} 0 20n",
        ],
    )


def _averaged_deck(ctx: Context, limit: float, bias: bool, stop: float) -> str:
    overrides = {"U10": common.AVERAGED_BOOST, "L1": common.SKIP}
    kind = "capacitors with their loss under bias" if bias else "linear capacitors"
    return ctx.deck(
        f"Start of the boost converter as drawn, averaged model, {limit:g} A, {kind}",
        common.boost_circuit(ctx, overrides, bias=bias),
        common.boost_stimulus(limit),
        control=[
            "save p5v p13v5 ldo_in src en_boost i(Vsrc)",
            f"tran 20u {stop:g} 0 20u",
        ],
        options=("method=gear",),
    )


def _charged(run: RunResult, level: float = 12.2) -> float:
    """Time from the start of the source to +13V5 at a level."""
    time = run.real("time")
    return common.crossing_after(time, run.real("p13v5"), level, True, 0.0) - common.RAMP_START


def _lowest_after_release(run: RunResult) -> float:
    """Lowest 5 V rail after it has passed the release level of the supervisor."""
    time = run.real("time")
    rail = run.real("p5v")
    released = common.crossing_after(time, rail, _RELEASE_LEVEL, True, 0.0)
    if not np.isfinite(released):
        return float("nan")
    return float(np.min(rail[time >= released]))


def _held(run: RunResult, limit: float) -> tuple[float, float]:
    """Time the source spends in its limit and the level of the rail meanwhile."""
    time = run.real("time")
    limited = -run.real("vsrc#branch") > 0.98 * limit
    spans = np.diff(time)[limited[:-1]]
    if spans.size == 0:
        return 0.0, float("nan")
    return float(np.sum(spans)), float(np.median(run.real("p5v")[limited]))


def _start_figures(name: str, limit: float, run: RunResult) -> list[Figure]:
    tag = _tag(name)
    time = run.real("time")
    in_limit, level = _held(run, limit)
    released = common.crossing_after(time, run.real("p5v"), _RELEASE_LEVEL, True, 0.0)
    figures = [
        Figure(
            f"charged_{tag}",
            f"Source limited to {name}: +13V5 above 12.2 V after the source starts",
            _charged(run),
            "s",
            expected=3e-3,
            high=4.5e-3,
            source="section 3, step 2: charged about 3 ms after the start",
        ),
        Figure(
            f"limited_{tag}",
            f"Source limited to {name}: time the source spends in its limit",
            in_limit,
            "s",
        ),
        Figure(
            f"held_{tag}",
            f"Source limited to {name}: level of the 5 V rail while the source is in its limit",
            level,
            "V",
        ),
        Figure(
            f"rail_up_{tag}",
            f"Source limited to {name}: 5 V rail above 4.12 V after the source starts",
            released - common.RAMP_START,
            "s",
        ),
        Figure(
            f"rail_low_{tag}",
            f"Source limited to {name}: lowest 5 V rail after it has passed 4.12 V",
            _lowest_after_release(run),
            "V",
            low=_TRIP_LEVEL,
            source="section 4.1: the supervisor trips at 3.83 V to 4.00 V; a rail that "
            "stays above 4.00 V is a start in one go (criterion of this bench)",
        ),
        Figure(
            f"peak_{tag}",
            f"Source limited to {name}: highest inductor current",
            float(np.max(run.real("@l.xl1.l1[i]"))),
            "A",
            high=_SATURATION,
            source="datasheet of the inductor: 30 % of the inductance lost at 5.95 A (10 % at 3 A)",
        ),
        Figure(
            f"overshoot_{tag}",
            f"Source limited to {name}: highest +13V5",
            float(np.max(run.real("p13v5"))),
            "V",
            high=20.0,
            source="datasheet of the +12V_A regulator: input up to 20 V",
        ),
    ]
    if in_limit == 0.0:
        figures = [figure for figure in figures if figure.key != f"held_{tag}"]
    return figures


def _variant_figures(key: str, label: str, run: RunResult) -> list[Figure]:
    in_limit, level = _held(run, _NOMINAL)
    return [
        Figure(
            f"charged_{key}",
            f"0.76 A, {label}: +13V5 above 12.2 V after the source starts",
            _charged(run),
            "s",
            expected=3e-3,
            high=4.5e-3,
            source="section 3, step 2: charged about 3 ms after the start",
        ),
        Figure(
            f"limited_{key}",
            f"0.76 A, {label}: time the source spends in its limit",
            in_limit,
            "s",
        ),
        Figure(
            f"held_{key}",
            f"0.76 A, {label}: level of the 5 V rail while the source is in its limit",
            level,
            "V",
        ),
        Figure(
            f"rail_low_{key}",
            f"0.76 A, {label}: lowest 5 V rail after it has passed 4.12 V",
            _lowest_after_release(run),
            "V",
            low=_TRIP_LEVEL,
            source="section 4.1: the supervisor trips at 3.83 V to 4.00 V",
        ),
    ]


@bench(
    "analog_rails",
    "boost-start",
    "Boost converter as drawn: its start on a source limited to 0.67 A to 0.85 A",
    "section 4.1 (no lock-out, no soft start), section 16 and the risk register (start on the "
    "data cable alone), decision D-51",
)
def boost_start(ctx: Context) -> Outcome:
    """The 5 V rail is brought up through a current limit and the converter starts by itself.

    The circuit is the converter as drawn: the position of the voltage
    detector U9 is empty and the enable pin is on the rail through R29. The
    converter is taken cycle by cycle. The source is limited to 0.67 A,
    0.76 A and 0.85 A, the span of the limiter on the input of the controller
    module, and to 2.0 A, the USB-C input. The rail carries its capacitors
    and the 25 mA of the controller module.

    Three more runs on the 0.76 A source change one assumption about the
    converter each: an error amplifier that lets go of the full current
    earlier, the least current limit of the datasheet, and a converter that
    works only from the 2.7 V at which its datasheet begins. A last run of a
    second with the averaged model counts the starts.
    """
    decks = {_tag(name): _switching_deck(ctx, limit) for name, limit in _LIMITS.items()}
    for key, (label, params) in _VARIANTS.items():
        decks[key] = _switching_deck(ctx, _NOMINAL, params, f", {label}")
    decks["averaged"] = _averaged_deck(ctx, _NOMINAL, False, _STOP)
    runs = ctx.run_many(decks)
    ctx.kept[f"{ctx.prefix}.limited-0p76.cir"] = decks[_tag("0.76 A")]
    figures: list[Figure] = []
    traces: list[Trace] = []
    keep = slice(None, None, 25)
    for name, limit in _LIMITS.items():
        run = runs[_tag(name)]
        figures += _start_figures(name, limit, run)
        milli = run.real("time")[keep] * 1e3
        traces += [
            Trace(milli, run.real("p5v")[keep], name, 0),
            Trace(milli, run.real("p13v5")[keep], name, 1),
            Trace(milli, -run.real("vsrc#branch")[keep], name, 2),
        ]
    nominal = runs[_tag("0.76 A")]
    others: list[Trace] = [
        Trace(nominal.real("time")[keep] * 1e3, nominal.real("p5v")[keep], "as assumed", 0),
        Trace(nominal.real("time")[keep] * 1e3, nominal.real("p13v5")[keep], "as assumed", 1),
    ]
    for key, (label, _) in _VARIANTS.items():
        run = runs[key]
        figures += _variant_figures(key, label, run)
        milli = run.real("time")[keep] * 1e3
        others += [
            Trace(milli, run.real("p5v")[keep], label, 0),
            Trace(milli, run.real("p13v5")[keep], label, 1),
        ]
    wide = runs[_tag("2.0 A")]
    current = -wide.real("vsrc#branch")
    above = np.diff(wide.real("time"))[(current > 1.0)[:-1]]
    long_run = ctx.run("averaged-second", _averaged_deck(ctx, _NOMINAL, True, _LONG_STOP))
    starts = measure.crossings(long_run.real("time"), long_run.real("en_boost"), 1.0, rising=True)
    figures += [
        Figure(
            "inrush_usbc",
            "Source limited to 2.0 A: highest current of the source",
            float(np.max(current)),
            "A",
            low=1.5,
            high=2.5,
            source="section 16: start current expected at 1.5 A to 2.5 A",
        ),
        Figure(
            "inrush_usbc_time",
            "Source limited to 2.0 A: time the source gives more than 1 A",
            float(np.sum(above)),
            "s",
            low=0.15e-3,
            high=0.2e-3,
            source="section 16: expected for 0.15 ms to 0.2 ms",
        ),
        near(
            "model_agreement",
            "0.76 A: +13V5 above 12.2 V after the source starts, averaged model",
            _charged(runs["averaged"]),
            "s",
            _charged(nominal),
            0.15,
            "the cycle-by-cycle model in the same circuit (check of the averaged model)",
        ),
        Figure(
            "starts",
            "0.76 A, averaged model: number of starts of the converter in the first second",
            float(starts.size),
            "",
            high=1.0,
            source="section 16: a start that neither hangs nor repeats",
        ),
        Figure(
            "settled",
            "0.76 A, averaged model: +13V5 at the end of the first second",
            measure.mean(
                long_run.real("time"), long_run.real("p13v5"), _LONG_STOP - 0.05, _LONG_STOP
            ),
            "V",
            low=13.0,
            high=14.1,
            source="section 3: 13.0 V to 14.1 V",
        ),
    ]
    start = Graph(
        name="start",
        title="Start of the boost converter as drawn, for four limits of the source",
        xlabel="Time (ms)",
        panels=(
            Panel("5 V rail (V)", marks=((_TRIP_LEVEL, "supervisor trips at most at 4.00 V"),)),
            Panel("+13V5 (V)"),
            Panel("Current of the source (A)"),
        ),
        traces=tuple(traces),
        xmarks=((common.RAMP_START * 1e3, "source starts"),),
    )
    assumed = Graph(
        name="assumptions",
        title="0.76 A source: the same start with other assumptions about the converter",
        xlabel="Time (ms)",
        panels=(Panel("5 V rail (V)"), Panel("+13V5 (V)")),
        traces=tuple(others),
        xmarks=((common.RAMP_START * 1e3, "source starts"),),
    )
    notes = (
        "The source is a voltage behind 0.2 ohm with a flat current limit and no path "
        "back. A real limiter may fold back or switch off while it limits; that belongs "
        "to the power input block and is not in this bench.",
        "What the converter does below the 2.7 V at which its datasheet begins decides "
        "this bench, and the datasheet does not say it. The model works from 2.0 V and "
        "its current limit there continues the trend of the datasheet curves. With that "
        "the converter starts while the rail is still rising and takes all the source "
        "gives: the rail stands at the level of the figures for about a millisecond and "
        "rises to 5 V when +13V5 is charged. The start neither hangs nor repeats, with "
        "each of the other assumptions as well. A part that stops below some supply "
        "voltage would hold the rail at that voltage instead.",
        "While the rail is held low nothing else is supplied from it: the supervisor has "
        "not released the other rails, and the controller module has its own regulator.",
        "The error amplifier of the converter model is an assumption: the overshoot of "
        "+13V5 at the end of the start is not a figure of the part.",
        "The ceramic capacitors are linear in the cycle-by-cycle runs: those of +13V5 "
        "take the value that needs the energy of the real charge from 0 V to 13.5 V, "
        "those of the 5 V rail the value they have at 5 V. The run of a second has them "
        "with their loss under bias.",
        "The inductor is linear here; at the highest current of these runs it has lost "
        "less than 10 % of its inductance (datasheet curve).",
    )
    return Outcome(tuple(figures), (start, assumed), notes)
