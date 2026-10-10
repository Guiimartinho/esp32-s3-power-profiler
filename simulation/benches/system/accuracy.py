"""From the load current to the code: every range at rest, as the host reads it."""

from __future__ import annotations

import numpy as np

from benches import frontend
from benches.system import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.report import format_quantity

_LEVELS = np.concatenate(([0.0], np.logspace(-3, np.log10(1.2), 28)))
"""Load currents of the staircase, as fractions of the full scale of a range."""

_HOLD = (1.5e-3, 150e-6, 150e-6, 150e-6)
"""Time each level is held, by range.

The chain settles in about 70 us (section 4.5). In range 0 the 1 kohm shunt
works against the 100 nF on the node after the shunts, a time constant of
100 us, so its levels are held ten times longer.
"""

_EDGE = 5e-6
"""Time the load takes from one level to the next."""

_READ = 20e-6
"""Window at the end of a level over which the converter input is read."""

_FULL_SCALE_SHUNT_VOLTS = 0.1229
"""Shunt voltage at which the converter reads full scale (section 4.3)."""


def _deck(ctx: Context, index: int) -> str:
    full = frontend.FULL_SCALE_AMPS[index]
    hold = _HOLD[index]
    points = ["0 0"]
    for step, level in enumerate(_LEVELS[1:], start=1):
        start = step * hold
        points.append(f"{start:g} {_LEVELS[step - 1] * full:.6g}")
        points.append(f"{start + _EDGE:g} {level * full:.6g}")
    stimulus = "\n".join(
        [
            "* the source meter as an ideal 5 V source on the supply node; the",
            "* load as a current sink on the node after the shunts, stepped",
            "* through its levels as a staircase and read at the end of each",
            "Vsupply supply 0 5",
            f"Iload vout_s 0 PWL({' '.join(points)})",
        ]
    )
    stop = _LEVELS.size * hold
    control = ["save adc_in amp_raw inp inn supply vout_s", f"tran 1u {stop:g}"]
    return ctx.deck(
        f"Whole measuring path, range {index} held, load stepped through the range",
        common.front_end(ctx, comparators=False),
        frontend.rails(),
        frontend.fixed_range(index),
        stimulus,
        control=control,
    )


@bench(
    "system",
    "accuracy",
    "From the load current to the code, every range held",
    "sections 4.3, 4.5 and 8 (gain, pedestal, resolution, full scale), requirement R-12",
)
def accuracy(ctx: Context) -> Outcome:
    """Ladder, multiplexer and amplifier chain run as one circuit, from the netlist.

    Each range is held and the load current is stepped from zero to 120 % of
    the full scale as a staircase. At the end of each step the voltage at the
    converter input becomes a 16-bit code. The host reading is that code with
    the nominal calibration of the specification. The figures say what one
    code is worth in each range, where zero and full scale lie, and how far
    the path is from a straight line, which is what remains on a board after
    its calibration at two points.
    """
    figures: list[Figure] = []
    traces: list[Trace] = []
    for index in range(4):
        result = ctx.run(f"r{index}", _deck(ctx, index))
        time, adc = result.real("time"), result.real("adc_in")
        full = frontend.FULL_SCALE_AMPS[index]
        currents = _LEVELS * full
        ends = (np.arange(_LEVELS.size) + 1) * _HOLD[index]
        volts = np.array([measure.mean(time, adc, end - _READ, end) for end in ends])
        code = common.codes(volts)
        linear = (currents > 0.0) & (currents <= 1.0001 * full)
        slope, intercept = np.polyfit(currents[linear], volts[linear], 1)
        lsb = common.VREF / common.CODES / slope
        nominal = common.reading(code, np.full(code.size, index))
        if index == 0:
            figures.append(
                Figure(
                    "zero_code",
                    "Code at zero current (the pedestal)",
                    float(code[0]),
                    "codes",
                    expected=float(common.ZERO_CODE),
                    low=common.ZERO_CODE - 5.0,
                    high=common.ZERO_CODE + 5.0,
                    source="section 4.5: about 1313 codes, calculated",
                )
            )
            figures.append(
                near(
                    "pedestal",
                    "Converter input at zero current",
                    float(volts[0]),
                    "V",
                    0.05008,
                    0.005,
                    "section 4.5: pedestal of 50 mV",
                )
            )
        figures.append(
            near(
                f"lsb_r{index}",
                f"R{index}: current of one code",
                float(lsb),
                "A",
                common.LSB_AMPS[index],
                0.002,
                "sections 4.3 and 8, calculated",
            )
        )
        full_code_volts = (common.VREF - intercept) / slope * frontend.SHUNT_OHMS[index]
        figures.append(
            near(
                f"full_scale_r{index}",
                f"R{index}: shunt voltage at which the converter reads full scale",
                float(full_code_volts),
                "V",
                _FULL_SCALE_SHUNT_VOLTS,
                0.005,
                "section 4.3: 122.9 mV, calculated",
            )
        )
        at_full = int(np.argmin(np.abs(currents - full)))
        figures.append(
            Figure(
                f"nominal_error_r{index}",
                f"R{index}: reading with the nominal calibration at {format_quantity(full, 'A')}",
                float(100.0 * (nominal[at_full] - currents[at_full]) / currents[at_full]),
                "%",
                low=-0.5,
                high=0.5,
                source="limit of this bench: nominal values agree within 0.5 %",
            )
        )
        fitted = (volts - intercept) / slope
        residual = np.abs(fitted - currents)[linear] / lsb
        figures.append(
            Figure(
                f"residual_r{index}",
                f"R{index}: largest deviation from a straight line, zero to full scale",
                float(np.max(residual)),
                "codes",
                high=1.0,
                source="limit of this bench: one code",
            )
        )
        shown = currents > 0.0
        error = 100.0 * (nominal[shown] - currents[shown]) / currents[shown]
        traces.append(Trace(currents[shown], code[shown].astype(float), f"R{index}", 0))
        traces.append(Trace(currents[shown], error, f"R{index}", 1))
    graph = Graph(
        name="transfer",
        title="Load current to code and to the reading, every range held",
        xlabel="Load current (A)",
        panels=(
            Panel("Code", marks=((65535.0, "full scale"), (1313.0, "zero"))),
            Panel("Reading with nominal calibration, error (%)"),
        ),
        traces=tuple(traces),
        logx=True,
    )
    notes = (
        "The converter is ideal arithmetic on the voltage at its input: no "
        "noise, no nonlinearity of its own, no sampling kick.",
        "Offset, bias current and noise of the amplifiers are zero in these "
        "runs, so the error at small currents is the size of one code and the "
        "rounding to it; a real board adds its offsets, which the zero "
        "calibration removes (section 8).",
        "The levels are a staircase in time, because a fresh operating point of "
        "this circuit does not always converge in the simulator; each level is "
        "held for 150 us (1.5 ms in range 0) and read over its last 20 us.",
        "Range 0 is slow by itself: its 1 kohm shunt and the 100 nF capacitor "
        "C71 on the node after the shunts make a time constant of 100 us, "
        "before any capacitance of the load is counted.",
        "The comparators are left out of this circuit; their divider loads the "
        "amplifier output as drawn.",
    )
    return Outcome(tuple(figures), (graph,), notes)
