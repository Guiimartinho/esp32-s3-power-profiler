"""The board as immutable value objects.

This is the whole of a board that the calculations see: nets with their
classes, pads with their outlines, tracks, vias and the filled polygons of
the copper zones. All coordinates are millimeters in the coordinates of the
board editor (x to the right, y downward). Nothing here knows how a board is
stored; :mod:`board_figures.loader` builds these objects from a dump.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property

from board_figures.errors import BoardError

Point = tuple[float, float]
"""A position in millimeters: x, then y."""

Ring = tuple[Point, ...]
"""The corners of a closed outline; the last corner joins the first."""

DEFAULT_NET_CLASS = "Default"
"""Net class of a net that the board does not list."""


@dataclass(frozen=True, slots=True)
class Polygon:
    """A filled area with holes."""

    outline: Ring
    holes: tuple[Ring, ...] = ()


@dataclass(frozen=True, slots=True)
class Net:
    """A net and the net class that the board assigns to it."""

    name: str
    net_class: str


@dataclass(frozen=True, slots=True)
class Footprint:
    """A part on the board: its reference and the position of its anchor."""

    ref: str
    position: Point


@dataclass(frozen=True, slots=True)
class Pad:
    """A pad of a footprint.

    Attributes:
        ref: Reference of the footprint, such as ``R110``.
        number: Pad number within the footprint, such as ``1`` or ``A3``.
        net: Name of the net, empty for a pad without one.
        position: Center of the pad.
        size: Width and height of the pad before rotation.
        layers: Copper layers the pad has copper on.
        drill: Diameter of the plated hole, zero for a surface pad.
        outline: The copper of the pad as a polygon, already rotated and
            placed. Empty when the dump could not produce it.
    """

    ref: str
    number: str
    net: str
    position: Point
    size: tuple[float, float]
    layers: tuple[str, ...]
    drill: float
    outline: Ring

    @property
    def name(self) -> str:
        """The pad as it is named on the command line, such as ``R110.1``."""
        return f"{self.ref}.{self.number}"


@dataclass(frozen=True, slots=True)
class Track:
    """A straight track segment with round ends."""

    net: str
    layer: str
    start: Point
    end: Point
    width: float

    @property
    def length(self) -> float:
        """Length of the center line."""
        return math.dist(self.start, self.end)


@dataclass(frozen=True, slots=True)
class Via:
    """A through via: it has its copper on every layer."""

    net: str
    position: Point
    diameter: float
    drill: float


@dataclass(frozen=True, slots=True)
class ZoneFill:
    """The filled copper of one zone on one layer.

    Attributes:
        net: Name of the net of the zone.
        layer: Copper layer of this fill.
        priority: Priority of the zone; where two zones overlap, the higher
            one owns the copper.
        polygons: The filled polygons as the board editor calculated them,
            with the clearances to other nets already cut out.
    """

    net: str
    layer: str
    priority: int
    polygons: tuple[Polygon, ...]


@dataclass(frozen=True)
class Board:
    """Everything of a board that the calculations use.

    The board keeps lookup tables that it builds on first use, which is why
    it is the one value object of the package without slots.
    """

    nets: tuple[Net, ...] = ()
    footprints: tuple[Footprint, ...] = ()
    pads: tuple[Pad, ...] = ()
    tracks: tuple[Track, ...] = ()
    vias: tuple[Via, ...] = ()
    fills: tuple[ZoneFill, ...] = ()

    @cached_property
    def _class_of(self) -> dict[str, str]:
        return {net.name: net.net_class for net in self.nets}

    @cached_property
    def _pads_by_name(self) -> dict[str, tuple[Pad, ...]]:
        found: dict[str, tuple[Pad, ...]] = {}
        for pad in self.pads:
            found[pad.name] = (*found.get(pad.name, ()), pad)
        return found

    def has_net(self, net: str) -> bool:
        """Whether the board lists a net of this name."""
        return net in self._class_of

    def net_class(self, net: str) -> str:
        """Net class of a net, :data:`DEFAULT_NET_CLASS` for an unlisted one."""
        return self._class_of.get(net, DEFAULT_NET_CLASS)

    def nets_of_classes(self, classes: frozenset[str]) -> tuple[str, ...]:
        """Names of the nets whose class is one of ``classes``, sorted."""
        return tuple(sorted(net.name for net in self.nets if net.net_class in classes))

    def pads_named(self, name: str, net: str) -> tuple[Pad, ...]:
        """The pads with a name, which all have to be on the given net.

        A footprint may repeat a pad number (the two legs of a terminal, for
        example), so the answer can hold more than one pad.

        Raises:
            BoardError: If no pad has the name, or one of them is on another net.
        """
        pads = self._pads_by_name.get(name, ())
        if not pads:
            raise BoardError(f"the board has no pad {name}")
        for pad in pads:
            if pad.net != net:
                raise BoardError(f"the pad {name} is on the net {pad.net!r}, not on {net!r}")
        return pads

    def via_count(self, net: str) -> int:
        """Number of vias of a net."""
        return sum(1 for via in self.vias if via.net == net)

    def track_layers(self, net: str) -> tuple[str, ...]:
        """Layers on which a net has tracks, sorted."""
        return tuple(sorted({track.layer for track in self.tracks if track.net == net}))
