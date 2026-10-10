"""Fixtures shared by the test modules.

``small_board`` is a synthetic board with one of everything that the report
looks at, drawn on round coordinates so that every figure can be worked out
by hand. ``SMALL_DEFINITION`` is the definition file that goes with it. No
test needs KiCad or the board of the project.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from board_figures import sketch
from board_figures.model import Board, Footprint

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

SMALL_DEFINITION = r"""
[copper]
layers = ["F.Cu", "In2.Cu", "B.Cu"]
reference_thickness_um = 35.0
milliohm_per_square = 0.5
temperature_c = 40.0
via_squares = 1.7
via_drill_mm = 0.4
plated_hole_squares = 0.5

[copper.thickness_um]
"F.Cu" = 35.0
"In1.Cu" = 17.5
"In2.Cu" = 17.5
"B.Cu" = 35.0

[path]
grid_mm = 0.25
limit_squares = 30.0

[[path.source_mode]]
label = "supply"
net = "PWR"
from = ["A.1"]
to = ["B.1"]

[[path.source_mode]]
label = "output"
net = "OUT"
from = ["B.2"]
to = ["J.1"]

[[path.ampere_mode]]
label = "input"
net = "IN"
from = ["J.2"]
to = ["F.1"]

[[path.ampere_mode]]
label = "output"
net = "OUT"
from = ["B.2"]
to = ["J.1"]

[[pair]]
label = "shunt to amplifier"
first = { net = "SP", from = "R.1", to = "U.1" }
second = { net = "SN", from = "R.2", to = "U.2" }

[leakage]
node_classes = ["Sense", "Node1A"]
followers = ["GUARD"]
ohm_per_square = 1e11
layers = ["F.Cu"]
window = [56.0, 4.0, 74.0, 20.0]
grid_mm = 0.25
reach_mm = 3.0
can = [56.0, 4.0, 74.0, 10.0]

[leakage.voltage]
default = 5.0

[[leakage.voltage.rule]]
volts = 9.0
name_prefixes = ["-4V"]

[[leakage.voltage.rule]]
volts = 7.0
name_contains = ["+12V"]
classes = ["GateDrive"]

[sense]
classes = ["Sense"]

[track_width]
default_mm = 0.25

[track_width.class_mm]
Sense = 0.25
Default = 0.5

[mounting_holes]
reference = 'H\d+'
layers = ["F.Cu", "B.Cu"]
keepout_mm = 4.0

[shield_can]
reference = "SH1"
ground_net = "GND"
via_within_mm = 1.5
"""


@pytest.fixture
def small_board() -> Board:
    """A board with a current path in two modes, a pair, a hole and a can."""
    return sketch.board(
        # Source mode: PWR, then OUT. Each strip is 5 mm wide.
        sketch.fill("PWR", (10.0, 10.0, 50.0, 15.0)),
        sketch.pad("A.1", "PWR", (10.0, 10.0, 11.0, 15.0)),
        sketch.pad("B.1", "PWR", (49.0, 10.0, 50.0, 15.0)),
        sketch.fill("OUT", (10.0, 20.0, 30.0, 25.0)),
        sketch.pad("B.2", "OUT", (10.0, 20.0, 11.0, 25.0)),
        sketch.pad("J.1", "OUT", (29.0, 20.0, 30.0, 25.0)),
        # Ampere mode: IN, then OUT again.
        sketch.fill("IN", (10.0, 30.0, 30.0, 35.0)),
        sketch.pad("J.2", "IN", (10.0, 30.0, 11.0, 35.0)),
        sketch.pad("F.1", "IN", (29.0, 30.0, 30.0, 35.0)),
        # A pair: SP runs straight (10 mm), SN takes a detour (12 mm) with a via.
        sketch.pad("R.1", "SP", (59.5, 9.5, 60.5, 10.5)),
        sketch.pad("U.1", "SP", (69.5, 9.5, 70.5, 10.5)),
        sketch.track("SP", (60.0, 10.0), (70.0, 10.0), 0.25),
        sketch.pad("R.2", "SN", (59.5, 11.5, 60.5, 12.5)),
        sketch.pad("U.2", "SN", (69.5, 13.5, 70.5, 14.5)),
        sketch.track("SN", (60.0, 12.0), (65.0, 12.0), 0.25),
        sketch.track("SN", (65.0, 12.0), (65.0, 14.0), 0.25),
        sketch.track("SN", (65.0, 14.0), (70.0, 14.0), 0.125),
        sketch.via("SN", (65.0, 12.0)),
        # Ground 2 mm below the pair, and a gate node 2 mm above it.
        sketch.track("GND", (58.0, 16.0), (72.0, 16.0), 0.5),
        sketch.track("GATE", (58.0, 8.0), (72.0, 8.0), 0.5),
        # A mounting hole with a ground track 2 mm from its center.
        Footprint("H1", (80.0, 80.0)),
        sketch.track("GND", (70.0, 82.0), (90.0, 82.0), 0.5, layer="B.Cu"),
        # A shield can with two lands; only the first has a ground via beside it.
        sketch.pad("SH1.1", "GND", (100.0, 10.0, 101.0, 11.0)),
        sketch.pad("SH1.1", "GND", (120.0, 10.0, 121.0, 11.0)),
        sketch.via("GND", (100.5, 12.0)),
        classes={
            "PWR": "Power1A",
            "OUT": "Node1A",
            "IN": "Power1A",
            "SP": "Sense",
            "SN": "Sense",
            "GATE": "GateDrive",
        },
    )


@pytest.fixture
def small_definition() -> dict[str, Any]:
    """The definition of ``small_board``, as the parsed TOML."""
    return tomllib.loads(SMALL_DEFINITION)


@pytest.fixture
def dump_file(tmp_path: Path, small_board: Board) -> Path:
    """The dump of ``small_board`` in a file."""
    path = tmp_path / "board.json"
    path.write_text(json.dumps(sketch.to_dump(small_board)), encoding="utf-8")
    return path


@pytest.fixture
def definition_file(tmp_path: Path) -> Path:
    """The definition of ``small_board`` in a file."""
    path = tmp_path / "small.toml"
    path.write_text(SMALL_DEFINITION, encoding="utf-8")
    return path
