"""The SN74LVC8T245 model against the figures of its datasheet."""

from __future__ import annotations

from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_DOCUMENT = "TI SCES584D"

_SUPPLIES = {
    1.65: (0.35 * 1.65, 0.65 * 1.65, 0.8e-9, 7.2e-9, 2e-12),
    1.8: (0.35 * 1.8, 0.65 * 1.8, 0.8e-9, 7.2e-9, 2e-12),
    2.5: (0.7, 1.7, 0.8e-9, 6.2e-9, 2e-12),
    3.3: (0.8, 2.0, 0.7e-9, 6.1e-9, 2e-12),
    5.0: (0.3 * 5.0, 0.7 * 5.0, 0.6e-9, 6.0e-9, 3e-12),
    5.5: (0.3 * 5.5, 0.7 * 5.5, 0.6e-9, 6.0e-9, 3e-12),
}
"""By supply of the B side: the highest low level, the lowest high level
(page 7), the limits of the delay B to A with 3.3 V on the A side (page 11)
and the power-dissipation capacitance of an input (page 11)."""

_EDGE = 100e-9
"""Instant of the rising edge of the delay test."""

_RAMP = (1e-6, 11e-6)
"""Start and end of the slow ramp that finds the threshold."""

_TOGGLE_HERTZ = 10e6
"""Frequency of the input that measures the supply current."""

_SERIES_OHMS = 330.0
"""Resistor in front of the third input, which shows its capacitance."""


def _deck(ctx: Context, vccb: float, cpd: float) -> str:
    half = 0.5 / _TOGGLE_HERTZ
    lines = [
        "* A side at 3.3 V; load of the datasheet, 15 pF and 2 kohm, at output 1",
        "Vcca vcca 0 3.3",
        f"Vccb vccb 0 {vccb:g}",
        f"X1 vcca 0 a1 a2 a3 a4 a5 a6 a7 a8 0 0 0 b8 b7 b6 b5 b4 b3 b2 b1 0 vccb vccb "
        f"DIGITAL_LVC8T245 cpd={cpd:g}",
        "* input 1: a fast edge from 50 ohm, then a slow ramp",
        f"V1 g1 0 PWL(0 0 {_EDGE:g} 0 {_EDGE + 1e-9:g} {vccb:g} 300n {vccb:g} 301n 0 "
        f"{_RAMP[0]:g} 0 {_RAMP[1]:g} {vccb:g})",
        "R1 g1 b1 50",
        "Cl a1 0 15p",
        "Rl a1 0 2k",
        "* input 2: a square wave, for the charge that an edge costs the supply",
        f"V2 b2 0 PULSE(0 {vccb:g} 10n 1n 1n {half - 1e-9:g} {2 * half:g})",
        "* input 3: an edge behind 330 ohm, for the capacitance of the pin",
        f"V3 g3 0 PWL(0 0 {_EDGE:g} 0 {_EDGE + 0.1e-9:g} {vccb:g})",
        f"R3 g3 b3 {_SERIES_OHMS:g}",
        "Rb4 b4 0 1k",
        "Rb5 b5 0 1k",
        "Rb6 b6 0 1k",
        "Rb7 b7 0 1k",
        "Rb8 b8 0 1k",
    ]
    return ctx.deck(
        f"SN74LVC8T245: B to A with {vccb:g} V on the B side",
        "\n".join(lines),
        control=["tran 0.05n 11.2u 0 0.5n"],
        libraries=("digital.lib",),
    )


def _static_deck(ctx: Context) -> str:
    """Output levels under load, the supply current at rest and the isolation."""
    lines = [
        "* output levels at 3.0 V with 24 mA, the test of the datasheet",
        "Vcca vcca 0 3.0",
        "Vccb vccb 0 3.3",
        "X1 vcca 0 a1 a2 a3 a4 a5 a6 a7 a8 0 0 0 b8 b7 b6 b5 b4 b3 b2 b1 0 vccb vccb "
        "DIGITAL_LVC8T245",
        "Vb1 b1 0 3.3",
        "Ih a1 0 24m",
        "Vb2 b2 0 0",
        "Il 0 a2 24m",
        "Rb3 b3 0 1k",
        "Rb4 b4 0 1k",
        "Rb5 b5 0 1k",
        "Rb6 b6 0 1k",
        "Rb7 b7 0 1k",
        "Rb8 b8 0 1k",
        "* a second part without supply on the B side: its output is open",
        "Vccd vccd 0 0",
        "X2 vcca 0 c1 c2 c3 c4 c5 c6 c7 c8 0 0 0 d8 d7 d6 d5 d4 d3 d2 d1 0 vccd vccd "
        "DIGITAL_LVC8T245",
        "Vd1 d1 0 3.3",
        "Rpull vcca c1 100k",
        "Rd2 d2 0 1k",
        "Rd3 d3 0 1k",
        "Rd4 d4 0 1k",
        "Rd5 d5 0 1k",
        "Rd6 d6 0 1k",
        "Rd7 d7 0 1k",
        "Rd8 d8 0 1k",
    ]
    return ctx.deck(
        "SN74LVC8T245: output levels, supply current at rest, isolation",
        "\n".join(lines),
        control=["op"],
        libraries=("digital.lib",),
    )


@bench(
    "models",
    "digital-sn74lvc8t245",
    "SN74LVC8T245 model against its datasheet",
    "the model of the level translator U38",
)
def sn74lvc8t245(ctx: Context) -> Outcome:
    """One part is run with six supplies on its B side and 3.3 V on its A side.

    An edge from 50 ohm into the load of the datasheet gives the delay, a
    slow ramp the threshold, a square wave of 10 MHz the charge that an
    input edge costs the supply of the B side, and an edge behind 330 ohm
    the capacitance of the pin. An operating point gives the output levels
    at 24 mA, the supply current at rest and the state of the output
    without supply on the B side.
    """
    figures: list[Figure] = []
    traces: list[Trace] = []
    for vccb, (low, high, fastest, slowest, cpd) in _SUPPLIES.items():
        tag = f"{vccb:g}v".replace(".", "p")
        run = ctx.run(tag, _deck(ctx, vccb, cpd), keep=vccb == 3.3)
        time = run.real("time")
        pin, out = run.real("b1"), run.real("a1")
        start = measure.first_crossing(time, pin, 0.5 * vccb, rising=True, after=_EDGE - 1e-9)
        delay = measure.first_crossing(time, out, 1.65, rising=True, after=start) - start
        flips = measure.first_crossing(time, out, 1.65, rising=True, after=_RAMP[0])
        threshold = measure.value_at(time, pin, flips - 3.3e-9)
        figures.append(
            Figure(
                f"threshold_{tag}",
                f"Input level at which the output changes, {vccb:g} V on the B side",
                threshold,
                "V",
                low=low,
                high=high,
                source=_DOCUMENT + ", page 7: between the low and the high input level",
            )
        )
        figures.append(
            Figure(
                f"delay_{tag}",
                f"Delay B to A into 15 pF and 2 kohm, {vccb:g} V on the B side",
                delay,
                "s",
                low=fastest,
                high=slowest,
                source=_DOCUMENT + ", page 11",
            )
        )
        supply = -run.real("vccb#branch")
        mean = measure.mean(time, supply, 0.4e-6, 0.9e-6)
        figures.append(
            near(
                f"dynamic_{tag}",
                f"Supply current of the B side for one input at 10 MHz, {vccb:g} V",
                mean - 8e-6,
                "A",
                cpd * vccb * _TOGGLE_HERTZ,
                0.10,
                _DOCUMENT + ", page 11: power-dissipation capacitance times voltage and frequency",
            )
        )
        if vccb in (1.8, 3.3, 5.0):
            shown = (time > _EDGE - 5e-9) & (time < _EDGE + 25e-9)
            nano = (time[shown] - _EDGE) * 1e9
            traces.append(Trace(nano, pin[shown], f"input, {vccb:g} V", 0))
            traces.append(Trace(nano, out[shown], f"output, B side at {vccb:g} V", 1))
        if vccb == 3.3:
            behind = run.real("b3")
            rise = measure.rise_time(time, behind, 0.1 * vccb, 0.9 * vccb, after=_EDGE - 1e-9)
            figures.append(
                Figure(
                    "pin_capacitance",
                    "Capacitance of an input pin, from its edge behind 330 ohm",
                    rise / (2.197 * _SERIES_OHMS),
                    "F",
                    expected=8.5e-12,
                    low=8.0e-12,
                    high=10e-12,
                    source=_DOCUMENT + ", page 9: 8.5 pF typical, 10 pF at the most",
                )
            )
    static = ctx.run("static", _static_deck(ctx))
    figures += [
        Figure(
            "output_high",
            "Output high with 24 mA at 3.0 V",
            float(static.real("a1")[0]),
            "V",
            low=2.4,
            source=_DOCUMENT + ", page 9: 2.4 V at the least",
        ),
        Figure(
            "output_low",
            "Output low with 24 mA at 3.0 V",
            float(static.real("a2")[0]),
            "V",
            high=0.55,
            source=_DOCUMENT + ", page 9: 0.55 V at the most",
        ),
        near(
            "supply_at_rest",
            "Supply current of the B side at rest",
            -float(static.real("vccb#branch")[0]),
            "A",
            8e-6,
            0.05,
            _DOCUMENT + ", page 9: 8 uA at the most",
        ),
        Figure(
            "isolated_output",
            "Output with 100 kohm to 3.0 V, input high, no supply on the B side",
            float(static.real("c1")[0]),
            "V",
            low=2.95,
            source=_DOCUMENT + ", page 15: outputs open with a supply below 0.1 V",
        ),
    ]
    graph = Graph(
        name="edges",
        title="SN74LVC8T245: an edge at the B side and the output of the A side",
        xlabel="Time after the edge of the generator (ns)",
        panels=(Panel("Input pin (V)"), Panel("Output pin (V)")),
        traces=tuple(traces),
    )
    notes = (
        "The threshold of the model is half the supply of the B side, an assumption "
        "inside the input levels of the datasheet. A real part may switch anywhere "
        "between the two levels; the benches of the logic inputs read both.",
        "The delay of the model is 3 ns plus the edge of its output, an assumption "
        "inside the limits of the datasheet; the benches set it to a limit where "
        "the result depends on it.",
        "The supply current at rest is set to the maximum of the datasheet, which "
        "gives no typical value.",
    )
    return Outcome(tuple(figures), (graph,), notes)
