"""A logic input with a voltage it is not made for: +12 V, -12 V, a discharge."""

from __future__ import annotations

import numpy as np

from benches.digital import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench

_REFS = ("U38", "U36", "RN8", "RN11", "RN6", "C100", "C101")
"""The translator, the array of the lines D0 to D3 with their series and
pull-down networks, and the pull-downs of the 3.3 V side."""

_SERIES_OHMS = 330.0
"""Series resistor of a line, an element of RN8."""

_PIN_HIGH = 6.5
"""Highest voltage a pin of the translator is rated for (TI SCES584D, page 6)."""

_PIN_CLAMP_AMPS = 0.050
"""Largest current in the clamp of a translator input below ground (TI SCES584D, page 6)."""

_HBM_AMPS = 4000.0 / 1500.0
"""Peak current of the 4 kV human body model that the translator is rated
for (TI SCES584D, page 6): 4 kV through 1.5 kohm."""

_ARRAY_VOLTS = 5.5
"""Highest voltage at a line of the array in operation (TI SLVSBQ9D, page 4)."""

_STRIKE = 5e-9
"""Instant at which the discharge starts."""

_KILOVOLTS = 8.0
"""Level of the contact discharge (specification, section 4.8)."""


def _discharge(node: str, sign: int) -> str:
    """The current of a contact discharge of IEC 61000-4-2 into a node."""
    scale = sign * _KILOVOLTS / 4.0
    return "\n".join(
        [
            "* contact discharge as a current source: two pulses that give 3.75 A per",
            "* kilovolt at the first peak with 0.8 ns of rise, 2 A per kilovolt at",
            "* 30 ns and 1 A per kilovolt at 60 ns",
            f".param esd_t0={_STRIKE:g}",
            f".param esd_a1={scale * 16.6 / 0.3455106:g}",
            f".param esd_a2={scale * 9.3 / 0.4315466:g}",
            "Bx esd_x 0 V = max(time - esd_t0, 0)",
            "Rx esd_x 0 1",
            f"Besd 0 {node} I = esd_a1*pwr(v(esd_x)/1.1n, 1.8)/(1 + pwr(v(esd_x)/1.1n, 1.8))"
            "*exp(-v(esd_x)/2n) + esd_a2*pwr(v(esd_x)/12n, 1.8)/(1 + pwr(v(esd_x)/12n, 1.8))"
            "*exp(-v(esd_x)/37n)",
        ]
    )


def _steady_deck(ctx: Context, source_ohms: float, breakdown: float, title: str) -> str:
    """A source behind a resistor at line D0, stepped from -12 V to +12 V."""
    array = ctx.models.model_of(ctx.netlist.component("U36"))
    circuit = ctx.circuit(
        _REFS, common.ALIASES, overrides={"U36": common.with_params(array, vbr=breakdown)}
    )
    lines = [
        "* a source with its internal resistance at the connector pin of D0;",
        "* the translator supplies as ideal sources, the other lines open",
        "Vabuse src 0 0",
        f"Rsource src j_d0 {source_ohms:g}",
        "Vccb vccb 0 3.3",
        "Vlogic v3c 0 3.3",
    ]
    return ctx.deck(
        title, circuit, "\n".join(lines), control=["dc Vabuse -12 12 0.05"], options=("gmin=1e-13",)
    )


def _strike_deck(ctx: Context, sign: int, pin_clamp: bool, title: str) -> str:
    """A contact discharge of 8 kV into line D0; D1 open, D2 held low."""
    part = ctx.models.model_of(ctx.netlist.component("U38"))
    overrides = {"U38": common.with_params(part, vpos=_PIN_HIGH - 0.6)} if pin_clamp else {}
    circuit = ctx.circuit(_REFS, common.ALIASES, overrides=overrides)
    lines = [
        _discharge("j_d0", sign),
        "Vccb vccb 0 3.3",
        "Vlogic v3c 0 3.3",
        "* D2 is held low by a device under test with 50 ohm",
        "Rd2 j_d2 0 50",
    ]
    return ctx.deck(
        title,
        circuit,
        "\n".join(lines),
        control=["tran 0.01n 150n 0 0.05n"],
        options=("gmin=1e-13",),
    )


@bench(
    "digital",
    "logic-abuse",
    "A logic input at +12 V, at -12 V and under a contact discharge of 8 kV",
    "section 4.8 (D-50), section 4.9 (protection of the terminals)",
)
def logic_abuse(ctx: Context) -> Outcome:
    """Line D0 of the logic port meets voltages outside its range.

    A source behind 0.1 ohm, 100 ohm and 1 kohm is stepped from -12 V to
    +12 V at the connector, and the bench reads the voltage that the array
    leaves, the current it takes and the voltage at the translator pin
    behind 330 ohm. Then a contact discharge of 8 kV of either polarity is
    applied as the current of IEC 61000-4-2, once with a translator pin that
    takes no current above its rating and once with a pin that clamps at
    6.5 V, as the estimate of the specification assumes.
    """
    figures: list[Figure] = []
    cases = {
        "stiff": (0.1, 7.5),
        "100r": (100.0, 7.5),
        "1k": (1e3, 7.5),
        "1k-low": (1e3, 6.5),
        "1k-high": (1e3, 8.5),
    }
    sweeps = {}
    for name, (ohms, breakdown) in cases.items():
        title = (
            f"Logic line D0: a source behind {ohms:g} ohm stepped from -12 V to +12 V, "
            f"array breakdown {breakdown:g} V"
        )
        run = ctx.run(name, _steady_deck(ctx, ohms, breakdown, title), keep=name == "1k")
        sweeps[name] = (
            run.real("src"),
            run.real("j_d0"),
            run.real("b_d0"),
            -run.real("vabuse#branch"),
        )

    def at(name: str, column: int, volts: float) -> float:
        data = sweeps[name]
        return float(np.interp(volts, data[0], data[column]))

    for name, label in (("stiff", "0.1 ohm"), ("100r", "100 ohm"), ("1k", "1 kohm")):
        tag = name.replace("-", "_")
        figures.append(
            Figure(
                f"plus_array_amps_{tag}",
                f"+12 V behind {label}: current in the array",
                at(name, 3, 12.0),
                "A",
                source="TI SLVSBQ9D rates the array for surges of 8/20 us only: 3 A, 45 W",
            )
        )
        figures.append(
            Figure(
                f"plus_pin_{tag}",
                f"+12 V behind {label}: voltage at the translator pin",
                at(name, 2, 12.0),
                "V",
                high=_PIN_HIGH,
                source="TI SCES584D, page 6: 6.5 V at the most; the specification states "
                "no withstand voltage for the port",
            )
        )
        figures.append(
            Figure(
                f"minus_array_amps_{tag}",
                f"-12 V behind {label}: current in the array",
                -at(name, 3, -12.0),
                "A",
                source="TI SLVSBQ9D rates the array for surges of 8/20 us only: 3 A, 45 W",
            )
        )
        figures.append(
            Figure(
                f"minus_pin_amps_{tag}",
                f"-12 V behind {label}: current in the ground clamp of the translator pin",
                (at(name, 2, -12.0) - at(name, 1, -12.0)) / _SERIES_OHMS,
                "A",
                high=_PIN_CLAMP_AMPS,
                source="TI SCES584D, page 6: 50 mA in the clamp of an input below ground",
            )
        )
    figures.append(
        Figure(
            "plus_pin_low",
            "+12 V behind 1 kohm, array breakdown at its lower limit: translator pin",
            at("1k-low", 2, 12.0),
            "V",
            high=_PIN_HIGH,
            source="TI SCES584D, page 6: 6.5 V at the most",
        )
    )
    figures.append(
        Figure(
            "plus_pin_high",
            "+12 V behind 1 kohm, array breakdown at its upper limit: translator pin",
            at("1k-high", 2, 12.0),
            "V",
            high=_PIN_HIGH,
            source="TI SCES584D, page 6: 6.5 V at the most",
        )
    )
    volts = sweeps["1k"][0]
    reaches = float(np.interp(_PIN_HIGH, sweeps["1k-high"][2], sweeps["1k-high"][0]))
    figures.append(
        Figure(
            "pin_at_rating_from",
            "Source voltage from which the translator pin can stand above 6.5 V",
            reaches,
            "V",
            low=_ARRAY_VOLTS,
            source="TI SLVSBQ9D, page 4: a line of the array works up to 5.5 V",
        )
    )
    steady = Graph(
        name="steady",
        title="Line D0 with a source behind 1 kohm: what the array leaves",
        xlabel="Source voltage (V)",
        panels=(
            Panel("Connector pin and translator pin (V)", marks=((_PIN_HIGH, "pin rating 6.5 V"),)),
            Panel("Current in the array (mA)"),
        ),
        traces=(
            Trace(volts, sweeps["1k"][1], "connector pin, breakdown 7.5 V", 0),
            Trace(volts, sweeps["1k"][2], "translator pin, breakdown 7.5 V", 0, "--"),
            Trace(volts, sweeps["1k-high"][2], "translator pin, breakdown 8.5 V", 0, ":"),
            Trace(volts, sweeps["1k"][3] * 1e3, "source behind 1 kohm", 1),
        ),
    )
    strikes = {
        "plus-open": (+1, False),
        "plus-clamped": (+1, True),
        "minus": (-1, False),
    }
    waves = {}
    for name, (sign, pin_clamp) in strikes.items():
        title = (
            f"Logic line D0: contact discharge of {sign * _KILOVOLTS:+g} kV, translator pin "
            + ("with a clamp at 6.5 V (assumption)" if pin_clamp else "without a clamp of its own")
        )
        run = ctx.run(name, _strike_deck(ctx, sign, pin_clamp, title), keep=name != "plus-open")
        time = run.real("time")
        connector, pin = run.real("j_d0"), run.real("b_d0")
        waves[name] = (time, connector, pin, (connector - pin) / _SERIES_OHMS, run.real("j_d1"))
    time, connector, pin, series, neighbor = waves["plus-clamped"]
    figures += [
        Figure(
            "strike_array_30ns",
            "+8 kV: voltage at the array 30 ns after the start",
            measure.value_at(time, connector, _STRIKE + 30e-9),
            "V",
            expected=7.5 + 16.0,
            source="section 4.8, estimate behind the 50 mA: 7.5 V and 1 ohm at 16 A",
        ),
        Figure(
            "strike_pin_amps_peak",
            "+8 kV, pin clamps at 6.5 V: largest current through 330 ohm into the pin",
            float(np.max(series)),
            "A",
            expected=0.095,
            low=0.045,
            high=0.105,
            source="section 4.8: about 50 mA to 95 mA (estimate)",
        ),
        Figure(
            "strike_pin_amps_30ns",
            "+8 kV, pin clamps at 6.5 V: current into the pin 30 ns after the start",
            measure.value_at(time, series, _STRIKE + 30e-9),
            "A",
            expected=0.050,
            low=0.045,
            high=0.105,
            source="section 4.8: about 50 mA to 95 mA (estimate)",
        ),
        Figure(
            "strike_pin_amps_rating",
            "+8 kV, pin clamps at 6.5 V: largest current into the pin against its own rating",
            float(np.max(series)),
            "A",
            high=_HBM_AMPS,
            source="TI SCES584D, page 6: 4 kV human body model, 2.7 A through 1.5 kohm",
        ),
        Figure(
            "strike_pin_charge",
            "+8 kV, pin clamps at 6.5 V: charge into the pin in 150 ns",
            measure.integral(time, np.maximum(series, 0.0), _STRIKE, 150e-9),
            "C",
            high=100e-12 * 4000.0,
            source="TI SCES584D, page 6: 4 kV human body model, 100 pF at 4 kV",
        ),
    ]
    open_time, _, open_pin, _, _ = waves["plus-open"]
    above = open_pin > _PIN_HIGH
    figures += [
        Figure(
            "strike_open_pin_peak",
            "+8 kV, pin takes no current: highest voltage at the translator pin",
            float(np.max(open_pin)),
            "V",
            source="what the pin would have to stand without a clamp of its own",
        ),
        Figure(
            "strike_open_pin_time",
            "+8 kV, pin takes no current: time the pin stands above 6.5 V",
            float(np.sum(np.diff(open_time)[above[:-1]])),
            "s",
            source="what the pin would have to stand without a clamp of its own",
        ),
        Figure(
            "strike_neighbor",
            "+8 kV at D0: highest level at the open neighbor line D1",
            float(np.max(neighbor)),
            "V",
            source="the lines of an array share one clamp",
        ),
    ]
    _, _, pin_n, series_n, _ = waves["minus"]
    figures += [
        Figure(
            "minus_strike_pin_amps",
            "-8 kV: largest current in the ground clamp of the translator pin",
            float(np.max(-series_n)),
            "A",
            high=_HBM_AMPS,
            source="TI SCES584D, page 6: 4 kV human body model, 2.7 A through 1.5 kohm",
        ),
        Figure(
            "minus_strike_pin_volts",
            "-8 kV: lowest voltage at the translator pin",
            float(np.min(pin_n)),
            "V",
            source="TI SCES584D, page 6: below -0.5 V the current counts, 50 mA steady",
        ),
    ]
    nano = (time - _STRIKE) * 1e9
    strike = Graph(
        name="discharge",
        title="Contact discharge of +8 kV at D0, translator pin with a clamp at 6.5 V",
        xlabel="Time after the start of the discharge (ns)",
        panels=(
            Panel("Voltage (V)", marks=((_PIN_HIGH, "pin rating 6.5 V"),)),
            Panel("Current through 330 ohm into the pin (mA)"),
        ),
        traces=(
            Trace(nano, connector, "connector pin, at the array", 0),
            Trace(nano, pin, "translator pin", 0),
            Trace((open_time - _STRIKE) * 1e9, open_pin, "translator pin without a clamp", 0, "--"),
            Trace(nano, series * 1e3, "", 1),
        ),
    )
    notes = (
        "The specification states no withstand voltage for the logic port; the "
        "limits here are the ratings of the parts. A line that stands at +12 V "
        "leaves 7.5 V to 8.5 V and more at the translator pin, above its 6.5 V "
        "rating, whatever the source resistance: the array starts to conduct only "
        "above the rating of the pin, and the 330 ohm drop nothing while the pin "
        "takes no current. The array itself has no rating for a steady current; "
        "from a stiff source it carries amperes. The range of a line is 0 V to "
        "5.5 V.",
        "At -12 V the array carries the current of the source and the translator "
        "pin sees about -0.7 V behind 330 ohm; its clamp current stays below 50 mA.",
        "The discharge is the current waveform of IEC 61000-4-2 for 8 kV (30 A at "
        "the first peak, 16 A at 30 ns, 8 A at 60 ns), written from the figures of "
        "the standard as they are commonly quoted; the standard was not read for "
        "this bench. No inductance of the array, of its ground path or of the "
        "tracks is in the circuit, so the first peak at the connector is lower "
        "than the 145 V that the datasheet of the array shows on its test board.",
        "What the translator pin does above 6.5 V is not in its datasheet. With a "
        "clamp at 6.5 V (assumption) it takes the current that the specification "
        "estimates; without one it would stand at the voltage of the array for "
        "tens of nanoseconds. The pin has passed a human body test of 4 kV, which "
        "puts 30 times that current through it.",
    )
    return Outcome(tuple(figures), (steady, strike), notes)
