from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from board_figures import sketch
from board_figures.definition import Definition, PathPiece, definition_from_dict
from board_figures.errors import BoardError
from board_figures.model import Board
from board_figures.report import (
    PathFigures,
    Report,
    build_report,
    can_lands,
    class_widths,
    format_leakage,
    format_report,
    hole_intrusions,
    path_figures,
    sense_nets,
)
from board_figures.resistance import net_resistance

# On the grid of 0.25 mm a strip of 5 mm is 21 cells wide. The pads of the
# long strip are 152 cells apart, those of the short strips 72 cells.
LONG = 152 / 21
SHORT = 72 / 21


@pytest.fixture
def definition(small_definition: dict[str, Any]) -> Definition:
    return definition_from_dict(small_definition)


@pytest.fixture
def report(small_board: Board, definition: Definition) -> Report:
    return build_report(small_board, definition)


def test_the_path_is_the_sum_of_its_pieces_in_each_mode(report: Report) -> None:
    source, ampere = report.path

    assert (source.mode, ampere.mode) == ("source mode", "ampere mode")
    assert [entry.squares for entry in source.pieces] == pytest.approx([LONG, SHORT])
    assert [entry.piece.label for entry in ampere.pieces] == ["input", "output"]
    assert source.squares == pytest.approx(LONG + SHORT)
    assert ampere.squares == pytest.approx(2 * SHORT)
    assert source.milliohm == pytest.approx((LONG + SHORT) * 0.5)
    assert source.complete
    assert ampere.complete


def _strip(net: str, top: float, cells: int, first: str, second: str) -> tuple[Any, ...]:
    """A strip of 5 mm with two pads of 1 mm that are ``cells`` cells of 0.25 mm apart."""
    end = 12.0 + 0.25 * cells
    return (
        sketch.fill(net, (10.0, top, end, top + 5.0)),
        sketch.pad(first, net, (10.0, top, 11.0, top + 5.0)),
        sketch.pad(second, net, (end - 1.0, top, end, top + 5.0)),
    )


def test_the_sum_of_a_mode_adds_the_pieces_as_they_were_solved(
    report: Report, definition: Definition
) -> None:
    # Pieces of 15/21, 15/21 and 11/21 squares add to 41/21 = 1.952. Each
    # rounded to 0.01 square first, they would add to 0.71 + 0.71 + 0.52 =
    # 1.94, and the two sums print differently with one decimal.
    board = sketch.board(
        *_strip("PWR", 10.0, 15, "A.1", "B.1"),
        *_strip("MID", 20.0, 15, "B.2", "C.1"),
        *_strip("OUT", 30.0, 11, "C.2", "J.1"),
    )
    pieces = (
        PathPiece("supply", "PWR", ("A.1",), ("B.1",)),
        PathPiece("middle", "MID", ("B.2",), ("C.1",)),
        PathPiece("output", "OUT", ("C.2",), ("J.1",)),
    )
    three = dataclasses.replace(definition, modes={"source mode": pieces})

    (figures,) = path_figures(board, three)

    assert [entry.squares for entry in figures.pieces] == pytest.approx([15 / 21, 15 / 21, 11 / 21])
    assert figures.squares == pytest.approx(41 / 21)
    assert figures.milliohm == pytest.approx(41 / 21 * 0.5)
    lines = format_report(dataclasses.replace(report, path=(figures,)), three).splitlines()
    assert lines[2] == "   source mode: 2.0 squares = 1.0 mOhm at 40 C"
    assert [line.split()[-1] for line in lines[3:6]] == ["0.7", "0.7", "0.5"]

    # A sum is rounded only where it is printed, and as a number is usually rounded.
    for squares, printed in ((23.2534, "23.3"), (19.52, "19.5"), (29.96, "30.0")):
        total = PathFigures("ampere mode", (), squares, three.copper.milliohm(squares))
        lines = format_report(dataclasses.replace(report, path=(total,)), three).splitlines()
        assert lines[2].startswith(f"   ampere mode: {printed} squares = ")


def test_a_piece_that_two_modes_share_is_solved_once(
    small_board: Board, definition: Definition, monkeypatch: pytest.MonkeyPatch
) -> None:
    solved: list[str] = []
    real = net_resistance

    def counting(board: Board, net: str, *arguments: Any) -> Any:
        solved.append(net)
        return real(board, net, *arguments)

    monkeypatch.setattr("board_figures.report.net_resistance", counting)

    path_figures(small_board, definition)

    assert solved == ["PWR", "OUT", "IN"]


def test_a_piece_without_a_path_leaves_the_mode_incomplete(
    report: Report, definition: Definition
) -> None:
    board = sketch.board(
        sketch.fill("PWR", (10.0, 10.0, 50.0, 15.0)),
        sketch.pad("A.1", "PWR", (10.0, 10.0, 11.0, 15.0)),
        sketch.pad("B.1", "PWR", (49.0, 10.0, 50.0, 15.0)),
        # The output strip is cut in two.
        sketch.fill("OUT", (10.0, 20.0, 15.0, 25.0)),
        sketch.fill("OUT", (20.0, 20.0, 30.0, 25.0)),
        sketch.pad("B.2", "OUT", (10.0, 20.0, 11.0, 25.0)),
        sketch.pad("J.1", "OUT", (29.0, 20.0, 30.0, 25.0)),
    )
    source_only = dataclasses.replace(
        definition, modes={"source mode": definition.modes["source mode"]}
    )

    (figures,) = path_figures(board, source_only)

    assert not figures.complete
    assert [entry.squares for entry in figures.pieces] == [pytest.approx(LONG), None]
    assert figures.squares == pytest.approx(LONG)
    lines = format_report(dataclasses.replace(report, path=(figures,)), source_only).splitlines()
    assert lines[2].endswith("at 40 C (a piece has no path!)")
    assert lines[4].split() == ["output", "OUT", "no", "path"]


def test_a_net_that_the_board_does_not_have_is_an_error(definition: Definition) -> None:
    with pytest.raises(BoardError, match="the board has no net 'PWR'"):
        build_report(Board(), definition)


def test_the_pairs_come_with_both_lengths(report: Report) -> None:
    (entry,) = report.pairs

    assert entry.pair.label == "shunt to amplifier"
    assert entry.length.first == pytest.approx(10.0)
    assert entry.length.second == pytest.approx(12.0)


def test_the_sense_nets_come_with_their_vias(small_board: Board, definition: Definition) -> None:
    first, second = sense_nets(small_board, definition)

    assert (first.net, first.net_class, first.vias, first.track_layers) == (
        "SN",
        "Sense",
        1,
        ("F.Cu",),
    )
    assert (second.net, second.vias) == ("SP", 0)


def test_the_track_widths_are_weighed_by_length(small_board: Board, definition: Definition) -> None:
    widths = {entry.net_class: entry for entry in class_widths(small_board, definition)}

    assert list(widths) == ["Default", "GateDrive", "Sense"]
    # SP has 10 mm at the class width; SN has 7 mm at it and 5 mm narrower.
    assert widths["Sense"].width == 0.25
    assert widths["Sense"].length == pytest.approx(22.0)
    assert widths["Sense"].share == pytest.approx(100.0 * 17.0 / 22.0)
    assert widths["Default"].length == pytest.approx(34.0)
    assert widths["Default"].share == 100.0
    # The class is not listed: the default width applies.
    assert widths["GateDrive"].width == 0.25
    assert widths["GateDrive"].share == 100.0


def test_a_class_with_tracks_of_no_length_counts_as_in_order(definition: Definition) -> None:
    board = sketch.board(sketch.track("A", (1.0, 1.0), (1.0, 1.0), 0.1))

    (entry,) = class_widths(board, definition)

    assert (entry.length, entry.share) == (0.0, 100.0)


def test_a_track_near_a_mounting_hole_is_found(small_board: Board, definition: Definition) -> None:
    holes, intrusions = hole_intrusions(small_board, definition)

    assert holes == 1
    (found,) = intrusions
    assert (found.hole, found.net, found.layer) == ("H1", "GND", "B.Cu")
    # The center line is 2 mm from the hole center and the track is 0.5 mm wide.
    assert found.distance == pytest.approx(1.75)


def test_only_the_layers_of_the_rule_count_at_a_mounting_hole(
    small_board: Board, definition: Definition
) -> None:
    top_only = dataclasses.replace(
        definition, holes=dataclasses.replace(definition.holes, layers=("F.Cu",))
    )

    assert hole_intrusions(small_board, top_only) == (1, ())


def test_the_lands_of_the_can_want_a_ground_via(small_board: Board, definition: Definition) -> None:
    lands = can_lands(small_board, definition)

    assert (lands.lands, lands.without_via) == (2, 1)


def test_the_leakage_is_solved_on_the_layers_of_the_definition(report: Report) -> None:
    (leakage,) = report.leakage

    assert leakage.layer == "F.Cu"
    assert leakage.converged
    assert leakage.nanoamperes > 0.0
    assert leakage.nanoamperes == pytest.approx(leakage.inside_can + leakage.outside_can)
    assert {entry.net: entry.volts for entry in leakage.by_net} == {"GATE": 7.0, "GND": 5.0}
    # The gate track runs beside the upper conductor of the pair, inside
    # the can; ground runs below the pair, outside it.
    gate, ground = leakage.by_net
    assert (gate.net, ground.net) == ("GATE", "GND")
    assert gate.squares > 10.0 / 1.75
    assert leakage.inside_can > 0.5 * gate.nanoamperes
    assert leakage.outside_can > 0.5 * ground.nanoamperes


def test_the_slow_parts_can_be_left_out(small_board: Board, definition: Definition) -> None:
    report = build_report(small_board, definition, with_path=False, with_leakage=False)

    assert report.path == ()
    assert report.leakage == ()
    assert len(report.pairs) == 1
    text = format_report(report, definition)
    assert "The 1 A path" not in text
    assert "Surface leakage" not in text


def test_the_report_as_text(report: Report, definition: Definition) -> None:
    lines = format_report(report, definition).splitlines()

    assert (
        lines[0] == "Figures of the board, calculated from the drawn copper. Nothing is measured."
    )
    assert lines[1] == "The 1 A path (limit: 30 squares in either mode)"
    source = f"{LONG + SHORT:.1f} squares = {(LONG + SHORT) * 0.5:.1f} mOhm"
    assert lines[2] == f"   source mode: {source} at 40 C"
    assert lines[3].split() == ["supply", "PWR", f"{LONG:.1f}"]
    assert f"   ampere mode: {2 * SHORT:.1f} squares = {SHORT:.1f} mOhm at 40 C" in lines
    assert "   shunt to amplifier: 10.00 / 12.00 mm, difference 2.00 mm" in lines
    assert "Sense and guarded nets: 1 of 2 without a via" in lines
    assert "   SP                         Sense    vias 0  tracks on F.Cu" in lines
    assert "   Sense       0.25 mm:     22.0 mm of tracks,  77.3 % at that width or wider" in lines
    assert "Mounting holes: 1 holes; tracks nearer than 4 mm to a center: 1 -> H1:GND@1.75" in lines
    assert "Shield can: 2 lands, 1 with a ground via within 1.5 mm, 1 without" in lines
    assert "Surface leakage on F.Cu (raster 0.25 mm, reach 3 mm, " in "\n".join(lines)


def test_a_pair_whose_tracks_do_not_join_is_said_so(
    small_board: Board, definition: Definition
) -> None:
    board = dataclasses.replace(
        small_board, tracks=tuple(track for track in small_board.tracks if track.net != "SP")
    )

    text = format_report(
        build_report(board, definition, with_path=False, with_leakage=False), definition
    )

    assert "   shunt to amplifier: the tracks do not join the pads of a conductor" in text
    assert "   SP                         Sense    vias 0  tracks on none" in text
    assert "tracks nearer than 4 mm to a center: 1" in text


def test_a_board_without_intrusions_lists_none(small_board: Board, definition: Definition) -> None:
    board = dataclasses.replace(
        small_board,
        footprints=(),
        pads=tuple(pad for pad in small_board.pads if pad.ref != "SH1"),
        tracks=tuple(track for track in small_board.tracks if track.layer == "F.Cu"),
    )

    text = format_report(
        build_report(board, definition, with_path=False, with_leakage=False), definition
    )

    assert "Mounting holes: 0 holes; tracks nearer than 4 mm to a center: 0\n" in text
    assert "Shield can: 0 lands, 0 with a ground via within 1.5 mm, 0 without" in text


def test_the_leakage_as_text(report: Report, definition: Definition) -> None:
    (leakage,) = report.leakage

    lines = format_leakage(leakage, definition, top=1)

    assert len(lines) == 3
    assert lines[0].startswith("Surface leakage on F.Cu (raster 0.25 mm, reach 3 mm, ")
    assert "the solver" not in lines[0]
    assert f"into the measured node: {leakage.nanoamperes:.2f} nA" in lines[1]
    assert "(calculated, 1e+11 ohm per square)" in lines[1]
    assert lines[2].endswith("7 V  GATE")


def test_a_solver_that_did_not_converge_is_said_so(report: Report, definition: Definition) -> None:
    failed = dataclasses.replace(report.leakage[0], converged=False)

    assert "the solver did NOT converge" in format_leakage(failed, definition)[0]
