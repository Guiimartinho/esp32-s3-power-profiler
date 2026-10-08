"""Command-line interface.

``s3pp --version`` prints the version. ``s3pp simulate`` runs the client
against the simulated instrument and prints the statistics of the capture,
which exercises the whole stack without hardware.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from s3_power_profiler import __version__
from s3_power_profiler.capture import (
    CaptureStatistics,
    StatisticsAccumulator,
    StreamReader,
    nominal_table,
)
from s3_power_profiler.device import DeviceClient
from s3_power_profiler.protocol import RANGE_COUNT
from s3_power_profiler.sim import SimulatorConfig, connect_simulator

_UNITS = ((1.0, "A"), (1e-3, "mA"), (1e-6, "uA"))
_SMALLEST_UNIT = (1e-9, "nA")


def format_current(amperes: float) -> str:
    """Format a current with a unit that suits its size, such as ``1.500 mA``."""
    magnitude = abs(amperes)
    scale, unit = next((entry for entry in _UNITS if magnitude >= entry[0]), _SMALLEST_UNIT)
    return f"{amperes / scale:.3f} {unit}"


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def _non_negative_int(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser of the ``s3pp`` command."""
    parser = argparse.ArgumentParser(
        prog="s3pp", description="Host tools for the Open Power Profiler."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)

    simulate = subcommands.add_parser(
        "simulate",
        help="capture from the simulated instrument",
        description="Run the client against the simulated instrument and print "
        "the statistics of the capture. No hardware is involved.",
    )
    simulate.add_argument(
        "--blocks", type=_positive_int, default=100, help="stream frames to read (default: 100)"
    )
    simulate.add_argument(
        "--drop-every",
        type=_non_negative_int,
        default=0,
        metavar="N",
        help="make the instrument drop one block after every N frames (default: never)",
    )
    simulate.add_argument(
        "--range",
        type=int,
        choices=range(RANGE_COUNT),
        default=None,
        dest="range_index",
        help="lock one range instead of automatic ranging",
    )
    return parser


def run_simulate(blocks: int, drop_every: int, range_index: int | None) -> int:
    """Capture ``blocks`` stream frames from a simulated instrument and report.

    Returns:
        The process exit status: zero on success, one if the stream stopped early.
    """
    transport, _simulator = connect_simulator(SimulatorConfig(drop_every=drop_every))
    reader = StreamReader(start_index=0)
    accumulator = StatisticsAccumulator(nominal_table())
    with DeviceClient(transport) as client:
        info = client.get_info()
        client.set_range(range_index)
        client.set_dut_power(True)
        client.start()
        for _ in range(blocks):
            payload = client.read_stream()
            if payload is None:
                break
            accumulator.add(reader.push(payload).words)
        client.stop()
        client.set_dut_power(False)
        link = client.statistics

    major, minor, patch = info.firmware_version
    print(
        f"Instrument: simulated, protocol {info.protocol_version}, "
        f"hardware revision {info.hardware_revision}, firmware {major}.{minor}.{patch}"
    )
    print(f"Blocks read: {reader.blocks} of {blocks} ({reader.samples} samples)")
    print(
        f"Gaps: {len(reader.gaps)} ({reader.missing_samples} samples missing, "
        f"{reader.dropped_blocks} blocks dropped by the instrument)"
    )
    print(f"Link: {link.crc_errors} CRC errors, {link.discarded_bytes} bytes discarded")
    _print_statistics(accumulator.result())
    return 0 if reader.blocks == blocks else 1


def _print_statistics(statistics: CaptureStatistics) -> None:
    print(
        f"Samples: {statistics.valid_samples} valid, {statistics.invalid_samples} invalid, "
        f"{statistics.fault_samples} with the fault flag"
    )
    per_range = ", ".join(
        f"R{index} {count}" for index, count in enumerate(statistics.range_samples)
    )
    print(f"Valid samples per range: {per_range}")
    if (
        statistics.mean_current is None
        or statistics.min_current is None
        or statistics.max_current is None
    ):
        print("Current: no valid samples")
        return
    print(
        "Current (nominal calibration, design targets): "
        f"mean {format_current(statistics.mean_current)}, "
        f"min {format_current(statistics.min_current)}, "
        f"max {format_current(statistics.max_current)}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return the process exit status."""
    args = build_parser().parse_args(argv)
    return run_simulate(args.blocks, args.drop_every, args.range_index)
