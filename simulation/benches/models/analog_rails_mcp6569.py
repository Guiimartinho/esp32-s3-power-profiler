"""The open-drain comparator model of the rail monitor against its datasheet."""

from __future__ import annotations

import numpy as np

from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_LIBRARY = ("analog_rails.lib",)
"""The model file of the analog rails."""

_LOW_LEVELS = ((1.8, 3e-3, 0.20), (5.5, 25e-3, 0.48))
"""Low level of the output by supply and current (DS20002143E page 10, 25 C)."""


@bench(
    "models",
    "analog-rails-mcp6569",
    "MCP6569 model (open-drain output) against its datasheet",
    "the model of the four comparators of the rail monitor U14",
)
def mcp6569(ctx: Context) -> Outcome:
    """One comparator of the model in the test circuit of the datasheet.

    A slow triangle around a reference gives the two trip points, with and
    without an offset. A current forced into the low output gives its level
    at the two supplies of the datasheet figures. A step of 100 mV around
    the reference with 20 kohm to the supply and 25 pF at the output gives
    the delay and the fall time.
    """
    lines = [
        "* trip points: a triangle of +-10 mV around 1 V in 20 ms",
        "Vdd vdd 0 PWL(0 0 0.1m 3.3)",
        "Vtri tri 0 PWL(0 0.99 10m 1.01 20m 0.99)",
        "Vref ref 0 1.0",
        "Xa tri ref oa vdd 0 MCP6569_OD",
        "Rpa vdd oa 20k",
        "Xb tri ref ob vdd 0 MCP6569_OD vos=5m vhy=1m",
        "Rpb vdd ob 20k",
    ]
    for index, (supply, amps, _) in enumerate(_LOW_LEVELS):
        lines += [
            f"* low level at {supply:g} V with {amps * 1e3:g} mA",
            f"Vd{index} vd{index} 0 PWL(0 0 0.1m {supply:g})",
            f"Vl{index} lo{index} 0 PWL(0 0 0.1m 0.4)",
            f"Vh{index} hi{index} 0 PWL(0 0 0.1m 0.6)",
            f"Xl{index} lo{index} hi{index} ol{index} vd{index} 0 MCP6569_OD",
            f"Il{index} 0 ol{index} PWL(0 0 0.2m 0 0.3m {amps:g})",
        ]
    static = ctx.run(
        "static",
        ctx.deck(
            "MCP6569: trip points and low level",
            "\n".join(lines),
            control=["tran 2u 20m 0 5u"],
            libraries=_LIBRARY,
        ),
    )
    time = static.real("time")
    drive = static.real("tri") - 1.0

    def trips(node: str) -> tuple[float, float]:
        out = static.real(node)
        up = measure.first_crossing(time, out, 1.65, rising=True, after=1e-3)
        down = measure.first_crossing(time, out, 1.65, rising=False, after=10e-3)
        return float(np.interp(up, time, drive)), float(np.interp(down, time, drive))

    up_a, down_a = trips("oa")
    up_b, down_b = trips("ob")
    figures = [
        near(
            "hysteresis",
            "Hysteresis, typical variant",
            up_a - down_a,
            "V",
            3.5e-3,
            0.05,
            "DS20002143E page 7, figure 2-4: mean of 3.4 mV to 3.6 mV",
        ),
        Figure(
            "center",
            "Middle of the two trip points, no offset",
            0.5 * (up_a + down_a),
            "V",
            low=-0.1e-3,
            high=0.1e-3,
            source="DS20002143E page 3: the offset is the middle of the trip points",
        ),
        near(
            "hysteresis_min",
            "Hysteresis with the parameter at 1 mV",
            up_b - down_b,
            "V",
            1e-3,
            0.05,
            "DS20002143E page 3: 1 mV at least",
        ),
        near(
            "offset",
            "Middle of the two trip points with an offset of 5 mV",
            0.5 * (up_b + down_b),
            "V",
            5e-3,
            0.03,
            "the parameter of the model",
        ),
    ]
    for index, (supply, amps, expected) in enumerate(_LOW_LEVELS):
        figures.append(
            near(
                f"low_{index}",
                f"Low level at {supply:g} V of supply and {amps * 1e3:g} mA",
                measure.mean(time, static.real(f"ol{index}"), 15e-3, 19e-3),
                "V",
                expected,
                0.1,
                "DS20002143E page 10, figures 2-21 and 2-24",
            )
        )
    step = ctx.run(
        "step",
        ctx.deck(
            "MCP6569: step of 100 mV with 20 kohm and 25 pF",
            "\n".join(
                [
                    "Vdd vdd 0 PWL(0 0 1u 3.3)",
                    "Vin inn 0 PWL(0 1.55 20u 1.55 20.001u 1.75 60u 1.75 60.001u 1.55)",
                    "Vref ref 0 1.65",
                    "X1 ref inn out vdd 0 MCP6569_OD",
                    "Rp vdd out 20k",
                    "Cl out 0 25p",
                ]
            ),
            control=["tran 1n 80u 0 20n"],
            libraries=_LIBRARY,
        ),
    )
    t2 = step.real("time")
    out = step.real("out")
    falls = measure.first_crossing(t2, out, 1.65, rising=False, after=20e-6)
    figures += [
        Figure(
            "delay",
            "Delay from the step to the falling output at half the supply, 3.3 V",
            falls - 20e-6,
            "s",
            expected=45e-9,
            low=34e-9,
            high=80e-9,
            source="DS20002143E page 4: 56 ns at 1.8 V and 34 ns at 5.5 V typical, 80 ns at most",
        ),
        Figure(
            "fall_time",
            "Fall time of the output from 90 % to 10 %",
            measure.rise_time(t2, out, 0.33, 2.97, after=20e-6),
            "s",
            expected=20e-9,
            high=40e-9,
            source="DS20002143E page 4: 20 ns typical",
        ),
    ]
    shown = (t2 >= 19.9e-6) & (t2 <= 20.4e-6)
    graph = Graph(
        name="step",
        title="MCP6569 model: output after a step of 100 mV, 20 kohm and 25 pF",
        xlabel="Time after the step (ns)",
        panels=(Panel("Output (V)"),),
        traces=(Trace((t2[shown] - 20e-6) * 1e9, out[shown], "", 0),),
    )
    notes = (
        "The delay of the model does not change with the overdrive, and the model has no "
        "input bias current, no limit of the common-mode range and no supply current.",
        "The output switch opens below a supply of 1.2 V, which is an assumption: the "
        "datasheet promises operation from 1.8 V and says nothing below.",
    )
    return Outcome(tuple(figures), (graph,), notes)
