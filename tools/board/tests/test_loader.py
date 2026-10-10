from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from board_figures import sketch
from board_figures.errors import DumpError
from board_figures.loader import board_from_dict, read_board
from board_figures.model import Board


@pytest.fixture
def dump(small_board: Board) -> dict[str, Any]:
    plain: dict[str, Any] = json.loads(json.dumps(sketch.to_dump(small_board)))
    return plain


def test_a_dump_gives_back_the_board_it_was_made_from(
    small_board: Board, dump: dict[str, Any]
) -> None:
    assert board_from_dict(dump) == small_board


def test_a_dump_is_read_from_a_file(
    tmp_path: Path, small_board: Board, dump: dict[str, Any]
) -> None:
    path = tmp_path / "board.json"
    path.write_text(json.dumps(dump), encoding="utf-8")

    assert read_board(path) == small_board


def test_fields_that_no_calculation_uses_are_ignored(
    small_board: Board, dump: dict[str, Any]
) -> None:
    dump["drawings"] = [{"layer": "Dwgs.User", "kind": "PCB_TEXT"}]
    dump["edge"] = [0, 0, 100, 100]
    dump["pads"][0]["uuid"] = "0000"

    assert board_from_dict(dump) == small_board


def test_a_rule_area_has_no_copper(dump: dict[str, Any]) -> None:
    before = len(board_from_dict(dump).fills)
    dump["zones"].append({"net": "", "rule_area": True, "priority": 0, "fills": {}})

    assert len(board_from_dict(dump).fills) == before


def test_a_zone_gives_one_fill_per_layer(dump: dict[str, Any]) -> None:
    square = {"outline": [[0, 0], [1, 0], [1, 1], [0, 1]], "holes": []}
    dump["zones"] = [
        {
            "net": "GND",
            "rule_area": False,
            "priority": None,
            "fills": {"F.Cu": [square], "B.Cu": [square, square]},
        }
    ]

    fills = board_from_dict(dump).fills

    assert [(fill.layer, fill.priority, len(fill.polygons)) for fill in fills] == [
        ("F.Cu", 0, 1),
        ("B.Cu", 0, 2),
    ]


def test_outlines_that_enclose_no_area_are_dropped(dump: dict[str, Any]) -> None:
    dump["zones"] = [
        {
            "net": "GND",
            "rule_area": False,
            "priority": 1,
            "fills": {
                "F.Cu": [
                    {"outline": [[0, 0], [1, 0]], "holes": []},
                    {
                        "outline": [[0, 0], [4, 0], [4, 4], [0, 4]],
                        "holes": [[[1, 1], [2, 1]], [[1, 1], [2, 1], [2, 2]]],
                    },
                ]
            },
        }
    ]
    dump["pads"][0]["poly"] = []

    board = board_from_dict(dump)

    assert len(board.fills[0].polygons) == 1
    assert len(board.fills[0].polygons[0].holes) == 1
    assert board.pads[0].outline == ()


def test_a_dump_that_is_not_a_table_is_rejected() -> None:
    with pytest.raises(DumpError, match="dump: expected a table, found list"):
        board_from_dict([])


@pytest.mark.parametrize("key", ["nets", "footprints", "pads", "tracks", "vias", "zones"])
def test_a_missing_section_is_named(dump: dict[str, Any], key: str) -> None:
    del dump[key]

    with pytest.raises(DumpError, match=f"dump: the field '{key}' is missing"):
        board_from_dict(dump)


def test_a_missing_field_is_named_with_its_place(dump: dict[str, Any]) -> None:
    del dump["tracks"][2]["w"]

    with pytest.raises(DumpError, match=r"dump.tracks\[2\]: the field 'w' is missing"):
        board_from_dict(dump)


def test_a_value_of_the_wrong_kind_is_named_with_its_place(dump: dict[str, Any]) -> None:
    dump["vias"][0]["drill"] = "0.3"

    with pytest.raises(DumpError, match=r"dump.vias\[0\]: the field 'drill' must be a number"):
        board_from_dict(dump)


def test_a_net_needs_its_class(dump: dict[str, Any]) -> None:
    dump["nets"]["PWR"] = {}

    with pytest.raises(DumpError, match=r"dump.nets.PWR: the field 'class' is missing"):
        board_from_dict(dump)


@pytest.mark.parametrize("point", [[1.0], [1.0, "2"], "ab", [True, 1.0], None])
def test_a_point_must_be_a_pair_of_numbers(dump: dict[str, Any], point: object) -> None:
    dump["pads"][0]["poly"] = [[0, 0], point, [1, 1]]

    with pytest.raises(DumpError, match=r"dump.pads\[0\].poly: a point must be a pair of numbers"):
        board_from_dict(dump)


def test_an_outline_must_be_a_list_of_points(dump: dict[str, Any]) -> None:
    zone = copy.deepcopy(dump["zones"][0])
    zone["fills"]["F.Cu"][0]["holes"] = [7]
    dump["zones"] = [zone]

    with pytest.raises(DumpError, match=r"holes\[0\]: expected a list of points, found int"):
        board_from_dict(dump)


def test_a_file_that_is_not_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "board.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(DumpError, match="is not valid JSON"):
        read_board(path)


def test_a_file_that_does_not_exist_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(DumpError, match="cannot read the dump"):
        read_board(tmp_path / "missing.json")
