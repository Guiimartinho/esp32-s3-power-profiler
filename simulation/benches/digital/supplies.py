"""Lines that are driven into parts without supply, and the supply of the module."""

from __future__ import annotations

import numpy as np

from benches.digital import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel

_LOGIC_REFS = (
    "U30", "RN5", "RN4", "RN3", "R3", "U33", "U34", "R138", "U7", "R51", "R52",
    "C16", "C35", "C92", "C98", "C99", "C101",
)  # fmt: skip
"""The converter pins and the registers with their series resistors, the
regulator of the logic rail (switched off), the divider of PWR_GOOD and the
capacitors of the rail."""

_ANALOG_REFS = ("RN1", "RN2", "RN3", "RN4", "R3", "U40", "U15", "U8", "C17", "C102", "C111", "C112")
"""The slow SPI lines with their resistors, the monitor converter, the pins
of the DAC, the regulator of the analog 3.3 V rail (switched off) and
capacitors of that rail."""

_GATE_REFS = ("R89", "R97", "U23", "R95", "R112", "U24")
"""One gate line and one address line with their receivers."""

_DRIVE = 20e-6
"""Instant at which the pads are driven high."""

_CHARGED = _DRIVE + 2e-6
"""Instant at which the pin capacitances are charged and the rails are still empty."""


def _pin(units: tuple[tuple[str, ...], ...]) -> PartModel:
    """Logic inputs of a part of another sheet, each with its supply pin and ground."""
    return PartModel(
        kind="subckt",
        name="DIGITAL_INPUT_PIN",
        units=units,
        library=common.LIBRARY,
        origin="written here",
        params="cin=5p",
    )


def _logic_deck(ctx: Context, title: str, pad_ohms: float, iovdd: float, scale: float) -> str:
    """Clock, convert-start and load driven high while the logic rail has no supply."""
    circuit = ctx.circuit(
        _LOGIC_REFS,
        common.ALIASES,
        overrides={"U30": common.ADS8860_PINS, "U7": common.LP5907_OFF},
        scales={"RN4": scale, "RN5": scale},
    )
    pads = [common.Pad(name, name, pad_ohms, pad_ohms) for name in ("gp19", "gp20", "gp21")]
    lines = [
        common.module_supply(iovdd).rstrip(),
        "* the 5 V rail stands; the supervisor holds the two 3.3 V regulators off",
        "Vrail v5 0 5",
        "Vanalog v3a 0 0",
        "* three pads of the controller are driven high at 20 us",
    ]
    for pad in pads:
        lines += [
            pad.line(),
            f"V{pad.name}_ctl {pad.name}_ctl 0 PWL(0 0 {_DRIVE:g} 0 {_DRIVE + 1e-8:g} 1)",
            f"V{pad.name}_oe {pad.name}_oe 0 1",
        ]
    for name in ("gp16", "gp17", "gp22"):
        pad = common.Pad(name, name)
        lines += [pad.line(), pad.held(False, False)]
    return ctx.deck(
        title, circuit, "\n".join(lines), control=["tran 20n 6m 0 5u"], libraries=(common.LIBRARY,)
    )


def _analog_deck(
    ctx: Context,
    title: str,
    lines_high: bool,
    pad_ohms: float,
    iovdd: float,
    scales: dict[str, float],
) -> str:
    """The selects, and with ``lines_high`` clock and data too, high into a dead analog rail."""
    circuit = ctx.circuit(
        _ANALOG_REFS,
        common.ALIASES,
        overrides={"U15": common.MCP4921_PINS, "U8": common.LP5907_OFF},
        scales=scales,
    )
    lines = [
        common.module_supply(iovdd).rstrip(),
        "* the 5 V rail stands; the analog rail and the reference have no supply",
        "Vrail v5 0 5",
        "Vref vref 0 0",
        "* pads of the controller: driven high at 20 us, or held low",
    ]
    for name in ("gp13", "gp22", "gp14", "gp15"):
        pad = common.Pad(name, name, pad_ohms, pad_ohms)
        high = lines_high or name in ("gp13", "gp22")
        level = f"PWL(0 0 {_DRIVE:g} 0 {_DRIVE + 1e-8:g} 1)" if high else "0"
        lines += [pad.line(), f"V{name}_ctl {name}_ctl 0 {level}", f"V{name}_oe {name}_oe 0 1"]
    for name in ("gp12", "gp19", "gp20", "gp21"):
        pad = common.Pad(name, name)
        lines += [pad.line(), pad.held(False, False)]
    return ctx.deck(
        title, circuit, "\n".join(lines), control=["tran 20n 5m 0 5u"], libraries=(common.LIBRARY,)
    )


def _gate_deck(ctx: Context, title: str, iovdd: float, scale: float) -> str:
    """A gate line and an address line high while +12 V_A is absent."""
    circuit = ctx.circuit(
        _GATE_REFS,
        common.ALIASES,
        overrides={
            "U23": _pin((("2", "6", "3"), ("4", "6", "3"))),
            "U24": _pin((("1", "14", "15"), ("16", "14", "15"), ("2", "14", "15"))),
        },
        scales={"R89": scale, "R97": scale, "R95": scale, "R112": scale},
    )
    lines = [
        common.module_supply(iovdd).rstrip(),
        "* +12 V_A held at 0 V: its loads would let it rise and take less",
        "Vp12 v12 0 0",
        "* two pads without resistance of their own drive the lines high at 20 us",
    ]
    for name, node in (("pgate", "gate_r1"), ("paddr", "mux_a0")):
        pad = common.Pad(name, node, 0.1, 0.1)
        lines += [
            pad.line(),
            f"V{name}_ctl {name}_ctl 0 PWL(0 0 {_DRIVE:g} 0 {_DRIVE + 1e-8:g} 1)",
            f"V{name}_oe {name}_oe 0 1",
        ]
    return ctx.deck(
        title, circuit, "\n".join(lines), control=["tran 10n 100u"], libraries=(common.LIBRARY,)
    )


@bench(
    "digital",
    "unpowered-inputs",
    "Controller lines driven high into parts that have no supply",
    "sections 4.6, 4.11 and 5 (D-75, D-77), rules F-2 and F-7",
)
def unpowered_inputs(ctx: Context) -> Outcome:
    """Pads of the controller are driven high while the supervisor holds the carrier off.

    Three circuits. In the first the clock, convert-start and load lines go
    high into the converter and the registers; the logic rail has only the
    discharge of its regulator and its capacitors. In the second the two
    selects, and then also the clock and the data line of the slow SPI bus,
    go high into the monitor converter and the DAC with the analog rail
    dead. In the third a gate line and an address line go high with +12 V_A
    at 0 V. Each is run with nominal values and at the tolerance limits
    that the specification calculates with.
    """
    figures: list[Figure] = []
    traces: list[Trace] = []
    cases = {
        "weak": ("weakest pad of the 4 mA setting", common.PAD_HIGH_OHMS, 3.3, 1.0, 6e-3),
        "strong": ("strong pad", common.PAD_STRONG_OHMS, 3.3, 1.0, 10e-3),
        "limit": ("pad without resistance, resistors 5 % low, 3.366 V", 0.1, 3.366, 0.95, 11.3e-3),
    }
    for name, (label, ohms, iovdd, scale, stated) in cases.items():
        run = ctx.run(
            f"logic-{name}",
            _logic_deck(
                ctx, f"Acquisition lines high into a dead logic rail: {label}", ohms, iovdd, scale
            ),
            keep=name == "weak",
        )
        time = run.real("time")
        into_clock = (run.real("adc_sck") - run.real("u30_sclk")) / (220.0 * scale)
        into_convert = (run.real("adc_cnv") - run.real("u30_cnv")) / (220.0 * scale)
        rail = run.real("v3c")
        figures.append(
            Figure(
                f"clock_pin_peak_{name}",
                f"{label}: current into the clock pin of the converter, rail still empty",
                measure.value_at(time, into_clock, _CHARGED),
                "A",
                expected=stated,
                high=11.3e-3,
                source="sections 4.6 and 5: 6 mA to 10 mA with nominal values, 11.3 mA at the "
                "tolerance limits (calculated)",
            )
        )
        if name != "limit":
            figures.append(
                Figure(
                    f"clock_pin_settled_{name}",
                    f"{label}: current into the clock pin once the rail has risen",
                    float(into_clock[-1]),
                    "A",
                    source="rule F-7: the series resistors bound the state",
                )
            )
        if name == "weak":
            figures.append(
                Figure(
                    "convert_pin_peak",
                    f"{label}: current into the convert-start pin, rail still empty",
                    measure.value_at(time, into_convert, _CHARGED),
                    "A",
                    high=11.3e-3,
                    source="section 5: the two clock inputs of the converter",
                )
            )
            shown = time < 3e-3
            traces += [
                Trace(
                    time[shown] * 1e3, np.asarray(into_clock[shown]) * 1e3, "into the clock pin", 0
                ),
                Trace(time[shown] * 1e3, np.asarray(rail[shown]), "logic rail without supply", 1),
            ]
        if name == "limit":
            figures.append(
                Figure(
                    "rail_lifted",
                    f"{label}: level to which the two lines lift the logic rail",
                    float(rail[-1]),
                    "V",
                    expected=1.6,
                    low=1.2,
                    high=2.0,
                    source="rule F-2: 3V3_C lifted to about 1.6 V (calculated); within 25 %",
                )
            )
    selects = ctx.run(
        "selects",
        _analog_deck(
            ctx,
            "Both selects driven high into a dead analog rail",
            False,
            common.PAD_STRONG_OHMS,
            3.3,
            {},
        ),
    )
    figures.append(
        Figure(
            "analog_rail_selects",
            "Both selects driven high: level at which they hold the dead analog rail",
            float(selects.real("v3a")[-1]),
            "V",
            expected=0.76,
            low=0.68,
            high=0.84,
            source="rule F-7: 0.76 V, above the 0.7 V the converter needs before it is "
            "powered again (calculated); within 10 %",
        )
    )
    bus = ctx.run(
        "bus-limit",
        _analog_deck(
            ctx,
            "Slow SPI lines high into a dead analog rail, tolerance limits",
            True,
            0.1,
            3.40,
            {"RN1": 0.95, "RN4": 0.95, "R3": 0.99},
        ),
        keep=False,
    )
    clock_amps = (bus.real("gp14") - bus.real("c_sck")) / (2200.0 * 0.95)
    select_amps = (bus.real("dac_cs_mid") - bus.real("c_dac_cs")) / (1500.0 * 0.99)
    figures += [
        Figure(
            "slow_line_peak",
            "Clock of the slow bus high, tolerance limits: current through 2.2 kohm, rail empty",
            measure.value_at(bus.real("time"), clock_amps, _CHARGED),
            "A",
            expected=1.39e-3,
            high=1.39e-3,
            source="sections 4.11 and 5 and rule F-2: 1.39 mA into a slow SPI input (calculated)",
        ),
        Figure(
            "dac_select_peak",
            "Select of the DAC high, tolerance limits: current into its pin, rail still empty",
            measure.value_at(bus.real("time"), select_amps, _CHARGED + 4e-6),
            "A",
            expected=1.90e-3,
            high=2e-3,
            source="section 5 and rule F-2: 1.90 mA against the 2 mA of the datasheet",
        ),
    ]
    for name, iovdd, scale, stated in (
        ("nominal", 3.3, 1.0, 2.7e-3),
        ("limit", 3.366, 0.99, 2.9e-3),
    ):
        gate = ctx.run(
            f"gate-{name}",
            _gate_deck(
                ctx, f"A gate line and an address line high without +12 V_A, {name}", iovdd, scale
            ),
            keep=False,
        )
        current = gate.real("vp12#branch")
        figures.append(
            Figure(
                f"gate_inputs_{name}",
                f"Gate and address line high, {name} values: current into the two inputs together",
                float(current[-1]),
                "A",
                expected=2.0 * stated,
                high=2.0 * 2.9e-3,
                source="sections 4.11 and 5: 2.7 mA per input, 2.9 mA at the limits (calculated)",
            )
        )
    graph = Graph(
        name="logic",
        title="Clock, convert-start and load high at 20 us into a dead logic rail, weakest pad",
        xlabel="Time (ms)",
        panels=(Panel("Current into the clock pin of the converter (mA)"), Panel("Logic rail (V)")),
        traces=tuple(traces),
    )
    notes = (
        "The inputs of the converter, of the monitor converter, of the DAC, of the "
        "gate driver and of the multiplexer are a capacitance and a diode to each "
        "rail, 0.6 V at 1 mA: their datasheets rate the pins a few tenths of a volt "
        "beyond the supply and give no curve. The specification calculates with "
        "0.5 V to 0.6 V; a softer diode gives less current.",
        "A rail without supply is the discharge of its regulator, 230 ohm "
        "(datasheet), its capacitors and, on the logic rail, the divider of "
        "PWR_GOOD. Every other load of the rails is left out, so the rails rise "
        "higher here than on the board. The registers take no current: their "
        "inputs have no diode to the supply.",
        "The first values are read 2 us after the pads went high, when the pin "
        "capacitances are charged and the capacitors of the rail are still empty; "
        "after about a millisecond the rail has risen and the currents are lower.",
        "These states are the ones rules F-2 and F-7 forbid; the bench shows what "
        "the resistors leave if firmware fails to keep them.",
    )
    return Outcome(tuple(figures), (graph,), notes)


_SUPPLY_REFS = ("U1", "JP1", "D1", "R23", "C1", "R5", "R6")
"""The module (its supply side), the jumper, the diode from the 5 V rail, the
load resistor of that rail and what stands on the node behind the jumper."""


def _supply_deck(
    ctx: Context,
    title: str,
    lines: list[str],
    control: list[str],
    overrides: dict[str, PartModel] | None = None,
) -> str:
    """The supply side of the module with the sources of one case."""
    circuit = ctx.circuit(_SUPPLY_REFS, common.ALIASES, overrides=overrides)
    return ctx.deck(title, circuit, "\n".join(lines), control=control)


@bench(
    "digital",
    "module-supply",
    "The 5 V of the controller module against the 5 V rail: which way current flows",
    "section 4.11 (D-42, D-47), section 5",
)
def module_supply(ctx: Context) -> Outcome:
    """The supply pins of the module meet the 5 V rail through JP1 and D1.

    The module is its Schottky diode from VBUS to VSYS, its VBUS sense
    divider and a load of 0.1 W. Four cases: the USB-C input alone (the rail
    stands, no cable at the module), the cable of the module alone with the
    rail fed through the jumper, the same with the jumper cut, and both
    cables. In the second case the rail voltage is stepped around the
    voltage of the cable, to show how the two diodes share the current of
    the module.
    """
    figures: list[Figure] = []
    usbc = ctx.run(
        "usbc-alone",
        _supply_deck(
            ctx,
            "USB-C alone: the rail stands at 5 V, no cable at the module",
            ["* the 5 V rail as an ideal source; nothing drives VBUS", "Vrail v5 0 5"],
            ["tran 10u 50m"],
        ),
    )
    figures += [
        Figure(
            "usbc_vsys",
            "USB-C alone: voltage at the VSYS pin of the module",
            float(usbc.real("vsys")[-1]),
            "V",
            low=4.25,
            source="section 4.11: the module is supplied through the diode D1; Pico 2 "
            "datasheet: 1.8 V to 5.5 V at VSYS",
        ),
        Figure(
            "usbc_vbus",
            "USB-C alone: voltage at the VBUS pin of the module",
            float(usbc.real("vbus")[-1]),
            "V",
            high=0.1,
            source="section 4.11: the carrier does not feed the VBUS pin",
        ),
        Figure(
            "usbc_sense",
            "USB-C alone: level at the VBUS sense pin of the module, GP24",
            float(usbc.real("xu1.gp24")[-1]),
            "V",
            high=common.PAD_INPUT_LOW,
            source="section 4.11: expected to read low (estimate)",
        ),
    ]
    sweep = ctx.run(
        "cable-alone",
        _supply_deck(
            ctx,
            "Cable of the module alone: the rail voltage stepped around the cable voltage",
            [
                "* 5 V at VBUS behind the cable; the rail as an ideal source that is stepped:",
                "* the limiter and the multiplexer between the jumper and the rail are not here",
                "Vcable cable 0 5",
                "Rcable cable vbus 0.2",
                "Vrail v5 0 4.9",
            ],
            ["dc Vrail 4.0 5.5 0.01"],
        ),
    )
    rail = sweep.real("v5")
    from_cable = -sweep.real("vcable#branch")
    from_rail = -sweep.real("vrail#branch")
    through_r23 = rail / 10e3

    def at(values: np.ndarray, volts: float) -> float:
        return float(np.interp(volts, rail, values))

    figures += [
        Figure(
            "cable_rail_share",
            "Cable alone, rail 0.1 V below the cable: current that D1 gives the module",
            at(from_rail - through_r23, 4.9),
            "A",
            source="section 4.11: with the data cable alone the module is supplied from its "
            "own connector",
        ),
        Figure(
            "cable_own_share",
            "Cable alone, rail 0.1 V below the cable: current through the diode of the module",
            at(from_cable, 4.9) - 5.0 / 15.6e3 - 5.0 / 7.54e3,
            "A",
            source="section 4.11: with the data cable alone the module is supplied from its "
            "own connector",
        ),
        Figure(
            "cable_backfeed",
            "Cable alone, rail at 4.0 V: current from the module back into the rail",
            -at(from_rail - through_r23, 4.0),
            "A",
            high=50e-6,
            source="section 4.11: neither input feeds the other one back; 50 uA is the "
            "largest reverse current of D1 (datasheet)",
        ),
    ]
    for name, ohms, stated in (("typical", 1e6, None), ("largest", 87e3, 0.5)):
        part = ctx.models.model_of(ctx.netlist.component("D1"))
        cut = ctx.run(
            f"jumper-cut-{name}",
            _supply_deck(
                ctx,
                f"Cable of the module alone, jumper cut, {name} reverse current of D1",
                [
                    "* 5 V at VBUS behind the cable; nothing feeds the rail",
                    "Vcable cable 0 5",
                    "Rcable cable vbus 0.2",
                ],
                ["tran 10u 50m"],
                overrides={
                    "JP1": PartModel(kind="skip"),
                    "D1": common.with_params(part, rleak=ohms),
                },
            ),
            keep=name == "largest",
        )
        figures.append(
            Figure(
                f"cut_rail_{name}",
                f"Jumper cut, module powered, {name} reverse current of D1: level of the 5 V rail",
                float(cut.real("v5")[-1]),
                "V",
                expected=stated,
                high=0.5 if stated else None,
                source="section 4.11: 0.5 V or below with the largest reverse current of "
                "50 uA at 25 C (calculated)",
            )
        )
    both = ctx.run(
        "both",
        _supply_deck(
            ctx,
            "Both cables: the cable voltage of the module stepped against a rail at 5.0 V",
            [
                "* the rail stands at 5.0 V from the USB-C input; the cable of the module",
                "* is stepped from 4.4 V to 5.5 V. The multiplexer has chosen USB-C, so",
                "* the node behind the jumper only carries its divider.",
                "Vcable cable 0 5",
                "Rcable cable vbus 0.2",
                "Vrail v5 0 5",
            ],
            ["dc Vcable 4.4 5.5 0.01"],
        ),
        keep=False,
    )
    cable_volts = both.real("cable")
    cable_amps = -both.real("vcable#branch") - cable_volts / 15.6e3 - cable_volts / 7.54e3
    rail_amps = -both.real("vrail#branch") - 5.0 / 10e3
    figures += [
        Figure(
            "both_cable_least",
            "Both cables: smallest current through the diode of the module, cable 4.4 V to 5.5 V",
            float(np.min(cable_amps)),
            "A",
            low=-1e-6,
            source="section 4.11: neither input feeds the other one back",
        ),
        Figure(
            "both_rail_least",
            "Both cables: smallest current through D1, cable 4.4 V to 5.5 V",
            float(np.min(rail_amps)),
            "A",
            low=-50e-6,
            source="section 4.11: neither input feeds the other one back; 50 uA is the "
            "largest reverse current of D1 (datasheet)",
        ),
        Figure(
            "both_handover",
            "Both cables: cable voltage above which the module takes more from its own diode",
            float(np.interp(0.0, cable_amps - rail_amps, cable_volts)),
            "V",
            source="the two diodes hand the module over where their drops match",
        ),
    ]
    graph = Graph(
        name="share",
        title="Cable of the module at 5 V: who supplies the module as the rail voltage moves",
        xlabel="Voltage of the 5 V rail (V)",
        panels=(Panel("Current (mA)"), Panel("VSYS pin (V)")),
        traces=(
            Trace(rail, (from_rail - through_r23) * 1e3, "through D1 of the carrier", 0),
            Trace(
                rail,
                (from_cable - 5.0 / 15.6e3 - 5.0 / 7.54e3) * 1e3,
                "through the diode of the module",
                0,
            ),
            Trace(rail, sweep.real("vsys"), "", 1),
        ),
    )
    notes = (
        "The module is a model of its supply side from the figure of its "
        "datasheet: a Schottky diode PMEG6010ELR from VBUS to VSYS, 5.6 kohm and "
        "10 kohm from VBUS to ground with the sense pin between them, and a load "
        "of 0.1 W behind VSYS (assumption).",
        "The limiter U3 and the multiplexer U5 between the jumper and the rail are "
        "parts of the power input and are not in this circuit: the rail is an "
        "ideal source. The multiplexer blocks current from the rail back to the "
        "node of the jumper (datasheet), which this bench takes as given.",
        "With the cable of the module alone and the jumper closed, the diode D1 of "
        "the carrier has the lower drop: most of the current of the module then "
        "flows through the limiter and the multiplexer of the carrier and back "
        "through D1, not through the diode of the module. Nothing flows backward "
        "in any case; the module keeps its own path if the rail falls.",
        "The reverse current of D1 is a model fitted to the typical and to the "
        "largest value of its datasheet at 25 C. At 100 C the datasheet states "
        "1 mA typical: with the jumper cut the rail then rises until other loads "
        "of the rail take that current; they are not in this circuit.",
    )
    return Outcome(tuple(figures), (graph,), notes)
