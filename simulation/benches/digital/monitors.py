"""The monitor converter: its eight channels at rest and while it samples them."""

from __future__ import annotations

import numpy as np

from benches.digital import common
from benches.models.digital_mcp3208 import sample_window, sources
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.tolerance import corner_scales, tolerances

_LSB = 2.5 / 4096.0
"""One step of the monitor converter with the 2.5 V reference."""

_CHANNELS = {
    0: ("ladder output", 0.4545),
    1: ("VIN", 1.0 / 44.0),
    2: ("5 V rail, USB-C in use", 0.4545),
    6: ("+12 V_A", 0.1754),
}
"""Scale of the plain dividers (specification, table of section 4.2)."""

_UPPER = ("R140", "R141", "R142", "R147", "R148")
"""Resistors from a source to a converter input."""

_LOWER = ("R149", "R150", "R151", "R152", "R153", "R143")
"""Resistors from a converter input to ground, to the status line or to -4 V."""

_LEAK = 1e-6
"""Largest leakage of an analog input of the converter (Microchip DS21298E, page 3)."""

_SPI_PERIOD = 2e-6
"""Clock period of the slow SPI bus: 500 kHz (rule F-6)."""

_TRACK = 10e-12
"""Capacitance of a slow SPI track with its two branches (assumption)."""


def _refs(ctx: Context) -> tuple[str, ...]:
    """The monitor sheet, the resistors of the slow SPI lines and the pins of the DAC."""
    return (*ctx.netlist.on_sheet(common.MONITOR_SHEET), "RN1", "RN2", "U15")


def _sources(values: dict[str, float], module_input: bool) -> str:
    """Ideal sources for everything a channel reads."""
    lines = [
        "* what the channels read, as ideal sources",
        f"Vout vout_buf 0 {values['vout']:g}",
        f"Vin vin_p 0 {values['vin']:g}",
        f"Vrail v5 0 {values['rail']:g}",
        f"Vcc1 cc1 0 {values['cc1']:g}",
        f"Vcc2 cc2 0 {values['cc2']:g}",
        f"Vp12 v12 0 {values['p12']:g}",
        f"Vm4 vm4 0 {values['m4']:g}",
        f"Vref vref 0 {values['vref']:g}",
        f"Vanalog v3a 0 {values['v3a']:g}",
        "* the select of the DAC rests high; its pad and resistors are not here",
        f"Vdac c_dac_cs 0 {values['v3a']:g}",
    ]
    if module_input:
        lines.append(
            "* the input of the module supplies: the status output of the multiplexer is low"
        )
        lines.append("Vst src_st 0 0")
    return "\n".join(lines)


_NOMINAL = {
    "vout": 5.0,
    "vin": 5.0,
    "rail": 5.0,
    "cc1": 0.92,
    "cc2": 0.0,
    "p12": 12.0,
    "m4": -4.0,
    "vref": 2.5,
    "v3a": 3.3,
}
"""Voltages of the nominal case."""


def _idle_spi() -> str:
    """The three lines of the bus at rest: select high, clock and data low."""
    return "\n".join(
        [
            "* the bus at rest: select high, clock and data low, as ideal sources",
            "Vcs gp13 0 3.3",
            "Vck gp14 0 0",
            "Vdi gp15 0 0",
        ]
    )


def _static_deck(
    ctx: Context,
    title: str,
    values: dict[str, float],
    module_input: bool = False,
    scales: dict[str, float] | None = None,
    leak: float = 0.0,
    celsius: float = 27.0,
) -> str:
    circuit = ctx.circuit(
        _refs(ctx), common.ALIASES, overrides={"U15": common.MCP4921_PINS}, scales=scales
    )
    lines = [_sources(values, module_input), _idle_spi()]
    if leak:
        lines.append("* leakage of the analog inputs at the limit of the datasheet")
        lines += [f"Ileak{index} ch{index} 0 {leak:g}" for index in range(8)]
    return ctx.deck(
        title,
        circuit,
        "\n".join(lines),
        control=["tran 1u 50u"],
        options=(f"temp={celsius:g}",),
    )


def _pins(ctx: Context, name: str, deck: str, keep: bool = False) -> list[float]:
    run = ctx.run(name, deck, keep=keep)
    return [float(run.real(f"ch{index}")[-1]) for index in range(8)]


@bench(
    "digital",
    "monitor-channels",
    "Monitor channels at rest: scale, tolerance, input leakage, VIN at -20 V and +20 V",
    "section 4.2 (D-80), rules F-11, F-12, F-26 and F-28, section 16",
)
def monitor_channels(ctx: Context) -> Outcome:
    """Every channel of the monitor converter is read at rest.

    The sources of the eight channels are ideal; the dividers, the filter
    capacitors, the temperature sensor and the inputs of the converter come
    from the schematic. The voltage at each converter input is compared with
    the scale of the specification. The run is repeated with the resistors
    at the limits of their tolerance, with the input of the module as the
    supply (the status line low), with the leakage of the converter inputs
    at the limit of the datasheet in either direction, with VIN at -20 V
    and +20 V, and at -20 C and 100 C for the temperature channel.
    """
    figures: list[Figure] = []
    nominal = _pins(
        ctx,
        "nominal",
        _static_deck(ctx, "Monitor channels at rest, nominal values", _NOMINAL),
        keep=True,
    )
    drive = {0: _NOMINAL["vout"], 1: _NOMINAL["vin"], 2: _NOMINAL["rail"], 6: _NOMINAL["p12"]}
    for index, (label, scale) in _CHANNELS.items():
        figures.append(
            near(
                f"scale_ch{index}",
                f"Channel {index}, {label}: scale at the converter input",
                nominal[index] / drive[index],
                "",
                scale,
                0.002,
                "section 4.2, table of the channels (calculated)",
            )
        )
    figures += [
        near(
            "scale_ch3",
            "Channel 3, CC1 at 0.92 V: converter input",
            nominal[3],
            "V",
            0.92,
            0.002,
            "section 4.2: times 1 behind 10 kohm",
        ),
        near(
            "ch7_nominal",
            "Channel 7, -4 V_A at -4.00 V: converter input",
            nominal[7],
            "V",
            0.333 * -4.0 + 1.667,
            0.01,
            "section 4.2: 0.333 x V + 1.667 V",
        ),
        near(
            "ch5_room",
            "Channel 5, temperature sensor at 27 C: converter input",
            nominal[5],
            "V",
            0.77,
            0.01,
            "Microchip DS20001942L: 500 mV and 10 mV per kelvin",
        ),
    ]
    module = _pins(
        ctx,
        "module-input",
        _static_deck(
            ctx, "Monitor channels: the input of the module supplies", _NOMINAL, module_input=True
        ),
    )
    figures.append(
        near(
            "scale_ch2_module",
            "Channel 2 with the input of the module in use: scale",
            module[2] / _NOMINAL["rail"],
            "",
            0.2524,
            0.002,
            "section 4.2 and rule F-11 (calculated)",
        )
    )
    spread = tolerances(ctx.netlist, (*_UPPER, *_LOWER))
    low_set = corner_scales(spread, {**dict.fromkeys(_UPPER, 1), **dict.fromkeys(_LOWER, -1)})
    high_set = corner_scales(spread, {**dict.fromkeys(_UPPER, -1), **dict.fromkeys(_LOWER, 1)})
    band: dict[str, list[float]] = {}
    for rail in (4.25, 5.50):
        values = {**_NOMINAL, "rail": rail}
        for name, scales in (("low", low_set), ("high", high_set)):
            for module_input in (False, True):
                key = "module" if module_input else "usbc"
                pins = _pins(
                    ctx,
                    f"band-{rail:g}-{name}-{key}".replace(".", "p"),
                    _static_deck(
                        ctx,
                        f"Monitor channels at the tolerance limits, rail {rail:g} V",
                        values,
                        module_input,
                        scales,
                    ),
                )
                band.setdefault(key, []).append(pins[2])
                if rail == 5.5 and not module_input:
                    band.setdefault(f"all-{name}", pins)
    figures += [
        Figure(
            "band_usbc_low",
            "Channel 2, USB-C in use, rail at 4.25 V, resistors at their limits: lowest reading",
            min(band["usbc"]),
            "V",
            expected=1.93,
            low=1.67,
            source="section 4.2 and rule F-11: band 1.93 V to 2.50 V, separated at 1.67 V",
        ),
        Figure(
            "band_usbc_high",
            "Channel 2, USB-C in use, rail at 5.50 V, resistors at their limits: highest reading",
            max(band["usbc"]),
            "V",
            expected=2.50,
            high=2.5,
            source="section 4.2: band up to 2.50 V; the converter reads up to 2.5 V",
        ),
        Figure(
            "band_module_high",
            "Channel 2, input of the module in use, rail at 5.50 V: highest reading",
            max(band["module"]),
            "V",
            expected=1.39,
            high=1.67,
            source="section 4.2 and rule F-11: band 1.07 V to 1.39 V, separated at 1.67 V",
        ),
        Figure(
            "band_module_low",
            "Channel 2, input of the module in use, rail at 4.25 V: lowest reading",
            min(band["module"]),
            "V",
            expected=1.07,
            source="section 4.2: band from 1.07 V",
        ),
    ]
    tolerance_values = {**_NOMINAL, "rail": 5.5}
    reference = _pins(
        ctx, "rail-5v5", _static_deck(ctx, "Monitor channels, rail at 5.50 V", tolerance_values)
    )
    for index, label in (
        (0, "ladder output"),
        (1, "VIN"),
        (2, "5 V rail"),
        (6, "+12 V_A"),
        (7, "-4 V_A"),
    ):
        worst = max(
            abs(band["all-low"][index] - reference[index]),
            abs(band["all-high"][index] - reference[index]),
        )
        figures.append(
            Figure(
                f"tolerance_ch{index}",
                f"Channel {index}, {label}: largest change of the input with resistors at 1 %",
                worst / abs(reference[index]) * 100.0,
                "%",
                source="section 4.2: the scale factors are calculated from nominal values",
            )
        )
    leaky = _pins(
        ctx,
        "leakage",
        _static_deck(
            ctx, "Monitor channels with 1 uA of leakage out of every input", _NOMINAL, leak=_LEAK
        ),
    )
    for index, label, back, limit, rule in (
        (
            0,
            "ladder output",
            1.0 / 0.4545,
            0.100,
            "rule F-28: channel 0 within 100 mV of the set-point",
        ),
        (1, "VIN", 44.0, 0.13, "rule F-26: a true 0.8 V may read 0.67 V before calibration"),
        (2, "5 V rail", 1.0 / 0.4545, None, "rule F-12: limits of 4.25 V and 5.50 V"),
        (6, "+12 V_A", 1.0 / 0.1754, 0.6, "rule F-12: window of 11.4 V to 12.6 V"),
        (7, "-4 V_A", 3.0, 0.3, "rule F-12: window of -4.3 V to -3.7 V"),
    ):
        figures.append(
            Figure(
                f"leakage_ch{index}",
                f"Channel {index}, {label}: error of the reading with 1 uA of input leakage",
                abs(leaky[index] - nominal[index]) * back,
                "V",
                high=limit,
                source=rule + "; Microchip DS21298E, page 3: 1 uA at the most, 1 nA typical",
            )
        )
    for volts in (-20.0, 20.0):
        tag = "minus" if volts < 0 else "plus"
        for supply, word in ((3.3, "supplied"), (0.0, "without supply")):
            values = {**_NOMINAL, "vin": volts, "v3a": supply, "vref": 2.5 if supply else 0.0}
            pins = _pins(
                ctx,
                f"vin-{tag}-{'on' if supply else 'off'}",
                _static_deck(
                    ctx, f"Monitor channels with {volts:+g} V at VIN, converter {word}", values
                ),
            )
            figures.append(
                Figure(
                    f"vin_{tag}_{'on' if supply else 'off'}",
                    f"VIN at {volts:+g} V, converter {word}: voltage at its input",
                    pins[1],
                    "V",
                    expected=volts / 44.0,
                    low=-0.5,
                    high=0.5,
                    source="section 16: within 0.5 V of ground with -20 V and +20 V at VIN "
                    "(rating 0.6 V beyond the rails, datasheet)",
                )
            )
    for celsius, stated in ((-20.0, 0.3), (100.0, 1.5)):
        pins = _pins(
            ctx,
            f"temp-{celsius:g}".replace("-", "m"),
            _static_deck(ctx, f"Monitor channels at {celsius:g} C", _NOMINAL, celsius=celsius),
        )
        figures.append(
            near(
                f"ch5_{celsius:g}c".replace("-", "m"),
                f"Channel 5 at {celsius:g} C: converter input",
                pins[5],
                "V",
                stated,
                0.01,
                "rule F-12: channel 5 between 0.3 V and 1.5 V",
            )
        )
    sweep_volts = np.linspace(-20.0, 20.0, 41)
    sweep = [
        _pins(
            ctx,
            f"sweep-{index}",
            _static_deck(ctx, "Monitor channels, VIN stepped", {**_NOMINAL, "vin": float(volts)}),
        )[1]
        for index, volts in enumerate(sweep_volts)
    ]
    graph = Graph(
        name="vin",
        title="Channel 1: converter input against the voltage at VIN, converter supplied",
        xlabel="Voltage at VIN (V)",
        panels=(Panel("Converter input (V)", marks=((0.5, "0.5 V"), (-0.5, "-0.5 V"))),),
        traces=(Trace(sweep_volts, np.array(sweep), "", 0),),
    )
    notes = (
        "The converter model has the input structure of the datasheet and no "
        "error of its own: offset 3 LSB, gain 5 LSB and linearity 1 LSB at the "
        "most add to every figure here.",
        "The leakage of an analog input is 1 nA typical and 1 uA at the most "
        "(datasheet). The specification does not name it. At the limit it shifts "
        "channel 0 by more than the 100 mV of rule F-28 and channel 1 by more than "
        "the allowance of rule F-26, through the 54.5 kohm and 9.8 kohm of their "
        "dividers; at the typical value the shift is a thousand times smaller. "
        "Rule F-26 stores the offset of channel 1 at calibration; no rule does so "
        "for channel 0.",
        "With VIN at +20 V or -20 V the diodes of the converter input start to "
        "conduct a few microamperes and hold the input at about 0.42 V: the rating "
        "of 0.6 V is kept, and a current flows into the substrate or the supply of "
        "the converter that the datasheet does not rate.",
        "The CC pins and the status line are ideal sources; the resistors of the "
        "USB-C receptacle and the multiplexer are not in this circuit.",
    )
    return Outcome(tuple(figures), (graph,), notes)


def _scan_deck(
    ctx: Context,
    title: str,
    frames: list[tuple[float, int]],
    end: float,
    values: dict[str, float],
    reset: bool,
    pad_high: float,
    pad_low: float,
) -> str:
    """Frames of the slow SPI bus from three pads of the controller."""
    part = ctx.models.model_of(ctx.netlist.component("U40"))
    overrides = {"U15": common.MCP4921_PINS}
    if reset:
        overrides["U40"] = common.with_params(part, reset=1, vres=0)
    circuit = ctx.circuit(_refs(ctx), common.ALIASES, overrides=overrides)
    pads = [
        common.Pad("gp13", "gp13", pad_high, pad_low),
        common.Pad("gp14", "gp14", pad_high, pad_low),
        common.Pad("gp15", "gp15", pad_high, pad_low),
        common.Pad("gp12", "gp12"),
    ]
    lines = [
        _sources(values, module_input=False),
        common.module_supply().rstrip(),
        "* three pads of the controller drive the bus, one reads",
        *[pad.line() for pad in pads],
        sources(frames, _SPI_PERIOD, 1.0, ("gp13_ctl", "gp14_ctl", "gp15_ctl")),
        "Vgp13_oe gp13_oe 0 1",
        "Vgp14_oe gp14_oe 0 1",
        "Vgp15_oe gp15_oe 0 1",
        "Vgp12_ctl gp12_ctl 0 0",
        "Vgp12_oe gp12_oe 0 0",
        "* tracks of the bus (assumption)",
        f"Ct1 c_sck 0 {_TRACK:g}",
        f"Ct2 c_mosi 0 {_TRACK:g}",
        f"Ct3 c_mon_cs 0 {_TRACK:g}",
    ]
    return ctx.deck(
        title,
        circuit,
        "\n".join(lines),
        control=[
            "save ch0 ch1 ch2 ch3 ch4 ch5 ch6 ch7 c_sck c_mosi c_mon_cs gp14 xu40.samp",
            f"tran 20n {end:g} 0 20u",
        ],
        libraries=(common.LIBRARY,),
    )


def _held(run_time: np.ndarray, samp: np.ndarray, start: float) -> float:
    """The voltage on the sampling capacitor when the sampling of a frame has ended."""
    _, closes = sample_window(start, _SPI_PERIOD)
    return measure.value_at(run_time, samp, closes + 3e-6)


@bench(
    "digital",
    "monitor-sampling",
    "Monitor converter while it samples: charge step, settling, edges of the slow SPI bus",
    "section 4.2, section 5 (slow SPI bus), rules F-6 and F-10",
)
def monitor_sampling(ctx: Context) -> Outcome:
    """Three pads of the controller read the monitor converter over the slow SPI bus.

    The frames are those of the converter datasheet at 500 kHz, through the
    2.2 kohm of RN1. First all eight channels are read in turn, 1.25 ms
    apart, for five cycles of 10 ms, and the voltage that each sample holds
    is compared with the voltage of its channel at rest. Then channel 0
    alone is read at 100 SPS, at 1 kSPS and at 2 kSPS with a sampling
    capacitor that starts every sample from 0 V, the worst case that the
    specification calculates with. The edges of the clock are read at the
    converter.
    """
    figures: list[Figure] = []
    values = {**_NOMINAL, "vout": 5.5}
    rest = _pins(
        ctx, "rest", _static_deck(ctx, "Monitor channels at rest, output at 5.5 V", values)
    )
    cycle, cycles = 10e-3, 5
    frames = [
        (0.2e-3 + index * cycle + channel * cycle / 8.0, channel)
        for index in range(cycles)
        for channel in range(8)
    ]
    run = ctx.run(
        "scan",
        _scan_deck(
            ctx,
            "Monitor scan: eight channels at 100 SPS each, five cycles",
            frames,
            cycles * cycle + 0.1e-3,
            values,
            reset=False,
            pad_high=common.PAD_HIGH_OHMS,
            pad_low=common.PAD_LOW_OHMS,
        ),
    )
    time, samp = run.real("time"), run.real("xu40.samp")
    last = frames[-8:]
    worst_channel, worst = 0, 0.0
    for start, channel in last:
        error = (_held(time, samp, start) - rest[channel]) / _LSB
        if abs(error) > abs(worst):
            worst_channel, worst = channel, error
        if channel in (0, 2, 7):
            figures.append(
                Figure(
                    f"scan_ch{channel}",
                    f"Scan of eight channels at 100 SPS: error of the sample of channel {channel}",
                    error,
                    "LSB",
                    expected=-0.97 if channel == 0 else None,
                    low=-0.97 * 1.05,
                    high=0.97 * 1.05,
                    source="section 4.2 and rule F-10: 0.97 LSB at the sampled instant at 100 SPS "
                    "(calculated for a capacitor that starts 2.5 V away)",
                )
            )
    figures.append(
        Figure(
            "scan_worst",
            f"Scan of eight channels at 100 SPS: largest sample error, channel {worst_channel}",
            abs(worst),
            "LSB",
            high=0.97 * 1.05,
            source="rule F-10: 0.97 LSB behind 54.5 kohm and 66.7 kohm",
        )
    )
    clock = run.real("c_sck")
    start0 = frames[0][0]
    first_rise = start0 + 0.5 * _SPI_PERIOD
    top = measure.value_at(time, clock, first_rise + 0.45 * _SPI_PERIOD)
    edge = measure.rise_time(time, clock, 0.1 * top, 0.9 * top, after=first_rise - 10e-9)
    high_from = measure.first_crossing(
        time, clock, 0.7 * 3.3, rising=True, after=first_rise - 10e-9
    )
    high_to = measure.first_crossing(time, clock, 0.7 * 3.3, rising=False, after=high_from)
    low_to = measure.first_crossing(time, clock, 0.3 * 3.3, rising=True, after=high_to)
    low_from = measure.first_crossing(time, clock, 0.3 * 3.3, rising=False, after=high_from)
    figures += [
        Figure(
            "clock_edge",
            "Clock at the converter behind 2.2 kohm, weakest pad: rise time, 10 % to 90 %",
            edge,
            "s",
            expected=156e-9,
            high=1.15 * 156e-9,
            source="section 5 and rule F-6: 156 ns (calculated); within 15 %",
        ),
        Figure(
            "clock_level",
            "Clock at the converter, weakest pad: high level against the 4.7 kohm pull-down",
            top,
            "V",
            low=0.7 * 3.3,
            source="Microchip DS21298E, page 3: 0.7 of the supply at the least",
        ),
        Figure(
            "clock_high",
            "Clock at the converter at 500 kHz: time above its high level",
            high_to - high_from,
            "s",
            low=500e-9,
            source="Microchip DS21298E, page 3: 1 MHz at 2.7 V, half a period of 500 ns",
        ),
        Figure(
            "clock_low",
            "Clock at the converter at 500 kHz: time below its low level",
            low_to - low_from,
            "s",
            low=500e-9,
            source="Microchip DS21298E, page 3: 1 MHz at 2.7 V, half a period of 500 ns",
        ),
    ]
    traces: list[Trace] = []
    for rate, stated in ((100.0, 0.97), (1000.0, 4.9), (2000.0, None)):
        period = 1.0 / rate
        count = max(6, round(40e-3 * rate))
        alone = [(0.2e-3 + index * period, 0) for index in range(count)]
        tag = f"{rate:g}sps"
        single = ctx.run(
            f"alone-{tag}",
            _scan_deck(
                ctx,
                f"Channel 0 alone at {rate:g} SPS, sampling capacitor from 0 V each time",
                alone,
                alone[-1][0] + 0.2e-3,
                values,
                reset=True,
                pad_high=common.PAD_HIGH_OHMS,
                pad_low=common.PAD_LOW_OHMS,
            ),
            keep=rate == 1000.0,
        )
        t_single, s_single = single.real("time"), single.real("xu40.samp")
        error = (_held(t_single, s_single, alone[-1][0]) - rest[0]) / _LSB
        figures.append(
            Figure(
                f"worst_{tag}",
                f"Channel 0 at {rate:g} SPS, capacitor from 0 V each time: error of the sample",
                -error,
                "LSB",
                expected=stated,
                low=0.9 * stated if stated else None,
                high=1.1 * stated if stated else None,
                source="section 4.2 and rule F-10 (calculated); within 10 %"
                if stated
                else "rule F-10: more at the rate of the exception of rule F-33 (0.5 ms)",
            )
        )
        figures.append(
            Figure(
                f"worst_volts_{tag}",
                f"Channel 0 at {rate:g} SPS: the same error as a voltage at the output",
                -error * _LSB / 0.4545,
                "V",
                expected=1.3e-3 if rate == 100.0 else None,
                source="section 4.2: 1.3 mV at VOUT at 100 SPS",
            )
        )
        pin = single.real("ch0")
        traces.append(Trace(t_single * 1e3, (rest[0] - pin) * 1e3, f"{rate:g} SPS", 0))
    first = frames[0][0]
    shown = (time > first - 2e-6) & (time < first + 16e-6)
    micro = (time[shown] - first) * 1e6
    frame_graph = Graph(
        name="frame",
        title="Start of a frame at 500 kHz behind 2.2 kohm: clock, data and the sampling capacitor",
        xlabel="Time after the select was driven low (us)",
        panels=(
            Panel("Clock (V)", marks=((2.31, "0.7 x supply"), (0.99, "0.3 x supply"))),
            Panel("Select and data input at the converter (V)"),
            Panel("Sampling capacitor (V)"),
        ),
        traces=(
            Trace(micro, np.asarray(run.real("gp14")[shown]), "pad GP14", 0),
            Trace(micro, np.asarray(clock[shown]), "converter pin", 0),
            Trace(micro, np.asarray(run.real("c_mon_cs")[shown]), "select", 1),
            Trace(micro, np.asarray(run.real("c_mosi")[shown]), "data input", 1),
            Trace(micro, np.asarray(samp[shown]), "sampling capacitor", 2),
        ),
    )
    droop = Graph(
        name="droop",
        title="Converter input of channel 0 below its level at rest, capacitor from 0 V each time",
        xlabel="Time (ms)",
        panels=(Panel("Level at rest less converter input (mV)"),),
        traces=tuple(traces),
    )
    notes = (
        "The sampling capacitor of the converter model keeps the voltage of the "
        "channel before: in a scan every sample then starts from its neighbor "
        "channel, which is less than the 2.5 V of the calculation of the "
        "specification. The runs with channel 0 alone set the capacitor to 0 V "
        "before every sample and repeat that calculation.",
        "The frames are 1.25 ms apart in the scan; the specification says 100 SPS "
        "per channel and not how the eight frames are placed in the 10 ms.",
        "The output of the converter is not in the model, so the line to the pad "
        "GP12 is not judged. Each track of the bus has 10 pF (assumption); the "
        "pins have the 10 pF of the datasheets.",
        "The pads are at the limit of the 4 mA setting, 170 ohm and 125 ohm.",
    )
    return Outcome(tuple(figures), (frame_graph, droop), notes)
