"""The enable pin of the pre-regulator behind Q1, over the voltage of the 5 V rail."""

from __future__ import annotations

import numpy as np

from benches.source_meter import common
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_REFS = ("Q1", "R53", "R25", "R27", "R28")
"""Q1 with its source resistor, and the pull-up of 5V_OK with its divider load
(the last three are drawn on the analog rails sheet)."""

_PULL_DOWN = 1e6
"""Pull-down of the enable input of each LP5907 on the line 5V_OK (TI SNVS798)."""

_VARIANTS = (
    ("typical", ""),
    ("low", "SOURCE_METER_BSS138_LO"),
    ("high", "SOURCE_METER_BSS138_HI"),
)
"""Threshold of Q1: typical and the two limits of its datasheet."""

_THRESHOLD = 1.2
"""Level above which the enable pin counts as high (SLVS916I, page 6)."""

_LOW_LEVEL = 0.4
"""Level below which the enable pin counts as low (SLVS916I, page 6)."""

_POINTS = ((5.0, None), (4.25, 2.36), (3.83, 1.96))
"""Rail voltages of the figures and what section 4.2 calculates for them."""


def _deck(ctx: Context, model: str, smu_on: float) -> str:
    overrides = {"Q1": common.device(ctx, "Q1", model)} if model else None
    aliases = {**common.ALIASES, "Net-(U11-EN)": "pump_en"}
    circuit = ctx.circuit(_REFS, aliases, overrides)
    stimulus = "\n".join(
        [
            "* the 5 V rail swept; the supervisor has released 5V_OK, which the two",
            "* enable inputs of the 3.3 V regulators load with 1 Mohm each",
            "Vp5 p5v 0 5",
            f"Ren7 ok_5v 0 {_PULL_DOWN:g}",
            f"Ren8 ok_5v 0 {_PULL_DOWN:g}",
            "* SMU_ON: a pin of the controller behind its output resistance",
            f"Vsmu smu_pin 0 {smu_on:g}",
            f"Rsmu smu_pin smu_on {common.PAD_OHMS:g}",
        ]
    )
    return ctx.deck(
        "Enable pin of the pre-regulator over the 5 V rail",
        circuit,
        stimulus,
        control=["dc Vp5 0 5.5 0.01"],
    )


def _at(run: RunResult, name: str, volts: float) -> float:
    return float(np.interp(volts, run.real("v-sweep"), run.real(name)))


@bench(
    "source_meter",
    "enable",
    "The enable pin of the pre-regulator behind Q1, over the 5 V rail",
    "section 4.2 (enable), decision D-48",
)
def enable(ctx: Context) -> Outcome:
    """Q1 with its resistors is taken alone and the 5 V rail is swept from 0 V to 5.5 V.

    The gate of Q1 is the line 5V_OK, which R25 pulls up to the rail
    against the divider of the charge pump and the enable inputs of the two
    3.3 V regulators. The controller holds SMU_ON at 3.3 V. The sweep gives
    the voltage of the enable pin at the nominal rail, at 4.25 V and at the
    lowest threshold of the supervisor, with a typical transistor and with
    the threshold at both limits of its datasheet. One more sweep holds
    SMU_ON low.
    """
    runs = {
        name: ctx.run(
            f"sweep-{name}", _deck(ctx, model, common.LOGIC_VOLTS), keep=name == "typical"
        )
        for name, model in _VARIANTS
    }
    off = ctx.run("sweep-off", _deck(ctx, "", 0.0), keep=False)
    figures = [
        Figure(
            "gate_share",
            "Line 5V_OK as a share of the 5 V rail, at 5 V",
            100.0 * _at(runs["typical"], "ok_5v", 5.0) / 5.0,
            "%",
            expected=100.0 * common.OK_SHARE,
            low=93.0,
            high=95.5,
            source="calculated from R25, R27, R28 and the two pull-downs of 1 Mohm",
        )
    ]
    for volts, expected in _POINTS:
        for name, _ in _VARIANTS:
            tag = f"{volts:g}v_{name}".replace(".", "p")
            figures.append(
                Figure(
                    f"enable_{tag}",
                    f"Enable pin at {volts:g} V on the rail, {name} threshold of Q1",
                    _at(runs[name], "smu_en", volts),
                    "V",
                    expected=expected if name == "high" else None,
                    low=_THRESHOLD,
                    source="section 4.2: 2.36 V at 4.25 V and 1.96 V at the lowest supervisor "
                    "threshold (calculated, with an estimate of the gate threshold), against "
                    "1.2 V",
                )
            )
    figures += [
        Figure(
            "enable_off",
            "Enable pin with SMU_ON low, rail at 5 V",
            _at(off, "smu_en", 5.0),
            "V",
            high=_LOW_LEVEL,
            source="SLVS916I, page 6: low below 0.4 V",
        ),
        Figure(
            "pin_current",
            "Current that the pin SMU_ON delivers, rail at 5 V, typical transistor",
            _at(runs["typical"], "smu_en", 5.0) / 1000.0,
            "A",
        ),
    ]
    rail = runs["typical"].real("v-sweep")
    graph = Graph(
        name="sweep",
        title="Enable pin of the pre-regulator over the 5 V rail, SMU_ON at 3.3 V",
        xlabel="5 V rail (V)",
        panels=(Panel("Enable pin (V)", marks=((_THRESHOLD, "high above 1.2 V"),)),),
        traces=(
            *(
                Trace(rail, runs[name].real("smu_en"), f"{name} threshold of Q1", 0)
                for name, _ in _VARIANTS
            ),
            Trace(rail, runs["typical"].real("ok_5v"), "line 5V_OK", 0, "--"),
        ),
        xmarks=((3.83, "3.83 V"), (4.25, "4.25 V")),
    )
    notes = (
        "The supervisor is not in this circuit: its output is released for the whole "
        "sweep, so the curve shows what Q1 passes, not when the supervisor lets it. "
        "Below its threshold the supervisor pulls 5V_OK low and the pin is at 0 V.",
        "The converter takes no current at its enable pin that counts (0.1 uA at the "
        "most, datasheet) and is left out; R53 is the load.",
        "The three models of Q1 differ in the threshold alone: 0.5 V, typical and 1.5 V "
        "at 250 uA (datasheet limits at 25 C). The pin of the controller is 3.3 V "
        "behind 33 ohm (assumption).",
    )
    return Outcome(tuple(figures), (graph,), notes)
