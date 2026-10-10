from __future__ import annotations

import math

import numpy as np
import pytest

from board_figures import sketch
from board_figures.errors import BoardError
from board_figures.model import Board
from board_figures.path import layer_path, shortest_way
from board_figures.raster import BoolGrid

GRID = 0.125


def grid_of(rows: list[list[int]]) -> BoolGrid:
    return np.array(rows, dtype=np.bool_)


def one_cell(shape: tuple[int, int], row: int, col: int) -> BoolGrid:
    mask = np.zeros(shape, dtype=np.bool_)
    mask[row, col] = True
    return mask


def test_the_way_along_a_row_of_cells() -> None:
    copper = grid_of([[1, 1, 1, 1, 1]])

    assert shortest_way(copper, one_cell((1, 5), 0, 0), one_cell((1, 5), 0, 4), 0.5) == 2.0


def test_a_diagonal_step_counts_its_length() -> None:
    copper = grid_of([[1, 1], [1, 1]])

    way = shortest_way(copper, one_cell((2, 2), 0, 0), one_cell((2, 2), 1, 1), 1.0)

    assert way == pytest.approx(math.sqrt(2))


def test_the_other_diagonal_counts_as_well() -> None:
    copper = grid_of([[1, 1], [1, 1]])

    way = shortest_way(copper, one_cell((2, 2), 0, 1), one_cell((2, 2), 1, 0), 1.0)

    assert way == pytest.approx(math.sqrt(2))


def test_no_way_between_two_cells_that_touch_at_a_corner_only() -> None:
    copper = grid_of([[1, 0], [0, 1]])

    assert shortest_way(copper, one_cell((2, 2), 0, 0), one_cell((2, 2), 1, 1), 1.0) is None


def test_a_diagonal_step_needs_both_cells_beside_it() -> None:
    copper = grid_of([[1, 1], [0, 1]])

    assert shortest_way(copper, one_cell((2, 2), 0, 0), one_cell((2, 2), 1, 1), 1.0) == 2.0


def test_no_way_without_a_start_or_a_goal() -> None:
    copper = grid_of([[1, 1, 1]])
    nowhere = np.zeros((1, 3), dtype=np.bool_)

    assert shortest_way(copper, nowhere, one_cell((1, 3), 0, 2), 1.0) is None
    assert shortest_way(copper, one_cell((1, 3), 0, 0), nowhere, 1.0) is None


def test_start_and_goal_count_only_where_there_is_copper() -> None:
    copper = grid_of([[1, 1, 0]])

    assert shortest_way(copper, one_cell((1, 3), 0, 0), one_cell((1, 3), 0, 2), 1.0) is None


def pads() -> tuple[sketch.Item, sketch.Item]:
    return (
        sketch.pad("R.1", "A", (-0.5, -0.5, 0.5, 0.5)),
        sketch.pad("R.2", "A", (9.5, -0.5, 10.5, 0.5)),
    )


def test_a_straight_track_joins_its_pads_on_one_layer() -> None:
    board = sketch.board(sketch.track("A", (0.0, 0.0), (10.0, 0.0), 0.5), *pads())

    found = layer_path(board, "A", "R.1", "R.2", grid=GRID)

    assert found.exists
    # 9 mm from pad edge to pad edge, less one cell that the raster adds to a pad.
    assert found.length == pytest.approx(9.0, abs=2 * GRID)
    assert (found.net, found.layer, found.vias, found.track_layers) == ("A", "F.Cu", 0, ("F.Cu",))


def test_the_way_follows_the_copper_around_a_corner() -> None:
    board = sketch.board(
        sketch.track("A", (0.0, 0.0), (10.0, 0.0), 0.5),
        sketch.track("A", (10.0, 0.0), (10.0, 10.0), 0.5),
        sketch.pad("R.1", "A", (-0.5, -0.5, 0.5, 0.5)),
        sketch.pad("R.2", "A", (9.5, 9.5, 10.5, 10.5)),
    )

    found = layer_path(board, "A", "R.1", "R.2", grid=GRID)

    # 9.5 mm to the corner and 9.5 mm on, less the corner that the way cuts.
    assert found.length == pytest.approx(19.0, abs=0.8)
    assert found.length is not None
    assert found.length < 19.0


def interrupted() -> Board:
    """A track that leaves the top layer between its pads."""
    return sketch.board(
        sketch.track("A", (0.0, 0.0), (4.0, 0.0), 0.5),
        sketch.via("A", (4.0, 0.0)),
        sketch.track("A", (4.0, 0.0), (6.0, 0.0), 0.5, layer="B.Cu"),
        sketch.via("A", (6.0, 0.0)),
        sketch.track("A", (6.0, 0.0), (10.0, 0.0), 0.5),
        *pads(),
    )


def test_no_path_when_the_copper_changes_layer() -> None:
    found = layer_path(interrupted(), "A", "R.1", "R.2", grid=GRID)

    assert not found.exists
    assert found.length is None
    assert found.vias == 2
    assert found.track_layers == ("B.Cu", "F.Cu")


def test_the_layer_is_chosen_by_the_caller() -> None:
    board = sketch.board(
        sketch.track("A", (0.0, 0.0), (10.0, 0.0), 0.5, layer="B.Cu"),
        sketch.pad("R.1", "A", (-0.5, -0.5, 0.5, 0.5), layers=("B.Cu",)),
        sketch.pad("R.2", "A", (9.5, -0.5, 10.5, 0.5), layers=("B.Cu",)),
    )

    assert layer_path(board, "A", "R.1", "R.2", layer="B.Cu", grid=GRID).exists


def test_a_net_without_copper_on_the_layer_is_an_error() -> None:
    board = sketch.board(sketch.track("A", (0.0, 0.0), (10.0, 0.0), 0.5), *pads())

    with pytest.raises(BoardError, match=r"the net 'A' has no copper on In1.Cu"):
        layer_path(board, "A", "R.1", "R.2", layer="In1.Cu")


def test_a_net_that_the_board_does_not_have_is_an_error() -> None:
    board = sketch.board(sketch.track("A", (0.0, 0.0), (10.0, 0.0), 0.5), *pads())

    with pytest.raises(BoardError, match=r"the board has no net '/Missing'"):
        layer_path(board, "/Missing", "R.1", "R.2")


def test_a_pad_on_another_net_is_an_error() -> None:
    board = sketch.board(
        sketch.track("A", (0.0, 0.0), (10.0, 0.0), 0.5),
        sketch.pad("R.1", "A", (-0.5, -0.5, 0.5, 0.5)),
        sketch.pad("R.2", "B", (9.5, -0.5, 10.5, 0.5)),
    )

    with pytest.raises(BoardError, match=r"the pad R.2 is on the net 'B', not on 'A'"):
        layer_path(board, "A", "R.1", "R.2")


def test_a_pad_without_copper_on_the_layer_has_no_path_on_it() -> None:
    # Two pads on the top and a pour of their net under both on the bottom:
    # the bottom joins the places of the pads, not the pads.
    board = sketch.board(
        sketch.fill("A", (-1.0, -1.0, 11.0, 1.0), layer="B.Cu"),
        sketch.track("A", (0.0, 0.0), (10.0, 0.0), 0.5),
        *pads(),
    )

    assert layer_path(board, "A", "R.1", "R.2", grid=GRID).exists
    assert not layer_path(board, "A", "R.1", "R.2", layer="B.Cu", grid=GRID).exists


def test_only_the_pad_with_copper_on_the_layer_is_an_end() -> None:
    # A terminal with two legs of the same number: one through the board,
    # one on the top only. On the bottom the way starts at the first.
    board = sketch.board(
        sketch.fill("A", (-1.0, -1.0, 21.0, 1.0), layer="B.Cu"),
        sketch.pad("J.1", "A", (-0.5, -0.5, 0.5, 0.5), layers=("F.Cu", "B.Cu"), drill=0.5),
        sketch.pad("J.1", "A", (9.5, -0.5, 10.5, 0.5)),
        sketch.pad("J.2", "A", (19.5, -0.5, 20.5, 0.5), layers=("F.Cu", "B.Cu"), drill=0.5),
    )

    found = layer_path(board, "A", "J.1", "J.2", layer="B.Cu", grid=GRID)

    assert found.length == pytest.approx(19.0, abs=2 * GRID)


def test_a_path_through_a_via_alone_exists_on_neither_layer() -> None:
    board = sketch.board(
        sketch.track("A", (0.0, 0.0), (4.0, 0.0), 0.5),
        sketch.via("A", (4.0, 0.0)),
        sketch.track("A", (4.0, 0.0), (10.0, 0.0), 0.5, layer="B.Cu"),
        sketch.pad("R.1", "A", (-0.5, -0.5, 0.5, 0.5)),
        sketch.pad("R.2", "A", (9.5, -0.5, 10.5, 0.5), layers=("B.Cu",)),
    )

    assert not layer_path(board, "A", "R.1", "R.2", grid=GRID).exists
    assert not layer_path(board, "A", "R.1", "R.2", layer="B.Cu", grid=GRID).exists


def test_the_window_lies_three_tenths_of_a_millimeter_outside_the_copper() -> None:
    # The copper starts at x = -0.5, so the window starts at -0.8 and the
    # sample points of the cells lie at -0.7375 + n / 8. The first pad ends
    # at 0.55, which moves to the sample point of cell 10 at 0.5125; the
    # second starts at 9.5 and moves to cell 81 at 9.3875. With the window
    # two cells outside the copper the first pad would end in cell 9.
    board = sketch.board(
        sketch.track("A", (0.0, 0.0), (10.0, 0.0), 0.5),
        sketch.pad("R.1", "A", (-0.5, -0.5, 0.55, 0.5)),
        sketch.pad("R.2", "A", (9.5, -0.5, 10.5, 0.5)),
    )

    assert layer_path(board, "A", "R.1", "R.2", grid=GRID).length == pytest.approx(71 * GRID)


def test_halving_the_grid_moves_the_length_by_less_than_a_cell() -> None:
    board = sketch.board(
        sketch.track("A", (0.0, 0.0), (10.0, 0.0), 0.5),
        sketch.track("A", (10.0, 0.0), (10.0, 10.0), 0.5),
        sketch.pad("R.1", "A", (-0.5, -0.5, 0.5, 0.5)),
        sketch.pad("R.2", "A", (9.5, 9.5, 10.5, 10.5)),
    )

    coarse = layer_path(board, "A", "R.1", "R.2", grid=GRID).length
    fine = layer_path(board, "A", "R.1", "R.2", grid=GRID / 2).length

    assert coarse is not None
    assert fine is not None
    assert abs(coarse - fine) < 2 * GRID
