"""The model of the supervisor TPS3808G01 against the figures of its datasheet."""

from __future__ import annotations

from benches.models import power_input_parts as parts
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_REF = "U6"
"""The supervisor of the schematic; the bench uses it alone."""

_PINS = {"1": "reset", "3": "mr", "4": "ct", "5": "sense", "6": "vdd"}
"""Node names of its pins: RESET, MR, CT, SENSE, VDD."""

_DOCUMENT = "TI SBVS050N"

_VIT = 0.405
"""Threshold of the adjustable version at its SENSE pin (page 6)."""

_OVERDRIVES = (0.05, 0.10, 0.20, 0.50)
"""Steps below the threshold, as fractions of it, for the reaction time."""


def _deck(ctx: Context, title: str, stimulus: str, control: list[str]) -> str:
    """The supervisor alone, with 100 kohm and 50 pF at its output as in the datasheet."""
    fixed = "Vdd vdd 0 PWL(0 0 1m 3.3)\nRpull reset vdd 100k\nCload reset 0 50p\nRmr mr vdd 1e9\n"
    return ctx.deck(
        title,
        parts.part(ctx, _REF, _PINS),
        fixed + stimulus,
        control=control,
        libraries=(parts.LIBRARY,),
    )


def _slow_deck(ctx: Context, tied: bool) -> str:
    """The SENSE pin rises slowly, holds, and falls slowly; CT tied to the supply or open."""
    stimulus = "Vs sense 0 PWL(0 0 10m 0.30 110m 0.45 600m 0.45 700m 0.35)\n"
    stimulus += "Rct ct vdd 100k\n" if tied else "Rct ct 0 1e12\n"
    label = "CT tied to the supply" if tied else "CT open"
    return _deck(
        ctx, f"Supervisor: thresholds and delay, {label}", stimulus, [parts.transient(20e-6, 0.72)]
    )


def _step_deck(ctx: Context, overdrive: float) -> str:
    """The SENSE pin steps from 5 % above the threshold to a level below it."""
    low = _VIT * (1.0 - overdrive)
    stimulus = (
        f"Vs sense 0 PWL(0 0 10u {_VIT * 1.05:g} 30m {_VIT * 1.05:g} 30.0001m {low:g})\n"
        "Rct ct 0 1e12\n"
    )
    return _deck(
        ctx,
        f"Supervisor: step of {overdrive * 100:g} % below the threshold",
        stimulus,
        [parts.transient(0.2e-6, 30.2e-3, 29.9e-3)],
    )


def _low_deck(ctx: Context) -> str:
    """The output sinks 1 mA while it is low."""
    stimulus = "Vs sense 0 0.3\nRct ct 0 1e12\nIsink vdd reset PWL(0 0 2m 0 2.1m 1m)\n"
    return _deck(
        ctx, "Supervisor: low level of the output", stimulus, [parts.transient(5e-6, 4e-3)]
    )


@bench(
    "models",
    "power-input-supervisor",
    "TPS3808G01 model against its datasheet",
    "the model of the supervisor U6",
)
def supervisor(ctx: Context) -> Outcome:
    """The supervisor of the schematic is put, alone, into the test circuit of its datasheet.

    A slow rise and fall of the SENSE pin gives the two thresholds and the
    release delay, with the CT pin tied to the supply and open. Steps of
    5 % to 50 % below the threshold give the reaction time, and a current of
    1 mA into the output its low level.
    """
    decks = {"tied": _slow_deck(ctx, True), "open": _slow_deck(ctx, False), "low": _low_deck(ctx)}
    decks.update(
        {f"step-{overdrive * 100:g}": _step_deck(ctx, overdrive) for overdrive in _OVERDRIVES}
    )
    runs, failed = parts.try_runs(ctx, decks, keep=("tied", "step-5"))
    figures: list[Figure] = []
    rise_at = 0.0
    if "tied" in runs:
        run = runs["tied"]
        time, sense, reset = run.real("time"), run.real("sense"), run.real("reset")
        released = measure.first_crossing(time, reset, 1.65, rising=True, after=20e-3)
        fell = measure.first_crossing(time, reset, 1.65, rising=False, after=0.6)
        rise_at = measure.first_crossing(time, sense, _VIT * 1.015, rising=True)
        figures += [
            near(
                "delay_tied",
                "Release delay with CT tied to the supply",
                released - rise_at,
                "s",
                0.30,
                0.05,
                f"{_DOCUMENT} page 7: 180 ms to 420 ms",
            ),
            Figure(
                "threshold_fall",
                "SENSE voltage at which the output falls",
                measure.value_at(time, sense, fell),
                "V",
                expected=_VIT,
                low=_VIT * 0.98,
                high=_VIT * 1.02,
                source=f"{_DOCUMENT} page 6: 0.405 V, 2 %",
            ),
        ]
    if "open" in runs:
        run = runs["open"]
        time, sense, reset = run.real("time"), run.real("sense"), run.real("reset")
        released = measure.first_crossing(time, reset, 1.65, rising=True, after=20e-3)
        crossed = measure.first_crossing(time, sense, _VIT * 1.015, rising=True)
        figures += [
            near(
                "delay_open",
                "Release delay with CT open",
                released - crossed,
                "s",
                0.02,
                0.1,
                f"{_DOCUMENT} page 7: 12 ms to 28 ms",
            ),
            Figure(
                "threshold_rise",
                "SENSE voltage at which the delay starts (output high 20 ms later, CT open)",
                measure.value_at(time, sense, released - 0.02),
                "V",
                expected=_VIT * 1.015,
                low=_VIT,
                high=_VIT * 1.03,
                source=f"{_DOCUMENT} page 6: hysteresis 1.5 % typical, 3 % at most",
            ),
        ]
    for overdrive in _OVERDRIVES:
        name = f"step-{overdrive * 100:g}"
        if name not in runs:
            continue
        run = runs[name]
        time = run.real("time")
        low_at = measure.first_crossing(time, run.real("reset"), 1.65, False, after=30e-3)
        if overdrive == _OVERDRIVES[0]:
            figures.append(
                near(
                    "react_5",
                    "Output low after a step from 5 % above to 5 % below",
                    low_at - 30.0001e-3,
                    "s",
                    20e-6,
                    0.25,
                    f"{_DOCUMENT} page 7: 20 us typical",
                )
            )
        else:
            figures.append(
                Figure(
                    f"react_{overdrive * 100:g}",
                    f"Output low after a step to {overdrive * 100:g} % below",
                    low_at - 30.0001e-3,
                    "s",
                )
            )
    if "low" in runs:
        run = runs["low"]
        figures.append(
            Figure(
                "output_low",
                "Output voltage at 1 mA with a supply of 3.3 V",
                measure.value_at(run.real("time"), run.real("reset"), 3.9e-3),
                "V",
                high=0.4,
                source=f"{_DOCUMENT} page 6",
            )
        )
    graphs = []
    if "tied" in runs:
        run = runs["tied"]
        graphs.append(
            Graph(
                name="slow",
                title="SENSE rises and falls slowly; CT tied to the supply",
                xlabel="Time (s)",
                panels=(Panel("SENSE (V)", marks=((_VIT, "0.405 V"),)), Panel("Output (V)")),
                traces=(
                    Trace(run.real("time"), run.real("sense"), "SENSE", 0),
                    Trace(run.real("time"), run.real("reset"), "RESET", 1),
                ),
            )
        )
    notes = (
        "The limits of the delay figures are the fit this project asks of the model "
        "around the typical value; the limits of the thresholds are the ones of the "
        "datasheet.",
        "Figure 6-5 of the datasheet shows about 8 us for a step of 10 %, 4 us for 20 % "
        "and 2 us for 50 %; the model, a single filter in front of the comparator, is "
        "slower than that for the larger steps.",
        "A capacitor at the CT pin is not modelled.",
        *parts.failure_note(failed),
    )
    return Outcome(tuple(figures), tuple(graphs), notes)
