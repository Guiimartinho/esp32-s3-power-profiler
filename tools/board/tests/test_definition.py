from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from board_figures.definition import (
    PathPiece,
    definition_from_dict,
    read_definition,
)
from board_figures.errors import DefinitionError
from board_figures.pairs import Conductor

CARRIER = Path(__file__).resolve().parents[1] / "carrier.toml"


def test_the_definition_of_the_carrier_board_loads() -> None:
    definition = read_definition(CARRIER)

    assert list(definition.modes) == ["source mode", "ampere mode"]
    assert [len(pieces) for pieces in definition.modes.values()] == [7, 8]
    assert definition.modes["source mode"][0] == PathPiece(
        "regulator output",
        "/Path Switching/LDO_OUT",
        ("U18.1", "U18.2", "U18.3", "U18.9"),
        ("Q4.5",),
    )
    # Both modes end with the same four pieces, from the range 3 transistor on.
    assert definition.modes["source mode"][3:] == definition.modes["ampere mode"][4:]
    assert definition.path_grid == 0.1
    assert definition.path_limit == 30.0
    assert len(definition.pairs) == 3
    assert definition.pairs[2].second == Conductor("/Shunt Ladder/INN", "U24.9", "U27.1")


def test_the_copper_of_the_carrier_board() -> None:
    copper = read_definition(CARRIER).copper

    assert copper.layers == ("F.Cu", "In2.Cu", "B.Cu")
    assert dict(copper.layer_squares) == {"F.Cu": 1.0, "In1.Cu": 2.0, "In2.Cu": 2.0, "B.Cu": 1.0}
    assert copper.milliohm_per_square == 0.531
    assert copper.temperature == 40.0
    assert copper.squares_of_via(0.4) == pytest.approx(1.7)
    assert copper.plated_hole_squares == 0.5


def test_the_leakage_assumptions_of_the_carrier_board() -> None:
    definition = read_definition(CARRIER)
    leakage = definition.leakage

    assert leakage.node_classes == {"Sense", "Guarded", "Node1A"}
    assert len(leakage.followers) == 5
    assert "/Path Switching/SUPPLY" in leakage.followers
    assert leakage.ohm_per_square == 1e11
    assert leakage.can == (122.75, 87.45, 167.55, 118.75)
    assert leakage.volts("GND", "Default") == 5.0
    assert leakage.volts("+12V_A", "Supply") == 7.0
    assert leakage.volts("Net-(Q15-G)", "Default") == 7.0
    assert leakage.volts("/Output Stage/DRV_OUT", "GateDrive") == 7.0
    assert leakage.volts("-4V_A", "Supply") == 9.0
    assert definition.leakage_layers == ("F.Cu", "B.Cu")
    assert definition.leakage_area.window == (136.0, 84.0, 200.0, 134.0)
    assert definition.leakage_area.grid == 0.04
    assert definition.leakage_area.reach == 3.0


def test_the_layout_rules_of_the_carrier_board() -> None:
    definition = read_definition(CARRIER)

    assert definition.sense_classes == {"Sense", "Guarded"}
    assert definition.width_of("Node1A") == 1.5
    assert definition.width_of("a class of another board") == 0.2
    assert definition.holes.keepout == 4.0
    assert definition.holes.layers == ("F.Cu", "B.Cu")
    assert definition.can.reference == "SH1"
    assert definition.can.ground_net == "GND"
    assert definition.can.via_within == 1.5


def test_a_definition_is_built_from_parsed_toml(small_definition: dict[str, Any]) -> None:
    definition = definition_from_dict(small_definition)

    assert definition.modes["ampere mode"][0] == PathPiece("input", "IN", ("J.2",), ("F.1",))
    assert definition.pairs[0].label == "shunt to amplifier"
    assert definition.class_widths == {"Sense": 0.25, "Default": 0.5}
    assert definition.default_width == 0.25
    assert definition.holes.reference == r"H\d+"


def test_a_definition_cannot_be_changed(small_definition: dict[str, Any]) -> None:
    definition = definition_from_dict(small_definition)

    with pytest.raises(TypeError):
        definition.modes["new mode"] = ()  # type: ignore[index]
    with pytest.raises(TypeError):
        definition.class_widths["Sense"] = 1.0  # type: ignore[index]


def test_a_definition_that_is_not_a_table_is_rejected() -> None:
    with pytest.raises(DefinitionError, match="definition: expected a table"):
        definition_from_dict(["copper"])


@pytest.mark.parametrize(
    "section",
    ["copper", "path", "pair", "leakage", "sense", "track_width", "mounting_holes", "shield_can"],
)
def test_a_missing_section_is_named(small_definition: dict[str, Any], section: str) -> None:
    del small_definition[section]

    with pytest.raises(DefinitionError, match=f"definition: the field '{section}' is missing"):
        definition_from_dict(small_definition)


def test_a_missing_field_is_named_with_its_place(small_definition: dict[str, Any]) -> None:
    del small_definition["path"]["ampere_mode"][1]["net"]

    with pytest.raises(
        DefinitionError, match=r"definition.path.ampere_mode\[1\]: the field 'net' is missing"
    ):
        definition_from_dict(small_definition)


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("copper", "milliohm_per_square"),
        ("copper", "via_drill_mm"),
        ("path", "grid_mm"),
        ("leakage", "ohm_per_square"),
        ("leakage", "reach_mm"),
        ("track_width", "default_mm"),
        ("mounting_holes", "keepout_mm"),
        ("shield_can", "via_within_mm"),
    ],
)
def test_a_quantity_must_be_greater_than_zero(
    small_definition: dict[str, Any], section: str, key: str
) -> None:
    small_definition[section][key] = 0.0

    with pytest.raises(
        DefinitionError, match=f"definition.{section}: the field '{key}' must be greater than zero"
    ):
        definition_from_dict(small_definition)


def test_the_copper_needs_a_layer(small_definition: dict[str, Any]) -> None:
    small_definition["copper"]["layers"] = []

    with pytest.raises(
        DefinitionError, match=r"definition.copper: the field 'layers' names no layer"
    ):
        definition_from_dict(small_definition)


@pytest.mark.parametrize("window", [[0.0, 0.0, 10.0], [10.0, 0.0, 0.0, 5.0], [0.0, 5.0, 10.0, 5.0]])
def test_a_rectangle_needs_four_ordered_numbers(
    small_definition: dict[str, Any], window: list[float]
) -> None:
    small_definition["leakage"]["window"] = window

    with pytest.raises(DefinitionError, match=r"definition.leakage: the field 'window'"):
        definition_from_dict(small_definition)


def test_a_voltage_rule_needs_a_condition(small_definition: dict[str, Any]) -> None:
    small_definition["leakage"]["voltage"]["rule"].append({"volts": 3.0})

    with pytest.raises(
        DefinitionError, match=r"definition.leakage.voltage.rule\[2\]: the rule matches no net"
    ):
        definition_from_dict(small_definition)


def test_the_reference_of_the_holes_must_be_a_regular_expression(
    small_definition: dict[str, Any],
) -> None:
    small_definition["mounting_holes"]["reference"] = "H("

    with pytest.raises(DefinitionError, match="is not a regular expression"):
        definition_from_dict(small_definition)


def test_a_file_that_is_not_toml_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "board.toml"
    path.write_text("[copper\n", encoding="utf-8")

    with pytest.raises(DefinitionError, match="is not valid TOML"):
        read_definition(path)


def test_a_file_that_does_not_exist_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(DefinitionError, match="cannot read the definition"):
        read_definition(tmp_path / "missing.toml")
