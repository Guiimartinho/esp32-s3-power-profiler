from __future__ import annotations

import runpy
import sys

import pytest

from s3_power_profiler import __version__
from s3_power_profiler.cli import build_parser, format_current, main, run_simulate
from s3_power_profiler.device import DeviceClient
from s3_power_profiler.protocol import BLOCK_SAMPLES

CURRENT_LINE = "Current (nominal calibration, design targets): "


def test_version_option_prints_the_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["--version"])

    assert stopped.value.code == 0
    assert capsys.readouterr().out.strip() == f"s3pp {__version__}"


def test_package_can_be_run_as_a_module(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["s3_power_profiler", "--version"])

    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("s3_power_profiler", run_name="__main__")

    assert stopped.value.code == 0
    assert capsys.readouterr().out.strip() == f"s3pp {__version__}"


def test_a_command_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        main([])

    assert stopped.value.code == 2
    assert "required" in capsys.readouterr().err


@pytest.mark.parametrize(
    "arguments",
    [
        ["simulate", "--blocks", "0"],
        ["simulate", "--blocks", "many"],
        ["simulate", "--drop-every", "-1"],
        ["simulate", "--range", "4"],
    ],
)
def test_bad_arguments_are_rejected(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(arguments)

    assert stopped.value.code == 2
    assert "usage: s3pp simulate" in capsys.readouterr().err


def test_parser_defaults() -> None:
    arguments = build_parser().parse_args(["simulate"])

    assert (arguments.blocks, arguments.drop_every, arguments.range_index) == (100, 0, None)


def test_simulate_reports_a_capture_without_gaps(capsys: pytest.CaptureFixture[str]) -> None:
    status = main(["simulate", "--blocks", "8"])

    # 2048 samples: 1000 in R0, 1000 in R1 and 48 in R2, and the first 4 samples
    # after each of the two range changes are flagged invalid.
    lines = capsys.readouterr().out.splitlines()
    assert status == 0
    assert lines[:6] == [
        "Instrument: simulated, protocol 1, hardware revision 0, firmware 0.1.0",
        f"Blocks read: 8 of 8 ({8 * BLOCK_SAMPLES} samples)",
        "Gaps: 0 (0 samples missing, 0 blocks dropped by the instrument)",
        "Link: 0 CRC errors, 0 bytes discarded",
        "Samples: 2040 valid, 8 invalid, 0 with the fault flag",
        "Valid samples per range: R0 1000, R1 996, R2 44, R3 0",
    ]
    assert lines[6].startswith(CURRENT_LINE + "mean ")
    assert len(lines) == 7


def test_simulate_reports_blocks_dropped_by_the_instrument(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = main(["simulate", "--blocks", "6", "--drop-every", "2"])

    lines = capsys.readouterr().out.splitlines()
    assert status == 0
    assert lines[1] == f"Blocks read: 6 of 6 ({6 * BLOCK_SAMPLES} samples)"
    assert lines[2] == (
        f"Gaps: 2 ({2 * BLOCK_SAMPLES} samples missing, 2 blocks dropped by the instrument)"
    )


def test_simulate_can_lock_a_range(capsys: pytest.CaptureFixture[str]) -> None:
    status = main(["simulate", "--blocks", "2", "--range", "3"])

    # The waveform rises one step per sample from the pedestal for 512 samples.
    # In R3 that is 5.34 uA up to 511 mA; the figures were computed separately.
    lines = capsys.readouterr().out.splitlines()
    assert status == 0
    assert lines[4] == f"Samples: {2 * BLOCK_SAMPLES} valid, 0 invalid, 0 with the fault flag"
    assert lines[5] == f"Valid samples per range: R0 0, R1 0, R2 0, R3 {2 * BLOCK_SAMPLES}"
    assert lines[6] == CURRENT_LINE + "mean 255.497 mA, min 5.341 uA, max 511.003 mA"


def test_stream_that_stops_early_is_reported_as_a_failure(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(DeviceClient, "read_stream", lambda self, timeout=None: None)

    status = run_simulate(blocks=3, drop_every=0, range_index=None)

    lines = capsys.readouterr().out.splitlines()
    assert status == 1
    assert lines[1] == "Blocks read: 0 of 3 (0 samples)"
    assert lines[-1] == "Current: no valid samples"


@pytest.mark.parametrize(
    ("amperes", "text"),
    [
        (1.5, "1.500 A"),
        (1.0, "1.000 A"),
        (0.25, "250.000 mA"),
        (0.001, "1.000 mA"),
        (0.000123, "123.000 uA"),
        (1e-6, "1.000 uA"),
        (5e-7, "500.000 nA"),
        (2e-10, "0.200 nA"),
        (0.0, "0.000 nA"),
        (-0.002, "-2.000 mA"),
    ],
)
def test_format_current_picks_a_unit_that_suits_the_size(amperes: float, text: str) -> None:
    assert format_current(amperes) == text
