from __future__ import annotations

import numpy as np
import pytest

from circuit_sim.errors import NetlistError
from circuit_sim.netlist import Netlist
from circuit_sim.tolerance import corner_scales, draw_scales, tolerances


def test_the_tolerance_of_a_part_comes_from_its_value(netlist: Netlist) -> None:
    found = tolerances(netlist, ["R1", "R2", "R3", "RN1"])

    assert found == pytest.approx({"R1": 0.001, "R2": 0.01, "R3": 0.0025, "RN1": 0.01})
    assert list(found) == ["R1", "R2", "R3", "RN1"]


def test_parts_that_are_not_passive_are_left_out(netlist: Netlist) -> None:
    assert tolerances(netlist, ["Q1", "U1", "D1", "TP1", "JP1", "R2"]) == {"R2": 0.01}


def test_a_passive_part_without_a_tolerance_is_left_out(netlist: Netlist) -> None:
    # R4 is a zero-ohm link, the capacitors and the inductor state no tolerance.
    assert tolerances(netlist, ["R4", "C1", "C3", "L1"]) == {}


def test_a_default_stands_in_by_the_kind_of_part(netlist: Netlist) -> None:
    found = tolerances(
        netlist, ["R1", "R4", "C1", "L1", "RN1", "C3"], default={"C": 0.1, "L": 0.2, "RN": 0.05}
    )

    # The value wins over the default, and a kind without a default stays out.
    assert found == pytest.approx({"R1": 0.001, "C1": 0.1, "L1": 0.2, "RN1": 0.01, "C3": 0.1})


def test_a_part_that_the_schematic_does_not_have_is_an_error(netlist: Netlist) -> None:
    with pytest.raises(NetlistError, match="the schematic has no part R99"):
        tolerances(netlist, ["R1", "R99"])


def test_a_random_set_stays_inside_the_tolerance_of_each_part() -> None:
    spread = {"R1": 0.001, "R2": 0.01, "C1": 0.1, "R9": 0.0}
    rng = np.random.default_rng(7)

    sets = [draw_scales(spread, rng) for _ in range(2000)]

    for ref, limit in spread.items():
        factors = np.array([one[ref] for one in sets])
        assert np.all(np.abs(factors - 1.0) <= limit)
    assert {one["R9"] for one in sets} == {1.0}
    # Uniform inside the limits: both halves are used, and so are the edges.
    capacitor = np.array([one["C1"] for one in sets])
    assert capacitor.min() < 0.905
    assert capacitor.max() > 1.095
    assert np.mean(capacitor) == pytest.approx(1.0, abs=0.005)
    assert np.std(capacitor) == pytest.approx(0.1 / np.sqrt(3.0), rel=0.05)


def test_a_random_set_is_the_same_for_the_same_seed_whatever_the_order_of_the_parts() -> None:
    forward = {"R1": 0.01, "R2": 0.02, "C1": 0.1}
    backward = {"C1": 0.1, "R2": 0.02, "R1": 0.01}

    first = draw_scales(forward, np.random.default_rng(42))
    second = draw_scales(backward, np.random.default_rng(42))
    other = draw_scales(forward, np.random.default_rng(43))

    assert first == second
    assert list(first) == ["C1", "R1", "R2"]
    assert first != other


def test_a_corner_puts_the_chosen_parts_at_a_limit() -> None:
    spread = {"R1": 0.001, "R2": 0.01, "C1": 0.1}

    scales = corner_scales(spread, {"R1": +1, "R2": -1})

    assert scales == pytest.approx({"R1": 1.001, "R2": 0.99})


def test_a_corner_leaves_out_parts_without_a_tolerance() -> None:
    assert corner_scales({"R1": 0.001}, {"R1": -1, "Q1": +1, "R7": -1}) == pytest.approx(
        {"R1": 0.999}
    )
    assert corner_scales({"R1": 0.001}, {}) == {}
