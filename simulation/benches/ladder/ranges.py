"""The four ranges at rest: effective shunt, burden voltage and current split."""

from __future__ import annotations

import numpy as np

from benches import frontend
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.report import format_quantity

_CURRENTS = np.logspace(-7, np.log10(1.2), 72)
"""Load currents of the sweep: 100 nA to 1.2 A, ten per decade."""

_BURDEN_MOST = {3: 0.107}
"""Largest burden at full scale that the specification states, by range."""


def _deck(ctx: Context, index: int, vout: float) -> str:
    """One range held, the load current stepped over the whole span."""
    circuit = ctx.circuit(frontend.ladder_refs(ctx.netlist), frontend.ALIASES)
    stimulus = "\n".join(
        [
            "* the source meter as an ideal source on the supply node; the load",
            "* as a current sink on the node after the shunts",
            f"Vsupply supply 0 {vout:g}",
            "Iload vout_s 0 1u",
        ]
    )
    points = " ".join(f"{current:.6g}" for current in _CURRENTS)
    control = [
        f"foreach level {points}",
        "  alter Iload dc = $level",
        "  op",
        "end",
    ]
    return ctx.deck(
        f"Shunt ladder at rest, range {index}, supply node at {vout:g} V",
        circuit,
        frontend.rails(vref=None),
        frontend.fixed_range(index),
        stimulus,
        control=control,
        options=("gmin=1e-15", "abstol=1e-15"),
    )


def _sweep(ctx: Context, index: int, vout: float, keep: bool) -> dict[str, np.ndarray]:
    """The node voltages of one range over the sweep, by node name."""
    result = ctx.run(f"r{index}-{vout:g}v".replace(".", "p"), _deck(ctx, index, vout), keep=keep)
    names = ("supply", "vout_s", "inp", "inn", f"sense_r{index}" if index else "supply")
    return {
        name: np.array(
            [float(result.real(name, plot=f"op{step + 1}")[0]) for step in range(_CURRENTS.size)]
        )
        for name in names
    }


@bench(
    "ladder",
    "ranges",
    "The four ranges at rest: shunt seen by the amplifier and burden voltage",
    "section 4.3 (range table, Kelvin sensing, one-hot selection), section 8 (shunt values)",
)
def ranges(ctx: Context) -> Outcome:
    """Each range is held and the load current is stepped from 100 nA to 1.2 A.

    The voltage between the two outputs of the multiplexer is read. Its slope
    is the shunt that the amplifier sees; the voltage from the supply node to
    the node after the shunts is the burden. The run is repeated with the
    supply node at 0.8 V and at 5 V, because the gate drive of the range
    switches depends on it.
    """
    figures: list[Figure] = []
    traces: list[Trace] = []
    for index in range(4):
        data = {vout: _sweep(ctx, index, vout, keep=vout == 5.0) for vout in (5.0, 0.8)}
        full_scale = frontend.FULL_SCALE_AMPS[index]
        expected = frontend.SHUNT_OHMS[index]
        for vout, nodes in data.items():
            sense = nodes["inp"] - nodes["inn"]
            burden = nodes["supply"] - nodes["vout_s"]
            inside = 1.0001 * full_scale >= _CURRENTS
            shunt = float(np.polyfit(_CURRENTS[inside], sense[inside], 1)[0])
            at_full = float(np.interp(full_scale, _CURRENTS, burden))
            tag = f"r{index}_{vout:g}v".replace(".", "p")
            figures.append(
                near(
                    f"shunt_{tag}",
                    f"R{index}: shunt seen by the amplifier, supply node at {vout:g} V",
                    shunt,
                    "ohm",
                    expected,
                    0.001,
                    "sections 4.3 and 8, calculated",
                )
            )
            high = _BURDEN_MOST.get(index)
            figures.append(
                Figure(
                    f"burden_{tag}",
                    f"R{index}: burden at {format_quantity(full_scale, 'A')}, "
                    f"supply node at {vout:g} V",
                    at_full,
                    "V",
                    high=high,
                    source="section 4.3: 105 mV to 107 mV, calculated" if high else "",
                )
            )
            if vout == 5.0:
                traces.append(Trace(_CURRENTS, sense * 1e3, f"R{index}", panel=0))
                traces.append(Trace(_CURRENTS, burden * 1e3, f"R{index}", panel=1))
        if index == 0:
            clamped = data[5.0]["supply"] - data[5.0]["vout_s"]
            figures.append(
                Figure(
                    "clamp_at_1a",
                    "R0 held with 1 A of load: the ladder clamp bounds the ladder at",
                    float(np.interp(1.0, _CURRENTS, clamped)),
                    "V",
                    low=2.5,
                    high=2.9,
                    source="section 4.4 and rule F-21: 2.5 V to 2.9 V",
                )
            )
        if index == 1:
            nodes = data[5.0]
            through_r0 = (nodes["supply"] - nodes["vout_s"]) / 1000.0
            share = float(np.interp(full_scale, _CURRENTS, through_r0 / _CURRENTS))
            figures.append(
                Figure(
                    "r0_share_in_r1",
                    "R1: share of the current that flows through R0",
                    share * 100.0,
                    "%",
                    expected=3.0,
                    low=2.5,
                    high=3.5,
                    source="section 4.3, about 3 %",
                )
            )
    graph = Graph(
        name="map",
        title="Shunt ladder at rest, supply node at 5 V: what each range gives",
        xlabel="Load current (A)",
        panels=(
            Panel(
                "Sense voltage at the multiplexer (mV)",
                log=True,
                marks=((122.9, "converter full scale 122.9 mV"), (91.0, "step up 91 mV")),
            ),
            Panel("Burden, supply node to load (mV)", log=True),
        ),
        traces=tuple(traces),
        logx=True,
    )
    notes = (
        "The supply node is an ideal source and the load an ideal current sink: the "
        "output switch and the source meter are not in this circuit.",
        "The multiplexer is the behavioral model with 250 ohm per channel; its "
        "resistance carries no current here and does not enter these figures.",
        "The range switches are fitted to the typical on-resistance of their "
        "datasheets. The burden of range 3 therefore is a typical value.",
    )
    return Outcome(tuple(figures), (graph,), notes)
