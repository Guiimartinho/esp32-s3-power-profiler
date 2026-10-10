"""The model of the digital pins of the ADS8860 against the figures of its datasheet."""

from __future__ import annotations

import numpy as np

from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench

_DOCUMENT = "TI SBAS569B"

_CODE = 0xA5C3
"""The word that the model shifts out in this test."""

_DVDD = 3.0
"""Supply of the timing table of the datasheet."""

_CONVERT = 50e-9
"""Instant of the rising edge of CONVST."""

_READ = 800e-9
"""Instant of the falling edge of CONVST, after the longest conversion."""

_PERIOD = 66.667e-9
"""Clock period, 15 MHz."""

_FIRST_FALL = _READ + 40e-9
"""Instant of the first falling edge of SCLK."""


def _deck(ctx: Context) -> str:
    high = 0.5 * _PERIOD
    start = _FIRST_FALL - high
    lines = [
        "* supply 3.0 V; 20 pF at DOUT as in the load circuit of the datasheet;",
        "* two resistors hold DOUT at half the supply while it is open",
        f"Vdd dvdd 0 {_DVDD:g}",
        f"X1 cnv dout sck dvdd dvdd 0 DIGITAL_ADS8860_IO code={_CODE}",
        "Cl dout 0 20p",
        "Rup dvdd dout 5k",
        "Rdn dout 0 5k",
        f"Vcnv cnv 0 PWL(0 0 {_CONVERT:g} 0 {_CONVERT + 1e-9:g} {_DVDD:g} {_READ:g} {_DVDD:g} "
        f"{_READ + 1e-9:g} 0 2.05u 0 2.051u {_DVDD:g})",
        f"Vsck sck 0 PULSE(0 {_DVDD:g} {start:g} 1n 1n {high - 1e-9:g} {_PERIOD:g} 16)",
    ]
    return ctx.deck(
        "ADS8860 digital pins: one frame in the three-wire mode into 20 pF",
        "\n".join(lines),
        control=["tran 0.05n 2.2u 0 0.5n"],
        libraries=("digital.lib",),
    )


@bench(
    "models",
    "digital-ads8860",
    "ADS8860 digital pins: model against the datasheet",
    "the model of the convert-start, clock and data pins of the converter U30",
)
def ads8860(ctx: Context) -> Outcome:
    """One frame of the three-wire mode is clocked out of the model.

    CONVST rises, stays high for the longest conversion and falls; sixteen
    clocks of 15 MHz follow. DOUT carries 20 pF as in the load circuit of
    the datasheet and is held at half the supply while it is open. The
    delays are read between the input levels and the output levels of the
    datasheet, and the sixteen bits are compared with the word of the model.
    """
    run = ctx.run("frame", _deck(ctx))
    time, out = run.real("time"), run.real("dout")
    clock, convert = run.real("sck"), run.real("cnv")
    low, high = 0.2 * _DVDD, 0.8 * _DVDD
    bits = [(_CODE >> (15 - index)) & 1 for index in range(16)]
    falls = [_FIRST_FALL + index * _PERIOD for index in range(16)]
    read = [
        int(
            measure.value_at(time, out, (_READ + 35e-9) if index == 0 else falls[index - 1] + 60e-9)
            > 0.5 * _DVDD
        )
        for index in range(16)
    ]
    wrong = sum(int(got != want) for got, want in zip(read, bits, strict=True))
    first = measure.first_crossing(time, out, high if bits[0] else low, after=_READ) - _READ
    delays, holds = [], []
    for index in range(15):
        if bits[index + 1] == bits[index]:
            continue
        edge = measure.first_crossing(
            time, clock, 0.3 * _DVDD, rising=False, after=falls[index] - 5e-9
        )
        target = high if bits[index + 1] else low
        leave = low if bits[index + 1] else high
        delays.append(measure.first_crossing(time, out, target, after=edge) - edge)
        holds.append(measure.first_crossing(time, out, leave, after=edge) - edge)
    last = measure.first_crossing(time, clock, 0.3 * _DVDD, rising=False, after=falls[15] - 5e-9)
    settled = measure.value_at(time, out, last + 5e-9)
    opened = measure.first_crossing(
        time, out, settled + 0.1 if bits[15] == 0 else settled - 0.1, after=last
    )
    during = measure.mean(time, out, 300e-9, 700e-9)
    figures = (
        Figure(
            "wrong_bits",
            "Bits read wrong, of 16",
            float(wrong),
            "",
            high=0.0,
            source=_DOCUMENT + ", page 22: most significant bit first",
        ),
        Figure(
            "open_while_converting",
            "DOUT while CONVST is high: level of the open line",
            during,
            "V",
            low=0.45 * _DVDD,
            high=0.55 * _DVDD,
            source=_DOCUMENT + ", page 22: DOUT is open from the rising edge of CONVST",
        ),
        Figure(
            "first_bit",
            "CONVST low to first bit valid",
            first,
            "s",
            expected=12.3e-9,
            low=11.3e-9,
            high=12.3e-9,
            source=_DOCUMENT + ", page 8: 12.3 ns at the most; the model sits at the limit",
        ),
        Figure(
            "next_bit",
            "SCLK falling to next bit valid, slowest transition",
            max(delays),
            "s",
            expected=13.4e-9,
            low=12.4e-9,
            high=13.4e-9,
            source=_DOCUMENT + ", page 8: 13.4 ns at the most; the model sits at the limit",
        ),
        Figure(
            "hold",
            "SCLK falling to the bit before it no longer valid, earliest",
            min(holds),
            "s",
            low=3e-9,
            source=_DOCUMENT + ", page 8: 3 ns at the least",
        ),
        Figure(
            "released",
            "Sixteenth falling edge of SCLK to DOUT leaving its level",
            opened - last,
            "s",
            high=18.2e-9,
            source=_DOCUMENT + ", page 8: open 13.2 ns after the edge at the most; 5 ns "
            "more for the line to move by 0.1 V with 2.5 kohm and 25 pF",
        ),
    )
    shown = (time > _READ - 60e-9) & (time < falls[15] + 150e-9)
    nano = (time[shown] - _READ) * 1e9
    graph = Graph(
        name="frame",
        title="ADS8860 digital pins: the word 0xA5C3 at 15 MHz into 20 pF",
        xlabel="Time after the falling edge of CONVST (ns)",
        panels=(
            Panel("CONVST and SCLK (V)"),
            Panel("DOUT (V)", marks=((high, "0.8 x DVDD"), (low, "0.2 x DVDD"))),
        ),
        traces=(
            Trace(nano, np.asarray(convert[shown]), "CONVST", 0),
            Trace(nano, np.asarray(clock[shown]), "SCLK", 0),
            Trace(nano, np.asarray(out[shown]), "DOUT", 1),
        ),
    )
    notes = (
        "The datasheet gives only the largest delays and the shortest hold time; "
        "the model sits at the largest delays by default, and a bench that needs "
        "the earliest change sets its delay parameter to 3 ns.",
        "The output resistance of 40 ohm and the pin capacitance of 5 pF are "
        "assumptions: the datasheet states the output levels at 500 uA only and no "
        "capacitance of a digital pin.",
        "The conversion itself is not in the model: DOUT carries the word given as a parameter.",
    )
    return Outcome(figures, (graph,), notes)
