"""Is there a path between two pads through the copper of one layer alone?

The copper of the net on that layer (pads, tracks, filled zones; vias only
as the dot of copper they have on the layer) is laid on a grid, and the
shortest way from the first pad to the second inside that copper is
measured. No path means that the two pads are joined only through a via or
another layer, or not at all. A pad that has no copper on the layer has no
path on it, whatever copper of the net lies under it there.

The question matters for the current loops of the converters, which have to
close on the top layer without a via, and for nets that may not have a via.
The length is the shortest way through the copper from pad edge to pad edge;
it cuts the corners of a meander and so reads shorter than the center line
of a track (see :mod:`board_figures.pairs` for that).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import sparse
from scipy.sparse.csgraph import dijkstra
from shapely.geometry.base import BaseGeometry

from board_figures.errors import BoardError
from board_figures.geometry import net_copper, pad_shape
from board_figures.model import Board
from board_figures.raster import BoolGrid, Window, rasterize

DEFAULT_GRID = 0.05
"""Cell size in millimeters; fine enough for the narrowest track of the board."""

DEFAULT_LAYER = "F.Cu"
"""The layer that carries the parts."""

_STEPS = ((0, 1), (1, 0), (1, 1), (1, -1))  # half of the eight neighbors; the graph is undirected

_MARGIN = 0.3
"""Free board in millimeters kept around the copper of the net.

The place of the window decides on which side of a cell a corner falls that
lies between two sample points, and the length follows by a cell at most.
The margin is the one that the lengths in the documents of the board were
calculated with, kept so that they stay comparable.
"""


@dataclass(frozen=True, slots=True)
class LayerPath:
    """The answer for one net and one pair of pads.

    Attributes:
        net: Name of the net.
        layer: The layer that was searched.
        length: Shortest way through the copper of the layer in millimeters,
            None when the layer alone does not join the pads.
        vias: Number of vias of the net, wherever they are.
        track_layers: Layers on which the net has tracks.
    """

    net: str
    layer: str
    length: float | None
    vias: int
    track_layers: tuple[str, ...]

    @property
    def exists(self) -> bool:
        """Whether the copper of the layer alone joins the two pads."""
        return self.length is not None


def layer_path(
    board: Board,
    net: str,
    start: str,
    goal: str,
    layer: str = DEFAULT_LAYER,
    grid: float = DEFAULT_GRID,
) -> LayerPath:
    """Search a path between two pads through the copper of a net on one layer.

    Raises:
        BoardError: If the board has no such net, a pad does not exist or is
            on another net, or the net has no copper on the layer.
    """
    if not board.has_net(net):
        raise BoardError(f"the board has no net {net!r}")
    shapes = net_copper(board, net, layer)
    if not shapes:
        raise BoardError(f"the net {net!r} has no copper on {layer}")
    window = _window_around(shapes, grid)
    copper = rasterize(window, shapes)
    ends = [
        rasterize(
            window,
            [pad_shape(pad) for pad in board.pads_named(name, net) if layer in pad.layers],
        )
        & copper
        for name in (start, goal)
    ]
    length = shortest_way(copper, ends[0], ends[1], grid)
    return LayerPath(net, layer, length, board.via_count(net), board.track_layers(net))


def _window_around(shapes: Sequence[BaseGeometry], grid: float) -> Window:
    """The window over the copper of a net, with :data:`_MARGIN` on every side."""
    boxes = [shape.bounds for shape in shapes]
    left = min(box[0] for box in boxes) - _MARGIN
    top = min(box[1] for box in boxes) - _MARGIN
    right = max(box[2] for box in boxes) + _MARGIN
    bottom = max(box[3] for box in boxes) + _MARGIN
    return Window(
        left, top, grid, math.ceil((bottom - top) / grid), math.ceil((right - left) / grid)
    )


def shortest_way(copper: BoolGrid, start: BoolGrid, goal: BoolGrid, grid: float) -> float | None:
    """Length of the shortest way through copper cells from a start to a goal cell.

    A step goes to one of the eight neighbors of a cell. A diagonal step is
    allowed only when both cells beside it are copper too, so that the way
    never slips between two pieces that touch at a corner only.

    Returns:
        The length in the unit of ``grid``, or None when no way exists.
    """
    sources, targets = start & copper, goal & copper
    if not sources.any() or not targets.any():
        return None
    numbers = np.full(copper.shape, -1, dtype=np.int64)
    numbers[copper] = np.arange(int(copper.sum()))
    graph = _neighbor_graph(copper, numbers, grid)
    distance = dijkstra(graph, directed=False, indices=numbers[sources], min_only=True)
    best = float(np.min(distance[numbers[targets]]))
    return best if math.isfinite(best) else None


def _neighbor_graph(copper: BoolGrid, numbers: NDArray[np.int64], grid: float) -> sparse.csr_matrix:
    """The copper cells as a graph, each joined to its copper neighbors."""
    rows, cols = copper.shape
    count = int(copper.sum())
    first: list[NDArray[np.int64]] = []
    second: list[NDArray[np.int64]] = []
    lengths: list[NDArray[np.float64]] = []
    for down, right in _STEPS:
        here = (slice(0, rows - down), slice(max(-right, 0), cols - max(right, 0)))
        there = (slice(down, rows), slice(max(right, 0), cols - max(-right, 0)))
        joined = copper[here] & copper[there]
        if down and right:
            # The two cells beside a diagonal step: same row as the start,
            # and same column as the start.
            joined = joined & copper[here[0], there[1]] & copper[there[0], here[1]]
        first.append(numbers[here][joined])
        second.append(numbers[there][joined])
        lengths.append(np.full(int(joined.sum()), grid * math.hypot(down, right)))
    return sparse.csr_matrix(
        (np.concatenate(lengths), (np.concatenate(first), np.concatenate(second))),
        shape=(count, count),
    )
