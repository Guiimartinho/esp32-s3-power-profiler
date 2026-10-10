"""The model of the suppressor PTVS15VS1UR against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from benches.output_stage import common
from circuit_sim.bench import OPEN_TIER, Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import Circuit, PartModel

_REF = "D21"
"""The part of the schematic that stands for its type."""

_DOCUMENT = "Nexperia PTVSxS1UR series, 1 December 2025"
"""The datasheet the figures are taken from."""

_REVERSE_AMPS = np.logspace(-6, np.log10(20.0), 45)
"""Reverse currents of the curve: 1 uA to 20 A."""

_FORWARD_AMPS = np.logspace(-4, np.log10(20.0), 40)
"""Forward currents of the curve: 100 uA to 20 A."""

_BREAKDOWN_AMPS = 1e-3
"""Current at which the datasheet states the breakdown voltage."""

_CLAMP_AMPS = 16.4
"""Peak current at which the datasheet states the clamping voltage."""

_STANDOFF_VOLTS = 15.0
"""Reverse stand-off voltage of the type."""

_TEST_HERTZ = 1e6
"""Frequency of the capacitance measurement."""


def _device(ctx: Context, model: PartModel | None = None) -> Circuit:
    """The suppressor alone, on the nodes k (cathode) and a (anode, ground)."""
    found = ctx.netlist.component(_REF)
    overrides = {_REF: model} if model is not None else None
    return ctx.circuit([_REF], {found.net_of("K"): "k"}, overrides)


def _current_deck(ctx: Context, title: str, model: PartModel | None = None) -> str:
    """A current forced through the part, stepped: first backward, then forward."""
    stimulus = "\n".join(
        [
            "* a current source from the anode (ground) into the cathode: a positive",
            "* value is a reverse current, a negative value a forward current",
            "Itest 0 k 1m",
        ]
    )
    backward = " ".join(f"{amps:.6g}" for amps in _REVERSE_AMPS)
    forward = " ".join(f"{-amps:.6g}" for amps in _FORWARD_AMPS)
    control = [
        f"foreach level {_BREAKDOWN_AMPS:g} {_CLAMP_AMPS:g} -0.1 -1 -10 {backward} {forward}",
        "  alter Itest dc = $level",
        "  op",
        "end",
    ]
    return ctx.deck(title, _device(ctx, model), stimulus, control=control)


def _voltage_deck(ctx: Context) -> str:
    """The stand-off voltage applied, then a small signal at 0 V and at 5 V."""
    stimulus = "\n".join(
        [
            "* the cathode is driven by a voltage source",
            f"Vk k 0 dc {_STANDOFF_VOLTS:g} ac 1",
        ]
    )
    control = [
        "op",
        "alter Vk dc = 0",
        f"ac lin 1 {_TEST_HERTZ:g} {_TEST_HERTZ:g}",
        "alter Vk dc = 5",
        f"ac lin 1 {_TEST_HERTZ:g} {_TEST_HERTZ:g}",
    ]
    return ctx.deck(
        "PTVS15VS1UR: stand-off current and capacitance", _device(ctx), stimulus, control=control
    )


def _points(result_volts: list[float]) -> tuple[np.ndarray, np.ndarray]:
    """The two curves of a current run, from the voltages of its plots."""
    values = np.asarray(result_volts)
    start = 5
    backward = values[start : start + _REVERSE_AMPS.size]
    forward = -values[start + _REVERSE_AMPS.size :]
    return backward, forward


@bench(
    "models",
    "output-stage-suppressor",
    "PTVS15VS1UR model against its datasheet",
    "the model of the suppressor D21 of the output terminal",
)
def suppressor(ctx: Context) -> Outcome:
    """The suppressor of the schematic is put in the test circuits of its datasheet.

    A current is forced through it backward and forward and the voltage is
    read: the breakdown voltage at 1 mA, the clamping voltage at the rated
    peak current and the forward voltage. The stand-off voltage is applied
    and the current is read, and a small signal gives the capacitance. The
    datasheet has neither a forward curve nor a capacitance, so those
    figures carry no limit: they are what the benches of the output stage
    assume. With the model written here the run is repeated for a part at
    each limit of the breakdown voltage and for the larger forward
    resistance that the benches also use.
    """
    run = ctx.run("curve", _current_deck(ctx, "PTVS15VS1UR: voltage against forced current"))
    count = 5 + _REVERSE_AMPS.size + _FORWARD_AMPS.size
    volts = [float(run.real("k", plot=f"op{step + 1}")[0]) for step in range(count)]
    backward, forward = _points(volts)
    static = ctx.run("standoff", _voltage_deck(ctx))
    leak = -float(static.real("vk#branch", plot="op")[0])
    farads = [
        float(np.imag(-static.vector("vk#branch", plot=plot)[0])) / (2.0 * np.pi * _TEST_HERTZ)
        for plot in ("ac1", "ac2")
    ]
    figures = [
        Figure(
            "breakdown",
            "Breakdown voltage at 1 mA",
            volts[0],
            "V",
            expected=17.6,
            low=16.7,
            high=18.5,
            source=f"{_DOCUMENT}, table 8, page 4",
        ),
        Figure(
            "clamp",
            "Clamping voltage at 16.4 A",
            volts[1],
            "V",
            high=24.4,
            source=f"{_DOCUMENT}, table 8, page 4: at most 24.4 V (10/1000 us pulse)",
        ),
        Figure(
            "standoff_current",
            "Reverse current at the stand-off voltage of 15 V",
            leak,
            "A",
            expected=1e-9,
            high=0.1e-6,
            source=f"{_DOCUMENT}, table 8, page 4: 0.001 uA typical, 0.1 uA at most",
        ),
        Figure("forward_0a1", "Forward voltage at 0.1 A (assumption)", -volts[2], "V"),
        Figure("forward_1a", "Forward voltage at 1 A (assumption)", -volts[3], "V"),
        Figure("forward_10a", "Forward voltage at 10 A (assumption)", -volts[4], "V"),
        Figure("capacitance_0v", "Capacitance at 0 V and 1 MHz (assumption)", farads[0], "F"),
        Figure("capacitance_5v", "Capacitance at 5 V and 1 MHz (assumption)", farads[1], "F"),
    ]
    traces = [
        Trace(backward, _REVERSE_AMPS, "typical", 0),
        Trace(forward, _FORWARD_AMPS, "forward resistance 0.03 ohm", 1),
    ]
    if ctx.tier == OPEN_TIER:
        for key, label, limit in (("low", "lowest", 16.7), ("high", "highest", 18.5)):
            variant = ctx.run(
                f"breakdown-{key}",
                _current_deck(
                    ctx,
                    f"PTVS15VS1UR: {label} breakdown voltage",
                    common.suppressor(breakdown=limit),
                ),
                keep=False,
            )
            points = [float(variant.real("k", plot=f"op{step + 1}")[0]) for step in range(count)]
            figures.append(
                Figure(
                    f"breakdown_{key}",
                    f"Part with the {label} breakdown voltage: at 1 mA",
                    points[0],
                    "V",
                    expected=limit,
                    low=limit - 0.05,
                    high=limit + 0.05,
                    source=f"{_DOCUMENT}, table 8, page 4",
                )
            )
            if key == "high":
                figures.append(
                    Figure(
                        "clamp_high",
                        "Part with the highest breakdown voltage: clamping voltage at 16.4 A",
                        points[1],
                        "V",
                        expected=24.4,
                        high=24.4,
                        source=f"{_DOCUMENT}, table 8, page 4",
                    )
                )
            traces.append(Trace(_points(points)[0], _REVERSE_AMPS, f"{label} breakdown voltage", 0))
        stiff = ctx.run(
            "forward-high",
            _current_deck(ctx, "PTVS15VS1UR: forward resistance 0.15 ohm", common.suppressor(0.15)),
            keep=False,
        )
        points = [float(stiff.real("k", plot=f"op{step + 1}")[0]) for step in range(count)]
        figures.append(
            Figure(
                "forward_10a_high",
                "Forward voltage at 10 A with 0.15 ohm of forward resistance (assumption)",
                -points[4],
                "V",
            )
        )
        traces.append(Trace(_points(points)[1], _FORWARD_AMPS, "forward resistance 0.15 ohm", 1))
    graph = Graph(
        name="curves",
        title="PTVS15VS1UR: current against voltage, backward and forward",
        xlabel="Voltage across the part (V)",
        panels=(
            Panel("Reverse current (A)", log=True, marks=((16.4, "16.4 A"), (1e-3, "1 mA"))),
            Panel("Forward current (A)", log=True),
        ),
        traces=tuple(traces),
        xmarks=((15.0, "stand-off"), (24.4, "clamp limit")),
    )
    notes = (
        "The datasheet states the clamping voltage for a pulse of a millisecond, in "
        "which the part heats. The model has no temperature: for microseconds it "
        "clamps too high, which is the cautious side for the parts behind it.",
        "The datasheet has no forward curve. The forward voltage of the model, 0.75 V "
        "at 0.1 A, and its forward resistance, 0.03 ohm with a second run at 0.15 ohm, "
        "are assumptions; so is the capacitance.",
        "The reverse current below the breakdown is a resistor that gives the typical "
        "1 nA at 15 V. No leakage figure may be taken from this model: the datasheet "
        "gives none at 5 V or above 25 C.",
    )
    return Outcome(tuple(figures), (graph,), notes)
