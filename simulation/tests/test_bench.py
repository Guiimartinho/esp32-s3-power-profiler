from __future__ import annotations

import dataclasses
import math
import sys
import threading
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from circuit_sim.bench import (
    FAIL,
    INFO,
    OPEN_TIER,
    PASS,
    VENDOR_TIER,
    Bench,
    Context,
    Figure,
    Graph,
    Outcome,
    Panel,
    Trace,
    bench,
    block,
    block_title,
    clear_registry,
    discover,
    near,
    registered,
)
from circuit_sim.circuit import ModelMap, PartModel, build_circuit
from circuit_sim.engine import Engine, RunResult
from circuit_sim.errors import BenchError, EngineError, ModelError
from circuit_sim.netlist import Netlist

BLOCK_PACKAGE = '''"""Benches of the ladder."""

from circuit_sim.bench import block

block("ladder", "Shunt Ladder")
'''

SHARED_MODULE = '''"""What the benches of the ladder share; it registers nothing."""

FULL_SCALE = 3e-3
'''

REST_MODULE = '''"""The ladder at rest."""

from benches.ladder import common
from circuit_sim.bench import Context, Figure, Outcome, bench


@bench("ladder", "rest", "The ladder at rest", "section 4.3")
def rest(ctx: Context) -> Outcome:
    """The ladder is held in one range.

    Its burden is read at full scale.
    """
    return Outcome((Figure("full_scale", "Full scale", common.FULL_SCALE, "A"),))
'''

GAIN_MODULE = '''"""The gain of the chain."""

from circuit_sim.bench import Context, Outcome, bench


@bench("chain", "gain", "The gain of the chain")
def gain(ctx: Context) -> Outcome:
    return Outcome(())
'''

TWICE_MODULE = '''"""Two benches under one name."""

from circuit_sim.bench import Context, Outcome, bench


@bench("ladder", "rest", "The first")
def first(ctx: Context) -> Outcome:
    return Outcome(())


@bench("ladder", "rest", "The second")
def second(ctx: Context) -> Outcome:
    return Outcome(())
'''


def nothing(ctx: Context) -> Outcome:
    """A bench that takes no figure."""
    return Outcome(())


def write_module(folder: Path, name: str, text: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


@pytest.fixture
def context(root: Path, engine: Engine, netlist: Netlist, models: ModelMap) -> Context:
    return Context(
        engine=engine,
        netlist=netlist,
        models=models,
        models_dir=root / "models",
        workdir=root / ".work" / "ladder",
        prefix="ranges",
    )


@pytest.mark.parametrize(
    ("value", "low", "high", "verdict"),
    [
        (2.5, None, None, INFO),
        (math.nan, None, None, INFO),
        (2.5, 2.4, 2.6, PASS),
        (2.4, 2.4, 2.6, PASS),
        (2.6, 2.4, 2.6, PASS),
        (2.39999, 2.4, 2.6, FAIL),
        (2.60001, 2.4, 2.6, FAIL),
        (5.0, 2.4, None, PASS),
        (2.0, 2.4, None, FAIL),
        (-5.0, None, 2.6, PASS),
        (3.0, None, 2.6, FAIL),
        (0.0, 0.0, 0.0, PASS),
    ],
)
def test_a_figure_is_judged_against_its_limits(
    value: float, low: float | None, high: float | None, verdict: str
) -> None:
    assert Figure("tap", "Tap voltage", value, "V", low=low, high=high).verdict == verdict
    assert (PASS, FAIL, INFO) == ("pass", "fail", "info")


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize(("low", "high"), [(2.4, 2.6), (2.4, None), (None, 2.6)])
def test_a_value_that_is_no_number_fails_whatever_its_limits_are(
    value: float, low: float | None, high: float | None
) -> None:
    assert Figure("tap", "Tap voltage", value, "V", low=low, high=high).verdict == FAIL


def test_a_figure_takes_the_values_that_numpy_gives() -> None:
    figure = Figure("tap", "Tap voltage", np.float64(2.5), "V", low=np.float64(2.4))

    assert figure.verdict == PASS
    assert Figure("tap", "Tap voltage", np.float64("nan"), "V", high=1.0).verdict == FAIL


@pytest.mark.parametrize(
    ("value", "expected", "deviation"),
    [
        (2.6, 2.5, 0.04),
        (2.4, 2.5, -0.04),
        (-2.6, -2.5, -0.04),
        (-2.4, -2.5, 0.04),
        (2.5, 2.5, 0.0),
    ],
)
def test_the_deviation_is_the_distance_from_the_expected_value_as_a_fraction_of_it(
    value: float, expected: float, deviation: float
) -> None:
    found = Figure("tap", "Tap voltage", value, "V", expected=expected).deviation

    assert found == pytest.approx(deviation, abs=1e-12)


def test_a_figure_without_an_expected_value_or_with_one_of_zero_has_no_deviation() -> None:
    assert Figure("tap", "Tap voltage", 2.5, "V").deviation is None
    assert Figure("offset", "Offset", 1e-6, "V", expected=0.0).deviation is None


@pytest.mark.parametrize(
    ("value", "expected", "verdict"),
    [
        (31.95, 31.95, PASS),
        (31.98, 31.95, PASS),
        (31.92, 31.95, PASS),
        (31.99, 31.95, FAIL),
        (31.91, 31.95, FAIL),
        (-4.004, -4.0, PASS),
        (-4.005, -4.0, FAIL),
        (-3.995, -4.0, FAIL),
    ],
)
def test_a_figure_near_its_expected_value(value: float, expected: float, verdict: str) -> None:
    figure = near("shunt", "Shunt", value, "ohm", expected, 0.001, "section 8")

    assert figure.verdict == verdict
    assert figure.expected == expected
    assert figure.low == pytest.approx(expected - abs(expected) * 0.001)
    assert figure.high == pytest.approx(expected + abs(expected) * 0.001)
    assert (figure.key, figure.label, figure.unit, figure.source) == (
        "shunt",
        "Shunt",
        "ohm",
        "section 8",
    )
    assert near("shunt", "Shunt", value, "ohm", expected, 0.001).source == ""


def test_the_value_objects_of_a_bench_cannot_be_changed() -> None:
    figure = Figure("tap", "Tap voltage", 2.5, "V")
    trace = Trace(np.array([0.0, 1.0]), np.array([0.0, 2.0]), "tap")
    panel = Panel("Voltage (V)")
    graph = Graph("map", "A map", "Time (s)", (panel,), (trace,))
    outcome = Outcome((figure,))

    assert (figure.expected, figure.low, figure.high, figure.source) == (None, None, None, "")
    assert (trace.panel, trace.style) == (0, "-")
    assert (panel.log, panel.marks) == (False, ())
    assert (graph.logx, graph.xmarks) == (False, ())
    assert (outcome.graphs, outcome.notes) == ((), ())
    for thing, field in ((figure, "value"), (trace, "label"), (panel, "log"), (graph, "name")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(thing, field, 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.notes = ("changed",)  # type: ignore[misc]


def test_a_bench_registers_itself_with_what_its_function_says() -> None:
    @bench("ladder", "rest", "The ladder at rest", "section 4.3")
    def rest(ctx: Context) -> Outcome:
        """The ladder is held in one range.

        Its burden is read   at full scale.
        """
        return Outcome(())

    (entry,) = registered()

    assert entry == Bench(
        block="ladder",
        name="rest",
        title="The ladder at rest",
        covers="section 4.3",
        summary="The ladder is held in one range. Its burden is read at full scale.",
        run=rest,
    )
    assert entry.ident == "ladder/rest"
    # The decorator hands the function back as it was.
    assert rest.__name__ == "rest"


def test_a_bench_without_a_docstring_or_a_cover_has_an_empty_summary() -> None:
    def bare(ctx: Context) -> Outcome:
        return Outcome(())

    bench("chain", "bare", "A bare bench")(bare)

    assert (registered()[0].summary, registered()[0].covers) == ("", "")


def test_the_benches_come_by_block_and_name() -> None:
    for block_name, name in (
        ("ladder", "rest"),
        ("chain", "noise"),
        ("ladder", "change"),
        ("chain", "gain"),
    ):
        bench(block_name, name, "A bench")(lambda ctx: Outcome(()))

    assert [entry.ident for entry in registered()] == [
        "chain/gain",
        "chain/noise",
        "ladder/change",
        "ladder/rest",
    ]


def test_two_benches_of_one_name_are_refused() -> None:
    bench("ladder", "rest", "The first")(nothing)

    with pytest.raises(BenchError, match="two benches are named ladder/rest"):
        bench("ladder", "rest", "The second")(lambda ctx: Outcome(()))

    assert registered()[0].title == "The first"


@pytest.mark.parametrize(
    ("block_name", "name"),
    [
        ("ladder", "rest"),
        ("range_logic", "load-step"),
        ("models", "mosfet-csd17577q3a"),
        ("output_stage2", "on-resistance"),
        ("a", "1"),
    ],
)
def test_a_block_and_a_bench_are_named_in_lower_case_letters_and_digits(
    block_name: str, name: str
) -> None:
    bench(block_name, name, "A bench")(nothing)

    assert registered()[0].ident == f"{block_name}/{name}"


@pytest.mark.parametrize(
    "block_name", ["Ladder", "shunt-ladder", "shunt ladder", "ladder.rest", "ladder/x", "", "größe"]
)
def test_a_block_that_is_not_lower_case_letters_digits_and_underscores_is_refused(
    block_name: str,
) -> None:
    with pytest.raises(BenchError) as refused:
        bench(block_name, "rest", "A bench")

    assert str(refused.value) == (
        f"the block {block_name!r} of the bench 'rest' has to be named in lower case letters, "
        "digits and underscores"
    )
    assert registered() == ()


@pytest.mark.parametrize(
    "name", ["Rest", "at_rest", "at rest", "r0.5v", "rest.vendor", "ladder/rest", "", "größe"]
)
def test_a_bench_that_is_not_lower_case_letters_digits_and_hyphens_is_refused(name: str) -> None:
    # The name is the start of the file names of the bench: a dot in it
    # would make its files look like those of another bench.
    with pytest.raises(BenchError) as refused:
        bench("ladder", name, "A bench")

    assert str(refused.value) == (
        f"the bench {name!r} of the block 'ladder' has to be named in lower case letters, "
        "digits and hyphens"
    )
    assert registered() == ()


def test_the_same_function_may_register_again() -> None:
    bench("ladder", "rest", "The first title")(nothing)
    bench("ladder", "rest", "A better title")(nothing)
    bench("chain", "rest", "The same name in another block")(nothing)

    assert [(entry.ident, entry.title) for entry in registered()] == [
        ("chain/rest", "The same name in another block"),
        ("ladder/rest", "A better title"),
    ]


def test_a_block_has_the_title_it_gave_or_its_name() -> None:
    block("ladder", "Shunt Ladder")

    assert block_title("ladder") == "Shunt Ladder"
    assert block_title("chain") == "chain"

    block("ladder", "The Ladder")

    assert block_title("ladder") == "The Ladder"


def test_the_registry_can_be_emptied() -> None:
    block("ladder", "Shunt Ladder")
    bench("ladder", "rest", "The ladder at rest")(nothing)

    clear_registry()

    assert registered() == ()
    assert block_title("ladder") == "ladder"


def test_the_bench_modules_of_a_folder_are_found(root: Path, bench_imports: None) -> None:
    benches = root / "benches"
    write_module(benches / "ladder", "__init__.py", BLOCK_PACKAGE)
    write_module(benches / "ladder", "common.py", SHARED_MODULE)
    write_module(benches / "ladder", "rest.py", REST_MODULE)
    # A block without a package file of its own is found too.
    write_module(benches / "chain", "gain.py", GAIN_MODULE)

    found = discover(benches)

    assert [entry.ident for entry in found] == ["chain/gain", "ladder/rest"]
    assert found == registered()
    assert found[1].title == "The ladder at rest"
    assert found[1].covers == "section 4.3"
    assert found[1].summary == "The ladder is held in one range. Its burden is read at full scale."
    assert (block_title("ladder"), block_title("chain")) == ("Shunt Ladder", "chain")
    assert sorted(name for name in sys.modules if name.startswith("benches")) == [
        "benches",
        "benches.chain",
        "benches.chain.gain",
        "benches.ladder",
        "benches.ladder.common",
        "benches.ladder.rest",
    ]


def test_the_folder_above_the_benches_goes_on_the_search_path_once(
    root: Path, bench_imports: None
) -> None:
    benches = root / "benches"
    write_module(benches / "ladder", "rest.py", REST_MODULE)
    write_module(benches / "ladder", "common.py", SHARED_MODULE)
    before = list(sys.path)

    first = discover(benches)
    second = discover(benches)

    # The modules of a block import each other through that entry.
    assert sys.path == [str(root.resolve()), *before]
    assert second == first
    assert [entry.ident for entry in second] == ["ladder/rest"]


def test_a_folder_that_is_no_package_of_benches_is_refused(root: Path, bench_imports: None) -> None:
    (root / "benches" / "__init__.py").unlink()
    before = list(sys.path)

    with pytest.raises(BenchError, match=r"benches is not a package of benches \(no __init__.py\)"):
        discover(root / "benches")
    with pytest.raises(BenchError, match="is not a package of benches"):
        discover(root / "missing")

    assert sys.path == before


def test_a_bench_module_that_fails_to_import_is_named(root: Path, bench_imports: None) -> None:
    write_module(root / "benches" / "ladder", "broken.py", "FULL_SCALE = undefined_name\n")

    with pytest.raises(
        BenchError,
        match=r"cannot import the bench module benches\.ladder\.broken: NameError\(",
    ):
        discover(root / "benches")


def test_two_benches_of_one_name_in_a_folder_stop_the_discovery(
    root: Path, bench_imports: None
) -> None:
    write_module(root / "benches" / "ladder", "twice.py", TWICE_MODULE)

    with pytest.raises(
        BenchError,
        match=r"cannot import the bench module benches\.ladder\.twice: "
        r"BenchError\('two benches are named ladder/rest'\)",
    ):
        discover(root / "benches")


def test_a_context_builds_its_circuits_from_the_schematic(
    context: Context, netlist: Netlist, models: ModelMap
) -> None:
    aliases = {"/Ladder/SUPPLY": "supply"}
    overrides = {"R2": PartModel("resistor", params="tc1=1e-5")}
    scales = {"R1": 1.001}

    circuit = context.circuit(["R1", "R2", "Q1"], aliases, overrides, scales)

    assert circuit == build_circuit(netlist, models, ["R1", "R2", "Q1"], aliases, overrides, scales)
    assert circuit.lines == (
        "MQ1 supply n_q1_g n_q1_s IRLML0030",
        "R1 supply ladder_vout_s 1001",
        "R2 n_q1_s ladder_vout_s 33 tc1=1e-5",
    )
    assert context.tier == OPEN_TIER


def test_a_context_remembers_the_models_of_its_circuits(context: Context) -> None:
    context.circuit(["Q1", "R1"])
    context.circuit(["Q1", "Q2", "U1"])
    context.circuit(["C1"])

    assert context.origins == {
        ("Q1", "IRLML0030", "written here"),
        ("Q2", "IRLML0030", "written here"),
        ("U1", "OPA365", "written here"),
    }


def test_the_vendor_tier_takes_the_models_of_the_manufacturers_and_their_dialect(
    context: Context, runs: list[dict[str, Any]]
) -> None:
    vendor = dataclasses.replace(context, tier=VENDOR_TIER, origins=set(), kept={})

    context.circuit(["U1", "Q1"])
    context.run("open", "* deck\n.end\n")
    vendor.circuit(["Q1"])
    vendor.run("before", "* deck\n.end\n")
    circuit = vendor.circuit(["U1", "Q1"])
    vendor.run("after", "* deck\n.end\n")

    assert circuit.lines[1] == "XU1 n_u1_p n_u1_n p12v_a m4v_a chain_amp_out OPA365_TI"
    assert ("U1", "OPA365_TI", "vendor") in vendor.origins
    # The compatibility mode goes on with the first model of a manufacturer.
    assert [(run["name"], run["pspice"]) for run in runs] == [
        ("ranges.open", False),
        ("ranges.before", False),
        ("ranges.after", True),
    ]


def test_a_model_of_a_manufacturer_given_for_one_part_turns_the_dialect_on(
    context: Context, runs: list[dict[str, Any]]
) -> None:
    theirs = PartModel("subckt", name="OPA365_TI", ports=("3", "4", "1"), origin="vendor")

    context.circuit(["U1"], overrides={"U1": theirs})
    context.run("mixed", "* deck\n.end\n")

    assert runs[0]["pspice"] is True


def test_a_deck_is_put_together_in_order(context: Context) -> None:
    circuit = context.circuit(["R1", "C1", "Q1"], {"/Ladder/SUPPLY": "supply"})
    stimulus = "* the source meter as an ideal source\nVsupply supply 0 5\n\n"

    deck = context.deck(
        "Ladder at rest",
        circuit,
        stimulus,
        "Iload ladder_vout_s 0 1m",
        control=["op", "print all"],
        options=("gmin=1e-15", "abstol=1e-15"),
    )

    assert deck == "\n".join(
        [
            "* Ladder at rest",
            '.include "../../models/mosfets.lib"',
            "C1 supply 0 1e-07",
            "MQ1 supply n_q1_g n_q1_s IRLML0030",
            "R1 supply ladder_vout_s 1000",
            "* the source meter as an ideal source",
            "Vsupply supply 0 5",
            "Iload ladder_vout_s 0 1m",
            ".options gmin=1e-15",
            ".options abstol=1e-15",
            ".control",
            "op",
            "print all",
            ".endc",
            ".end",
            "",
        ]
    )


def test_a_deck_without_a_circuit_is_its_lines_and_its_analysis(context: Context) -> None:
    deck = context.deck("A divider", "V1 in 0 10\nR1 in out 3k\nR2 out 0 1k", control=[])

    assert deck == "* A divider\nV1 in 0 10\nR1 in out 3k\nR2 out 0 1k\n.control\n.endc\n.end\n"


def test_a_deck_includes_every_model_file_once(context: Context) -> None:
    switches = context.circuit(["Q1", "Q2"])
    amplifier = context.circuit(["U1", "D1", "Q1"])

    deck = context.deck(
        "Front end",
        switches,
        amplifier,
        control=["op"],
        libraries=("logic.lib", "sequencer.lib", "logic.lib", "opamps.lib"),
    )

    # The files asked for by name first, then those of the circuits as they come.
    assert [line for line in deck.splitlines() if line.startswith(".include")] == [
        '.include "../../models/logic.lib"',
        '.include "../../models/sequencer.lib"',
        '.include "../../models/opamps.lib"',
        '.include "../../models/mosfets.lib"',
        '.include "../../models/diodes.lib"',
    ]


def test_a_deck_reads_the_file_of_a_manufacturer_through_a_copy_beside_it(
    root: Path, context: Context
) -> None:
    (root / "models" / "vendor").mkdir()
    source = root / "models" / "vendor" / "ti-opa365.lib"
    source.write_text(
        "\t.SUBCKT OPA365_TI 1 2 3 4 5\n  .PARAM GBW 50MEG\n.ENDS\n", encoding="utf-8"
    )
    vendor = dataclasses.replace(
        context, tier=VENDOR_TIER, workdir=root / ".work" / "vendor" / "chain"
    )

    deck = vendor.deck("Amplifier", vendor.circuit(["U1", "Q1"]), control=["op"])

    assert deck.splitlines()[1:3] == [
        '.include "../../../models/mosfets.lib"',
        '.include "vendor/ti-opa365.lib"',
    ]
    copy = root / ".work" / "vendor" / "chain" / "vendor" / "ti-opa365.lib"
    assert (
        copy.read_text(encoding="utf-8") == ".SUBCKT OPA365_TI 1 2 3 4 5\n.PARAM GBW=50MEG\n.ENDS\n"
    )
    assert source.read_text(encoding="utf-8").startswith("\t.SUBCKT")


def test_a_deck_that_needs_a_file_of_a_manufacturer_that_is_not_there_is_an_error(
    context: Context,
) -> None:
    vendor = dataclasses.replace(context, tier=VENDOR_TIER)

    with pytest.raises(
        ModelError, match=r"the model file vendor/ti-opa365\.lib of the manufacturer is not present"
    ):
        vendor.deck("Amplifier", vendor.circuit(["U1"]), control=["op"])
    with pytest.raises(ModelError, match=r"vendor/other\.lib of the manufacturer is not present"):
        context.deck("Amplifier", control=["op"], libraries=("vendor/other.lib",))


def test_a_deck_runs_under_the_name_of_its_bench_and_is_kept(
    root: Path, context: Context, engine: Engine, runs: list[dict[str, Any]], run_result: RunResult
) -> None:
    result = context.run("r0-5v", "* first\n.end\n")
    context.run("r1-5v", "* second\n.end\n", allowed=["model issue"])

    assert result is run_result
    assert runs == [
        {
            "engine": engine,
            "deck": "* first\n.end\n",
            "workdir": root / ".work" / "ladder",
            "name": "ranges.r0-5v",
            "pspice": False,
            "allowed": (),
        },
        {
            "engine": engine,
            "deck": "* second\n.end\n",
            "workdir": root / ".work" / "ladder",
            "name": "ranges.r1-5v",
            "pspice": False,
            "allowed": ["model issue"],
        },
    ]
    assert context.kept == {
        "ranges.r0-5v.cir": "* first\n.end\n",
        "ranges.r1-5v.cir": "* second\n.end\n",
    }


def test_a_context_knows_the_simulator_after_its_first_run(
    context: Context, runs: list[dict[str, Any]], run_result: RunResult
) -> None:
    assert (context.engine_version, context.library_sha256) == ("", "")

    context.run("r0", "* deck\n.end\n")

    assert context.engine_version == run_result.version == "ngspice-45.2 shared library"
    assert context.library_sha256 == run_result.library_sha256


def test_a_deck_of_a_sweep_can_be_left_out_of_the_results(
    context: Context, runs: list[dict[str, Any]]
) -> None:
    context.run("point-17", "* deck\n.end\n", keep=False)

    assert context.kept == {}
    assert runs[0]["name"] == "ranges.point-17"


def test_a_run_that_fails_is_not_swallowed(
    context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run_deck(*arguments: Any, **options: Any) -> RunResult:
        raise EngineError("ranges.r0: the run failed: singular matrix")

    monkeypatch.setattr("circuit_sim.bench.run_deck", run_deck)

    with pytest.raises(EngineError, match="singular matrix"):
        context.run("r0", "* deck\n.end\n")
    with pytest.raises(EngineError, match="singular matrix"):
        context.run_many({"a": "* a\n.end\n", "b": "* b\n.end\n"})
    assert context.engine_version == ""


def test_the_decks_of_a_sweep_run_side_by_side_and_none_is_kept(
    context: Context, monkeypatch: pytest.MonkeyPatch, run_result: RunResult
) -> None:
    together = threading.Barrier(3, timeout=20.0)
    asked: list[tuple[str, Any]] = []

    def run_deck(engine: Engine, deck: str, workdir: Path, name: str, **options: Any) -> RunResult:
        # Three decks have to be under way at once to get past this point.
        together.wait()
        asked.append((name, options["allowed"]))
        return dataclasses.replace(run_result, log=(deck,))

    monkeypatch.setattr("circuit_sim.bench.run_deck", run_deck)
    decks = {f"point-{number}": f"* deck {number}\n.end\n" for number in (3, 1, 2)}

    results = context.run_many(decks, allowed=["harmless"])

    assert list(results) == ["point-3", "point-1", "point-2"]
    assert {name: result.log for name, result in results.items()} == {
        name: (deck,) for name, deck in decks.items()
    }
    assert sorted(asked) == [(f"ranges.point-{number}", ["harmless"]) for number in (1, 2, 3)]
    assert context.kept == {}
    assert context.engine_version == run_result.version
    assert context.run_many({}) == {}


def test_the_decks_of_a_sweep_are_kept_with_the_results_when_asked(
    context: Context, runs: list[dict[str, Any]]
) -> None:
    decks = {f"ring-{key}": f"* deck {key}\n.end\n" for key in ("large", "assumed", "bare")}
    context.run("rest", "* at rest\n.end\n")

    results = context.run_many(decks, keep=True, allowed=["harmless"])
    context.run_many({"point-1": "* a point\n.end\n"})

    # Like the decks of single runs, under the name of the bench, in the
    # order in which they were given whichever run ends first.
    assert context.kept == {
        "ranges.rest.cir": "* at rest\n.end\n",
        "ranges.ring-large.cir": "* deck large\n.end\n",
        "ranges.ring-assumed.cir": "* deck assumed\n.end\n",
        "ranges.ring-bare.cir": "* deck bare\n.end\n",
    }
    assert list(context.kept) == [
        "ranges.rest.cir",
        "ranges.ring-large.cir",
        "ranges.ring-assumed.cir",
        "ranges.ring-bare.cir",
    ]
    assert list(results) == ["ring-large", "ring-assumed", "ring-bare"]
    assert sorted(run["name"] for run in runs) == [
        "ranges.point-1",
        "ranges.rest",
        "ranges.ring-assumed",
        "ranges.ring-bare",
        "ranges.ring-large",
    ]
    assert {run["name"]: run["allowed"] for run in runs}["ranges.ring-bare"] == ["harmless"]


@pytest.mark.needs_ngspice
def test_a_circuit_of_the_schematic_runs_in_ngspice_with_the_model_file_it_names(
    root: Path, ngspice: Engine, context: Context
) -> None:
    # Range 1 of the small ladder: 33 ohm behind a switch, beside the 1 kohm
    # that is always there. A load of 1 mA sees the two in parallel.
    (root / "models" / "mosfets.lib").write_text(
        "* a switch of a few milliohm, with three pins as the model map names them\n"
        ".model IRLML0030 VDMOS(VTO=1.7 KP=20)\n",
        encoding="utf-8",
    )
    real = dataclasses.replace(context, engine=ngspice, prefix="rest")
    aliases = {"/Ladder/SUPPLY": "supply", "/Ladder/VOUT_S": "vout_s", "Net-(Q1-G)": "gate"}
    circuit = real.circuit(["R1", "R2", "Q1"], aliases)
    deck = real.deck(
        "Range 1 at rest",
        circuit,
        "Vsupply supply 0 5\nVgate gate 0 12\nIload vout_s 0 1m",
        control=["op"],
    )

    result = real.run("r1", deck)
    sweep = real.run_many(
        {f"load-{milliamps}": deck.replace("0 1m", f"0 {milliamps}m") for milliamps in (1, 2, 3)}
    )

    burden = float(result.real("supply")[0] - result.real("vout_s")[0])
    shunt = 1000.0 * 33.0 / 1033.0
    assert burden == pytest.approx(1e-3 * shunt, rel=2e-3)
    assert float(result.real("vsupply#branch")[0]) == pytest.approx(-1e-3, rel=1e-4)
    assert [
        float(run.real("supply")[0] - run.real("vout_s")[0]) for run in sweep.values()
    ] == pytest.approx([1e-3 * shunt, 2e-3 * shunt, 3e-3 * shunt], rel=2e-3)
    assert real.engine_version.startswith("ngspice-")
    assert len(real.library_sha256) == 64
    assert list(real.kept) == ["rest.r1.cir"]
    assert (root / ".work" / "ladder" / "rest.r1.cir").read_text(encoding="utf-8") == deck
    assert (root / ".work" / "ladder" / "rest.load-3.cir").is_file()


@pytest.mark.needs_ngspice
def test_a_file_of_a_manufacturer_runs_in_ngspice_through_its_copy(
    root: Path, ngspice: Engine, context: Context
) -> None:
    # A divider as a manufacturer might write it: a tab, a line that starts
    # with blanks, a parameter without its equals sign.
    (root / "models" / "vendor").mkdir()
    (root / "models" / "vendor" / "divider.lib").write_text(
        "* a divider\n\t.SUBCKT DIVIDER top tap\n  .PARAM RTOP 3k\n"
        "R1\ttop\ttap\t{RTOP}\n  R2 tap 0 1k\n.ENDS\n",
        encoding="utf-8",
    )
    real = dataclasses.replace(context, engine=ngspice, prefix="vendor")

    deck = real.deck(
        "A divider of a manufacturer",
        "V1 in 0 10\nX1 in out DIVIDER",
        control=["op"],
        libraries=("vendor/divider.lib",),
    )
    result = real.run("divider", deck)

    assert '.include "vendor/divider.lib"' in deck
    assert result.real("out") == pytest.approx([2.5], rel=1e-6)
