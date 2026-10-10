"""What the benches of the power input share.

The parts of the two sheets and of the neighbors that hang on the 5 V rail,
short node names for their nets, and the lines that a bench has to write
itself because the schematic does not hold them: a USB source behind its
cable, the port of a computer, and the loads of the other blocks.

Nothing here types a part of the schematic. The capacitors, the diodes and
the integrated circuits come from the netlist through ``circuit``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
from numpy.typing import NDArray

from circuit_sim.bench import Context
from circuit_sim.circuit import Circuit, PartModel
from circuit_sim.engine import RunResult
from circuit_sim.errors import BenchError
from circuit_sim.netlist import Netlist
from circuit_sim.values import parse_value

Real = NDArray[np.float64]

LIBRARY = "power_input.lib"
"""Model file of the block; a deck that uses its helper functions includes it."""

INPUT_SHEET = "/Power Input/"
LOGIC_SHEET = "/Logic Supplies/"

NOT_FITTED = frozenset({"R14", "C5", "U9"})
"""Positions of the schematic without a part (decision D-84 of the specification)."""

MODULE = ("U1", "D1", "JP1")
"""The supply side of the controller module, its diode from the rail and its
jumper. Their models are the ones of the digital block."""

RAIL_NEIGHBORS = ("C18", "C39", "C40", "R23")
"""Capacitors of other sheets that stand on the 5 V rail, and its 10 kohm load."""

CHARGE_PUMP_FILTER = ("R30", "C21")
"""The resistor and the capacitor ahead of the charge pump, which hang on the rail."""

BOOST_PASSIVES = ("L1", "D6", "C25", "C27", "R37", "C29")
"""The parts through which the rail charges the output of the boost converter.
The inductor and the diode take the models of the analog rails block."""

MONITOR = ("R142", "R143", "R151", "C105", "R144", "R145", "C106", "C107")
"""The dividers of the monitor converter for the rail and the two CC pins."""

OK_LOADS = ("R27", "R28")
"""The divider that the line 5V_OK drives on the sheet of the analog rails."""

ALIASES = {
    "Net-(D2-A1)": "vbus_c",
    "Net-(D4-A)": "vin1",
    "Net-(D3-A)": "vin2",
    "/Controller/PICO_5V": "pico_5v",
    "Net-(JP1-A)": "pico_vbus",
    "Net-(D1-K)": "vsys",
    "+5V": "rail",
    "/Analog Rails/5V_OK": "ok5v",
    "+3V3_C": "v3c",
    "+3V3_A": "v3a",
    "/Monitors/SRC_ST": "src_st",
    "/Monitors/CC1": "cc1",
    "/Monitors/CC2": "cc2",
    "Net-(U4-ILM)": "ilm_c",
    "Net-(U3-ILM)": "ilm_p",
    "Net-(R16-Pad2)": "imon",
    "Net-(U4-dV/dT)": "dvdt_c",
    "Net-(U4-EN/UVLO)": "en_c",
    "Net-(U3-EN/UVLO)": "en_p",
    "Net-(U5-PR1)": "pr1",
    "Net-(C10-Pad1)": "damper",
    "Net-(U6-SENSE)": "sense",
    "Net-(U6-CT)": "ct",
    "Net-(D5-A)": "led",
    "Net-(U40-CH2)": "mon_5v",
    "Net-(U40-CH3)": "mon_cc1",
    "Net-(U40-CH4)": "mon_cc2",
    "+13V5": "p13v5",
    "Net-(D6-A)": "sw",
    "Net-(C29-Pad1)": "p13v5_f",
    "Net-(U11-VIN)": "cp_in",
    "Net-(U11-EN)": "cp_en",
}
"""Short node names for the nets of the power input and its neighbors."""

BIAS_HALF_VOLTS = {
    "CL21B475KAFNNNE": 8.0,
    "CL31B226KPHNNNE": 7.39,
    "CL21A106KAYNNNE": 4.97,
    "CL32B106KAJNNNE": 20.4,
}
"""Voltage at which a ceramic capacitor has lost half its capacitance, by part
number: fits to the bias curves of the manufacturer (see PWRIN_MLCC)."""

VENDOR_DIODE = PartModel(
    kind="device",
    name="DI_1N5819HW",
    ports=("2", "1"),
    letter="D",
    library="vendor/diodes-1N5819HW-1N5819HW.spice.txt",
    origin="vendor",
)
"""The model of the manufacturer for the diodes across the limiters. They
have an entry of their own in the model map, which the vendor tier does not
replace; the qualification bench of the diodes asks for this model by hand.
The benches of the block do not: the file holds a line of plain text that
stops the simulator."""

SUPERVISOR_TYP = (3.912, 3.971)
"""Nominal falling and rising level of the supervisor on the rail, from the
0.405 V of its datasheet, 1.5 % of hysteresis and the divider R21, R22."""

SUPERVISOR_FALL = (3.83, 4.00)
"""Limits of the falling level of the supervisor (specification, section 3)."""

SUPERVISOR_RISE_MOST = 4.12
"""Highest release level of the supervisor (specification, section 3)."""

RAIL_FIRMWARE_LIMIT = 4.25
"""Level below which firmware opens the output (specification, rule F-14)."""

LIMIT_USB_C = (2.0, 1.81, 2.17)
"""Current limit of the USB-C input: nominal, least, most (specification, section 4.1)."""

LIMIT_MODULE = (0.76, 0.67, 0.85)
"""Current limit of the module input: nominal, least, most (specification, section 4.1)."""

PATH_OHMS = (0.126, 0.170)
"""Resistance from a connector to the rail, typical and at most (section 4.1)."""

CABLE_OHMS = 0.15
"""Resistance of a USB cable with its contacts, both conductors: an assumption."""

CABLE_HENRIES = 0.5e-6
"""Inductance of a short USB cable: an assumption (the earlier estimates of
the specification used the same)."""

IDLE_AMPS = 0.085
"""What the converters of the carrier take from the rail at idle, beside the
3.3 V rails: an assumption (0.12 A in all with the two figures below)."""

LOGIC_3V3C_AMPS = 0.010
"""Load of the logic rail 3V3_C at idle: an assumption."""

LOGIC_3V3A_AMPS = 0.025
"""Load of the analog rail 3V3_A at idle: an assumption."""

BOOST_START_AMPS = 1.5
"""Input current of the boost converter while it charges its output: an
assumption between the least (1.4 A) and the typical (2 A) switch current
limit of its datasheet (SNVS735B, page 4); the part has no soft start."""

BOOST_TARGET_VOLTS = 13.5
"""Output of the boost converter (specification, section 3)."""

BIAS_FIXED = "fixed"
BIAS_CURVE = "curve"
BIAS_NONE = "none"

FAST_SUPERVISOR = "tdhi=1m"
"""Release delay of the supervisor shortened to 1 ms, for runs in which the
0.3 s of the part only cost time."""

RUNNING_AT = 6.5e-3
"""Instant at which a carrier that was plugged in at 0.1 ms runs at idle, with
the supervisor shortened: the rail is up after 4 ms, 5V_OK follows 1 ms later."""


def check_assumed_values(netlist: Netlist) -> None:
    """Stop when a value that a model repeats has changed in the schematic.

    The model of the aluminum capacitor C11 carries its capacitance, because
    a capacitor with a series resistance is a subcircuit.

    Raises:
        BenchError: When the schematic no longer says 47 uF.
    """
    farads = parse_value(netlist.component("C11").value)
    if abs(farads - 47e-6) > 1e-9:
        raise BenchError(f"C11 is {farads:g} F in the schematic; its model still says 47 uF")


def input_refs(netlist: Netlist) -> tuple[str, ...]:
    """The fitted parts of the power input sheet."""
    return tuple(ref for ref in netlist.on_sheet(INPUT_SHEET) if ref not in NOT_FITTED)


def logic_refs(netlist: Netlist) -> tuple[str, ...]:
    """The parts of the logic supplies sheet."""
    return netlist.on_sheet(LOGIC_SHEET)


def decoupling_refs(netlist: Netlist, net: str) -> tuple[str, ...]:
    """The capacitors of other sheets between a rail and ground."""
    found = []
    for part in netlist.components.values():
        if part.prefix != "C" or part.sheet in (INPUT_SHEET, LOGIC_SHEET):
            continue
        nets = {pin.net for pin in part.pins}
        if nets == {net, "GND"}:
            found.append(part.ref)
    return tuple(found)


def carrier_refs(netlist: Netlist, *, module: bool = True, boost: bool = True) -> tuple[str, ...]:
    """Everything of the schematic that the benches of the whole input use.

    The two sheets, the capacitors of other sheets on the 5 V rail and on
    the two 3.3 V rails, the filter of the charge pump, the passive parts of
    the boost converter, the dividers of the monitor and of 5V_OK, and the
    supply side of the controller module.

    Args:
        netlist: The schematic.
        module: Include the controller module, its diode and its jumper.
        boost: Include the inductor, the diode and the capacitors of the
            boost converter.
    """
    refs = [*input_refs(netlist), *logic_refs(netlist), *RAIL_NEIGHBORS, *CHARGE_PUMP_FILTER]
    refs += [*MONITOR, *OK_LOADS]
    refs += [*decoupling_refs(netlist, "+3V3_C"), *decoupling_refs(netlist, "+3V3_A")]
    if boost:
        refs += BOOST_PASSIVES
    if module:
        refs += MODULE
    return tuple(dict.fromkeys(refs))


def bias_models(netlist: Netlist, refs: Iterable[str]) -> dict[str, PartModel]:
    """Models with the loss of capacitance under bias for the ceramic capacitors.

    Only the part numbers whose bias curve was read get one; the value of
    each capacitor is the one of the schematic.
    """
    models = {}
    for ref in refs:
        part = netlist.component(ref)
        half = BIAS_HALF_VOLTS.get(part.mpn)
        if part.prefix != "C" or half is None:
            continue
        models[ref] = PartModel(
            kind="subckt",
            name="PWRIN_MLCC",
            ports=("1", "2"),
            library=LIBRARY,
            origin="written here",
            params=f"c={parse_value(part.value):g} v0={half:g}",
        )
    return models


def bias_scales(netlist: Netlist, refs: Iterable[str]) -> dict[str, float]:
    """The share of its capacitance that each ceramic capacitor keeps in operation.

    The capacitors behind the boost converter work at 13.5 V, every other
    one at 5 V. Only the part numbers whose bias curve was read are scaled.
    """
    scales = {}
    for ref in refs:
        part = netlist.component(ref)
        half = BIAS_HALF_VOLTS.get(part.mpn)
        if part.prefix != "C" or half is None:
            continue
        volts = BOOST_TARGET_VOLTS if ref in BOOST_PASSIVES else 5.0
        scales[ref] = 1.0 / (1.0 + (volts / half) ** 2)
    return scales


def variant(ctx: Context, ref: str, params: str) -> PartModel:
    """The model of a part with other parameters, for corner runs."""
    model = ctx.models.model_of(ctx.netlist.component(ref), ctx.tier)
    if model.origin == "vendor":
        return model  # the parameters belong to the models written here
    return PartModel(
        kind=model.kind,
        name=model.name,
        ports=model.ports,
        units=model.units,
        letter=model.letter,
        library=model.library,
        origin=model.origin,
        params=params,
    )


def circuit(
    ctx: Context,
    refs: Iterable[str],
    *,
    bias: str = BIAS_FIXED,
    overrides: Mapping[str, PartModel] | None = None,
    params: Mapping[str, str] | None = None,
    scales: Mapping[str, float] | None = None,
) -> Circuit:
    """The parts of the schematic as a circuit, with the names of this block.

    Args:
        ctx: The bench context.
        refs: Reference designators.
        bias: What the ceramic capacitors lose under bias. ``fixed`` gives
            them the capacitance they keep at their working voltage,
            ``curve`` a capacitance that follows their voltage (for runs
            that start at 0 V and for the peak at the receptacle), ``none``
            the value of the schematic.
        overrides: Models that replace the ones of the model map.
        params: Parameters for the models of single parts, by designator.
        scales: Factors on the values of single passive parts, on top of
            the ones of ``fixed``.
    """
    chosen = tuple(dict.fromkeys(refs))
    check_assumed_values(ctx.netlist)
    models: dict[str, PartModel] = {}
    scaled: dict[str, float] = {}
    if bias == BIAS_CURVE:
        models.update(bias_models(ctx.netlist, chosen))
    elif bias == BIAS_FIXED:
        scaled.update(bias_scales(ctx.netlist, chosen))
    elif bias != BIAS_NONE:
        raise BenchError(f"unknown bias option {bias!r}")
    for ref, text in (params or {}).items():
        if ref in chosen:
            models[ref] = variant(ctx, ref, text)
    models.update(overrides or {})
    for ref, factor in (scales or {}).items():
        if ref in models and models[ref].name == "PWRIN_MLCC":
            raise BenchError(f"{ref} has a bias model: scale it through its parameters")
        scaled[ref] = scaled.get(ref, 1.0) * factor
    return ctx.circuit(chosen, ALIASES, models, scaled)


def switch(name: str, a: str, b: str, close_at: float, open_at: float | None = None) -> str:
    """A contact that closes at one instant and, if asked, opens at another.

    The contact is a conductance that changes within 50 ns when it closes
    and within 1 us when it opens: a hard switch stops the solver.
    """
    state = f"pwrin_hi((time - {close_at:g})/20n)"
    if open_at is not None:
        state += f"*pwrin_hi(({open_at:g} - time)/0.4u)"
    return f"B{name} {a} {b} I = v({a},{b})*(1e-9 + 200*{state})\n"


def cable(
    name: str, a: str, b: str, ohms: float = CABLE_OHMS, henries: float = CABLE_HENRIES
) -> str:
    """A cable: resistance and inductance in series.

    A resistor of 100 ohm lies across the inductance. It damps the ringing
    of the megahertz range, which a real cable loses in its skin effect, and
    carries the current when a contact at its end opens.
    """
    return (
        f"R{name} {a} {name}_m {ohms:g}\n"
        f"L{name} {name}_m {b} {henries:g}\n"
        f"R{name}_d {name}_m {b} 100\n"
    )


def usb_c_source(
    volts: float,
    plug_at: float,
    *,
    unplug_at: float | None = None,
    replug_at: float | None = None,
    ohms: float = CABLE_OHMS,
    henries: float = CABLE_HENRIES,
    amps: float | None = None,
    waveform: str = "",
) -> str:
    """A live USB-C source that is plugged into the receptacle of the carrier.

    The source is an ideal voltage, or one that gives no more than ``amps``,
    behind the cable; the contact closes at ``plug_at``, opens at
    ``unplug_at`` and closes for good at ``replug_at``. With ``waveform``
    the source follows that SPICE waveform in place of the steady voltage.
    The current of the cable is ``i(Vusbc_i)``.
    """
    lines = "* USB-C source behind its cable (not in the schematic)\n"
    lines += f"Vusbc usbc_s 0 {waveform or format(volts, 'g')}\n"
    if amps is None:
        lines += "Rusbc_s usbc_s usbc_l 1m\n"
    else:
        lines += limited("usbc", "usbc_s", "usbc_l", amps)
    lines += "Vusbc_i usbc_l usbc_o 0\n"
    lines += switch("usbc_sw", "usbc_o", "usbc_p", plug_at, unplug_at)
    if replug_at is not None:
        lines += switch("usbc_sw2", "usbc_o", "usbc_p", replug_at)
    lines += cable("usbc_c", "usbc_p", "vbus_c", ohms, henries)
    return lines


def limited(name: str, a: str, b: str, amps: float, ohms: float = 0.05) -> str:
    """A source resistance that lets no more than ``amps`` pass, in either direction.

    Most of ``ohms`` is a resistor; one fourteenth is an element whose
    current saturates at ``amps``. Up to 85 % of the limit the two together
    are within 4 % of ``ohms``.
    """
    knee = ohms / 14.0
    return (
        f"R{name}_lim {a} {name}_k {ohms - knee:g}\n"
        f"B{name}_lim {name}_k {b} I = {amps:g}*tanh(v({name}_k,{b})/{amps * knee:g})\n"
    )


def module_port(
    volts: float,
    plug_at: float,
    *,
    unplug_at: float | None = None,
    replug_at: float | None = None,
    ohms: float = 0.25,
    henries: float = 0.8e-6,
    switch_amps: float | None = 1.0,
    farads: float = 120e-6,
) -> str:
    """The USB port of a computer that the cable of the module is plugged into.

    The port is a 5 V supply behind a power switch that limits the current
    (70 mohm and 1 A, the figures of a common port switch: an assumption, as
    in the earlier estimates of the specification), with 120 uF behind the
    switch, the least that the USB specification asks of a port. With
    ``switch_amps`` None the supply is stiff. The capacitor of the port is
    charged when the run starts. The contact closes at ``plug_at``, opens at
    ``unplug_at`` and closes for good at ``replug_at``. The current of the
    cable is ``i(Vport_i)``.
    """
    lines = "* USB port of a computer behind the cable of the module (not in the schematic)\n"
    lines += f"Vport port_s 0 {volts:g}\n"
    if switch_amps is None:
        lines += "Rport_s port_s port_b 1m\n"
    else:
        lines += limited("port", "port_s", "port_b", switch_amps, 0.07)
        lines += f"Cport port_b port_c {farads:g} ic={volts:g}\nRport_c port_c 0 0.1\n"
    lines += "Vport_i port_b port_o 0\n"
    lines += switch("port_sw", "port_o", "port_p", plug_at, unplug_at)
    if replug_at is not None:
        lines += switch("port_sw2", "port_o", "port_p", replug_at)
    lines += cable("port_cb", "port_p", "pico_vbus", ohms, henries)
    return lines


def idle_loads(scale: float = 1.0) -> str:
    """The loads of the other blocks at idle, as current sinks.

    The sinks of the two 3.3 V rails follow their rail, so they take nothing
    from a rail that is off. The sink of the 5 V rail stands for the two
    converters of the analog rails and runs while 5V_OK is high.
    """
    return (
        "* loads of the other blocks at idle (assumptions)\n"
        f"Bload_c v3c 0 I = {LOGIC_3V3C_AMPS * scale:g}*v(v3c)/3.3\n"
        f"Bload_a v3a 0 I = {LOGIC_3V3A_AMPS * scale:g}*v(v3a)/3.3\n"
        f"Bload_5 rail 0 I = {IDLE_AMPS * scale:g}*pwrin_hi((v(ok5v) - 2)/0.2)"
        "*pwrin_hi((v(rail) - 2.7)/0.2)\n"
    )


def boost_start(amps: float = BOOST_START_AMPS, efficiency: float = 0.8) -> str:
    """The boost converter as a load: it takes a fixed current until its output is up.

    The converter has no soft start and no under-voltage lock-out. It runs
    from 2.7 V on the rail (the least of its datasheet), takes ``amps`` from
    the rail and delivers that power, less its losses, to its output until
    the output has reached 13.5 V. Its inductor and its diode come from the
    schematic and charge the output to the level of the rail before that.
    """
    run = (
        "pwrin_hi((v(rail) - 2.7)/0.05)"
        f"*pwrin_hi(({BOOST_TARGET_VOLTS:g} - v(p13v5))/0.05)*v(boost_lag)"
    )
    return (
        "* boost converter as a load (assumption: see the notes)\n"
        "Bboost_on boost_on 0 V = pwrin_hi((v(rail) - 2.7)/0.05)\n"
        "Rboost_lag boost_on boost_lag 5k\n"
        "Cboost_lag boost_lag 0 1n\n"
        f"Bboost_in rail 0 I = {amps:g}*{run}\n"
        f"Bboost_out 0 p13v5 I = {amps * efficiency:g}*v(rail)/max(v(p13v5), 1)*{run}\n"
        "Rboost_load p13v5 0 146k\n"
    )


def step_load(name: str, node: str, amps: float, at: float, edge: float = 1e-6) -> str:
    """A current sink that steps on at one instant."""
    return f"B{name} {node} 0 I = {amps:g}*pwrin_hi((time - {at:g})/{edge / 4:g})\n"


def power_load(
    name: str,
    node: str,
    watts: float,
    at: float,
    until: float | None = None,
    gate: str = "ok5v",
) -> str:
    """A load of constant power that follows a gate signal, as the pre-regulator does.

    The pre-regulator is enabled through the transistor that 5V_OK turns
    on, so the load is shed when the supervisor trips; it follows the gate
    with a delay of 50 us (the specification estimates 0.1 ms at most).
    Below 2 V the load takes the current it takes at 2 V.
    """
    window = f"pwrin_hi((time - {at:g})/0.25u)"
    if until is not None:
        window += f"*pwrin_hi(({until:g} - time)/0.25u)"
    return (
        f"B{name}_g {name}_g 0 V = pwrin_hi((v({gate}) - 1.5)/0.1)*{window}\n"
        f"R{name}_g {name}_g {name}_d 50k\n"
        f"C{name}_g {name}_d 0 1n\n"
        f"B{name} {node} 0 I = {watts:g}/max(v({node}), 2.0)*v({name}_d)"
        f"*pwrin_hi((v({node}) - 0.3)/0.05)\n"
    )


def ideal_supply(name: str, node: str, volts: float, at: float, rise: float = 20e-6) -> str:
    """A supply without a cable that comes up at one instant, for static runs.

    The current of the supply is ``i(V<name>_i)``.
    """
    return (
        f"V{name} {name}_s 0 PWL(0 0 {at:g} 0 {at + rise:g} {volts:g})\n"
        f"V{name}_i {name}_s {name}_o 0\n"
        f"R{name} {name}_o {node} 1m\n"
    )


def run_all(
    ctx: Context, decks: Mapping[str, str], keep: Iterable[str] = ()
) -> dict[str, RunResult]:
    """Run the decks of a bench side by side and keep the named ones with the results."""
    for name in keep:
        ctx.kept[f"{ctx.prefix}.{name}.cir"] = decks[name]
    return ctx.run_many(decks)


def transient(step: float, stop: float, start: float = 0.0) -> str:
    """The transient analysis of a run that starts with everything at zero.

    The run begins without an operating point (``uic``): every capacitor is
    empty and every source of a bench starts at zero or behind an open
    contact. The operating point of the unpowered board is a matrix of
    conductances from 1 pS to 200 S, on which the solver reports a singular
    matrix and then a point found by stepping; a start from zero needs none.
    """
    return f"tran {step:g} {stop:g} {start:g} {step:g} uic"


def charge_above(time: Real, amps: Real, level: float, start: float, stop: float) -> float:
    """The charge that a current carries above a level, between two instants."""
    inside = (time >= start) & (time <= stop)
    excess = np.clip(amps[inside] - level, 0.0, None)
    return float(np.sum(0.5 * (excess[1:] + excess[:-1]) * np.diff(time[inside])))


def time_above(time: Real, values: Real, level: float, start: float, stop: float) -> float:
    """The time a waveform spends above a level between two instants."""
    inside = (time >= start) & (time <= stop)
    over = (values[inside] > level).astype(np.float64)
    return float(np.sum(0.5 * (over[1:] + over[:-1]) * np.diff(time[inside])))


def cut(time: Real, start: float, stop: float) -> NDArray[np.bool_]:
    """The samples between two instants."""
    return np.asarray((time >= start) & (time <= stop), dtype=np.bool_)
