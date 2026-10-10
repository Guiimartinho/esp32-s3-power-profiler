"""What the benches of the path switches share.

The circuit of every bench is the path switching sheet from the netlist:
the two mode pairs with their gate networks, the interlock, the
over-voltage detector, the fuse and the suppressor of the VIN terminal, and
the capacitors of the supply node. Where a bench needs what stands behind
that node, the shunt ladder and the output pair come from the netlist as
well. This module names those parts, gives the nets short node names and
writes the lines that stand for what the schematic does not hold.

What is assumed here, and said in the notes of every bench that uses it:

- The source meter is a voltage source behind a small resistance on the
  node of the regulator output. The regulator and its loop belong to
  another block.
- The external supply of the ampere mode is a voltage source behind the
  resistance and the inductance of its leads.
- A line of the controller is a source of 3.3 V behind the output
  resistance of a pin. No program of the controller exists.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from benches import frontend
from circuit_sim.bench import VENDOR_TIER, Context
from circuit_sim.circuit import Circuit, PartModel
from circuit_sim.engine import RunResult
from circuit_sim.netlist import Netlist

Real = NDArray[np.float64]

SHEET = "/Path Switching/"

ALIASES = {
    **frontend.ALIASES,
    "/Path Switching/LDO_OUT": "ldo_out",
    "/Monitors/VIN_P": "vin_p",
    "/Output Stage/VIN_RAW": "vin_raw",
    "/Controller/GATE_SRC": "gate_src",
    "/Controller/GATE_AMP": "gate_amp",
    "/Controller/VIN_OV": "vin_ov",
    "Net-(Q2-D)": "amp_in",
    "Net-(U20-IN_A)": "src_in",
    "Net-(U20-OUT_A)": "drv_src",
    "Net-(U20-OUT_B)": "drv_amp",
    "Net-(D16-A)": "g_src",
    "Net-(D17-A)": "g_amp",
    "Net-(D18-A)": "s_src",
    "Net-(D19-A)": "s_amp",
    "Net-(D18-K)": "b_src",
    "Net-(D19-K)": "b_amp",
    "Net-(D16-common)": "off_src",
    "Net-(D17-common)": "off_amp",
    "Net-(C60-Pad2)": "ramp_src",
    "Net-(C61-Pad2)": "ramp_amp",
    "Net-(D15-common)": "det",
    "Net-(C63-Pad1)": "damper",
    "Net-(U40-CH1)": "vin_mon",
    "Net-(D21-K)": "vout",
    "Net-(D20-common)": "out_gate",
    "Net-(D20-K)": "out_off",
    "Net-(Q15-G)": "g_out",
    "Net-(Q15-S-Pad1)": "s_out",
}
"""Short node names.

``vin_raw`` is the VIN terminal and ``vin_p`` the same line behind the fuse
(test point TP27). ``g_src`` and ``g_amp`` are the gates of the two mode
pairs (TP31, TP32), ``s_src`` and ``s_amp`` their common sources, ``b_src``
and ``b_amp`` the bases of the hold-off transistors. ``amp_in`` is the input
of the ampere driver, the node of the interlock. ``det`` is the input of the
over-voltage detector and ``vin_ov`` its output (TP30). ``supply`` is the
supply node of the ladder (TP33) and ``damper`` the node between R87 and
C63. ``vout`` is the output terminal behind the output pair.
"""

VIN_MONITOR = ("R141", "R150", "C104")
"""The divider of the VIN monitor (drawn on the monitor sheet): it loads the terminal."""

OUTPUT_PAIR = ("Q15", "Q16", "R115", "R116", "R117", "R120", "C74", "D20")
"""The output pair with its gate network (drawn on the output sheet)."""

OUTPUT_SUPPRESSOR = ("D21",)
"""The suppressor of the output terminal (drawn on the output sheet)."""

REGULATOR_OUTPUT = ("C53", "C54", "R69")
"""What stands on the output of the regulator (drawn on the source meter sheet):
its output capacitors and its minimum load to -4 V_A."""

LOGIC_VOLTS = frontend.LOGIC_VOLTS

PAD_OHMS = 33.0
"""Output resistance of a pin of the controller, as the sequencer model has it."""

EDGE = 10e-9
"""Rise and fall time of a line of the controller."""

REGULATOR_OHMS = 0.02
"""Resistance of the stand-in for the source meter (assumption)."""

LEAD_OHMS_PER_HENRY = 40e3
"""Resistance of supply leads by their inductance: 40 mohm per uH (assumption).

A pair of leads of 1 m has about 1 uH and, with 1 mm2 of copper, about
35 mohm; the contacts are counted with the rest.
"""

RAIL_VOLTS = 12.0
"""Nominal +12 V_A, the supply of the gate drivers and of the multiplexer."""

NODE_LIMIT = 11.5
"""Highest voltage of the supply node at a trip (specification, section 4.3)."""

TRANSISTOR_VOLTS = 30.0
"""Drain-source rating of the CSD17577Q3A (TI SLPS515A, page 1)."""

GATE_VOLTS = 20.0
"""Gate-source rating of the CSD17577Q3A (TI SLPS515A, page 1)."""

CAPACITOR_VOLTS = 25.0
"""Rated voltage of C62 and C63 (value fields of the schematic)."""

HOLD_OFF_VOLTS = 45.0
"""Collector-emitter rating of the BC847B (Diodes DS11108, page 2)."""

HOLD_OFF_BASE_VOLTS = 6.0
"""Emitter-base rating of the BC847B (Diodes DS11108, page 2)."""

DIODE_PULSE_AMPS = 4.0
"""Peak forward current of a BAV199 for 1 us (Nexperia BAV199 of 2023, page 2)."""

DIODE_REPEAT_AMPS = 0.5
"""Repetitive peak forward current of a BAV199 (Nexperia BAV199 of 2023, page 2)."""

FUSE_MELT = 1.764
"""Nominal melting I2t of the fuse, A2s (Littelfuse 466 series, page 1)."""

SUPPRESSOR_PULSE_AMPS = 12.3
"""Peak pulse current of the SMAJ20CA for the 10/1000 us wave (Vishay 88390, page 2)."""

SUPPRESSOR_PULSE_WATTS = 400.0
"""Peak pulse power of the SMAJ20CA for the 10/1000 us wave (Vishay 88390, page 1)."""

SUPPRESSOR_SLOPE = -0.47
"""Slope of figure 1 of the suppressor datasheet: power against pulse width, both
on logarithmic axes (30 kW at 0.1 us, 0.4 kW at 1000 us, read from the curve)."""


def suppressor_rating(seconds: float) -> float:
    """The peak pulse power the suppressor is rated for at a pulse width.

    Figure 1 of the datasheet (Vishay 88390, page 4) as a straight line on
    logarithmic axes through its 400 W at 1000 us. The figure ends at
    0.1 us; shorter pulses take the value of that end.
    """
    width = max(seconds, 1e-7)
    return float(SUPPRESSOR_PULSE_WATTS * (width / 1e-3) ** SUPPRESSOR_SLOPE)


def sheet_refs(netlist: Netlist) -> tuple[str, ...]:
    """The parts drawn on the path switching sheet."""
    return netlist.on_sheet(SHEET)


def refs(
    netlist: Netlist,
    *,
    ladder: bool = True,
    output: bool = False,
    extra: Iterable[str] = (),
    leave_out: Iterable[str] = (),
) -> tuple[str, ...]:
    """The parts of a bench circuit.

    Args:
        netlist: The schematic.
        ladder: Take the sheet of the shunt ladder as well. Without it only
            the bleed resistor R90, the 1 kohm shunt R101 and the capacitor
            C71 behind it stand on the supply node.
        output: Take the output pair with its gate network and the
            suppressor of the output terminal as well.
        extra: Further designators, of any sheet.
        leave_out: Designators to leave out.
    """
    chosen: list[str] = [*sheet_refs(netlist), *VIN_MONITOR, *extra]
    chosen += frontend.ladder_refs(netlist) if ladder else ["R90", "R101", "C71"]
    if output:
        chosen += [*OUTPUT_PAIR, *OUTPUT_SUPPRESSOR]
    dropped = set(leave_out)
    return tuple(ref for ref in dict.fromkeys(chosen) if ref not in dropped)


def circuit(
    ctx: Context,
    *,
    ladder: bool = True,
    output: bool = False,
    extra: Iterable[str] = (),
    leave_out: Iterable[str] = (),
    overrides: Mapping[str, PartModel] | None = None,
    scales: Mapping[str, float] | None = None,
    detector: bool = False,
) -> Circuit:
    """The circuit of a bench, with the node names of :data:`ALIASES`.

    Args:
        ctx: The context of the bench.
        ladder: See :func:`refs`.
        output: See :func:`refs`.
        extra: See :func:`refs`.
        leave_out: See :func:`refs`.
        overrides: Models that replace the model map for single parts.
        scales: Factors on the values of single passive parts.
        detector: The bench is about the over-voltage detector. Only then
            does a run with the models of the manufacturers take their
            comparator: its operating point does not converge inside the
            larger circuits, and the other benches ask nothing of it.
    """
    chosen = refs(ctx.netlist, ladder=ladder, output=output, extra=extra, leave_out=leave_out)
    models = dict(overrides or {})
    if ctx.tier == VENDOR_TIER and not detector and "U21" in chosen:
        models.setdefault("U21", comparator())
    return ctx.circuit(chosen, ALIASES, models, scales)


def rails(p12: float = RAIL_VOLTS, p3v3: float = 3.3, vref: float = 2.5) -> str:
    """Ideal analog rails and an ideal reference."""
    return frontend.rails(p12=p12, p3v3=p3v3, vref=vref)


def range_lines(index: int = 3, output: bool | None = False) -> str:
    """The lines of the controller toward the ladder, held for one range.

    Args:
        index: The range; firmware selects range 3 before a mode pair closes
            (rule F-20).
        output: The level of the line of the output pair, or None to leave
            that line to the bench.
    """
    lines = frontend.fixed_range(index, output_on=bool(output)).splitlines()
    if output is None:
        lines = [line for line in lines if not line.startswith("Vgate_out ")]
    return "\n".join(lines) + "\n"


def pwl(points: Sequence[tuple[float, float]], edge: float = EDGE) -> str:
    """The argument of a piecewise linear source that steps between levels.

    Args:
        points: Instants with the level from then on; the first gives the
            level from the start, whatever its instant.
        edge: Time a step takes.
    """
    level = points[0][1]
    steps = [f"0 {level:g}"]
    for instant, target in points[1:]:
        steps.append(f"{instant:.9g} {level:g}")
        level = target
        steps.append(f"{instant + edge:.9g} {level:g}")
    return f"PWL({' '.join(steps)})"


def pin(name: str, node: str, *points: tuple[float, bool], edge: float = EDGE) -> str:
    """A line of the controller: a pin behind its output resistance.

    Args:
        name: Name of the source; it also names the node in front of the
            resistance.
        node: The node of the line.
        *points: Instants at which the line changes, each with its new
            level; the first point gives the level from the start.
        edge: Rise and fall time of the pin.
    """
    levels = [(instant, LOGIC_VOLTS if high else 0.0) for instant, high in points]
    return f"V{name} pin_{name} 0 {pwl(levels, edge)}\nRpad_{name} pin_{name} {node} {PAD_OHMS:g}\n"


def requests(
    source: Sequence[tuple[float, bool]] = ((0.0, False),),
    ampere: Sequence[tuple[float, bool]] = ((0.0, False),),
) -> str:
    """The two mode requests GATE_SRC and GATE_AMP as pins of the controller."""
    return (
        "* mode requests: pins of the controller behind their output resistance\n"
        + pin("src", "gate_src", *source)
        + pin("amp", "gate_amp", *ampere)
    )


def regulator(volts: float | str = 5.0, ohms: float = REGULATOR_OHMS) -> str:
    """The source meter as a source on the output node of the regulator.

    Args:
        volts: The voltage, or the argument of a source (``PWL(...)``).
        ohms: Resistance between the source and the node.
    """
    value = f"{volts:g}" if isinstance(volts, float | int) else volts
    return (
        "* stand-in for the source meter: a source behind a small resistance\n"
        f"Vldo ldo_src 0 {value}\n"
        f"Rldo ldo_src ldo_out {ohms:g}\n"
    )


def lead_ohms(henries: float) -> float:
    """The resistance that goes with supply leads of an inductance (assumption)."""
    return LEAD_OHMS_PER_HENRY * henries


def supply(volts: float | str = 5.0, henries: float = 0.0, ohms: float | None = None) -> str:
    """The external supply on the VIN terminal, behind its leads.

    A source of 0 V in the leads gives their current as ``vlead#branch``,
    positive into the instrument.

    Args:
        volts: The voltage, or the argument of a source (``PWL(...)``).
        henries: Inductance of the leads; none when zero.
        ohms: Resistance of the leads; :func:`lead_ohms` of the inductance
            when left out, and 20 mohm without inductance.
    """
    value = f"{volts:g}" if isinstance(volts, float | int) else volts
    if ohms is None:
        ohms = lead_ohms(henries) if henries > 0.0 else 0.02
    lines = [
        "* external supply on the VIN terminal, behind its leads",
        f"Vin vin_src 0 {value}",
        "Vlead vin_src vin_a 0",
    ]
    if henries > 0.0:
        lines += [f"Rlead vin_a vin_b {ohms:g}", f"Llead vin_b vin_raw {henries:g}"]
    else:
        lines.append(f"Rlead vin_a vin_raw {ohms:g}")
    return "\n".join(lines) + "\n"


def no_supply() -> str:
    """The VIN terminal left open: only a resistor that keeps the node defined."""
    return "* VIN terminal open\nRopen vin_raw 0 1e12\n"


def no_regulator() -> str:
    """The regulator output without a source: the minimum load pulls it to 0 V."""
    return (
        "* regulator output at rest: its minimum load and capacitor hold it at 0 V\n"
        "Rldo ldo_out 0 1\n"
    )


def transistor(variant: str) -> PartModel:
    """A CSD17577Q3A with its threshold at a limit of the datasheet: ``LO`` or ``HI``."""
    return PartModel(
        kind="device",
        letter="M",
        name=f"PATH_CSD17577_{variant}",
        ports=("5", "4", "1"),
        library="path_switching.lib",
        origin="written here",
    )


def diode_pair(variant: str) -> PartModel:
    """A BAV199 pair with its forward voltage at a limit: ``HI`` or ``LO``."""
    return PartModel(
        kind="device",
        letter="D",
        name=f"BAV199_{variant}",
        units=(("1", "3"), ("3", "2")),
        library="diodes.lib",
        origin="written here",
    )


def hold_off(variant: str) -> PartModel:
    """A BC847B with its gain at a limit of the datasheet: ``LO`` or ``HI``."""
    return PartModel(
        kind="device",
        letter="Q",
        name=f"PATH_BC847B_{variant}",
        ports=("3", "1", "2"),
        library="path_switching.lib",
        origin="written here",
    )


def interlock(variant: str) -> PartModel:
    """A BSS138 with its threshold at a limit of the datasheet: ``LO`` or ``HI``."""
    return PartModel(
        kind="device",
        letter="M",
        name=f"PATH_BSS138_{variant}",
        ports=("3", "1", "2"),
        library="path_switching.lib",
        origin="written here",
    )


def suppressor(variant: str) -> PartModel:
    """The suppressor D14 with its breakdown voltage at a limit: ``LO`` or ``HI``."""
    return PartModel(
        kind="subckt",
        name=f"PATH_SMAJ20CA_{variant}",
        ports=("1", "2"),
        library="path_switching.lib",
        origin="written here",
    )


def driver(delay: float = 30e-9, ohms: float = 7.0) -> PartModel:
    """The gate driver U20 with another delay or output resistance."""
    return PartModel(
        kind="subckt",
        name="TC4427CH",
        units=(("2", "7", "6", "3"), ("4", "5", "6", "3")),
        library="logic.lib",
        origin="written here",
        params=f"td={delay:g} ro={ohms:g}",
    )


def comparator(offset: float = 0.0, hysteresis: float = 3e-3, delay: float = 47e-9) -> PartModel:
    """The comparator U21 of the detector with another offset, hysteresis or delay."""
    return PartModel(
        kind="subckt",
        name="MCP656X",
        ports=("3", "4", "1", "5", "2"),
        library="logic.lib",
        origin="written here",
        params=f"vos={offset:g} vhy={hysteresis:g} td={delay:g}",
    )


def joules(time: Real, watts: Real, start: float, stop: float) -> float:
    """The integral of a waveform between two instants: the energy of a power.

    The samples inside the window are joined by straight lines. The windows
    of the benches start and end where the waveform is flat, so their ends
    are not interpolated.
    """
    inside = (time >= start) & (time <= stop)
    x, y = time[inside], watts[inside]
    return float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(x)))


VENDOR_OPTIONS = ("method=gear", "reltol=2e-3", "abstol=1e-9", "vntol=1e-5")
"""Solver settings for the runs with the models of the manufacturers.

The subcircuit that the manufacturer publishes for the CSD17577Q3A stops
the transients of this block with a time step too small under the default
settings. These are the settings the earlier simulations used with it.
"""


def deck(
    ctx: Context,
    title: str,
    *parts: Circuit | str,
    control: Sequence[str],
    options: Sequence[str] = (),
) -> str:
    """A deck of this block: the deck of the context with the settings of its tier."""
    extra = VENDOR_OPTIONS if ctx.tier == VENDOR_TIER else ()
    return ctx.deck(title, *parts, control=control, options=(*options, *extra))


def through(ctx: Context, run: RunResult, pair: str) -> Real:
    """The current that enters a mode pair from its feeding side.

    With the models written here it is the drain current of the transistor
    on that side. The subcircuit of the manufacturer offers no such vector:
    there the current of the supply leads less what the suppressor takes, or
    the current of the regulator stand-in, stands for it, which also counts
    the current that charges the capacitances of the transistor.

    Args:
        ctx: The context of the bench.
        run: A run that saved the vectors named above.
        pair: ``ampere`` or ``source``.
    """
    if ctx.tier != VENDOR_TIER:
        return run.real("@mq5[id]" if pair == "ampere" else "@mq4[id]")
    if pair == "ampere":
        return run.real("vlead#branch") - run.real("@d.xd14.d1[id]")
    return -run.real("vldo#branch")
