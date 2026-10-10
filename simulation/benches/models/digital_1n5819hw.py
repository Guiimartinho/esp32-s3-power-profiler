"""The 1N5819HW model against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_DOCUMENT = "Diodes Incorporated DS30217 rev. 22-2, page 2"

_FORWARD_MOST = {0.1: 0.320, 1.0: 0.450}
"""Largest forward voltage by forward current at 25 C."""

_FORWARD_TYPICAL = {1e-3: 0.15, 0.1: 0.29, 1.0: 0.40}
"""Typical forward voltage by forward current, read from figure 1 on page 3."""

_LEAKY_OHMS = 87e3
"""Value of the leakage resistor that gives the largest reverse current of the datasheet."""


def _deck(ctx: Context, celsius: float) -> str:
    """Forward sweep of the diode, and reverse sweeps of the two leakage variants."""
    lines = [
        "* forward: a current is forced through the diode",
        "If 0 f 1m",
        "Xf f 0 DIGITAL_1N5819HW",
        "* reverse: the typical part and the part at the maximum of the datasheet",
        "Vr r 0 4",
        "Xt 0 r DIGITAL_1N5819HW",
        "Vq q 0 4",
        f"Xl 0 q DIGITAL_1N5819HW rleak={_LEAKY_OHMS:g}",
        "* capacitance at 4 V",
        "Vc c 0 DC 4 AC 1",
        "Xc 0 c DIGITAL_1N5819HW",
    ]
    points = " ".join(f"{amps:.4g}" for amps in np.logspace(-4, np.log10(3.0), 46))
    control = [
        f"foreach level {points}",
        "  alter If dc = $level",
        "  op",
        "end",
        "dc Vr 0.2 6 0.2",
        "dc Vq 0.2 6 0.2",
        "ac lin 1 1e6 1e6",
    ]
    return ctx.deck(
        f"1N5819HW: forward voltage, reverse current and capacitance at {celsius:g} C",
        "\n".join(lines),
        control=control,
        options=(f"temp={celsius:g}",),
        libraries=("digital.lib",),
    )


@bench(
    "models",
    "digital-1n5819hw",
    "1N5819HW model against its datasheet",
    "the model of the diode D1 from the 5 V rail to the module",
)
def diode_1n5819hw(ctx: Context) -> Outcome:
    """A current is forced through the diode and a reverse voltage is stepped across it.

    The forward voltage is compared with the maxima of the datasheet table
    and with its typical curve. The reverse current is read from the
    typical variant and from the variant whose leakage resistor is set to
    the maximum of the datasheet, at 4 V and at 6 V, and from the typical
    variant at 100 C.
    """
    amps = np.logspace(-4, np.log10(3.0), 46)
    run = ctx.run("27c", _deck(ctx, 27.0))
    forward = np.array(
        [float(run.real("f", plot=f"op{index + 1}")[0]) for index in range(amps.size)]
    )
    figures: list[Figure] = []
    for current, expected in _FORWARD_TYPICAL.items():
        figures.append(
            near(
                f"forward_{current * 1e3:g}ma",
                f"Forward voltage at {current * 1e3:g} mA",
                float(np.interp(np.log(current), np.log(amps), forward)),
                "V",
                expected,
                0.10,
                "Diodes Incorporated DS30217 rev. 22-2, page 3, figure 1 (read from the graph)",
            )
        )
    for current, limit in _FORWARD_MOST.items():
        figures.append(
            Figure(
                f"forward_limit_{current * 1e3:g}ma",
                f"Forward voltage at {current * 1e3:g} mA against the maximum",
                float(np.interp(np.log(current), np.log(amps), forward)),
                "V",
                high=limit,
                source=_DOCUMENT + ", maximum",
            )
        )
    plots = sorted(
        {key.split("/")[0] for key in run.vectors if key.startswith("dc")},
        key=lambda name: int(name[2:]),
    )
    typical_volts = run.real("r", plot=plots[0])
    typical = -run.real("vr#branch", plot=plots[0])
    leaky_volts = run.real("q", plot=plots[1])
    leaky = -run.real("vq#branch", plot=plots[1])
    for volts, usual, most in ((4.0, 10e-6, 50e-6), (6.0, 15e-6, 75e-6)):
        figures.append(
            Figure(
                f"reverse_typical_{volts:g}v",
                f"Typical variant: reverse current at {volts:g} V",
                float(np.interp(volts, typical_volts, typical)),
                "A",
                expected=usual,
                low=0.5 * usual,
                high=1.5 * usual,
                source=_DOCUMENT + ", typical; within 50 %",
            )
        )
        figures.append(
            near(
                f"reverse_leaky_{volts:g}v",
                f"Variant at the maximum: reverse current at {volts:g} V",
                float(np.interp(volts, leaky_volts, leaky)),
                "A",
                most,
                0.10,
                _DOCUMENT + ", maximum",
            )
        )
    admittance = run.vector("vc#branch", plot="ac")
    figures.append(
        near(
            "capacitance_4v",
            "Capacitance at 4 V and 1 MHz",
            abs(float(np.imag(admittance[0]))) / (2.0 * np.pi * 1e6),
            "F",
            50e-12,
            0.15,
            _DOCUMENT + ", typical",
        )
    )
    hot = ctx.run("100c", _deck(ctx, 100.0), keep=False)
    hot_plots = sorted(
        {key.split("/")[0] for key in hot.vectors if key.startswith("dc")},
        key=lambda name: int(name[2:]),
    )
    hot_volts = hot.real("r", plot=hot_plots[0])
    hot_amps = -hot.real("vr#branch", plot=hot_plots[0])
    figures.append(
        Figure(
            "reverse_100c",
            "Typical variant: reverse current at 4 V and 100 C",
            float(np.interp(4.0, hot_volts, hot_amps)),
            "A",
            expected=1e-3,
            low=0.5e-3,
            high=2e-3,
            source=_DOCUMENT + ": 1 mA typical, 2 mA at the most",
        )
    )
    reverse = Graph(
        name="reverse",
        title="1N5819HW: reverse current of the model",
        xlabel="Reverse voltage (V)",
        panels=(Panel("Reverse current (uA)", log=True),),
        traces=(
            Trace(typical_volts, typical * 1e6, "typical, 27 C", 0),
            Trace(leaky_volts, leaky * 1e6, "at the maximum, 27 C", 0, "--"),
            Trace(hot_volts, hot_amps * 1e6, "typical, 100 C", 0, ":"),
        ),
    )
    forward_graph = Graph(
        name="forward",
        title="1N5819HW: forward voltage of the model at 27 C",
        xlabel="Forward current (A)",
        panels=(Panel("Forward voltage (V)"),),
        traces=(Trace(amps, forward, "", 0),),
        logx=True,
    )
    notes = (
        "The forward limits are the maxima of the datasheet; the typical curve is "
        "read from a graph and the model has to lie within 10 % of it.",
        "The reverse current is a saturation current of 4 uA plus a resistor: 1 Mohm "
        "for the typical part, 87 kohm for a part at the maximum of 50 uA at 4 V. Its "
        "rise with temperature comes from the saturation current alone.",
    )
    return Outcome(tuple(figures), (forward_graph, reverse), notes)
