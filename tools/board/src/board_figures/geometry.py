"""The copper of the board as shapes.

The model stores copper as numbers: an outline, a center line with a width,
a center with a diameter. The calculations need areas they can lay on a
raster or test for distance, so this module turns each item into a shapely
polygon and collects the copper of one net on one layer.
"""

from __future__ import annotations

from collections.abc import Iterator

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from board_figures.model import Board, Pad, Track, Via, ZoneFill

_ARC_SEGMENTS = 16
"""Straight pieces per quarter circle of a round track end or a via."""


def pad_shape(pad: Pad) -> Polygon:
    """The copper of a pad.

    A pad whose outline is missing from the dump is drawn as a circle around
    its center that reaches its longer side.
    """
    if pad.outline:
        return Polygon(pad.outline)
    return Point(pad.position).buffer(max(pad.size) / 2, quad_segs=_ARC_SEGMENTS)


def track_shape(track: Track) -> Polygon:
    """The copper of a track segment: its center line widened, with round ends."""
    line = LineString([track.start, track.end])
    return line.buffer(track.width / 2, quad_segs=_ARC_SEGMENTS)


def via_shape(via: Via) -> Polygon:
    """The copper ring of a via, as a filled circle."""
    return Point(via.position).buffer(via.diameter / 2, quad_segs=_ARC_SEGMENTS)


def fill_shapes(fill: ZoneFill) -> list[BaseGeometry]:
    """The filled polygons of a zone on its layer.

    A fill that the board editor wrote with a self-touching outline is
    repaired on the way, which can split it into several polygons.
    """
    return [Polygon(polygon.outline, polygon.holes).buffer(0) for polygon in fill.polygons]


def polygons_of(shape: BaseGeometry) -> Iterator[Polygon]:
    """The polygons that make up a shape; lines and points are left out."""
    if isinstance(shape, Polygon):
        if not shape.is_empty:
            yield shape
        return
    for part in getattr(shape, "geoms", ()):
        yield from polygons_of(part)


def net_copper(board: Board, net: str, layer: str) -> list[BaseGeometry]:
    """Every piece of copper of a net on a layer.

    Pads count on the layers they have copper on, tracks and fills on their
    own layer, and vias on every layer, since they are through vias.
    """
    shapes: list[BaseGeometry] = [
        pad_shape(pad) for pad in board.pads if pad.net == net and layer in pad.layers
    ]
    shapes.extend(
        track_shape(track) for track in board.tracks if track.net == net and track.layer == layer
    )
    shapes.extend(via_shape(via) for via in board.vias if via.net == net)
    for fill in board.fills:
        if fill.net == net and fill.layer == layer:
            shapes.extend(fill_shapes(fill))
    return shapes
