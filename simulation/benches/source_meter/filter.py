"""The filter between the pre-regulator and the IN pin: the impedance the regulator sees."""

from __future__ import annotations

import numpy as np

from benches.source_meter import common
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_DAMPED = ("FB1", "C46", "C43", "R59", "C42", "C45", "C50", "R62")
"""The filter with its damper and the output capacitors of the converter."""

_PLAIN = tuple(ref for ref in _DAMPED if ref not in ("C43", "R59"))
"""The same without the damper C43 and R59."""

_BEADS = (0.1e-6, 0.2e-6, 0.5e-6)
"""Inductance of the bead below the frequency at which it turns resistive (assumption)."""

_OUTPUTS = (0.8, 5.0)
"""Output voltages that decide the bias of the capacitors."""

_SWEEP = "ac dec 100 1k 30meg"

_BAND = (20e3, 30e6)
"""Band in which the peak of the impedance is looked for: above the loop of the
converter, which holds the impedance down below it."""


def _deck(ctx: Context, volts: float, henries: float, damped: bool) -> str:
    refs = _DAMPED if damped else _PLAIN
    circuit = common.source(
        ctx, volts, refs=refs, overrides={"FB1": common.part(ctx, "FB1", lb=henries)}
    )
    stimulus = "\n".join(
        [
            "* 1 A of test current into the IN pin node; the converter is left out, so",
            "* its output node is held by its capacitors alone",
            "Itest 0 ldo_in dc 0 ac 1",
            "Rdc ldo_in 0 1e6",
        ]
    )
    return ctx.deck(
        "Impedance at the IN pin of the regulator",
        circuit,
        stimulus,
        control=[_SWEEP],
    )


def _peak(run: RunResult) -> tuple[float, float]:
    """The highest impedance inside the band and its frequency."""
    frequency = run.real("frequency")
    ohms = np.abs(run.vector("ldo_in"))
    inside = (frequency >= _BAND[0]) & (frequency <= _BAND[1])
    index = int(np.argmax(ohms[inside]))
    return float(ohms[inside][index]), float(frequency[inside][index])


@bench(
    "source_meter",
    "filter",
    "The filter in front of the IN pin: source impedance with and without the damper",
    "section 4.2 (filter toward the regulator)",
)
def filter_impedance(ctx: Context) -> Outcome:
    """A test current is fed into the node of the IN pin and the voltage is read.

    The circuit is the bead FB1, the capacitor C46, the damper C43 with
    R59, and the output capacitors of the converter with their bleeder; the
    converter and the regulator are left out. The capacitors have the
    capacitance of their bias curve at 0.8 V and at 5.0 V of output, and
    the bead takes three values of its inductance, which its specification
    does not state. The same runs without the damper show what it is for.
    """
    decks = {}
    for volts in _OUTPUTS:
        for henries in _BEADS:
            for with_damper in (True, False):
                name = f"{'damped' if with_damper else 'plain'}-{volts:g}v-{henries * 1e9:g}nh"
                decks[name.replace(".", "p")] = _deck(ctx, volts, henries, with_damper)
    kept = "damped-5v-200nh"
    runs = {kept: ctx.run(kept, decks[kept])}
    runs.update(ctx.run_many({name: deck for name, deck in decks.items() if name != kept}))
    figures: list[Figure] = []
    traces: list[Trace] = []
    for volts in _OUTPUTS:
        for henries in _BEADS:
            tail = f"{volts:g}v-{henries * 1e9:g}nh".replace(".", "p")
            damped, plain = runs[f"damped-{tail}"], runs[f"plain-{tail}"]
            ohms, hertz = _peak(damped)
            text = f"{volts:g} V of output, bead of {henries * 1e6:g} uH"
            tag = tail.replace("-", "_")
            figures += [
                Figure(
                    f"peak_{tag}",
                    f"{text}: highest impedance at the IN pin above 20 kHz, with the damper",
                    ohms,
                    "ohm",
                    expected=0.32,
                    source="section 4.2: 0.27 ohm to 0.37 ohm with the damper (simulated)",
                ),
                Figure(f"peak_hertz_{tag}", f"{text}: frequency of that peak", hertz, "Hz"),
                Figure(
                    f"plain_{tag}",
                    f"{text}: highest impedance without the damper",
                    _peak(plain)[0],
                    "ohm",
                ),
            ]
            if henries == _BEADS[1]:
                frequency = damped.real("frequency")
                traces += [
                    Trace(frequency, np.abs(damped.vector("ldo_in")), f"{volts:g} V, damper", 0),
                    Trace(
                        frequency,
                        np.abs(plain.vector("ldo_in")),
                        f"{volts:g} V, no damper",
                        0,
                        "--",
                    ),
                ]
    graph = Graph(
        name="impedance",
        title="Impedance at the IN pin of the regulator, bead of 0.2 uH",
        xlabel="Frequency (Hz)",
        panels=(Panel("Impedance (ohm)", log=True),),
        traces=tuple(traces),
        logx=True,
    )
    notes = (
        "The inductance of the bead is an assumption, 0.1 uH to 0.5 uH: its reference "
        "specification gives the impedance at 100 MHz and the DC resistance alone. The "
        "copper between the converter and the bead, which section 10 holds to 15 mohm, "
        "is not in the netlist and not in this circuit; its inductance would add to "
        "that of the bead.",
        "The capacitors are ideal apart from their bias: no series resistance and no "
        "series inductance, so the impedance above some megahertz is lower here than "
        "on a board.",
        "The converter is left out: below its crossover, 19 kHz to 28 kHz in the model, "
        "its loop holds the impedance down, and the band of the peak starts there. "
        "The specification gives no limit for this impedance; the datasheet of the "
        "regulator asks for none at the IN pin.",
    )
    return Outcome(tuple(figures), (graph,), notes)
