from __future__ import annotations

import dataclasses

import pytest

from board_figures import sketch
from board_figures.errors import BoardError
from board_figures.model import DEFAULT_NET_CLASS, Board, Polygon


def test_a_pad_is_named_by_reference_and_number() -> None:
    pad = sketch.pad("R110.1", "VOUT", (0.0, 0.0, 1.0, 2.0))

    assert pad.name == "R110.1"
    assert pad.position == (0.5, 1.0)
    assert pad.size == (1.0, 2.0)


def test_the_length_of_a_track_is_that_of_its_center_line() -> None:
    assert sketch.track("A", (0.0, 0.0), (3.0, 4.0), 0.2).length == 5.0


def test_value_objects_cannot_be_changed() -> None:
    via = sketch.via("A", (1.0, 1.0))

    with pytest.raises(dataclasses.FrozenInstanceError):
        via.net = "B"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        Board().pads = ()  # type: ignore[misc]


def test_a_polygon_has_no_holes_unless_given() -> None:
    assert Polygon(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0))).holes == ()


def test_a_board_knows_the_nets_it_lists() -> None:
    board = sketch.board(sketch.via("A", (0.0, 0.0)))

    assert board.has_net("A")
    assert not board.has_net("a")
    assert not board.has_net("")


def test_the_net_class_of_an_unlisted_net_is_the_default() -> None:
    board = sketch.board(sketch.via("A", (0.0, 0.0)), classes={"A": "Sense"})

    assert board.net_class("A") == "Sense"
    assert board.net_class("unknown") == DEFAULT_NET_CLASS


def test_nets_are_found_by_class_in_sorted_order() -> None:
    board = sketch.board(classes={"B": "Sense", "A": "Guarded", "C": "Supply"})

    assert board.nets_of_classes(frozenset({"Sense", "Guarded"})) == ("A", "B")
    assert board.nets_of_classes(frozenset()) == ()


def test_pads_are_found_by_name_on_their_net() -> None:
    first = sketch.pad("J4.3", "OUT", (0.0, 0.0, 1.0, 1.0))
    second = sketch.pad("J4.3", "OUT", (5.0, 0.0, 6.0, 1.0))
    board = sketch.board(first, second, sketch.pad("J4.2", "IN", (2.0, 0.0, 3.0, 1.0)))

    assert board.pads_named("J4.3", "OUT") == (first, second)


def test_a_pad_that_does_not_exist_is_an_error() -> None:
    with pytest.raises(BoardError, match=r"the board has no pad R1.1"):
        Board().pads_named("R1.1", "A")


def test_a_pad_on_another_net_is_an_error() -> None:
    board = sketch.board(sketch.pad("R1.1", "B", (0.0, 0.0, 1.0, 1.0)))

    with pytest.raises(BoardError, match=r"the pad R1.1 is on the net 'B', not on 'A'"):
        board.pads_named("R1.1", "A")


def test_vias_and_track_layers_are_counted_per_net() -> None:
    board = sketch.board(
        sketch.via("A", (0.0, 0.0)),
        sketch.via("A", (1.0, 0.0)),
        sketch.via("B", (2.0, 0.0)),
        sketch.track("A", (0.0, 0.0), (1.0, 0.0), 0.2, layer="In2.Cu"),
        sketch.track("A", (0.0, 0.0), (1.0, 0.0), 0.2),
        sketch.track("A", (1.0, 0.0), (2.0, 0.0), 0.2),
    )

    assert board.via_count("A") == 2
    assert board.via_count("C") == 0
    assert board.track_layers("A") == ("F.Cu", "In2.Cu")
    assert board.track_layers("B") == ()
