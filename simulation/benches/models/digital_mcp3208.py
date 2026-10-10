"""The model of the inputs of the MCP3208 against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_DOCUMENT = "Microchip DS21298E"

_PERIOD = 1e-6
"""Clock period of the test: 1 MHz, the figure of the datasheet for 2.7 V."""

_FRAME = 30e-6
"""Distance between two frames."""

_VDD = 3.3

_RESERVOIR = 100e-9
"""Capacitor at channel 7 in the charge test, as on the board."""


def frame(start: float, channel: int, period: float) -> list[tuple[float, int, int, int]]:
    """The levels of select, clock and data input of one frame, as (instant, cs, clk, din).

    The frame is that of the datasheet (page 19): select low, a start bit, the
    single-ended bit, three channel bits, then clocks for the conversion.
    The data input changes on falling edges of the clock.
    """
    bits = [1, 1, (channel >> 2) & 1, (channel >> 1) & 1, channel & 1]
    events = [(start, 0, 0, bits[0])]
    instant = start + 0.5 * period
    for index in range(19):
        events.append((instant, 0, 1, bits[index] if index < len(bits) else 0))
        nxt = bits[index + 1] if index + 1 < len(bits) else 0
        events.append((instant + 0.5 * period, 0, 0, nxt))
        instant += period
    events.append((instant, 1, 0, 0))
    return events


def sources(
    frames: list[tuple[float, int]], period: float, volts: float, nodes: tuple[str, str, str]
) -> str:
    """PWL sources for select, clock and data input over several frames.

    Args:
        frames: Start instant and channel of every frame.
        period: Clock period.
        volts: High level.
        nodes: Names of the nodes of select, clock and data input.
    """
    events: list[tuple[float, int, int, int]] = [(0.0, 1, 0, 0)]
    for start, channel in frames:
        events += frame(start, channel, period)
    lines = []
    for column, node in enumerate(nodes, start=1):
        points = []
        level = events[0][column]
        points.append(f"0 {level * volts:g}")
        for event in events[1:]:
            if event[column] == level:
                continue
            points.append(f"{event[0]:.9g} {level * volts:g}")
            points.append(f"{event[0] + 5e-9:.9g} {event[column] * volts:g}")
            level = event[column]
        lines.append(f"V{node} {node} 0 PWL({' '.join(points)})")
    return "\n".join(lines)


def sample_window(start: float, period: float) -> tuple[float, float]:
    """Start and end of the sampling of a frame that starts at ``start``."""
    first_rise = start + 0.5 * period
    return first_rise + 4.0 * period, first_rise + 5.5 * period


def _deck(ctx: Context) -> str:
    frames = [(2e-6 + index * _FRAME, index) for index in range(8)]
    frames.append((2e-6 + 8 * _FRAME, 7))
    lines = [
        "* channels 0 to 6 at 0.3 V steps from stiff sources; channel 7 is a",
        "* capacitor of 100 nF charged to 2.5 V with nothing to refill it",
        f"Vdd vdd 0 {_VDD:g}",
        "Vref vref 0 2.5",
        "X1 ch0 ch1 ch2 ch3 ch4 ch5 ch6 ch7 0 cs din dout clk 0 vref vdd DIGITAL_MCP3208",
    ]
    lines += [f"Vch{index} ch{index} 0 {0.3 * (index + 1):g}" for index in range(7)]
    lines += [
        f"C7 ch7 0 {_RESERVOIR:g} IC=2.5",
        "R7 ch7 0 1e12",
        sources(frames, _PERIOD, _VDD, ("cs", "clk", "din")),
    ]
    return ctx.deck(
        "MCP3208 inputs: nine frames, one per channel and channel 7 twice",
        "\n".join(lines),
        control=[f"tran 2n {2e-6 + 9 * _FRAME:g} 0 20n uic"],
        libraries=("digital.lib",),
    )


def _clamp_deck(ctx: Context) -> str:
    lines = [
        "* 1 mA into an analog input and out of one, with the supply present",
        f"Vdd vdd 0 {_VDD:g}",
        "Vref vref 0 2.5",
        "X1 up dn ch2 ch3 ch4 ch5 ch6 ch7 0 cs din dout clk 0 vref vdd DIGITAL_MCP3208",
        "Iup 0 up 1m",
        "Idn dn 0 1m",
        "Vcs cs 0 3.3",
        "Vck clk 0 0",
        "Vdi din 0 0",
    ]
    lines += [f"R{index} ch{index} 0 1k" for index in range(2, 8)]
    return ctx.deck(
        "MCP3208 inputs: the diodes of an analog pin",
        "\n".join(lines),
        control=["tran 1n 100n"],
        libraries=("digital.lib",),
    )


@bench(
    "models",
    "digital-mcp3208",
    "MCP3208 inputs: model against the datasheet",
    "the model of the monitor converter U40",
)
def mcp3208(ctx: Context) -> Outcome:
    """Nine frames select the eight channels in turn and channel 7 once more.

    Channels 0 to 6 stand at different voltages on stiff sources, so the
    voltage on the sampling capacitor shows which channel a frame selects
    and when. Channel 7 is a capacitor of 100 nF without a source: what a
    sample takes from it is the charge of the sampling capacitor. A second
    deck forces 1 mA through the diodes of a pin.
    """
    run = ctx.run("frames", _deck(ctx))
    time, held = run.real("time"), run.real("x1.samp")
    figures: list[Figure] = []
    worst = 0.0
    for index in range(7):
        start = 2e-6 + index * _FRAME
        _, closes = sample_window(start, _PERIOD)
        worst = max(worst, abs(measure.value_at(time, held, closes + 2e-6) - 0.3 * (index + 1)))
    figures.append(
        Figure(
            "selection",
            "Channels 0 to 6: largest distance of the held voltage from its channel",
            worst,
            "V",
            high=1e-4,
            source=_DOCUMENT + ", page 19: channel bits D2, D1, D0",
        )
    )
    start = 2e-6 + 3 * _FRAME
    opens, closes = sample_window(start, _PERIOD)
    before = measure.value_at(time, held, opens - 50e-9)
    target = 0.3 * 4
    began = measure.first_crossing(time, held, before + 0.1 * (target - before), after=start)
    tenth = measure.first_crossing(time, held, before + 0.9 * (target - before), after=start)
    figures.append(
        Figure(
            "window_start",
            "Sampling starts after the first rising clock edge of the frame by",
            began - (start + 0.5 * _PERIOD),
            "s",
            expected=4.0 * _PERIOD,
            low=4.0 * _PERIOD,
            high=4.0 * _PERIOD + 30e-9,
            source=_DOCUMENT + ", page 19: at the fourth rising edge after the start bit",
        )
    )
    figures.append(
        near(
            "switch_and_capacitor",
            "Time constant of the sampling, from the 10 % to 90 % time",
            (tenth - began) / 2.197,
            "s",
            1e3 * 20e-12,
            0.15,
            _DOCUMENT + ", page 18: 1 kohm and 20 pF",
        )
    )
    ch7 = run.real("ch7")
    first = 2e-6 + 7 * _FRAME
    second = 2e-6 + 8 * _FRAME
    _, closes7 = sample_window(first, _PERIOD)
    step = measure.value_at(time, ch7, first) - measure.value_at(time, ch7, closes7 + 1e-6)
    was = measure.value_at(time, held, first)
    expected = (2.5 - was) * 20e-12 / (_RESERVOIR + 27e-12)
    figures.append(
        near(
            "charge_step",
            "Step of a 100 nF capacitor at 2.5 V when it is sampled after channel 6",
            step,
            "V",
            expected,
            0.03,
            _DOCUMENT + ", page 18: 20 pF charged from 2.1 V to 2.5 V out of 100 nF",
        )
    )
    _, closes8 = sample_window(second, _PERIOD)
    again = measure.value_at(time, ch7, second) - measure.value_at(time, ch7, closes8 + 1e-6)
    figures.append(
        Figure(
            "second_sample",
            "Step of the same capacitor at the next sample of the same channel",
            again,
            "V",
            high=0.02 * expected,
            source="the sampling capacitor keeps its voltage between samples (assumption)",
        )
    )
    clamp = ctx.run("clamp", _clamp_deck(ctx))
    figures.append(
        near(
            "diode_up",
            "Analog pin above the supply with 1 mA into it",
            float(clamp.real("up")[-1]) - _VDD,
            "V",
            0.6,
            0.05,
            _DOCUMENT + ", page 18: diode threshold 0.6 V",
        )
    )
    figures.append(
        near(
            "diode_down",
            "Analog pin below ground with 1 mA out of it",
            -float(clamp.real("dn")[-1]),
            "V",
            0.6,
            0.05,
            _DOCUMENT + ", page 18: diode threshold 0.6 V",
        )
    )
    shown = (time > start - 1e-6) & (time < start + 9e-6)
    micro = (time[shown] - start) * 1e6
    graph = Graph(
        name="frame",
        title="MCP3208 inputs: the frame that selects channel 3, at 1 MHz",
        xlabel="Time after the select went low (us)",
        panels=(
            Panel("Select and clock (V)"),
            Panel("Data input (V)"),
            Panel("Sampling capacitor (V)", marks=((1.2, "channel 3"), (0.9, "channel 2"))),
        ),
        traces=(
            Trace(micro, np.asarray(run.real("cs")[shown]), "select", 0),
            Trace(micro, np.asarray(run.real("clk")[shown]), "clock", 0),
            Trace(micro, np.asarray(run.real("din")[shown]), "data input", 1),
            Trace(micro, np.asarray(held[shown]), "sampling capacitor", 2),
        ),
    )
    notes = (
        "The model samples and holds; the conversion, the data output and the "
        "errors of the converter (offset 3 LSB, gain 5 LSB, linearity 1 LSB at the "
        "most) are not in it.",
        "The sampling capacitor keeps the voltage of the channel before: an "
        "assumption about the capacitor array, which the datasheet does not "
        "describe. The benches of the monitors also run the case of a capacitor "
        "that starts 2.5 V away.",
        "The diode drop of 0.6 V at 1 mA is the threshold that the datasheet draws; "
        "the current is an assumption.",
    )
    return Outcome(tuple(figures), (graph,), notes)
