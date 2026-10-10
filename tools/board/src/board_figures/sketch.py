"""Small boards built from a few rectangles.

A calculation is easiest to trust on a shape whose answer is known: a strip
of length L and width W has L / W squares. This module builds such boards in
a few lines, which is how the tests of the package check every calculation
against a hand calculation, without KiCad and without the real board.
:func:`to_dump` writes a board in the form of a dump, so that the same
boards can also go through the loader and the command line.
"""

from __future__ import annotations

from collections.abc import Mapping

from board_figures.model import (
    DEFAULT_NET_CLASS,
    Board,
    Footprint,
    Net,
    Pad,
    Point,
    Polygon,
    Ring,
    Track,
    Via,
    ZoneFill,
)
from board_figures.raster import Bounds

Item = Footprint | Pad | Track | Via | ZoneFill
"""Anything that :func:`board` accepts."""

TOP = "F.Cu"
"""The layer that an item goes on unless another is named."""


def rectangle(bounds: Bounds) -> Ring:
    """The four corners of a rectangle given as left, top, right, bottom."""
    left, top, right, bottom = bounds
    return ((left, top), (right, top), (right, bottom), (left, bottom))


def pad(
    name: str, net: str, bounds: Bounds, layers: tuple[str, ...] = (TOP,), drill: float = 0.0
) -> Pad:
    """A rectangular pad named ``REFERENCE.NUMBER``."""
    ref, number = name.split(".", 1)
    left, top, right, bottom = bounds
    return Pad(
        ref=ref,
        number=number,
        net=net,
        position=((left + right) / 2, (top + bottom) / 2),
        size=(right - left, bottom - top),
        layers=layers,
        drill=drill,
        outline=rectangle(bounds),
    )


def track(net: str, start: Point, end: Point, width: float, layer: str = TOP) -> Track:
    """A track segment."""
    return Track(net, layer, start, end, width)


def via(net: str, position: Point, diameter: float = 0.6, drill: float = 0.3) -> Via:
    """A through via."""
    return Via(net, position, diameter, drill)


def fill(
    net: str,
    bounds: Bounds,
    layer: str = TOP,
    priority: int = 0,
    holes: tuple[Bounds, ...] = (),
) -> ZoneFill:
    """A rectangular piece of filled copper, with rectangular holes."""
    polygon = Polygon(rectangle(bounds), tuple(rectangle(hole) for hole in holes))
    return ZoneFill(net, layer, priority, (polygon,))


def board(*items: Item, classes: Mapping[str, str] | None = None) -> Board:
    """A board made of the given items.

    Args:
        *items: Footprints, pads, tracks, vias and fills, in any order.
        classes: Net class by net name. A net that the items use and the
            mapping does not list gets the default net class.
    """
    named = dict(classes or {})
    for item in items:
        if not isinstance(item, Footprint) and item.net:
            named.setdefault(item.net, DEFAULT_NET_CLASS)
    return Board(
        nets=tuple(Net(name, net_class) for name, net_class in named.items()),
        footprints=tuple(item for item in items if isinstance(item, Footprint)),
        pads=tuple(item for item in items if isinstance(item, Pad)),
        tracks=tuple(item for item in items if isinstance(item, Track)),
        vias=tuple(item for item in items if isinstance(item, Via)),
        fills=tuple(item for item in items if isinstance(item, ZoneFill)),
    )


def to_dump(source: Board) -> dict[str, object]:
    """A board in the form of a dump, with the fields that the loader reads."""
    return {
        "nets": {net.name: {"class": net.net_class} for net in source.nets},
        "footprints": [
            {"ref": part.ref, "x": part.position[0], "y": part.position[1]}
            for part in source.footprints
        ],
        "pads": [
            {
                "ref": item.ref,
                "num": item.number,
                "net": item.net,
                "x": item.position[0],
                "y": item.position[1],
                "w": item.size[0],
                "h": item.size[1],
                "layers": list(item.layers),
                "drill": item.drill,
                "poly": _points(item.outline),
            }
            for item in source.pads
        ],
        "tracks": [
            {
                "net": item.net,
                "layer": item.layer,
                "x1": item.start[0],
                "y1": item.start[1],
                "x2": item.end[0],
                "y2": item.end[1],
                "w": item.width,
            }
            for item in source.tracks
        ],
        "vias": [
            {
                "net": item.net,
                "x": item.position[0],
                "y": item.position[1],
                "d": item.diameter,
                "drill": item.drill,
            }
            for item in source.vias
        ],
        "zones": [
            {
                "net": item.net,
                "rule_area": False,
                "priority": item.priority,
                "fills": {
                    item.layer: [
                        {
                            "outline": _points(polygon.outline),
                            "holes": [_points(hole) for hole in polygon.holes],
                        }
                        for polygon in item.polygons
                    ]
                },
            }
            for item in source.fills
        ],
    }


def _points(ring: Ring) -> list[list[float]]:
    return [[x, y] for x, y in ring]
