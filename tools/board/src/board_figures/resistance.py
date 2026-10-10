"""Resistance of the copper of a net between two groups of pads.

The copper of the net (pads, tracks, vias and filled zones) is laid on a
grid, one sheet per layer. Neighboring cells of a layer are joined by the
sheet resistance of that layer; a via or a plated hole joins the layers at
its place. The pads of the first group are held at one potential, those of
the second at another, and the current that flows gives the resistance.

The result is counted in squares: one square is the resistance of a square
piece of the reference copper, whatever its size, measured between two
opposite sides. A strip of length L and width W has L / W squares. A layer of
thinner copper counts more squares for the same shape.

It is a calculation from the drawn copper, not a measurement.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import spsolve
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from board_figures.errors import BoardError
from board_figures.geometry import fill_shapes, pad_shape, track_shape, via_shape
from board_figures.model import Board
from board_figures.raster import BoolGrid, Bounds, Window, rasterize

DEFAULT_GRID = 0.1
"""Cell size in millimeters that the figures of the documents use."""


@dataclass(frozen=True, slots=True)
class CopperModel:
    """The assumptions about the copper of the board.

    Attributes:
        layers: The layers that carry current between the pads, in the
            order of the stack. A via joins each of them to the next.
        layer_squares: For each layer, how many squares of the reference
            copper one square of that layer is worth: the reference
            thickness over the thickness of the layer.
        milliohm_per_square: Resistance of one square of the reference
            copper at ``temperature``.
        temperature: Temperature in degrees Celsius that the resistance per
            square is given for.
        via_squares: Squares that a via of ``via_drill`` counts from one
            layer to the next.
        via_drill: Drill diameter that ``via_squares`` is given for. A via
            of another drill counts in inverse proportion.
        plated_hole_squares: Squares that the plated hole of a through-hole
            pad counts from one layer to the next.
        min_via_drill: Smallest drill used in the proportion, so that a via
            dumped without a drill does not divide by zero.
    """

    layers: tuple[str, ...]
    layer_squares: Mapping[str, float]
    milliohm_per_square: float
    temperature: float
    via_squares: float
    via_drill: float
    plated_hole_squares: float
    min_via_drill: float = 0.1

    def squares_of_via(self, drill: float) -> float:
        """Squares of a via with the given drill, from one layer to the next."""
        return self.via_squares * self.via_drill / max(drill, self.min_via_drill)

    def milliohm(self, squares: float) -> float:
        """Resistance of a number of squares of the reference copper."""
        return squares * self.milliohm_per_square


@dataclass(frozen=True, slots=True)
class Link:
    """A join between the layers at one cell, such as a via.

    Attributes:
        row: Row of the cell.
        col: Column of the cell.
        squares: Resistance from one layer to the next that has copper there.
    """

    row: int
    col: int
    squares: float


@dataclass(frozen=True, slots=True)
class Resistance:
    """The result for one piece of a current path.

    Attributes:
        squares: Squares of the reference copper between the two groups of
            pads; infinite when the copper does not join them.
        milliohm: The same as a resistance at the temperature of the model.
        copper_area: Area of the copper of the net in square millimeters,
            summed over the layers.
    """

    squares: float
    milliohm: float
    copper_area: float

    @property
    def connected(self) -> bool:
        """Whether the copper of the net joins the two groups of pads."""
        return math.isfinite(self.squares)


def net_resistance(
    board: Board,
    net: str,
    start: Sequence[str],
    goal: Sequence[str],
    model: CopperModel,
    grid: float = DEFAULT_GRID,
) -> Resistance:
    """Resistance of the copper of a net between two groups of pads.

    Args:
        board: The board.
        net: Name of the net whose copper carries the current.
        start: Names of the pads held at the first potential.
        goal: Names of the pads held at the second potential.
        model: The assumptions about the copper.
        grid: Cell size in millimeters.

    Raises:
        BoardError: If the board has no such net, a pad does not exist or is
            on another net, or the net has no copper on the layers of the
            model.
    """
    if not board.has_net(net):
        raise BoardError(f"the board has no net {net!r}")
    shapes, joins = _copper_by_layer(board, net, model)
    merged = {layer: unary_union(shapes[layer]) for layer in model.layers}
    bounds = [shape.bounds for shape in merged.values() if not shape.is_empty]
    if not bounds:
        raise BoardError(f"the net {net!r} has no copper on {', '.join(model.layers)}")
    window = Window.around(_enclosing(bounds), grid)
    masks = {layer: rasterize(window, shapes[layer]) for layer in model.layers}
    links = [Link(*window.cell(position), squares) for position, squares in joins]
    squares = solve_squares(
        masks,
        links,
        _pad_cells(board, net, start, window, model.layers),
        _pad_cells(board, net, goal, window, model.layers),
        model.layer_squares,
    )
    area = sum(float(shape.area) for shape in merged.values())
    return Resistance(squares, model.milliohm(squares), area)


def solve_squares(
    masks: Mapping[str, BoolGrid],
    links: Sequence[Link],
    source: Mapping[str, BoolGrid],
    sink: Mapping[str, BoolGrid],
    layer_squares: Mapping[str, float],
) -> float:
    """Squares between the source cells and the sink cells of a stack of sheets.

    Args:
        masks: The copper of each layer; the order of the mapping is the
            order of the stack.
        links: The joins between the layers.
        source: Cells of each layer held at the first potential.
        sink: Cells of each layer held at the second potential.
        layer_squares: Squares of the reference copper per square of each
            layer; a layer that is not listed counts 1.

    Returns:
        The resistance in squares, infinite when no copper joins the source
        to the sink.

    Raises:
        BoardError: If the source or the sink has no copper under it.
    """
    numbers, count = _number_cells(masks)
    matrix = _conductances(numbers, links, layer_squares, count)
    potential = np.full(count, np.nan)
    for layer, ids in numbers.items():
        potential[ids[source[layer] & masks[layer]]] = 1.0
        potential[ids[sink[layer] & masks[layer]]] = 0.0
    held = ~np.isnan(potential)
    at_source, at_sink = potential == 1.0, potential == 0.0
    if not at_source.any() or not at_sink.any():
        raise BoardError("a group of pads has no copper of the net on the grid")
    _, piece = connected_components(matrix, directed=False)
    if not np.isin(piece[at_source], piece[at_sink]).any():
        return math.inf
    # Copper that reaches neither group carries no current and would make
    # the system singular, so it is left out of the solution.
    free = ~held & np.isin(piece, piece[held])
    potential[~held] = 0.0
    if free.any():
        system = matrix[free][:, free]
        potential[free] = spsolve(system.tocsc(), -(matrix[free][:, held] @ potential[held]))
    current = float((matrix[at_source] @ potential).sum())
    return 1.0 / current


def _copper_by_layer(
    board: Board, net: str, model: CopperModel
) -> tuple[dict[str, list[BaseGeometry]], list[tuple[tuple[float, float], float]]]:
    """The shapes of a net on each layer of the model, and its layer joins."""
    shapes: dict[str, list[BaseGeometry]] = {layer: [] for layer in model.layers}
    joins: list[tuple[tuple[float, float], float]] = []
    for pad in board.pads:
        if pad.net != net:
            continue
        for layer in pad.layers:
            if layer in shapes:
                shapes[layer].append(pad_shape(pad))
        if pad.drill > 0:
            joins.append((pad.position, model.plated_hole_squares))
    for track in board.tracks:
        if track.net == net and track.layer in shapes:
            shapes[track.layer].append(track_shape(track))
    for via in board.vias:
        if via.net == net:
            for layer in model.layers:
                shapes[layer].append(via_shape(via))
            joins.append((via.position, model.squares_of_via(via.drill)))
    for fill in board.fills:
        if fill.net == net and fill.layer in shapes:
            shapes[fill.layer].extend(fill_shapes(fill))
    return shapes, joins


def _enclosing(bounds: Sequence[Bounds]) -> Bounds:
    return (
        min(box[0] for box in bounds),
        min(box[1] for box in bounds),
        max(box[2] for box in bounds),
        max(box[3] for box in bounds),
    )


def _pad_cells(
    board: Board, net: str, names: Sequence[str], window: Window, layers: Sequence[str]
) -> dict[str, BoolGrid]:
    """The cells under a group of pads, on each layer the pads have copper on."""
    cells = {layer: window.empty() for layer in layers}
    for name in names:
        for pad in board.pads_named(name, net):
            for layer in pad.layers:
                if layer in cells:
                    cells[layer] |= rasterize(window, [pad_shape(pad)])
    return cells


def _number_cells(masks: Mapping[str, BoolGrid]) -> tuple[dict[str, NDArray[np.int64]], int]:
    """Give every copper cell of every layer a number; -1 marks no copper."""
    numbers: dict[str, NDArray[np.int64]] = {}
    count = 0
    for layer, mask in masks.items():
        ids = np.full(mask.shape, -1, dtype=np.int64)
        cells = int(mask.sum())
        ids[mask] = np.arange(count, count + cells)
        numbers[layer] = ids
        count += cells
    return numbers, count


def _conductances(
    numbers: Mapping[str, NDArray[np.int64]],
    links: Sequence[Link],
    layer_squares: Mapping[str, float],
    count: int,
) -> sparse.csr_matrix:
    """The conductance matrix of the network of cells, in units of 1 / square."""
    first: list[NDArray[np.int64]] = []
    second: list[NDArray[np.int64]] = []
    values: list[NDArray[np.float64]] = []
    for layer, ids in numbers.items():
        conductance = 1.0 / layer_squares.get(layer, 1.0)
        for a, b in ((ids[:-1, :], ids[1:, :]), (ids[:, :-1], ids[:, 1:])):
            both = (a >= 0) & (b >= 0)
            first.append(a[both])
            second.append(b[both])
            values.append(np.full(int(both.sum()), conductance))
    for link in links:
        stack = [int(ids[link.row, link.col]) for ids in numbers.values()]
        through = [cell for cell in stack if cell >= 0]
        first.append(np.array(through[:-1], dtype=np.int64))
        second.append(np.array(through[1:], dtype=np.int64))
        values.append(np.full(max(len(through) - 1, 0), 1.0 / link.squares))
    a, b, g = np.concatenate(first), np.concatenate(second), np.concatenate(values)
    return sparse.csr_matrix(
        (
            np.concatenate([g, g, -g, -g]),
            (np.concatenate([a, b, a, b]), np.concatenate([a, b, b, a])),
        ),
        shape=(count, count),
    )
