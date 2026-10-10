"""The MCP9700A model against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_DOCUMENT = "Microchip DS20001942L, pages 3 and 4"

_CELSIUS = (-40.0, -20.0, 0.0, 25.0, 50.0, 70.0, 100.0, 125.0)
"""Temperatures of the runs."""

_LOAD_AMPS = 100e-6
"""Load of the output impedance test, the largest output current of the datasheet."""


def _deck(ctx: Context, celsius: float) -> str:
    lines = [
        "* one sensor without load, one with 100 uA drawn from its output,",
        "* and one without supply",
        "Vdd vdd 0 3.3",
        "X1 vdd out 0 DIGITAL_MCP9700A",
        "Ro out 0 1e9",
        "X2 vdd loaded 0 DIGITAL_MCP9700A",
        f"Il loaded 0 {_LOAD_AMPS:g}",
        "Voff off 0 0",
        "X3 off dead 0 DIGITAL_MCP9700A",
        "Rd dead 0 1e6",
    ]
    return ctx.deck(
        f"MCP9700A at {celsius:g} C",
        "\n".join(lines),
        control=["op"],
        options=(f"temp={celsius:g}",),
        libraries=("digital.lib",),
    )


@bench(
    "models",
    "digital-mcp9700a",
    "MCP9700A model against its datasheet",
    "the model of the board temperature sensor U39",
)
def mcp9700a(ctx: Context) -> Outcome:
    """The sensor is run at eight temperatures between -40 C and 125 C.

    The output without load gives the offset and the slope, the output with
    100 uA drawn from it the output impedance, and the supply current is
    read at 25 C. A third sensor has no supply.
    """
    volts, loaded, supply, dead = [], [], [], []
    for celsius in _CELSIUS:
        run = ctx.run(f"{celsius:g}c".replace("-", "m"), _deck(ctx, celsius), keep=celsius == 25.0)
        volts.append(float(run.real("out")[0]))
        loaded.append(float(run.real("loaded")[0]))
        supply.append(-float(run.real("vdd#branch")[0]))
        dead.append(float(run.real("dead")[0]))
    values = np.array(volts)
    slope = float(np.polyfit(np.array(_CELSIUS), values, 1)[0])
    at_zero = float(values[_CELSIUS.index(0.0)])
    room = _CELSIUS.index(25.0)
    figures = (
        near("offset", "Output at 0 C", at_zero, "V", 0.5, 0.01, _DOCUMENT + ": 500 mV"),
        near("slope", "Slope of the output", slope, "V", 0.010, 0.01, _DOCUMENT + ": 10.0 mV/K"),
        near(
            "room",
            "Output at 25 C",
            float(values[room]),
            "V",
            0.75,
            0.01,
            _DOCUMENT + ": 500 mV and 10.0 mV/K",
        ),
        near(
            "impedance",
            "Output impedance, from the drop with 100 uA",
            (values[room] - loaded[room]) / _LOAD_AMPS,
            "ohm",
            20.0,
            0.05,
            _DOCUMENT + ": 20 ohm typical",
        ),
        Figure(
            "supply_current",
            "Supply current of one sensor at 25 C",
            supply[room] / 2.0,
            "A",
            expected=6e-6,
            low=5e-6,
            high=12e-6,
            source=_DOCUMENT + ": 6 uA typical, 12 uA at the most",
        ),
        Figure(
            "without_supply",
            "Output without supply",
            dead[room],
            "V",
            high=0.01,
            source="a sensor without supply gives no voltage",
        ),
    )
    graph = Graph(
        name="output",
        title="MCP9700A: output of the model against the temperature",
        xlabel="Temperature (C)",
        panels=(Panel("Output (V)", marks=((0.3, "0.3 V"), (1.5, "1.5 V"))),),
        traces=(Trace(np.array(_CELSIUS), values, "", 0),),
    )
    notes = (
        "The model is the straight line of the datasheet. The accuracy of the part, "
        "+/-2 C at the most from 0 C to 70 C, is a parameter that the benches of "
        "the monitors set.",
        "The marks at 0.3 V and 1.5 V are the limits of rule F-12 of the "
        "specification for this channel: -20 C and 100 C.",
    )
    return Outcome(figures, (graph,), notes)
