from __future__ import annotations

import pytest

from board_figures import sketch
from board_figures.errors import BoardError
from board_figures.model import Board
from board_figures.pairs import Conductor, PairLength, center_line_length, pair_length


def square_pad(name: str, net: str, x: float, y: float) -> sketch.Item:
    return sketch.pad(name, net, (x - 0.5, y - 0.5, x + 0.5, y + 0.5))


def test_a_straight_track_from_pad_to_pad() -> None:
    board = sketch.board(
        sketch.track("A", (0.0, 0.0), (10.0, 0.0), 0.2),
        square_pad("R.1", "A", 0.0, 0.0),
        square_pad("U.1", "A", 10.0, 0.0),
    )

    assert center_line_length(board, "A", "R.1", "U.1") == pytest.approx(10.0)
    assert center_line_length(board, "A", "U.1", "R.1") == pytest.approx(10.0)


def test_the_length_follows_the_corners_of_a_polyline() -> None:
    board = sketch.board(
        sketch.track("A", (0.0, 0.0), (5.0, 0.0), 0.2),
        sketch.track("A", (5.0, 0.0), (8.0, 4.0), 0.2),
        sketch.track("A", (8.0, 4.0), (12.0, 4.0), 0.2),
        square_pad("R.1", "A", 0.0, 0.0),
        square_pad("U.1", "A", 12.0, 4.0),
    )

    assert center_line_length(board, "A", "R.1", "U.1") == pytest.approx(5.0 + 5.0 + 4.0)


def t_joint(stub_start: float) -> Board:
    """A track with a stub that leaves it half way, ``stub_start`` beside its center line."""
    return sketch.board(
        sketch.track("A", (0.0, 0.0), (10.0, 0.0), 0.2),
        sketch.track("A", (5.0, stub_start), (5.0, 3.0), 0.2),
        square_pad("R.1", "A", 0.0, 0.0),
        square_pad("U.1", "A", 10.0, 0.0),
        square_pad("C.1", "A", 5.0, 3.0),
    )


def test_a_stub_is_followed_from_the_point_where_it_leaves_the_track() -> None:
    assert center_line_length(t_joint(0.0), "A", "R.1", "C.1") == pytest.approx(5.0 + 3.0)
    assert center_line_length(t_joint(0.0), "A", "C.1", "U.1") == pytest.approx(3.0 + 5.0)
    assert center_line_length(t_joint(0.0), "A", "R.1", "U.1") == pytest.approx(10.0)


def test_a_track_end_just_beside_a_center_line_is_joined_to_it() -> None:
    assert center_line_length(t_joint(0.02), "A", "R.1", "C.1") == pytest.approx(8.0, abs=0.05)


def test_a_track_end_away_from_a_center_line_is_not_joined() -> None:
    assert center_line_length(t_joint(0.05), "A", "R.1", "C.1") is None


def test_the_shorter_of_two_ways_counts() -> None:
    board = sketch.board(
        sketch.track("A", (0.0, 0.0), (10.0, 0.0), 0.2),
        sketch.track("A", (0.0, 0.0), (0.0, 5.0), 0.2),
        sketch.track("A", (0.0, 5.0), (10.0, 5.0), 0.2),
        sketch.track("A", (10.0, 5.0), (10.0, 0.0), 0.2),
        square_pad("R.1", "A", 0.0, 0.0),
        square_pad("U.1", "A", 10.0, 0.0),
    )

    assert center_line_length(board, "A", "R.1", "U.1") == pytest.approx(10.0)


def test_tracks_that_meet_at_a_via_are_joined_whatever_their_layer() -> None:
    board = sketch.board(
        sketch.track("A", (0.0, 0.0), (5.0, 0.0), 0.2),
        sketch.via("A", (5.0, 0.0)),
        sketch.track("A", (5.0, 0.0), (10.0, 0.0), 0.2, layer="In2.Cu"),
        square_pad("R.1", "A", 0.0, 0.0),
        square_pad("U.1", "A", 10.0, 0.0),
    )

    assert center_line_length(board, "A", "R.1", "U.1") == pytest.approx(10.0)


def test_a_track_of_no_length_does_no_harm() -> None:
    board = sketch.board(
        sketch.track("A", (0.0, 0.0), (10.0, 0.0), 0.2),
        sketch.track("A", (4.0, 0.0), (4.0, 0.0), 0.2),
        square_pad("R.1", "A", 0.0, 0.0),
        square_pad("U.1", "A", 10.0, 0.0),
    )

    assert center_line_length(board, "A", "R.1", "U.1") == pytest.approx(10.0)


def test_tracks_that_do_not_reach_a_pad_give_no_length() -> None:
    board = sketch.board(
        sketch.track("A", (0.0, 0.0), (4.0, 0.0), 0.2),
        sketch.track("A", (6.0, 0.0), (10.0, 0.0), 0.2),
        square_pad("R.1", "A", 0.0, 0.0),
        square_pad("U.1", "A", 10.0, 0.0),
        square_pad("C.1", "A", 20.0, 20.0),
    )

    assert center_line_length(board, "A", "R.1", "U.1") is None
    assert center_line_length(board, "A", "R.1", "C.1") is None
    assert center_line_length(board, "A", "C.1", "U.1") is None


def test_a_pad_on_another_net_is_an_error() -> None:
    board = sketch.board(square_pad("R.1", "A", 0.0, 0.0), square_pad("U.1", "B", 10.0, 0.0))

    with pytest.raises(BoardError, match=r"the pad U.1 is on the net 'B', not on 'A'"):
        center_line_length(board, "A", "R.1", "U.1")


def test_the_two_conductors_of_a_pair(small_board: Board) -> None:
    length = pair_length(small_board, Conductor("SP", "R.1", "U.1"), Conductor("SN", "R.2", "U.2"))

    assert length.first == pytest.approx(10.0)
    assert length.second == pytest.approx(12.0)
    assert length.difference == pytest.approx(2.0)


def test_a_pair_with_a_missing_length_has_no_difference() -> None:
    assert PairLength(10.0, None).difference is None
    assert PairLength(None, 10.0).difference is None
    assert PairLength(10.0, 10.5).difference == pytest.approx(0.5)


def test_a_shorter_way_found_later_replaces_the_first_one() -> None:
    # The joint at (3, 0) is first reached over the corner at (0, 1) and then,
    # shorter, along the straight track.
    board = sketch.board(
        sketch.track("A", (0.0, 0.0), (0.0, 1.0), 0.2),
        sketch.track("A", (0.0, 1.0), (3.0, 0.0), 0.2),
        sketch.track("A", (0.0, 0.0), (2.0, 0.0), 0.2),
        sketch.track("A", (2.0, 0.0), (3.0, 0.0), 0.2),
        sketch.track("A", (3.0, 0.0), (3.0, -20.0), 0.2),
        square_pad("R.1", "A", 0.0, 0.0),
        square_pad("U.1", "A", 3.0, -20.0),
    )

    assert center_line_length(board, "A", "R.1", "U.1") == pytest.approx(23.0)
