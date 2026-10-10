"""What the benches of the source meter share.

The circuit of every bench is the source meter sheet from the netlist: the
set-point DAC with its reference divider and filter, the buffer that
drives the SET pin, the linear regulator with its clamps and its minimum
load, the tracking pre-regulator with its inductor, its bleeder and its
enable gate, the difference amplifier that sets its target, and the filter
between the two. This module names those parts, gives the nets short node
names and writes the lines that stand for what the schematic does not hold.

What is assumed here, and said in the notes of every bench that uses it:

- Every rail is an ideal source: the 5 V rail, the +13.5 V of the boost
  converter, +12 V_A, -4 V_A, 3V3_A and the reference. Their own circuits
  belong to other blocks.
- The line SMU_ON is a source of 3.3 V behind the output resistance of a
  pin of the controller, and the gate of Q1 a source at the level that the
  released line 5V_OK takes. No program of the controller exists.
- The path from the regulator output to the device under test is three
  resistors: the closed source pair, the shunt of one range with its
  switch, and the closed output pair with copper and contacts. The
  capacitors of the supply node and of the node after the shunts come from
  the netlist. The switches and the range logic belong to other blocks.
- The device under test is a current sink with a capacitor beside it.
- A ceramic capacitor keeps the capacitance of the typical bias curve of
  its maker at the voltage it stands at.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

import numpy as np
from numpy.typing import NDArray

from benches import frontend
from circuit_sim.bench import OPEN_TIER, Context
from circuit_sim.circuit import Circuit, PartModel
from circuit_sim.engine import RunResult
from circuit_sim.netlist import Netlist
from circuit_sim.vendor import VENDOR_FOLDER

Real = NDArray[np.float64]

SHEET = "/Source Meter/"

ALIASES = {
    "/Path Switching/LDO_OUT": "ldo_out",
    "/Path Switching/SUPPLY": "supply",
    "/Output Stage/VOUT_S": "vout_s",
    "/Controller/SMU_ON": "smu_on",
    "/Analog Rails/5V_OK": "ok_5v",
    "Net-(C42-Pad1)": "v_pre",
    "Net-(D11-K)": "ldo_in",
    "Net-(U18-SET)": "ldo_set",
    "Net-(D10-K)": "vctl",
    "Net-(D10-A)": "vctl_feed",
    "Net-(R58-Pad1)": "set_drv",
    "Net-(U17-+)": "dac_filt",
    "Net-(U17--)": "set_fb",
    "Net-(U15-Vout)": "dac_out",
    "Net-(U15-Vref)": "dac_ref",
    "Net-(U16-FB)": "pre_fb",
    "Net-(U19-+)": "trk_p",
    "Net-(U19--)": "trk_n",
    "Net-(D13-K)": "trk_sense",
    "Net-(Q1-S)": "smu_en",
    "Net-(L2-Pad1)": "sw_l1",
    "Net-(L2-Pad2)": "sw_l2",
    "Net-(U16-PS/SYNC)": "vina",
    "Net-(C43-Pad2)": "damper",
    "Net-(C63-Pad1)": "supply_damper",
    "unconnected-(U16-PG-Pad14)": "pg_open",
    "+5V": "p5v",
    "+13V5": "p13v5",
    "+12V_A": "p12v_a",
    "-4V_A": "m4v_a",
    "+3V3_A": "p3v3_a",
    "VREF": "vref",
}
"""Short node names.

``ldo_out`` is the output of the linear regulator (TP26), ``ldo_in`` its IN
pin (TP22), ``ldo_set`` its SET pin (TP23) and ``vctl`` its VCONTROL pin.
``v_pre`` is the output of the pre-regulator (TP21) and ``pre_fb`` its
feedback pin (TP24). ``set_drv`` is the output of the buffer U17,
``dac_out`` the output of the DAC and ``dac_ref`` its reference input
(TP19). ``smu_en`` is the enable pin of the pre-regulator (TP18).
``supply`` is the supply node of the ladder and ``vout_s`` the node after
the shunts.
"""

SUPPLY_NODE = (*frontend.SUPPLY_NODE, "R90")
"""The capacitors and the bleeder of the supply node (drawn on the path sheet)."""

AFTER_SHUNTS = frontend.AFTER_SHUNTS
"""The capacitor on the node after the shunts (drawn on the output sheet)."""

DAC = "U15"
BUFFER = "U17"
REGULATOR = "U18"
CONVERTER = "U16"
TRACKER = "U19"

RAIL_5V = 5.0
RAIL_13V5 = 13.5
RAIL_12V = 12.0
RAIL_M4V = -4.0
RAIL_3V3 = 3.3
REFERENCE = 2.5

LOGIC_VOLTS = frontend.LOGIC_VOLTS

PAD_OHMS = 33.0
"""Output resistance of a pin of the controller (assumption, as in the sequencer model)."""

OK_SHARE = 0.9434
"""Level of the released line 5V_OK as a share of the 5 V rail.

R25 (10 kohm) pulls the line up; R27 and R28 (250 kohm together) and the
pull-down of 1 Mohm in each of the two LP5907 enable inputs (TI SNVS798,
pin functions) load it: 166.7 kohm against 10 kohm.
"""

DAC_STEPS = 4096
BUFFER_GAIN = 2.1
"""Gain of the buffer U17 with R57 (10 kohm) and R58 (11 kohm)."""

SET_STEP = REFERENCE / DAC_STEPS * BUFFER_GAIN
"""Step of the output voltage per code: 1.2817 mV (rule F-30)."""

SET_OFFSET = 10e-3
"""Output with the DAC at zero: the SET current of 10 uA in R60 (rule F-30)."""

LAW_OFFSET = 0.672
LAW_SLOPE = 0.956
"""The tracking law of section 4.2: V_PRE = 0.672 V + 0.956 x V_LDO."""

PAIR_OHMS = 10.6e-3
"""A closed pair of CSD17577Q3A: twice 5.3 mohm (TI SLPS515A, typical at 4.5 V)."""

RANGE_OHMS = (1000.0, 31.97, 1.021, 0.1041)
"""Shunt of each range with its switch, as the benches of the ladder find it."""

OUTPUT_OHMS = 30.6e-3
"""The closed output pair and 20 mohm for copper and contacts.

The 20 mohm are the allowance of section 2 (R-06), which has no source.
With the source pair and the shunt of range 3 the path has 145.3 mohm;
section 2 gives 144 mV at 1 A with typical parts.
"""

DUT_ESR = 5e-3
"""Series resistance of the capacitor at the device under test (assumption: ceramic)."""

CURVE = ((0.8, 1.0), (2.0, 1.0), (3.3, 0.83), (5.0, 0.6))
"""Output voltage and current of the curve of requirement R-08."""

DROPOUT_OFFSET = 0.170
DROPOUT_OHMS = 0.300
"""Dropout that section 4.2 takes as the need: 170 mV + 0.300 ohm x I."""

LIMIT_DROPOUT = {"voff": 0.147, "rc": 0.134}
"""Parameters that put the regulator model on that line (guaranteed limits)."""

LIMIT_CURRENT = {"ibmax": 17.3e-3}
"""Parameter for the least current limit of the datasheet, 1.1 A."""

ANTI_ALIAS_HERTZ = 40e3
ANTI_ALIAS_Q = 0.74
"""The filter in front of the converter: two poles (section 4.5)."""

_BIAS_VOLTS = np.array([0.0, 0.8, 1.4, 2.0, 2.5, 3.3, 3.8, 5.0, 5.5, 12.0, 13.5])

_BIAS_SHARE = {
    "CL31A226KAHNNNE": (1.0, 1.0, 0.978, 0.932, 0.882, 0.795, 0.740, 0.620, 0.576, 0.260, 0.224),
    "CL21A106KAYNNNE": (1.0, 0.986, 0.937, 0.873, 0.807, 0.696, 0.629, 0.497, 0.452, 0.188, 0.163),
    "CL21B475KAFNNNE": (1.0, 1.0, 0.994, 0.968, 0.933, 0.867, 0.822, 0.716, 0.673, 0.327, 0.283),
    "C0603C105K3RACTU": (1.0, 1.0, 0.993, 0.975, 0.953, 0.914, 0.890, 0.825, 0.797, 0.55, 0.50),
}
"""Share of the capacitance that a ceramic part keeps under bias, by part number.

The three Samsung parts follow the typical curve of the product page of
their maker (read on 2026-10-08). The KEMET part of 1 uF, 25 V, X7R in 0603
has no curve on file: it takes the curve of the Samsung part of the same
size, rating and dielectric up to 5.5 V, and the two values above 10 V are
an assumption.
"""


def bias_share(mpn: str, volts: float) -> float:
    """The share of its capacitance that a ceramic part keeps at a voltage.

    Args:
        mpn: Manufacturer part number.
        volts: The voltage across the part.

    Returns:
        1 for a part without a curve on file.
    """
    curve = _BIAS_SHARE.get(mpn)
    if curve is None:
        return 1.0
    return float(np.interp(abs(volts), _BIAS_VOLTS, np.array(curve)))


def law(v_ldo: float) -> float:
    """The target of the pre-regulator for an output voltage (section 4.2)."""
    return LAW_OFFSET + LAW_SLOPE * v_ldo


def code_of(volts: float) -> int:
    """The nominal DAC code of an output voltage (rule F-30)."""
    return round((volts - SET_OFFSET) / SET_STEP)


def volts_of(code: int) -> float:
    """The nominal output voltage of a DAC code (rule F-30)."""
    return SET_OFFSET + code * SET_STEP


def bias_scales(netlist: Netlist, v_ldo: float, v_pre: float | None = None) -> dict[str, float]:
    """Factors that put the ceramic capacitors of the block at their bias.

    Args:
        netlist: The schematic.
        v_ldo: Voltage at the regulator output and on the supply node.
        v_pre: Voltage at the pre-regulator output; the tracking law by default.
    """
    pre = law(v_ldo) if v_pre is None else v_pre
    at = {
        "C53": v_ldo,
        "C62": v_ldo,
        "C63": v_ldo,
        "C42": pre,
        "C45": pre,
        "C50": pre,
        "C46": pre,
        "C43": pre,
        "C39": RAIL_5V,
        "C40": RAIL_5V,
        "C47": RAIL_13V5,
        "C41": v_ldo / BUFFER_GAIN,
    }
    return {ref: bias_share(netlist.component(ref).mpn, volts) for ref, volts in at.items()}


def sheet_refs(netlist: Netlist) -> tuple[str, ...]:
    """Every part of the source meter sheet."""
    return netlist.on_sheet(SHEET)


def source_refs(netlist: Netlist, dut: bool = True) -> tuple[str, ...]:
    """The sheet and, with ``dut``, the capacitors on the way to the device under test."""
    refs = sheet_refs(netlist)
    return (*refs, *SUPPLY_NODE, *AFTER_SHUNTS) if dut else refs


def _level(value: float | str) -> str:
    """A source value: a number of volts, or the text of a waveform."""
    return value if isinstance(value, str) else f"{value:g}"


def rails(
    p5: float | str = RAIL_5V,
    p13: float | str = RAIL_13V5,
    p12: float | str = RAIL_12V,
    m4: float | str = RAIL_M4V,
    p3v3: float | str = RAIL_3V3,
    vref: float | str = REFERENCE,
) -> str:
    """Ideal rails; each value is a voltage or the text of a waveform."""
    return (
        "* ideal rails: the circuits that make them belong to other blocks\n"
        f"Vp5 p5v 0 {_level(p5)}\n"
        f"Vp13 p13v5 0 {_level(p13)}\n"
        f"Vp12 p12v_a 0 {_level(p12)}\n"
        f"Vm4 m4v_a 0 {_level(m4)}\n"
        f"Vp3v3a p3v3_a 0 {_level(p3v3)}\n"
        f"Vref vref 0 {_level(vref)}\n"
    )


def controller(smu_on: float | str = LOGIC_VOLTS, ok_5v: float | str | None = None) -> str:
    """The line SMU_ON of the controller and the gate of Q1.

    Args:
        smu_on: Level of the pin, or the text of a waveform.
        ok_5v: Level of the line 5V_OK; the released level at a rail of
            5 V by default.
    """
    gate = OK_SHARE * RAIL_5V if ok_5v is None else ok_5v
    return (
        "* SMU_ON: a pin of the controller behind its output resistance\n"
        f"Vsmu smu_pin 0 {_level(smu_on)}\n"
        f"Rsmu smu_pin smu_on {PAD_OHMS:g}\n"
        "* 5V_OK: released by the supervisor, pulled up by R25 against its loads\n"
        f"Vok ok_5v 0 {_level(gate)}\n"
    )


def dut(index: int, current: float | str, farads: float = 0.0, esr: float = DUT_ESR) -> str:
    """The path to the device under test and the device itself.

    Args:
        index: The range whose shunt carries the current, 0 to 3.
        current: The current of the device, or the text of a waveform.
        farads: Capacitance beside the device; none when 0.
        esr: Series resistance of that capacitance.
    """
    lines = [
        "* the path to the device under test, as three resistors: the closed",
        "* source pair, the shunt of the range with its switch, the closed",
        "* output pair with copper and contacts",
        f"Rpair ldo_out supply {PAIR_OHMS:g}",
        f"Rshunt supply vout_s {RANGE_OHMS[index]:g}",
        f"Rpath vout_s dut {OUTPUT_OHMS:g}",
        "* the device under test: a current sink and its capacitor",
        f"Iload dut 0 {_level(current)}",
    ]
    if farads > 0.0:
        lines += [f"Cdut dut dut_c {farads:g}", f"Rdut dut_c 0 {esr:g}"]
    return "\n".join(lines) + "\n"


def part(ctx: Context, ref: str, **params: float | str) -> PartModel:
    """The model of a part with parameters of its own, as an override.

    The parameters are those of the subcircuits of the repository, so the
    model is the one of the repository in every tier: a model of a
    manufacturer does not know them.

    Args:
        ctx: The context of the bench; its model map gives the model.
        ref: Reference designator.
        **params: Parameters of the subcircuit.
    """
    model = ctx.models.model_of(ctx.netlist.component(ref), OPEN_TIER)
    text = " ".join(
        f"{name}={value if isinstance(value, str) else format(value, '.9g')}"
        for name, value in params.items()
    )
    return PartModel(
        kind=model.kind,
        name=model.name,
        ports=model.ports,
        units=model.units,
        letter=model.letter,
        library=model.library,
        origin=model.origin,
        params=text,
    )


def device(ctx: Context, ref: str, name: str) -> PartModel:
    """A part with another device model of the block's file, as an override."""
    model = ctx.models.model_of(ctx.netlist.component(ref), OPEN_TIER)
    return PartModel(
        kind=model.kind,
        name=name,
        ports=model.ports,
        units=model.units,
        letter=model.letter,
        library=model.library,
        origin=model.origin,
    )


def source(
    ctx: Context,
    v_ldo: float,
    *,
    with_dut: bool = True,
    overrides: Mapping[str, PartModel] | None = None,
    scales: Mapping[str, float] | None = None,
    refs: Iterable[str] | None = None,
    switching: bool = False,
) -> Circuit:
    """The source meter from the netlist, its capacitors at their bias.

    The converter is the averaged model of the repository in every tier,
    unless ``switching`` asks for the transient model of the manufacturer:
    that model switches at 2.4 MHz and takes minutes for a millisecond, so
    only a run of a millisecond or two can afford it.

    Args:
        ctx: The context of the bench.
        v_ldo: Output voltage that decides the bias of the capacitors.
        with_dut: Take the capacitors on the way to the device under test.
        overrides: Models for single parts.
        scales: More factors on single passive parts; they multiply the
            bias factors.
        refs: Other parts than the whole sheet.
        switching: In the vendor tier, take the transient model of the
            manufacturer for the converter.
    """
    chosen = tuple(refs) if refs is not None else source_refs(ctx.netlist, with_dut)
    factors = {
        ref: share for ref, share in bias_scales(ctx.netlist, v_ldo).items() if ref in chosen
    }
    for ref, factor in (scales or {}).items():
        factors[ref] = factors.get(ref, 1.0) * factor
    models = dict(overrides or {})
    if not switching and CONVERTER in chosen and CONVERTER not in models:
        models[CONVERTER] = ctx.models.model_of(ctx.netlist.component(CONVERTER), OPEN_TIER)
    return ctx.circuit(chosen, ALIASES, models, factors)


def last(result: RunResult, name: str, plot: str | None = None) -> float:
    """The last value of a vector: the end of a run, or an operating point."""
    return float(result.real(name, plot)[-1])


def regulator_watts(result: RunResult, plot: str | None = None) -> Real:
    """The dissipation of the linear regulator along a run.

    The pass transistor takes the current of the IN pin across the voltage
    from IN to OUT; the control path takes the current of R61 across the
    voltage from VCONTROL to OUT.
    """
    out = result.real("ldo_out", plot)
    pass_amps = result.real(f"v.x{REGULATOR.lower()}.vic#branch", plot)
    control_amps = (result.real("p13v5", plot) - result.real("vctl_feed", plot)) / 10.0
    return np.asarray(
        (result.real("ldo_in", plot) - out) * pass_amps
        + (result.real("vctl", plot) - out) * control_amps,
        dtype=np.float64,
    )


def anti_alias(frequency: Real) -> Real:
    """The magnitude of the filter in front of the converter (section 4.5)."""
    ratio = frequency / ANTI_ALIAS_HERTZ
    return np.asarray(
        1.0 / np.sqrt((1.0 - ratio**2) ** 2 + (ratio / ANTI_ALIAS_Q) ** 2), dtype=np.float64
    )


def nodeset(
    circuit: Circuit,
    v_ldo: float,
    amps: float = 0.0,
    *,
    enabled: bool = True,
    code: int | None = None,
) -> str:
    """Start values for the operating point of the source.

    The amplifier models and the regulator models hold integrators, which
    start a search far from where they rest. These lines put every state
    node near its value for an output voltage; the solver still has to
    find the point itself. They are start values, not initial conditions.
    Only nodes that the circuit holds are named, and never both ends of an
    inductor: a start value on each end of a branch without resistance
    leaves the solver a matrix it cannot solve.

    Args:
        circuit: The circuit the lines are for.
        v_ldo: Output voltage that the set-point asks for.
        amps: Load current, for the states of the two regulators.
        enabled: Whether the pre-regulator runs.
        code: DAC code, when it does not follow from the output voltage.
    """
    if code is None:
        dac_volts = max(v_ldo - SET_OFFSET, 0.0) / BUFFER_GAIN
    else:
        dac_volts = code * REFERENCE / DAC_STEPS
    drive = dac_volts * BUFFER_GAIN
    pre = law(v_ldo) if enabled else max(v_ldo - 0.1, 0.0)
    plus = (pre / 100e3 + REFERENCE / 137e3) / (1 / 100e3 + 1 / 137e3 + 1 / 23.7e3)
    feedback = 0.5 if enabled else min(max(plus * 1.2052 - 0.2052 * v_ldo, 0.02), 3.28)
    base = v_ldo + 0.62 + 0.03 * float(np.log10(max(amps, 1e-3) / 1e-3)) + 0.1 * amps
    dac, buffer, tracker = f"x{DAC.lower()}", f"x{BUFFER.lower()}", f"x{TRACKER.lower()}"
    regulator = f"x{REGULATOR.lower()}"
    values = {
        "dac_ref": REFERENCE / 2.0,
        "dac_out": dac_volts,
        "dac_filt": dac_volts,
        "set_fb": dac_volts,
        "set_drv": drive,
        "ldo_set": drive + SET_OFFSET,
        "ldo_out": v_ldo,
        "supply": v_ldo,
        "vctl": RAIL_13V5 - 0.75,
        "v_pre": pre,
        "pre_fb": feedback,
        "trk_p": plus,
        "trk_n": plus,
        "trk_sense": v_ldo,
        f"{dac}.s": dac_volts,
        f"{dac}.act": 1.0,
        f"{buffer}.x1.x": drive,
        f"{buffer}.x1.y": drive,
        f"{tracker}.x1.x": feedback,
        f"{tracker}.x1.y": feedback,
        f"{regulator}.x": base,
        f"{regulator}.cmd": base,
        f"{regulator}.b": base,
    }
    nodes = set(circuit.nodes.values())
    parts = {line.split()[0].lower() for line in circuit.lines}
    present = {
        name: value
        for name, value in values.items()
        if (name.split(".")[0] in parts if "." in name else name in nodes)
    }
    return "".join(f".nodeset v({name})={value:.6g}\n" for name, value in present.items())


READY = 0.6e-3
"""Instant of a power-up run at which rails, enable and set-point are all present."""

SETTLE_STOP = 25e-3
"""Length of a power-up run that ends at rest."""

SETTLE_FILTER = 0.01
"""Factor on C41 in a power-up run: the set-point filter then has 0.1 ms.

The capacitor carries no current at rest, so the state the run ends in does
not depend on it.
"""

REST_WINDOW = 2e-3
"""Window at the end of a run in which a node at rest must not move."""

REST_LIMIT = 100e-6
"""Movement inside that window below which a run counts as at rest."""


def ramp(volts: float, start: float, stop: float) -> str:
    """A source that stays at zero and then rises in a straight line."""
    return f"PWL(0 0 {start:g} 0 {stop:g} {volts:g})"


def power_up_rails(
    p5: float = RAIL_5V,
    p13: float = RAIL_13V5,
    p12: float = RAIL_12V,
    m4: float = RAIL_M4V,
    p3v3: float = RAIL_3V3,
    vref: float = REFERENCE,
) -> str:
    """The rails rising from zero within 0.45 ms.

    A circuit without any supply is at rest with every node at zero, which
    the solver finds without a search. From there the run reaches the
    wanted state through the behavior of the circuit itself. The order of
    the rails follows section 3; their rise times are not those of the
    board.
    """
    return rails(
        p5=ramp(p5, 10e-6, 110e-6),
        p13=ramp(p13, 20e-6, 150e-6),
        p3v3=ramp(p3v3, 160e-6, 260e-6),
        m4=ramp(m4, 250e-6, 300e-6),
        p12=ramp(p12, 300e-6, 400e-6),
        vref=ramp(vref, 400e-6, 450e-6),
    )


def power_up_controller(enabled: bool = True, p5: float = RAIL_5V) -> str:
    """The controller lines of a power-up run: 5V_OK released, then SMU_ON."""
    return controller(
        ramp(LOGIC_VOLTS, 500e-6, 501e-6) if enabled else 0.0,
        ramp(OK_SHARE * p5, 200e-6, 210e-6),
    )


def stepped(amps: float, start: float = 9e-3, rise: float = 0.5e-3) -> float | str:
    """A load current that is applied after the source has started."""
    return ramp(amps, start, start + rise) if amps else 0.0


def power_up_code(ctx: Context, code: int, **params: float | str) -> PartModel:
    """The DAC of a power-up run: code zero until the rails stand."""
    return part(ctx, DAC, code=0, code1=code, t1=READY, **params)


def moved(result: RunResult, name: str, window: float = REST_WINDOW) -> float:
    """How far a node moved inside the last window of a run."""
    time = result.real("time")
    values = result.real(name)
    inside = time >= time[-1] - window
    return float(np.max(values[inside]) - np.min(values[inside]))


def nodeset_from(result: RunResult) -> str:
    """Start values for an operating point, from the end of a run at rest.

    Every node of the run is named, the internal ones of the models too:
    with part of them the solver starts between two states and fails.
    """
    lines = []
    for key, vector in result.vectors.items():
        plot, name = key.split("/", 1)
        if not plot.startswith("tran") or "#" in name or name == "time":
            continue
        lines.append(f".nodeset v({name})={float(np.real(vector[-1])):.9g}")
    return "\n".join(lines) + "\n"


_DOUBLED_KEYWORD = re.compile(r"params:\s+params:", re.IGNORECASE)


def repair_vendor_copies(ctx: Context) -> None:
    """Repair the working copies of the model files of the manufacturers.

    The transient model of the TPS63020 holds one line with the keyword
    ``PARAMS:`` twice, which PSpice accepts and ngspice does not. The
    package writes a copy of such a file beside the decks each time a deck
    is put together; this takes the second keyword out of that copy. The
    file of the manufacturer is not changed. Call it after the last
    ``ctx.deck`` and before the run.
    """
    folder = ctx.workdir / VENDOR_FOLDER
    if not folder.is_dir():
        return
    for path in folder.iterdir():
        text = path.read_text(encoding="utf-8")
        repaired = _DOUBLED_KEYWORD.sub("PARAMS:", text)
        if repaired != text:
            path.write_text(repaired, encoding="utf-8", newline="\n")


def settle_deck(
    ctx: Context,
    title: str,
    v_ldo: float,
    *,
    code: int | None = None,
    amps: float = 0.0,
    index: int = 0,
    farads: float = 0.0,
    overrides: Mapping[str, PartModel] | None = None,
    scales: Mapping[str, float] | None = None,
    dac: Mapping[str, float | str] | None = None,
    supplies: Mapping[str, float] | None = None,
    enabled: bool = True,
    extra: str = "",
    stop: float = SETTLE_STOP,
) -> str:
    """A deck that powers the source up and ends at rest in one state.

    The rails rise from zero, the line 5V_OK is released, SMU_ON is raised,
    the DAC takes its code and the load is applied; the run ends after the
    circuit has come to rest. Figures are read from the end of the run.

    Args:
        ctx: The context of the bench.
        title: First line of the deck.
        v_ldo: Output voltage asked for; it sets the bias of the capacitors
            and, without ``code``, the DAC code.
        code: DAC code, when it does not follow from ``v_ldo``.
        amps: Load current of the device under test.
        index: Range whose shunt carries that current.
        farads: Capacitance beside the device under test.
        overrides: Models for single parts; the DAC is set by ``code``.
        scales: Factors on single passive parts.
        dac: More parameters of the DAC model.
        supplies: Rail voltages that differ from the nominal ones, by the
            argument names of :func:`power_up_rails`.
        enabled: Whether SMU_ON is raised.
        extra: More lines of the stimulus.
        stop: Length of the run.
    """
    chosen = code_of(v_ldo) if code is None else code
    models = dict(overrides or {})
    models[DAC] = power_up_code(ctx, chosen, **dict(dac or {}))
    factors = {"C41": SETTLE_FILTER}
    for ref, factor in (scales or {}).items():
        factors[ref] = factors.get(ref, 1.0) * factor
    circuit = source(ctx, v_ldo, overrides=models, scales=factors)
    rail_values = dict(supplies or {})
    return ctx.deck(
        title,
        circuit,
        power_up_rails(**rail_values),
        power_up_controller(enabled, rail_values.get("p5", RAIL_5V)),
        dut(index, stepped(amps), farads),
        extra,
        control=[f"tran 2u {stop:g} 0 20u"],
    )


def at_rest(result: RunResult, names: Iterable[str] = ("ldo_out", "v_pre")) -> float:
    """The largest movement of the named nodes inside the last window of a run."""
    return max(moved(result, name) for name in names)
