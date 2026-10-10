"""The OPA197 model with a capacitive load, against the table of its datasheet."""

from __future__ import annotations

import numpy as np

from benches.output_stage import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import Circuit

_DOCUMENT = "TI SBOS737C"
"""The datasheet the figures are taken from."""

_CASES = (
    (1e-9, 24.0, 45.0, 22.5),
    (1e-9, 100.0, 60.0, 9.0),
    (10e-9, 20.0, 45.0, 22.1),
    (10e-9, 51.0, 60.0, 8.7),
    (100e-9, 6.2, 45.0, 23.1),
    (100e-9, 15.8, 60.0, 8.6),
    (1e-6, 2.0, 45.0, 21.0),
    (1e-6, 4.7, 60.0, 8.6),
)
"""Table 3, page 23: load capacitance, isolation resistor, phase margin in
degrees and measured overshoot in percent."""

_BOARD = (100e-9, 47.0)
"""Load capacitance and isolation resistor of the guard buffer on the board."""

_MARGIN_BAND = 10.0
"""Distance from the phase margin of the table that this project accepts, degrees."""

_OVERSHOOT_BAND = 8.0
"""Distance from the overshoot of the table that this project accepts, percent."""

_STEP_VOLTS = 0.1
"""Height of the output step of the overshoot test (figure 28)."""

_STEP_AT = 20e-6
"""Instant of the step."""


def _device(ctx: Context, **probe: float) -> Circuit:
    """The buffer alone, on the nodes buf_in and buf_out, with its probe sources."""
    return ctx.circuit([common.BUFFER], common.ALIASES, common.buffer_probe(ctx, **probe))


def _load(farads: float, ohms: float) -> str:
    return "\n".join(
        [
            "* the load of the datasheet: an isolation resistor, a capacitor, 10 kohm",
            f"Riso buf_out cl {ohms:g}",
            f"Cl cl 0 {farads:g}",
            "Rl cl 0 10k",
        ]
    )


def _ac_deck(ctx: Context, farads: float, ohms: float, **probe: float) -> str:
    return ctx.deck(
        "OPA197: loop gain with a capacitive load",
        _device(ctx, **probe),
        _rails(),
        "Vin buf_in 0 0",
        _load(farads, ohms),
        control=["ac dec 60 100 100meg"],
        options=common.buffer_options(ctx),
        libraries=common.buffer_libraries(ctx),
    )


def _step_deck(ctx: Context, farads: float, ohms: float) -> str:
    stop = _STEP_AT + max(60e-6, 60.0 * ohms * farads)
    return ctx.deck(
        "OPA197: step with a capacitive load",
        _device(ctx),
        _rails(),
        f"Vin buf_in 0 PWL(0 0 {_STEP_AT:g} 0 {_STEP_AT + 20e-9:g} {_STEP_VOLTS:g})",
        _load(farads, ohms),
        control=[f"tran {stop / 20000:g} {stop:g} 0 {stop / 20000:g}"],
        options=common.buffer_options(ctx),
        libraries=common.buffer_libraries(ctx),
    )


def _rails() -> str:
    return "\n".join(["* the rails of the board", "Vp12 p12v_a 0 12", "Vm4 m4v_a 0 -4"])


def _tag(farads: float, ohms: float) -> str:
    return f"{farads * 1e9:g}n_{ohms:g}r".replace(".", "p")


@bench(
    "models",
    "output-stage-buffer",
    "OPA197 model with a capacitive load behind an isolation resistor",
    "the model of the guard buffer U25 in the use the output stage makes of it",
)
def buffer(ctx: Context) -> Outcome:
    """The buffer of the schematic drives the loads of table 3 of its datasheet.

    The datasheet gives, for a capacitor behind an isolation resistor, the
    resistor that leaves 45 degrees and the one that leaves 60 degrees of
    phase margin, with the overshoot measured for a step of 100 mV. The
    guard buffer works in that circuit, with 47 ohm and 100 nF, so this is
    the property of the model that the output stage rests on. The loop
    gain is taken by double injection at the output of the amplifier, with
    the feedback closed, and the step is run in the same circuit. The last
    row is the load of the board, for which the table has no entry.
    """
    decks = {}
    cases = [(farads, ohms) for farads, ohms, _, _ in _CASES] + [_BOARD]
    for farads, ohms in cases:
        tag = _tag(farads, ohms)
        decks[f"series-{tag}"] = _ac_deck(ctx, farads, ohms, vac=1.0)
        decks[f"shunt-{tag}"] = _ac_deck(ctx, farads, ohms, iac=1.0)
        decks[f"step-{tag}"] = _step_deck(ctx, farads, ohms)
    ctx.run("series-100n-15p8r", decks[f"series-{_tag(100e-9, 15.8)}"])
    runs = ctx.run_many(decks)
    figures: list[Figure] = []
    traces: list[Trace] = []
    step_traces: list[Trace] = []
    expected = {(farads, ohms): (margin, shoot) for farads, ohms, margin, shoot in _CASES}
    for farads, ohms in cases:
        tag = _tag(farads, ohms)
        frequency, loop = common.loop_gain(runs[f"series-{tag}"], runs[f"shunt-{tag}"])
        crossover, margin = measure.stability_margins(frequency, loop)
        step = runs[f"step-{tag}"]
        time, load = step.real("time"), step.real("cl")
        shoot = round(100.0 * measure.overshoot(time, load, 0.0, float(load[-1]), _STEP_AT), 3)
        text = f"{farads * 1e9:g} nF behind {ohms:g} ohm"
        wanted = expected.get((farads, ohms))
        if wanted is None:
            figures += [
                Figure(f"margin_{tag}", f"Load of the board, {text}: phase margin", margin, "deg"),
                Figure(
                    f"crossover_{tag}", f"Load of the board, {text}: crossover", crossover, "Hz"
                ),
                Figure(f"overshoot_{tag}", f"Load of the board, {text}: overshoot", shoot, "%"),
            ]
        else:
            figures += [
                Figure(
                    f"margin_{tag}",
                    f"{text}: phase margin",
                    margin,
                    "deg",
                    expected=wanted[0],
                    low=wanted[0] - _MARGIN_BAND,
                    high=wanted[0] + _MARGIN_BAND,
                    source=f"{_DOCUMENT}, table 3, page 23",
                ),
                Figure(
                    f"overshoot_{tag}",
                    f"{text}: overshoot of a 100 mV step",
                    shoot,
                    "%",
                    expected=wanted[1],
                    low=max(0.0, wanted[1] - _OVERSHOOT_BAND),
                    high=wanted[1] + _OVERSHOOT_BAND,
                    source=f"{_DOCUMENT}, table 3, page 23, measured",
                ),
            ]
        if farads == 100e-9:
            label = f"{ohms:g} ohm"
            traces.append(Trace(frequency, measure.decibels(loop), label, 0))
            traces.append(Trace(frequency, measure.phase_degrees(loop) + 180.0, label, 1))
            shown = (time >= _STEP_AT - 2e-6) & (time <= _STEP_AT + 40e-6)
            step_traces.append(
                Trace((time[shown] - _STEP_AT) * 1e6, np.asarray(load[shown] * 1e3), label, 0)
            )
    unloaded_series = ctx.run("series-open", _ac_deck(ctx, 1e-15, 1e-3, vac=1.0), keep=False)
    unloaded_shunt = ctx.run("shunt-open", _ac_deck(ctx, 1e-15, 1e-3, iac=1.0), keep=False)
    frequency, loop = common.loop_gain(unloaded_series, unloaded_shunt)
    crossover, margin = measure.stability_margins(frequency, loop)
    figures += [
        Figure(
            "unity_gain",
            "Without a capacitor: frequency at which the loop gain is 1",
            crossover,
            "Hz",
            expected=10e6,
            low=8e6,
            high=12e6,
            source=f"{_DOCUMENT}, page 8: unity gain bandwidth 10 MHz",
        ),
        Figure("margin_open", "Without a capacitor: phase margin", margin, "deg"),
    ]
    bode = Graph(
        name="loop",
        title="OPA197 follower with 100 nF behind an isolation resistor: loop gain",
        xlabel="Frequency (Hz)",
        panels=(Panel("Loop gain (dB)", marks=((0.0, "0 dB"),)), Panel("Phase above -180 (deg)")),
        traces=tuple(traces),
        logx=True,
    )
    steps = Graph(
        name="step",
        title="OPA197 follower with 100 nF behind an isolation resistor: 100 mV step",
        xlabel="Time after the step (us)",
        panels=(Panel("Voltage at the capacitor (mV)", marks=((100.0, "final value"),)),),
        traces=tuple(step_traces),
    )
    notes = (
        "The limits are the fit this project asks of the model: 10 degrees around the "
        "phase margin of the table and 8 points around its overshoot. They are not "
        "datasheet limits.",
        "What fails is a limit of the model, not of the board. Where the table gives "
        "45 degrees the model is close. Where the table gives 60 degrees the model "
        "leaves 15 to 30 degrees more, and no overshoot where 9 % were measured: an "
        "output impedance that is a resistance up to 1 MHz, as figure 26 of the "
        "datasheet shows it, does not reproduce that column. The model is too "
        "optimistic once the isolation resistor is larger than the value for 45 "
        "degrees.",
        "The guard buffer has 47 ohm in front of 100 nF, three times the resistor of "
        "the 60 degree row of the table. Its margin is therefore above 60 degrees by "
        "the table itself; the figure that the model gives for the board is too high "
        "by what the 60 degree rows show. In the vendor tier the model of the "
        "manufacturer is further from the table than the one written here, on the "
        "optimistic side in every row.",
        "The rails are those of the board, +12 V and -4 V; the datasheet states the "
        "table for +18 V and -18 V. The model does not depend on its rails.",
    )
    return Outcome(tuple(figures), (bode, steps), notes)
