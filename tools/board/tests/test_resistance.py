from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from board_figures import sketch
from board_figures.errors import BoardError
from board_figures.model import Board, Pad
from board_figures.raster import BoolGrid
from board_figures.resistance import CopperModel, Link, net_resistance, solve_squares

GRID = 0.125

MODEL = CopperModel(
    layers=("F.Cu", "In2.Cu", "B.Cu"),
    layer_squares={"F.Cu": 1.0, "In2.Cu": 2.0, "B.Cu": 1.0},
    milliohm_per_square=0.5,
    temperature=40.0,
    via_squares=1.7,
    via_drill=0.4,
    plated_hole_squares=0.5,
)

# A strip of 40 mm by 5 mm with a pad of 1 mm at each end: 38 mm between the
# pad edges, so 38 / 5 = 7.6 squares.
STRIP = (0.0, 0.0, 40.0, 5.0)
STRIP_SQUARES = 38.0 / 5.0


def end_pads(layer: str = "F.Cu") -> tuple[Pad, Pad]:
    return (
        sketch.pad("P.1", "A", (0.0, 0.0, 1.0, 5.0), layers=(layer,)),
        sketch.pad("P.2", "A", (39.0, 0.0, 40.0, 5.0), layers=(layer,)),
    )


def strip_board(layer: str = "F.Cu") -> Board:
    return sketch.board(sketch.fill("A", STRIP, layer=layer), *end_pads(layer))


def squares(board: Board, model: CopperModel = MODEL, grid: float = GRID) -> float:
    return net_resistance(board, "A", ["P.1"], ["P.2"], model, grid).squares


def strip_masks() -> tuple[BoolGrid, BoolGrid, BoolGrid]:
    """A strip of 200 by 50 cells with a source column and a sink column."""
    mask = np.zeros((70, 220), dtype=np.bool_)
    mask[10:60, 10:210] = True
    source, sink = np.zeros_like(mask), np.zeros_like(mask)
    source[10:60, 10] = True
    sink[10:60, 209] = True
    return mask, source, sink


def test_a_strip_of_cells_is_length_over_width() -> None:
    mask, source, sink = strip_masks()

    result = solve_squares({"F.Cu": mask}, [], {"F.Cu": source}, {"F.Cu": sink}, {})

    assert result == pytest.approx(199 / 50)


def test_a_layer_of_thinner_copper_counts_more_squares() -> None:
    mask, source, sink = strip_masks()

    result = solve_squares(
        {"In2.Cu": mask}, [], {"In2.Cu": source}, {"In2.Cu": sink}, {"In2.Cu": 2.0}
    )

    assert result == pytest.approx(2 * 199 / 50)


def test_two_sheets_joined_at_both_ends_halve_the_resistance() -> None:
    mask, source, sink = strip_masks()
    nothing = np.zeros_like(mask)
    links = [Link(row, col, 0.001) for row in range(10, 60) for col in (10, 209)]

    result = solve_squares(
        {"F.Cu": mask, "B.Cu": mask.copy()},
        links,
        {"F.Cu": source, "B.Cu": nothing},
        {"F.Cu": sink, "B.Cu": nothing},
        {},
    )

    assert result == pytest.approx(199 / 100, rel=1e-3)


def test_copper_that_reaches_neither_group_does_not_move_the_answer() -> None:
    mask, source, sink = strip_masks()
    mask[2:5, 2:200] = True

    result = solve_squares({"F.Cu": mask}, [], {"F.Cu": source}, {"F.Cu": sink}, {})

    assert result == pytest.approx(199 / 50, rel=1e-6)


def test_two_sheets_without_a_join_are_not_connected() -> None:
    mask, source, sink = strip_masks()
    nothing = np.zeros_like(mask)

    result = solve_squares(
        {"F.Cu": mask, "B.Cu": mask.copy()},
        [],
        {"F.Cu": source, "B.Cu": nothing},
        {"F.Cu": nothing, "B.Cu": sink},
        {},
    )

    assert result == math.inf


def test_a_group_without_copper_under_it_is_an_error() -> None:
    mask, source, _ = strip_masks()

    with pytest.raises(BoardError, match="a group of pads has no copper of the net on the grid"):
        solve_squares({"F.Cu": mask}, [], {"F.Cu": source}, {"F.Cu": np.zeros_like(mask)}, {})


def test_a_strip_between_two_pads_is_length_over_width() -> None:
    result = squares(strip_board())

    # On the grid the strip is 41 cells wide and the pads are 304 cells apart.
    assert result == pytest.approx(304 / 41)
    # The raster draws the strip one cell too wide, so the figure is a
    # little lower than the drawing; the error shrinks with the cell.
    assert result == pytest.approx(STRIP_SQUARES, rel=0.03)
    assert result < STRIP_SQUARES
    coarse = squares(strip_board(), grid=0.5)
    assert abs(coarse - STRIP_SQUARES) > abs(result - STRIP_SQUARES)


def test_the_result_carries_the_resistance_and_the_copper_area() -> None:
    result = net_resistance(strip_board(), "A", ["P.1"], ["P.2"], MODEL, GRID)

    assert result.connected
    assert result.milliohm == pytest.approx(result.squares * 0.5)
    assert result.copper_area == pytest.approx(200.0)


def test_two_layers_joined_by_vias_halve_the_resistance() -> None:
    model = dataclasses.replace(MODEL, layers=("F.Cu", "B.Cu"), via_squares=1e-3)
    rows = [0.125 + 0.125 * step for step in range(39)]
    vias = [sketch.via("A", (x, y), diameter=0.1, drill=0.4) for x in (0.5, 39.5) for y in rows]
    board = sketch.board(
        sketch.fill("A", STRIP), sketch.fill("A", STRIP, layer="B.Cu"), *end_pads(), *vias
    )

    assert squares(board, model) == pytest.approx(squares(strip_board()) / 2, rel=0.03)


def test_an_inner_layer_of_half_the_thickness_counts_double() -> None:
    assert squares(strip_board("In2.Cu")) == pytest.approx(2 * squares(strip_board()))


def test_a_via_counts_in_inverse_proportion_to_its_drill() -> None:
    assert MODEL.squares_of_via(0.4) == pytest.approx(1.7)
    assert MODEL.squares_of_via(0.3) == pytest.approx(1.7 * 0.4 / 0.3)
    assert MODEL.squares_of_via(0.0) == pytest.approx(1.7 * 0.4 / 0.1)
    assert MODEL.milliohm(10.0) == pytest.approx(5.0)


def changing_layer(*joins: sketch.Item) -> Board:
    """Half of the way on the top, the other half on the bottom."""
    return sketch.board(
        sketch.fill("A", (0.0, 0.0, 20.0, 5.0)),
        sketch.fill("A", (19.0, 0.0, 40.0, 5.0), layer="B.Cu"),
        sketch.pad("P.1", "A", (0.0, 0.0, 1.0, 5.0)),
        sketch.pad("P.2", "A", (39.0, 0.0, 40.0, 5.0), layers=("B.Cu",)),
        *joins,
    )


def test_a_via_adds_its_squares_once_per_layer_it_passes() -> None:
    board = changing_layer(sketch.via("A", (19.5, 2.5), drill=0.4))

    low = squares(board, dataclasses.replace(MODEL, via_squares=1.0))
    high = squares(board, dataclasses.replace(MODEL, via_squares=5.0))

    # From the top to the bottom the via passes the inner layer: two steps.
    assert high - low == pytest.approx(2 * 4.0, rel=1e-6)


def test_two_layers_without_a_via_are_not_connected() -> None:
    result = net_resistance(changing_layer(), "A", ["P.1"], ["P.2"], MODEL, GRID)

    assert result.squares == math.inf
    assert not result.connected


def test_a_plated_hole_joins_the_layers_of_its_pad() -> None:
    pin = sketch.pad("J.1", "A", (19.0, 2.0, 20.0, 3.0), layers=("F.Cu", "B.Cu"), drill=0.8)
    surface = dataclasses.replace(pin, drill=0.0)

    assert math.isfinite(squares(changing_layer(pin)))
    assert squares(changing_layer(surface)) == math.inf


def test_tracks_carry_current_as_well() -> None:
    board = sketch.board(
        sketch.track("A", (0.5, 2.5), (39.5, 2.5), 1.0),
        sketch.track("A", (0.5, 2.5), (39.5, 2.5), 1.0, layer="In1.Cu"),
        *end_pads(),
    )

    # 38 mm of a track 1 mm wide, less what the raster and the spreading at
    # the pads take off.
    assert 30.0 < squares(board) < 38.0


def test_a_net_without_copper_on_the_layers_is_an_error() -> None:
    board = sketch.board(sketch.track("A", (0.0, 0.0), (5.0, 0.0), 0.5, layer="In1.Cu"))

    with pytest.raises(BoardError, match=r"the net 'A' has no copper on F.Cu, In2.Cu, B.Cu"):
        net_resistance(board, "A", ["P.1"], ["P.2"], MODEL)


def test_a_net_that_the_board_does_not_have_is_an_error() -> None:
    with pytest.raises(BoardError, match=r"the board has no net 'B'"):
        net_resistance(strip_board(), "B", ["P.1"], ["P.2"], MODEL)


def test_a_pad_that_does_not_exist_is_an_error() -> None:
    with pytest.raises(BoardError, match=r"the board has no pad X.9"):
        net_resistance(strip_board(), "A", ["P.1"], ["X.9"], MODEL)


def test_a_pad_on_a_layer_that_carries_no_current_is_an_error() -> None:
    board = sketch.board(
        sketch.fill("A", STRIP),
        sketch.pad("P.1", "A", (0.0, 0.0, 1.0, 5.0)),
        sketch.pad("P.2", "A", (39.0, 0.0, 40.0, 5.0), layers=("In1.Cu",)),
    )

    with pytest.raises(BoardError, match="a group of pads has no copper of the net on the grid"):
        net_resistance(board, "A", ["P.1"], ["P.2"], MODEL)


def test_two_cells_side_by_side_are_one_square() -> None:
    copper = np.ones((1, 2), dtype=np.bool_)
    source = np.array([[True, False]])
    sink = np.array([[False, True]])

    assert solve_squares({"F.Cu": copper}, [], {"F.Cu": source}, {"F.Cu": sink}, {}) == 1.0


def l_shape() -> Board:
    """Two arms 5 mm wide at a right angle, 24 mm each up to the corner square."""
    return sketch.board(
        sketch.fill("A", (0.0, 0.0, 30.0, 5.0)),
        sketch.fill("A", (25.0, 0.0, 30.0, 30.0)),
        sketch.pad("P.1", "A", (0.0, 0.0, 1.0, 5.0)),
        sketch.pad("P.2", "A", (25.0, 29.0, 30.0, 30.0)),
    )


def test_the_corner_of_an_l_shape_counts_about_half_a_square() -> None:
    result = squares(l_shape())

    # The textbook figure for a right-angle bend is 0.56 squares.
    assert result == pytest.approx(2 * 24.0 / 5.0 + 0.56, rel=0.03)
    # Less than the two arms and a whole corner square laid end to end.
    assert result < 2 * 24.0 / 5.0 + 1.0


HOLE = (15.0, 1.5, 25.0, 3.5)


def holed_strip(hole: tuple[float, float, float, float] = HOLE) -> Board:
    """The strip with a hole; ``HOLE`` leaves two lanes of 1.5 mm over 10 mm."""
    return sketch.board(sketch.fill("A", STRIP, holes=(hole,)), *end_pads())


def test_a_hole_in_a_strip_adds_resistance() -> None:
    result = squares(holed_strip())

    # Sections in series, as if the current filled each one evenly, are a
    # lower limit of the drawing; the crowding at the ends of the hole comes
    # on top, and the raster takes a little off.
    in_series = 28.0 / 5.0 + 10.0 / 3.0
    assert result > squares(strip_board()) + 1.0
    assert result == pytest.approx(in_series, rel=0.03)
    assert squares(holed_strip(), grid=GRID / 2) > in_series


def test_a_slit_across_the_strip_opens_it() -> None:
    assert squares(holed_strip((15.0, -1.0, 16.0, 6.0))) == math.inf


def through_vias(count: int) -> Board:
    """The top carries the current to the middle and the bottom from there, through vias."""
    rows = [5.0 * (step + 0.5) / count for step in range(count)]
    return sketch.board(
        sketch.fill("A", (0.0, 0.0, 20.0, 5.0)),
        sketch.fill("A", (15.0, 0.0, 40.0, 5.0), layer="B.Cu"),
        sketch.pad("P.1", "A", (0.0, 0.0, 1.0, 5.0)),
        sketch.pad("P.2", "A", (39.0, 0.0, 40.0, 5.0), layers=("B.Cu",)),
        *[sketch.via("A", (17.5, y), drill=0.4) for y in rows],
    )


def test_many_vias_carry_the_current_better_than_one() -> None:
    model = dataclasses.replace(MODEL, layers=("F.Cu", "B.Cu"))
    one, two, four, eight = (squares(through_vias(count), model) for count in (1, 2, 4, 8))
    sheet = squares(strip_board())

    assert one > two > four > eight > sheet
    # One via: its 1.7 squares, and on top the crowding of the whole
    # current into one cell of each layer.
    assert one > sheet + 1.7
    # Eight vias across the strip: an eighth of a via and little crowding.
    assert eight == pytest.approx(sheet + 1.7 / 8, rel=0.05)


@pytest.mark.parametrize("board", [strip_board(), l_shape(), holed_strip()])
def test_halving_the_grid_moves_the_result_by_a_few_percent_at_most(board: Board) -> None:
    coarse, fine = squares(board, grid=2 * GRID), squares(board, grid=GRID)

    assert fine == pytest.approx(coarse, rel=0.03)
    # The raster draws copper too wide, so a finer grid reads higher.
    assert fine > coarse
