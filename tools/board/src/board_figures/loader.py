"""Build the board model from a dump.

The dump is the JSON file that the adapter ``kicad/dump_board.py`` writes
under the Python of KiCad. :func:`board_from_dict` turns the parsed JSON into
the immutable model and checks every field it reads on the way, so that a
dump of another version or a damaged file is reported with the place of the
problem. :func:`read_board` is the thin file adapter in front of it.

Fields of the dump that no calculation uses (courtyards, drawings, the
position of the reference texts) are not read.
"""

from __future__ import annotations

import json
from pathlib import Path

from board_figures._fields import Record
from board_figures.errors import DumpError
from board_figures.model import (
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

_MIN_CORNERS = 3  # fewer corners do not enclose an area


def read_board(path: Path) -> Board:
    """Read a dump file and build the board from it.

    Raises:
        DumpError: If the file cannot be read, is not JSON, or does not have
            the form of a dump.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise DumpError(f"cannot read the dump {path}: {error.strerror}") from error
    except ValueError as error:
        raise DumpError(f"the dump {path} is not valid JSON: {error}") from error
    return board_from_dict(data)


def board_from_dict(data: object) -> Board:
    """Build the board from the parsed JSON of a dump.

    Raises:
        DumpError: If a field is missing or holds a value of the wrong kind.
    """
    dump = Record(data, "dump", DumpError)
    nets = dump.record("nets")
    return Board(
        nets=tuple(Net(name, nets.record(name).text("class")) for name in nets.names()),
        footprints=tuple(
            Footprint(entry.text("ref"), (entry.number("x"), entry.number("y")))
            for entry in dump.records("footprints")
        ),
        pads=tuple(_pad(entry) for entry in dump.records("pads")),
        tracks=tuple(_track(entry) for entry in dump.records("tracks")),
        vias=tuple(_via(entry) for entry in dump.records("vias")),
        fills=tuple(fill for zone in dump.records("zones") for fill in _fills(zone)),
    )


def _pad(entry: Record) -> Pad:
    outline = _ring(entry.items("poly"), f"{entry.where}.poly")
    return Pad(
        ref=entry.text("ref"),
        number=entry.text("num"),
        net=entry.text("net"),
        position=(entry.number("x"), entry.number("y")),
        size=(entry.number("w"), entry.number("h")),
        layers=entry.texts("layers"),
        drill=entry.number("drill"),
        outline=outline if len(outline) >= _MIN_CORNERS else (),
    )


def _track(entry: Record) -> Track:
    return Track(
        net=entry.text("net"),
        layer=entry.text("layer"),
        start=(entry.number("x1"), entry.number("y1")),
        end=(entry.number("x2"), entry.number("y2")),
        width=entry.number("w"),
    )


def _via(entry: Record) -> Via:
    return Via(
        net=entry.text("net"),
        position=(entry.number("x"), entry.number("y")),
        diameter=entry.number("d"),
        drill=entry.number("drill"),
    )


def _fills(zone: Record) -> list[ZoneFill]:
    """The fills of one zone, one per layer. A rule area has no copper."""
    if zone.flag("rule_area"):
        return []
    net = zone.text("net")
    priority = zone.integer("priority") if zone.has("priority") else 0
    fills = zone.record("fills")
    return [
        ZoneFill(net, layer, priority, _polygons(fills.records(layer))) for layer in fills.names()
    ]


def _polygons(entries: tuple[Record, ...]) -> tuple[Polygon, ...]:
    polygons = []
    for entry in entries:
        outline = _ring(entry.items("outline"), f"{entry.where}.outline")
        if len(outline) < _MIN_CORNERS:
            continue
        holes = (
            _ring(hole, f"{entry.where}.holes[{index}]")
            for index, hole in enumerate(entry.items("holes"))
        )
        polygons.append(
            Polygon(outline, tuple(hole for hole in holes if len(hole) >= _MIN_CORNERS))
        )
    return tuple(polygons)


def _ring(value: object, where: str) -> Ring:
    if not isinstance(value, (list, tuple)):
        raise DumpError(f"{where}: expected a list of points, found {type(value).__name__}")
    return tuple(_point(point, where) for point in value)


def _point(value: object, where: str) -> Point:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        x, y = value
        if _is_number(x) and _is_number(y):
            return (float(x), float(y))
    raise DumpError(f"{where}: a point must be a pair of numbers, found {value!r}")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
