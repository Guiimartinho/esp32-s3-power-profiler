"""The three loops of the source: linear regulator, pre-regulator, tracking amplifier."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.source_meter import common
from circuit_sim import measure
from circuit_sim.bench import VENDOR_TIER, Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_SWEEP = "ac dec 50 10 20meg"
"""Frequencies of the small-signal runs of the two regulators."""

_AMPLIFIER_SWEEP = "ac dec 50 10 1g"
"""Frequencies of the runs of the amplifier, whose loop crosses above 10 MHz."""

_AMPLIFIER = ("U19", "R63", "R64", "R65", "R66", "R67", "R68", "C52", "C55", "D13", "C51")
"""The difference amplifier alone."""

_VENDOR_AMPLIFIER = "vendor/ti-opa365-OPA365-PSpiceFiles__SCHEMATIC1__TransientAnalysis__OPA365.lib"
"""File of the model of the manufacturer of the OPA365 (not in the repository)."""

_IDLE = 10e-6
"""Current of a device at rest."""

_SPEEDS = (0.5, 2.0)
"""Factors on the unity-gain frequency of the error amplifier of the regulator
model, for the figures that show how far the margin rests on that assumption."""

_REGULATOR_BAND = 150e3
"""Unity-gain frequency of the error amplifier in the regulator model."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One state of the source in which a loop is measured.

    Attributes:
        volts: Set-point.
        amps: Current of the device.
        index: Range whose shunt stands in the path.
        farads: Capacitance beside the device.
    """

    volts: float
    amps: float
    index: int
    farads: float

    @property
    def tag(self) -> str:
        load = "idle" if self.amps <= _IDLE else f"{self.amps * 1e3:g}ma"
        return f"{self.volts:g}v_{load}_r{self.index}_{self.farads * 1e6:g}uf".replace(".", "p")

    @property
    def text(self) -> str:
        load = "10 uA" if self.amps <= _IDLE else f"{self.amps * 1e3:g} mA"
        beside = f"{self.farads * 1e6:g} uF" if self.farads else "no capacitor"
        return f"{self.volts:g} V, {load}, range {self.index}, {beside} at the device"


def _cases(volts: float, curve: float) -> tuple[_Case, ...]:
    return (
        _Case(volts, _IDLE, 0, 0.0),
        _Case(volts, _IDLE, 3, 100e-6),
        _Case(volts, 0.1, 2, 10e-6),
        _Case(volts, 0.1, 3, 100e-6),
        _Case(volts, curve, 3, 1e-6),
        _Case(volts, curve, 3, 100e-6),
    )


_CASES = (*_cases(0.8, 1.0), *_cases(5.0, 0.6))
"""States of the regulator loop: idle, 100 mA and the current of the R-08 curve."""

_CONVERTER_CASES = (
    _Case(0.8, _IDLE, 0, 0.0),
    _Case(0.8, 1.0, 3, 10e-6),
    _Case(3.3, 0.83, 3, 10e-6),
    _Case(5.0, _IDLE, 0, 0.0),
    _Case(5.0, 0.6, 3, 10e-6),
)
"""States of the pre-regulator loop: both ends of the output range, idle and loaded."""


def _settle(ctx: Context, case: _Case, overrides: dict[str, PartModel] | None = None) -> str:
    return common.settle_deck(
        ctx,
        f"State for a loop run: {case.text}",
        case.volts,
        amps=case.amps,
        index=case.index,
        farads=case.farads,
        overrides=overrides,
    )


def _probe_deck(
    ctx: Context, case: _Case, settled: RunResult, overrides: dict[str, PartModel]
) -> str:
    """The same state as an operating point, with one probe source switched on."""
    models = {common.DAC: common.part(ctx, common.DAC, code=common.code_of(case.volts))}
    models.update(overrides)
    circuit = common.source(ctx, case.volts, overrides=models)
    return ctx.deck(
        f"Loop gain at {case.text}",
        circuit,
        common.rails(),
        common.controller(),
        common.dut(case.index, case.amps, case.farads),
        common.nodeset_from(settled),
        control=[_SWEEP],
    )


def _regulator_loop(run: RunResult) -> tuple[np.ndarray, np.ndarray]:
    sense = run.vector(f"x{common.REGULATOR.lower()}.sns")
    return run.real("frequency"), np.asarray(-run.vector("ldo_out") / sense, dtype=np.complex128)


def _converter_loop(run: RunResult) -> tuple[np.ndarray, np.ndarray]:
    sense = run.vector(f"x{common.CONVERTER.lower()}.fbs")
    return run.real("frequency"), np.asarray(-run.vector("pre_fb") / sense, dtype=np.complex128)


def _amplifier_model(ctx: Context, vac: float, iac: float) -> PartModel:
    """U19 behind the probe sources, with the amplifier model of the tier."""
    vendor = ctx.tier == VENDOR_TIER
    return PartModel(
        kind="subckt",
        name="SOURCE_METER_OPA365_PROBE",
        ports=("3", "4", "5", "2", "1"),
        library="source_meter.lib",
        origin="vendor" if vendor else "written here",
        params=f"vac={vac:g} iac={iac:g}",
    )


def _amplifier_deck(ctx: Context, vac: float, iac: float, feedback: bool = True) -> str:
    """The difference amplifier alone, its inputs held, one probe source on."""
    refs = _AMPLIFIER if feedback else tuple(ref for ref in _AMPLIFIER if ref != "C52")
    circuit = common.source(
        ctx, 3.3, refs=refs, overrides={common.TRACKER: _amplifier_model(ctx, vac, iac)}
    )
    stimulus = "\n".join(
        [
            "* the inputs of the difference amplifier held by sources; the feedback pin",
            "* of the converter takes no current",
            "Vpre v_pre 0 3.827",
            "Vldo ldo_out 0 3.3",
            f"Vref vref 0 {common.REFERENCE:g}",
            f"Vp3v3a p3v3_a 0 {common.RAIL_3V3:g}",
            "Rfb pre_fb 0 1e10",
        ]
    )
    vendor = ctx.tier == VENDOR_TIER
    return ctx.deck(
        "Loop of the tracking amplifier U19",
        circuit,
        stimulus,
        control=[_AMPLIFIER_SWEEP],
        options=("rshunt=1e13",) if vendor else (),
        libraries=(_VENDOR_AMPLIFIER,) if vendor else ("opamps.lib",),
    )


def _amplifier_loop(series: RunResult, shunt: RunResult) -> tuple[np.ndarray, np.ndarray]:
    """The loop gain of U19 from the two runs of a double injection at its output."""
    inner = f"x{common.TRACKER.lower()}"
    voltage_ratio = -series.vector(f"{inner}.amp") / series.vector("pre_fb")
    delivered = shunt.vector(f"v.{inner}.vser#branch")
    current_ratio = -delivered / (delivered + 1.0)
    loop = measure.loop_gain(
        np.asarray(voltage_ratio, dtype=np.complex128),
        np.asarray(current_ratio, dtype=np.complex128),
    )
    return series.real("frequency"), loop


def _amplifier_margin(ctx: Context, feedback: bool) -> tuple[float, float, np.ndarray, np.ndarray]:
    tag = "c52" if feedback else "no-c52"
    series = ctx.run(
        f"amplifier-series-{tag}", _amplifier_deck(ctx, 1.0, 0.0, feedback), keep=feedback
    )
    shunt = ctx.run(f"amplifier-shunt-{tag}", _amplifier_deck(ctx, 0.0, 1.0, feedback), keep=False)
    frequency, loop = _amplifier_loop(series, shunt)
    crossover, margin = measure.stability_margins(frequency, loop)
    return crossover, margin, frequency, loop


@bench(
    "source_meter",
    "loop",
    "Loop gain and phase margin: linear regulator, pre-regulator, tracking amplifier",
    "section 4.2 (loop of the pre-regulator, C52), section 16 (open checks of U16 and U18)",
)
def loop(ctx: Context) -> Outcome:
    """Each loop is measured closed, with a source inside the model or at the output pin.

    The source is first powered up into a state and brought to rest; the
    operating point of the small-signal run starts from the end of that
    run. The loop of the linear regulator is read at its sense input with
    the output network of the netlist: C53 and C54, the capacitors of the
    supply node, the path to the device and the capacitor beside it. The
    loop of the pre-regulator is read at its feedback pin, with the
    difference amplifier in the path. The loop of the amplifier U19 is
    read by a double injection at its output, with and without C52. With
    the model of the manufacturer only the amplifier is measured.
    """
    figures: list[Figure] = []
    traces: list[Trace] = []
    amplifier_traces: list[Trace] = []
    with_c52 = _amplifier_margin(ctx, True)
    without = _amplifier_margin(ctx, False)
    figures += [
        Figure(
            "amplifier_margin",
            "Tracking amplifier U19 with C52: phase margin",
            with_c52[1],
            "deg",
            expected=75.0,
            low=60.0,
            source="section 4.2: 73 to 77 degrees with the model of the manufacturer; the "
            "lower limit of 60 degrees is the one of this bench",
        ),
        Figure(
            "amplifier_crossover",
            "Tracking amplifier U19 with C52: crossover",
            with_c52[0],
            "Hz",
        ),
        Figure(
            "amplifier_margin_without",
            "Tracking amplifier U19 without C52: phase margin",
            without[1],
            "deg",
        ),
    ]
    for label, (_, _, frequency, gain) in (("with C52", with_c52), ("without C52", without)):
        amplifier_traces += [
            Trace(frequency, measure.decibels(gain), label, 0),
            Trace(frequency, measure.phase_degrees(gain), label, 1),
        ]
    amplifier_graph = Graph(
        name="amplifier",
        title="Loop gain of the tracking amplifier U19",
        xlabel="Frequency (Hz)",
        panels=(Panel("Magnitude (dB)", marks=((0.0, "0 dB"),)), Panel("Phase (degrees)")),
        traces=tuple(amplifier_traces),
        logx=True,
    )
    if ctx.tier == VENDOR_TIER:
        vendor_notes = (
            "The amplifier is the model of its manufacturer; the regulator and the "
            "converter have no model of a manufacturer that gives a loop gain, so this "
            "tier holds the amplifier alone.",
        )
        return Outcome(tuple(figures), (amplifier_graph,), vendor_notes)

    settled = ctx.run_many(
        {f"state-{case.tag}".replace("_", "-"): _settle(ctx, case) for case in _CASES}
        | {f"cstate-{case.tag}".replace("_", "-"): _settle(ctx, case) for case in _CONVERTER_CASES}
    )
    probe = {common.REGULATOR: common.part(ctx, common.REGULATOR, vac=1)}
    decks = {
        f"loop-{case.tag}".replace("_", "-"): _probe_deck(
            ctx, case, settled[f"state-{case.tag}".replace("_", "-")], probe
        )
        for case in _CASES
    }
    idle = _CASES[0]
    for factor in _SPEEDS:
        decks[f"speed-{factor:g}"] = _probe_deck(
            ctx,
            idle,
            settled[f"state-{idle.tag}".replace("_", "-")],
            {
                common.REGULATOR: common.part(
                    ctx, common.REGULATOR, vac=1, fu=_REGULATOR_BAND * factor
                )
            },
        )
    converter_probe = {common.CONVERTER: common.part(ctx, common.CONVERTER, vac=1)}
    for case in _CONVERTER_CASES:
        decks[f"converter-{case.tag}".replace("_", "-")] = _probe_deck(
            ctx, case, settled[f"cstate-{case.tag}".replace("_", "-")], converter_probe
        )
    kept = {
        f"loop-{idle.tag}".replace("_", "-"),
        f"converter-{_CONVERTER_CASES[-1].tag}".replace("_", "-"),
    }
    runs = {name: ctx.run(name, decks[name]) for name in kept}
    runs.update(ctx.run_many({name: deck for name, deck in decks.items() if name not in kept}))

    for case in _CASES:
        frequency, gain = _regulator_loop(runs[f"loop-{case.tag}".replace("_", "-")])
        crossover, margin = measure.stability_margins(frequency, gain)
        figures += [
            Figure(f"margin_{case.tag}", f"Regulator, {case.text}: phase margin", margin, "deg"),
            Figure(f"crossover_{case.tag}", f"Regulator, {case.text}: crossover", crossover, "Hz"),
        ]
        if case.volts == 0.8:
            traces += [
                Trace(frequency, measure.decibels(gain), case.text, 0),
                Trace(frequency, measure.phase_degrees(gain), case.text, 1),
            ]
    for factor in _SPEEDS:
        frequency, gain = _regulator_loop(runs[f"speed-{factor:g}"])
        figures.append(
            Figure(
                f"margin_speed_{factor:g}".replace(".", "p"),
                f"Regulator, {idle.text}, error amplifier of the model {factor:g} times as "
                "fast: phase margin",
                measure.stability_margins(frequency, gain)[1],
                "deg",
            )
        )
    converter_traces: list[Trace] = []
    for case in _CONVERTER_CASES:
        frequency, gain = _converter_loop(runs[f"converter-{case.tag}".replace("_", "-")])
        crossover, margin = measure.stability_margins(frequency, gain)
        figures += [
            Figure(
                f"converter_margin_{case.tag}",
                f"Pre-regulator, {case.text}: phase margin",
                margin,
                "deg",
                expected=55.0,
                low=55.0,
                source="section 4.2: 55 degrees or more, from a behavioral model whose "
                "compensation is an assumption",
            ),
            Figure(
                f"converter_crossover_{case.tag}",
                f"Pre-regulator, {case.text}: crossover",
                crossover,
                "Hz",
            ),
        ]
        converter_traces += [
            Trace(frequency, measure.decibels(gain), case.text, 0),
            Trace(frequency, measure.phase_degrees(gain), case.text, 1),
        ]
    graphs = (
        Graph(
            name="regulator",
            title="Loop gain of the linear regulator model at 0.8 V, by load and capacitor",
            xlabel="Frequency (Hz)",
            panels=(Panel("Magnitude (dB)", marks=((0.0, "0 dB"),)), Panel("Phase (degrees)")),
            traces=tuple(traces),
            logx=True,
        ),
        Graph(
            name="converter",
            title="Loop gain of the pre-regulator model with the difference amplifier",
            xlabel="Frequency (Hz)",
            panels=(Panel("Magnitude (dB)", marks=((0.0, "0 dB"),)), Panel("Phase (degrees)")),
            traces=tuple(converter_traces),
            logx=True,
        ),
        amplifier_graph,
    )
    notes = (
        "The loop of the regulator model is a fit to three load steps and one response "
        "curve of the datasheet, which shows no loop gain, no load below 50 mA and no "
        "capacitor above 10 uF. Its phase margin carries no limit here: at idle, where "
        "only the minimum load R69 flows, it is an extrapolation. The two runs with a "
        "slower and a faster error amplifier show how far the figure moves with one "
        "assumption of the model.",
        "The loop of the pre-regulator model is fitted to a load step of the transient "
        "model of the manufacturer in the application circuit of the datasheet; its "
        "current loop of 100 kHz is an assumption. The model is averaged: it holds no "
        "effect of the switching frequency on the phase. The specification names a "
        "risk prototype for this loop, and this bench does not replace it.",
        "The regulator loop is measured at the sense input inside the model and the "
        "pre-regulator loop at its feedback pin; both points take no current, so one "
        "injection is exact there. The amplifier loop is a double injection at its "
        "output pin.",
        "The path to the device is three resistors for one range; the capacitor beside "
        "the device is a ceramic part with 5 mohm. The capacitors of the netlist have "
        "the capacitance of their bias curve at the state of each run.",
    )
    return Outcome(tuple(figures), graphs, notes)
