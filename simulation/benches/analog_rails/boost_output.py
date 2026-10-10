"""The output of the boost converter: level with tolerances, load, ripple."""

from __future__ import annotations

import numpy as np

from benches.analog_rails import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.circuit import Circuit
from circuit_sim.engine import RunResult

_REFS = ("U10", "L1", "D6", "R29", "R32", "R33", "R37", "C23", "C25", "C27", "C29")
"""The boost converter with its feedback and the filter to the +12V_A regulator."""

_LOADS = {"light": 10e-3, "heavy": 40e-3}
"""Load on +13V5 behind R37: the +12V_A regulator with its loads and the control
pin of the source regulator at rest, and the same with that pin at 1 A of output."""

_REFERENCE = {"low": 1.205, "typ": 1.23, "high": 1.255}
"""Feedback voltage of the converter: the limits and the typical value of its datasheet."""

_SETTLE = 60e-3
"""Length of an averaged run: the level has settled long before."""

_SWITCHING = 7e-3
"""Length of a cycle-by-cycle run: the start and its overshoot are over after 4 ms."""

_WINDOW = 0.25e-3
"""The last part of a cycle-by-cycle run, in which the ripple is read."""

_FREQUENCY = 1.6e6
"""Switching frequency of the converter (datasheet, typical)."""

_SHORTED = 1e-3
"""Factor on R37 for the runs with a 0 ohm part in its place."""

_REJECTION_DB = 79.0
"""Ripple rejection of the +12V_A regulator at 1 MHz (its datasheet, page 4)."""


def _circuit(
    ctx: Context, averaged: bool, reference: float, corner: int, filter_scale: float = 1.0
) -> Circuit:
    refs = (*_REFS, *common.capacitors_on(ctx.netlist, ("+5V",)))
    # R32 up and R33 down give the highest output
    scales = {
        "R32": 1.0 + 0.01 * corner,
        "R33": 1.0 - 0.01 * corner,
        "R37": filter_scale,
    }
    if averaged:
        overrides = common.bias_models(ctx.netlist, refs)
        overrides["U10"] = common.with_params(common.AVERAGED_BOOST, f"vref={reference:g}")
        overrides["L1"] = common.SKIP
        return ctx.circuit(refs, common.ALIASES, overrides, scales)
    scales.update(common.bias_scales(ctx.netlist, refs))
    return ctx.circuit(refs, common.ALIASES, None, scales)


def _averaged_deck(ctx: Context, reference: float, corner: int, rail: float) -> str:
    stimulus = "\n".join(
        [
            f"Vp5 p5v 0 PWL(0 0 1m {rail:g})",
            "* the load steps from the light one to the heavy one at 30 ms",
            f"Bload ldo_in 0 I = (time < 30m ? {_LOADS['light']:g} : {_LOADS['heavy']:g})"
            "*tanh(max(v(ldo_in), 0)/2)",
        ]
    )
    return ctx.deck(
        f"Boost output, averaged model, reference {reference:g} V, 5 V rail at {rail:g} V",
        _circuit(ctx, True, reference, corner),
        stimulus,
        control=["save p5v p13v5 ldo_in i(Vp5)", f"tran 20u {_SETTLE:g} 0 20u"],
        options=("method=gear",),
    )


def _switching_deck(ctx: Context, load: float, filter_scale: float = 1.0) -> str:
    stimulus = "\n".join(
        [
            "* the 5 V rail behind the resistance of its source",
            "Vsrc src 0 PWL(0 0 0.2m 5)",
            f"Rsrc src p5v {common.SOURCE_OHMS:g}",
            f"Bload ldo_in 0 I = {load:g}*tanh(max(v(ldo_in), 0)/2)",
        ]
    )
    part = "R37 as drawn" if filter_scale == 1.0 else "R37 at 0 ohm"
    return ctx.deck(
        f"Boost output, cycle by cycle, {load * 1e3:g} mA, {part}",
        _circuit(ctx, False, _REFERENCE["typ"], 0, filter_scale),
        stimulus,
        control=[
            "save p5v p13v5 ldo_in sw @l.xl1.l1[i]",
            f"tran 5n {_SWITCHING:g} {_SWITCHING - 2 * _WINDOW:g} 20n",
        ],
    )


def _ripple(time: common.Real, wave: common.Real, start: float, stop: float) -> float:
    """Peak to peak within two switching periods, as the median over a window.

    The output of the model also moves slowly; that part is read by
    :func:`_wander`.
    """
    span = 2.0 / _FREQUENCY
    grid = np.arange(start, stop, 5e-9)
    samples = np.interp(grid, time, wave)
    count = int(span / 5e-9)
    chunks = samples[: samples.size // count * count].reshape(-1, count)
    return float(np.median(np.ptp(chunks, axis=1)))


def _wander(time: common.Real, wave: common.Real, start: float, stop: float) -> float:
    """Peak to peak of the mean over two switching periods, without a straight line."""
    span = 2.0 / _FREQUENCY
    grid = np.arange(start, stop, 5e-9)
    samples = np.interp(grid, time, wave)
    count = int(span / 5e-9)
    means = samples[: samples.size // count * count].reshape(-1, count).mean(axis=1)
    axis = np.arange(means.size, dtype=np.float64)
    return float(np.ptp(means - np.polyval(np.polyfit(axis, means, 1), axis)))


def _level(run: RunResult, start: float, stop: float) -> float:
    return measure.mean(run.real("time"), run.real("p13v5"), start, stop)


@bench(
    "analog_rails",
    "boost-output",
    "Boost converter: +13V5 with tolerances, against load, and its ripple",
    "section 3 (analog rails, 13.0 V to 14.1 V), decision D-51",
)
def boost_output(ctx: Context) -> Outcome:
    """The boost converter on a 5 V rail that is up, with the loads of +13V5.

    The level of +13V5 is read from the averaged model: with typical parts,
    with the feedback voltage and the 1 % divider at their limits, at 10 mA
    and at 40 mA of load, and with the 5 V rail at 4.25 V and at 5.5 V. The
    ripple is read from the cycle-by-cycle model at the same two loads, at
    the output of the converter, behind the filter R37 with C29 at the input
    of the +12V_A regulator, and on the 5 V rail; then once more with a
    0 ohm part in the place of R37.
    """
    typ = ctx.run("level-typical", _averaged_deck(ctx, _REFERENCE["typ"], 0, 5.0))
    high = ctx.run("level-high", _averaged_deck(ctx, _REFERENCE["high"], 1, 5.0), keep=False)
    low = ctx.run("level-low", _averaged_deck(ctx, _REFERENCE["low"], -1, 5.0), keep=False)
    sag = ctx.run("level-4v25", _averaged_deck(ctx, _REFERENCE["typ"], 0, 4.25), keep=False)
    top = ctx.run("level-5v5", _averaged_deck(ctx, _REFERENCE["typ"], 0, 5.5), keep=False)
    light = (25e-3, 30e-3)
    heavy = (_SETTLE - 5e-3, _SETTLE)
    time = typ.real("time")
    current = -typ.real("vp5#branch")
    figures = [
        near(
            "level_typ",
            "+13V5, typical parts, 10 mA",
            _level(typ, *light),
            "V",
            13.53,
            0.005,
            "section 3: 13.5 V; 1.23 V x (1 + R32 / R33)",
        ),
        Figure(
            "level_high",
            "+13V5, feedback voltage and divider at the limits that make it highest",
            _level(high, *light),
            "V",
            low=13.0,
            high=14.1,
            source="section 3: 13.0 V to 14.1 V",
        ),
        Figure(
            "level_low",
            "+13V5, feedback voltage and divider at the limits that make it lowest, 40 mA",
            _level(low, *heavy),
            "V",
            low=13.0,
            high=14.1,
            source="section 3: 13.0 V to 14.1 V",
        ),
        Figure(
            "load_step",
            "+13V5: change from 10 mA to 40 mA",
            _level(typ, *heavy) - _level(typ, *light),
            "V",
        ),
        Figure(
            "line_low",
            "+13V5 with the 5 V rail at 4.25 V, 40 mA",
            _level(sag, *heavy),
            "V",
            low=13.0,
            high=14.1,
            source="section 3: 13.0 V to 14.1 V; D-49: the rail may stand at 4.25 V",
        ),
        Figure(
            "line_high",
            "+13V5 with the 5 V rail at 5.5 V, 10 mA",
            _level(top, *light),
            "V",
            low=13.0,
            high=14.1,
            source="section 3: 13.0 V to 14.1 V",
        ),
        Figure(
            "input_light",
            "Current from the 5 V rail at 10 mA of load",
            measure.mean(time, current, *light),
            "A",
        ),
        Figure(
            "input_heavy",
            "Current from the 5 V rail at 40 mA of load",
            measure.mean(time, current, *heavy),
            "A",
        ),
    ]
    decks = {name: _switching_deck(ctx, load) for name, load in _LOADS.items()}
    for name, load in _LOADS.items():
        decks[f"{name}-0r"] = _switching_deck(ctx, load, _SHORTED)
    ripple = ctx.run_many(decks)
    ctx.kept[f"{ctx.prefix}.ripple-light.cir"] = _switching_deck(ctx, _LOADS["light"])
    traces: list[Trace] = []
    start, stop = _SWITCHING - _WINDOW, _SWITCHING
    for name, load in _LOADS.items():
        run = ripple[name]
        t = run.real("time")
        label = f"{load * 1e3:g} mA"
        for key, text in (
            ("p13v5", "at the output of the converter"),
            ("ldo_in", "behind R37 with C29"),
            ("p5v", "on the 5 V rail"),
        ):
            figures.append(
                Figure(
                    f"ripple_{key}_{name}",
                    f"Ripple {text} within two switching periods, peak to peak, {label}",
                    _ripple(t, run.real(key), start, stop),
                    "V",
                )
            )
            figures.append(
                Figure(
                    f"wander_{key}_{name}",
                    f"Slow movement {text} over 0.25 ms, peak to peak, {label}",
                    _wander(t, run.real(key), start, stop),
                    "V",
                )
            )
        shorted = ripple[f"{name}-0r"]
        behind = _ripple(t, run.real("ldo_in"), start, stop)
        direct = _ripple(shorted.real("time"), shorted.real("ldo_in"), start, stop)
        figures += [
            Figure(
                f"ripple_ldo_in_{name}_0r",
                f"Ripple at the input of the +12V_A regulator with R37 at 0 ohm, {label}",
                direct,
                "V",
            ),
            Figure(
                f"passed_{name}",
                f"That ripple behind the regulator by its 79 dB, R37 as drawn, {label}",
                behind * 10.0 ** (-_REJECTION_DB / 20.0),
                "V",
            ),
            Figure(
                f"passed_{name}_0r",
                f"The same with R37 at 0 ohm, {label}",
                direct * 10.0 ** (-_REJECTION_DB / 20.0),
                "V",
            ),
        ]
        figures.append(
            Figure(
                f"peak_{name}",
                f"Highest inductor current in regulation, {label}",
                float(np.max(run.real("@l.xl1.l1[i]")[t >= start])),
                "A",
                high=3.0,
                source="datasheet of the inductor: 10 % of the inductance lost at 3 A",
            )
        )
        shown = (t >= stop - 12e-6) & (t <= stop)
        micro = (t[shown] - t[shown][0]) * 1e6
        mean_out = measure.mean(t, run.real("p13v5"), start, stop)
        mean_in = measure.mean(t, run.real("ldo_in"), start, stop)
        traces += [
            Trace(micro, run.real("sw")[shown], label, 0),
            Trace(micro, run.real("@l.xl1.l1[i]")[shown] * 1e3, label, 1),
            Trace(micro, (run.real("p13v5")[shown] - mean_out) * 1e3, f"output, {label}", 2),
            Trace(
                micro, (run.real("ldo_in")[shown] - mean_in) * 1e3, f"behind R37, {label}", 2, "--"
            ),
        ]
    graph = Graph(
        name="ripple",
        title="Boost converter in regulation: the last 12 us of each run",
        xlabel="Time (us)",
        panels=(
            Panel("Switch node (V)"),
            Panel("Inductor current (mA)"),
            Panel("+13V5 around its mean (mV)"),
        ),
        traces=tuple(traces),
    )
    step = slice(None, None, 4)
    level = Graph(
        name="level",
        title="+13V5 from the averaged model: load step from 10 mA to 40 mA at 30 ms",
        xlabel="Time (ms)",
        panels=(Panel("+13V5 (V)"),),
        traces=(
            Trace(typ.real("time")[step] * 1e3, typ.real("p13v5")[step], "typical parts", 0),
            Trace(high.real("time")[step] * 1e3, high.real("p13v5")[step], "highest", 0),
            Trace(low.real("time")[step] * 1e3, low.real("p13v5")[step], "lowest", 0),
        ),
    )
    notes = (
        "The level of +13V5 is that of the feedback divider and of the feedback voltage; "
        "the models add nothing to it. The response to the load step and the pattern of "
        "the pulses belong to an error amplifier that is an assumption: the compensation "
        "of the part is not published.",
        "At these loads the converter works with a discontinuous inductor current. The "
        "ripple figures hold the capacitors at the capacitance they have at their "
        "voltage and no series resistance or inductance of the capacitors or of the "
        "board: the spikes at the edges of the switch node are not in them.",
        "Beside the ripple of a cycle the output of the model moves by a few millivolts "
        "over a quarter of a millisecond. That slow movement belongs to the assumed "
        "error amplifier and is not a figure of the part; it is listed so that the next "
        "bench can take the worse of the two.",
        "With a 0 ohm part in the place of R37 the ripple of the converter output stands "
        "at the input of the +12V_A regulator. Behind the regulator both cases are "
        "nanovolts by the 79 dB that its datasheet gives at 1 MHz: by conduction the "
        "choice of R37 does not matter. A bead cannot be simulated without a part "
        "number. What decides in practice is not in a circuit simulation: the edges of "
        "the switch node, which pass a regulator through its pass element and the board.",
        "The load is a current sink behind R37: 10 mA stands for the +12V_A regulator "
        "with its loads and the control pin of the source regulator at rest, 40 mA for "
        "the same with 30 mA into that pin (datasheet limit at 1.1 A of output).",
    )
    return Outcome(tuple(figures), (graph, level), notes)
