from __future__ import annotations

import math

import numpy as np
import pytest
from numpy.typing import NDArray

from board_figures import sketch
from board_figures.leakage import (
    NO_NET,
    Leakage,
    LeakageArea,
    LeakageModel,
    VoltageRule,
    label_copper,
    solve_flow,
    surface_leakage,
)
from board_figures.model import Board, Polygon, ZoneFill
from board_figures.raster import Bounds, Window

GRID = 0.25
WINDOW = (0.0, 0.0, 20.0, 12.0)
AREA = LeakageArea(window=WINDOW, grid=GRID, reach=4.0)
CLASSES = {"NODE": "Sense", "GATE": "GateHiZ"}

RULES = (
    VoltageRule(9.0, name_prefixes=("-4V",)),
    VoltageRule(7.0, name_contains=("+12V", "-G)"), classes=("GateHiZ", "GateDrive")),
)


def model(can: Bounds = (0.0, 0.0, 1.0, 1.0)) -> LeakageModel:
    return LeakageModel(
        node_classes=frozenset({"Sense"}),
        followers=frozenset({"GUARD"}),
        ohm_per_square=1e11,
        default_volts=5.0,
        rules=RULES,
        can=can,
    )


def strip(net: str, top: float, bottom: float) -> sketch.Item:
    """A strip across the whole window and beyond, so that no field goes around its ends."""
    return sketch.fill(net, (-5.0, top, 25.0, bottom))


def leak(*items: sketch.Item, can: Bounds = (0.0, 0.0, 1.0, 1.0)) -> Leakage:
    board = sketch.board(*items, classes=CLASSES)
    return surface_leakage(board, "F.Cu", model(can), AREA)


@pytest.mark.parametrize(
    ("net", "net_class", "volts"),
    [
        ("GND", "Default", 5.0),
        ("-4V_A", "Supply", 9.0),
        ("+12V_A", "Supply", 7.0),
        ("/Rails/+12V", "Supply", 7.0),
        ("Net-(Q14-G)", "Default", 7.0),
        ("/Output Stage/DRV_OUT", "GateDrive", 7.0),
        ("Net-(U22-OUT_B)", "GateHiZ", 7.0),
        ("X-4V", "Default", 5.0),
        ("-4V_GATE", "GateHiZ", 9.0),
    ],
)
def test_the_voltage_rule(net: str, net_class: str, volts: float) -> None:
    assert model().volts(net, net_class) == volts


def test_a_rule_without_a_condition_matches_nothing() -> None:
    assert not VoltageRule(3.0).matches("GND", "Default")


def test_current_is_voltage_over_squares_of_sheet_resistance() -> None:
    assert model().nanoamperes(20.0, 5.0) == pytest.approx(1.0)


def test_two_parallel_strips_leak_length_over_gap() -> None:
    # 20 mm of the node, 1 mm from ground: 20 squares, and 5 V over
    # 1e11 ohm / 20 is 1 nA.
    leakage = leak(strip("NODE", 5.0, 6.0), strip("GND", 7.0, 8.0))

    assert leakage.converged
    assert leakage.squares == pytest.approx(20.0, rel=1e-4)
    assert leakage.nanoamperes == pytest.approx(1.0, rel=1e-4)
    assert [(entry.net, entry.volts) for entry in leakage.by_net] == [("GND", 5.0)]
    assert leakage.layer == "F.Cu"
    # Three bare cells between the strips in each of the 80 columns.
    assert leakage.cells >= 3 * 80


def test_a_wider_gap_leaks_less() -> None:
    leakage = leak(strip("NODE", 5.0, 6.0), strip("GND", 9.0, 10.0))

    assert leakage.squares == pytest.approx(20.0 / 3.0, rel=1e-4)


def test_nothing_leaks_past_a_follower_between_the_strips() -> None:
    leakage = leak(strip("NODE", 5.0, 6.0), strip("GUARD", 7.0, 8.0), strip("GND", 9.0, 10.0))

    assert leakage.squares == pytest.approx(0.0, abs=1e-6)
    assert leakage.nanoamperes == pytest.approx(0.0, abs=1e-6)


def test_a_conductor_beyond_the_reach_adds_nothing() -> None:
    near = LeakageArea(window=WINDOW, grid=GRID, reach=2.0)
    board = sketch.board(strip("NODE", 5.0, 6.0), strip("GND", 9.0, 10.0), classes=CLASSES)

    leakage = surface_leakage(board, "F.Cu", model(), near)

    assert leakage.squares == pytest.approx(0.0, abs=1e-6)


def test_each_conductor_leaks_at_its_own_voltage_and_the_largest_comes_first() -> None:
    leakage = leak(strip("GND", 3.0, 4.0), strip("NODE", 5.0, 6.0), strip("GATE", 7.0, 8.0))

    assert [(entry.net, entry.volts) for entry in leakage.by_net] == [("GATE", 7.0), ("GND", 5.0)]
    assert [entry.squares for entry in leakage.by_net] == pytest.approx([20.0, 20.0], rel=1e-4)
    assert [entry.nanoamperes for entry in leakage.by_net] == pytest.approx([1.4, 1.0], rel=1e-4)
    assert leakage.squares == pytest.approx(40.0, rel=1e-4)
    assert leakage.nanoamperes == pytest.approx(2.4, rel=1e-4)


def test_the_current_is_split_at_the_fence_of_the_can() -> None:
    items = (strip("GND", 3.0, 4.0), strip("NODE", 5.0, 6.0), strip("GATE", 7.0, 8.0))

    # The can holds the upper side of the node: the current from ground.
    upper = leak(*items, can=(-1.0, 0.0, 21.0, 5.0))
    everything = leak(*items, can=(-1.0, -1.0, 21.0, 13.0))
    nothing = leak(*items)

    assert (upper.inside_can, upper.outside_can) == pytest.approx((1.0, 1.4), rel=1e-4)
    assert (everything.inside_can, everything.outside_can) == pytest.approx((2.4, 0.0), abs=1e-4)
    assert (nothing.inside_can, nothing.outside_can) == pytest.approx((0.0, 2.4), abs=1e-4)


def test_copper_without_a_net_is_foreign_at_the_default_voltage() -> None:
    leakage = leak(strip("NODE", 5.0, 6.0), strip("", 7.0, 8.0))

    assert [(entry.net, entry.volts) for entry in leakage.by_net] == [(NO_NET, 5.0)]
    assert leakage.nanoamperes == pytest.approx(1.0, rel=1e-4)


def test_only_the_copper_of_the_layer_counts() -> None:
    leakage = leak(
        strip("NODE", 5.0, 6.0),
        sketch.fill("GND", (-5.0, 7.0, 25.0, 8.0), layer="B.Cu"),
        sketch.track("GND", (-5.0, 7.5), (25.0, 7.5), 0.5, layer="B.Cu"),
        sketch.pad("J.1", "GND", (2.0, 7.0, 3.0, 8.0), layers=("B.Cu",)),
    )

    assert leakage.by_net == ()
    assert leakage.squares == 0.0
    assert leakage.nanoamperes == 0.0


def labels_of(board: Board, layer: str = "F.Cu") -> tuple[NDArray[np.int32], list[str]]:
    names = sorted(net.name for net in board.nets)
    window = Window.spanning((0.0, 0.0, 10.0, 10.0), 1.0)
    return label_copper(board, layer, model(), window, names), names


def test_every_cell_gets_its_role() -> None:
    board = sketch.board(
        sketch.pad("R.1", "NODE", (1.0, 1.0, 2.0, 2.0)),
        sketch.track("GUARD", (0.0, 4.0), (9.0, 4.0), 0.5),
        sketch.via("GND", (5.0, 7.0), diameter=1.0),
        sketch.pad("R.2", "", (8.0, 8.0, 9.0, 9.0)),
        sketch.pad("R.3", "GND", (1.0, 8.0, 2.0, 9.0), layers=("B.Cu",)),
        classes=CLASSES,
    )

    labels, names = labels_of(board)

    assert labels[1, 1] == 1
    assert labels[4, 5] == 2
    assert labels[7, 5] == 10 + names.index("GND")
    assert labels[8, 8] == 9
    assert labels[8, 1] == 0
    assert labels[6, 0] == 0


def test_a_via_has_copper_on_every_layer() -> None:
    board = sketch.board(sketch.via("GND", (5.0, 7.0), diameter=1.0), classes=CLASSES)

    labels, names = labels_of(board, layer="B.Cu")

    assert labels[7, 5] == 10 + names.index("GND")


def test_the_fill_of_higher_priority_owns_the_copper() -> None:
    board = sketch.board(
        sketch.fill("NODE", (2.0, 2.0, 6.0, 6.0), priority=2),
        sketch.fill("GND", (0.0, 0.0, 9.0, 9.0), priority=1),
        classes=CLASSES,
    )

    labels, names = labels_of(board)

    assert labels[4, 4] == 1
    assert labels[8, 8] == 10 + names.index("GND")


def test_the_hole_of_a_fill_keeps_what_lies_in_it() -> None:
    board = sketch.board(
        sketch.fill("NODE", (4.0, 4.0, 5.0, 5.0), priority=0),
        sketch.fill("GND", (0.0, 0.0, 9.0, 9.0), priority=1, holes=((2.0, 2.0, 7.0, 7.0),)),
        classes=CLASSES,
    )

    labels, _ = labels_of(board)

    assert labels[4, 4] == 1
    assert labels[3, 3] == 0


def test_the_flow_is_solved_on_a_labeled_raster() -> None:
    labels = np.zeros((7, 5), dtype=np.int32)
    labels[1] = 1
    labels[5] = 12

    flow = solve_flow(labels, grid=1.0, reach=10.0)

    # Three bare rows between the node and the conductor: a quarter of a
    # square per column, entering the node from the row below it.
    assert flow.converged
    assert flow.cells == 5 * 5
    assert flow.squares.sum() == pytest.approx(5 / 4, rel=1e-4)
    assert set(flow.rows[flow.squares > 1e-9].tolist()) == {2}
    assert sorted(flow.cols[flow.squares > 1e-9].tolist()) == [0, 1, 2, 3, 4]
    assert set(flow.source[flow.squares > 1e-9].tolist()) == {12}


SQUARE = LeakageArea(window=(0.0, 0.0, 20.0, 20.0), grid=0.125, reach=6.0)
NODE_PAD = sketch.pad("R.1", "NODE", (9.0, 9.0, 11.0, 11.0))
GROUND_AROUND = sketch.fill(
    "GND", (-5.0, -5.0, 25.0, 25.0), priority=1, holes=((5.0, 5.0, 15.0, 15.0),)
)


def guard_ring(opening: float = 12.0, priority: int = 0) -> sketch.Item:
    """A guard pour around the node pad; an ``opening`` beyond 13 cuts the ring open."""
    return sketch.fill(
        "GUARD", (7.0, 7.0, 13.0, 13.0), priority=priority, holes=((8.0, 8.0, 12.0, opening),)
    )


def leak_in(area: LeakageArea, *items: sketch.Item) -> Leakage:
    return surface_leakage(sketch.board(*items, classes=CLASSES), "F.Cu", model(), area)


def test_a_round_node_in_a_round_hole_leaks_like_a_coaxial_line() -> None:
    # A disc of 1 mm radius in a hole of 4 mm radius: 2 pi / ln(4) squares.
    hole = tuple(
        (10.0 + 4.0 * math.cos(step * math.pi / 64), 10.0 + 4.0 * math.sin(step * math.pi / 64))
        for step in range(128)
    )
    ground = ZoneFill(
        "GND", "F.Cu", 0, (Polygon(sketch.rectangle((-5.0, -5.0, 25.0, 25.0)), (hole,)),)
    )

    leakage = leak_in(SQUARE, sketch.via("NODE", (10.0, 10.0), diameter=2.0), ground)

    assert leakage.converged
    assert leakage.squares == pytest.approx(2 * math.pi / math.log(4.0), rel=0.02)


def test_a_pad_in_the_hole_of_a_fill_leaks_to_the_fill_all_around() -> None:
    leakage = leak_in(SQUARE, NODE_PAD, GROUND_AROUND)

    # Between two round lines: one from the circle through the corners of
    # the pad to the circle inside the hole, which leaks more, and one from
    # the circle inside the pad to the circle through the corners of the
    # hole, which leaks less.
    least = 2 * math.pi / math.log(5.0 * math.sqrt(2.0) / 1.0)
    most = 2 * math.pi / math.log(5.0 / math.sqrt(2.0))
    assert least < leakage.squares < most
    assert [entry.net for entry in leakage.by_net] == ["GND"]


def test_halving_the_grid_moves_the_leakage_by_a_few_percent_at_most() -> None:
    coarse = leak_in(LeakageArea(SQUARE.window, 0.25, SQUARE.reach), NODE_PAD, GROUND_AROUND)
    fine = leak_in(SQUARE, NODE_PAD, GROUND_AROUND)

    assert fine.squares == pytest.approx(coarse.squares, rel=0.02)


@pytest.mark.parametrize("priority", [0, 5])
def test_a_guard_pour_in_the_hole_of_the_ground_fill_stops_the_leakage(priority: int) -> None:
    # The hole of the ground fill must not erase the guard that was laid
    # before it, whichever of the two fills comes first on the board.
    for items in (
        (NODE_PAD, guard_ring(priority=priority), GROUND_AROUND),
        (NODE_PAD, GROUND_AROUND, guard_ring(priority=priority)),
    ):
        leakage = leak_in(SQUARE, *items)

        assert leakage.squares == pytest.approx(0.0, abs=1e-6)


def test_an_open_guard_ring_lets_a_part_of_the_leakage_through() -> None:
    unguarded = leak_in(SQUARE, NODE_PAD, GROUND_AROUND).squares
    through_the_opening = leak_in(SQUARE, NODE_PAD, guard_ring(opening=14.0), GROUND_AROUND).squares

    assert 0.02 * unguarded < through_the_opening < 0.25 * unguarded


def test_a_node_fill_in_the_hole_leaks_like_a_pad_whatever_the_order() -> None:
    node_fill = sketch.fill("NODE", (9.0, 9.0, 11.0, 11.0))
    as_pad = leak_in(SQUARE, NODE_PAD, GROUND_AROUND).squares

    assert leak_in(SQUARE, node_fill, GROUND_AROUND).squares == pytest.approx(as_pad)
    assert leak_in(SQUARE, GROUND_AROUND, node_fill).squares == pytest.approx(as_pad)
