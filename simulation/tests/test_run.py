from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from circuit_sim.bench import Bench, Context, Figure, Graph, Outcome, Panel, Trace, block
from circuit_sim.circuit import ModelMap
from circuit_sim.engine import Engine, RunResult
from circuit_sim.errors import BenchError
from circuit_sim.netlist import Netlist
from circuit_sim.report import ERROR, OK, Record, block_page, dump_record, load_record
from circuit_sim.run import Layout, run_bench, write_report

SEEN: list[Context] = []

NOTE = "An ideal source feeds the divider."


def tap_graph(name: str, panel: int = 0) -> Graph:
    line = np.array([0.0, 1.0])
    return Graph(
        name, f"The {name}", "Step", (Panel("Tap (V)"),), (Trace(line, line, "tap", panel),)
    )


def divider(ctx: Context) -> Outcome:
    """The divider is read at its tap."""
    SEEN.append(ctx)
    circuit = ctx.circuit(["R1", "R2", "Q1", "U1"])
    result = ctx.run("at-rest", ctx.deck("Divider", circuit, control=["op"]))
    ctx.run("sweep-1", "* a deck of a sweep\n.end\n", keep=False)
    tap = float(result.real("out")[0])
    figure = Figure("tap", "Tap voltage", tap, "V", expected=2.5, low=2.4, high=2.6, source="4.3")
    return Outcome((figure,), (tap_graph("tap"), tap_graph("zoom")), (NOTE,))


def unmodeled(ctx: Context) -> Outcome:
    """The connector has no model."""
    ctx.run("before", "* a deck that ran before the bench broke\n.end\n")
    ctx.circuit(["J1"])
    return Outcome(())


def badly_drawn(ctx: Context) -> Outcome:
    """The second graph puts its curve on a panel that it does not have."""
    ctx.run("at-rest", "* deck\n.end\n")
    return Outcome(
        (Figure("tap", "Tap voltage", 2.5, "V"),), (tap_graph("tap"), tap_graph("zoom", 1))
    )


def defective(ctx: Context) -> Outcome:
    """The bench divides by zero."""
    return Outcome((Figure("ratio", "A ratio", 1 / len(ctx.kept), ""),))


DIVIDER = Bench(
    "ladder", "divider", "A divider at rest", "section 4.3", "The tap is read.", divider
)


@pytest.fixture
def layout(root: Path) -> Layout:
    SEEN.clear()
    return Layout(root)


def files_of(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


def test_the_folders_of_the_simulations(tmp_path: Path) -> None:
    layout = Layout(tmp_path)

    assert layout.benches == tmp_path / "benches"
    assert layout.models == tmp_path / "models"
    assert layout.netlist == tmp_path / "netlist" / "carrier.json"
    assert layout.results == tmp_path / "results"
    assert layout.work == tmp_path / ".work"


def test_a_bench_that_ran_leaves_its_record_its_graphs_and_its_decks(
    layout: Layout,
    engine: Engine,
    netlist: Netlist,
    models: ModelMap,
    runs: list[dict[str, Any]],
    run_result: RunResult,
) -> None:
    block("ladder", "Shunt Ladder")

    record = run_bench(DIVIDER, layout, engine, netlist, models)

    assert record == Record(
        block="ladder",
        block_title="Shunt Ladder",
        bench="divider",
        title="A divider at rest",
        covers="section 4.3",
        summary="The tap is read.",
        status=OK,
        tier="open",
        engine=run_result.version,
        library_sha256=run_result.library_sha256,
        figures=(Figure("tap", "Tap voltage", 2.5, "V", 2.5, 2.4, 2.6, "4.3"),),
        graphs=(("tap", "The tap", "divider.tap.png"), ("zoom", "The zoom", "divider.zoom.png")),
        notes=(NOTE,),
        models=(("Q1", "IRLML0030", "written here"), ("U1", "OPA365", "written here")),
        decks=("divider.at-rest.cir",),
    )
    folder = layout.results / "ladder"
    assert files_of(folder) == [
        "divider.at-rest.cir",
        "divider.json",
        "divider.tap.png",
        "divider.zoom.png",
    ]
    assert (folder / "divider.json").read_bytes() == dump_record(record).encode("utf-8")
    assert load_record((folder / "divider.json").read_text(encoding="utf-8")) == record
    assert (folder / "divider.at-rest.cir").read_bytes() == runs[0]["deck"].encode("utf-8")
    assert runs[0]["deck"].startswith("* Divider\n")
    assert (folder / "divider.tap.png").read_bytes().startswith(b"\x89PNG")
    assert [run["name"] for run in runs] == ["divider.at-rest", "divider.sweep-1"]


def test_a_bench_works_in_the_scratch_folder_of_its_block(
    layout: Layout, engine: Engine, netlist: Netlist, models: ModelMap, runs: list[dict[str, Any]]
) -> None:
    record = run_bench(DIVIDER, layout, engine, netlist, models)

    (context,) = SEEN
    assert context.engine == engine
    assert context.netlist is netlist
    assert context.models is models
    assert context.models_dir == layout.root / "models"
    assert context.workdir == layout.root / ".work" / "ladder"
    assert (context.prefix, context.tier) == ("divider", "open")
    assert runs[0]["workdir"] == layout.root / ".work" / "ladder"
    assert '.include "../../models/mosfets.lib"' in runs[0]["deck"]
    # A block that gave no title is shown under its name.
    assert record.block_title == "ladder"


def test_the_files_of_an_earlier_run_of_the_bench_are_removed(
    layout: Layout, engine: Engine, netlist: Netlist, models: ModelMap, runs: list[dict[str, Any]]
) -> None:
    folder = layout.results / "ladder"
    folder.mkdir(parents=True)
    stale = ["divider.json", "divider.spectrum.png", "divider.up-down.cir", "divider.notes.txt"]
    kept = ["divider.vendor.json", "divider-two.json", "other.json", "other.map.png", "README.md"]
    for name in (*stale, *kept):
        (folder / name).write_text("from an earlier run", encoding="utf-8")

    run_bench(DIVIDER, layout, engine, netlist, models)

    assert files_of(folder) == sorted(
        [*kept, "divider.at-rest.cir", "divider.json", "divider.tap.png", "divider.zoom.png"]
    )
    assert all(
        (folder / name).read_text(encoding="utf-8") == "from an earlier run" for name in kept
    )


def test_a_bench_that_cannot_run_leaves_a_record_that_says_why(
    layout: Layout, engine: Engine, netlist: Netlist, models: ModelMap, runs: list[dict[str, Any]]
) -> None:
    folder = layout.results / "ladder"
    folder.mkdir(parents=True)
    (folder / "connector.old.png").write_bytes(b"from an earlier run")
    entry = Bench("ladder", "connector", "The connector", "", "It has no model.", unmodeled)

    record = run_bench(entry, layout, engine, netlist, models)

    assert record == Record(
        block="ladder",
        block_title="ladder",
        bench="connector",
        title="The connector",
        covers="",
        summary="It has no model.",
        status=ERROR,
        error="J1 (Conn_01x02) has no model in the model map",
    )
    # The deck that ran before the bench broke is not filed with the results.
    assert files_of(folder) == ["connector.json"]
    assert load_record((folder / "connector.json").read_text(encoding="utf-8")) == record


def test_a_bench_whose_graph_cannot_be_drawn_leaves_a_record_that_says_why(
    layout: Layout, engine: Engine, netlist: Netlist, models: ModelMap, runs: list[dict[str, Any]]
) -> None:
    entry = Bench("ladder", "drawn", "A bench with a bad graph", "", "", badly_drawn)

    record = run_bench(entry, layout, engine, netlist, models)

    assert (record.status, record.error) == (ERROR, "the graph zoom has no panel 1")
    assert record.figures == ()
    # The graph that was drawn before the bad one does not stay behind.
    assert files_of(layout.results / "ladder") == ["drawn.json"]


def test_a_bench_with_a_defect_leaves_a_record_that_names_the_error(
    layout: Layout, engine: Engine, netlist: Netlist, models: ModelMap
) -> None:
    folder = layout.results / "ladder"
    folder.mkdir(parents=True)
    (folder / "ratio.old.png").write_bytes(b"from an earlier run")
    (folder / "other.json").write_text("of another bench", encoding="utf-8")
    entry = Bench("ladder", "ratio", "A defect", "section 4.3", "It divides.", defective)

    record = run_bench(entry, layout, engine, netlist, models)

    # One broken bench does not stop the run: it is on file as a bench that did not run.
    assert record == Record(
        block="ladder",
        block_title="ladder",
        bench="ratio",
        title="A defect",
        covers="section 4.3",
        summary="It divides.",
        status=ERROR,
        error="ZeroDivisionError: division by zero",
    )
    assert files_of(folder) == ["other.json", "ratio.json"]
    assert load_record((folder / "ratio.json").read_text(encoding="utf-8")) == record


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (KeyError("tran1/out"), "KeyError: 'tran1/out'"),
        (IndexError("index 0 is out of bounds for axis 0 with size 0"), "IndexError: index 0 is"),
        (TypeError("unsupported operand type(s)"), "TypeError: unsupported operand type(s)"),
        (RuntimeError(), "RuntimeError"),
        (AssertionError(), "AssertionError"),
    ],
)
def test_any_error_of_a_bench_is_named_with_its_kind_and_its_message(
    layout: Layout,
    engine: Engine,
    netlist: Netlist,
    models: ModelMap,
    error: Exception,
    message: str,
) -> None:
    def broken(ctx: Context) -> Outcome:
        raise error

    record = run_bench(
        Bench("ladder", "broken", "", "", "", broken), layout, engine, netlist, models
    )

    assert record.status == ERROR
    assert record.error.startswith(message)
    assert not record.error.endswith((":", " "))


def test_a_curve_that_cannot_be_plotted_leaves_a_record_too(
    layout: Layout, engine: Engine, netlist: Netlist, models: ModelMap
) -> None:
    def uneven(ctx: Context) -> Outcome:
        curve = Trace(np.array([0.0, 1.0]), np.array([0.0, 1.0, 2.0]), "three values on two")
        graph = Graph("curve", "A curve", "Step", (Panel("Tap (V)"),), (curve,))
        return Outcome((Figure("tap", "Tap voltage", 2.5, "V"),), (tap_graph("tap"), graph))

    record = run_bench(
        Bench("ladder", "uneven", "", "", "", uneven), layout, engine, netlist, models
    )

    assert record.status == ERROR
    assert record.error.startswith("ValueError: x and y must have same first dimension")
    assert files_of(layout.results / "ladder") == ["uneven.json"]


@pytest.mark.parametrize("stop", [KeyboardInterrupt, SystemExit])
def test_a_person_who_stops_the_run_is_not_taken_for_a_bench_that_broke(
    layout: Layout,
    engine: Engine,
    netlist: Netlist,
    models: ModelMap,
    stop: type[BaseException],
) -> None:
    def stopped(ctx: Context) -> Outcome:
        raise stop

    with pytest.raises(stop):
        run_bench(Bench("ladder", "stopped", "", "", "", stopped), layout, engine, netlist, models)

    assert files_of(layout.results / "ladder") == []


def test_the_record_that_a_run_returns_is_the_record_on_file(
    layout: Layout, engine: Engine, netlist: Netlist, models: ModelMap
) -> None:
    def close(ctx: Context) -> Outcome:
        return Outcome(
            (
                # 40 parts in a thousand million below its limit.
                Figure("gain", "Gain of the chain", 0.99899996, "", low=0.999),
                Figure("third", "A third", 1.0 / 3.0, "V", expected=1.0 / 3.0, high=0.33333334),
                Figure("ripple", "Ripple", 2.0e-3 / 3.0, "V", low=1e-3 / 3.0),
            )
        )

    record = run_bench(Bench("chain", "close", "", "", "", close), layout, engine, netlist, models)

    text = (layout.results / "chain" / "close.json").read_text(encoding="utf-8")
    assert load_record(text) == record
    # The figures are rounded to the digits on file before they are judged:
    # what the run prints, what the file holds and what the page shows agree.
    assert [figure.value for figure in record.figures] == [0.999, 0.3333333, 0.0006666667]
    assert (record.figures[1].expected, record.figures[1].high) == (0.3333333, 0.3333333)
    assert [figure.verdict for figure in record.figures] == ["pass", "pass", "pass"]
    assert record.counts() == (3, 0, 0)
    assert '"verdict": "fail"' not in text
    assert "| Gain of the chain | 0.999 | | at least 0.999 | pass | |" in block_page(
        "chain", "chain", [load_record(text)]
    )


def test_the_decks_of_a_sweep_that_a_bench_keeps_are_filed_with_its_results(
    layout: Layout, engine: Engine, netlist: Netlist, models: ModelMap, runs: list[dict[str, Any]]
) -> None:
    def rings(ctx: Context) -> Outcome:
        ctx.run_many({"ring-large": "* large\n.end\n", "ring-bare": "* bare\n.end\n"}, keep=True)
        ctx.run_many({"point-1": "* a point of a sweep\n.end\n"})
        return Outcome(())

    record = run_bench(Bench("chain", "rings", "", "", "", rings), layout, engine, netlist, models)

    folder = layout.results / "chain"
    assert record.decks == ("rings.ring-bare.cir", "rings.ring-large.cir")
    assert files_of(folder) == ["rings.json", "rings.ring-bare.cir", "rings.ring-large.cir"]
    assert (folder / "rings.ring-bare.cir").read_bytes() == b"* bare\n.end\n"
    assert len(runs) == 3


def test_a_vendor_run_files_its_figures_alone(
    layout: Layout,
    engine: Engine,
    netlist: Netlist,
    models: ModelMap,
    runs: list[dict[str, Any]],
    run_result: RunResult,
) -> None:
    (layout.models / "vendor").mkdir()
    (layout.models / "vendor" / "ti-opa365.lib").write_text(".SUBCKT OPA365_TI 1 2 3 4 5\n.ENDS\n")
    folder = layout.results / "ladder"
    folder.mkdir(parents=True)
    earlier = ["divider.json", "divider.tap.png", "divider.at-rest.cir", "divider.vendor.json"]
    for name in earlier:
        (folder / name).write_text("from an earlier run", encoding="utf-8")

    record = run_bench(DIVIDER, layout, engine, netlist, models, tier="vendor")

    assert (record.status, record.tier, record.error) == (OK, "vendor", "")
    assert record.figures == (Figure("tap", "Tap voltage", 2.5, "V", 2.5, 2.4, 2.6, "4.3"),)
    assert (record.graphs, record.decks) == ((), ())
    assert record.models == (("Q1", "IRLML0030", "written here"), ("U1", "OPA365_TI", "vendor"))
    assert record.engine == run_result.version
    # The files of the open tier stay as they are; only the vendor record is new.
    assert files_of(folder) == sorted(earlier)
    assert (folder / "divider.json").read_text(encoding="utf-8") == "from an earlier run"
    assert load_record((folder / "divider.vendor.json").read_text(encoding="utf-8")) == record
    (context,) = SEEN
    assert context.workdir == layout.root / ".work" / "vendor" / "ladder"
    assert context.tier == "vendor"
    assert runs[0]["pspice"] is True
    assert '.include "vendor/ti-opa365.lib"' in runs[0]["deck"]


def test_a_vendor_run_that_cannot_run_says_so_in_its_own_record(
    layout: Layout, engine: Engine, netlist: Netlist, models: ModelMap, runs: list[dict[str, Any]]
) -> None:
    record = run_bench(DIVIDER, layout, engine, netlist, models, tier="vendor")

    assert record.status == ERROR
    assert record.tier == "vendor"
    assert "vendor/ti-opa365.lib of the manufacturer is not present" in record.error
    assert files_of(layout.results / "ladder") == ["divider.vendor.json"]


def test_the_pages_are_written_from_the_records_on_file(
    layout: Layout, engine: Engine, netlist: Netlist, models: ModelMap, runs: list[dict[str, Any]]
) -> None:
    block("ladder", "Shunt Ladder")
    ladder = run_bench(DIVIDER, layout, engine, netlist, models)
    broken = run_bench(
        Bench("ladder", "connector", "The connector", "", "It has no model.", unmodeled),
        layout,
        engine,
        netlist,
        models,
    )
    chain = run_bench(
        dataclasses.replace(DIVIDER, block="chain", name="gain", title="The gain"),
        layout,
        engine,
        netlist,
        models,
    )

    written = write_report(layout)

    results = layout.results
    assert written == [
        results / "README.md",
        results / "chain" / "README.md",
        results / "ladder" / "README.md",
    ]
    assert (results / "ladder" / "README.md").read_bytes() == block_page(
        "ladder", "Shunt Ladder", [broken, ladder]
    ).encode("utf-8")
    assert (results / "chain" / "README.md").read_bytes() == block_page(
        "chain", "chain", [chain]
    ).encode("utf-8")
    assert (results / "README.md").read_text(encoding="utf-8").split("\n") == [
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
        "| Block | Bench | What is simulated | Pass | Fail | No limit |",
        "| --- | --- | --- | --- | --- | --- |",
        "| chain | [gain](chain/README.md) | The gain | 1 | 0 | 0 |",
        "| ladder | [connector](ladder/README.md) | The connector | did not run | | |",
        "| ladder | [divider](ladder/README.md) | A divider at rest | 1 | 0 | 0 |",
        "",
        "Simulator: ngspice-45.2 shared library.",
        "",
    ]
    assert b"\r" not in (results / "README.md").read_bytes()


def test_the_summary_names_every_build_of_the_simulator_behind_the_results(
    layout: Layout, engine: Engine, netlist: Netlist, models: ModelMap, runs: list[dict[str, Any]]
) -> None:
    record = run_bench(DIVIDER, layout, engine, netlist, models)
    older = dataclasses.replace(record, bench="older", engine="ngspice-42 shared library")
    (layout.results / "ladder" / "older.json").write_text(dump_record(older), encoding="utf-8")

    write_report(layout)

    summary = (layout.results / "README.md").read_text(encoding="utf-8")
    assert summary.endswith(
        "\nSimulator: ngspice-42 shared library, ngspice-45.2 shared library.\n"
    )


def test_a_summary_without_a_bench_that_ran_names_no_simulator(
    layout: Layout, engine: Engine, netlist: Netlist, models: ModelMap, runs: list[dict[str, Any]]
) -> None:
    layout.results.mkdir()

    assert write_report(layout) == [layout.results / "README.md"]
    assert (
        (layout.results / "README.md")
        .read_text(encoding="utf-8")
        .endswith("| --- | --- | --- | --- | --- | --- |\n")
    )

    run_bench(
        Bench("ladder", "connector", "The connector", "", "", unmodeled),
        layout,
        engine,
        netlist,
        models,
    )

    assert len(write_report(layout)) == 2
    assert (
        (layout.results / "README.md")
        .read_text(encoding="utf-8")
        .endswith("| The connector | did not run | | |\n")
    )


def test_a_result_file_that_is_broken_stops_the_report(layout: Layout) -> None:
    (layout.results / "ladder").mkdir(parents=True)
    (layout.results / "ladder" / "divider.json").write_text("{}", encoding="utf-8")

    with pytest.raises(BenchError, match="the result file has a format this package does not read"):
        write_report(layout)
