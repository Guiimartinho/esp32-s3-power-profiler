from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import Point, Polygon, box

from board_figures.raster import Window, cover, rasterize


def cells(window: Window, shape: Polygon) -> set[tuple[int, int]]:
    return {(int(row), int(col)) for row, col in np.argwhere(rasterize(window, [shape]))}


def test_a_window_around_copper_keeps_free_cells_on_every_side() -> None:
    window = Window.around((10.0, 20.0, 14.0, 21.0), 0.5)

    assert (window.x0, window.y0) == (9.0, 19.0)
    assert window.shape == (8, 14)
    assert window.sample == 0.5
    mask = rasterize(window, [box(10.0, 20.0, 14.0, 21.0)])
    assert not mask[0].any()
    assert not mask[-1].any()
    assert not mask[:, 0].any()
    assert not mask[:, -1].any()


def test_a_window_spanning_a_rectangle_covers_exactly_that() -> None:
    window = Window.spanning((136.0, 84.0, 200.0, 134.0), 0.04)

    assert window.shape == (1250, 1600)
    assert window.sample == 0.0
    assert window.bounds == pytest.approx((136.0, 84.0, 200.0, 134.0))


def test_cells_and_positions() -> None:
    window = Window(x0=10.0, y0=20.0, grid=0.5, rows=4, cols=6)

    assert window.cell((10.6, 21.9)) == (3, 1)
    assert window.position(3, 1) == (10.75, 21.75)
    assert Window(10.0, 20.0, 0.5, 4, 6, sample=0.0).position(3, 1) == (10.5, 21.5)
    assert window.empty().shape == (4, 6)
    assert not window.empty().any()


def test_a_rectangle_covers_the_cells_from_corner_to_corner() -> None:
    window = Window(0.0, 0.0, 1.0, rows=10, cols=10, sample=0.0)

    # Corners at 2..5 and 3..4: the outline is filled with its boundary.
    assert cells(window, box(2.0, 3.0, 5.0, 4.0)) == {
        (row, col) for row in (3, 4) for col in (2, 3, 4, 5)
    }


def test_a_corner_moves_to_the_sample_point_at_or_before_it() -> None:
    corner = Window(0.0, 0.0, 1.0, rows=10, cols=10, sample=0.0)
    center = Window(0.0, 0.0, 1.0, rows=10, cols=10, sample=0.5)
    shape = box(2.9, 3.9, 5.1, 4.1)

    assert cells(corner, shape) == {(row, col) for row in (3, 4) for col in (2, 3, 4, 5)}
    # Cell centers lie at 0.5, 1.5, ...: 2.9 moves to 2.5, 5.1 to 4.5.
    assert cells(center, shape) == {(row, col) for row in (3,) for col in (2, 3, 4)}


def test_a_triangle_is_filled_with_its_boundary() -> None:
    window = Window(0.0, 0.0, 1.0, rows=6, cols=6, sample=0.0)

    assert cells(window, Polygon([(0, 0), (4, 0), (0, 4)])) == {
        (row, col) for row in range(5) for col in range(5 - row)
    }


def test_a_sliver_between_two_sample_points_still_covers_cells() -> None:
    window = Window(0.0, 0.0, 1.0, rows=6, cols=6, sample=0.0)

    assert cells(window, box(1.2, 1.2, 1.8, 3.9)) == {(1, 1), (2, 1), (3, 1)}


def test_a_circle_covers_about_its_area() -> None:
    window = Window(0.0, 0.0, 0.1, rows=100, cols=100)

    mask = rasterize(window, [Point(5.0, 5.0).buffer(3.0)])

    # The rule draws copper wider than it is, by up to one cell.
    assert np.pi * 3.0**2 < mask.sum() * 0.01 < np.pi * 3.05**2


def test_a_shape_outside_the_window_covers_nothing() -> None:
    window = Window(0.0, 0.0, 1.0, rows=5, cols=5)

    assert cover(window, box(10.0, 10.0, 12.0, 12.0)) is None
    assert cover(window, box(-9.0, 1.0, -7.0, 2.0)) is None
    assert cover(window, Polygon()) is None
    assert not rasterize(window, [box(10.0, 10.0, 12.0, 12.0)]).any()


def test_a_shape_across_the_edge_is_cut_at_the_window() -> None:
    window = Window(0.0, 0.0, 1.0, rows=4, cols=4, sample=0.0)

    assert cells(window, box(-5.0, 1.0, 1.0, 20.0)) == {
        (row, col) for row in (1, 2, 3) for col in (0, 1)
    }


def test_a_slanted_edge_across_the_window_is_cut_too() -> None:
    window = Window(0.0, 0.0, 1.0, rows=4, cols=4, sample=0.0)

    mask = rasterize(window, [Polygon([(-4, -4), (8, -4), (8, 8)])])

    # The edge from (-4, -4) to (8, 8) is the diagonal; everything on it
    # and to its right is covered.
    assert mask.tolist() == np.triu(np.ones((4, 4), dtype=bool)).tolist()


def test_a_patch_spans_only_the_cells_around_its_polygon() -> None:
    window = Window(0.0, 0.0, 1.0, rows=50, cols=50, sample=0.0)

    patch = cover(window, box(10.0, 20.0, 12.0, 21.0))

    assert patch is not None
    assert (patch.rows, patch.cols) == (slice(20, 22), slice(10, 13))
    assert patch.cells.all()


def test_a_hole_is_cut_out_with_its_boundary() -> None:
    window = Window(0.0, 0.0, 1.0, rows=12, cols=12, sample=0.0)
    ring = Polygon(box(1, 1, 10, 10).exterior.coords, [box(4, 4, 7, 7).exterior.coords])

    mask = rasterize(window, [ring])

    assert mask[1:11, 1:11].sum() == 100 - 16
    assert not mask[4:8, 4:8].any()


def test_the_hole_of_one_shape_does_not_erase_another_shape() -> None:
    window = Window(0.0, 0.0, 1.0, rows=12, cols=12, sample=0.0)
    ring = Polygon(box(1, 1, 10, 10).exterior.coords, [box(4, 4, 7, 7).exterior.coords])
    island = box(5.0, 5.0, 6.0, 6.0)

    for order in ([island, ring], [ring, island]):
        assert rasterize(window, order)[5:7, 5:7].all()
