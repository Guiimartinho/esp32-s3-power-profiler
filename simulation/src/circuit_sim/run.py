"""Running benches and filing what they produce.

The folder of the simulations has a fixed layout: the benches, the models,
the snapshot of the netlist and the results each in a folder of their own.
:func:`run_bench` runs one bench and writes its record, its graphs and its
decks; :func:`write_report` writes the pages from the records on file.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, replace

from circuit_sim.bench import OPEN_TIER, Bench, Context, block_title
from circuit_sim.circuit import ModelMap
from circuit_sim.engine import Engine
from circuit_sim.errors import SimulationError
from circuit_sim.netlist import Netlist
from circuit_sim.plot import render
from circuit_sim.report import (
    ERROR,
    OK,
    Record,
    as_stored,
    block_page,
    dump_record,
    read_records,
    summary_table,
)


@dataclass(frozen=True, slots=True)
class Layout:
    """The folders of the simulations.

    Attributes:
        root: The folder that holds the others.
    """

    root: pathlib.Path

    @property
    def benches(self) -> pathlib.Path:
        """The package of the benches."""
        return self.root / "benches"

    @property
    def models(self) -> pathlib.Path:
        """The model files and the model map."""
        return self.root / "models"

    @property
    def netlist(self) -> pathlib.Path:
        """The snapshot of the netlist of the schematic."""
        return self.root / "netlist" / "carrier.json"

    @property
    def results(self) -> pathlib.Path:
        """The records, graphs, decks and pages."""
        return self.root / "results"

    @property
    def work(self) -> pathlib.Path:
        """Scratch folder of the runs; not part of the repository."""
        return self.root / ".work"


def run_bench(
    entry: Bench,
    layout: Layout,
    engine: Engine,
    netlist: Netlist,
    models: ModelMap,
    tier: str = OPEN_TIER,
) -> Record:
    """Run one bench and file its record, graphs and decks.

    A bench that cannot run leaves a record that says why; the error is not
    raised, so that one broken bench does not hide the others. That holds for
    a deck that failed, for a graph that cannot be drawn and for a defect of
    the bench itself, which is named by the kind of its error. Only a stop by
    the person at the keyboard passes through.

    The figures are rounded to the digits that a record keeps before they are
    judged, so that the record returned, the result file and the page give
    one verdict.

    Args:
        entry: The bench.
        layout: The folders.
        engine: The simulator.
        netlist: The schematic.
        models: The model map.
        tier: ``open`` or ``vendor``. A vendor run files its figures only:
            they stand beside the ones of the open tier in the report.
    """
    is_open = tier == OPEN_TIER
    workdir = layout.work / entry.block if is_open else layout.work / tier / entry.block
    target = layout.results / entry.block
    target.mkdir(parents=True, exist_ok=True)
    context = Context(
        engine=engine,
        netlist=netlist,
        models=models,
        models_dir=layout.models,
        workdir=workdir,
        prefix=entry.name,
        tier=tier,
    )
    # What every record of this bench says, whether it ran or not.
    failed = Record(
        block=entry.block,
        block_title=block_title(entry.block),
        bench=entry.name,
        title=entry.title,
        covers=entry.covers,
        summary=entry.summary,
        status=ERROR,
        tier=tier,
    )
    record_path = target / (f"{entry.name}.json" if is_open else f"{entry.name}.{tier}.json")
    if is_open:
        for stale in target.glob(f"{entry.name}.*"):
            if not stale.name.endswith(".vendor.json"):
                stale.unlink()
    graphs: list[tuple[str, str, str]] = []
    drawn: list[pathlib.Path] = []
    try:
        outcome = entry.run(context)
        figures = tuple(as_stored(figure) for figure in outcome.figures)
        notes = tuple(outcome.notes)
        if is_open:
            for graph in outcome.graphs:
                file_name = f"{entry.name}.{graph.name}.png"
                drawn.append(target / file_name)
                render(graph, target / file_name)
                graphs.append((graph.name, graph.title, file_name))
    except Exception as error:
        # A deck that could not run, a graph that could not be drawn or a
        # defect of the bench: none of them stops the benches that follow.
        # The graphs drawn before the error do not stay behind.
        for path in drawn:
            path.unlink(missing_ok=True)
        record = replace(failed, error=_reason(error))
        record_path.write_text(dump_record(record), encoding="utf-8", newline="\n")
        return record
    if is_open:
        for file_name, deck in context.kept.items():
            (target / file_name).write_text(deck, encoding="utf-8", newline="\n")
    record = replace(
        failed,
        status=OK,
        engine=context.engine_version,
        library_sha256=context.library_sha256,
        figures=figures,
        graphs=tuple(graphs),
        notes=notes,
        models=tuple(sorted(context.origins)),
        decks=tuple(sorted(context.kept)) if is_open else (),
    )
    record_path.write_text(dump_record(record), encoding="utf-8", newline="\n")
    return record


def _reason(error: Exception) -> str:
    """Why a bench did not run.

    An error that the package raises on purpose says it in its message. Any
    other error is a defect of the bench or of the package, and is named by
    its kind as well.
    """
    if isinstance(error, SimulationError):
        return str(error)
    text = str(error)
    return f"{type(error).__name__}: {text}" if text else type(error).__name__


def write_report(layout: Layout) -> list[pathlib.Path]:
    """Write the pages of the report from the records on file.

    Returns:
        The files written: the summary and one page per block.
    """
    records = read_records(layout.results)
    blocks: dict[str, list[Record]] = {}
    for record in records:
        blocks.setdefault(record.block, []).append(record)
    written = []
    for name, group in blocks.items():
        page = layout.results / name / "README.md"
        page.write_text(
            block_page(name, group[0].block_title, group), encoding="utf-8", newline="\n"
        )
        written.append(page)
    lines = [
        "# Simulation Results",
        "",
        "Everything in this folder is a simulation result: circuits taken from",
        "the netlist of the schematic, run in ngspice, with models that are",
        "named beside every result. Nothing here is measured on hardware. A",
        "figure that passes says that the circuit as drawn, with these models,",
        "keeps the limit; it does not say that a built board will.",
        "",
        "The pages are written by `circuit-sim report` from the result files;",
        "do not edit them by hand.",
        "",
        *summary_table(records),
    ]
    engines = sorted({record.engine for record in records if record.engine})
    if engines:
        lines += ["", f"Simulator: {', '.join(engines)}."]
    summary = layout.results / "README.md"
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return [summary, *written]
