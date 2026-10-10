"""Settling of the chain after a range change."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from benches import frontend
from benches.signal_chain import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_CHANGE = 30e-6
"""Instant at which the address lines of the multiplexer change."""

_END = _CHANGE + 190e-6
"""End of a run: the chain has settled far below one code."""

_EDGE = 5e-9
"""Edge of the address lines at the controller."""

_REST = 50e-3
"""Shunt voltage in the old range before a short overload begins."""

_TENTH_PERCENT = 0.001 * common.VREF
"""0.1 % of the converter range at its input: 2.5 mV, 65.5 codes."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One range change.

    Attributes:
        name: Short name of the case.
        label: What the case is, as the report shows it.
        old: Range before the change.
        new: Range after the change.
        before: Shunt voltage of the old range.
        after: Shunt voltage of the new range.
        overload: How long the old shunt voltage stands before the change;
            None when it stands from the start of the run.
        mux_ohms: On-resistance of a multiplexer channel.
        diode: Model of the limiter diodes.
    """

    name: str
    label: str
    old: int
    new: int
    before: float
    after: float
    overload: float | None = None
    mux_ohms: float = 250.0
    diode: str = "BAV199"


_BASE = _Case("jump-15mv", "jump to range 3 from an overload, 15 mV after it", 0, 3, 0.6, 15e-3)

_CASES = (
    _BASE,
    replace(_BASE, name="jump-5mv", label="jump from an overload, 5 mV after it", after=5e-3),
    replace(_BASE, name="jump-50mv", label="jump from an overload, 50 mV after it", after=50e-3),
    replace(_BASE, name="jump-100mv", label="jump from an overload, 100 mV after it", after=0.1),
    replace(
        _BASE,
        name="diode-slow",
        label="jump from an overload, diodes at 0.9 V and 3 us of recovery",
        diode="BAV199_HI",
    ),
    replace(
        _BASE, name="diode-low", label="jump from an overload, diodes at 0.7 V", diode="BAV199_LO"
    ),
    replace(_BASE, name="mux-125r", label="jump from an overload, 125 ohm", mux_ohms=125.0),
    replace(_BASE, name="mux-430r", label="jump from an overload, 430 ohm", mux_ohms=430.0),
    replace(_BASE, name="overload-2us", label="jump after 2 us of overload", overload=2e-6),
    replace(_BASE, name="overload-5us", label="jump after 5 us of overload", overload=5e-6),
    replace(_BASE, name="ladder-3v", label="jump with 3 V across the ladder before it", before=3.0),
    _Case("step-up", "step up at 91 mV, range 0 to range 1", 0, 1, 91e-3, 2.9e-3),
    _Case("step-down", "step down at 60 uA, range 1 to range 0", 1, 0, 1.92e-3, 60e-3),
    _Case("full-swing", "120 mV to 1.2 mV, range 2 to range 3", 2, 3, 0.12, 1.2e-3),
)


def _line(name: str, before: bool, after: bool) -> str:
    """One address line of the multiplexer as a source that changes at the event."""
    low, high = 0.0, frontend.LOGIC_VOLTS
    start, stop = (high if before else low), (high if after else low)
    return f"V{name} {name} 0 PWL(0 {start:g} {_CHANGE:g} {start:g} {_CHANGE + _EDGE:g} {stop:g})"


def _deck(ctx: Context, case: _Case) -> str:
    if case.overload is None:
        old = f"{case.before:g}"
    else:
        begin = _CHANGE - case.overload
        old = f"PWL(0 {_REST:g} {begin:g} {_REST:g} {begin + 1e-7:g} {case.before:g})"
    shunt = {case.old: old, case.new: f"{case.after:g}"}
    lines = [
        "* range change: the address lines of the multiplexer, as the controller drives them",
        _line("mux_a0", case.old in (1, 3), case.new in (1, 3)),
        _line("mux_a1", case.old in (2, 3), case.new in (2, 3)),
    ]
    models: dict[str, PartModel] = {}
    if case.diode != "BAV199":
        base = ctx.models.model_of(ctx.netlist.component("D22"), ctx.tier)
        models["D22"] = replace(base, name=case.diode)
    return ctx.deck(
        f"Signal chain: {case.label}",
        common.chain(ctx, mux_ohms=case.mux_ohms, overrides=models),
        frontend.rails(),
        common.taps(shunt),
        "\n".join(lines),
        control=[
            "save amp_raw lim flt adc_drv adc_in vdrv inp inn",
            f"tran 20n {_END:g} 0 50n",
        ],
        libraries=common.LIBRARIES,
    )


@dataclass(frozen=True, slots=True)
class _Settled:
    """What one run gives."""

    time: common.Vector
    error: common.Vector
    tenth_percent: float
    one_code: float
    at_first: float
    at_last: float
    final: float


def _settled(result: RunResult) -> _Settled:
    time = result.real("time")
    adc = result.real("adc_in")
    final = measure.mean(time, adc, _END - 10e-6, _END - 1e-6)
    first, last = common.first_valid_samples()
    return _Settled(
        time=time,
        error=adc - final,
        tenth_percent=measure.settling_time(time, adc, final, _TENTH_PERCENT, _CHANGE),
        one_code=measure.settling_time(time, adc, final, common.LSB, _CHANGE),
        at_first=(measure.value_at(time, adc, _CHANGE + first) - final) / common.LSB,
        at_last=(measure.value_at(time, adc, _CHANGE + last) - final) / common.LSB,
        final=final,
    )


@bench(
    "signal_chain",
    "settling",
    "Settling of the chain after a range change",
    "section 4.5 (settling, D-76), rule F-35 and section 8 (settling window), requirement R-05",
)
def settling(ctx: Context) -> Outcome:
    """A range change is a change of the multiplexer address between two held voltages.

    Each sense tap of the multiplexer holds the voltage of its shunt; the
    address lines change at one instant, and the converter input is followed
    until it rests. The time counts from the edge of the address lines. In
    the jump cases the old range stands in overload (0.6 V across its shunt,
    the amplifier at its positive limit, the limiter at work); the other
    cases stay inside the linear range. Every case gives the time to 0.1 %
    of the converter range and to one code, and what a sample taken 70 us
    and 80 us after the change still carries: the first valid sample falls
    between the two.
    """
    base = ctx.run(_BASE.name, _deck(ctx, _BASE))
    others = ctx.run_many({case.name: _deck(ctx, case) for case in _CASES[1:]})
    runs = {_BASE.name: base, **others}
    figures: list[Figure] = []
    traces: list[Trace] = []
    results: dict[str, _Settled] = {}
    for case in _CASES:
        got = _settled(runs[case.name])
        results[case.name] = got
        key = case.name.replace("-", "_")
        is_base = case is _BASE
        figures += [
            Figure(
                f"tenth_percent_{key}",
                f"{case.label}: within 0.1 % of the range after",
                got.tenth_percent,
                "s",
                expected=45e-6 if is_base else None,
                high=50e-6,
                source="section 4.5: about 45 us, 37 us to 50 us over the simulated cases",
            ),
            Figure(
                f"one_code_{key}",
                f"{case.label}: within one code after",
                got.one_code,
                "s",
                expected=65e-6 if is_base else None,
                high=70e-6,
                source="section 4.5: about 65 us, 64 us to 70 us over the simulated cases",
            ),
        ]
        micro = (got.time - _CHANGE) * 1e6
        shown = (micro >= 5.0) & (micro <= 110.0)
        traces.append(
            Trace(
                micro[shown],
                np.maximum(np.abs(got.error[shown]) / common.LSB, 1e-3),
                case.name,
                0,
            )
        )
    worst_first = max(results.values(), key=lambda item: abs(item.at_first))
    worst_last = max(results.values(), key=lambda item: abs(item.at_last))
    figures += [
        Figure(
            "sample_at_70us",
            "Largest error of a sample taken 70 us after the change, any case",
            abs(worst_first.at_first),
            "codes",
            high=_TENTH_PERCENT / common.LSB,
            source="requirement R-05: 0.1 % of range, 65.5 codes",
        ),
        Figure(
            "sample_at_80us",
            "Largest error of a sample taken 80 us after the change, any case",
            abs(worst_last.at_last),
            "codes",
            high=_TENTH_PERCENT / common.LSB,
            source="requirement R-05: 0.1 % of range, 65.5 codes",
        ),
        Figure(
            "tenth_percent_longest",
            "Longest time to 0.1 % of the range, any case",
            max(item.tenth_percent for item in results.values()),
            "s",
            high=common.FLAGGED_SAMPLES * common.SAMPLE_PERIOD,
            source="rule F-35: seven samples are flagged, the eighth is taken after 70 us",
        ),
    ]
    time = base.real("time")
    micro = (time - _CHANGE) * 1e6
    shown = (micro >= -5.0) & (micro <= 100.0)
    first, last = common.first_valid_samples()
    waves = Graph(
        name="waveforms",
        title="Jump to range 3 out of an overload: 0.6 V at the old shunt, 15 mV at the new",
        xlabel="Time after the change of the address lines (us)",
        panels=(
            Panel("Amplifier (V)"),
            Panel("Limiter, filter and converter input (V)", marks=((common.VREF, "VREF"),)),
        ),
        traces=(
            Trace(micro[shown], base.real("amp_raw")[shown], "amplifier output", 0),
            Trace(
                micro[shown],
                (base.real("inp") - base.real("inn"))[shown],
                "at the amplifier inputs",
                0,
                "--",
            ),
            Trace(micro[shown], base.real("lim")[shown], "limiter node", 1),
            Trace(micro[shown], base.real("vdrv")[shown], "driver rail", 1, "--"),
            Trace(micro[shown], base.real("adc_in")[shown], "converter input", 1),
        ),
        xmarks=((first * 1e6, "70 us"), (last * 1e6, "80 us")),
    )
    errors = Graph(
        name="errors",
        title="Distance of the converter input from its final value, every case",
        xlabel="Time after the change of the address lines (us)",
        panels=(
            Panel(
                "Distance from the final value (codes)",
                log=True,
                marks=((_TENTH_PERCENT / common.LSB, "0.1 % of the range"), (1.0, "one code")),
            ),
        ),
        traces=tuple(traces),
        xmarks=((first * 1e6, "70 us"), (last * 1e6, "80 us")),
    )
    notes = (
        "The ladder is not in this circuit. Each sense tap is an ideal source, so the new "
        "shunt voltage stands at once: the time that the load and its capacitor need to "
        "reach the new voltage across the shunt (benches of the ladder) is not in these "
        "figures.",
        "The amplifier model leaves an overload as fast as it slews: its datasheet states "
        "no recovery time. The 5 us that section 4.5 allows for it are not in these figures "
        "and would add to every jump case.",
        "The multiplexer model has a fixed resistance per channel and no charge injection; "
        "the diode models carry the recovery time of their datasheet.",
        "One code is 15 ppm of the range. No model here resolves such a tail (thermal "
        "effects of the amplifier, dielectric absorption): the time to one code is what "
        "the two poles of the filter give, not a prediction of the board.",
    )
    return Outcome(tuple(figures), (waves, errors), notes)
