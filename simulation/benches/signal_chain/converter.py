"""The converter input: the kick of its sampling capacitor, and its reference line."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches import frontend
from benches.signal_chain import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult
from circuit_sim.errors import MeasureError

_DRIVER_PARTS = (
    "U28",
    "R124",
    "R126",
    "R127",
    "R129",
    "C86",
    "C88",
    "U29",
    "D22",
    "R125",
    "R128",
    "C85",
    "C87",
    "R130",
    "C90",
    "U30",
)
"""The driver with its filter and its rail, the network at the converter, the converter."""

_REFERENCE_PARTS = ("U12", "R31", "C20", "C24", "R35", "C26", "C113", "R131", "C89", "U30")
"""The reference with its capacitors, the line to the converter, the converter."""

_FIRST = 5e-6
"""Instant of the first rising edge of the convert-start line."""

_HIGH = 1e-6
"""Time for which the convert-start line stays high: longer than the conversion."""

_CONVERSION = 710e-9
"""Longest conversion (ADS8860 datasheet, page 6), the value of the model."""

_HALF_CODE = 0.5 * common.LSB
"""Half a code: what "settled to 16 bits" means here."""

_RATES = ((100e3, "100 kSPS", 7), (500e3, "500 kSPS", 16))
"""Sample rates: hertz, label and the number of conversions of a run."""

_LEVELS = ((0.05, "pedestal"), (1.25, "half scale"), (2.45, "near full scale"))
"""Voltages at the converter input: volts and label."""

_KEEPS = 5.5e-12
"""Charge-sharing capacitor of a converter that keeps nine tenths of its charge."""

_REFERENCE_AMPS = 150e-6
"""Reference current of the converter model during a conversion at 2.5 V."""


@dataclass(frozen=True, slots=True)
class _Kick:
    """What one run of the sampling kick gives."""

    error_codes: float
    dip: float
    back_after: float


def _convert(rate: float, count: int) -> str:
    """The convert-start line at the pin of the converter."""
    return (
        "* convert-start line at the pin of the converter\n"
        f"Vcnv cnv 0 PULSE(0 3.3 {_FIRST:g} 5n 5n {_HIGH:g} {1.0 / rate:g} {count})\n"
    )


def _kick_deck(ctx: Context, rate: float, count: int, level: float, cres: float | None) -> str:
    models: dict[str, PartModel] = {}
    if cres is not None:
        models["U30"] = common.with_params(ctx, "U30", cres=cres)
    stop = _FIRST + count / rate
    return ctx.deck(
        f"Converter input: sampling at {rate / 1e3:g} kSPS with {level:g} V at the input",
        ctx.circuit(_DRIVER_PARTS, common.ALIASES, models),
        frontend.rails(),
        f"* the amplifier output as a source\nVamp amp_raw 0 {level:g}\n",
        _convert(rate, count),
        control=[
            "save adc_in adc_drv cnv vdrv xu30.shp xu30.q",
            f"tran 1n {stop:g} 0 4n",
        ],
        options=("reltol=1e-5", "vntol=1e-8", "abstol=1e-13"),
        libraries=("opamps.lib",),
    )


def _kick(run: RunResult, rate: float, count: int) -> _Kick:
    time = run.real("time")
    pin = run.real("adc_in")
    held = run.real("xu30.shp")
    settled = measure.mean(time, pin, 1e-6, _FIRST - 1e-7)
    last = _FIRST + (count - 1) / rate
    sampled = measure.value_at(time, held, last - 2e-9)
    closes = _FIRST + (count - 2) / rate + _CONVERSION
    lowest = measure.extremes(time, pin, closes, last - 2e-9)[0]
    try:
        back = measure.settling_time(time, pin, settled, _HALF_CODE, closes, last - 2e-9)
    except MeasureError:
        # Still outside half a code when the next conversion starts.
        back = float("nan")
    return _Kick((sampled - settled) / common.LSB, settled - lowest, back)


@bench(
    "signal_chain",
    "sampling-kick",
    "The converter input: settling of the sampling kick through R130 and C90",
    "section 4.5 (network at the converter input), section 4.6 (100 kSPS, option of 500 kSPS)",
)
def sampling_kick(ctx: Context) -> Outcome:
    """The converter samples a steady voltage and the driver refills its capacitor.

    The circuit holds the driver U29 with its filter and its rail, the
    22 ohm and 10 nF at the converter input, and the model of that input: a
    switch of 96 ohm and a capacitor of 55 pF, opened by the convert-start
    line for the longest conversion of the datasheet, 710 ns. The capacitor
    comes back empty from every conversion, which is the bounding case: the
    datasheet does not state what it holds. The voltage on it at the next
    sampling instant is compared with the voltage that the input has
    without any sampling. The run is made at 100 kSPS and at 500 kSPS, at
    three levels of the input.
    """
    decks: dict[str, str] = {}
    for rate, _, count in _RATES:
        for level, _ in _LEVELS:
            decks[f"{rate / 1e3:g}k-{level:g}v".replace(".", "p")] = _kick_deck(
                ctx, rate, count, level, None
            )
    decks["500k-2p45v-keeps"] = _kick_deck(ctx, 500e3, 16, 2.45, _KEEPS)
    shown = ctx.run("500k-2p45v", decks["500k-2p45v"])
    runs = ctx.run_many(decks)
    figures: list[Figure] = []
    for rate, rate_label, count in _RATES:
        acquisition = 1.0 / rate - _CONVERSION
        for level, level_label in _LEVELS:
            tag = f"{rate / 1e3:g}k-{level:g}v".replace(".", "p")
            got = _kick(runs[tag], rate, count)
            key = tag.replace("-", "_")
            figures.append(
                Figure(
                    f"error_{key}",
                    f"{rate_label}, {level_label}: sample against the settled input",
                    got.error_codes,
                    "codes",
                    low=-0.5,
                    high=0.5,
                    source="ADS8860 datasheet, page 32: the input must settle to 16 bits "
                    "within the acquisition time",
                )
            )
            if level == 2.45:
                figures += [
                    Figure(
                        f"dip_{key}",
                        f"{rate_label}, {level_label}: the input pin dips by",
                        got.dip,
                        "V",
                    ),
                    Figure(
                        f"back_{key}",
                        f"{rate_label}, {level_label}: pin back within half a code after",
                        got.back_after,
                        "s",
                        high=acquisition,
                        source=f"the acquisition time at {rate_label} with the longest "
                        "conversion, calculated here",
                    ),
                ]
    keeps = _kick(runs["500k-2p45v-keeps"], 500e3, 16)
    figures.append(
        Figure(
            "error_500k_keeps",
            "500 kSPS, near full scale, capacitor keeps nine tenths of its charge: sample "
            "against the settled input",
            keeps.error_codes,
            "codes",
        )
    )
    time = shown.real("time")
    first_shown = _FIRST + 12 / 500e3
    window = (time >= first_shown - 0.3e-6) & (time <= first_shown + 4.3e-6)
    micro = (time[window] - first_shown) * 1e6
    pin = shown.real("adc_in")[window]
    settled = measure.mean(time, shown.real("adc_in"), 1e-6, _FIRST - 1e-7)
    graph = Graph(
        name="kick",
        title="500 kSPS, 2.45 V at the input: two conversions",
        xlabel="Time after a rising edge of the convert-start line (us)",
        panels=(
            Panel("Convert-start line (V)"),
            Panel("Voltage (V)"),
            Panel("Input pin against its settled value (codes)"),
        ),
        traces=(
            Trace(micro, shown.real("cnv")[window], "", 0),
            Trace(micro, pin, "input pin", 1),
            Trace(micro, shown.real("xu30.shp")[window], "sampling capacitor", 1, "--"),
            Trace(micro, np.clip((pin - settled) / common.LSB, -30.0, 5.0), "", 2),
        ),
    )
    notes = (
        "The sampling capacitor is empty at the start of every acquisition. A real "
        "converter keeps part of its charge and kicks less; the last figure shows the "
        "size of that effect with nine tenths kept.",
        "The conversion takes 710 ns, the longest of the datasheet; a shorter one leaves "
        "more time to settle.",
        "An error that is the same at every sample is a gain error, which the calibration "
        "removes; it matters as an error that depends on the sample before, which this "
        "bench does not separate.",
        "The driver model has the open-loop output impedance and the bandwidth of its "
        "datasheet; the amplifier output is an ideal source, the reference and the rails "
        "are ideal. The clock and data lines of the converter are not in the circuit.",
    )
    return Outcome(tuple(figures), (graph,), notes)


def _reference_deck(ctx: Context, rate: float, count: int, c89: float) -> str:
    stop = _FIRST + count / rate
    mean = _REFERENCE_AMPS * _CONVERSION * rate
    return ctx.deck(
        f"Reference line: conversions at {rate / 1e3:g} kSPS",
        ctx.circuit(_REFERENCE_PARTS, common.ALIASES, None, {"C89": c89}),
        "* the supply of the reference; the converter input rests at half scale\n"
        "Vp3v3a p3v3_a 0 3.3\nVin adc_in 0 1.25\n",
        "* before the first conversion the line carries the mean reference current of\n"
        "* the converter, so that the run starts as if it had been converting for long\n"
        f"Imean vref 0 PWL(0 {mean:g} {_FIRST:g} {mean:g} {_FIRST + 1e-9:g} 0)\n",
        _convert(rate, count),
        control=[
            "save vref ref_cap cnv xu30.q @r131[i]",
            f"tran 2n {stop:g} 0 10n",
        ],
        options=("reltol=1e-5", "vntol=1e-8", "abstol=1e-13"),
    )


@bench(
    "signal_chain",
    "reference-line",
    "The reference pin of the converter during a conversion: R131 and C89",
    "section 4.6 (capacitors on the reference line, D-75)",
)
def reference_line(ctx: Context) -> Outcome:
    """The converter takes its reference current and the line is watched.

    The circuit holds the reference U12 with its capacitors, the 22 uF of
    C89 behind the 0.22 ohm of R131 at the REF pin of the converter, and
    the 100 nF of the monitor converter on the same line. The model of the
    converter draws its reference current for the 710 ns of every
    conversion: 150 uA at 2.5 V, the 300 uA of the datasheet in proportion
    to the reference. Before the first conversion the line carries the mean
    of that current, so that the run starts in the state of a converter
    that has been running for long. The run is made at 100 kSPS and at
    500 kSPS with C89 at its nominal value, and at 500 kSPS with the 14 uF
    and the 10.8 uF that the part keeps under bias.
    """
    cases = {
        "100k": (100e3, 12, 1.0, "100 kSPS"),
        "500k": (500e3, 40, 1.0, "500 kSPS"),
        "500k-14u": (500e3, 40, 14.0 / 22.0, "500 kSPS, C89 at 14 uF"),
        "500k-10u8": (500e3, 40, 10.8 / 22.0, "500 kSPS, C89 at 10.8 uF"),
    }
    decks = {
        name: _reference_deck(ctx, rate, count, c89)
        for name, (rate, count, c89, _) in cases.items()
    }
    kept = ctx.run("500k", decks["500k"])
    runs = ctx.run_many(decks)
    figures: list[Figure] = []
    for name, (rate, count, _c89, label) in cases.items():
        run = runs[name]
        time = run.real("time")
        pin = run.real("vref")
        idle = measure.mean(time, pin, 1e-6, _FIRST - 1e-7)
        last = _FIRST + (count - 1) / rate
        before = measure.value_at(time, pin, last - 5e-9)
        lowest = measure.extremes(time, pin, last, last + _CONVERSION)[0]
        key = name.replace("-", "_")
        figures += [
            Figure(
                f"start_{key}",
                f"{label}: REF pin at the start of a conversion, off its mean level by",
                abs(idle - before),
                "V",
                high=common.LSB,
                source="ADS8860 datasheet, page 31: within one code when a conversion starts",
            ),
            Figure(
                f"dip_{key}",
                f"{label}: REF pin falls during a conversion by",
                before - lowest,
                "V",
            ),
            Figure(
                f"dip_ppm_{key}",
                f"{label}: the same as a part of the reference",
                (before - lowest) / common.VREF * 1e6,
                "ppm",
            ),
        ]
    time = kept.real("time")
    first_shown = _FIRST + 30 / 500e3
    window = (time >= first_shown - 0.5e-6) & (time <= first_shown + 4.5e-6)
    micro = (time[window] - first_shown) * 1e6
    idle = measure.mean(time, kept.real("vref"), 1e-6, _FIRST - 1e-7)
    graph = Graph(
        name="line",
        title="Reference line at 500 kSPS: two conversions",
        xlabel="Time after a rising edge of the convert-start line (us)",
        panels=(
            Panel("Against the level at rest (uV)"),
            Panel("Current through R131 out of C89 (uA)"),
        ),
        traces=(
            Trace(micro, (kept.real("vref")[window] - idle) * 1e6, "REF pin", 0),
            Trace(micro, (kept.real("ref_cap")[window] - idle) * 1e6, "C89", 0, "--"),
            Trace(micro, -kept.real("@r131[i]")[window] * 1e6, "", 1),
        ),
    )
    notes = (
        "The reference current of the model is a constant current during the conversion. "
        "The real converter takes its charge as one packet per bit, with peaks far above "
        "the mean; the dip of the REF pin inside a bit period is therefore larger than "
        "this figure, and what counts is that the pin has recovered at the end of each "
        "bit, which no model here resolves.",
        "The current is taken as 150 uA at 2.5 V (the datasheet states 300 uA at 5 V and "
        "mid-code); it depends on the code, which the model leaves out.",
        "The reference is the model of the analog rails block, whose output impedance is "
        "a fit to two figures of its datasheet. The track between the reference and the "
        "converter has no inductance or resistance here, and C89 no inductance.",
        "A dip that is the same at every conversion is part of the gain, which the "
        "calibration removes.",
    )
    return Outcome(tuple(figures), (graph,), notes)
