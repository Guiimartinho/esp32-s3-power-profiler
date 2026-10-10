"""The VIN terminal with the ampere pair open: -20 V to +20 V, slowly and at a plug-in edge."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.path_switching import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_SEGMENT = 40e-3
"""Time of each ramp of the slow sweep, s: 0.5 V/ms."""

_HOLD = 10e-3
"""Time the sweep rests at each end, s: the gate network settles within 3 ms."""

_AT_PLUS = _SEGMENT + _HOLD
"""Instant at which the values at +20 V are read: the end of the rest there."""

_AT_MINUS = 3 * _SEGMENT + 2 * _HOLD
"""Instant at which the values at -20 V are read."""

_AT_FIVE = 0.25 * _SEGMENT
"""Instant at which the rising sweep passes 5 V."""

_END = 4 * _SEGMENT + 2 * _HOLD

_CEILING = 5.26
"""Highest output of the regulator that the set-point path can command, V (section 4.2)."""

_RATED = 20.0
"""Voltage the terminal withstands either way, V (requirement R-09)."""

_STATES = ("idle", "off", "source")
"""Instrument idle with its rails, without any supply, and with source mode running."""

_STATE_TEXT = {
    "idle": "instrument idle",
    "off": "instrument without supply",
    "source": "source mode running at 5.26 V",
}


def _rails(state: str) -> str:
    """The rails of a state: all present, or all at 0 V."""
    if state == "off":
        return (
            "* no supply: every rail held at 0 V by its loads\n"
            "Vp12 p12v_a 0 0\nVm4 m4v_a 0 0\nVp3v3a p3v3_a 0 0\nVref vref 0 0\n"
        )
    return common.rails()


def _sources(state: str) -> str:
    """Regulator stand-in and requests of a state."""
    if state == "source":
        return common.regulator(_CEILING) + common.requests(source=((0.0, True),))
    return common.no_regulator() + common.requests()


def _sweep_deck(ctx: Context, state: str) -> str:
    """The terminal is taken slowly to +20 V, back, to -20 V and back."""
    ramp, hold = _SEGMENT, _HOLD
    stimulus = (
        "* the terminal driven by a source without leads\n"
        f"Vin vin_src 0 PWL(0 0 {ramp:g} {_RATED:g} {ramp + hold:g} {_RATED:g} "
        f"{2 * ramp + hold:g} 0 {3 * ramp + hold:g} {-_RATED:g} "
        f"{3 * ramp + 2 * hold:g} {-_RATED:g} {_END:g} 0)\n"
        "Vlead vin_src vin_raw 0\n" + _sources(state)
    )
    control = [
        "save vin_p det vin_ov g_amp s_amp b_amp supply ldo_out amp_in vin_mon "
        "vlead#branch @qq7[ic] @qq7[ib] @d.xd14.d1[id] @dd15_1[id] @dd15_2[id] @mq5[id]",
        f"tran 20u {_END:g} 0 50u",
    ]
    return common.deck(
        ctx,
        f"VIN terminal from -20 V to +20 V, {_STATE_TEXT[state]}",
        common.circuit(ctx, ladder=False),
        _rails(state),
        stimulus,
        control=control,
    )


@dataclass(frozen=True, slots=True)
class _Point:
    """The circuit at one end of the sweep.

    Attributes:
        amps: Current into the terminal.
        detector: Voltage at the detector input.
        output: Voltage of the detector output.
        drive: Gate-source voltage of the ampere pair.
        node: Voltage of the supply node.
        supply_side: Voltage across the transistor on the supply side.
        ladder_side: Voltage across the transistor on the ladder side.
        hold_off: Collector current of the hold-off transistor.
    """

    amps: float
    detector: float
    output: float
    drive: float
    node: float
    supply_side: float
    ladder_side: float
    hold_off: float


def _point(run: RunResult, instant: float) -> _Point:
    """The circuit at one instant of the sweep."""
    time = run.real("time")

    def at(values: np.ndarray) -> float:
        return measure.value_at(time, values, instant)

    source = run.real("s_amp")
    return _Point(
        amps=at(run.real("vlead#branch")),
        detector=at(run.real("det")),
        output=at(run.real("vin_ov")),
        drive=at(run.real("g_amp") - source),
        node=at(run.real("supply")),
        supply_side=at(run.real("vin_p") - source),
        ladder_side=at(run.real("supply") - source),
        hold_off=at(run.real("@qq7[ic]")),
    )


@bench(
    "path_switching",
    "withstand",
    "The VIN terminal from -20 V to +20 V with the ampere pair open",
    "requirement R-09, section 4.9 (VIN, D-60; hold-off below ground, D-61), sections 11 and 16",
)
def withstand(ctx: Context) -> Outcome:
    """The VIN terminal is taken slowly to +20 V and to -20 V with the ampere pair open.

    Three states of the instrument are run: idle with its rails present,
    without any supply, and with source mode running at the highest output
    the set-point path can command. The run shows the current that the
    terminal takes, where it flows, and the voltages across the two
    transistors of the pair. The sweep moves at 0.5 V/ms and rests 10 ms at
    each end, where the values are read.
    """
    runs = ctx.run_many({state: _sweep_deck(ctx, state) for state in _STATES[1:]})
    runs["idle"] = ctx.run("idle", _sweep_deck(ctx, "idle"))
    figures: list[Figure] = []
    traces: list[Trace] = []
    for state in _STATES:
        run = runs[state]
        text = _STATE_TEXT[state]
        plus = _point(run, _AT_PLUS)
        minus = _point(run, _AT_MINUS)
        five = _point(run, _AT_FIVE)
        figures += [
            Figure(
                f"plus_{state}",
                f"Current into the terminal at +20 V, {text}",
                plus.amps,
                "A",
                expected=0.19e-3 if state != "off" else None,
                high=1e-3,
                source="section 4.9: less than 1 mA; 0.19 mA at +20 V, simulated",
            ),
            Figure(
                f"minus_{state}",
                f"Current out of the terminal at -20 V, {text}",
                -minus.amps,
                "A",
                expected=0.64e-3 if state != "off" else None,
                high=1e-3,
                source="section 4.9: less than 1 mA; 0.64 mA at -20 V, simulated",
            ),
            Figure(
                f"drive_{state}",
                f"Gate-source voltage of the ampere pair at -20 V, {text}",
                minus.drive,
                "V",
                high=0.3,
                source="section 4.9: the hold-off transistor joins gate and common source "
                "(limit of this bench: well below the lowest threshold of 1.1 V)",
            ),
            Figure(
                f"input_low_{state}",
                f"Detector input at -20 V, {text}",
                minus.detector,
                "V",
                low=-1.0,
                source="section 16: input pin above -1.0 V with -20 V",
            ),
            Figure(
                f"input_high_{state}",
                f"Detector input above its supply at +20 V, {text}",
                plus.detector - (0.0 if state == "off" else 3.3),
                "V",
                high=1.0,
                source="rating of the comparator input, supply plus 1.0 V "
                "(Microchip DS20002139E, page 3)",
            ),
            Figure(
                f"supply_side_{state}",
                f"Voltage across the transistor on the supply side at +20 V, {text}",
                plus.supply_side,
                "V",
                high=common.TRANSISTOR_VOLTS,
                source="rating of the CSD17577Q3A, 30 V (TI SLPS515A, page 1)",
            ),
            Figure(
                f"ladder_side_{state}",
                f"Voltage across the transistor on the ladder side at -20 V, {text}",
                minus.ladder_side,
                "V",
                expected=25.3 if state == "source" else None,
                high=common.TRANSISTOR_VOLTS,
                source="section 4.9: 25.3 V with source mode at its ceiling, calculated"
                if state == "source"
                else "rating of the CSD17577Q3A, 30 V (TI SLPS515A, page 1)",
            ),
            Figure(
                f"node_{state}",
                f"Largest change of the supply node over the sweep, {text}",
                float(np.max(np.abs(run.real("supply") - run.real("supply")[0]))),
                "V",
                high=0.01,
                source="section 11: TP33 unchanged; 10 mV asked here",
            ),
        ]
        if state == "idle":
            figures += [
                Figure(
                    "output_high",
                    "Detector output at +20 V, instrument idle",
                    plus.output,
                    "V",
                    low=3.0,
                    source="section 16: TP30 steady high with +20 V on VIN and power on; 3.0 V "
                    "asked here",
                ),
                Figure(
                    "open_5v",
                    "Current into the terminal at 5 V with the pair open, instrument idle",
                    five.amps,
                    "A",
                    expected=35e-6,
                    low=33e-6,
                    high=37e-6,
                    source="section 4.9: 35 uA from a 5 V supply, calculated; 5 % asked here",
                ),
                Figure(
                    "hold_off_current",
                    "Collector current of the hold-off transistor at -20 V, instrument idle",
                    minus.hold_off,
                    "A",
                    source="",
                ),
            ]
        if state == "off":
            figures.append(
                Figure(
                    "off_5v",
                    "Current into the terminal at 5 V, instrument without supply",
                    five.amps,
                    "A",
                    expected=49e-6,
                    low=44e-6,
                    high=54e-6,
                    source="section 4.9: about 49 uA, the clamp of the detector conducts "
                    "into the dead 3V3_A, calculated; 10 % asked here",
                )
            )
        traces.append(Trace(run.real("vin_p"), run.real("vlead#branch") * 1e3, text, 0))
    idle = runs["idle"]
    curve = Graph(
        name="terminal",
        title="Current into the VIN terminal against its voltage, ampere pair open",
        xlabel="Voltage on VIN behind the fuse (V)",
        panels=(Panel("Current into the terminal (mA)", marks=((1.0, "1 mA"), (-1.0, "-1 mA"))),),
        traces=tuple(traces),
    )
    time = idle.real("time") * 1e3
    inside = Graph(
        name="idle",
        title="The sweep with the instrument idle: detector and ampere pair",
        xlabel="Time (ms)",
        panels=(
            Panel("VIN behind the fuse (V)"),
            Panel("Detector (V)"),
            Panel("Ampere pair (V)"),
        ),
        traces=(
            Trace(time, idle.real("vin_p"), "", 0),
            Trace(time, idle.real("det"), "detector input", 1),
            Trace(time, idle.real("vin_ov"), "detector output VIN_OV (TP30)", 1),
            Trace(time, idle.real("g_amp"), "gate (TP32)", 2),
            Trace(time, idle.real("s_amp"), "common source", 2, "--"),
            Trace(time, idle.real("b_amp"), "base of the hold-off transistor", 2, ":"),
        ),
    )
    notes = (
        "What takes the current at +20 V: the divider of the detector with its clamp "
        "D15 into 3V3_A (0.14 mA) and the divider of the VIN monitor (0.05 mA). At "
        "-20 V the hold-off transistor adds its base current through R86 and the "
        "current of R80 from the driver output, about 0.2 mA each.",
        "No rail has a load in these runs: a dead rail is a source of 0 V, which "
        "stands for the loads that hold it there. A live 3V3_A takes the clamp "
        "current of 0.1 mA without rising, which a real regulator does only while "
        "its loads take more than that.",
        "The models say nothing about leakage: the currents here are those of the "
        "resistors. The transistor models have no breakdown; the voltages across "
        "them are compared with the 30 V rating.",
        "The suppressor D14 does not conduct at 20 V in the model (breakdown at "
        "23.35 V, 22.2 V at the least by its datasheet).",
    )
    return Outcome(tuple(figures), (curve, inside), notes)
