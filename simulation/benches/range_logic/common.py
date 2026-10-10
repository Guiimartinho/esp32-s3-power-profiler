"""The measuring front end in a closed loop, and what stands around it.

Every bench of the range control logic runs the same circuit: the shunt
ladder with its multiplexer and gate drivers, the amplifier chain, the three
comparators and the output switch, as drawn, with the model of the range
sequencer between the comparator outputs and the lines of the controller.
This module names those parts, builds that circuit with the delays and the
comparator offsets a bench asks for, and writes what the schematic does not
hold: the source, the device under test with its leads, and the lines that
firmware would drive.

What is assumed here, and said in the notes of every bench:

- The source meter with its closed mode switch is a voltage source behind a
  resistance (``SOURCE_OHMS``). It holds its voltage: the response of the
  regulator is not in these runs.
- The device under test is a current sink beside a capacitor with a series
  resistance, behind a lead with resistance and, where a bench says so,
  inductance. The sink stops drawing below about 0.1 V, as a real load does.
- The sequencer is the model of rules F-16 to F-18; no program exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray

from benches import frontend
from circuit_sim import measure
from circuit_sim.bench import Context
from circuit_sim.circuit import Circuit, PartModel
from circuit_sim.engine import RunResult

Real = NDArray[np.float64]

OUTPUT_SWITCH = ("Q15", "Q16", "R115", "R116", "R117", "R120", "D20", "C74", "D21")
"""The output switch, its gate network and the suppressor of the terminal.

They are drawn on the output sheet. The guard buffer of that sheet is left
out: it loads the node after the shunts with 10 kohm into an amplifier input.
"""

ALIASES = {
    **frontend.ALIASES,
    "Net-(D21-K)": "vout",
    "Net-(Q15-G)": "g_out",
    "Net-(D20-common)": "g_out_rc",
    "Net-(D20-K)": "g_out_off",
    "Net-(Q15-S-Pad1)": "out_mid",
    "Net-(Q10-G)": "g_clamp_a",
    "Net-(Q11-G)": "g_clamp_b",
}
"""Short node names: the ones of the front end and the ones of the output switch."""

SOURCE_OHMS = 0.02
"""Resistance of the source as the supply node sees it (assumption).

Two transistors of the closed mode switch at about 5 mohm each and 10 mohm
for the output capacitor of the regulator and the copper between them.
"""

DUT_ESR = 5e-3
"""Series resistance of the capacitor at the device under test (assumption, ceramic)."""

LEAD_OHMS = 1e-3
"""Resistance from the output terminal to the device under test (assumption)."""

GAIN = 1.0 + 9900.0 / 523.0
"""Gain of the amplifier with the 523 ohm gain resistor (section 4.5)."""

PEDESTAL = 2.5 * 1.02 / (49.9 + 1.02)
"""Voltage at the reference pin of the amplifier, V (section 4.5)."""

DIVIDER = 4.01
"""Ratio of the divider in front of the comparators (section 4.4)."""

THRESHOLD_SHUNT = {"up": 0.09095, "oc": 0.11504, "jump": 0.15118}
"""Nominal thresholds at the shunt, V, calculated from the resistor values."""

THRESHOLD_BAND = {
    "up": (0.0875, 0.0944),
    "oc": (0.1114, 0.1187),
    "jump": (0.1472, 0.1551),
}
"""The thresholds at the shunt with tolerances, V (table of section 4.4)."""

HALF_LOGIC = frontend.LOGIC_VOLTS / 2.0
"""Level at which a line of the controller or a comparator output counts as high."""

CONDUCTS_AMPS = 0.05
"""Current from which the range 3 branch counts as conducting.

The specification gives no level. This is the one the earlier simulations
of the design used: 5 mV across the 0.1 ohm shunt, 5 % of the full scale
of range 3.
"""


CLAMP_TYPICAL = "IRLML0030_CLAMP"
CLAMP_LOW = "IRLML0030_CLAMP_LO"
CLAMP_HIGH = "IRLML0030_CLAMP_HI"
"""The clamp models of mosfets.lib: typical curve, threshold 0.4 V lower, 0.6 V higher."""


@dataclass(frozen=True, slots=True)
class Delays:
    """The delays between the shunt and the gate that a bench can vary.

    Attributes:
        mux_ohms: On-resistance of a channel of the multiplexer; with the
            capacitors at the amplifier inputs it delays the sense voltage.
        comparator: Propagation delay of the three comparators, s.
        reaction: Reaction time of the sequencer, s.
        driver: Propagation delay of the gate drivers, s.
        driver_ohms: Output resistance of the gate drivers.
    """

    mux_ohms: float = 250.0
    comparator: float = 47e-9
    reaction: float = 100e-9
    driver: float = 30e-9
    driver_ohms: float = 7.0


NOMINAL = Delays()
"""The models as they are: 250 ohm, 47 ns, a sequencer of 100 ns, 30 ns and 7 ohm."""

BEST = Delays(125.0, 47e-9, 20e-9, 20e-9, 7.0)
"""Fastest: 125 ohm, typical comparator, sequencer of 20 ns, typical driver at 18 V."""

WORST = Delays(430.0, 80e-9, 100e-9, 40e-9, 10.0)
"""Slowest with the sequencer at its limit of 100 ns (rule F-16).

430 ohm, the comparator at its 80 ns limit, and the driver at 40 ns, its
limit over temperature, with 10 ohm, its limit at 25 C (TC4427 datasheet
DS20001422G, pages 3 and 4).
"""


@dataclass(frozen=True, slots=True)
class Offsets:
    """Input offsets of the three comparators, V; a positive one raises the threshold.

    Attributes:
        up: Step-up comparator U32.
        oc: Over-current comparator, second half of U31.
        jump: Jump comparator, first half of U31.
    """

    up: float = 0.0
    oc: float = 0.0
    jump: float = 0.0


def offset_for(name: str, shunt_volts: float) -> float:
    """The comparator offset that puts a threshold at a given shunt voltage.

    The benches use it to move a threshold to a limit of the band that the
    specification states, whatever mix of resistor tolerances and offset
    gives that limit on a board.

    Args:
        name: ``up``, ``oc`` or ``jump``.
        shunt_volts: Where the threshold shall lie, referred to the shunt.
    """
    return (shunt_volts - THRESHOLD_SHUNT[name]) * GAIN / DIVIDER


def _with_params(ctx: Context, ref: str, **params: float) -> PartModel:
    """The model of a part as the open model map gives it, with parameters."""
    base = ctx.models.model_of(ctx.netlist.component(ref))
    return replace(base, params=" ".join(f"{name}={value:g}" for name, value in params.items()))


def slow_amplifier(ctx: Context) -> dict[str, PartModel]:
    """The amplifier with half the bandwidth of its model, as a sensitivity.

    The datasheet of the amplifier gives typical bandwidths and no spread;
    half of the model, about 3.2 MHz at this gain, is the assumption that
    the earlier simulations of the design made for their worst case.
    """
    base = ctx.models.model_of(ctx.netlist.component("U27"))
    return {"U27": replace(base, params="gbwi=100meg fout=5meg")}


def overrides(
    ctx: Context,
    delays: Delays = NOMINAL,
    offsets: Offsets | None = None,
    clamps: tuple[str, str] | None = None,
) -> dict[str, PartModel]:
    """The models that differ from the model map for a set of delays and offsets.

    Multiplexer, drivers and clamp transistors get an entry only when their
    figures differ from the ones of the model map. The comparators always
    get one: they keep the model written here also in the vendor tier, where
    the range 3 switch and the output switch take the model of their
    manufacturer.

    Args:
        ctx: The bench context.
        delays: Delays between the shunt and the gate.
        offsets: Offsets of the comparators; none when left out.
        clamps: Model names of mosfets.lib for the two transistors of the
            ladder clamp, Q10 and Q11, for the spread of their threshold; the
            typical curve when left out.
    """
    offsets = offsets or Offsets()
    found: dict[str, PartModel] = {}
    if delays.mux_ohms != NOMINAL.mux_ohms:
        found["U24"] = _with_params(ctx, "U24", ron=delays.mux_ohms)
    if (delays.driver, delays.driver_ohms) != (NOMINAL.driver, NOMINAL.driver_ohms):
        for ref in ("U22", "U23"):
            found[ref] = _with_params(ctx, ref, td=delays.driver, ro=delays.driver_ohms)
    # The comparators keep the model written here in both tiers: a run has to
    # start with their hysteresis in a known state (see rest), and that state
    # is a node of this model.
    found["U32"] = _with_params(ctx, "U32", td=delays.comparator, vos=offsets.up)
    found["U31"] = PartModel(
        kind="subckt",
        name="RL_MCP6562",
        ports=("1", "2", "3", "4", "5", "6", "7", "8"),
        library="range_logic.lib",
        origin="written here",
        params=(
            f"tda={delays.comparator:g} tdb={delays.comparator:g} "
            f"vosa={offsets.jump:g} vosb={offsets.oc:g}"
        ),
    )
    if clamps is not None:
        for ref, name in zip(("Q10", "Q11"), clamps, strict=True):
            found[ref] = replace(ctx.models.model_of(ctx.netlist.component(ref)), name=name)
    return found


def front_end(
    ctx: Context,
    delays: Delays = NOMINAL,
    offsets: Offsets | None = None,
    *,
    clamps: tuple[str, str] | None = None,
    scales: Mapping[str, float] | None = None,
    more: Mapping[str, PartModel] | None = None,
) -> Circuit:
    """Ladder, amplifier chain, comparators and output switch as drawn.

    Args:
        ctx: The bench context.
        delays: Delays between the shunt and the gate.
        offsets: Offsets of the comparators.
        clamps: Model names for the two transistors of the ladder clamp.
        scales: Factors on the values of passive parts, for tolerance runs.
        more: Further models that replace the ones of the model map.
    """
    refs = (
        *frontend.ladder_refs(ctx.netlist),
        *frontend.chain_refs(ctx.netlist),
        *frontend.comparator_refs(ctx.netlist),
        *OUTPUT_SWITCH,
    )
    replaced = {**overrides(ctx, delays, offsets, clamps), **(more or {})}
    return ctx.circuit(refs, ALIASES, replaced, scales)


def source(volts: float, ohms: float = SOURCE_OHMS) -> str:
    """The source meter as a voltage source behind a resistance, on the supply node."""
    return (
        f"* source meter and closed mode switch: {volts:g} V behind {ohms * 1e3:g} mohm\n"
        f"Vsrc src 0 {volts:g}\n"
        f"Rsrc src supply {ohms:g}\n"
    )


def controller(
    delays: Delays = NOMINAL,
    *,
    overlap: float = 1e-6,
    blanking: float = 2e-6,
    trip_time: float = 12e-6,
    down: str = "0",
    output_on: str = f"{frontend.LOGIC_VOLTS:g}",
) -> str:
    """The sequencer on the comparator outputs, and the lines firmware would drive.

    Args:
        delays: Its reaction time is the one of the sequencer.
        overlap: Make-before-break overlap (rule F-17).
        blanking: Blanking time after the last change of a line (rule F-17).
        trip_time: Qualification time of the over-current trip (rule F-18).
        down: Source value of the step-down request, a level or a waveform.
        output_on: Source value of the request to close the output switch.
    """
    return (
        frontend.sequencer(delays.reaction, overlap, blanking, trip_time, comparators=True)
        + "* lines that firmware would drive: step-down request, enable, output request\n"
        f"Vdown seq_down 0 {down}\n"
        f"Venable seq_enable 0 {frontend.LOGIC_VOLTS:g}\n"
        f"Vouton seq_out_on 0 {output_on}\n"
    )


_COMPARATOR_OUTPUTS = ("cmp_up", "cmp_oc", "cmp_jump")
"""Nodes of the three comparator outputs."""


GATE_VOLTS = 12.0
"""Level of a gate that its driver holds high: the +12 V rail."""


def rest(
    circuit: Circuit,
    index: int | None,
    high: Sequence[str] = (),
    *,
    sequencer: bool = True,
    output_on: bool = True,
) -> str:
    """Lines that define the state in which a run starts.

    The loop through the comparators and the sequencer has more than one
    stable state, and each comparator has two by its hysteresis. Left alone,
    the search for the operating point ends in any of them or in none. The
    lines hold nodes at the values they have at rest while the simulator
    finds that point, and release them when the run starts: the three
    latches of the sequencer and the latch of the trip, the node that
    carries the hysteresis of each comparator, and the gates of the
    switches, which rest at the level of their drivers. The run then starts
    from the circuit at rest in the range asked for.

    The model of the sequencer has no input that selects a range, as
    firmware does before a path closes (rule F-20); this is how a run starts
    in a range other than 0.

    Args:
        circuit: The circuit of the run; the nodes to hold are looked up in it.
        index: Range at rest; None for a circuit without the ladder.
        high: Outputs of the comparators (``cmp_up``, ``cmp_oc``,
            ``cmp_jump``) that are high in the state at rest.
        sequencer: Whether the model of the sequencer is in the deck.
        output_on: Whether the output switch is closed at rest.
    """
    unknown = set(high) - set(_COMPARATOR_OUTPUTS)
    if unknown:
        raise ValueError(f"no comparator output is named {sorted(unknown)}")
    if index is not None and not 0 <= index <= 3:
        raise ValueError(f"there is no range {index}")
    held: list[str] = []
    for line in circuit.lines:
        words = line.split()
        element = words[0].lower()
        if "MCP656X" in words:
            held.append(f"v({element}.h)={int(words[3] in high)}")
        elif "RL_MCP6562" in words:
            held.append(f"v({element}.xa.h)={int(words[1] in high)}")
            held.append(f"v({element}.xb.h)={int(words[7] in high)}")
    nodes = set(circuit.nodes.values())
    if index is not None:
        held += [
            f"v(g_r{gate})={GATE_VOLTS if gate == index else 0:g}"
            for gate in (1, 2, 3)
            if f"g_r{gate}" in nodes
        ]
        level = GATE_VOLTS if output_on else 0.0
        held += [f"v({node})={level:g}" for node in ("g_out", "g_out_rc") if node in nodes]
    if sequencer and index is not None:
        held += [f"v(xseq.l{latch})={int(index >= latch)}" for latch in (1, 2, 3)]
        held.append("v(xseq.trip)=0")
    state = "on" if output_on else "off"
    where = "" if index is None else f" in range {index}, the output {state}"
    lines = [f"* the run starts at rest{where}"]
    if held:
        lines.append(".ic " + " ".join(held))
    return "\n".join(lines) + "\n"


def request(at: float, width: float = 1e-6) -> str:
    """One step-down request of firmware: a pulse on the request line."""
    level = frontend.LOGIC_VOLTS
    return pwl(
        ((0.0, 0.0), (at, 0.0), (at + 10e-9, level), (at + width, level), (at + width + 10e-9, 0.0))
    )


def pwl(points: Sequence[tuple[float, float]]) -> str:
    """A piecewise linear waveform from (time, value) pairs."""
    return "PWL(" + " ".join(f"{time:.9g} {value:.9g}" for time, value in points) + ")"


def step(before: float, after: float, at: float, edge: float = 10e-9) -> str:
    """One step of a current or voltage, with a finite edge."""
    return pwl(((0.0, before), (at, before), (at + edge, after)))


def dut(
    current: str,
    capacitance: float | None,
    *,
    esr: float = DUT_ESR,
    lead_ohms: float = LEAD_OHMS,
    lead_henries: float = 0.0,
    node: str = "vout",
) -> str:
    """The device under test on the output terminal.

    Args:
        current: Waveform of the load current in amperes (a level or ``PWL``).
        capacitance: Capacitor beside the load; none when left out.
        esr: Series resistance of that capacitor.
        lead_ohms: Resistance of the lead from the terminal to the device.
        lead_henries: Inductance of that lead; none when zero.
        node: The node of the terminal.
    """
    lines = [
        "* device under test: a lead, a capacitor with its series resistance and",
        "* a current sink that stops drawing below about 0.1 V",
    ]
    if lead_henries > 0.0:
        lines += [f"Rlead {node} lead {lead_ohms:g}", f"Llead lead dut {lead_henries:g}"]
    else:
        lines.append(f"Rlead {node} dut {lead_ohms:g}")
    if capacitance is not None:
        lines += [f"Cdut dut dut_c {capacitance:g}", f"Resr dut_c 0 {esr:g}"]
    lines += [
        f"Vprog iprog 0 {current}",
        "Rprog iprog 0 1k",
        "Bload dut 0 I = v(iprog)*0.5*(1 + tanh((v(dut) - 0.1)/0.02))",
    ]
    return "\n".join(lines) + "\n"


VENDOR_NOTE = (
    "Vendor tier: the range 3 switch and the two transistors of the output switch "
    "take the model of their manufacturer. The comparators keep the model written "
    "here, because the loop finds its operating point only with their hysteresis "
    "held, and the model of the manufacturer offers no node for that. The bench "
    "models/range-logic-mcp6561 puts the two comparator models side by side."
)
"""Note for the benches of the closed loop: what the vendor tier changes."""

OPTIONS = ("method=gear", "trtol=1", "itl4=100", "abstol=1e-9")
"""Simulator options of a transient run with the models written here.

Gear integration, a truncation error limit of 1 in place of 7, more
iterations for a time point than the 10 of the default, and a current
limit of convergence of 1 nA in place of 1 pA.

The truncation error limit: the comparator model has a hysteresis that
regenerates with a time constant of 2 ns. On a voltage that creeps up to a
threshold in steps of a microsecond, the solver with its default limit
arrives at the instant of the regeneration with a step far too long,
fails, shortens the step by 8 again and again and ends with "timestep too
small", naming a clamp transistor that carries no current. With the
tighter limit it shortens its steps as soon as the state of the comparator
begins to move.

The current limit: a switch of a few milliohms that carries microamperes
cannot be solved to 1 pA, because the noise of its node voltages times its
conductance is larger. No bench of this block reads a current below a
microampere.
"""

VENDOR_OPTIONS = ("method=gear", "itl4=100", "abstol=1e-9", "vntol=1e-5")
"""Simulator options of a transient run in the vendor tier.

With the transistor model of the manufacturer the tighter truncation error
limit makes a run of microseconds take longer than half an hour. The vendor
tier therefore keeps the default limit and gets convergence limits of 1 nA
and 10 uV in place of 1 pA and 1 uV, with which most of its runs get
through the range changes. No bench of this block reads a current below a
microampere.
"""


def options(ctx: Context) -> tuple[str, ...]:
    """The simulator options of a transient run in the tier of a context."""
    return VENDOR_OPTIONS if ctx.tier == "vendor" else OPTIONS


STEP_AT = 2e-6
"""Instant of the event in a run: the circuit rests for this long before it."""


@dataclass(frozen=True, slots=True)
class Load:
    """A device under test and what it does in a run.

    Attributes:
        before: Load current before the event, A.
        after: Load current after it, A.
        capacitance: Capacitor beside the load, F; none when left out.
        esr: Series resistance of that capacitor, ohm.
        lead_ohms: Resistance of the lead from the terminal to the device.
        lead_henries: Inductance of that lead.
        edge: Duration of the current edge, s.
    """

    before: float = 1e-6
    after: float = 0.5
    capacitance: float | None = 1e-6
    esr: float = DUT_ESR
    lead_ohms: float = LEAD_OHMS
    lead_henries: float = 0.0
    edge: float = 10e-9

    def text(self, at: float = STEP_AT) -> str:
        """The lines of the device with its current stepping at an instant."""
        return dut(
            step(self.before, self.after, at, self.edge),
            self.capacitance,
            esr=self.esr,
            lead_ohms=self.lead_ohms,
            lead_henries=self.lead_henries,
        )


def step_deck(
    ctx: Context,
    title: str,
    load: Load,
    *,
    volts: float = 5.0,
    delays: Delays = NOMINAL,
    offsets: Offsets | None = None,
    clamps: tuple[str, str] | None = None,
    more: Mapping[str, PartModel] | None = None,
    start: int = 0,
    end: float = 8e-6,
    max_step: float = 2e-9,
    blanking: float = 2e-6,
    trip_time: float = 12e-6,
    down: str = "0",
    high: Sequence[str] = (),
    supply: str | None = None,
    save: str = "",
) -> str:
    """The deck of a load step on the closed loop, from a range at rest.

    Args:
        ctx: The bench context.
        title: First line of the deck.
        load: The device under test and its step.
        volts: Voltage of the source.
        delays: Delays between the shunt and the gate.
        offsets: Offsets of the comparators.
        clamps: Model names for the two transistors of the ladder clamp.
        more: Further models that replace the ones of the model map.
        start: Range in which the run starts.
        end: End of the run, s.
        max_step: Largest time step, s.
        blanking: Blanking time of the sequencer, s.
        trip_time: Qualification time of the over-current trip, s.
        down: Waveform of the step-down request of firmware.
        supply: Lines of what feeds the supply node, in place of the source
            that holds ``volts`` behind ``SOURCE_OHMS``.
        high: Comparator outputs that are high in the state at rest.
        save: Further vectors to keep beside ``SAVED``.
    """
    circuit = front_end(ctx, delays, offsets, clamps=clamps, more=more)
    return ctx.deck(
        title,
        circuit,
        frontend.rails(),
        source(volts) if supply is None else supply,
        controller(delays, blanking=blanking, trip_time=trip_time, down=down),
        load.text(),
        rest(circuit, start, high),
        control=[f"save {SAVED} {save}".rstrip(), f"tran {max_step:g} {end:g}"],
        options=options(ctx),
        libraries=frontend.SEQUENCER_LIBRARIES,
    )


SAVED = (
    "supply vout_s vout dut inp inn amp_raw cmp_in th_up th_oc th_jump cmp_up cmp_oc cmp_jump "
    "gate_r1 gate_r2 gate_r3 gate_out mux_a0 mux_a1 g_r1 g_r2 g_r3 g_out sense_r1 sense_r2 "
    "sense_r3 iprog @r101[i] @r104[i] @r107[i] @r110[i] @r108[i] @mq10[id] @mq11[id]"
)
"""What a transient run of the front end keeps: the nodes and currents the benches read."""


def range_index(result: RunResult) -> Real:
    """The range that the multiplexer address selects, along a transient run."""
    low = result.real("mux_a0") > HALF_LOGIC
    high = result.real("mux_a1") > HALF_LOGIC
    return np.asarray(low.astype(np.float64) + 2.0 * high.astype(np.float64), dtype=np.float64)


SETTLED_ADDRESS = 30e-9
"""Time an address has to stand to count as a range, s.

The two address lines of a change cross the logic level a few nanoseconds
apart, so the address passes through a third value on the way. The
multiplexer needs 50 ns or more to act on an address.
"""


def range_changes(result: RunResult) -> tuple[Real, Real]:
    """The instants at which the selected range changes, and the range after each.

    An address that stands for less than ``SETTLED_ADDRESS`` is the passage
    from one range to another and is left out.
    """
    time = result.real("time")
    index = range_index(result)
    moved = np.flatnonzero(np.diff(index) != 0.0) + 1
    starts = np.concatenate(([0], moved))
    ends = np.concatenate((moved, [time.size - 1]))
    instants: list[float] = []
    ranges: list[float] = []
    current = float(index[0])
    for start, end in zip(starts[1:], ends[1:], strict=True):
        lasting = end == time.size - 1 or time[end] - time[start] >= SETTLED_ADDRESS
        if lasting and index[start] != current:
            current = float(index[start])
            instants.append(float(time[start]))
            ranges.append(current)
    return np.asarray(instants, dtype=np.float64), np.asarray(ranges, dtype=np.float64)


def settled_range(result: RunResult) -> Real:
    """The selected range along a run, without the passages between two addresses."""
    time = result.real("time")
    instants, ranges = range_changes(result)
    values = np.concatenate(([float(range_index(result)[0])], ranges))
    return np.asarray(values[np.searchsorted(instants, time, side="right")], dtype=np.float64)


def high_in_range(result: RunResult, signal: str, index: int, start: float) -> float:
    """The longest uninterrupted time a logic signal is high while a range is selected."""
    time = result.real("time")
    both = np.where(settled_range(result) == float(index), result.real(signal), 0.0)
    return high_time(time, np.asarray(both, dtype=np.float64), start, float(time[-1]))


def branch_r3(result: RunResult) -> Real:
    """The current that the 0.1 ohm branch takes from the supply node.

    The charging current of the gate of the range 3 switch flows through
    its source and through the same shunt, about 0.6 A for 30 ns at every
    edge of the gate. It is taken out here with the current of the gate
    resistor, so that a level on this waveform means a conducting channel.
    """
    return result.real("@r110[i]") - result.real("@r108[i]")


def ladder(result: RunResult) -> Real:
    """The ladder voltage: supply node minus the node after the shunts."""
    return result.real("supply") - result.real("vout_s")


def drop(result: RunResult) -> Real:
    """What the instrument adds: supply node minus the output terminal (R-07)."""
    return result.real("supply") - result.real("vout")


def high_time(time: Real, signal: Real, start: float, stop: float) -> float:
    """The longest uninterrupted time a logic signal is high inside a window."""
    xs, ys = measure.window(time, signal, start, stop)
    rises = measure.crossings(xs, ys, HALF_LOGIC, rising=True)
    falls = measure.crossings(xs, ys, HALF_LOGIC, rising=False)
    if ys[0] > HALF_LOGIC:
        rises = np.concatenate(([xs[0]], rises))
    if ys[-1] > HALF_LOGIC:
        falls = np.concatenate((falls, [xs[-1]]))
    if rises.size == 0:
        return 0.0
    return float(np.max(falls[: rises.size] - rises[: falls.size]))


def time_above(time: Real, signal: Real, level: float, start: float, stop: float) -> float:
    """The total time a waveform spends above a level inside a window."""
    xs, ys = measure.window(time, signal, start, stop)
    fine = np.linspace(xs[0], xs[-1], 20001)
    above = np.interp(fine, xs, ys) > level
    return float(np.count_nonzero(above) * (fine[1] - fine[0]))
