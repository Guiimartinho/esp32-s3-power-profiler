"""The lines of the controller while its pins float, and the status lines."""

from __future__ import annotations

import numpy as np

from benches.digital import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench

_REFS = (
    # gate and address lines: resistor to ground and series resistor
    "R89", "R97", "R94", "R99", "R88", "R96", "R93", "R98", "R70", "R75", "R71", "R72",
    "R95", "R112", "R91", "R111",
    # slow SPI and acquisition lines
    "RN1", "RN2", "RN3", "RN4", "R3", "RN5", "R138",
    # status lines
    "R1", "R4", "R51", "R52", "U21",
)  # fmt: skip
"""Every pull resistor and series resistor of a line of the controller, and
the detector that drives the VIN_OV line."""

_E9_AMPS = 120e-6
"""Current that a released pad of stepping A2 can source (specification, section 5)."""

_LINES = {
    # pad node, node at the receiver, lowest low level of the receiver, stated level
    "GATE_R1": ("gate_r1", "n_u23_in_a", 0.8, 0.12),
    "GATE_R2": ("gate_r2", "n_u23_in_b", 0.8, 0.12),
    "GATE_R3": ("gate_r3", "n_u22_in_a", 0.8, 0.12),
    "GATE_OUT": ("gate_out", "n_u22_in_b", 0.8, 0.12),
    "GATE_SRC": ("gate_src", "n_u20_in_a", 0.8, 0.12),
    "GATE_AMP": ("gate_amp", "n_u20_in_b", 0.8, 0.56),
    "MUX_A0": ("mux_a0", "n_u24_a0", 0.8, 0.61),
    "MUX_A1": ("mux_a1", "n_u24_a1", 0.8, 0.61),
    "ADC_SCK": ("gp19", "u30_sclk", 0.99, None),
    "ADC_CNV": ("gp20", "u30_cnv", 0.99, None),
    "SIDE_LOAD": ("gp21", "side_load", 0.99, None),
    "SPI_SCK": ("gp14", "c_sck", 0.66, None),
    "SPI_MOSI": ("gp15", "c_mosi", 0.66, None),
}
"""The lines that have to rest low, with the highest level that their
receiver takes for low: 0.8 V at the gate drivers and the multiplexer
(Microchip DS20001422G page 3, TI SBAS758C), 0.3 of 3.3 V at the converter
and the registers, 0.2 of 3.3 V at the DAC (Microchip DS22248A page 7)."""

_RECEIVER_NETS = {
    "R97": "n_u23_in_a",
    "R99": "n_u23_in_b",
    "R96": "n_u22_in_a",
    "R98": "n_u22_in_b",
    "R75": "n_u20_in_a",
    "R72": "n_u20_in_b",
    "R112": "n_u24_a0",
    "R111": "n_u24_a1",
}
"""Series resistor of each gate and address line and the node name its far end gets here."""

_SELECT_LOW = 0.7 * 3.3 * (1.0 - common.RAIL_TOLERANCE)
"""Lowest level a converter takes for a high select: 0.7 of its supply at
the low limit of the rail (datasheets of the MCP3208 and the MCP4921)."""


def _aliases(ctx: Context) -> dict[str, str]:
    """Short names, with the far end of every series resistor named after its receiver."""
    names = dict(common.ALIASES)
    for ref, node in _RECEIVER_NETS.items():
        part = ctx.netlist.component(ref)
        pad_side = {"/Controller/" + key for key in _LINES}
        for pin in part.pins:
            if pin.net not in pad_side:
                names[pin.net] = node
    names["Net-(D15-common)"] = "detector_in"
    return names


def _pads(pull_down: float, e9: bool) -> list[common.Pad]:
    pads = []
    for index, (node, _, _, _) in enumerate(_LINES.values()):
        pads.append(common.Pad(f"p{index}", node, pull_down=pull_down, e9=e9))
    pads.append(common.Pad("pmiso", "gp12", pull_down=pull_down, e9=e9))
    return pads


def _readers() -> str:
    """The two pads that read the data lines of the acquisition, released."""
    lines = []
    for name, node in (("pdo", "gp16"), ("psd", "gp17")):
        pad = common.Pad(name, node)
        lines += [pad.line(), pad.held(high=False, drive=False)]
    return "\n".join(lines)


def _rails(analog: float, logic: float) -> str:
    return "\n".join(
        [
            common.module_supply().rstrip(),
            "* rails of the carrier as ideal sources; the detector rests low",
            f"Vanalog v3a 0 {analog:g}",
            f"Vlogic v3c 0 {logic:g}",
            "Vref vref 0 2.5",
            "Vdet detector_in 0 0",
            _readers(),
        ]
    )


def _forced_deck(ctx: Context) -> str:
    """Every pad released, with 120 uA forced out of each of them."""
    circuit = ctx.circuit(_REFS, _aliases(ctx))
    pads = _pads(0.0, e9=False)
    lines = [_rails(3.3, 3.3), "* pads released; a source stands for the current of erratum E9"]
    for pad in pads:
        lines += [
            pad.line(),
            pad.held(high=False, drive=False),
            f"I{pad.name} 0 {pad.node} {_E9_AMPS:g}",
        ]
    lines += [
        common.Pad("psel", "gp13").line(),
        common.Pad("psel", "gp13").held(False, False),
        common.Pad("pdac", "gp22").line(),
        common.Pad("pdac", "gp22").held(False, False),
        common.Pad("pgood", "gp28", standard=True).line(),
        common.Pad("pgood", "gp28").held(False, False),
        common.Pad("pov", "gp11").line(),
        common.Pad("pov", "gp11").held(False, False),
    ]
    return ctx.deck(
        "Lines of the controller with the pads released and 120 uA out of each pad",
        circuit,
        "\n".join(lines),
        control=["tran 10n 5u"],
        libraries=(common.LIBRARY, "logic.lib"),
    )


def _release_deck(ctx: Context, selects_pull: float, analog: float, title: str) -> str:
    """Pads of stepping A2 driven high and released at 2 us; selects against a pad pull-down."""
    circuit = ctx.circuit(_REFS, _aliases(ctx))
    pads = _pads(113e3, e9=True)
    lines = [_rails(analog, 3.3), "* pads of stepping A2: driven high, released at 2 us"]
    for pad in pads:
        lines += [
            pad.line(),
            f"V{pad.name}_ctl {pad.name}_ctl 0 1",
            f"V{pad.name}_oe {pad.name}_oe 0 PWL(0 1 2u 1 2.01u 0)",
        ]
    select = common.Pad("psel", "gp13", pull_down=selects_pull)
    dac = common.Pad("pdac", "gp22", pull_down=selects_pull)
    good = common.Pad("pgood", "gp28", pull_down=selects_pull, standard=True)
    over = common.Pad("pov", "gp11")
    lines += [
        "* the two selects, PWR_GOOD and VIN_OV: released pads with their pull-down",
        select.line(),
        select.held(False, False),
        dac.line(),
        dac.held(False, False),
        good.line(),
        good.held(False, False),
        over.line(),
        over.held(False, False),
    ]
    return ctx.deck(
        title,
        circuit,
        "\n".join(lines),
        control=["tran 10n 30u"],
        libraries=(common.LIBRARY, "logic.lib"),
    )


def _mistake_deck(ctx: Context) -> str:
    """Pads that rule F-4 forbids to drive, driven against their sources."""
    circuit = ctx.circuit(_REFS, _aliases(ctx))
    good = common.Pad("pgood", "gp28", standard=True)
    over = common.Pad("pov", "gp11")
    lines = [
        common.module_supply().rstrip(),
        "Vanalog v3a 0 3.3",
        "Vref vref 0 2.5",
        "* the 3.3 V of the logic at its upper limit; the flag is held low by its comparators",
        "Vlogic v3c 0 3.3",
        "Vflag pwr_good 0 0",
        "* the detector output is low at first and high from 10 us on",
        "Vdet detector_in 0 PWL(0 0 10u 0 10.1u 3.3)",
        _readers(),
        good.line(),
        good.held(True, True),
        over.line(),
        "Vpov_oe pov_oe 0 1",
        "* the pad at VIN_OV drives high against a low detector, then low against a high one",
        "Vpov_ctl pov_ctl 0 PWL(0 1 10u 1 10.1u 0)",
    ]
    return ctx.deck(
        "Pads of rule F-4 driven by mistake against the flag and the detector",
        circuit,
        "\n".join(lines),
        control=["tran 10n 20u"],
        libraries=(common.LIBRARY, "logic.lib"),
    )


@bench(
    "digital",
    "released-pins",
    "Lines of the controller with its pins released, and the two status lines",
    "section 4.11 (D-67, D-77, D-78), section 5, section 4.7, rules F-4 and F-5",
)
def released_pins(ctx: Context) -> Outcome:
    """Every line that the controller drives is left to its resistors.

    The circuit is the pull resistor and the series resistor of each line,
    with pad models of the controller in place of the module. First 120 uA
    is forced out of every released pad, the current of erratum E9 as the
    specification takes it, and the level at each receiver is read. Then
    pads of stepping A2 are driven high and released, and the lines are
    followed as their resistors pull them through the range in which that
    current flows. The two selects are read against the strongest pull-down
    of a pad with the analog rail at its lower limit. PWR_GOOD is read at
    the register and at the pad, and two pads that rule F-4 keeps as inputs
    are driven by mistake.
    """
    figures: list[Figure] = []
    forced = ctx.run("forced", _forced_deck(ctx))
    for name, (_, receiver, low, stated) in _LINES.items():
        figures.append(
            Figure(
                f"forced_{name.lower()}",
                f"{name} with 120 uA out of the released pad: level at the receiver",
                float(forced.real(receiver)[-1]),
                "V",
                expected=stated,
                high=low,
                source="section 5: still low for the receiver (calculated); the limit is the "
                "highest low level of its datasheet",
            )
        )
    figures.append(
        Figure(
            "forced_miso",
            "SPI_MISO with 120 uA out of the released pad: level at the pad",
            float(forced.real("gp12")[-1]),
            "V",
            expected=0.83,
            source="section 5: the pad sees 6.9 kohm, inside the 8.2 kohm of the erratum",
        )
    )
    release = ctx.run(
        "released",
        _release_deck(
            ctx,
            36e3,
            3.3 * (1.0 - common.RAIL_TOLERANCE),
            "Pads of stepping A2 released from high; selects against 36 kohm",
        ),
    )
    time = release.real("time")
    highest_name, highest = "", 0.0
    slowest = 0.0
    for name, (pad_node, receiver, low, _) in _LINES.items():
        end = float(release.real(receiver)[-1])
        if end > highest:
            highest_name, highest = name, end
        slowest = max(
            slowest, common.crossing(time, release.real(pad_node), low, False, 2e-6) - 2e-6
        )
    figures += [
        Figure(
            "released_highest",
            f"Stepping A2, pads released from high: highest level at a receiver ({highest_name})",
            highest,
            "V",
            high=0.1,
            source="section 5: the gate, address and clock lines stand at 0 V",
        ),
        Figure(
            "released_slowest",
            "Stepping A2, pads released from high: slowest line is below its low level after",
            slowest,
            "s",
            source="RP2350 datasheet, erratum E9: 8.2 kohm or less overcomes the current",
        ),
        Figure(
            "released_miso",
            "Stepping A2, SPI_MISO released from high: level left at the pad",
            float(release.real("gp12")[-1]),
            "V",
            high=common.PAD_INPUT_LOW,
            source="section 5: 6.9 kohm from the pad to ground, inside the 8.2 kohm of the erratum",
        ),
        Figure(
            "select_monitor",
            "Select of the monitor converter, pad pull-down 36 kohm, rail at its lower limit",
            float(release.real("c_mon_cs")[-1]),
            "V",
            expected=2.80,
            low=2.80,
            source="sections 4.11 and 5: 2.80 V or more against the strongest pad pull-down",
        ),
        Figure(
            "select_dac",
            "Select of the DAC, pad pull-down 36 kohm, rail at its lower limit",
            float(release.real("c_dac_cs")[-1]),
            "V",
            expected=2.80,
            low=2.80,
            source="sections 4.11 and 5: 2.80 V or more against the strongest pad pull-down",
        ),
        Figure(
            "select_margin",
            "The same select against the high level that the converters ask for",
            float(release.real("c_mon_cs")[-1]) - _SELECT_LOW,
            "V",
            low=0.0,
            source="section 5: the converters need 0.7 of their supply (datasheet)",
        ),
    ]
    flag = ctx.run(
        "flag",
        _release_deck(ctx, 1e12, 3.3, "PWR_GOOD high with the pad pull-down of GP28 off"),
        keep=False,
    )
    figures += [
        Figure(
            "flag_ratio",
            "PWR_GOOD high, pad pull-down off: level at the register over the 3.3 V rail",
            float(flag.real("pwr_good")[-1]) / 3.3,
            "",
            expected=0.82,
            low=0.7,
            source="section 4.7: 0.82 of the rail against the 0.7 that the register needs",
        ),
        Figure(
            "flag_ratio_pulled",
            "PWR_GOOD high, pad pull-down of 36 kohm on: level at the register over the rail",
            float(release.real("pwr_good")[-1]) / 3.3,
            "",
            expected=0.79,
            low=0.7,
            source="section 4.7: 0.79 with the pad pull-down of GP28 on",
        ),
        Figure(
            "flag_at_pad",
            "PWR_GOOD high, pull-down on, rail at 3.234 V: level at the pad GP28",
            float(release.real("gp28")[-1]) * (1.0 - common.RAIL_TOLERANCE),
            "V",
            expected=2.50,
            low=common.PAD_INPUT_HIGH,
            source="sections 4.7 and 4.11: 2.50 V at the pin against the 2.0 V it needs",
        ),
    ]
    mistake = ctx.run("mistake", _mistake_deck(ctx))
    t_m = mistake.real("time")
    node = mistake.real("vin_ov")
    pad_current = (mistake.real("gp28") - mistake.real("pwr_good")) / 1000.0
    figures += [
        Figure(
            "flag_driven",
            "GP28 driven high by mistake while the flag is low: current through R4",
            measure.value_at(t_m, pad_current, 5e-6),
            "A",
            expected=3.3e-3,
            high=25e-3,
            source="section 4.7 and rule F-4: 3.3 mA against 25 mA at the comparator outputs",
        ),
        Figure(
            "interlock_low",
            "GP11 driven high against a low detector: the interlock node rises to",
            measure.value_at(t_m, node, 9e-6),
            "V",
            expected=0.14,
            high=0.14,
            source="section 4.7 and rule F-4: a pin moves the node by 0.14 V at the most",
        ),
        Figure(
            "interlock_high",
            "GP11 driven low against a high detector: the interlock node falls by",
            3.3 - measure.value_at(t_m, node, 19e-6),
            "V",
            expected=0.14,
            high=0.14,
            source="section 4.7 and rule F-4: a pin moves the node by 0.14 V at the most",
        ),
    ]
    micro = time * 1e6
    shown = micro < 8.0
    graph = Graph(
        name="release",
        title="Pads of stepping A2, driven high and released at 2 us: lines at the pads",
        xlabel="Time (us)",
        panels=(
            Panel(
                "Line at the pad (V)",
                marks=((2.4, "E9 current below 2.4 V"), (1.2, "and above 1.2 V")),
            ),
        ),
        traces=(
            Trace(micro[shown], np.asarray(release.real("gate_r1")[shown]), "GATE_R1, 1 kohm", 0),
            Trace(
                micro[shown], np.asarray(release.real("gate_amp")[shown]), "GATE_AMP, 4.7 kohm", 0
            ),
            Trace(micro[shown], np.asarray(release.real("mux_a0")[shown]), "MUX_A0, 5.1 kohm", 0),
            Trace(micro[shown], np.asarray(release.real("gp19")[shown]), "ADC_SCK, 4.7 kohm", 0),
            Trace(
                micro[shown], np.asarray(release.real("gp12")[shown]), "SPI_MISO, 6.9 kohm", 0, "--"
            ),
        ),
    )
    notes = (
        "The receivers are not in this circuit: the gate drivers, the multiplexer, "
        "the converters and the registers take 1 uA to 10 uA at an input by their "
        "datasheets, which adds millivolts to the levels.",
        "The 120 uA of the first run is the worst case of the specification: the "
        "current flows at any pad voltage. The figure of the datasheet shows it "
        "only between 1.2 V and 2.4 V; with that curve a line that is released "
        "from high is pulled through the range and rests at 0 V, as the second "
        "run shows.",
        "The pad capacitance of 5 pF and the output resistance of the detector "
        "(100 ohm in the comparator model of this repository) are assumptions.",
        "SMU_ON has no resistor on the controller side of its transistor and is "
        "not in this bench; the console lines have none either.",
    )
    return Outcome(tuple(figures), (graph,), notes)
