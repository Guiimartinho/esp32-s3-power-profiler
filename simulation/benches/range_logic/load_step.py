"""Requirement R-07: what a fast load step costs at the output, and the ladder clamp."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from benches.range_logic import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_JUMP_HIGH = common.Offsets(jump=common.offset_for("jump", common.THRESHOLD_BAND["jump"][1]))
"""The jump threshold at the upper limit of its band, 155.1 mV at the shunt."""

_LEAD = 20e-9
"""Inductance of 20 mm of lead to the capacitor, H (the fixture of section 11)."""

_CLAMP_STARTS = 1.3
"""Lowest gate threshold of the clamp transistors at 25 uA, V (section 4.3)."""

_LOW_CLAMPS = (common.CLAMP_LOW, common.CLAMP_LOW)
"""Both clamp transistors with their threshold at the lower limit."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One run of the bench.

    Attributes:
        load: The device under test and its step.
        volts: Output voltage.
        delays: Delays between the shunt and the gate.
        offsets: Offsets of the comparators.
        end: End of the run, s.
        clamps: Models of the two clamp transistors, when not the typical ones.
        slow_amplifier: The amplifier at half the bandwidth of its model.
    """

    load: common.Load
    volts: float = 5.0
    delays: common.Delays = common.NOMINAL
    offsets: common.Offsets | None = None
    end: float = 12e-6
    clamps: tuple[str, str] | None = None
    slow_amplifier: bool = False


_ONE = common.Load(before=1e-6, after=0.5, capacitance=1e-6)
_TEN = replace(_ONE, capacitance=10e-6)
_ONE_LOW = replace(_ONE, capacitance=0.9e-6, lead_henries=_LEAD)
_TEN_LOW = replace(_ONE, capacitance=9e-6, lead_henries=_LEAD)
_SLOW = replace(common.WORST, reaction=300e-9)


def _clamp_case(amps: float, capacitance: float | None) -> _Case:
    """A step that tries the ladder clamp: worst delays, lowest clamp threshold."""
    load = common.Load(before=1e-6, after=amps, capacitance=capacitance)
    return _Case(load, delays=common.WORST, clamps=_LOW_CLAMPS)


_CASES = {
    "nominal-1u": _Case(_ONE),
    "nominal-1u-3v3": _Case(_ONE, volts=3.3),
    "nominal-1u-0v8": _Case(_ONE, volts=0.8),
    "nominal-10u": _Case(_TEN, end=30e-6),
    "nominal-10u-0v8": _Case(_TEN, volts=0.8, end=30e-6),
    "worst-1u": _Case(_ONE_LOW, delays=common.WORST, offsets=_JUMP_HIGH),
    "worst-1u-3v3": _Case(_ONE_LOW, volts=3.3, delays=common.WORST, offsets=_JUMP_HIGH),
    "worst-1u-0v8": _Case(_ONE_LOW, volts=0.8, delays=common.WORST, offsets=_JUMP_HIGH),
    "worst-10u": _Case(_TEN_LOW, delays=common.WORST, offsets=_JUMP_HIGH, end=30e-6),
    "worst-1u-slow-amplifier": _Case(
        _ONE_LOW, delays=common.WORST, offsets=_JUMP_HIGH, slow_amplifier=True
    ),
    "worst-10u-slow-amplifier": _Case(
        _TEN_LOW, delays=common.WORST, offsets=_JUMP_HIGH, end=30e-6, slow_amplifier=True
    ),
    "slow-sequencer": _Case(_ONE, delays=_SLOW),
    "slow-sequencer-worst": _Case(_ONE_LOW, delays=_SLOW, offsets=_JUMP_HIGH),
    "clamp-500m-470n": _clamp_case(0.5, 470e-9),
    "clamp-1a-470n": _clamp_case(1.0, 470e-9),
    "clamp-1a-100n": _clamp_case(1.0, 100e-9),
    "clamp-1a-none": _clamp_case(1.0, None),
}
"""Every run of the bench, by name."""

_KEPT = ("nominal-1u", "nominal-10u", "worst-1u", "clamp-1a-470n")
"""The runs whose decks are filed with the results."""


def _deck(ctx: Context, name: str) -> str:
    case = _CASES[name]
    load = case.load
    cap = "no capacitor" if load.capacitance is None else f"{load.capacitance * 1e6:g} uF"
    return common.step_deck(
        ctx,
        f"Load step, {name}: 1 uA to {load.after:g} A with {cap} at {case.volts:g} V",
        load,
        volts=case.volts,
        delays=case.delays,
        offsets=case.offsets,
        clamps=case.clamps,
        more=common.slow_amplifier(ctx) if case.slow_amplifier else None,
        end=case.end,
    )


@dataclass(frozen=True, slots=True)
class _Drop:
    """What a load step did at the output.

    Attributes:
        peak: Largest drop from the supply node to the terminal, V.
        above: Time the drop spent above 0.2 V, s.
        late: Distance of the drop from its final value at the check instant, V.
        final_range: The range at the end of the run.
        ladder: Largest ladder voltage, V.
        clamp: Largest current in one clamp transistor, A.
    """

    peak: float
    above: float
    late: float
    final_range: float
    ladder: float
    clamp: float


def _drop(result: RunResult, check_after: float) -> _Drop:
    """The figures of one run; the check instant counts from the step."""
    time = result.real("time")
    start, stop = common.STEP_AT, float(time[-1])
    drop = common.drop(result)
    final = measure.mean(time, drop, stop - 1e-6, stop)
    clamp = max(
        measure.extremes(time, result.real(name), start, stop)[1]
        for name in ("@mq10[id]", "@mq11[id]")
    )
    return _Drop(
        peak=measure.extremes(time, drop, start, stop)[1],
        above=common.time_above(time, drop, 0.2, start, stop),
        late=abs(measure.value_at(time, drop, start + check_after) - final),
        final_range=float(common.range_index(result)[-1]),
        ladder=measure.extremes(time, common.ladder(result), start, stop)[1],
        clamp=clamp,
    )


def _to_limit(result: RunResult) -> float:
    """How long the ladder voltage would take from the jump threshold to 0.5 V.

    The ladder voltage rises in a straight line while the capacitor at the
    load carries the step; its slope between 100 mV and 250 mV is carried
    on to the limit of requirement R-07.
    """
    time = result.real("time")
    ladder = common.ladder(result)
    low = measure.first_crossing(time, ladder, 0.10, rising=True, after=common.STEP_AT)
    high = measure.first_crossing(time, ladder, 0.25, rising=True, after=common.STEP_AT)
    slope = 0.15 / (high - low)
    return (0.5 - common.THRESHOLD_SHUNT["jump"]) / slope


def _drop_graph(
    name: str, title: str, runs: dict[str, RunResult], limit: float, span: float
) -> Graph:
    """Drop, terminal voltage and range of some runs over one time axis."""
    traces: list[Trace] = []
    for label, result in runs.items():
        time = result.real("time")
        shown = (time >= common.STEP_AT - 0.5e-6) & (time <= common.STEP_AT + span)
        micro = (time[shown] - common.STEP_AT) * 1e6
        traces += [
            Trace(micro, common.drop(result)[shown] * 1e3, label, 0),
            Trace(micro, result.real("vout")[shown], label, 1),
            Trace(micro, common.branch_r3(result)[shown], f"0.1 ohm branch, {label}", 2),
            Trace(micro, common.settled_range(result)[shown], label, 3),
        ]
    marks: tuple[tuple[float, str], ...] = ((limit * 1e3, f"limit {limit * 1e3:g} mV"),)
    if limit > 0.2:
        marks += ((200.0, "0.2 V, for 1 us at the most"),)
    return Graph(
        name=name,
        title=title,
        xlabel="Time after the load step (us)",
        panels=(
            Panel("Drop, supply node to terminal (mV)", marks=marks),
            Panel("Voltage at the terminal (V)"),
            Panel("Current (A)"),
            Panel("Selected range"),
        ),
        traces=tuple(traces),
    )


@bench(
    "range_logic",
    "load-step",
    "Requirement R-07: the drop on a step from 1 uA to 500 mA, and the ladder clamp",
    "requirement R-07, sections 4.3 (ladder clamp) and 4.4 (jump up), decision D-65",
)
def load_step(ctx: Context) -> Outcome:
    """The load steps from 1 uA to 500 mA in range 0 with 1 uF and with 10 uF.

    Until range 3 conducts the capacitor at the terminals supplies the step,
    and the voltage between the supply node and the output terminal, which is
    what the requirement limits, grows with it. The run is made with the
    nominal delays at 5 V, 3.3 V and 0.8 V, and with everything against the
    limit at once: the worst delays with the sequencer at its 100 ns, the
    jump threshold at the upper end of its band, the capacitor 10 % low and
    20 nH of lead to it. Two more runs give the sequencer 300 ns, which rule
    F-16 forbids. The last runs take less capacitance and 1 A, to see when
    the ladder clamp begins to conduct.
    """
    results = {name: ctx.run(name, _deck(ctx, name)) for name in _KEPT}
    results.update(ctx.run_many({name: _deck(ctx, name) for name in _CASES if name not in _KEPT}))
    found = {
        name: _drop(result, 10e-6 if (_CASES[name].load.capacitance or 0.0) > 5e-6 else 5e-6)
        for name, result in results.items()
    }
    r07 = "requirement R-07"

    def peak(name: str, label: str, expected: float | None, high: float | None) -> Figure:
        key = "drop_" + name.replace("-", "_")
        source = f"{r07}; simulated value of section 2" if high else "risk register, section 14"
        return Figure(
            key, label, found[name].peak, "V", expected=expected, high=high, source=source
        )

    def above(name: str, label: str) -> Figure:
        key = "above_" + name.replace("-", "_")
        return Figure(key, label, found[name].above, "s", high=1e-6, source=f"{r07}: 1 us")

    def late(name: str, label: str) -> Figure:
        key = "late_" + name.replace("-", "_")
        source = "section 11, test of R-07: within 50 mV"
        return Figure(key, label, found[name].late, "V", high=0.05, source=source)

    def ladder_peak(name: str, label: str, limited: bool) -> Figure:
        key = "ladder_" + name.replace("-", "_")
        high = _CLAMP_STARTS if limited else None
        source = "section 4.3: no conduction with 470 nF or more; threshold 1.3 V at 25 uA"
        return Figure(
            key, label, found[name].ladder, "V", high=high, source=source if limited else ""
        )

    def clamp_peak(name: str, label: str) -> Figure:
        return Figure("clamp_" + name.replace("-", "_"), label, found[name].clamp, "A")

    figures = [
        peak("nominal-1u", "1 uF, nominal, 5 V: largest drop", 0.312, 0.5),
        above("nominal-1u", "1 uF, nominal, 5 V: time above 0.2 V"),
        late("nominal-1u", "1 uF, nominal, 5 V: from the final value after 5 us"),
        peak("nominal-1u-3v3", "1 uF, nominal, 3.3 V: largest drop", 0.312, 0.5),
        peak("nominal-1u-0v8", "1 uF, nominal, 0.8 V: largest drop", 0.312, 0.5),
        peak("worst-1u", "0.9 uF, worst case, 5 V: largest drop", 0.422, 0.5),
        above("worst-1u", "0.9 uF, worst case, 5 V: time above 0.2 V"),
        late("worst-1u", "0.9 uF, worst case, 5 V: from the final value after 5 us"),
        peak("worst-1u-3v3", "0.9 uF, worst case, 3.3 V: largest drop", 0.422, 0.5),
        peak("worst-1u-0v8", "0.9 uF, worst case, 0.8 V: largest drop", 0.422, 0.5),
        above("worst-1u-0v8", "0.9 uF, worst case, 0.8 V: time above 0.2 V"),
        peak(
            "worst-1u-slow-amplifier",
            "0.9 uF, worst case, amplifier at half its bandwidth: largest drop",
            0.422,
            0.5,
        ),
        above(
            "worst-1u-slow-amplifier",
            "0.9 uF, worst case, amplifier at half its bandwidth: time above 0.2 V",
        ),
        peak("nominal-10u", "10 uF, nominal, 5 V: largest drop", 0.169, 0.25),
        late("nominal-10u", "10 uF, nominal, 5 V: from the final value after 10 us"),
        peak("nominal-10u-0v8", "10 uF, nominal, 0.8 V: largest drop", 0.169, 0.25),
        peak("worst-10u", "9 uF, worst case, 5 V: largest drop", 0.186, 0.25),
        late("worst-10u", "9 uF, worst case, 5 V: from the final value after 10 us"),
        peak(
            "worst-10u-slow-amplifier",
            "9 uF, worst case, amplifier at half its bandwidth: largest drop",
            0.186,
            0.25,
        ),
        peak("slow-sequencer", "1 uF, sequencer of 300 ns: largest drop", 0.472, None),
        peak("slow-sequencer-worst", "0.9 uF, worst case, sequencer of 300 ns: drop", 0.519, None),
        Figure(
            "time_to_limit",
            "1 uF, nominal: time from the jump threshold to 0.5 V across the ladder",
            _to_limit(results["nominal-1u"]),
            "s",
            expected=0.77e-6,
            low=0.72e-6,
            high=0.82e-6,
            source="section 4.4: 0.5 V corresponds to 0.77 us with 1 uF, calculated",
        ),
        Figure(
            "final_range",
            "Range at the end of every run",
            min(entry.final_range for entry in found.values()),
            "",
            expected=3.0,
            low=3.0,
            high=3.0,
            source="section 4.4: the jump comparator forces range 3",
        ),
        ladder_peak("clamp-500m-470n", "470 nF, 500 mA, worst delays: ladder voltage", True),
        ladder_peak("clamp-1a-470n", "470 nF, 1 A, worst delays: ladder voltage", True),
        clamp_peak("clamp-1a-470n", "470 nF, 1 A: current in a clamp transistor"),
        ladder_peak("clamp-1a-100n", "100 nF, 1 A, worst delays: ladder voltage", False),
        clamp_peak("clamp-1a-100n", "100 nF, 1 A: current in a clamp transistor"),
        ladder_peak("clamp-1a-none", "No capacitor, 1 A, worst delays: ladder voltage", False),
        clamp_peak("clamp-1a-none", "No capacitor, 1 A: current in a clamp transistor"),
    ]
    one = _drop_graph(
        "drop-1u",
        "1 uA to 500 mA with 1 uF at the terminals, 5 V",
        {
            "nominal, 1 uF": results["nominal-1u"],
            "worst case, 0.9 uF": results["worst-1u"],
            "sequencer of 300 ns, 1 uF": results["slow-sequencer"],
        },
        0.5,
        4e-6,
    )
    ten = _drop_graph(
        "drop-10u",
        "1 uA to 500 mA with 10 uF at the terminals, 5 V",
        {"nominal, 10 uF": results["nominal-10u"], "worst case, 9 uF": results["worst-10u"]},
        0.25,
        14e-6,
    )
    traces: list[Trace] = []
    for label, name in (
        ("470 nF", "clamp-1a-470n"),
        ("100 nF", "clamp-1a-100n"),
        ("no capacitor", "clamp-1a-none"),
    ):
        result = results[name]
        time = result.real("time")
        shown = (time >= common.STEP_AT - 0.2e-6) & (time <= common.STEP_AT + 2.5e-6)
        micro = (time[shown] - common.STEP_AT) * 1e6
        both = result.real("@mq10[id]") + result.real("@mq11[id]")
        traces += [
            Trace(micro, common.ladder(result)[shown], label, 0),
            Trace(micro, np.asarray(both[shown]), label, 1),
            Trace(micro, common.branch_r3(result)[shown], label, 2),
        ]
    clamp = Graph(
        name="clamp",
        title="1 uA to 1 A, worst delays, clamp threshold at its lower limit",
        xlabel="Time after the load step (us)",
        panels=(
            Panel("Ladder voltage (V)", marks=((_CLAMP_STARTS, "1.3 V: lowest threshold"),)),
            Panel("Current in the ladder clamp, both parts (A)"),
            Panel("Current in the 0.1 ohm branch (A)"),
        ),
        traces=tuple(traces),
    )
    notes = (
        "The drop is taken between the supply node and the output terminal, as the "
        "requirement defines it. The source holds its voltage behind 20 mohm, so the "
        "terminal voltage falls by about the same amount; what the regulator or an "
        "external supply adds is not in these runs.",
        "Worst case: multiplexer 430 ohm, comparators 80 ns, sequencer 100 ns, "
        "driver 40 ns and 10 ohm, jump threshold at 155.1 mV, capacitor 10 % low, "
        "20 nH of lead between the terminal and the capacitor. The amplifier keeps "
        "the bandwidth of its model, 6.4 MHz; two more runs give it half of that, "
        "which is an assumption (its datasheet states no spread) and comes close "
        "to the worst case of the earlier simulations of the design.",
        "The two runs with a sequencer of 300 ns are outside rule F-16. They show "
        "where the limit of 0.5 V is lost and carry no limit themselves.",
        "The gate charge of the range 3 switch, about 15 nC, is pushed into the load "
        "node when the switch turns on and lifts 1 uF by about 14 mV: the drop peaks "
        "that much below what the delay alone would give.",
        "The clamp runs use the clamp model with its threshold 0.4 V below the "
        "typical curve. That model has no current below its threshold, so the "
        "ladder voltage against the 1.3 V of the datasheet is the figure that "
        "counts; the current is what the model shows beyond it.",
        "The load is a current sink beside the capacitor (5 mohm in series) and "
        "stops drawing below about 0.1 V.",
        common.VENDOR_NOTE,
    )
    return Outcome(tuple(figures), (one, ten, clamp), notes)
