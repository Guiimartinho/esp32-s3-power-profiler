"""A slow ramp of the load from microamperes to an ampere and back."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches import frontend
from benches.range_logic import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_FLOOR, _TOP = 1e-6, 1.0
"""Ends of the ramp, A."""

_DECADE = 10e-3
"""Time the ramp takes for one decade of current, s."""

_START = 0.5e-3
"""Rest before the ramp, s."""

_HOLD = 2e-3
"""Time at the top of the ramp, s."""

_DECADES = float(np.log10(_TOP / _FLOOR))
_UP_END = _START + _DECADES * _DECADE
_DOWN_START = _UP_END + _HOLD
_DOWN_END = _DOWN_START + _DECADES * _DECADE
_END = _DOWN_END + 1.5e-3

_SWITCH_DOWN = (60e-3, 1.8e-3, 60e-6)
"""Levels below which firmware asks for a step down, from range 3 (section 4.3)."""

_SAMPLES_BELOW = 1e-3
"""Time firmware waits below a level: 100 samples at 100 kSPS (section 4.4)."""

_REQUEST = 1e-6
"""Width of a step-down request, s."""

_BLANKED = 3e-6
"""Shortest time between two steps: 1 us of overlap and 2 us of blanking (rule F-17)."""

_READ_AT = (30e-6, 1e-3, 30e-3, 0.3)
"""Load currents at which the reading is compared with the load, one per range."""


def _current(time: np.ndarray) -> np.ndarray:
    """The load current of the ramp at given instants."""
    up = _FLOOR * 10.0 ** ((time - _START) / _DECADE)
    down = _TOP * 10.0 ** (-(time - _DOWN_START) / _DECADE)
    return np.clip(np.where(time < _DOWN_START, up, down), _FLOOR, _TOP)


def _ramp() -> str:
    """The ramp as a piecewise linear waveform, 40 points per decade."""
    steps = int(40 * _DECADES)
    rising = np.linspace(_START, _UP_END, steps + 1)
    falling = np.linspace(_DOWN_START, _DOWN_END, steps + 1)
    instants = np.concatenate(([0.0], rising, falling, [_END]))
    return common.pwl(tuple(zip(instants, _current(instants), strict=True)))


def _requests() -> tuple[str, tuple[float, ...]]:
    """The step-down requests of firmware and their instants.

    Firmware asks for one step when the current has been below the level of
    the range for 100 samples. On this ramp that is 1 ms after the current
    falls through the level.
    """
    instants = tuple(
        _DOWN_START + _DECADE * float(np.log10(_TOP / level)) + _SAMPLES_BELOW
        for level in _SWITCH_DOWN
    )
    points: list[tuple[float, float]] = [(0.0, 0.0)]
    for instant in instants:
        points += [
            (instant, 0.0),
            (instant + 10e-9, frontend.LOGIC_VOLTS),
            (instant + _REQUEST, frontend.LOGIC_VOLTS),
            (instant + _REQUEST + 10e-9, 0.0),
        ]
    return common.pwl(points), instants


def _deck(ctx: Context, capacitance: float | None, title: str) -> str:
    circuit = common.front_end(ctx)
    requests, _ = _requests()
    return ctx.deck(
        title,
        circuit,
        frontend.rails(),
        common.source(5.0),
        common.controller(down=requests),
        common.dut(_ramp(), capacitance),
        common.rest(circuit, 0),
        control=[f"save {common.SAVED} seq_down", f"tran 2u {_END:g}"],
        options=common.options(ctx),
        libraries=frontend.SEQUENCER_LIBRARIES,
    )


@dataclass(frozen=True, slots=True)
class _Climb:
    """What one ramp shows.

    Attributes:
        instants: Instants of the range changes, s.
        ranges: The range after each change.
        through_shunt: Current through the ladder at each step up, A.
        load: Load current at each step up, A.
        shortest: Shortest time between two changes, s.
        jump_high: Longest time the jump comparator was high, s.
    """

    instants: np.ndarray
    ranges: np.ndarray
    through_shunt: tuple[float, ...]
    load: tuple[float, ...]
    shortest: float
    jump_high: float


def _ladder_current(result: RunResult) -> np.ndarray:
    """The current through all branches of the ladder."""
    names = ("@r101[i]", "@r104[i]", "@r107[i]", "@r110[i]")
    return np.asarray(sum(result.real(name) for name in names), dtype=np.float64)


def _climb(result: RunResult) -> _Climb:
    time = result.real("time")
    instants, ranges = common.range_changes(result)
    total = _ladder_current(result)
    ups = [index for index in range(instants.size) if instants[index] < _DOWN_START]
    # The current just before a step: 0.2 us earlier the old range still stands.
    through = tuple(measure.value_at(time, total, instants[index] - 0.2e-6) for index in ups)
    load = tuple(float(_current(np.array([instants[index]]))[0]) for index in ups)
    shortest = float(np.min(np.diff(instants))) if instants.size > 1 else float("inf")
    jump_high = common.high_time(time, result.real("cmp_jump"), float(time[0]), float(time[-1]))
    return _Climb(instants, ranges, through, load, shortest, jump_high)


def _reading(result: RunResult, amps: float) -> float:
    """The current the amplifier output stands for, on the way up at a load current."""
    time = result.real("time")
    instant = _START + _DECADE * float(np.log10(amps / _FLOOR))
    output = measure.value_at(time, result.real("amp_raw"), instant)
    index = int(measure.value_at(time, common.range_index(result), instant) + 0.5)
    return (output - common.PEDESTAL) / common.GAIN / frontend.SHUNT_OHMS[index]


def _zoom(result: RunResult, instant: float, name: str, title: str) -> Graph:
    """One step up at close range: lines, gates, sense voltage, amplifier."""
    time = result.real("time")
    shown = (time >= instant - 1.5e-6) & (time <= instant + 6.5e-6)
    micro = (time[shown] - instant) * 1e6

    def cut(node: str) -> np.ndarray:
        return result.real(node)[shown]

    return Graph(
        name=name,
        title=title,
        xlabel="Time after the address changes (us)",
        panels=(
            Panel("Comparator and controller lines (V)"),
            Panel("Gates of the switches (V)"),
            Panel("Sense voltage at the amplifier (mV)", marks=((90.95, "step up 91 mV"),)),
            Panel("Amplifier output (V)"),
        ),
        traces=(
            Trace(micro, cut("cmp_up"), "CMP_UP", 0),
            Trace(micro, cut("mux_a0"), "MUX_A0", 0, "--"),
            Trace(micro, cut("mux_a1"), "MUX_A1", 0, "--"),
            Trace(micro, cut("gate_r1"), "GATE_R1", 0, ":"),
            Trace(micro, cut("gate_r2"), "GATE_R2", 0, ":"),
            Trace(micro, cut("g_r1"), "gate of Q12 (range 1)", 1),
            Trace(micro, cut("g_r2"), "gate of Q13 (range 2)", 1),
            Trace(micro, (cut("inp") - cut("inn")) * 1e3, "INP - INN", 2),
            Trace(
                micro, common.ladder(result)[shown] * 1e3, "ladder, supply node to load", 2, "--"
            ),
            Trace(micro, cut("amp_raw"), "AMP_RAW", 3),
        ),
        xmarks=((1.0, "old gate off"), (3.0, "blanking ends")),
    )


@bench(
    "range_logic",
    "ramp",
    "A slow ramp from 1 uA to 1 A and back: one range at a time, no bounce",
    "section 4.4 (step up, blanking, step down), rule F-17, requirement R-07",
)
def ramp(ctx: Context) -> Outcome:
    """The load current rises from 1 uA to 1 A in 60 ms and falls again.

    The ramp takes 10 ms for every decade, slow against every delay of the
    loop. On the way up the step-up comparator moves the sequencer; on the
    way down the bench plays firmware and asks for one step down 1 ms after
    the current has fallen below the level of the range (60 mA, 1.8 mA,
    60 uA), which is the 100 samples of the rule. The run counts the range
    changes, reads the current at which each step up comes and the shortest
    time between two changes, and compares the reading that the amplifier
    output stands for with the load in the middle of every range. It is made
    without a capacitor at the terminals and with 1 uF.
    """
    plain = ctx.run("no-capacitor", _deck(ctx, None, "Slow ramp, no capacitor at the terminals"))
    loaded = ctx.run("with-1uf", _deck(ctx, 1e-6, "Slow ramp, 1 uF at the terminals"))
    found = {"none": _climb(plain), "1uf": _climb(loaded)}
    band = common.THRESHOLD_BAND["up"]
    shunts = frontend.SHUNT_OHMS
    figures: list[Figure] = []
    for key, text in (("none", "no capacitor"), ("1uf", "1 uF")):
        climb = found[key]
        figures += [
            Figure(
                f"changes_{key}",
                f"Range changes on the whole ramp, {text}",
                float(climb.instants.size),
                "",
                expected=6.0,
                low=6.0,
                high=6.0,
                source="section 4.4: three steps up, three steps down, none back",
            ),
            Figure(
                f"order_{key}",
                f"Ranges in the order 1, 2, 3, 2, 1, 0, {text} (1 when so)",
                float(np.array_equal(climb.ranges, [1, 2, 3, 2, 1, 0])),
                "",
                low=1.0,
                high=1.0,
                source="section 4.4: a slow rise climbs range by range",
            ),
            Figure(
                f"shortest_{key}",
                f"Shortest time between two range changes, {text}",
                climb.shortest,
                "s",
                low=_BLANKED,
                source="rule F-17: 1 us of overlap and 2 us of blanking",
            ),
            Figure(
                f"jump_{key}",
                f"Longest time the jump comparator is high, {text}",
                climb.jump_high,
                "s",
                high=0.0,
                source="section 4.4: a slow rise does not reach the jump threshold",
            ),
        ]
        for index, amps in enumerate(climb.through_shunt[:3]):
            expected = common.THRESHOLD_SHUNT["up"] / shunts[index]
            figures.append(
                Figure(
                    f"leaves_r{index}_{key}",
                    f"Current through the ladder when range {index} is left, {text}",
                    amps,
                    "A",
                    expected=expected,
                    low=band[0] / shunts[index],
                    high=band[1] / shunts[index],
                    source="section 4.3, switch up above: 91 uA, 2.85 mA, 91 mA",
                )
            )
        for index, amps in enumerate(climb.load[:3]):
            figures.append(
                Figure(
                    f"load_r{index}_{key}",
                    f"Load current at that instant, {text}",
                    amps,
                    "A",
                    expected=common.THRESHOLD_SHUNT["up"] / shunts[index],
                )
            )
    for index, amps in enumerate(_READ_AT):
        for key, text, result in (("none", "no capacitor", plain), ("1uf", "1 uF", loaded)):
            error = 100.0 * (_reading(result, amps) - amps) / amps
            limited = key == "none"
            figures.append(
                Figure(
                    f"reading_r{index}_{key}",
                    f"Reading against the load at {amps * 1e3:g} mA on the way up, {text}",
                    error,
                    "%",
                    low=-5.0 if limited else None,
                    high=5.0 if limited else None,
                    source="limit of this bench: the ramp is slow enough for the node "
                    "after the shunts alone"
                    if limited
                    else "",
                )
            )

    def staircase(result: RunResult, name: str, title: str) -> Graph:
        time = result.real("time")
        milli = time * 1e3
        sense = (result.real("inp") - result.real("inn")) * 1e3
        return Graph(
            name=name,
            title=title,
            xlabel="Time (ms)",
            panels=(
                Panel("Current (A)", log=True),
                Panel("Selected range"),
                Panel(
                    "Sense voltage at the amplifier (mV)",
                    marks=((90.95, "step up 91 mV"), (151.2, "jump 151 mV")),
                ),
                Panel("Amplifier output (V)"),
            ),
            traces=(
                Trace(milli, np.maximum(_current(time), 1e-7), "load", 0),
                Trace(milli, np.maximum(_ladder_current(result), 1e-7), "through the ladder", 0),
                Trace(milli, common.settled_range(result), "from MUX_A1 and MUX_A0", 1),
                Trace(
                    milli, result.real("seq_down") / frontend.LOGIC_VOLTS, "step-down request", 1
                ),
                Trace(milli, sense, "INP - INN", 2),
                Trace(milli, result.real("amp_raw"), "AMP_RAW", 3),
            ),
        )

    whole = staircase(plain, "staircase", "1 uA to 1 A and back, no capacitor at the terminals")
    with_cap = staircase(loaded, "staircase-1uf", "The same ramp with 1 uF at the terminals")
    step = _zoom(
        plain,
        float(found["none"].instants[1]),
        "step",
        "The step from range 1 to range 2 at 2.85 mA, no capacitor at the terminals",
    )
    notes = (
        "The sequencer is the model of rules F-16 to F-18. It steps down on a "
        "request only; the requests are placed by this bench where firmware would "
        "issue them and are not the work of a program.",
        "With 1 uF at the terminals the shunt of range 0 and that capacitor have a "
        "time constant of 1.1 ms: on a ramp of 10 ms per decade the current "
        "through the ladder lags the load by about a quarter, and range 0 is left "
        "at a load current that much above 91 uA. The figures without a limit show "
        "it. The instrument measures the current into the node; the capacitor "
        "supplies the rest.",
        "The reading is the amplifier output minus the pedestal, divided by the "
        "gain and the shunt of the selected range. Without a capacitor it trails "
        "the ramp by the time constant of the shunt with the 100 nF after the "
        "shunts, 2.3 % in range 0 at this rate.",
        "The source holds 5 V behind 20 mohm. The amplifier and the comparators "
        "have no noise in these runs: a real ramp that rests at a threshold for "
        "long would see the comparator output chatter inside its hysteresis, "
        "which the blanking bounds to one step.",
        common.VENDOR_NOTE,
    )
    return Outcome(tuple(figures), (whole, with_cap, step), notes)
