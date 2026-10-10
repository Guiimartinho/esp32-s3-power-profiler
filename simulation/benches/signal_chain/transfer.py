"""From the shunt voltage to the converter input and to the code."""

from __future__ import annotations

import numpy as np

from benches import frontend
from benches.signal_chain import common
from circuit_sim import tolerance
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_SWEEP = (-5e-3, 160e-3, 0.25e-3)
"""Shunt voltage of the sweep: start, stop, step."""

_LINEAR = (5e-3, 115e-3)
"""Span of the shunt voltage over which the straight line is fitted."""

_DRAWS = 120
"""Boards of the Monte Carlo run."""

_POINTS = (0.0, 10e-3, 110e-3)
"""Shunt voltages at which a board of the Monte Carlo run is solved."""

_SEED = 20261010
"""Seed of the Monte Carlo run, so that it gives the same boards every time."""

_GAIN_ERROR = 0.002
"""Gain error of the amplifier itself, at most (AD8421 datasheet, page 4)."""

_INPUT_OFFSET = 60e-6
"""Offset of the input stage of the amplifier, at most (AD8421, page 3)."""

_OUTPUT_OFFSET = 350e-6
"""Offset of the output stage of the amplifier, at most (AD8421, page 3)."""

_BUFFER_OFFSET = 100e-6
"""Offset of the pedestal buffer, at most (OPA197 datasheet, page 7)."""

_DRIVER_OFFSET = 200e-6
"""Offset of the converter driver, at most (OPA365 datasheet, page 6)."""

_CONVERTER_OFFSET = 4e-3
"""Offset error of the converter, at most (ADS8860 datasheet, page 6)."""

_HEADROOM = 0.1
"""Distance from the rail down to which the driver keeps its gain (OPA365, page 6)."""

_UNDER_RANGE = 650
"""Code below which firmware reports an under-range (section 4.4)."""

_TRIP_MOST = 118.7e-3
"""Highest shunt voltage of the over-current threshold (section 4.4)."""

_SPARE = 3.6e-3
"""Room between that threshold and the converter full scale (section 4.4)."""


def _sweep_deck(ctx: Context) -> str:
    start, stop, step = _SWEEP
    return ctx.deck(
        "Signal chain: shunt voltage swept in range 0, node after the shunts at 3.3 V",
        common.chain(ctx),
        frontend.rails(),
        common.taps({}),
        common.address(0),
        control=[f"dc Vsh0 {start:g} {stop:g} {step:g}"],
        libraries=common.LIBRARIES,
    )


def _board_deck(ctx: Context, scales: dict[str, float], models: dict[str, PartModel]) -> str:
    """One board of the Monte Carlo run, solved at a few shunt voltages."""
    points = " ".join(f"{value:g}" for value in _POINTS)
    return ctx.deck(
        "Signal chain: one board with its tolerances",
        common.chain(ctx, overrides=models, scales=scales),
        frontend.rails(),
        common.taps({}),
        common.address(0),
        control=[f"foreach level {points}", "  alter Vsh0 dc = $level", "  op", "end"],
        libraries=common.LIBRARIES,
    )


def _board(result: RunResult) -> tuple[float, float]:
    """Gain and converter input at zero current of one board."""
    adc = [float(result.real("adc_in", plot=f"op{step + 1}")[0]) for step in range(len(_POINTS))]
    gain = (adc[2] - adc[1]) / (_POINTS[2] - _POINTS[1])
    return gain, adc[0]


@bench(
    "signal_chain",
    "transfer",
    "From the shunt voltage to the converter input and to the code, with tolerances",
    "sections 4.3, 4.5 and 8 (gain, pedestal, zero code, full scale, resolution), section 4.4 "
    "(room above the trip level)",
)
def transfer(ctx: Context) -> Outcome:
    """The shunt voltage is swept and the converter input is read.

    Range 0 is held, the node after the shunts stands at 3.3 V and the
    voltage across the shunt is swept from -5 mV to 160 mV as an operating
    point sweep. The slope of the converter input is the gain of the chain,
    its value at 0 V the pedestal; an ideal converter turns it into codes.
    Then 120 boards are drawn: every resistor of the chain inside its
    tolerance, the gain error and the offsets of the amplifiers inside the
    limits of their datasheets, all with a uniform distribution.
    """
    result = ctx.run("sweep", _sweep_deck(ctx))
    shunt = result.real("v-sweep")
    adc = result.real("adc_in")
    raw = result.real("amp_raw")
    rail = result.real("vdrv")
    inside = (shunt >= _LINEAR[0]) & (shunt <= _LINEAR[1])
    gain, offset = (float(value) for value in np.polyfit(shunt[inside], adc[inside], 1))
    pedestal = float(np.interp(0.0, shunt, adc))
    codes = common.code(adc)
    zero_code = float(np.interp(0.0, shunt, codes))
    top = common.VREF - 0.5 * common.LSB
    full_scale = float(np.interp(top, adc[shunt < 0.13], shunt[shunt < 0.13]))
    deviation = (adc - (gain * shunt + offset)) / common.LSB
    worst_line = float(np.max(np.abs(deviation[(shunt >= 0.0) & (shunt <= full_scale)])))
    rail_at_full = float(np.interp(full_scale, shunt, rail))
    keeps_gain = float(
        np.interp(rail_at_full - _HEADROOM, adc[shunt < 0.135], shunt[shunt < 0.135])
    )
    clipped = float(np.interp(0.15, shunt, adc))
    figures = [
        near(
            "gain",
            "Gain from the shunt to the converter input",
            gain,
            "",
            common.GAIN,
            0.001,
            "section 4.5: 19.93 from R123, a 0.1 % part",
        ),
        near(
            "pedestal",
            "Converter input at zero shunt voltage (the pedestal)",
            pedestal,
            "V",
            common.PEDESTAL,
            0.005,
            "section 4.5: +50 mV from R121 and R122",
        ),
        Figure(
            "zero_code",
            "Code at zero shunt voltage",
            zero_code,
            "codes",
            expected=1313.0,
            low=1310.0,
            high=1316.0,
            source="section 4.5: about 1313 codes",
        ),
        near(
            "full_scale",
            "Shunt voltage at which the converter reads full scale",
            full_scale,
            "V",
            0.1229,
            0.002,
            "section 4.3: 122.9 mV",
        ),
        Figure(
            "straight",
            "Largest distance from a straight line, zero to full scale",
            worst_line,
            "codes",
            high=1.0,
            source="section 4.5: the driver is linear beyond the full scale of the converter",
        ),
        Figure(
            "rail_above_full_scale",
            "Driver rail above the converter input at full scale",
            rail_at_full - common.VREF,
            "V",
            low=_HEADROOM,
            source="OPA365 datasheet, page 6: gain specified down to 100 mV from the rail",
        ),
        Figure(
            "keeps_gain_to",
            "Shunt voltage at which the driver output is 100 mV below its rail",
            keeps_gain,
            "V",
            expected=0.1268,
            low=0.1229,
            source="section 4.5: linear up to 126.8 mV, above the full scale of the converter",
        ),
        Figure(
            "clipped",
            "Converter input with 150 mV at the shunt (driver against its rail)",
            clipped,
            "V",
            high=common.VREF + 0.25,
            source="section 4.5: never above VREF + 0.25 V",
        ),
    ]
    resolution = (1.914e-9, 59.9e-9, 1.916e-6, 19.14e-6)
    for index, (ohms, expected) in enumerate(zip(frontend.SHUNT_OHMS, resolution, strict=True)):
        figures.append(
            near(
                f"lsb_r{index}",
                f"R{index}: current of one code, with the shunt of the specification",
                common.LSB / (gain * ohms),
                "A",
                expected,
                0.002,
                "sections 4.3 and 8",
            )
        )

    spread = tolerance.tolerances(ctx.netlist, frontend.chain_refs(ctx.netlist))
    rng = np.random.default_rng(_SEED)
    decks: dict[str, str] = {}
    converter_offsets: list[float] = []
    for draw in range(_DRAWS):
        scales = tolerance.draw_scales(spread, rng)
        models = {
            "U27": common.with_params(
                ctx,
                "U27",
                gerr=float(rng.uniform(-_GAIN_ERROR, _GAIN_ERROR)),
                vosi=float(rng.uniform(-_INPUT_OFFSET, _INPUT_OFFSET)),
                voso=float(rng.uniform(-_OUTPUT_OFFSET, _OUTPUT_OFFSET)),
            ),
            "U26": common.with_params(
                ctx, "U26", vos=float(rng.uniform(-_BUFFER_OFFSET, _BUFFER_OFFSET))
            ),
            "U29": common.with_params(
                ctx, "U29", vos=float(rng.uniform(-_DRIVER_OFFSET, _DRIVER_OFFSET))
            ),
        }
        converter_offsets.append(float(rng.uniform(-_CONVERTER_OFFSET, _CONVERTER_OFFSET)))
        decks[f"board{draw:03d}"] = _board_deck(ctx, scales, models)
    boards = [_board(run) for _, run in sorted(ctx.run_many(decks).items())]
    gains = np.array([board[0] for board in boards])
    zeros = np.array([board[1] for board in boards])
    shifts = np.array(converter_offsets)
    zero_codes = common.code(zeros)
    zero_codes_all = common.code(zeros + shifts)
    full_scales = (common.VREF - zeros - shifts) / gains
    figures += [
        Figure(
            "gain_low",
            f"Lowest gain of {_DRAWS} boards",
            float(gains.min()),
            "",
            low=common.GAIN * (1.0 - 0.001 - _GAIN_ERROR),
            source="0.1 % of R123 (section 4.5) and 0.2 % of the amplifier (AD8421, page 4)",
        ),
        Figure(
            "gain_high",
            f"Highest gain of {_DRAWS} boards",
            float(gains.max()),
            "",
            high=common.GAIN * (1.0 + 0.001 + _GAIN_ERROR),
            source="0.1 % of R123 (section 4.5) and 0.2 % of the amplifier (AD8421, page 4)",
        ),
        Figure(
            "zero_code_low",
            "Lowest code at zero shunt voltage, offsets of the chain alone",
            float(zero_codes.min()),
            "codes",
        ),
        Figure(
            "zero_code_high",
            "Highest code at zero shunt voltage, offsets of the chain alone",
            float(zero_codes.max()),
            "codes",
        ),
        Figure(
            "zero_code_lowest",
            "Lowest code at zero shunt voltage with the offset error of the converter",
            float(zero_codes_all.min()),
            "codes",
            low=float(_UNDER_RANGE),
            source="section 4.4: a code below 650 counts as under-range",
        ),
        Figure(
            "zero_code_highest",
            "Highest code at zero shunt voltage with the offset error of the converter",
            float(zero_codes_all.max()),
            "codes",
        ),
        Figure(
            "full_scale_low",
            "Lowest shunt voltage of the converter full scale",
            float(full_scales.min()),
            "V",
            low=_TRIP_MOST + _SPARE,
            source="section 4.4: 3.6 mV to spare above the highest trip level of 118.7 mV",
        ),
        Figure(
            "lsb_r0_spread",
            "R0: spread of the current of one code over the boards, highest to lowest",
            float(gains.max() / gains.min() - 1.0) * 100.0,
            "%",
        ),
    ]
    shown = shunt <= 0.16
    graph = Graph(
        name="transfer",
        title="Signal chain: from the shunt voltage to the converter input",
        xlabel="Voltage across the shunt (mV)",
        panels=(
            Panel(
                "Voltage (V)",
                marks=((common.VREF, "converter full scale 2.5 V"),),
            ),
            Panel("Off the line (codes)"),
        ),
        traces=(
            Trace(shunt[shown] * 1e3, raw[shown], "amplifier output", 0),
            Trace(shunt[shown] * 1e3, adc[shown], "converter input", 0),
            Trace(shunt[shown] * 1e3, rail[shown], "driver rail", 0, "--"),
            Trace(
                shunt[(shunt >= 0) & (shunt <= 0.125)] * 1e3,
                deviation[(shunt >= 0) & (shunt <= 0.125)],
                "converter input",
                1,
            ),
        ),
        xmarks=((full_scale * 1e3, "converter full scale"),),
    )
    order = np.argsort(gains)
    boards_graph = Graph(
        name="boards",
        title=f"{_DRAWS} boards: gain and code at zero current",
        xlabel="Board, in the order of its gain",
        panels=(Panel("Gain"), Panel("Code at zero shunt voltage")),
        traces=(
            Trace(np.arange(_DRAWS, dtype=np.float64), gains[order], "", 0),
            Trace(np.arange(_DRAWS, dtype=np.float64), zero_codes[order], "chain alone", 1),
            Trace(
                np.arange(_DRAWS, dtype=np.float64),
                zero_codes_all[order],
                "with the converter",
                1,
                ":",
            ),
        ),
    )
    notes = (
        "The ladder is not in this circuit: ideal sources stand on the inputs of the "
        "multiplexer. The current of one code uses the shunt values of the specification.",
        "The converter is ideal: one code per VREF / 65536. Its offset error (4 mV at most) "
        "is added by arithmetic in the figures that say so; its gain error (0.01 %) is left "
        "out.",
        "The amplifier models are typical parts without offset in the sweep. Their offsets "
        "and the gain error of U27 are drawn only in the Monte Carlo run, inside the limits "
        "of the datasheets, with a uniform distribution; the reference is ideal.",
        "The driver model keeps its gain up to its rail. The figure for the driver output "
        "100 mV below the rail marks where the datasheet stops to state the gain.",
        "The models are straight inside their limits, so the distance from the straight "
        "line in the second panel is the residue of the solver, a few ten-thousandths of "
        "a code. The non-linearity of the real parts is not in it: the amplifier has "
        "5 ppm typical and 10 ppm at the most over an output of -5 V to +5 V (AD8421, "
        "page 4), the converter 1 code typical and 2 codes at the most (ADS8860, page 1).",
    )
    return Outcome(tuple(figures), (graph, boards_graph), notes)
