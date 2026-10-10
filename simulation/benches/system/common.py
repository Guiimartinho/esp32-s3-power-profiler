"""The whole measuring path as one circuit, and the reading the host makes of it.

The circuit is the shunt ladder, the multiplexer, the amplifier chain up to
the converter input and the comparators, as drawn. The converter itself is
arithmetic here: a sample is the voltage at its input at the sampling
instant, turned into a 16-bit code with the reference. The reading is that
code with the nominal calibration of the specification, which is what the
host does with a board that was never calibrated.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from benches import frontend
from circuit_sim.bench import Context
from circuit_sim.circuit import Circuit

VREF = 2.5
"""Reference of the converter, V."""

CODES = 65536
"""Codes of the 16-bit converter."""

GAIN = 19.93
"""Nominal gain of the amplifier (specification, sections 4.5 and 8)."""

ZERO_CODE = 1313
"""Nominal code at zero current: the pedestal (specification, section 4.5)."""

SAMPLE_PERIOD = 10e-6
"""Sample period at 100 kSPS."""

FLAGGED_SAMPLES = 7
"""Samples flagged invalid after a change of the range bits (rule F-35)."""

LSB_AMPS = tuple(VREF / CODES / GAIN / shunt for shunt in frontend.SHUNT_OHMS)
"""Nominal current of one code in each range."""


COMPARATORS = ("U31", "U32")
"""The comparators themselves; their divider and clamp are other parts."""


def front_end(ctx: Context, comparators: bool = True) -> Circuit:
    """Ladder, multiplexer, amplifier chain and comparators as drawn.

    Args:
        ctx: The context of the bench.
        comparators: Leave the three comparators out when false. Their
            divider and clamp stay, so the amplifier output is loaded as
            drawn. A comparator with hysteresis has two stable states, and
            an operating point of a circuit that holds one may not converge.
    """
    refs = (
        *frontend.ladder_refs(ctx.netlist),
        *frontend.chain_refs(ctx.netlist),
        *frontend.comparator_refs(ctx.netlist),
    )
    if not comparators:
        refs = tuple(ref for ref in refs if ref not in COMPARATORS)
    return ctx.circuit(refs, frontend.ALIASES)


def codes(volts: NDArray[np.float64]) -> NDArray[np.int64]:
    """The codes of an ideal 16-bit converter for voltages at its input."""
    raw = np.floor(volts / VREF * CODES + 0.5)
    return np.clip(raw, 0, CODES - 1).astype(np.int64)


def reading(code: NDArray[np.int64], range_index: NDArray[np.int64]) -> NDArray[np.float64]:
    """The current the host reports for codes, with the nominal calibration."""
    lsb = np.asarray(LSB_AMPS)[range_index]
    return np.asarray((code - ZERO_CODE) * lsb, dtype=np.float64)
