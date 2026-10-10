"""The pre-regulator with its tracking amplifier: start and load step at the IN pin."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.source_meter import common
from circuit_sim import measure
from circuit_sim.bench import VENDOR_TIER, Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_REFS = (
    "U16",
    "L2",
    "C37",
    "C39",
    "C40",
    "C42",
    "C45",
    "C50",
    "R62",
    "U19",
    "R63",
    "R64",
    "R65",
    "R66",
    "R67",
    "R68",
    "C52",
    "C55",
    "D13",
    "C51",
    "FB1",
    "C46",
    "C43",
    "R59",
)
"""The converter with its inductor and capacitors, the difference amplifier
and the filter toward the regulator."""

_ENABLE = 20e-6
_STEP = 0.9e-3
_RELEASE = 1.2e-3
_STOP = 1.5e-3
"""Enable, load step, release and end of the run: short, because the model of
the manufacturer switches at 2.4 MHz."""

_SAVE = "save v_pre ldo_in pre_fb trk_sense l.xl2.l1#branch vp5#branch"
"""What the run keeps: the model of the manufacturer has hundreds of nodes and
takes millions of steps."""

_IDLE = 0.01
"""Current of the IN pin before the step."""

_SPAN = 10e-6
"""Window of the running mean that takes the switching out of a waveform."""

_RETURN_LIMIT = 0.25
"""Power that the instrument takes from the 5 V rail in source mode without load
(section 4.2 and section 16): what the converter returns has to stay below it."""


_EMPTY = "empty"
_AT_OUTPUT = "output"
_AT_TARGET = "target"
"""Where the capacitors of the pre-regulator stand before the enable: at 0 V, at
the voltage of the regulator output, or at the target of the converter."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One state of the regulator around the pre-regulator.

    Attributes:
        volts: Voltage at which the regulator output is held.
        amps: Current of the IN pin after the step.
        start: Where the capacitors of the pre-regulator stand before the
            enable.
    """

    volts: float
    amps: float
    start: str

    @property
    def tag(self) -> str:
        return f"{self.volts:g}v".replace(".", "p")

    @property
    def target(self) -> float:
        return common.law(self.volts)

    @property
    def need(self) -> float:
        return common.DROPOUT_OFFSET + common.DROPOUT_OHMS * self.amps

    @property
    def precharge(self) -> float:
        if self.start == _AT_OUTPUT:
            return self.volts
        return self.target if self.start == _AT_TARGET else 0.0


_CASES = (
    _Case(0.8, 1.0, _AT_OUTPUT),
    _Case(3.3, 0.83, _EMPTY),
    _Case(4.5, 0.67, _AT_TARGET),
    _Case(5.0, 0.6, _AT_TARGET),
)
"""Four points of the curve of requirement R-08. At 0.8 V the capacitors start
at the output voltage, where the regulator holds them while the converter is
off: the start of rule F-28. At 4.5 V the target of the converter, 4.97 V, is
the voltage of its input, and at 5.0 V it stands above it: there the
capacitors start at the target, because no sequence starts the converter at
those set-points."""


def _sense_rest(volts: float) -> float:
    """The voltage at which the sense capacitor C55 rests.

    The difference amplifier holds its inverting input at the voltage of
    the divider R66, R67, R68; R64 carries the current from the sense node
    to it, and R65 drops a part of the regulator output.
    """
    target = common.law(volts)
    held = (target / 100e3 + common.REFERENCE / 137e3) / (1 / 100e3 + 1 / 137e3 + 1 / 23.7e3)
    return volts - (volts - held) * 6.65e3 / (6.65e3 + 93.1e3)


def _deck(ctx: Context, case: _Case) -> str:
    vendor = ctx.tier == VENDOR_TIER
    circuit = common.source(ctx, case.volts, refs=_REFS, switching=True)
    lines = [
        "* the regulator output held by a source, the IN pin loaded by a current sink",
        f"Vldo ldo_out 0 {case.volts:g}",
        "* a resistor carries the idle current, so that the start has a load that",
        "* falls with the voltage; the step is a current",
        f"Rin ldo_in 0 {case.target / _IDLE:g}",
        f"Iin ldo_in 0 PULSE(0 {case.amps - _IDLE:g} {_STEP:g} 1u 1u {_RELEASE - _STEP:g} 1)",
        "* rails present from the start, the enable pin raised after them",
        f"Vp5 p5v 0 PWL(0 0 5u {common.RAIL_5V:g})",
        f"Vp3v3a p3v3_a 0 PWL(0 0 5u {common.RAIL_3V3:g})",
        f"Vref vref 0 PWL(0 0 5u {common.REFERENCE:g})",
        f"Ven smu_en 0 PWL(0 0 {_ENABLE:g} 0 {_ENABLE + 1e-6:g} {common.LOGIC_VOLTS:g})",
        "* the sense capacitor of the tracking starts at the voltage it rests at",
        f".ic v(trk_sense)={_sense_rest(case.volts):.6g}",
    ]
    if case.precharge:
        lines += [
            "* the capacitors of the pre-regulator start charged; the node between C43",
            "* and R59 starts at 0 V, so that C43 holds that voltage too",
            f".ic v(v_pre)={case.precharge:.6g} v(ldo_in)={case.precharge:.6g}",
        ]
    if vendor:
        lines += [
            "* the model of the manufacturer does not hold the feed of VINA from VIN",
            "Rvina p5v vina 100",
            "Rpg pg_open 0 1meg",
        ]
    step = "20n" if vendor else "0.2u"
    return ctx.deck(
        f"Pre-regulator with its tracking amplifier at {case.volts:g} V: start and load step",
        circuit,
        "\n".join(lines) + "\n",
        control=[_SAVE, f"tran {step} {_STOP:g} 0 {step} uic"],
    )


def _running_mean(
    time: np.ndarray, values: np.ndarray, start: float, stop: float
) -> tuple[np.ndarray, np.ndarray]:
    """The mean of a waveform over a moving window of 10 us.

    The mean is taken from the integral of the waveform, so that the
    current pulses of a switching converter are counted in full whatever
    the time steps are.

    Returns:
        The centers of the windows, 1 us apart, and the mean in each.
    """
    area = np.concatenate(([0.0], np.cumsum(0.5 * (values[1:] + values[:-1]) * np.diff(time))))
    centers = np.arange(start + _SPAN / 2, stop - _SPAN / 2, 1e-6)
    late = np.interp(centers + _SPAN / 2, time, area)
    early = np.interp(centers - _SPAN / 2, time, area)
    return centers, np.asarray((late - early) / _SPAN, dtype=np.float64)


def _figures(case: _Case, run: RunResult) -> list[Figure]:
    time = run.real("time")
    pre = run.real("v_pre")
    pin = run.real("ldo_in")
    rail = -run.real("vp5#branch")
    before = measure.mean(time, pin, _STEP - 0.1e-3, _STEP)
    loaded = measure.mean(time, pin, _RELEASE - 50e-6, _RELEASE)
    lowest = measure.extremes(time, pin, _STEP, _RELEASE)[0]
    highest = measure.extremes(time, pin, _RELEASE, _STOP)[1]
    _, settled = _running_mean(time, pin, _STEP + 15e-6, _RELEASE)
    _, dipped = _running_mean(time, pin, _STEP - _SPAN / 2, _RELEASE)
    rebound = float(settled.max() - loaded)
    start_clock, start_rail = _running_mean(time, rail, _ENABLE, _STEP)
    _, release_rail = _running_mean(time, rail, _RELEASE, _STOP)
    tag = case.tag
    text = f"{case.volts:g} V"
    step = f"{_IDLE * 1e3:g} mA to {case.amps:g} A"
    figures = [
        Figure(
            f"target_{tag}",
            f"{text}: pre-regulator output before the step",
            measure.mean(time, pre, _STEP - 0.1e-3, _STEP),
            "V",
            expected=case.target,
            low=case.target - 0.03,
            high=case.target + 0.03,
            source=f"section 4.2: 0.672 V + 0.956 x {case.volts:g} V; the band is the "
            "feedback reference of 495 mV to 505 mV",
        ),
        Figure(
            f"feedback_{tag}",
            f"{text}: feedback pin before the step",
            measure.mean(time, run.real("pre_fb"), _STEP - 0.1e-3, _STEP),
            "V",
            expected=0.5,
            low=0.495,
            high=0.505,
            source="SLVS916I, page 6",
        ),
        Figure(
            f"dip_{tag}",
            f"{text}, step of {step}: lowest voltage of the IN pin below its value before",
            before - lowest,
            "V",
        ),
        Figure(
            f"headroom_{tag}",
            f"{text}, step of {step}: lowest voltage of the IN pin above the regulator output",
            lowest - case.volts,
            "V",
            low=case.need,
            source=f"section 4.2: dropout need of {case.need * 1e3:.0f} mV at {case.amps:g} A, "
            "170 mV + 0.300 ohm x I",
        ),
        Figure(
            f"regulation_{tag}",
            f"{text}: fall of the IN pin from {step}, at rest",
            before - loaded,
            "V",
        ),
        Figure(
            f"rebound_{tag}",
            f"{text}: highest voltage of the IN pin above its loaded value after the dip "
            "(mean of 10 us)",
            rebound,
            "V",
        ),
        Figure(
            f"rebound_share_{tag}",
            f"{text}: that overshoot as a share of the dip below the loaded value (means of 10 us)",
            100.0 * rebound / float(loaded - dipped.min()),
            "%",
        ),
        Figure(
            f"release_{tag}",
            f"{text}, release of the step: highest voltage of the IN pin above its value before",
            highest - before,
            "V",
        ),
        Figure(
            f"release_returned_{tag}",
            f"{text}, release of the step: most power returned to the 5 V rail (mean of 10 us)",
            float(-release_rail.min() * common.RAIL_5V),
            "W",
        ),
        Figure(
            f"ripple_pre_{tag}",
            f"{text}: ripple at the pre-regulator output at 10 mA, peak to peak",
            measure.peak_to_peak(time, pre, _STEP - 50e-6, _STEP),
            "V",
        ),
        Figure(
            f"ripple_in_{tag}",
            f"{text}: ripple at the IN pin at 10 mA, peak to peak",
            measure.peak_to_peak(time, pin, _STEP - 50e-6, _STEP),
            "V",
        ),
    ]
    if case.start != _AT_TARGET:
        figures += [
            Figure(
                f"start_{tag}",
                f"{text}, start: 90 % of the target after the enable",
                measure.first_crossing(time, pre, 0.9 * case.target, rising=True, after=_ENABLE)
                - _ENABLE,
                "s",
            ),
            Figure(
                f"start_peak_{tag}",
                f"{text}, start: highest pre-regulator output above its target",
                measure.extremes(time, pre, _ENABLE, _STEP)[1] - case.target,
                "V",
            ),
            Figure(
                f"start_inrush_{tag}",
                f"{text}, start: highest current of the 5 V rail (mean of 10 us)",
                float(start_rail.max()),
                "A",
            ),
        ]
    if case.start == _EMPTY:
        return figures
    charged = f"{text}, start on capacitors at {case.precharge:.3g} V"
    returned = float(-start_rail.min() * common.RAIL_5V)
    if case.start == _AT_OUTPUT:
        figures.append(
            Figure(
                f"start_returned_{tag}",
                f"{charged}: most power returned to the 5 V rail (mean of 10 us)",
                returned,
                "W",
                high=_RETURN_LIMIT,
                source="section 4.2 and section 16: less than the instrument takes from the "
                "rail in source mode without load, for which 0.25 W is the condition",
            )
        )
    else:
        figures.append(
            Figure(
                f"start_returned_{tag}",
                f"{charged}, the state that rule F-28 forbids: most power returned to the "
                "5 V rail (mean of 10 us)",
                returned,
                "W",
            )
        )
    figures += [
        Figure(
            f"start_charge_{tag}",
            f"{charged}: charge returned to the 5 V rail",
            float(-np.sum(np.minimum(start_rail, 0.0)) * (start_clock[1] - start_clock[0])),
            "C",
        ),
        Figure(
            f"start_lowest_{tag}",
            f"{charged}: lowest pre-regulator output after the enable",
            measure.extremes(time, pre, _ENABLE, _STEP)[0],
            "V",
        ),
        Figure(
            f"start_highest_{tag}",
            f"{charged}: highest pre-regulator output above its target after the enable",
            measure.extremes(time, pre, _ENABLE, _STEP)[1] - case.target,
            "V",
        ),
    ]
    return figures


def _graphs(case: _Case, run: RunResult) -> list[Graph]:
    time = run.real("time")
    pre = run.real("v_pre")
    pin = run.real("ldo_in")
    coil = run.real("l.xl2.l1#branch")
    clock, rail = _running_mean(time, -run.real("vp5#branch"), _ENABLE, _STOP)
    shown = (time >= _STEP - 20e-6) & (time <= _STEP + 150e-6)
    micro = (time[shown] - _STEP) * 1e6
    return [
        Graph(
            name=f"run-{case.tag}",
            title=f"Pre-regulator at {case.volts:g} V of regulator output: start, "
            f"{_IDLE * 1e3:g} mA to {case.amps:g} A, release",
            xlabel="Time (ms)",
            panels=(
                Panel("Voltage (V)"),
                Panel("Inductor current (A)"),
                Panel("5 V rail, mean of 10 us (A)", marks=((0.0, "0"),)),
            ),
            traces=(
                Trace(time * 1e3, pre, "pre-regulator output", 0),
                Trace(time * 1e3, pin, "IN pin", 0),
                Trace(time * 1e3, coil, "", 1),
                Trace(clock * 1e3, rail, "", 2),
            ),
            xmarks=((_STEP * 1e3, f"{case.amps:g} A"), (_RELEASE * 1e3, "10 mA")),
        ),
        Graph(
            name=f"step-{case.tag}",
            title=f"The load step at the IN pin, regulator output at {case.volts:g} V",
            xlabel="Time after the step (us)",
            panels=(
                Panel("Voltage (V)", marks=((case.volts + case.need, "dropout need"),)),
                Panel("Inductor current (A)"),
            ),
            traces=(
                Trace(micro, pre[shown], "pre-regulator output", 0),
                Trace(micro, pin[shown], "IN pin", 0),
                Trace(micro, coil[shown], "", 1),
            ),
        ),
    ]


@bench(
    "source_meter",
    "pre-regulator",
    "The pre-regulator with its tracking amplifier: start and a load step to the curve",
    "section 4.2 (loop of the pre-regulator), rule F-28, section 16 (open check of U16)",
)
def pre_regulator(ctx: Context) -> Outcome:
    """The converter runs with its real feedback path and answers a load step to the curve.

    The circuit is the converter with its inductor and capacitors, the
    difference amplifier U19 with its network and the filter toward the
    regulator. The regulator itself is replaced: a source holds its output,
    so that the target of the converter stands still, and a current sink at
    the IN pin steps from 10 mA to the current of the curve and back. Four
    states are run: 0.8 V with a step to 1 A, from capacitors that stand at
    0.8 V as they do when rule F-28 raises SMU_ON; 3.3 V with a step to
    0.83 A, from empty capacitors; 4.5 V with a step to 0.67 A, where the
    converter has to deliver the voltage of its own input; and 5.0 V with a
    step to 0.6 A, where it has to deliver more. Each run gives the dip at
    the IN pin against the dropout need and how the loop comes to rest, the
    first two the start as well. The runs are short enough for the
    transient model of the manufacturer, which the vendor tier puts in the
    place of the averaged model: its ripple and its loop are then those
    that Texas Instruments published.
    """
    decks = {f"step-{case.tag}": _deck(ctx, case) for case in _CASES}
    common.repair_vendor_copies(ctx)
    if ctx.tier == VENDOR_TIER:
        runs = ctx.run_many(decks)
    else:
        runs = {name: ctx.run(name, deck) for name, deck in decks.items()}
    figures: list[Figure] = []
    graphs: list[Graph] = []
    for case in _CASES:
        run = runs[f"step-{case.tag}"]
        figures += _figures(case, run)
        graphs += _graphs(case, run)
    notes = (
        "The regulator is not in this circuit: its output is a source and its IN pin a "
        "current sink, so the pre-regulator is alone with its own loop. The rails and "
        "the reference are ideal sources that stand from the first microseconds; the "
        "enable pin is driven directly.",
        "In the open tier the converter is the averaged model: it shows no ripple, and "
        "its loop is fitted to a load step of the model of the manufacturer in the "
        "application circuit of the datasheet. In the vendor tier the converter is "
        "that transient model itself, with the feedback path of this board.",
        "The two models agree at 3.3 V, 4.5 V and 5.0 V: dips of 103 mV, 89 mV and "
        "82 mV in both, and a recovery that overshoots by 1 mV to 5 mV, less than a "
        "tenth of the dip. At 0.8 V they do not: the transient model dips by 138 mV "
        "where the averaged model has 109 mV, its recovery overshoots by 38 mV, a third "
        "of the dip, where the averaged model has 6 mV, and it falls twice as far at "
        "rest for 1 A. A recovery that overshoots by a third of the dip is that of a "
        "loop with about 40 degrees of phase margin, if the loop is taken as a "
        "second-order system; the averaged model has 58 degrees there. The start of the "
        "transient model overshoots by 0.14 V at 3.3 V and by 0.21 V at 0.8 V, that of "
        "the averaged model by 0.04 V and 0.06 V.",
        "The capacitors have the capacitance of their bias curve and no series "
        "resistance or inductance; the ripple figures of the vendor tier are therefore "
        "those of ideal capacitors behind an ideal bead of 0.2 uH (assumption).",
        "The step takes 1 us at the IN pin. On the board the regulator stands between "
        "the device and this pin, and its output capacitor carries the first "
        "microseconds of a load step, so the step here is faster than the one the "
        "pre-regulator sees. The dropout need is the straight line of section 4.2 "
        "between the two guaranteed points; the head room of this run is the nominal "
        "one, with no tolerance taken off.",
        "At 0.8 V the capacitors of the pre-regulator start at 0.8 V: the regulator "
        "holds them near its output while the converter is off (0.81 V in the bench of "
        "the sequence, 0.15 V to 0.18 V less in section 4.2). The current of the 5 V "
        "rail is the mean over 10 us of the current of an ideal source, read from the "
        "enable on: before it the rail rises in 5 us and charges the input capacitors.",
        "At 4.5 V and at 5.0 V the capacitors start at the target of the converter: the "
        "state that rule F-28 forbids, run here to see what the rule guards against. "
        "The two models answer it in opposite ways. The averaged model starts its duty "
        "cycle from zero and takes the capacitors down by 2 V with its negative "
        "current limit of 0.7 A (TI SLVA726), which returns more than 3 W to the 5 V "
        "rail for 0.15 ms. The transient model of the manufacturer leaves them "
        "charged, lifts them by 0.11 V and returns nothing. The datasheet does not say "
        "which the part does; rule F-28 is safe in both cases.",
        "The averaged model passes from step-down to step-up operation without a "
        "seam, so at 4.5 V, where the converter has to deliver the voltage of its own "
        "input, only the vendor tier shows what it does at that border: the ripple at "
        "the IN pin is 0.75 mV there against 0.4 mV elsewhere, with ideal capacitors.",
    )
    return Outcome(tuple(figures), tuple(graphs), notes)
