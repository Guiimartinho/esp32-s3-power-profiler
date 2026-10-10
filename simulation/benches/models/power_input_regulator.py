"""The model of the regulator LP5907-3.3 against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from benches.models import power_input_parts as parts
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_REF = "U8"
"""A regulator of the schematic; the bench uses it alone."""

_PINS = {"1": "in", "3": "en", "5": "out"}
"""Node names of its pins: IN, EN, OUT."""

_DOCUMENT = "TI SNVS798Q"

_REJECTION = {100.0: 90.0, 1e3: 82.0, 1e4: 65.0, 1e5: 60.0}
"""Supply rejection in decibels by frequency, at 20 mA (page 5, typical)."""


def _deck(ctx: Context, title: str, stimulus: str, control: list[str], extra: str = "") -> str:
    """The regulator alone with 1 uF at its output."""
    return ctx.deck(
        title,
        parts.part(ctx, _REF, _PINS),
        "Cout out 0 1u\n" + stimulus + extra,
        control=control,
        libraries=(parts.LIBRARY,),
    )


def _start_deck(ctx: Context) -> str:
    """4.3 V at the input; the enable pin steps high and low again; 1 mA of load."""
    stimulus = (
        "Vin in 0 PWL(0 0 10u 4.3)\n"
        "Ven en 0 PWL(0 0 1m 0 1.0002m 1.2 3m 1.2 3.0002m 0)\n"
        "Rload out 0 3.3k\n"
    )
    return _deck(ctx, "Regulator: start and discharge", stimulus, [parts.transient(0.2e-6, 4.5e-3)])


def _load_deck(ctx: Context) -> str:
    """The load rises to 250 mA; then the output is pulled to ground."""
    stimulus = (
        "Vin in 0 PWL(0 0 10u 4.3)\n"
        "Ren in en 1k\n"
        "Iload out 0 PWL(0 0 1m 0 1.1m 1m 2m 1m 3m 250m 4m 250m 4.1m 0)\n"
        "Bpull out 0 I = v(out)*20*pwrin_hi((time - 5m)/2u)\n"
    )
    return _deck(
        ctx, "Regulator: load regulation and limit", stimulus, [parts.transient(1e-6, 6e-3)]
    )


def _dropout_deck(ctx: Context, amps: float) -> str:
    """The input falls slowly from 4.3 V to 3.0 V under load."""
    stimulus = (
        "Vin in 0 PWL(0 0 10u 4.3 2m 4.3 8m 3.0)\n"
        "Ren in en 1k\n"
        f"Iload out 0 PWL(0 0 1m 0 1.1m {amps:g})\n"
    )
    return _deck(ctx, f"Regulator: dropout at {amps:g} A", stimulus, [parts.transient(1e-6, 8e-3)])


def _enable_deck(ctx: Context) -> str:
    """The enable pin rises and falls slowly with 5 V at the input."""
    stimulus = (
        "Vin in 0 PWL(0 0 10u 5)\nVen en 0 PWL(0 0 1m 0.3 21m 1.3 41m 0.3)\nRload out 0 3.3k\n"
    )
    return _deck(ctx, "Regulator: enable thresholds", stimulus, [parts.transient(2e-6, 42e-3)])


def _rejection_deck(ctx: Context) -> str:
    """A small signal on the input at 20 mA of load."""
    stimulus = "Vin in 0 DC 4.3 AC 1\nRen in en 1k\nIload out 0 20m\n"
    nodeset = ".nodeset v(out)=3.3 v(en)=4.3\n"
    if ctx.tier == "open":
        nodeset = ".nodeset v(out)=3.3 v(en)=4.3 v(xu8.r)=3.3 v(xu8.se)=1\n"
    return _deck(
        ctx, "Regulator: supply rejection", stimulus, ["op", "ac dec 10 10 1meg"], extra=nodeset
    )


@bench(
    "models",
    "power-input-regulator",
    "LP5907-3.3 model against its datasheet",
    "the model of the 3.3 V regulators U7 and U8",
)
def regulator(ctx: Context) -> Outcome:
    """A regulator of the schematic is put, alone, into the test circuits of its datasheet.

    The start from the enable pin and the discharge of the output, the load
    regulation and the current limit, the dropout at 100 mA and at 250 mA,
    the thresholds of the enable pin, and the supply rejection from 100 Hz to
    100 kHz.
    """
    decks = {
        "start": _start_deck(ctx),
        "load": _load_deck(ctx),
        "dropout-0a1": _dropout_deck(ctx, 0.1),
        "dropout-0a25": _dropout_deck(ctx, 0.25),
        "enable": _enable_deck(ctx),
        "rejection": _rejection_deck(ctx),
    }
    runs, failed = parts.try_runs(ctx, decks, keep=("start", "rejection"))
    figures: list[Figure] = []
    if "start" in runs:
        run = runs["start"]
        time, out = run.real("time"), run.real("out")
        enabled = measure.first_crossing(time, run.real("en"), 0.9, rising=True)
        at_95 = measure.first_crossing(time, out, 0.95 * 3.3, rising=True, after=enabled)
        level = measure.value_at(time, out, 2.9e-3)
        fell = measure.first_crossing(time, out, 3.3 * 0.368, rising=False, after=3e-3)
        figures += [
            Figure(
                "output",
                "Output with 4.3 V at the input and 1 mA",
                level,
                "V",
                expected=3.3,
                low=3.3 * 0.98,
                high=3.3 * 1.02,
                source=f"{_DOCUMENT} page 5",
            ),
            Figure(
                "start",
                "Output at 95 % after the enable",
                at_95 - enabled,
                "s",
                expected=80e-6,
                high=150e-6,
                source=f"{_DOCUMENT} page 6",
            ),
            Figure(
                "overshoot",
                "Overshoot of the start",
                float(np.max(out[(time > 1e-3) & (time < 3e-3)])) / 3.3 - 1.0,
                "",
                high=0.01,
                source=f"{_DOCUMENT} page 6: 1 % with the enable",
            ),
            near(
                "discharge",
                "Output at 36.8 % after the enable has fallen (1 uF, 3.3 kohm beside the 230 ohm)",
                fell - 3.0002e-3,
                "s",
                215e-6,
                parts.MODEL_FIT,
                f"{_DOCUMENT} page 5: 230 ohm typical",
            ),
        ]
    if "load" in runs:
        run = runs["load"]
        time, out = run.real("time"), run.real("out")
        light = measure.value_at(time, out, 1.9e-3)
        heavy = measure.value_at(time, out, 3.9e-3)
        current = -measure.value_at(time, run.real("vin#branch"), 5.8e-3)
        figures += [
            near(
                "load_regulation",
                "Load regulation from 1 mA to 250 mA",
                (light - heavy) / 249.0,
                "V",
                33e-6,
                0.2,
                f"{_DOCUMENT} page 5: 0.001 % per mA, which is 33 uV per mA",
            ),
            Figure(
                "limit",
                "Current with the output held at ground",
                current,
                "A",
                expected=0.5,
                low=0.25,
                source=f"{_DOCUMENT} page 5: 250 mA at least",
            ),
        ]
    for name, amps, typical, most in (
        ("dropout-0a1", 0.1, 0.050, None),
        ("dropout-0a25", 0.25, None, 0.250),
    ):
        if name not in runs:
            continue
        run = runs[name]
        time = run.real("time")
        at = measure.first_crossing(time, run.real("out"), 3.2, rising=False, after=2e-3)
        dropout = measure.value_at(time, run.real("in"), at) - 3.2
        key = name.replace("-", "_")
        if typical is not None:
            figures.append(
                near(
                    key,
                    f"Dropout at {amps:g} A",
                    dropout,
                    "V",
                    typical,
                    parts.MODEL_FIT,
                    f"{_DOCUMENT} page 5: 50 mV typical",
                )
            )
        else:
            figures.append(
                Figure(
                    key,
                    f"Dropout at {amps:g} A",
                    dropout,
                    "V",
                    high=most,
                    source=f"{_DOCUMENT} page 5: 250 mV at most in SOT-23",
                )
            )
    if "enable" in runs:
        run = runs["enable"]
        time, out = run.real("time"), run.real("out")
        on_at = measure.first_crossing(time, out, 0.3, rising=True, after=1e-3)
        off_at = measure.first_crossing(time, out, 3.0, rising=False, after=21e-3)
        figures += [
            Figure(
                "enable_on",
                "Enable voltage at which the output starts",
                measure.value_at(time, run.real("en"), on_at - 40e-6),
                "V",
                expected=0.87,
                low=0.4,
                high=1.2,
                source=f"{_DOCUMENT} page 6 and figure 5-2",
            ),
            Figure(
                "enable_off",
                "Enable voltage at which the output ends",
                measure.value_at(time, run.real("en"), off_at),
                "V",
                expected=0.84,
                low=0.4,
                high=1.2,
                source=f"{_DOCUMENT} page 6 and figure 5-2",
            ),
        ]
    graphs = []
    if "rejection" in runs:
        run = runs["rejection"]
        frequency = np.real(run.vector("frequency", plot="ac")).astype(np.float64)
        rejection = -measure.decibels(run.vector("out", plot="ac"))
        for hertz, decibel in _REJECTION.items():
            figures.append(
                Figure(
                    f"rejection_{hertz:g}",
                    f"Supply rejection at {hertz:g} Hz",
                    float(np.interp(np.log10(hertz), np.log10(frequency), rejection)),
                    "dB",
                    expected=decibel,
                    low=decibel - 3.0,
                    high=decibel + 3.0,
                    source=f"{_DOCUMENT} page 5, typical at 20 mA",
                )
            )
        graphs.append(
            Graph(
                name="rejection",
                title="Supply rejection at 20 mA with 1 uF at the output",
                xlabel="Frequency (Hz)",
                panels=(Panel("Rejection (dB)"),),
                traces=(Trace(frequency, rejection, "", 0),),
                logx=True,
            )
        )
    if "start" in runs:
        run = runs["start"]
        time = run.real("time")
        shown = (time > 0.95e-3) & (time < 1.25e-3)
        graphs.append(
            Graph(
                name="start",
                title="Start from the enable pin with 4.3 V at the input",
                xlabel="Time (us)",
                panels=(Panel("Voltage (V)"),),
                traces=(
                    Trace((time[shown] - 1e-3) * 1e6, run.real("en")[shown], "enable", 0),
                    Trace((time[shown] - 1e-3) * 1e6, run.real("out")[shown], "output", 0),
                ),
            )
        )
    notes = (
        f"The fit this project asks of the model is {parts.MODEL_FIT * 100:.0f} % on a typical "
        "value, and 3 dB on the supply rejection; where the datasheet states limits, the "
        "limits are the ones of the datasheet.",
        "The model follows the supply rejection up to 100 kHz only, and it has no response "
        "of its own to a load step: the 40 mV of the datasheet for 250 mA are not in it.",
        "The supply rejection is a small-signal analysis around an operating point that "
        "the solver finds with the regulator on.",
        *parts.failure_note(failed),
    )
    return Outcome(tuple(figures), tuple(graphs), notes)
