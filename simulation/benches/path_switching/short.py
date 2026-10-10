"""A short circuit in ampere mode: the trip opens the output and the leads kick."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.path_switching import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_SHORT = 5e-6
"""Instant at which the short circuit closes."""

_END = 205e-6

_VIN = 5.0

_TRIP_VOLTS = 0.115
"""Voltage across the 0.1 ohm shunt at the over-current level (section 4.4)."""

_CHAIN = 0.3e-6
"""Delay from the shunt to the pin of the controller: amplifier, filter and
comparator (assumption, in the range the specification states for the jump
path)."""

_QUALIFY = 12e-6
"""Time the comparator has to stay high before the output opens (rule F-18)."""

_QUALIFY_MOST = 20e-6
"""Longest qualification time a build may have (rule F-18)."""

_PRELOAD_OHMS = 50.0
"""Load before the short circuit: 100 mA, inside range 3."""

_SHORT_SIEMENS = 200.0
"""Conductance of the short circuit: 5 mohm."""

_BIAS = 0.4
"""Share of their nominal capacitance that C62 and C63 keep in the corner
runs (assumption; an X7R part of this size loses about that much toward
12 V)."""

_TERMINAL_LIMIT = 36.0
"""Highest voltage on VIN behind the fuse at a short circuit (section 11)."""

_DAMPER_OHMS = 0.47

_DAMPER_PULSE_WATTS = 600.0
"""Single pulse of 10 us that a RCWE1206 bears (Vishay 20019, page 3, read from the curve)."""

_BOUND_AMPS = 1.0
"""Peak forward current of a BAV199 for 1 ms (Nexperia, page 2): any shorter pulse may be larger."""


_PARTS_TEXT = {
    "typical": "",
    "corner": ", corner parts",
    "threshold": ", transistors with the lowest threshold",
    "diodes": ", gate bound with the highest forward voltage",
    "capacitors": ", capacitors at 40 %",
    "clamp-low": ", suppressor at its lower limit",
}
"""What the labels say about a set of parts."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One run: a short circuit behind given leads, with given parts.

    Attributes:
        henries: Inductance of the supply leads.
        parts: ``typical``; ``corner`` for the parts that let the node and
            the terminal rise highest; ``threshold``, ``diodes`` and
            ``capacitors`` for one property of that corner alone;
            ``clamp-low`` for the suppressor at its lowest breakdown voltage.
        qualify: Qualification time of the trip.
        damper: The damped branch C63, R87 is in the circuit.
        cable: Inductance of the cable between the output terminal and the
            short circuit.
    """

    henries: float
    parts: str = "typical"
    qualify: float = _QUALIFY
    damper: bool = True
    cable: float = 50e-9

    @property
    def tag(self) -> str:
        """Short name of the run."""
        text = f"{self.henries * 1e6:g}uh"
        if self.parts != "typical":
            text += f"_{self.parts}"
        if self.qualify != _QUALIFY:
            text += f"_{self.qualify * 1e6:g}us"
        if not self.damper:
            text += "_no_damper"
        if self.cable > 100e-9:
            text += "_cable"
        return text.replace(".", "p").replace("-", "_")

    @property
    def text(self) -> str:
        """The case as the labels name it."""
        text = f"{self.henries * 1e6:g} uH"
        text += _PARTS_TEXT[self.parts]
        if self.qualify != _QUALIFY:
            text += f", trip after {self.qualify * 1e6:g} us"
        if not self.damper:
            text += ", without the damper"
        if self.cable > 100e-9:
            text += ", short behind 1 m of cable"
        return text


_CASES = (
    _Case(2e-6),
    _Case(0.5e-6),
    _Case(1e-6),
    _Case(3e-6),
    _Case(0.5e-6, qualify=_QUALIFY_MOST),
    _Case(2e-6, qualify=_QUALIFY_MOST),
    _Case(0.5e-6, parts="corner"),
    _Case(1e-6, parts="corner"),
    _Case(2e-6, parts="corner"),
    _Case(3e-6, parts="corner"),
    _Case(2e-6, parts="corner", qualify=_QUALIFY_MOST),
    _Case(2e-6, parts="threshold"),
    _Case(2e-6, parts="diodes"),
    _Case(2e-6, parts="capacitors"),
    _Case(2e-6, parts="clamp-low"),
    _Case(0.5e-6, cable=1e-6),
    _Case(2e-6, cable=1e-6),
    _Case(0.5e-6, damper=False),
    _Case(2e-6, damper=False),
    _Case(2e-6, parts="corner", damper=False),
)
"""The first case is the one that is drawn."""


def _overrides(case: _Case) -> dict[str, PartModel]:
    """The models that a set of parts replaces."""
    # The node rises to the gate less a threshold: transistors with the
    # lowest threshold and diodes with the highest forward voltage let it
    # rise highest. The suppressor at its upper limit lets the terminal rise
    # highest.
    low_threshold = {"Q5": common.transistor("LO"), "Q9": common.transistor("LO")}
    high_bound = {"D17": common.diode_pair("HI")}
    if case.parts == "corner":
        return {**low_threshold, **high_bound, "D14": common.suppressor("HI")}
    if case.parts == "threshold":
        return low_threshold
    if case.parts == "diodes":
        return high_bound
    if case.parts == "clamp-low":
        return {"D14": common.suppressor("LO")}
    return {}


def _deck(ctx: Context, case: _Case, opens: float | None) -> str:
    """Ampere mode on 5 V, output closed on a light load, then a short circuit.

    Args:
        ctx: The context of the bench.
        case: Leads and parts.
        opens: Instant at which the line of the output pair falls, or None
            for the first pass, which only looks for the instant at which
            the over-current level is passed.
    """
    derated = case.parts in ("corner", "capacitors")
    scales = {"C62": _BIAS, "C63": _BIAS} if derated else None
    leave_out = () if case.damper else ("C63", "R87")
    cable_ohms = 0.005 if case.cable <= 100e-9 else 0.04
    command = [(0.0, True)] if opens is None else [(0.0, True), (opens, False)]
    stimulus = (
        common.supply(_VIN, henries=case.henries)
        + common.no_regulator()
        + common.requests(ampere=((0.0, True),))
        + "* GATE_OUT: the over-current trip of rule F-18, as an instant found in a\n"
        "* first pass; no program of the controller exists\n"
        + common.pin("out", "gate_out", *command)
        + "* device under test: a light load, then a short circuit behind a cable\n"
        "Vdut vout dut_a 0\n"
        f"Rcab dut_a dut_b {cable_ohms:g}\n"
        f"Lcab dut_b dut {case.cable:g}\n"
        f"Rpre dut 0 {_PRELOAD_OHMS:g}\n"
        f"Vsh shc 0 PWL(0 0 {_SHORT:g} 0 {_SHORT + 50e-9:g} 1)\n"
        f"Bshort dut 0 I = v(dut)*{_SHORT_SIEMENS:g}*v(shc)\n"
    )
    if opens is None:
        control = ["save sense_r3 vout_s", f"tran 5n {_SHORT + 4e-6:g} 0 20n"]
    else:
        saves = (
            "save vin_raw vin_p s_amp g_amp b_amp off_amp drv_amp supply vout_s sense_r3 "
            "s_out out_gate g_out vout dut gate_out drv_out det vin_ov "
            "vlead#branch vdut#branch @mq5[id] @mq9[id] @mq14[id] @mq15[id] "
            "@mq10[id] @mq11[id] @d.xd14.d1[id] @d.xd14.d2[id] @dd17_1[id] @dd17_2[id] "
            "@r79[i] @qq7[ic]"
        )
        if case.damper:
            saves += " damper @r87[i]"
        control = [saves, f"tran 5n {_END:g} 0 50n"]
    return common.deck(
        ctx,
        f"Short circuit in ampere mode: {case.text}",
        common.circuit(
            ctx, output=True, leave_out=leave_out, overrides=_overrides(case), scales=scales
        ),
        common.rails(),
        common.range_lines(3, output=None),
        stimulus,
        control=control,
    )


def _opens(case: _Case, first: RunResult) -> float:
    """The instant at which the output line falls, from the first pass of a case."""
    time = first.real("time")
    shunt = first.real("sense_r3") - first.real("vout_s")
    passed = measure.first_crossing(time, shunt, _TRIP_VOLTS, rising=True, after=_SHORT)
    return passed + _CHAIN + case.qualify


@dataclass(frozen=True, slots=True)
class _Seen:
    """What one run shows.

    Attributes:
        amps: Largest current of the supply leads.
        node: Highest voltage of the supply node.
        terminal: Highest voltage on VIN behind the fuse.
        supply_side: Largest voltage across the transistor on the supply side.
        ladder_side: Largest voltage across the transistor on the ladder side.
        gate_source: Largest gate-source voltage of the ampere pair.
        gate: Highest voltage of the gate.
        suppressor_amps: Largest current in the suppressor.
        suppressor_joules: Energy the suppressor takes.
        suppressor_share: Its largest power as a share of its rating for a
            pulse of that width.
        fuse: I2t of the event.
        damper_watts: Largest power in the resistor of the damped branch.
        damper_joules: Energy in that resistor.
        bound: Largest current in either diode of the gate bound.
        back: Largest current from the gate network into the driver output.
        transistor_joules: Energy in the transistor on the supply side.
        hold_off: Largest collector current of the hold-off transistor.
    """

    amps: float
    node: float
    terminal: float
    supply_side: float
    ladder_side: float
    gate_source: float
    gate: float
    suppressor_amps: float
    suppressor_joules: float
    suppressor_share: float
    fuse: float
    damper_watts: float
    damper_joules: float
    bound: float
    back: float
    transistor_joules: float
    hold_off: float


def _seen(ctx: Context, case: _Case, run: RunResult) -> _Seen:
    """The figures of one run."""
    time = run.real("time")
    leads = run.real("vlead#branch")
    node, terminal = run.real("supply"), run.real("vin_p")
    source, gate = run.real("s_amp"), run.real("g_amp")
    clamp = np.maximum(np.abs(run.real("@d.xd14.d1[id]")), np.abs(run.real("@d.xd14.d2[id]")))
    clamp_watts = clamp * np.abs(terminal)
    clamp_joules = common.joules(time, clamp_watts, _SHORT, _END)
    clamp_peak = float(np.max(clamp_watts))
    # The datasheet states the pulse width as the time to half the peak; a
    # pulse that decays in a straight line has its energy over its peak power.
    width = clamp_joules / clamp_peak if clamp_peak > 1.0 else 0.0
    share = clamp_peak / common.suppressor_rating(width) if clamp_peak > 1.0 else 0.0
    damper = run.real("@r87[i]") if case.damper else np.zeros_like(time)
    damper_watts = _DAMPER_OHMS * damper * damper
    through = common.through(ctx, run, "ampere")
    return _Seen(
        amps=float(np.max(leads)),
        node=float(np.max(node)),
        terminal=float(np.max(terminal)),
        supply_side=float(np.max(terminal - source)),
        ladder_side=float(np.max(node - source)),
        gate_source=float(np.max(np.abs(gate - source))),
        gate=float(np.max(gate)),
        suppressor_amps=float(np.max(clamp)),
        suppressor_joules=clamp_joules,
        suppressor_share=share,
        fuse=common.joules(time, leads * leads, _SHORT, _END),
        damper_watts=float(np.max(damper_watts)),
        damper_joules=common.joules(time, damper_watts, _SHORT, _END),
        bound=float(np.max(np.maximum(run.real("@dd17_1[id]"), run.real("@dd17_2[id]")))),
        # R79 is drawn from the driver output to the diodes: a current into
        # the driver is negative in it.
        back=float(np.max(-run.real("@r79[i]"))),
        transistor_joules=common.joules(time, np.abs((terminal - source) * through), _SHORT, _END),
        hold_off=float(np.max(np.abs(run.real("@qq7[ic]")))),
    )


def _per_run(case: _Case, seen: _Seen) -> list[Figure]:
    """The three figures every run shows by itself."""
    limited = case.damper
    return [
        Figure(
            f"amps_{case.tag}",
            f"Largest current of the supply leads: {case.text}",
            seen.amps,
            "A",
            source="section 15, D-63: 15 A to 34 A of lead current" if limited else "",
        ),
        Figure(
            f"node_{case.tag}",
            f"Highest voltage of the supply node: {case.text}",
            seen.node,
            "V",
            high=common.NODE_LIMIT if limited else None,
            source="sections 4.3 and 11: the node stays below 11.5 V" if limited else "",
        ),
        Figure(
            f"terminal_{case.tag}",
            f"Highest voltage on VIN behind the fuse: {case.text}",
            seen.terminal,
            "V",
            high=_TERMINAL_LIMIT if limited else None,
            source="section 11: TP27 below 36 V (section 16 expects below 34 V)" if limited else "",
        ),
    ]


def _worst(seen: list[_Seen]) -> list[Figure]:
    """Every part of the path against its rating, over the runs with the damper."""

    def most(name: str) -> float:
        return max(float(getattr(item, name)) for item in seen)

    transistor = "rating of the CSD17577Q3A (TI SLPS515A, page 1)"
    return [
        Figure(
            "supply_side",
            "Largest voltage across the transistor on the supply side (Q5)",
            most("supply_side"),
            "V",
            high=common.TRANSISTOR_VOLTS,
            source=f"{transistor}: 30 V",
        ),
        Figure(
            "ladder_side",
            "Largest voltage across the transistor on the ladder side (Q9)",
            most("ladder_side"),
            "V",
            high=common.TRANSISTOR_VOLTS,
            source=f"{transistor}: 30 V",
        ),
        Figure(
            "gate_source",
            "Largest gate-source voltage of the ampere pair",
            most("gate_source"),
            "V",
            high=common.GATE_VOLTS,
            source=f"{transistor}: 20 V",
        ),
        Figure(
            "transistor_energy",
            "Largest energy in the transistor on the supply side while it limits",
            most("transistor_joules"),
            "J",
            high=39e-3,
            source="single-pulse avalanche energy of the CSD17577Q3A, 39 mJ, taken as "
            "the measure of what the part bears in microseconds (TI SLPS515A, page 1)",
        ),
        Figure(
            "gate",
            "Highest voltage of the gate of the ampere pair",
            most("gate"),
            "V",
            source="",
        ),
        Figure(
            "suppressor_amps",
            "Largest current in the suppressor D14",
            most("suppressor_amps"),
            "A",
            expected=16.9,
            source="section 16: up to 16.9 A for microseconds, simulated before; the "
            "datasheet rates 12.3 A for the 10/1000 us wave",
        ),
        Figure(
            "suppressor_share",
            "Largest pulse power of the suppressor as a share of its rating at that width",
            100.0 * most("suppressor_share"),
            "%",
            high=100.0,
            source="Vishay 88390, page 4, figure 1, read from the curve",
        ),
        Figure(
            "suppressor_energy",
            "Largest energy in the suppressor per event",
            most("suppressor_joules"),
            "J",
            source="",
        ),
        Figure(
            "fuse",
            "Largest I2t of the event as a share of the melting figure of the fuse F1",
            100.0 * most("fuse") / common.FUSE_MELT,
            "%",
            high=100.0,
            source="Littelfuse 466 series, page 1: 1.764 A2s nominal",
        ),
        Figure(
            "damper_power",
            "Largest power in the resistor R87 of the damped branch",
            most("damper_watts"),
            "W",
            high=_DAMPER_PULSE_WATTS,
            source="Vishay 20019, page 3: single pulse of 10 us, read from the curve",
        ),
        Figure(
            "damper_energy",
            "Largest energy in the resistor R87 per event",
            most("damper_joules"),
            "J",
            source="",
        ),
        Figure(
            "bound",
            "Largest current in a diode of the gate bound (D17)",
            most("bound"),
            "A",
            high=_BOUND_AMPS,
            source="BAV199: 1 A for 1 ms, 4 A for 1 us (Nexperia, page 2)",
        ),
        Figure(
            "driver",
            "Largest current from the gate network back into the driver output (R79)",
            most("back"),
            "A",
            high=0.5,
            source="the driver withstands 0.5 A of reverse current (Microchip DS20001422G, page 3)",
        ),
        Figure(
            "hold_off",
            "Largest collector current of the hold-off transistor Q7",
            most("hold_off"),
            "A",
            high=0.2,
            source="peak collector current of the BC847B, 200 mA (Diodes DS11108, page 2)",
        ),
    ]


@bench(
    "path_switching",
    "short",
    "A short circuit in ampere mode: the trip opens the output and the supply leads kick",
    "sections 4.3 and 4.9 (supply node, D-63; bound of the gate, D-61; suppressor, D-60), "
    "section 4.4 and rule F-18 (trip), the tests of sections 11 and 16",
)
def short(ctx: Context) -> Outcome:
    """Ampere mode on a stiff 5 V supply, and the output terminal is shorted.

    The ampere pair and the output pair are closed, range 3 is selected and
    the load takes 100 mA. Then a short circuit of 5 mohm closes at the
    terminal. The current rises as fast as the supply leads allow until the
    over-current trip opens the output pair: 12 us after the shunt passes
    1.15 A, plus 0.3 us for the amplifier and the comparator. From then on
    the current of the leads has to go somewhere: into the capacitor of the
    supply node and its damped branch, and, once the ampere pair works as a
    follower against its bounded gate, into the suppressor of the VIN
    terminal. The run is made with 0.5 uH to 3 uH of leads, with the longest
    qualification time of rule F-18, with the parts that let the node and
    the terminal rise highest, with a short behind 1 m of cable and, for
    comparison, without the damped branch.
    """
    first = ctx.run_many({case.tag: _deck(ctx, case, None) for case in _CASES})
    instants = {case.tag: _opens(case, first[case.tag]) for case in _CASES}
    runs = ctx.run_many({case.tag: _deck(ctx, case, instants[case.tag]) for case in _CASES[1:]})
    shown_case = _CASES[0]
    runs[shown_case.tag] = ctx.run(shown_case.tag, _deck(ctx, shown_case, instants[shown_case.tag]))
    seen = {case.tag: _seen(ctx, case, runs[case.tag]) for case in _CASES}
    figures: list[Figure] = []
    for case in _CASES:
        figures += _per_run(case, seen[case.tag])
    figures += _worst([seen[case.tag] for case in _CASES if case.damper])
    with_damper = [seen[case.tag].node for case in _CASES if case.damper]
    figures.append(
        Figure(
            "margin",
            "Supply node below +12 V_A at the least, runs with the damper",
            common.RAIL_VOLTS - max(with_damper),
            "V",
            low=0.5,
            source="section 4.9: 0.5 V or more below the supply of the multiplexer",
        )
    )

    run = runs[shown_case.tag]
    time = run.real("time")
    micro = (time - _SHORT) * 1e6
    near = (micro >= -2.0) & (micro <= 45.0)
    opened = (instants[shown_case.tag] - _SHORT) * 1e6
    waves = Graph(
        name="kick",
        title=f"Short circuit in ampere mode on 5 V, {shown_case.text} of leads, typical parts",
        xlabel="Time after the short circuit (us)",
        panels=(
            Panel(
                "Voltage (V)",
                marks=((common.NODE_LIMIT, "11.5 V"), (common.TRANSISTOR_VOLTS, "30 V")),
            ),
            Panel("Gates (V)", marks=((common.RAIL_VOLTS, "+12 V_A"),)),
            Panel("Current (A)"),
        ),
        traces=(
            Trace(micro[near], run.real("vin_p")[near], "VIN behind the fuse (TP27)", 0),
            Trace(micro[near], run.real("supply")[near], "supply node (TP33)", 0),
            Trace(
                micro[near], run.real("s_amp")[near], "common source of the ampere pair", 0, "--"
            ),
            Trace(micro[near], run.real("vout")[near], "output terminal", 0, ":"),
            Trace(micro[near], run.real("g_amp")[near], "gate of the ampere pair (TP32)", 1),
            Trace(micro[near], run.real("out_gate")[near], "gate of the output pair (TP37)", 1),
            Trace(micro[near], run.real("gate_out")[near], "line GATE_OUT", 1, "--"),
            Trace(micro[near], run.real("vlead#branch")[near], "supply leads", 2),
            Trace(micro[near], run.real("vdut#branch")[near], "into the short circuit", 2, "--"),
            Trace(micro[near], run.real("@r87[i]")[near], "damped branch (R87)", 2),
            Trace(
                micro[near],
                np.maximum(np.abs(run.real("@d.xd14.d1[id]")), np.abs(run.real("@d.xd14.d2[id]")))[
                    near
                ],
                "suppressor D14",
                2,
                ":",
            ),
        ),
        xmarks=((opened, "GATE_OUT falls"),),
    )
    traces = []
    for case in _CASES:
        if case.qualify != _QUALIFY or case.cable > 100e-9:
            continue
        if case.parts not in ("typical", "corner") or case.henries == 1e-6:
            continue
        if case.parts == "corner" and case.henries != 2e-6:
            continue
        other = runs[case.tag]
        axis = (other.real("time") - instants[case.tag]) * 1e6
        inside = (axis >= -3.0) & (axis <= 40.0)
        style = "-" if case.damper else "--"
        traces.append(Trace(axis[inside], other.real("supply")[inside], case.text, 0, style))
        traces.append(Trace(axis[inside], other.real("vin_p")[inside], case.text, 1, style))
    every = Graph(
        name="all",
        title="Leads, parts and the damped branch: supply node and VIN line at the trip",
        xlabel="Time after GATE_OUT falls (us)",
        panels=(
            Panel(
                "Supply node (TP33) (V)",
                marks=((common.NODE_LIMIT, "11.5 V"), (common.RAIL_VOLTS, "+12 V_A")),
            ),
            Panel(
                "VIN behind the fuse (TP27) (V)",
                marks=((common.TRANSISTOR_VOLTS, "30 V"), (_TERMINAL_LIMIT, "36 V")),
            ),
        ),
        traces=tuple(traces),
    )
    notes = (
        "The external supply is a voltage source behind its leads, 40 mohm per uH: "
        "a supply that limits its current at 10 A still delivers the surge from its "
        "output capacitor, which this stands for. The short circuit is 5 mohm behind "
        "50 nH, or behind 1 uH and 40 mohm for 1 m of cable.",
        "The trip is not simulated as a program: a first pass finds the instant at "
        "which the 0.1 ohm shunt passes 115 mV, and the line GATE_OUT falls 0.3 us "
        "plus the qualification time after it. The 0.3 us for amplifier, filter and "
        "comparator are an assumption. The output pair, its gate network and the "
        "suppressor of the output terminal are the parts of the schematic with the "
        "models of their block; this bench does not judge them.",
        "The voltage on VIN behind the fuse is the voltage across the suppressor "
        "D14, the detector divider and the monitor divider. The transistor Q5 "
        "blocks that voltage less the voltage of its source, which stands near "
        "10 V at that moment: that difference, not the terminal voltage, is what "
        "its 30 V rating limits.",
        "The suppressor model clamps at the datasheet maximum for a pulse of a "
        "millisecond; in microseconds a real part clamps lower. The corner parts "
        "are: transistors with the lowest threshold, the diodes of the gate bound "
        "with the highest forward voltage, the suppressor at its upper limit and "
        "both capacitors of the node at 40 % of their value (an assumption for "
        "their loss under bias).",
        "The transistor models have no avalanche and no heating. The energy in the "
        "transistor on the supply side is compared with its avalanche rating for "
        "want of a better figure: the datasheet gives the safe operating area from "
        "10 us on, where 20 V allow about 60 A.",
        "The gate of the ampere pair is bound through two diodes in series: one "
        "diode into the driver output behind 22 ohm, and from there the second one "
        "to +12 V_A. It therefore rises to about two diode drops above the rail "
        "while the bound carries current.",
    )
    return Outcome(tuple(figures), (waves, every), notes)
