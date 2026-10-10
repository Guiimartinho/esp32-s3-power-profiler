"""The OPA197 and OPA365 models against the figures of their datasheets."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_CREST = 6.6
"""Peak-to-peak over RMS that the datasheets use for noise from 0.1 Hz to 10 Hz."""


@dataclass(frozen=True, slots=True)
class _Datasheet:
    """What a datasheet states about an operational amplifier, typical values at 25 C.

    Attributes:
        model: Name of the SPICE subcircuit.
        document: The datasheet, as the results name it.
        positive: Positive supply of the test conditions.
        negative: Negative supply of the test conditions.
        gain_db: Open-loop gain at DC, typical and at the least.
        bandwidth: Gain-bandwidth product.
        crossover: Frequency at which the open-loop gain falls through 1.
        margin: Phase margin, as read from the open-loop curve.
        load_farads: Capacitive load of that curve.
        slew: Slew rate, V/s.
        step: Height of the step of the settling figure.
        settling: Settling time to 0.01 % after that step.
        density: Voltage noise density by frequency.
        peak_to_peak: Noise from 0.1 Hz to 10 Hz, peak to peak.
        swing: Output swing from a rail by load resistance (None for no load),
            typical and at the most.
        output_ohms: Open-loop output impedance at 1 MHz.
        supply_amps: Supply current, typical and at the most.
        short_amps: Short-circuit current.
        common_farads: Input capacitance from each input.
        between_farads: Input capacitance between the inputs.
        overshoot: Overshoot of a small step of a follower, by load capacitance.
    """

    model: str
    document: str
    positive: float
    negative: float
    gain_db: tuple[float, float]
    bandwidth: float
    crossover: float
    margin: float
    load_farads: float
    slew: float
    step: float
    settling: float
    density: dict[float, float]
    peak_to_peak: float
    swing: dict[float | None, tuple[float, float]]
    output_ohms: float
    supply_amps: tuple[float, float]
    short_amps: float
    common_farads: float
    between_farads: float
    overshoot: dict[float, float]


_OPA197 = _Datasheet(
    model="OPA197",
    document="TI SBOS737C",
    positive=18.0,
    negative=-18.0,
    gain_db=(134.0, 120.0),
    bandwidth=10e6,
    crossover=10e6,
    margin=50.0,
    load_farads=15e-12,
    slew=20e6,
    step=10.0,
    settling=1.4e-6,
    density={100.0: 10.5e-9, 1e3: 5.5e-9},
    peak_to_peak=1.3e-6,
    swing={None: (5e-3, 25e-3), 10e3: (95e-3, 125e-3), 2e3: (430e-3, 500e-3)},
    output_ohms=375.0,
    supply_amps=(1e-3, 1.3e-3),
    short_amps=65e-3,
    common_farads=6.4e-12,
    between_farads=1.6e-12,
    overshoot={100e-12: 15.0, 1e-9: 40.0},
)

_OPA365 = _Datasheet(
    model="OPA365",
    document="TI SBOS365G",
    positive=5.0,
    negative=0.0,
    gain_db=(120.0, 100.0),
    bandwidth=50e6,
    crossover=50e6,
    margin=50.0,
    load_farads=0.0,
    slew=25e6,
    step=4.0,
    settling=0.3e-6,
    density={1e3: 13e-9, 100e3: 4.5e-9},
    peak_to_peak=5e-6,
    swing={10e3: (10e-3, 20e-3)},
    output_ohms=30.0,
    supply_amps=(4.6e-3, 5e-3),
    short_amps=65e-3,
    common_farads=2e-12,
    between_farads=6e-12,
    overshoot={100e-12: 30.0},
)


def _supplies(part: _Datasheet) -> list[str]:
    middle = 0.5 * (part.positive + part.negative)
    return [f"Vp vp 0 {part.positive:g}", f"Vn vn 0 {part.negative:g}", f"Vmid mid 0 {middle:g}"]


def _open_loop_deck(ctx: Context, part: _Datasheet, *, impedance: bool) -> str:
    """The loop closed for DC through a large inductor, open from 0.1 Hz on."""
    lines = [
        *_supplies(part),
        f"Vin in mid dc 0 ac {0 if impedance else 1}",
        f"X1 in fb vp vn out {part.model}",
        "Lfb out fb 1meg",
        "Cfb fb mid 1k",
        f"Itest mid out dc 0 ac {1 if impedance else 0}",
    ]
    if not impedance:
        lines.append("Rl out mid 10k")
        if part.load_farads:
            lines.append(f"Cl out mid {part.load_farads:g}")
    control = ["ac dec 60 0.1 500meg"]
    if not impedance:
        control.append("noise v(out) Vin dec 30 0.1 1meg")
    return ctx.deck(
        f"{part.model}: open loop" + (", impedance of the output" if impedance else ""),
        "\n".join(lines),
        control=control,
        libraries=("opamps.lib",),
    )


def _static_deck(ctx: Context, part: _Datasheet) -> str:
    """Followers at the rails with their loads, supply current, short circuit, inputs."""
    top = part.positive + 1.0
    lines = [*_supplies(part), f"Vhigh high 0 {top:g}", f"Vlow low 0 {part.negative - 1.0:g}"]
    for index, ohms in enumerate(part.swing):
        for side in ("high", "low"):
            name = f"{side}{index}"
            lines.append(f"X{name} {side} o_{name} vp vn o_{name} {part.model}")
            if ohms is not None:
                lines.append(f"R{name} o_{name} mid {ohms:g}")
    lines += [
        "* supply current of a follower without load, on supplies of its own",
        f"Vpq vpq 0 {part.positive:g}",
        f"Vnq vnq 0 {part.negative:g}",
        f"Xq mid o_q vpq vnq o_q {part.model}",
        "* a follower asked for 1 V above the middle, its output held at the middle",
        "Vask ask mid 1",
        f"Xs ask o_s vp vn o_s {part.model}",
        "Vshort o_s mid 0",
        "* a follower on 1 V of supply: below the supply range",
        "Vpd vpd 0 1",
        "Vin_d in_d 0 0.5",
        f"Xd in_d o_d vpd 0 o_d {part.model}",
        "Rd o_d 0 10k",
    ]
    return ctx.deck(
        f"{part.model}: static figures",
        "\n".join(lines),
        control=["op"],
        libraries=("opamps.lib",),
    )


def _input_deck(ctx: Context, part: _Datasheet) -> str:
    """The capacitance of the inputs: both moved together, then one alone."""
    lines = [
        *_supplies(part),
        "Vboth both mid dc 0 ac 1",
        f"Xa both both vp vn o_a {part.model}",
        "Vone one mid dc 0 ac 1",
        f"Xb one mid vp vn o_b {part.model}",
    ]
    return ctx.deck(
        f"{part.model}: input capacitance",
        "\n".join(lines),
        control=["ac lin 1 100k 100k"],
        libraries=("opamps.lib",),
    )


def _step_deck(ctx: Context, part: _Datasheet, volts: float, farads: float) -> str:
    """A follower with a step at its input."""
    half = volts / 2.0
    lines = [
        *_supplies(part),
        f"Vin in mid PWL(0 {-half:g} 1u {-half:g} 1.002u {half:g})",
        f"X1 in out vp vn out {part.model}",
        "Rl out mid 10k",
    ]
    if farads:
        lines.append(f"Cl out mid {farads:g}")
    return ctx.deck(
        f"{part.model}: follower, step of {volts:g} V",
        "\n".join(lines),
        control=["tran 0.5n 6u 0 1n"],
        libraries=("opamps.lib",),
    )


def _qualify(ctx: Context, part: _Datasheet) -> Outcome:
    decks = {
        "open-loop": _open_loop_deck(ctx, part, impedance=False),
        "impedance": _open_loop_deck(ctx, part, impedance=True),
        "inputs": _input_deck(ctx, part),
        "step-large": _step_deck(ctx, part, part.step, 0.0),
    }
    for farads in part.overshoot:
        decks[f"step-{farads * 1e12:g}p"] = _step_deck(ctx, part, 0.1, farads)
    static = ctx.run("static", _static_deck(ctx, part))
    ctx.run("open-loop", decks["open-loop"])
    runs = ctx.run_many(decks)

    loop = runs["open-loop"]
    frequency = loop.real("frequency", plot="ac")
    gain = np.asarray(loop.vector("out", plot="ac"), dtype=np.complex128)
    level = measure.decibels(gain)
    log_f = np.log10(frequency)
    crossover, margin = measure.stability_margins(frequency, gain)
    figures: list[Figure] = [
        Figure(
            "gain",
            "Open-loop gain at 0.1 Hz into 10 kohm",
            float(level[0]),
            "dB",
            expected=part.gain_db[0],
            low=part.gain_db[1],
            high=part.gain_db[0] + 10.0,
            source=f"{part.document}: typical value and least value",
        ),
        near(
            "bandwidth",
            "Gain-bandwidth product, from the gain at a hundredth of it",
            float(10.0 ** (np.interp(np.log10(part.bandwidth / 100.0), log_f, level) / 20.0))
            * part.bandwidth
            / 100.0,
            "Hz",
            part.bandwidth,
            0.15,
            part.document,
        ),
        near(
            "crossover",
            "Frequency at which the open-loop gain falls through 1",
            crossover,
            "Hz",
            part.crossover,
            0.2,
            part.document,
        ),
        Figure(
            "margin",
            "Phase margin of a follower"
            + (f" with {part.load_farads * 1e12:g} pF" if part.load_farads else ""),
            margin,
            "deg",
            expected=part.margin,
            low=part.margin - 10.0,
            high=part.margin + 10.0,
            source=f"{part.document}: read from the open-loop curve",
        ),
    ]
    noise_frequency = loop.real("frequency", plot="noise")
    referred = loop.real("inoise_spectrum")
    for hertz, density in part.density.items():
        figures.append(
            near(
                f"density_{int(hertz)}",
                f"Voltage noise at {hertz:g} Hz",
                float(np.interp(np.log10(hertz), np.log10(noise_frequency), referred)),
                "V/√Hz",
                density,
                0.12,
                part.document,
            )
        )
    figures.append(
        near(
            "low_frequency",
            "Noise from 0.1 Hz to 10 Hz, peak to peak",
            _CREST * measure.integrated_noise(noise_frequency, referred, 0.1, 10.0),
            "V",
            part.peak_to_peak,
            0.25,
            part.document,
        )
    )
    impedance = runs["impedance"]
    figures.append(
        near(
            "output_impedance",
            "Open-loop output impedance at 1 MHz",
            float(
                np.interp(
                    6.0, np.log10(impedance.real("frequency")), np.abs(impedance.vector("out"))
                )
            ),
            "ohm",
            part.output_ohms,
            0.1,
            part.document,
        )
    )

    def point(name: str) -> float:
        return float(static.real(name)[0])

    for index, (ohms, (typical, most)) in enumerate(part.swing.items()):
        load = "without load" if ohms is None else f"into {ohms / 1e3:g} kohm"
        figures += [
            Figure(
                f"swing_high_{index}",
                f"Output {load}: distance from the positive supply",
                part.positive - point(f"o_high{index}"),
                "V",
                expected=typical,
                high=most,
                source=f"{part.document}: typical value and limit",
            ),
            Figure(
                f"swing_low_{index}",
                f"Output {load}: distance from the negative supply",
                point(f"o_low{index}") - part.negative,
                "V",
                expected=typical,
                high=most,
                source=f"{part.document}: typical value and limit",
            ),
        ]
    figures += [
        Figure(
            "supply_current",
            "Supply current without load",
            -point("vpq#branch"),
            "A",
            expected=part.supply_amps[0],
            low=0.9 * part.supply_amps[0],
            high=part.supply_amps[1],
            source=f"{part.document}: typical value and limit",
        ),
        near(
            "short_circuit",
            "Current into a short circuit at the output",
            abs(point("vshort#branch")),
            "A",
            part.short_amps,
            0.1,
            part.document,
        ),
        Figure(
            "without_supply",
            "Output of a follower on 1 V of supply with 0.5 V at its input",
            point("o_d"),
            "V",
            high=0.02,
            source="the model: no output below 1.5 V of supply (assumption)",
        ),
    ]
    inputs = runs["inputs"]
    omega = 2.0 * np.pi * 100e3
    both = abs(complex(inputs.vector("vboth#branch")[0])) / omega
    one = abs(complex(inputs.vector("vone#branch")[0])) / omega
    figures += [
        near(
            "input_common",
            "Input capacitance from each input",
            both / 2.0,
            "F",
            part.common_farads,
            0.05,
            part.document,
        ),
        near(
            "input_between",
            "Input capacitance between the inputs",
            one - both / 2.0,
            "F",
            part.between_farads,
            0.05,
            part.document,
        ),
    ]
    large = runs["step-large"]
    time = large.real("time")
    output = large.real("out")
    middle = 0.5 * (part.positive + part.negative)
    low_level = middle - 0.3 * part.step
    high_level = middle + 0.3 * part.step
    rise = measure.rise_time(time, output, low_level, high_level, after=1e-6)
    final = measure.mean(time, output, 5.5e-6, 5.9e-6)
    figures += [
        near(
            "slew_rate",
            f"Slew rate, step of {part.step:g} V",
            0.6 * part.step / rise / 1e6,
            "V/us",
            part.slew / 1e6,
            0.1,
            part.document,
        ),
        Figure(
            "settling",
            f"Step of {part.step:g} V: within 0.01 % after",
            measure.settling_time(time, output, final, 1e-4 * part.step, 1e-6),
            "s",
            expected=part.settling,
            high=2.0 * part.settling,
            source=f"{part.document}: typical value; twice that is the fit asked here",
        ),
    ]
    step_traces: list[Trace] = []
    for farads, percent in part.overshoot.items():
        small = runs[f"step-{farads * 1e12:g}p"]
        small_time = small.real("time")
        small_output = small.real("out")
        settled = measure.mean(small_time, small_output, 5.5e-6, 5.9e-6)
        figures.append(
            Figure(
                f"overshoot_{farads * 1e12:g}p",
                f"Follower with {farads * 1e12:g} pF: overshoot of a 100 mV step",
                100.0 * measure.overshoot(small_time, small_output, settled - 0.1, settled, 1e-6),
                "%",
                expected=percent,
                source=f"{part.document}: read from the overshoot curve",
            )
        )
        step_traces.append(
            Trace(small_time * 1e6, (small_output - middle) * 1e3, f"{farads * 1e12:g} pF", 1)
        )
    graph = Graph(
        name="open-loop",
        title=f"{part.model} model: open-loop gain and phase",
        xlabel="Frequency (Hz)",
        panels=(
            Panel("Gain (dB)", marks=((0.0, "0 dB"),)),
            Panel("Phase above -180 degrees (degrees)"),
        ),
        traces=(
            Trace(frequency, level, "", 0),
            Trace(frequency, measure.phase_degrees(gain) + 180.0, "", 1),
        ),
        logx=True,
    )
    steps = Graph(
        name="step",
        title=f"{part.model} model: follower steps",
        xlabel="Time (us)",
        panels=(Panel("Large step (V)"), Panel("Small step with a capacitive load (mV)")),
        traces=(Trace(time * 1e6, output, "", 0), *step_traces),
    )
    notes = (
        "The limits of the dynamic figures are the fit this project asks of a model: 15 % "
        "on the gain-bandwidth product, 20 % on the crossover, 10 degrees on the phase "
        "margin, 12 % on a noise density, 25 % on the noise from 0.1 Hz to 10 Hz. They are "
        "not datasheet limits.",
        "The model is a typical part at 25 C without offset; the offset and the bias "
        "current are parameters.",
        "The overshoot with a capacitive load carries no limit: the open-loop output "
        "impedance of the model is a resistance, with a capacitor across it for the "
        "OPA197, and the real parts differ from that above 1 MHz.",
    )
    return Outcome(tuple(figures), (graph, steps), notes)


@bench(
    "models",
    "signal-chain-opa197",
    "OPA197 model against its datasheet",
    "the model of the pedestal buffer U26 (and of U17 and U25)",
)
def opa197(ctx: Context) -> Outcome:
    """The model is put in the test circuits of its datasheet, on +/-18 V.

    An open-loop run gives the gain, the gain-bandwidth product, the phase
    margin and the noise; a current into the output gives the open-loop
    output impedance. Followers driven beyond the rails give the output
    swing with each load of the table, others the supply current, the
    short-circuit current and the input capacitances. Steps of a follower
    give the slew rate, the settling time and the overshoot with a
    capacitive load. The datasheet has a table of isolation resistors for
    capacitive loads as well; the bench of the output stage for its guard
    buffer compares the model with it.
    """
    return _qualify(ctx, _OPA197)


@bench(
    "models",
    "signal-chain-opa365",
    "OPA365 model against its datasheet",
    "the model of the rail buffer U28 and of the converter driver U29 (and of U19)",
)
def opa365(ctx: Context) -> Outcome:
    """The model is put in the test circuits of its datasheet, on 5 V.

    An open-loop run gives the gain, the gain-bandwidth product, the phase
    margin and the noise; a current into the output gives the open-loop
    output impedance. Followers driven beyond the rails give the output
    swing into 10 kohm, others the supply current, the short-circuit
    current and the input capacitances. Steps of a follower give the slew
    rate, the settling time and the overshoot with a capacitive load.
    """
    return _qualify(ctx, _OPA365)
