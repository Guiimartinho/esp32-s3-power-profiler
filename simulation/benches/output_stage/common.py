"""What the benches of the output stage share.

The circuit of every bench is the sheet of the output stage with the shunt
ladder in front of it, both from the netlist. This module names their parts,
gives the nets short node names and writes the lines that stand for what
the two sheets do not hold: the source meter with its closed mode pair, the
controller, the cable and the device under test.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from benches import frontend
from circuit_sim import measure
from circuit_sim.bench import VENDOR_TIER, Context
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult
from circuit_sim.netlist import Netlist

Real = NDArray[np.float64]
Complex = NDArray[np.complex128]

SHEET = "/Output Stage/"

ALIASES = {
    **frontend.ALIASES,
    "Net-(D21-K)": "vout",
    "Net-(D20-common)": "out_gate",
    "Net-(D20-K)": "gate_off",
    "Net-(Q15-G)": "g_out",
    "Net-(Q15-S-Pad1)": "mid",
    "Net-(U25-+)": "buf_in",
    "Net-(U25--)": "buf_out",
    "/Monitors/VOUT_BUF": "guard",
    "/Digital Inputs/VCCB_SRC": "vccb_src",
    "Net-(JP2-C)": "vccb",
    "Net-(U40-CH0)": "mon_ch0",
    "Net-(C63-Pad1)": "damper",
}
"""Short node names: ``vout`` is the output terminal, ``vout_s`` the node after
the shunts, ``mid`` the common source of the pair, ``out_gate`` the gate node
behind R117 (test point TP37) and ``guard`` the output of the buffer behind
R119."""

SOURCE_OHMS = 0.010
"""Output impedance of the stand-in for the source meter: two closed
transistors of the mode pair, about 4.5 mohm each, and their copper
(assumption)."""

PAD_OHMS = 33.0
"""Output resistance of a pin of the controller, as the sequencer model has it."""

LOGIC_VOLTS = frontend.LOGIC_VOLTS

CABLE_OHMS = 0.050
"""Resistance of the cable to the device under test and back (assumption:
two leads of half a meter and 0.5 mm2, with their contacts)."""

ESR_OHMS = 0.020
"""Series resistance of the capacitor of the device under test (assumption)."""

TRIP_AMPS = 1.15
"""Over-current level in range 3 (specification, section 4.4)."""

TRIP_AMPS_LOW = 1.114
"""Lowest over-current level with the tolerances (specification, section 4.4)."""

TRANSISTOR_VOLTS = 30.0
"""Drain-source rating of the CSD17577Q3A (TI SLPS515A, page 1)."""

GATE_VOLTS = 20.0
"""Gate-source rating of the CSD17577Q3A (TI SLPS515A, page 1)."""

AVALANCHE_JOULES = 39e-3
"""Single-pulse avalanche energy of the CSD17577Q3A (TI SLPS515A, page 1)."""

SURGE_AMPS = 50.0
"""Forward surge rating of the suppressor D21 (Nexperia PTVSxS1UR, page 3)."""

POWER_UP = 200e-6
"""Time in which the sources rise in a run that starts with everything at zero."""

COMPARATOR_DELAY = 0.2e-6
"""Delay of the stand-in for the amplifier chain and a comparator
(assumption: section 4.4 gives 0.35 us from the threshold to a conducting
branch with a sequencer of 100 ns and a gate driver of 30 ns)."""

THRESHOLDS = {"up": 0.09095, "oc": 0.115, "jump": 0.151}
"""Shunt voltage at which each comparator acts (specification, section 4.4)."""

BUFFER = "U25"
"""The guard buffer."""

_BUFFER_PINS = ("3", "4", "5", "2", "1")
"""Pins of the buffer in the order of its models: both inputs, both supplies, output."""

VENDOR_BUFFER_LIBRARY = "vendor/ti-opa197-OPAx197.LIB"
"""The model file of the manufacturer of the buffer, for the vendor tier."""


def stage_refs(netlist: Netlist) -> tuple[str, ...]:
    """The parts drawn on the sheet of the output stage."""
    return netlist.on_sheet(SHEET)


def path_refs(netlist: Netlist) -> tuple[str, ...]:
    """The shunt ladder with its two nodes and the output stage behind it."""
    return (*frontend.ladder_refs(netlist), *stage_refs(netlist))


def transistor(variant: str) -> PartModel:
    """A CSD17577Q3A at a limit of its datasheet: ``LO``, ``HI`` or ``RMAX``."""
    return PartModel(
        kind="device",
        letter="M",
        name=f"OUTPUT_CSD17577_{variant}",
        ports=("5", "4", "1"),
        library="output_stage.lib",
        origin="written here",
    )


def suppressor(forward_ohms: float = 0.03, breakdown: float = 17.6) -> PartModel:
    """The suppressor D21 with another forward resistance or breakdown voltage."""
    return PartModel(
        kind="subckt",
        name="OUTPUT_PTVS15V",
        ports=("2", "1"),
        library="output_stage.lib",
        origin="written here",
        params=f"rsf={forward_ohms:g} vbr={breakdown:g}",
    )


def _risen(volts: float, ramp: float) -> str:
    """The value of a source: steady, or risen from zero within the ramp time."""
    if ramp <= 0.0 or volts == 0.0:
        return f"{volts:g}"
    return f"PWL(0 0 {ramp:g} {volts:g})"


def rails(p12: float = 12.0, m4: float = -4.0, ramp: float = 0.0) -> str:
    """Ideal analog rails; with ``ramp`` they rise from zero in that time."""
    if ramp <= 0.0:
        return frontend.rails(p12=p12, m4=m4, vref=None)
    return (
        "* ideal rails, risen from zero\n"
        f"Vp12 p12v_a 0 {_risen(p12, ramp)}\n"
        f"Vm4 m4v_a 0 {_risen(m4, ramp)}\n"
        f"Vp3v3a p3v3_a 0 {_risen(LOGIC_VOLTS, ramp)}\n"
    )


def controller(range_index: int = 3, ramp: float = 0.0) -> str:
    """The lines of the controller held for one range, without the output line.

    The line of the output switch is left to the bench, which drives it with
    :func:`command` or with the model of the sequencer. With ``ramp`` the
    lines rise from zero in that time.
    """
    lines = []
    for line in frontend.fixed_range(range_index).splitlines():
        if line.startswith("Vgate_out "):
            continue
        words = line.split()
        if ramp > 0.0 and line.startswith("V") and len(words) == 4:
            line = " ".join((*words[:3], _risen(float(words[3]), ramp)))
        lines.append(line)
    return "\n".join(lines) + "\n"


def command(*points: tuple[float, bool], edge: float = 20e-9) -> str:
    """The line GATE_OUT as a pin of the controller drives it.

    Args:
        *points: Instants at which the line changes, each with its new
            level; the first point gives the level from the start.
        edge: Rise and fall time of the pin.
    """
    level = LOGIC_VOLTS if points[0][1] else 0.0
    steps = [f"0 {level:g}"]
    for instant, high in points[1:]:
        steps.append(f"{instant:.9g} {level:g}")
        level = LOGIC_VOLTS if high else 0.0
        steps.append(f"{instant + edge:.9g} {level:g}")
    return (
        "* GATE_OUT: a pin of the controller behind its output resistance\n"
        f"Vcmd cmd 0 PWL({' '.join(steps)})\n"
        f"Rpad cmd gate_out {PAD_OHMS:g}\n"
    )


def source(volts: float, ohms: float = SOURCE_OHMS, henries: float = 0.0, ramp: float = 0.0) -> str:
    """The source meter with its closed mode pair, as a source on the supply node.

    The source meter and the mode pairs belong to other blocks. Here an
    ideal source behind a small resistance stands for them and, when
    ``henries`` is given, behind the inductance of supply leads, which is the
    ampere mode on a stiff external supply. With ``ramp`` the source rises
    from zero in that time.
    """
    lines = [
        "* stand-in for the source meter and the closed mode pair",
        f"Vsrc src 0 {_risen(volts, ramp)}",
    ]
    if henries > 0.0:
        lines += [f"Rsrc src srcl {ohms:g}", f"Lsrc srcl supply {henries:g}"]
    else:
        lines.append(f"Rsrc src supply {ohms:g}")
    return "\n".join(lines) + "\n"


def cable(ohms: float = CABLE_OHMS, henries: float = 0.0) -> str:
    """The cable from the output terminal to the node ``dut``.

    A source of 0 V in the cable gives its current as ``vcab#branch``,
    positive toward the device under test.
    """
    lines = ["* cable to the device under test", "Vcab vout cab 0"]
    if henries > 0.0:
        lines += [f"Rcab cab cabl {ohms:g}", f"Lcab cabl dut {henries:g}"]
    else:
        lines.append(f"Rcab cab dut {ohms:g}")
    return "\n".join(lines) + "\n"


def capacitor_load(farads: float, ohms: float = 1e6, esr: float = ESR_OHMS) -> str:
    """A device under test that is a capacitor with a resistor beside it."""
    return (
        "* device under test: a capacitor with its series resistance and a resistor\n"
        f"Cdut dut dutc {farads:g}\n"
        f"Resr dutc 0 {esr:g}\n"
        f"Rdut dut 0 {ohms:g}\n"
    )


def suppressor_current(ctx: Context, result: RunResult) -> Real:
    """The current in D21 from ground to the terminal: forward is positive.

    The vectors that hold it differ between the model written here and the
    model of the manufacturer; :func:`suppressor_saves` names them.
    """
    if ctx.tier == VENDOR_TIER:
        # The subcircuit of the manufacturer has its anode first, so the
        # currents of its diode and of its resistor count forward as they are.
        return result.real("@d.xd21.d1[id]") + result.real("@r.xd21.r1[i]")
    return result.real("@r.xd21.rf[i]") - result.real("v.xd21.vz#branch")


def suppressor_saves(ctx: Context) -> str:
    """The device currents a deck has to save for :func:`suppressor_current`."""
    if ctx.tier == VENDOR_TIER:
        return "@d.xd21.d1[id] @r.xd21.r1[i]"
    return "@r.xd21.rf[i] v.xd21.vz#branch"


def slope(time: Real, values: Real) -> Real:
    """The time derivative of a waveform, at its samples."""
    return np.asarray(np.gradient(values, time), dtype=np.float64)


def energy(time: Real, power: Real, start: float, stop: float) -> float:
    """The energy of a power waveform between two instants."""
    return measure.integral(time, power, start, stop)


def buffer_model(ctx: Context) -> dict[str, PartModel]:
    """The model of the buffer that the vendor tier takes, as an override.

    The shared model map names no model of the manufacturer for the
    OPA197, so the benches of this block name it here. In the open tier
    the result is empty and the model map decides.
    """
    if ctx.tier != VENDOR_TIER:
        return {}
    return {
        BUFFER: PartModel(
            kind="subckt",
            name="OPAx197",
            ports=_BUFFER_PINS,
            library=VENDOR_BUFFER_LIBRARY,
            origin="vendor",
        )
    }


def buffer_probe(
    ctx: Context, vac: float = 0.0, iac: float = 0.0, vfb: float = 0.0
) -> dict[str, PartModel]:
    """The buffer with the sources that measure its loop, as an override.

    Args:
        ctx: The context of the bench; its tier decides the amplifier model.
        vac: Amplitude of the voltage in series with the amplifier output.
        iac: Amplitude of the current into the output pin.
        vfb: Amplitude of the voltage in series with the inverting input.
    """
    vendor = ctx.tier == VENDOR_TIER
    return {
        BUFFER: PartModel(
            kind="subckt",
            name="OUTPUT_OPAX197_PROBE" if vendor else "OUTPUT_OPA197_PROBE",
            ports=_BUFFER_PINS,
            library="output_stage.lib",
            origin="vendor" if vendor else "written here",
            params=f"vac={vac:g} iac={iac:g} vfb={vfb:g}",
        )
    }


def buffer_libraries(ctx: Context) -> tuple[str, ...]:
    """The model file that a deck with :func:`buffer_probe` has to include."""
    return (VENDOR_BUFFER_LIBRARY,) if ctx.tier == VENDOR_TIER else ("opamps.lib",)


def buffer_options(ctx: Context) -> tuple[str, ...]:
    """Solver options that a deck with the buffer needs in the vendor tier.

    The model of the manufacturer holds nodes without a path to ground for
    direct current, and its operating point does not converge in ngspice
    as it is. A resistance of 10 teraohm from every node to ground settles
    it. That is 1 pA at 12 V: nothing beside the figures of these benches,
    which quote no leakage.
    """
    return ("rshunt=1e13",) if ctx.tier == VENDOR_TIER else ()


def loop_gain(series: RunResult, shunt: RunResult, node: str = "buf_out") -> tuple[Real, Complex]:
    """The loop gain of the buffer from the two runs of a double injection.

    The amplifier output is the driving side of the injection point and the
    net of its output pin the receiving side. The voltage ratio is the
    returned voltage over the forward one, ``-v(amp)/v(out)``; the current
    ratio is ``-i(amp)/i(out)``, with the current that the amplifier
    delivers and the current that enters the net, which is the first plus
    the injected ampere. A loop of known gain gives that gain back with
    these two ratios.

    Args:
        series: The run with 1 V in series with the amplifier output.
        shunt: The run with 1 A into the output pin.
        node: Node of the net at the output pin of the buffer.

    Returns:
        The frequencies and the loop gain along them.
    """
    frequency = series.real("frequency")
    inner = f"x{BUFFER.lower()}.amp"
    voltage_ratio = -series.vector(inner) / series.vector(node)
    delivered = shunt.vector(f"v.x{BUFFER.lower()}.vser#branch")
    current_ratio = -delivered / (delivered + 1.0)
    return frequency, measure.loop_gain(
        np.asarray(voltage_ratio, dtype=np.complex128),
        np.asarray(current_ratio, dtype=np.complex128),
    )


def feedback_loop_gain(run: RunResult, node: str = "buf_out") -> tuple[Real, Complex]:
    """The loop gain of the buffer from one injection at its inverting input.

    The input takes no current that counts beside the impedance of the net,
    so the voltage ratio alone is the loop gain there: an independent check
    of :func:`loop_gain`.
    """
    inner = f"x{BUFFER.lower()}.fb"
    ratio = -run.vector(node) / run.vector(inner)
    return run.real("frequency"), np.asarray(ratio, dtype=np.complex128)


def path_models(ctx: Context) -> dict[str, PartModel]:
    """Overrides that every circuit of this block takes: the buffer and Q14.

    In the vendor tier the buffer takes the model of its manufacturer (see
    :func:`buffer_model`), and the range 3 switch Q14 keeps the model
    written here: with the model of the manufacturer in that place, switched
    on and without current, the operating point of these circuits does not
    converge. The transistors of the output pair, Q15 and Q16, take the
    model of the manufacturer through the shared model map.
    """
    if ctx.tier != VENDOR_TIER:
        return {}
    ladder_switch = PartModel(
        kind="device",
        letter="M",
        name="CSD17577Q3A",
        ports=("5", "4", "1"),
        library="mosfets.lib",
        origin="written here",
    )
    return {**buffer_model(ctx), "Q14": ladder_switch}


def protection(trip_time: float = 12e-6, start_range: int = 3) -> str:
    """The sequencer model with stand-ins for the comparators in front of it.

    The amplifier chain and the comparators belong to other blocks. Here
    three ideal thresholds on the voltage between the two outputs of the
    multiplexer, each with one delay, stand for them. The line ``force``
    stands for the firmware that selects range 3 before a path closes (rule
    F-20): it holds the jump input high for the first microseconds of a run,
    so that the run starts from a defined state. The bench drives
    ``seq_out_on``.

    A run that starts with every voltage at zero reaches range 3 by itself,
    because the charging currents pass the jump level. For a start in range 0
    three requests to step down follow, at 70 us, 80 us and 90 us; the bench
    places its event later.

    Args:
        trip_time: Qualification time of the over-current trip (rule F-18).
        start_range: 3 to start in range 3, 0 to start in range 0.
    """
    if start_range not in (0, 3):
        raise ValueError("a run starts in range 0 or in range 3")
    force = "PWL(0 1 2u 1 2.02u 0)"
    state = 1 if start_range == 3 else 0
    down = "0"
    if start_range == 0:
        edges = []
        for instant in (70e-6, 80e-6, 90e-6):
            edges += [
                f"{instant:.9g} 0",
                f"{instant + 1e-8:.9g} {LOGIC_VOLTS:g}",
                f"{instant + 1e-6:.9g} {LOGIC_VOLTS:g}",
                f"{instant + 1.01e-6:.9g} 0",
            ]
        down = f"PWL(0 0 {' '.join(edges)})"
    lines = [
        "* stand-in for the amplifier chain and the comparators: ideal thresholds",
        "* on the voltage between the outputs of the multiplexer, one delay each",
    ]
    for name, level in THRESHOLDS.items():
        lines += [
            f"Bc{name} c{name}0 0 V = 0.5*(1 + tanh((v(inp,inn) - {level:g})/0.5m))",
            f"Xc{name} c{name}0 c{name}1 DLY td={COMPARATOR_DELAY:g}",
        ]
    lines += [
        f"Eup seq_up 0 cup1 0 {LOGIC_VOLTS:g}",
        f"Eoc seq_oc 0 coc1 0 {LOGIC_VOLTS:g}",
        "* firmware selects range 3 before the path closes: the jump input is held",
        f"Vforce force 0 {force}",
        f"Bjump seq_jump 0 V = {LOGIC_VOLTS:g}*(1 - (1 - v(cjump1))*(1 - v(force)))",
        f"Vdown seq_down 0 {down}",
        f"Venable seq_enable 0 {LOGIC_VOLTS:g}",
        f".nodeset v(xseq.l1)={state} v(xseq.l2)={state} v(xseq.l3)={state} v(xseq.trip)=0",
    ]
    return "\n".join(lines) + "\n" + frontend.sequencer(comparators=False, trip_time=trip_time)


QUICK_POWER_UP = 20e-6
"""Rise time of the sources in a run that starts with the output switch closed."""

GATE_READY = 60e-6
"""Instant at which the helper that charges the gate node lets go of it."""

EVENT_AT = 120e-6
"""Earliest instant of an event in a run that starts with the output switch closed."""


def closed_start(p12: float = 12.0) -> str:
    """Lines that bring the gate of the output pair to its rest value at once.

    A run starts with every voltage at zero and its sources rising, which
    the models of the manufacturers need: their operating point is not
    found reliably. Through R117 alone the gate node would then need a
    quarter of a second. A switch ties it to a source at the level of
    +12 V_A while the circuit comes up and opens at :data:`GATE_READY`;
    from there on the gate rests on R117 and C74 as drawn. The bench keeps
    GATE_OUT high from the start and places its event at
    :data:`EVENT_AT` or later.
    """
    return (
        "* the gate node is brought to its rest value by a helper that opens before the\n"
        "* event; through R117 alone the gate needs a quarter of a second\n"
        f"Vpre pre 0 PWL(0 0 {QUICK_POWER_UP:g} {p12:g})\n"
        f"Vprectl prectl 0 PWL(0 1 {GATE_READY:g} 1 {GATE_READY + 1e-7:g} 0)\n"
        "Spre out_gate pre prectl 0 OUTPUT_PRECHARGE\n"
        ".model OUTPUT_PRECHARGE SW(vt=0.5 vh=0.1 ron=100 roff=1e12)\n"
    )


def pair_current(ctx: Context, result: RunResult) -> Real:
    """The current through the output pair toward the terminal.

    It is the current of the cable less what the suppressor adds to it from
    ground; the capacitance of the terminal is left out.
    """
    return result.real("vcab#branch") - suppressor_current(ctx, result)


REGULATOR_REFS = ("C53", "C54")
"""The output capacitors of the linear regulator (source meter sheet)."""

REGULATOR_ALIASES = {"/Path Switching/LDO_OUT": "ldo"}
"""Node name of the regulator output."""

REGULATOR_AMPS = 1.4
"""Current limit of the stand-in for the linear regulator (assumption: the
datasheet of the LT3080 gives 1.1 A at least and about 1.4 A typical)."""

C53_AT_5V = 13.6e-6 / 22e-6
"""What is left of C53 at 5 V of bias (specification, section 4.2: 13.6 uF)."""


def regulator(volts: float, ramp: float = 0.0) -> str:
    """Stand-in for the source mode: a regulator that limits and cannot sink.

    A current source drives the regulator output toward its set voltage,
    limits at :data:`REGULATOR_AMPS` and delivers nothing while the output
    is above the set voltage. The output capacitors come from the
    schematic (:data:`REGULATOR_REFS`); 10 mohm stand for the closed source
    pair. The regulator, its pre-regulator and the diodes D11 and D12 at
    its output belong to the source meter block and are not in this
    circuit.
    """
    return (
        "* stand-in for the source mode: a regulator that limits its current and cannot\n"
        "* sink, on the output capacitors of the schematic; 10 mohm for the source pair\n"
        f"Vset set 0 {_risen(volts, ramp)}\n"
        "Bpos pos 0 V = 5m*ln(1 + exp((v(set) - v(ldo))/5m))\n"
        f"Bldo 0 ldo I = {REGULATOR_AMPS:g}*tanh(v(pos)*{20.0 / REGULATOR_AMPS:g})\n"
        f"Rpair ldo supply {SOURCE_OHMS:g}\n"
    )
