"""The BAT54S model against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_DOCUMENT = "onsemi BAT54SLT1/D rev. 18, page 2"

_TYPICAL = {0.1e-3: 0.22, 1e-3: 0.29, 10e-3: 0.35, 30e-3: 0.41, 100e-3: 0.52}
"""Typical forward voltage by forward current at 25 C."""

_MAXIMUM = {0.1e-3: 0.24, 1e-3: 0.32, 10e-3: 0.40, 30e-3: 0.50, 100e-3: 0.80}
"""Largest forward voltage by forward current at 25 C."""

_BY_TEMPERATURE = {-40.0: 0.335, 85.0: 0.125}
"""Forward voltage at 0.1 mA by temperature, read from figure 2 on page 3."""

_FIT = 0.08
"""Fit this project asks of the typical model: 8 % of the forward voltage."""


def _deck(ctx: Context, celsius: float) -> str:
    """A voltage across the three variants of the model, stepped from 0 V to 0.7 V."""
    lines = [
        "* one diode of each variant, each behind a 0 V source that reads its current",
        "Vd a 0 0",
        "Vt a t 0",
        "Dt t 0 DIGITAL_BAT54S",
        "Vh a h 0",
        "Dh h 0 DIGITAL_BAT54S_HI",
        "* the reverse current at 25 V and the capacitance at 1 V",
        "Vr r 0 25",
        "Dr 0 r DIGITAL_BAT54S",
        "Vl l 0 25",
        "Dl 0 l DIGITAL_BAT54S_LEAKY",
        "Vc c 0 DC 1 AC 1",
        "Dc 0 c DIGITAL_BAT54S",
    ]
    return ctx.deck(
        f"BAT54S: forward curve, reverse current and capacitance at {celsius:g} C",
        "\n".join(lines),
        control=["dc Vd 0 0.7 0.002", "ac lin 1 1e6 1e6"],
        options=(f"temp={celsius:g}", "gmin=1e-15"),
        libraries=("digital.lib",),
    )


def _volts_at(current: np.ndarray, volts: np.ndarray, amps: float) -> float:
    """The forward voltage at one current, interpolated on a logarithmic axis."""
    shown = current > 1e-9
    return float(np.interp(np.log(amps), np.log(current[shown]), volts[shown]))


@bench(
    "models",
    "digital-bat54s",
    "BAT54S model against its datasheet",
    "the model of the clamp D24 of the translator supply",
)
def bat54s(ctx: Context) -> Outcome:
    """A voltage is stepped across one diode of each variant of the model.

    The forward voltage at the currents of the datasheet table is read from
    the typical variant and from the variant fitted to the maxima. The run
    is repeated at -40 C and at 85 C, where the datasheet gives a curve and
    no table. The reverse current at 25 V and the capacitance at 1 V are
    read at 27 C.
    """
    figures: list[Figure] = []
    traces: list[Trace] = []
    for celsius in (27.0, -40.0, 85.0):
        tag = f"{celsius:g}c".replace("-", "m")
        run = ctx.run(tag, _deck(ctx, celsius), keep=celsius == 27.0)
        volts = run.real("a", plot="dc")
        typical = run.real("vt#branch", plot="dc")
        highest = run.real("vh#branch", plot="dc")
        shown = typical > 1e-6
        traces.append(Trace(volts[shown], typical[shown] * 1e3, f"typical, {celsius:g} C", 0))
        if celsius == 27.0:
            traces.append(
                Trace(volts[shown], highest[shown] * 1e3, "at the maximum, 27 C", 0, "--")
            )
            for amps, expected in _TYPICAL.items():
                figures.append(
                    near(
                        f"typical_{amps * 1e3:g}ma".replace(".", "p"),
                        f"Typical variant: forward voltage at {amps * 1e3:g} mA",
                        _volts_at(typical, volts, amps),
                        "V",
                        expected,
                        _FIT,
                        _DOCUMENT + ", typical",
                    )
                )
            for amps, limit in _MAXIMUM.items():
                figures.append(
                    Figure(
                        f"maximum_{amps * 1e3:g}ma".replace(".", "p"),
                        f"Variant at the maximum: forward voltage at {amps * 1e3:g} mA",
                        _volts_at(highest, volts, amps),
                        "V",
                        expected=limit,
                        low=_TYPICAL[amps],
                        high=limit * 1.05,
                        source=_DOCUMENT + ", maximum; between typical and 5 % above it",
                    )
                )
            reverse = float(run.real("vr#branch", plot="dc")[0])
            leaky = float(run.real("vl#branch", plot="dc")[0])
            figures.append(
                Figure(
                    "reverse_typical",
                    "Typical variant: reverse current at 25 V",
                    abs(reverse),
                    "A",
                    expected=0.15e-6,
                    high=2e-6,
                    source=_DOCUMENT + ": 0.15 uA typical, 2 uA at the most",
                )
            )
            figures.append(
                near(
                    "reverse_leaky",
                    "Leaky variant: reverse current at 25 V",
                    abs(leaky),
                    "A",
                    2e-6,
                    0.10,
                    _DOCUMENT + ", maximum",
                )
            )
            admittance = run.vector("vc#branch", plot="ac")
            farads = abs(float(np.imag(admittance[0]))) / (2.0 * np.pi * 1e6)
            figures.append(
                near(
                    "capacitance_1v",
                    "Capacitance at 1 V and 1 MHz",
                    farads,
                    "F",
                    7.6e-12,
                    0.10,
                    _DOCUMENT + ", typical",
                )
            )
        else:
            figures.append(
                near(
                    f"forward_{tag}",
                    f"Typical variant: forward voltage at 0.1 mA and {celsius:g} C",
                    _volts_at(typical, volts, 0.1e-3),
                    "V",
                    _BY_TEMPERATURE[celsius],
                    0.10,
                    "onsemi BAT54SLT1/D rev. 18, page 3, figure 2 (read from the graph)",
                )
            )
    graph = Graph(
        name="forward",
        title="BAT54S: forward current of the model against its voltage",
        xlabel="Forward voltage (V)",
        panels=(Panel("Forward current (mA)", log=True),),
        traces=tuple(traces),
    )
    notes = (
        "The limits of the typical variant are the fit this project asks of a model, "
        "8 % of the forward voltage; they are not datasheet limits.",
        "The variant at the maximum is fitted to the largest forward voltage at 1 mA "
        "and 10 mA, the range in which the clamp works. At 30 mA and 100 mA it stays "
        "below the maximum of the datasheet.",
        "The reverse current of the typical variant is its saturation current and "
        "does not rise with the voltage as the datasheet curve does: 20 nA against "
        "0.15 uA at 25 V. The leaky variant carries the maximum of 2 uA; its forward "
        "voltage is too low and is not used.",
    )
    return Outcome(tuple(figures), (graph,), notes)
