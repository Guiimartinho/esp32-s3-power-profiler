"""Command-line interface.

``board-figures`` takes the dump of a board and prints figures as plain
text. Each subcommand is one calculation; ``report`` runs all of them for
the nets and pads that a definition file names.

Exit status: 0 on success, 1 when a file or the board does not allow the
calculation (and for ``path`` when there is no path), 2 on a usage error.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from board_figures import __version__
from board_figures.definition import Definition, Pair, read_definition
from board_figures.errors import BoardFiguresError
from board_figures.leakage import LeakageArea, surface_leakage
from board_figures.loader import read_board
from board_figures.pairs import Conductor, pair_length
from board_figures.path import DEFAULT_GRID as PATH_GRID
from board_figures.path import DEFAULT_LAYER, layer_path
from board_figures.report import build_report, format_leakage, format_report
from board_figures.resistance import net_resistance

DEFAULT_DEFINITION = "carrier.toml"
"""Definition file that is read from the working directory unless another is named."""


def _number(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(f"{text!r} is not a finite number")
    return value


def _positive(text: str) -> float:
    value = _number(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value


def _count(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from None
    if value < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return value


def _rectangle(text: str) -> tuple[float, float, float, float]:
    parts = text.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("must be four numbers: left,top,right,bottom")
    left, top, right, bottom = (_number(part) for part in parts)
    if right <= left or bottom <= top:
        raise argparse.ArgumentTypeError("right must lie beyond left and bottom beyond top")
    return (left, top, right, bottom)


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser of the ``board-figures`` command."""
    parser = argparse.ArgumentParser(
        prog="board-figures",
        description="Figures of a board layout, calculated from the drawn copper of a "
        "board dump. Nothing is measured on hardware.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)

    def add(name: str, summary: str, *, definition: bool) -> argparse.ArgumentParser:
        command = subcommands.add_parser(name, help=summary, description=summary)
        command.add_argument("dump", type=Path, help="board dump written by kicad/dump_board.py")
        if definition:
            command.add_argument(
                "--definition",
                type=Path,
                default=Path(DEFAULT_DEFINITION),
                help=f"board definition file (default: {DEFAULT_DEFINITION})",
            )
        return command

    squares = add(
        "squares",
        "Resistance of the copper of a net between two groups of pads, in squares.",
        definition=True,
    )
    squares.add_argument("--net", required=True, help="name of the net")
    squares.add_argument(
        "--from", dest="start", nargs="+", required=True, metavar="REF.PAD", help="first group"
    )
    squares.add_argument(
        "--to", dest="goal", nargs="+", required=True, metavar="REF.PAD", help="second group"
    )
    squares.add_argument("--grid", type=_positive, help="cell size in mm (default: definition)")
    squares.add_argument(
        "--layers", help="layers that carry the current, comma separated (default: definition)"
    )

    path = add(
        "path",
        "Is there a path between two pads through the copper of a net on one layer alone?",
        definition=False,
    )
    path.add_argument("--net", required=True, help="name of the net")
    path.add_argument("--from", dest="start", required=True, metavar="REF.PAD", help="first pad")
    path.add_argument("--to", dest="goal", required=True, metavar="REF.PAD", help="second pad")
    path.add_argument("--layer", default=DEFAULT_LAYER, help=f"layer (default: {DEFAULT_LAYER})")
    path.add_argument(
        "--grid", type=_positive, default=PATH_GRID, help=f"cell size in mm (default: {PATH_GRID})"
    )

    pairs = add(
        "pairs",
        "Center-line length of the two conductors of a pair. Without --first and "
        "--second: every pair of the definition.",
        definition=True,
    )
    for option in ("--first", "--second"):
        pairs.add_argument(
            option, nargs=3, metavar=("NET", "REF.PAD", "REF.PAD"), help="one conductor of a pair"
        )

    leakage = add(
        "leakage", "Surface leakage into the measured node on one outer layer.", definition=True
    )
    leakage.add_argument("--layer", default=DEFAULT_LAYER, help=f"layer (default: {DEFAULT_LAYER})")
    leakage.add_argument("--grid", type=_positive, help="cell size in mm (default: definition)")
    leakage.add_argument(
        "--reach", type=_positive, help="distance from the node solved, in mm (default: definition)"
    )
    leakage.add_argument(
        "--window",
        type=_rectangle,
        metavar="LEFT,TOP,RIGHT,BOTTOM",
        help="part of the board solved, in mm (default: definition)",
    )
    leakage.add_argument(
        "--top", type=_count, default=12, help="number of foreign nets listed (default: 12)"
    )

    report = add("report", "Every figure that the definition asks for.", definition=True)
    report.add_argument("--skip-path", action="store_true", help="leave out the 1 A path")
    report.add_argument("--skip-leakage", action="store_true", help="leave out the leakage")
    return parser


def run_squares(arguments: argparse.Namespace) -> int:
    """Print the resistance of a net between two groups of pads."""
    definition = read_definition(arguments.definition)
    model = definition.copper
    if arguments.layers:
        model = replace(model, layers=tuple(arguments.layers.split(",")))
    grid = arguments.grid or definition.path_grid
    result = net_resistance(
        read_board(arguments.dump), arguments.net, arguments.start, arguments.goal, model, grid
    )
    ends = f"from {' '.join(arguments.start)} to {' '.join(arguments.goal)}"
    if not result.connected:
        print(f"{arguments.net}: {ends}: the copper of the net does not join the pads")
        return 1
    print(
        f"{arguments.net}: {ends}: {result.squares:.2f} squares, {result.milliohm:.2f} mOhm "
        f"at {model.temperature:g} C (calculated from the drawn copper; grid {grid:g} mm; "
        f"copper area {result.copper_area:.1f} mm2 on {len(model.layers)} layers)"
    )
    return 0


def run_path(arguments: argparse.Namespace) -> int:
    """Print whether one layer alone joins two pads, and how long the way is."""
    found = layer_path(
        read_board(arguments.dump),
        arguments.net,
        arguments.start,
        arguments.goal,
        arguments.layer,
        arguments.grid,
    )
    print(
        f"{found.net}: {found.vias} vias; tracks on {', '.join(found.track_layers) or 'no layer'}"
    )
    ends = f"from {arguments.start} to {arguments.goal}"
    if found.length is None:
        print(f"NO path {ends} through the copper on {found.layer} alone")
        return 1
    print(f"path {ends} on {found.layer} alone: {found.length:.2f} mm between the pad edges")
    return 0


def run_pairs(arguments: argparse.Namespace) -> int:
    """Print the center-line lengths of one pair, or of the pairs of the definition."""
    board = read_board(arguments.dump)
    if arguments.first and arguments.second:
        pairs: tuple[Pair, ...] = (
            Pair("pair", Conductor(*arguments.first), Conductor(*arguments.second)),
        )
    else:
        pairs = read_definition(arguments.definition).pairs
    status = 0
    for pair in pairs:
        length = pair_length(board, pair.first, pair.second)
        if length.first is None or length.second is None:
            print(f"{pair.label}: the tracks do not join the pads of a conductor")
            status = 1
            continue
        print(
            f"{pair.label}: {pair.first.net}: {length.first:.2f} mm; "
            f"{pair.second.net}: {length.second:.2f} mm; "
            f"difference {abs(length.first - length.second):.2f} mm "
            "(center lines, pad edge to pad edge)"
        )
    return status


def run_leakage(arguments: argparse.Namespace) -> int:
    """Print the surface leakage into the measured node on one layer."""
    definition = _with_area(read_definition(arguments.definition), arguments)
    leakage = surface_leakage(
        read_board(arguments.dump), arguments.layer, definition.leakage, definition.leakage_area
    )
    print("\n".join(format_leakage(leakage, definition, arguments.top)))
    return 0


def run_report(arguments: argparse.Namespace) -> int:
    """Print every figure that the definition asks for."""
    definition = read_definition(arguments.definition)
    report = build_report(
        read_board(arguments.dump),
        definition,
        with_path=not arguments.skip_path,
        with_leakage=not arguments.skip_leakage,
    )
    print(format_report(report, definition))
    return 0


def _with_area(definition: Definition, arguments: argparse.Namespace) -> Definition:
    """The definition with the leakage area that the command line asks for."""
    area = definition.leakage_area
    return replace(
        definition,
        leakage_area=LeakageArea(
            window=arguments.window or area.window,
            grid=arguments.grid or area.grid,
            reach=arguments.reach or area.reach,
        ),
    )


_COMMANDS = {
    "squares": run_squares,
    "path": run_path,
    "pairs": run_pairs,
    "leakage": run_leakage,
    "report": run_report,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return the process exit status."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "pairs" and bool(arguments.first) != bool(arguments.second):
        parser.error("--first and --second go together")
    try:
        return _COMMANDS[arguments.command](arguments)
    except BoardFiguresError as error:
        print(f"board-figures: error: {error}", file=sys.stderr)
        return 1
