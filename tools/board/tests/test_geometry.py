from __future__ import annotations

import dataclasses
import math

import pytest
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon, box

from board_figures import sketch
from board_figures.geometry import (
    fill_shapes,
    net_copper,
    pad_shape,
    polygons_of,
    track_shape,
    via_shape,
)


def test_a_pad_is_its_outline() -> None:
    shape = pad_shape(sketch.pad("R1.1", "A", (1.0, 2.0, 3.0, 5.0)))

    assert shape.bounds == (1.0, 2.0, 3.0, 5.0)
    assert shape.area == pytest.approx(6.0)


def test_a_pad_without_an_outline_is_a_circle_over_its_longer_side() -> None:
    pad = dataclasses.replace(sketch.pad("R1.1", "A", (0.0, 0.0, 2.0, 4.0)), outline=())

    shape = pad_shape(pad)

    assert shape.bounds == pytest.approx((-1.0, 0.0, 3.0, 4.0))
    assert shape.area == pytest.approx(math.pi * 4.0, rel=0.01)


def test_a_track_is_its_center_line_widened_with_round_ends() -> None:
    shape = track_shape(sketch.track("A", (0.0, 0.0), (10.0, 0.0), 2.0))

    assert shape.bounds == pytest.approx((-1.0, -1.0, 11.0, 1.0))
    assert shape.area == pytest.approx(10.0 * 2.0 + math.pi, rel=0.01)


def test_a_via_is_a_filled_circle() -> None:
    shape = via_shape(sketch.via("A", (5.0, 5.0), diameter=0.8))

    assert shape.bounds == pytest.approx((4.6, 4.6, 5.4, 5.4))
    assert shape.area == pytest.approx(math.pi * 0.16, rel=0.01)


def test_a_fill_keeps_its_holes() -> None:
    fill = sketch.fill("GND", (0.0, 0.0, 10.0, 10.0), holes=((4.0, 4.0, 6.0, 6.0),))

    (shape,) = fill_shapes(fill)

    assert shape.area == pytest.approx(96.0)


def test_shapes_are_taken_apart_into_polygons() -> None:
    first, second = box(0, 0, 1, 1), box(2, 0, 3, 1)
    mixed = GeometryCollection([first, LineString([(0, 0), (1, 1)]), MultiPolygon([second])])

    assert list(polygons_of(first)) == [first]
    assert list(polygons_of(MultiPolygon([first, second]))) == [first, second]
    assert list(polygons_of(mixed)) == [first, second]
    assert list(polygons_of(Polygon())) == []
    assert list(polygons_of(LineString([(0, 0), (1, 1)]))) == []


def test_the_copper_of_a_net_on_a_layer() -> None:
    board = sketch.board(
        sketch.pad("R1.1", "A", (0.0, 0.0, 1.0, 1.0)),
        sketch.pad("J1.1", "A", (5.0, 0.0, 6.0, 1.0), layers=("F.Cu", "B.Cu"), drill=0.8),
        sketch.pad("R1.2", "B", (2.0, 0.0, 3.0, 1.0)),
        sketch.track("A", (0.5, 0.5), (5.5, 0.5), 0.2),
        sketch.track("A", (0.5, 0.5), (5.5, 0.5), 0.2, layer="B.Cu"),
        sketch.track("B", (2.5, 0.5), (2.5, 4.0), 0.2),
        sketch.via("A", (3.0, 0.5)),
        sketch.via("B", (2.5, 4.0)),
        sketch.fill("A", (0.0, 2.0, 6.0, 3.0)),
        sketch.fill("A", (0.0, 2.0, 6.0, 3.0), layer="B.Cu"),
        sketch.fill("B", (0.0, 5.0, 6.0, 6.0)),
    )

    # Two pads, one track, one via and one fill on the top; the through-hole
    # pad, one track, the same via and one fill on the bottom.
    assert len(net_copper(board, "A", "F.Cu")) == 5
    assert len(net_copper(board, "A", "B.Cu")) == 4
    # A via is a through via: it has copper on a layer the net does not use.
    assert len(net_copper(board, "A", "In2.Cu")) == 1
    assert net_copper(board, "C", "F.Cu") == []
