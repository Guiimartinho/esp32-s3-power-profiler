"""The three comparator thresholds, at the comparator inputs and at the shunt."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from benches import frontend
from benches.range_logic import common
from circuit_sim import measure, tolerance
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_NAMES = ("up", "oc", "jump")
_TITLES = {"up": "Step up", "oc": "Over-current", "jump": "Jump"}
_OUTPUTS = {"up": "cmp_up", "oc": "cmp_oc", "jump": "cmp_jump"}

_TABLE_INPUT = {"up": 0.464, "oc": 0.584, "jump": 0.764}
"""Thresholds at the comparator inputs, V (table of section 4.4)."""

_TABLE_SHUNT = {"up": 0.091, "oc": 0.115, "jump": 0.151}
"""Thresholds at the shunt, V (table of section 4.4)."""

_STRING = ("R132", "R133", "R134", "R135")
"""The resistor string on the reference, from the reference down to ground."""

_BELOW = {"up": ("R135",), "oc": ("R134", "R135"), "jump": ("R133", "R134", "R135")}
"""The resistors of the string below the tap of each comparator."""

_OFFSET_LIMIT = 0.010
"""Largest input offset of a comparator, V (datasheet value quoted in section 4.4)."""

_GAIN_ERROR = 0.003
"""Largest gain error of the amplifier at this gain (AD8421 datasheet, page 4, A grade)."""

_INPUT_OFFSET = 60e-6
_OUTPUT_OFFSET = 350e-6
"""Largest offsets of the amplifier, V (AD8421 datasheet, page 4, A grade)."""

_BUFFER_OFFSET = 100e-6
"""Largest offset of the pedestal buffer, V (figure of its model)."""

_REFERENCE_TOLERANCE = 0.001
"""Tolerance of the reference: an assumption, the standard grade of the part."""

_FULL_SCALE = 2.5
"""Converter input at full scale, V."""

_LOW_AMPS, _HIGH_AMPS = 0.80, 1.60
"""The load current of the ramp in range 3: 80 mV to 160 mV at the shunt."""

_SLOW_RAMP = 2e-3
"""Duration of one slope of the ramp in the nominal run, s."""

_FAST_RAMP = 0.4e-3
"""Duration of one slope in the tolerance runs, s."""

_START = 20e-6
"""Rest before the ramp, s."""

_DRAWS = 120
"""Number of Monte Carlo runs."""

_SEED = 20261010
"""Seed of the Monte Carlo runs, so that every run of the bench draws the same boards."""


@dataclass(frozen=True, slots=True)
class _Board:
    """One set of deviations from the nominal circuit.

    Attributes:
        scales: Factors on the values of resistors.
        offsets: Input offsets of the three comparators.
        amplifier: Parameters of the amplifier model that differ from zero.
        buffer_offset: Offset of the pedestal buffer, V.
        reference: Factor on the reference voltage.
    """

    scales: dict[str, float]
    offsets: common.Offsets
    amplifier: str = ""
    buffer_offset: float = 0.0
    reference: float = 1.0


_NOMINAL = _Board({}, common.Offsets())


def _corner(ctx: Context, name: str, sign: int, everything: bool) -> _Board:
    """The board that puts one threshold at an end of its range.

    Args:
        ctx: The bench context.
        name: The comparator.
        sign: +1 for the highest threshold at the shunt, -1 for the lowest.
        everything: Also move what the specification does not name: gain
            error and offsets of the amplifier, pedestal, reference.
    """
    spread = tolerance.tolerances(ctx.netlist, (*_STRING, "R136", "R137", "R123", "R121", "R122"))
    signs = {ref: (sign if ref in _BELOW[name] else -sign) for ref in _STRING}
    signs.update({"R136": sign, "R137": -sign, "R123": sign})
    if everything:
        signs.update({"R121": sign, "R122": -sign})
    scales = tolerance.corner_scales(spread, signs)
    offsets = common.Offsets(**{name: sign * _OFFSET_LIMIT})
    if not everything:
        return _Board(scales, offsets)
    # A gain error is the same as a gain resistor that is off by that much
    # more: the gain is 1 + 9.9 kohm / RG, 0.95 of it comes from the resistor.
    scales["R123"] *= 1.0 + sign * _GAIN_ERROR * common.GAIN / (common.GAIN - 1.0)
    return _Board(
        scales,
        offsets,
        amplifier=f"vosi={sign * _INPUT_OFFSET:g} voso={-sign * _OUTPUT_OFFSET:g}",
        buffer_offset=sign * _BUFFER_OFFSET,
        reference=1.0 + sign * _REFERENCE_TOLERANCE,
    )


def _draws(ctx: Context) -> list[_Board]:
    """The boards of the Monte Carlo runs: resistors and offsets, uniform."""
    rng = np.random.default_rng(_SEED)
    spread = tolerance.tolerances(ctx.netlist, (*_STRING, "R136", "R137", "R123"))
    boards = []
    for _ in range(_DRAWS):
        scales = tolerance.draw_scales(spread, rng)
        up, oc, jump = (float(value) for value in rng.uniform(-_OFFSET_LIMIT, _OFFSET_LIMIT, 3))
        boards.append(_Board(scales, common.Offsets(up=up, oc=oc, jump=jump)))
    return boards


def _deck(ctx: Context, board: _Board, slope: float, title: str) -> str:
    """Range 3 held, the load current ramped up and down again."""
    more: dict[str, PartModel] = {}
    if board.amplifier:
        base = ctx.models.model_of(ctx.netlist.component("U27"))
        more["U27"] = replace(base, params=board.amplifier)
    if board.buffer_offset != 0.0:
        base = ctx.models.model_of(ctx.netlist.component("U26"))
        more["U26"] = replace(base, params=f"vos={board.buffer_offset:g}")
    circuit = common.front_end(ctx, offsets=board.offsets, scales=board.scales, more=more)
    ramp = common.pwl(
        (
            (0.0, _LOW_AMPS),
            (_START, _LOW_AMPS),
            (_START + slope, _HIGH_AMPS),
            (_START + 2.0 * slope, _LOW_AMPS),
        )
    )
    end = 2.0 * _START + 2.0 * slope
    return ctx.deck(
        title,
        circuit,
        frontend.rails(vref=2.5 * board.reference),
        frontend.fixed_range(3, output_on=True),
        common.source(5.0),
        common.dut(ramp, None),
        common.rest(circuit, 3, sequencer=False),
        control=[
            "save inp inn amp_raw cmp_in adc_in cmp_up cmp_oc cmp_jump th_up th_oc th_jump "
            "iprog @r110[i]",
            f"tran {slope / 4000.0:g} {end:g}",
        ],
        options=common.options(ctx),
    )


@dataclass(frozen=True, slots=True)
class _Found:
    """What one ramp shows of one board.

    Attributes:
        shunt: Threshold of each comparator at the shunt, V: the middle of
            the voltages at which its output rises and falls.
        input: The same at the comparator input, V.
        hysteresis: Distance between the two at the comparator input, V.
        hysteresis_shunt: The same referred to the shunt, V.
        amps: Load current at the threshold, A.
        full_scale: Shunt voltage at which the converter input is at full scale, V.
    """

    shunt: dict[str, float]
    input: dict[str, float]
    hysteresis: dict[str, float]
    hysteresis_shunt: dict[str, float]
    amps: dict[str, float]
    full_scale: float


def _middle(time: np.ndarray, wave: np.ndarray, rises: float, falls: float) -> float:
    """The middle of the values of a waveform at two instants."""
    return 0.5 * (measure.value_at(time, wave, rises) + measure.value_at(time, wave, falls))


def _span(time: np.ndarray, wave: np.ndarray, rises: float, falls: float) -> float:
    """The distance of the values of a waveform at two instants."""
    return measure.value_at(time, wave, rises) - measure.value_at(time, wave, falls)


def _read(result: RunResult) -> _Found:
    """The thresholds of one run."""
    time = result.real("time")
    shunt = result.real("inp") - result.real("inn")
    at_input = result.real("cmp_in")
    amps = result.real("@r110[i]")
    found = _Found({}, {}, {}, {}, {}, 0.0)
    for name in _NAMES:
        output = result.real(_OUTPUTS[name])
        rises = measure.first_crossing(time, output, common.HALF_LOGIC, rising=True)
        falls = measure.first_crossing(time, output, common.HALF_LOGIC, rising=False, after=rises)
        found.shunt[name] = _middle(time, shunt, rises, falls)
        found.input[name] = _middle(time, at_input, rises, falls)
        found.amps[name] = _middle(time, amps, rises, falls)
        found.hysteresis[name] = _span(time, at_input, rises, falls)
        found.hysteresis_shunt[name] = _span(time, shunt, rises, falls)
    converter = result.real("adc_in")
    up = measure.first_crossing(time, converter, _FULL_SCALE, rising=True)
    down = measure.first_crossing(time, converter, _FULL_SCALE, rising=False, after=up)
    return replace(found, full_scale=_middle(time, shunt, up, down))


def _band(name: str, key: str, label: str, value: float) -> Figure:
    """A threshold at the shunt against the band of the specification."""
    low, high = common.THRESHOLD_BAND[name]
    return Figure(
        key, label, value, "V", low=low, high=high, source="table of section 4.4, with tolerances"
    )


@bench(
    "range_logic",
    "thresholds",
    "The three comparator thresholds, with tolerances, and their hysteresis",
    "section 4.4 (table of the thresholds, over-current level), decisions D-28 and D-74",
)
def thresholds(ctx: Context) -> Outcome:
    """Range 3 is held and the load current is ramped from 0.8 A to 1.6 A and back.

    The shunt voltage passes all three thresholds twice, slowly. For each
    comparator the run reads the shunt voltage and the voltage at its own
    input at the instants its output rises and falls: their middle is the
    threshold, their distance the hysteresis. The same ramp tells at which
    shunt voltage the input of the converter reaches full scale. The run is
    repeated with every part at the end of its tolerance that moves one
    threshold furthest, first with what the specification names (the six
    resistors of the string and the divider, the gain resistor, 10 mV of
    comparator offset), then with what it does not name as well (gain error
    and offsets of the amplifier, the pedestal, the reference), and with
    120 boards drawn at random.
    """
    result = ctx.run("nominal", _deck(ctx, _NOMINAL, _SLOW_RAMP, "Thresholds, nominal"))
    nominal = _read(result)
    decks: dict[str, str] = {}
    for name in _NAMES:
        for sign, end in ((-1, "low"), (1, "high")):
            for everything, kind in ((False, "named"), (True, "all")):
                board = _corner(ctx, name, sign, everything)
                title = f"Thresholds, {name} at its {end} end, {kind} tolerances"
                decks[f"{kind}-{name}-{end}"] = _deck(ctx, board, _FAST_RAMP, title)
    for index, board in enumerate(_draws(ctx)):
        decks[f"draw-{index:03d}"] = _deck(ctx, board, _FAST_RAMP, f"Thresholds, board {index}")
    found = {key: _read(run) for key, run in ctx.run_many(decks).items()}
    drawn = [found[f"draw-{index:03d}"] for index in range(_DRAWS)]

    figures: list[Figure] = []
    for name in _NAMES:
        title = _TITLES[name]
        figures += [
            Figure(
                f"input_{name}",
                f"{title}: threshold at the comparator input",
                nominal.input[name],
                "V",
                expected=_TABLE_INPUT[name],
                low=_TABLE_INPUT[name] - 0.5e-3,
                high=_TABLE_INPUT[name] + 0.5e-3,
                source="table of section 4.4, to its last digit",
            ),
            Figure(
                f"shunt_{name}",
                f"{title}: threshold at the shunt",
                nominal.shunt[name],
                "V",
                expected=_TABLE_SHUNT[name],
                low=_TABLE_SHUNT[name] - 0.5e-3,
                high=_TABLE_SHUNT[name] + 0.5e-3,
                source="table of section 4.4, to its last digit",
            ),
            Figure(
                f"hysteresis_{name}",
                f"{title}: hysteresis at the comparator input",
                nominal.hysteresis[name],
                "V",
                low=1e-3,
                high=5e-3,
                source="datasheet range of 1 mV to 5 mV (section 3); the model is set to 3 mV",
            ),
            Figure(
                f"hysteresis_shunt_{name}",
                f"{title}: hysteresis referred to the shunt",
                nominal.hysteresis_shunt[name],
                "V",
            ),
        ]
    figures.append(
        Figure(
            "trip_current",
            "Load current at the over-current threshold in range 3",
            nominal.amps["oc"],
            "A",
            expected=1.15,
            low=1.114,
            high=1.187,
            source="section 4.4: 1.15 A, 1.114 A to 1.187 A with tolerances",
        )
    )
    for kind, text in (("named", "tolerances the specification names"), ("all", "every tolerance")):
        for name in _NAMES:
            for end, word in (("low", "lowest"), ("high", "highest")):
                figures.append(
                    _band(
                        name,
                        f"corner_{kind}_{name}_{end}",
                        f"{_TITLES[name]}: {word} threshold at the shunt, {text}",
                        found[f"{kind}-{name}-{end}"].shunt[name],
                    )
                )
    for name in _NAMES:
        values = np.array([board.shunt[name] for board in drawn])
        figures += [
            _band(
                name,
                f"draws_{name}_low",
                f"{_TITLES[name]}: lowest of {_DRAWS} random boards",
                float(values.min()),
            ),
            _band(
                name,
                f"draws_{name}_high",
                f"{_TITLES[name]}: highest of {_DRAWS} random boards",
                float(values.max()),
            ),
        ]
    margins = [board.full_scale - board.shunt["oc"] for board in drawn]
    corner_margin = found["all-oc-high"].full_scale - found["all-oc-high"].shunt["oc"]
    figures += [
        Figure(
            "full_scale",
            "Shunt voltage at which the converter input is at full scale",
            nominal.full_scale,
            "V",
            expected=0.1229,
            low=0.1229 * 0.995,
            high=0.1229 * 1.005,
            source="section 4.3: 122.9 mV, calculated",
        ),
        Figure(
            "margin_nominal",
            "Full scale of the converter above the over-current threshold, nominal",
            nominal.full_scale - nominal.shunt["oc"],
            "V",
        ),
        Figure(
            "margin_draws",
            f"The same, least of {_DRAWS} random boards",
            float(min(margins)),
            "V",
            low=0.0,
            source="section 4.4: the level lies below the full scale on every board",
        ),
        Figure(
            "margin_corner",
            "The same with the over-current threshold at its highest, every tolerance",
            corner_margin,
            "V",
            expected=3.6e-3,
            low=0.0,
            source="section 4.4: 3.6 mV to spare in the worst case, calculated",
        ),
    ]

    milli = result.real("time") * 1e3
    shunt = (result.real("inp") - result.real("inn")) * 1e3
    ramp = Graph(
        name="ramp",
        title="Range 3 held, the load ramped from 0.8 A to 1.6 A and back: nominal circuit",
        xlabel="Time (ms)",
        panels=(
            Panel(
                "Shunt voltage (mV)",
                marks=tuple(
                    (common.THRESHOLD_SHUNT[name] * 1e3, _TITLES[name].lower()) for name in _NAMES
                ),
            ),
            Panel("At the comparator inputs (V)"),
            Panel("Comparator outputs (V)"),
            Panel("Converter input (V)", marks=((_FULL_SCALE, "full scale 2.5 V"),)),
        ),
        traces=(
            Trace(milli, shunt, "at the amplifier inputs", 0),
            Trace(milli, result.real("cmp_in"), "amplifier output divided by 4.01", 1),
            Trace(milli, result.real("th_up"), "step-up tap", 1, "--"),
            Trace(milli, result.real("th_oc"), "over-current tap", 1, "--"),
            Trace(milli, result.real("th_jump"), "jump tap", 1, "--"),
            Trace(milli, result.real("cmp_up"), "CMP_UP", 2),
            Trace(milli, result.real("cmp_oc"), "CMP_OC", 2),
            Trace(milli, result.real("cmp_jump"), "CMP_JUMP", 2),
            Trace(milli, result.real("adc_in"), "behind the driver", 3),
        ),
    )
    fraction = (np.arange(_DRAWS) + 0.5) / _DRAWS
    traces = []
    for name in _NAMES:
        values = np.sort([board.shunt[name] for board in drawn])
        traces.append(
            Trace((values - common.THRESHOLD_SHUNT[name]) * 1e3, fraction, _TITLES[name], 0)
        )
    spread = Graph(
        name="spread",
        title=f"The three thresholds on {_DRAWS} random boards, around their nominal values",
        xlabel="Threshold at the shunt minus its nominal value (mV)",
        panels=(Panel("Share of the boards below"),),
        traces=tuple(traces),
        xmarks=tuple(
            (
                (common.THRESHOLD_BAND["up"][end] - common.THRESHOLD_SHUNT["up"]) * 1e3,
                "limit of the step-up band, the narrowest",
            )
            for end in (0, 1)
        ),
    )
    notes = (
        "A threshold is the middle of the two shunt voltages at which the "
        "comparator output rises and falls on a slow ramp; the delay of the chain "
        "shifts both by the same amount in opposite directions and drops out.",
        "The hysteresis of 3 mV is a parameter of the comparator model, inside the "
        "1 mV to 5 mV of the datasheet: the figure shows that the circuit passes it "
        "on unchanged, not what a part has. It moves the threshold for a rising "
        "voltage by half of it, 0.3 mV at the shunt, 0.5 mV for a part at 5 mV.",
        "Tolerances the specification names: the 0.1 % of R132 to R137 and of the "
        "gain resistor R123, and 10 mV of comparator offset. Every tolerance adds "
        "0.3 % of gain error and 60 uV and 350 uV of offset of the amplifier "
        "(datasheet limits of the A grade), 0.1 % on the two pedestal resistors, "
        "100 uV of the pedestal buffer and 0.1 % of the reference. The 0.1 % of "
        "the reference is an assumption.",
        "Random boards: the seven resistors uniform inside 0.1 % and the three "
        "offsets uniform inside 10 mV, each comparator with its own. Uniform is "
        "the cautious reading of an offset limit; real parts cluster near the "
        "typical 3 mV.",
        "The drift with temperature is not in these runs: 25 ppm/K on the "
        "resistors moves a threshold by less than 0.01 mV over 20 K.",
        "The margin to full scale is taken at the input of the converter in the "
        "same run; the converter itself is not in the circuit.",
    )
    return Outcome(tuple(figures), (ramp, spread), notes)
