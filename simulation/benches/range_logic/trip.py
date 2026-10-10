"""The over-current trip, and the recharge of a load capacitor that must not trip it."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches import frontend
from benches.range_logic import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_TRIP_TIME = 12e-6
"""Qualification time of the trip, s (rule F-18)."""

_SHORTEST_TRIP_TIME = 10e-6
"""Lowest value rule F-18 allows for that time, s."""

_REST_AMPS = 0.8
"""Load in range 3 before an over-current: 80 mV, below every threshold."""

_OVER_AMPS = 1.3
"""Load above the over-current level of 1.15 A."""

_OC_LOW = common.THRESHOLD_BAND["oc"][0]
_UP_HIGH = common.THRESHOLD_BAND["up"][1]
_JUMP_HIGH = common.THRESHOLD_BAND["jump"][1]

_CAPACITORS = (47e-6, 56e-6, 68e-6, 75e-6, 82e-6, 86e-6, 90e-6, 100e-6)
"""Load capacitors of the recharge runs, F."""


@dataclass(frozen=True, slots=True)
class _Variant:
    """One set of conditions for the recharge runs.

    Attributes:
        text: What the set is, for the labels.
        delays: Delays between the shunt and the gate.
        offsets: Offsets of the comparators.
        esr: Series resistance of the load capacitor, ohm.
    """

    text: str
    delays: common.Delays
    offsets: common.Offsets
    esr: float = common.DUT_ESR


def _offsets(oc: float, up: float | None = None, jump: float | None = None) -> common.Offsets:
    """Offsets that put the named thresholds at given shunt voltages."""
    return common.Offsets(
        up=0.0 if up is None else common.offset_for("up", up),
        oc=common.offset_for("oc", oc),
        jump=0.0 if jump is None else common.offset_for("jump", jump),
    )


_VARIANTS = {
    "nominal": _Variant("nominal", common.NOMINAL, common.Offsets()),
    "low": _Variant("over-current threshold lowest, worst delays", common.WORST, _offsets(_OC_LOW)),
    "spread": _Variant(
        "thresholds at opposite ends, worst delays",
        common.WORST,
        _offsets(_OC_LOW, _UP_HIGH, _JUMP_HIGH),
    ),
    "spread-esr": _Variant(
        "the same with 2 mohm in the capacitor",
        common.WORST,
        _offsets(_OC_LOW, _UP_HIGH, _JUMP_HIGH),
        esr=2e-3,
    ),
    "spread-lossy": _Variant(
        "the same with 30 mohm in the capacitor",
        common.WORST,
        _offsets(_OC_LOW, _UP_HIGH, _JUMP_HIGH),
        esr=30e-3,
    ),
}
"""The recharge runs are made for each of these, with every capacitor."""


def _recharge_deck(ctx: Context, variant: str, capacitance: float) -> str:
    chosen = _VARIANTS[variant]
    load = common.Load(before=1e-6, after=1.0, capacitance=capacitance, esr=chosen.esr)
    return common.step_deck(
        ctx,
        f"Step from 1 uA to 1 A with {capacitance * 1e6:g} uF at the load, {chosen.text}",
        load,
        delays=chosen.delays,
        offsets=chosen.offsets,
        end=common.STEP_AT + 0.25 * capacitance + 30e-6,
        max_step=5e-9,
    )


def _over_deck(ctx: Context, current: str, title: str) -> str:
    """Range 3 at rest with 0.8 A, then the load current of the bench."""
    circuit = common.front_end(ctx)
    return ctx.deck(
        title,
        circuit,
        frontend.rails(),
        common.source(5.0),
        common.controller(),
        common.dut(current, None),
        common.rest(circuit, 3),
        control=[f"save {common.SAVED}", "tran 5n 40u"],
        options=common.options(ctx),
        libraries=frontend.SEQUENCER_LIBRARIES,
    )


def _pulses() -> str:
    """Two pulses above the over-current level, 8 us each, 2 us apart."""
    at, edge = common.STEP_AT, 10e-9
    points = [(0.0, _REST_AMPS)]
    for start in (at, at + 10e-6):
        points += [
            (start, _REST_AMPS),
            (start + edge, _OVER_AMPS),
            (start + 8e-6, _OVER_AMPS),
            (start + 8e-6 + edge, _REST_AMPS),
        ]
    return common.pwl(points)


@dataclass(frozen=True, slots=True)
class _Recharge:
    """What one recharge run shows.

    Attributes:
        high: Longest time CMP_OC is high without interruption, s.
        in_range_3: The same while range 3 is selected, s.
        tripped: Whether the output switch was told to open.
    """

    high: float
    in_range_3: float
    tripped: bool


def _recharge(result: RunResult) -> _Recharge:
    time = result.real("time")
    start, stop = common.STEP_AT, float(time[-1])
    return _Recharge(
        high=common.high_time(time, result.real("cmp_oc"), start, stop),
        in_range_3=common.high_in_range(result, "cmp_oc", 3, start),
        tripped=bool(np.min(result.real("gate_out")) < common.HALF_LOGIC),
    )


@bench(
    "range_logic",
    "trip",
    "The over-current trip after 12 us, and the recharge of a load capacitor",
    "section 4.4 (over-current, qualification), rules F-18 and F-19, section 11 (step to 1.0 A)",
)
def trip(ctx: Context) -> Outcome:
    """Three questions about the over-current comparator are answered.

    Does the trip act: range 3 carries 0.8 A, the load steps to 1.3 A and
    stays, and the output switch has to open 12 us after the comparator
    rose. Does a shorter excess pass: two pulses of 1.3 A, 8 us each and
    2 us apart, must leave the output on. Does the recharge of a load
    capacitor pass: the load steps from 1 uA in range 0 to 1.0 A beside
    47 uF to 100 uF, the sequencer climbs to range 3 while the capacitor
    sags, and in range 3 the shunt carries the load and the current that
    brings the capacitor back. The run reads how long the comparator stays
    high, in any range and in range 3 alone, with nominal parts, with the
    over-current threshold at its lowest and the worst delays, and with the
    three thresholds at opposite ends of their bands.
    """
    trip_run = ctx.run(
        "trip",
        _over_deck(
            ctx,
            common.step(_REST_AMPS, _OVER_AMPS, common.STEP_AT),
            "Over-current in range 3: 0.8 A to 1.3 A",
        ),
    )
    pulse_run = ctx.run(
        "pulses", _over_deck(ctx, _pulses(), "Two pulses of 1.3 A in range 3, 8 us each")
    )
    kept = {("spread", 82e-6), ("nominal", 56e-6)}
    names = {
        (variant, capacitance): f"{variant}-{capacitance * 1e6:g}u"
        for variant in _VARIANTS
        for capacitance in _CAPACITORS
    }
    runs = {key: ctx.run(names[key], _recharge_deck(ctx, *key)) for key in sorted(kept)}
    others = ctx.run_many(
        {name: _recharge_deck(ctx, *key) for key, name in names.items() if key not in kept}
    )
    runs.update({key: others[name] for key, name in names.items() if key not in kept})
    found = {key: _recharge(result) for key, result in runs.items()}

    time = trip_run.real("time")
    start = common.STEP_AT
    rises = measure.first_crossing(
        time, trip_run.real("cmp_oc"), common.HALF_LOGIC, rising=True, after=start
    )
    opens = measure.first_crossing(
        time, trip_run.real("gate_out"), common.HALF_LOGIC, rising=False, after=start
    )
    gate_low = measure.first_crossing(time, trip_run.real("g_out"), 2.0, rising=False, after=opens)
    load_off = measure.first_crossing(
        time, trip_run.real("@r110[i]"), 0.1 * _OVER_AMPS, rising=False, after=opens
    )
    figures = [
        Figure(
            "trip_time",
            "Over-current comparator high to the line of the output switch low",
            opens - rises,
            "s",
            expected=_TRIP_TIME,
            low=_SHORTEST_TRIP_TIME,
            high=20e-6,
            source="rule F-18: 12 us, never below 10 us or above 20 us; a parameter of the model",
        ),
        Figure(
            "trip_gate",
            "Line low to the gate of the output switch below 2 V",
            gate_low - opens,
            "s",
            expected=7e-6,
            source="rule F-8: below 2 V within 7 us, simulated",
        ),
        Figure(
            "trip_current",
            "Line low to the current in the shunt below a tenth",
            load_off - opens,
            "s",
        ),
        Figure(
            "trip_from_step",
            "Load step above the level to the current below a tenth",
            load_off - start,
            "s",
            high=20e-6 + 10e-6,
            source="limit of this bench: the longest time of rule F-18 and 10 us to open",
        ),
        Figure(
            "trip_stays",
            "Line of the output switch at the end of the run",
            float(trip_run.real("gate_out")[-1]),
            "V",
            high=0.1,
            source="rule F-19: low until the fault is cleared",
        ),
        Figure(
            "trip_range",
            "Range selected after the trip",
            float(common.range_index(trip_run)[-1]),
            "",
            expected=3.0,
            low=3.0,
            high=3.0,
            source="rule F-19: after a trip range 3 stays selected",
        ),
        Figure(
            "pulses_pass",
            "Two pulses of 8 us, 2 us apart: lowest level of the output line",
            float(np.min(pulse_run.real("gate_out"))),
            "V",
            low=3.0,
            source="rule F-18: high without interruption for 12 us",
        ),
    ]
    for variant, chosen in _VARIANTS.items():
        rows = {capacitance: found[(variant, capacitance)] for capacitance in _CAPACITORS}
        worst = max(rows, key=lambda capacitance: rows[capacitance].high)
        inside = max(rows, key=lambda capacitance: rows[capacitance].in_range_3)
        failing = variant not in ("nominal", "spread-lossy")
        figures += [
            Figure(
                f"high_{variant.replace('-', '_')}",
                f"CMP_OC high, longest over 47 uF to 100 uF, {chosen.text}",
                rows[worst].high,
                "s",
                expected=8.6e-6 if variant == "low" else None,
                high=_SHORTEST_TRIP_TIME if failing else None,
                source="section 4.4: up to 8.6 us; section 11: high for less than 10 us"
                if failing
                else "",
            ),
            Figure(
                f"high_at_{variant.replace('-', '_')}",
                "Load capacitor of that run",
                worst,
                "F",
                expected=56e-6 if variant == "low" else None,
            ),
            Figure(
                f"inside_{variant.replace('-', '_')}",
                f"CMP_OC high in range 3, longest over 47 uF to 100 uF, {chosen.text}",
                rows[inside].in_range_3,
                "s",
                high=_SHORTEST_TRIP_TIME,
                source="rule F-18: the trip acts in range 3 only; shortest time 10 us",
            ),
        ]
    figures += [
        Figure(
            "high_56u_low",
            "CMP_OC high with 56 uF, over-current threshold lowest, worst delays",
            found[("low", 56e-6)].high,
            "s",
            expected=8.6e-6,
            source="section 4.4: 8.6 us with 56 uF at the lowest threshold, simulated",
        ),
        Figure(
            "recharge_trips",
            f"Recharge runs in which the trip acted, of {len(found)}",
            float(sum(entry.tripped for entry in found.values())),
            "",
            high=0.0,
            source="section 4.4: the qualification lets the recharge pass",
        ),
    ]

    shown = (time >= start - 2e-6) & (time <= start + 30e-6)
    micro = (time[shown] - start) * 1e6

    def cut(node: str) -> np.ndarray:
        return trip_run.real(node)[shown]

    pulse_time = pulse_run.real("time")
    pulse_shown = (pulse_time >= start - 2e-6) & (pulse_time <= start + 30e-6)
    pulse_micro = (pulse_time[pulse_shown] - start) * 1e6
    tripping = Graph(
        name="trip",
        title="Range 3 at 5 V: a load of 1.3 A that stays, and two pulses of 8 us",
        xlabel="Time after the load passes the over-current level (us)",
        panels=(
            Panel("Current in the 0.1 ohm shunt (A)", marks=((1.15, "level 1.15 A"),)),
            Panel("CMP_OC and the line of the output switch (V)"),
            Panel("Gate of the output switch (V)"),
            Panel("Voltage at the terminal (V)"),
        ),
        traces=(
            Trace(micro, cut("@r110[i]"), "load stays", 0),
            Trace(pulse_micro, pulse_run.real("@r110[i]")[pulse_shown], "two pulses", 0, "--"),
            Trace(micro, cut("cmp_oc"), "CMP_OC, load stays", 1),
            Trace(micro, cut("gate_out"), "GATE_OUT, load stays", 1),
            Trace(pulse_micro, pulse_run.real("cmp_oc")[pulse_shown], "CMP_OC, pulses", 1, "--"),
            Trace(pulse_micro, pulse_run.real("gate_out")[pulse_shown], "GATE_OUT, pulses", 1, ":"),
            Trace(micro, cut("g_out"), "load stays", 2),
            Trace(pulse_micro, pulse_run.real("g_out")[pulse_shown], "two pulses", 2, "--"),
            Trace(micro, cut("vout"), "load stays", 3),
            Trace(pulse_micro, pulse_run.real("vout")[pulse_shown], "two pulses", 3, "--"),
        ),
        xmarks=((12.0, "12 us"),),
    )
    traces: list[Trace] = []
    for key, label in (
        (("nominal", 56e-6), "56 uF, nominal"),
        (("spread", 82e-6), "82 uF, thresholds at opposite ends, worst delays"),
    ):
        result = runs[key]
        axis = result.real("time")
        part = (axis >= start - 1e-6) & (axis <= start + 32e-6)
        scaled = (axis[part] - start) * 1e6
        traces += [
            Trace(scaled, common.ladder(result)[part] * 1e3, label, 0),
            Trace(scaled, common.branch_r3(result)[part], label, 1),
            Trace(scaled, common.settled_range(result)[part], label, 2),
            Trace(scaled, result.real("cmp_oc")[part], label, 3),
        ]
    recharge = Graph(
        name="recharge",
        title="1 uA to 1.0 A beside a large capacitor: the climb to range 3 and the recharge",
        xlabel="Time after the load step (us)",
        panels=(
            Panel(
                "Ladder voltage (mV)",
                marks=((151.2, "jump"), (115.0, "over-current"), (91.0, "step up")),
            ),
            Panel("Current in the 0.1 ohm branch (A)", marks=((1.15, "level 1.15 A"),)),
            Panel("Selected range"),
            Panel("CMP_OC (V)"),
        ),
        traces=tuple(traces),
    )
    sweep_traces = [
        Trace(
            np.array(_CAPACITORS) * 1e6,
            np.array([found[(variant, c)].high for c in _CAPACITORS]) * 1e6,
            chosen.text,
            0,
        )
        for variant, chosen in _VARIANTS.items()
    ] + [
        Trace(
            np.array(_CAPACITORS) * 1e6,
            np.array([found[(variant, c)].in_range_3 for c in _CAPACITORS]) * 1e6,
            chosen.text,
            1,
        )
        for variant, chosen in _VARIANTS.items()
    ]
    sweep = Graph(
        name="sweep",
        title="How long the over-current comparator stays high after a step to 1.0 A",
        xlabel="Capacitor at the load (uF)",
        panels=(
            Panel(
                "CMP_OC high, any range (us)",
                marks=(
                    (10.0, "10 us: section 11, shortest trip time"),
                    (8.6, "8.6 us: section 4.4"),
                ),
            ),
            Panel("CMP_OC high in range 3 (us)", marks=((10.0, "10 us"),)),
        ),
        traces=tuple(sweep_traces),
    )
    notes = (
        "The trip is the model of rule F-18: a timer that runs while CMP_OC is "
        "high and range 3 is selected. Its 12 us are a parameter, so the first "
        "figure shows that the bench is wired right, not that a program keeps "
        "the time.",
        "With a large capacitor the load voltage sags slowly, the sequencer steps "
        "to range 1 at 91 mV, waits out the blanking, steps to range 2, waits "
        "again, and reaches range 3 with 145 mV to 160 mV across the ladder. The "
        "over-current comparator is high from 115 mV on, that is for microseconds "
        "before range 3 is selected, and then until the capacitor is recharged.",
        "The blanking here is that of rule F-17 as written: 3 us from the first "
        "change of a line to the next step. The 8.6 us of the specification came "
        "from runs with 2 us between steps; with 3 us the longest time is found at "
        "a larger capacitor and is longer.",
        "The figures that fail are the time the comparator output is high in any "
        "range, which is what a probe at TP46 shows and what the test of section "
        "11 limits to 10 us. The time in range 3, the only one the trip of rule "
        "F-18 counts in this model, stays below 10 us in every run, and no run "
        "trips. A program that started its count at the comparator edge and not "
        "at the entry into range 3 would have no margin at 12 us in the worst run "
        "and would trip at the 10 us that the rule allows.",
        "The capacitor has 5 mohm in series unless said otherwise and 1 mohm of "
        "lead; the recharge current, and with it these times, falls quickly with "
        "more series resistance, as the runs with 30 mohm show.",
        "The source holds 5 V behind 20 mohm. The amplifier model recovers from "
        "overload at its slew rate; these runs do not overload it.",
        common.VENDOR_NOTE,
    )
    return Outcome(tuple(figures), (tripping, recharge, sweep), notes)
