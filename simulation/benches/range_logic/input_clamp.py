"""The comparator inputs while 3V3_A is off and the amplifier output is high."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from benches import frontend
from benches.range_logic import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_RAMP_START = 10e-6
_RAMP = 1e-3
"""The amplifier output rises from 0 V to the rail in this time, s."""

_RAIL = 12.0
"""Positive supply of the amplifier, V: the most its output could reach."""

_SWING = _RAIL - 1.6
"""Highest output of the amplifier, V (datasheet limit quoted in section 4.5)."""

_DIODES = {"typical": "BAV199", "highest": "BAV199_HI", "lowest": "BAV199_LO"}
"""Forward voltage of the clamp diode: assumed typical, datasheet maximum, assumed low."""

_RATING = 1.0
"""Voltage a comparator input may stand above its supply, V (section 4.5)."""


def _deck(ctx: Context, diode: str, rail: float) -> str:
    """The comparator sheet alone, with a source in the place of the amplifier."""
    base = ctx.models.model_of(ctx.netlist.component("D23"))
    circuit = ctx.circuit(
        frontend.comparator_refs(ctx.netlist),
        common.ALIASES,
        {"D23": replace(base, name=_DIODES[diode])},
    )
    ramp = common.pwl(((0.0, 0.0), (_RAMP_START, 0.0), (_RAMP_START + _RAMP, _RAIL)))
    reference = 2.5 if rail > 0.0 else 0.0
    return ctx.deck(
        f"Comparator inputs, 3V3_A at {rail:g} V, clamp diode {diode}",
        circuit,
        "* the rail of the comparators and the reference, which is supplied from it\n"
        f"Vp3v3a p3v3_a 0 {rail:g}\n"
        f"Vref vref 0 {reference:g}\n",
        "* the amplifier output as a source that rises to the positive rail\n"
        f"Vamp amp_raw 0 {ramp}\n",
        common.rest(circuit, None),
        control=[
            "save amp_raw cmp_in p3v3_a cmp_up cmp_oc cmp_jump @r136[i] @r137[i] "
            "@dd23_1[id] @dd23_2[id]",
            f"tran {_RAMP / 2000.0:g} {_RAMP_START + _RAMP:g}",
        ],
        options=common.options(ctx),
    )


def _at(result: RunResult, name: str, volts: float) -> float:
    """A waveform at the instant the amplifier output passes a voltage."""
    time = result.real("time")
    instant = min(
        measure.first_crossing(time, result.real("amp_raw"), volts * 0.999999, rising=True),
        float(time[-1]),
    )
    return measure.value_at(time, result.real(name), instant)


@bench(
    "range_logic",
    "input-clamp",
    "The comparator inputs with 3V3_A off and the amplifier output at 10 V",
    "section 4.5 (comparator inputs, limiter), decision D-76, section 16 (comparators)",
)
def input_clamp(ctx: Context) -> Outcome:
    """The supply of the comparators is at 0 V and the amplifier output rises to 12 V.

    The amplifier runs from +12 V and can hold its output high while 3V3_A
    is off: after a failed part, or with the negative rail missing. The
    divider R136 and R137 and the diode pair D23 then have to keep the
    comparator inputs within 1.0 V of their supply. The run takes the
    comparator sheet alone with a source in the place of the amplifier
    output, ramps that source from 0 V to 12 V, and reads the node of the
    comparator inputs and the currents in R136 and in the diode at 10 V, at
    10.4 V, which is the highest output of the amplifier, and at 12 V. It is
    repeated with the diode at the forward voltage that its datasheet gives
    as the maximum, and with 3V3_A present.
    """
    off = {diode: ctx.run(f"off-{diode}", _deck(ctx, diode, 0.0)) for diode in _DIODES}
    present = ctx.run("present", _deck(ctx, "typical", 3.3))
    typical, highest = off["typical"], off["highest"]
    spec_current = "section 4.5: limited to 2.3 mA to 2.8 mA, calculated; 2.8 mA to its last digit"
    figures = [
        Figure(
            "node_10v_highest",
            "Node above 3V3_A, amplifier at 10 V, diode at its datasheet maximum",
            _at(highest, "cmp_in", 10.0),
            "V",
            expected=0.95,
            high=0.95,
            source="section 4.5: the node cannot pass 3V3_A + 0.95 V at 25 C",
        ),
        Figure(
            "node_swing_highest",
            "The same with the amplifier at its highest output, 10.4 V",
            _at(highest, "cmp_in", _SWING),
            "V",
            high=_RATING,
            source="section 4.5: rating of the comparator inputs, 1.0 V beyond the supply",
        ),
        Figure(
            "node_rail_highest",
            "The same with the amplifier output at its 12 V rail",
            _at(highest, "cmp_in", _RAIL),
            "V",
            high=_RATING,
            source="section 4.5: rating of the comparator inputs, 1.0 V beyond the supply",
        ),
        Figure(
            "node_10v_typical",
            "Node above 3V3_A, amplifier at 10 V, typical diode",
            _at(typical, "cmp_in", 10.0),
            "V",
        ),
        Figure(
            "node_10v_lowest",
            "Node above 3V3_A, amplifier at 10 V, diode with a low forward voltage",
            _at(off["lowest"], "cmp_in", 10.0),
            "V",
        ),
        Figure(
            "diode_10v",
            "Current in the clamp diode, amplifier at 10 V, typical diode",
            _at(typical, "@dd23_2[id]", 10.0),
            "A",
            expected=2.3e-3,
            high=2.85e-3,
            source=spec_current,
        ),
        Figure(
            "diode_swing",
            "The same with the amplifier at its highest output, 10.4 V",
            _at(typical, "@dd23_2[id]", _SWING),
            "A",
            expected=2.3e-3,
            high=2.85e-3,
            source=spec_current,
        ),
        Figure(
            "diode_swing_lowest",
            "The same with a diode of low forward voltage",
            _at(off["lowest"], "@dd23_2[id]", _SWING),
            "A",
            high=2.85e-3,
            source=spec_current,
        ),
        Figure(
            "diode_rail",
            "Typical diode, amplifier output at its 12 V rail, which it cannot reach",
            _at(typical, "@dd23_2[id]", _RAIL),
            "A",
            expected=2.8e-3,
        ),
        Figure(
            "divider_swing",
            "Current in R136, amplifier at 10.4 V, typical diode",
            _at(typical, "@r136[i]", _SWING),
            "A",
        ),
        Figure(
            "power_r136",
            "Power in R136 with the amplifier output at its 12 V rail",
            _at(typical, "@r136[i]", _RAIL) ** 2 * 3010.0,
            "W",
            high=0.1,
            source="limit of this bench: 0.1 W, the usual rating of a 0603 resistor (assumption)",
        ),
        Figure(
            "present_node",
            "3V3_A present, amplifier at 10.4 V: node of the comparator inputs",
            _at(present, "cmp_in", _SWING),
            "V",
            expected=_SWING / common.DIVIDER,
            high=3.3,
            source="section 4.5: the divider keeps the inputs inside the supply",
        ),
        Figure(
            "present_diode",
            "3V3_A present, amplifier at 12 V: current in the clamp diode",
            _at(present, "@dd23_2[id]", _RAIL),
            "A",
            high=1e-6,
            source="limit of this bench: no clamp current while the rail is present",
        ),
    ]
    traces: list[Trace] = []
    for diode, result in off.items():
        volts = result.real("amp_raw")
        traces += [
            Trace(volts, result.real("cmp_in"), f"3V3_A off, diode {diode}", 0),
            Trace(volts, result.real("@dd23_2[id]") * 1e3, f"diode {diode}", 1),
        ]
    traces += [
        Trace(present.real("amp_raw"), present.real("cmp_in"), "3V3_A present", 0, "--"),
        Trace(
            typical.real("amp_raw"), typical.real("@r136[i]") * 1e3, "R136, typical diode", 1, "--"
        ),
        Trace(
            present.real("amp_raw"),
            np.asarray(present.real("@dd23_2[id]") * 1e3),
            "diode, 3V3_A present",
            1,
            ":",
        ),
    ]
    graph = Graph(
        name="transfer",
        title="Comparator inputs against the amplifier output, 3V3_A off and present",
        xlabel="Amplifier output (V)",
        panels=(
            Panel(
                "Node of the comparator inputs (V)",
                marks=((_RATING, "rating with the rail at 0 V"), (0.95, "0.95 V")),
            ),
            Panel("Current (mA)"),
        ),
        traces=tuple(traces),
        xmarks=((10.0, "10 V"), (_SWING, "highest output 10.4 V")),
    )
    notes = (
        "The amplifier is not in this circuit: a source stands for its output, "
        "so the run says nothing about how that output gets high. The rail is "
        "held at 0 V by a source; a rail that is merely unpowered is lifted by "
        "the clamp current through whatever loads it, and the node rises with "
        "it by the same amount.",
        "The diode model is fitted to the maximum forward voltage of its "
        "datasheet at 25 C (0.9 V at 1 mA, 1.0 V at 10 mA). The typical and the "
        "low curve are assumptions: the datasheet gives a maximum only. Near "
        "0 C the forward voltage is about 50 mV higher, which uses up the "
        "margin to the rating that these figures show.",
        "The comparator model draws no input current and has no input "
        "protection of its own. The real part has protection structures at its "
        "inputs that take a share of the current once the node stands a diode "
        "drop above its rail; how the current divides between them and D23 is "
        "not in this run.",
        "The current in the diode is the current of R136 less what R137 takes. "
        "It grows with the amplifier output and with a lower forward voltage: "
        "the 2.3 mA and 2.8 mA of the specification are met at 10.4 V and just "
        "passed, by 0.06 mA, with the output at the 12 V rail itself.",
        "With 3V3_A present the node follows the divider and stays below the "
        "rail up to an amplifier output of 13.2 V, more than its supply.",
    )
    return Outcome(tuple(figures), (graph,), notes)
