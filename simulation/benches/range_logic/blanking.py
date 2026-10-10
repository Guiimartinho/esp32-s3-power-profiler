"""What the blanking time has to cover: the old voltage and the pulse of a step down."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from benches.range_logic import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_OVERLAP = 1e-6
_BLANKING = 2e-6
"""Overlap of the gates and blanking after the last change (rule F-17)."""

_LOWEST = common.THRESHOLD_BAND["up"][0]
"""Lowest step-up threshold at the shunt, V (table of section 4.4)."""

_LOWEST_INPUT = (_LOWEST * common.GAIN + common.PEDESTAL) / common.DIVIDER
"""The same at the comparator input, V."""

_LOW_UP = common.Offsets(up=common.offset_for("up", _LOWEST))
"""The step-up comparator with its threshold at the lower limit of its band."""

_DOWN_AMPS = 0.059
"""Load of the step down: just below the 60 mA at which firmware asks for it."""

_SETTLED = 2e-3
"""Distance from the final sense voltage at which the pulse counts as over, V."""


@dataclass(frozen=True, slots=True)
class _Up:
    """A load step in range 0 that ends in range 3 with CMP_UP low.

    Attributes:
        amps: Load current after the step.
        capacitance: Capacitor at the terminals; none when left out.
        delays: Delays between the shunt and the gate.
    """

    amps: float
    capacitance: float | None
    delays: common.Delays = common.NOMINAL


def _mux(ohms: float) -> common.Delays:
    return replace(common.NOMINAL, mux_ohms=ohms)


_UPS = {
    "1uf-125": _Up(0.5, 1e-6, _mux(125.0)),
    "1uf-250": _Up(0.5, 1e-6),
    "1uf-430": _Up(0.5, 1e-6, _mux(430.0)),
    "1uf-worst": _Up(0.5, 1e-6, common.WORST),
    "none-125": _Up(0.5, None, _mux(125.0)),
    "none-250": _Up(0.5, None),
    "none-430": _Up(0.5, None, _mux(430.0)),
    "none-worst": _Up(0.5, None, common.WORST),
    "100nf-250": _Up(0.5, 100e-9),
    "small-none-250": _Up(0.02, None),
    "small-none-430": _Up(0.02, None, _mux(430.0)),
}
"""The load steps of the first part, by name."""

_DOWNS = {
    f"{volts:g}v-{ohms:g}".replace(".", "p"): (volts, ohms)
    for volts in (5.0, 5.5, 0.8)
    for ohms in (125.0, 250.0, 430.0)
}
"""The steps down of the second part: output voltage and multiplexer resistance."""


def _up_deck(ctx: Context, name: str) -> str:
    case = _UPS[name]
    load = common.Load(before=1e-6, after=case.amps, capacitance=case.capacitance)
    return common.step_deck(
        ctx, f"Old voltage after a jump, {name}", load, delays=case.delays, end=8e-6
    )


def _down_deck(ctx: Context, name: str) -> str:
    volts, ohms = _DOWNS[name]
    load = common.Load(before=_DOWN_AMPS, after=_DOWN_AMPS, capacitance=None)
    return common.step_deck(
        ctx,
        f"Step down from range 3 at 59 mA, {volts:g} V, multiplexer {ohms:g} ohm",
        load,
        volts=volts,
        delays=_mux(ohms),
        offsets=_LOW_UP,
        start=3,
        end=10e-6,
        down=common.request(common.STEP_AT),
        save="seq_down",
    )


def _stale(result: RunResult) -> float:
    """How long CMP_UP stays high after the last change of the address."""
    time = result.real("time")
    instants, ranges = common.range_changes(result)
    if ranges.size == 0 or ranges[-1] != 3.0:
        return float("nan")
    last = float(instants[-1])
    falls = measure.first_crossing(
        time, result.real("cmp_up"), common.HALF_LOGIC, rising=False, after=last
    )
    return falls - last


@dataclass(frozen=True, slots=True)
class _Pulse:
    """What a step down from range 3 shows.

    Attributes:
        changes: Range changes after the request.
        ladder: Largest ladder voltage after the old gate falls, V.
        sense: Largest voltage at the amplifier inputs there, V.
        at_input: Largest voltage at the comparator inputs there, V.
        over: Time from the falling gate line to the sense voltage near its end value, s.
        comparator: Longest time CMP_UP is high after the request, s.
    """

    changes: int
    ladder: float
    sense: float
    at_input: float
    over: float
    comparator: float


def _pulse(result: RunResult) -> _Pulse:
    time = result.real("time")
    stop = float(time[-1])
    instants, _ = common.range_changes(result)
    gate_falls = measure.first_crossing(
        time, result.real("gate_r3"), common.HALF_LOGIC, rising=False, after=common.STEP_AT
    )
    sense = result.real("inp") - result.real("inn")
    final = measure.mean(time, sense, stop - 0.5e-6, stop)
    return _Pulse(
        changes=int(np.count_nonzero(instants > common.STEP_AT)),
        ladder=measure.extremes(time, common.ladder(result), gate_falls, stop)[1],
        sense=measure.extremes(time, sense, gate_falls, stop)[1],
        at_input=measure.extremes(time, result.real("cmp_in"), gate_falls, stop)[1],
        over=measure.settling_time(time, sense, final, _SETTLED, gate_falls),
        comparator=common.high_time(time, result.real("cmp_up"), common.STEP_AT, stop),
    )


@bench(
    "range_logic",
    "blanking",
    "The blanking time: the old voltage after a change and the pulse of a step down",
    "section 4.4 (blanking), rule F-17, decision D-76, section 11 (step down at 59 mA)",
)
def blanking(ctx: Context) -> Outcome:
    """Two things that the step-up comparator must not act on are measured.

    First the old voltage. After a jump to range 3 the comparators still see
    what the amplifier held before: the capacitors at its inputs discharge
    through the multiplexer, and its output comes back from a voltage far
    above the thresholds. The run steps the load from 1 uA to 500 mA and to
    20 mA, with and without a capacitor at the terminals, and reads how long
    CMP_UP stays high after the address changed. Second the pulse of a step
    down. The sequencer is in range 3 with 59 mA and no capacitor at the
    terminals, firmware asks for one step down, and the gate of the range 3
    switch falls 1 us after range 2 took over. Below its threshold that gate
    pulls its charge out of the load node through the 1 ohm shunt. The run
    reads the pulse at the ladder, at the amplifier inputs and at the
    comparator inputs, with the step-up threshold at the lower limit of its
    band, at 5.0 V, 5.5 V and 0.8 V and with the multiplexer at 125 ohm,
    250 ohm and 430 ohm.
    """
    ups = {name: ctx.run(name, _up_deck(ctx, name)) for name in ("1uf-250", "none-250")}
    ups.update(ctx.run_many({name: _up_deck(ctx, name) for name in _UPS if name not in ups}))
    downs = {name: ctx.run(name, _down_deck(ctx, name)) for name in ("5v-125", "5p5v-125")}
    downs.update(
        ctx.run_many({name: _down_deck(ctx, name) for name in _DOWNS if name not in downs})
    )
    stale = {name: _stale(result) for name, result in ups.items()}
    pulses = {name: _pulse(result) for name, result in downs.items()}
    window = _OVERLAP + _BLANKING
    old = "section 4.4: 0.6 us to 1.0 us, simulated; rule F-17: blanked for 3 us"
    figures = [
        Figure(
            "stale_shortest",
            "CMP_UP high after the address changed, shortest of the load steps",
            float(np.nanmin(list(stale.values()))),
            "s",
            expected=0.6e-6,
            high=window,
            source=old,
        ),
        Figure(
            "stale_longest",
            "CMP_UP high after the address changed, longest of the load steps",
            float(np.nanmax(list(stale.values()))),
            "s",
            expected=1.0e-6,
            high=window,
            source=old,
        ),
    ]
    labels = {
        "1uf-125": "500 mA, 1 uF, 125 ohm",
        "1uf-250": "500 mA, 1 uF, 250 ohm",
        "1uf-430": "500 mA, 1 uF, 430 ohm",
        "1uf-worst": "500 mA, 1 uF, worst delays",
        "none-125": "500 mA, no capacitor, 125 ohm",
        "none-250": "500 mA, no capacitor, 250 ohm",
        "none-430": "500 mA, no capacitor, 430 ohm",
        "none-worst": "500 mA, no capacitor, worst delays",
        "100nf-250": "500 mA, 100 nF, 250 ohm",
        "small-none-250": "20 mA, no capacitor, 250 ohm",
        "small-none-430": "20 mA, no capacitor, 430 ohm",
    }
    figures += [
        Figure(f"stale_{name.replace('-', '_')}", f"The same: {labels[name]}", stale[name], "s")
        for name in _UPS
    ]
    figures += [
        Figure(
            "down_changes",
            "Range changes after one step-down request, most of the nine runs",
            float(max(pulse.changes for pulse in pulses.values())),
            "",
            expected=1.0,
            low=1.0,
            high=1.0,
            source="section 11: one change of the range bits, no step back up",
        ),
        Figure(
            "down_over",
            "Pulse over after the gate line fell, longest of the nine runs",
            max(pulse.over for pulse in pulses.values()),
            "s",
            high=_BLANKING,
            source="rule F-17: blanked until 2.0 us after the last change",
        ),
    ]
    for name, text in (("5v-125", "5.0 V"), ("5p5v-125", "5.5 V"), ("0p8v-125", "0.8 V")):
        pulse = pulses[name]
        reaches = name == "5p5v-125"
        figures += [
            Figure(
                f"down_ladder_{name.replace('-', '_')}",
                f"{text}, 125 ohm: largest ladder voltage in the pulse",
                pulse.ladder,
                "V",
            ),
            Figure(
                f"down_sense_{name.replace('-', '_')}",
                f"{text}, 125 ohm: largest voltage at the amplifier inputs",
                pulse.sense,
                "V",
                expected=_LOWEST if reaches else None,
                source="section 4.4: reaches the lowest step-up threshold, simulated"
                if reaches
                else "",
            ),
            Figure(
                f"down_input_{name.replace('-', '_')}",
                f"{text}, 125 ohm: largest voltage at the comparator inputs",
                pulse.at_input,
                "V",
                expected=_LOWEST_INPUT if reaches else None,
                source="the same threshold at the comparator input" if reaches else "",
            ),
        ]
    for name, text in (("5p5v-250", "250 ohm"), ("5p5v-430", "430 ohm")):
        figures.append(
            Figure(
                f"down_sense_{name.replace('-', '_')}",
                f"5.5 V, {text}: largest voltage at the amplifier inputs",
                pulses[name].sense,
                "V",
            )
        )
    figures.append(
        Figure(
            "down_comparator",
            "CMP_UP high after the request, threshold at its lowest, longest of the runs",
            max(pulse.comparator for pulse in pulses.values()),
            "s",
        )
    )

    def after_change(result: RunResult, label: str) -> list[Trace]:
        time = result.real("time")
        instants, _ = common.range_changes(result)
        last = float(instants[-1])
        shown = (time >= last - 0.5e-6) & (time <= last + 2.0e-6)
        micro = (time[shown] - last) * 1e6
        sense = result.real("inp") - result.real("inn")
        return [
            Trace(micro, np.minimum(sense[shown], 0.6) * 1e3, label, 0),
            Trace(micro, result.real("amp_raw")[shown], label, 1),
            Trace(micro, result.real("cmp_up")[shown], label, 2),
        ]

    old_voltage = Graph(
        name="old-voltage",
        title="After the jump to range 3 on a 500 mA step: what the step-up comparator sees",
        xlabel="Time after the address changes (us)",
        panels=(
            Panel(
                "At the amplifier inputs (mV, cut at 600)",
                marks=((90.95, "step up 91 mV"),),
            ),
            Panel("Amplifier output (V)", marks=((1.863, "step-up level"),)),
            Panel("CMP_UP (V)"),
        ),
        traces=tuple(
            after_change(ups["1uf-250"], "1 uF, 250 ohm")
            + after_change(ups["1uf-430"], "1 uF, 430 ohm")
            + after_change(ups["none-250"], "no capacitor, 250 ohm")
            + after_change(ups["none-430"], "no capacitor, 430 ohm")
        ),
    )
    traces: list[Trace] = []
    for name, label in (("5p5v-125", "5.5 V"), ("5v-125", "5.0 V"), ("0p8v-125", "0.8 V")):
        result = downs[name]
        time = result.real("time")
        shown = (time >= common.STEP_AT - 0.3e-6) & (time <= common.STEP_AT + 3.2e-6)
        micro = (time[shown] - common.STEP_AT) * 1e6
        traces += [
            Trace(micro, result.real("g_r3")[shown], f"gate of Q14, {label}", 0),
            Trace(micro, result.real("g_r2")[shown], f"gate of Q13, {label}", 0, "--"),
            Trace(micro, common.ladder(result)[shown] * 1e3, label, 1),
            Trace(micro, (result.real("inp") - result.real("inn"))[shown] * 1e3, label, 2),
            Trace(micro, result.real("cmp_in")[shown], label, 3),
        ]
    step_down = Graph(
        name="step-down",
        title="Step down from range 3 to range 2 at 59 mA, no capacitor, multiplexer 125 ohm",
        xlabel="Time after the step-down request (us)",
        panels=(
            Panel("Gates of the switches (V)"),
            Panel("Ladder voltage (mV)"),
            Panel(
                "At the amplifier inputs (mV)",
                marks=((_LOWEST * 1e3, "lowest step-up threshold 87.5 mV"),),
            ),
            Panel(
                "At the comparator inputs (V)",
                marks=((_LOWEST_INPUT, "lowest step-up threshold"),),
            ),
        ),
        traces=tuple(traces),
        xmarks=((0.1, "range 2 on"), (1.1, "gate of range 3 falls"), (3.1, "blanking ends")),
    )
    notes = (
        "Old voltage: the amplifier model returns from its output limit at its "
        "slew rate. The overload recovery of the real part is not in its "
        "datasheet and not in the model; it adds to these times, and the "
        "specification allows 5 us for it elsewhere (section 4.5), which is "
        "longer than the 3 us from the first change to the end of the blanking. "
        "After a jump that does no harm, because range 3 has no step up left.",
        "Step down: the size of the pulse follows the gate charge of the range 3 "
        "switch below its threshold. The model of that switch is fitted to the "
        "typical gate charge curve of its datasheet (12 nC at 4.5 V) and has a "
        "fixed gate-source capacitance; a part at the upper end of its gate "
        "charge gives a larger pulse.",
        "With the transistor model written here the pulse stays 6 mV below the "
        "lowest step-up threshold at 5.5 V with the multiplexer at 125 ohm. With "
        "the model of the manufacturer, in the vendor tier, it is a tenth larger "
        "and passes that threshold by 3 mV at 5.5 V, as the specification says, "
        "and comes within 1 mV of it at 5.0 V. The two models differ in how they "
        "split the gate charge, which the datasheet does not settle. The "
        "blanking covers the pulse in either case.",
        "The comparator model passes no pulse shorter than its delay of 47 ns, "
        "and the model of the sequencer none shorter than its reaction time: "
        "whether a short pulse above a threshold would move a real sequencer "
        "cannot be read from them. The figures to rely on are the voltages.",
        "The source holds its voltage behind 20 mohm; 5.5 V is above the 5.00 V "
        "that firmware allows as a set-point and stands for the worst case of "
        "section 11.",
        common.VENDOR_NOTE,
    )
    return Outcome(tuple(figures), (old_voltage, step_down), notes)
