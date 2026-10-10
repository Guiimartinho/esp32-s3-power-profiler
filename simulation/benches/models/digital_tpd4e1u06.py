"""The TPD4E1U06 model against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_DOCUMENT = "TI SLVSBQ9D"

_PULSED = {6.0: 13.0, 12.0: 18.5, 18.0: 24.0, 27.0: 30.5}
"""Voltage of a line by pulsed current into it, read from figure 1 on page 6."""

_PULSED_BACK = {9.0: 7.0, 18.0: 11.5}
"""Voltage below ground by pulsed current out of a line, read from figure 2."""

_AMPS = np.concatenate((np.logspace(-6, 0, 25), np.linspace(2.0, 30.0, 29)))
"""Currents of the sweep, 1 uA to 30 A."""


def _deck(ctx: Context) -> str:
    """Currents forced into and out of one line; the other lines rest at 0 V and 3.3 V."""
    lines = [
        "* three parts with the breakdown at its lower limit, in the middle, at its upper limit",
        "Ip 0 p 1m",
        "Xp p p2 p3 p4 0 DIGITAL_TPD4E1U06 vbr=7.5",
        "Rp2 p2 0 1k",
        "Vp3 p3s 0 3.3",
        "Rp3 p3s p3 1k",
        "Rp4 p4 0 1e9",
        "Il 0 l 1m",
        "Xl l l2 l3 l4 0 DIGITAL_TPD4E1U06 vbr=6.5",
        "Rl2 l2 0 1k",
        "Rl3 l3 0 1k",
        "Rl4 l4 0 1k",
        "Ih 0 h 1m",
        "Xh h h2 h3 h4 0 DIGITAL_TPD4E1U06 vbr=8.5",
        "Rh2 h2 0 1k",
        "Rh3 h3 0 1k",
        "Rh4 h4 0 1k",
        "* current out of a line",
        "In n 0 1m",
        "Xn n n2 n3 n4 0 DIGITAL_TPD4E1U06",
        "Rn2 n2 0 1k",
        "Rn3 n3 0 1k",
        "Rn4 n4 0 1k",
        "* capacitance of a line at 2.5 V",
        "Vc c 0 DC 2.5 AC 1",
        "Xc c c2 c3 c4 0 DIGITAL_TPD4E1U06",
        "Rc2 c2 0 1k",
        "Rc3 c3 0 1k",
        "Rc4 c4 0 1k",
    ]
    points = " ".join(f"{amps:.4g}" for amps in _AMPS)
    control = [
        f"foreach level {points}",
        "  alter Ip dc = $level",
        "  alter Il dc = $level",
        "  alter Ih dc = $level",
        "  alter In dc = $level",
        "  op",
        "end",
        "ac lin 1 1e6 1e6",
    ]
    return ctx.deck(
        "TPD4E1U06: one line driven, the others at rest",
        "\n".join(lines),
        control=control,
        libraries=("digital.lib",),
    )


@bench(
    "models",
    "digital-tpd4e1u06",
    "TPD4E1U06 model against its datasheet",
    "the model of the arrays U35, U36 and U37 at the logic port",
)
def tpd4e1u06(ctx: Context) -> Outcome:
    """A current is forced into one line of the array and out of it.

    The breakdown at 1 mA is read for the three values of the parameter,
    the forward voltage at 1 mA, and the voltages at the pulsed currents of
    the datasheet curves. A neighbor line that rests at 3.3 V behind 1 kohm
    shows whether a line in breakdown disturbs it. The capacitance of a line
    is read at 2.5 V.
    """
    run = ctx.run("lines", _deck(ctx))

    def sweep(node: str) -> np.ndarray:
        return np.array(
            [float(run.real(node, plot=f"op{index + 1}")[0]) for index in range(_AMPS.size)]
        )

    middle, low, high, back = sweep("p"), sweep("l"), sweep("h"), -sweep("n")
    neighbor = sweep("p3")

    def at(volts: np.ndarray, amps: float) -> float:
        return float(np.interp(np.log(amps), np.log(_AMPS), volts))

    figures: list[Figure] = [
        Figure(
            "breakdown_low",
            "Breakdown at 1 mA, parameter at the lower limit",
            at(low, 1e-3),
            "V",
            expected=6.5,
            low=6.4,
            high=6.6,
            source=_DOCUMENT + ", page 5: 6.5 V at the least",
        ),
        Figure(
            "breakdown_middle",
            "Breakdown at 1 mA, default parameter",
            at(middle, 1e-3),
            "V",
            expected=7.5,
            low=6.5,
            high=8.5,
            source=_DOCUMENT + ", page 5: 6.5 V to 8.5 V",
        ),
        Figure(
            "breakdown_high",
            "Breakdown at 1 mA, parameter at the upper limit",
            at(high, 1e-3),
            "V",
            expected=8.5,
            low=8.4,
            high=8.6,
            source=_DOCUMENT + ", page 5: 8.5 V at the most",
        ),
        near(
            "forward",
            "Voltage below ground at 1 mA out of a line",
            at(back, 1e-3),
            "V",
            0.75,
            0.10,
            _DOCUMENT + ", page 6, figure 5 (read from the graph)",
        ),
    ]
    for amps, volts in _PULSED.items():
        figures.append(
            near(
                f"pulsed_{amps:g}a",
                f"Voltage of a line at {amps:g} A into it",
                at(middle, amps),
                "V",
                volts,
                0.12,
                _DOCUMENT + ", page 6, figure 1 (read from the graph)",
            )
        )
    for amps, volts in _PULSED_BACK.items():
        figures.append(
            near(
                f"pulsed_back_{amps:g}a",
                f"Voltage below ground at {amps:g} A out of a line",
                at(back, amps),
                "V",
                volts,
                0.15,
                _DOCUMENT + ", page 6, figure 2 (read from the graph)",
            )
        )
    slope = (at(middle, 20.0) - at(middle, 10.0)) / 10.0
    figures.append(
        near(
            "dynamic_resistance",
            "Dynamic resistance between 10 A and 20 A, line to ground",
            slope,
            "ohm",
            1.0,
            0.15,
            _DOCUMENT + ", page 5",
        )
    )
    figures.append(
        Figure(
            "neighbor",
            "Neighbor line at 3.3 V behind 1 kohm while 1 A flows into the driven line",
            at(neighbor, 1.0),
            "V",
            low=3.25,
            high=3.35,
            source="a line in breakdown must not move a line that rests below it",
        )
    )
    admittance = run.vector("vc#branch", plot="ac")
    figures.append(
        Figure(
            "capacitance",
            "Capacitance of a line at 2.5 V and 1 MHz",
            abs(float(np.imag(admittance[0]))) / (2.0 * np.pi * 1e6),
            "F",
            expected=0.8e-12,
            low=0.6e-12,
            high=1.0e-12,
            source=_DOCUMENT + ", page 5: 0.8 pF typical, 1 pF at the most",
        )
    )
    graph = Graph(
        name="curve",
        title="TPD4E1U06: voltage of a line against the current forced through it",
        xlabel="Current (A)",
        panels=(Panel("Line above ground (V)"), Panel("Line below ground (V)")),
        traces=(
            Trace(_AMPS, low, "breakdown 6.5 V", 0, "--"),
            Trace(_AMPS, middle, "breakdown 7.5 V", 0),
            Trace(_AMPS, high, "breakdown 8.5 V", 0, "--"),
            Trace(_AMPS, back, "current out of the line", 1),
        ),
        logx=True,
    )
    notes = (
        "The pulsed curves of the datasheet are taken with pulses of 100 ns. In a "
        "surge of 8/20 us the part heats and clamps higher, 11 V at 1 A and 15 V at "
        "3 A (page 5); the model does not heat and gives lower values there.",
        "The model says nothing about leakage and nothing about the current or the "
        "energy that destroys the part: the datasheet rates 3 A and 45 W for a surge "
        "of 8/20 us and gives no figure for a continuous current.",
        "The limits on the pulsed points are the fit this project asks of the model.",
    )
    return Outcome(tuple(figures), (graph,), notes)
