"""The driver rail: the buffer U28 with R129 and C88."""

from __future__ import annotations

import numpy as np

from benches import frontend
from benches.signal_chain import common
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
from circuit_sim.circuit import Circuit, PartModel
from circuit_sim.engine import RunResult

_PARTS = (
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
)
"""The rail buffer with its network, and the driver that the rail supplies."""

_VENDOR_LIBRARY = "vendor/ti-opa365-OPA365-PSpiceFiles__SCHEMATIC1__TransientAnalysis__OPA365.lib"
"""Model of the manufacturer for the OPA365, where it is present."""

_SIGNAL = 1.0
"""Voltage at the amplifier output node, which the driver follows."""

_SWEEP = "ac dec 80 1k 200meg"
"""Frequencies of the loop gain runs."""

_STEP_AT = 10e-6
"""Instant of the load step on the rail."""

_STEP_AMPS = 3e-3
"""Load step on the rail."""

_STOP = 60e-6
"""End of the step runs."""

_WITHOUT = 1e-4
"""Factor on R129 that stands for the buffer without it: 1 mohm."""

_LEAST_MARGIN = 45.0
"""Phase margin that this bench asks of a rail buffer; the specification states 54."""

_HELD_INPUT = 0.01
"""Factor on R126 that holds the non-inverting input of the buffer: 100 ohm."""

_MODEL_FIT = 0.25
"""Fit that this bench asks of an amplifier model in the three figures that decide
the loop: within 25 % of the datasheet."""

_BETWEEN_FARADS = 6e-12
"""Capacitance between the inputs of the amplifier (OPA365 datasheet, page 6)."""

_COMMON_FARADS = 2e-12
"""Capacitance from each input of the amplifier (OPA365 datasheet, page 6)."""

_OUTPUT_OHMS = 30.0
"""Open-loop output impedance of the amplifier at 1 MHz (OPA365 datasheet, page 7)."""

_MODEL_AT = 1e6
"""Frequency at which the three figures of the amplifier model are read."""


def _models(ctx: Context, vac: float = 0.0, iac: float = 0.0) -> dict[str, PartModel]:
    """The rail buffer with its probe sources, and in the vendor tier the model of its maker."""
    base = ctx.models.model_of(ctx.netlist.component("U28"))
    vendor = ctx.tier == VENDOR_TIER
    probe = PartModel(
        kind="subckt",
        name="SIGNAL_CHAIN_OPA365X_PROBE" if vendor else "SIGNAL_CHAIN_OPA365_PROBE",
        ports=base.ports,
        library="signal_chain.lib",
        origin="vendor" if vendor else "written here",
        params=f"vac={vac:g} iac={iac:g}",
    )
    models = {"U28": probe}
    if vendor:
        models["U29"] = PartModel(
            kind="subckt", name="OPA365", ports=base.ports, library=_VENDOR_LIBRARY, origin="vendor"
        )
    return models


def _circuit(
    ctx: Context, r129: float, c88: float, vac: float = 0.0, iac: float = 0.0, r126: float = 1.0
) -> Circuit:
    scales = {"R129": r129, "C88": c88, "R126": r126}
    return ctx.circuit(_PARTS, common.ALIASES, _models(ctx, vac, iac), scales)


def _libraries(ctx: Context) -> tuple[str, ...]:
    return (_VENDOR_LIBRARY,) if ctx.tier == VENDOR_TIER else ("opamps.lib",)


def _stimulus(load: str = "0") -> str:
    return "\n".join(
        [
            "* the amplifier output as a source; a load on the rail beside the driver",
            f"Vamp amp_raw 0 {_SIGNAL:g}",
            f"Iload vdrv 0 {load}",
        ]
    )


def _ac_deck(ctx: Context, r129: float, c88: float, r126: float, *, vac: float, iac: float) -> str:
    return ctx.deck(
        "Driver rail buffer: loop gain by double injection",
        _circuit(ctx, r129, c88, vac, iac, r126),
        frontend.rails(),
        _stimulus(),
        control=[_SWEEP],
        libraries=_libraries(ctx),
    )


def _step_deck(ctx: Context, r129: float) -> str:
    load = f"PWL(0 0 {_STEP_AT:g} 0 {_STEP_AT + 2e-8:g} {_STEP_AMPS:g})"
    return ctx.deck(
        "Driver rail buffer: load step on the rail",
        _circuit(ctx, r129, 1.0),
        frontend.rails(),
        _stimulus(load),
        control=["save vdrv buf_out buf_n buf_p adc_in", f"tran 2n {_STOP:g} 0 5n"],
        libraries=_libraries(ctx),
    )


def _model_deck(ctx: Context, *, into_output: bool) -> str:
    """The amplifier model of the tier alone, without feedback for small signals.

    An inductor closes the loop for the operating point, and a capacitor
    holds the inverting input for small signals. A source at the
    non-inverting input gives the input capacitances: its own current is
    that of both capacitances, the current that arrives at the held input
    that of the capacitance between the inputs. A current into the output
    gives the open-loop output impedance.
    """
    lines = [
        "* the amplifier model alone, on the supply of the buffer",
        "Vp vp 0 3.3",
        "Vmid mid 0 1.65",
        "X1 inp inn vp 0 out OPA365",
        "Lfb out inn 1meg",
        "Cfb inn held 1k",
        "Vheld held mid 0",
        f"Vin inp mid dc 0 ac {0 if into_output else 1}",
        f"Iout 0 out dc 0 ac {1 if into_output else 0}",
    ]
    what = "open-loop output impedance" if into_output else "input capacitances"
    return ctx.deck(
        f"Amplifier model of the rail buffer: {what}",
        "\n".join(lines),
        control=["ac dec 10 10k 10meg"],
        libraries=_libraries(ctx),
    )


def _model_figures(inputs: RunResult, output: RunResult) -> list[Figure]:
    """Input capacitances and output impedance of the amplifier model against its datasheet."""
    log_f = np.log10(inputs.real("frequency"))
    at = float(np.log10(_MODEL_AT))
    omega = 2.0 * np.pi * _MODEL_AT
    total = float(np.interp(at, log_f, np.abs(inputs.vector("vin#branch")))) / omega
    between = float(np.interp(at, log_f, np.abs(inputs.vector("vheld#branch")))) / omega
    ohms = float(np.interp(at, log_f, np.abs(output.vector("out"))))
    rows = (
        ("model_between", "capacitance between its inputs", between, "F", _BETWEEN_FARADS, 6),
        ("model_common", "capacitance from each input", total - between, "F", _COMMON_FARADS, 6),
        ("model_output", "open-loop output impedance at 1 MHz", ohms, "ohm", _OUTPUT_OHMS, 7),
    )
    return [
        Figure(
            key,
            f"Amplifier model of this run: {label}",
            value,
            unit,
            expected=expected,
            low=expected * (1.0 - _MODEL_FIT),
            high=expected * (1.0 + _MODEL_FIT),
            source=f"OPA365 datasheet, page {page}; 25 % is the fit this bench asks of a model",
        )
        for key, label, value, unit, expected, page in rows
    ]


def _loop(series: RunResult, shunt: RunResult) -> tuple[common.Vector, np.ndarray]:
    """The loop gain of the buffer from the two runs of a double injection.

    The amplifier inside the probe is the driving side of the injection
    point, the net of its output pin the receiving side. The voltage ratio
    is the returned voltage over the forward one; the current ratio the
    current that the amplifier delivers over the one that enters the net,
    which is the first plus the injected ampere.
    """
    frequency = series.real("frequency")
    voltage_ratio = -series.vector("xu28.amp") / series.vector("buf_out")
    delivered = shunt.vector("v.xu28.vser#branch")
    current_ratio = -delivered / (delivered + 1.0)
    loop = measure.loop_gain(
        np.asarray(voltage_ratio, dtype=np.complex128),
        np.asarray(current_ratio, dtype=np.complex128),
    )
    return frequency, loop


@bench(
    "signal_chain",
    "driver-rail",
    "The driver rail: output of the buffer U28, the rail, and the stability of its loop",
    "section 4.5 (driver rail D-73), section 16 (driver rail and its step response)",
)
def driver_rail(ctx: Context) -> Outcome:
    """The buffer U28 with its network supplies the converter driver U29.

    The circuit holds the buffer, its gain resistors, the 10 ohm of R129,
    the 100 nF of C88 and the driver with its filter; the amplifier output
    is a source at 1 V. An operating point gives the voltages and the
    supply current. The loop gain of the buffer is taken by double
    injection at its output, with the feedback closed: as drawn, with C88
    at 60 nF and at 110 nF (its value under bias and at its tolerance), with
    R126 at 100 ohm, which holds the non-inverting input, and with R129
    reduced to 1 mohm, which stands for the buffer without it.
    A load step of 3 mA on the rail is then run with and without R129.
    Two more runs take the amplifier model alone and read its input
    capacitances and its open-loop output impedance against the datasheet:
    these three figures decide the loop, and the two tiers differ in them.
    """
    rest = ctx.run(
        "rest",
        ctx.deck(
            "Driver rail buffer: operating point",
            _circuit(ctx, 1.0, 1.0),
            frontend.rails(),
            _stimulus(),
            control=["save all @r129[i]", "op"],
            libraries=_libraries(ctx),
        ),
    )
    cases = {
        "drawn": (1.0, 1.0, 1.0),
        "c88-60n": (1.0, 0.6, 1.0),
        "c88-110n": (1.0, 1.1, 1.0),
        "r126-100r": (1.0, 1.0, _HELD_INPUT),
        "without": (_WITHOUT, 1.0, 1.0),
    }
    decks: dict[str, str] = {}
    for name, (r129, c88, r126) in cases.items():
        decks[f"series-{name}"] = _ac_deck(ctx, r129, c88, r126, vac=1.0, iac=0.0)
        decks[f"shunt-{name}"] = _ac_deck(ctx, r129, c88, r126, vac=0.0, iac=1.0)
    ctx.run("loop-series", decks["series-drawn"])
    runs = ctx.run_many(decks)
    step = ctx.run("step", _step_deck(ctx, 1.0))
    step_without = ctx.run("step-without", _step_deck(ctx, _WITHOUT))
    model_inputs = ctx.run("model-inputs", _model_deck(ctx, into_output=False), keep=False)
    model_output = ctx.run("model-output", _model_deck(ctx, into_output=True), keep=False)

    buffer_out = float(rest.real("buf_out")[0])
    rail = float(rest.real("vdrv")[0])
    supply = -float(rest.real("vp3v3a#branch")[0])
    through = float(rest.real("@r129[i]")[0])
    figures = [
        near(
            "buffer_output",
            "Output of the buffer U28",
            buffer_out,
            "V",
            2.727,
            0.003,
            "section 4.5: 1.091 x VREF, 2.73 V",
        ),
        Figure(
            "rail",
            "Driver rail at the test point TP42",
            rail,
            "V",
            expected=2.68,
            low=2.67,
            high=2.69,
            source="section 4.5: about 2.68 V after the drop in the 10 ohm",
        ),
        Figure(
            "driver_current",
            "Current through R129, the supply current of the driver",
            through,
            "A",
        ),
        Figure(
            "supply_current",
            "Current that buffer and driver take from 3V3_A together",
            supply,
            "A",
        ),
        Figure(
            "buffer_adds",
            "Of which the buffer adds (its own supply current and its gain resistors)",
            supply - through,
            "A",
            expected=4.8e-3,
            high=5.3e-3,
            source="section 4.5: 4.8 mA, 5.3 mA at the most",
        ),
    ]
    traces: list[Trace] = []
    labels = {
        "drawn": "as drawn, 10 ohm and 100 nF",
        "c88-60n": "C88 at 60 nF",
        "c88-110n": "C88 at 110 nF",
        "r126-100r": "R126 at 100 ohm in place of 10 kohm",
        "without": "without R129",
    }
    for name in cases:
        frequency, loop = _loop(runs[f"series-{name}"], runs[f"shunt-{name}"])
        crossover, margin = measure.stability_margins(frequency, loop)
        key = name.replace("-", "_")
        if name == "without":
            figures += [
                Figure(
                    f"margin_{key}",
                    "Phase margin of the loop without R129",
                    margin,
                    "deg",
                    high=0.0,
                    source="section 4.5: without the 10 ohm the loop is unstable",
                ),
                Figure(f"crossover_{key}", "Crossover of the loop without R129", crossover, "Hz"),
            ]
        else:
            figures += [
                Figure(
                    f"margin_{key}",
                    f"Phase margin of the loop, {labels[name]}",
                    margin,
                    "deg",
                    expected=54.0 if name == "drawn" else None,
                    low=_LEAST_MARGIN,
                    source="section 4.5: 54 degrees with the 10 ohm; 45 degrees is the least "
                    "this bench accepts",
                ),
                Figure(
                    f"crossover_{key}", f"Crossover of the loop, {labels[name]}", crossover, "Hz"
                ),
            ]
        if name in ("drawn", "r126-100r", "without"):
            traces += [
                Trace(frequency, measure.decibels(loop), labels[name], 0),
                Trace(frequency, measure.phase_degrees(loop) + 180.0, labels[name], 1),
            ]
    time = step.real("time")
    rail_step = step.real("vdrv")
    final = measure.mean(time, rail_step, _STOP - 5e-6, _STOP - 1e-6)
    lowest = measure.extremes(time, rail_step, _STEP_AT, _STOP)[0]
    time_without = step_without.real("time")
    rail_without = step_without.real("vdrv")
    figures += [
        Figure(
            "step_drop",
            "Load step of 3 mA: the rail falls by",
            rail - final,
            "V",
            expected=_STEP_AMPS * 10.0,
            source="3 mA in the 10 ohm of R129, calculated here",
        ),
        Figure(
            "step_undershoot",
            "Load step of 3 mA: the rail dips below its new level by",
            final - lowest,
            "V",
        ),
        Figure(
            "step_settles",
            "Load step of 3 mA: the rail is within 1 mV of its new level after",
            measure.settling_time(time, rail_step, final, 1e-3, _STEP_AT),
            "s",
        ),
        Figure(
            "ringing_without",
            "Without R129: swing of the rail in the last 10 us of the run",
            measure.peak_to_peak(time_without, rail_without, _STOP - 10e-6, _STOP),
            "V",
        ),
    ]
    figures += _model_figures(model_inputs, model_output)
    loop_graph = Graph(
        name="loop",
        title="Driver rail buffer: loop gain by double injection",
        xlabel="Frequency (Hz)",
        panels=(
            Panel("Loop gain (dB)", marks=((0.0, "0 dB"),)),
            Panel("Phase above -180 degrees (degrees)", marks=((0.0, "no margin"),)),
        ),
        traces=tuple(traces),
        logx=True,
    )
    step_graph = Graph(
        name="step",
        title="Driver rail: load step of 3 mA at 10 us",
        xlabel="Time (us)",
        panels=(Panel("Rail with R129 as drawn (V)"), Panel("Rail without R129 (V)")),
        traces=(
            Trace(time * 1e6, rail_step, "rail at TP42", 0),
            Trace(time * 1e6, step.real("buf_out"), "buffer output", 0, "--"),
            Trace(time_without * 1e6, rail_without, "rail", 1),
        ),
        xmarks=((_STEP_AT * 1e6, "load step"),),
    )
    notes = (
        "The amplifier model has the gain-bandwidth product, the open-loop output impedance "
        "at 1 MHz (30 ohm) and the input capacitances of its datasheet, 6 pF between the "
        "inputs and 2 pF from each input; its second pole is fitted to the phase curve of "
        "the datasheet.",
        "The margin as drawn is lower than the 54 degrees of the specification because of "
        "R126: with 10 kohm at the non-inverting input and no capacitor there, the 6 pF "
        "between the inputs let that input follow the inverting one, which lowers the "
        "crossover and costs about 36 degrees there. With R126 at 100 ohm the same model "
        "has the margin of the row above.",
        "The model of the manufacturer, run in the vendor tier, shows no such effect and "
        "gives 69 degrees as drawn. The last three figures say why: that model has about "
        "6 pF from each input and less than 1 pF between the inputs, the two values of the "
        "datasheet the other way round, and 56 ohm of output impedance where the "
        "datasheet states 30 ohm. In the figures that decide this loop it is not the part "
        "of the datasheet, so its margin does not speak against the lower one. A capacitor "
        "from the non-inverting input to ground would make the loop independent of the "
        "question.",
        "C88 and the other capacitors are ideal: no series resistance, no inductance. The "
        "reference and 3V3_A are ideal sources.",
        "The supply current of the two amplifiers follows the typical curve of the "
        "datasheet (4.3 mA at 3.3 V, 4.2 mA at 2.7 V), not the 4.6 mA of its table, which "
        "holds at 5 V. The figure that the buffer adds is therefore below the 4.8 mA of "
        "the specification.",
        "The amplifier U27, its pedestal buffer and the multiplexer are not in this "
        "circuit: the amplifier output is an ideal source.",
    )
    return Outcome(tuple(figures), (loop_graph, step_graph), notes)
