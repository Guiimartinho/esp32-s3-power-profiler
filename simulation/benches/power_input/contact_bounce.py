"""A contact of the USB-C cable opens and closes again: what reaches the multiplexer."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_PLUG = 0.1e-3
"""Instant at which the source is plugged."""

_OPEN = common.RUNNING_AT + 0.5e-3
"""Instant at which the contact of a running carrier opens."""

_AFTER = 0.9e-3
"""Time a run goes on after the contact has closed again. It ends before the
shortened supervisor would release the carrier a second time."""

_GAPS = (20e-6, 100e-6, 0.3e-3, 1e-3, 3e-3, 20e-3)
"""Times for which the contact of a running carrier stays open (section 16:
20 us to 20 ms)."""

_TYPICAL_GAPS = (100e-6, 3e-3)
"""Gaps that are also run with the typical limiter and the longer cable."""

_LOADED_GAPS = (20e-6, 100e-6, 0.3e-3)
"""Gaps that are repeated with the source meter at full power."""

_START_OPEN = _PLUG + 0.9e-3
"""Instant at which the contact opens in the runs that bounce during the
start: the limiter has charged its output, the multiplexer still waits."""

_START_CLOSES = (1.45e-3, 1.5e-3, 1.55e-3, 1.6e-3, 1.65e-3, 1.75e-3)
"""Times after the plug at which the contact closes again in those runs. The
multiplexer begins to charge the rail about 1.4 ms after the plug, from the
capacitors behind the limiter alone."""

_SOURCE_VOLTS = 5.5
"""Highest voltage of the supply range at the receptacle (section 4.1)."""

_LOAD_WATTS = 6.3
"""Power of the pre-regulator at full output (the estimate of section 4.1)."""

_TP2_LIMIT = 5.8
"""Level that input 1 of the multiplexer has to stay below (section 16)."""

_INPUT_RATING = 6.0
"""Absolute maximum of the inputs and the output of the multiplexer and of
the input of the 3.3 V regulators (TPS2116 datasheet SLVSFG1A, page 4;
LP5907 datasheet SNVS798Q, page 4)."""

_STEP = 0.5e-6
"""Longest time step. The highest level of input 1 does not depend on it
between 0.1 us and 1 us; the peak of the ring at the receptacle does, by
about 0.2 V."""

_LONG_STEP = 1e-6
"""Longest time step of the runs with a gap of 20 ms."""

_SAVE = "save vbus_c vin1 vin2 rail ok5v v3a pr1 dvdt_c i(Vusbc_i)"
"""What a run keeps: the long ones would fill the disk with everything."""

_SOURCE_NOTE = "section 16: contact interrupted for 20 us to 20 ms, TP2 below 5.8 V"


@dataclass(frozen=True)
class _Corner:
    """One combination of limiter and cable.

    Attributes:
        label: What the figures call it.
        limiter: Parameters of the limiter U4, empty for the typical part.
        ohms: Resistance of the cable with its contacts.
        henries: Inductance of the cable.
    """

    label: str
    limiter: str
    ohms: float
    henries: float


_TYPICAL = _Corner(
    "typical limiter, cable of 0.15 ohm and 0.5 uH", "", common.CABLE_OHMS, common.CABLE_HENRIES
)
_WORST = _Corner("late clamp, cable of 0.08 ohm and 0.3 uH", "vovc=5.83 vclamp=5.61", 0.08, 0.3e-6)
"""The typical case, and the corner that the specification names: a limiter
that clamps as late as its datasheet allows (from 5.83 V at its input, to
5.61 V; SLVSET8A page 6) behind a short cable."""


@dataclass(frozen=True)
class _Case:
    """One run.

    Attributes:
        label: What the figures call it.
        corner: Limiter and cable.
        opens: Instant at which the contact opens.
        closes: Instant at which it closes again.
        loaded: True with the source meter at full power.
    """

    label: str
    corner: _Corner
    opens: float
    closes: float
    loaded: bool = False


def _text(seconds: float) -> str:
    """A time with its unit."""
    return f"{seconds * 1e6:g} us" if seconds < 1e-3 else f"{seconds * 1e3:g} ms"


def _cases() -> dict[str, _Case]:
    """Every run of the bench by name."""
    cases: dict[str, _Case] = {}
    for gap in _GAPS:
        cases[f"run-{_text(gap).replace(' ', '')}"] = _Case(
            f"Running at idle, {_WORST.label}: contact open for {_text(gap)}",
            _WORST,
            _OPEN,
            _OPEN + gap,
        )
    for gap in _TYPICAL_GAPS:
        cases[f"run-typical-{_text(gap).replace(' ', '')}"] = _Case(
            f"Running at idle, {_TYPICAL.label}: contact open for {_text(gap)}",
            _TYPICAL,
            _OPEN,
            _OPEN + gap,
        )
    for gap in _LOADED_GAPS:
        cases[f"run-loaded-{_text(gap).replace(' ', '')}"] = _Case(
            f"Running at full output, {_WORST.label}: contact open for {_text(gap)}",
            _WORST,
            _OPEN,
            _OPEN + gap,
            loaded=True,
        )
    for closes in _START_CLOSES:
        cases[f"start-{closes * 1e3:g}ms".replace(".", "p")] = _Case(
            f"During the start, {_WORST.label}: contact open from 0.9 ms to "
            f"{closes * 1e3:g} ms after the plug",
            _WORST,
            _START_OPEN,
            _PLUG + closes,
        )
    middle = _START_CLOSES[3]
    cases["start-typical"] = _Case(
        f"During the start, {_TYPICAL.label}: contact open from 0.9 ms to "
        f"{middle * 1e3:g} ms after the plug",
        _TYPICAL,
        _START_OPEN,
        _PLUG + middle,
    )
    return cases


def _deck(ctx: Context, case: _Case) -> str:
    """The carrier on a 5.5 V source whose contact opens once and closes again."""
    params = {"U6": common.FAST_SUPERVISOR}
    if case.corner.limiter:
        params["U4"] = case.corner.limiter
    circuit = common.circuit(ctx, common.carrier_refs(ctx.netlist), params=params)
    stimulus = (
        common.usb_c_source(
            _SOURCE_VOLTS,
            _PLUG,
            unplug_at=case.opens,
            replug_at=case.closes,
            ohms=case.corner.ohms,
            henries=case.corner.henries,
        )
        + common.boost_start()
        + common.idle_loads()
    )
    if case.loaded:
        stimulus += "* the pre-regulator as a load of constant power, shed with 5V_OK\n"
        stimulus += common.power_load("smu", "rail", _LOAD_WATTS, common.RUNNING_AT - 0.3e-3)
    step = _LONG_STEP if case.closes - case.opens > 5e-3 else _STEP
    control = [_SAVE, common.transient(step, case.closes + _AFTER)]
    return ctx.deck(case.label, circuit, stimulus, control=control)


def _peak(run: RunResult, name: str, case: _Case) -> float:
    """The highest level of a node after the contact has closed again."""
    time = run.real("time")
    return float(np.max(run.real(name)[common.cut(time, case.closes, case.closes + _AFTER)]))


@bench(
    "power_input",
    "contact-bounce",
    "A contact of the USB-C cable opens and closes again: what reaches the multiplexer",
    "section 4.1 (limits of the USB-C input: a contact that opens and closes again), "
    "section 14, section 16 (contact interrupted for 20 us to 20 ms)",
)
def contact_bounce(ctx: Context) -> Outcome:
    """The carrier is on a 5.5 V source when a contact of the cable opens and closes.

    In the first runs the carrier is running. While the contact is open the
    capacitors of the board feed it and every node falls with them; when
    the contact closes, the cable and the capacitor at the receptacle ring,
    and the limiter passes what reaches it until its current limit acts.
    The rail hangs on input 1 through the multiplexer and takes part. In
    the other runs the contact bounces during the start, when the limiter
    has charged its output and the multiplexer begins to charge the rail
    from the capacitors behind the limiter alone: input 1 then falls fast,
    and the rail does not help to damp the ring. The corner is a limiter
    that clamps as late as its datasheet allows behind a short cable.
    """
    cases = _cases()
    keep = ("run-3ms", "start-1p6ms")
    runs = common.run_all(ctx, {name: _deck(ctx, case) for name, case in cases.items()}, keep=keep)
    figures: list[Figure] = []
    for name, case in cases.items():
        run = runs[name]
        figures.append(
            Figure(
                f"input1_{name.replace('-', '_')}",
                f"{case.label}: highest level of input 1 after the contact has closed",
                _peak(run, "vin1", case),
                "V",
                high=_TP2_LIMIT,
                source=_SOURCE_NOTE,
            )
        )
    for name, case in cases.items():
        if case.corner is not _WORST or case.loaded:
            continue
        run = runs[name]
        figures.append(
            Figure(
                f"before_{name.replace('-', '_')}",
                f"{case.label}: input 1 when the contact closes",
                measure.value_at(run.real("time"), run.real("vin1"), case.closes - 1e-6),
                "V",
            )
        )
    peaks = {name: _peak(runs[name], "vin1", case) for name, case in cases.items()}
    rails = {name: _peak(runs[name], "rail", case) for name, case in cases.items()}
    figures += [
        Figure(
            "input1_highest",
            "Highest level of input 1 after the contact has closed, in all runs",
            max(peaks.values()),
            "V",
            expected=5.945,
            high=_INPUT_RATING,
            source="section 4.1: within 25 mV to 85 mV of the 6 V rating in the worst corners "
            "(simulated before); TPS2116 datasheet, page 4: 6 V",
        ),
        Figure(
            "rail_highest",
            "Highest level of the 5 V rail after the contact has closed, in all runs",
            max(rails.values()),
            "V",
            high=_INPUT_RATING,
            source="TPS2116 and LP5907 datasheets, page 4 of each: 6 V",
        ),
        Figure(
            "rail_over_source",
            "Highest level of the 5 V rail above the source, in all runs",
            max(rails.values()) - _SOURCE_VOLTS,
            "V",
            high=0.0,
            source="section 4.1: the rail never rises above the source",
        ),
        Figure(
            "receptacle_highest",
            "Highest voltage at the receptacle after the contact has closed, in all runs",
            max(_peak(runs[name], "vbus_c", case) for name, case in cases.items()),
            "V",
            high=11.1,
            source="section 4.1: the suppressor conducts from 11.1 V",
        ),
        Figure(
            "cable_highest",
            "Largest current of the cable when the contact closes, in all runs",
            max(_peak(runs[name], "vusbc_i#branch", case) for name, case in cases.items()),
            "A",
        ),
    ]
    graphs = []
    for name, graph_name in (("start-1p6ms", "start"), ("run-3ms", "running")):
        case = cases[name]
        run = runs[name]
        time = run.real("time")
        shown = common.cut(time, case.closes - 20e-6, case.closes + 180e-6)
        micro = (time[shown] - case.closes) * 1e6
        graphs.append(
            Graph(
                name=graph_name,
                title=case.label,
                xlabel="Time after the contact has closed (us)",
                panels=(
                    Panel("Voltage (V)", marks=((_TP2_LIMIT, "5.8 V"),)),
                    Panel("Current of the cable (A)"),
                ),
                traces=(
                    Trace(micro, run.real("vbus_c")[shown], "receptacle", 0),
                    Trace(micro, run.real("vin1")[shown], "input 1 (TP2)", 0),
                    Trace(micro, run.real("rail")[shown], "5 V rail", 0),
                    Trace(micro, run.real("vusbc_i#branch")[shown], "cable", 1),
                ),
            )
        )
    notes = (
        "The source is an ideal 5.5 V behind its cable, and the contact is a conductance "
        "that opens within 1 us and closes within 50 ns: assumptions. A real contact "
        "bounces several times; one opening is simulated.",
        "The cable values are assumptions. The late clamp is the datasheet limit of 5.83 V "
        "at the input with an output level of 5.61 V; the reaction time of the clamp is "
        "the typical 5 us, for which the datasheet states no limit.",
        "The cable of the module is not plugged, so the module is fed from the rail and "
        "empties the board: after a gap of 20 ms input 1 stands at 2.2 V, the limiter has "
        "turned off (2.76 V at the receptacle) and the run ends with a new start. After "
        "the shorter gaps the limiter is still on.",
        "The current through the limiter in the first microseconds after the contact has "
        "closed is bounded by resistances alone in the model, which has no saturation of "
        "the pass transistor; the ring at the receptacle that follows when the limiter "
        "cuts that current back is an upper bound for the same reason.",
        "The ceramic capacitors have the capacitance they keep at 5 V; at a lower voltage "
        "they have more, which these runs do not show.",
        "The supervisor has its release delay shortened to 1 ms, and each run ends before "
        "it would release the carrier again.",
    )
    return Outcome(tuple(figures), tuple(graphs), notes)
