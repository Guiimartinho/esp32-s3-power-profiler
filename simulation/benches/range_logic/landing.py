"""Where the sequencer lands after a load step, with a capacitor at the load."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches import frontend
from benches.range_logic import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_STEPS = {"150ua": 150e-6, "5ma": 5e-3, "80ma": 80e-3}
"""Load currents after the step, A."""

_CAPACITORS = {"100nf": 100e-9, "1uf": 1e-6, "10uf": 10e-6, "100uf": 100e-6}
"""Capacitors at the load, F."""

_PROPER = {"150ua": 1, "5ma": 2, "80ma": 2}
"""The range whose full scale is the first above each current (section 4.3)."""

_AFTER_SHUNTS = 100e-9
"""Capacitor on the node after the shunts, C71, F."""

_BAND = 0.01
"""The reading counts as the load current inside this fraction of it."""

_STEP_UP = common.THRESHOLD_SHUNT["up"]


def _labels(step: str, capacitor: str) -> str:
    amps, farads = _STEPS[step], _CAPACITORS[capacitor]
    current = f"{amps * 1e6:g} uA" if amps < 1e-3 else f"{amps * 1e3:g} mA"
    size = f"{farads * 1e9:g} nF" if farads < 1e-6 else f"{farads * 1e6:g} uF"
    return f"{current} with {size}"


def _duration(amps: float, farads: float) -> float:
    """How long a run has to be: range 0 up to its threshold, then settling."""
    total = farads + _AFTER_SHUNTS
    in_range_0 = -1000.0 * total * float(np.log(1.0 - _STEP_UP / (amps * 1000.0)))
    return common.STEP_AT + in_range_0 + 10.0 * frontend.SHUNT_OHMS[1] * total + 60e-6


def _deck(ctx: Context, step: str, capacitor: str) -> str:
    amps, farads = _STEPS[step], _CAPACITORS[capacitor]
    end = _duration(amps, farads)
    return common.step_deck(
        ctx,
        f"Load step from 1 uA to {_labels(step, capacitor)} at the load",
        common.Load(before=1e-6, after=amps, capacitance=farads),
        end=end,
        max_step=float(np.clip(end / 30000.0, 5e-9, 2e-6)),
    )


def _reading(result: RunResult) -> np.ndarray:
    """The current that the amplifier output stands for in the selected range."""
    shunts = np.asarray(frontend.SHUNT_OHMS)[common.settled_range(result).astype(np.int64)]
    return np.asarray(
        (result.real("amp_raw") - common.PEDESTAL) / common.GAIN / shunts, dtype=np.float64
    )


@dataclass(frozen=True, slots=True)
class _Landing:
    """What one load step shows.

    Attributes:
        ranges: The range after each change.
        instants: Time of each change after the step, s.
        final: The range at the end of the run.
        reads: Time from the step until the reading stays within 1 % of the load, s.
        shortest: Shortest time between two changes, s.
        jumped: Whether the jump comparator acted.
    """

    ranges: tuple[int, ...]
    instants: tuple[float, ...]
    final: int
    reads: float
    shortest: float
    jumped: bool


def _landing(result: RunResult, amps: float) -> _Landing:
    time = result.real("time")
    instants, ranges = common.range_changes(result)
    reads = measure.settling_time(time, _reading(result), amps, _BAND * amps, common.STEP_AT)
    return _Landing(
        ranges=tuple(int(value) for value in ranges),
        instants=tuple(float(value - common.STEP_AT) for value in instants),
        final=int(common.settled_range(result)[-1]),
        reads=reads,
        shortest=float(np.min(np.diff(instants))) if instants.size > 1 else float("inf"),
        jumped=bool(np.max(result.real("cmp_jump")) > common.HALF_LOGIC),
    )


def _digits(ranges: tuple[int, ...]) -> float:
    """The ranges of a run as one number: 123 for range 1, then 2, then 3."""
    return float("".join(str(value) for value in ranges) or "0")


@bench(
    "range_logic",
    "landing",
    "Load steps with a capacitor at the load: the range reached and the time to a true reading",
    "sections 4.3 and 4.4 (step up, blanking, jump), requirement R-07",
)
def landing(ctx: Context) -> Outcome:
    """The load steps from 1 uA to 150 uA, 5 mA and 80 mA beside a capacitor.

    A capacitor at the load supplies a step at first, and the ladder sees
    the voltage by which that capacitor has sagged, not the load current
    times a shunt. The sequencer therefore acts on the sag. The runs take
    100 nF, 1 uF, 10 uF and 100 uF and read which ranges the sequencer
    passes, where it stays, and how long it takes until the current that
    the amplifier output stands for is the load current within 1 %. No
    request to step down is made: what firmware does afterwards is not in
    these runs.
    """
    keys = [(step, capacitor) for step in _STEPS for capacitor in _CAPACITORS]
    kept = ("80ma", "10uf")
    results = {kept: ctx.run("80ma-10uf", _deck(ctx, *kept))}
    others = ctx.run_many(
        {
            f"{step}-{capacitor}": _deck(ctx, step, capacitor)
            for step, capacitor in keys
            if (step, capacitor) != kept
        }
    )
    results.update({key: others[f"{key[0]}-{key[1]}"] for key in keys if key != kept})
    found = {key: _landing(results[key], _STEPS[key[0]]) for key in keys}

    figures: list[Figure] = []
    for key in keys:
        step, capacitor = key
        text = _labels(step, capacitor)
        entry = found[key]
        name = f"{step}_{capacitor}"
        figures += [
            Figure(
                f"final_{name}",
                f"{text}: range at the end",
                float(entry.final),
                "",
                expected=float(_PROPER[step]),
            ),
            Figure(
                f"passed_{name}",
                f"{text}: ranges passed, as digits in their order",
                _digits(entry.ranges),
                "",
            ),
            Figure(
                f"reads_{name}",
                f"{text}: reading within 1 % of the load after",
                entry.reads,
                "s",
            ),
        ]
    above = sum(found[key].final > _PROPER[key[0]] for key in keys)
    spaced = [entry.shortest for entry in found.values() if not entry.jumped]
    figures += [
        Figure(
            "above_proper",
            "Runs that end above the range of their current, of 12",
            float(above),
            "",
        ),
        Figure(
            "final_reading",
            "Largest distance of the reading from the load at the end of a run",
            max(
                abs(float(_reading(results[key])[-1]) - _STEPS[key[0]]) / _STEPS[key[0]]
                for key in keys
            )
            * 100.0,
            "%",
            high=100.0 * _BAND,
            source="limit of this bench: every run is long enough to settle",
        ),
        Figure(
            "shortest_step",
            "Shortest time between two steps in the runs without a jump",
            min(spaced) if spaced else float("nan"),
            "s",
            expected=3e-6,
            low=3e-6,
            source="rule F-17: 1 us of overlap and 2 us of blanking between two steps",
        ),
    ]

    def over_time(name: str, title: str, ylabel: str, ratio: bool) -> Graph:
        traces: list[Trace] = []
        for panel, step in enumerate(_STEPS):
            for capacitor in _CAPACITORS:
                result = results[(step, capacitor)]
                time = result.real("time")
                shown = time > common.STEP_AT + 20e-9
                micro = (time[shown] - common.STEP_AT) * 1e6
                if ratio:
                    values = np.clip(_reading(result)[shown] / _STEPS[step], 0.0, 3.0)
                else:
                    values = common.settled_range(result)[shown]
                label = _labels(step, capacitor).split(" with ")[1]
                traces.append(Trace(micro, np.asarray(values, dtype=np.float64), label, panel))
        return Graph(
            name=name,
            title=title,
            xlabel="Time after the load step (us)",
            panels=tuple(
                Panel(
                    f"{ylabel}, step to {_labels(step, '1uf').split(' with ')[0]}",
                    marks=((1.0, "load current"),) if ratio else (),
                )
                for step in _STEPS
            ),
            traces=tuple(traces),
            logx=True,
        )

    ranges = over_time(
        "ranges", "The selected range after a load step, by capacitor", "Range", ratio=False
    )
    readings = over_time(
        "readings",
        "The reading over the load current after a load step, by capacitor (cut at 3)",
        "Reading / load",
        ratio=True,
    )
    detail = results[kept]
    time = detail.real("time")
    first = common.STEP_AT + found[kept].instants[0]
    shown = (time >= first - 3e-6) & (time <= first + 12e-6)
    micro = (time[shown] - first) * 1e6
    climb = Graph(
        name="climb",
        title="1 uA to 80 mA beside 10 uF: three steps up, one blanking time apart",
        xlabel="Time after the first step up (us)",
        panels=(
            Panel(
                "Voltage (mV)",
                marks=((151.2, "jump"), (90.95, "step up")),
            ),
            Panel("Selected range and CMP_UP"),
            Panel("Branch current (A)"),
        ),
        traces=(
            Trace(micro, common.ladder(detail)[shown] * 1e3, "ladder, supply node to load", 0),
            Trace(
                micro, (detail.real("inp") - detail.real("inn"))[shown] * 1e3, "at the amplifier", 0
            ),
            Trace(micro, common.settled_range(detail)[shown], "range", 1),
            Trace(micro, detail.real("cmp_up")[shown] / frontend.LOGIC_VOLTS, "CMP_UP", 1, "--"),
            Trace(micro, detail.real("@r104[i]")[shown], "33 ohm branch", 2),
            Trace(micro, detail.real("@r107[i]")[shown], "1 ohm branch", 2),
            Trace(micro, common.branch_r3(detail)[shown], "0.1 ohm branch", 2),
            Trace(micro, detail.real("iprog")[shown], "load", 2, ":"),
        ),
    )
    notes = (
        "The range of a current is the lowest one whose full scale lies above "
        "it: range 1 for 150 uA, range 2 for 5 mA and for 80 mA. The "
        "specification promises no range after a step; the figures carry that "
        "range as the expected value and no limit.",
        "A step up comes when the capacitor has sagged by 91 mV, whatever the "
        "current. The new shunt then sees those 91 mV as well and recharges the "
        "capacitor with them; while its voltage stays above the threshold after "
        "the blanking time, the sequencer takes the next step. With enough "
        "capacitance it so passes the range of the current.",
        "Until the capacitor is back at its voltage the shunt carries the load "
        "and the recharge. The reading is the current into the node, which is "
        "what a shunt can measure; in range 0 with 100 uF that takes a tenth of "
        "a second.",
        "Firmware would step down again 100 samples after the current fell "
        "below the level of the range (60 mA, 1.8 mA, 60 uA). A current between "
        "the step-down level of a range and the step-up level of the one below "
        "stays where the step left it: 80 mA in range 3 reads with a resolution "
        "of 19 uA and an offset allowance of 1 mA, where range 2 gives 1.9 uA "
        "and 0.1 mA.",
        "The model of the sequencer takes the next step 2.96 us after the one "
        "before, 1.2 % short of the 3 us that its parameters ask for: its delay "
        "element switches a little before its time has passed. That is a property "
        "of the model and says nothing about a program.",
        "The amplifier and the comparators have no noise here, and the "
        "comparator hysteresis is the 2 mV of the model. A real comparator that "
        "rests within its hysteresis of the threshold after a step may or may "
        "not ask for the next one.",
        "The load is a current sink beside the capacitor (5 mohm in series); "
        "the source holds 5 V behind 20 mohm.",
        common.VENDOR_NOTE,
    )
    return Outcome(tuple(figures), (ranges, readings, climb), notes)
