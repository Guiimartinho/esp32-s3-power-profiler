"""Offset and gain of the chain against the output voltage of the instrument."""

from __future__ import annotations

import numpy as np

from benches import frontend
from benches.signal_chain import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_REJECTION = 86.0
"""Common-mode rejection of the A grade at a gain of 1, at the least, dB (AD8421, page 3)."""

_VOLTAGES = (0.8, 3.3, 5.0)
"""Output voltages at which the figures are read."""

_SWEEP = (0.0, 5.5, 0.05)
"""Output voltage of the sweep: start, stop, step."""

_FULL = 0.1
"""Shunt voltage at which the gain is read."""

_RANGE_LIMIT = 0.001 * common.VREF / common.LSB
"""0.1 % of the converter range in codes, the range term of requirement R-05."""


def _amplifier(ctx: Context, sign: int) -> dict[str, PartModel]:
    """The amplifier with its rejection at the limit of the datasheet, of either sign."""
    if sign == 0:
        return {}
    return {"U27": common.with_params(ctx, "U27", cmrr=_REJECTION, cmsign=sign)}


def _dc_deck(ctx: Context, sign: int, shunt: float) -> str:
    start, stop, step = _SWEEP
    return ctx.deck(
        "Signal chain: output voltage swept, shunt voltage held",
        common.chain(ctx, overrides=_amplifier(ctx, sign)),
        frontend.rails(),
        common.taps({0: f"{shunt:g}"}, "0"),
        common.address(0),
        control=[f"dc Vvout {start:g} {stop:g} {step:g}"],
        libraries=common.LIBRARIES,
    )


def _ac_deck(ctx: Context, sign: int) -> str:
    return ctx.deck(
        "Signal chain: both sense taps moved together at 3.3 V",
        common.chain(ctx, overrides=_amplifier(ctx, sign)),
        frontend.rails(),
        common.taps({0: "dc 0.05 ac 0"}, "dc 3.3 ac 1"),
        common.address(0),
        control=["ac dec 40 1 1meg"],
        libraries=common.LIBRARIES,
    )


def _shift(run: RunResult) -> tuple[common.Vector, common.Vector]:
    """Output voltage and the converter input relative to its value at 0 V."""
    volts = run.real("v-sweep")
    adc = run.real("adc_in")
    return volts, adc - adc[0]


@bench(
    "signal_chain",
    "common-mode",
    "Offset and gain of the chain against the output voltage",
    "section 4.5 (supplies and common mode of U27), section 8 (zero calibration), "
    "section 4.10 (zero of R0), requirement R-05",
)
def common_mode(ctx: Context) -> Outcome:
    """The node after the shunts is swept from 0 V to 5.5 V with the shunt voltage held.

    That node is the output voltage of the instrument and the common mode
    of the amplifier. With 0 V across the shunt the converter input shows
    how the zero moves with the output voltage; with 100 mV it shows the
    gain. The run is made with the typical amplifier model, which has no
    common-mode error, and with the rejection of the amplifier at the limit
    of its datasheet (86 dB at a gain of 1, which is 112 dB at this gain),
    once with each sign. The shift from 0 V is what a zero taken with the
    ladder at 0 V does not remove; a zero taken with the ladder at its
    working voltage (section 4.2, D-29) leaves the slope times the change
    of the output voltage since that zero. A small-signal run gives the
    same rejection over frequency.
    """
    decks: dict[str, str] = {}
    for sign, tag in ((0, "typical"), (1, "plus"), (-1, "minus")):
        decks[f"zero-{tag}"] = _dc_deck(ctx, sign, 0.0)
        decks[f"gain-{tag}"] = _dc_deck(ctx, sign, _FULL)
        decks[f"ac-{tag}"] = _ac_deck(ctx, sign)
    ctx.run("zero-plus", decks["zero-plus"])
    runs = ctx.run_many(decks)
    figures: list[Figure] = []
    traces: list[Trace] = []
    volts, typical = _shift(runs["zero-typical"])
    _, plus = _shift(runs["zero-plus"])
    _, minus = _shift(runs["zero-minus"])
    figures.append(
        Figure(
            "typical_5v",
            "Typical model: the zero at 5 V against the zero at 0 V, at the shunt",
            float(np.interp(5.0, volts, typical)) / common.GAIN,
            "V",
        )
    )
    for level in _VOLTAGES:
        moved = float(np.interp(level, volts, plus))
        tag = f"{level:g}v".replace(".", "p")
        figures += [
            Figure(
                f"shift_{tag}",
                f"Rejection at its limit: the zero at {level:g} V against the zero at 0 V",
                abs(moved) / common.LSB,
                "codes",
                high=_RANGE_LIMIT,
                source="requirement R-05: 0.1 % of range, 65.5 codes",
            ),
            Figure(
                f"shift_r0_{tag}",
                f"The same as a current in range 0, at {level:g} V",
                abs(moved) / common.GAIN / frontend.SHUNT_OHMS[0],
                "A",
            ),
        ]
    slope = float(np.polyfit(volts, plus, 1)[0]) / common.GAIN
    figures += [
        Figure(
            "slope",
            "Rejection at its limit: the zero moves with the output voltage by, at the shunt",
            abs(slope),
            "V",
            expected=2.5e-6,
            source="AD8421 datasheet, page 3: 86 dB at G = 1, divided by the gain, per volt",
        ),
        Figure(
            "slope_r0",
            "The same as a current in range 0, for each volt of output voltage",
            abs(slope) / frontend.SHUNT_OHMS[0],
            "A",
        ),
        Figure(
            "symmetric",
            "The other sign gives the opposite shift at 5 V: sum of the two",
            float(np.interp(5.0, volts, plus) + np.interp(5.0, volts, minus)) / common.LSB,
            "codes",
            low=-0.5,
            high=0.5,
            source="check of this bench",
        ),
    ]
    for index in range(1, 4):
        figures.append(
            Figure(
                f"shift_r{index}_5v",
                f"The shift at 5 V as a current in range {index}",
                abs(float(np.interp(5.0, volts, plus))) / common.GAIN / frontend.SHUNT_OHMS[index],
                "A",
            )
        )
    gain_volts = runs["gain-plus"].real("v-sweep")
    with_signal = runs["gain-plus"].real("adc_in")
    without = runs["zero-plus"].real("adc_in")
    gains = (with_signal - without) / _FULL
    figures += [
        Figure(
            "gain_0v8",
            "Gain at 0.8 V of output voltage",
            float(np.interp(0.8, gain_volts, gains)),
            "",
            expected=common.GAIN,
            low=common.GAIN * 0.9999,
            high=common.GAIN * 1.0001,
            source="section 4.5: the common mode of 0.8 V to 5 V stays inside the input range",
        ),
        Figure(
            "gain_5v",
            "Gain at 5 V of output voltage",
            float(np.interp(5.0, gain_volts, gains)),
            "",
            expected=common.GAIN,
            low=common.GAIN * 0.9999,
            high=common.GAIN * 1.0001,
            source="section 4.5: the common mode of 0.8 V to 5 V stays inside the input range",
        ),
        Figure(
            "gain_change",
            "Change of the gain from 0.8 V to 5 V of output voltage",
            float(np.interp(5.0, gain_volts, gains) / np.interp(0.8, gain_volts, gains) - 1.0)
            * 1e6,
            "ppm",
        ),
    ]
    frequency = runs["ac-plus"].real("frequency")
    response = np.asarray(runs["ac-plus"].vector("adc_in"), dtype=np.complex128) / common.GAIN
    typical_response = np.asarray(runs["ac-typical"].vector("adc_in"), dtype=np.complex128)
    rejection = -measure.decibels(response)
    log_f = np.log10(frequency)
    for hertz, text in ((50.0, "50 Hz"), (1e3, "1 kHz"), (20e3, "20 kHz")):
        figures.append(
            Figure(
                f"rejection_{int(hertz)}",
                f"Rejection at its limit: common-mode rejection of the chain at {text}",
                float(np.interp(np.log10(hertz), log_f, rejection)),
                "dB",
            )
        )
    figures.append(
        Figure(
            "typical_rejection_1k",
            "Typical model with nominal parts: what reaches the converter at 1 kHz, of 1 V",
            float(np.interp(3.0, log_f, np.abs(typical_response))),
            "V",
        )
    )
    traces += [
        Trace(volts, plus / common.LSB, "rejection at its limit, one sign", 0),
        Trace(volts, minus / common.LSB, "rejection at its limit, other sign", 0),
        Trace(volts, typical / common.LSB, "typical model", 0, "--"),
        Trace(gain_volts, (gains / gains[0] - 1.0) * 1e6, "gain", 1),
        Trace(frequency, rejection, "", 2),
    ]
    drift = Graph(
        name="zero",
        title="Zero and gain of the chain against the output voltage",
        xlabel="Voltage of the node after the shunts (V)",
        panels=(
            Panel("Zero against its value at 0 V (codes)"),
            Panel("Gain against its value at 0 V (ppm)"),
        ),
        traces=tuple(trace for trace in traces if trace.panel < 2),
        xmarks=((0.8, "0.8 V"), (5.0, "5 V")),
    )
    over_frequency = Graph(
        name="rejection",
        title="Common-mode rejection of the chain, amplifier at the limit of its datasheet",
        xlabel="Frequency (Hz)",
        panels=(Panel("Rejection, referred to the shunt (dB)"),),
        traces=(Trace(frequency, rejection, "", 0),),
        logx=True,
    )
    notes = (
        "The datasheet of the amplifier states the rejection as a least value and gives "
        "no typical one; the limit of the A grade is used with either sign. A part can "
        "sit anywhere between the two lines of the graph.",
        "The model makes the error in the output stage of the amplifier, as a straight "
        "line over the common mode. A real part can bend; the figures say how large the "
        "term is, not its shape.",
        "The amplifier model has no term that changes its gain with the common mode, and "
        "its datasheet states none. The gain figures show that the chain stays inside "
        "its linear range from 0.8 V to 5 V, nothing more.",
        "The ladder is not in this circuit, so the bias current of the amplifier inputs "
        "flows in ideal sources. On the board the current of the inverting input flows "
        "through the shunt in use: 2 nA at the most in every range, which the zero "
        "calibration removes, and its change with the common mode (30 Gohm) is 0.14 nA "
        "from 0.8 V to 5 V.",
        "Leakage of the multiplexer against the common mode adds to this on the board; "
        "no model here gives a believable figure for it.",
        "The closed-switch zero of section 8 is taken at 5.0 V and at the working "
        "voltage and so contains this term at those voltages. For the open-switch zero "
        "section 8 does not say where the ladder stands. Section 4.2 (D-29) lets it run "
        "with the mode pair closed, the ladder at its working voltage: the term is then "
        "in the zero for that voltage, and a later change of the set-point or of the "
        "supply of the user brings it back with the slope above. A zero taken in the "
        "reset state, or after the output was switched off (the ladder rests at 0 V and "
        "falls there with 0.57 s), does not contain it.",
    )
    return Outcome(tuple(figures), (drift, over_frequency), notes)
