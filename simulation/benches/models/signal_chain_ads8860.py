"""The model of the analog input of the ADS8860 against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_DOCUMENT = "TI SBAS569B"
"""The datasheet the figures are taken from."""

_REFERENCE = 5.0
"""Reference voltage at which the datasheet states the reference current."""

_LEVEL = 1.0
"""Voltage of the source at the input."""

_SOURCE_OHMS = 1e3
"""Resistance of the source in the settling run."""

_CONVERT = 2e-6
"""Instant of the rising edge of the convert-start line."""

_CONVERSION = 710e-9
"""Longest conversion (page 6), the value of the model."""


def _transient_deck(ctx: Context) -> str:
    lines = [
        f"Vref ref 0 {_REFERENCE:g}",
        f"Vs src 0 {_LEVEL:g}",
        f"Rs src ainp {_SOURCE_OHMS:g}",
        "X1 ref ainp 0 0 cnv SIGNAL_CHAIN_ADS8860",
        f"Vcnv cnv 0 PULSE(0 3.3 {_CONVERT:g} 5n 5n 1u 1)",
    ]
    return ctx.deck(
        "ADS8860 input: one conversion with 1 V behind 1 kohm",
        "\n".join(lines),
        control=["tran 0.5n 5u 0 1n"],
        libraries=("signal_chain.lib",),
    )


def _static_deck(ctx: Context) -> str:
    """The input while the converter acquires: its capacitance, the leakage of REF, the diode."""
    lines = [
        f"Vref ref 0 {_REFERENCE:g}",
        f"Vs ainp 0 dc {_LEVEL:g} ac 1",
        "X1 ref ainp 0 0 cnv SIGNAL_CHAIN_ADS8860",
        "Vcnv cnv 0 0",
        "* a second converter with its input 0.3 V above its reference",
        f"Vref2 ref2 0 {_REFERENCE:g}",
        f"Vover over 0 {_REFERENCE + 0.3:g}",
        "X2 ref2 over 0 0 cnv SIGNAL_CHAIN_ADS8860",
    ]
    return ctx.deck(
        "ADS8860 input: acquiring",
        "\n".join(lines),
        control=["op", "ac lin 1 10k 10k"],
        libraries=("signal_chain.lib",),
    )


@bench(
    "models",
    "signal-chain-ads8860",
    "ADS8860 analog input and reference pin: model against the datasheet",
    "the model of the analog side of the converter U30",
)
def ads8860(ctx: Context) -> Outcome:
    """The input model samples 1 V from a source of 1 kohm, with a reference of 5 V.

    One conversion is run. The time for which the sampling switch is open
    is the conversion time; the current of the reference pin in that time
    is the reference current of the datasheet; after it the sampling
    capacitor, which the model empties, charges again through the source
    and the switch. A small-signal run with the converter acquiring gives
    the input capacitance, an operating point the leakage of the reference
    pin and the current of a protection diode with the input 0.3 V above
    the reference.
    """
    run = ctx.run("conversion", _transient_deck(ctx))
    static = ctx.run("acquiring", _static_deck(ctx))
    time = run.real("time")
    held = run.real("x1.shp")
    converting = run.real("x1.q")
    opens = measure.first_crossing(time, converting, 0.5, rising=True, after=_CONVERT - 1e-7)
    closes = measure.first_crossing(time, converting, 0.5, rising=False, after=opens)
    sampled = measure.value_at(time, held, _CONVERT - 5e-9)
    residue = measure.value_at(time, held, closes - 5e-9)
    target = residue + (1.0 - np.exp(-1.0)) * (_LEVEL - residue)
    recharged = measure.first_crossing(time, held, float(target), rising=True, after=closes)
    reference = -run.real("vref#branch")
    during = measure.mean(time, reference, opens + 2e-8, closes - 2e-8)
    capacitance = abs(complex(static.vector("vs#branch", plot="ac")[0])) / (2.0 * np.pi * 10e3)
    leakage = -float(static.real("vref#branch", plot="op")[0])
    diode = -float(static.real("vover#branch", plot="op")[0])
    figures = (
        near(
            "capacitance",
            "Input capacitance while the converter acquires",
            capacitance,
            "F",
            59e-12,
            0.03,
            f"{_DOCUMENT}, page 6; figure 45 on page 20: 4 pF and 55 pF",
        ),
        near(
            "sampled",
            "Voltage on the sampling capacitor when the switch opens",
            sampled,
            "V",
            _LEVEL,
            0.001,
            "the input voltage",
        ),
        near(
            "conversion",
            "Time for which the sampling switch is open",
            closes - opens,
            "s",
            _CONVERSION,
            0.02,
            f"{_DOCUMENT}, page 6: 710 ns at the most",
        ),
        Figure(
            "residue",
            "Part of its voltage that the sampling capacitor keeps over a conversion",
            residue / sampled,
            "",
            expected=55.0 / 5555.0,
            high=0.02,
            source="the model: charge shared with 5.5 nF, the bounding case of an empty capacitor",
        ),
        near(
            "recharge",
            "Sampling capacitor back to 63 % of the step through 1 kohm and the switch",
            recharged - closes,
            "s",
            _SOURCE_OHMS * 59e-12 + 96.0 * 55e-12,
            0.1,
            f"{_DOCUMENT}, figure 45: 96 ohm, 55 pF and 4 pF, calculated here",
        ),
        near(
            "reference_current",
            "Current of the reference pin during the conversion, reference at 5 V",
            during,
            "A",
            300e-6,
            0.03,
            f"{_DOCUMENT}, page 6",
        ),
        near(
            "reference_leakage",
            "Current of the reference pin while the converter acquires",
            leakage,
            "A",
            250e-9,
            0.03,
            f"{_DOCUMENT}, page 6",
        ),
        Figure(
            "diode",
            "Current of the protection diode with the input 0.3 V above the reference",
            diode,
            "A",
        ),
    )
    micro = time * 1e6
    graph = Graph(
        name="conversion",
        title="ADS8860 input model: one conversion, 1 V behind 1 kohm",
        xlabel="Time (us)",
        panels=(
            Panel("Convert-start line (V)"),
            Panel("Voltage (V)"),
            Panel("Current of the reference pin (uA)"),
        ),
        traces=(
            Trace(micro, run.real("cnv"), "", 0),
            Trace(micro, run.real("ainp"), "input pin", 1),
            Trace(micro, held, "sampling capacitor", 1, "--"),
            Trace(micro, reference * 1e6, "", 2),
        ),
    )
    notes = (
        "The model is the equivalent circuit of the datasheet with the timing of the "
        "three-wire mode. It does not convert: no code comes out of it.",
        "What the sampling capacitor keeps over a conversion is not in the datasheet. The "
        "model empties it, the bounding case for the kick at the input.",
        "The reference current is a constant current during the conversion, in proportion "
        "to the reference voltage (assumption); the datasheet states it at 5 V and "
        "mid-code. The real current comes as one packet per bit.",
        "The protection diodes are an assumed junction: the datasheet gives the rating of "
        "0.3 V beyond the reference and no curve. The figure of the diode current is not a "
        "figure to rely on.",
    )
    return Outcome(figures, (graph,), notes)
