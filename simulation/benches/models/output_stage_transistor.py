"""The limit variants of the CSD17577Q3A model against its datasheet."""

from __future__ import annotations

import numpy as np

from benches.output_stage import common
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.circuit import Circuit, PartModel

_REF = "Q15"
"""The part of the schematic that stands for its type."""

_DOCUMENT = "TI SLPS515A, page 3"
"""The datasheet the figures are taken from."""

_THRESHOLD_AMPS = 250e-6
"""Drain current at which the datasheet states the threshold."""

_THRESHOLDS = {"LO": 1.1, "HI": 1.8}
"""Limits of the gate threshold, by variant."""

_ON_POINTS = ((4.5, 10.0, 6.4e-3), (10.0, 16.0, 4.8e-3))
"""Upper limits of the on-resistance: gate voltage, drain current, resistance."""

_GATE_VOLTS = np.linspace(0.8, 3.2, 49)
"""Gate voltages of the transfer curve."""

_TRANSFER_DRAIN_VOLTS = 5.0
"""Drain voltage of the transfer curve (figure 3 of the datasheet)."""


def _device(ctx: Context, model: PartModel | None) -> Circuit:
    """The transistor alone, on the nodes d, g and s."""
    found = ctx.netlist.component(_REF)
    aliases = {found.net_of("D"): "d", found.net_of("G"): "g", found.net_of("S"): "s"}
    return ctx.circuit([_REF], aliases, {_REF: model} if model is not None else None)


def _threshold_deck(ctx: Context, model: PartModel | None) -> str:
    stimulus = "\n".join(
        [
            "* threshold: gate tied to drain, drain current forced",
            "Vs s 0 0",
            "Vgd g d 0",
            f"Id 0 d {_THRESHOLD_AMPS:g}",
        ]
    )
    return ctx.deck("CSD17577Q3A: threshold", _device(ctx, model), stimulus, control=["op"])


def _on_deck(ctx: Context, model: PartModel | None, volts: float, amps: float) -> str:
    stimulus = "\n".join(
        [
            "* on-resistance: gate held, drain current forced",
            "Vs s 0 0",
            f"Vg g 0 {volts:g}",
            f"Id 0 d {amps:g}",
        ]
    )
    return ctx.deck(
        f"CSD17577Q3A: on-resistance at {volts:g} V", _device(ctx, model), stimulus, control=["op"]
    )


def _transfer_deck(ctx: Context, model: PartModel | None) -> str:
    stimulus = "\n".join(
        [
            "* transfer curve: drain held, gate stepped",
            "Vs s 0 0",
            f"Vd d 0 {_TRANSFER_DRAIN_VOLTS:g}",
            "Vg g 0 0",
        ]
    )
    step = float(_GATE_VOLTS[1] - _GATE_VOLTS[0])
    control = [f"dc Vg {_GATE_VOLTS[0]:g} {_GATE_VOLTS[-1]:g} {step:g}"]
    return ctx.deck("CSD17577Q3A: transfer curve", _device(ctx, model), stimulus, control=control)


@bench(
    "models",
    "output-stage-transistor",
    "CSD17577Q3A at the limits of its datasheet: the variants of the output stage",
    "the models that stand for a transistor of the output pair at a limit",
)
def transistor(ctx: Context) -> Outcome:
    """The variants of the transistor model are put in the test circuits of the datasheet.

    The benches of the output stage use the typical model of the shared
    file and three variants of it written for this block: the gate
    threshold at its lower and at its upper limit, and the on-resistance at
    its upper limit. Here each variant stands in the circuit in which the
    datasheet states that limit. The transfer curves show what the shifted
    threshold does at the currents of an in-rush, 0.1 A to 1 A.
    """
    variants: dict[str, PartModel | None] = {"typical": None}
    variants.update({name: common.transistor(name) for name in ("LO", "HI", "RMAX")})
    decks = {}
    for name, model in variants.items():
        decks[f"threshold-{name}"] = _threshold_deck(ctx, model)
        decks[f"transfer-{name}"] = _transfer_deck(ctx, model)
    for volts, amps, _ in _ON_POINTS:
        for name in ("typical", "RMAX"):
            decks[f"on-{name}-{volts:g}".replace(".", "p")] = _on_deck(
                ctx, variants[name], volts, amps
            )
    runs = ctx.run_many(decks)
    figures: list[Figure] = [
        Figure(
            "threshold_typical",
            "Typical model: gate threshold at 250 uA",
            float(runs["threshold-typical"].real("d")[0]),
            "V",
            expected=1.4,
            low=1.3,
            high=1.5,
            source=f"{_DOCUMENT}: 1.4 V typical",
        )
    ]
    for name, limit in _THRESHOLDS.items():
        side = "lower" if name == "LO" else "upper"
        figures.append(
            near(
                f"threshold_{name.lower()}",
                f"Variant {name}: gate threshold at 250 uA",
                float(runs[f"threshold-{name}"].real("d")[0]),
                "V",
                limit,
                0.05,
                f"{_DOCUMENT}: {limit:g} V, the {side} limit",
            )
        )
    for volts, amps, limit in _ON_POINTS:
        tag = f"{volts:g}".replace(".", "p")
        figures.append(
            near(
                f"on_rmax_{tag}v",
                f"Variant RMAX: on-resistance at {volts:g} V on the gate and {amps:g} A",
                float(runs[f"on-RMAX-{tag}"].real("d")[0]) / amps,
                "ohm",
                limit,
                0.03,
                f"{_DOCUMENT}: {limit * 1e3:g} mohm at most",
            )
        )
        figures.append(
            Figure(
                f"on_typical_{tag}v",
                f"Typical model: on-resistance at {volts:g} V on the gate and {amps:g} A",
                float(runs[f"on-typical-{tag}"].real("d")[0]) / amps,
                "ohm",
            )
        )
    traces = []
    for name in ("typical", "LO", "HI"):
        run = runs[f"transfer-{name}"]
        drain = -run.real("vd#branch")
        traces.append(Trace(run.real("v-sweep"), drain, f"{name} threshold", 0))
        figures.extend(
            Figure(
                f"gate_{name.lower()}_{level:g}a".replace(".", "p"),
                f"Model {name}: gate voltage for {level:g} A at 5 V on the drain",
                float(np.interp(level, drain, run.real("v-sweep"))),
                "V",
            )
            for level in (0.1, 1.0)
        )
    graph = Graph(
        name="transfer",
        title="CSD17577Q3A: drain current against gate voltage at 5 V on the drain",
        xlabel="Gate-source voltage (V)",
        panels=(
            Panel(
                "Drain current (A)",
                log=True,
                marks=((250e-6, "250 uA"), (1.0, "1 A")),
            ),
        ),
        traces=tuple(traces),
    )
    notes = (
        "The variants are the typical model of the shared file with one property "
        "moved. The limits of 5 % and 3 % around the datasheet figures are the fit "
        "asked of a variant here; they are not datasheet limits.",
        "Between 250 uA and some amperes the datasheet gives one typical curve "
        "(figure 3) and no spread. The slope of the models below the threshold "
        "is a fit to those two ends; currents of microamperes and below taken "
        "from them are not datasheet values.",
        "The datasheet gives 1.4 ohm typical for the gate resistance (page 3); "
        "the shared model has 1 ohm.",
    )
    return Outcome(tuple(figures), (graph,), notes)
