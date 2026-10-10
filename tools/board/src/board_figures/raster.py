"""Shapes laid on a grid of square cells.

Every calculation of the package that solves a potential works on a raster:
a rectangle of the board cut into square cells, each of which is copper or
not. This module holds the rectangle (:class:`Window`) and the rule that
decides which cells a polygon covers.

The rule is the one of the raster that the figures in the documents of the
board were calculated with, kept so that the figures stay comparable:

1. Every corner of the polygon moves to the sample point of a cell, the one
   at or before it on both axes.
2. The moved outline is filled including its boundary, and each filled run
   of a row is rounded to whole cells.

The rule draws copper wider than it is, by up to one cell, so a conductor
reads slightly lower in resistance than the drawing. The distance between
two conductors comes out right to one cell, either way. Both errors shrink
with the cell size.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from board_figures.geometry import polygons_of
from board_figures.model import Point

BoolGrid = NDArray[np.bool_]
"""One truth value per cell of a window: rows downward, columns to the right."""

Bounds = tuple[float, float, float, float]
"""A rectangle on the board: left, top, right, bottom."""

_MARGIN_CELLS = 2  # free cells kept around the copper by Window.around


@dataclass(frozen=True, slots=True)
class Window:
    """A rectangle of the board cut into square cells.

    Attributes:
        x0: Left edge.
        y0: Top edge.
        grid: Side of a cell.
        rows: Number of cells downward.
        cols: Number of cells to the right.
        sample: Where in a cell its sample point lies, as a fraction of the
            cell from its top left corner: 0.5 for the center, 0.0 for the
            corner.
    """

    x0: float
    y0: float
    grid: float
    rows: int
    cols: int
    sample: float = 0.5

    @classmethod
    def around(cls, bounds: Bounds, grid: float) -> Window:
        """A window around a piece of copper, with free cells on every side."""
        x0 = bounds[0] - _MARGIN_CELLS * grid
        y0 = bounds[1] - _MARGIN_CELLS * grid
        rows = int((bounds[3] - y0) / grid) + 2 * _MARGIN_CELLS
        cols = int((bounds[2] - x0) / grid) + 2 * _MARGIN_CELLS
        return cls(x0, y0, grid, rows, cols)

    @classmethod
    def spanning(cls, bounds: Bounds, grid: float) -> Window:
        """A window over exactly a rectangle, sampled at the cell corners."""
        rows = round((bounds[3] - bounds[1]) / grid)
        cols = round((bounds[2] - bounds[0]) / grid)
        return cls(bounds[0], bounds[1], grid, rows, cols, sample=0.0)

    @property
    def shape(self) -> tuple[int, int]:
        """Rows and columns, as the shape of an array over the window."""
        return (self.rows, self.cols)

    @property
    def bounds(self) -> Bounds:
        """The rectangle that the cells cover."""
        return (self.x0, self.y0, self.x0 + self.cols * self.grid, self.y0 + self.rows * self.grid)

    def empty(self) -> BoolGrid:
        """An array over the window with no cell set."""
        return np.zeros(self.shape, dtype=np.bool_)

    def cell(self, point: Point) -> tuple[int, int]:
        """Row and column of the cell that holds a point."""
        return (int((point[1] - self.y0) / self.grid), int((point[0] - self.x0) / self.grid))

    def position(self, row: int, col: int) -> Point:
        """The sample point of a cell."""
        return (
            self.x0 + (col + self.sample) * self.grid,
            self.y0 + (row + self.sample) * self.grid,
        )


@dataclass(frozen=True, slots=True)
class Patch:
    """The cells of a window that one polygon covers.

    Attributes:
        rows: The rows of the window that the patch spans.
        cols: The columns of the window that the patch spans.
        cells: The covered cells within that span.
    """

    rows: slice
    cols: slice
    cells: BoolGrid


def cover(window: Window, polygon: Polygon) -> Patch | None:
    """The cells of a window that a polygon covers, or None if it lies outside.

    The holes of the polygon are cut out of the patch only: laying the patch
    over copper that is already on a raster keeps what lies in the holes.
    """
    if polygon.is_empty or not _overlap(polygon.bounds, window.bounds):
        return None
    xs, ys = _corner_cells(window, polygon.exterior.coords)
    row0, row1 = max(int(ys.min()), 0), min(int(ys.max()) + 1, window.rows)
    col0, col1 = max(int(xs.min()), 0), min(int(xs.max()) + 1, window.cols)
    shape = (row1 - row0, col1 - col0)
    cells = _filled(shape, xs - col0, ys - row0)
    for ring in polygon.interiors:
        hole_xs, hole_ys = _corner_cells(window, ring.coords)
        cells &= ~_filled(shape, hole_xs - col0, hole_ys - row0)
    return Patch(slice(row0, row1), slice(col0, col1), cells)


def rasterize(window: Window, shapes: Iterable[BaseGeometry]) -> BoolGrid:
    """The cells of a window covered by any of the shapes."""
    result = window.empty()
    for shape in shapes:
        for polygon in polygons_of(shape):
            patch = cover(window, polygon)
            if patch is not None:
                result[patch.rows, patch.cols] |= patch.cells
    return result


def _overlap(first: Bounds, second: Bounds) -> bool:
    return (
        first[0] <= second[2]
        and second[0] <= first[2]
        and first[1] <= second[3]
        and second[1] <= first[3]
    )


def _corner_cells(
    window: Window, coords: Iterable[tuple[float, ...]]
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Step 1 of the rule: the cells whose sample points the corners move to."""
    points = np.asarray(list(coords), dtype=np.float64)
    xs = np.trunc((points[:, 0] - window.x0) / window.grid - window.sample)
    ys = np.trunc((points[:, 1] - window.y0) / window.grid - window.sample)
    return xs.astype(np.int64), ys.astype(np.int64)


def _filled(shape: tuple[int, int], xs: NDArray[np.int64], ys: NDArray[np.int64]) -> BoolGrid:
    """Step 2 of the rule: fill a closed outline whose corners are cells.

    The filled runs of a row are found twice, once as the outline is cut
    just below the row and once just above it, and joined with the edges
    that lie along the row. Together they are the cut through the outline
    with its boundary included.
    """
    rows, cols = shape
    changes = np.zeros((rows, cols + 1), dtype=np.int32)
    next_xs, next_ys = np.roll(xs, -1), np.roll(ys, -1)
    level = ys == next_ys
    _add_runs(changes, ys[level], np.minimum(xs, next_xs)[level], np.maximum(xs, next_xs)[level])
    xa, ya, xb, yb = xs[~level], ys[~level], next_xs[~level], next_ys[~level]
    if len(xa):
        top = np.minimum(ya, yb)
        height = np.abs(yb - ya)
        # Single precision keeps a run that ends exactly between two cells on
        # the side that the reference raster puts it.
        slope = (xb - xa).astype(np.float32) / (yb - ya).astype(np.float32)
        edge = np.repeat(np.arange(len(xa)), height)
        step = np.arange(int(height.sum())) - np.repeat(np.cumsum(height) - height, height)
        for side in (0, 1):
            row = top[edge] + step + side
            x = (row - ya[edge]).astype(np.float32) * slope[edge] + xa[edge].astype(np.float32)
            order = np.lexsort((x, row))
            row, crossing = row[order], x[order].astype(np.float64)
            _add_runs(
                changes,
                row[0::2],
                np.floor(crossing[0::2] + 0.5).astype(np.int64),
                np.ceil(crossing[1::2] - 0.5).astype(np.int64),
            )
    filled: BoolGrid = np.cumsum(changes, axis=1)[:, :cols] > 0
    return filled


def _add_runs(
    changes: NDArray[np.int32],
    row: NDArray[np.int64],
    first: NDArray[np.int64],
    last: NDArray[np.int64],
) -> None:
    """Book runs of cells, each from ``first`` to ``last`` inclusive in its row."""
    rows, cols = changes.shape[0], changes.shape[1] - 1
    keep = (row >= 0) & (row < rows) & (last >= first) & (last >= 0) & (first < cols)
    np.add.at(changes, (row[keep], np.clip(first[keep], 0, cols)), 1)
    np.add.at(changes, (row[keep], np.clip(last[keep] + 1, 0, cols)), -1)
