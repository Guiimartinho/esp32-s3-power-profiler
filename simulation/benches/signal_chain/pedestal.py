"""The pedestal: divider, buffer U26 and the reference pin of the amplifier."""

from __future__ import annotations

import numpy as np

from benches import frontend
from benches.signal_chain import common
from circuit_sim import measure, tolerance
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_SWEEP = "ac dec 60 1 100meg"
"""Frequencies of the small-signal runs."""

_BUFFER_OFFSET = 100e-6
"""Offset of the buffer U26, at most (OPA197 datasheet, page 7)."""

_BIAS_HOT = 5e-9
"""Bias current of the buffer over temperature, at most (OPA197, page 7)."""

_SOURCE_OHMS = 1.0
"""Source impedance that the amplifier asks of its reference pin (AD8421, page 23)."""

_STEP_AT = 20e-6
"""Instant of the step of the shunt voltage."""

_STEP = (10e-3, 110e-3)
"""Shunt voltage before and after the step."""

_POWER_UP = 1e-3
"""Instant at which the reference appears in the start-up run."""

_LEAST_MARGIN = 45.0
"""Phase margin that this bench asks of the buffer loop."""


def _probe(
    ctx: Context, vac: float = 0.0, iac: float = 0.0, **params: float
) -> dict[str, PartModel]:
    """The buffer U26 with the sources that measure its loop."""
    base = ctx.models.model_of(ctx.netlist.component("U26"))
    extra = "".join(f" {name}={value:g}" for name, value in params.items())
    return {
        "U26": PartModel(
            kind="subckt",
            name="SIGNAL_CHAIN_OPA197_PROBE",
            ports=base.ports,
            library="signal_chain.lib",
            origin="written here",
            params=f"vac={vac:g} iac={iac:g}{extra}",
        )
    }


def _deck(
    ctx: Context,
    title: str,
    control: list[str],
    *,
    reference: str = "2.5",
    shunt: str = "0.05",
    test_current: str = "0",
    models: dict[str, PartModel] | None = None,
    scales: dict[str, float] | None = None,
) -> str:
    return ctx.deck(
        title,
        common.chain(ctx, overrides=models, scales=scales),
        frontend.rails(vref=None),
        f"Vref vref 0 {reference}\n",
        common.taps({0: shunt}),
        common.address(0),
        f"* a test current into the pedestal node\nItest 0 ped {test_current}\n",
        control=control,
        libraries=common.LIBRARIES,
    )


def _loop(series: RunResult, shunt: RunResult) -> tuple[common.Vector, np.ndarray]:
    """The loop gain of the buffer from the two runs of a double injection."""
    frequency = series.real("frequency")
    voltage_ratio = -series.vector("xu26.amp") / series.vector("ped")
    delivered = shunt.vector("v.xu26.vser#branch")
    current_ratio = -delivered / (delivered + 1.0)
    loop = measure.loop_gain(
        np.asarray(voltage_ratio, dtype=np.complex128),
        np.asarray(current_ratio, dtype=np.complex128),
    )
    return frequency, loop


@bench(
    "signal_chain",
    "pedestal",
    "The pedestal: divider with its 1 uF, the buffer U26 and the reference pin of U27",
    "section 4.5 (reference pin at +50 mV), section 8 (zero calibration)",
)
def pedestal(ctx: Context) -> Outcome:
    """The pedestal is followed from the reference to the reference pin of the amplifier.

    An operating point gives the voltage at the test point and the current
    that the reference pin takes from the buffer; the same point is solved
    with the divider at the two ends of its tolerance and with the offset
    and the bias current of the buffer at their limits. Small-signal runs
    give what the divider and its 1 uF let through from the reference, the
    impedance that the buffer offers the reference pin, and the loop gain
    of the buffer by double injection. Two transient runs follow: the
    amplifier output steps by 2 V, which changes the current of the
    reference pin, and the reference appears at power-up.
    """
    rest = ctx.run(
        "rest",
        _deck(ctx, "Pedestal: operating point", ["save all @r121[i]", "op"], models=_probe(ctx)),
    )
    spread = tolerance.tolerances(ctx.netlist, ("R121", "R122"))
    corners = {
        "high": _deck(
            ctx,
            "Pedestal: divider and buffer at the high corner",
            ["op"],
            models=_probe(ctx, vos=-_BUFFER_OFFSET, ib=-_BIAS_HOT),
            scales=tolerance.corner_scales(spread, {"R121": -1, "R122": 1}),
        ),
        "low": _deck(
            ctx,
            "Pedestal: divider and buffer at the low corner",
            ["op"],
            models=_probe(ctx, vos=_BUFFER_OFFSET, ib=_BIAS_HOT),
            scales=tolerance.corner_scales(spread, {"R121": 1, "R122": -1}),
        ),
        "from-reference": _deck(
            ctx, "Pedestal: from the reference to the test point", [_SWEEP], reference="dc 2.5 ac 1"
        ),
        "impedance": _deck(
            ctx, "Pedestal: impedance at the reference pin", [_SWEEP], test_current="dc 0 ac 1"
        ),
        "series": _deck(
            ctx, "Pedestal buffer: loop, series", [_SWEEP], models=_probe(ctx, vac=1.0)
        ),
        "shunt": _deck(ctx, "Pedestal buffer: loop, shunt", [_SWEEP], models=_probe(ctx, iac=1.0)),
    }
    runs = ctx.run_many(corners)
    step = ctx.run(
        "step",
        _deck(
            ctx,
            "Pedestal: the amplifier output steps by 2 V",
            ["save ped ped_div amp_raw adc_in", "tran 5n 120u 0 20n"],
            shunt=f"PWL(0 {_STEP[0]:g} {_STEP_AT:g} {_STEP[0]:g} {_STEP_AT + 2e-8:g} {_STEP[1]:g})",
        ),
    )
    power = ctx.run(
        "power-up",
        _deck(
            ctx,
            "Pedestal: the reference appears",
            ["save ped ped_div vref adc_in", "tran 10u 20m 0 20u"],
            reference=f"PWL(0 0 {_POWER_UP:g} 0 {_POWER_UP + 1e-5:g} 2.5)",
            shunt="0",
        ),
    )
    level = float(rest.real("ped")[0])
    divider_current = float(rest.real("@r121[i]")[0])
    pin_current = float(rest.real("v.xu26.vser#branch")[0])
    high = float(runs["high"].real("ped")[0])
    low = float(runs["low"].real("ped")[0])
    figures = [
        near(
            "pedestal",
            "Pedestal at the test point TP41",
            level,
            "V",
            common.PEDESTAL,
            0.002,
            "section 4.5: +50 mV from 49.9 kohm and 1.02 kohm",
        ),
        Figure(
            "pedestal_low",
            "Pedestal with divider and buffer at the low corner",
            low,
            "V",
        ),
        Figure(
            "pedestal_high",
            "Pedestal with divider and buffer at the high corner",
            high,
            "V",
        ),
        Figure(
            "spread_codes",
            "The two corners apart, in codes of the converter",
            (high - low) / common.LSB,
            "codes",
        ),
        Figure(
            "divider_current",
            "Current that the divider takes from the reference",
            divider_current,
            "A",
        ),
        Figure(
            "pin_current",
            "Current of the buffer output at 50 mV of shunt voltage (negative: into the buffer)",
            pin_current,
            "A",
        ),
    ]
    frequency = runs["from-reference"].real("frequency")
    through = np.asarray(runs["from-reference"].vector("ped"), dtype=np.complex128)
    impedance = np.asarray(runs["impedance"].vector("ped"), dtype=np.complex128)
    log_f = np.log10(frequency)
    figures += [
        Figure(
            "divider_ratio",
            "From the reference to the pedestal at 1 Hz",
            float(np.abs(through[0])),
            "",
            expected=1020.0 / 50920.0,
        ),
        near(
            "divider_corner",
            "Corner above which the divider and its 1 uF keep reference noise off the pedestal",
            measure.corner_frequency(frequency, through),
            "Hz",
            159.0,
            0.03,
            "1 uF with 49.9 kohm and 1.02 kohm in parallel, calculated here",
        ),
    ]
    for hertz, text in ((1e3, "1 kHz"), (10e3, "10 kHz"), (40e3, "40 kHz")):
        figures.append(
            Figure(
                f"impedance_{int(hertz)}",
                f"Impedance that the buffer offers the reference pin at {text}",
                float(np.interp(np.log10(hertz), log_f, np.abs(impedance))),
                "ohm",
                high=_SOURCE_OHMS,
                source="AD8421 datasheet, page 23: source impedance of the REF pin below 1 ohm",
            )
        )
    at_band_edge = float(np.interp(np.log10(40e3), log_f, np.abs(impedance)))
    figures.append(
        Figure(
            "gain_error_40khz",
            "Gain error that this impedance causes at 40 kHz",
            at_band_edge / 20e3 * 1e6,
            "ppm",
        )
    )
    loop_frequency, loop = _loop(runs["series"], runs["shunt"])
    crossover, margin = measure.stability_margins(loop_frequency, loop)
    figures += [
        Figure(
            "loop_margin",
            "Phase margin of the buffer loop with the reference pin as its load",
            margin,
            "deg",
            low=_LEAST_MARGIN,
            source="this bench: 45 degrees is the least it accepts",
        ),
        Figure("loop_crossover", "Crossover of the buffer loop", crossover, "Hz"),
    ]
    time = step.real("time")
    node = step.real("ped")
    before = measure.mean(time, node, _STEP_AT - 5e-6, _STEP_AT - 1e-6)
    after = measure.mean(time, node, 110e-6, 119e-6)
    lowest, highest = measure.extremes(time, node, _STEP_AT, 119e-6)
    figures += [
        Figure(
            "step_peak",
            "Amplifier output steps by 2 V: largest excursion of the pedestal",
            max(highest - before, before - lowest),
            "V",
        ),
        Figure(
            "step_shift",
            "Amplifier output steps by 2 V: lasting shift of the pedestal",
            after - before,
            "V",
            low=-0.5 * common.LSB,
            high=0.5 * common.LSB,
            source="this bench: below half a code of the converter",
        ),
        Figure(
            "step_settles",
            "Amplifier output steps by 2 V: pedestal within half a code after",
            measure.settling_time(time, node, after, 0.5 * common.LSB, _STEP_AT, 119e-6),
            "s",
        ),
    ]
    power_time = power.real("time")
    power_node = power.real("ped")
    final = measure.mean(power_time, power_node, 19e-3, 19.9e-3)
    figures.append(
        Figure(
            "power_up",
            "Reference appears: pedestal within one code of its level after",
            measure.settling_time(power_time, power_node, final, common.LSB, _POWER_UP),
            "s",
            high=0.2,
            source="rule F-36: the zero calibration starts no earlier than 200 ms after a reset",
        )
    )
    response = Graph(
        name="response",
        title="Pedestal: what comes through from the reference, and the impedance at the pin",
        xlabel="Frequency (Hz)",
        panels=(
            Panel("Reference to pedestal (dB)"),
            Panel("Impedance at the reference pin (ohm)", log=True, marks=((1.0, "1 ohm"),)),
            Panel("Loop gain of the buffer (dB)", marks=((0.0, "0 dB"),)),
        ),
        traces=(
            Trace(frequency, measure.decibels(through), "", 0),
            Trace(frequency, np.abs(impedance), "", 1),
            Trace(loop_frequency, measure.decibels(loop), "", 2),
        ),
        logx=True,
    )
    micro = time * 1e6
    waves = Graph(
        name="step",
        title="Pedestal while the amplifier output steps from 0.25 V to 2.24 V",
        xlabel="Time (us)",
        panels=(Panel("Amplifier output (V)"), Panel("Pedestal at TP41 (mV)")),
        traces=(
            Trace(micro, step.real("amp_raw"), "", 0),
            Trace(micro, node * 1e3, "", 1),
        ),
        xmarks=((_STEP_AT * 1e6, "step"),),
    )
    start = Graph(
        name="power-up",
        title="Pedestal when the reference appears at 1 ms",
        xlabel="Time (ms)",
        panels=(Panel("Voltage (mV)"),),
        traces=(
            Trace(power_time * 1e3, power_node * 1e3, "pedestal at TP41", 0),
            Trace(power_time * 1e3, power.real("ped_div") * 1e3, "divider node", 0, "--"),
        ),
    )
    notes = (
        "The reference is an ideal source: its own noise, tolerance and output impedance "
        "are not in these figures. The pedestal follows the reference in proportion, as "
        "the converter does, so a reference error does not move the code at zero current.",
        "The corners take the two divider resistors to opposite ends of their 0.1 % and "
        "the buffer to 100 uV of offset and 5 nA of bias current, its limit over "
        "temperature. The zero calibration removes what is constant of it.",
        "The load of the buffer is the reference pin of the amplifier model, 20 kohm to "
        "its first stage. The capacitance of the test point and of the track is not in "
        "the circuit.",
        "The buffer model has the open-loop output impedance of its datasheet, 375 ohm "
        "with 100 pF across it. Its impedance in closed loop passes 1 ohm near 30 kHz; "
        "the datasheet of the amplifier asks for less than 1 ohm without naming a "
        "frequency. The consequence is a gain error of the positive input by the ratio "
        "to 20 kohm.",
    )
    return Outcome(tuple(figures), (response, waves, start), notes)
