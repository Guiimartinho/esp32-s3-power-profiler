"""The board-specific definition: what the figures are calculated for.

The calculations of the package know nothing of a particular board. Which
nets form the 1 A path, which pads the current enters and leaves, which
conductors are a pair, and every assumption behind a figure are read from a
TOML file, ``carrier.toml`` for the carrier board of this project. A change
of the board (a renamed net, a moved part) changes that file, not the code.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from board_figures._fields import Record
from board_figures.errors import DefinitionError
from board_figures.leakage import LeakageArea, LeakageModel, VoltageRule
from board_figures.pairs import Conductor
from board_figures.raster import Bounds
from board_figures.resistance import CopperModel

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - the standard library has no TOML reader before 3.11
    import tomli as tomllib


@dataclass(frozen=True, slots=True)
class PathPiece:
    """One piece of a current path: the copper of a net between two groups of pads.

    Attributes:
        label: What the piece is, for the report.
        net: Name of the net.
        start: Pads where the current enters the net.
        goal: Pads where it leaves.
    """

    label: str
    net: str
    start: tuple[str, ...]
    goal: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Pair:
    """Two conductors that should have the same length."""

    label: str
    first: Conductor
    second: Conductor


@dataclass(frozen=True, slots=True)
class HoleRule:
    """The keep-out around the mounting holes.

    Attributes:
        reference: Regular expression that the reference of a mounting hole
            matches as a whole.
        layers: Layers on which the keep-out applies.
        keepout: Smallest distance from the center of a hole to the copper
            of a track, in millimeters.
    """

    reference: str
    layers: tuple[str, ...]
    keepout: float


@dataclass(frozen=True, slots=True)
class CanRule:
    """The grounding of the lands of the shield can.

    Attributes:
        reference: Reference of the shield can.
        ground_net: Net that the lands are tied to.
        via_within: Largest distance in millimeters from a land to its
            nearest via of the ground net.
    """

    reference: str
    ground_net: str
    via_within: float


@dataclass(frozen=True, slots=True)
class Definition:
    """Everything the report of one board needs to know.

    Attributes:
        copper: The assumptions about the copper.
        path_grid: Cell size in millimeters for the resistance of the path.
        path_limit: Largest number of squares allowed for the path in a mode.
        modes: The pieces of the 1 A path by mode, in the order of the
            report.
        pairs: The Kelvin pairs.
        leakage: The assumptions of the surface leakage.
        leakage_area: Where and how finely the leakage is solved.
        leakage_layers: Layers the leakage is calculated on.
        sense_classes: Net classes whose nets should have no via.
        class_widths: Track width in millimeters that each net class asks for.
        default_width: Width for a net class that is not listed.
        holes: The keep-out around the mounting holes.
        can: The grounding of the shield can.
    """

    copper: CopperModel
    path_grid: float
    path_limit: float
    modes: Mapping[str, tuple[PathPiece, ...]]
    pairs: tuple[Pair, ...]
    leakage: LeakageModel
    leakage_area: LeakageArea
    leakage_layers: tuple[str, ...]
    sense_classes: frozenset[str]
    class_widths: Mapping[str, float]
    default_width: float
    holes: HoleRule
    can: CanRule

    def width_of(self, net_class: str) -> float:
        """Track width in millimeters that a net class asks for."""
        return self.class_widths.get(net_class, self.default_width)


_MODES = (("source mode", "source_mode"), ("ampere mode", "ampere_mode"))


def read_definition(path: Path) -> Definition:
    """Read a definition file.

    Raises:
        DefinitionError: If the file cannot be read, is not TOML, or misses
            a field or holds a value of the wrong kind.
    """
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise DefinitionError(f"cannot read the definition {path}: {error.strerror}") from error
    except ValueError as error:
        raise DefinitionError(f"the definition {path} is not valid TOML: {error}") from error
    return definition_from_dict(data)


def definition_from_dict(data: object) -> Definition:
    """Build the definition from the parsed TOML.

    Raises:
        DefinitionError: If a field is missing or holds a value of the wrong kind.
    """
    root = Record(data, "definition", DefinitionError)
    path = root.record("path")
    leakage = root.record("leakage")
    widths = root.record("track_width")
    holes = root.record("mounting_holes")
    can = root.record("shield_can")
    class_widths = widths.record("class_mm")
    return Definition(
        copper=_copper(root.record("copper")),
        path_grid=_positive(path, "grid_mm"),
        path_limit=_positive(path, "limit_squares"),
        modes=MappingProxyType(
            {name: tuple(_piece(entry) for entry in path.records(key)) for name, key in _MODES}
        ),
        pairs=tuple(_pair(entry) for entry in root.records("pair")),
        leakage=_leakage_model(leakage),
        leakage_area=LeakageArea(
            window=_bounds(leakage, "window"),
            grid=_positive(leakage, "grid_mm"),
            reach=_positive(leakage, "reach_mm"),
        ),
        leakage_layers=leakage.texts("layers"),
        sense_classes=frozenset(root.record("sense").texts("classes")),
        class_widths=MappingProxyType(
            {name: _positive(class_widths, name) for name in class_widths.names()}
        ),
        default_width=_positive(widths, "default_mm"),
        holes=HoleRule(
            _pattern(holes, "reference"), holes.texts("layers"), _positive(holes, "keepout_mm")
        ),
        can=CanRule(can.text("reference"), can.text("ground_net"), _positive(can, "via_within_mm")),
    )


def _copper(table: Record) -> CopperModel:
    layers = table.texts("layers")
    if not layers:
        raise DefinitionError(f"{table.where}: the field 'layers' names no layer")
    reference = _positive(table, "reference_thickness_um")
    thickness = table.record("thickness_um")
    return CopperModel(
        layers=layers,
        layer_squares=MappingProxyType(
            {layer: reference / _positive(thickness, layer) for layer in thickness.names()}
        ),
        milliohm_per_square=_positive(table, "milliohm_per_square"),
        temperature=table.number("temperature_c"),
        via_squares=_positive(table, "via_squares"),
        via_drill=_positive(table, "via_drill_mm"),
        plated_hole_squares=_positive(table, "plated_hole_squares"),
    )


def _piece(table: Record) -> PathPiece:
    return PathPiece(table.text("label"), table.text("net"), table.texts("from"), table.texts("to"))


def _pair(table: Record) -> Pair:
    return Pair(
        table.text("label"), _conductor(table.record("first")), _conductor(table.record("second"))
    )


def _conductor(table: Record) -> Conductor:
    return Conductor(table.text("net"), table.text("from"), table.text("to"))


def _leakage_model(table: Record) -> LeakageModel:
    voltage = table.record("voltage")
    return LeakageModel(
        node_classes=frozenset(table.texts("node_classes")),
        followers=frozenset(table.texts("followers")),
        ohm_per_square=_positive(table, "ohm_per_square"),
        default_volts=voltage.number("default"),
        rules=tuple(_voltage_rule(entry) for entry in voltage.records("rule")),
        can=_bounds(table, "can"),
    )


def _voltage_rule(table: Record) -> VoltageRule:
    def optional(key: str) -> tuple[str, ...]:
        return table.texts(key) if table.has(key) else ()

    rule = VoltageRule(
        table.number("volts"),
        optional("name_prefixes"),
        optional("name_contains"),
        optional("classes"),
    )
    if not (rule.name_prefixes or rule.name_contains or rule.classes):
        raise DefinitionError(f"{table.where}: the rule matches no net")
    return rule


def _positive(table: Record, key: str) -> float:
    value = table.number(key)
    if value <= 0:
        raise DefinitionError(f"{table.where}: the field '{key}' must be greater than zero")
    return value


def _bounds(table: Record, key: str) -> Bounds:
    left, top, right, bottom = table.numbers(key, count=4)
    if right <= left or bottom <= top:
        raise DefinitionError(
            f"{table.where}: the field '{key}' must be [left, top, right, bottom] "
            "with right beyond left and bottom beyond top"
        )
    return (left, top, right, bottom)


def _pattern(table: Record, key: str) -> str:
    text = table.text(key)
    try:
        re.compile(text)
    except re.error as error:
        raise DefinitionError(
            f"{table.where}: the field '{key}' is not a regular expression: {error}"
        ) from error
    return text
