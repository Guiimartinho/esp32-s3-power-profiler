"""Tolerances of the passive parts, for corner and Monte Carlo runs.

The value strings of the schematic carry the tolerance of a part
(``1k 0.1% 25ppm``). The functions here turn those tolerances into factors
on the values of a circuit: one random set per run, or the same extreme for
a chosen group of parts.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np

from circuit_sim.netlist import Netlist
from circuit_sim.values import parse_tolerance

_PASSIVE = frozenset({"R", "C", "L", "RN"})


def tolerances(
    netlist: Netlist, refs: Iterable[str], default: Mapping[str, float] | None = None
) -> dict[str, float]:
    """The tolerance of every passive part of a list, as a fraction.

    Args:
        netlist: The schematic.
        refs: Reference designators; parts that are not passive are left out.
        default: Tolerance by designator prefix (``R``, ``C``, ``L``, ``RN``)
            for parts whose value gives none. A passive part without a
            tolerance and without a default is left out.
    """
    found: dict[str, float] = {}
    for ref in refs:
        part = netlist.component(ref)
        if part.prefix not in _PASSIVE:
            continue
        tolerance = parse_tolerance(part.value)
        if tolerance is None:
            tolerance = (default or {}).get(part.prefix)
        if tolerance is not None:
            found[ref] = tolerance
    return found


def draw_scales(spread: Mapping[str, float], rng: np.random.Generator) -> dict[str, float]:
    """One random set of factors, uniform inside the tolerance of each part.

    A uniform distribution is the cautious reading of a tolerance: nothing
    says that the parts of a reel sit near their nominal value.
    """
    return {ref: 1.0 + float(rng.uniform(-limit, limit)) for ref, limit in sorted(spread.items())}


def corner_scales(spread: Mapping[str, float], signs: Mapping[str, int]) -> dict[str, float]:
    """Factors with chosen parts at a limit of their tolerance.

    Args:
        spread: The tolerance of each part.
        signs: +1 or -1 for the parts to move to their upper or lower limit;
            parts not named stay nominal.
    """
    return {ref: 1.0 + sign * spread[ref] for ref, sign in signs.items() if ref in spread}
