"""The TPS63020 model of the source meter against its datasheet."""

from __future__ import annotations

import numpy as np

from benches.source_meter import common
from circuit_sim import measure
from circuit_sim.bench import (
    VENDOR_TIER,
    Context,
    Figure,
    Graph,
    Outcome,
    Panel,
    Trace,
    bench,
    near,
)
from circuit_sim.circuit import Circuit
from circuit_sim.engine import RunResult

_REF = common.CONVERTER

_DOCUMENT = "Texas Instruments SLVS916I"
"""The datasheet the figures are taken from."""

_REFERENCE_OUT = 0.5 * (1.0 + 1e6 / 180e3)
"""Output of the application circuit of page 13: 1 Mohm over 180 kohm."""

_OUT_FARADS = 40e-6
"""What three capacitors of 22 uF are taken to keep at 3.3 V (assumption).

The datasheet allows for 20 % more to 50 % less than the nominal value
(page 13, table 1, note 2).
"""

_ENABLE = 20e-6
"""Instant at which the enable pin rises."""

_STEP = 1.0e-3
_RELEASE = 1.3e-3
_STOP = 1.6e-3
"""Load step of 0.5 A to 1.5 A and back, and the end of the run."""

_SAVE = "save vout fb l.xl2.l1#branch vin#branch"
"""What the start and load step run keeps: the model of the manufacturer has
hundreds of nodes and takes millions of steps."""

_STATIC_STOP = 3e-3
"""Length of a run that ends at rest."""

_EFFICIENCY = (
    (3.6, 2.5, 0.01, 0.40),
    (3.6, 2.5, 1.0, 0.91),
    (3.6, 4.5, 0.01, 0.42),
    (3.6, 4.5, 1.0, 0.92),
)
"""Input voltage, output voltage, load and efficiency read from page 18, figure 9."""


def _part(ctx: Context, **params: float | str) -> Circuit:
    """The converter with its inductor and the capacitor of its control supply."""
    found = ctx.netlist.component(_REF)
    aliases = {
        found.net_of("10"): "vin",
        found.net_of("1"): "vina",
        found.net_of("12"): "en",
        found.net_of("3"): "fb",
        found.net_of("4"): "vout",
        found.net_of("8"): "l1",
        found.net_of("6"): "l2",
        found.net_of("14"): "pg",
    }
    overrides = {_REF: common.part(ctx, _REF, **params)} if params else None
    return ctx.circuit([_REF, "L2", "C37"], aliases, overrides)


def _application(
    ctx: Context, vin: float, vout: float, load: str, farads: float = _OUT_FARADS
) -> str:
    """The application circuit of page 13 around the converter."""
    lower = 1e6 * 0.5 / (vout - 0.5)
    lines = [
        "* application circuit of the datasheet: divider of 1 Mohm, output capacitors,",
        "* the enable pin raised after the input stands",
        f"Vin vin 0 PWL(0 0 5u {vin:g})",
        f"Ven en 0 PWL(0 0 {_ENABLE:g} 0 {_ENABLE + 1e-6:g} {vin:g})",
        "R1 vout fb 1meg",
        f"R2 fb 0 {lower:g}",
        f"Cout vout out_c {farads:g}",
        "Resr out_c 0 2m",
        load,
    ]
    if ctx.tier == VENDOR_TIER:
        lines += [
            "* the model of the manufacturer does not hold the feed of VINA from VIN",
            "Rvina vin vina 100",
            "Rpg pg vout 1meg",
        ]
    return "\n".join(lines) + "\n"


def _step_deck(ctx: Context, vin: float) -> str:
    """Start into 6.6 ohm, then a load step of 1 A and its release."""
    load = f"Rload vout 0 6.6\nIload vout 0 PULSE(0 1 {_STEP:g} 1u 1u {_RELEASE - _STEP:g} 1)"
    step = "20n" if ctx.tier == VENDOR_TIER else "0.2u"
    deck = ctx.deck(
        f"TPS63020: start and load step from {vin:g} V",
        _part(ctx),
        _application(ctx, vin, _REFERENCE_OUT, load),
        control=[_SAVE, f"tran {step} {_STOP:g} 0 {step} uic"],
    )
    common.repair_vendor_copies(ctx)
    return deck


def _static_deck(ctx: Context, vin: float, vout: float, amps: float) -> str:
    """A run that ends at rest with a constant load."""
    return ctx.deck(
        f"TPS63020: {vin:g} V to {vout:g} V at {amps:g} A",
        _part(ctx),
        _application(ctx, vin, vout, f"Iload vout 0 PWL(0 0 0.6m 0 0.8m {amps:g})"),
        control=[f"tran 1u {_STATIC_STOP:g} 0 5u uic"],
    )


def _limit_deck(ctx: Context, ohms: float, **params: float | str) -> str:
    """The output loaded with a resistor that asks for more than the limit."""
    return ctx.deck(
        "TPS63020: current limit",
        _part(ctx, **params),
        _application(ctx, 4.2, _REFERENCE_OUT, f"Rload vout 0 {ohms:g}"),
        control=[f"tran 1u {_STATIC_STOP:g} 0 5u uic"],
    )


def _reverse_deck(ctx: Context) -> str:
    """The output held above its target by a source: the part takes current."""
    load = "Vhold hold 0 PWL(0 0 0.6m 0 0.8m 3.6)\nRhold hold vout 50m"
    return ctx.deck(
        "TPS63020: output held above the target",
        _part(ctx),
        _application(ctx, 4.2, _REFERENCE_OUT, load),
        control=[f"tran 1u {_STATIC_STOP:g} 0 5u uic"],
    )


def _inductor_amps(run: RunResult) -> np.ndarray:
    """The current of the inductor of the circuit."""
    return run.real("l.xl2.l1#branch")


def _step_figures(run: RunResult, vin: float) -> tuple[list[Figure], np.ndarray, np.ndarray]:
    """The figures of the start and of the load step of one run."""
    time = run.real("time")
    out = run.real("vout")
    tag = f"{vin:g}v".replace(".", "p")
    before = measure.mean(time, out, _STEP - 0.1e-3, _STEP)
    loaded = measure.mean(time, out, _RELEASE - 50e-6, _RELEASE)
    lowest = measure.extremes(time, out, _STEP, _RELEASE)[0]
    highest = measure.extremes(time, out, _RELEASE, _STOP)[1]
    risen = measure.first_crossing(time, out, 0.9 * _REFERENCE_OUT, rising=True, after=_ENABLE)
    figures = [
        near(
            f"output_{tag}",
            f"Output from {vin:g} V with 1 Mohm over 180 kohm",
            before,
            "V",
            _REFERENCE_OUT,
            0.01,
            f"{_DOCUMENT}, page 6: reference 0.5 V, 495 mV to 505 mV",
        ),
        Figure(
            f"step_dip_{tag}",
            f"Load step of 0.5 A to 1.5 A from {vin:g} V: lowest point",
            lowest - before,
            "V",
            expected=-0.1,
            low=-0.13,
            high=-0.07,
            source=f"{_DOCUMENT}, page 20, figures 21 and 22: about -75 mV to -115 mV",
        ),
        Figure(
            f"step_peak_{tag}",
            f"Release of that step from {vin:g} V: highest point",
            highest - before,
            "V",
            expected=0.1,
            low=0.07,
            high=0.13,
            source=f"{_DOCUMENT}, page 20, figures 21 and 22",
        ),
        Figure(
            f"load_regulation_{tag}",
            f"Fall of the output for 1 A more from {vin:g} V",
            before - loaded,
            "V",
            high=0.005 * _REFERENCE_OUT,
            source=f"{_DOCUMENT}, page 6: load regulation 0.5 %",
        ),
        Figure(
            f"start_{tag}",
            f"Start from {vin:g} V into 6.6 ohm: 90 % of the output after the enable",
            risen - _ENABLE,
            "s",
            expected=250e-6,
            low=100e-6,
            high=400e-6,
            source=f"{_DOCUMENT}, page 20, figures 24 and 25, into 2.2 ohm",
        ),
        Figure(
            f"start_peak_{tag}",
            f"Start from {vin:g} V: highest output before the load step",
            measure.extremes(time, out, _ENABLE, _STEP)[1] - before,
            "V",
        ),
    ]
    return figures, time, out


@bench(
    "models",
    "source-meter-tps63020",
    "TPS63020 model of the source meter against its datasheet",
    "the model of the tracking pre-regulator U16 with its inductor L2",
)
def tps63020(ctx: Context) -> Outcome:
    """The converter U16 and its inductor are put in the application circuit of the datasheet.

    A divider of 1 Mohm over 180 kohm sets 3.28 V. The run starts the
    converter, steps the load from 0.5 A to 1.5 A and back, and gives the
    start time, the dip and the load regulation. Runs that end at rest
    give the efficiency in forced PWM, the current limit above and below
    1.2 V of output, and the current that the part takes back when its
    output is held above the target. With the model of the manufacturer
    only the first run from 4.2 V is made: it switches at 2.4 MHz and a
    millisecond takes minutes.
    """
    figures: list[Figure] = []
    traces: list[Trace] = []
    inputs = (4.2,) if ctx.tier == VENDOR_TIER else (4.2, 2.4)
    for vin in inputs:
        run = ctx.run(f"step-{vin:g}v".replace(".", "p"), _step_deck(ctx, vin))
        found, time, out = _step_figures(run, vin)
        figures += found
        traces += [
            Trace(time * 1e3, out, f"output, {vin:g} V in", 0),
            Trace(time * 1e3, _inductor_amps(run), f"inductor, {vin:g} V in", 1),
        ]
    graph = Graph(
        name="step",
        title="TPS63020 in its application circuit: start, load step of 1 A, release",
        xlabel="Time (ms)",
        panels=(Panel("Output (V)"), Panel("Inductor current (A)")),
        traces=tuple(traces),
        xmarks=((_STEP * 1e3, "0.5 A to 1.5 A"), (_RELEASE * 1e3, "back")),
    )
    if ctx.tier == VENDOR_TIER:
        vendor_notes = (
            "The transient model of the manufacturer, in the same circuit as the open "
            "tier. Its line with a doubled keyword is repaired in the working copy; "
            "the file itself is not changed.",
        )
        return Outcome(tuple(figures), (graph,), vendor_notes)

    decks = {
        f"eff-{index}": _static_deck(ctx, vin, vout, amps)
        for index, (vin, vout, amps, _) in enumerate(_EFFICIENCY)
    }
    decks["limit"] = _limit_deck(ctx, 0.5)
    decks["limit-short"] = _limit_deck(ctx, 0.01)
    decks["reverse"] = _reverse_deck(ctx)
    decks["off"] = ctx.deck(
        "TPS63020: enable pin low",
        _part(ctx),
        _application(ctx, 4.2, _REFERENCE_OUT, "Rload vout 0 6.6").replace(
            f"Ven en 0 PWL(0 0 {_ENABLE:g} 0 {_ENABLE + 1e-6:g} 4.2)", "Ven en 0 0.4"
        ),
        control=[f"tran 1u {_STATIC_STOP:g} 0 5u uic"],
    )
    runs = ctx.run_many(decks)
    for index, (vin, vout, amps, expected) in enumerate(_EFFICIENCY):
        run = runs[f"eff-{index}"]
        power_in = -common.last(run, "vin#branch") * vin
        power_out = common.last(run, "vout") * amps
        figures.append(
            Figure(
                f"efficiency_{index}",
                f"Efficiency in forced PWM, {vin:g} V to {vout:g} V at {amps * 1e3:g} mA",
                100.0 * power_out / power_in,
                "%",
                expected=100.0 * expected,
                low=100.0 * expected - 5.0,
                high=100.0 * expected + 5.0,
                source=f"{_DOCUMENT}, page 18, figure 9, read from the curve",
            )
        )
    figures += [
        Figure(
            "current_limit",
            "Average inductor current into 0.5 ohm, output above 1.2 V",
            float(_inductor_amps(runs["limit"])[-1]),
            "A",
            expected=4.0,
            low=3.5,
            high=4.5,
            source=f"{_DOCUMENT}, page 6: 3.5 A to 4.5 A",
        ),
        Figure(
            "current_limit_short",
            "Average inductor current into a short circuit",
            float(_inductor_amps(runs["limit-short"])[-1]),
            "A",
            expected=0.4,
            low=0.3,
            high=0.6,
            source=f"{_DOCUMENT}, page 10, 7.4.1: the limit starts at 400 mA",
        ),
        Figure(
            "reverse_limit",
            "Inductor current with the output held at 3.6 V, above the target",
            float(_inductor_amps(runs["reverse"])[-1]),
            "A",
            expected=-0.7,
            low=-0.8,
            high=-0.6,
            source="Texas Instruments SLVA726, page 3: 0.6 A to 0.8 A, typical",
        ),
        Figure(
            "returned_power",
            "Power returned to the input in that state",
            common.last(runs["reverse"], "vin#branch") * 4.2,
            "W",
        ),
        Figure(
            "off_output",
            "Output with the enable pin at 0.4 V, 6.6 ohm of load",
            common.last(runs["off"], "vout"),
            "V",
            high=0.01,
            source=f"{_DOCUMENT}, page 6: low below 0.4 V; page 9: the load is disconnected",
        ),
    ]
    notes = (
        "The model is averaged over the switching period: the graph shows no ripple, "
        "and the limits of the load step are the span that the datasheet figures show, "
        "not datasheet limits.",
        "The loop gains of the model are fitted to this load step, and its losses to "
        "the four efficiency points; both are therefore not independent checks. The "
        "run with the model of the manufacturer is the second opinion.",
        "The output capacitance of 40 uF, the straight line of the current limit "
        "below 1.2 V and the hold of the least duty cycle are assumptions.",
    )
    return Outcome(tuple(figures), (graph,), notes)
