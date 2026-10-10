"""The model of the current limiter TPS259621 against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from benches.models import power_input_parts as parts
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.engine import RunResult

_REF = "U4"
"""A limiter of the schematic; the bench uses it alone."""

_PINS = {"4": "in", "5": "out", "3": "en", "8": "ovcsel", "7": "ilm", "2": "dvdt", "6": "flt"}
"""Node names of its pins: IN, OUT, EN/UVLO, OVCSEL, ILM, dVdt, FLT."""

_DOCUMENT = "TI SLVSET8A"

_LIMITS = {
    7870.0: (0.113, 0.125, 0.139),
    3830.0: (0.224, 0.247, 0.269),
    909.0: (0.949, 1.005, 1.051),
    453.0: (1.83, 2.004, 2.147),
}
"""Current limit by resistor at the ILM pin: least, typical, most (page 6)."""

_FOLD_BACK = {7870.0: 0.105, 453.0: 0.80}
"""Current limit with the output at 0 V, at 25 C and 12 V (figures 22 and 23)."""

_ON = 0.2e-3
"""Instant at which the enable pin steps high in the start runs."""


def _deck(ctx: Context, title: str, stimulus: str, control: list[str]) -> str:
    """The limiter alone with a stimulus."""
    floating = "Rflt flt 0 1e9\nRdv dvdt 0 1e12\n"
    return ctx.deck(
        title,
        parts.part(ctx, _REF, _PINS),
        floating + stimulus,
        control=control,
        libraries=(parts.LIBRARY,),
    )


def _start_deck(ctx: Context, farads: float) -> str:
    """The switching test of page 8: 5 V, 100 ohm and 1 uF at the output."""
    stimulus = (
        "Vin in 0 PWL(0 0 10u 5)\n"
        f"Ven en 0 PWL(0 0 {_ON:g} 0 {_ON + 1e-6:g} 3.3)\n"
        "Rsel ovcsel 0 400k\nRilm ilm 0 453\nRout out 0 100\nCout out 0 1u\n"
    )
    if farads:
        stimulus += f"Cdv dvdt 0 {farads:g}\n"
    label = f"{farads * 1e12:g} pF at the dVdt pin" if farads else "dVdt pin open"
    return _deck(ctx, f"Limiter: start, {label}", stimulus, [parts.transient(0.2e-6, 1.2e-3)])


def _limit_deck(ctx: Context, ohms: float) -> str:
    """12 V at the input; the output held 0.5 V below it, then at 0 V."""
    stimulus = (
        "Vin in 0 PWL(0 0 100u 12)\n"
        "Ven en 0 PWL(0 0 200u 0 201u 3.3)\n"
        f"Rilm ilm 0 {ohms:g}\n"
        "Rsel ovcsel 0 1e12\n"
        "Vout out 0 PWL(0 0 100u 11.5 3m 11.5 3.5m 0)\n"
    )
    return _deck(ctx, f"Limiter: limit with {ohms:g} ohm", stimulus, [parts.transient(2e-6, 5e-3)])


def _overload_deck(ctx: Context) -> str:
    """Figure 33: the load steps from 8.33 ohm to 4.54 ohm at 12 V; then a short circuit."""
    stimulus = (
        "Vin in 0 PWL(0 0 100u 12)\n"
        "Ven en 0 PWL(0 0 200u 0 201u 3.3)\n"
        "Rilm ilm 0 453\nRsel ovcsel 0 1e12\nCout out 0 1u\nRout out 0 8.33\n"
        "Bstep out 0 I = v(out)*(1/4.54 - 1/8.33)*pwrin_hi((time - 2m)/0.2u)\n"
        "Bshort out 0 I = v(out)*50*pwrin_hi((time - 3m)/0.1u)\n"
    )
    control = [parts.transient(0.1e-6, 3.3e-3, 1.9e-3)]
    return _deck(ctx, "Limiter: overload and short circuit", stimulus, control)


def _clamp_deck(ctx: Context, amps: float) -> str:
    """The input rises slowly from 5 V to 7 V with a load on the output."""
    stimulus = (
        "Vin in 0 PWL(0 0 100u 5 2m 5 6m 7)\n"
        "Ven en 0 PWL(0 0 200u 0 201u 3.3)\n"
        "Rilm ilm 0 453\nRsel ovcsel 0 400k\nCout out 0 1u\nRout out 0 10k\n"
        f"Iload out 0 PWL(0 0 1m 0 1.1m {amps:g})\n"
    )
    return _deck(ctx, f"Limiter: clamp with {amps:g} A", stimulus, [parts.transient(2e-6, 6.5e-3)])


def _enable_deck(ctx: Context) -> str:
    """The enable pin rises and falls slowly with 5 V at the input."""
    stimulus = (
        "Vin in 0 PWL(0 0 100u 5)\n"
        "Ven en 0 PWL(0 0 1m 0.9 31m 1.5 61m 0.9)\n"
        "Rilm ilm 0 453\nRsel ovcsel 0 400k\nCout out 0 1u\nRout out 0 100\n"
    )
    return _deck(ctx, "Limiter: enable thresholds", stimulus, [parts.transient(5e-6, 62e-3)])


def _supply_deck(ctx: Context) -> str:
    """The input rises and falls slowly with the enable pin tied to it through 100 kohm."""
    stimulus = (
        "Vin in 0 PWL(0 0 1m 2 31m 3 61m 2)\n"
        "Ren in en 100k\n"
        "Rilm ilm 0 453\nRsel ovcsel 0 400k\nCout out 0 1u\nRout out 0 100\n"
    )
    return _deck(ctx, "Limiter: under-voltage thresholds", stimulus, [parts.transient(5e-6, 62e-3)])


def _static_deck(ctx: Context) -> str:
    """5 V at the input; 0.13 A, 0.2 A and 2 A... the load steps for resistance and monitor."""
    stimulus = (
        "Vin in 0 PWL(0 0 100u 5)\n"
        "Ven en 0 PWL(0 0 200u 0 201u 3.3)\n"
        "Rilm ilm 0 453\nRsel ovcsel 0 400k\nCout out 0 1u\n"
        "Iload out 0 PWL(0 0 1m 0 1.1m 0.13 2m 0.13 2.1m 0.2 3m 0.2 3.1m 1.5 4m 1.5)\n"
    )
    return _deck(ctx, "Limiter: on-resistance and monitor", stimulus, [parts.transient(1e-6, 4e-3)])


def _crossing(run: RunResult, name: str, level: float, rising: bool, after: float) -> float:
    """A crossing of one waveform of a run."""
    return measure.first_crossing(run.real("time"), run.real(name), level, rising, after)


def _start_figures(runs: dict[str, RunResult]) -> list[Figure]:
    """Turn-on delay, rise time and slope for the two capacitors of page 8."""
    figures = []
    expected = {"start-open": (78.9e-6, 94.1e-6, 42.7e3), "start-3n3": (247.3e-6, 311.0e-6, 13.1e3)}
    labels = {"start-open": "dVdt pin open", "start-3n3": "3300 pF at the dVdt pin"}
    for name, (delay, rise, slope) in expected.items():
        if name not in runs:
            continue
        run = runs[name]
        enabled = _crossing(run, "en", 1.2, True, 0.0)
        at_10 = _crossing(run, "out", 0.5, True, enabled)
        at_90 = _crossing(run, "out", 4.5, True, at_10)
        key = name.replace("-", "_")
        figures += [
            near(
                f"{key}_delay",
                f"Start, {labels[name]}: turn-on delay to 10 %",
                at_10 - enabled,
                "s",
                delay,
                parts.MODEL_FIT,
                f"{_DOCUMENT} page 8, typical",
            ),
            near(
                f"{key}_rise",
                f"Start, {labels[name]}: rise from 10 % to 90 %",
                at_90 - at_10,
                "s",
                rise,
                parts.MODEL_FIT,
                f"{_DOCUMENT} page 8, typical",
            ),
            near(
                f"{key}_slope",
                f"Start, {labels[name]}: slope of the output",
                4.0 / (at_90 - at_10),
                "V/s",
                slope,
                parts.MODEL_FIT,
                f"{_DOCUMENT} page 8, typical",
            ),
        ]
    return figures


def _limit_figures(runs: dict[str, RunResult]) -> list[Figure]:
    """The limit with 0.5 V across the part and with the output at 0 V."""
    figures = []
    for ohms, (least, typical, most) in _LIMITS.items():
        name = f"limit-{ohms:g}"
        if name not in runs:
            continue
        run = runs[name]
        time = run.real("time")
        amps = run.real("vout#branch")
        figures.append(
            Figure(
                f"limit_{ohms:g}",
                f"Current limit with {ohms:g} ohm, 0.5 V across the part",
                measure.value_at(time, amps, 2.9e-3),
                "A",
                expected=typical,
                low=least,
                high=most,
                source=f"{_DOCUMENT} page 6",
            )
        )
        if ohms in _FOLD_BACK:
            figures.append(
                near(
                    f"fold_{ohms:g}",
                    f"Current limit with {ohms:g} ohm, output at 0 V",
                    measure.value_at(time, amps, 4.9e-3),
                    "A",
                    _FOLD_BACK[ohms],
                    parts.MODEL_FIT,
                    f"{_DOCUMENT} page 13, figures 22 and 23, 12 V and 25 C",
                )
            )
    return figures


@bench(
    "models",
    "power-input-limiter",
    "TPS259621 model against its datasheet",
    "the model of the current limiters U3 and U4",
)
def limiter(ctx: Context) -> Outcome:
    """The limiter of the schematic is put, alone, into the test circuits of its datasheet.

    The start with and without a capacitor at the dVdt pin, the current limit
    with four resistors and its fold-back at an output of 0 V, the response
    to an overload and to a short circuit, the clamp with a light and with a
    heavy load, the thresholds of the enable pin and of the input, the
    on-resistance and the gain of the current monitor.
    """
    decks = {
        "start-open": _start_deck(ctx, 0.0),
        "start-3n3": _start_deck(ctx, 3.3e-9),
        "overload": _overload_deck(ctx),
        "clamp-10m": _clamp_deck(ctx, 0.01),
        "clamp-1a": _clamp_deck(ctx, 1.0),
        "enable": _enable_deck(ctx),
        "supply": _supply_deck(ctx),
        "static": _static_deck(ctx),
    }
    decks.update({f"limit-{ohms:g}": _limit_deck(ctx, ohms) for ohms in _LIMITS})
    runs, failed = parts.try_runs(ctx, decks, keep=("start-3n3", "overload", "clamp-10m"))
    figures = _start_figures(runs) + _limit_figures(runs)
    if "overload" in runs:
        run = runs["overload"]
        time = run.real("time")
        amps = run.real("out") / 8.33 + run.real("out") * (1 / 4.54 - 1 / 8.33) * (
            (time > 2e-3).astype(float)
        )
        peak = float(time[np.argmax(np.where(time < 2.9e-3, amps, 0.0))])
        limited = measure.first_crossing(time, amps, 2.004 * 1.02, False, after=peak)
        figures += [
            near(
                "overload_time",
                "Overload of 32 %: load current within 2 % of the limit after",
                limited - 2e-3,
                "s",
                87e-6,
                0.3,
                f"{_DOCUMENT} page 8: 87 us typical",
            ),
            Figure(
                "short_out",
                "Short circuit with 20 mohm: output 10 us after the short",
                measure.value_at(time, run.real("out"), 3e-3 + 10e-6),
                "V",
                high=2.147 * 0.02 * 1.5,
                source=f"{_DOCUMENT} page 8: 5 us to the limit; 1.5 times the limit in "
                "20 mohm is 64 mV",
            ),
        ]
    for name, amps_load, typical in (("clamp-10m", 0.01, 5.45), ("clamp-1a", 1.0, 5.23)):
        if name not in runs:
            continue
        run = runs[name]
        time = run.real("time")
        level = measure.mean(time, run.real("out"), 6.2e-3, 6.5e-3)
        key = name.replace("-", "_")
        if amps_load < 0.1:
            figures.append(
                Figure(
                    f"{key}_level",
                    "Clamp: output with 7 V at the input and 10 mA",
                    level,
                    "V",
                    expected=typical,
                    low=5.28,
                    high=5.61,
                    source=f"{_DOCUMENT} page 6",
                )
            )
            top = float(time[np.argmax(run.real("out"))])
            figures.append(
                Figure(
                    "clamp_threshold",
                    "Clamp: input voltage at which the output is highest",
                    measure.value_at(time, run.real("in"), top),
                    "V",
                    expected=5.69,
                    low=5.54,
                    high=5.83,
                    source=f"{_DOCUMENT} page 6",
                )
            )
        else:
            figures.append(
                near(
                    f"{key}_level",
                    "Clamp: output with 7 V at the input and 1 A",
                    level,
                    "V",
                    typical,
                    0.03,
                    f"{_DOCUMENT} page 12, figure 16 at 25 C",
                )
            )
    if "enable" in runs:
        run = runs["enable"]
        time = run.real("time")
        on_at = _crossing(run, "out", 0.5, True, 1e-3)
        off_at = _crossing(run, "out", 4.5, False, 31e-3)
        figures += [
            Figure(
                "enable_on",
                "Enable pin: voltage at which the output starts",
                measure.value_at(time, run.real("en"), on_at - 80e-6),
                "V",
                expected=1.20,
                low=1.18,
                high=1.22,
                source=f"{_DOCUMENT} page 7",
            ),
            Figure(
                "enable_off",
                "Enable pin: voltage at which the output ends",
                measure.value_at(time, run.real("en"), off_at - 12e-6),
                "V",
                expected=1.10,
                low=1.08,
                high=1.13,
                source=f"{_DOCUMENT} page 7",
            ),
        ]
    if "supply" in runs:
        run = runs["supply"]
        time = run.real("time")
        on_at = _crossing(run, "out", 0.25, True, 1e-3)
        off_at = _crossing(run, "out", 2.2, False, 31e-3)
        figures += [
            Figure(
                "supply_on",
                "Input: voltage at which the output starts",
                measure.value_at(time, run.real("in"), on_at - 80e-6),
                "V",
                expected=2.53,
                low=2.46,
                high=2.58,
                source=f"{_DOCUMENT} page 6",
            ),
            Figure(
                "supply_off",
                "Input: voltage at which the output ends",
                measure.value_at(time, run.real("in"), off_at - 12e-6),
                "V",
                expected=2.42,
                low=2.36,
                high=2.46,
                source=f"{_DOCUMENT} page 6",
            ),
        ]
    if "static" in runs:
        run = runs["static"]
        time = run.real("time")
        drop = measure.value_at(time, run.real("in") - run.real("out"), 2.9e-3)
        figures += [
            Figure(
                "on_ohms",
                "On-resistance at 0.2 A and 5 V",
                drop / 0.2,
                "ohm",
                expected=0.089,
                high=0.0926,
                source=f"{_DOCUMENT} page 7, 25 C",
            ),
            Figure(
                "monitor_0a13",
                "Current monitor gain at 0.13 A",
                measure.value_at(time, run.real("ilm"), 1.9e-3) / 453.0 / 0.13,
                "A/A",
                expected=653.21e-6,
                low=531.22e-6,
                high=800e-6,
                source=f"{_DOCUMENT} page 6",
            ),
            Figure(
                "monitor_1a5",
                "Current monitor gain at 1.5 A",
                measure.value_at(time, run.real("ilm"), 3.9e-3) / 453.0 / 1.5,
                "A/A",
                expected=657.15e-6,
                low=635.77e-6,
                high=684.05e-6,
                source=f"{_DOCUMENT} page 6 (stated at 2 A)",
            ),
        ]
    graphs = []
    if "start-3n3" in runs and "start-open" in runs:
        slow, fast = runs["start-3n3"], runs["start-open"]
        graphs.append(
            Graph(
                name="start",
                title="Start at 5 V into 100 ohm and 1 uF",
                xlabel="Time (us)",
                panels=(Panel("Voltage (V)"),),
                traces=(
                    Trace(slow.real("time") * 1e6, slow.real("en"), "enable", 0),
                    Trace(fast.real("time") * 1e6, fast.real("out"), "output, dVdt open", 0),
                    Trace(slow.real("time") * 1e6, slow.real("out"), "output, 3300 pF", 0),
                ),
            )
        )
    if "overload" in runs:
        run = runs["overload"]
        time = run.real("time")
        graphs.append(
            Graph(
                name="overload",
                title="12 V, limit 2 A: the load steps to 2.64 A at 2 ms and is shorted at 3 ms",
                xlabel="Time (ms)",
                panels=(Panel("Output (V)"), Panel("Voltage at the ILM pin (V)")),
                traces=(
                    Trace(time * 1e3, run.real("out"), "output", 0),
                    Trace(time * 1e3, run.real("ilm"), "ILM pin", 1),
                ),
            )
        )
    notes = (
        f"The fit this project asks of the model is {parts.MODEL_FIT * 100:.0f} % on a typical "
        "value; where the datasheet states limits, the limits are the ones of the datasheet.",
        "The model is a typical part at 25 C without thermal shutdown. The fold-back of "
        "its limit between an output of 0 V and the full limit is an assumption: the "
        "datasheet gives the two ends only.",
        "The short circuit is judged by the output voltage, because the current of the "
        "first microseconds depends on a saturation current that the datasheet does not "
        "give and the model does not have.",
        *parts.failure_note(failed),
    )
    return Outcome(tuple(figures), tuple(graphs), notes)
