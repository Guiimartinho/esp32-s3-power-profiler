"""Too much voltage and the wrong polarity at the USB-C receptacle."""

from __future__ import annotations

import numpy as np

from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_PLUG = 0.1e-3
"""Instant at which the source is connected."""

_RAMP_START = 7.0e-3
"""Instant at which the source starts to rise from 5 V: the carrier runs at idle."""

_RAMP_END = 14.5e-3
"""Instant at which the source has reached 12.5 V."""

_END = 15e-3
"""End of the runs with a rising source."""

_TOP = 12.5
"""Highest voltage of the source."""

_REVERSE_END = 2e-3
"""End of the run with a reversed source."""

_REVERSE_AMPS = 3.0
"""Current that the reversed source gives: a USB-C source of 3 A."""

_PIN_LOW = -0.3
"""Lowest voltage at the input of the limiter and at an input of the
multiplexer (absolute maximum ratings: TPS2596 SLVSET8A page 5, TPS2116
SLVSFG1A page 4)."""

_UNITS = {
    "typical": "",
    "high": "vovc=5.83 vclamp=5.61",
    "low": "vovc=5.54 vclamp=5.28",
}
"""The limiter of the USB-C input: typical, and with the highest and the
lowest clamp threshold and clamp level of its datasheet (page 6)."""


def _rise_deck(ctx: Context, unit: str) -> str:
    """The running carrier on a source that rises from 5 V to 12.5 V."""
    params = {"U6": common.FAST_SUPERVISOR}
    if _UNITS[unit]:
        params["U4"] = _UNITS[unit]
    circuit = common.circuit(ctx, common.carrier_refs(ctx.netlist), params=params)
    waveform = f"PWL(0 5 {_RAMP_START:g} 5 {_RAMP_END:g} {_TOP:g})"
    stimulus = (
        common.usb_c_source(5.0, _PLUG, waveform=waveform)
        + common.boost_start()
        + common.idle_loads()
    )
    control = ["save all @b.xu5.b1[i]", common.transient(1e-6, _END)]
    return ctx.deck(
        f"USB-C source rising from 5 V to 12.5 V, {unit} limiter",
        circuit,
        stimulus,
        control=control,
    )


def _reverse_deck(ctx: Context) -> str:
    """A source of the wrong polarity, 5 V and 3 A, at the receptacle."""
    circuit = common.circuit(ctx, common.carrier_refs(ctx.netlist))
    stimulus = (
        common.usb_c_source(-5.0, _PLUG, amps=_REVERSE_AMPS)
        + common.boost_start()
        + common.idle_loads()
    )
    return ctx.deck(
        "USB-C source of the wrong polarity, 5 V and 3 A",
        circuit,
        stimulus,
        control=[common.transient(0.5e-6, _REVERSE_END)],
    )


def _source_volts(time: np.ndarray) -> np.ndarray:
    """The voltage of the rising source at each instant."""
    slope = (_TOP - 5.0) / (_RAMP_END - _RAMP_START)
    return np.asarray(5.0 + slope * np.clip(time - _RAMP_START, 0.0, _RAMP_END - _RAMP_START))


def _at_source(run: RunResult, name: str, volts: float) -> float:
    """The value of a waveform when the rising source stands at a voltage."""
    time = run.real("time")
    instant = _RAMP_START + (volts - 5.0) / (_TOP - 5.0) * (_RAMP_END - _RAMP_START)
    return measure.value_at(time, run.real(name), instant)


@bench(
    "power_input",
    "overvoltage",
    "Too much voltage and the wrong polarity at the USB-C receptacle",
    "section 4.1 (limits of the USB-C input, thresholds of the 5 V rail), section 11",
)
def overvoltage(ctx: Context) -> Outcome:
    """The source at the USB-C receptacle rises from 5 V to 12.5 V; another one is reversed.

    The carrier runs at idle when the source starts to rise by 1 V per
    millisecond. The limiter lets the rail follow up to its clamp threshold
    and then holds its output at the clamp level; from 11.1 V to 12.3 V the
    suppressor conducts. The run is repeated with the highest and the lowest
    clamp of the datasheet of the limiter. In a last run a source of 5 V and
    3 A is connected with the wrong polarity.
    """
    decks = {unit: _rise_deck(ctx, unit) for unit in _UNITS}
    decks["reverse"] = _reverse_deck(ctx)
    runs = common.run_all(ctx, decks, keep=("typical", "reverse"))
    typical, high, low = runs["typical"], runs["high"], runs["low"]
    time = typical.real("time")
    rising = common.cut(time, _RAMP_START, _END)
    source = _source_volts(time)
    amps = typical.real("vusbc_i#branch")
    suppressor = typical.real("v.xd2.vz#branch") if ctx.tier == "open" else np.zeros_like(time)
    watts = (typical.real("vbus_c") - typical.real("vin1")) * typical.real("@b.xu5.b1[i]")
    figures = [
        Figure(
            "rail_5v5",
            "Typical limiter: rail with 5.5 V at the source",
            _at_source(typical, "rail", 5.5),
            "V",
            high=5.5,
            source="section 4.1: 5.50 V is the highest rail in operation",
        ),
        Figure(
            "rail_peak_typical",
            "Typical limiter: highest level of the rail while the source rises",
            float(np.max(typical.real("rail")[rising])),
            "V",
            expected=5.69,
            high=5.83,
            source="section 4.1: a source up to 5.83 V can reach the rail without being clamped",
        ),
        Figure(
            "rail_peak_high",
            "Limiter with the highest clamp threshold: highest level of the rail",
            float(np.max(high.real("rail")[common.cut(high.real("time"), _RAMP_START, _END)])),
            "V",
            high=5.83,
            source="section 4.1: a source up to 5.83 V can reach the rail without being clamped",
        ),
        Figure(
            "rail_8v",
            "Typical limiter: rail with 8 V at the source",
            _at_source(typical, "rail", 8.0),
            "V",
            expected=5.45,
            low=5.28,
            high=5.61,
            source="section 4.1: output clamped at 5.28 V to 5.61 V (datasheet)",
        ),
        Figure(
            "rail_10v",
            "Typical limiter: rail with 10 V at the source",
            _at_source(typical, "rail", 10.0),
            "V",
            expected=5.45,
            low=5.28,
            high=5.61,
            source="section 4.1: output clamped at 5.28 V to 5.61 V (datasheet)",
        ),
        Figure(
            "rail_10v_low",
            "Limiter with the lowest clamp: rail with 10 V at the source",
            _at_source(low, "rail", 10.0),
            "V",
            low=common.RAIL_FIRMWARE_LIMIT,
            source="section 4.1: the rail has to stay above the firmware limit, 4.25 V",
        ),
        Figure(
            "limiter_watts_10v",
            "Typical limiter: dissipation of the limiter with 10 V at the source, idle carrier",
            float(np.interp(10.0, source[rising], watts[rising])),
            "W",
        ),
        Figure(
            "v3a_10v",
            "Typical limiter: 3V3_A with 10 V at the source",
            _at_source(typical, "v3a", 10.0),
            "V",
            low=3.3 * 0.98,
            high=3.3 * 1.02,
            source="LP5907 datasheet, page 5: 2 %",
        ),
        Figure(
            "suppressor_10v",
            "Typical suppressor: current of its breakdown path with 10 V at the source",
            float(np.interp(10.0, source[rising], suppressor[rising])),
            "A",
            high=1e-6 * 1.1,
            source="suppressor datasheet: 1 uA at most at 10 V",
        ),
        Figure(
            "suppressor_12v5",
            "Typical suppressor: its current with 12.5 V at the source",
            float(np.interp(_TOP, source[rising], suppressor[rising])),
            "A",
        ),
        Figure(
            "suppressor_watts",
            "Typical suppressor: its dissipation with 12.5 V at the source",
            float(np.interp(_TOP, source[rising], suppressor[rising]))
            * _at_source(typical, "vbus_c", _TOP - 0.01),
            "W",
            high=3.3,
            source="suppressor datasheet, page 1: 3.3 W on an infinite heat sink; section "
            "4.1: a source that delivers amperes destroys it",
        ),
        Figure(
            "source_amps_12v5",
            "Current from the source with 12.5 V",
            float(np.interp(_TOP, source[rising], amps[rising])),
            "A",
        ),
    ]
    reverse = runs["reverse"]
    t_rev = reverse.real("time")
    settled = common.cut(t_rev, _PLUG + 0.5e-3, _REVERSE_END)
    figures += [
        Figure(
            "reverse_receptacle",
            "Reversed source of 3 A: voltage at the receptacle and at the input of the limiter",
            float(np.mean(reverse.real("vbus_c")[settled])),
            "V",
            low=_PIN_LOW,
            source="TPS2596 datasheet, page 5: -0.3 V at the input; the specification "
            "states no figure",
        ),
        Figure(
            "reverse_input1",
            "Reversed source of 3 A: voltage at input 1 of the multiplexer",
            float(np.mean(reverse.real("vin1")[settled])),
            "V",
            low=_PIN_LOW,
            source="TPS2116 datasheet, page 4: -0.3 V at an input; the specification "
            "states no figure",
        ),
        Figure(
            "reverse_rail",
            "Reversed source of 3 A: lowest level of the rail",
            float(np.min(reverse.real("rail")[settled])),
            "V",
            low=_PIN_LOW,
            source="LP5907 datasheet, page 4: -0.3 V at the input",
        ),
        Figure(
            "reverse_amps",
            "Reversed source of 3 A: current in the cable",
            float(np.mean(reverse.real("vusbc_i#branch")[settled])),
            "A",
        ),
    ]
    volts = source[rising]
    graph = Graph(
        name="rise",
        title="The source at the receptacle rises from 5 V to 12.5 V; the carrier runs at idle",
        xlabel="Voltage of the source (V)",
        panels=(
            Panel("Voltage (V)", marks=((5.5, "highest rail in operation 5.5 V"),)),
            Panel("Current (A)"),
        ),
        traces=(
            Trace(volts, typical.real("vbus_c")[rising], "receptacle", 0),
            Trace(volts, typical.real("rail")[rising], "5 V rail, typical limiter", 0),
            Trace(
                _source_volts(high.real("time"))[common.cut(high.real("time"), _RAMP_START, _END)],
                high.real("rail")[common.cut(high.real("time"), _RAMP_START, _END)],
                "5 V rail, highest clamp",
                0,
                "--",
            ),
            Trace(
                _source_volts(low.real("time"))[common.cut(low.real("time"), _RAMP_START, _END)],
                low.real("rail")[common.cut(low.real("time"), _RAMP_START, _END)],
                "5 V rail, lowest clamp",
                0,
                ":",
            ),
            Trace(volts, typical.real("v3a")[rising], "3V3_A", 0),
            Trace(volts, amps[rising], "from the source", 1),
            Trace(volts, suppressor[rising], "through the suppressor", 1),
        ),
    )
    shown = common.cut(t_rev, 0.0, 1e-3)
    reverse_graph = Graph(
        name="reverse",
        title="A source of 5 V and 3 A with the wrong polarity, connected at 0.1 ms",
        xlabel="Time (ms)",
        panels=(Panel("Voltage (V)", marks=((_PIN_LOW, "rating -0.3 V"),)), Panel("Current (A)")),
        traces=(
            Trace(t_rev[shown] * 1e3, reverse.real("vbus_c")[shown], "receptacle", 0),
            Trace(t_rev[shown] * 1e3, reverse.real("vin1")[shown], "input 1", 0),
            Trace(t_rev[shown] * 1e3, reverse.real("rail")[shown], "5 V rail", 0),
            Trace(t_rev[shown] * 1e3, reverse.real("vusbc_i#branch")[shown], "in the cable", 1),
        ),
        xmarks=((_PLUG * 1e3, "connected"),),
    )
    notes = (
        "The source rises by 1 V per millisecond: the levels are static ones. The response "
        "of the clamp to a fast edge (5 us in the datasheet) is not what this run shows.",
        "Between its clamp level and its clamp threshold the limiter lets the rail follow "
        "the source: with a typical part the rail reaches 5.69 V, with the highest "
        "threshold 5.83 V, before it falls back to the clamp level.",
        "The suppressor is a typical part with a breakdown of 11.7 V at 1 mA; the "
        "datasheet allows 11.1 V to 12.3 V. Its dissipation is the product of its current "
        "and the receptacle voltage; nothing here heats up or fails.",
        "The thermal shutdown of the limiter is not modelled. With the idle carrier it "
        "dissipates little; with a load of 1 A and 10 V at its input it would take 4.5 W "
        "and cycle, as the specification says.",
        "With the wrong polarity the suppressor conducts in its forward direction. Its "
        "forward voltage (0.8 V at 3 A in the model) is an assumption: the datasheet "
        "gives only 3.5 V at most at 25 A. The diode across the limiter and the body diode "
        "of the limiter (an assumption) take input 1 down with the receptacle. A USB-C "
        "plug cannot be turned to reverse VBUS; a reversed source is a faulty cable or "
        "charger.",
    )
    return Outcome(tuple(figures), (graph, reverse_graph), notes)
