"""The diode, capacitor and detector models of the analog rails against their figures."""

from __future__ import annotations

import numpy as np

from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_LIBRARY = ("analog_rails.lib",)
"""The model file of the analog rails."""

_FORWARD = ((0.1, 0.375), (0.5, 0.430))
"""Largest forward voltage of the B0530W by current (datasheet DS30139, page 2)."""

_CAPACITANCE = ((0.0, 170e-12), (5.0, 65e-12), (20.0, 33e-12))
"""Capacitance of the B0530W by reverse voltage (page 2 and figure 4)."""

_BIAS = (
    ("CL21B475KAFNNNE, 4.7 uF 0805", 4.7e-6, 8.0, ((5.0, 0.715), (10.0, 0.393), (12.0, 0.327))),
    ("CL32B106KAJNNNE, 10 uF 1210", 10e-6, 20.4, ((5.0, 0.947), (13.5, 0.695))),
    ("CL31B226KPHNNNE, 22 uF 1206", 22e-6, 7.39, ((5.0, 0.686), (10.0, 0.372))),
)
"""Share of the capacitance left under bias, as the model file of the block cites it."""


@bench(
    "models",
    "analog-rails-b0530w",
    "B0530W models against the datasheet",
    "the models of the Schottky diodes D6 to D9",
)
def b0530w(ctx: Context) -> Outcome:
    """Both variants of the diode model carry the currents of the datasheet table.

    A forced current gives the forward voltage, a forced reverse voltage the
    reverse current, and a small ramp on top of a reverse voltage the
    capacitance. The variant ``B0530W_HI`` has to sit on the largest forward
    voltage of the datasheet; the variant ``B0530W`` is the assumed typical
    part and has to stay below it.
    """
    lines = ["* forward voltage at the two currents of the datasheet, both variants"]
    for index, (amps, _) in enumerate(_FORWARD):
        lines += [
            f"It{index} 0 at{index} {amps:g}",
            f"Dt{index} at{index} 0 B0530W",
            f"Ih{index} 0 ah{index} {amps:g}",
            f"Dh{index} ah{index} 0 B0530W_HI",
        ]
    lines += [
        "* the clamp current of the rails",
        "Ic 0 ac 5m",
        "Dc ac 0 B0530W",
        "Ich 0 ach 5m",
        "Dch ach 0 B0530W_HI",
        "* reverse current",
        "Vr15 r15 0 15",
        "Dr15 0 r15 B0530W",
        "Vr30 r30 0 30",
        "Dr30 0 r30 B0530W",
    ]
    static = ctx.run(
        "static",
        ctx.deck(
            "B0530W: forward voltage and reverse current",
            "\n".join(lines),
            control=["op"],
            libraries=_LIBRARY,
        ),
    )
    figures: list[Figure] = []
    for index, (amps, limit) in enumerate(_FORWARD):
        figures += [
            near(
                f"vf_max_{index}",
                f"Largest-drop variant: forward voltage at {amps:g} A",
                float(static.real(f"ah{index}")[0]),
                "V",
                limit,
                0.01,
                "datasheet DS30139 page 2, maximum",
            ),
            Figure(
                f"vf_typ_{index}",
                f"Typical variant: forward voltage at {amps:g} A",
                float(static.real(f"at{index}")[0]),
                "V",
                high=limit,
                source="datasheet DS30139 page 2, maximum; the typical value is an assumption",
            ),
        ]
    figures += [
        Figure(
            "vf_clamp", "Typical variant: forward voltage at 5 mA", float(static.real("ac")[0]), "V"
        ),
        Figure(
            "vf_clamp_max",
            "Largest-drop variant: forward voltage at 5 mA",
            float(static.real("ach")[0]),
            "V",
        ),
        Figure(
            "ir_15",
            "Typical variant: reverse current at 15 V",
            abs(float(static.real("vr15#branch")[0])),
            "A",
            high=20e-6,
            source="datasheet DS30139 page 2, maximum",
        ),
        Figure(
            "ir_30",
            "Typical variant: reverse current at 30 V",
            abs(float(static.real("vr30#branch")[0])),
            "A",
            high=130e-6,
            source="datasheet DS30139 page 2, maximum",
        ),
    ]
    lines = ["* capacitance: a ramp of 1 V/us on top of a reverse voltage; the current is C dV/dt"]
    for index, (volts, _) in enumerate(_CAPACITANCE):
        lines += [
            f"Vc{index} k{index} 0 PWL(0 {volts:g} 1u {volts:g} 1.02u {volts + 0.02:g})",
            f"Dcap{index} 0 k{index} B0530W",
        ]
    ramp = ctx.run(
        "capacitance",
        ctx.deck(
            "B0530W: capacitance",
            "\n".join(lines),
            control=["tran 0.1n 1.03u 0 0.2n"],
            libraries=_LIBRARY,
        ),
    )
    time = ramp.real("time")
    traces = []
    for index, (volts, expected) in enumerate(_CAPACITANCE):
        current = ramp.real(f"vc{index}#branch")
        farads = -measure.mean(time, current, 1.005e-6, 1.015e-6) / 1e6
        figures.append(
            near(
                f"c_{index}",
                f"Capacitance at {volts:g} V of reverse voltage",
                farads,
                "F",
                expected,
                0.15,
                "datasheet DS30139 page 2 (0 V) and figure 4",
            )
        )
        traces.append(Trace(time * 1e6, -current * 1e6, f"{volts:g} V", 0))
    graph = Graph(
        name="capacitance",
        title="B0530W: current while the reverse voltage rises by 1 V/us",
        xlabel="Time (us)",
        panels=(Panel("Current (uA), equal to the capacitance in pF"),),
        traces=tuple(traces),
    )
    notes = (
        "The typical forward voltage is an assumption 40 mV and 20 mV below the datasheet "
        "maximum: figure 2 of the datasheet does not agree with its table and was not used.",
        "The reverse current of the model is flat with the voltage and that of the "
        "largest-drop variant is far below a real part: no leakage figure may be taken "
        "from these models.",
    )
    return Outcome(tuple(figures), (graph,), notes)


@bench(
    "models",
    "analog-rails-mlcc",
    "Ceramic capacitor with its loss under bias against the cited curves",
    "the model of C18 to C22 and C27 to C31 in the runs of the analog rails",
)
def mlcc(ctx: Context) -> Outcome:
    """A constant current charges each capacitor model and the slope gives its capacitance.

    The capacitance at a voltage is the current divided by the slope of the
    voltage there. It is compared with the share that the model file cites
    for each part number. A second circuit charges the 4.7 uF part with the
    2 mA of the fast start-up of the +12V_A regulator, which is where the
    18 ms of the specification come from.
    """
    lines = ["* each capacitor is charged with 1 mA"]
    for index, (_, farads, half, _) in enumerate(_BIAS):
        lines += [
            f"I{index} 0 n{index} PULSE(0 1m 1m 1u 1u 10 20)",
            f"X{index} n{index} 0 RAILS_MLCC c={farads:g} v0={half:g}",
            f"R{index} n{index} 0 1e9",
        ]
    lines += [
        "* the SET capacitor with the 2 mA of the fast start-up",
        "Iset 0 nset PULSE(0 2m 1m 1u 1u 10 20)",
        "Xset nset 0 RAILS_MLCC c=4.7u v0=8",
        "Rset nset 0 1e9",
    ]
    run = ctx.run(
        "charge",
        ctx.deck(
            "Ceramic capacitors: charge with a constant current",
            "\n".join(lines),
            control=["tran 50u 0.3 0 50u"],
            libraries=_LIBRARY,
        ),
    )
    time = run.real("time")
    figures: list[Figure] = []
    traces = []
    for index, (label, farads, _, points) in enumerate(_BIAS):
        volts = run.real(f"n{index}")
        slope = np.gradient(volts, time)
        for at, share in points:
            instant = measure.first_crossing(time, volts, at, rising=True)
            now = 1e-3 / float(np.interp(instant, time, slope))
            figures.append(
                near(
                    f"c{index}_{at:g}".replace(".", "p"),
                    f"{label}: share of the capacitance left at {at:g} V",
                    now / farads,
                    "",
                    share,
                    0.08,
                    "bias curve of the part as the model file cites it",
                )
            )
        shown = (volts <= 16.0) & (slope > 0.0)
        traces.append(Trace(volts[shown], 1e-3 / slope[shown] / farads * 100.0, label, 0))
    reached = measure.first_crossing(time, run.real("nset"), 11.0, rising=True) - 1e-3
    figures.append(
        near(
            "set_11v",
            "4.7 uF part charged with 2 mA: time to 11 V",
            reached,
            "s",
            18e-3,
            0.05,
            "rule F-3 of the specification: +12V_A at 11 V after 18 ms",
        )
    )
    graph = Graph(
        name="bias",
        title="Capacitance left under bias",
        xlabel="Voltage (V)",
        panels=(Panel("Share of the nominal capacitance (%)"),),
        traces=tuple(traces),
    )
    notes = (
        "The model is one law, capacitance = nominal / (1 + (V / v0)^2), with v0 fitted "
        "per part number. The points it is compared with were read from the part pages "
        "of the manufacturer by the power input block; they were not read again here.",
        "Temperature, aging and the amplitude of the ripple are not in the model.",
    )
    return Outcome(tuple(figures), (graph,), notes)


@bench(
    "models",
    "analog-rails-detector",
    "803-type voltage detector model against its datasheet",
    "the model of the voltage detector at the position U9, which is not fitted",
)
def detector(ctx: Context) -> Outcome:
    """The supply of the detector rises, dips for 10 us, dips for 100 us and falls.

    The output is pulled up to the supply through 51 kohm, as R29 does on
    the board. The run gives the threshold, the time the output stays low
    after the supply has returned, and shows that a dip shorter than the
    20 us of the datasheet is passed over while a longer one starts the
    time again.
    """
    lines = [
        "Vdd vdd 0 PWL(0 0 10m 5 0.4 5 0.400001 2.9 0.40001 2.9 0.400011 5 "
        "0.5 5 0.500001 2.9 0.5001 2.9 0.500101 5 0.9 5 1.0 2.5)",
        "X1 0 out vdd RAILS_803",
        "Rpull vdd out 51k",
    ]
    run = ctx.run(
        "sequence",
        ctx.deck(
            "803-type detector: threshold, time-out, short and long dips",
            "\n".join(lines),
            control=["tran 100u 1.0 0 100u"],
            libraries=_LIBRARY,
        ),
    )
    time = run.real("time")
    supply, out = run.real("vdd"), run.real("out")
    passed = measure.first_crossing(time, supply, 3.08, rising=True)
    released = measure.first_crossing(time, out, 2.5, rising=True)
    again = measure.first_crossing(time, out, 2.5, rising=True, after=0.5)
    fell = measure.first_crossing(time, out, 1.0, rising=False, after=0.9)
    during = (time > 0.3999) & (time < 0.45)
    short_dip = float(np.min(out[during]))
    figures = (
        near(
            "timeout",
            "Output released after the supply has passed 3.08 V",
            released - passed,
            "s",
            0.24,
            0.05,
            "datasheet DS39161 page 3: 240 ms typical (140 ms to 280 ms)",
        ),
        Figure(
            "short_dip",
            "Output during a dip of 10 us to 2.9 V: lowest level",
            short_dip,
            "V",
            low=2.5,
            source="datasheet DS39161 page 3: the part takes 20 us to answer, so the "
            "output only follows its pull-up down to 2.9 V",
        ),
        near(
            "restart",
            "Output released again after a dip of 100 us",
            again - 0.500101,
            "s",
            0.24,
            0.05,
            "datasheet DS39161 page 3: the timer starts again",
        ),
        near(
            "threshold",
            "Supply at which the output falls",
            float(np.interp(fell, time, supply)),
            "V",
            3.08,
            0.01,
            "datasheet DS39161 page 3: 3.08 V (3.04 V to 3.13 V)",
        ),
    )
    graph = Graph(
        name="sequence",
        title="803-type detector: supply and open-drain output with 51 kohm to the supply",
        xlabel="Time (s)",
        panels=(Panel("Voltage (V)"),),
        traces=(Trace(time, supply, "supply", 0), Trace(time, out, "output", 0)),
    )
    notes = (
        "The figures are those of the APX803S-31; the schematic names the position "
        '"803 type, 3.08 V" without a part number.',
        "The 20 us are taken for any depth of a dip; the datasheet gives them for a step "
        "to 100 mV below the threshold.",
    )
    return Outcome(figures, (graph,), notes)
