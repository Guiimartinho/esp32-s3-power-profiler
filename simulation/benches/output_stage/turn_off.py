"""The fast opening of the output switch under load, and the rest of its gate."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.output_stage import common
from circuit_sim import measure, tolerance
from circuit_sim.bench import OPEN_TIER, Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_EVENT = 200e-6
"""Instant at which GATE_OUT falls."""

_WINDOW = 80e-6
"""Time that a fast run goes on after the command."""

_LOAD_AMPS = 1.0
"""Current that flows when the switch is told to open."""

_PATH_OHMS = 0.115
"""Resistance from the source to the terminal in range 3, to size the load:
the 0.1 ohm shunt, its switch and the output pair (about)."""

_PIN_FARADS = 20e-12
"""Capacitance on GATE_OUT with the pin released: pad, track and the input of
the side register (assumption)."""

_C74_TOLERANCE = 0.05
"""Tolerance of C74: its value string gives none; 5 % is the grade of its part number."""

_GATE_LIMIT = 7e-6
"""Time in which the gate node is below 2 V (specification, section 4.2)."""

_RESIDUAL_DELAYS = (30e-6, 100e-6, 1e-3, 10e-3)
"""Instants after the command at which the current left in Q15 is read."""

_SAVES = (
    "save gate_out drv_out out_gate g_out mid vout_s vout dut supply guard @r110[i] vcab#branch"
)
"""What a run of this bench keeps, beside the currents of the suppressor."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One opening of the switch.

    Attributes:
        key: Short name, part of the keys of its figures.
        label: What the case is, as the report shows it.
        volts: Voltage of the supply node.
        cable: Inductance of the cable to the device, H.
        leads: Inductance of supply leads in front of the supply node, H.
        farads: Capacitance at the device, F.
        slow: The corner in which the gate falls latest.
        released: The pin of the controller is released instead of driven low.
    """

    key: str
    label: str
    volts: float = 5.0
    cable: float = 0.0
    leads: float = 0.0
    farads: float = 0.0
    slow: bool = False
    released: bool = False


_CASES = (
    _Case("plain", "5 V, no inductance"),
    _Case("cable1", "5 V, 1 uH of cable", cable=1e-6),
    _Case("cable3", "5 V, 3 uH of cable", cable=3e-6),
    _Case(
        "leads",
        "5 V, 3 uH of cable, 2 uH of supply leads, 10 uF at the device",
        cable=3e-6,
        leads=2e-6,
        farads=10e-6,
    ),
    _Case("low", "0.8 V, no inductance", volts=0.8),
    _Case("low3", "0.8 V, 3 uH of cable", volts=0.8, cable=3e-6),
    _Case("slow", "5 V, slow corner", slow=True),
    _Case("lowslow", "0.8 V, slow corner", volts=0.8, slow=True),
    _Case("released", "5 V, pin released by a reset", released=True),
)
"""The openings that are run."""


def _corner(ctx: Context, slow: bool) -> tuple[dict[str, float], dict[str, PartModel]]:
    """Scales and models of the corner in which the gate falls latest."""
    if not slow:
        return {}, {}
    spread = tolerance.tolerances(ctx.netlist, ("R116", "C74"), {"C": _C74_TOLERANCE})
    scales = tolerance.corner_scales(spread, {"R116": 1, "C74": 1})
    diode = PartModel(
        kind="device",
        letter="D",
        name="BAV199_HI",
        units=(("1", "3"), ("3", "2")),
        library="diodes.lib",
        origin="written here",
    )
    models: dict[str, PartModel] = {"D20": diode}
    if ctx.tier == OPEN_TIER:
        models.update({"Q15": common.transistor("LO"), "Q16": common.transistor("LO")})
    return scales, models


def _command(released: bool) -> str:
    """GATE_OUT falls: driven low, or left to R93 when a reset releases the pin."""
    if not released:
        return common.command((0.0, True), (_EVENT, False))
    return "\n".join(
        [
            "* GATE_OUT: the pin drives high until a reset releases it; R93 pulls it down",
            f"Vcmd cmd 0 {common.LOGIC_VOLTS:g}",
            f"Rpad cmd pad {common.PAD_OHMS:g}",
            f"Vrelease rel 0 PWL(0 1 {_EVENT:g} 1 {_EVENT + 1e-9:g} 0)",
            "Spin pad gate_out rel 0 OUTPUT_PIN",
            ".model OUTPUT_PIN SW(vt=0.5 vh=0.1 ron=1m roff=1e12)",
            f"Cpin gate_out 0 {_PIN_FARADS:g}",
        ]
    )


def _residual_save(ctx: Context) -> str:
    """The drain current of Q15, which only the transistor model written here gives."""
    return "@mq15[id]" if ctx.tier == OPEN_TIER else ""


def _load(case: _Case) -> str:
    ohms = case.volts / _LOAD_AMPS - common.CABLE_OHMS - _PATH_OHMS
    lines = ["* device under test: a resistor that takes 1 A", f"Rload dut 0 {ohms:g}"]
    if case.farads > 0.0:
        lines += [f"Cdut dut dutc {case.farads:g}", f"Resr dutc 0 {common.ESR_OHMS:g}"]
    return "\n".join(lines)


def _deck(ctx: Context, case: _Case, stop: float, step: str = "5n", most: str = "10n") -> str:
    scales, models = _corner(ctx, case.slow)
    circuit = ctx.circuit(
        common.path_refs(ctx.netlist),
        common.ALIASES,
        {**common.path_models(ctx), **models},
        scales,
    )
    ramp = common.QUICK_POWER_UP
    return ctx.deck(
        f"Output switched off under load: {case.label}",
        circuit,
        common.rails(ramp=ramp),
        common.controller(3, ramp=ramp),
        _command(case.released),
        common.source(case.volts, henries=case.leads, ramp=ramp),
        common.cable(henries=case.cable),
        _load(case),
        common.closed_start(),
        control=[
            f"{_SAVES} {common.suppressor_saves(ctx)} {_residual_save(ctx)}",
            f"tran {step} {stop:.9g} 0 {most} uic",
        ],
        options=(*common.buffer_options(ctx), "method=gear"),
    )


@dataclass(frozen=True, slots=True)
class _Reading:
    """What one opening shows.

    Attributes:
        command: Instant at which GATE_OUT passes half its level.
        gate: Time from the command to the gate node below 2 V.
        tenth: Time from the command after which the pair carries less than 10 %.
        hundredth: The same for 1 %.
        terminal_low: Lowest voltage of the terminal after the command.
        terminal_high: Highest voltage of the terminal after the command.
        node_high: Highest voltage of the node after the shunts.
        supply_high: Highest voltage of the supply node.
        diode_peak: Largest forward current of the suppressor.
        first: Energy in Q15 from the command on.
        second: Energy in Q16 from the command on.
        drain_first: Largest drain-source voltage of Q15.
        drain_second: Largest drain-source voltage of Q16, either sign.
        gate_source: Largest gate-source voltage of the pair, either sign.
        guard_error: Largest distance of the guard from the node after the shunts.
    """

    command: float
    gate: float
    tenth: float
    hundredth: float
    terminal_low: float
    terminal_high: float
    node_high: float
    supply_high: float
    diode_peak: float
    first: float
    second: float
    drain_first: float
    drain_second: float
    gate_source: float
    guard_error: float


def _read(ctx: Context, run: RunResult) -> _Reading:
    time = run.real("time")
    end = float(time[-1])
    command = measure.first_crossing(
        time, run.real("gate_out"), 0.5 * common.LOGIC_VOLTS, rising=False, after=_EVENT - 1e-6
    )
    pair = common.pair_current(ctx, run)
    before = measure.value_at(time, pair, command - 1e-6)
    mid, node, terminal = run.real("mid"), run.real("vout_s"), run.real("vout")
    diode = common.suppressor_current(ctx, run)

    def span(values: np.ndarray) -> tuple[float, float]:
        return measure.extremes(time, values, command, end)

    return _Reading(
        command=command,
        gate=measure.first_crossing(time, run.real("out_gate"), 2.0, False, command) - command,
        tenth=measure.settling_time(time, pair, 0.0, 0.1 * before, command),
        hundredth=measure.settling_time(time, pair, 0.0, 0.01 * before, command),
        terminal_low=span(terminal)[0],
        terminal_high=span(terminal)[1],
        node_high=span(node)[1],
        supply_high=span(run.real("supply"))[1],
        diode_peak=span(diode)[1],
        first=common.energy(time, (node - mid) * pair, command, end),
        second=common.energy(time, (mid - terminal) * pair, command, end),
        drain_first=span(node - mid)[1],
        drain_second=float(np.max(np.abs(span(terminal - mid)))),
        gate_source=float(np.max(np.abs(span(run.real("g_out") - mid)))),
        guard_error=float(np.max(np.abs(span(run.real("guard") - node)))),
    )


def _fast_figures(case: _Case, reading: _Reading) -> list[Figure]:
    return [
        Figure(
            f"{case.key}_gate",
            f"{case.label}: command to the gate node below 2 V",
            reading.gate,
            "s",
            high=_GATE_LIMIT,
            source="section 4.2, D-71 and rule F-8: below 2 V within 7 us",
        ),
        Figure(
            f"{case.key}_tenth",
            f"{case.label}: command to less than 10 % of the current in the pair",
            reading.tenth,
            "s",
        ),
        Figure(
            f"{case.key}_terminal_low",
            f"{case.label}: lowest voltage at the terminal",
            reading.terminal_low,
            "V",
        ),
        Figure(
            f"{case.key}_node_high",
            f"{case.label}: highest voltage at the node after the shunts",
            reading.node_high,
            "V",
            high=11.5,
            source="section 4.3: the ladder stays below 11.5 V, under +12 V_A",
        ),
        Figure(
            f"{case.key}_diode",
            f"{case.label}: largest forward current in the suppressor D21",
            reading.diode_peak,
            "A",
            high=common.SURGE_AMPS,
            source="section 4.9: surge rating 50 A (datasheet value)",
        ),
    ]


def _decay_figures(ctx: Context, figures: list[Figure]) -> tuple[RunResult, RunResult | None]:
    """The long runs: the gate after the opening, with typical and low thresholds."""
    case = _Case("rest", "5 V, resistor of 5 ohm")
    stop = _EVENT + 0.3
    typical = ctx.run("rest", _deck(ctx, case, stop, step="20u", most="20u"))
    time = typical.real("time")
    gate = typical.real("out_gate")
    command = measure.first_crossing(
        time, typical.real("gate_out"), 0.5 * common.LOGIC_VOLTS, False, _EVENT - 1e-6
    )
    early, late = command + 10e-3, command + 60e-3
    constant = (late - early) / float(
        np.log(measure.value_at(time, gate, early) / measure.value_at(time, gate, late))
    )
    figures += [
        Figure(
            "rest_level",
            "Gate node 100 us after the command: the diode drop it rests at",
            measure.value_at(time, gate, command + 100e-6),
            "V",
            low=0.3,
            high=0.9,
            source="section 4.2: the gate rests at a diode drop",
        ),
        Figure(
            "rest_constant",
            "Time constant of the gate node from 10 ms to 60 ms after the command",
            constant,
            "s",
            expected=31e-3,
            low=26e-3,
            high=36e-3,
            source="section 4.2 and rule F-36: 31 ms; limit set here, 15 % around it",
        ),
        Figure(
            "rest_200ms",
            "Gate node 200 ms after the command",
            measure.value_at(time, gate, command + 0.2),
            "V",
            high=0.11,
            source="rule F-36: readings 200 ms after GATE_OUT fell; limit set here, a "
            "tenth of the lowest threshold of 1.1 V",
        ),
    ]
    if ctx.tier != OPEN_TIER:
        return typical, None
    residual = typical.real("@mq15[id]")
    for delay in _RESIDUAL_DELAYS:
        figures.append(
            Figure(
                f"rest_current_{delay * 1e6:g}us",
                f"Typical transistors: current through Q15 {delay * 1e3:g} ms after the command",
                measure.value_at(time, residual, command + delay),
                "A",
            )
        )
    weak = {"Q15": common.transistor("LO"), "Q16": common.transistor("LO")}
    circuit = ctx.circuit(common.path_refs(ctx.netlist), common.ALIASES, weak)
    ramp = common.QUICK_POWER_UP
    deck = ctx.deck(
        "Output switched off, transistors with the lowest threshold",
        circuit,
        common.rails(ramp=ramp),
        common.controller(3, ramp=ramp),
        _command(False),
        common.source(case.volts, ramp=ramp),
        common.cable(),
        _load(case),
        common.closed_start(),
        control=[
            f"{_SAVES} {common.suppressor_saves(ctx)} {_residual_save(ctx)}",
            f"tran 20u {stop:.9g} 0 20u uic",
        ],
        options=("method=gear",),
    )
    low = ctx.run("rest-low-threshold", deck, keep=False)
    low_time = low.real("time")
    for delay in _RESIDUAL_DELAYS:
        figures.append(
            Figure(
                f"rest_low_current_{delay * 1e6:g}us",
                f"Lowest threshold: current through Q15 {delay * 1e3:g} ms after the command",
                measure.value_at(low_time, low.real("@mq15[id]"), command + delay),
                "A",
            )
        )
    return typical, low


@bench(
    "output_stage",
    "turn-off",
    "The output switch opens under load: gate, current, terminal and suppressor",
    "section 4.2 (output switch, D-71), section 4.9 (VOUT, D-70), rules F-8, F-23 and F-36",
)
def turn_off(ctx: Context) -> Outcome:
    """The output is switched off while 1 A flows into a resistor, in range 3.

    The gate is discharged through one diode of D20 and R116 into the gate
    driver. The run is repeated with inductance in the cable to the device,
    with a capacitor at the device and inductance in supply leads, at 0.8 V,
    in the corner in which the gate falls latest (R116 and C74 at their
    upper limits, D20 with the highest forward voltage, transistors with
    the lowest threshold), and with the pin of the controller released by a
    reset instead of driven low. Each run gives the time to a gate node
    below 2 V, the time after which the pair carries less than a tenth of
    its current, and what the terminal, the node after the shunts and the
    suppressor see. A long run follows the gate after the opening: the
    level it rests at, the time constant with which it leaves it, and the
    current that the pair still passes into a device that holds the
    terminal at 0 V.
    """
    stop = _EVENT + _WINDOW
    runs = ctx.run_many({case.key: _deck(ctx, case, stop) for case in _CASES})
    for case in _CASES[:1] + _CASES[3:4]:
        ctx.kept[f"{ctx.prefix}.{case.key}.cir"] = _deck(ctx, case, stop)
    readings = {case.key: _read(ctx, runs[case.key]) for case in _CASES}
    figures: list[Figure] = []
    for case in _CASES:
        figures += _fast_figures(case, readings[case.key])
    worst = readings.values()
    figures += [
        Figure(
            "pair_energy",
            "Largest energy in Q15 during an opening",
            max(reading.first for reading in worst),
            "J",
            high=common.AVALANCHE_JOULES,
            source="TI SLPS515A, page 1: 39 mJ of avalanche energy, taken as the scale",
        ),
        Figure(
            "pair_energy_second",
            "Largest energy in Q16 during an opening",
            max(reading.second for reading in worst),
            "J",
            high=common.AVALANCHE_JOULES,
            source="TI SLPS515A, page 1: 39 mJ of avalanche energy, taken as the scale",
        ),
        Figure(
            "drain_first",
            "Largest drain-source voltage of Q15",
            max(reading.drain_first for reading in worst),
            "V",
            high=common.TRANSISTOR_VOLTS,
            source="section 4.9: the transistors are rated 30 V (datasheet value)",
        ),
        Figure(
            "drain_second",
            "Largest drain-source voltage of Q16, either sign",
            max(reading.drain_second for reading in worst),
            "V",
            high=common.TRANSISTOR_VOLTS,
            source="section 4.9: the transistors are rated 30 V (datasheet value)",
        ),
        Figure(
            "gate_source",
            "Largest gate-source voltage of the pair, either sign",
            max(reading.gate_source for reading in worst),
            "V",
            high=common.GATE_VOLTS,
            source="TI SLPS515A, page 1: gate-source voltage 20 V at most",
        ),
        Figure(
            "terminal_high",
            "Highest voltage at the terminal after an opening",
            max(reading.terminal_high for reading in worst),
            "V",
            high=15.0,
            source="section 4.9: stand-off voltage of the suppressor D21",
        ),
        Figure(
            "guard_error",
            "Largest distance of the guard from the node after the shunts",
            max(reading.guard_error for reading in worst),
            "V",
        ),
    ]
    typical, low = _decay_figures(ctx, figures)

    def panel_traces(key: str, start: float, end: float) -> tuple[list[Trace], float]:
        run, reading = runs[key], readings[key]
        time = run.real("time")
        micro = (time - reading.command) * 1e6
        shown = (micro >= start) & (micro <= end)
        pair = common.pair_current(ctx, run)
        diode = common.suppressor_current(ctx, run)
        traces = [
            Trace(micro[shown], run.real("gate_out")[shown], "GATE_OUT", 0),
            Trace(micro[shown], run.real("drv_out")[shown], "driver output", 0),
            Trace(micro[shown], run.real("out_gate")[shown], "gate node, TP37", 0),
            Trace(micro[shown], run.real("mid")[shown], "common source", 0),
            Trace(micro[shown], run.real("vout")[shown], "terminal", 1),
            Trace(micro[shown], run.real("dut")[shown], "device", 1, "--"),
            Trace(micro[shown], run.real("vout_s")[shown], "node after the shunts", 1),
            Trace(micro[shown], run.real("supply")[shown], "supply node", 1, "--"),
            Trace(micro[shown], run.real("guard")[shown], "guard", 1, ":"),
            Trace(micro[shown], pair[shown], "output pair", 2),
            Trace(micro[shown], run.real("vcab#branch")[shown], "cable", 2, "--"),
            Trace(micro[shown], diode[shown], "suppressor D21, forward", 2),
        ]
        return traces, reading.command

    panels = (
        Panel("Gate drive (V)", marks=((2.0, "2 V"),)),
        Panel("Path (V)"),
        Panel("Current (A)"),
    )
    plain = Graph(
        name="plain",
        title="Output switched off at 5 V and 1 A, no inductance",
        xlabel="Time after the command (us)",
        panels=panels,
        traces=tuple(panel_traces("plain", -2.0, 20.0)[0]),
        xmarks=((7.0, "7 us"),),
    )
    leads = Graph(
        name="leads",
        title="Switched off at 5 V and 1 A: 3 uH of cable, 2 uH of supply leads, 10 uF",
        xlabel="Time after the command (us)",
        panels=panels,
        traces=tuple(panel_traces("leads", -2.0, 40.0)[0]),
    )
    low_voltage = Graph(
        name="low-voltage",
        title="Output switched off at 0.8 V and 1 A, 3 uH of cable",
        xlabel="Time after the command (us)",
        panels=panels,
        traces=tuple(panel_traces("low3", -2.0, 30.0)[0]),
        xmarks=((7.0, "7 us"),),
    )
    time = typical.real("time")
    milli = (time - _EVENT) * 1e3
    after = milli > 0.02
    rest_traces = [
        Trace(milli[after], typical.real("out_gate")[after], "gate node, TP37", 0),
        Trace(milli[after], typical.real("mid")[after], "common source", 0),
    ]
    if low is not None:
        low_milli = (low.real("time") - _EVENT) * 1e3
        part = low_milli > 0.02
        rest_traces += [
            Trace(
                milli[after],
                np.abs(typical.real("@mq15[id]")[after]) + 1e-12,
                "typical transistors",
                1,
            ),
            Trace(
                low_milli[part],
                np.abs(low.real("@mq15[id]")[part]) + 1e-12,
                "lowest threshold",
                1,
            ),
        ]
    else:
        rest_traces.append(
            Trace(milli[after], np.abs(typical.real("vcab#branch")[after]) + 1e-12, "cable", 1)
        )
    rest = Graph(
        name="rest",
        title="After the opening: the gate leaves its diode drop through R117",
        xlabel="Time after the command (ms)",
        panels=(
            Panel("Gate node and common source (V)"),
            Panel("Current through Q15 (A)", log=True, marks=((1e-6, "1 uA"),)),
        ),
        traces=tuple(rest_traces),
        logx=True,
        xmarks=((200.0, "200 ms"),),
    )
    notes = (
        "An ideal source behind 10 mohm stands for the source meter and its closed mode "
        "pair. In the case with supply leads their inductance sits between that source "
        "and the supply node; the ampere pair and the suppressor of the VIN terminal, "
        "which bound that node at a trip, belong to the path switching block and are "
        "not in this circuit.",
        "Every run starts with all voltages at zero and its sources rising in 20 us. A "
        "switch ties the gate node to 12 V until 60 us, because through R117 alone the "
        "gate needs a quarter of a second; the command comes at 200 us.",
        "The suppressor carries the cable current only while the terminal is below "
        "ground. With a resistor as device and little inductance the pair itself "
        "brings the current down as a follower, and the suppressor stays off.",
        "The forward curve of the suppressor is an assumption (0.75 V at 0.1 A, "
        "0.03 ohm); its datasheet has none.",
        "The current that the pair passes after the opening comes from the slope of "
        "the transistor model below its threshold, which is a fit between 250 uA and "
        "amperes. The figures show that it is microamperes for milliseconds; no value "
        "of nanoamperes may be taken from them, and none is quoted at 200 ms.",
        "With the pin released the line falls through R93 into 20 pF, which is an "
        "assumption for the pad, the track and the input of the side register.",
    )
    return Outcome(tuple(figures), (plain, leads, low_voltage, rest), notes)
