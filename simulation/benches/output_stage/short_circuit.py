"""A short circuit at the output with the switch closed, up to the trip and after it."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches import frontend
from benches.output_stage import common
from circuit_sim import measure
from circuit_sim.bench import OPEN_TIER, Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_EVENT = 200e-6
"""Instant at which the short circuit closes."""

_WINDOW = 110e-6
"""Time that a run goes on after the short circuit."""

_SHORT_OHMS = 0.010
"""Resistance of the short circuit itself (assumption)."""

_REST_AMPS = 0.1
"""Load current before the short circuit: inside range 3."""

_PEAK_AMPS = 27.0
"""Largest current that the specification names for R110 (section 4.3)."""

_SHUNT_JOULES = 0.2
"""Pulse energy of R110 that the specification quotes (section 4.3)."""

_SAVES = (
    "save gate_out out_gate g_out mid vout_s vout dut supply guard gate_r3 "
    "@r110[i] vcab#branch xseq.trip"
)
"""What a run of this bench keeps, beside the currents of the suppressor."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One short circuit.

    Attributes:
        key: Short name, part of the keys of its figures.
        label: What the case is, as the report shows it.
        volts: Voltage of the supply node.
        cable: Inductance of the cable to the short circuit, H.
        ohms: Resistance of that cable, ohm.
        trip: Qualification time of the trip, s.
        forward: Forward resistance of the suppressor, ohm.
        regulator: The stand-in for the source mode instead of the stiff source.
        start_range: Range in which the run starts.
    """

    key: str
    label: str
    volts: float = 5.0
    cable: float = 1e-6
    ohms: float = common.CABLE_OHMS
    trip: float = 12e-6
    forward: float = 0.03
    regulator: bool = False
    start_range: int = 3


_CASES = (
    _Case("nominal", "5 V, 1 uH, trip after 12 us"),
    _Case("late", "5 V, 1 uH, trip after 20 us", trip=20e-6),
    _Case("near", "5 V, 0.2 uH, trip after 20 us", cable=0.2e-6, trip=20e-6),
    _Case("far", "5 V, 3 uH, trip after 20 us", cable=3e-6, trip=20e-6),
    _Case(
        "across",
        "5 V, short circuit across the terminals (5 mohm, 50 nH), trip after 20 us",
        cable=50e-9,
        ohms=0.005,
        trip=20e-6,
    ),
    _Case(
        "stiff",
        "5 V, 3 uH, trip after 20 us, suppressor with 0.15 ohm",
        cable=3e-6,
        trip=20e-6,
        forward=0.15,
    ),
    _Case("low", "0.8 V, 1 uH, trip after 20 us", volts=0.8, trip=20e-6),
    _Case("regulator", "Source mode stand-in, 5 V, 1 uH, trip after 12 us", regulator=True),
    _Case("range0", "5 V, 1 uH, from range 0, trip after 12 us", start_range=0),
)
"""The short circuits that are run."""


def _supply(case: _Case) -> str:
    """The stiff source, or a regulator that limits with its output capacitor."""
    ramp = common.QUICK_POWER_UP
    if case.regulator:
        return common.regulator(case.volts, ramp)
    return common.source(case.volts, ramp=ramp)


def _deck(ctx: Context, case: _Case) -> str:
    refs = list(common.path_refs(ctx.netlist))
    scales = {}
    if case.regulator:
        refs += common.REGULATOR_REFS
        scales["C53"] = common.C53_AT_5V
    models = dict(common.path_models(ctx))
    if case.forward != 0.03:
        models["D21"] = common.suppressor(case.forward)
    aliases = {**common.ALIASES, **common.REGULATOR_ALIASES}
    circuit = ctx.circuit(refs, aliases, models, scales)
    rest_ohms = case.volts / _REST_AMPS if case.start_range == 3 else 1e6
    stimulus = "\n".join(
        [
            "* the output is on; the device takes a small current until a short circuit",
            "* closes at the end of the cable",
            f"Vouton seq_out_on 0 {common.LOGIC_VOLTS:g}",
            f"Rload dut 0 {rest_ohms:g}",
            f".model OUTPUT_SHORT SW(vt=0.5 vh=0.1 ron={_SHORT_OHMS:g} roff=1e9)",
            f"Vshort shc 0 PWL(0 0 {_EVENT:g} 0 {_EVENT + 1e-8:g} 1)",
            "Sshort dut 0 shc 0 OUTPUT_SHORT",
        ]
    )
    ramp = common.QUICK_POWER_UP
    return ctx.deck(
        f"Short circuit at the output: {case.label}",
        circuit,
        common.rails(ramp=ramp),
        common.protection(case.trip, case.start_range),
        _supply(case),
        common.cable(ohms=case.ohms, henries=case.cable),
        stimulus,
        common.closed_start(),
        control=[
            f"{_SAVES} {common.suppressor_saves(ctx)}",
            f"tran 5n {_EVENT + _WINDOW:.9g} 0 10n uic",
        ],
        options=(*common.buffer_options(ctx), "method=gear"),
        libraries=frontend.SEQUENCER_LIBRARIES,
    )


@dataclass(frozen=True, slots=True)
class _Reading:
    """What one short circuit shows.

    Attributes:
        trip: Time from the short circuit to the fall of GATE_OUT.
        qualified: Time from the over-current level in the shunt to that fall.
        range_three: Time from the short circuit to range 3 selected.
        open: Time from the short circuit until the pair carries less than 1 A.
        peak: Largest current in the 0.1 ohm shunt.
        at_12: Current in the shunt 12 us after the short circuit.
        at_20: Current in the shunt 20 us after the short circuit.
        shunt: Energy in the 0.1 ohm shunt.
        first: Energy in Q15.
        second: Energy in Q16.
        power: Largest power in Q15.
        drain_first: Largest drain-source voltage of Q15.
        drain_second: Largest drain-source voltage of Q16, either sign.
        gate_source: Largest gate-source voltage of the pair, either sign.
        diode_peak: Largest forward current of the suppressor.
        terminal_low: Lowest voltage of the terminal.
        below: Time for which the terminal is below -0.5 V.
        node_low: Lowest voltage of the node after the shunts.
        node_high: Highest voltage of the node after the shunts.
        left: Current in the pair 60 us after the trip.
    """

    trip: float
    qualified: float
    range_three: float
    open: float
    peak: float
    at_12: float
    at_20: float
    shunt: float
    first: float
    second: float
    power: float
    drain_first: float
    drain_second: float
    gate_source: float
    diode_peak: float
    terminal_low: float
    below: float
    node_low: float
    node_high: float
    left: float


def _read(ctx: Context, run: RunResult) -> _Reading:
    time = run.real("time")
    end = float(time[-1])
    shunt = run.real("@r110[i]")
    pair = common.pair_current(ctx, run)
    mid, node, terminal = run.real("mid"), run.real("vout_s"), run.real("vout")
    trip = measure.first_crossing(
        time, run.real("gate_out"), 0.5 * common.LOGIC_VOLTS, rising=False, after=_EVENT
    )

    def span(values: np.ndarray) -> tuple[float, float]:
        return measure.extremes(time, values, _EVENT, end)

    under = np.where(terminal < -0.5, 1.0, 0.0)
    loss = (node - mid) * pair
    level = measure.first_crossing(time, shunt, common.TRIP_AMPS, rising=True, after=_EVENT)
    half = 0.5 * common.LOGIC_VOLTS
    selected = run.real("gate_r3")
    range_three = 0.0
    if measure.value_at(time, selected, _EVENT) < half:
        range_three = measure.first_crossing(time, selected, half, True, _EVENT) - _EVENT
    return _Reading(
        trip=trip - _EVENT,
        qualified=trip - level,
        range_three=range_three,
        open=measure.settling_time(time, pair, 0.0, 1.0, _EVENT),
        peak=span(shunt)[1],
        at_12=measure.value_at(time, shunt, _EVENT + 12e-6),
        at_20=measure.value_at(time, shunt, _EVENT + 20e-6),
        shunt=common.energy(time, 0.1 * shunt * shunt, _EVENT, end),
        first=common.energy(time, loss, _EVENT, end),
        second=common.energy(time, (mid - terminal) * pair, _EVENT, end),
        power=span(loss)[1],
        drain_first=span(node - mid)[1],
        drain_second=float(np.max(np.abs(span(terminal - mid)))),
        gate_source=float(np.max(np.abs(span(run.real("g_out") - mid)))),
        diode_peak=span(common.suppressor_current(ctx, run))[1],
        terminal_low=span(terminal)[0],
        below=measure.integral(time, under, _EVENT, end),
        node_low=span(node)[0],
        node_high=span(node)[1],
        left=abs(measure.value_at(time, pair, min(trip + 60e-6, end))),
    )


def _figures(case: _Case, reading: _Reading) -> list[Figure]:
    figures = [
        Figure(
            f"{case.key}_trip",
            f"{case.label}: short circuit to the fall of GATE_OUT",
            reading.trip,
            "s",
        ),
        Figure(
            f"{case.key}_qualified",
            f"{case.label}: 1.15 A in the shunt to the fall of GATE_OUT",
            reading.qualified,
            "s",
            low=10e-6,
            high=20.5e-6,
            source="rule F-18: qualification 10 us to 20 us; the upper limit here adds "
            "0.5 us for the comparator stand-in and the sequencer model",
        ),
        Figure(
            f"{case.key}_open",
            f"{case.label}: short circuit to less than 1 A in the pair",
            reading.open,
            "s",
        ),
        Figure(
            f"{case.key}_peak",
            f"{case.label}: largest current in the 0.1 ohm shunt",
            reading.peak,
            "A",
            high=_PEAK_AMPS,
            source="section 4.3: R3 carries up to 27 A for microseconds",
        ),
        Figure(
            f"{case.key}_at_12us",
            f"{case.label}: current in the shunt 12 us after the short circuit",
            reading.at_12,
            "A",
        ),
        Figure(
            f"{case.key}_at_20us",
            f"{case.label}: current in the shunt 20 us after the short circuit",
            reading.at_20,
            "A",
        ),
        Figure(
            f"{case.key}_shunt_energy",
            f"{case.label}: energy in the 0.1 ohm shunt R110",
            reading.shunt,
            "J",
            expected=1e-3,
            high=_SHUNT_JOULES,
            source="section 4.3: about 1 mJ against 200 mJ",
        ),
        Figure(
            f"{case.key}_pair_energy",
            f"{case.label}: energy in Q15",
            reading.first,
            "J",
            high=common.AVALANCHE_JOULES,
            source="TI SLPS515A, page 1: 39 mJ of avalanche energy, taken as the scale",
        ),
        Figure(
            f"{case.key}_pair_power",
            f"{case.label}: largest power in Q15",
            reading.power,
            "W",
        ),
        Figure(
            f"{case.key}_diode",
            f"{case.label}: largest forward current in the suppressor D21",
            reading.diode_peak,
            "A",
            expected=11.6,
            high=common.SURGE_AMPS,
            source="section 4.9: at most 11.6 A against a surge rating of 50 A",
        ),
        Figure(
            f"{case.key}_terminal",
            f"{case.label}: lowest voltage at the terminal",
            reading.terminal_low,
            "V",
            low=-1.7,
            source="section 4.9: the terminal goes to -0.8 V to -1.7 V",
        ),
        Figure(
            f"{case.key}_below",
            f"{case.label}: time for which the terminal is below -0.5 V",
            reading.below,
            "s",
        ),
    ]
    if case.start_range == 0:
        figures.append(
            Figure(
                f"{case.key}_range_three",
                f"{case.label}: short circuit to range 3 selected",
                reading.range_three,
                "s",
            )
        )
    return figures


@bench(
    "output_stage",
    "short-circuit",
    "A short circuit at the closed output: current, trip, energy and voltages",
    "sections 4.2 and 4.9 (output switch, suppressor, D-70, D-71), section 4.4 "
    "(over-current trip), rules F-18 and F-19, section 4.3 (pulse in R110)",
)
def short_circuit(ctx: Context) -> Outcome:
    """The output is on in range 3 and a short circuit closes at the end of the cable.

    The current rises as the inductance of the cable and the resistance of
    the path allow. The model of the sequencer sees the over-current
    through ideal comparators on the shunt voltage and lets GATE_OUT fall
    after the qualification time; the gate then leaves through D20 and
    R116, the pair brings the current down, and the suppressor carries
    what the cable still holds. The cases differ in the inductance of the
    cable (0.2 uH, 1 uH, 3 uH), in the qualification time (12 us and the
    20 us that rule F-18 allows at most), in the output voltage and in the
    forward resistance of the suppressor. One case takes a regulator that
    limits its current, with the output capacitor of the schematic, in
    place of the stiff source; one starts in range 0, so that the jump to
    range 3 comes first.
    """
    cases = [case for case in _CASES if case.forward == 0.03 or ctx.tier == OPEN_TIER]
    runs = ctx.run_many({case.key: _deck(ctx, case) for case in cases})
    for key in ("nominal", "far"):
        ctx.kept[f"{ctx.prefix}.{key}.cir"] = _deck(ctx, next(c for c in cases if c.key == key))
    readings = {case.key: _read(ctx, runs[case.key]) for case in cases}
    figures: list[Figure] = []
    for case in cases:
        figures += _figures(case, readings[case.key])
    worst = readings.values()
    figures += [
        Figure(
            "drain_first",
            "Largest drain-source voltage of Q15 in any case",
            max(reading.drain_first for reading in worst),
            "V",
            high=common.TRANSISTOR_VOLTS,
            source="section 4.9: the transistors are rated 30 V (datasheet value)",
        ),
        Figure(
            "drain_second",
            "Largest drain-source voltage of Q16 in any case, either sign",
            max(reading.drain_second for reading in worst),
            "V",
            high=common.TRANSISTOR_VOLTS,
            source="section 4.9: the transistors are rated 30 V (datasheet value)",
        ),
        Figure(
            "gate_source",
            "Largest gate-source voltage of the pair in any case, either sign",
            max(reading.gate_source for reading in worst),
            "V",
            high=common.GATE_VOLTS,
            source="TI SLPS515A, page 1: gate-source voltage 20 V at most",
        ),
        Figure(
            "second_energy",
            "Largest energy in Q16 in any case",
            max(reading.second for reading in worst),
            "J",
            high=common.AVALANCHE_JOULES,
            source="TI SLPS515A, page 1: 39 mJ of avalanche energy, taken as the scale",
        ),
        Figure(
            "node_low",
            "Lowest voltage at the node after the shunts, stiff source",
            min(readings[case.key].node_low for case in cases if not case.regulator),
            "V",
        ),
        Figure(
            "node_low_regulator",
            "Lowest voltage at the node after the shunts, source mode stand-in",
            readings["regulator"].node_low,
            "V",
        ),
        Figure(
            "node_high",
            "Highest voltage at the node after the shunts in any case",
            max(reading.node_high for reading in worst),
            "V",
            high=11.5,
            source="section 4.3: the ladder stays below 11.5 V, under +12 V_A",
        ),
        Figure(
            "left",
            "Largest current in the pair 60 us after a trip",
            max(reading.left for reading in worst),
            "A",
            high=1e-3,
            source="rule F-19: GATE_OUT stays low after a trip",
        ),
    ]
    nominal = runs["nominal"]
    time = nominal.real("time")
    micro = (time - _EVENT) * 1e6
    shown = (micro >= -3.0) & (micro <= 60.0)
    pair = common.pair_current(ctx, nominal)
    diode = common.suppressor_current(ctx, nominal)
    mid, node, terminal = nominal.real("mid"), nominal.real("vout_s"), nominal.real("vout")
    waveforms = Graph(
        name="waveforms",
        title="Short circuit at 5 V behind 1 uH, trip after 12 us",
        xlabel="Time after the short circuit (us)",
        panels=(
            Panel("Gate drive (V)", marks=((2.0, "2 V"),)),
            Panel("Path (V)"),
            Panel("Current (A)"),
            Panel("Power (W)"),
        ),
        traces=(
            Trace(micro[shown], nominal.real("gate_out")[shown], "GATE_OUT", 0),
            Trace(micro[shown], nominal.real("out_gate")[shown], "gate node, TP37", 0),
            Trace(micro[shown], mid[shown], "common source", 0),
            Trace(micro[shown], terminal[shown], "terminal", 1),
            Trace(micro[shown], node[shown], "node after the shunts", 1),
            Trace(micro[shown], nominal.real("supply")[shown], "supply node", 1, "--"),
            Trace(micro[shown], nominal.real("guard")[shown], "guard", 1, ":"),
            Trace(micro[shown], nominal.real("@r110[i]")[shown], "0.1 ohm shunt", 2),
            Trace(micro[shown], nominal.real("vcab#branch")[shown], "cable", 2, "--"),
            Trace(micro[shown], diode[shown], "suppressor D21, forward", 2),
            Trace(micro[shown], ((node - mid) * pair)[shown], "Q15", 3),
            Trace(micro[shown], ((mid - terminal) * pair)[shown], "Q16", 3),
        ),
        xmarks=((12.0, "12 us"), (20.0, "20 us")),
    )
    rise_traces = []
    for case in cases:
        if case.key in ("nominal", "late", "near", "far", "low", "regulator"):
            run = runs[case.key]
            axis = (run.real("time") - _EVENT) * 1e6
            part = (axis >= -1.0) & (axis <= 45.0)
            rise_traces.append(Trace(axis[part], run.real("@r110[i]")[part], case.label, 0))
            rise_traces.append(Trace(axis[part], run.real("vout")[part], case.label, 1))
    rise = Graph(
        name="current",
        title="Current in the 0.1 ohm shunt and voltage at the terminal, case by case",
        xlabel="Time after the short circuit (us)",
        panels=(
            Panel("Current in the shunt (A)", marks=((common.TRIP_AMPS, "trip 1.15 A"),)),
            Panel("Terminal (V)", marks=((-1.7, "-1.7 V"),)),
        ),
        traces=tuple(rise_traces),
        xmarks=((12.0, "12 us"), (20.0, "20 us")),
    )
    notes = (
        "The stiff source is an ideal source behind 10 mohm: the ampere mode on a "
        "supply without lead inductance, which is the largest current the path can "
        "see. The inductance of supply leads is left out here: at a trip it lifts the "
        "supply node, which the ampere pair and the suppressor of the VIN terminal "
        "bound, and those belong to the path switching block.",
        "The source mode stand-in is a current source that limits at 1.4 A on C53 and "
        "C54 of the schematic, with C53 at the 13.6 uF that the specification gives for "
        "5 V, and 10 mohm for the source pair. The regulator itself belongs to the "
        "source meter block.",
        "The cable has 50 mohm and the short circuit 10 mohm; both are assumptions, and "
        "the largest current follows them directly. With them the shunt carries up to "
        "26 A, inside the 27 A of the specification. A short circuit across the "
        "terminals themselves (5 mohm, 50 nH) gives 32 A on this stiff source: the 27 A "
        "are not a bound of the circuit. The energy in the shunt stays at 2.6 mJ, far "
        "below the 200 mJ on which the specification accepts the pulse.",
        "The source mode stand-in has no diode from ground to the regulator output "
        "(D12 of the source meter sheet). Its output capacitors ring against the cable "
        "and take the supply node and the node after the shunts below ground, to "
        "-0.85 V, within 8 us of the short circuit and before the trip acts. On the "
        "board D12 has to carry that current.",
        "The suppressor carries up to 14 A forward (17 A with the model of its "
        "manufacturer), more than the 11.6 A of section 4.9 and well inside its "
        "rating of 50 A.",
        "Q15 takes up to 70 W for about 5 us at 6.4 V or less. The safe operating area "
        "of its datasheet (figure 10) allows more than 100 A at that voltage for "
        "10 us.",
        "The trip is the model of rule F-18 behind ideal comparators with 0.2 us of "
        "delay. No program of the controller exists yet.",
        "Every run starts with all voltages at zero and its sources rising in 20 us; a "
        "switch ties the gate node to 12 V until 60 us, and the short circuit closes at "
        "200 us.",
        "The forward curve of the suppressor is an assumption (0.75 V at 0.1 A; 0.03 ohm, "
        "and 0.15 ohm in one case); its datasheet has none. The lowest voltage of the "
        "terminal follows that assumption.",
        "The ladder clamp conducts while the shunt drops more than about 2.5 V, so the "
        "cable carries more than the shunt; the clamp belongs to the ladder block.",
        "Typical transistors at 25 C; nothing here is thermal.",
    )
    return Outcome(tuple(figures), (waveforms, rise), notes)
