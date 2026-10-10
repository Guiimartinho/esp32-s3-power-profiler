from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from circuit_sim import __version__
from circuit_sim.cli import main
from circuit_sim.engine import Engine
from circuit_sim.errors import EngineError
from circuit_sim.netlist import dump_snapshot, snapshot_from_kicad_xml
from circuit_sim.report import load_record

OHM = "Ω"

LADDER_PACKAGE = '''"""Benches of the ladder."""

from circuit_sim.bench import block

block("ladder", "Shunt Ladder")
'''

DIVIDER = '''"""The ladder at rest."""

from circuit_sim.bench import Context, Figure, Outcome, bench


@bench("ladder", "divider", "A divider at rest", "section 4.3")
def divider(ctx: Context) -> Outcome:
    """The divider is read at its tap."""
    result = ctx.run("at-rest", ctx.deck("Divider", ctx.circuit(["R1", "U1"]), control=["op"]))
    tap = float(result.real("out")[0])
    return Outcome(
        (
            Figure("tap", "Tap voltage", tap, "V", expected=2.5, low=2.4, high=2.6),
            Figure("shunt", "Shunt seen by the amplifier", 31.95, "ohm"),
        )
    )
'''

LIMITS = '''"""A figure outside its limit."""

from circuit_sim.bench import Context, Figure, Outcome, bench


@bench("ladder", "limits", "The burden of range 3")
def limits(ctx: Context) -> Outcome:
    return Outcome(
        (
            Figure("burden", "Burden at 1 A", 0.1085, "V", expected=0.106, high=0.107),
            Figure("floor", "A figure inside its limit", 1.0, "V", low=0.5),
        )
    )
'''

GAIN = '''"""The gain of the chain."""

from circuit_sim.bench import Context, Outcome, bench


@bench("chain", "gain", "The gain of the chain")
def gain(ctx: Context) -> Outcome:
    return Outcome(())
'''

CONNECTOR = '''"""A part without a model."""

from circuit_sim.bench import Context, Outcome, bench


@bench("chain", "connector", "The connector of the output")
def connector(ctx: Context) -> Outcome:
    ctx.circuit(["J1"])
    return Outcome(())
'''

DEFECT = '''"""A bench with a defect."""

from circuit_sim.bench import Context, Figure, Outcome, bench


@bench("chain", "defect", "A bench that divides by zero")
def defect(ctx: Context) -> Outcome:
    return Outcome((Figure("ratio", "A ratio", 1 / len(ctx.kept), ""),))
'''

EXPORT = """<?xml version="1.0" encoding="UTF-8"?>
<export version="E">
  <design>
    <sheet number="1" name="/" tstamps="/">
      <title_block>
        <title>A Divider</title>
        <rev>T2</rev>
      </title_block>
    </sheet>
  </design>
  <components>
    <comp ref="R2">
      <value>1k</value>
      <sheetpath names="/" tstamps="/"/>
    </comp>
    <comp ref="R1">
      <value>3k</value>
      <sheetpath names="/" tstamps="/"/>
    </comp>
  </components>
  <nets>
    <net code="1" name="/TAP">
      <node ref="R1" pin="2" pintype="passive"/>
      <node ref="R2" pin="1" pintype="passive"/>
    </net>
    <net code="2" name="GND">
      <node ref="R2" pin="2" pintype="passive"/>
    </net>
    <net code="3" name="/IN">
      <node ref="R1" pin="1" pintype="passive"/>
    </net>
  </nets>
</export>
"""


def write_bench(root: Path, block: str, name: str, text: str) -> None:
    folder = root / "benches" / block
    folder.mkdir(exist_ok=True)
    (folder / f"{name}.py").write_text(text, encoding="utf-8")


@pytest.fixture
def simulations(
    root: Path, bench_imports: None, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A folder of simulations with two benches of the ladder and a simulator that is found."""
    write_bench(root, "ladder", "__init__", LADDER_PACKAGE)
    write_bench(root, "ladder", "divider", DIVIDER)
    write_bench(root, "ladder", "limits", LIMITS)
    monkeypatch.setattr("circuit_sim.cli.default_engine", lambda: engine)
    return root


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
    assert capsys.readouterr().out.strip() == f"circuit-sim {__version__}"


def test_the_module_can_be_run_as_a_program() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "circuit_sim.cli", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert (done.returncode, done.stdout.strip()) == (0, f"circuit-sim {__version__}")


def test_a_command_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    assert "required" in usage_error(capsys)


def test_an_unknown_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert "invalid choice" in usage_error(capsys, "simulate")


def test_a_tier_that_does_not_exist_is_a_usage_error(
    capsys: pytest.CaptureFixture[str], simulations: Path
) -> None:
    assert "--tier" in usage_error(capsys, "--root", simulations, "run", "--tier", "fast")


def test_list_names_every_bench(capsys: pytest.CaptureFixture[str], simulations: Path) -> None:
    write_bench(simulations, "chain", "gain", GAIN)

    status, out, err = run(capsys, "--root", simulations, "list")

    assert (status, err) == (0, "")
    assert out.splitlines() == [
        f"{'chain/gain':42} The gain of the chain",
        f"{'ladder/divider':42} A divider at rest",
        f"{'ladder/limits':42} The burden of range 3",
    ]


def test_the_folder_of_the_simulations_is_the_current_one_by_default(
    capsys: pytest.CaptureFixture[str], simulations: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(simulations)

    status, out, _ = run(capsys, "list")

    assert status == 0
    assert [line.split()[0] for line in out.splitlines()] == ["ladder/divider", "ladder/limits"]


def test_a_folder_without_benches_is_reported(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, bench_imports: None
) -> None:
    status, out, err = run(capsys, "--root", tmp_path, "list")

    assert (status, out) == (2, "")
    assert err.startswith("circuit-sim: ")
    assert err.rstrip().endswith("benches is not a package of benches (no __init__.py)")


def test_run_runs_every_bench_and_files_its_results(
    capsys: pytest.CaptureFixture[str], simulations: Path, runs: list[dict[str, Any]]
) -> None:
    status, out, err = run(capsys, "--root", simulations, "run")

    assert (status, err) == (0, "")
    assert out.splitlines() == [
        "ladder/divider: 1 pass, 0 fail, 1 without limit",
        "ladder/limits: 1 pass, 1 fail, 0 without limit",
        "  FAIL Burden at 1 A: 108.5 mV (spec 106 mV)",
    ]
    results = simulations / "results"
    assert sorted(path.name for path in (results / "ladder").iterdir()) == [
        "README.md",
        "divider.at-rest.cir",
        "divider.json",
        "limits.json",
    ]
    assert (results / "README.md").is_file()
    assert [run["name"] for run in runs] == ["divider.at-rest"]
    assert runs[0]["workdir"] == simulations.resolve() / ".work" / "ladder"
    page = (results / "ladder" / "README.md").read_text(encoding="utf-8")
    assert page.startswith("# Simulation Results: Shunt Ladder\n")
    assert "| Burden at 1 A | 108.5 mV | 106 mV (+2.36 %) | at most 107 mV | **FAIL** | |" in page


def test_run_prints_every_figure_when_asked(
    capsys: pytest.CaptureFixture[str], simulations: Path, runs: list[dict[str, Any]]
) -> None:
    status, out, _ = run(capsys, "--root", simulations, "run", "-v")

    assert status == 0
    assert out.splitlines() == [
        "ladder/divider: 1 pass, 0 fail, 1 without limit",
        "       Tap voltage: 2.5 V (spec 2.5 V)",
        f"       Shunt seen by the amplifier: 31.95 {OHM}",
        "ladder/limits: 1 pass, 1 fail, 0 without limit",
        "  FAIL Burden at 1 A: 108.5 mV (spec 106 mV)",
        "       A figure inside its limit: 1 V",
    ]
    assert run(capsys, "--root", simulations, "run", "--verbose")[1] == out


def test_run_takes_the_benches_of_a_block_or_single_benches(
    capsys: pytest.CaptureFixture[str], simulations: Path, runs: list[dict[str, Any]]
) -> None:
    write_bench(simulations, "chain", "gain", GAIN)

    by_block = run(capsys, "--root", simulations, "run", "chain")
    by_name = run(capsys, "--root", simulations, "run", "ladder/divider")
    both = run(capsys, "--root", simulations, "run", "ladder/limits", "chain", "chain/gain")

    assert by_block[:2] == (0, "chain/gain: 0 pass, 0 fail, 0 without limit\n")
    assert by_name[:2] == (0, "ladder/divider: 1 pass, 0 fail, 1 without limit\n")
    assert [line.split(":")[0] for line in both[1].splitlines()] == [
        "chain/gain",
        "ladder/limits",
        "  FAIL Burden at 1 A",
    ]


def test_run_refuses_a_name_that_is_no_block_and_no_bench(
    capsys: pytest.CaptureFixture[str], simulations: Path, runs: list[dict[str, Any]]
) -> None:
    status, out, err = run(
        capsys, "--root", simulations, "run", "ladder", "chain", "ladder/missing", "divider"
    )

    assert (status, out) == (2, "")
    assert err == "circuit-sim: no block or bench is named chain, ladder/missing, divider\n"
    assert runs == []
    assert not (simulations / "results").exists()


def test_a_figure_outside_its_limit_fails_the_command_only_when_asked(
    capsys: pytest.CaptureFixture[str], simulations: Path, runs: list[dict[str, Any]]
) -> None:
    assert run(capsys, "--root", simulations, "run")[0] == 0
    assert run(capsys, "--root", simulations, "run", "--strict")[0] == 2
    assert run(capsys, "--root", simulations, "run", "--strict", "ladder/divider")[0] == 0


def test_a_bench_that_could_not_run_fails_the_command(
    capsys: pytest.CaptureFixture[str], simulations: Path, runs: list[dict[str, Any]]
) -> None:
    write_bench(simulations, "chain", "connector", CONNECTOR)

    status, out, err = run(capsys, "--root", simulations, "run", "--strict")

    assert (status, err) == (1, "")
    assert out.splitlines() == [
        "chain/connector: DID NOT RUN: J1 (Conn_01x02) has no model in the model map",
        "ladder/divider: 1 pass, 0 fail, 1 without limit",
        "ladder/limits: 1 pass, 1 fail, 0 without limit",
        "  FAIL Burden at 1 A: 108.5 mV (spec 106 mV)",
    ]
    # The benches after the broken one ran, and the pages say what happened.
    summary = (simulations / "results" / "README.md").read_text(encoding="utf-8")
    assert (
        "| chain | [connector](chain/README.md) | The connector of the output | did not run | | |"
        in summary
    )
    assert run(capsys, "--root", simulations, "run", "chain")[0] == 1


def test_a_bench_with_a_defect_does_not_hide_the_others(
    capsys: pytest.CaptureFixture[str], simulations: Path, runs: list[dict[str, Any]]
) -> None:
    write_bench(simulations, "chain", "defect", DEFECT)

    status, out, err = run(capsys, "--root", simulations, "run")

    assert (status, err) == (1, "")
    assert out.splitlines() == [
        "chain/defect: DID NOT RUN: ZeroDivisionError: division by zero",
        "ladder/divider: 1 pass, 0 fail, 1 without limit",
        "ladder/limits: 1 pass, 1 fail, 0 without limit",
        "  FAIL Burden at 1 A: 108.5 mV (spec 106 mV)",
    ]
    page = (simulations / "results" / "chain" / "README.md").read_text(encoding="utf-8")
    assert page.split("\n")[6:] == [
        "## `chain/defect`",
        "",
        "**A bench that divides by zero.**",
        "",
        "**The bench did not run:** ZeroDivisionError: division by zero",
        "",
    ]


def test_run_can_leave_the_pages_alone(
    capsys: pytest.CaptureFixture[str], simulations: Path, runs: list[dict[str, Any]]
) -> None:
    status, _, _ = run(capsys, "--root", simulations, "run", "--no-report")

    results = simulations / "results"
    assert status == 0
    assert (results / "ladder" / "divider.json").is_file()
    assert not (results / "README.md").exists()
    assert not (results / "ladder" / "README.md").exists()


def test_run_gives_a_deck_the_time_that_the_engine_allows_unless_told_otherwise(
    capsys: pytest.CaptureFixture[str],
    simulations: Path,
    runs: list[dict[str, Any]],
    engine: Engine,
) -> None:
    run(capsys, "--root", simulations, "run", "ladder/divider")
    run(capsys, "--root", simulations, "run", "--timeout", "90", "ladder/divider")
    run(capsys, "--root", simulations, "run", "ladder/divider", "--timeout", "0.5")

    assert [asked["engine"].timeout for asked in runs] == [1800.0, 90.0, 0.5]
    # Nothing else of the engine changes with the time.
    assert [asked["engine"].library for asked in runs] == [engine.library] * 3
    assert engine.timeout == 1800.0


def test_a_deck_that_takes_longer_than_the_time_given_is_a_bench_that_did_not_run(
    capsys: pytest.CaptureFixture[str], simulations: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def too_slow(engine: Engine, deck: str, workdir: Path, name: str, **options: Any) -> None:
        raise EngineError(f"{name}: no result after {engine.timeout:.0f} s")

    monkeypatch.setattr("circuit_sim.bench.run_deck", too_slow)

    status, out, _ = run(capsys, "--root", simulations, "run", "--timeout", "45")

    assert status == 1
    assert out.splitlines() == [
        "ladder/divider: DID NOT RUN: divider.at-rest: no result after 45 s",
        "ladder/limits: 1 pass, 1 fail, 0 without limit",
        "  FAIL Burden at 1 A: 108.5 mV (spec 106 mV)",
    ]


@pytest.mark.parametrize(
    ("seconds", "reason"),
    [
        ("0", "must be greater than zero"),
        ("-30", "must be greater than zero"),
        ("soon", "'soon' is not a number of seconds"),
        ("nan", "'nan' is not a number of seconds"),
        ("inf", "'inf' is not a number of seconds"),
    ],
)
def test_the_time_for_a_deck_must_be_a_number_of_seconds_above_zero(
    capsys: pytest.CaptureFixture[str], simulations: Path, seconds: str, reason: str
) -> None:
    error = usage_error(capsys, "--root", simulations, "run", f"--timeout={seconds}")

    assert f"argument --timeout: {reason}" in error


def test_run_with_the_models_of_the_manufacturers_files_a_second_record(
    capsys: pytest.CaptureFixture[str], simulations: Path, runs: list[dict[str, Any]]
) -> None:
    (simulations / "models" / "vendor").mkdir()
    (simulations / "models" / "vendor" / "ti-opa365.lib").write_text(
        ".SUBCKT OPA365_TI 1 2 3 4 5\n.ENDS\n"
    )
    run(capsys, "--root", simulations, "run", "ladder/divider")
    before = (simulations / "results" / "ladder" / "divider.json").read_bytes()

    status, out, _ = run(capsys, "--root", simulations, "run", "--tier", "vendor", "ladder/divider")

    folder = simulations / "results" / "ladder"
    assert (status, out) == (0, "ladder/divider: 1 pass, 0 fail, 1 without limit\n")
    assert (folder / "divider.json").read_bytes() == before
    vendor = load_record((folder / "divider.vendor.json").read_text(encoding="utf-8"))
    assert vendor.tier == "vendor"
    assert vendor.models == (("U1", "OPA365_TI", "vendor"),)
    assert [run["pspice"] for run in runs] == [False, True]
    # The page shows the two values side by side.
    page = (folder / "README.md").read_text(encoding="utf-8")
    assert (
        "| Figure | Simulated | Vendor models | Specification | Limits | Verdict | Source |" in page
    )
    assert "| Tap voltage | 2.5 V | 2.5 V | 2.5 V (+0.00 %) | 2.4 V to 2.6 V | pass | |" in page


def test_a_machine_without_the_simulator_is_reported(
    capsys: pytest.CaptureFixture[str], simulations: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_engine() -> Engine:
        raise EngineError("no ngspice shared library found: set NGSPICE_LIBRARY to its path")

    monkeypatch.setattr("circuit_sim.cli.default_engine", no_engine)

    status, out, err = run(capsys, "--root", simulations, "run")

    assert (status, out) == (2, "")
    assert err == "circuit-sim: no ngspice shared library found: set NGSPICE_LIBRARY to its path\n"


def test_a_folder_without_its_snapshot_or_its_model_map_is_reported(
    capsys: pytest.CaptureFixture[str], simulations: Path, runs: list[dict[str, Any]]
) -> None:
    (simulations / "models" / "models.toml").unlink()

    without_models = run(capsys, "--root", simulations, "run")

    (simulations / "netlist" / "carrier.json").unlink()

    without_snapshot = run(capsys, "--root", simulations, "run")

    assert without_models[0] == 2
    assert "circuit-sim: the folder " in without_models[2]
    assert without_models[2].rstrip().endswith("models holds no model map")
    assert without_snapshot[0] == 2
    assert without_snapshot[2].startswith("circuit-sim: cannot read the netlist snapshot ")
    assert runs == []


def test_report_writes_the_pages_and_names_them(
    capsys: pytest.CaptureFixture[str], simulations: Path, runs: list[dict[str, Any]]
) -> None:
    write_bench(simulations, "chain", "gain", GAIN)
    run(capsys, "--root", simulations, "run", "--no-report")

    status, out, err = run(capsys, "--root", simulations, "report")

    assert (status, err) == (0, "")
    assert out.splitlines() == [
        "results/README.md",
        "results/chain/README.md",
        "results/ladder/README.md",
    ]
    assert all((simulations / line).is_file() for line in out.splitlines())


def test_report_without_a_results_folder_is_reported(
    capsys: pytest.CaptureFixture[str], simulations: Path
) -> None:
    status, out, err = run(capsys, "--root", simulations, "report")

    assert (status, out) == (2, "")
    assert err.startswith("circuit-sim: ")
    assert "README.md" in err


def test_parts_shows_single_parts_with_their_nets_and_models(
    capsys: pytest.CaptureFixture[str], simulations: Path
) -> None:
    status, out, err = run(capsys, "--root", simulations, "parts", "U1", "R1", "J1", "TP1", "R1")

    assert (status, err) == (0, "")
    assert out.splitlines() == [
        "J1     Conn_01x02 [] <NO MODEL>  1(Pin_1)=/Ladder/VOUT_S 2(Pin_2)=GND",
        "R1     1k 0.1% 25ppm [RT0603BRD071KL] <resistor>  1=/Ladder/SUPPLY 2=/Ladder/VOUT_S",
        "TP1    TestPoint [] <skip>  1(1)=/Ladder/VOUT_S",
        "U1     OPA365AIDBV [OPA365AIDBVR] <OPA365>  1=/Chain/AMP_OUT 2(V-)=-4V_A "
        "3(+)=Net-(U1-+) 4(-)=Net-(U1--) 5(V+)=+12V_A",
    ]


def test_parts_shows_the_parts_of_a_sheet(
    capsys: pytest.CaptureFixture[str], simulations: Path
) -> None:
    status, out, _ = run(capsys, "--root", simulations, "parts", "--sheet", "CHAIN")
    with_more = run(capsys, "--root", simulations, "parts", "R2", "U1", "--sheet", "chain")[1]

    assert status == 0
    assert [line.split()[0] for line in out.splitlines()] == ["C3", "JP1", "L1", "RN1", "U1", "U2"]
    assert out.splitlines()[1] == "JP1    Jumper [] <short>  1(A)=Net-(L1-Pad2) 2(B)=+12V_A"
    assert [line.split()[0] for line in with_more.splitlines()] == [
        "C3",
        "JP1",
        "L1",
        "R2",
        "RN1",
        "U1",
        "U2",
    ]


def test_parts_without_a_choice_shows_the_whole_schematic(
    capsys: pytest.CaptureFixture[str], simulations: Path
) -> None:
    status, out, _ = run(capsys, "--root", simulations, "parts")

    lines = out.splitlines()
    assert status == 0
    assert len(lines) == 19
    assert [line.split()[0] for line in lines[:4]] == ["C1", "C2", "C3", "D1"]
    assert lines[4] == "FID1   Fiducial [] <skip>  "


@pytest.mark.parametrize(("text", "count"), [("a", 2), ("/", 3), ("nowhere", 0)])
def test_a_sheet_has_to_be_named_so_that_it_is_one(
    capsys: pytest.CaptureFixture[str], simulations: Path, text: str, count: int
) -> None:
    status, out, err = run(capsys, "--root", simulations, "parts", "--sheet", text)

    assert (status, out) == (2, "")
    assert err == (
        f"circuit-sim: '{text}' names {count} sheets; the sheets are /, /Chain/, /Ladder/\n"
    )


def test_parts_reports_a_part_that_the_schematic_does_not_have(
    capsys: pytest.CaptureFixture[str], simulations: Path
) -> None:
    status, out, err = run(capsys, "--root", simulations, "parts", "R1", "R99")

    assert status == 2
    assert out.startswith("R1 ")
    assert err == "circuit-sim: the schematic has no part R99\n"


def test_parts_without_a_model_map_shows_the_parts_alone(
    capsys: pytest.CaptureFixture[str], simulations: Path
) -> None:
    (simulations / "models" / "models.toml").write_text("[part\n", encoding="utf-8")

    status, out, _ = run(capsys, "--root", simulations, "parts", "R1", "U1")

    assert status == 0
    assert out.splitlines()[0] == (
        "R1     1k 0.1% 25ppm [RT0603BRD071KL]  1=/Ladder/SUPPLY 2=/Ladder/VOUT_S"
    )
    assert "<" not in out


def test_netlist_writes_the_snapshot_of_an_export(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    export = tmp_path / "carrier.xml"
    export.write_text(EXPORT, encoding="utf-8")
    root = tmp_path / "simulation"

    status, out, err = run(capsys, "--root", root, "netlist", export)

    stored = root / "netlist" / "carrier.json"
    assert (status, out, err) == (0, "wrote netlist/carrier.json\n", "")
    assert stored.read_bytes() == dump_snapshot(snapshot_from_kicad_xml(EXPORT)).encode("utf-8")
    assert [
        entry["ref"] for entry in json.loads(stored.read_text(encoding="utf-8"))["components"]
    ] == [
        "R1",
        "R2",
    ]


def test_netlist_says_whether_the_snapshot_still_matches_the_schematic(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    export = tmp_path / "carrier.xml"
    export.write_text(EXPORT, encoding="utf-8")
    changed = tmp_path / "changed.xml"
    changed.write_text(EXPORT.replace("<value>3k</value>", "<value>3.3k</value>"), encoding="utf-8")
    root = tmp_path / "simulation"

    missing = run(capsys, "--root", root, "netlist", export, "--check")
    run(capsys, "--root", root, "netlist", export)
    same = run(capsys, "--root", root, "netlist", export, "--check")
    other = run(capsys, "--root", root, "netlist", changed, "--check")

    assert missing == (1, "the snapshot differs from the netlist of the schematic\n", "")
    assert same == (0, "the snapshot matches the netlist of the schematic\n", "")
    assert other == (1, "the snapshot differs from the netlist of the schematic\n", "")
    # A check writes nothing.
    assert (
        json.loads((root / "netlist" / "carrier.json").read_text(encoding="utf-8"))["components"][
            0
        ]["value"]
        == "3k"
    )


def test_netlist_reports_an_export_that_is_missing_or_is_none(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    (tmp_path / "notes.xml").write_text("(export (version E))", encoding="utf-8")

    missing = run(capsys, "--root", tmp_path, "netlist", tmp_path / "missing.xml")
    no_export = run(capsys, "--root", tmp_path, "netlist", tmp_path / "notes.xml")

    assert missing[:2] == (2, "")
    assert missing[2].startswith("circuit-sim: ")
    assert "missing.xml" in missing[2]
    assert no_export[:2] == (2, "")
    assert no_export[2].startswith("circuit-sim: the netlist export is not XML")
    assert not (tmp_path / "netlist").exists()


def test_a_console_that_cannot_show_a_unit_does_not_stop_the_command(
    simulations: Path, runs: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A console code page without the ohm sign, as Windows has them.
    raw = io.BytesIO()
    console = io.TextIOWrapper(raw, encoding="ascii", errors="strict", newline="\n")
    monkeypatch.setattr(sys, "stdout", console)

    status = main(["--root", str(simulations), "run", "-v", "ladder/divider"])

    console.flush()
    assert status == 0
    assert b"       Shunt seen by the amplifier: 31.95 ?\n" in raw.getvalue()


def test_a_stream_that_cannot_be_set_up_is_left_as_it_is(
    simulations: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    assert main(["--root", str(simulations), "list"]) == 0
    assert main(["--root", str(simulations), "parts", "R99"]) == 2

    assert out.getvalue().splitlines()[0].startswith("ladder/divider ")
    assert err.getvalue() == "circuit-sim: the schematic has no part R99\n"
