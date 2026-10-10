"""The figures of a board definition put together.

:func:`build_report` runs every calculation that the definition of a board
asks for and returns the results as one value; :func:`format_report` turns
that value into the text that the command line prints. Both are pure: the
first takes a board and a definition, the second takes the report.

The sections follow the layout rules of section 10 of the specification:
the 1 A path in both modes, the Kelvin pairs, the vias of the sense nets,
the track widths against their net class, the copper around the mounting
holes, the ground vias at the lands of the shield can, and the surface
leakage into the measured node. Everything is calculated from the drawn
copper; nothing is measured on hardware.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from shapely.geometry import LineString
from shapely.geometry import Point as ShapelyPoint

from board_figures.definition import Definition, Pair, PathPiece
from board_figures.geometry import pad_shape
from board_figures.leakage import Leakage, surface_leakage
from board_figures.model import Board
from board_figures.pairs import PairLength, pair_length
from board_figures.resistance import net_resistance

_WIDTH_TOLERANCE = 1e-6  # a width stored as 0.2999999 mm is 0.3 mm


@dataclass(frozen=True, slots=True)
class PieceSquares:
    """One piece of a current path with its result.

    Attributes:
        piece: The piece as the definition names it.
        squares: Its resistance in squares, None when the copper of the net
            does not join its pads.
    """

    piece: PathPiece
    squares: float | None


@dataclass(frozen=True, slots=True)
class PathFigures:
    """The 1 A path in one mode.

    Attributes:
        mode: Name of the mode.
        pieces: The pieces in the order of the current.
        squares: Sum of the pieces that have a path.
        milliohm: The sum as a resistance.
    """

    mode: str
    pieces: tuple[PieceSquares, ...]
    squares: float
    milliohm: float

    @property
    def complete(self) -> bool:
        """Whether every piece has a path."""
        return all(entry.squares is not None for entry in self.pieces)


@dataclass(frozen=True, slots=True)
class PairFigures:
    """A Kelvin pair with the lengths of its conductors."""

    pair: Pair
    length: PairLength


@dataclass(frozen=True, slots=True)
class SenseNet:
    """A net that should have no via, with what it has."""

    net: str
    net_class: str
    vias: int
    track_layers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClassWidth:
    """The tracks of one net class against the width of the class.

    Attributes:
        net_class: Name of the net class.
        width: Width in millimeters that the class asks for.
        length: Length of all tracks of the class in millimeters.
        share: Percent of that length drawn at the class width or wider.
    """

    net_class: str
    width: float
    length: float
    share: float


@dataclass(frozen=True, slots=True)
class HoleIntrusion:
    """A track that comes too near to a mounting hole."""

    hole: str
    net: str
    layer: str
    distance: float


@dataclass(frozen=True, slots=True)
class CanLands:
    """The lands of the shield can and how many lack a ground via nearby."""

    lands: int
    without_via: int


@dataclass(frozen=True, slots=True)
class Report:
    """Every figure of a board definition.

    Attributes:
        path: The 1 A path by mode; empty when the path was left out.
        pairs: The Kelvin pairs.
        sense_nets: The nets that should have no via.
        widths: The track widths by net class.
        holes: Number of mounting holes.
        intrusions: Tracks inside the keep-out of a mounting hole.
        can: The lands of the shield can.
        leakage: The surface leakage by layer; empty when it was left out.
    """

    path: tuple[PathFigures, ...]
    pairs: tuple[PairFigures, ...]
    sense_nets: tuple[SenseNet, ...]
    widths: tuple[ClassWidth, ...]
    holes: int
    intrusions: tuple[HoleIntrusion, ...]
    can: CanLands
    leakage: tuple[Leakage, ...]


def build_report(
    board: Board, definition: Definition, *, with_path: bool = True, with_leakage: bool = True
) -> Report:
    """Calculate every figure that a definition asks of a board.

    Args:
        board: The board.
        definition: What to calculate, and under which assumptions.
        with_path: Whether to solve the 1 A path, which takes the longest
            after the leakage.
        with_leakage: Whether to solve the surface leakage.

    Raises:
        BoardError: If the definition names a pad that the board does not
            have, or a pad on another net.
    """
    holes, intrusions = hole_intrusions(board, definition)
    return Report(
        path=path_figures(board, definition) if with_path else (),
        pairs=tuple(
            PairFigures(pair, pair_length(board, pair.first, pair.second))
            for pair in definition.pairs
        ),
        sense_nets=sense_nets(board, definition),
        widths=class_widths(board, definition),
        holes=holes,
        intrusions=intrusions,
        can=can_lands(board, definition),
        leakage=tuple(
            surface_leakage(board, layer, definition.leakage, definition.leakage_area)
            for layer in (definition.leakage_layers if with_leakage else ())
        ),
    )


def path_figures(board: Board, definition: Definition) -> tuple[PathFigures, ...]:
    """The 1 A path in every mode of the definition.

    A piece that two modes share is solved once. The sum of a mode adds
    its pieces as they were solved; a figure is rounded only where it is
    printed.
    """
    solved: dict[PathPiece, float | None] = {}
    figures = []
    for mode, pieces in definition.modes.items():
        for piece in pieces:
            if piece not in solved:
                solved[piece] = _piece_squares(board, piece, definition)
        results = tuple(PieceSquares(piece, solved[piece]) for piece in pieces)
        total = sum(entry.squares for entry in results if entry.squares is not None)
        figures.append(PathFigures(mode, results, total, definition.copper.milliohm(total)))
    return tuple(figures)


def sense_nets(board: Board, definition: Definition) -> tuple[SenseNet, ...]:
    """The nets of the sense classes with their vias and track layers."""
    return tuple(
        SenseNet(net, board.net_class(net), board.via_count(net), board.track_layers(net))
        for net in board.nets_of_classes(definition.sense_classes)
    )


def class_widths(board: Board, definition: Definition) -> tuple[ClassWidth, ...]:
    """For each net class, the share of its track length at the class width or wider."""
    length: defaultdict[str, float] = defaultdict(float)
    wide: defaultdict[str, float] = defaultdict(float)
    for track in board.tracks:
        net_class = board.net_class(track.net)
        length[net_class] += track.length
        if track.width + _WIDTH_TOLERANCE >= definition.width_of(net_class):
            wide[net_class] += track.length
    return tuple(
        ClassWidth(
            net_class,
            definition.width_of(net_class),
            length[net_class],
            100.0 * wide[net_class] / length[net_class] if length[net_class] else 100.0,
        )
        for net_class in sorted(length)
    )


def hole_intrusions(board: Board, definition: Definition) -> tuple[int, tuple[HoleIntrusion, ...]]:
    """The number of mounting holes, and the tracks inside their keep-out."""
    rule = definition.holes
    holes = [part for part in board.footprints if re.fullmatch(rule.reference, part.ref)]
    found = []
    for hole in holes:
        center = ShapelyPoint(hole.position)
        for track in board.tracks:
            if track.layer not in rule.layers:
                continue
            line = LineString([track.start, track.end])
            distance = float(line.distance(center)) - track.width / 2
            if distance < rule.keepout:
                found.append(HoleIntrusion(hole.ref, track.net, track.layer, distance))
    return len(holes), tuple(found)


def can_lands(board: Board, definition: Definition) -> CanLands:
    """The lands of the shield can, and how many have no ground via nearby."""
    rule = definition.can
    lands = [pad for pad in board.pads if pad.ref == rule.reference]
    vias = [ShapelyPoint(via.position) for via in board.vias if via.net == rule.ground_net]
    without = sum(
        1
        for land in lands
        if not any(pad_shape(land).distance(via) <= rule.via_within for via in vias)
    )
    return CanLands(len(lands), without)


def format_report(report: Report, definition: Definition) -> str:
    """The report as the text that the command line prints."""
    lines = ["Figures of the board, calculated from the drawn copper. Nothing is measured."]
    if report.path:
        lines.append(f"The 1 A path (limit: {definition.path_limit:g} squares in either mode)")
        for figures in report.path:
            lines.extend(_format_path(figures, definition))
    lines.append("Kelvin pairs (track center lines, pad edge to pad edge)")
    lines.extend(_format_pair(entry) for entry in report.pairs)
    without = sum(1 for net in report.sense_nets if net.vias == 0)
    lines.append(f"Sense and guarded nets: {without} of {len(report.sense_nets)} without a via")
    lines.extend(
        f"   {net.net:26s} {net.net_class:8s} vias {net.vias}  "
        f"tracks on {', '.join(net.track_layers) or 'none'}"
        for net in report.sense_nets
    )
    lines.append("Track widths (share of the track length at the class width or wider)")
    lines.extend(
        f"   {entry.net_class:11s} {entry.width:4.2f} mm: {entry.length:8.1f} mm of tracks, "
        f"{entry.share:5.1f} % at that width or wider"
        for entry in report.widths
    )
    lines.extend(_format_mechanics(report, definition))
    for leakage in report.leakage:
        lines.extend(format_leakage(leakage, definition))
    return "\n".join(lines)


def format_leakage(leakage: Leakage, definition: Definition, top: int = 12) -> list[str]:
    """The leakage of one layer as lines of text, with the largest sources."""
    area = definition.leakage_area
    lines = [
        f"Surface leakage on {leakage.layer} (raster {area.grid:g} mm, "
        f"reach {area.reach:g} mm, {leakage.cells} cells"
        + ("" if leakage.converged else ", the solver did NOT converge")
        + ")",
        f"   into the measured node: {leakage.nanoamperes:.2f} nA "
        f"({leakage.squares:.1f} squares of length over gap), "
        f"{leakage.inside_can:.2f} nA inside the can, {leakage.outside_can:.2f} nA outside "
        f"(calculated, {definition.leakage.ohm_per_square:.0e} ohm per square)",
    ]
    lines.extend(
        f"   {entry.nanoamperes:6.2f} nA  {entry.squares:7.1f} squares  "
        f"{entry.volts:.0f} V  {entry.net}"
        for entry in leakage.by_net[:top]
    )
    return lines


def _piece_squares(board: Board, piece: PathPiece, definition: Definition) -> float | None:
    result = net_resistance(
        board, piece.net, piece.start, piece.goal, definition.copper, definition.path_grid
    )
    return result.squares if result.connected else None


def _format_path(figures: PathFigures, definition: Definition) -> list[str]:
    verdict = "" if figures.complete else " (a piece has no path!)"
    lines = [
        f"   {figures.mode}: {figures.squares:.1f} squares = {figures.milliohm:.1f} mOhm "
        f"at {definition.copper.temperature:g} C{verdict}"
    ]
    lines.extend(
        f"      {entry.piece.label:32s} {entry.piece.net:28s} "
        + ("no path" if entry.squares is None else f"{entry.squares:6.1f}")
        for entry in figures.pieces
    )
    return lines


def _format_pair(entry: PairFigures) -> str:
    length = entry.length
    if length.first is None or length.second is None:
        return f"   {entry.pair.label}: the tracks do not join the pads of a conductor"
    return (
        f"   {entry.pair.label}: {length.first:.2f} / {length.second:.2f} mm, "
        f"difference {abs(length.first - length.second):.2f} mm"
    )


def _format_mechanics(report: Report, definition: Definition) -> list[str]:
    near = sorted({f"{entry.hole}:{entry.net}@{entry.distance:.2f}" for entry in report.intrusions})
    return [
        f"Mounting holes: {report.holes} holes; tracks nearer than "
        f"{definition.holes.keepout:g} mm to a center: {len(report.intrusions)}"
        + (" -> " + ", ".join(near) if near else ""),
        f"Shield can: {report.can.lands} lands, {report.can.lands - report.can.without_via} "
        f"with a ground via within {definition.can.via_within:g} mm, "
        f"{report.can.without_via} without",
    ]
