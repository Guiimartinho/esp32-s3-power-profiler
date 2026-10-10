"""Surface leakage into the measured node on one outer layer.

The instrument measures down to 100 nA, so a current that creeps over the
board surface into the measured node is an error of the measurement. This
module estimates it from the drawn copper, to compare one layout with
another.

The copper of the layer is laid on a raster and every cell gets one of four
roles:

- the measured node: every net of the node classes of the model;
- a follower: copper that is held at the potential of the node (a guard, a
  buffer output that drives it), which counts as part of the node for the
  potential and feeds no current into it;
- foreign: every other conductor;
- bare laminate.

The bare laminate within a reach of the node is solved as a resistive
sheet, with the node and its followers at 0 and the foreign copper at 1.
The current that enters the node is summed in squares: one square between
the node and a conductor is one sheet resistance. Each piece of current is
booked to the nearest foreign conductor and multiplied by the voltage
assumed for that conductor.

Solder mask, cleanliness and humidity are not modeled, and the sheet
resistance is an assumption. The figure compares layouts; it does not
predict a measurement, and nothing here is measured on hardware.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage, sparse
from scipy.sparse.linalg import cg
from shapely.geometry.base import BaseGeometry

from board_figures.geometry import fill_shapes, pad_shape, polygons_of, track_shape, via_shape
from board_figures.model import Board
from board_figures.raster import BoolGrid, Bounds, Window, cover

NO_NET = "(no net)"
"""Name under which the current to copper without a net is booked."""

_BARE, _NODE, _FOLLOWER, _UNNAMED = 0, 1, 2, 9
_FIRST_NET = 10  # labels from here on are foreign nets, in the order of their names
_NEIGHBORS = ((0, 1), (1, 0))  # right and down; each pair of cells is visited from both sides
_TOLERANCE = 1e-6
_MAX_ITERATIONS = 20000


@dataclass(frozen=True, slots=True)
class VoltageRule:
    """A voltage against the measured node for the nets that match.

    A net matches when its name starts with one of the prefixes, or holds
    one of the fragments, or its net class is one of the classes.

    Attributes:
        volts: Voltage assumed between a matching conductor and the node.
        name_prefixes: Beginnings of net names.
        name_contains: Fragments of net names.
        classes: Net classes.
    """

    volts: float
    name_prefixes: tuple[str, ...] = ()
    name_contains: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()

    def matches(self, net: str, net_class: str) -> bool:
        """Whether the rule applies to a net of the given class."""
        return (
            net.startswith(self.name_prefixes)
            or any(fragment in net for fragment in self.name_contains)
            or net_class in self.classes
        )


@dataclass(frozen=True, slots=True)
class LeakageModel:
    """The assumptions of the leakage calculation.

    Attributes:
        node_classes: Net classes whose nets make up the measured node.
        followers: Nets that follow the potential of the node.
        ohm_per_square: Sheet resistance assumed for the bare surface.
        default_volts: Voltage between the node and a conductor that no rule
            matches.
        rules: Voltages for particular conductors; the first rule that
            matches a net decides.
        can: Rectangle of the shield can. The current is reported apart for
            the part of the node inside it.
    """

    node_classes: frozenset[str]
    followers: frozenset[str]
    ohm_per_square: float
    default_volts: float
    rules: tuple[VoltageRule, ...]
    can: Bounds

    def volts(self, net: str, net_class: str) -> float:
        """Voltage assumed between a conductor and the measured node."""
        for rule in self.rules:
            if rule.matches(net, net_class):
                return rule.volts
        return self.default_volts

    def nanoamperes(self, squares: float, volts: float) -> float:
        """Current through a number of squares of bare surface at a voltage."""
        return squares * volts / self.ohm_per_square * 1e9


@dataclass(frozen=True, slots=True)
class LeakageArea:
    """Where and how finely the leakage is solved.

    Attributes:
        window: Rectangle of the board that holds the measured node.
        grid: Cell size in millimeters.
        reach: Distance from the node in millimeters up to which the bare
            surface is solved; a conductor farther away adds nothing that
            shows.
    """

    window: Bounds
    grid: float
    reach: float


@dataclass(frozen=True, slots=True)
class NetLeakage:
    """The current into the node that is booked to one foreign net."""

    net: str
    squares: float
    volts: float
    nanoamperes: float


@dataclass(frozen=True, slots=True)
class Leakage:
    """The result for one layer.

    Attributes:
        layer: The layer.
        cells: Number of bare cells that were solved.
        converged: Whether the iterative solver reached its tolerance.
        squares: Conductance into the node, as length over gap.
        nanoamperes: Current into the node.
        inside_can: The part of the current that enters the node inside the
            rectangle of the shield can.
        outside_can: The part that enters it outside.
        by_net: The current by foreign net, the largest first.
    """

    layer: str
    cells: int
    converged: bool
    squares: float
    nanoamperes: float
    inside_can: float
    outside_can: float
    by_net: tuple[NetLeakage, ...]


def surface_leakage(board: Board, layer: str, model: LeakageModel, area: LeakageArea) -> Leakage:
    """Leakage over the bare surface of a layer into the measured node."""
    window = Window.spanning(area.window, area.grid)
    names = sorted(net.name for net in board.nets)
    labels = label_copper(board, layer, model, window, names)
    volts = np.full(_FIRST_NET + len(names), model.default_volts)
    volts[_FIRST_NET:] = [model.volts(name, board.net_class(name)) for name in names]
    flow = solve_flow(labels, area.grid, area.reach)
    return _summarize(layer, flow, volts, names, model, window)


def label_copper(
    board: Board, layer: str, model: LeakageModel, window: Window, names: list[str]
) -> NDArray[np.int32]:
    """The role of every cell of a window on a layer.

    Returns:
        An array of labels: 0 for bare laminate, 1 for the measured node, 2
        for a follower, 9 for copper without a net, and 10 plus the index in
        ``names`` for every other net.
    """
    node = set(board.nets_of_classes(model.node_classes))
    index = {name: number + _FIRST_NET for number, name in enumerate(names)}

    def label(net: str) -> int:
        if net in node:
            return _NODE
        if net in model.followers:
            return _FOLLOWER
        return index.get(net, _UNNAMED)

    labels = np.zeros(window.shape, dtype=np.int32)
    # The fills go down first, the lowest priority first, and then the items
    # that lie in their clearance holes.
    for fill in sorted(board.fills, key=lambda fill: fill.priority):
        if fill.layer == layer:
            _paint(labels, window, fill_shapes(fill), label(fill.net))
    for pad in board.pads:
        if layer in pad.layers:
            _paint(labels, window, [pad_shape(pad)], label(pad.net))
    for track in board.tracks:
        if track.layer == layer:
            _paint(labels, window, [track_shape(track)], label(track.net))
    for via in board.vias:
        _paint(labels, window, [via_shape(via)], label(via.net))
    return labels


@dataclass(frozen=True, slots=True)
class Flow:
    """The solved surface: where current enters the node, and from whom.

    Attributes:
        rows: Row of each bare cell that touches the node, once per side
            that touches it.
        cols: Column of the same cells.
        squares: Conductance from that cell into the node, in squares.
        source: Label of the foreign conductor nearest to the cell.
        cells: Number of bare cells that were solved; zero when the raster
            holds no foreign conductor and nothing had to be solved.
        converged: Whether the iterative solver reached its tolerance.
    """

    rows: NDArray[np.int64]
    cols: NDArray[np.int64]
    squares: NDArray[np.float64]
    source: NDArray[np.int32]
    cells: int
    converged: bool


def solve_flow(labels: NDArray[np.int32], grid: float, reach: float) -> Flow:
    """Solve the bare surface of a labeled raster as a resistive sheet.

    Args:
        labels: The roles of the cells, as :func:`label_copper` gives them.
        grid: Cell size.
        reach: Distance from the node, in the unit of ``grid``, up to which
            the bare surface is solved.
    """
    node = labels == _NODE
    foreign = labels >= _UNNAMED
    from_node = np.asarray(ndimage.distance_transform_edt(~node), dtype=np.float64)
    domain = (labels == _BARE) & (from_node * grid <= reach)
    if not foreign.any():
        nothing = np.zeros(0, dtype=np.int64)
        return Flow(nothing, nothing, np.zeros(0), np.zeros(0, dtype=np.int32), 0, True)
    potential = np.zeros(labels.shape)
    solution, converged = _solve_sheet(domain, labels > _BARE, foreign)
    potential[domain] = solution
    _, (near_row, near_col) = ndimage.distance_transform_edt(~foreign, return_indices=True)
    nearest = labels[near_row, near_col]
    rows, cols, squares, source = [], [], [], []
    for here, there in _sides(labels.shape):
        edge = domain[here] & node[there]
        found_rows, found_cols = np.nonzero(edge)
        rows.append(found_rows + (here[0].start or 0))
        cols.append(found_cols + (here[1].start or 0))
        squares.append(potential[here][edge])
        source.append(nearest[here][edge])
    return Flow(
        np.concatenate(rows),
        np.concatenate(cols),
        np.concatenate(squares),
        np.concatenate(source),
        int(domain.sum()),
        converged,
    )


def _paint(
    labels: NDArray[np.int32], window: Window, shapes: Iterable[BaseGeometry], value: int
) -> None:
    """Lay shapes on the raster.

    Each polygon covers the cells of its own patch only, so the holes of a
    fill never erase copper that was laid before it, such as a guard pour
    inside a hole of the ground fill.
    """
    for shape in shapes:
        for polygon in polygons_of(shape):
            patch = cover(window, polygon)
            if patch is not None:
                labels[patch.rows, patch.cols][patch.cells] = value


def _sides(shape: tuple[int, ...]) -> list[tuple[tuple[slice, slice], tuple[slice, slice]]]:
    """Every cell paired with each of its four neighbors, as two views of an array."""
    rows, cols = shape
    pairs = []
    for down, right in _NEIGHBORS:
        first = (slice(0, rows - down), slice(0, cols - right))
        second = (slice(down, rows), slice(right, cols))
        pairs.extend([(first, second), (second, first)])
    return pairs


def _solve_sheet(
    domain: BoolGrid, conductor: BoolGrid, foreign: BoolGrid
) -> tuple[NDArray[np.float64], bool]:
    """Potential of the bare cells, with foreign copper at 1 and the rest at 0.

    The outer edge of the solved area carries no current: beyond the reach,
    the surface is left out.
    """
    count = int(domain.sum())
    number = np.full(domain.shape, -1, dtype=np.int64)
    number[domain] = np.arange(count)
    diagonal = np.zeros(count)
    drive = np.zeros(count)
    first: list[NDArray[np.int64]] = []
    second: list[NDArray[np.int64]] = []
    for here, there in _sides(domain.shape):
        both = domain[here] & domain[there]
        first.append(number[here][both])
        second.append(number[there][both])
        np.add.at(diagonal, number[here][both], 1)
        beside = domain[here] & conductor[there]
        np.add.at(diagonal, number[here][beside], 1)
        np.add.at(drive, number[here][beside], foreign[there][beside].astype(np.float64))
    diagonal[diagonal == 0] = 1
    a, b = np.concatenate(first), np.concatenate(second)
    cells = np.arange(count)
    matrix = sparse.csr_matrix(
        (
            np.concatenate([-np.ones(len(a)), diagonal]),
            (np.concatenate([a, cells]), np.concatenate([b, cells])),
        ),
        shape=(count, count),
    )
    scale = sparse.diags(1.0 / diagonal, format="csr")
    solution, status = cg(matrix, drive, M=scale, rtol=_TOLERANCE, maxiter=_MAX_ITERATIONS)
    return solution, status == 0


def _summarize(
    layer: str,
    flow: Flow,
    volts: NDArray[np.float64],
    names: list[str],
    model: LeakageModel,
    window: Window,
) -> Leakage:
    """Book the current by foreign net and by side of the shield can."""
    by_net = []
    for label in np.unique(flow.source):
        squares = float(flow.squares[flow.source == label].sum())
        name = names[label - _FIRST_NET] if label >= _FIRST_NET else NO_NET
        applied = float(volts[label])
        by_net.append(NetLeakage(name, squares, applied, model.nanoamperes(squares, applied)))
    by_net.sort(key=lambda entry: -entry.nanoamperes)
    x = window.x0 + flow.cols * window.grid
    y = window.y0 + flow.rows * window.grid
    inside = (x > model.can[0]) & (x < model.can[2]) & (y > model.can[1]) & (y < model.can[3])
    current = flow.squares * volts[flow.source] / model.ohm_per_square * 1e9
    return Leakage(
        layer=layer,
        cells=flow.cells,
        converged=flow.converged,
        squares=sum(entry.squares for entry in by_net),
        nanoamperes=sum(entry.nanoamperes for entry in by_net),
        inside_can=float(current[inside].sum()),
        outside_can=float(current[~inside].sum()),
        by_net=tuple(by_net),
    )
