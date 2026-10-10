"""The comparator model against the figures that its datasheet gives."""

from __future__ import annotations

import numpy as np

from benches.range_logic import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import Circuit

_REF = "U32"
"""The single comparator of the schematic that stands for its type."""

_SUPPLY = 3.3
_REFERENCE = 0.5
"""Voltage at the inverting input, V: between the thresholds of the board."""

_SWEEP = 20e-3
"""The slow triangle moves the other input this far to both sides, V."""

_SLOPE = 2e-3
"""Duration of one slope of the triangle, s."""

_OVERDRIVES = (5e-3, 20e-3, 100e-3)
"""Overdrives of the delay run, V; the datasheet states the delay at 100 mV."""

_BELOW = 100e-3
"""Distance below the reference from which each step starts, V."""

_DOCUMENT = (
    "datasheet figure as the head of the model in logic.lib quotes it "
    "(Microchip DS20002139E, pages 3 and 4)"
)


def _device(ctx: Context) -> Circuit:
    """The comparator alone, on the nodes inp, inn, out and vdd."""
    part = ctx.netlist.component(_REF)
    aliases = {
        part.net_of("+"): "inp",
        part.net_of("-"): "inn",
        part.net_of("1"): "out",
        part.net_of("V+"): "vdd",
    }
    return ctx.circuit([_REF], aliases)


def _hysteresis_deck(ctx: Context) -> str:
    device = _device(ctx)
    low, high = _REFERENCE - _SWEEP, _REFERENCE + _SWEEP
    triangle = common.pwl(
        ((0.0, low), (20e-6, low), (20e-6 + _SLOPE, high), (20e-6 + 2.0 * _SLOPE, low))
    )
    return ctx.deck(
        "Comparator: thresholds on a slow triangle",
        device,
        f"Vdd vdd 0 {_SUPPLY:g}\nVinn inn 0 {_REFERENCE:g}\nVinp inp 0 {triangle}\n"
        "Rload out 0 1meg\n",
        common.rest(device, None),
        control=[f"tran {_SLOPE / 4000.0:g} {40e-6 + 2.0 * _SLOPE:g}"],
        options=common.options(ctx),
    )


def _instants() -> list[tuple[float, float]]:
    """Start and end of the pulse for each overdrive."""
    return [(2e-6 + 4e-6 * index, 4e-6 + 4e-6 * index) for index in range(len(_OVERDRIVES))]


def _delay_deck(ctx: Context) -> str:
    device = _device(ctx)
    rest = _REFERENCE - _BELOW
    points: list[tuple[float, float]] = [(0.0, rest)]
    for (start, stop), overdrive in zip(_instants(), _OVERDRIVES, strict=True):
        top = _REFERENCE + overdrive
        points += [(start, rest), (start + 1e-9, top), (stop, top), (stop + 1e-9, rest)]
    return ctx.deck(
        "Comparator: delay at three overdrives",
        device,
        f"Vdd vdd 0 {_SUPPLY:g}\nVinn inn 0 {_REFERENCE:g}\nVinp inp 0 {common.pwl(points)}\n"
        "Rload out 0 1meg\n",
        common.rest(device, None),
        control=[f"tran 1n {4e-6 * len(_OVERDRIVES) + 2e-6:g}"],
        options=common.options(ctx),
    )


@bench(
    "models",
    "range-logic-mcp6561",
    "MCP6561 model against its datasheet: thresholds, hysteresis and delay",
    "the model of the comparators U21, U31 and U32",
)
def comparator(ctx: Context) -> Outcome:
    """The comparator of the schematic is put on a bench of its own.

    One input rests at 0.5 V. The other is moved slowly through it and back,
    which gives the two thresholds, their middle as the offset and their
    distance as the hysteresis. Then it is stepped from 100 mV below to
    5 mV, 20 mV and 100 mV above, with an edge of 1 ns, and the delay to the
    middle of the output edge is read for the rising and for the falling
    output. The benches of the range control logic use this model for all
    three comparators.
    """
    slow = ctx.run("hysteresis", _hysteresis_deck(ctx))
    time = slow.real("time")
    output = slow.real("out")
    across = slow.real("inp") - slow.real("inn")
    half = _SUPPLY / 2.0
    rises = measure.first_crossing(time, output, half, rising=True)
    falls = measure.first_crossing(time, output, half, rising=False, after=rises)
    upper = measure.value_at(time, across, rises)
    lower = measure.value_at(time, across, falls)
    figures = [
        Figure(
            "hysteresis",
            "Hysteresis: distance of the two thresholds",
            upper - lower,
            "V",
            expected=3e-3,
            low=1e-3,
            high=5e-3,
            source=f"1 mV to 5 mV; {_DOCUMENT}",
        ),
        Figure(
            "offset",
            "Offset: middle of the two thresholds",
            0.5 * (upper + lower),
            "V",
            low=-10e-3,
            high=10e-3,
            source=f"10 mV at the most; {_DOCUMENT}",
        ),
        Figure("high_level", "Output high without load", float(np.max(output)), "V"),
        Figure("low_level", "Output low without load", float(np.min(output)), "V"),
    ]
    fast = ctx.run("delay", _delay_deck(ctx))
    time = fast.real("time")
    output = fast.real("out")
    traces: list[Trace] = []
    for (start, stop), overdrive in zip(_instants(), _OVERDRIVES, strict=True):
        up = measure.first_crossing(time, output, half, rising=True, after=start) - start
        down = measure.first_crossing(time, output, half, rising=False, after=stop) - stop
        stated = overdrive == 100e-3
        name = f"{overdrive * 1e3:g}mv"
        figures += [
            Figure(
                f"delay_up_{name}",
                f"Delay to a rising output, {overdrive * 1e3:g} mV of overdrive",
                up,
                "s",
                expected=47e-9 if stated else None,
                high=80e-9 if stated else None,
                source=f"47 ns typical, 80 ns at the most; {_DOCUMENT}" if stated else "",
            ),
            Figure(
                f"delay_down_{name}",
                f"Delay to a falling output after {overdrive * 1e3:g} mV of overdrive",
                down,
                "s",
                expected=47e-9 if stated else None,
                high=80e-9 if stated else None,
                source=f"47 ns typical, 80 ns at the most; {_DOCUMENT}" if stated else "",
            ),
        ]
        shown = (time >= start - 20e-9) & (time <= start + 300e-9)
        nano = (time[shown] - start) * 1e9
        traces.append(Trace(nano, output[shown], f"{overdrive * 1e3:g} mV of overdrive", 0))
    edges = Graph(
        name="delay",
        title="Comparator output after a step of its input, by overdrive",
        xlabel="Time after the input step (ns)",
        panels=(Panel("Output (V)"),),
        traces=tuple(traces),
        xmarks=((47.0, "47 ns typical"), (80.0, "80 ns at the most")),
    )
    slow_time = slow.real("time")
    loop = Graph(
        name="hysteresis",
        title="Comparator on a slow triangle of 40 mV around its other input",
        xlabel="Time (ms)",
        panels=(Panel("Input above the other input (mV)"), Panel("Output (V)")),
        traces=(
            Trace(slow_time * 1e3, across * 1e3, "", 0),
            Trace(slow_time * 1e3, slow.real("out"), "", 1),
        ),
    )
    notes = (
        "The datasheet figures are the ones the head of the model in logic.lib "
        "quotes; the datasheet was not read again for this bench.",
        "The model written here has one delay for every overdrive and no offset "
        "unless a bench gives it one. Its hysteresis parameter is 3 mV; the "
        "thresholds lie 2.1 mV apart, because the switching curve of the model "
        "is 0.2 mV wide and rounds the corners of the loop.",
        "The delay is counted from the middle of an input edge of 1 ns to the "
        "middle of the output edge.",
        "In the vendor tier the same bench runs the model of the manufacturer, "
        "which the benches of the range control logic do not use: it shows how "
        "the delay of that model grows at small overdrive.",
    )
    return Outcome(tuple(figures), (edges, loop), notes)
