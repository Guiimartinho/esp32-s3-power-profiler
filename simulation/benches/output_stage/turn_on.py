"""The slow closing of the output switch: gate ramp, output ramp and in-rush."""

from __future__ import annotations

import numpy as np

from benches import frontend
from benches.output_stage import common
from circuit_sim import measure, tolerance
from circuit_sim.bench import OPEN_TIER, Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_COMMAND_AT = 0.1
"""Instant at which GATE_OUT rises. Every run starts with all voltages at zero
and its sources rising; the rise of the supply node lifts the gate node by
0.1 V to 0.2 V through the drain of Q15, and that charge has left through
R117 when the command comes."""

_LONG = _COMMAND_AT + 0.3
"""End of the runs that follow the gate to its rest: 300 ms after the command."""

_SHORT = _COMMAND_AT + 0.08
"""End of the runs of a sweep: 80 ms after the command."""

_CAPACITANCES = (100e-6, 220e-6, 470e-6, 1000e-6, 1500e-6, 2200e-6, 2700e-6, 3300e-6, 3900e-6)
"""Capacitances of the device under test in the sweep."""

_RAIL_SPREAD = 0.6
"""Half the window of +12 V_A inside which the rails count as valid (rule F-12)."""

_C74_TOLERANCE = 0.05
"""Tolerance of C74: its value string gives none; 5 % is the grade of its part number."""

_TRIP_TIME = 12e-6
"""Qualification time of the over-current trip (rule F-18)."""

_SOLVER = ("method=gear",)
"""Integration method of the long runs. The trapezoidal rule rings between the
10 ohm of R120 and the gate capacitance once the step is longer than their
35 ns, and the current in R120 is then noise."""

_SAVES = (
    "save gate_out drv_out out_gate g_out mid vout_s vout dut supply guard "
    "@r110[i] vcab#branch @r120[i]"
)
"""What a run of this bench keeps."""


def _corner(ctx: Context, sign: int) -> tuple[dict[str, float], dict[str, PartModel], float]:
    """Scales, transistor models and rail of a corner: +1 fast, -1 slow, 0 nominal."""
    if sign == 0:
        return {}, {}, 12.0
    spread = tolerance.tolerances(ctx.netlist, ("R117", "C74"), {"C": _C74_TOLERANCE})
    scales = tolerance.corner_scales(spread, {"R117": -sign, "C74": -sign})
    models: dict[str, PartModel] = {}
    if ctx.tier == OPEN_TIER:
        variant = common.transistor("LO" if sign > 0 else "HI")
        models = {"Q15": variant, "Q16": variant}
    return scales, models, 12.0 + sign * _RAIL_SPREAD


def _deck(
    ctx: Context,
    farads: float,
    volts: float = 5.0,
    sign: int = 0,
    stop: float = _SHORT,
) -> str:
    """The output is switched on into a capacitor that starts empty."""
    scales, models, rail = _corner(ctx, sign)
    circuit = ctx.circuit(
        common.path_refs(ctx.netlist),
        common.ALIASES,
        {**common.path_models(ctx), **models},
        scales,
    )
    return ctx.deck(
        f"Output switched on into {farads * 1e6:g} uF at {volts:g} V",
        circuit,
        common.rails(p12=rail, ramp=common.POWER_UP),
        common.controller(3, ramp=common.POWER_UP),
        common.command((0.0, False), (_COMMAND_AT, True)),
        common.source(volts, ramp=common.POWER_UP),
        common.cable(),
        common.capacitor_load(farads),
        control=[_SAVES, f"tran 20u {stop:.9g} 0 20u uic"],
        options=(*common.buffer_options(ctx), *_SOLVER),
    )


def _fault_deck(ctx: Context, load: str, stop: float) -> str:
    """The output is switched on by the sequencer model, with the trip armed."""
    circuit = ctx.circuit(common.path_refs(ctx.netlist), common.ALIASES, common.path_models(ctx))
    request = (
        "* the request to close the output switch\n"
        f"Vouton seq_out_on 0 PWL(0 0 {_COMMAND_AT:g} 0 {_COMMAND_AT + 2e-8:g} "
        f"{common.LOGIC_VOLTS:g})\n"
    )
    return ctx.deck(
        "Output switched on with the trip armed",
        circuit,
        common.rails(ramp=common.POWER_UP),
        common.protection(_TRIP_TIME),
        request,
        common.source(5.0, ramp=common.POWER_UP),
        common.cable(henries=1e-6),
        load,
        control=[_SAVES + " xseq.trip", f"tran 1u {stop:.9g} 0 5u uic"],
        options=(*common.buffer_options(ctx), *_SOLVER),
        libraries=frontend.SEQUENCER_LIBRARIES,
    )


def _after(result: RunResult, name: str, level: float, rising: bool = True) -> float:
    """Time from the command to the first crossing of a level."""
    time = result.real("time")
    crossed = measure.first_crossing(time, result.real(name), level, rising, _COMMAND_AT)
    return crossed - _COMMAND_AT


def _slopes(result: RunResult, volts: float) -> tuple[float, float]:
    """Largest slope of the voltage at the device and its slope at 98 %."""
    time, dut = result.real("time"), result.real("dut")
    grid = np.arange(_COMMAND_AT, float(time[-1]), 50e-6)
    rate = common.slope(grid, np.interp(grid, time, dut))
    late = _COMMAND_AT + _after(result, "dut", 0.98 * volts)
    return float(np.max(rate)), float(np.interp(late, grid, rate))


def _peak(result: RunResult) -> float:
    """Largest current in the 0.1 ohm shunt after the command."""
    time = result.real("time")
    return measure.extremes(time, result.real("@r110[i]"), _COMMAND_AT, float(time[-1]))[1]


def _largest(peaks: list[float], level: float) -> float:
    """The capacitance at which the in-rush reaches a level, between the points run."""
    return float(np.interp(level, peaks, _CAPACITANCES))


@bench(
    "output_stage",
    "turn-on",
    "The output switch closes: gate ramp, output ramp and in-rush into a capacitor",
    "section 4.2 (output switch, D-71), section 4.4 (trip at power on), rules F-19, F-24 "
    "and F-36, section 10.6 (dissipation of Q15)",
)
def turn_on(ctx: Context) -> Outcome:
    """The output is switched on into a capacitor that starts empty, behind the ladder in range 3.

    The pair closes as a source follower behind R117 and C74, so the output
    follows the gate and the capacitor of the device takes a current that
    the slope of the gate sets. The capacitance is swept and the largest
    current in the 0.1 ohm shunt is compared with the over-current level;
    the sweep is repeated for the corner in which the in-rush is highest:
    R117 and C74 at their lower limits, +12 V_A at the upper end of its
    window and both transistors at their lowest threshold. A long run
    follows the gate to its rest and reads the current that charges it,
    which reaches the device without passing the shunts. Two runs with the
    model of the sequencer show a start into a short circuit and a start
    into a capacitor that is too large.
    """
    nominal = ctx.run("5v-2200u", _deck(ctx, 2200e-6, stop=_LONG))
    decks = {f"c{farads * 1e6:g}": _deck(ctx, farads) for farads in _CAPACITANCES}
    decks.update({f"f{farads * 1e6:g}": _deck(ctx, farads, sign=1) for farads in _CAPACITANCES})
    decks["slow"] = _deck(ctx, 2200e-6, sign=-1)
    decks["low-100u"] = _deck(ctx, 100e-6, volts=0.8)
    decks["low-2200u"] = _deck(ctx, 2200e-6, volts=0.8)
    decks["low-fast"] = _deck(ctx, 100e-6, volts=0.8, sign=1)
    runs = ctx.run_many(decks)
    light = runs["c100"]
    peaks = [_peak(runs[f"c{farads * 1e6:g}"]) for farads in _CAPACITANCES]
    fast = [_peak(runs[f"f{farads * 1e6:g}"]) for farads in _CAPACITANCES]
    steep, late = _slopes(light, 5.0)
    time = nominal.real("time")
    cable = nominal.real("vcab#branch")
    power = (nominal.real("vout_s") - nominal.real("mid")) * cable
    gate_amps = nominal.real("@r120[i]")
    figures = [
        Figure(
            "start_5v",
            "5 V, 100 uF: command to 10 % of the voltage at the device",
            _after(light, "dut", 0.5),
            "s",
            low=6e-3,
            high=7e-3,
            source="section 4.2 and rule F-24: starts to rise 6 ms to 7 ms after the request",
        ),
        Figure(
            "first_5v",
            "5 V, 100 uF: command to the first 50 mV at the device",
            _after(light, "dut", 0.05),
            "s",
        ),
        Figure(
            "start_0v8",
            "0.8 V, 100 uF: command to 10 % of the voltage at the device",
            _after(runs["low-100u"], "dut", 0.08),
            "s",
            low=6e-3,
            high=7e-3,
            source="section 4.2 and rule F-24: starts to rise 6 ms to 7 ms after the request",
        ),
        Figure(
            "start_earliest",
            "0.8 V, 100 uF, fast corner: command to the first 50 mV at the device",
            _after(runs["low-fast"], "dut", 0.05),
            "s",
        ),
        Figure(
            "start_latest",
            "5 V, 2200 uF, slow corner: command to 10 % of the voltage at the device",
            _after(runs["slow"], "dut", 0.5),
            "s",
        ),
        Figure(
            "slope_first",
            "5 V, 100 uF: largest slope of the output",
            steep,
            "V/s",
            expected=440.0,
            low=396.0,
            high=484.0,
            source="section 4.2: 0.44 V/ms; limit set here, 10 % around it",
        ),
        Figure(
            "slope_late",
            "5 V, 100 uF: slope of the output at 98 % of 5 V",
            late,
            "V/s",
            expected=210.0,
            low=180.0,
            high=240.0,
            source="section 4.2: 0.21 V/ms near 5 V; limit set here, 15 % around it",
        ),
        Figure(
            "ninety_100u",
            "5 V, 100 uF: command to 90 % of the voltage at the device",
            _after(light, "dut", 4.5),
            "s",
            expected=20e-3,
            low=17e-3,
            high=23e-3,
            source="section 4.2 and D-71: about 20 ms; limit set here, 15 % around it",
        ),
        Figure(
            "ninety_2200u",
            "5 V, 2200 uF: command to 90 % of the voltage at the device",
            _after(nominal, "dut", 4.5),
            "s",
            expected=20e-3,
            low=17e-3,
            high=23e-3,
            source="section 4.2 and D-71: about 20 ms; limit set here, 15 % around it",
        ),
        Figure(
            "ninety_slow",
            "5 V, 2200 uF, slow corner: command to 90 % of the voltage at the device",
            _after(runs["slow"], "dut", 4.5),
            "s",
            high=50e-3,
            source="rule F-24: the output counts as on 50 ms after GATE_OUT",
        ),
        Figure(
            "inrush_1000u",
            "5 V, 1000 uF: largest current in the 0.1 ohm shunt",
            peaks[_CAPACITANCES.index(1000e-6)],
            "A",
            expected=0.39,
            high=common.TRIP_AMPS_LOW,
            source="section 4.2: 0.39 A; limit: lowest trip level, section 4.4",
        ),
        Figure(
            "inrush_2200u",
            "5 V, 2200 uF: largest current in the 0.1 ohm shunt",
            peaks[_CAPACITANCES.index(2200e-6)],
            "A",
            expected=0.85,
            high=common.TRIP_AMPS_LOW,
            source="section 4.2: 0.85 A; limit: lowest trip level, section 4.4",
        ),
        Figure(
            "inrush_2200u_fast",
            "5 V, 2200 uF, fast corner: largest current in the 0.1 ohm shunt",
            fast[_CAPACITANCES.index(2200e-6)],
            "A",
            high=common.TRIP_AMPS_LOW,
            source="sections 4.2 and 4.4: about 2200 uF starts without a trip",
        ),
        Figure(
            "inrush_0v8",
            "0.8 V, 2200 uF: largest current in the 0.1 ohm shunt",
            _peak(runs["low-2200u"]),
            "A",
            high=common.TRIP_AMPS_LOW,
            source="lowest trip level, section 4.4",
        ),
        Figure(
            "largest_nominal",
            "Largest capacitance below the trip level of 1.15 A, nominal parts",
            _largest(peaks, common.TRIP_AMPS),
            "F",
            expected=2200e-6,
            low=2200e-6,
            source="sections 4.2 and 4.4, rule F-19: about 2200 uF nominal",
        ),
        Figure(
            "largest_fast",
            "Largest capacitance below the lowest trip level of 1.114 A, fast corner",
            _largest(fast, common.TRIP_AMPS_LOW),
            "F",
            expected=2160e-6,
            low=2160e-6,
            source="sections 4.2 and 11: 1800 uF with a capacitor 20 % high, which is 2160 uF",
        ),
        Figure(
            "pair_energy",
            "5 V, 2200 uF: energy in the transistor on the ladder side, Q15",
            common.energy(time, power, _COMMAND_AT, _COMMAND_AT + 0.08),
            "J",
            expected=25e-3,
            low=20e-3,
            high=30e-3,
            source="section 10.6: about 25 mJ; limit set here, 20 % around it",
        ),
        Figure(
            "pair_power",
            "5 V, 2200 uF: largest power in Q15",
            measure.extremes(time, power, _COMMAND_AT, float(time[-1]))[1],
            "W",
            expected=3.5,
            low=2.8,
            high=4.2,
            source="section 10.6: about 3.5 W; limit set here, 20 % around it",
        ),
    ]
    for delay, expected in ((30e-3, 0.5e-6), (50e-3, 0.3e-6), (100e-3, 60e-9), (200e-3, 4e-9)):
        figures.append(
            Figure(
                f"gate_current_{delay * 1e3:g}ms",
                f"Current into the two gates {delay * 1e3:g} ms after the command",
                measure.value_at(time, gate_amps, _COMMAND_AT + delay),
                "A",
                expected=expected,
                low=0.5 * expected,
                high=2.0 * expected,
                source="sections 4.2 and 4.10; limit set here, a factor of two around it",
            )
        )
    figures.append(
        Figure(
            "gate_current_300ms",
            "Current into the two gates 300 ms after the command",
            measure.value_at(time, gate_amps, _COMMAND_AT + 0.29999),
            "A",
            high=1.9e-9,
            source="rule F-36: zero with the output on 300 ms after GATE_OUT; one code of "
            "range 0 is 1.9 nA (section 4.3)",
        )
    )
    shorted = ctx.run("into-short", _fault_deck(ctx, "Rshort dut 0 10m", _COMMAND_AT + 11e-3))
    heavy = ctx.run(
        "into-4700u", _fault_deck(ctx, common.capacitor_load(4700e-6), _COMMAND_AT + 24e-3)
    )
    for key, run, text in (
        ("short", shorted, "Start into a short circuit"),
        ("heavy", heavy, "Start into 4700 uF"),
    ):
        run_time = run.real("time")
        current = run.real("@r110[i]")
        tripped = float(run.real("xseq.trip")[-1])
        fell = _after(run, "gate_out", 0.5 * common.LOGIC_VOLTS, rising=False)
        loss = (run.real("vout_s") - run.real("mid")) * run.real("vcab#branch")
        figures += [
            Figure(
                f"{key}_tripped",
                f"{text}: the trip is latched at the end of the run (1 is yes)",
                tripped,
                "",
                low=0.5,
                source="rules F-18 and F-19",
            ),
            Figure(f"{key}_trip_time", f"{text}: command to the trip", fell, "s"),
            Figure(
                f"{key}_peak",
                f"{text}: largest current in the 0.1 ohm shunt",
                measure.extremes(run_time, current, _COMMAND_AT, float(run_time[-1]))[1],
                "A",
            ),
            Figure(
                f"{key}_energy",
                f"{text}: energy in Q15",
                common.energy(run_time, loss, _COMMAND_AT, float(run_time[-1])),
                "J",
                high=common.AVALANCHE_JOULES,
                source="TI SLPS515A, page 1: 39 mJ of avalanche energy, taken as the scale",
            ),
            Figure(
                f"{key}_after",
                f"{text}: current in the shunt 1 ms after the trip",
                abs(measure.value_at(run_time, current, _COMMAND_AT + fell + 1e-3)),
                "A",
                high=1e-3,
                source="rule F-19: GATE_OUT stays low after a trip",
            ),
        ]
    milli = (time - _COMMAND_AT) * 1e3
    shown = (milli >= -1.0) & (milli <= 60.0)
    sweep_traces: list[Trace] = []
    for farads in (100e-6, 1000e-6, 2200e-6, 3300e-6):
        run = runs[f"c{farads * 1e6:g}"]
        axis = (run.real("time") - _COMMAND_AT) * 1e3
        part = (axis >= -1.0) & (axis <= 60.0)
        label = f"{farads * 1e6:g} uF"
        sweep_traces.append(Trace(axis[part], run.real("dut")[part], label, 1))
        sweep_traces.append(Trace(axis[part], run.real("@r110[i]")[part], label, 2))
    waveforms = Graph(
        name="waveforms",
        title="Output switched on at 5 V: gate, output and in-rush",
        xlabel="Time after the command (ms)",
        panels=(
            Panel("2200 uF: gate and source (V)"),
            Panel("Voltage at the device (V)"),
            Panel("Current in the 0.1 ohm shunt (A)", marks=((common.TRIP_AMPS, "trip 1.15 A"),)),
        ),
        traces=(
            Trace(milli[shown], nominal.real("gate_out")[shown], "GATE_OUT", 0),
            Trace(milli[shown], nominal.real("out_gate")[shown], "gate node, TP37", 0),
            Trace(milli[shown], nominal.real("mid")[shown], "common source", 0),
            Trace(milli[shown], nominal.real("vout_s")[shown], "node after the shunts", 0, "--"),
            *sweep_traces,
        ),
    )
    micro_farads = np.asarray(_CAPACITANCES) * 1e6
    sweep = Graph(
        name="inrush",
        title="In-rush against the capacitance of the device, 5 V",
        xlabel="Capacitance of the device (uF)",
        panels=(
            Panel(
                "Largest current in the shunt (A)",
                marks=((common.TRIP_AMPS, "trip 1.15 A"), (common.TRIP_AMPS_LOW, "lowest 1.114 A")),
            ),
        ),
        traces=(
            Trace(micro_farads, np.asarray(peaks), "nominal", 0),
            Trace(micro_farads, np.asarray(fast), "fast corner", 0, "--"),
        ),
        xmarks=((2200.0, "2200 uF"),),
    )
    tail = milli >= 5.0
    gate = Graph(
        name="gate-current",
        title="Current that charges the gates after the switch has closed, 5 V",
        xlabel="Time after the command (ms)",
        panels=(
            Panel(
                "Current into the two gates (A)",
                log=True,
                marks=((1e-6, "1 uA"), (1.9e-9, "one code of range 0")),
            ),
            Panel("Gate node, TP37 (V)"),
        ),
        traces=(
            Trace(milli[tail], np.abs(gate_amps[tail]) + 1e-12, "", 0),
            Trace(milli[tail], nominal.real("out_gate")[tail], "", 1),
        ),
    )
    fault_time = (shorted.real("time") - _COMMAND_AT) * 1e3
    heavy_time = (heavy.real("time") - _COMMAND_AT) * 1e3
    near_short = fault_time >= -1.0
    near_heavy = heavy_time >= -1.0
    faults = Graph(
        name="faults",
        title="Starts that end in a trip: a short circuit and 4700 uF",
        xlabel="Time after the command (ms)",
        panels=(
            Panel("Gate node, TP37 (V)"),
            Panel("Current in the 0.1 ohm shunt (A)", marks=((common.TRIP_AMPS, "trip 1.15 A"),)),
            Panel("Voltage at the device (V)"),
        ),
        traces=(
            Trace(fault_time[near_short], shorted.real("out_gate")[near_short], "short circuit", 0),
            Trace(heavy_time[near_heavy], heavy.real("out_gate")[near_heavy], "4700 uF", 0),
            Trace(fault_time[near_short], shorted.real("@r110[i]")[near_short], "short circuit", 1),
            Trace(heavy_time[near_heavy], heavy.real("@r110[i]")[near_heavy], "4700 uF", 1),
            Trace(fault_time[near_short], shorted.real("dut")[near_short], "short circuit", 2),
            Trace(heavy_time[near_heavy], heavy.real("dut")[near_heavy], "4700 uF", 2),
        ),
    )
    notes = (
        "An ideal source behind 10 mohm stands for the source meter and its closed mode "
        "pair, which belong to other blocks. The device under test is a capacitor with "
        "20 mohm in series and 1 Mohm beside it, behind a cable of 50 mohm; these three "
        "values are assumptions.",
        "The fast corner: R117 at -1 %, C74 at -5 % (its value string gives no tolerance; "
        "5 % is the grade of its part number), +12 V_A at 12.6 V, both transistors with "
        "the threshold at the lower limit of the datasheet. The slow corner is the "
        "opposite. In the vendor tier the transistors stay typical in both corners.",
        "Every run starts with all voltages at zero and its sources rising in 200 us; "
        "the command comes 100 ms later, when the charge that this rise leaves on the "
        "gate node has gone. On the board the mode pair closes 40 ms before the "
        "command (rule F-24), which leaves a quarter of that charge and moves the "
        "start by less than 0.1 ms.",
        "The specification gives 6 ms to 7 ms from the command to the rise of the "
        "output. That holds at 5 V with a small capacitor and typical parts. The time "
        "follows the output voltage, the capacitance and the threshold of the "
        "transistors: 3.9 ms to the first 50 mV at 0.8 V in the fast corner, 10 ms to "
        "10 % at 5 V with 2200 uF in the slow corner.",
        "The in-rush is the slope of the gate times the capacitance, so it does not "
        "depend on the output voltage; the time to the first rise does, because the "
        "gate has less way to go at 0.8 V.",
        "With nominal parts 3000 uF stay below the trip level of 1.15 A, and 2480 uF "
        "stay below its lowest value in the fast corner. The 2200 uF and the 1800 uF "
        "with a capacitor 20 % high of the specification are inside that.",
        "The current into the gates is the current in R120. It reaches the device "
        "through the gate capacitances and is not measured by the shunts.",
        "The two starts with a trip use the model of the sequencer with ideal "
        "comparators on the shunt voltage, 0.2 us of delay and 12 us of qualification, "
        "and 1 uH in the cable. No program of the controller exists yet.",
        "The transistors are typical parts at 25 C; nothing here is thermal.",
    )
    return Outcome(tuple(figures), (waveforms, sweep, gate, faults), notes)
