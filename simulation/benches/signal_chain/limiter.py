"""The limiter in front of the converter driver during an over-range."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from benches import frontend
from benches.signal_chain import common
from circuit_sim import measure, tolerance
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult
from circuit_sim.values import parse_value

_START = 20e-6
"""Instant at which the shunt voltage leaves the range."""

_RISE = 1e-6
"""Time in which the shunt voltage reaches its over-range value."""

_END = 400e-6
"""End of a run: the limiter and the filter rest."""

_NORMAL = 50e-3
"""Shunt voltage before the over-range."""

_ABSOLUTE = 0.3
"""How far the converter input may stand above its reference (ADS8860, page 5)."""

_BOUND = 0.25
"""Bound that section 4.5 calculates for the converter input above the reference."""

_INPUT_BEYOND = 0.5
"""How far an input of the driver may stand beyond its supply before its
protection diode conducts (OPA365 datasheet, page 5)."""

_INPUT_CURRENT_MOST = 10e-3
"""Current that this diode may carry (OPA365 datasheet, page 5)."""

_LOW_SUPPLY_CURRENT = 4.0e-3
"""Supply current of a driver at the low end, at 5 V: an assumption, the datasheet
of the OPA365 states 4.6 mA typical and 5 mA at most and no least value."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One over-range.

    Attributes:
        name: Short name of the case.
        label: What the case is, as the report shows it.
        shunt: Shunt voltage of the over-range.
        diode: Model of the limiter diodes.
        positive_rail: Voltage of the +12 V rail.
        swing: Distance the amplifier output keeps from its positive supply.
        corner: Move the resistors and the driver to the corner that lifts
            the driver rail.
    """

    name: str
    label: str
    shunt: float = 0.6
    diode: str = "BAV199"
    positive_rail: float = 12.0
    swing: float | None = None
    corner: bool = False


_NOMINAL = _Case("nominal", "0.6 V at the shunt")

_CASES = (
    _NOMINAL,
    replace(_NOMINAL, name="diode-high", label="diodes at 0.9 V", diode="BAV199_HI"),
    replace(_NOMINAL, name="diode-low", label="diodes at 0.7 V", diode="BAV199_LO"),
    replace(_NOMINAL, name="ladder-3v", label="3 V at the shunt", shunt=3.0),
    replace(
        _NOMINAL,
        name="rail-high",
        label="+12 V rail at 12.6 V, amplifier 1.2 V below it",
        positive_rail=12.6,
        swing=1.2,
    ),
    replace(
        _NOMINAL,
        name="corner",
        label="rail and resistors at the corner that lifts the driver rail",
        diode="BAV199_LO",
        positive_rail=12.6,
        swing=1.2,
        corner=True,
    ),
    replace(_NOMINAL, name="reverse", label="-0.3 V at the shunt (reverse current)", shunt=-0.3),
)


def _deck(ctx: Context, case: _Case) -> str:
    models: dict[str, PartModel] = {}
    scales: dict[str, float] = {}
    if case.diode != "BAV199":
        base = ctx.models.model_of(ctx.netlist.component("D22"), ctx.tier)
        models["D22"] = replace(base, name=case.diode)
    if case.swing is not None:
        models["U27"] = common.with_params(ctx, "U27", vhi=case.swing)
    if case.corner:
        spread = tolerance.tolerances(ctx.netlist, ("R124", "R125", "R127", "R129"))
        scales = tolerance.corner_scales(spread, {"R124": -1, "R125": -1, "R127": 1, "R129": -1})
        models["U29"] = common.with_params(ctx, "U29", iq=_LOW_SUPPLY_CURRENT)
        models["U28"] = common.with_params(ctx, "U28", vos=200e-6)
    stimulus = f"PWL(0 {_NORMAL:g} {_START:g} {_NORMAL:g} {_START + _RISE:g} {case.shunt:g})"
    return ctx.deck(
        f"Signal chain: over-range, {case.label}",
        common.chain(ctx, converter=True, overrides=models, scales=scales),
        frontend.rails(p12=case.positive_rail),
        common.taps({0: stimulus}),
        common.address(0),
        "* the converter acquires: its convert-start line is low\nVcnv cnv 0 0\n",
        control=[
            "save amp_raw lim flt adc_drv adc_in vdrv buf_out inp inn Vref#branch "
            "@r125[i] @r129[i] @dd22_1[id] @dd22_2[id] @d.xu30.dpu[id]",
            f"tran 50n {_END:g} 0 200n",
        ],
        libraries=common.LIBRARIES,
    )


def _rest(result: RunResult, name: str, before: bool = False) -> float:
    """The value of a vector at rest: before the over-range or at the end of the run."""
    time = result.real("time")
    if before:
        return measure.mean(time, result.real(name), _START - 5e-6, _START - 1e-6)
    return measure.mean(time, result.real(name), _END - 20e-6, _END - 1e-6)


@bench(
    "signal_chain",
    "limiter",
    "The limiter in front of the converter driver during an over-range",
    "section 4.5 (limiter D-73, driver rail), section 4.6 (converter input), section 16",
)
def limiter(ctx: Context) -> Outcome:
    """The shunt voltage leaves the range and stays there.

    Range 0 is held. The voltage across the shunt rises from 50 mV to 0.6 V
    within 1 us and stays, so that the amplifier goes to its positive limit
    and the limiter works: R125 feeds the diode pair D22, whose upper diode
    ends on the driver rail. The run goes on until everything rests. It is
    repeated with the forward voltage variants of the diodes, with 3 V
    across the shunt, with the +12 V rail and the parts at the corner that
    lifts the driver rail, and with a reverse current, which takes the
    amplifier output below ground and the lower diode into conduction.
    """
    runs = {
        case.name: ctx.run(case.name, _deck(ctx, case), keep=case is _NOMINAL) for case in _CASES
    }
    figures: list[Figure] = []
    highest = -np.inf
    for case in _CASES:
        run = runs[case.name]
        time = run.real("time")
        key = case.name.replace("-", "_")
        adc_rest = _rest(run, "adc_in")
        adc_peak = measure.extremes(time, run.real("adc_in"), _START, _END)[1]
        if case.shunt < 0.0:
            figures += [
                Figure(
                    f"amp_{key}",
                    f"{case.label}: amplifier output",
                    _rest(run, "amp_raw"),
                    "V",
                ),
                Figure(
                    f"limiter_{key}",
                    f"{case.label}: limiter node",
                    _rest(run, "lim"),
                    "V",
                ),
                Figure(
                    f"converter_{key}",
                    f"{case.label}: converter input",
                    measure.extremes(time, run.real("adc_in"), _START, _END)[0],
                    "V",
                    low=-0.1,
                    source="ADS8860 datasheet, page 6: input range from -0.1 V",
                ),
                Figure(
                    f"clamp_current_{key}",
                    f"{case.label}: current through R125",
                    _rest(run, "@r125[i]"),
                    "A",
                ),
            ]
            continue
        highest = max(highest, adc_peak - common.VREF)
        figures += [
            Figure(
                f"converter_{key}",
                f"{case.label}: converter input above the reference, at rest",
                adc_rest - common.VREF,
                "V",
                expected=0.20 if case is _NOMINAL else None,
                high=_BOUND,
                source="section 4.5: VREF + 0.25 V at the most, VREF + 0.20 V simulated",
            ),
            Figure(
                f"clamp_current_{key}",
                f"{case.label}: current through R125 into the limiter",
                _rest(run, "@r125[i]"),
                "A",
            ),
        ]
    nominal = runs[_NOMINAL.name]
    time = nominal.real("time")
    r128 = parse_value(ctx.netlist.component("R128").value)
    reference_before = _rest(nominal, "vref#branch", before=True)
    reference_after = _rest(nominal, "vref#branch")
    figures += [
        Figure(
            "amplifier",
            "Amplifier output during the over-range",
            _rest(nominal, "amp_raw"),
            "V",
            expected=10.0,
            source="section 4.5: the amplifier output can reach 10 V",
        ),
        Figure(
            "limiter_node",
            "Limiter node during the over-range",
            _rest(nominal, "lim"),
            "V",
        ),
        Figure(
            "driver_input_beyond",
            "Limiter node above the supply of the driver during the over-range",
            _rest(nominal, "lim") - _rest(nominal, "vdrv"),
            "V",
        ),
        Figure(
            "driver_input_current",
            "Current into the driver input through R128 if its protection diode holds it "
            "0.5 V above the supply",
            (_rest(nominal, "lim") - _rest(nominal, "vdrv") - _INPUT_BEYOND) / r128,
            "A",
            high=_INPUT_CURRENT_MOST,
            source="OPA365 datasheet, page 5: inputs that pass 0.5 V beyond a supply are to "
            "be limited to 10 mA",
        ),
        Figure(
            "rail_before",
            "Driver rail at the test point before the over-range",
            _rest(nominal, "vdrv", before=True),
            "V",
            expected=2.68,
            low=2.66,
            high=2.70,
            source="section 4.5: about 2.68 V",
        ),
        Figure(
            "rail_during",
            "Driver rail at the test point during the over-range",
            _rest(nominal, "vdrv"),
            "V",
        ),
        Figure(
            "into_rail",
            "Current that the upper diode puts into the driver rail",
            _rest(nominal, "@dd22_2[id]"),
            "A",
            high=2.3e-3,
            source="section 4.5: R125 limits the current into the driver rail to 2.3 mA",
        ),
        Figure(
            "buffer_current",
            "Current of the rail buffer through R129 during the over-range (out of the buffer)",
            _rest(nominal, "@r129[i]"),
            "A",
            low=0.0,
            source="this bench: the buffer keeps sourcing, the rail stays regulated",
        ),
        Figure(
            "into_reference",
            "Change of the current that the reference delivers, over-range against before",
            abs(reference_after - reference_before),
            "A",
            high=1e-6,
            source="section 4.5: no current flows into the reference (limit of this bench: 1 uA)",
        ),
        Figure(
            "input_diode",
            "Current through the protection diode of the converter input into its REF pin",
            _rest(nominal, "@d.xu30.dpu[id]"),
            "A",
        ),
        Figure(
            "highest",
            "Highest converter input above the reference, any case and any instant",
            highest,
            "V",
            high=_ABSOLUTE,
            source="ADS8860 datasheet, page 5: VREF + 0.3 V is the absolute maximum",
        ),
        Figure(
            "outside_operating_range",
            "Converter input above the end of its operating range, VREF + 0.1 V, at rest",
            _rest(nominal, "adc_in") - common.VREF - 0.1,
            "V",
        ),
    ]
    micro = time * 1e6
    shown = micro <= 200.0
    reverse = runs["reverse"]
    reverse_micro = reverse.real("time") * 1e6
    reverse_shown = reverse_micro <= 200.0
    graph = Graph(
        name="waveforms",
        title="Over-range: 0.6 V across the shunt from 20 us on",
        xlabel="Time (us)",
        panels=(
            Panel("Amplifier output (V)"),
            Panel("Limiter and converter (V)", marks=((common.VREF + _ABSOLUTE, "VREF + 0.3 V"),)),
            Panel("Current (mA)"),
        ),
        traces=(
            Trace(micro[shown], nominal.real("amp_raw")[shown], "amplifier output", 0),
            Trace(
                reverse_micro[reverse_shown],
                reverse.real("amp_raw")[reverse_shown],
                "amplifier output, reverse current",
                0,
                "--",
            ),
            Trace(micro[shown], nominal.real("lim")[shown], "limiter node", 1),
            Trace(micro[shown], nominal.real("vdrv")[shown], "driver rail", 1, "--"),
            Trace(micro[shown], nominal.real("adc_in")[shown], "converter input", 1),
            Trace(
                reverse_micro[reverse_shown],
                reverse.real("lim")[reverse_shown],
                "limiter node, reverse current",
                1,
                ":",
            ),
            Trace(micro[shown], nominal.real("@r125[i]")[shown] * 1e3, "through R125", 2),
            Trace(
                micro[shown],
                nominal.real("@dd22_2[id]")[shown] * 1e3,
                "into the driver rail",
                2,
                "--",
            ),
            Trace(micro[shown], nominal.real("@r129[i]")[shown] * 1e3, "buffer, through R129", 2),
        ),
        xmarks=((_START * 1e6, "over-range"),),
    )
    notes = (
        "The amplifier model goes to 1.4 V below its positive supply, the reading of a "
        "typical curve of its datasheet at 2 kohm; the table guarantees 1.6 V. With +12 V "
        "that is 10.6 V, more than the 10 V of section 4.5, so the clamp current here is "
        "the larger one.",
        "The driver model rests 2 mV below its supply when it is not loaded (assumption). "
        "The converter input in an over-range therefore is the driver rail itself, and "
        "the rail rises by what the clamp current takes off the 10 ohm of R129.",
        "The supply current of the two OPA365 follows the typical curve of the datasheet: "
        "4.2 mA at 2.7 V. The corner case takes 4.0 mA at 5 V for the driver, an "
        "assumption: the datasheet states no least value.",
        "The protection diodes of the converter input are an assumed junction; the current "
        "into the REF pin at 0.2 V of forward voltage is not a figure to rely on.",
        "During an over-range the limiter node stands a diode drop above the driver rail, "
        "which is the supply of the driver, and with a reverse current a diode drop below "
        "ground. The input of the driver behind R128 is then held by its own protection "
        "diode, which the amplifier model does not have; the current through R128 is "
        "calculated for a diode that holds the input 0.5 V beyond the supply.",
        "The reference, the rails and their impedance are ideal. Leakage of the diode pair "
        "is not modelled.",
    )
    return Outcome(tuple(figures), (graph,), notes)
