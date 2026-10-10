"""The BSS138 model of the path switching sheet against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.circuit import Circuit

_REF = "Q2"
"""The part of the schematic that stands for the two of its sheet."""

_DOCUMENT = "Diodes Incorporated DS30144 Rev. 25-2"
"""The datasheet the figures are taken from."""

_CURVE_GATES = (2.5, 2.75, 3.0, 3.25, 3.5)
"""Gate voltages of the output characteristics of figure 1."""

_CURVE_AMPS = {2.5: 0.20, 3.0: 0.36, 3.5: 0.545}
"""Current in saturation at 5 V, read from figure 1 of the datasheet."""

_INTERLOCK_AMPS = 3.3e-3
"""Current of the interlock node: 3.3 V across R72 (1 kohm)."""

_TEST_HERTZ = 1e6
"""Frequency of the capacitance figures."""


def _device(ctx: Context) -> Circuit:
    """The transistor alone: drain on d, gate on g; its source is ground in the schematic."""
    found = ctx.netlist.component(_REF)
    aliases = {found.net_of("D"): "d", found.net_of("G"): "g"}
    return ctx.circuit([_REF], aliases)


def _static_deck(ctx: Context) -> str:
    """On-resistance at 10 V and the state of the interlock, as operating points."""
    stimulus = "\n".join(
        [
            "* a gate source and a drain current source; the control lines set them",
            "Vg g 0 10",
            "Id 0 d 0.22",
        ]
    )
    control = ["op", "alter Vg dc = 3.3", f"alter Id dc = {_INTERLOCK_AMPS:g}", "op"]
    return ctx.deck("BSS138: on-resistance", _device(ctx), stimulus, control=control)


def _threshold_deck(ctx: Context) -> str:
    """Gate tied to drain, 250 uA forced."""
    stimulus = "\n".join(["* gate tied to drain, drain current forced", "Vgd g d 0", "Id 0 d 250u"])
    return ctx.deck("BSS138: threshold", _device(ctx), stimulus, control=["op"])


def _curves_deck(ctx: Context) -> str:
    """Output characteristics: drain voltage swept at five gate voltages."""
    stimulus = "\n".join(["* drain and gate held by sources", "Vd d 0 5", "Vg g 0 2.5"])
    return ctx.deck(
        "BSS138: output characteristics",
        _device(ctx),
        stimulus,
        control=["dc Vd 0 10 0.05 Vg 2.5 3.5 0.25"],
    )


def _gain_deck(ctx: Context) -> str:
    """Transfer curve at 25 V for the transconductance at 0.2 A."""
    stimulus = "\n".join(["* drain at 25 V, gate swept", "Vd d 0 25", "Vg g 0 2.5"])
    return ctx.deck(
        "BSS138: transfer curve", _device(ctx), stimulus, control=["dc Vg 0.5 3.5 0.005"]
    )


def _capacitance_deck(ctx: Context) -> str:
    """Input, output and reverse transfer capacitance at 10 V and 1 MHz."""
    stimulus = "\n".join(
        [
            "* 10 V on the drain, gate at 0 V; one terminal carries the test voltage",
            "Vd d 0 dc 10 ac 0",
            "Vg g 0 dc 0 ac 1",
        ]
    )
    control = [
        f"ac lin 1 {_TEST_HERTZ:g} {_TEST_HERTZ:g}",
        "alter Vg ac = 0",
        "alter Vd ac = 1",
        f"ac lin 1 {_TEST_HERTZ:g} {_TEST_HERTZ:g}",
    ]
    return ctx.deck("BSS138: capacitances", _device(ctx), stimulus, control=control)


@bench(
    "models",
    "path-switching-bss138",
    "BSS138 model of the path switching sheet against its datasheet",
    "the model of the interlock transistors Q2 and Q3",
)
def bss138(ctx: Context) -> Outcome:
    """The transistor Q2 of the schematic is put in the test circuits of its datasheet.

    The gate tied to the drain gives the threshold, a forced drain current
    the on-resistance, swept drain and gate voltages the output
    characteristics and the transconductance, and two small-signal runs the
    capacitances. One more point is the state of the interlock: 3.3 V on the
    gate and the 3.3 mA that the series resistor of the ampere request
    delivers.
    """
    static = ctx.run("static", _static_deck(ctx))
    on_ohms = float(static.real("d", plot="op1")[0]) / 0.22
    interlock_volts = float(static.real("d", plot="op2")[0])
    threshold = float(ctx.run("threshold", _threshold_deck(ctx)).real("d")[0])

    curves = ctx.run("curves", _curves_deck(ctx))
    drain = curves.real("d")
    current = -curves.real("vd#branch")
    points = drain.size // len(_CURVE_GATES)
    families = {
        gate: (
            drain[index * points : (index + 1) * points],
            current[index * points : (index + 1) * points],
        )
        for index, gate in enumerate(_CURVE_GATES)
    }

    gain = ctx.run("gain", _gain_deck(ctx))
    gate_axis = gain.real("g")
    transfer = -gain.real("vd#branch")
    slope = np.gradient(transfer, gate_axis)
    transconductance = float(np.interp(0.2, transfer, slope))

    caps = ctx.run("capacitance", _capacitance_deck(ctx))
    omega = 2.0 * np.pi * _TEST_HERTZ
    ciss = float(-np.imag(caps.vector("vg#branch", plot="ac1")[0]) / omega)
    crss = float(np.imag(caps.vector("vg#branch", plot="ac2")[0]) / omega)
    coss = float(-np.imag(caps.vector("vd#branch", plot="ac2")[0]) / omega)

    figures = [
        Figure(
            "threshold",
            "Gate threshold at 250 uA",
            threshold,
            "V",
            expected=1.2,
            low=0.5,
            high=1.5,
            source=f"{_DOCUMENT}, page 2",
        ),
        Figure(
            "on_10v",
            "On-resistance at 10 V on the gate and 0.22 A",
            on_ohms,
            "ohm",
            expected=1.4,
            high=3.5,
            source=f"{_DOCUMENT}, page 2: 1.4 ohm typical, 3.5 ohm at most",
        ),
        Figure(
            "transconductance",
            "Transconductance at 0.2 A and 25 V",
            transconductance,
            "S",
            low=0.1,
            source=f"{_DOCUMENT}, page 2: 100 mS at least",
        ),
    ]
    for gate, expected in _CURVE_AMPS.items():
        volts, amps = families[gate]
        figures.append(
            near(
                f"saturation_{gate:g}v".replace(".", "p"),
                f"Drain current at {gate:g} V on the gate and 5 V on the drain",
                float(np.interp(5.0, volts, amps)),
                "A",
                expected,
                0.15,
                f"{_DOCUMENT}, page 3, figure 1, read from the curve; 15 % asked of the fit",
            )
        )
    figures += [
        Figure(
            "ciss",
            "Input capacitance at 10 V",
            ciss,
            "F",
            high=50e-12,
            source=f"{_DOCUMENT}, page 2: 50 pF at most",
        ),
        Figure(
            "coss",
            "Output capacitance at 10 V",
            coss,
            "F",
            high=25e-12,
            source=f"{_DOCUMENT}, page 2: 25 pF at most",
        ),
        Figure(
            "crss",
            "Reverse transfer capacitance at 10 V",
            crss,
            "F",
            high=8e-12,
            source=f"{_DOCUMENT}, page 2: 8 pF at most",
        ),
        Figure(
            "interlock_drop",
            "Drain voltage with 3.3 V on the gate and 3.3 mA",
            interlock_volts,
            "V",
            source="the state of the interlock node with both requests high",
        ),
    ]
    graph = Graph(
        name="output",
        title="BSS138: drain current against drain voltage, as figure 1 of the datasheet",
        xlabel="Drain voltage (V)",
        panels=(Panel("Drain current (A)"),),
        traces=tuple(
            Trace(volts, amps, f"{gate:g} V on the gate", 0)
            for gate, (volts, amps) in families.items()
        ),
    )
    notes = (
        "The table and the typical curves of the datasheet do not agree on the "
        "threshold; the model lies between them, at 1.1 V and 250 uA.",
        "The capacitances of the model are the upper limits of the datasheet. The "
        "benches of the interlock also run the variants with the threshold at 0.5 V "
        "and at 1.5 V.",
        "The gate resistance and the body diode are assumptions; the model has no "
        "breakdown and says nothing about leakage.",
    )
    return Outcome(tuple(figures), (graph,), notes)
