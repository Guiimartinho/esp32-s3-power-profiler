"""Command line of the package.

``circuit-sim list`` names the benches, ``run`` runs them and files their
results, ``report`` writes the pages, ``parts`` shows the schematic as the
benches see it, and ``netlist`` writes or checks the snapshot that the
benches are built from.
"""

from __future__ import annotations

import argparse
import dataclasses
import math
import pathlib
import sys
from collections.abc import Sequence

from circuit_sim import __version__
from circuit_sim.bench import FAIL, OPEN_TIER, VENDOR_TIER, Bench, discover
from circuit_sim.circuit import load_model_map
from circuit_sim.engine import Engine, default_engine
from circuit_sim.errors import ModelError, SimulationError
from circuit_sim.netlist import dump_snapshot, load_snapshot, natural_key, snapshot_from_kicad_xml
from circuit_sim.report import ERROR, format_quantity
from circuit_sim.run import Layout, run_bench, write_report


def _selected(benches: Sequence[Bench], wanted: Sequence[str]) -> list[Bench]:
    """The benches that match the names given: a block or ``block/bench``."""
    if not wanted:
        return list(benches)
    chosen = [entry for entry in benches if entry.block in wanted or entry.ident in wanted]
    known = {entry.block for entry in benches} | {entry.ident for entry in benches}
    unknown = [name for name in wanted if name not in known]
    if unknown:
        raise SimulationError(f"no block or bench is named {', '.join(unknown)}")
    return chosen


def _list(layout: Layout, _arguments: argparse.Namespace) -> int:
    for entry in discover(layout.benches):
        print(f"{entry.ident:42} {entry.title}")
    return 0


def _run(layout: Layout, arguments: argparse.Namespace) -> int:
    benches = _selected(discover(layout.benches), arguments.select)
    engine = default_engine()
    if arguments.timeout is not None:
        # The models of some manufacturers take minutes per deck or never end.
        engine = dataclasses.replace(engine, timeout=arguments.timeout)
    netlist = load_snapshot(layout.netlist)
    models = load_model_map(layout.models)
    failed = 0
    broken = 0
    for entry in benches:
        record = run_bench(entry, layout, engine, netlist, models, arguments.tier)
        if record.status == ERROR:
            broken += 1
            print(f"{entry.ident}: DID NOT RUN: {record.error}")
            continue
        passed, fails, plain = record.counts()
        failed += fails
        print(f"{entry.ident}: {passed} pass, {fails} fail, {plain} without limit")
        for figure in record.figures:
            if arguments.verbose or figure.verdict == FAIL:
                mark = "FAIL" if figure.verdict == FAIL else "    "
                value = format_quantity(figure.value, figure.unit)
                expected = format_quantity(figure.expected, figure.unit)
                print(
                    f"  {mark} {figure.label}: {value}"
                    + (f" (spec {expected})" if expected else "")
                )
    if not arguments.no_report:
        write_report(layout)
    if broken:
        return 1
    return 2 if failed and arguments.strict else 0


def _report(layout: Layout, _arguments: argparse.Namespace) -> int:
    for path in write_report(layout):
        print(path.relative_to(layout.root).as_posix())
    return 0


def _parts(layout: Layout, arguments: argparse.Namespace) -> int:
    netlist = load_snapshot(layout.netlist)
    refs = list(arguments.refs)
    if arguments.sheet:
        sheets = sorted({part.sheet for part in netlist.components.values()})
        match = [sheet for sheet in sheets if arguments.sheet.lower() in sheet.lower()]
        if len(match) != 1:
            raise SimulationError(
                f"{arguments.sheet!r} names {len(match)} sheets; the sheets are {', '.join(sheets)}"
            )
        refs += netlist.on_sheet(match[0])
    if not refs:
        refs = list(netlist.components)
    try:
        models = load_model_map(layout.models)
    except ModelError:
        models = None
    for ref in sorted(set(refs), key=natural_key):
        part = netlist.component(ref)
        pins = " ".join(
            f"{pin.number}{'(' + pin.function + ')' if pin.function else ''}={pin.net}"
            for pin in part.pins
        )
        model = ""
        if models is not None:
            try:
                found = models.model_of(part)
                model = f" <{found.name or found.kind}>"
            except ModelError:
                model = " <NO MODEL>"
        print(f"{ref:6} {part.value} [{part.mpn}]{model}  {pins}")
    return 0


def _netlist(layout: Layout, arguments: argparse.Namespace) -> int:
    text = dump_snapshot(
        snapshot_from_kicad_xml(pathlib.Path(arguments.xml).read_text(encoding="utf-8"))
    )
    if arguments.check:
        stored = layout.netlist.read_text(encoding="utf-8") if layout.netlist.is_file() else ""
        if stored != text:
            print("the snapshot differs from the netlist of the schematic")
            return 1
        print("the snapshot matches the netlist of the schematic")
        return 0
    layout.netlist.parent.mkdir(parents=True, exist_ok=True)
    layout.netlist.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {layout.netlist.relative_to(layout.root).as_posix()}")
    return 0


def _seconds(text: str) -> float:
    """A time in seconds as the command line gives it: a number above zero."""
    try:
        seconds = float(text)
    except ValueError:
        seconds = math.nan
    if not math.isfinite(seconds):
        raise argparse.ArgumentTypeError(f"{text!r} is not a number of seconds")
    if seconds <= 0.0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return seconds


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="circuit-sim",
        description="Circuit simulations of the carrier board, from its netlist, in ngspice.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--root",
        type=pathlib.Path,
        default=pathlib.Path(),
        help="folder with benches, models, netlist and results (default: the current folder)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="name every bench").set_defaults(handler=_list)

    run = commands.add_parser("run", help="run benches and file their results")
    run.add_argument("select", nargs="*", help="blocks or block/bench names; all without any")
    run.add_argument(
        "--tier",
        choices=(OPEN_TIER, VENDOR_TIER),
        default=OPEN_TIER,
        help="vendor: use the models of the manufacturers where they are present",
    )
    run.add_argument("--strict", action="store_true", help="exit with 2 when a figure fails")
    run.add_argument("--verbose", "-v", action="store_true", help="print every figure")
    run.add_argument(
        "--no-report",
        action="store_true",
        help="leave the pages alone; write them later with the report command",
    )
    run.add_argument(
        "--timeout",
        type=_seconds,
        metavar="SECONDS",
        help="give up on a deck that has no result after this time "
        f"(default: {Engine(pathlib.Path()).timeout:g})",
    )
    run.set_defaults(handler=_run)

    commands.add_parser("report", help="write the pages from the results on file").set_defaults(
        handler=_report
    )

    parts = commands.add_parser("parts", help="show parts of the schematic with their nets")
    parts.add_argument("refs", nargs="*", help="reference designators")
    parts.add_argument("--sheet", help="every part of the sheet whose name holds this text")
    parts.set_defaults(handler=_parts)

    netlist = commands.add_parser("netlist", help="write or check the netlist snapshot")
    netlist.add_argument("xml", help="netlist of the schematic, exported by KiCad as XML")
    netlist.add_argument(
        "--check", action="store_true", help="compare with the stored snapshot instead of writing"
    )
    netlist.set_defaults(handler=_netlist)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line.

    Returns:
        0 on success, 1 when a bench could not run or a check failed, 2 when
        a figure failed under ``--strict`` or the input was wrong.
    """
    arguments = _parser().parse_args(argv)
    layout = Layout(arguments.root.resolve())
    for stream in (sys.stdout, sys.stderr):
        # The units of the figures are not in every console code page.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    try:
        return int(arguments.handler(layout, arguments))
    except SimulationError as error:
        print(f"circuit-sim: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"circuit-sim: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
