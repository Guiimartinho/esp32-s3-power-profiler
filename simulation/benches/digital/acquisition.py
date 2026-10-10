"""The acquisition lines: convert-start, clock, converter data, load and side data.

Two benches share one circuit: the converter pins behind their 220 ohm, the
two shift registers, the series resistors and pull-downs at the controller,
and three pads of the controller that run the frame of rule F-34.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.digital import common
from benches.models.digital_sn74lv165a import internal_delay
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_REFS = ("U30", "U33", "U34", "R138", "RN3", "RN4", "RN5", "C92", "C98", "C99")
"""The converter (its digital pins), the two registers, the series resistors
of the lines and the pull resistors at the pins of the controller."""

_CLOCK = common.SYSTEM_CLOCK

_CONVERT_AT = 20
"""System clock at which convert-start rises."""

_CONVERT_CLOCKS = 108
"""Convert-start high, in system clocks (rule F-34)."""

_LOAD_CLOCKS = 3
"""Load line low, in system clocks (rule F-34)."""

_REGISTER_HIGH = 0.7 * common.LOGIC_VOLTS
_REGISTER_LOW = 0.3 * common.LOGIC_VOLTS
"""Input levels of the registers and of the converter (0.7 and 0.3 of the supply)."""

_SIDE_BITS = ["MUX_A1", "MUX_A0", "GATE_OUT", "VIN_OV", "CMP_OC", "CMP_JUMP", "CMP_UP", "PWR_GOOD"]
"""Signals at the inputs D7 down to D0 of U34, the first eight side bits."""

_SIDE_NODES = ("mux_a1", "mux_a0", "gate_out", "vin_ov", "cmp_oc", "cmp_jump", "cmp_up", "pwr_good")


@dataclass(frozen=True, slots=True)
class Corner:
    """One set of delays and loads of the acquisition lines.

    Attributes:
        name: Short name of the corner.
        pad_high: Output resistance of a pad that drives high.
        pad_low: Output resistance of a pad that drives low.
        track: Capacitance of a track with its vias (assumption).
        pin: Capacitance of a digital pin of the converter (assumption).
        pad_farads: Capacitance of a pad that reads (assumption).
        converter_delay: Delay parameter of the converter data output.
        register_clock: Delay of the registers from the clock, into 15 pF.
        register_load: Delay of the registers from the load pin, into 15 pF.
    """

    name: str
    pad_high: float
    pad_low: float
    track: float
    pin: float
    pad_farads: float
    converter_delay: float
    register_clock: float
    register_load: float


LONG_TRACKS = (10e-12, 8e-12, 8e-12)
"""A board with long tracks and heavy pins: capacitance of a track, of a
converter pin and of a pad (assumptions)."""

SHORT_TRACKS = (2e-12, 3e-12, 3e-12)
"""A board with short tracks and light pins (assumptions)."""

WEAK_PAD = (common.PAD_HIGH_OHMS, common.PAD_LOW_OHMS, *LONG_TRACKS)
"""Weakest pad of the 4 mA setting on the board with long tracks: output
resistance high and low, then the three capacitances."""

STRONG_PAD = (common.PAD_STRONG_OHMS, common.PAD_STRONG_OHMS, *SHORT_TRACKS)
"""A strong pad on the board with short tracks."""

DRIVE_12MA = (56.7, 41.7)
"""Weakest pad of the 12 mA setting (RP2350 datasheet, table 1683: 2.62 V
and 0.5 V at 12 mA): output resistance high and low."""

SLOW_CONVERTER = (11.2e-9, 1e-9, 1e-9)
"""Converter at its largest delay, registers at their smallest: the pair
that opens the reading window late and closes it early."""

FAST_CONVERTER = (2.8e-9, 18e-9, 18.5e-9)
"""Converter at its earliest change, registers at their largest delay."""


def corner(name: str, pad: tuple[float, ...], delays: tuple[float, ...]) -> Corner:
    """A corner from a set of pad and track values and a set of delays."""
    return Corner(name, *pad, *delays)


LATE = corner("late", WEAK_PAD, (11.2e-9, 18e-9, 18.5e-9))
"""Everything slow: weakest pad, long tracks, the largest delays of the datasheets."""

EARLY = corner("early", STRONG_PAD, (2.8e-9, 1e-9, 1e-9))
"""Everything fast: strong pad, short tracks, the earliest changes of the datasheets."""

TYPICAL = Corner("typical", 60.0, 50.0, 5e-12, 5e-12, 5e-12, 6e-9, 8.6e-9, 9.1e-9)
"""A middle case. The pad resistance and the converter delay are assumptions;
the register delays are the typical values of its datasheet."""


@dataclass(frozen=True, slots=True)
class Frame:
    """The instants of one frame of the acquisition program.

    Attributes:
        bit_clocks: System clocks per bit: 16 at 9.375 MHz, 10 at 15 MHz.
        convert: Instant at which convert-start is driven high.
        read: Instant at which it is driven low.
        rises: Instants at which the clock is driven high, 16 of them.
        falls: Instants at which the clock is driven low, 16 of them.
        end: End of the run.
        again: Start of a second frame after the first one, or 0 for none.
    """

    bit_clocks: int
    convert: float
    read: float
    rises: tuple[float, ...]
    falls: tuple[float, ...]
    end: float
    again: float = 0.0

    @property
    def period(self) -> float:
        """One clock period."""
        return self.bit_clocks * _CLOCK


def frame(bit_clocks: int, sample_clocks: int = 0) -> Frame:
    """The frame of rule F-34 with a given number of system clocks per bit.

    Args:
        bit_clocks: System clocks per bit.
        sample_clocks: System clocks per sample; when given, the run holds a
            second frame that starts one sample after the first.
    """
    convert = _CONVERT_AT * _CLOCK
    read = convert + _CONVERT_CLOCKS * _CLOCK
    half = bit_clocks // 2
    first = read + half * _CLOCK
    rises = tuple(first + index * bit_clocks * _CLOCK for index in range(16))
    falls = tuple(instant + half * _CLOCK for instant in rises)
    if not sample_clocks:
        return Frame(bit_clocks, convert, read, rises, falls, falls[-1] + 12 * _CLOCK)
    again = sample_clocks * _CLOCK
    return Frame(bit_clocks, convert, read, rises, falls, again + rises[2], again)


def deck(
    ctx: Context,
    when: Frame,
    corner: Corner,
    code: int,
    side: int,
    title: str,
    released: bool = False,
) -> str:
    """One frame on the acquisition lines.

    Args:
        ctx: The bench context.
        when: The instants of the frame.
        corner: Delays and loads.
        code: The word of the converter.
        side: The 16 side bits, the first one in bit 15.
        title: First line of the deck.
        released: Leave the three pads of the controller released.
    """
    register = ctx.models.model_of(ctx.netlist.component("U33"))
    slow = common.with_params(
        register,
        tclk=internal_delay(corner.register_clock),
        tld=internal_delay(corner.register_load),
    )
    circuit = ctx.circuit(
        _REFS,
        common.ALIASES,
        overrides={
            "U30": common.ads8860(
                code=code, tdo=corner.converter_delay, cin=corner.pin, cout=corner.pin
            ),
            "U33": slow,
            "U34": slow,
        },
    )
    pads = [
        common.Pad("gp19", "gp19", corner.pad_high, corner.pad_low, corner.pad_farads),
        common.Pad("gp20", "gp20", corner.pad_high, corner.pad_low, corner.pad_farads),
        common.Pad("gp21", "gp21", corner.pad_high, corner.pad_low, corner.pad_farads),
        common.Pad("gp16", "gp16", farads=corner.pad_farads),
        common.Pad("gp17", "gp17", farads=corner.pad_farads),
    ]
    starts = (0.0, when.again) if when.again else (0.0,)
    clock = [(0.0, 0.0)]
    convert = [(0.0, 0.0)]
    load = [(0.0, 1.0)]
    for start in starts:
        for rise, fall in zip(when.rises, when.falls, strict=True):
            clock += [(start + rise, 1.0), (start + fall, 0.0)]
        convert += [(start + when.convert, 1.0), (start + when.read, 0.0)]
        load += [(start + when.convert, 0.0), (start + when.convert + _LOAD_CLOCKS * _CLOCK, 1.0)]
    drive = 0 if released else 1
    lines = [
        common.module_supply().rstrip(),
        "* rails of the carrier as ideal sources",
        "Vlogic v3c 0 3.3",
        "Vanalog v3a 0 3.3",
        "* three pads of the controller run the frame; two pads read",
        *[pad.line() for pad in pads],
        f"Vgp20_ctl gp20_ctl 0 {common.pulses(convert)}",
        f"Vgp19_ctl gp19_ctl 0 {common.pulses(clock)}",
        f"Vgp21_ctl gp21_ctl 0 {common.pulses(load)}",
        f"Vgp19_oe gp19_oe 0 {drive}",
        f"Vgp20_oe gp20_oe 0 {drive}",
        f"Vgp21_oe gp21_oe 0 {drive}",
        "Vgp16_ctl gp16_ctl 0 0",
        "Vgp16_oe gp16_oe 0 0",
        "Vgp17_ctl gp17_ctl 0 0",
        "Vgp17_oe gp17_oe 0 0",
        "* tracks (assumption)",
        f"Ct1 adc_sck 0 {2 * corner.track:g}",
        f"Ct2 adc_cnv 0 {corner.track:g}",
        f"Ct3 side_load 0 {corner.track:g}",
        f"Ct4 gp16 0 {corner.track:g}",
        f"Ct5 gp17 0 {corner.track:g}",
        "* the sixteen inputs of the registers, held by ideal sources",
    ]
    lines += [
        f"Vs{index} {node} 0 {3.3 * ((side >> (15 - index)) & 1):g}"
        for index, node in enumerate(_SIDE_NODES)
    ]
    lines += [
        f"Vd{index} din{7 - index} 0 {3.3 * ((side >> (7 - index)) & 1):g}" for index in range(8)
    ]
    return ctx.deck(
        title,
        circuit,
        "\n".join(lines),
        control=[f"tran 0.05n {when.end:g} 0 0.25n"],
        libraries=(common.LIBRARY,),
    )


def _decode(run: RunResult, when: Frame, node: str, offset: float) -> int:
    """The 16 bits that a pad reads, sampled before each rising edge of the clock."""
    time, wave = run.real("time"), run.real(node)
    word = 0
    for rise in when.rises:
        level = measure.value_at(time, wave, rise - offset)
        word = (word << 1) | int(level > 0.5 * (common.PAD_INPUT_LOW + common.PAD_INPUT_HIGH))
    return word


def _valid_after(run: RunResult, node: str, edges: tuple[float, ...], period: float) -> float:
    """Longest time after an edge until a line is at a level the pad reads for certain."""
    time, wave = run.real("time"), run.real(node)
    worst = 0.0
    for edge in edges:
        final = measure.value_at(time, wave, edge + 0.45 * period)
        before = measure.value_at(time, wave, edge - 0.5e-9)
        if abs(final - before) < 1.0:
            continue
        level = common.PAD_INPUT_HIGH if final > before else common.PAD_INPUT_LOW
        worst = max(worst, measure.first_crossing(time, wave, level, after=edge) - edge)
    return worst


def _held_after(run: RunResult, node: str, edges: tuple[float, ...], period: float) -> float:
    """Shortest time after an edge until a line leaves the level it had."""
    time, wave = run.real("time"), run.real(node)
    best = float("inf")
    for edge in edges:
        final = measure.value_at(time, wave, edge + 0.45 * period)
        before = measure.value_at(time, wave, edge - 0.5e-9)
        if abs(final - before) < 1.0:
            continue
        level = common.PAD_INPUT_LOW if final > before else common.PAD_INPUT_HIGH
        best = min(best, measure.first_crossing(time, wave, level, after=edge) - edge)
    return best


def window(
    ctx: Context, bit_clocks: int, pad: tuple[float, ...], name: str, keep: bool = False
) -> dict[str, float]:
    """The window in which a pad reads converter data and side data, on one board.

    Two runs with the same pads and tracks. In the first the converter is at
    its largest delay and the registers at their smallest: it gives the
    instant from which the converter data is valid and the instant at which
    the side data changes again. The second has the delays the other way
    round and gives the two other instants.

    Args:
        ctx: The bench context.
        bit_clocks: System clocks per bit.
        pad: Pad, track and pin values of the board.
        name: Name of the pad case, for the titles and the files.
        keep: Keep the deck of the first run with the results.

    Returns:
        The instants after the falling clock command of the pad at which the
        window opens and closes, its width and half the clock period.
    """
    when = frame(bit_clocks)
    megahertz = 150.0 / bit_clocks
    first = ctx.run(
        f"{name}-a-{bit_clocks}",
        deck(
            ctx,
            when,
            corner(name, pad, SLOW_CONVERTER),
            0xAAAA,
            0xAAAA,
            f"Acquisition frame at {megahertz:g} MHz, {name} pad: converter slow, registers fast",
        ),
        keep=keep,
    )
    second = ctx.run(
        f"{name}-b-{bit_clocks}",
        deck(
            ctx,
            when,
            corner(name, pad, FAST_CONVERTER),
            0x5555,
            0x5555,
            f"Acquisition frame at {megahertz:g} MHz, {name} pad: converter fast, registers slow",
        ),
        keep=False,
    )
    period = when.period
    converter_valid = _valid_after(first, "gp16", when.falls[:15], period)
    side_held = _held_after(first, "gp17", when.rises[:15], period)
    side_valid = _valid_after(second, "gp17", when.rises[:15], period)
    converter_held = _held_after(second, "gp16", when.falls[:15], period)
    opens = max(converter_valid, side_valid - 0.5 * period)
    closes = min(0.5 * period + side_held, period + converter_held)
    return {
        "converter_valid": converter_valid,
        "side_valid": side_valid,
        "opens": opens,
        "closes": closes,
        "width": closes - opens,
        "half": 0.5 * period,
    }


@bench(
    "digital",
    "converter-lines",
    "Converter lines: edges behind 47 ohm and 220 ohm, cost in timing, reading window",
    "section 4.6 (D-75, D-40), section 4.7, rules F-5 and F-34",
)
def converter_lines(ctx: Context) -> Outcome:
    """Three pads of the controller run the frame of rule F-34 on the converter.

    Convert-start is high for 108 system clocks; then 16 clock pulses shift
    the result out, with 16 system clocks per bit (9.375 MHz) and with 10
    (15 MHz). The edges are read at the pins of the converter behind 47 ohm
    and 220 ohm and at the pad that reads the data behind 220 ohm. Each rate
    is run on a board with the weakest pad of the 4 mA setting and long
    tracks and on a board with a strong pad and short tracks, with the
    delays of the converter and of the registers at the limits of their
    datasheets. The reading window of a board is the time in which converter
    data and side data are both valid; the window that one fixed reading
    instant has on every board is the part that the two boards share.
    """
    figures: list[Figure] = []
    when = frame(16)
    typical = ctx.run(
        "typical-16",
        deck(ctx, when, TYPICAL, 0xA5C3, 0xB269, "Acquisition frame at 9.375 MHz, a middle case"),
    )
    late = ctx.run(
        "edges-weak",
        deck(
            ctx,
            when,
            LATE,
            0xAAAA,
            0xAAAA,
            "Acquisition frame at 9.375 MHz, weak pad, everything slow",
        ),
        keep=False,
    )
    early = ctx.run(
        "edges-strong",
        deck(
            ctx,
            when,
            EARLY,
            0x5555,
            0x5555,
            "Acquisition frame at 9.375 MHz, strong pad, everything fast",
        ),
        keep=False,
    )
    for label, run in (("weak pad, long tracks", late), ("strong pad, short tracks", early)):
        tag = label.split()[0]
        time = run.real("time")
        clock, convert = run.real("u30_sclk"), run.real("u30_cnv")
        rise, fall = when.rises[3], when.falls[3]
        up = measure.first_crossing(time, clock, _REGISTER_HIGH, rising=True, after=rise) - rise
        down = measure.first_crossing(time, clock, _REGISTER_LOW, rising=False, after=fall) - fall
        start = measure.first_crossing(
            time, convert, _REGISTER_HIGH, rising=True, after=when.convert
        )
        stop = measure.first_crossing(time, convert, _REGISTER_HIGH, rising=False, after=when.read)
        figures.append(
            Figure(
                f"clock_cost_{tag}",
                f"{label}: clock edge valid at the converter pin after the pad command",
                max(up, down),
                "s",
                expected=1e-9,
                source="section 4.6: about 1 ns on the two inputs (estimate)",
            )
        )
        figures.append(
            Figure(
                f"clock_edge_{tag}",
                f"{label}: rise time of the clock at the converter pin, 10 % to 90 %",
                measure.rise_time(time, clock, 0.33, 2.97, after=rise - 1e-9),
                "s",
                source="section 4.6: the resistors damp the edges",
            )
        )
        figures.append(
            Figure(
                f"convert_high_{tag}",
                f"{label}: convert-start above its high level at the converter pin for",
                stop - start,
                "s",
                low=710e-9,
                source="section 4.6 and rule F-34: 710 ns at the least (datasheet), 108 clocks",
            )
        )
        figures.append(
            Figure(
                f"clock_high_level_{tag}",
                f"{label}: high level of the clock at the converter pin",
                measure.value_at(time, clock, fall - 1e-9),
                "V",
                low=_REGISTER_HIGH,
                source="TI SBAS569B, page 7: 0.7 of the digital supply at the least",
            )
        )
    cost = _valid_after(late, "gp16", when.falls[:15], when.period) - 13.4e-9
    figures.append(
        Figure(
            "data_cost_weak",
            "Weak pad, long tracks: converter data valid at the pad later than the 13.4 ns "
            "of the datasheet by",
            cost,
            "s",
            expected=4e-9,
            source="sections 4.6 and 4.7: about 1 ns on the clock, 3 ns on the data (estimates)",
        )
    )
    cost = _valid_after(typical, "gp16", when.falls[:15], when.period) - (6e-9 + 2.1e-9)
    figures.append(
        Figure(
            "data_cost_typical",
            "Middle case: converter data valid at the pad later than the converter alone gives by",
            cost,
            "s",
            expected=4e-9,
            source="sections 4.6 and 4.7: about 1 ns on the clock, 3 ns on the data (estimates)",
        )
    )
    for bit_clocks, stated in ((16, 36.9e-9), (10, 16.9e-9)):
        megahertz = 150.0 / bit_clocks
        tag = f"{megahertz:g}mhz".replace(".", "p")
        weak = window(ctx, bit_clocks, WEAK_PAD, "weak", keep=bit_clocks == 10)
        strong = window(ctx, bit_clocks, STRONG_PAD, "strong")
        for name, found in (
            ("weak pad of the 4 mA setting, long tracks", weak),
            ("strong pad, short tracks", strong),
        ):
            key = name.split()[0]
            figures += [
                Figure(
                    f"window_{key}_{tag}",
                    f"{megahertz:g} MHz, {name}: window of the board",
                    found["width"],
                    "s",
                    expected=stated,
                    low=2.0 * _CLOCK,
                    source="sections 4.6 and 4.7 and rule F-34: against two system clocks, 13.3 ns",
                ),
                Figure(
                    f"window_opens_{key}_{tag}",
                    f"{megahertz:g} MHz, {name}: the window opens after the falling clock by",
                    found["opens"],
                    "s",
                    expected=17.4e-9,
                    source="section 4.7: 13.4 ns of the converter and 4 ns of the resistors",
                ),
                Figure(
                    f"window_closes_{key}_{tag}",
                    f"{megahertz:g} MHz, {name}: the window closes after the next rising clock by",
                    found["closes"] - found["half"],
                    "s",
                    expected=1e-9,
                    source="section 4.7: the smallest delay of the register, 1 ns (datasheet)",
                ),
            ]
        for tracks, label in ((LONG_TRACKS, "long tracks"), (SHORT_TRACKS, "short tracks")):
            key = label.split()[0]
            limits = (common.PAD_HIGH_OHMS, common.PAD_LOW_OHMS)
            strongest = (common.PAD_STRONG_OHMS, common.PAD_STRONG_OHMS)
            slow_board = (
                weak
                if tracks is LONG_TRACKS
                else window(ctx, bit_clocks, (*limits, *tracks), f"weak-{key}")
            )
            fast_board = (
                strong
                if tracks is SHORT_TRACKS
                else window(ctx, bit_clocks, (*strongest, *tracks), f"strong-{key}")
            )
            shared = min(slow_board["closes"], fast_board["closes"]) - max(
                slow_board["opens"], fast_board["opens"]
            )
            figures.append(
                Figure(
                    f"window_shared_{key}_{tag}",
                    f"{megahertz:g} MHz, {label}: window that one reading instant has with a weak "
                    "and with a strong pad, 4 mA setting",
                    shared,
                    "s",
                    expected=stated,
                    low=2.0 * _CLOCK,
                    source="rule F-34: the program reads at one fixed instant; against two "
                    "system clocks, 13.3 ns",
                )
            )
            if tracks is LONG_TRACKS:
                mid_board = window(ctx, bit_clocks, (*DRIVE_12MA, *tracks), "12ma")
                shared = min(mid_board["closes"], fast_board["closes"]) - max(
                    mid_board["opens"], fast_board["opens"]
                )
                figures.append(
                    Figure(
                        f"window_shared_12ma_{tag}",
                        f"{megahertz:g} MHz, {label}: the same with the weakest 12 mA pad",
                        shared,
                        "s",
                        expected=stated,
                        low=2.0 * _CLOCK,
                        source="rule F-34: against two system clocks, 13.3 ns; rule F-5 sets "
                        "4 mA on these pads",
                    )
                )
        figures.append(
            Figure(
                f"side_valid_{tag}",
                f"{megahertz:g} MHz, weak pad: side data valid at the pad after the rising clock",
                weak["side_valid"],
                "s",
                expected=18e-9,
                high=weak["half"] + weak["opens"],
                source="section 4.7: 18 ns at the most (datasheet); it has to be valid when the "
                "window opens",
            )
        )
    two = frame(10, 300)
    pair = ctx.run(
        "two-frames",
        deck(
            ctx,
            two,
            LATE,
            0xAAAA,
            0xAAAA,
            "Two frames at 500 kSPS and 15 MHz, weak pad, everything slow",
        ),
    )
    time, data = pair.real("time"), pair.real("gp16")
    read_again = two.again + two.read
    first_valid = measure.first_crossing(
        time, data, common.PAD_INPUT_HIGH, rising=True, after=read_again
    )
    convert_pin = pair.real("u30_cnv")
    clock_pin = pair.real("u30_sclk")
    last_low = common.last_crossing(time, clock_pin, _REGISTER_LOW, two.again + two.convert)
    next_start = measure.first_crossing(
        time, convert_pin, _REGISTER_LOW, rising=True, after=two.again
    )
    figures += [
        Figure(
            "first_bit_weak",
            "Second frame, weak pad: first converter bit valid at the pad after convert-start fell",
            first_valid - read_again,
            "s",
            expected=12.3e-9,
            high=two.rises[0] - two.read,
            source="rule F-34 at 15 MHz: the first rising clock command comes 5 system clocks "
            "later; TI SBAS569B, page 8: 12.3 ns at the converter",
        ),
        Figure(
            "quiet_time",
            "500 kSPS: last falling clock edge to the next rising convert-start, at the converter",
            next_start - last_low,
            "s",
            low=20e-9,
            source="section 4.6 and rule F-34: 20 ns of quiet at the least (datasheet), 4 clocks",
        ),
        Figure(
            "open_line",
            "Converter data line between the frames, at the pad: level it is left at",
            measure.value_at(time, data, two.again + two.read - 5e-9),
            "V",
            source="section 5: the line is open between frames and has no pull resistor",
        ),
    ]
    typical_time = typical.real("time")
    shown = (typical_time > when.read - 30e-9) & (typical_time < when.falls[3] + 30e-9)
    nano = (typical_time[shown] - when.read) * 1e9

    def cut(node: str) -> np.ndarray:
        return np.asarray(typical.real(node)[shown])

    graph = Graph(
        name="edges",
        title="Start of the read-out at 9.375 MHz, middle case: pads and converter pins",
        xlabel="Time after convert-start was driven low (ns)",
        panels=(
            Panel("Convert-start (V)"),
            Panel("Clock (V)"),
            Panel(
                "Data lines at the pads (V)",
                marks=((2.0, "high above 2.0 V"), (0.8, "low below 0.8 V")),
            ),
        ),
        traces=(
            Trace(nano, cut("gp20"), "pad GP20", 0),
            Trace(nano, cut("u30_cnv"), "converter pin", 0),
            Trace(nano, cut("gp19"), "pad GP19", 1),
            Trace(nano, cut("adc_sck"), "behind 47 ohm, at the registers", 1),
            Trace(nano, cut("u30_sclk"), "converter pin, behind 220 ohm more", 1),
            Trace(nano, cut("gp16"), "converter data at GP16", 2),
            Trace(nano, cut("gp17"), "side data at GP17", 2),
        ),
    )
    late_time = late.real("time")
    late_shown = (late_time > when.rises[2] - 10e-9) & (late_time < when.rises[4] + 10e-9)
    early_time = early.real("time")
    early_shown = (early_time > when.rises[2] - 10e-9) & (early_time < when.rises[4] + 10e-9)
    origin = when.falls[2]
    spread = Graph(
        name="spread",
        title="One clock period at 9.375 MHz on a weak pad with long tracks and on a strong pad",
        xlabel="Time after the falling clock command (ns)",
        panels=(
            Panel("Clock at the converter pin (V)"),
            Panel("Converter data at GP16 (V)", marks=((2.0, "2.0 V"), (0.8, "0.8 V"))),
        ),
        traces=(
            Trace(
                (late_time[late_shown] - origin) * 1e9,
                np.asarray(late.real("u30_sclk")[late_shown]),
                "weak pad",
                0,
            ),
            Trace(
                (early_time[early_shown] - origin) * 1e9,
                np.asarray(early.real("u30_sclk")[early_shown]),
                "strong pad",
                0,
            ),
            Trace(
                (late_time[late_shown] - origin) * 1e9,
                np.asarray(late.real("gp16")[late_shown]),
                "weak pad, slow",
                1,
            ),
            Trace(
                (early_time[early_shown] - origin) * 1e9,
                np.asarray(early.real("gp16")[early_shown]),
                "strong pad, fast",
                1,
            ),
        ),
    )
    notes = (
        "The frame is the one rule F-34 describes, written as ideal commands to "
        "three pad models; no program of the controller exists yet. Convert-start "
        "falls before the clocks: the converter puts its data out only while that "
        "line is low (datasheet, page 22), not while it is high as section 4.6 "
        "says.",
        "The estimates of the specification, 1 ns on the inputs and 3 ns on the "
        "data line, hold for the series resistors alone. The pad adds its own "
        "resistance, up to 170 ohm at the 4 mA setting that rule F-5 gives these "
        "pads (datasheet limit), into the registers, the converter pin and the "
        "track: a clock edge then reaches the converter up to 12 ns late.",
        "On one board the window keeps about the width that the specification "
        "calculates, because a late clock moves its opening and its closing alike. "
        "Its position moves with the output resistance of the pad, which differs "
        "from part to part: one reading instant that has to fit a weak and a strong "
        "pad on the same board has less. The figures give that shared window for a "
        "board with long tracks and for one with short tracks.",
        "Assumptions: the capacitance of the tracks (2 pF to 10 pF, twice that on "
        "the clock), of the converter pins (3 pF to 8 pF) and of the pads (3 pF to "
        "8 pF), the output resistance of the converter (40 ohm) and the strong pad "
        "of 30 ohm. The datasheets give none of them, and the weak pad is the "
        "limit of its datasheet, not a typical part. No inductance and no "
        "reflection is in the circuit.",
        "Between two frames nothing drives the converter data line; the pad sees "
        "the level of the last bit on its capacitance. The specification gives "
        "that line no pull resistor.",
    )
    return Outcome(tuple(figures), (graph, spread), notes)


@bench(
    "digital",
    "side-data",
    "Side data chain: load pulse, shift and the sixteen bits at the controller",
    "section 4.7 (D-41), rule F-34",
)
def side_data(ctx: Context) -> Outcome:
    """The two registers are loaded and shifted by the frame of rule F-34.

    The load line is low for three system clocks at the rising edge of
    convert-start; sixteen clocks later shift the sixteen bits to the pad
    GP17 through R138, while the converter shifts its word to GP16. The
    pulse widths are read at the pins of the registers and compared with
    the times that their datasheet asks for. The two words are read back at
    the pads, with 16 and with 10 system clocks per bit, with everything
    slow, everything fast and a middle case. A last run releases the pads.
    """
    figures: list[Figure] = []
    side_word, code = 0xB269, 0xA5C3
    traces: list[Trace] = []
    for bit_clocks in (16, 10):
        when = frame(bit_clocks)
        megahertz = 150.0 / bit_clocks
        tag = f"{megahertz:g}mhz".replace(".", "p")
        weak = window(ctx, bit_clocks, WEAK_PAD, "weak")
        strong = window(ctx, bit_clocks, STRONG_PAD, "strong")
        opens = max(weak["opens"], strong["opens"])
        closes = min(weak["closes"], strong["closes"])
        offset = weak["half"] - 0.5 * (opens + closes)
        wrong = 0
        for corner in (LATE, TYPICAL, EARLY):
            title = f"Side data and converter data at {megahertz:g} MHz, {corner.name} delays"
            run = ctx.run(
                f"{corner.name}-{bit_clocks}",
                deck(ctx, when, corner, code, side_word, title),
                keep=corner is TYPICAL and bit_clocks == 16,
            )
            wrong += bin(_decode(run, when, "gp17", offset) ^ side_word).count("1")
            wrong += bin(_decode(run, when, "gp16", offset) ^ code).count("1")
            if corner is LATE:
                time = run.real("time")
                load = run.real("side_load")
                falls = measure.first_crossing(
                    time, load, _REGISTER_LOW, rising=False, after=when.convert
                )
                rises = measure.first_crossing(time, load, _REGISTER_LOW, rising=True, after=falls)
                clock = run.real("adc_sck")
                up = measure.first_crossing(
                    time, clock, _REGISTER_HIGH, rising=True, after=when.rises[2]
                )
                down = measure.first_crossing(time, clock, _REGISTER_HIGH, rising=False, after=up)
                again = measure.first_crossing(
                    time, clock, _REGISTER_LOW, rising=True, after=when.rises[3]
                )
                below = measure.first_crossing(time, clock, _REGISTER_LOW, rising=False, after=up)
                first_valid = measure.first_crossing(
                    time, run.real("gp17"), common.PAD_INPUT_HIGH, rising=True, after=when.convert
                )
                figures += [
                    Figure(
                        f"load_low_{tag}",
                        f"{megahertz:g} MHz: load pin of the registers below its low level for",
                        rises - falls,
                        "s",
                        expected=_LOAD_CLOCKS * _CLOCK,
                        low=9e-9,
                        source="rule F-34: three clocks; TI SCLS402R, page 6: 9 ns at the least",
                    ),
                    Figure(
                        f"clock_high_{tag}",
                        f"{megahertz:g} MHz: clock pin of the registers above its high level for",
                        down - up,
                        "s",
                        low=7e-9,
                        source="TI SCLS402R, page 6: clock pulse 7 ns at the least",
                    ),
                    Figure(
                        f"clock_low_{tag}",
                        f"{megahertz:g} MHz: clock pin of the registers below its low level for",
                        again - below,
                        "s",
                        low=7e-9,
                        source="TI SCLS402R, page 6: clock pulse 7 ns at the least",
                    ),
                    Figure(
                        f"first_bit_{tag}",
                        f"{megahertz:g} MHz: first side bit valid at the pad after the load began",
                        first_valid - when.convert,
                        "s",
                        high=when.rises[0] - when.convert,
                        source="rule F-34: the first rising clock edge comes after the conversion",
                    ),
                ]
            if corner is TYPICAL and bit_clocks == 16:
                time = run.real("time")
                shown = time > when.read - 60e-9
                nano = (time[shown] - when.read) * 1e9
                traces += [
                    Trace(
                        nano, np.asarray(run.real("adc_sck")[shown]), "clock at the registers", 0
                    ),
                    Trace(nano, np.asarray(run.real("gp17")[shown]), "side data at GP17", 1),
                    Trace(nano, np.asarray(run.real("gp16")[shown]), "converter data at GP16", 2),
                ]
                early_time = time < when.convert + 60e-9
                load_traces = (
                    Trace(
                        time[early_time] * 1e9,
                        np.asarray(run.real("gp21")[early_time]),
                        "pad GP21",
                        0,
                    ),
                    Trace(
                        time[early_time] * 1e9,
                        np.asarray(run.real("side_load")[early_time]),
                        "load pins of the registers",
                        0,
                    ),
                    Trace(
                        time[early_time] * 1e9,
                        np.asarray(run.real("gp20")[early_time]),
                        "pad GP20",
                        1,
                    ),
                    Trace(
                        time[early_time] * 1e9,
                        np.asarray(run.real("gp17")[early_time]),
                        "side data at GP17",
                        1,
                    ),
                )
        figures.append(
            Figure(
                f"wrong_bits_{tag}",
                f"{megahertz:g} MHz: bits read wrong at the two pads in three runs, of 96",
                float(wrong),
                "",
                high=0.0,
                source="section 4.7: one word per sample holds the result and its side bits",
            )
        )
        figures.append(
            Figure(
                f"read_before_{tag}",
                f"{megahertz:g} MHz: the pads are read before the rising clock edge by",
                offset,
                "s",
                source="the middle of the window that a weak and a strong board share",
            )
        )
    floating = ctx.run(
        "released",
        deck(
            ctx,
            frame(16),
            TYPICAL,
            code,
            side_word,
            "Acquisition lines with the pads released",
            released=True,
        ),
        keep=False,
    )
    figures += [
        Figure(
            "released_load",
            "Pads released: load line of the registers",
            float(floating.real("side_load")[-1]),
            "V",
            high=_REGISTER_LOW,
            source="section 4.7: its pull-down keeps the registers loading",
        ),
        Figure(
            "released_first_bit",
            "Pads released: side data line shows the input D7 of U34 (high in this run)",
            float(floating.real("gp17")[-1]),
            "V",
            low=common.PAD_INPUT_HIGH,
            source="section 4.7: with the load line low the registers follow their inputs",
        ),
    ]
    graph = Graph(
        name="frame",
        title="Read-out at 9.375 MHz, middle case: side word 0xB269 and converter word 0xA5C3",
        xlabel="Time after convert-start was driven low (ns)",
        panels=(
            Panel("Clock (V)"),
            Panel("Side data (V)", marks=((2.0, "2.0 V"), (0.8, "0.8 V"))),
            Panel("Converter data (V)", marks=((2.0, "2.0 V"), (0.8, "0.8 V"))),
        ),
        traces=tuple(traces),
    )
    load_graph = Graph(
        name="load",
        title="The load pulse at the rising edge of convert-start, middle case",
        xlabel="Time (ns)",
        panels=(Panel("Load line (V)"), Panel("Convert-start pad and side data (V)")),
        traces=load_traces,
    )
    notes = (
        "The first side bit is the input D7 of U34, MUX_A1; the sixteenth is D0 of "
        "U33, DIN0. The side word of the runs is 0xB269 and the converter word "
        "0xA5C3, so that neighbors differ in both.",
        "The pads are read at one instant per bit, in the middle of the window that "
        "the bench converter-lines finds. A program of the controller reads on a "
        "grid of 6.7 ns and through a synchronizer; where that instant falls is not "
        "decided yet.",
        "The register model does not check its own timing; the pulse widths are "
        "read at its pins and compared with its datasheet. Data inputs that change "
        "during a load are not in these runs: the inputs are held.",
    )
    return Outcome(tuple(figures), (graph, load_graph), notes)
