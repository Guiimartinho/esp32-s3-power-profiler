"""What the benches of the signal chain share.

The chain is simulated alone: the amplifier U27 with its pedestal buffer,
the limiter, the driver rail, the filter around the driver and the network
at the converter, all taken from the netlist. The shunt ladder is not in
these circuits. Its place is taken by ideal sources on the inputs of the
multiplexer U24, one per range, so that the amplifier sees the shunt voltage
behind the resistance and the capacitance of a multiplexer channel, and a
range change is a change of the address lines.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

import numpy as np
from numpy.typing import NDArray

from benches import frontend
from circuit_sim.bench import Context
from circuit_sim.circuit import Circuit, PartModel

VREF = 2.5
"""Reference voltage (specification, section 4.6)."""

CODES = 65536
"""Codes of the 16-bit converter."""

LSB = VREF / CODES
"""One code at the converter input: 38.1 uV."""

GAIN = 1.0 + 9900.0 / 523.0
"""Gain that the specification calculates from R123 = 523 ohm: 19.929."""

PEDESTAL = VREF * 1020.0 / (49900.0 + 1020.0)
"""Pedestal that the specification calculates from R121 and R122: 50.08 mV."""

FULL_SCALE_SHUNT = (VREF - PEDESTAL) / GAIN
"""Shunt voltage at which the converter reads full scale: 122.9 mV."""

SAMPLE_PERIOD = 10e-6
"""Sample period at 100 kSPS."""

FLAGGED_SAMPLES = 7
"""Samples flagged as invalid after a range change (rule F-35)."""

MUX_OHMS = (125.0, 250.0, 430.0)
"""On-resistance of a multiplexer channel: the span the specification sweeps."""

ALIASES = {
    **frontend.ALIASES,
    "Net-(U26-+)": "ped_div",
    "Net-(U28-+)": "buf_p",
    "Net-(U28--)": "buf_n",
    "Net-(R127-Pad1)": "buf_out",
    "Net-(U29-+)": "flt",
    "Net-(U29--)": "adc_drv",
    "Net-(C89-Pad1)": "ref_cap",
    "Net-(R123-Pad1)": "rg_a",
    "Net-(R123-Pad2)": "rg_b",
    "Net-(U24-S3A)": "s3a",
    "Net-(U24-S3B)": "s3b",
    "Net-(U24-S4A)": "s4a",
    "Net-(U24-S4B)": "s4b",
    "Net-(U24-A0)": "a0",
    "Net-(U24-A1)": "a1",
    "Net-(U24-EN)": "mux_en",
    "Net-(RN5-R3.1)": "cnv",
}
"""Short node names for the nets of the chain and of the multiplexer."""

MUX_PARTS = ("U24", "R111", "R112", "R113", "R91", "R95")
"""The multiplexer with the resistors of its address and enable inputs."""

CONVERTER = ("U30",)
"""The converter: its analog input and its reference pin."""

LIBRARIES = ("logic.lib",)
"""Model file that the multiplexer model needs beside its own: its delay element."""

POSITIVE_TAPS = ("supply", "sense_r1", "s3a", "s4a")
"""Node of the positive sense tap of each range, as the multiplexer sees it."""

Vector = NDArray[np.float64]


def with_params(ctx: Context, ref: str, **params: float) -> PartModel:
    """The model of a part as the model map gives it, with parameters set.

    Args:
        ctx: The bench context.
        ref: Reference designator of the part.
        **params: Parameters of its subcircuit.
    """
    base = ctx.models.model_of(ctx.netlist.component(ref), ctx.tier)
    text = " ".join(f"{name}={value:g}" for name, value in params.items())
    return replace(base, params=text)


def chain(
    ctx: Context,
    *,
    mux_ohms: float | None = None,
    converter: bool = False,
    overrides: Mapping[str, PartModel] | None = None,
    scales: Mapping[str, float] | None = None,
) -> Circuit:
    """The signal chain behind the multiplexer, from the netlist.

    Args:
        ctx: The bench context.
        mux_ohms: On-resistance of a multiplexer channel; the value of the
            model (250 ohm) when left out.
        converter: Include the converter U30 (its analog input).
        overrides: Models that replace the ones of the model map.
        scales: Factors on the values of passive parts, for tolerance runs.
    """
    refs = [*frontend.chain_refs(ctx.netlist), *MUX_PARTS]
    if converter:
        refs += CONVERTER
    replaced: dict[str, PartModel] = {}
    if mux_ohms is not None:
        replaced["U24"] = with_params(ctx, "U24", ron=mux_ohms)
    replaced.update(overrides or {})
    return ctx.circuit(refs, ALIASES, replaced, scales)


def taps(shunt: Mapping[int, str], vout: str = "3.3") -> str:
    """Ideal sources on the inputs of the multiplexer, in place of the ladder.

    Args:
        shunt: The voltage across the shunt of a range as the value of a
            SPICE source (``0.05``, ``dc 0 ac 1``, ``PWL(...)``), by range;
            a range that is not named has 0 V.
        vout: The voltage of the node after the shunts, the output voltage
            of the instrument, as the value of a SPICE source.
    """
    lines = [
        "* the ladder as ideal sources: the node after the shunts, and the",
        "* voltage across the shunt of each range at its sense taps",
        f"Vvout vout_s 0 {vout}",
        f"Vsh0 supply vout_s {shunt.get(0, '0')}",
        f"Vsh1 sense_r1 vout_s {shunt.get(1, '0')}",
        f"Vsh2 s3a s3b {shunt.get(2, '0')}",
        "Vk2 s3b vout_s 0",
        f"Vsh3 s4a s4b {shunt.get(3, '0')}",
        "Vk3 s4b vout_s 0",
    ]
    return "\n".join(lines) + "\n"


def address(index: int) -> str:
    """The two address lines of the multiplexer held for one range."""
    high = frontend.LOGIC_VOLTS
    return (
        f"* multiplexer address held for range {index}\n"
        f"Vmux_a0 mux_a0 0 {high if index in (1, 3) else 0:g}\n"
        f"Vmux_a1 mux_a1 0 {high if index in (2, 3) else 0:g}\n"
    )


def code(volts: Vector | float) -> Vector:
    """The code of an ideal converter for a voltage at its input.

    The converter of the datasheet reads straight binary with one code per
    VREF / 65536 and stops at 0 and at 65535.
    """
    raw = np.floor(np.asarray(volts, dtype=np.float64) / LSB + 0.5)
    return np.asarray(np.clip(raw, 0, CODES - 1), dtype=np.float64)


def first_valid_samples() -> tuple[float, float]:
    """Earliest and latest instant of the first valid sample after a range change.

    Seven samples are flagged; the change can fall anywhere inside a sample
    period, so the eighth sample is taken 70 us to 80 us after it.
    """
    return FLAGGED_SAMPLES * SAMPLE_PERIOD, (FLAGGED_SAMPLES + 1) * SAMPLE_PERIOD
