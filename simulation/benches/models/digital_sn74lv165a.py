"""The SN74LV165A model against the figures of its datasheet."""

from __future__ import annotations

from typing import Any

import numpy as np

from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_DOCUMENT = "TI SCLS402R"

_PATTERN = (1, 0, 1, 1, 0, 0, 1, 0)
"""Levels at the inputs D7 down to D0 of the function test."""

_LOAD_END = 100e-9
"""Instant at which the load pin goes high."""

_FIRST_CLOCK = 150e-9
_PERIOD = 100e-9

OUTPUT_EDGE = 1.0e-9
"""What the output stage adds to the delay parameters of the model into 15 pF."""


def internal_delay(datasheet: float) -> float:
    """The delay parameter of the model that gives a delay of the datasheet into 15 pF."""
    return max(datasheet - OUTPUT_EDGE, 0.05e-9)


def _deck(ctx: Context, clock_delay: float, load_delay: float) -> str:
    """Function and delays: a load, then nine clocks into the load of the datasheet."""
    levels = {f"d{7 - index}": bit for index, bit in enumerate(_PATTERN)}
    lines = [
        "* supply 3.3 V, 15 pF at the output, generators with edges of 1 ns",
        "Vcc vcc 0 3.3",
        f"X1 pl cp d4 d5 d6 d7 qn 0 q ds d0 d1 d2 d3 0 vcc DIGITAL_LV165A "
        f"tclk={clock_delay:g} tld={load_delay:g}",
        "Cq q 0 15p",
        f"Vpl pl 0 PWL(0 3.3 20n 3.3 21n 0 {_LOAD_END:g} 0 {_LOAD_END + 1e-9:g} 3.3)",
        f"Vcp cp 0 PULSE(0 3.3 {_FIRST_CLOCK:g} 1n 1n {0.5 * _PERIOD - 1e-9:g} {_PERIOD:g})",
        "Vds ds 0 3.3",
        "* input D7 changes while the load pin is low: the output follows it",
        "Vd7 d7 0 PWL(0 0 50n 0 51n 3.3)",
    ]
    lines += [f"V{name} {name} 0 {3.3 * bit:g}" for name, bit in levels.items() if name != "d7"]
    return ctx.deck(
        "SN74LV165A: load, shift and delays into 15 pF",
        "\n".join(lines),
        control=["tran 0.05n 1.1u 0 0.5n"],
        libraries=("digital.lib",),
    )


def _static_deck(ctx: Context) -> str:
    """Output levels with 6 mA at 3.0 V, the test of the datasheet."""
    lines = [
        "Vcc vcc 0 3.0",
        "X1 0 0 0 0 0 hi qn 0 q 0 0 0 0 0 0 vcc DIGITAL_LV165A",
        "Vhi hi 0 3.0",
        "Ih q 0 6m",
        "Il 0 qn 6m",
    ]
    return ctx.deck(
        "SN74LV165A: output levels with 6 mA at 3.0 V",
        "\n".join(lines),
        control=["tran 1n 200n"],
        libraries=("digital.lib",),
    )


def _delays(
    ctx: Context, name: str, clock_delay: float, load_delay: float, keep: bool
) -> dict[str, Any]:
    run = ctx.run(name, _deck(ctx, clock_delay, load_delay), keep=keep)
    time, out = run.real("time"), run.real("q")
    half = 1.65
    load = measure.first_crossing(time, run.real("pl"), half, rising=False)
    data = measure.first_crossing(time, run.real("d7"), half, rising=True)
    clock = measure.first_crossing(time, run.real("cp"), half, rising=True)
    bits = [
        int(measure.value_at(time, out, _FIRST_CLOCK + step * _PERIOD - 10e-9) > half)
        for step in range(9)
    ]
    return {
        "time": time,
        "q": out,
        "pl": run.real("pl"),
        "cp": run.real("cp"),
        "d7": run.real("d7"),
        "from_data": measure.first_crossing(time, out, half, rising=True, after=data) - data,
        "from_clock": measure.first_crossing(time, out, half, after=clock) - clock,
        "from_load": load,
        "bits": bits,
    }


@bench(
    "models",
    "digital-sn74lv165a",
    "SN74LV165A model against its datasheet",
    "the model of the side data registers U33 and U34",
)
def sn74lv165a(ctx: Context) -> Outcome:
    """A register is loaded and shifted into the load of the datasheet.

    While the load pin is low the input D7 rises and the output follows it.
    Then the load pin goes high and nine clocks shift the pattern out, with
    the serial input high. The delays are read at half the supply, with the
    typical parameters and with the parameters set to the limits of the
    datasheet. A second deck loads the two outputs with 6 mA.
    """
    typical = _delays(ctx, "typical", 7.6e-9, 8.0e-9, keep=True)
    slow = _delays(ctx, "slow", internal_delay(18e-9), internal_delay(18.5e-9), keep=False)
    fast = _delays(ctx, "fast", internal_delay(1e-9), internal_delay(1e-9), keep=False)
    expected = [*_PATTERN, 1]
    wrong = sum(int(got != want) for got, want in zip(typical["bits"], expected, strict=True))
    static = ctx.run("levels", _static_deck(ctx))
    figures = (
        Figure(
            "wrong_bits",
            "Bits of the pattern that come out wrong, of nine",
            float(wrong),
            "",
            high=0.0,
            source=_DOCUMENT + ", page 11: D7 first, the serial input after D0",
        ),
        near(
            "clock_typical",
            "Clock to output, typical parameters",
            typical["from_clock"],
            "s",
            8.6e-9,
            0.05,
            _DOCUMENT + ", page 7: 8.6 ns typical at 3.3 V into 15 pF",
        ),
        near(
            "data_typical",
            "Input D7 to output while the load pin is low, typical parameters",
            typical["from_data"],
            "s",
            8.9e-9,
            0.05,
            _DOCUMENT + ", page 7: 8.9 ns typical; the load pin itself has 9.1 ns",
        ),
        near(
            "clock_slow",
            "Clock to output, parameter for the largest delay",
            slow["from_clock"],
            "s",
            18e-9,
            0.03,
            _DOCUMENT + ", page 7: 18 ns at the most",
        ),
        near(
            "clock_fast",
            "Clock to output, parameter for the smallest delay",
            fast["from_clock"],
            "s",
            1e-9,
            0.20,
            _DOCUMENT + ", page 7: 1 ns at the least",
        ),
        Figure(
            "output_high",
            "Output high with 6 mA at 3.0 V",
            float(static.real("q")[-1]),
            "V",
            low=2.48,
            source=_DOCUMENT + ", page 6: 2.48 V at the least",
        ),
        Figure(
            "output_low",
            "Output low with 6 mA at 3.0 V",
            float(static.real("qn")[-1]),
            "V",
            high=0.44,
            source=_DOCUMENT + ", page 6: 0.44 V at the most",
        ),
    )
    time = typical["time"]
    nano = time * 1e9
    shown = time < 650e-9

    def cut(values: np.ndarray) -> np.ndarray:
        return np.asarray(values[shown])

    graph = Graph(
        name="shift",
        title="SN74LV165A: a load and the first clocks, typical delays",
        xlabel="Time (ns)",
        panels=(Panel("Load pin and input D7 (V)"), Panel("Clock (V)"), Panel("Output (V)")),
        traces=(
            Trace(nano[shown], cut(typical["pl"]), "load pin", 0),
            Trace(nano[shown], cut(typical["d7"]), "input D7", 0, "--"),
            Trace(nano[shown], cut(typical["cp"]), "clock", 1),
            Trace(nano[shown], cut(typical["q"]), "output", 2),
        ),
    )
    notes = (
        "The delay parameters of the model are the delays of the datasheet less "
        "1 ns, which the output stage adds into 15 pF.",
        "The threshold of the inputs is half the supply and the output resistance "
        "50 ohm: assumptions inside the limits of the datasheet. The model does not "
        "check pulse widths, setup or hold times; the benches of the side data "
        "measure them at the pins.",
    )
    return Outcome(figures, (graph,), notes)
