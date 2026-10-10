"""A logic input from the connector to the side data register."""

from __future__ import annotations

import numpy as np

from benches.digital import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_REFS = (
    "U38",
    "U36",
    "U37",
    "RN8",
    "RN9",
    "RN10",
    "RN11",
    "RN6",
    "RN7",
    "U33",
    "C98",
    "C100",
    "C101",
)
"""The translator, the two arrays, the series and pull-down networks of the
eight lines, the pull-downs of the 3.3 V side and the register that reads them."""

_SUPPLIES = {
    1.65: (0.35 * 1.65, 0.65 * 1.65, 20.0, 7.2e-9),
    1.8: (0.35 * 1.8, 0.65 * 1.8, 20.0, 7.2e-9),
    3.3: (0.8, 2.0, 10.0, 6.1e-9),
    5.0: (0.3 * 5.0, 0.7 * 5.0, 5.0, 6.0e-9),
    5.5: (0.3 * 5.5, 0.7 * 5.5, 5.0, 6.0e-9),
}
"""By supply of the user side: highest low level and lowest high level of an
input, largest transition time per volt that the input allows (TI SCES584D,
page 7), largest delay to the 3.3 V side (page 11)."""

_STATED_RATE = {1.8: 9.2, 3.3: 5.0, 5.0: 3.3}
"""Upper end of the edge rates that section 4.8 states, in ns/V."""

_RISE = 20e-9
"""Instant of the rising edge of the device under test."""

_FALL = 200e-9
"""Instant of its falling edge."""

_END = 400e-9

_PIN_FARADS = 10e-12
"""Largest capacitance of a translator pin (TI SCES584D, page 9)."""

_REGISTER_HIGH = 0.7 * common.LOGIC_VOLTS
"""Lowest high level of a register input (TI SCLS402R, page 5)."""

_REGISTER_LOW = 0.3 * common.LOGIC_VOLTS
"""Highest low level of a register input (TI SCLS402R, page 5)."""

_SAMPLE_PERIOD = 10e-6
"""One sample at 100 kSPS (specification, section 12, test of R-10)."""


def _deck(ctx: Context, vccb: float, delay: float, title: str) -> str:
    part = ctx.models.model_of(ctx.netlist.component("U38"))
    circuit = ctx.circuit(
        _REFS,
        common.ALIASES,
        overrides={"U38": common.with_params(part, cio=_PIN_FARADS, tpd=delay)},
    )
    lines = [
        "* the translator supply and the 3.3 V rail as ideal sources; the register",
        "* is held loading, as with the pins of the controller released",
        f"Vccb vccb 0 {vccb:g}",
        "Vlogic v3c 0 3.3",
        "Vload side_load 0 0",
        "Vclock adc_sck 0 0",
        "* D0: an edge of the device under test, an ideal source at the connector",
        f"Vd0 j_d0 0 PWL(0 0 {_RISE:g} 0 {_RISE + 0.5e-9:g} {vccb:g} {_FALL:g} {vccb:g} "
        f"{_FALL + 0.5e-9:g} 0)",
        "* D1 and D2: nothing connected; the translator pin leaks into the line at",
        "* the limit of its datasheet at 25 C and at the limit over temperature",
        "Ileak1 0 b_d1 1u",
        "Ileak2 0 b_d2 2u",
        "* D3: held high by the device under test, whose current is read",
        f"Vd3 j_d3 0 {vccb:g}",
        "* D4 to D7: held low",
        "Vd4 j_d4 0 0",
        "Vd5 j_d5 0 0",
        "Vd6 j_d6 0 0",
        "Vd7 j_d7 0 0",
    ]
    return ctx.deck(
        title,
        circuit,
        "\n".join(lines),
        control=[f"tran 0.05n {_END:g} 0 0.5n"],
        options=("gmin=1e-14",),
    )


def _unpowered_deck(ctx: Context) -> str:
    """The user side of the translator without supply and every line of the port high."""
    circuit = ctx.circuit(_REFS, common.ALIASES)
    lines = [
        "* the translator supply at 0 V; the device under test holds all lines at 5 V",
        "Vccb vccb 0 0",
        "Vlogic v3c 0 3.3",
        "Vload side_load 0 0",
        "Vclock adc_sck 0 0",
    ]
    lines += [f"Vd{index} j_d{index} 0 5" for index in range(8)]
    return ctx.deck(
        "Logic inputs with the translator supply at 0 V and all lines at 5 V",
        circuit,
        "\n".join(lines),
        control=["tran 0.1n 300n 0 1n"],
    )


@bench(
    "digital",
    "logic-input",
    "A logic input: edge, levels, open line, load on the device under test",
    "section 4.8 (D-50, D-79), section 4.7, requirement R-10",
)
def logic_input(ctx: Context) -> Outcome:
    """One line of the logic port is driven from the connector to the register.

    The supply of the user side is set to five values from 1.65 V to 5.5 V.
    Line D0 gets a clean edge of that height at the connector; the edge at
    the translator pin behind 330 ohm is read with the largest pin
    capacitance, and the delay to the register input with the largest
    delay of the translator. Lines D1 and D2 are open and carry the leakage
    limit of the translator pin, 1 uA and 2 uA. Line D3 is held high and
    the current that the device under test gives is read. A last run takes
    the supply of the user side away and holds all eight lines at 5 V.
    """
    figures: list[Figure] = []
    traces: list[Trace] = []
    for vccb, (low, high, rate_limit, delay) in _SUPPLIES.items():
        tag = f"{vccb:g}v".replace(".", "p")
        title = f"Logic input D0 with {vccb:g} V on the user side of the translator"
        run = ctx.run(tag, _deck(ctx, vccb, delay, title), keep=vccb == 3.3)
        time = run.real("time")
        pin, line = run.real("b_d0"), run.real("din0")
        tenth = measure.first_crossing(time, pin, 0.1 * vccb, rising=True)
        ninth = measure.first_crossing(time, pin, 0.9 * vccb, rising=True)
        t_low = measure.first_crossing(time, pin, low, rising=True)
        t_high = measure.first_crossing(time, pin, high, rising=True)
        figures.append(
            Figure(
                f"edge_{tag}",
                f"{vccb:g} V: edge at the translator pin, 10 % to 90 %, per volt",
                (ninth - tenth) / (0.8 * vccb) * 1e9,
                "ns/V",
                expected=_STATED_RATE.get(vccb),
                high=rate_limit,
                source=f"section 4.8: the translator allows {rate_limit:g} ns/V (datasheet)",
            )
        )
        figures.append(
            Figure(
                f"between_levels_{tag}",
                f"{vccb:g} V: time between the low and the high input level, per volt",
                (t_high - t_low) / (high - low) * 1e9,
                "ns/V",
                high=rate_limit,
                source=f"section 4.8: the translator allows {rate_limit:g} ns/V (datasheet)",
            )
        )
        rises = measure.first_crossing(time, line, _REGISTER_HIGH, rising=True)
        falls = measure.first_crossing(time, line, _REGISTER_LOW, rising=False, after=_FALL)
        figures.append(
            Figure(
                f"delay_{tag}",
                f"{vccb:g} V: edge at the connector to a valid level at the register, slower edge",
                max(rises - _RISE, falls - _FALL),
                "s",
                high=_SAMPLE_PERIOD,
                source="section 12, test of R-10: edges aligned with the current within "
                "one sample, 10 us",
            )
        )
        settled = _FALL - 10e-9
        open_25 = measure.value_at(time, run.real("b_d1"), settled)
        open_hot = measure.value_at(time, run.real("b_d2"), settled)
        if vccb == 1.65:
            figures.append(
                Figure(
                    "open_1ua",
                    "Open line with 1 uA of pin leakage: level at the translator pin",
                    open_25,
                    "V",
                    expected=0.47,
                    high=low,
                    source="section 4.8: 0.47 V against a low level of 0.58 V at 1.65 V",
                )
            )
        if vccb in (3.3, 5.0):
            figures.append(
                Figure(
                    f"open_2ua_{tag}",
                    f"Open line with 2 uA of pin leakage against the low level at {vccb:g} V",
                    open_hot,
                    "V",
                    expected=0.94,
                    high=low if vccb >= 4.5 else None,
                    source="section 4.8: at 2 uA an open line reads 0 only from 4.5 V on"
                    if vccb >= 4.5
                    else f"section 4.8 states no limit here; the low level is {low:g} V",
                )
            )
        if vccb in (1.65, 3.3, 5.0):
            stated = {1.65: 3.5e-6, 3.3: 7.0e-6, 5.0: 10.6e-6}[vccb]
            figures.append(
                near(
                    f"load_{tag}",
                    f"Line held high at {vccb:g} V: current from the device under test",
                    -measure.value_at(time, run.real("vd3#branch"), settled),
                    "A",
                    stated,
                    0.03,
                    "section 4.8: the voltage across 470 kohm (calculated)",
                )
            )
        if vccb in (1.8, 3.3, 5.0):
            shown = time < 60e-9
            nano = time[shown] * 1e9
            traces.append(Trace(nano, np.asarray(pin[shown]), f"translator pin, {vccb:g} V", 0))
            traces.append(Trace(nano, np.asarray(line[shown]), f"register input, {vccb:g} V", 1))
    dead = ctx.run("unpowered", _unpowered_deck(ctx))
    highest = max(float(dead.real(f"din{index}")[-1]) for index in range(8))
    figures.append(
        Figure(
            "unpowered_lines",
            "User side without supply, all lines at 5 V: highest level at the register",
            highest,
            "V",
            high=_REGISTER_LOW,
            source="sections 4.7 and 4.8: all eight bits read 0",
        )
    )
    figures.append(
        Figure(
            "unpowered_current",
            "User side without supply: current that one line at 5 V takes",
            -float(dead.real("vd0#branch")[-1]),
            "A",
            expected=10.6e-6,
            high=12.6e-6,
            source="section 4.8: 10.6 uA in the pull-down; 2 uA of pin leakage allowed "
            "(TI SCES584D, page 9), which the model does not have",
        )
    )
    graph = Graph(
        name="edge",
        title="A clean edge at the connector, at the translator pin and at the register",
        xlabel="Time (ns)",
        panels=(Panel("Translator pin behind 330 ohm (V)"), Panel("Register input (V)")),
        traces=tuple(traces),
        xmarks=((_RISE * 1e9, "edge at the connector"),),
    )
    notes = (
        "The device under test is an ideal source with an edge of 0.5 ns: cable, "
        "source resistance and ringing are not in this circuit, and a slower edge "
        "of the device under test adds to the figures.",
        "The edge rates use the largest pin capacitance, 10 pF, and the delay the "
        "largest delay of the translator. The specification takes four to five "
        "time constants for the whole swing; this bench reads the 10 % to 90 % time, "
        "which is 2.2 time constants over 80 % of the swing, so its figures are "
        "about half of the stated ones.",
        "The threshold of the translator model is half its supply, an assumption "
        "inside the input levels of the datasheet. The open-line figures are "
        "compared with the highest low level, which does not depend on it.",
        "The leakage of an open line is a source of 1 uA and 2 uA at the translator "
        "pin, the limits of the datasheet; the arrays have no leakage in their "
        "model, so the load on a device under test is the pull-down alone.",
    )
    return Outcome(tuple(figures), (graph,), notes)
