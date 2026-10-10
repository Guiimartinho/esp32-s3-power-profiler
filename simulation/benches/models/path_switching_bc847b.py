"""The BC847B model against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import Circuit

_REF = "Q7"
"""The part of the schematic that stands for its type."""

_DOCUMENT = "Diodes Incorporated DS11108 Rev. 28-2"
"""The datasheet the figures are taken from."""

_SWEEP_AMPS = np.logspace(-5, np.log10(0.2), 44)
"""Collector currents of the gain curve: 10 uA to 200 mA."""

_FORCED_GAIN = 20.0
"""Ratio of collector to base current of the saturation curve (figure 6)."""

_TEST_HERTZ = 100e6
"""Frequency at which the datasheet states the transition frequency."""


def _device(ctx: Context) -> Circuit:
    """The transistor alone, on the nodes c, b and e."""
    found = ctx.netlist.component(_REF)
    aliases = {found.net_of("C"): "c", found.net_of("B"): "b", found.net_of("E"): "e"}
    return ctx.circuit([_REF], aliases)


def _active_deck(ctx: Context) -> str:
    """Collector current forced at 5 V between collector and emitter, stepped."""
    stimulus = "\n".join(
        [
            "* the collector current is forced; an ideal amplifier drives the base",
            "* until the collector stands at 5 V",
            "Ve e 0 0",
            "V5 v5 0 5",
            "Ic 0 c 2m",
            "Eservo drive 0 c v5 1e4",
            "Vib drive b 0",
        ]
    )
    points = " ".join(f"{amps:.6g}" for amps in _SWEEP_AMPS)
    control = ["foreach level 2m 10m " + points, "  alter Ic dc = $level", "  op", "end"]
    return ctx.deck(
        "BC847B: gain and base-emitter voltage", _device(ctx), stimulus, control=control
    )


def _saturation_deck(ctx: Context) -> str:
    """Collector and base current both forced, stepped."""
    stimulus = "\n".join(
        [
            "* both currents are forced: the collector settles at its saturation voltage",
            "Ve e 0 0",
            "Ic 0 c 10m",
            "Ib 0 b 0.5m",
        ]
    )
    pairs = [(10e-3, 0.5e-3), (100e-3, 5e-3), (0.2e-3, 0.2e-3)]
    pairs += [
        (float(amps), float(amps) / _FORCED_GAIN) for amps in _SWEEP_AMPS[_SWEEP_AMPS >= 1e-4]
    ]
    control = []
    for collector, base in pairs:
        control += [f"alter Ic dc = {collector:.6g}", f"alter Ib dc = {base:.6g}", "op"]
    return ctx.deck("BC847B: saturation", _device(ctx), stimulus, control=control)


def _capacitance_deck(ctx: Context) -> str:
    """Output capacitance: emitter open, 10 V between collector and base."""
    stimulus = "\n".join(
        [
            "* as the datasheet measures it: base grounded, emitter open, 1 MHz",
            "Vb b 0 0",
            "Re e 0 1e12",
            "Vc c 0 dc 10 ac 1",
        ]
    )
    return ctx.deck(
        "BC847B: output capacitance", _device(ctx), stimulus, control=["ac lin 1 1meg 1meg"]
    )


def _transit_deck(ctx: Context, base_amps: float) -> str:
    """Current gain at 100 MHz with 10 mA of collector current at 5 V."""
    stimulus = "\n".join(
        [
            "* collector held at 5 V; the base takes its bias and the test current",
            "Ve e 0 0",
            "Vc c 0 5",
            f"Ib 0 b dc {base_amps:.6g} ac 1",
        ]
    )
    return ctx.deck(
        "BC847B: transition frequency",
        _device(ctx),
        stimulus,
        control=[f"ac lin 1 {_TEST_HERTZ:g} {_TEST_HERTZ:g}"],
    )


@bench(
    "models",
    "path-switching-bc847b",
    "BC847B model against its datasheet",
    "the model of the hold-off transistors Q6 and Q7",
)
def bc847b(ctx: Context) -> Outcome:
    """The transistor Q7 of the schematic is put in the test circuits of its datasheet.

    A forced collector current at 5 V gives the gain and the base-emitter
    voltage, forced collector and base currents give the saturation
    voltages, and two small-signal runs give the output capacitance and the
    transition frequency. The last saturation point has equal base and
    collector current, which is how the transistor works when it holds a
    mode pair open.
    """
    active = ctx.run("active", _active_deck(ctx))

    def at(step: int) -> tuple[float, float]:
        """Gain and base-emitter voltage of one step of the first run."""
        plot = f"op{step}"
        collector = (2e-3, 10e-3, *_SWEEP_AMPS)[step - 1]
        base = float(active.real("vib#branch", plot=plot)[0])
        return collector / base, float(active.real("b", plot=plot)[0])

    gain_2ma, vbe_2ma = at(1)
    gain_10ma, _ = at(2)
    curve = np.array([at(step + 3)[0] for step in range(_SWEEP_AMPS.size)])

    saturation = ctx.run("saturation", _saturation_deck(ctx))

    def sat(step: int) -> tuple[float, float]:
        plot = f"op{step}"
        return (
            float(saturation.real("c", plot=plot)[0]),
            float(saturation.real("b", plot=plot)[0]),
        )

    vce_10, vbe_10 = sat(1)
    vce_100, vbe_100 = sat(2)
    vce_hold, _ = sat(3)
    sat_amps = _SWEEP_AMPS[_SWEEP_AMPS >= 1e-4]
    sat_curve = np.array([sat(step + 4)[0] for step in range(sat_amps.size)])

    capacitance = ctx.run("capacitance", _capacitance_deck(ctx))
    cobo = float(-np.imag(capacitance.vector("vc#branch")[0]) / (2.0 * np.pi * 1e6))
    transit = ctx.run("transit", _transit_deck(ctx, 10e-3 / gain_10ma))
    h21 = abs(complex(transit.vector("vc#branch")[0]))
    figures = (
        Figure(
            "gain_2ma",
            "Current gain at 2 mA and 5 V",
            gain_2ma,
            "",
            expected=290.0,
            low=200.0,
            high=450.0,
            source=f"{_DOCUMENT}, page 4",
        ),
        Figure(
            "vbe_2ma",
            "Base-emitter voltage at 2 mA and 5 V",
            vbe_2ma,
            "V",
            expected=0.660,
            low=0.580,
            high=0.700,
            source=f"{_DOCUMENT}, page 4",
        ),
        Figure(
            "vce_sat_10ma",
            "Saturation voltage at 10 mA with 0.5 mA of base current",
            vce_10,
            "V",
            expected=0.090,
            high=0.250,
            source=f"{_DOCUMENT}, page 4: 90 mV typical, 250 mV at most",
        ),
        Figure(
            "vce_sat_100ma",
            "Saturation voltage at 100 mA with 5 mA of base current",
            vce_100,
            "V",
            expected=0.200,
            high=0.600,
            source=f"{_DOCUMENT}, page 4: 200 mV typical, 600 mV at most",
        ),
        Figure(
            "vbe_sat_10ma",
            "Base-emitter voltage at 10 mA with 0.5 mA of base current",
            vbe_10,
            "V",
            expected=0.700,
            low=0.665,
            high=0.735,
            source=f"{_DOCUMENT}, page 4, typical; 5 % asked of the fit",
        ),
        Figure(
            "vbe_sat_100ma",
            "Base-emitter voltage at 100 mA with 5 mA of base current",
            vbe_100,
            "V",
            expected=0.900,
            low=0.855,
            high=0.945,
            source=f"{_DOCUMENT}, page 4, typical; 5 % asked of the fit",
        ),
        Figure(
            "output_capacitance",
            "Output capacitance at 10 V, emitter open",
            cobo,
            "F",
            expected=3e-12,
            low=2.25e-12,
            high=3.75e-12,
            source=f"{_DOCUMENT}, page 4, typical; 25 % asked of the fit",
        ),
        Figure(
            "transition_frequency",
            "Transition frequency at 10 mA and 5 V",
            h21 * _TEST_HERTZ,
            "Hz",
            expected=300e6,
            low=100e6,
            source=f"{_DOCUMENT}, page 4: 300 MHz typical, 100 MHz at least",
        ),
        Figure(
            "gain_100ma",
            "Current gain at 100 mA and 5 V",
            float(np.interp(0.1, _SWEEP_AMPS, curve)),
            "",
            expected=100.0,
            source=f"{_DOCUMENT}, page 5, figure 5, read from the curve of the type family",
        ),
        Figure(
            "gain_10ua",
            "Current gain at 10 uA and 5 V",
            float(curve[0]),
            "",
            source="not in the datasheet: an assumption of the model",
        ),
        Figure(
            "vce_hold",
            "Saturation voltage with 0.2 mA in the base and in the collector",
            vce_hold,
            "V",
            source="the state of the hold-off of a mode pair at -20 V",
        ),
    )
    graph = Graph(
        name="curves",
        title="BC847B: gain at 5 V and saturation voltage at 20 times the base current",
        xlabel="Collector current (mA)",
        panels=(
            Panel("Current gain", marks=((200.0, "least at 2 mA"), (450.0, "most at 2 mA"))),
            Panel("Saturation voltage (mV)"),
        ),
        traces=(
            Trace(_SWEEP_AMPS * 1e3, curve, "", 0),
            Trace(sat_amps * 1e3, sat_curve * 1e3, "", 1),
        ),
        logx=True,
    )
    notes = (
        "The limits of the gain, of the base-emitter voltage and of the saturation "
        "voltages are those of the datasheet; the limits of the typical figures are "
        "the fit this project asks of a model.",
        "The gain below 1 mA is an assumption: the datasheet states the gain at 2 mA "
        "only. The benches of the reversed supply run the two variants of the model "
        "with the least and the highest gain of the datasheet as well.",
        "The model has no breakdown and no leakage: the benches compare the simulated "
        "voltages with the ratings (45 V collector to emitter, 6 V emitter to base).",
    )
    return Outcome(figures, (graph,), notes)
