"""The model of the power multiplexer TPS2116 against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from benches.models import power_input_parts as parts
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_REF = "U5"
"""The multiplexer of the schematic; the bench uses it alone."""

_PINS = {"3": "in1", "6": "in2", "2": "out", "4": "pr1", "8": "st"}
"""Node names of its pins. The MODE pin is on the net of input 1 in the
schematic, so the part is in priority mode in every test."""

_DOCUMENT = "TI SLVSFG1A"

_SOFT_START = {5.0: (1.0e-3, 1.7e-3), 3.3: (1.2e-3, 1.3e-3), 1.8: (1.4e-3, 0.9e-3)}
"""Delay to 10 % and time from 10 % to 90 % by input voltage, with 100 ohm
and 10 uF at the output (page 7)."""

_ON = 0.1e-3
"""Instant at which the input steps on in the soft start runs."""


def _deck(ctx: Context, title: str, stimulus: str, control: list[str]) -> str:
    """The multiplexer alone with a stimulus."""
    return ctx.deck(
        title, parts.part(ctx, _REF, _PINS), stimulus, control=control, libraries=(parts.LIBRARY,)
    )


def _start_deck(ctx: Context, volts: float) -> str:
    """An input steps on with the priority pin tied to it; 100 ohm and 10 uF at the output."""
    stimulus = (
        f"Vin in1 0 PWL(0 0 {_ON:g} 0 {_ON + 10e-6:g} {volts:g})\n"
        "Rpr in1 pr1 1\nRin2 in2 0 1k\nRst st in1 10k\nRout out 0 100\nCout out 0 10u\n"
    )
    return _deck(
        ctx, f"Multiplexer: soft start at {volts:g} V", stimulus, [parts.transient(2e-6, 5e-3)]
    )


def _change_deck(ctx: Context) -> str:
    """Both inputs present; the priority pin rises and falls slowly, then steps."""
    stimulus = (
        "Vin1 in1 0 PWL(0 0 10u 5)\n"
        "Vin2 s2 0 PWL(0 0 10u 5)\n"
        "Vi2 s2 in2 0\n"
        "Vpr pr1 0 PWL(0 0 5m 0.8 15m 1.2 25m 0.8 30m 0.8 30.001m 5 31m 5 31.001m 0)\n"
        "Rst st vp 3.3k\nVp vp 0 PWL(0 0 10u 3.4)\n"
        "Rout out 0 10\nCout out 0 10u\n"
    )
    return _deck(ctx, "Multiplexer: change of input", stimulus, [parts.transient(0.5e-6, 31.5e-3)])


def _reverse_deck(ctx: Context) -> str:
    """Input 1 at 5 V; a load of 0.2 A, then the output is pushed above the input."""
    stimulus = (
        "Vin in1 0 PWL(0 0 10u 5)\n"
        "Vi in1 in1s 0\n"
        "Rpr in1 pr1 1\nRin2 in2 0 1k\nRst st in1 10k\n"
        "Cout out 0 1u\n"
        "Iload out 0 PWL(0 0 4m 0 4.1m 0.2 5m 0.2 5.1m 0)\n"
        "Vpush ps 0 PWL(0 0 10u 4.9 6m 4.9 7m 5.2 8m 5.2 9m 4.9)\n"
        "Rpush ps out 0.05\n"
    )
    return _deck(
        ctx,
        "Multiplexer: on-resistance and reverse blocking",
        stimulus,
        [parts.transient(1e-6, 10e-3)],
    )


@bench(
    "models",
    "power-input-multiplexer",
    "TPS2116 model against its datasheet",
    "the model of the power multiplexer U5",
)
def multiplexer(ctx: Context) -> Outcome:
    """The multiplexer of the schematic is put, alone, into the test circuits of its datasheet.

    The soft start at three input voltages, the change of input with the
    threshold of the priority pin and the time without a channel, the
    on-resistance, the two levels of the reverse current blocking and the
    status output.
    """
    decks = {
        f"start-{volts:g}v".replace(".", "p"): _start_deck(ctx, volts) for volts in _SOFT_START
    }
    decks["change"] = _change_deck(ctx)
    decks["reverse"] = _reverse_deck(ctx)
    runs, failed = parts.try_runs(ctx, decks, keep=("start-5v", "change", "reverse"))
    figures: list[Figure] = []
    for volts, (delay, soft) in _SOFT_START.items():
        name = f"start-{volts:g}v".replace(".", "p")
        if name not in runs:
            continue
        run = runs[name]
        time, out = run.real("time"), run.real("out")
        final = float(out[-1])
        chosen = measure.first_crossing(time, run.real("pr1"), 1.0, rising=True)
        at_10 = measure.first_crossing(time, out, 0.1 * final, rising=True, after=chosen)
        at_90 = measure.first_crossing(time, out, 0.9 * final, rising=True, after=at_10)
        key = name.replace("-", "_")
        figures += [
            near(
                f"{key}_delay",
                f"Soft start at {volts:g} V: delay to 10 %",
                at_10 - chosen,
                "s",
                delay,
                parts.MODEL_FIT,
                f"{_DOCUMENT} page 7, typical",
            ),
            near(
                f"{key}_soft",
                f"Soft start at {volts:g} V: 10 % to 90 %",
                at_90 - at_10,
                "s",
                soft,
                parts.MODEL_FIT,
                f"{_DOCUMENT} page 7, typical",
            ),
        ]
    if "change" in runs:
        run = runs["change"]
        time, out = run.real("time"), run.real("out")
        two = run.real("vi2#branch")
        to_one = measure.first_crossing(time, two, 0.2, rising=False, after=5e-3)
        to_two = measure.first_crossing(time, two, 0.2, rising=True, after=15e-3)
        window = (time > 31.001e-3) & (time < 31.2e-3)
        lowest = float(time[window][np.argmin(out[window])])
        before = measure.value_at(time, out, 31.0e-3)
        figures += [
            Figure(
                "priority_up",
                "Priority pin: voltage at which input 1 is taken",
                measure.value_at(time, run.real("pr1"), to_one),
                "V",
                expected=1.0,
                low=0.92,
                high=1.08,
                source=f"{_DOCUMENT} page 6",
            ),
            Figure(
                "priority_down",
                "Priority pin: voltage at which input 1 is left",
                measure.value_at(time, run.real("pr1"), to_two - 8e-6),
                "V",
                expected=1.0,
                low=0.92,
                high=1.08,
                source=f"{_DOCUMENT} page 6",
            ),
            near(
                "change_time",
                "Change of input at 5 V with 10 ohm and 10 uF: output at its "
                "lowest after the priority pin has stepped",
                lowest - 31.001e-3,
                "s",
                8e-6,
                0.4,
                f"{_DOCUMENT} page 7: 8 us typical",
            ),
            Figure(
                "change_dip",
                "The same: dip of the output",
                before - float(np.min(out[window])),
                "V",
            ),
            Figure(
                "status_low",
                "Status output at 1 mA while input 2 supplies",
                measure.value_at(time, run.real("st"), 4e-3),
                "V",
                high=0.1,
                source=f"{_DOCUMENT} page 6",
            ),
            Figure(
                "status_high",
                "Status output while input 1 supplies",
                measure.value_at(time, run.real("st"), 20e-3),
                "V",
                low=3.3,
                source=f"{_DOCUMENT} page 11: pulled high while input 1 is used",
            ),
        ]
    if "reverse" in runs:
        run = runs["reverse"]
        time = run.real("time")
        diff = run.real("out") - run.real("in1")
        amps = run.real("vin#branch")
        drop = -measure.value_at(time, diff, 4.9e-3)
        through = -measure.value_at(time, amps, 4.9e-3)
        figures.append(
            Figure(
                "on_ohms",
                "On-resistance at 5 V, from the drop and the current of input 1",
                drop / through,
                "ohm",
                expected=0.037,
                high=0.046,
                source=f"{_DOCUMENT} page 6, 25 C",
            )
        )
        # The source of input 1 takes current back until the channel opens.
        rising = (time > 6e-3) & (time < 7.2e-3)
        reverse = amps[rising]
        opened = float(time[rising][np.argmax(reverse)])
        resumed = measure.first_crossing(time, amps, 0.01, rising=True, after=8.05e-3)
        figures += [
            Figure(
                "reverse_open",
                "Reverse blocking: output above the input when the channel opens",
                measure.value_at(time, diff, opened),
                "V",
                expected=0.042,
                high=0.070,
                source=f"{_DOCUMENT} page 6",
            ),
            Figure(
                "reverse_amps",
                "Reverse blocking: current back into the input before that",
                float(np.max(reverse)),
                "A",
                expected=1.4,
                high=4.0,
                source=f"{_DOCUMENT} page 6",
            ),
            Figure(
                "reverse_close",
                "Reverse blocking: output above the input when the channel closes again",
                measure.value_at(time, diff, resumed - 10e-6),
                "V",
                expected=0.017,
                high=0.040,
                source=f"{_DOCUMENT} page 6",
            ),
            Figure(
                "reverse_leak",
                "Current back into the input while the channel is open",
                float(np.max(np.abs(amps[(time > 7.3e-3) & (time < 7.9e-3)]))),
                "A",
                high=0.15e-6,
                source=f"{_DOCUMENT} page 6: 1 nA typical, 0.15 uA at 105 C",
            ),
        ]
    graphs = []
    if "start-5v" in runs:
        run = runs["start-5v"]
        graphs.append(
            Graph(
                name="start",
                title="Soft start at 5 V into 100 ohm and 10 uF",
                xlabel="Time (ms)",
                panels=(Panel("Voltage (V)"),),
                traces=(
                    Trace(run.real("time") * 1e3, run.real("in1"), "input 1", 0),
                    Trace(run.real("time") * 1e3, run.real("out"), "output", 0),
                    Trace(run.real("time") * 1e3, run.real("st"), "status output", 0, "--"),
                ),
            )
        )
    if "change" in runs:
        run = runs["change"]
        time = run.real("time")
        shown = (time > 30.99e-3) & (time < 31.06e-3)
        graphs.append(
            Graph(
                name="change",
                title="Change from input 1 to input 2, both at 5 V, with 10 ohm and 10 uF",
                xlabel="Time after the priority pin steps (us)",
                panels=(Panel("Voltage (V)"),),
                traces=(
                    Trace((time[shown] - 31.001e-3) * 1e6, run.real("out")[shown], "output", 0),
                    Trace((time[shown] - 31.001e-3) * 1e6, run.real("pr1")[shown], "priority", 0),
                ),
            )
        )
    notes = (
        f"The fit this project asks of the model is {parts.MODEL_FIT * 100:.0f} % on a typical "
        "value; where the datasheet states limits, the limits are the ones of the datasheet.",
        "The model is a typical part at 25 C. Its leakage is a resistor that keeps the "
        "matrix regular: the leakage figure is no statement about the part.",
        "The time of the change is read at the lowest point of the output; the datasheet "
        "does not say how it measures its 8 us, so the limit is wide.",
        *parts.failure_note(failed),
    )
    return Outcome(tuple(figures), tuple(graphs), notes)
