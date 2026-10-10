"""Frequency response: the input filter and the anti-alias filter."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from benches import frontend
from benches.signal_chain import common
from circuit_sim import measure, tolerance
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.engine import RunResult

_BIAS = "0.05"
"""Shunt voltage of the operating point: the chain works in its linear range."""

_SWEEP = "ac dec 60 10 200meg"
"""Frequencies of every run."""

_DRAWS = 60
"""Boards of the tolerance run of the anti-alias filter."""

_SEED = 20261011
"""Seed of the tolerance run."""

_CAPACITOR_TOLERANCE = 0.05
"""Tolerance of the C0G capacitors of the filters: the J parts of the netlist."""

_SAMPLE_RATE = 100e3
"""Sample rate of the instrument."""


def _deck(
    ctx: Context,
    title: str,
    *,
    mux_ohms: float,
    common_mode: bool,
    scales: Mapping[str, float] | None = None,
) -> str:
    shunt = f"dc {_BIAS} ac 0" if common_mode else f"dc {_BIAS} ac 1"
    vout = "dc 3.3 ac 1" if common_mode else "3.3"
    return ctx.deck(
        title,
        common.chain(ctx, mux_ohms=mux_ohms, scales=scales),
        frontend.rails(),
        common.taps({0: shunt}, vout),
        common.address(0),
        control=[_SWEEP],
        libraries=common.LIBRARIES,
    )


def _filter(result: RunResult) -> tuple[float, float]:
    """Natural frequency and Q of the filter, from the driver output over the amplifier output."""
    frequency = result.real("frequency")
    response = result.vector("adc_drv") / result.vector("amp_raw")
    phase = measure.phase_degrees(np.asarray(response, dtype=np.complex128))
    log_f = np.log10(frequency)
    natural = 10.0 ** measure.first_crossing(log_f, phase, -90.0, rising=False)
    quality = float(np.interp(np.log10(natural), log_f, np.abs(response)))
    return natural, quality


@bench(
    "signal_chain",
    "frequency",
    "Frequency response: input filter and anti-alias filter",
    "section 4.5 (input filter D-65, anti-alias filter), section 4.3 (multiplexer resistance)",
)
def frequency(ctx: Context) -> Outcome:
    """Small-signal runs around a shunt voltage of 50 mV in range 0.

    A source across the shunt gives the response to the signal: from the
    shunt to the amplifier inputs (the input filter, with 125 ohm, 250 ohm
    and 430 ohm in a multiplexer channel), from the amplifier output to the
    driver output (the anti-alias filter) and from the shunt to the
    converter input. A source on the node after the shunts moves both sense
    taps together and gives the response of the input filter to the common
    mode. The parts of the anti-alias filter are then drawn 60 times inside
    their tolerances.
    """
    runs = {
        ohms: ctx.run(
            f"signal-{ohms:g}r",
            _deck(
                ctx,
                f"Signal chain: response to the shunt voltage, {ohms:g} ohm per channel",
                mux_ohms=ohms,
                common_mode=False,
            ),
            keep=ohms == 250.0,
        )
        for ohms in common.MUX_OHMS
    }
    nominal = runs[250.0]
    freq = nominal.real("frequency")
    figures: list[Figure] = []
    traces: list[Trace] = []
    expected_tau = {125.0: 0.06e-6, 250.0: 0.12e-6, 430.0: 0.20e-6}
    for ohms, run in runs.items():
        at_inputs = np.asarray(run.vector("inp") - run.vector("inn"), dtype=np.complex128)
        corner = measure.corner_frequency(freq, at_inputs)
        tag = f"{ohms:g}r"
        if ohms == 250.0:
            figures.append(
                near(
                    "input_corner",
                    "Input filter, signal: corner with 250 ohm per channel",
                    corner,
                    "Hz",
                    1.35e6,
                    0.05,
                    "section 4.5, D-65: 1.35 MHz",
                )
            )
        figures.append(
            near(
                f"input_tau_{tag}",
                f"Input filter, signal: time constant with {ohms:g} ohm per channel",
                1.0 / (2.0 * np.pi * corner),
                "s",
                expected_tau[ohms],
                0.1,
                "section 4.5: 0.06 us to 0.20 us over 125 ohm to 430 ohm",
            )
        )
        traces.append(Trace(freq, measure.decibels(at_inputs), f"signal, {ohms:g} ohm", 0))

    cm = ctx.run(
        "common-mode",
        _deck(
            ctx,
            "Signal chain: both sense taps moved together, 250 ohm per channel",
            mux_ohms=250.0,
            common_mode=True,
        ),
    )
    both = np.asarray(0.5 * (cm.vector("inp") + cm.vector("inn")), dtype=np.complex128)
    cm_corner = measure.corner_frequency(freq, both)
    figures.append(
        near(
            "input_corner_cm",
            "Input filter, common mode: corner with 250 ohm per channel",
            cm_corner,
            "Hz",
            20e6,
            0.1,
            "section 4.5, D-65: 20 MHz",
        )
    )
    traces.append(Trace(freq, measure.decibels(both), "common mode, 250 ohm", 0, "--"))

    natural, quality = _filter(nominal)
    section = np.asarray(nominal.vector("adc_drv") / nominal.vector("amp_raw"), dtype=np.complex128)
    whole = np.asarray(nominal.vector("adc_in"), dtype=np.complex128)
    whole_db = measure.decibels(whole)
    figures += [
        near(
            "filter_frequency",
            "Anti-alias filter: natural frequency",
            natural,
            "Hz",
            40e3,
            0.03,
            "section 4.5: two poles at 40 kHz",
        ),
        near(
            "filter_q",
            "Anti-alias filter: Q",
            quality,
            "",
            0.74,
            0.03,
            "section 4.5: Q = 0.74",
        ),
        Figure(
            "filter_peaking",
            "Anti-alias filter: rise above its level at low frequency",
            measure.peaking_db(section),
            "dB",
        ),
        Figure(
            "chain_gain",
            "Whole chain: gain at 10 Hz",
            float(np.abs(whole[0])),
            "",
            expected=common.GAIN,
            low=common.GAIN * 0.999,
            high=common.GAIN * 1.001,
            source="section 4.5: 19.93",
        ),
        Figure(
            "chain_corner",
            "Whole chain: frequency at which the response is 3 dB down",
            measure.corner_frequency(freq, whole),
            "Hz",
        ),
        Figure(
            "chain_at_nyquist",
            "Whole chain: response at half the sample rate, below its level at 10 Hz",
            float(whole_db[0] - np.interp(np.log10(_SAMPLE_RATE / 2), np.log10(freq), whole_db)),
            "dB",
        ),
        Figure(
            "chain_at_rate",
            "Whole chain: response at the sample rate, below its level at 10 Hz",
            float(whole_db[0] - np.interp(np.log10(_SAMPLE_RATE), np.log10(freq), whole_db)),
            "dB",
        ),
        Figure(
            "chain_at_1mhz",
            "Whole chain: response at 1 MHz, below its level at 10 Hz",
            float(whole_db[0] - np.interp(6.0, np.log10(freq), whole_db)),
            "dB",
        ),
    ]

    refs = ("R125", "R128", "C85", "C87")
    spread = tolerance.tolerances(ctx.netlist, refs, default={"C": _CAPACITOR_TOLERANCE})
    rng = np.random.default_rng(_SEED)
    decks = {
        f"board{draw:02d}": _deck(
            ctx,
            "Signal chain: anti-alias filter with its tolerances",
            mux_ohms=250.0,
            common_mode=False,
            scales=tolerance.draw_scales(spread, rng),
        )
        for draw in range(_DRAWS)
    }
    boards = [_filter(run) for run in ctx.run_many(decks).values()]
    naturals = np.array([board[0] for board in boards])
    qualities = np.array([board[1] for board in boards])
    figures += [
        Figure(
            "filter_frequency_low",
            f"Anti-alias filter: lowest natural frequency of {_DRAWS} boards",
            float(naturals.min()),
            "Hz",
        ),
        Figure(
            "filter_frequency_high",
            f"Anti-alias filter: highest natural frequency of {_DRAWS} boards",
            float(naturals.max()),
            "Hz",
        ),
        Figure(
            "filter_q_low",
            f"Anti-alias filter: lowest Q of {_DRAWS} boards",
            float(qualities.min()),
            "",
        ),
        Figure(
            "filter_q_high",
            f"Anti-alias filter: highest Q of {_DRAWS} boards",
            float(qualities.max()),
            "",
        ),
    ]
    traces += [
        Trace(freq, measure.decibels(section), "anti-alias filter, driver over amplifier", 1),
        Trace(freq, whole_db - whole_db[0], "whole chain, converter input over shunt", 1, "--"),
    ]
    graph = Graph(
        name="response",
        title="Signal chain: frequency response",
        xlabel="Frequency (Hz)",
        panels=(
            Panel("Input filter, at the amplifier inputs (dB)", marks=((-3.0, "-3 dB"),)),
            Panel("Relative to the level at 10 Hz (dB)", marks=((-3.0, "-3 dB"),)),
        ),
        traces=tuple(traces),
        logx=True,
        xmarks=((_SAMPLE_RATE / 2, "half the sample rate"),),
    )
    notes = (
        "The ladder is not in this circuit: ideal sources stand on the inputs of the "
        "multiplexer, so the source of the input filter is the channel resistance alone.",
        "The multiplexer model has a fixed resistance per channel and 6.7 pF at each output; "
        "the amplifier model has 3 pF between its inputs and 3 pF from each input. The "
        "capacitance of the tracks is not in the circuit; with 22 pF from each input to "
        "ground it moves the common-mode corner.",
        "The tolerance of the two filter capacitors is taken as 5 %, the tolerance of their "
        "part numbers; the netlist value does not state it. The limits of the natural "
        "frequency and of Q are the fit that this bench asks of the nominal circuit, 3 %.",
        "The amplifier model has two poles and gives 6.4 MHz at this gain; it does not have "
        "the peaking near 8 MHz that the datasheet shows at low gain.",
    )
    return Outcome(tuple(figures), (graph,), notes)
