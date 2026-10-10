"""Load steps on the source: droop, recovery and head room."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.source_meter import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_IDLE = 10e-6
"""Current of the device before and after the step."""

_STEP = 15e-3
"""Instant of the step, after the power-up run has come to rest."""

_RELEASE = 18e-3
"""Instant at which the device returns to its idle current."""

_STOP = 24e-3
_EDGE = 1e-6
"""End of the run and edge of the load current."""

_CAPACITORS = (1e-6, 10e-6, 100e-6)
"""Capacitance beside the device under test."""

_CURVE_FARADS = 10e-6
"""Capacitance beside the device in the steps to each point of the curve."""

_FEEDBACK_LOW = 0.495
"""Lowest feedback reference of the converter in forced PWM (SLVS916I, page 6)."""

_BAND = 5e-3
"""Band around the final value in which the output counts as recovered (this bench)."""

_OVERLOAD_VOLTS = 0.3
_OVERLOAD_SECONDS = 20e-3
"""Rule F-32: more than 0.3 V below the set-point for 20 ms is an overload."""

_REVERSE_LIMIT = -0.3
"""Rating of the IN pin relative to the output (LT3080 Rev. E, page 2)."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One load step.

    Attributes:
        volts: Set-point.
        amps: Current of the device after the step.
        index: Range whose shunt stands in the path.
    """

    volts: float
    amps: float
    index: int

    @property
    def tag(self) -> str:
        return f"{self.volts:g}v_{self.amps * 1e3:g}ma".replace(".", "p")

    @property
    def text(self) -> str:
        return f"{self.volts:g} V, {_IDLE * 1e6:g} uA to {self.amps * 1e3:g} mA"


_CASES = (
    _Case(0.8, 0.1, 2),
    _Case(0.8, 1.0, 3),
    _Case(5.0, 0.1, 2),
    _Case(5.0, 0.6, 3),
)
"""The steps: to 100 mA in range 2 and to the current of the R-08 curve in range 3."""


def _deck(
    ctx: Context, case: _Case, farads: float, models: dict[str, PartModel] | None = None
) -> str:
    load = (
        f"PWL(0 {_IDLE:g} {_STEP:g} {_IDLE:g} {_STEP + _EDGE:g} {case.amps:g} "
        f"{_RELEASE:g} {case.amps:g} {_RELEASE + _EDGE:g} {_IDLE:g})"
    )
    circuit = common.source(
        ctx,
        case.volts,
        overrides={
            common.DAC: common.power_up_code(ctx, common.code_of(case.volts)),
            **(models or {}),
        },
        scales={"C41": common.SETTLE_FILTER},
    )
    return ctx.deck(
        f"Load step at {case.text}, {farads * 1e6:g} uF at the device",
        circuit,
        common.power_up_rails(),
        common.power_up_controller(),
        common.dut(case.index, load, farads),
        control=[f"tran 0.2u {_STOP:g} 0 1u"],
    )


def _deviation(run: RunResult, name: str, reference: float) -> np.ndarray:
    return run.real(name) - reference


def _figures(run: RunResult, case: _Case, farads: float) -> list[Figure]:
    """The figures of one run."""
    time = run.real("time")
    out = run.real("ldo_out")
    terminal = run.real("dut")
    headroom = run.real("ldo_in") - out
    rest = measure.mean(time, out, _STEP - 1e-3, _STEP)
    loaded = measure.mean(time, out, _RELEASE - 0.2e-3, _RELEASE)
    terminal_loaded = measure.mean(time, terminal, _RELEASE - 0.2e-3, _RELEASE)
    lowest = measure.extremes(time, out, _STEP, _RELEASE)[0]
    terminal_lowest = measure.extremes(time, terminal, _STEP, _RELEASE)[0]
    highest = measure.extremes(time, out, _RELEASE, _STOP)[1]
    recovered = measure.settling_time(time, out, loaded, _BAND, _STEP, _RELEASE)
    low_headroom = measure.extremes(time, headroom, _STEP, _STOP)[0]
    below = (time >= _STEP) & (out < rest - _OVERLOAD_VOLTS)
    seconds_below = float(np.sum(np.diff(time)[below[:-1]])) if np.any(below) else 0.0
    tail = measure.peak_to_peak(time, out, _STOP - 1e-3, _STOP)
    tag = f"{case.tag}_{farads * 1e6:g}uf"
    text = f"{case.text}, {farads * 1e6:g} uF"
    return [
        Figure(
            f"droop_{tag}",
            f"{text}: lowest regulator output below its value before the step",
            rest - lowest,
            "V",
        ),
        Figure(
            f"terminal_{tag}",
            f"{text}: lowest terminal voltage below its final value under load",
            terminal_loaded - terminal_lowest,
            "V",
        ),
        Figure(
            f"recovery_{tag}",
            f"{text}: regulator output within 5 mV of its loaded value after",
            recovered,
            "s",
        ),
        Figure(
            f"overshoot_{tag}",
            f"{text}: highest regulator output above its idle value after the release",
            highest - rest,
            "V",
        ),
        Figure(
            f"headroom_{tag}",
            f"{text}: lowest voltage of the IN pin above the output",
            low_headroom,
            "V",
            low=_REVERSE_LIMIT,
            source="LT3080 Rev. E, page 2: IN not more than 0.3 V below the output (D-57)",
        ),
        Figure(
            f"overload_{tag}",
            f"{text}: time the output spends more than 0.3 V below its value",
            seconds_below,
            "s",
            high=_OVERLOAD_SECONDS,
            source="rule F-32: 20 ms of that is reported as an overload",
        ),
        Figure(
            f"tail_{tag}",
            f"{text}: movement of the output in the last millisecond, at idle",
            tail,
            "V",
        ),
    ]


def _graph(case: _Case, runs: dict[float, RunResult]) -> Graph:
    """The waveforms of one case with its three capacitors."""
    traces: list[Trace] = []
    for farads, run in runs.items():
        time = run.real("time")
        shown = (time >= _STEP - 0.2e-3) & (time <= _RELEASE + 2.5e-3)
        axis = (time[shown] - _STEP) * 1e3
        label = f"{farads * 1e6:g} uF"
        rest = measure.mean(time, run.real("ldo_out"), _STEP - 1e-3, _STEP)
        traces += [
            Trace(axis, (run.real("ldo_out")[shown] - rest) * 1e3, label, 0),
            Trace(axis, run.real("dut")[shown], label, 1),
            Trace(axis, (run.real("ldo_in") - run.real("ldo_out"))[shown] * 1e3, label, 2),
            Trace(axis, run.real(f"v.x{common.REGULATOR.lower()}.vic#branch")[shown], label, 3),
        ]
    return Graph(
        name=f"step-{case.tag}".replace("_", "-"),
        title=f"Load step at {case.text}, by the capacitance at the device",
        xlabel="Time after the step (ms)",
        panels=(
            Panel("Regulator output, deviation (mV)"),
            Panel("Terminal (V)"),
            Panel("IN pin above the output (mV)"),
            Panel("Current of the IN pin (A)"),
        ),
        traces=tuple(traces),
        xmarks=((0.0, "step"), ((_RELEASE - _STEP) * 1e3, "release")),
    )


def _zoom(case: _Case, runs: dict[float, RunResult]) -> Graph:
    """The first 200 us after the step."""
    traces: list[Trace] = []
    for farads, run in runs.items():
        time = run.real("time")
        shown = (time >= _STEP - 10e-6) & (time <= _STEP + 200e-6)
        axis = (time[shown] - _STEP) * 1e6
        label = f"{farads * 1e6:g} uF"
        rest = measure.mean(time, run.real("ldo_out"), _STEP - 1e-3, _STEP)
        traces += [
            Trace(axis, (run.real("ldo_out")[shown] - rest) * 1e3, label, 0),
            Trace(axis, run.real("dut")[shown], label, 1),
            Trace(axis, run.real("v_pre")[shown], label, 2),
        ]
    return Graph(
        name=f"zoom-{case.tag}".replace("_", "-"),
        title=f"The first 200 us of the load step at {case.text}",
        xlabel="Time after the step (us)",
        panels=(
            Panel("Regulator output, deviation (mV)"),
            Panel("Terminal (V)"),
            Panel("Pre-regulator output (V)"),
        ),
        traces=tuple(traces),
    )


@bench(
    "source_meter",
    "load-step",
    "Load steps from microamperes to 100 mA and to the curve: droop, recovery, head room",
    "section 4.2 (output capacitor, head room), rule F-32, decision D-57, requirement R-08",
)
def load_step(ctx: Context) -> Outcome:
    """The source is powered up, comes to rest, and its load is stepped up and back.

    The device under test draws 10 uA, steps to 100 mA or to the current of
    the curve of requirement R-08 within 1 us, and returns after 3 ms. The
    runs are made at 0.8 V and at 5.0 V with 1 uF, 10 uF and 100 uF beside
    the device. They show the droop of the regulator output and of the
    terminal, the recovery, the overshoot at the release, and the head room
    of the regulator while the pre-regulator answers the step. Steps to
    each of the four points of the curve, with 10 uF, are repeated with a
    regulator at the guaranteed dropout.
    """
    figures: list[Figure] = []
    graphs: list[Graph] = []
    decks = {
        f"{case.tag}-{farads * 1e6:g}uf".replace("_", "-"): _deck(ctx, case, farads)
        for case in _CASES
        for farads in _CAPACITORS
    }
    kept = {"0p8v-1000ma-10uf", "5v-600ma-10uf"}
    runs = {name: ctx.run(name, decks[name]) for name in kept}
    runs.update(ctx.run_many({name: deck for name, deck in decks.items() if name not in kept}))
    for case in _CASES:
        by_capacitor = {
            farads: runs[f"{case.tag}-{farads * 1e6:g}uf".replace("_", "-")]
            for farads in _CAPACITORS
        }
        for farads, run in by_capacitor.items():
            figures += _figures(run, case, farads)
        graphs.append(_graph(case, by_capacitor))
        if case.index == 3:
            graphs.append(_zoom(case, by_capacitor))
    worst = {
        common.REGULATOR: common.part(ctx, common.REGULATOR, **common.LIMIT_DROPOUT),
        common.CONVERTER: common.part(ctx, common.CONVERTER, vref=_FEEDBACK_LOW),
    }
    curve = ctx.run_many(
        {
            f"curve-{volts:g}v-{name}".replace(".", "p"): _deck(
                ctx, _Case(volts, amps, 3), _CURVE_FARADS, models
            )
            for volts, amps in common.CURVE
            for name, models in (("typical", None), ("limit", worst))
        }
    )
    for volts, amps in common.CURVE:
        tag = f"{volts:g}v".replace(".", "p")
        need = common.DROPOUT_OFFSET + common.DROPOUT_OHMS * amps
        droop = {}
        for name in ("typical", "limit"):
            run = curve[f"curve-{tag}-{name}"]
            time, out = run.real("time"), run.real("ldo_out")
            rest = measure.mean(time, out, _STEP - 1e-3, _STEP)
            droop[name] = rest - measure.extremes(time, out, _STEP, _RELEASE)[0]
        limit_run = curve[f"curve-{tag}-limit"]
        clock = limit_run.real("time")
        headroom = limit_run.real("ldo_in") - limit_run.real("ldo_out")
        text = f"{volts:g} V, 10 uA to {amps * 1e3:g} mA, 10 uF"
        figures += [
            Figure(
                f"curve_droop_{tag}",
                f"{text}: droop of the regulator output, typical regulator",
                droop["typical"],
                "V",
            ),
            Figure(
                f"curve_droop_limit_{tag}",
                f"{text}: droop with the regulator at the guaranteed dropout and the "
                "feedback reference at 495 mV",
                droop["limit"],
                "V",
            ),
            Figure(
                f"curve_margin_{tag}",
                f"{text}: lowest head room above the dropout need during that step",
                measure.extremes(clock, headroom, _STEP, _RELEASE)[0] - need,
                "V",
            ),
            Figure(
                f"curve_margin_rest_{tag}",
                f"{text}: head room above the dropout need at rest under load",
                measure.mean(clock, headroom, _RELEASE - 0.2e-3, _RELEASE) - need,
                "V",
                low=0.0,
                source="section 4.2, table of the curve: the margin is positive at rest",
            ),
        ]
    notes = (
        "The specification states no limit for the droop of the source at a load step; "
        "those figures carry none. The two limits are the rating of the IN pin and "
        "the overload time of rule F-32.",
        "The path to the device is three resistors for one range: range 2 for the steps "
        "to 100 mA, range 3 for the steps to the curve. The range logic, which starts "
        "such a step in a lower range and jumps, belongs to another block; here the "
        "path does not change.",
        "The regulator is the model fitted to the load steps of its datasheet. It dips "
        "less than the datasheet for a step of 1 A and more for a step of 200 mA with "
        "10 uF; the droop figures carry that error, about 30 % either way.",
        "After the release the regulator cannot take current back: the output stays "
        "above its value until the minimum load has emptied the capacitors, some "
        "tenths of a millisecond, and then rings for a few periods near 10 kHz. That "
        "ringing follows from the low phase margin of the model at light load, which "
        "is an extrapolation and not a datasheet value.",
        "The margin during a step is not a figure of the specification: its table of "
        "the curve is static. The last figures show how much of that static margin "
        "the dip of the pre-regulator takes for some tens of microseconds, with the "
        "regulator at the guaranteed dropout and the feedback reference of the "
        "converter at its lower limit.",
        "The converter is the averaged model with a loop fitted to the model of its "
        "manufacturer: the dip of the pre-regulator is the answer of that loop, without "
        "switching ripple. The capacitor at the device is a ceramic part with 5 mohm.",
    )
    return Outcome(tuple(figures), tuple(graphs), notes)
