"""The set-point: from the DAC code to the voltage at the regulator output and at the terminal."""

from __future__ import annotations

import numpy as np

from benches import frontend
from benches.source_meter import common
from circuit_sim import tolerance
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.engine import RunResult

_CODES = (0, 16, 100, 616, 617, 1000, 1553, 2048, 2567, 3000, 3893, 3894, 4095)
"""DAC codes of the nominal run; 616 and 3893 are the codes of 0.80 V and 5.00 V."""

_LOW = common.code_of(0.8)
_HIGH = common.code_of(5.0)
_TOP = 4095

_DRAWS = 24
"""Random sets of part values per code."""

_SEED = 20261010
"""Seed of the random sets, so that a run can be repeated."""

_PATH = ("R55", "R56", "R57", "R58", "R54", "R60")
"""Resistors between the reference and the SET pin."""

_REFERENCE_SPREAD = 0.0005
"""Tolerance taken for the reference voltage: 0.05 % (assumption for this bench;
the reference belongs to another block)."""

_SET_SPREAD = 0.02
"""Tolerance of the SET current over temperature and load (LT3080 Rev. E, page 4)."""

_DAC_GAIN = 0.01
_DAC_OFFSET = 0.01 * 2.5
"""Limits of the gain and offset error of the DAC: 1 % of the range (DS22248A, page 4)."""

_UNBUFFERED = 165e3
"""Resistance of the reference input of the DAC in unbuffered mode (DS22248A, page 4)."""

_DRIFT = 25e-6 * 40.0
"""Change of a 25 ppm/K resistor over 40 K."""

_REGULATOR_OFFSET = 3.5e-3
"""Limit of the offset from SET to OUT over temperature (LT3080 Rev. E, page 4)."""


def _figure_volts(run: RunResult, name: str = "ldo_out") -> float:
    return common.last(run, name)


@bench(
    "source_meter",
    "setpoint",
    "The set-point: DAC code to output voltage, step, ceiling and tolerances",
    "section 4.2 (voltage control, ceiling), rule F-30, requirement R-08, decision D-58",
)
def setpoint(ctx: Context) -> Outcome:
    """The whole source is powered up at one DAC code after the other and read at rest.

    The nominal run gives the output over the code, its step, the offset
    that the SET current adds and the ceiling at the highest code. A wrong
    gain bit is one more run. Random sets of resistor values, reference
    voltage and SET current give the spread of the uncalibrated output at
    0.80 V and at 5.00 V, and one run with every part at the limit that
    raises the output gives the ceiling at the tolerance limits. Four runs
    with the full-scale current of each range give the voltage at the
    terminal behind the burden.
    """
    decks = {
        f"code-{code}": common.settle_deck(
            ctx, f"Set-point at code {code}", common.volts_of(code), code=code
        )
        for code in _CODES
    }
    decks["gain-bit"] = common.settle_deck(
        ctx, "Code of 5.00 V with the gain bit wrong", 2.5, code=_HIGH, dac={"gain": 1}
    )
    decks["unbuffered"] = common.settle_deck(
        ctx,
        "Code of 5.00 V with the reference input unbuffered",
        5.0,
        code=_HIGH,
        extra=f"* the unbuffered reference input of the DAC\nRinput dac_ref 0 {_UNBUFFERED:g}\n",
    )
    decks["drift-reference"] = common.settle_deck(
        ctx,
        "Code of 5.00 V with R55 and R56 apart by their drift over 40 K",
        5.0,
        code=_HIGH,
        scales={"R55": 1.0 - _DRIFT, "R56": 1.0 + _DRIFT},
    )
    decks["drift-gain"] = common.settle_deck(
        ctx,
        "Code of 5.00 V with R57 and R58 apart by their drift over 40 K",
        5.0,
        code=_HIGH,
        scales={"R57": 1.0 - _DRIFT, "R58": 1.0 + _DRIFT},
    )
    spread = tolerance.tolerances(ctx.netlist, _PATH)
    rng = np.random.default_rng(_SEED)
    draws: dict[str, tuple[int, float, float]] = {}
    for code in (_LOW, _HIGH):
        for draw in range(_DRAWS):
            scales = tolerance.draw_scales(spread, rng)
            reference = common.REFERENCE * (1.0 + float(rng.uniform(-1, 1)) * _REFERENCE_SPREAD)
            current = 10e-6 * (1.0 + float(rng.uniform(-1, 1)) * _SET_SPREAD)
            name = f"draw-{code}-{draw}"
            draws[name] = (code, reference, current)
            decks[name] = common.settle_deck(
                ctx,
                f"Set-point at code {code}, random part values",
                common.volts_of(code),
                code=code,
                scales=scales,
                supplies={"vref": reference},
                overrides={common.REGULATOR: common.part(ctx, common.REGULATOR, iset=current)},
            )
    corner = tolerance.corner_scales(spread, {"R55": -1, "R56": 1, "R57": -1, "R58": 1})
    decks["ceiling-limit"] = common.settle_deck(
        ctx,
        "Highest code with every part at the limit that raises the output",
        5.39,
        code=_TOP,
        scales=corner,
        supplies={"vref": common.REFERENCE * (1.0 + _REFERENCE_SPREAD)},
        dac={"gerr": _DAC_GAIN, "offs": _DAC_OFFSET},
        overrides={
            common.REGULATOR: common.part(
                ctx, common.REGULATOR, iset=10e-6 * (1.0 + _SET_SPREAD), vos=_REGULATOR_OFFSET
            )
        },
    )
    for index, amps in enumerate(frontend.FULL_SCALE_AMPS):
        decks[f"burden-r{index}"] = common.settle_deck(
            ctx,
            f"Full scale of range {index} at 5.00 V",
            5.0,
            code=_HIGH,
            amps=amps,
            index=index,
        )
    keep = {"code-616", "code-3893"}
    runs = {name: ctx.run(name, deck) for name, deck in decks.items() if name in keep}
    runs.update(ctx.run_many({name: deck for name, deck in decks.items() if name not in keep}))

    out = {code: _figure_volts(runs[f"code-{code}"]) for code in _CODES}
    law = {code: common.volts_of(code) for code in _CODES}
    low_run, high_run = runs[f"code-{_LOW}"], runs[f"code-{_HIGH}"]
    buffer_gain = (common.last(high_run, "set_drv") - common.last(low_run, "set_drv")) / (
        common.last(high_run, "dac_out") - common.last(low_run, "dac_out")
    )
    rest = max(common.at_rest(run) for run in runs.values())
    figures = [
        near(
            "out_616",
            "Output at code 616",
            out[_LOW],
            "V",
            law[_LOW],
            0.002,
            "rule F-30: 10 mV + code x 1.2817 mV, nominal code of 0.80 V",
        ),
        near(
            "out_3893",
            "Output at code 3893",
            out[_HIGH],
            "V",
            law[_HIGH],
            0.0005,
            "rule F-30: nominal code of 5.00 V",
        ),
        near(
            "step_low",
            "Step from code 616 to code 617",
            out[617] - out[616],
            "V",
            common.SET_STEP,
            0.01,
            "rule F-30: 1.2817 mV; requirement R-08: steps of 1.3 mV",
        ),
        near(
            "step_high",
            "Step from code 3893 to code 3894",
            out[3894] - out[3893],
            "V",
            common.SET_STEP,
            0.01,
            "rule F-30: 1.2817 mV",
        ),
        near(
            "buffer_gain",
            "Gain of the buffer U17, between the two codes",
            buffer_gain,
            "",
            common.BUFFER_GAIN,
            0.001,
            "section 4.2: gain 2.1 with R57 and R58",
        ),
        Figure(
            "set_offset",
            "Output above the SET drive at code 616: the SET current in R60",
            out[_LOW] - common.last(low_run, "set_drv"),
            "V",
            expected=common.SET_OFFSET,
            low=8e-3,
            high=12e-3,
            source="section 4.2: about 10 mV",
        ),
        near(
            "dac_reference",
            "Reference input of the DAC (TP19)",
            common.last(high_run, "dac_ref"),
            "V",
            common.REFERENCE / 2.0,
            0.001,
            "section 4.2 and section 16: half the reference at TP19",
        ),
        near(
            "ceiling",
            "Output at the highest code, nominal parts",
            out[_TOP],
            "V",
            5.26,
            0.002,
            "section 4.2 and rule F-30: 5.26 V nominal",
        ),
        Figure(
            "ceiling_limit",
            "Output at the highest code, every part at the limit that raises it",
            _figure_volts(runs["ceiling-limit"]),
            "V",
            expected=5.39,
            high=5.5,
            source="section 4.2: 5.39 V at the tolerance limits, below the 5.5 V of the "
            "level translator",
        ),
        near(
            "gain_bit",
            "Output at code 3893 with the gain bit wrong",
            _figure_volts(runs["gain-bit"]),
            "V",
            (law[_HIGH] - common.SET_OFFSET) / 2.0 + common.SET_OFFSET,
            0.002,
            "section 4.2: a wrong gain bit halves the output",
        ),
        Figure(
            "unbuffered",
            "Fall of the output at code 3893 with the reference input unbuffered",
            out[_HIGH] - _figure_volts(runs["unbuffered"]),
            "V",
            expected=0.030,
            low=0.025,
            high=0.035,
            source="rule F-6: the unbuffered input would load the divider by 0.6 %, 30 mV at 5.0 V",
        ),
        Figure(
            "drift_reference",
            "Rise of the output at 5.00 V with R55 and R56 apart by 25 ppm/K over 40 K each",
            _figure_volts(runs["drift-reference"]) - out[_HIGH],
            "V",
            expected=5e-3,
            low=4e-3,
            high=6e-3,
            source="section 4.2: up to 5 mV per pair at 5 V over 40 K",
        ),
        Figure(
            "drift_gain",
            "Rise of the output at 5.00 V with R57 and R58 apart by 25 ppm/K over 40 K each",
            _figure_volts(runs["drift-gain"]) - out[_HIGH],
            "V",
            expected=5e-3,
            low=4e-3,
            high=6e-3,
            source="section 4.2: up to 5 mV per pair at 5 V over 40 K",
        ),
        Figure(
            "zero_code",
            "Output at code 0",
            out[0],
            "V",
            expected=common.SET_OFFSET,
            source="section 4.2: 0.01 V; the swing of the DAC ends 10 mV above ground",
        ),
    ]
    for code, text in ((_LOW, "0.80 V"), (_HIGH, "5.00 V")):
        values = np.array(
            [_figure_volts(runs[name]) for name, (drawn, _, _) in draws.items() if drawn == code]
        )
        figures += [
            Figure(
                f"spread_low_{code}",
                f"Lowest output of {_DRAWS} random sets at the code of {text}",
                float(values.min()),
                "V",
                expected=law[code],
            ),
            Figure(
                f"spread_high_{code}",
                f"Highest output of {_DRAWS} random sets at the code of {text}",
                float(values.max()),
                "V",
                expected=law[code],
            ),
        ]
    burden_traces = []
    for index, amps in enumerate(frontend.FULL_SCALE_AMPS):
        run = runs[f"burden-r{index}"]
        drop = common.last(run, "ldo_out") - common.last(run, "dut")
        figures.append(
            Figure(
                f"terminal_r{index}",
                f"Range {index}: regulator output above the terminal at full scale",
                drop,
                "V",
                expected=0.144 if index == 3 else None,
                high=0.2 if index == 3 else None,
                source="requirement R-06: 200 mV at 1 A; section 2: 144 mV typical"
                if index == 3
                else "",
            )
        )
        figures.append(
            Figure(
                f"regulation_r{index}",
                f"Range {index}: fall of the regulator output at full scale",
                out[_HIGH] - common.last(run, "ldo_out"),
                "V",
            )
        )
        burden_traces.append((amps, drop))
    figures.append(
        Figure(
            "rest",
            "Largest movement of output and pre-regulator in the last 2 ms of any run",
            rest,
            "V",
            high=common.REST_LIMIT,
            source="limit of this bench: a run counts as at rest below 0.1 mV",
        )
    )
    codes = np.array(_CODES, dtype=np.float64)
    graph = Graph(
        name="transfer",
        title="Set-point: output of the regulator over the DAC code, nominal parts",
        xlabel="DAC code",
        panels=(
            Panel("Output (V)", marks=((0.8, "0.80 V"), (5.0, "5.00 V"))),
            Panel("Output minus 10 mV + code x 1.2817 mV (mV)"),
        ),
        traces=(
            Trace(codes, np.array([out[code] for code in _CODES]), "regulator output", 0),
            Trace(
                codes,
                np.array([(out[code] - law[code]) * 1e3 for code in _CODES]),
                "deviation from the law of rule F-30",
                1,
            ),
        ),
    )
    time = high_run.real("time") * 1e3
    start = Graph(
        name="power-up",
        title="The run that every figure is read from: power-up to code 3893",
        xlabel="Time (ms)",
        panels=(Panel("Voltage (V)"),),
        traces=(
            Trace(time, high_run.real("ldo_out"), "regulator output", 0),
            Trace(time, high_run.real("v_pre"), "pre-regulator output", 0),
            Trace(time, high_run.real("set_drv"), "SET drive", 0, "--"),
        ),
    )
    notes = (
        "Every figure is the end of a run that starts with all rails at zero and ends at "
        "rest; the capacitor of the set-point filter, C41, has one hundredth of its "
        "value in these runs, which changes no voltage at rest.",
        "The rails and the reference are ideal sources. The DAC is the behavioral model "
        "without the serial interface: its code is a parameter, and the frame of rule "
        "F-6 is not simulated.",
        "The random sets draw the six resistors of the path inside their tolerance, the "
        "reference inside 0.05 % (assumption) and the SET current inside 2 %. The error "
        "of the DAC is left out of them: the calibration of rule F-30 removes it. The "
        "ceiling at the limits adds 1 % of gain and 1 % of offset of the DAC and 3.5 mV "
        "of regulator offset.",
        "At the highest code the pre-regulator is asked for 5.70 V, above the 5.5 V at "
        "which its datasheet ends; the model follows up to its assumed over-voltage "
        "level of 6.2 V. Rule F-30 keeps the set-point at or below 5.00 V.",
        "The path to the terminal is three resistors that stand for the closed switches, "
        "the shunt, copper and contacts; the ladder and the switches belong to other "
        "blocks.",
    )
    return Outcome(tuple(figures), (graph, start), notes)
