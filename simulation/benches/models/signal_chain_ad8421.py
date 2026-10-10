"""The AD8421 model against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.engine import RunResult

_DOCUMENT = "Analog Devices AD8421 Rev. A"
"""The datasheet the figures are taken from."""

_GAIN_OHMS = {1: None, 10: 1100.0, 100: 100.0, 1000: 9900.0 / 999.0}
"""Gain resistor of each gain of the tables: G = 1 + 9.9 kohm / RG (page 22)."""

_BANDWIDTH = {1: 10e6, 10: 10e6, 100: 2e6, 1000: 0.2e6}
"""Small-signal bandwidth by gain (page 4)."""

_DENSITY = {1: 60.1e-9, 10: 8.0e-9, 100: 3.5e-9, 1000: 3.0e-9}
"""Voltage noise referred to the input at 1 kHz by gain: 3 nV/rtHz and 60 nV/rtHz
with the noise of the gain resistor (pages 3 and 26, figure 42)."""

_PEAK_TO_PEAK = {1: 2e-6, 10: 0.5e-6, 1000: 0.07e-6}
"""Noise from 0.1 Hz to 10 Hz referred to the input, peak to peak, by gain (page 3)."""

_REJECTION = {1: 86.0, 10: 106.0, 100: 126.0}
"""Common-mode rejection of the A grade from DC to 60 Hz, at the least, by gain (page 3)."""

_CREST = 6.6
"""Peak-to-peak over RMS that the datasheets use for noise from 0.1 Hz to 10 Hz."""

_MODEL_BAND = 0.2
"""Distance from a typical dynamic figure of the datasheet that this project accepts."""


def _amplifier(gain: int, name: str = "X1", params: str = "", rails: str = "vp vn") -> list[str]:
    """One amplifier at a gain of the tables, between the nodes inn and inp, with 2 kohm."""
    positive, negative = rails.split()
    lines = [
        f"{name} inn_{name} rga_{name} rgb_{name} inp_{name} {negative} ref_{name} out_{name} "
        f"{positive} AD8421 {params}".rstrip(),
        f"Rl_{name} out_{name} 0 2k",
    ]
    ohms = _GAIN_OHMS[gain]
    if ohms is not None:
        lines.append(f"Rg_{name} rga_{name} rgb_{name} {ohms:.6g}")
    return lines


def _rails(volts: float = 15.0) -> list[str]:
    return [f"Vp vp 0 {volts:g}", f"Vn vn 0 {-volts:g}"]


def _response_deck(ctx: Context, gain: int) -> str:
    """Response and noise at one gain: the test circuit of the tables, +/-15 V."""
    lines = [
        *_rails(),
        "Vcm inn_X1 0 0",
        "Vd inp_X1 inn_X1 dc 0 ac 1",
        "Vref ref_X1 0 0",
        *_amplifier(gain),
    ]
    return ctx.deck(
        f"AD8421 at G = {gain}: response and noise",
        "\n".join(lines),
        control=["ac dec 60 10 200meg", "noise v(out_X1) Vd dec 30 0.1 100k"],
        libraries=("ad8421.lib",),
    )


def _rejection_deck(ctx: Context, gain: int) -> str:
    """Both inputs moved together, the rejection at the limit of the A grade."""
    lines = [
        *_rails(),
        "Vcm inn_X1 0 dc 0 ac 1",
        "Vd inp_X1 inn_X1 0",
        "Vref ref_X1 0 0",
        *_amplifier(gain, params="cmrr=86"),
    ]
    return ctx.deck(
        f"AD8421 at G = {gain}: common-mode rejection",
        "\n".join(lines),
        control=["ac dec 20 1 100k"],
        libraries=("ad8421.lib",),
    )


def _static_deck(ctx: Context) -> str:
    """Operating points: offsets, bias currents, reference pin, supply, overdrive, short."""
    lines = [
        *_rails(),
        "* A: offsets at their limits at G = 100",
        "Va inn_A 0 0",
        "Vda inp_A inn_A 0",
        "Vra ref_A 0 0",
        *_amplifier(100, "XA", "vosi=-60u voso=350u"),
        "* B: bias current 1 nA, offset current 0.5 nA, read in the input sources",
        "Vbn inn_B 0 0",
        "Vbp inp_B 0 0",
        "Vrb ref_B 0 0",
        *_amplifier(1, "XB", "ib=1n ios=0.5n"),
        "* C: reference pin at 0 V and, in the second point, at 1 V; own supplies",
        "Vpc vpc 0 15",
        "Vnc vnc 0 -15",
        "Vcn inn_C 0 0",
        "Vcp inp_C 0 0",
        "Vrc ref_C 0 0",
        *_amplifier(1, "XC", rails="vpc vnc"),
        "* D: G = 100 with one input at 6 V, the other at 0 V (figure 18)",
        "Vdn inn_D 0 0",
        "Vdp inp_D 0 6",
        "Vrd ref_D 0 0",
        *_amplifier(100, "XD"),
        "* E: the same with 1 V",
        "Ven inn_E 0 0",
        "Vep inp_E 0 1",
        "Vre ref_E 0 0",
        *_amplifier(100, "XE"),
        "* F: output held at 0 V while it is asked for 5 V",
        "Vfn inn_F 0 0",
        "Vfp inp_F 0 0.5",
        "Vrf ref_F 0 0",
        "XF inn_F rga_F rgb_F inp_F vn ref_F out_F vp AD8421",
        "Rg_F rga_F rgb_F 1100",
        "Vshort out_F 0 0",
    ]
    lines = [line.replace("_XA", "_A").replace("_XB", "_B") for line in lines]
    lines = [line.replace("_XC", "_C").replace("_XD", "_D").replace("_XE", "_E") for line in lines]
    return ctx.deck(
        "AD8421: static figures",
        "\n".join(lines),
        control=["op", "alter Vrc dc = 1", "op"],
        libraries=("ad8421.lib",),
    )


def _swing_deck(ctx: Context) -> str:
    lines = [*_rails(), "Vcm inn_X1 0 0", "Vd inp_X1 inn_X1 0", "Vref ref_X1 0 0", *_amplifier(10)]
    return ctx.deck(
        "AD8421 at G = 10: output swing into 2 kohm",
        "\n".join(lines),
        control=["dc Vd -2 2 0.01"],
        libraries=("ad8421.lib",),
    )


def _range_deck(ctx: Context, gain: int, supply: float, signal: float) -> str:
    """The common mode swept with a held signal: where the first stage leaves its range."""
    lines = [
        *_rails(supply),
        "Vcm cm 0 0",
        f"Vdn inn_X1 cm {-signal / 2:g}",
        f"Vdp inp_X1 cm {signal / 2:g}",
        "Vref ref_X1 0 0",
        *_amplifier(gain),
    ]
    return ctx.deck(
        f"AD8421 at G = {gain} on +/-{supply:g} V: common mode swept",
        "\n".join(lines),
        control=[f"dc Vcm {-supply:g} {supply:g} 0.02"],
        libraries=("ad8421.lib",),
    )


def _step_deck(ctx: Context, gain: int, volts: float) -> str:
    """A step of 10 V at the output."""
    half = volts / 2.0
    lines = [
        *_rails(),
        "Vcm inn_X1 0 0",
        f"Vd inp_X1 inn_X1 PWL(0 {-half:g} 1u {-half:g} 1.002u {half:g})",
        "Vref ref_X1 0 0",
        *_amplifier(gain),
        "Cl out_X1 0 100p",
    ]
    return ctx.deck(
        f"AD8421 at G = {gain}: step of 10 V at the output",
        "\n".join(lines),
        control=["tran 0.5n 4u 0 1n"],
        libraries=("ad8421.lib",),
    )


def _current_noise_deck(ctx: Context) -> str:
    """Noise at G = 1 with 1 Mohm in one input; the resistor itself makes none."""
    lines = [
        *_rails(),
        "Vd src 0 dc 0 ac 1",
        "Rs src inp_X1 1meg noisy=0",
        "Vcm inn_X1 0 0",
        "Vref ref_X1 0 0",
        *_amplifier(1),
    ]
    return ctx.deck(
        "AD8421 at G = 1: noise with 1 Mohm in one input",
        "\n".join(lines),
        control=["noise v(out_X1) Vd dec 30 0.1 10k"],
        libraries=("ad8421.lib",),
    )


def _lower_limit(run: RunResult, expected: float, band: float) -> float:
    """The lowest common mode at which the output still is where the gain puts it."""
    common_mode = run.real("v-sweep")
    output = run.real("out_x1")
    good = np.abs(output - expected) <= band
    return float(common_mode[good][0])


@bench(
    "models",
    "signal-chain-ad8421",
    "AD8421 model against its datasheet",
    "the model of the instrumentation amplifier U27",
)
def ad8421(ctx: Context) -> Outcome:
    """The model is put in the test circuits of its datasheet.

    On +/-15 V with 2 kohm at the output, as the tables of the datasheet
    are taken, the model runs at gains of 1, 10, 100 and 1000: response,
    noise density and noise from 0.1 Hz to 10 Hz, common-mode rejection
    with the parameter at the limit of the A grade. Operating points give
    the offsets, the bias currents, the reference pin, the supply current,
    the input current with 6 V between the inputs and the short-circuit
    current. Sweeps give the output swing and the common mode at which the
    first stage leaves its range, and a step of 10 V the slew rate and the
    settling time.
    """
    decks: dict[str, str] = {}
    for gain in _GAIN_OHMS:
        decks[f"response-g{gain}"] = _response_deck(ctx, gain)
    for gain in _REJECTION:
        decks[f"rejection-g{gain}"] = _rejection_deck(ctx, gain)
    decks["swing"] = _swing_deck(ctx)
    decks["range-g100-15v-0v"] = _range_deck(ctx, 100, 15.0, 0.001)
    decks["range-g100-15v-10v"] = _range_deck(ctx, 100, 15.0, 0.1)
    decks["range-g1-5v"] = _range_deck(ctx, 1, 5.0, 0.01)
    decks["step-g1"] = _step_deck(ctx, 1, 10.0)
    decks["step-g10"] = _step_deck(ctx, 10, 1.0)
    decks["current-noise"] = _current_noise_deck(ctx)
    static = ctx.run("static", _static_deck(ctx))
    ctx.run("response-g10", decks["response-g10"])
    runs = ctx.run_many(decks)

    figures: list[Figure] = []
    traces: list[Trace] = []
    noise_traces: list[Trace] = []
    for gain in _GAIN_OHMS:
        run = runs[f"response-g{gain}"]
        frequency = run.real("frequency", plot="ac")
        response = np.asarray(run.vector("out_x1", plot="ac"), dtype=np.complex128)
        figures += [
            near(
                f"gain_g{gain}",
                f"G = {gain}: gain at 10 Hz",
                float(np.abs(response[0])),
                "",
                float(gain),
                0.0005,
                f"{_DOCUMENT}, page 22: G = 1 + 9.9 kohm / RG",
            ),
            near(
                f"bandwidth_g{gain}",
                f"G = {gain}: small-signal bandwidth",
                measure.corner_frequency(frequency, response),
                "Hz",
                _BANDWIDTH[gain],
                _MODEL_BAND,
                f"{_DOCUMENT}, page 4",
            ),
        ]
        traces.append(Trace(frequency, measure.decibels(response), f"G = {gain}", 0))
        noise_frequency = run.real("frequency", plot="noise")
        referred = run.real("inoise_spectrum")
        figures.append(
            near(
                f"density_g{gain}",
                f"G = {gain}: voltage noise at 1 kHz, referred to the input",
                float(np.interp(3.0, np.log10(noise_frequency), referred)),
                "V/√Hz",
                _DENSITY[gain],
                0.1,
                f"{_DOCUMENT}, pages 3 and 26",
            )
        )
        if gain in _PEAK_TO_PEAK:
            figures.append(
                near(
                    f"low_frequency_g{gain}",
                    f"G = {gain}: noise from 0.1 Hz to 10 Hz, peak to peak, referred to the input",
                    _CREST * measure.integrated_noise(noise_frequency, referred, 0.1, 10.0),
                    "V",
                    _PEAK_TO_PEAK[gain],
                    0.25,
                    f"{_DOCUMENT}, page 3",
                )
            )
        noise_traces.append(Trace(noise_frequency, referred * 1e9, f"G = {gain}", 0))

    current = runs["current-noise"]
    current_frequency = current.real("frequency")
    at_output = current.real("onoise_spectrum")
    own = _DENSITY[1]
    in_resistor = np.sqrt(np.maximum(at_output**2 - own**2, 0.0)) / 1e6
    figures += [
        near(
            "current_noise",
            "Current noise of an input at 1 kHz",
            float(np.interp(3.0, np.log10(current_frequency), in_resistor)),
            "A/√Hz",
            200e-15,
            0.1,
            f"{_DOCUMENT}, page 3",
        ),
        near(
            "current_noise_low",
            "Current noise of an input from 0.1 Hz to 10 Hz, peak to peak",
            _CREST * measure.integrated_noise(current_frequency, in_resistor, 0.1, 10.0),
            "A",
            18e-12,
            0.25,
            f"{_DOCUMENT}, page 3",
        ),
    ]

    for gain, least in _REJECTION.items():
        run = runs[f"rejection-g{gain}"]
        frequency = run.real("frequency")
        leak = np.abs(np.asarray(run.vector("out_x1"), dtype=np.complex128))
        rejection = 20.0 * np.log10(gain / leak)
        figures.append(
            near(
                f"rejection_g{gain}",
                f"G = {gain}: common-mode rejection at 1 Hz with the parameter at 86 dB",
                float(rejection[0]),
                "dB",
                least,
                0.01,
                f"{_DOCUMENT}, page 3: limit of the A grade",
            )
        )
        if gain == 1:
            figures.append(
                near(
                    "rejection_20khz",
                    "G = 1: common-mode rejection at 20 kHz with the parameter at 86 dB",
                    float(np.interp(np.log10(20e3), np.log10(frequency), rejection)),
                    "dB",
                    80.0,
                    0.02,
                    f"{_DOCUMENT}, page 3: limit of the A grade",
                )
            )
        if gain == 10:
            figures.append(
                Figure(
                    "rejection_20khz_g10",
                    "G = 10: common-mode rejection at 20 kHz with the parameter at 86 dB",
                    float(np.interp(np.log10(20e3), np.log10(frequency), rejection)),
                    "dB",
                    expected=90.0,
                    source=f"{_DOCUMENT}, page 3: 90 dB at the least; the model does not have "
                    "this fall",
                )
            )

    def point(name: str, plot: str = "op1") -> float:
        return float(static.real(name, plot=plot)[0])

    reference_current = point("vrc#branch", "op2") - point("vrc#branch", "op1")
    figures += [
        near(
            "offset",
            "G = 100 with vosi at -60 uV and voso at 350 uV: output",
            point("out_a"),
            "V",
            100 * 60e-6 + 350e-6,
            0.01,
            f"{_DOCUMENT}, page 5: input offset times the gain plus output offset; "
            "a positive vosi lowers the output of this model, a positive voso raises it",
        ),
        near(
            "bias_positive",
            "Bias 1 nA, offset current 0.5 nA: current into the positive input",
            -point("vbp#branch"),
            "A",
            1.25e-9,
            0.02,
            "definition of the parameters ib and ios",
        ),
        near(
            "bias_negative",
            "Bias 1 nA, offset current 0.5 nA: current into the negative input",
            -point("vbn#branch"),
            "A",
            0.75e-9,
            0.02,
            "definition of the parameters ib and ios",
        ),
        Figure(
            "reference_current",
            "Current of the reference pin with all inputs at 0 V",
            abs(point("vrc#branch")),
            "A",
            expected=20e-6,
            high=24e-6,
            source=f"{_DOCUMENT}, page 4: 20 uA, 24 uA at the most",
        ),
        near(
            "reference_resistance",
            "Input resistance of the reference pin",
            1.0 / abs(reference_current),
            "ohm",
            20e3,
            0.02,
            f"{_DOCUMENT}, page 4",
        ),
        Figure(
            "supply_current",
            "Supply current without load",
            -point("vpc#branch"),
            "A",
            expected=2e-3,
            high=2.3e-3,
            source=f"{_DOCUMENT}, page 5: 2 mA, 2.3 mA at the most",
        ),
        near(
            "overdrive_6v",
            "G = 100, 6 V between the inputs: current into the positive input",
            -point("vdp#branch"),
            "A",
            10e-3,
            0.3,
            f"{_DOCUMENT}, page 14, figure 18 (read from the curve)",
        ),
        Figure(
            "overdrive_1v",
            "G = 100, 1 V between the inputs: current into the positive input",
            -point("vep#branch"),
            "A",
            high=1e-3,
            source=f"{_DOCUMENT}, page 14, figure 18: no visible current below about 2 V",
        ),
        near(
            "short_circuit",
            "Current into a short circuit at the output",
            abs(point("vshort#branch")),
            "A",
            65e-3,
            0.1,
            f"{_DOCUMENT}, page 4",
        ),
    ]

    swing = runs["swing"]
    swept = swing.real("out_x1")
    figures += [
        Figure(
            "swing_high",
            "Output swing into 2 kohm on +/-15 V: highest output",
            float(swept.max()),
            "V",
            expected=13.6,
            low=13.4,
            source=f"{_DOCUMENT}, page 4: +Vs - 1.6 V at the least; figure 36: +Vs - 1.4 V",
        ),
        Figure(
            "swing_low",
            "Output swing into 2 kohm on +/-15 V: lowest output",
            float(swept.min()),
            "V",
            expected=-13.9,
            high=-13.8,
            source=f"{_DOCUMENT}, page 4: -Vs + 1.2 V at the least; figure 36: -Vs + 1.1 V",
        ),
    ]
    figures += [
        Figure(
            "range_g100_0v",
            "G = 100 on +/-15 V, output near 0 V: lowest common mode",
            _lower_limit(runs["range-g100-15v-0v"], 0.1, 0.01),
            "V",
            expected=-13.0,
            low=-13.3,
            high=-12.7,
            source=f"{_DOCUMENT}, page 13, figure 13 (read from the curve)",
        ),
        Figure(
            "range_g100_10v",
            "G = 100 on +/-15 V, output at 10 V: lowest common mode",
            _lower_limit(runs["range-g100-15v-10v"], 10.0, 0.05),
            "V",
            expected=-8.0,
            low=-8.5,
            high=-7.5,
            source=f"{_DOCUMENT}, page 13, figure 13 (read from the curve)",
        ),
        Figure(
            "range_g1_5v",
            "G = 1 on +/-5 V, output near 0 V: lowest common mode",
            _lower_limit(runs["range-g1-5v"], 0.01, 0.005),
            "V",
            expected=-2.7,
            low=-3.0,
            high=-2.4,
            source=f"{_DOCUMENT}, page 4: -Vs + 2.3 V; page 13, figure 12",
        ),
    ]

    step = runs["step-g1"]
    time = step.real("time")
    output = step.real("out_x1")
    rise = measure.rise_time(time, output, -3.0, 3.0, after=1e-6)
    settle = runs["step-g10"]
    settle_time = settle.real("time")
    settle_output = settle.real("out_x1")
    final = measure.mean(settle_time, settle_output, 3.5e-6, 3.9e-6)
    figures += [
        near(
            "slew_rate",
            "Slew rate, step of 10 V at G = 1",
            6.0 / rise / 1e6,
            "V/us",
            35.0,
            0.1,
            f"{_DOCUMENT}, page 4",
        ),
        Figure(
            "settling_g10",
            "G = 10, step of 10 V: within 0.01 % after",
            measure.settling_time(settle_time, settle_output, final, 1e-3, 1e-6),
            "s",
            expected=0.4e-6,
            high=0.8e-6,
            source=f"{_DOCUMENT}, page 4: 0.4 us typical; twice that is the fit asked here",
        ),
    ]
    response_graph = Graph(
        name="response",
        title="AD8421 model: gain against frequency",
        xlabel="Frequency (Hz)",
        panels=(Panel("Gain (dB)"),),
        traces=tuple(traces),
        logx=True,
    )
    noise_graph = Graph(
        name="noise",
        title="AD8421 model: voltage noise referred to the input",
        xlabel="Frequency (Hz)",
        panels=(Panel("Density (nV/√Hz)", log=True),),
        traces=tuple(noise_traces),
        logx=True,
    )
    step_graph = Graph(
        name="step",
        title="AD8421 model: step of 10 V at the output",
        xlabel="Time (us)",
        panels=(Panel("Output (V)"),),
        traces=(
            Trace(time * 1e6, output, "G = 1", 0),
            Trace(settle_time * 1e6, settle_output, "G = 10", 0, "--"),
        ),
    )
    notes = (
        "The limits of the dynamic figures are the fit this project asks of a model: 20 % "
        "on a bandwidth, 10 % on a noise density, 25 % on the noise from 0.1 Hz to 10 Hz. "
        "They are not datasheet limits.",
        "The model is a typical part at 25 C. Its offsets, its bias currents and its "
        "common-mode error are parameters that are zero unless a bench sets them; the "
        "figures here show that a parameter gives what the datasheet defines.",
        "The model has no peaking: the datasheet shows 8 dB near 8 MHz at a gain of 1 "
        "(figure 22). The rejection at 20 kHz is right at a gain of 1 only.",
        "At low gain the table limits the inputs to -Vs + 2.3 V; the model only has the "
        "limit of its first-stage outputs, which lies 0.3 V lower. On this board the "
        "inputs stay 4 V above the negative supply.",
        "The input current in overdrive is a fit to one figure at a gain of 100.",
        "The noise from 0.1 Hz to 10 Hz at a gain of 10 fails and stays failed. The model "
        "has the two sources of the datasheet, one at the input and one at the output, "
        "fitted to the table at a gain of 1 (2 uV peak to peak) and at a gain of 100 and "
        "more (0.07 uV). The two together give 0.21 uV at a gain of 10 (calculated), where "
        "the table states 0.5 uV: that value does not follow from the other two, and the "
        "model was not bent to it. This board works at a gain of 19.93. If the table is "
        "right, the amplifier has up to twice the noise of the model below 10 Hz.",
    )
    return Outcome(tuple(figures), (response_graph, noise_graph, step_graph), notes)
