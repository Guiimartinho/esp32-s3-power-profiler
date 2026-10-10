from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from board_figures import __version__, sketch
from board_figures.cli import DEFAULT_DEFINITION, build_parser, main


def run(capsys: pytest.CaptureFixture[str], *arguments: str | Path) -> tuple[int, str, str]:
    status = main([str(argument) for argument in arguments])
    captured = capsys.readouterr()
    return status, captured.out, captured.err


def usage_error(capsys: pytest.CaptureFixture[str], *arguments: str | Path) -> str:
    with pytest.raises(SystemExit) as stopped:
        main([str(argument) for argument in arguments])
    assert stopped.value.code == 2
    return capsys.readouterr().err


def test_version_option_prints_the_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["--version"])

    assert stopped.value.code == 0
    assert capsys.readouterr().out.strip() == f"board-figures {__version__}"


def test_package_can_be_run_as_a_module(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["board_figures", "--version"])

    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("board_figures", run_name="__main__")

    assert stopped.value.code == 0
    assert capsys.readouterr().out.strip() == f"board-figures {__version__}"


def test_a_command_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    assert "required" in usage_error(capsys)


def test_an_unknown_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert "invalid choice" in usage_error(capsys, "route", "board.json")


def test_the_definition_defaults_to_the_file_of_the_carrier() -> None:
    arguments = build_parser().parse_args(["report", "board.json"])

    assert arguments.definition == Path(DEFAULT_DEFINITION)
    assert arguments.dump == Path("board.json")


def test_squares_prints_the_resistance_of_a_piece(
    capsys: pytest.CaptureFixture[str], dump_file: Path, definition_file: Path
) -> None:
    status, out, _ = run(
        capsys, "squares", dump_file, "--definition", definition_file,
        "--net", "PWR", "--from", "A.1", "--to", "B.1",
    )  # fmt: skip

    assert status == 0
    assert out == (
        "PWR: from A.1 to B.1: 7.24 squares, 3.62 mOhm at 40 C (calculated from the drawn "
        "copper; grid 0.25 mm; copper area 200.0 mm2 on 3 layers)\n"
    )


def test_squares_takes_the_grid_and_the_layers_from_the_command_line(
    capsys: pytest.CaptureFixture[str], dump_file: Path, definition_file: Path
) -> None:
    status, out, _ = run(
        capsys, "squares", dump_file, "--definition", definition_file, "--net", "PWR",
        "--from", "A.1", "--to", "B.1", "--grid", "0.125", "--layers", "F.Cu",
    )  # fmt: skip

    assert status == 0
    assert "7.41 squares" in out
    assert "grid 0.125 mm; copper area 200.0 mm2 on 1 layers" in out


def test_squares_reports_an_open_piece(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, definition_file: Path
) -> None:
    board = sketch.board(
        sketch.pad("R.1", "A", (0.0, 0.0, 1.0, 1.0)), sketch.pad("R.2", "A", (5.0, 0.0, 6.0, 1.0))
    )
    dump = tmp_path / "open.json"
    dump.write_text(json.dumps(sketch.to_dump(board)), encoding="utf-8")

    status, out, _ = run(
        capsys, "squares", dump, "--definition", definition_file,
        "--net", "A", "--from", "R.1", "--to", "R.2",
    )  # fmt: skip

    assert status == 1
    assert out == "A: from R.1 to R.2: the copper of the net does not join the pads\n"


def test_path_finds_the_way_on_one_layer(
    capsys: pytest.CaptureFixture[str], dump_file: Path
) -> None:
    status, out, _ = run(capsys, "path", dump_file, "--net", "SP", "--from", "R.1", "--to", "U.1")

    lines = out.splitlines()
    assert status == 0
    assert lines[0] == "SP: 0 vias; tracks on F.Cu"
    assert lines[1].startswith("path from R.1 to U.1 on F.Cu alone: ")
    assert lines[1].endswith(" mm between the pad edges")
    assert float(lines[1].split()[8]) == pytest.approx(9.0, abs=0.2)


def test_path_says_when_one_layer_does_not_join_the_pads(
    capsys: pytest.CaptureFixture[str], dump_file: Path
) -> None:
    status, out, _ = run(
        capsys, "path", dump_file, "--net", "GND", "--from", "SH1.1", "--to", "SH1.1",
        "--layer", "B.Cu", "--grid", "0.25",
    )  # fmt: skip

    assert status == 1
    assert out.splitlines() == [
        "GND: 1 vias; tracks on B.Cu, F.Cu",
        "NO path from SH1.1 to SH1.1 through the copper on B.Cu alone",
    ]


def test_pairs_prints_the_pairs_of_the_definition(
    capsys: pytest.CaptureFixture[str], dump_file: Path, definition_file: Path
) -> None:
    status, out, _ = run(capsys, "pairs", dump_file, "--definition", definition_file)

    assert status == 0
    assert out == (
        "shunt to amplifier: SP: 10.00 mm; SN: 12.00 mm; difference 2.00 mm "
        "(center lines, pad edge to pad edge)\n"
    )


def test_pairs_takes_a_pair_from_the_command_line(
    capsys: pytest.CaptureFixture[str], dump_file: Path
) -> None:
    status, out, _ = run(
        capsys, "pairs", dump_file, "--first", "SN", "R.2", "U.2", "--second", "SP", "R.1", "U.1"
    )

    assert status == 0
    assert out.startswith("pair: SN: 12.00 mm; SP: 10.00 mm; difference 2.00 mm")


def test_pairs_says_when_the_tracks_do_not_join_the_pads(
    capsys: pytest.CaptureFixture[str], dump_file: Path
) -> None:
    status, out, _ = run(
        capsys, "pairs", dump_file,
        "--first", "GND", "SH1.1", "SH1.1", "--second", "SP", "R.1", "U.1",
    )  # fmt: skip

    assert status == 1
    assert out == "pair: the tracks do not join the pads of a conductor\n"


def test_pairs_needs_both_conductors(capsys: pytest.CaptureFixture[str], dump_file: Path) -> None:
    error = usage_error(capsys, "pairs", dump_file, "--first", "SP", "R.1", "U.1")

    assert "--first and --second go together" in error


def test_leakage_prints_the_current_into_the_node(
    capsys: pytest.CaptureFixture[str], dump_file: Path, definition_file: Path
) -> None:
    status, out, _ = run(
        capsys, "leakage", dump_file, "--definition", definition_file, "--top", "1"
    )

    lines = out.splitlines()
    assert status == 0
    assert len(lines) == 3
    assert lines[0].startswith("Surface leakage on F.Cu (raster 0.25 mm, reach 3 mm, ")
    assert "into the measured node: " in lines[1]
    assert lines[2].endswith("7 V  GATE")


def test_leakage_takes_its_area_from_the_command_line(
    capsys: pytest.CaptureFixture[str], dump_file: Path, definition_file: Path
) -> None:
    status, out, _ = run(
        capsys, "leakage", dump_file, "--definition", definition_file, "--layer", "B.Cu",
        "--grid", "0.5", "--reach", "1", "--window", "56,4,74,20",
    )  # fmt: skip

    assert status == 0
    assert out.startswith("Surface leakage on B.Cu (raster 0.5 mm, reach 1 mm, 0 cells)\n")
    assert "into the measured node: 0.00 nA" in out


@pytest.mark.parametrize("window", ["1,2,3", "5,0,1,4", "0,4,5,4", "a,b,c,d", "0,0,inf,4"])
def test_a_window_must_be_a_rectangle(
    capsys: pytest.CaptureFixture[str], dump_file: Path, window: str
) -> None:
    assert "--window" in usage_error(capsys, "leakage", dump_file, "--window", window)


@pytest.mark.parametrize(
    ("grid", "reason"),
    [
        ("0", "must be greater than zero"),
        ("-1", "must be greater than zero"),
        ("fine", "'fine' is not a number"),
        ("nan", "'nan' is not a finite number"),
        ("inf", "'inf' is not a finite number"),
    ],
)
def test_a_grid_must_be_greater_than_zero(
    capsys: pytest.CaptureFixture[str], dump_file: Path, grid: str, reason: str
) -> None:
    error = usage_error(capsys, "leakage", dump_file, "--grid", grid)

    assert f"argument --grid: {reason}" in error


@pytest.mark.parametrize(
    ("top", "reason"), [("-1", "must not be negative"), ("few", "'few' is not a whole number")]
)
def test_the_number_of_listed_nets_must_be_a_count(
    capsys: pytest.CaptureFixture[str], dump_file: Path, top: str, reason: str
) -> None:
    error = usage_error(capsys, "leakage", dump_file, "--top", top)

    assert f"argument --top: {reason}" in error


def test_a_net_that_the_board_does_not_have_is_reported(
    capsys: pytest.CaptureFixture[str], dump_file: Path
) -> None:
    status, _, err = run(capsys, "path", dump_file, "--net", "/SP", "--from", "R.1", "--to", "U.1")

    assert status == 1
    assert err == "board-figures: error: the board has no net '/SP'\n"


def test_report_prints_every_figure(
    capsys: pytest.CaptureFixture[str], dump_file: Path, definition_file: Path
) -> None:
    status, out, _ = run(capsys, "report", dump_file, "--definition", definition_file)

    assert status == 0
    assert out.startswith("Figures of the board, calculated from the drawn copper.")
    assert "   source mode: 10.7 squares" in out
    assert "   shunt to amplifier: 10.00 / 12.00 mm, difference 2.00 mm" in out
    assert "Surface leakage on F.Cu" in out


def test_report_can_leave_out_the_slow_parts(
    capsys: pytest.CaptureFixture[str], dump_file: Path, definition_file: Path
) -> None:
    status, out, _ = run(
        capsys, "report", dump_file, "--definition", definition_file,
        "--skip-path", "--skip-leakage",
    )  # fmt: skip

    assert status == 0
    assert "The 1 A path" not in out
    assert "Surface leakage" not in out
    assert "Kelvin pairs" in out


def test_a_missing_dump_is_reported(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, definition_file: Path
) -> None:
    status, out, err = run(
        capsys, "report", tmp_path / "missing.json", "--definition", definition_file
    )

    assert status == 1
    assert out == ""
    assert err.startswith("board-figures: error: cannot read the dump")


def test_a_missing_definition_is_reported(
    capsys: pytest.CaptureFixture[str], dump_file: Path, tmp_path: Path
) -> None:
    status, _, err = run(capsys, "report", dump_file, "--definition", tmp_path / "missing.toml")

    assert status == 1
    assert err.startswith("board-figures: error: cannot read the definition")


def test_a_pad_that_the_board_does_not_have_is_reported(
    capsys: pytest.CaptureFixture[str], dump_file: Path
) -> None:
    status, _, err = run(capsys, "path", dump_file, "--net", "SP", "--from", "R.1", "--to", "X.9")

    assert status == 1
    assert err == "board-figures: error: the board has no pad X.9\n"
