"""The measuring front end as the benches use it.

The shunt ladder, the multiplexer, the amplifier chain and the comparators
are drawn on three sheets and work as one circuit. This module names their
parts, gives the nets short node names and writes the lines that every
bench of the front end needs: the rails, the lines of the controller for a
fixed range, and the model of the range sequencer.
"""

from __future__ import annotations

from circuit_sim.netlist import Netlist

LADDER_SHEET = "/Shunt Ladder/"
CHAIN_SHEET = "/Signal Chain/"
COMPARATOR_SHEET = "/Comparators/"

ALIASES = {
    "/Path Switching/SUPPLY": "supply",
    "/Output Stage/VOUT_S": "vout_s",
    "/Output Stage/DRV_OUT": "drv_out",
    "/Shunt Ladder/INP": "inp",
    "/Shunt Ladder/INN": "inn",
    "/Comparators/AMP_RAW": "amp_raw",
    "/Comparators/CMP_UP": "cmp_up",
    "/Comparators/CMP_JUMP": "cmp_jump",
    "/Comparators/CMP_OC": "cmp_oc",
    "/Controller/GATE_R1": "gate_r1",
    "/Controller/GATE_R2": "gate_r2",
    "/Controller/GATE_R3": "gate_r3",
    "/Controller/GATE_OUT": "gate_out",
    "/Controller/MUX_A0": "mux_a0",
    "/Controller/MUX_A1": "mux_a1",
    "VREF": "vref",
    "Net-(Q12-G)": "g_r1",
    "Net-(Q13-G)": "g_r2",
    "Net-(Q14-G)": "g_r3",
    "Net-(Q12-S)": "sense_r1",
    "Net-(Q13-S)": "sense_r2",
    "Net-(Q14-S-Pad1)": "sense_r3",
    "Net-(U26--)": "ped",
    "Net-(D22-common)": "lim",
    "Net-(D22-K)": "vdrv",
    "Net-(U30-AINP)": "adc_in",
    "Net-(D23-common)": "cmp_in",
    "Net-(U32--)": "th_up",
    "Net-(U31B--)": "th_oc",
    "Net-(U31A--)": "th_jump",
}
"""Short node names for the nets of the front end."""

SUPPLY_NODE = ("C62", "C63", "R87")
"""The capacitors on the supply node of the ladder (drawn on the path sheet)."""

AFTER_SHUNTS = ("C71",)
"""The capacitor on the node after the shunts (drawn on the output sheet)."""

SHUNT_OHMS = (1000.0, 31.95, 0.999, 0.1)
"""Effective shunt of each range (specification, sections 4.3 and 8)."""

FULL_SCALE_AMPS = (100e-6, 3e-3, 100e-3, 1.0)
"""Nominal full scale of each range (specification, section 4.3)."""

LOGIC_VOLTS = 3.3


def ladder_refs(netlist: Netlist) -> tuple[str, ...]:
    """The parts of the shunt ladder sheet with the capacitors of its two nodes."""
    return (*netlist.on_sheet(LADDER_SHEET), *SUPPLY_NODE, *AFTER_SHUNTS)


def chain_refs(netlist: Netlist) -> tuple[str, ...]:
    """The analog parts of the signal chain: everything but the converter lines."""
    skip = {"RN5", "U30", "C91", "C92"}
    return tuple(ref for ref in netlist.on_sheet(CHAIN_SHEET) if ref not in skip)


def comparator_refs(netlist: Netlist) -> tuple[str, ...]:
    """The parts of the comparator sheet."""
    return netlist.on_sheet(COMPARATOR_SHEET)


def rails(p12: float = 12.0, m4: float = -4.0, p3v3: float = 3.3, vref: float | None = 2.5) -> str:
    """Ideal analog rails and, unless left out, an ideal reference."""
    lines = [
        "* ideal rails",
        f"Vp12 p12v_a 0 {p12:g}",
        f"Vm4 m4v_a 0 {m4:g}",
        f"Vp3v3a p3v3_a 0 {p3v3:g}",
    ]
    if vref is not None:
        lines.append(f"Vref vref 0 {vref:g}")
    return "\n".join(lines) + "\n"


def fixed_range(index: int, output_on: bool = False) -> str:
    """The lines of the controller held for one range, as ideal sources.

    Args:
        index: The range, 0 to 3.
        output_on: Drive the line of the output switch high as well.
    """
    if not 0 <= index <= 3:
        raise ValueError(f"there is no range {index}")
    levels = {
        "gate_r1": index == 1,
        "gate_r2": index == 2,
        "gate_r3": index == 3,
        "mux_a0": index in (1, 3),
        "mux_a1": index in (2, 3),
        "gate_out": output_on,
    }
    lines = [f"* controller lines held for range {index}"]
    lines += [f"V{name} {name} 0 {LOGIC_VOLTS if high else 0:g}" for name, high in levels.items()]
    return "\n".join(lines) + "\n"


def sequencer(
    reaction: float = 100e-9,
    overlap: float = 1e-6,
    blanking: float = 2e-6,
    trip_time: float = 12e-6,
    comparators: bool = True,
) -> str:
    """The model of the range sequencer on the lines of the controller.

    The nodes ``seq_down``, ``seq_enable`` and ``seq_out_on`` are left to the
    bench, which drives them with its own sources. With ``comparators``
    false the three comparator inputs are named ``seq_up``, ``seq_jump`` and
    ``seq_oc`` instead of the nets of the comparators, for benches that
    command the range changes themselves.
    """
    inputs = "cmp_up cmp_jump cmp_oc" if comparators else "seq_up seq_jump seq_oc"
    return (
        "* range sequencer: model of rules F-16 to F-18, not a program\n"
        f"Xseq {inputs} seq_down seq_enable seq_out_on "
        "gate_r1 gate_r2 gate_r3 mux_a0 mux_a1 gate_out SEQUENCER "
        f"tseq={reaction:g} toverlap={overlap:g} tblank={blanking:g} toc={trip_time:g}\n"
    )


SEQUENCER_LIBRARIES = ("logic.lib", "sequencer.lib")
"""Model files a deck with the sequencer needs."""
