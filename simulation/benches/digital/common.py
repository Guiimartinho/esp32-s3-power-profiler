"""What the benches of the digital block share.

Short node names for the nets of the four sheets, the lines that stand for
a pad of the controller, and the models of the pins of parts of other
sheets that hang on these lines. The pads are not parts of the schematic:
the controller module is one symbol, so a bench writes the pads it needs
with the pad model of ``digital.lib``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from circuit_sim import measure
from circuit_sim.circuit import PartModel
from circuit_sim.errors import MeasureError

Real = NDArray[np.float64]

LIBRARY = "digital.lib"
"""Model file of the block; a deck that writes pads has to include it."""

LOGIC_VOLTS = 3.3
"""Nominal level of the 3.3 V rails and of the pads of the controller."""

RAIL_TOLERANCE = 0.02
"""Tolerance of the 3.3 V regulators (LP5907 datasheet, SNVS798Q page 5)."""

SYSTEM_CLOCK = 1.0 / 150e6
"""One cycle of the system clock of the controller (specification, section 4.6)."""

PAD_HIGH_OHMS = 170.0
"""Largest output resistance of a pad that drives high at the 4 mA setting
(RP2350 datasheet, table 1683: 2.62 V at 4 mA with 3.3 V)."""

PAD_LOW_OHMS = 125.0
"""Largest output resistance of a pad that drives low at the 4 mA setting
(RP2350 datasheet, table 1683: 0.5 V at 4 mA)."""

PAD_STRONG_OHMS = 30.0
"""Output resistance of a strong pad: an assumption, the datasheet gives no
lower limit. The specification brackets the pad between 0 ohm and 170 ohm."""

PAD_INPUT_LOW = 0.8
"""Highest level that a pad reads as low for certain (RP2350 datasheet)."""

PAD_INPUT_HIGH = 2.0
"""Lowest level that a pad reads as high for certain (RP2350 datasheet)."""

PAD_PULL_DOWN = (36e3, 113e3)
"""Limits of the pull-down of a pad at 3.3 V (RP2350 datasheet, table 1683)."""

TRACK_FARADS = 5e-12
"""Capacitance of a short track with its pads and vias (assumption)."""

ALIASES = {
    "+3V3_C": "v3c",
    "+3V3_A": "v3a",
    "+5V": "v5",
    "+12V_A": "v12",
    "-4V_A": "vm4",
    "VREF": "vref",
    # acquisition lines
    "Net-(RN3-R1.1)": "gp19",
    "Net-(RN3-R2.1)": "gp20",
    "Net-(RN3-R3.1)": "gp21",
    "Net-(RN3-R4.1)": "gp22",
    "/Controller/ADC_SCK": "adc_sck",
    "/Controller/ADC_CNV": "adc_cnv",
    "/Controller/ADC_DOUT": "gp16",
    "/Controller/SIDE_LOAD": "side_load",
    "/Controller/SIDE_DOUT": "gp17",
    "Net-(RN5-R1.1)": "u30_sclk",
    "Net-(RN5-R2.1)": "u30_dout",
    "Net-(RN5-R3.1)": "u30_cnv",
    "Net-(U33-Q7)": "q33",
    "Net-(U34-Q7)": "q34",
    # slow SPI bus
    "Net-(RN1-R1.1)": "gp12",
    "Net-(RN1-R2.1)": "gp13",
    "Net-(RN1-R3.1)": "gp14",
    "Net-(RN1-R4.1)": "gp15",
    "/Controller/C_MISO": "c_miso",
    "/Controller/C_MON_CS": "c_mon_cs",
    "/Controller/C_SCK": "c_sck",
    "/Controller/C_MOSI": "c_mosi",
    "/Controller/C_DAC_CS": "c_dac_cs",
    "Net-(RN4-R4.2)": "dac_cs_mid",
    # status lines
    "/Controller/PWR_GOOD": "pwr_good",
    "Net-(U1-GPIO28_ADC2)": "gp28",
    "/Controller/VIN_OV": "vin_ov",
    "Net-(U1-GPIO11)": "gp11",
    # lines of the range sequencer and the path switches
    "/Controller/GATE_R1": "gate_r1",
    "/Controller/GATE_R2": "gate_r2",
    "/Controller/GATE_R3": "gate_r3",
    "/Controller/GATE_OUT": "gate_out",
    "/Controller/GATE_SRC": "gate_src",
    "/Controller/GATE_AMP": "gate_amp",
    "/Controller/MUX_A0": "mux_a0",
    "/Controller/MUX_A1": "mux_a1",
    "/Controller/SMU_ON": "smu_on",
    "/Comparators/CMP_UP": "cmp_up",
    "/Comparators/CMP_JUMP": "cmp_jump",
    "/Comparators/CMP_OC": "cmp_oc",
    # supply of the module
    "Net-(D1-K)": "vsys",
    "Net-(JP1-A)": "vbus",
    "/Controller/PICO_5V": "pico_5v",
    # logic inputs: connector pin, translator pin, 3.3 V side
    "Net-(J5-Pin_1)": "j_vcc",
    "Net-(J5-Pin_10)": "j_d0",
    "Net-(J5-Pin_9)": "j_d1",
    "Net-(J5-Pin_8)": "j_d2",
    "Net-(J5-Pin_7)": "j_d3",
    "Net-(J5-Pin_6)": "j_d4",
    "Net-(J5-Pin_5)": "j_d5",
    "Net-(J5-Pin_4)": "j_d6",
    "Net-(J5-Pin_3)": "j_d7",
    "Net-(RN11-R1.1)": "b_d0",
    "Net-(RN11-R2.1)": "b_d1",
    "Net-(RN11-R3.1)": "b_d2",
    "Net-(RN11-R4.1)": "b_d3",
    "Net-(RN10-R1.1)": "b_d4",
    "Net-(RN10-R2.1)": "b_d5",
    "Net-(RN10-R3.1)": "b_d6",
    "Net-(RN10-R4.1)": "b_d7",
    "/Digital Inputs/DIN0": "din0",
    "/Digital Inputs/DIN1": "din1",
    "/Digital Inputs/DIN2": "din2",
    "/Digital Inputs/DIN3": "din3",
    "/Digital Inputs/DIN4": "din4",
    "/Digital Inputs/DIN5": "din5",
    "/Digital Inputs/DIN6": "din6",
    "/Digital Inputs/DIN7": "din7",
    "/Digital Inputs/VCCB_SRC": "vccb_src",
    "Net-(JP2-C)": "vccb",
    "Net-(JP2-B)": "vcc_pin",
    "Net-(U25--)": "buf_out",
    # monitors
    "Net-(U40-CH0)": "ch0",
    "Net-(U40-CH1)": "ch1",
    "Net-(U40-CH2)": "ch2",
    "Net-(U40-CH3)": "ch3",
    "Net-(U40-CH4)": "ch4",
    "Net-(U40-CH5)": "ch5",
    "Net-(U40-CH6)": "ch6",
    "Net-(U40-CH7)": "ch7",
    "/Monitors/VOUT_BUF": "vout_buf",
    "/Monitors/VIN_P": "vin_p",
    "/Monitors/SRC_ST": "src_st",
    "/Monitors/CC1": "cc1",
    "/Monitors/CC2": "cc2",
    "Net-(U39-V_{OUT})": "temp_out",
}
"""Short node names for the nets of the block."""

LOGIC_SHEET = "/Digital Inputs/"
SIDE_SHEET = "/Side Data/"
MONITOR_SHEET = "/Monitors/"
CONTROLLER_SHEET = "/Controller/"

ADS8860_PINS = PartModel(
    kind="subckt",
    name="DIGITAL_ADS8860_IO",
    ports=("6", "7", "8", "9", "10", "5"),
    library=LIBRARY,
    origin="written here",
)
"""The digital pins of the converter U30 (CONVST, DOUT, SCLK, DIN, DVDD,
ground). The converter is a part of the signal chain; this block needs its
pins only and names them through an override."""

MCP4921_PINS = PartModel(
    kind="subckt",
    name="DIGITAL_INPUT_PIN",
    units=(("2", "1", "7"), ("3", "1", "7"), ("4", "1", "7")),
    library=LIBRARY,
    origin="written here",
)
"""The three logic inputs of the DAC U15 (select, clock, data) with their
supply and ground: a part of the source meter, named through an override."""

LP5907_OFF = PartModel(
    kind="subckt",
    name="DIGITAL_LP5907_OFF",
    ports=("1", "5", "2"),
    library=LIBRARY,
    origin="written here",
)
"""A 3.3 V regulator (U7, U8) that the supervisor holds off: its output
discharge. Parts of the logic supplies, named through an override."""


def ads8860(**params: float | str) -> PartModel:
    """The pins of the converter with other parameters than the default ones."""
    text = " ".join(f"{key}={value}" for key, value in params.items())
    return PartModel(
        kind=ADS8860_PINS.kind,
        name=ADS8860_PINS.name,
        ports=ADS8860_PINS.ports,
        library=LIBRARY,
        origin="written here",
        params=text,
    )


def with_params(model: PartModel, **params: float | str) -> PartModel:
    """A copy of a model of the map with parameters appended to its element."""
    text = " ".join(f"{key}={value}" for key, value in params.items())
    return PartModel(
        kind=model.kind,
        name=model.name,
        ports=model.ports,
        units=model.units,
        letter=model.letter,
        library=model.library,
        origin=model.origin,
        params=text,
    )


@dataclass(frozen=True, slots=True)
class Pad:
    """One pad of the controller in a deck.

    Attributes:
        name: Name of the pad, used for its element and its control nodes
            (``gp19`` gives the element ``Xgp19`` and the nodes ``gp19_ctl``
            and ``gp19_oe``).
        node: The node the pad is on.
        high_ohms: Output resistance while it drives high.
        low_ohms: Output resistance while it drives low.
        farads: Capacitance of the pad with its pin and the socket.
        pull_down: Pull-down of the pad in ohms; none when 0.
        e9: Add the current of erratum E9 of stepping A2.
        standard: A standard pad (GP26 to GP28) with a diode to the 3.3 V of
            the module; the other pads are fault tolerant and have none.
    """

    name: str
    node: str
    high_ohms: float = PAD_HIGH_OHMS
    low_ohms: float = PAD_LOW_OHMS
    farads: float = 5e-12
    pull_down: float = 0.0
    e9: bool = False
    standard: bool = False

    def line(self) -> str:
        """The element of the pad; the 3.3 V of the module is the node ``iovdd``."""
        model = "DIGITAL_RP2350_PAD_STD" if self.standard else "DIGITAL_RP2350_PAD"
        pull = f" rpd={self.pull_down:g}" if self.pull_down else ""
        return (
            f"X{self.name} {self.node} {self.name}_ctl {self.name}_oe iovdd 0 {model} "
            f"roh={self.high_ohms:g} rol={self.low_ohms:g} cpad={self.farads:g}{pull}"
            f" e9={int(self.e9)}"
        )

    def held(self, high: bool, drive: bool = True) -> str:
        """Sources that hold the pad at one level, or released."""
        return (
            f"V{self.name}_ctl {self.name}_ctl 0 {1 if high else 0}\n"
            f"V{self.name}_oe {self.name}_oe 0 {1 if drive else 0}"
        )


def module_supply(volts: float = LOGIC_VOLTS) -> str:
    """The 3.3 V rail of the module, which feeds its pads."""
    return f"* the 3.3 V rail of the module, an ideal source\nViovdd iovdd 0 {volts:g}\n"


def pulses(times: list[tuple[float, float]], edge: float = 0.1e-9) -> str:
    """A PWL text from (instant, level) pairs: the level holds until the next instant.

    Args:
        times: The instants at which the level changes, with the new level,
            rising in time. The first pair gives the level at the start.
        edge: Duration of an edge.
    """
    points = [f"0 {times[0][1]:g}"]
    level = times[0][1]
    for instant, new in times[1:]:
        if new == level:
            continue
        points.append(f"{instant:.6g} {level:g}")
        points.append(f"{instant + edge:.6g} {new:g}")
        level = new
    return "PWL(" + " ".join(points) + ")"


def crossing(
    time: Real, wave: Real, level: float, rising: bool | None, after: float = 0.0
) -> float:
    """The first crossing after an instant, or NaN when there is none."""
    try:
        return measure.first_crossing(time, wave, level, rising, after)
    except MeasureError:
        return float("nan")


def last_crossing(time: Real, wave: Real, level: float, before: float) -> float:
    """The last crossing of a level before an instant, or NaN when there is none."""
    found = measure.crossings(time, wave, level)
    found = found[found <= before]
    return float(found[-1]) if found.size else float("nan")
