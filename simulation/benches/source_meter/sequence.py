"""Start and stop of the source in the order of the firmware rules, and set-point steps."""

from __future__ import annotations

import numpy as np

from benches.source_meter import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_LOW = common.code_of(0.8)
_HIGH = common.code_of(5.0)

_FIRST = 5e-3
"""Step 1 of rule F-28: the DAC takes the code of 0.80 V."""

_ENABLE = _FIRST + 200e-3
"""Step 3: SMU_ON high, 200 ms later."""

_WORK = _ENABLE + 5e-3
"""Step 5: the DAC takes the working value, 5 ms later."""

_READY = _WORK + 80e-3
"""End of step 5: 80 ms later the paths may close."""

_DISABLE = _READY + 60e-3
"""Stop, rule F-29: SMU_ON low (the paths are open in this run)."""

_ZERO = _DISABLE + 10e-3
"""The DAC goes to zero."""

_STOP = _ZERO + 250e-3
"""End of the start and stop run."""

_STEP_DOWN = 120e-3
"""Instant of the set-point step from 5.00 V to 0.80 V in the second run."""

_STEP_STOP = 300e-3
"""End of the set-point step run."""

_RELEASED_STOP = _STEP_DOWN + 60e-3
"""End of the run in which the set-point is taken away at once."""

_NO_FILTER = 1e-3
"""Share of C41 that is left in that run: a filter of 10 us in place of 10 ms."""

_LESS = 10e-3
"""Power below the value before a step from which the rail counts as relieved."""

_REVERSE_LIMIT = -0.3
"""Rating of the IN pin relative to the output (LT3080 Rev. E, page 2)."""


def _smu(*edges: tuple[float, float]) -> str:
    """The pin SMU_ON as a waveform: (instant, level) pairs, 1 us per edge."""
    points = ["0 0"]
    level = 0.0
    for instant, target in edges:
        points += [f"{instant:g} {level:g}", f"{instant + 1e-6:g} {target:g}"]
        level = target
    return f"PWL({' '.join(points)})"


def _start_deck(ctx: Context) -> str:
    """Idle, start in the order of rule F-28, stop in the order of rule F-29."""
    dac = common.part(
        ctx, common.DAC, code=0, code1=_LOW, t1=_FIRST, code2=_HIGH, t2=_WORK, code3=0, t3=_ZERO
    )
    circuit = common.source(ctx, 5.0, with_dut=False, overrides={common.DAC: dac})
    controller = common.controller(
        _smu((_ENABLE, common.LOGIC_VOLTS), (_DISABLE, 0.0)),
        common.ramp(common.OK_SHARE * common.RAIL_5V, 200e-6, 210e-6),
    )
    return ctx.deck(
        "Start and stop of the source, rules F-28 and F-29",
        circuit,
        common.power_up_rails(),
        controller,
        "* the source pair is open: nothing hangs on the regulator output but the sheet\n",
        control=[f"tran 5u {_STOP:g} 0 50u"],
    )


def _step_deck(ctx: Context, farads: float, index: int) -> str:
    """The source at 5.00 V, then the code of 0.80 V in one step."""
    dac = common.part(
        ctx, common.DAC, code=0, code1=_HIGH, t1=common.READY, code2=_LOW, t2=_STEP_DOWN
    )
    circuit = common.source(ctx, 5.0, overrides={common.DAC: dac})
    return ctx.deck(
        f"Set-point step from 5.00 V to 0.80 V, {farads * 1e6:g} uF at the device",
        circuit,
        common.power_up_rails(),
        common.power_up_controller(),
        common.dut(index, 0.0, farads),
        control=[f"tran 5u {_STEP_STOP:g} 0 50u"],
    )


def _released_deck(ctx: Context) -> str:
    """The same step with the set-point filter taken out and the source pair open."""
    dac = common.part(
        ctx, common.DAC, code=0, code1=_HIGH, t1=common.READY, code2=_LOW, t2=_STEP_DOWN
    )
    circuit = common.source(
        ctx, 5.0, with_dut=False, overrides={common.DAC: dac}, scales={"C41": _NO_FILTER}
    )
    return ctx.deck(
        "Set-point taken away at once: the released output, source pair open",
        circuit,
        common.power_up_rails(),
        common.power_up_controller(),
        "* the source pair is open: nothing hangs on the regulator output but the sheet\n",
        control=[f"tran 5u {_RELEASED_STOP:g} 0 50u"],
    )


def _rail_amps(run: RunResult) -> np.ndarray:
    """Current that the source takes from the 5 V rail; negative when it returns some."""
    return -run.real("vp5#branch")


def _relief(time: np.ndarray, rail: np.ndarray, stop: float) -> tuple[float, float]:
    """How much less power the 5 V rail gives after a step down, and for how long.

    Returns:
        The largest fall of the power below its value before the step, and
        the time for which it is at least 10 mW below the value at which it
        comes to rest after the step: the time for which the converter
        takes charge back from its output.
    """
    before = measure.mean(time, rail, _STEP_DOWN - 5e-3, _STEP_DOWN) * common.RAIL_5V
    after = measure.mean(time, rail, stop - 5e-3, stop) * common.RAIL_5V
    grid = np.arange(_STEP_DOWN, stop, 20e-6)
    watts = np.interp(grid, time, rail) * common.RAIL_5V
    return float(before - watts.min()), float(np.count_nonzero(watts < after - _LESS) * 20e-6)


def _slope(time: np.ndarray, values: np.ndarray, start: float, stop: float) -> np.ndarray:
    """The slope of a waveform inside a window, in volts per second, over 0.2 ms."""
    grid = np.arange(start, stop, 0.2e-3)
    return np.asarray(np.diff(np.interp(grid, time, values)) / 0.2e-3, dtype=np.float64)


@bench(
    "source_meter",
    "sequence",
    "Start and stop of the source in the order of rules F-28 and F-29, set-point steps",
    "section 4.2 (start and stop, clamps, bleeder, set-point filter), rules F-28 to F-31",
)
def sequence(ctx: Context) -> Outcome:
    """The source runs through the start and the stop that firmware has to follow.

    After the rails stand, the DAC takes the code of 0.80 V; 200 ms later
    SMU_ON rises; 5 ms later the DAC takes the code of 5.00 V; after 80 ms
    and a wait the source is stopped: SMU_ON falls and the DAC goes to
    zero. The paths to the device are open throughout. The run shows the
    regulator alone on its control supply, the start of the pre-regulator
    on its charged capacitors, the rise of the output behind the set-point
    filter, and what the IN pin and the 5 V rail see at the stop. Two more
    runs step the set-point from 5.00 V to 0.80 V at once, without a device
    and with 100 uF at the device in range 3. A last run takes the filter
    of the set-point out, so that the output is released and falls with its
    minimum load alone.
    """
    run = ctx.run("start-stop", _start_deck(ctx))
    time = run.real("time")
    out, pre, pin = run.real("ldo_out"), run.real("v_pre"), run.real("ldo_in")
    drive = run.real("set_drv")
    rail = _rail_amps(run)
    headroom = pin - out
    control_amps = (run.real("p13v5") - run.real("vctl_feed")) / 10.0
    alone = _ENABLE - 1e-3
    rise = _slope(time, out, _WORK, _READY)
    fall = _slope(time, out, _ZERO, _ZERO + 30e-3)
    figures = [
        Figure(
            "idle_output",
            "Idle, DAC at zero and SMU_ON low: regulator output",
            measure.value_at(time, out, _FIRST - 0.5e-3),
            "V",
        ),
        Figure(
            "alone_output",
            "Regulator on its control supply alone, code of 0.80 V: output",
            measure.value_at(time, out, alone),
            "V",
            expected=common.volts_of(_LOW),
            low=common.volts_of(_LOW) - 0.01,
            high=common.volts_of(_LOW) + 0.01,
            source="section 4.2: with the pre-regulator off the regulator follows the "
            "set-point; 10 mV is the limit of this bench",
        ),
        Figure(
            "alone_in_pin",
            "In that state: output above the IN pin",
            -measure.value_at(time, headroom, alone),
            "V",
            expected=0.165,
            high=-_REVERSE_LIMIT,
            source="section 4.2: D11 holds the IN pin 0.15 V to 0.18 V below the output; "
            "LT3080 Rev. E, page 2: not more than 0.3 V",
        ),
        Figure(
            "alone_precharge",
            "In that state: pre-regulator output before SMU_ON rises",
            measure.value_at(time, pre, alone),
            "V",
            high=common.law(common.volts_of(_LOW)),
            source="rule F-28: the converter is never enabled on capacitors charged above "
            "its target, 1.437 V at 0.80 V",
        ),
        Figure(
            "alone_control_current",
            "In that state: current of the VCONTROL pin",
            measure.value_at(time, control_amps, alone),
            "A",
            high=30e-3,
            source="section 4.2: the regulator supplies only the milliamperes of its control "
            "path; LT3080 Rev. E, page 4: 30 mA at the most",
        ),
        Figure(
            "enable_pin",
            "Enable pin of the pre-regulator with SMU_ON high",
            measure.value_at(time, run.real("smu_en"), _WORK),
            "V",
            low=1.2,
            source="section 4.2: threshold of 1.2 V (datasheet value)",
        ),
        Figure(
            "enable_returned",
            "Most power returned to the 5 V rail in the 5 ms after SMU_ON rises",
            -measure.extremes(time, rail, _ENABLE, _WORK)[0] * common.RAIL_5V,
            "W",
            high=0.25,
            source="section 4.2 and section 16: less than the instrument takes from the "
            "rail in source mode without load, for which 0.25 W is the condition",
        ),
        Figure(
            "enable_returned_charge",
            "Charge returned to the 5 V rail in the 5 ms after SMU_ON rises",
            -measure.integral(time, np.minimum(rail, 0.0), _ENABLE, _WORK),
            "C",
        ),
        Figure(
            "enable_inrush",
            "Highest current of the 5 V rail in the 5 ms after SMU_ON rises",
            measure.extremes(time, rail, _ENABLE, _WORK)[1],
            "A",
        ),
        Figure(
            "enable_disturbance",
            "Movement of the regulator output in the 5 ms after SMU_ON rises",
            measure.peak_to_peak(time, out, _ENABLE, _WORK),
            "V",
        ),
        Figure(
            "enable_pre",
            "Pre-regulator output 5 ms after SMU_ON rises",
            measure.value_at(time, pre, _WORK),
            "V",
            expected=common.law(common.volts_of(_LOW)),
            low=1.2,
            source="rule F-28: the pre-regulator is never asked for less than 1.2 V",
        ),
        Figure(
            "rise_slope",
            "Fastest rise of the output after the code of 5.00 V",
            float(rise.max()),
            "V/s",
            expected=520.0,
            high=600.0,
            source="section 4.2: the set-point moves at 0.52 V/ms at most after a full-scale "
            "step; 0.6 V/ms is the limit of this bench",
        ),
        Figure(
            "rise_lag",
            "Largest lag of the output behind the SET drive during that rise",
            measure.extremes(time, drive + common.SET_OFFSET - out, _WORK, _READY)[1],
            "V",
        ),
        Figure(
            "rise_headroom",
            "Lowest voltage of the IN pin above the output during that rise",
            measure.extremes(time, headroom, _WORK, _READY)[0],
            "V",
        ),
        Figure(
            "ready_error",
            "Output below its final value 80 ms after the code of 5.00 V",
            common.volts_of(_HIGH) - measure.value_at(time, out, _READY),
            "V",
            high=0.1,
            source="rule F-28, step 7: within 100 mV of the set-point",
        ),
        Figure(
            "stop_in_pin",
            "Stop: lowest voltage of the IN pin relative to the output",
            measure.extremes(time, headroom, _DISABLE, _STOP)[0],
            "V",
            expected=-0.165,
            low=_REVERSE_LIMIT,
            source="LT3080 Rev. E, page 2: not more than 0.3 V below the output; section 4.2: "
            "0.15 V to 0.18 V with D11",
        ),
        Figure(
            "stop_returned",
            "Stop: lowest current of the 5 V rail after SMU_ON falls",
            measure.extremes(time, rail, _DISABLE, _STOP)[0],
            "A",
            low=-1e-3,
            source="section 4.2: a disabled converter returns nothing; 1 mA is the limit of "
            "this bench",
        ),
        Figure(
            "fall_slope",
            "Fastest fall of the output after the DAC goes to zero",
            float(-fall.min()),
            "V/s",
            expected=520.0,
            high=600.0,
            source="section 4.2: the set-point moves at 0.52 V/ms at most after a full-scale "
            "step; 0.6 V/ms is the limit of this bench",
        ),
        Figure(
            "bleeder",
            "Pre-regulator output 0.2 s after SMU_ON fell",
            measure.value_at(time, pre, _DISABLE + 0.2),
            "V",
            high=0.3,
            source="section 4.2: the bleeder empties the capacitors in about 0.2 s; 0.3 V is "
            "the limit of this bench",
        ),
        Figure(
            "whole_in_pin",
            "Whole run: lowest voltage of the IN pin relative to the output",
            float(headroom.min()),
            "V",
            low=_REVERSE_LIMIT,
            source="LT3080 Rev. E, page 2 (D-57)",
        ),
    ]
    milli = time * 1e3
    graphs = [
        Graph(
            name="start-stop",
            title="Start and stop of the source without a device, to 5.00 V",
            xlabel="Time (ms)",
            panels=(
                Panel("Voltage (V)"),
                Panel("IN pin above the output (V)", marks=((_REVERSE_LIMIT, "rating -0.3 V"),)),
                Panel("Current of the 5 V rail (mA)"),
            ),
            traces=(
                Trace(milli, out, "regulator output", 0),
                Trace(milli, pre, "pre-regulator output", 0),
                Trace(milli, drive, "SET drive", 0, "--"),
                Trace(milli, run.real("smu_en"), "enable pin", 0, ":"),
                Trace(milli, headroom, "", 1),
                Trace(milli, rail * 1e3, "", 2),
            ),
            xmarks=(
                (_FIRST * 1e3, "code of 0.80 V"),
                (_ENABLE * 1e3, "SMU_ON, then 5.00 V"),
                (_DISABLE * 1e3, "SMU_ON low, then DAC zero"),
            ),
        )
    ]
    shown = (time >= _ENABLE - 1e-3) & (time <= _WORK + 12e-3)
    graphs.append(
        Graph(
            name="enable",
            title="The start of the pre-regulator and the first milliseconds of the rise",
            xlabel="Time (ms)",
            panels=(Panel("Voltage (V)"), Panel("Current of the 5 V rail (mA)")),
            traces=(
                Trace(milli[shown], out[shown], "regulator output", 0),
                Trace(milli[shown], pre[shown], "pre-regulator output", 0),
                Trace(milli[shown], drive[shown], "SET drive", 0, "--"),
                Trace(milli[shown], rail[shown] * 1e3, "", 1),
            ),
            xmarks=((_ENABLE * 1e3, "SMU_ON"), (_WORK * 1e3, "5.00 V")),
        )
    )
    for farads, index, tag in ((0.0, 0, "open"), (100e-6, 3, "100uf")):
        step = ctx.run(f"step-down-{tag}", _step_deck(ctx, farads, index), keep=tag == "open")
        clock = step.real("time")
        step_out = step.real("ldo_out")
        step_headroom = step.real("ldo_in") - step_out
        step_rail = _rail_amps(step)
        text = "no device" if not farads else "100 uF at the device, range 3"
        less, _ = _relief(clock, step_rail, _STEP_STOP)
        figures += [
            Figure(
                f"down_headroom_{tag}",
                f"Step from 5.00 V to 0.80 V, {text}: lowest voltage of the IN pin above "
                "the output",
                measure.extremes(clock, step_headroom, _STEP_DOWN, _STEP_STOP)[0],
                "V",
                expected=0.44,
                low=_REVERSE_LIMIT,
                source="section 4.2: at least 0.44 V on a full-scale step down (simulated); "
                "the limit is the rating of the IN pin",
            ),
            Figure(
                f"down_returned_{tag}",
                f"Step from 5.00 V to 0.80 V, {text}: most power returned to the 5 V rail",
                -measure.extremes(clock, step_rail, _STEP_DOWN, _STEP_STOP)[0] * common.RAIL_5V,
                "W",
                expected=0.06,
                high=0.27,
                source="section 4.2: at most 0.27 W (calculated bound), 0.06 W simulated",
            ),
            Figure(
                f"down_less_{tag}",
                f"Step from 5.00 V to 0.80 V, {text}: largest fall of the power taken from "
                "the 5 V rail below its value before the step",
                less,
                "W",
            ),
            Figure(
                f"down_slope_{tag}",
                f"Step from 5.00 V to 0.80 V, {text}: fastest fall of the output",
                float(-_slope(clock, step_out, _STEP_DOWN, _STEP_DOWN + 60e-3).min()),
                "V/s",
            ),
            Figure(
                f"down_settled_{tag}",
                f"Step from 5.00 V to 0.80 V, {text}: output within 10 mV of 0.80 V after",
                measure.settling_time(
                    clock, step_out, float(step_out[-1]), 10e-3, _STEP_DOWN, _STEP_STOP
                ),
                "s",
            ),
        ]
        shown = clock >= _STEP_DOWN - 5e-3
        graphs.append(
            Graph(
                name=f"step-down-{tag}",
                title=f"Set-point step from 5.00 V to 0.80 V, {text}",
                xlabel="Time (ms)",
                panels=(
                    Panel("Voltage (V)"),
                    Panel("IN pin above the output (V)"),
                    Panel("Current of the 5 V rail (mA)"),
                ),
                traces=(
                    Trace(clock[shown] * 1e3, step_out[shown], "regulator output", 0),
                    Trace(clock[shown] * 1e3, step.real("v_pre")[shown], "pre-regulator output", 0),
                    Trace(clock[shown] * 1e3, step.real("set_drv")[shown], "SET drive", 0, "--"),
                    Trace(clock[shown] * 1e3, step_headroom[shown], "", 1),
                    Trace(clock[shown] * 1e3, step_rail[shown] * 1e3, "", 2),
                ),
                xmarks=((_STEP_DOWN * 1e3, "code of 0.80 V"),),
            )
        )
    released = ctx.run("released", _released_deck(ctx), keep=False)
    clock = released.real("time")
    released_out = released.real("ldo_out")
    released_headroom = released.real("ldo_in") - released_out
    released_rail = _rail_amps(released)
    less, relieved = _relief(clock, released_rail, _RELEASED_STOP)
    figures += [
        Figure(
            "released_slope",
            "Set-point taken away at once at 5.00 V, source pair open: fastest fall of the output",
            float(-_slope(clock, released_out, _STEP_DOWN, _STEP_DOWN + 20e-3).min()),
            "V/s",
            expected=750.0,
            low=700.0,
            high=800.0,
            source="section 4.2: a released output falls with 0.7 V/ms to 0.8 V/ms at 5 V "
            "(calculated)",
        ),
        Figure(
            "released_returned",
            "Released output: most power returned to the 5 V rail",
            -measure.extremes(clock, released_rail, _STEP_DOWN, _RELEASED_STOP)[0] * common.RAIL_5V,
            "W",
            expected=0.16,
            high=0.25,
            source="section 4.2: 0.12 W to 0.20 W for about 5 ms (simulated); the limit is "
            "the 0.25 W that the instrument has to take from the rail (section 16)",
        ),
        Figure(
            "released_less",
            "Released output: largest fall of the power taken from the 5 V rail below its "
            "value before",
            less,
            "W",
        ),
        Figure(
            "released_time",
            "Released output: time for which the 5 V rail gives at least 10 mW less than at "
            "rest after the step",
            relieved,
            "s",
            expected=5e-3,
            source="section 4.2: for about 5 ms (simulated)",
        ),
        Figure(
            "released_headroom",
            "Released output: lowest voltage of the IN pin above the output",
            measure.extremes(clock, released_headroom, _STEP_DOWN, _RELEASED_STOP)[0],
            "V",
            low=_REVERSE_LIMIT,
            source="LT3080 Rev. E, page 2 (D-57)",
        ),
        Figure(
            "unfiltered_rise",
            "Set-point given at once, source pair open: slope of the output between 2 V and 4 V",
            2.0
            / (
                measure.first_crossing(clock, released_out, 4.0, rising=True, after=common.READY)
                - measure.first_crossing(clock, released_out, 2.0, rising=True, after=common.READY)
            ),
            "V/s",
            low=520.0,
            source="section 4.2: the set-point moves at 0.52 V/ms at most; the source has to "
            "rise at least that fast for its output to follow (limit of this bench)",
        ),
        Figure(
            "unfiltered_peak",
            "Set-point given at once, source pair open: highest output above its final value",
            measure.extremes(clock, released_out, common.READY, _STEP_DOWN)[1]
            - measure.value_at(clock, released_out, _STEP_DOWN - 1e-3),
            "V",
        ),
    ]
    shown = (clock >= _STEP_DOWN - 2e-3) & (clock <= _STEP_DOWN + 30e-3)
    graphs.append(
        Graph(
            name="released",
            title="The set-point taken away at once at 5.00 V, source pair open",
            xlabel="Time (ms)",
            panels=(
                Panel("Voltage (V)"),
                Panel("IN pin above the output (V)"),
                Panel("Current of the 5 V rail (mA)"),
            ),
            traces=(
                Trace(clock[shown] * 1e3, released_out[shown], "regulator output", 0),
                Trace(clock[shown] * 1e3, released.real("v_pre")[shown], "pre-regulator output", 0),
                Trace(clock[shown] * 1e3, released.real("set_drv")[shown], "SET drive", 0, "--"),
                Trace(clock[shown] * 1e3, released_headroom[shown], "", 1),
                Trace(clock[shown] * 1e3, released_rail[shown] * 1e3, "", 2),
            ),
            xmarks=((_STEP_DOWN * 1e3, "code of 0.80 V"),),
        )
    )
    notes = (
        "The paths to the device stay open in the start and stop run: steps 6 to 8 of "
        "rule F-28, the source pair, the check of the monitor and the output pair, belong "
        "to other blocks. Nothing hangs on the regulator output there but the parts of "
        "the sheet. In the two set-point steps the source pair is closed: the capacitors "
        "of the supply node hang on the output through the resistor that stands for it.",
        "The rails and the reference are ideal sources, so no rail moves when the "
        "converter starts or returns current: the current of the 5 V rail is what the "
        "source asks of it, not what the rail does with it.",
        "The power returned to the 5 V rail is the current of that rail, so it is what "
        "is left after the losses of the converter model: about 0.09 W, fitted to one "
        "efficiency curve at 3.6 V and taken to hold at 5 V. At 5.00 V without a device "
        "the source takes 0.16 W, of which 0.07 W go to the bleeder and to the minimum "
        "load. A converter without losses would return more; the fall of the power "
        "below its value before the step is an upper bound for that, to be held "
        "against the 0.06 W and the 0.12 W to 0.20 W of section 4.2.",
        "The run with the set-point taken away at once is not a state of the schematic: "
        "C41 is reduced to a thousandth, 10 us in place of 10 ms. The output then falls "
        "with its minimum load and with 3 mA more, which the clamp between OUT and SET "
        "of the regulator carries into R60: 0.70 V/ms over the first 0.2 ms, in which "
        "the output is already at 4.8 V. The figure stands 0.06 % below the 0.7 V/ms to "
        "0.8 V/ms of the specification and fails on that digit; the calculation of "
        "the specification is confirmed.",
        "With the filter in place the set-point of a full-scale step down falls with "
        "0.42 V/ms at first. The minimum load alone takes the output down with 0.36 "
        "V/ms while the source pair is closed, so the output lags its set-point by up "
        "to 84 mV for the first 8 ms, and by 0.7 V for tens of milliseconds with 100 uF "
        "at the device: the regulator cannot take current, and the clamp between OUT "
        "and SET conducts.",
        "Given at once, a set-point of 5.00 V is followed with 1.2 V/ms: the regulator "
        "rises in dropout as fast as the pre-regulator follows its own output through "
        "the diode of D13. That is 2.4 times the slope that the filter lets through, "
        "so the output follows the filtered set-point, 42 mV behind at the most.",
        "How the IN pin is fed while the pre-regulator is off depends on the reverse "
        "gain of the pass transistor of the regulator model, which is an assumption: "
        "with it the pin is charged from the control supply through the transistor, "
        "and D11 carries little.",
        "The converter is the averaged model. What the real part does when it is "
        "enabled on a charged output is not in its datasheet; the model starts its "
        "duty cycle from zero behind a time constant of 0.21 ms, and it may take up to "
        "0.7 A back from its output in forced PWM (TI SLVA726).",
        "The DAC is a behavioral model whose code changes in a step; the frames of the "
        "serial interface and the ramp of firmware (1 V/ms by default) are not simulated.",
    )
    return Outcome(tuple(figures), tuple(graphs), notes)
