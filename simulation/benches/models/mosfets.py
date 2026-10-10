"""The MOSFET models against the figures of their datasheets."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.circuit import Circuit

_GATE_AMPS = 1e-3
"""Current that charges the gate in the gate charge run."""


@dataclass(frozen=True, slots=True)
class _Datasheet:
    """What a datasheet states about a MOSFET, typical values at 25 C.

    Attributes:
        ref: A part of the schematic of this type, which the bench takes
            its element from, so that the model map decides the model.
        model: Name of the part type.
        document: The datasheet, as the results name it.
        on_ohms: On-resistance by gate voltage.
        on_amps: Drain current at which the on-resistance is stated.
        threshold: Gate threshold voltage.
        threshold_amps: Drain current at which the threshold is stated.
        charge: Total gate charge at 4.5 V.
        charge_amps: Drain current of the gate charge test.
        charge_volts: Drain supply of the gate charge test.
    """

    ref: str
    model: str
    document: str
    on_ohms: dict[float, float]
    on_amps: float
    threshold: float
    threshold_amps: float
    charge: float
    charge_amps: float
    charge_volts: float


_CSD17577 = _Datasheet(
    ref="Q14",
    model="CSD17577Q3A",
    document="TI SLPS515A page 1, typical",
    on_ohms={4.5: 5.3e-3, 10.0: 4.0e-3},
    on_amps=16.0,
    threshold=1.4,
    threshold_amps=250e-6,
    charge=12e-9,
    charge_amps=16.0,
    charge_volts=15.0,
)

_IRLML0030 = _Datasheet(
    ref="Q12",
    model="IRLML0030",
    document="Infineon PD-96278B page 2, typical",
    on_ohms={4.5: 33e-3, 10.0: 22e-3},
    on_amps=4.0,
    threshold=1.7,
    threshold_amps=25e-6,
    charge=2.6e-9,
    charge_amps=4.0,
    charge_volts=15.0,
)


def _device(ctx: Context, part: _Datasheet) -> Circuit:
    """The part of the schematic alone, on the nodes d, g and s."""
    found = ctx.netlist.component(part.ref)
    aliases = {found.net_of("D"): "d", found.net_of("G"): "g", found.net_of("S"): "s"}
    return ctx.circuit([part.ref], aliases)


def _static_decks(ctx: Context, part: _Datasheet) -> dict[str, str]:
    """On-resistance at each gate voltage and the threshold, as operating points."""
    device = _device(ctx, part)
    decks = {}
    for volts in part.on_ohms:
        stimulus = "\n".join(
            [
                "* on-resistance: gate held, drain current forced",
                "Vs s 0 0",
                f"Vg g 0 {volts:g}",
                f"Id 0 d {part.on_amps:g}",
            ]
        )
        decks[f"on-{volts:g}v".replace(".", "p")] = ctx.deck(
            f"{part.model}: on-resistance at {volts:g} V", device, stimulus, control=["op"]
        )
    stimulus = "\n".join(
        [
            "* threshold: gate tied to drain, drain current forced",
            "Vs s 0 0",
            "Vgd g d 0",
            f"Id 0 d {part.threshold_amps:g}",
        ]
    )
    decks["threshold"] = ctx.deck(f"{part.model}: threshold", device, stimulus, control=["op"])
    return decks


def _charge_deck(ctx: Context, part: _Datasheet) -> str:
    """Gate charge: a constant current into the gate, a clamped current as load."""
    lines = [
        "* the load is a current source clamped to the drain supply, as in the",
        "* gate charge test of a datasheet",
        ".model DCLAMP D(IS=1e-9 N=1 RS=5m CJO=20p)",
        "Vs s 0 0",
        f"Vdd dd 0 {part.charge_volts:g}",
        f"Iload dd d {part.charge_amps:g}",
        "Dclamp d dd DCLAMP",
        f"Ig 0 g PULSE(0 {_GATE_AMPS:g} 1u 1n 1n 1 2)",
        "Rg g 0 1e9",
    ]
    stop = 1e-6 + 4.0 * part.charge / _GATE_AMPS
    return ctx.deck(
        f"{part.model}: gate charge",
        _device(ctx, part),
        "\n".join(lines),
        control=[f"tran {stop / 4000:g} {stop:g}"],
    )


def _qualify(ctx: Context, part: _Datasheet) -> Outcome:
    static = ctx.run_many(_static_decks(ctx, part))
    figures: list[Figure] = []
    for volts, ohms in part.on_ohms.items():
        point = static[f"on-{volts:g}v".replace(".", "p")]
        figures.append(
            near(
                f"on_{volts:g}v".replace(".", "p"),
                f"On-resistance at {volts:g} V on the gate and {part.on_amps:g} A",
                float(point.real("d")[0]) / part.on_amps,
                "ohm",
                ohms,
                0.10,
                part.document,
            )
        )
    figures.append(
        Figure(
            "threshold",
            f"Gate threshold at {part.threshold_amps * 1e6:g} uA",
            float(static["threshold"].real("d")[0]),
            "V",
            expected=part.threshold,
            low=part.threshold - 0.4,
            high=part.threshold + 0.6,
            source=part.document,
        )
    )
    run = ctx.run("charge", _charge_deck(ctx, part))
    time, gate, drain = run.real("time"), run.real("g"), run.real("d")
    start = 1e-6
    reached = measure.first_crossing(time, gate, 4.5, rising=True, after=start)
    falls = measure.first_crossing(time, drain, 0.9 * part.charge_volts, rising=False, after=start)
    fallen = measure.first_crossing(time, drain, 0.1 * part.charge_volts, rising=False, after=start)
    figures += [
        near(
            "charge_4v5",
            "Gate charge to 4.5 V",
            (reached - start) * _GATE_AMPS,
            "C",
            part.charge,
            0.25,
            part.document,
        ),
        Figure(
            "plateau",
            "Gate voltage while the drain falls",
            measure.value_at(time, gate, 0.5 * (falls + fallen)),
            "V",
        ),
        Figure(
            "charge_plateau",
            "Gate charge while the drain falls from 90 % to 10 %",
            (fallen - falls) * _GATE_AMPS,
            "C",
        ),
    ]
    charge = (time - start) * _GATE_AMPS * 1e9
    shown = time >= start
    graph = Graph(
        name="gate-charge",
        title=f"{part.model}: gate charge at {part.charge_amps:g} A and {part.charge_volts:g} V",
        xlabel="Gate charge (nC)",
        panels=(Panel("Gate voltage (V)", marks=((4.5, "4.5 V"),)), Panel("Drain voltage (V)")),
        traces=(
            Trace(charge[shown], gate[shown], "", 0),
            Trace(charge[shown], np.asarray(drain[shown]), "", 1),
        ),
        xmarks=((part.charge * 1e9, "datasheet"),),
    )
    notes = (
        "The limits here are the fit this project asks of a model: 10 % on the "
        "on-resistance, 25 % on the gate charge. They are not datasheet limits.",
        "The model is a typical part at 25 C. It says nothing about leakage.",
    )
    return Outcome(tuple(figures), (graph,), notes)


@bench(
    "models",
    "mosfet-csd17577q3a",
    "CSD17577Q3A model against its datasheet",
    "the model of Q4, Q5, Q8, Q9, Q14, Q15 and Q16",
)
def csd17577q3a(ctx: Context) -> Outcome:
    """The model is put in the test circuits of a datasheet.

    A forced drain current with the gate held gives the on-resistance, the
    gate tied to the drain the threshold, and a constant current into the
    gate with a clamped current as load the gate charge. The element is one
    part of the schematic of this type, so the model map decides the model.
    """
    return _qualify(ctx, _CSD17577)


@bench(
    "models",
    "mosfet-irlml0030",
    "IRLML0030 model against its datasheet",
    "the model of the range switches Q12 and Q13",
)
def irlml0030(ctx: Context) -> Outcome:
    """The model is put in the test circuits of a datasheet.

    A forced drain current with the gate held gives the on-resistance, the
    gate tied to the drain the threshold, and a constant current into the
    gate with a clamped current as load the gate charge. The element is one
    part of the schematic of this type, so the model map decides the model.
    """
    return _qualify(ctx, _IRLML0030)
