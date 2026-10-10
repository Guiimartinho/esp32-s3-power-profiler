"""The supply node of the ladder in ampere mode: load step and release of the load."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.path_switching import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_EVENT = 5e-6
"""Instant at which the load current changes."""

_END = 155e-6

_VIN = 5.0

_STEP_EDGE = 100e-9
"""Edge of the load step, as the test of requirement R-07 asks it."""

_BIAS = 0.4
"""Share of their nominal capacitance that C62 and C63 keep in the cautious
runs (assumption; an X7R part of this size loses about that much near its
rated voltage)."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One run: a load current that changes behind supply leads.

    Attributes:
        henries: Inductance of the supply leads.
        amps: The load current, after a step up or before a release.
        fall: Time in which a released load current falls to zero; zero for
            a step up.
        damper: The damped branch C63, R87 is in the circuit.
        derated: C62 and C63 at the share :data:`_BIAS` of their value.
    """

    henries: float
    amps: float
    fall: float = 0.0
    damper: bool = True
    derated: bool = False

    @property
    def tag(self) -> str:
        """Short name of the run."""
        text = f"{self.henries * 1e6:g}uh_{self.amps:g}a"
        if self.fall:
            text += f"_{self.fall * 1e6:g}us"
        if not self.damper:
            text += "_no_damper"
        if self.derated:
            text += "_derated"
        return text.replace(".", "p")

    @property
    def text(self) -> str:
        """The case as the labels name it."""
        text = f"{self.henries * 1e6:g} uH, {self.amps:g} A"
        if self.fall:
            text += f", released in {self.fall * 1e6:g} us"
        if not self.damper:
            text += ", without the damper"
        if self.derated:
            text += ", capacitors at 40 %"
        return text


def _deck(ctx: Context, case: _Case) -> str:
    """Ampere mode on 5 V behind leads, range 3; the load is a current sink."""
    if case.fall:
        load = f"PWL(0 {case.amps:g} {_EVENT:g} {case.amps:g} {_EVENT + case.fall:g} 0)"
    else:
        load = f"PWL(0 0 {_EVENT:g} 0 {_EVENT + _STEP_EDGE:g} {case.amps:g})"
    stimulus = (
        common.supply(_VIN, henries=case.henries)
        + common.no_regulator()
        + common.requests(ampere=((0.0, True),))
        + "* the load: a current sink on the node after the shunts; the output pair,\n"
        "* which opens or closes this current, belongs to another block\n"
        f"Iload vout_s 0 {load}\n"
    )
    leave_out = () if case.damper else ("C63", "R87")
    scales = {"C62": _BIAS, "C63": _BIAS} if case.derated else None
    saves = "save all @mq5[id] @mq9[id] @d.xd14.d1[id] @dd17_2[id]"
    if case.damper:
        saves += " @r87[i]"
    return common.deck(
        ctx,
        f"Supply node in ampere mode: {case.text}",
        common.circuit(ctx, leave_out=leave_out, scales=scales),
        common.rails(),
        common.range_lines(3),
        stimulus,
        control=[saves, f"tran 2n {_END:g} 0 20n"],
    )


def _run_all(ctx: Context, cases: tuple[_Case, ...]) -> dict[str, RunResult]:
    """Run the cases; the deck of the first one is kept with the results."""
    runs = ctx.run_many({case.tag: _deck(ctx, case) for case in cases[1:]})
    runs[cases[0].tag] = ctx.run(cases[0].tag, _deck(ctx, cases[0]))
    return runs


_SAG_CASES = (
    _Case(1e-6, 0.5),
    _Case(0.5e-6, 0.5),
    _Case(0.75e-6, 0.5),
    _Case(3e-6, 0.5),
    _Case(1e-6, 0.5, derated=True),
    _Case(1e-6, 0.5, damper=False),
)


@bench(
    "path_switching",
    "sag",
    "Ampere mode: the supply node after a load step of 500 mA behind supply leads",
    "section 4.3 (supply node, D-63)",
)
def sag(ctx: Context) -> Outcome:
    """The ampere pair is closed on 5 V behind supply leads and the load steps to 500 mA.

    The step has an edge of 100 ns and is drawn from the node after the
    shunts, with range 3 selected. Until the current of the leads has risen,
    the capacitor of the supply node and its damped branch deliver the
    load. The run is repeated for 0.5 uH to 3 uH of leads, with the two
    capacitors at 40 % of their value, and without the damped branch.
    """
    runs = _run_all(ctx, _SAG_CASES)
    figures: list[Figure] = []
    traces: list[Trace] = []
    for case in _SAG_CASES:
        run = runs[case.tag]
        time = run.real("time")
        node = run.real("supply")
        before = measure.mean(time, node, 0.0, _EVENT)
        lowest = measure.extremes(time, node, _EVENT, _END)[0]
        settled = measure.mean(time, node, _END - 5e-6, _END)
        claimed = case.damper and not case.derated and case.henries <= 1e-6
        figures.append(
            Figure(
                f"sag_{case.tag}",
                f"Deepest sag of the supply node: {case.text}",
                before - lowest,
                "V",
                low=0.17 if claimed else None,
                high=0.21 if claimed else None,
                source="section 4.3: 0.17 V to 0.21 V behind 0.5 uH to 1 uH, simulated"
                if claimed
                else "",
            )
        )
        if case is _SAG_CASES[0]:
            figures.append(
                Figure(
                    "settled",
                    f"Drop of the supply node once the leads carry the load: {case.text}",
                    before - settled,
                    "V",
                    source="",
                )
            )
        micro = (time - _EVENT) * 1e6
        shown = (micro >= -1.0) & (micro <= 30.0)
        traces.append(Trace(micro[shown], node[shown], case.text, 0))
        traces.append(Trace(micro[shown], run.real("vlead#branch")[shown], case.text, 1))
    graph = Graph(
        name="step",
        title="Load step of 500 mA in ampere mode on 5 V: supply node and current of the leads",
        xlabel="Time after the step (us)",
        panels=(Panel("Supply node (TP33) (V)"), Panel("Current of the supply leads (A)")),
        traces=tuple(traces),
    )
    notes = (
        "The load is a current sink that steps within 100 ns, drawn from the node "
        "after the shunts with range 3 held: no capacitor at the device under test "
        "softens the step, and the range logic is not in the circuit.",
        "The external supply is a voltage source behind its leads, 40 mohm per uH; "
        "the sag is measured from the level before the step, so it includes the "
        "drop of leads, fuse and pair, about 30 mV.",
        "An X7R capacitor keeps less than its nominal value under bias; the run with "
        "both capacitors at 40 % shows the direction, the share itself is an "
        "assumption.",
    )
    return Outcome(tuple(figures), (graph,), notes)


_RELEASE_CASES = (
    _Case(3e-6, 1.2, fall=0.1e-6),
    _Case(0.5e-6, 1.2, fall=0.1e-6),
    _Case(1e-6, 1.2, fall=0.1e-6),
    _Case(2e-6, 1.2, fall=0.1e-6),
    _Case(3e-6, 0.5, fall=0.1e-6),
    _Case(3e-6, 1.0, fall=0.1e-6),
    _Case(3e-6, 1.2, fall=5e-6),
    _Case(3e-6, 1.2, fall=0.1e-6, derated=True),
    _Case(3e-6, 1.2, fall=0.1e-6, damper=False),
    _Case(3e-6, 1.2, fall=0.1e-6, damper=False, derated=True),
)


@bench(
    "path_switching",
    "trip",
    "Ampere mode: the output opens at 0.5 A to 1.2 A behind 0.5 uH to 3 uH of supply leads",
    "sections 4.3 and 4.9 (supply node, D-63; bound of the gate, D-61), section 4.4 (trip)",
)
def trip(ctx: Context) -> Outcome:
    """The ampere pair carries 0.5 A to 1.2 A and the output opens.

    The load current stops within 0.1 us, faster than the output pair opens,
    or within 5 us. The current of the supply leads then has to go into the
    capacitor of the supply node and its damped branch, drawn as on the
    final schematic. The run shows the supply node, the VIN line behind the
    fuse and the parts between them, each against its rating. It is repeated
    with the two capacitors at 40 % of their value and, for comparison,
    without the damped branch.
    """
    runs = _run_all(ctx, _RELEASE_CASES)
    figures: list[Figure] = []
    traces: list[Trace] = []
    worst: dict[str, float] = {}

    def keep(name: str, value: float) -> None:
        worst[name] = max(worst.get(name, value), value)

    for case in _RELEASE_CASES:
        run = runs[case.tag]
        time = run.real("time")
        node, terminal = run.real("supply"), run.real("vin_p")
        source, gate = run.real("s_amp"), run.real("g_amp")
        peak = float(np.max(node))
        figures.append(
            Figure(
                f"node_{case.tag}",
                f"Highest voltage of the supply node: {case.text}",
                peak,
                "V",
                high=common.NODE_LIMIT if case.damper else None,
                source="section 4.3: the node stays below 11.5 V" if case.damper else "",
            )
        )
        figures.append(
            Figure(
                f"terminal_{case.tag}",
                f"Highest voltage on VIN behind the fuse: {case.text}",
                float(np.max(terminal)),
                "V",
                source="",
            )
        )
        if case.damper:
            keep("supply_side", float(np.max(terminal - source)))
            keep("ladder_side", float(np.max(node - source)))
            keep("gate_source", float(np.max(np.abs(gate - source))))
            keep("gate", float(np.max(gate)))
            keep("suppressor", float(np.max(np.abs(run.real("@d.xd14.d1[id]")))))
            keep("bound", float(np.max(run.real("@dd17_2[id]"))))
            current = run.real("@r87[i]")
            keep("damper_amps", float(np.max(np.abs(current))))
            keep("damper_joules", common.joules(time, 0.47 * current * current, _EVENT, _END))
            keep("damper_volts", float(np.max(run.real("damper"))))
        micro = (time - _EVENT) * 1e6
        shown = (micro >= -2.0) & (micro <= 60.0)
        if case.amps == 1.2 and case.fall == 0.1e-6 and not case.derated:
            traces.append(Trace(micro[shown], node[shown], case.text, 0))
            traces.append(Trace(micro[shown], run.real("vlead#branch")[shown], case.text, 1))
    figures += [
        Figure(
            "supply_side",
            "Largest voltage across the transistor on the supply side, runs with the damper",
            worst["supply_side"],
            "V",
            high=common.TRANSISTOR_VOLTS,
            source="rating of the CSD17577Q3A, 30 V (TI SLPS515A, page 1)",
        ),
        Figure(
            "ladder_side",
            "Largest voltage across the transistor on the ladder side, runs with the damper",
            worst["ladder_side"],
            "V",
            high=common.TRANSISTOR_VOLTS,
            source="rating of the CSD17577Q3A, 30 V (TI SLPS515A, page 1)",
        ),
        Figure(
            "gate_source",
            "Largest gate-source voltage of the pair, runs with the damper",
            worst["gate_source"],
            "V",
            high=common.GATE_VOLTS,
            source="rating of the CSD17577Q3A, 20 V (TI SLPS515A, page 1)",
        ),
        Figure(
            "gate",
            "Highest voltage of the gate, runs with the damper",
            worst["gate"],
            "V",
            source="",
        ),
        Figure(
            "bound",
            "Largest current in the diode from the gate to +12 V_A, runs with the damper",
            worst["bound"],
            "A",
            high=common.DIODE_REPEAT_AMPS,
            source="repetitive peak current of the BAV199, 0.5 A (Nexperia, page 2)",
        ),
        Figure(
            "suppressor",
            "Largest current in the suppressor of VIN, runs with the damper",
            worst["suppressor"],
            "A",
            high=common.SUPPRESSOR_PULSE_AMPS,
            source="peak pulse current of the SMAJ20CA, 12.3 A (Vishay 88390, page 2)",
        ),
        Figure(
            "capacitor",
            "Highest voltage on the capacitor of the damped branch, runs with the damper",
            worst["damper_volts"],
            "V",
            high=common.CAPACITOR_VOLTS,
            source="rated voltage of C62 and C63, 25 V",
        ),
        Figure(
            "damper_current",
            "Largest current in the resistor of the damped branch, runs with the damper",
            worst["damper_amps"],
            "A",
            source="",
        ),
        Figure(
            "damper_energy",
            "Largest energy in the resistor of the damped branch per release",
            worst["damper_joules"],
            "J",
            source="",
        ),
    ]
    graph = Graph(
        name="release",
        title="1.2 A released within 0.1 us in ampere mode on 5 V: supply node and lead current",
        xlabel="Time after the release (us)",
        panels=(
            Panel("Supply node (TP33) (V)"),
            Panel("Current of the supply leads (A)"),
        ),
        traces=tuple(traces),
    )
    shown_case = _RELEASE_CASES[0]
    run = runs[shown_case.tag]
    time = run.real("time")
    micro = (time - _EVENT) * 1e6
    near = (micro >= -2.0) & (micro <= 40.0)
    detail = Graph(
        name="parts",
        title=f"The parts of the path at the release: {shown_case.text}",
        xlabel="Time after the release (us)",
        panels=(
            Panel("Voltage (V)", marks=((common.RAIL_VOLTS, "+12 V_A"),)),
            Panel("Current (A)"),
        ),
        traces=(
            Trace(micro[near], run.real("g_amp")[near], "gate of the ampere pair (TP32)", 0),
            Trace(micro[near], run.real("vin_p")[near], "VIN behind the fuse (TP27)", 0, "--"),
            Trace(micro[near], run.real("supply")[near], "supply node (TP33)", 0),
            Trace(micro[near], run.real("damper")[near], "capacitor of the damped branch", 0, ":"),
            Trace(micro[near], run.real("vlead#branch")[near], "supply leads", 1),
            Trace(micro[near], run.real("@r87[i]")[near], "damped branch (R87)", 1),
            Trace(micro[near], common.through(ctx, run, "ampere")[near], "transistor Q5", 1, "--"),
        ),
    )
    notes = (
        "The output pair and the device under test belong to another block. A current "
        "sink on the node after the shunts stands for them; it stops within 0.1 us, "
        "which is faster than the output pair opens (its gate is below 2 V within "
        "7 us, specification), or within 5 us.",
        "At these currents the leads hold microjoules: 2.2 uJ at 1.2 A and 3 uH. The "
        "node rises by 0.4 V to 1.1 V with the damped branch and by 1.9 V to 2.8 V "
        "without it, and neither the bound of the gate nor the suppressor takes "
        "part. Voltages of 10 V to 11 V on the node and of 30 V and more on the VIN "
        "line belong to a short circuit, in which the leads carry 15 A to 34 A "
        "when the trip acts, and to a supply that leaves its range while the pair "
        "is closed: the benches short, overvoltage and reversal run those cases.",
        "The external supply is a voltage source behind its leads, 40 mohm per uH, "
        "and it takes current back: after the release the node rings against the "
        "leads through the closed pair.",
        "The share of 40 % for the capacitors under bias is an assumption.",
    )
    return Outcome(tuple(figures), (graph, detail), notes)
