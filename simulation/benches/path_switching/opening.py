"""A mode pair opens under load: gate discharge, time to block, kick of the leads."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.path_switching import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_REQUEST = 2e-6
"""Instant at which the request of the pair goes low."""

_END = 80e-6

_REST = 20e-6
"""Time after the request at which the resting gate level is read."""

_THRESHOLD_LEAST = 1.1
"""Lowest gate threshold of the CSD17577Q3A at 250 uA, V (TI SLPS515A, page 3)."""

_ESTIMATE = (20.0, 24.0)
"""Voltage on VIN that rule F-23 states for a pair opened under load (estimate)."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One run: a pair that opens while it carries a load current.

    Attributes:
        pair: ``ampere`` or ``source``.
        volts: Voltage of the supply or of the regulator output.
        amps: Load current before the pair opens.
        henries: Inductance of the supply leads (ampere pair only).
        corner: Empty for typical parts; ``slow`` for the slowest opening the
            datasheets allow; ``clamp`` for the suppressor at its upper limit.
    """

    pair: str
    volts: float
    amps: float
    henries: float = 0.0
    corner: str = ""

    @property
    def tag(self) -> str:
        """Short name of the run, also part of the figure keys."""
        text = f"{self.pair}_{self.volts:g}v_{self.amps:g}a"
        if self.pair == "ampere":
            text += f"_{self.henries * 1e6:g}uh"
        if self.corner:
            text += f"_{self.corner}"
        return text.replace(".", "p")

    @property
    def suffix(self) -> str:
        """The suffix of the node names of this pair."""
        return "amp" if self.pair == "ampere" else "src"

    @property
    def text(self) -> str:
        """The case as the labels name it."""
        leads = f", {self.henries * 1e6:g} uH" if self.pair == "ampere" else ""
        corner = {
            "": "",
            "slow": ", slowest parts",
            "clamp": ", suppressor at its upper limit",
        }[self.corner]
        return f"{self.pair} pair, {self.volts:g} V, {self.amps:g} A{leads}{corner}"


_CASES = (
    _Case("ampere", 5.0, 1.0, 1e-6),
    _Case("ampere", 5.0, 0.5, 0.5e-6),
    _Case("ampere", 5.0, 1.0, 0.5e-6),
    _Case("ampere", 5.0, 1.0, 0.5e-6, "clamp"),
    _Case("ampere", 5.0, 1.0, 3e-6),
    _Case("ampere", 0.8, 1.0, 1e-6),
    _Case("ampere", 0.8, 1.0, 1e-6, "slow"),
    _Case("source", 5.0, 1.0),
    _Case("source", 0.8, 1.0),
    _Case("source", 0.8, 1.0, corner="slow"),
)
"""The first case is the one that is drawn."""


def _overrides(case: _Case) -> dict[str, PartModel]:
    """The models that a corner replaces."""
    if case.corner == "clamp":
        return {"D14": common.suppressor("HI")}
    if case.corner == "slow":
        # Longest delay and highest output resistance of the driver at 25 C
        # (datasheet), the highest forward voltage of the turn-off diodes and
        # transistors that conduct down to the lowest gate voltage.
        slow: dict[str, PartModel] = {
            "U20": common.driver(delay=50e-9, ohms=10.0),
            "D16": common.diode_pair("HI"),
            "D17": common.diode_pair("HI"),
        }
        slow.update({ref: common.transistor("LO") for ref in ("Q4", "Q5", "Q8", "Q9")})
        return slow
    return {}


def _deck(ctx: Context, case: _Case) -> str:
    """The pair of a case is closed and loaded, then its request goes low."""
    edge = ((0.0, True), (_REQUEST, False))
    if case.pair == "ampere":
        stimulus = (
            common.supply(case.volts, henries=case.henries)
            + common.no_regulator()
            + common.requests(ampere=edge)
        )
    else:
        stimulus = common.regulator(case.volts) + common.no_supply() + common.requests(source=edge)
    stimulus += (
        "* the load: a resistor on the node after the shunts; the output pair and\n"
        "* the device under test belong to another block\n"
        f"Rload vout_s 0 {case.volts / case.amps:g}\n"
    )
    control = [
        "save all @mq4[id] @mq5[id] @dd16_1[id] @dd17_1[id] @d.xd14.d1[id] @d.xd14.d2[id]",
        f"tran 1n {_END:g} 0 5n",
    ]
    return common.deck(
        ctx,
        f"Opening under load: {case.text}",
        common.circuit(ctx, overrides=_overrides(case)),
        common.rails(),
        common.range_lines(3),
        stimulus,
        control=control,
    )


def _figures(ctx: Context, case: _Case, run: RunResult) -> list[Figure]:
    """The figures of one run."""
    suffix = case.suffix
    time = run.real("time")
    gate, source = run.real(f"g_{suffix}"), run.real(f"s_{suffix}")
    feed = run.real("vin_p" if case.pair == "ampere" else "ldo_out")
    through = common.through(ctx, run, case.pair)
    before = measure.mean(time, through, 0.0, _REQUEST)
    edge = measure.first_crossing(
        time, run.real(f"gate_{suffix}"), common.LOGIC_VOLTS / 2.0, rising=False
    )
    blocked = measure.first_crossing(time, through, 0.1 * before, rising=False, after=edge)
    diode = run.real("@dd17_1[id]" if case.pair == "ampere" else "@dd16_1[id]")
    tag, text = case.tag, case.text
    figures = [
        Figure(
            f"blocks_{tag}",
            f"Current below 10 % after the request falls: {text}",
            blocked - edge,
            "s",
            high=1e-6,
            source="section 4.2: within 1 us (0.1 us to 0.3 us simulated before)",
        ),
        Figure(
            f"vds_{tag}",
            f"Largest voltage across the transistor on the supply side: {text}",
            float(np.max(feed - source)),
            "V",
            high=common.TRANSISTOR_VOLTS,
            source="rating of the CSD17577Q3A, 30 V (TI SLPS515A, page 1)",
        ),
        Figure(
            f"vds_node_{tag}",
            f"Largest voltage across the transistor on the ladder side: {text}",
            float(np.max(run.real("supply") - source)),
            "V",
            high=common.TRANSISTOR_VOLTS,
            source="rating of the CSD17577Q3A, 30 V (TI SLPS515A, page 1)",
        ),
        Figure(
            f"diode_{tag}",
            f"Largest current in the turn-off diode: {text}",
            float(np.max(diode)),
            "A",
            high=common.DIODE_REPEAT_AMPS,
            source="repetitive peak current of the BAV199, 0.5 A (Nexperia, page 2)",
        ),
        Figure(
            f"rest_{tag}",
            f"Gate-source voltage 20 us after the request fell: {text}",
            measure.value_at(time, gate - source, edge + _REST),
            "V",
            source="for comparison: the lowest threshold of the transistors is 1.1 V at "
            "250 uA and 25 C (TI SLPS515A, page 3)",
        ),
    ]
    if case.pair == "ampere":
        terminal = run.real("vin_p")
        clamp = np.maximum(np.abs(run.real("@d.xd14.d1[id]")), np.abs(run.real("@d.xd14.d2[id]")))
        after = time >= blocked
        estimate = case.volts == 5.0 and case.henries == 0.5e-6
        figures += [
            Figure(
                f"kick_{tag}",
                f"Highest voltage on VIN behind the fuse: {text}",
                float(np.max(terminal)),
                "V",
                low=_ESTIMATE[0] if estimate else None,
                high=_ESTIMATE[1] if estimate else None,
                source="rule F-23: 20 V to 24 V at 0.5 A to 1 A with 0.5 uH, estimate"
                if estimate
                else "",
            ),
            Figure(
                f"swing_{tag}",
                f"Lowest voltage on VIN behind the fuse after the kick: {text}",
                float(np.min(terminal[after])),
                "V",
                source="",
            ),
            Figure(
                f"back_{tag}",
                f"Largest current back through the pair after it blocked: {text}",
                float(np.max(-through[after])),
                "A",
                source="",
            ),
            Figure(
                f"suppressor_{tag}",
                f"Largest current in the suppressor: {text}",
                float(np.max(clamp)),
                "A",
                high=common.SUPPRESSOR_PULSE_AMPS,
                source="peak pulse current of the SMAJ20CA, 12.3 A (Vishay 88390, page 2)",
            ),
        ]
    return figures


@bench(
    "path_switching",
    "open",
    "A mode pair opens under load: time to block and the kick of the supply leads",
    "sections 4.2 and 4.9 (opening through a diode, D-61), rule F-23",
)
def opening(ctx: Context) -> Outcome:
    """A closed pair carries a load current and its request goes low.

    The driver pulls the gate down through one diode of the pair of diodes
    and 22 ohm. The run shows the gate, the current in the transistors and,
    for the ampere pair, the VIN line: the current of the supply leads has
    nowhere to go once the pair blocks, and the suppressor takes it. The
    load is a resistor on the node after the shunts, so the supply node
    falls after the pair has opened. This is not the order of normal
    operation, in which the output pair opens first (rule F-23); it is what
    the paths of rules F-7, F-26 and F-27 do. Two corners are run: the
    slowest opening that the datasheets of the driver, the diodes and the
    transistors allow, and the suppressor at its highest breakdown voltage.
    """
    runs = ctx.run_many({case.tag: _deck(ctx, case) for case in _CASES[1:]})
    first = _CASES[0]
    runs[first.tag] = ctx.run(first.tag, _deck(ctx, first))
    figures: list[Figure] = []
    for case in _CASES:
        figures += _figures(ctx, case, runs[case.tag])

    def window(run: RunResult, stop: float) -> tuple[np.ndarray, np.ndarray]:
        time = run.real("time")
        inside = (time >= _REQUEST - 0.2e-6) & (time <= _REQUEST + stop)
        return inside, (time[inside] - _REQUEST) * 1e6

    shown = runs[first.tag]
    inside, micro = window(shown, 1.3e-6)

    def cut(name: str) -> np.ndarray:
        return np.asarray(shown.real(name)[inside], dtype=np.float64)

    close_up = Graph(
        name="ampere-1a",
        title="The ampere pair opens at 1 A on 5 V behind 1 uH of leads",
        xlabel="Time after the request falls (us)",
        panels=(
            Panel("Gate network (V)"),
            Panel("Path (V)", marks=((common.TRANSISTOR_VOLTS, "rating of the transistors"),)),
            Panel("Current (A)"),
        ),
        traces=(
            Trace(micro, cut("gate_amp"), "request GATE_AMP", 0, "--"),
            Trace(micro, cut("drv_amp"), "driver output", 0, ":"),
            Trace(micro, cut("g_amp"), "gate (TP32)", 0),
            Trace(micro, cut("s_amp"), "common source of the pair", 0),
            Trace(micro, cut("vin_p"), "VIN behind the fuse (TP27)", 1),
            Trace(micro, cut("supply"), "supply node (TP33)", 1),
            Trace(micro, common.through(ctx, shown, "ampere")[inside], "transistor Q5", 2),
            Trace(micro, cut("vlead#branch"), "supply leads", 2, "--"),
            Trace(micro, cut("@dd17_1[id]"), "turn-off diode of D17", 2, ":"),
        ),
    )
    traces = []
    for case in _CASES:
        run = runs[case.tag]
        if case.pair != "ampere" or case.corner:
            continue
        inside, micro = window(run, 2.5e-6)
        traces.append(Trace(micro, run.real("vin_p")[inside], case.text, 0))
        traces.append(Trace(micro, common.through(ctx, run, "ampere")[inside], case.text, 1))
    kick = Graph(
        name="kick",
        title="The ampere pair opens: the VIN line rings on its leads",
        xlabel="Time after the request falls (us)",
        panels=(
            Panel(
                "VIN behind the fuse (V)",
                marks=((22.2, "suppressor conducts from 22.2 V"),),
            ),
            Panel("Current in the transistor Q5 (A)"),
        ),
        traces=tuple(traces),
    )
    slow = runs[_CASES[6].tag]
    time = slow.real("time")
    micro = (time - _REQUEST) * 1e6
    rest = Graph(
        name="rest",
        title="After the opening at 0.8 V, slowest parts: where gate and source come to rest",
        xlabel="Time after the request falls (us)",
        panels=(
            Panel("Gate network (V)"),
            Panel("Gate-source voltage (V)", marks=((_THRESHOLD_LEAST, "lowest threshold"),)),
        ),
        traces=(
            Trace(micro, slow.real("g_amp"), "gate (TP32)", 0),
            Trace(micro, slow.real("s_amp"), "common source of the pair", 0),
            Trace(micro, slow.real("supply"), "supply node (TP33)", 0, "--"),
            Trace(micro, np.clip(slow.real("g_amp") - slow.real("s_amp"), -1.0, 3.0), "", 1),
        ),
    )
    notes = (
        "The load is a resistor on the node after the shunts; the output pair, the "
        "cable and the device under test belong to another block. The regulator is "
        "a voltage source and the external supply a voltage source behind its leads.",
        "The capacitance on the VIN line that the leads ring against is that of the "
        "models of the suppressor and of the transistor, about 1 nF; the capacitance "
        "of the leads themselves and of the supply is not in the circuit. The height "
        "of the kick depends on it: rule F-23 states 20 V to 24 V as an estimate, the "
        "runs give 16 V at 0.5 A and 24 V to 25 V at 1 A, all below what the "
        "transistors and the suppressor bear.",
        "After the kick the line swings below ground on its leads. The transistor on "
        "the supply side then conducts through its body diode and the one on the "
        "ladder side as a follower, for some tens of nanoseconds: a current flows "
        "back from the supply node. The lead model has no loss but its resistance, "
        "so a real line rings less.",
        "After the opening the gate rests one diode drop above ground for as long as "
        "the ramp capacitor discharges through that diode, about 3 ms, and the "
        "common source floats near ground: 0.86 V to 1.08 V of gate-source voltage "
        "in these runs, against a lowest threshold of 1.1 V at 250 uA and 25 C that "
        "falls by about 4.6 mV/K (datasheet). The pair is a follower in both "
        "directions and can lift neither side above its gate less a threshold, "
        "which is near 0 V, so nothing follows from it for a load; no model here "
        "gives the current that flows meanwhile. The specification describes the "
        "same state for the output pair and not for the mode pairs.",
        "The forward recovery of the turn-off diode (1.75 V at the most at 10 mA, "
        "datasheet) is not modelled. The driver is a behavioral model; the slow "
        "corner gives it 50 ns and 10 ohm, the datasheet limits at 25 C. The "
        "transistor model has no avalanche: the figures are the voltages it would "
        "have to block.",
    )
    return Outcome(tuple(figures), (close_up, kick, rest), notes)
