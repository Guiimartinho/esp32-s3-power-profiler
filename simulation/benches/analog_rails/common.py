"""What the benches of the analog rails and of the rail monitor share.

The circuit of every bench is taken from the netlist: the sheet of the
analog rails (boost converter, regulator of +12V_A, charge pump, reference,
clamp diodes), the sheet of the rail monitor, and from the sheet of the
logic supplies the supervisor of the 5 V rail and the two 3.3 V regulators,
which the rail order cannot be shown without. Every capacitor of the
schematic that hangs on one of the rails is part of the circuit, on
whatever sheet it is drawn.

What the schematic does not hold is typed here and said in the notes of
every bench that uses it:

- The source of the 5 V rail is a voltage behind 0.2 ohm with a current
  limit and no path back. The two limiters and the multiplexer of the input
  belong to the power input block.
- The loads of the rails are current sinks of the supply currents that the
  datasheets of the supplied parts give. Each fades out below a few volts,
  as a part does that loses its supply.
- The output of the source regulator is held at 0 V: the source is off, and
  its minimum load R69 loads -4V_A from there.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

import numpy as np
from numpy.typing import NDArray

from circuit_sim.bench import Context
from circuit_sim.circuit import Circuit, PartModel
from circuit_sim.engine import RunResult
from circuit_sim.netlist import Netlist

Real = NDArray[np.float64]
"""A waveform or its time axis."""

RAILS_SHEET = "/Analog Rails/"
MONITOR_SHEET = "/Rail Monitor/"
"""The two sheets of this block."""

LIBRARY = "analog_rails.lib"
"""The model file of this block."""

ALIASES = {
    "+5V": "p5v",
    "+13V5": "p13v5",
    "+12V_A": "p12v_a",
    "-4V_A": "m4v_a",
    "+3V3_A": "p3v3_a",
    "+3V3_C": "p3v3_c",
    "VREF": "vref",
    "/Analog Rails/5V_OK": "ok5v",
    "/Controller/PWR_GOOD": "pwr_good",
    "/Path Switching/LDO_OUT": "ldo_out",
    "Net-(D6-A)": "sw",
    "Net-(U10-FB)": "fb_boost",
    "Net-(U10-EN)": "en_boost",
    "Net-(C29-Pad1)": "ldo_in",
    "Net-(U13-SET)": "set12",
    "Net-(U13-PGFB)": "pgfb",
    "Net-(U11-VIN)": "pump_in",
    "Net-(U11-CPOUT)": "cpout",
    "Net-(U11-VFB)": "fb_pump",
    "Net-(U11-EN)": "en_pump",
    "Net-(U11-C+)": "cfly_p",
    "Net-(U11-C-)": "cfly_n",
    "Net-(U12-Vin)": "ref_in",
    "Net-(U12-Trim/NR)": "ref_nr",
    "Net-(C26-Pad1)": "ref_c26",
    "Net-(C89-Pad1)": "ref_c89",
    "Net-(U15-Vref)": "dac_ref",
    "Net-(U40-CH7)": "mon_m4",
    "Net-(U14A--)": "th_low",
    "Net-(U14C--)": "th_high",
    "Net-(U14B--)": "sense_m4",
    "Net-(U14A-+)": "sense_p12",
    "Net-(U14C-+)": "sense_3v3a",
    "Net-(U14D-+)": "sense_vref",
    "Net-(U6-SENSE)": "sup_sense",
    "Net-(U6-CT)": "sup_ct",
    "Net-(D5-A)": "led",
    "Net-(U1-GPIO28_ADC2)": "gp28",
}
"""Short node names.

``sw`` is the switch node of the boost converter, ``ldo_in`` the input of
the +12V_A regulator behind R37, ``set12`` its SET pin. ``cpout`` is the
output of the charge pump ahead of its regulator. ``ref_in`` is the supply
pin of the reference behind R31, ``ref_c26`` and ``ref_c89`` the two
capacitors of the reference line behind their resistors. ``th_low`` and
``th_high`` are the two thresholds of the rail monitor, ``sense_*`` the
nodes at which it looks at each rail. ``ok5v`` is the output of the
supervisor, ``gp28`` the pin of the controller behind R4.
"""

RAIL_NETS = ("+5V", "+13V5", "+12V_A", "-4V_A", "+3V3_A", "+3V3_C", "VREF")
"""The rails whose capacitors belong to every circuit of this block."""

SUPPLY_REFS = ("U6", "U7", "U8", "R21", "R22", "R23", "R24", "R25", "R26", "D5", "C12")
"""Supervisor, 3.3 V regulators and their parts (sheet of the logic supplies)."""

REFERENCE_LINE = ("R131", "C89", "R55", "R56", "R148", "R153")
"""Parts of other sheets on the reference line: the capacitor at the
converter with its resistor, the divider of the set-point converter, the
divider of the monitor channel of -4V_A."""

OTHER_REFS = ("R69", "R4")
"""The minimum load of the source regulator and the series resistor of PWR_GOOD."""

BIAS_VOLTS = {
    "CL21B475KAFNNNE": 8.0,
    "CL32B106KAJNNNE": 20.4,
    "CL31B226KPHNNNE": 7.39,
    "CL21A106KAYNNNE": 4.97,
}
"""Voltage at which a ceramic capacitor has lost half its value, by part number.

The figures are those of ``RAILS_MLCC`` in the model file of this block.
"""

RAIL_VOLTS = {
    "+5V": 5.0,
    "+13V5": 13.5,
    "Net-(C29-Pad1)": 13.5,
    "+12V_A": 12.0,
    "Net-(U13-SET)": 12.0,
    "-4V_A": 4.0,
    "Net-(U11-CPOUT)": 4.9,
    "Net-(U11-VIN)": 5.0,
    "Net-(U12-Vin)": 3.3,
}
"""Voltage across the capacitors of each net once the rails are up."""

SOURCE_OHMS = 0.2
"""Resistance between the 5 V source and the rail: limiter, multiplexer, copper (assumed)."""

RAMP_START = 1e-3
"""Instant at which the source of the 5 V rail starts to rise."""

RAMP_TIME = 1.7e-3
"""Time the source takes to reach 5 V (section 3 of the specification, step 1)."""

AMPLIFIER_AMPS = 5.06e-3
"""Current from +12V_A to -4V_A: one AD8421 (2 mA), three OPA197 (1 mA each), the multiplexer."""

DRIVER_AMPS = 1.5e-3
"""Current from +12V_A to ground: three gate drivers at rest (0.4 mA each) and the dividers."""

ANALOG_3V3_AMPS = 10e-3
"""Current from 3V3_A to ground: two OPA365 (4.6 mA each), comparators, converters at rest."""

LOGIC_3V3_AMPS = 0.5e-3
"""Current from 3V3_C to ground beside the LED: the four comparators, logic at rest."""

CONTROL_AMPS = 1e-3
"""Current from +13V5 into the control pin of the source regulator while the source is off."""

MODULE_AMPS = 25e-3
"""Current of the controller module from the 5 V rail (0.12 W, assumed)."""

REFERENCE_AMPS = 0.15e-3
"""Current from the reference line into what the netlist parts here do not show.

The dividers of the pedestal, of the driver rail and of the comparator
thresholds, and the mean current of the converter at 100 kSPS.
"""

AVERAGED_BOOST = PartModel(
    kind="subckt",
    name="LMR62014_AVG",
    ports=("1", "2", "3", "4", "5"),
    library=LIBRARY,
    origin="written here",
)
"""The boost converter averaged over its cycle; the inductor has to be left out."""

AVERAGED_PUMP = PartModel(
    kind="subckt",
    name="LM27761_AVG",
    ports=("1", "2", "3", "4", "5", "6", "7", "8"),
    library=LIBRARY,
    origin="written here",
)
"""The charge pump without its switching."""

SWITCHING_BOOST = PartModel(
    kind="subckt",
    name="LMR62014",
    ports=("1", "2", "3", "4", "5"),
    library=LIBRARY,
    origin="written here",
)
"""The boost converter cycle by cycle, for runs that change its parameters."""

GENTLE_AMPLIFIER = "eknee=0.1 kover=20"
"""Parameters of the boost models for an error amplifier that lets the current
fall over the last 2.7 V of the output instead of the last 0.4 V."""

LEAST_LIMIT = "klim=0.7"
"""Parameter of the boost models for the least switch current limit of the
datasheet over temperature: 1.4 A against 2 A typical."""

SKIP = PartModel(kind="skip")
"""A part that is left out of a circuit."""

BOOST_REFS = ("U9", "U10", "L1", "D6", "R29", "R32", "R33", "R37", "C23", "C25", "C27", "C29")
"""The boost converter with its feedback, its filter and the position of the detector."""


OPEN_ONLY = ("U7", "U8", "U12")
"""Parts that keep the model of the repository in the circuit of all rails.

That circuit starts with every rail at 0 V. The models that the
manufacturers give for the 3.3 V regulators and for the reference do not get
through that: the first leaves the 3.3 V rails below ground, the second
gives a singular matrix while it has no supply. The reference is
cross-checked in its own bench, where its supply is applied in one step.
"""


def with_params(model: PartModel, params: str) -> PartModel:
    """A copy of a model with parameters on its element line."""
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


def supervisor(delay: float) -> PartModel:
    """The supervisor of the 5 V rail with a chosen release delay.

    The model is the one of the power input block; only its delay with the
    CT pin on the supply is set here (0.18 s to 0.42 s in the datasheet).
    """
    return PartModel(
        kind="subckt",
        name="PWRIN_TPS3808G01",
        ports=("1", "2", "3", "4", "5", "6"),
        library="power_input.lib",
        origin="written here",
        params=f"tdhi={delay:g}",
    )


def detector(delay: float = 0.24, threshold: float = 3.08) -> PartModel:
    """The voltage detector that decision D-84 keeps a position for (U9)."""
    return PartModel(
        kind="subckt",
        name="RAILS_803",
        ports=("1", "2", "3"),
        library=LIBRARY,
        origin="written here",
        params=f"vth={threshold:g} td={delay:g}",
    )


def capacitors_on(netlist: Netlist, nets: Iterable[str]) -> tuple[str, ...]:
    """The capacitors of the schematic between one of some nets and ground."""
    wanted = set(nets)
    found = []
    for ref, part in netlist.components.items():
        if part.prefix != "C" or len(part.pins) != 2:
            continue
        ends = {pin.net for pin in part.pins}
        if "GND" in ends and ends & wanted:
            found.append(ref)
    return tuple(found)


def bias_models(netlist: Netlist, refs: Iterable[str]) -> dict[str, PartModel]:
    """Models with the loss under bias for the ceramic capacitors that have a curve."""
    models: dict[str, PartModel] = {}
    for ref in refs:
        part = netlist.component(ref)
        half = BIAS_VOLTS.get(part.mpn)
        if part.prefix != "C" or half is None:
            continue
        value = part.value.split()[0]
        models[ref] = PartModel(
            kind="subckt",
            name="RAILS_MLCC",
            ports=("1", "2"),
            library=LIBRARY,
            origin="written here",
            params=f"c={value} v0={half:g}",
        )
    return models


def bias_scales(netlist: Netlist, refs: Iterable[str]) -> dict[str, float]:
    """Factors that give the ceramic capacitors their capacitance at the rail voltage.

    For runs in which the capacitors have to stay linear: each capacitor
    with a bias curve takes the value it has once its rail is up, which is
    less than its value on the way there.
    """
    scales: dict[str, float] = {}
    for ref in refs:
        part = netlist.component(ref)
        half = BIAS_VOLTS.get(part.mpn)
        if part.prefix != "C" or half is None:
            continue
        volts = [RAIL_VOLTS[pin.net] for pin in part.pins if pin.net in RAIL_VOLTS]
        if volts:
            scales[ref] = 1.0 / (1.0 + (volts[0] / half) ** 2)
    return scales


def rails_refs(netlist: Netlist, monitor: bool = True, supplies: bool = True) -> tuple[str, ...]:
    """The parts of a whole-rails circuit.

    Args:
        netlist: The schematic.
        monitor: Take the sheet of the rail monitor as well.
        supplies: Take the supervisor and the two 3.3 V regulators as well.
    """
    refs = list(netlist.on_sheet(RAILS_SHEET))
    if monitor:
        refs += netlist.on_sheet(MONITOR_SHEET)
    if supplies:
        refs += SUPPLY_REFS
    refs += REFERENCE_LINE + OTHER_REFS
    refs += capacitors_on(netlist, RAIL_NETS)
    return tuple(dict.fromkeys(refs))


def whole_rails(
    ctx: Context,
    overrides: Mapping[str, PartModel] | None = None,
    scales: Mapping[str, float] | None = None,
    averaged: bool = True,
    bias: bool = True,
) -> Circuit:
    """The circuit of all rails with the monitor and the logic supplies.

    Args:
        ctx: The bench context.
        overrides: Models for single parts, on top of the ones set here.
        scales: Factors on the values of passive parts.
        averaged: Use the averaged models of the two converters and leave
            the inductor of the boost converter out, for runs of seconds.
        bias: Give the ceramic capacitors with a bias curve their loss.
    """
    refs = rails_refs(ctx.netlist)
    chosen: dict[str, PartModel] = {
        ref: ctx.models.model_of(ctx.netlist.component(ref)) for ref in OPEN_ONLY
    }
    if bias:
        chosen.update(bias_models(ctx.netlist, refs))
    if averaged:
        chosen.update({"U10": AVERAGED_BOOST, "U11": AVERAGED_PUMP, "L1": SKIP})
    chosen.update(overrides or {})
    return ctx.circuit(refs, ALIASES, chosen, scales)


def energy_scale(half: float, start: float, end: float) -> float:
    """Factor that gives a ceramic capacitor the energy it takes between two voltages.

    A capacitor that loses capacitance under bias takes more energy on the
    way to a voltage than a linear one of the value it has there. The factor
    makes a linear capacitor take the same energy between ``start`` and
    ``end``.

    Args:
        half: Voltage at which the capacitor has lost half its value.
        start: Voltage at which the charge begins.
        end: Voltage at which it ends.
    """
    gained = math.log((1.0 + (end / half) ** 2) / (1.0 + (start / half) ** 2))
    return half**2 * gained / (end**2 - start**2)


def boost_circuit(
    ctx: Context,
    overrides: Mapping[str, PartModel] | None = None,
    start: float = 0.0,
    bias: bool = False,
) -> Circuit:
    """The boost converter alone, with the capacitors of the 5 V rail.

    Without ``bias`` the ceramic capacitors are linear: the solver does not
    get through the edges of the switch with capacitors that change with
    their voltage. Those of the 5 V rail take the value they have at 5 V;
    those of +13V5 take the value that gives them the energy of a charge
    from ``start`` to 13.5 V, which is what a start has to deliver.

    Args:
        ctx: The bench context.
        overrides: Models for single parts: a variant of the converter, the
            averaged converter without its inductor, a detector at U9.
        start: Voltage of +13V5 before the converter starts.
        bias: Give the ceramic capacitors their loss under bias instead, for
            runs with the averaged converter.
    """
    refs = (*BOOST_REFS, *capacitors_on(ctx.netlist, ("+5V",)))
    if bias:
        chosen = bias_models(ctx.netlist, refs)
        chosen.update(overrides or {})
        return ctx.circuit(refs, ALIASES, chosen)
    scales = bias_scales(ctx.netlist, refs)
    for ref in refs:
        part = ctx.netlist.component(ref)
        half = BIAS_VOLTS.get(part.mpn)
        if half is None or part.prefix != "C":
            continue
        if any(pin.net in ("+13V5", "Net-(C29-Pad1)") for pin in part.pins):
            scales[ref] = energy_scale(half, start, RAIL_VOLTS["+13V5"])
    return ctx.circuit(refs, ALIASES, overrides, scales)


def boost_stimulus(limit: float, control: float = CONTROL_AMPS) -> str:
    """Source and loads of the boost converter alone.

    Args:
        limit: Current limit of the source. Below 2 A it is the input of the
            controller module, whose limiter passes the rail within 0.2 ms;
            at 2 A it is the USB-C input with its ramp of 1.7 ms.
        control: Current from +13V5 into the control pin of the source
            regulator.
    """
    ramp = RAMP_TIME if limit >= 2.0 else 0.2e-3
    return "\n".join(
        [
            source_5v(limit=limit, ramp=ramp),
            "* loads: the controller module on the 5 V rail, the control pin of the source",
            "* regulator on +13V5; the +12V_A regulator is still held off",
            f"Bmod p5v 0 I = {MODULE_AMPS:g}*tanh(max(v(p5v), 0)/2)",
            "Rbleed p5v 0 10k",
            f"Bctl ldo_in 0 I = {control:g}*tanh(max(v(ldo_in), 0)/2)",
        ]
    )


def source_5v(
    limit: float = 2.0,
    start: float = RAMP_START,
    ramp: float = RAMP_TIME,
    events: str = "",
) -> str:
    """The source of the 5 V rail: a ramp to 5 V behind a resistance and a current limit.

    Args:
        limit: The current limit: 2.0 A on the USB-C input, 0.67 A to 0.85 A
            on the input of the controller module (section 4.1).
        start: The instant at which the source starts to rise.
        ramp: The time it takes to reach 5 V.
        events: More points of the piece-wise linear source, for a dip or a
            removal of the supply.
    """
    points = f"0 0 {start:g} 0 {start + ramp:g} 5 {events}".strip()
    return "\n".join(
        [
            "* the source of the 5 V rail: no path back, as behind the multiplexer",
            f"Vsrc src 0 PWL({points})",
            f"Bsrc src p5v I = min(max(v(src,p5v)/{SOURCE_OHMS:g}, 0), {limit:g})",
        ]
    )


def loads(module: float = MODULE_AMPS, control: float = CONTROL_AMPS) -> str:
    """The loads of the rails as current sinks, and the pins the schematic leaves open.

    Args:
        module: Current of the controller module from the 5 V rail.
        control: Current into the control pin of the source regulator.
    """
    return "\n".join(
        [
            "* loads of the rails: supply currents of the parts they feed, fading out",
            "* below a few volts",
            f"Bamp p12v_a m4v_a I = {AMPLIFIER_AMPS:g}*tanh(max(v(p12v_a,m4v_a), 0)/3)",
            f"Bdrv p12v_a 0 I = {DRIVER_AMPS:g}*tanh(max(v(p12v_a), 0)/2)",
            f"B3va p3v3_a 0 I = {ANALOG_3V3_AMPS:g}*tanh(max(v(p3v3_a), 0)/1.5)",
            f"B3vc p3v3_c 0 I = {LOGIC_3V3_AMPS:g}*tanh(max(v(p3v3_c), 0)/1.5)",
            f"Bctl p13v5 0 I = {control:g}*tanh(max(v(p13v5), 0)/2)",
            f"Bmod p5v 0 I = {module:g}*tanh(max(v(p5v), 0)/2)",
            f"Bref vref 0 I = {REFERENCE_AMPS:g}*tanh(max(v(vref), 0))",
            "* the output of the source regulator rests at 0 V while the source is off",
            "Vldo ldo_out 0 0",
            "* pin of the controller and input of the shift register on PWR_GOOD",
            "Cgp28 gp28 0 5p",
            "Cu34 pwr_good 0 3p",
        ]
    )


def crossing_after(time: Real, wave: Real, level: float, rising: bool, after: float) -> float:
    """The first crossing of a level after an instant, or NaN when there is none."""
    below = wave < level
    change = np.flatnonzero(below[1:] != below[:-1])
    change = change[below[change] == rising]
    for index in change:
        t0, t1, y0, y1 = time[index], time[index + 1], wave[index], wave[index + 1]
        instant = float(t0 + (level - y0) * (t1 - t0) / (y1 - y0))
        if instant >= after:
            return instant
    return float("nan")


def nodeset(run: RunResult) -> str:
    """Lines that start an operating point where a settled transient run ended.

    The models of this block hold comparators with hysteresis and timers: an
    operating point that the solver looks for from zero does not find their
    on state. A transient that starts with everything off and has settled
    does; its last point, given as ``.nodeset``, is where the solver then
    starts, and it has to confirm it by its own iterations.

    Args:
        run: A transient run that kept every node (``save all``).
    """
    lines = ["* start of the operating point: the end of a settled transient run"]
    for key in sorted(run.vectors):
        plot, name = key.split("/", 1)
        if not plot.startswith("tran") or name == "time" or "#" in name or name.startswith("@"):
            continue
        value = float(run.vectors[key].real[-1])
        lines.append(f".nodeset v({name})={value:.9g}")
    return "\n".join(lines)
