"""The over-voltage detector of VIN: thresholds, hysteresis, reaction time."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.path_switching import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_RAMP_START = 5.2
"""Voltage from which the slow ramp of VIN starts, V."""

_RAMP_TOP = 5.7
"""Voltage at which the slow ramp of VIN turns, V."""

_RAMP_TIME = 0.1
"""Time of each ramp, s: 5 V/s, which the filter of the detector follows within 0.3 mV."""

_STEP = 20e-6
"""Instant of the step of VIN in the reaction runs."""

_STEP_EDGE = 1e-6
"""Time the step takes."""

_TRIP = (5.46, 5.41, 5.51)
"""Trip level of the detector with its band (specification, section 4.9)."""

_RELEASE = (5.35, 5.30, 5.40)
"""Release level of the detector with its band (specification, section 4.9)."""

_REFERENCE_TOLERANCE = 0.001
"""Tolerance of the reference: 0.1 %, the standard grade of the REF5025."""

_RAIL_TOLERANCE = 0.03
"""Tolerance of 3V3_A as the detector sees it (assumption): it sets the high
level of the comparator and with it the hysteresis."""

_OFFSET = 10e-3
"""Largest input offset of the comparator, V (Microchip DS20002139E, page 3)."""

_HYSTERESIS = (1e-3, 5e-3)
"""Limits of the hysteresis of the comparator itself, V (same page)."""


@dataclass(frozen=True, slots=True)
class _Corner:
    """One set of tolerances of the detector.

    Attributes:
        name: Short name of the run.
        sign: +1 for the set that raises the levels, -1 for the one that
            lowers them, 0 for nominal parts.
        wide: Take the largest hysteresis (of the comparator and of the
            feedback resistor) instead of the smallest.
    """

    name: str
    sign: int
    wide: bool


_CORNERS = (
    _Corner("nominal", 0, False),
    _Corner("trip-high", 1, True),
    _Corner("trip-low", -1, False),
    _Corner("release-high", 1, False),
    _Corner("release-low", -1, True),
)


def _threshold_deck(ctx: Context, corner: _Corner) -> str:
    """VIN ramps slowly through both levels, with one set of tolerances."""
    sign = corner.sign
    spread = {"R73": 0.001, "R74": 0.001, "R76": 0.01}
    scales = {}
    hysteresis, offset, reference, rail = 3e-3, 0.0, 2.5, 3.3
    if sign:
        # A larger R73 and a smaller R74 raise both levels. A smaller R76 and
        # a higher rail widen the hysteresis: the trip rises, the release falls.
        feedback = -1 if corner.wide else 1
        scales = {
            "R73": 1.0 + sign * spread["R73"],
            "R74": 1.0 - sign * spread["R74"],
            "R76": 1.0 + feedback * spread["R76"],
        }
        hysteresis = _HYSTERESIS[1] if corner.wide else _HYSTERESIS[0]
        offset = sign * _OFFSET
        reference = 2.5 * (1.0 + sign * _REFERENCE_TOLERANCE)
        rail = 3.3 * (1.0 - feedback * _RAIL_TOLERANCE)
    top = _RAMP_TIME
    stimulus = (
        "* VIN ramps slowly up and down again; no leads\n"
        f"Vin vin_raw 0 PWL(0 {_RAMP_START:g} {top:g} {_RAMP_TOP:g} {2 * top:g} {_RAMP_START:g})\n"
        + common.no_regulator()
        + common.requests()
    )
    control = ["save vin_p det vin_ov vref amp_in", f"tran 20u {2 * top:g} 0 50u"]
    return common.deck(
        ctx,
        f"Over-voltage detector: slow ramp of VIN, {corner.name} parts",
        common.circuit(
            ctx,
            ladder=False,
            overrides={"U21": common.comparator(offset=offset, hysteresis=hysteresis)},
            scales=scales,
            detector=True,
        ),
        common.rails(p3v3=rail, vref=reference),
        stimulus,
        control=control,
    )


def _levels(run: RunResult) -> tuple[float, float]:
    """The voltage of VIN at which the detector output rises and falls."""
    time = run.real("time")
    terminal, output = run.real("vin_p"), run.real("vin_ov")
    half = common.LOGIC_VOLTS / 2.0
    rises = measure.first_crossing(time, output, half, rising=True)
    falls = measure.first_crossing(time, output, half, rising=False, after=rises)
    return measure.value_at(time, terminal, rises), measure.value_at(time, terminal, falls)


def _step_deck(ctx: Context, volts: float) -> str:
    """VIN steps from 5 V to a higher voltage within 1 us; the pairs are open."""
    stimulus = (
        "* VIN steps up within 1 us; no leads\n"
        f"Vin vin_raw 0 PWL(0 5 {_STEP:g} 5 {_STEP + _STEP_EDGE:g} {volts:g})\n"
        + common.no_regulator()
        + common.requests(ampere=((0.0, True),))
    )
    control = [
        "save vin_p det vin_ov amp_in drv_amp g_amp s_amp supply @dd15_1[id] @dd15_2[id]",
        "tran 20n 400u 0 200n",
    ]
    return common.deck(
        ctx,
        f"Over-voltage detector: VIN steps from 5 V to {volts:g} V",
        common.circuit(ctx, ladder=False, detector=True),
        common.rails(),
        stimulus,
        control=control,
    )


_STEPS = (5.6, 6.0, 8.0, 12.0, 20.0)
"""Voltages the terminal steps to in the reaction runs."""


@bench(
    "path_switching",
    "detector",
    "The over-voltage detector of VIN: levels with tolerances and reaction time",
    "section 4.9 (over-voltage detector, D-60, D-43), requirement R-09, section 16",
)
def detector(ctx: Context) -> Outcome:
    """VIN ramps slowly through the two levels of the detector, then steps above them.

    The slow ramp, 5 V/s up and down, gives the level at which the output
    VIN_OV rises and the one at which it falls. It is run with nominal parts
    and with four sets of tolerances: the divider resistors at 0.1 %, the
    feedback resistor at 1 %, the reference at 0.1 %, the offset of the
    comparator at 10 mV either way, its own hysteresis at 1 mV and 5 mV, and
    the 3.3 V rail, which is the high level of the output, at 3 %. The steps
    show how long the detector needs: its input has a filter of 53 us, so
    the time depends on how far the step passes the level. The ampere
    request is high in the step runs, with nothing connected behind the
    pair.
    """
    ramps = ctx.run_many({corner.name: _threshold_deck(ctx, corner) for corner in _CORNERS[1:]})
    ramps["nominal"] = ctx.run("ramp", _threshold_deck(ctx, _CORNERS[0]))
    found = {name: _levels(run) for name, run in ramps.items()}
    trip, release = found["nominal"]
    figures = [
        Figure(
            "trip",
            "VIN at which the detector output rises, nominal parts",
            trip,
            "V",
            expected=_TRIP[0],
            low=_TRIP[1],
            high=_TRIP[2],
            source="section 4.9: 5.46 V (5.41 V to 5.51 V), calculated",
        ),
        Figure(
            "release",
            "VIN at which the detector output falls, nominal parts",
            release,
            "V",
            expected=_RELEASE[0],
            low=_RELEASE[1],
            high=_RELEASE[2],
            source="section 4.9: 5.35 V (5.30 V to 5.40 V), calculated",
        ),
        Figure(
            "hysteresis",
            "Hysteresis at the terminal, nominal parts",
            trip - release,
            "V",
            expected=0.11,
            source="section 4.9: 5.46 V less 5.35 V",
        ),
        Figure(
            "trip_high",
            "Highest trip level with the tolerances",
            found["trip-high"][0],
            "V",
            high=_TRIP[2],
            source="section 4.9: 5.51 V at the most",
        ),
        Figure(
            "trip_low",
            "Lowest trip level with the tolerances",
            found["trip-low"][0],
            "V",
            low=_TRIP[1],
            source="section 4.9: 5.41 V at the least",
        ),
        Figure(
            "release_high",
            "Highest release level with the tolerances",
            found["release-high"][1],
            "V",
            high=_RELEASE[2],
            source="section 4.9: 5.40 V at the most",
        ),
        Figure(
            "release_low",
            "Lowest release level with the tolerances",
            found["release-low"][1],
            "V",
            low=_RELEASE[1],
            source="section 4.9: 5.30 V at the least",
        ),
        Figure(
            "hysteresis_least",
            "Smallest hysteresis at the terminal with the tolerances",
            min(found["release-high"][0] - found["release-high"][1], trip - release),
            "V",
            low=0.0,
            source="limit of this bench: the detector must not chatter",
        ),
    ]
    steps = ctx.run_many(
        {f"step-{volts:g}".replace(".", "p"): _step_deck(ctx, volts) for volts in _STEPS[1:]}
    )
    first = f"step-{_STEPS[0]:g}".replace(".", "p")
    steps[first] = ctx.run(first, _step_deck(ctx, _STEPS[0]))
    half = common.LOGIC_VOLTS / 2.0
    traces: list[Trace] = []
    for volts in _STEPS:
        run = steps[f"step-{volts:g}".replace(".", "p")]
        time = run.real("time")
        passes = measure.first_crossing(time, run.real("vin_p"), trip, rising=True)
        reports = measure.first_crossing(time, run.real("vin_ov"), half, rising=True)
        blocked = measure.first_crossing(
            time, run.real("g_amp") - run.real("s_amp"), 1.5, rising=False, after=_STEP
        )
        tag = f"{volts:g}v".replace(".", "p")
        figures += [
            Figure(
                f"reports_{tag}",
                f"Step to {volts:g} V: output high after the terminal passes the trip level",
                reports - passes,
                "s",
                source="",
            ),
            Figure(
                f"opens_{tag}",
                f"Step to {volts:g} V: gate-source voltage of the ampere pair below 1.5 V after",
                blocked - passes,
                "s",
                low=4e-6,
                high=45e-6,
                source="section 4.9: the detector opens the switch 4 us to 45 us after the "
                "terminal passes the threshold",
            ),
        ]
        if volts == 20.0:
            clamp = run.real("@dd15_2[id]")
            figures += [
                Figure(
                    "clamp_current",
                    "Step to 20 V: current of the clamp D15 into 3V3_A at the end",
                    float(clamp[-1]),
                    "A",
                    high=0.17e-3,
                    source="section 4.9: 0.17 mA at 20 V, calculated, which is the whole "
                    "current of R73",
                ),
                Figure(
                    "input_high",
                    "Step to 20 V: detector input above 3V3_A at the most",
                    float(np.max(run.real("det"))) - 3.3,
                    "V",
                    high=1.0,
                    source="rating of the comparator input, supply plus 1.0 V "
                    "(Microchip DS20002139E, page 3)",
                ),
            ]
        micro = (time - _STEP) * 1e6
        shown = micro <= 120.0
        traces.append(Trace(micro[shown], run.real("det")[shown], f"to {volts:g} V", 0))
        traces.append(Trace(micro[shown], run.real("vin_ov")[shown], f"to {volts:g} V", 1))
        traces.append(Trace(micro[shown], run.real("g_amp")[shown], f"to {volts:g} V", 2))
    nominal = ramps["nominal"]
    time = nominal.real("time")
    levels = Graph(
        name="levels",
        title="Slow ramp of VIN, nominal parts: the detector output against the terminal",
        xlabel="Time (ms)",
        panels=(
            Panel(
                "VIN (V)",
                marks=(
                    (_TRIP[1], "5.41 V"),
                    (_TRIP[2], "5.51 V"),
                    (_RELEASE[1], "5.30 V"),
                    (_RELEASE[2], "5.40 V"),
                ),
            ),
            Panel("Detector input (V)", marks=((2.5, "reference"),)),
            Panel("Detector output VIN_OV (V)"),
        ),
        traces=(
            Trace(time * 1e3, nominal.real("vin_p"), "", 0),
            Trace(time * 1e3, nominal.real("det"), "", 1),
            Trace(time * 1e3, nominal.real("vin_ov"), "", 2),
        ),
    )
    reaction = Graph(
        name="reaction",
        title="VIN steps up from 5 V within 1 us: the detector and the gate of the ampere pair",
        xlabel="Time after the step (us)",
        panels=(
            Panel("Detector input (V)", marks=((2.5, "reference"),)),
            Panel("Detector output VIN_OV (V)"),
            Panel("Gate of the ampere pair (V)"),
        ),
        traces=tuple(traces),
    )
    notes = (
        "The comparator is a behavioral model with a delay of 47 ns whatever the "
        "overdrive; its offset and its hysteresis are set to the limits of its "
        "datasheet in the tolerance runs. Drift with temperature is not in them.",
        "The tolerance of the 3.3 V rail, 3 %, is an assumption; it moves the "
        "release level by 3.5 mV. The reference is taken at 0.1 %.",
        "The reaction time is set by the filter at the detector input (53 us with "
        "the divider) and by how far the step passes the level. The specification "
        "states 4 us to 45 us without the step it holds for: a step to 5.6 V takes "
        "longer, a step to 20 V less. The 45 us hold for steps to about 5.8 V or "
        "more. Neither end is a hazard by itself: the slow case is the one that "
        "passes the level by little. In these runs nothing is connected behind the "
        "pair and the supply has no leads; the bench overvoltage shows what reaches "
        "a load.",
        "The clamp current is the current in the diode toward 3V3_A; the rest of "
        "the 0.14 mA that R73 carries at 20 V flows through R74.",
    )
    return Outcome(tuple(figures), (levels, reaction), notes)
