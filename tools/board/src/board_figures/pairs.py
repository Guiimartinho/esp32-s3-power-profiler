"""Length of a track along its center line between two pads.

The two conductors of a Kelvin pair should be as long as each other, so
that what they pick up cancels. This module measures one conductor: the
tracks of its net are a graph of segments, and the length is the shortest
way from the first pad to the second along the center lines, from pad edge
to pad edge (a track end inside a pad counts from there).

A track end that lies on another segment, or within a small distance of
another end, is joined to it, so a T joint and a stub are followed
correctly. The layers are not told apart: tracks that meet at a via are
joined there, and the via adds no length. Only tracks count: a conductor
that runs through a filled zone has no center line there, and the two pads
then read as not joined.

This is the electrical length. :mod:`board_figures.path` measures the
shortest way through the copper, which cuts the corners of a meander and so
reads shorter.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from itertools import pairwise

from shapely.geometry import Point as ShapelyPoint

from board_figures.geometry import pad_shape
from board_figures.model import Board, Pad, Point

JOIN_DISTANCE = 0.03
"""Largest gap in millimeters between a track end and a center line that still joins them."""

PAD_MARGIN = 0.01
"""A track end this far outside the outline of a pad still counts as in the pad."""


@dataclass(frozen=True, slots=True)
class Conductor:
    """One conductor of a pair: the tracks of a net between two pads.

    Attributes:
        net: Name of the net.
        start: Name of the pad at one end, such as ``R110.2``.
        goal: Name of the pad at the other end.
    """

    net: str
    start: str
    goal: str


@dataclass(frozen=True, slots=True)
class PairLength:
    """The lengths of the two conductors of a pair.

    Attributes:
        first: Center-line length of the first conductor in millimeters,
            None when its tracks do not join its two pads.
        second: The same for the second conductor.
    """

    first: float | None
    second: float | None

    @property
    def difference(self) -> float | None:
        """Difference of the two lengths, None when one of them is missing."""
        if self.first is None or self.second is None:
            return None
        return abs(self.first - self.second)


def center_line_length(board: Board, net: str, start: str, goal: str) -> float | None:
    """Length along the track center lines of a net between two pads.

    Returns:
        The length in millimeters, or None when the tracks of the net do not
        join the two pads.

    Raises:
        BoardError: If a pad does not exist or is on another net.
    """
    segments = [(track.start, track.end) for track in board.tracks if track.net == net]
    graph = _segment_graph(segments)
    sources = _points_in_pads(list(graph), board.pads_named(start, net))
    targets = set(_points_in_pads(list(graph), board.pads_named(goal, net)))
    return _shortest(graph, sources, targets)


def pair_length(board: Board, first: Conductor, second: Conductor) -> PairLength:
    """Lengths of both conductors of a pair.

    Raises:
        BoardError: If a pad does not exist or is on another net.
    """
    return PairLength(
        center_line_length(board, first.net, first.start, first.goal),
        center_line_length(board, second.net, second.start, second.goal),
    )


def _segment_graph(segments: list[tuple[Point, Point]]) -> dict[Point, list[tuple[Point, float]]]:
    """Join the end points of the segments along every segment they lie on."""
    points = sorted({point for segment in segments for point in segment})
    graph: dict[Point, list[tuple[Point, float]]] = {point: [] for point in points}
    for start, end in segments:
        on_it = sorted(
            (point for point in points if _distance(point, start, end) < JOIN_DISTANCE),
            key=lambda point: math.dist(start, point),
        )
        for a, b in pairwise(on_it):
            graph[a].append((b, math.dist(a, b)))
            graph[b].append((a, math.dist(a, b)))
    return graph


def _distance(point: Point, start: Point, end: Point) -> float:
    """Distance from a point to a straight segment."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    squared = dx * dx + dy * dy
    if squared == 0.0:
        return math.dist(point, start)
    along = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / squared
    along = min(max(along, 0.0), 1.0)
    return math.dist(point, (start[0] + along * dx, start[1] + along * dy))


def _points_in_pads(points: list[Point], pads: tuple[Pad, ...]) -> list[Point]:
    areas = [pad_shape(pad).buffer(PAD_MARGIN) for pad in pads]
    return [point for point in points if any(a.contains(ShapelyPoint(point)) for a in areas)]


def _shortest(
    graph: dict[Point, list[tuple[Point, float]]], sources: list[Point], targets: set[Point]
) -> float | None:
    """Shortest way through the graph from any source to any target."""
    best = dict.fromkeys(sources, 0.0)
    heap = [(0.0, point) for point in sources]
    heapq.heapify(heap)
    while heap:
        length, point = heapq.heappop(heap)
        if point in targets:
            return length
        if length > best[point]:
            continue
        for neighbor, step in graph[point]:
            if length + step < best.get(neighbor, math.inf):
                best[neighbor] = length + step
                heapq.heappush(heap, (length + step, neighbor))
    return None
