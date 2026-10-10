"""Fixtures shared by the test modules.

``snapshot`` is the netlist of a small invented front end with one of every
kind of part that the circuit builder knows, and ``MODEL_MAP`` is the model
map that goes with it. ``root`` is a folder laid out like the simulations of
the repository, built from the two. No test needs KiCad, the schematic of the
project or its benches, and only the tests marked ``needs_ngspice`` need the
simulator.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from circuit_sim.bench import clear_registry
from circuit_sim.circuit import ModelMap, load_model_map
from circuit_sim.engine import Engine, RunResult, default_engine
from circuit_sim.errors import EngineError
from circuit_sim.netlist import Netlist, dump_snapshot, natural_key, netlist_from_snapshot

MODEL_MAP = """
[part."IRLML0030TRPBF"]
kind = "device"
letter = "M"
name = "IRLML0030"
ports = ["3", "1", "2"]
library = "mosfets.lib"
origin = "written here"

[part."BAV199-7-F"]
kind = "device"
letter = "D"
name = "BAV199"
units = [["1", "3"], ["3", "2"]]
library = "diodes.lib"
origin = "written here"

[part."OPA365AIDBVR"]
kind = "subckt"
name = "OPA365"
ports = ["+", "-", "V+", "V-", "1"]
library = "opamps.lib"
origin = "written here"

[part."TC4427EOA713"]
kind = "subckt"
name = "TC4427CH"
units = [["2", "7", "6", "3"], ["4", "5", "6", "3"]]
library = "logic.lib"
origin = "written here"

[ref.R3]
kind = "kelvin"
ports = ["1", "2", "3", "4"]

[ref.JP1]
kind = "short"

[vendor."OPA365AIDBVR"]
kind = "subckt"
name = "OPA365_TI"
ports = ["3", "4", "5", "2", "1"]
library = "vendor/ti-opa365.lib"
origin = "vendor"
"""

VERSION_LINE = "ngspice-45.2 shared library"
CHECKSUM = "5f" * 32


def _part(
    ref: str, value: str, pins: list[tuple[str, str, str]], mpn: str = "", sheet: str = "/Ladder/"
) -> dict[str, Any]:
    """One part of a snapshot, its pins as (number, name, net)."""
    return {
        "ref": ref,
        "value": value,
        "mpn": mpn,
        "sheet": sheet,
        "pins": [{"pin": number, "net": net, "function": name} for number, name, net in pins],
    }


@pytest.fixture
def snapshot() -> dict[str, Any]:
    """The snapshot of a small front end: two ranges, an amplifier and a driver."""
    ladder = [
        _part(
            "R1",
            "1k 0.1% 25ppm",
            [("1", "", "/Ladder/SUPPLY"), ("2", "", "/Ladder/VOUT_S")],
            mpn="RT0603BRD071KL",
        ),
        _part("R2", "33R 1%", [("1", "", "Net-(Q1-S)"), ("2", "", "/Ladder/VOUT_S")]),
        _part(
            "R3",
            "0.1R 0.25% 50ppm",
            [
                ("1", "", "Net-(Q2-S)"),
                ("2", "", "Net-(U1-+)"),
                ("3", "", "Net-(U1--)"),
                ("4", "", "/Ladder/VOUT_S"),
            ],
            mpn="LVK12R100CER",
        ),
        _part("R4", "0R", [("1", "", "Net-(Q1-G)"), ("2", "", "/Ladder/GATE_R1")]),
        _part(
            "Q1",
            "IRLML0030",
            [("1", "G", "Net-(Q1-G)"), ("2", "S", "Net-(Q1-S)"), ("3", "D", "/Ladder/SUPPLY")],
            mpn="IRLML0030TRPBF",
        ),
        _part(
            "Q2",
            "IRLML0030",
            [("1", "G", "/Ladder/GATE_R2"), ("2", "S", "Net-(Q2-S)"), ("3", "D", "/Ladder/SUPPLY")],
            mpn="IRLML0030TRPBF",
        ),
        _part("C1", "100n 50V X7R", [("1", "", "/Ladder/SUPPLY"), ("2", "", "GND")]),
        _part("C2", "1u 25V X7R", [("1", "", "/Ladder/VOUT_S"), ("2", "", "GND")]),
        _part(
            "D1",
            "BAV199",
            [("1", "A", "GND"), ("2", "K", "+3V3_A"), ("3", "common", "Net-(U1-+)")],
            mpn="BAV199-7-F",
        ),
        _part("TP1", "TestPoint", [("1", "1", "/Ladder/VOUT_S")]),
    ]
    chain = [
        _part(
            "U1",
            "OPA365AIDBV",
            [
                ("1", "", "/Chain/AMP_OUT"),
                ("2", "V-", "-4V_A"),
                ("3", "+", "Net-(U1-+)"),
                ("4", "-", "Net-(U1--)"),
                ("5", "V+", "+12V_A"),
            ],
            mpn="OPA365AIDBVR",
            sheet="/Chain/",
        ),
        _part(
            "U2",
            "TC4427",
            [
                ("1", "NC", "unconnected-(U2-NC-Pad1)"),
                ("2", "IN A", "/Chain/CMD_A"),
                ("3", "GND", "GND"),
                ("4", "IN B", "/Chain/CMD_B"),
                ("5", "OUT B", "/Ladder/GATE_R2"),
                ("6", "VDD", "+12V_A"),
                ("7", "OUT A", "/Ladder/GATE_R1"),
                ("8", "NC", "unconnected-(U2-NC-Pad8)"),
            ],
            mpn="TC4427EOA713",
            sheet="/Chain/",
        ),
        # Three resistors of the network are in use; the schematic leaves the
        # fourth open, and KiCad then gives each of its pins a net of its own.
        _part(
            "RN1",
            "10k 1%",
            [
                ("1", "R1.1", "/Chain/CMD_A"),
                ("2", "R2.1", "/Chain/CMD_B"),
                ("3", "R3.1", "Net-(RN1-R3.1)"),
                ("4", "R4.1", "unconnected-(RN1-R4.1-Pad4)"),
                ("5", "R4.2", "unconnected-(RN1-R4.2-Pad5)"),
                ("6", "R3.2", "GND"),
                ("7", "R2.2", "GND"),
                ("8", "R1.2", "GND"),
            ],
            mpn="CAY16-103J4LF",
            sheet="/Chain/",
        ),
        _part("L1", "10u 3A", [("1", "1", "+5V"), ("2", "2", "Net-(L1-Pad2)")], sheet="/Chain/"),
        _part("C3", "10u 25V X5R", [("1", "", "+12V_A"), ("2", "", "GND")], sheet="/Chain/"),
        _part(
            "JP1", "Jumper", [("1", "A", "Net-(L1-Pad2)"), ("2", "B", "+12V_A")], sheet="/Chain/"
        ),
        _part("J1", "Conn_01x02", [("1", "Pin_1", "/Ladder/VOUT_S"), ("2", "Pin_2", "GND")]),
        _part("H1", "MountingHole", [("1", "1", "GND")], sheet="/"),
        _part("FID1", "Fiducial", [], sheet="/"),
    ]
    return {
        "format": 1,
        "title": "Small Front End",
        "revision": "T1",
        "components": sorted([*ladder, *chain], key=lambda entry: natural_key(entry["ref"])),
    }


@pytest.fixture
def netlist(snapshot: dict[str, Any]) -> Netlist:
    """The small front end as the package reads it."""
    return netlist_from_snapshot(snapshot)


@pytest.fixture
def models(tmp_path: Path) -> ModelMap:
    """The model map of the small front end."""
    path = tmp_path / "small-models.toml"
    path.write_text(MODEL_MAP, encoding="utf-8")
    return load_model_map(path)


@pytest.fixture
def root(tmp_path: Path, snapshot: dict[str, Any]) -> Path:
    """A folder laid out like the simulations: benches, models, netlist."""
    folder = tmp_path / "simulation"
    (folder / "netlist").mkdir(parents=True)
    (folder / "netlist" / "carrier.json").write_text(
        dump_snapshot(snapshot), encoding="utf-8", newline="\n"
    )
    (folder / "models").mkdir()
    (folder / "models" / "models.toml").write_text(MODEL_MAP, encoding="utf-8")
    (folder / "benches").mkdir()
    (folder / "benches" / "__init__.py").write_text('"""Benches of a test."""\n', encoding="utf-8")
    return folder


@pytest.fixture(autouse=True)
def empty_registry() -> Iterator[None]:
    """Every test starts and ends without a registered bench or block title."""
    clear_registry()
    yield
    clear_registry()


def _forget_benches() -> None:
    for name in [name for name in sys.modules if name == "benches" or name.startswith("benches.")]:
        del sys.modules[name]


@pytest.fixture
def bench_imports(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Let a test import a package named ``benches`` of its own.

    The module search path is put back afterward, and the modules of the
    package are forgotten, so that the next test imports its own files.
    """
    monkeypatch.setattr(sys, "path", list(sys.path))
    _forget_benches()
    importlib.invalidate_caches()
    yield
    _forget_benches()


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    """An engine whose library is a file of a few bytes; nothing loads it."""
    library = tmp_path / "bin" / "ngspice.dll"
    library.parent.mkdir()
    library.write_bytes(b"not a library")
    return Engine(library=library)


@pytest.fixture
def run_result() -> RunResult:
    """What the stand-in for the simulator returns for every deck."""
    return RunResult(
        vectors={"op1/out": np.array([2.5]), "op1/in": np.array([10.0])},
        log=("Circuit: * a deck",),
        version=VERSION_LINE,
        library_sha256=CHECKSUM,
        seconds=0.25,
    )


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch, run_result: RunResult) -> list[dict[str, Any]]:
    """Replace the simulator behind a bench context; the list holds every run asked."""
    asked: list[dict[str, Any]] = []

    def run_deck(engine: Engine, deck: str, workdir: Path, name: str, **options: Any) -> RunResult:
        asked.append({"engine": engine, "deck": deck, "workdir": workdir, "name": name, **options})
        return run_result

    monkeypatch.setattr("circuit_sim.bench.run_deck", run_deck)
    return asked


@pytest.fixture(scope="session")
def ngspice() -> Engine:
    """The simulator of this machine; the test is skipped where there is none."""
    try:
        return default_engine()
    except EngineError as error:
        pytest.skip(f"no ngspice shared library: {error}")
