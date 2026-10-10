"""Noise and ripple of +12V_A and -4V_A, and what passes from the rails ahead of them."""

from __future__ import annotations

import numpy as np

from benches.analog_rails import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.circuit import Circuit
from circuit_sim.engine import RunResult

_POSITIVE = ("U13", "R37", "R38", "R39", "R40", "C29", "C30", "C31", "D9")
"""The +12V_A regulator with the filter ahead of it and its setting parts."""

_NEGATIVE = ("U11", "R27", "R28", "R30", "R34", "R36", "R69", "D8", "C19", "C21", "C22", "C28")
"""The charge pump with its parts."""

_REFERENCE = ("U12", "R31", "C20", "C24", "R35", "C26", "D7", "C113")
"""The reference with its supply filter and capacitors."""

_POSITIVE_LOAD = common.AMPLIFIER_AMPS + common.DRIVER_AMPS
"""Load on +12V_A: the amplifiers and the drivers."""

_BOOST_HERTZ = 1.6e6
"""Switching frequency of the boost converter."""

_PUMP_HERTZ = 2e6
"""Switching frequency of the charge pump."""

NL = "\n"
"""Line break between the lines of a deck."""

_SPOTS = (120.0, 10e3, 100e3, _BOOST_HERTZ)
"""Frequencies at which the rejection of +12V_A is read; the first three are datasheet points."""


def _positive_circuit(ctx: Context) -> Circuit:
    refs = (*_POSITIVE, *common.capacitors_on(ctx.netlist, ("+12V_A",)))
    return ctx.circuit(refs, common.ALIASES, common.bias_models(ctx.netlist, refs))


def _positive_settle_deck(ctx: Context) -> str:
    """The regulator brought up from zero, to find the state it rests in."""
    stimulus = NL.join(
        [
            "V13 p13v5 0 PWL(0 0 0.1m 13.53)",
            "Vok ok5v 0 PWL(0 0 0.2m 0 0.21m 4.7)",
            f"Bload p12v_a 0 I = {_POSITIVE_LOAD:g}*tanh(max(v(p12v_a), 0)/2)",
        ]
    )
    return ctx.deck(
        "+12V_A: the regulator brought up, to find its state of rest",
        _positive_circuit(ctx),
        stimulus,
        control=["save all", "tran 20u 0.3 0 50u"],
    )


def _positive_deck(ctx: Context, start: str) -> str:
    stimulus = NL.join(
        [
            "* +13V5 as a source with a test signal, the regulator enabled, its load a sink",
            "V13 p13v5 0 DC 13.53 AC 1",
            "Vok ok5v 0 4.7",
            f"Iload p12v_a 0 {_POSITIVE_LOAD:g}",
        ]
    )
    return ctx.deck(
        "+12V_A: operating point, noise and rejection of +13V5",
        _positive_circuit(ctx),
        stimulus,
        start,
        control=["op", "noise v(p12v_a) V13 dec 30 1 10meg", "ac dec 30 1 10meg"],
    )


def _negative_circuit(ctx: Context) -> Circuit:
    refs = (*_NEGATIVE, *common.capacitors_on(ctx.netlist, ("-4V_A",)))
    overrides = common.bias_models(ctx.netlist, refs)
    overrides["U11"] = common.AVERAGED_PUMP
    return ctx.circuit(refs, common.ALIASES, overrides)


def _negative_settle_deck(ctx: Context) -> str:
    """The averaged pump brought up from zero, to find the state it rests in."""
    stimulus = NL.join(
        [
            "V5 p5v 0 PWL(0 0 0.1m 5)",
            "Vok ok5v 0 PWL(0 0 0.2m 0 0.21m 4.7)",
            f"Iload 0 m4v_a PWL(0 0 1m 0 1.1m {common.AMPLIFIER_AMPS:g})",
            "Vldo ldo_out 0 0",
        ]
    )
    return ctx.deck(
        "-4V_A: the averaged pump brought up, to find its state of rest",
        _negative_circuit(ctx),
        stimulus,
        control=["save all", "tran 10u 20m"],
    )


def _negative_small_deck(ctx: Context, start: str) -> str:
    stimulus = NL.join(
        [
            "V5 p5v 0 DC 5 AC 1",
            "Vok ok5v 0 4.7",
            f"Iload 0 m4v_a {common.AMPLIFIER_AMPS:g}",
            "Vldo ldo_out 0 0",
        ]
    )
    return ctx.deck(
        "-4V_A: operating point, noise and rejection of the 5 V rail (averaged pump)",
        _negative_circuit(ctx),
        stimulus,
        start,
        control=["op", "noise v(m4v_a) V5 dec 30 1 10meg", "ac dec 30 1 10meg"],
    )


def _negative_ripple_deck(ctx: Context) -> str:
    refs = (*_NEGATIVE, *common.capacitors_on(ctx.netlist, ("-4V_A",)))
    scales = common.bias_scales(ctx.netlist, refs)
    circuit = ctx.circuit(refs, common.ALIASES, None, scales)
    stimulus = "\n".join(
        [
            "V5 p5v 0 PWL(0 0 0.1m 5)",
            "Vok ok5v 0 PWL(0 0 0.2m 0 0.21m 4.7)",
            f"Bload 0 m4v_a I = {common.AMPLIFIER_AMPS:g}*tanh(max(-v(m4v_a), 0)/2)",
            "Vldo ldo_out 0 0",
        ]
    )
    return ctx.deck(
        "-4V_A: the pump switch by switch, with the loads of the rail",
        circuit,
        stimulus,
        control=["save m4v_a cpout pump_in cfly_p cfly_n", "tran 10n 3.5m 2.4m 25n"],
        options=("reltol=1e-5", "vntol=100n"),
    )


def _reference_deck(ctx: Context) -> str:
    refs = (*_REFERENCE, *common.REFERENCE_LINE)
    circuit = ctx.circuit(refs, common.ALIASES, common.bias_models(ctx.netlist, refs))
    stimulus = "\n".join(
        [
            "V3a p3v3_a 0 DC 3.3 AC 1",
            "Vm4 m4v_a 0 -4",
            f"Iload vref 0 {common.REFERENCE_AMPS:g}",
        ]
    )
    return ctx.deck(
        "VREF: what passes from 3V3_A",
        circuit,
        stimulus,
        control=["op", "ac dec 30 1 10meg"],
    )


def _gain_db(run: RunResult, node: str, hertz: float) -> float:
    frequency = run.real("frequency", plot="ac")
    level = measure.decibels(run.vector(node, plot="ac"))
    return float(np.interp(np.log10(hertz), np.log10(frequency), level))


@bench(
    "analog_rails",
    "supply-noise",
    "Noise and ripple of +12V_A and -4V_A, and what passes from the rails ahead",
    "section 3 (analog rails), section 4.6, decision D-51; the rails feed the amplifier, "
    "the multiplexer and the buffers of sections 4.3 and 4.5",
)
def supply_noise(ctx: Context) -> Outcome:
    """Each analog rail is taken alone, at rest, with an ideal rail ahead of it.

    For +12V_A the regulator runs from a 13.53 V source through R37 and C29
    with 6.6 mA of load; a noise analysis gives the noise of the rail and a
    test signal on the source gives what the regulator lets through. For
    -4V_A the same is done with the averaged pump on a 5 V source, and a
    transient with the pump switch by switch gives the ripple. For the
    reference a test signal on 3V3_A gives what reaches VREF. The supply
    pins of the amplifier, of the multiplexer and of the buffers are on
    these rail nets without a part in between, so what the rail carries is
    what the pins see.
    """
    rested = ctx.run("positive-settle", _positive_settle_deck(ctx), keep=False)
    positive = ctx.run("positive", _positive_deck(ctx, common.nodeset(rested)))
    frequency = positive.real("frequency", plot="noise1")
    density = positive.real("onoise_spectrum", plot="noise1")
    figures = [
        near(
            "p12_level",
            "+12V_A at rest",
            float(positive.real("p12v_a", plot="op")[0]),
            "V",
            12.0,
            0.011,
            "section 3: 12.0 V; SET current 1 % and R38 0.1 % (datasheet, netlist)",
        ),
        Figure(
            "p12_noise_10",
            "+12V_A: noise density at 10 Hz",
            float(np.interp(10.0, frequency, density)),
            "V/√Hz",
        ),
        Figure(
            "p12_noise_10k",
            "+12V_A: noise density at 10 kHz",
            float(np.interp(1e4, frequency, density)),
            "V/√Hz",
        ),
        Figure(
            "p12_noise",
            "+12V_A: noise from 10 Hz to 100 kHz",
            measure.integrated_noise(frequency, density, 10.0, 1e5),
            "V",
        ),
    ]
    figures += [
        Figure(
            f"p12_reject_{hertz:g}".replace(".", "p").replace("+", ""),
            f"+12V_A: what passes from +13V5 at {hertz:g} Hz",
            _gain_db(positive, "p12v_a", hertz),
            "dB",
        )
        for hertz in _SPOTS
    ]
    settled = ctx.run("negative-settle", _negative_settle_deck(ctx), keep=False)
    negative = ctx.run("negative", _negative_small_deck(ctx, common.nodeset(settled)))
    n_frequency = negative.real("frequency", plot="noise1")
    n_density = negative.real("onoise_spectrum", plot="noise1")
    figures += [
        near(
            "m4_level",
            "-4V_A at rest",
            float(negative.real("m4v_a", plot="op")[0]),
            "V",
            -3.977,
            0.005,
            "datasheet equation of the pump with R34 and R36",
        ),
        Figure(
            "m4_noise",
            "-4V_A: noise from 10 Hz to 100 kHz",
            measure.integrated_noise(n_frequency, n_density, 10.0, 1e5),
            "V",
        ),
    ]
    for hertz in (1e3, 100e3, _BOOST_HERTZ):
        figures.append(
            Figure(
                f"m4_reject_{hertz:g}".replace(".", "p").replace("+", ""),
                f"-4V_A: what passes from the 5 V rail at {hertz:g} Hz",
                _gain_db(negative, "m4v_a", hertz),
                "dB",
            )
        )
    ripple = ctx.run("negative-ripple", _negative_ripple_deck(ctx))
    time = ripple.real("time")
    start, stop = 3.0e-3, 3.5e-3
    out = ripple.real("m4v_a")
    pump = ripple.real("cpout")
    figures += [
        Figure(
            "m4_ripple",
            "-4V_A: ripple that the pump lets through, peak to peak",
            measure.peak_to_peak(time, out, start, stop),
            "V",
        ),
        Figure(
            "cpout_ripple",
            "Output of the pump ahead of its regulator: ripple, peak to peak",
            measure.peak_to_peak(time, pump, start, stop),
            "V",
        ),
        Figure(
            "pump_in_ripple",
            "Supply pin of the pump behind R30: ripple, peak to peak",
            measure.peak_to_peak(time, ripple.real("pump_in"), start, stop),
            "V",
        ),
    ]
    reference = ctx.run("reference", _reference_deck(ctx), keep=False)
    for hertz in (1e3, 100e3, _BOOST_HERTZ):
        figures.append(
            Figure(
                f"vref_reject_{hertz:g}".replace(".", "p").replace("+", ""),
                f"VREF: what passes from 3V3_A at {hertz:g} Hz",
                _gain_db(reference, "vref", hertz),
                "dB",
            )
        )
    ac_frequency = positive.real("frequency", plot="ac")
    spectrum = Graph(
        name="spectrum",
        title="Noise of the two rails and what they let through from the rail ahead",
        xlabel="Frequency (Hz)",
        panels=(
            Panel("Noise density (nV/√Hz)", log=True),
            Panel("Passed from the rail ahead (dB)"),
        ),
        traces=(
            Trace(frequency, density * 1e9, "+12V_A", 0),
            Trace(n_frequency, n_density * 1e9, "-4V_A", 0),
            Trace(
                ac_frequency,
                measure.decibels(positive.vector("p12v_a", plot="ac")),
                "+13V5 to +12V_A",
                1,
            ),
            Trace(
                negative.real("frequency", plot="ac"),
                measure.decibels(negative.vector("m4v_a", plot="ac")),
                "5 V rail to -4V_A",
                1,
            ),
            Trace(
                reference.real("frequency", plot="ac"),
                measure.decibels(reference.vector("vref", plot="ac")),
                "3V3_A to VREF",
                1,
            ),
        ),
        logx=True,
    )
    shown = (time >= stop - 40e-6) & (time <= stop)
    micro = (time[shown] - time[shown][0]) * 1e6
    waves = Graph(
        name="pump",
        title="The charge pump at 8 mA of load: the last 40 us",
        xlabel="Time (us)",
        panels=(
            Panel("Ahead of the regulator, around the mean (mV)"),
            Panel("-4V_A around the mean (uV)"),
        ),
        traces=(
            Trace(micro, (pump[shown] - np.mean(pump[shown])) * 1e3, "output of the pump", 0),
            Trace(micro, (out[shown] - np.mean(out[shown])) * 1e6, "-4V_A", 1),
        ),
    )
    notes = (
        "Noise of +12V_A: the model holds the 2 nV/rtHz of the error amplifier and the "
        "20 pA/rtHz of the reference current of the datasheet, white. Below 100 Hz the "
        "reference current into the SET capacitor decides, and that capacitor is 1.45 uF "
        "at 12 V instead of 4.7 uF, so the rail is noisier there than the 0.8 uV RMS that "
        "the datasheet gives for 4.7 uF.",
        "What +12V_A lets through is the datasheet rejection of the regulator up to "
        "1 MHz with the filter R37 and C29 ahead of it. With the boost ripple of the "
        "boost-output bench (2.5 mV at 1.6 MHz and up to 5 mV of slow movement at a few "
        "kilohertz, the latter a property of the model) less than 0.2 uV reaches +12V_A "
        "by conduction. The edges of the switch node, which the datasheet of the "
        "regulator says pass it, and coupling through the board are not in a circuit "
        "simulation.",
        "Noise of -4V_A: the 20 uV RMS of the datasheet are put at the reference of the "
        "regulator as if measured at -1.8 V of output; at -4 V that gives the figure "
        "here. Read as a figure of the output itself it would be 20 uV RMS. The ripple "
        "of -4V_A is only what the pump ripple passes through an assumed feed-through "
        "that reproduces the 35 dB at 2 MHz of the datasheet; the datasheet shows 0.8 mV "
        "to 3.2 mV of ripple on a 2.2 uF output (figure 5-1), most of which is coupling "
        "that a circuit simulation does not hold. Scaled to the 6.2 uF of this rail that "
        "would be about 1 mV: the figure to budget with until it is measured.",
        "The pulse skipping of the pump has a hysteresis of 10 mV that is an assumption; "
        "it sets the ripple ahead of the regulator and the pace of the bursts.",
    )
    return Outcome(tuple(figures), (spectrum, waves), notes)
