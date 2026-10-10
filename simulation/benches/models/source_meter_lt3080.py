"""The LT3080 model of the source meter against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from benches.source_meter import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.circuit import Circuit
from circuit_sim.engine import RunResult

_REF = common.REGULATOR

_DOCUMENT = "Analog Devices LT3080 Rev. E"
"""The datasheet the figures are taken from."""

_OUT = 1.5
"""Output voltage of the test circuits of the datasheet."""

_LOADS = (1e-3, 10e-3, 0.1, 0.2, 0.6, 1.0, 1.1)
"""Load currents of the static run."""

_DROP_AMPS = (0.1, 0.5, 1.0, 1.1)
"""Load currents at which the dropout is read."""

_DROP_CURVE = {0.1: 0.070, 0.5: 0.165, 1.1: 0.318}
"""Dropout at the IN pin at 25 C, read from the curves G09 and G10 of pages 5 and 6."""

_LOST = 10e-3
"""Fall of the output at which a supply pin counts as in dropout (this bench)."""

_FIT = 0.30
"""Share by which a step response of the model may differ from the curve of the
datasheet: the fit this project asks of the loop of this model."""

_STEPS = (
    ("g16", "0.1 A to 1.1 A with 10 uF", 0.1, 1.1, 10e-6, 12.5e-6, -0.095, 0.088),
    ("g15-2u2", "50 mA to 250 mA with 2.2 uF", 0.05, 0.25, 2.2e-6, 14e-6, -0.048, 0.038),
    ("g15-10u", "50 mA to 250 mA with 10 uF", 0.05, 0.25, 10e-6, 14e-6, -0.012, 0.008),
)
"""Load steps of page 6: name, text, the two currents, the output capacitor,
the length of the pulse, and the two deviations read from the curve."""

_STEP_START = 5e-6
_STEP_EDGE = 100e-9
"""Start and edge of the load pulse; the datasheet does not state the edge."""

_MARGIN_POINTS = ((4e-3, 22e-6), (0.1, 2.2e-6), (0.1, 22e-6), (1.1, 2.2e-6), (1.1, 22e-6))
"""Load current and output capacitor of the phase margin figures."""

_ESR = 5e-3
"""Series resistance of a ceramic output capacitor (assumption)."""


def _part(ctx: Context, **params: float | str) -> Circuit:
    """The regulator alone, its four pins on short node names."""
    found = ctx.netlist.component(_REF)
    aliases = {
        found.net_of("7"): "in",
        found.net_of("5"): "vctl",
        found.net_of("4"): "set",
        found.net_of("1"): "out",
    }
    overrides = {_REF: common.part(ctx, _REF, **params)} if params else None
    return ctx.circuit([_REF], aliases, overrides)


def _static_deck(ctx: Context) -> str:
    """Offset and control current over the load, as page 7 measures them."""
    stimulus = "\n".join(
        [
            "* IN 1 V and VCONTROL 2 V above the output, SET held by a source",
            f"Vin in 0 {_OUT + 1.0:g}",
            f"Vctl vctl 0 {_OUT + 2.0:g}",
            f"Vset set 0 {_OUT:g}",
            "Iload out 0 1m",
        ]
    )
    points = " ".join(f"{amps:g}" for amps in _LOADS)
    control = [f"foreach amps {points}", "  alter Iload dc = $amps", "  op", "end"]
    return ctx.deck("LT3080: offset and control current", _part(ctx), stimulus, control=control)


def _set_deck(ctx: Context) -> str:
    """The SET current into a resistor, and the residual output without load."""
    stimulus = "\n".join(
        [
            "* SET current into 150 kohm; then SET at 0 V and 1 kohm as the only load",
            "Vin in 0 5",
            "Vctl vctl 0 5",
            "Rset set 0 150k",
            "Rtest out 0 1k",
        ]
    )
    control = ["op", "alter Rset = 1m", "op", "alter Rtest = 2k", "op"]
    return ctx.deck(
        "LT3080: SET current and residual output", _part(ctx), stimulus, control=control
    )


def _dropout_deck(ctx: Context, pin: str, **params: float | str) -> str:
    """One supply pin swept down at each load current, the other held high."""
    held = "Vctl vctl 0 5" if pin == "in" else "Vin in 0 3"
    swept = "Vin in 0 2.3" if pin == "in" else "Vctl vctl 0 3.5"
    stimulus = "\n".join(
        [
            "* one supply pin is swept down until the output falls",
            held,
            swept,
            f"Vset set 0 {_OUT:g}",
            "* a resistor as the load, so that the output falls gently in dropout",
            "Rload out 0 15",
        ]
    )
    sweep = "dc Vin 2.3 1.5 -0.002" if pin == "in" else "dc Vctl 3.5 2.0 -0.002"
    control: list[str] = []
    for amps in _DROP_AMPS:
        control += [f"alter Rload = {_OUT / amps:g}", sweep]
    return ctx.deck(
        f"LT3080: dropout at the {pin} pin", _part(ctx, **params), stimulus, control=control
    )


def _limit_deck(ctx: Context, **params: float | str) -> str:
    """The current limit in the test condition of page 4."""
    stimulus = "\n".join(
        [
            "* 5 V on both supply pins, SET at 0 V, the output held at -0.1 V",
            "Vin in 0 5",
            "Vctl vctl 0 5",
            "Vset set 0 0",
            "Vout out 0 -0.1",
        ]
    )
    return ctx.deck("LT3080: current limit", _part(ctx, **params), stimulus, control=["op"])


def _step_deck(ctx: Context, low: float, high: float, farads: float, width: float) -> str:
    """A load step in the circuit of page 6: 3 V on both pins, 1.5 V out."""
    stimulus = "\n".join(
        [
            "* 3 V on IN and VCONTROL, SET by 150 kohm with 0.1 uF, ceramic output capacitor",
            "Vin in 0 3",
            "Rjoin in vctl 1m",
            "Rset set 0 150k",
            "Cset set 0 0.1u",
            f"Cout out out_c {farads:g}",
            f"Resr out_c 0 {_ESR:g}",
            f"Iload out 0 PULSE({low:g} {high:g} {_STEP_START:g} {_STEP_EDGE:g} {_STEP_EDGE:g} "
            f"{width:g} 1)",
        ]
    )
    return ctx.deck("LT3080: load step", _part(ctx), stimulus, control=["tran 10n 50u 0 10n"])


def _response_deck(ctx: Context, amps: float, farads: float, probe: bool) -> str:
    """Small-signal run: from SET to OUT, or around the loop with the probe source."""
    stimulus = "\n".join(
        [
            "* the loop is opened nowhere: a source in series with the sense input of",
            "* the error amplifier (inside the model) or on the SET pin carries the signal",
            "Vin in 0 3",
            "Rjoin in vctl 1m",
            f"Vset set 0 dc {_OUT:g} ac {0 if probe else 1}",
            f"Cout out out_c {farads:g}",
            f"Resr out_c 0 {_ESR:g}",
            f"Iload out 0 {amps:g}",
        ]
    )
    circuit = _part(ctx, vac=1) if probe else _part(ctx)
    return ctx.deck(
        "LT3080: small-signal response", circuit, stimulus, control=["ac dec 60 10 20meg"]
    )


def _noise_deck(ctx: Context) -> str:
    """Output noise in the condition of page 4: 1.1 A, 10 uF, 0.1 uF on SET."""
    inner = f"x{_REF.lower()}"
    stimulus = "\n".join(
        [
            "* SET by 100 kohm with 0.1 uF, 1.1 A of load",
            "Vin in 0 dc 3 ac 1",
            "Rjoin in vctl 1m",
            "Rset set 0 100k",
            "Cset set 0 0.1u",
            "Cout out out_c 10u",
            f"Resr out_c 0 {_ESR:g}",
            "Iload out 0 1.1",
            "* start values: the search begins near the state with 1 V at the output",
            f".nodeset v(out)=1 v(set)=1 v({inner}.x)=1.95 v({inner}.cmd)=1.95 v({inner}.b)=1.9",
        ]
    )
    return ctx.deck(
        "LT3080: output noise", _part(ctx), stimulus, control=["noise v(out) Vin dec 30 10 100k"]
    )


def _dropout(run: RunResult, index: int, supply: str) -> float:
    """The least voltage from a supply pin to the output that still regulates."""
    plot = f"dc{index + 1}"
    volts = run.real("v-sweep", plot)
    out = run.real("out", plot)
    held = np.flatnonzero(out >= _OUT - _LOST)
    del supply
    return float(volts[held[-1]] - out[held[-1]])


def _loop(run: RunResult) -> tuple[np.ndarray, np.ndarray]:
    """Frequency and loop gain of a run with the probe source."""
    sense = run.vector(f"x{_REF.lower()}.sns")
    return run.real("frequency"), np.asarray(-run.vector("out") / sense, dtype=np.complex128)


@bench(
    "models",
    "source-meter-lt3080",
    "LT3080 model of the source meter against its datasheet",
    "the model of the linear regulator U18",
)
def lt3080(ctx: Context) -> Outcome:
    """The regulator U18 of the schematic is put in the test circuits of its datasheet.

    Static runs give the SET current, the offset over the load, the current
    of the VCONTROL pin, the dropout of both supply pins, the current limit
    and the output without load. Three load steps and the response from SET
    to OUT are the curves that the loop of the model was fitted to; the
    phase margin that follows from that fit is reported without a limit,
    because the datasheet states none.
    """
    figures: list[Figure] = []

    static = ctx.run("static", _static_deck(ctx))
    offsets = np.array([static.real("out", f"op{i + 1}")[0] - _OUT for i in range(len(_LOADS))])
    control = np.array([-static.real("vctl#branch", f"op{i + 1}")[0] for i in range(len(_LOADS))])
    by_load = dict(zip(_LOADS, range(len(_LOADS)), strict=True))
    regulation = float(offsets[by_load[1e-3]] - offsets[by_load[1.1]])
    sets = ctx.run("set", _set_deck(ctx))
    set_amps = float(sets.real("set", "op1")[0]) / 150e3
    residual = float(sets.real("out", "op2")[0])
    figures += [
        near("set_current", "SET current", set_amps, "A", 10e-6, 0.01, f"{_DOCUMENT}, page 4"),
        Figure(
            "load_regulation",
            "Fall of the output from 1 mA to 1.1 A",
            regulation,
            "V",
            expected=0.6e-3,
            high=1.3e-3,
            source=f"{_DOCUMENT}, page 4: 0.6 mV typical, 1.3 mV at the most",
        ),
        Figure(
            "control_100ma",
            "Current of the VCONTROL pin at 100 mA",
            float(control[by_load[0.1]]),
            "A",
            expected=4e-3,
            low=2.8e-3,
            high=6e-3,
            source=f"{_DOCUMENT}, page 4: 4 mA typical, 6 mA at the most",
        ),
        Figure(
            "control_1a1",
            "Current of the VCONTROL pin at 1.1 A",
            float(control[by_load[1.1]]),
            "A",
            expected=17e-3,
            low=14e-3,
            high=30e-3,
            source=f"{_DOCUMENT}, page 4: 17 mA typical, 30 mA at the most",
        ),
        Figure(
            "residual_1k",
            "Output with SET at 0 V and 1 kohm as the only load, 5 V in",
            residual,
            "V",
            expected=0.3,
            low=0.2,
            high=0.5,
            source=f"{_DOCUMENT}, page 7, curve G21; page 4: 0.5 mA at the most at 10 V",
        ),
    ]

    typical = ctx.run("dropout-in", _dropout_deck(ctx, "in"))
    limit = ctx.run("dropout-in-limit", _dropout_deck(ctx, "in", **common.LIMIT_DROPOUT))
    controlled = ctx.run("dropout-vcontrol", _dropout_deck(ctx, "vctl"))
    drop = {amps: _dropout(typical, i, "in") for i, amps in enumerate(_DROP_AMPS)}
    drop_limit = {amps: _dropout(limit, i, "in") for i, amps in enumerate(_DROP_AMPS)}
    drop_control = {amps: _dropout(controlled, i, "vctl") for i, amps in enumerate(_DROP_AMPS)}
    figures += [
        Figure(
            "dropout_100ma",
            "Dropout at the IN pin at 100 mA",
            drop[0.1],
            "V",
            expected=0.1,
            low=0.06,
            high=0.2,
            source=f"{_DOCUMENT}, page 4: 100 mV typical, 200 mV at the most; curve G10: 70 mV",
        ),
        Figure(
            "dropout_1a1",
            "Dropout at the IN pin at 1.1 A",
            drop[1.1],
            "V",
            expected=0.35,
            low=0.30,
            high=0.40,
            source=f"{_DOCUMENT}, page 4: 350 mV typical; curve G09: 318 mV",
        ),
        near(
            "dropout_limit_100ma",
            "Dropout at 100 mA with the parameters of the guaranteed limits",
            drop_limit[0.1],
            "V",
            0.2,
            0.05,
            f"{_DOCUMENT}, page 4: 200 mV at the most",
        ),
        near(
            "dropout_limit_1a1",
            "Dropout at 1.1 A with the parameters of the guaranteed limits",
            drop_limit[1.1],
            "V",
            0.5,
            0.05,
            f"{_DOCUMENT}, page 4: 500 mV at the most",
        ),
        Figure(
            "dropout_limit_1a",
            "Dropout at 1.0 A with those parameters",
            drop_limit[1.0],
            "V",
            expected=common.DROPOUT_OFFSET + common.DROPOUT_OHMS * 1.0,
            source="section 4.2: 170 mV + 0.300 ohm x I, an estimate between the two limits",
        ),
        Figure(
            "dropout_control_100ma",
            "Dropout at the VCONTROL pin at 100 mA",
            drop_control[0.1],
            "V",
            expected=1.2,
            low=1.1,
            high=1.3,
            source=f"{_DOCUMENT}, page 4: 1.2 V typical",
        ),
        Figure(
            "dropout_control_1a1",
            "Dropout at the VCONTROL pin at 1.1 A",
            drop_control[1.1],
            "V",
            expected=1.35,
            low=1.25,
            high=1.6,
            source=f"{_DOCUMENT}, page 4: 1.35 V typical, 1.6 V at the most",
        ),
    ]

    limited = float(ctx.run("limit", _limit_deck(ctx)).real("vout#branch")[0])
    least = float(
        ctx.run("limit-least", _limit_deck(ctx, **common.LIMIT_CURRENT)).real("vout#branch")[0]
    )
    figures += [
        Figure(
            "current_limit",
            "Current limit, 5 V on both pins, output at -0.1 V",
            limited,
            "A",
            expected=1.4,
            low=1.3,
            high=1.5,
            source=f"{_DOCUMENT}, page 4: 1.4 A typical",
        ),
        near(
            "current_limit_least",
            "Current limit with the parameter of the least limit",
            least,
            "A",
            1.1,
            0.05,
            f"{_DOCUMENT}, page 4: 1.1 A at the least",
        ),
    ]

    traces: list[Trace] = []
    for panel, (name, text, low, high, farads, width, dip, peak) in enumerate(_STEPS):
        run = ctx.run(f"step-{name}", _step_deck(ctx, low, high, farads, width))
        time = run.real("time")
        deviation = run.real("out") - float(run.real("out")[0])
        release = _STEP_START + width
        lowest = measure.extremes(time, deviation, _STEP_START, release)[0]
        highest = measure.extremes(time, deviation, release, float(time[-1]))[1]
        figures += [
            near(
                f"step_{name}_dip".replace("-", "_"),
                f"Load step {text}: lowest point",
                lowest,
                "V",
                dip,
                _FIT,
                f"{_DOCUMENT}, page 6, read from the curve",
            ),
            near(
                f"step_{name}_peak".replace("-", "_"),
                f"Load step {text}: highest point after the release",
                highest,
                "V",
                peak,
                _FIT,
                f"{_DOCUMENT}, page 6, read from the curve",
            ),
        ]
        traces.append(Trace(time * 1e6, deviation * 1e3, "model", panel))

    response_traces: list[Trace] = []
    for amps, peak_db, corner in ((1.1, 3.0, 700e3), (0.1, 0.0, 300e3)):
        run = ctx.run(
            f"response-{amps:g}a".replace(".", "p"), _response_deck(ctx, amps, 2.2e-6, False)
        )
        frequency = run.real("frequency")
        response = run.vector("out")
        tag = f"{amps:g}a".replace(".", "p")
        figures += [
            Figure(
                f"response_peak_{tag}",
                f"From SET to OUT at {amps:g} A with 2.2 uF: peak above the level at 10 Hz",
                measure.peaking_db(response),
                "dB",
                expected=peak_db,
                source=f"{_DOCUMENT}, page 8, curve G28; its capacitor is not stated",
            ),
            Figure(
                f"response_corner_{tag}",
                f"From SET to OUT at {amps:g} A with 2.2 uF: 3 dB below the level at 10 Hz",
                measure.corner_frequency(frequency, response),
                "Hz",
                expected=corner,
                source=f"{_DOCUMENT}, page 8, curve G28; its capacitor is not stated",
            ),
        ]
        response_traces.append(
            Trace(frequency, measure.decibels(response), f"{amps:g} A, 2.2 uF", 0)
        )

    for amps, farads in _MARGIN_POINTS:
        tag = f"{amps * 1e3:g}ma_{farads * 1e6:g}uf".replace(".", "p")
        run = ctx.run(
            f"loop-{tag}".replace("_", "-"), _response_deck(ctx, amps, farads, True), keep=False
        )
        frequency, loop = _loop(run)
        crossover, margin = measure.stability_margins(frequency, loop)
        figures += [
            Figure(
                f"margin_{tag}",
                f"Phase margin of the model at {amps * 1e3:g} mA with {farads * 1e6:g} uF",
                margin,
                "deg",
            ),
            Figure(
                f"crossover_{tag}",
                f"Crossover of the loop at {amps * 1e3:g} mA with {farads * 1e6:g} uF",
                crossover,
                "Hz",
            ),
        ]
        response_traces.append(
            Trace(
                frequency,
                measure.decibels(loop),
                f"loop, {amps * 1e3:g} mA, {farads * 1e6:g} uF",
                1,
            )
        )

    noise = ctx.run("noise", _noise_deck(ctx))
    density = noise.real("onoise_spectrum")
    band = noise.real("frequency", "noise1")
    figures += [
        near(
            "noise_density",
            "Output noise density at 1 kHz",
            float(np.interp(1e3, band, density)),
            "V/√Hz",
            125e-9,
            0.10,
            f"{_DOCUMENT}, page 7, curve G26",
        ),
        near(
            "noise_10hz_100khz",
            "Output noise from 10 Hz to 100 kHz, 1.1 A, 10 uF, 0.1 uF on SET",
            measure.integrated_noise(band, density, 10.0, 100e3),
            "V",
            40e-6,
            0.15,
            f"{_DOCUMENT}, page 4",
        ),
    ]

    amps_axis = np.array(_DROP_AMPS)
    graphs = (
        Graph(
            name="load-steps",
            title="LT3080 model: the three load steps of page 6 of the datasheet",
            xlabel="Time (us)",
            panels=tuple(
                Panel(
                    f"{text}\nDeviation (mV)",
                    marks=((dip * 1e3, "datasheet"), (peak * 1e3, "datasheet")),
                )
                for _, text, _, _, _, _, dip, peak in _STEPS
            ),
            traces=tuple(traces),
        ),
        Graph(
            name="dropout",
            title="LT3080 model: dropout of the two supply pins over the load current",
            xlabel="Load current (A)",
            panels=(Panel("IN pin to output (mV)"), Panel("VCONTROL pin to output (V)")),
            traces=(
                Trace(
                    amps_axis, np.array([drop[a] for a in _DROP_AMPS]) * 1e3, "model, typical", 0
                ),
                Trace(
                    amps_axis,
                    np.array([drop_limit[a] for a in _DROP_AMPS]) * 1e3,
                    "model, guaranteed limits",
                    0,
                ),
                Trace(
                    np.array(list(_DROP_CURVE)),
                    np.array(list(_DROP_CURVE.values())) * 1e3,
                    "datasheet curves, 25 C",
                    0,
                    ":",
                ),
                Trace(
                    amps_axis,
                    (common.DROPOUT_OFFSET + common.DROPOUT_OHMS * amps_axis) * 1e3,
                    "170 mV + 0.300 ohm x I (section 4.2)",
                    0,
                    "--",
                ),
                Trace(amps_axis, np.array([drop_control[a] for a in _DROP_AMPS]), "model", 1),
            ),
        ),
        Graph(
            name="response",
            title="LT3080 model: response from SET to OUT and loop gain",
            xlabel="Frequency (Hz)",
            panels=(Panel("From SET to OUT (dB)"), Panel("Loop gain of the model (dB)")),
            traces=tuple(response_traces),
            logx=True,
        ),
    )
    notes = (
        "The limits are the fit this project asks of the model, not datasheet limits, "
        "except where the source names a limit of the datasheet. A supply pin counts as "
        "in dropout when the output has fallen by 10 mV; the datasheet does not define it.",
        "The loop of the model is a fit to the three load steps and to the response from "
        "SET to OUT. The step of 50 mA to 250 mA with 10 uF is not followed: the model "
        "dips about twice as far as the datasheet shows. The edge of the load steps "
        "(100 ns) and the capacitor of curve G28 (2.2 uF) are assumptions.",
        "The phase margin is a property of that fit and not a datasheet value. The "
        "datasheet shows no load step below 50 mA and no capacitor above 10 uF; the low "
        "margin of the model at 4 mA with 22 uF is an extrapolation.",
        "The model is a typical part at 27 C. It has no thermal limit, no fold-back of "
        "the current limit above 6 V and no fitted rejection of ripple on the IN pin.",
    )
    return Outcome(tuple(figures), graphs, notes)
