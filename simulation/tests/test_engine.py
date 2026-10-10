from __future__ import annotations

import ctypes.util
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from circuit_sim import engine as engine_module
from circuit_sim import measure
from circuit_sim.engine import (
    CODE_MODELS_VARIABLE,
    LIBRARY_VARIABLE,
    Engine,
    RunResult,
    default_engine,
    failures,
    find_code_models,
    find_library,
    run_deck,
)
from circuit_sim.errors import EngineError

VERSION = "ngspice-45.2 shared library"

# The file of vectors as the worker writes it, one array under each name.
write_vectors: Callable[..., None] = np.savez_compressed

QUIET_LOG = (
    "Warning: can't find the initialization file spinit.",
    "** ngspice-45.2 shared library",
    "Note: No compatibility mode selected!",
    "Circuit: * divider",
    "Doing analysis at TEMP = 27.000000 and TNOM = 27.000000",
    "No. of Data Rows : 1",
)


class Child:
    """Stands in for the child process: notes how it was started and leaves what a worker leaves."""

    def __init__(
        self,
        *,
        vectors: dict[str, Any] | None = None,
        log: tuple[str, ...] = QUIET_LOG,
        returncode: int = 0,
        stdout: str | None = None,
        stderr: str = "",
        writes: bool = True,
        expires: bool = False,
    ) -> None:
        self.vectors = {"op1/out": np.array([2.5])} if vectors is None else vectors
        self.log = log
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.writes = writes
        self.expires = expires
        self.command: list[str] = []
        self.options: dict[str, Any] = {}
        self.deck = b""
        self.found_output = False

    def __call__(self, command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        self.command = command
        self.options = options
        self.deck = Path(command[3]).read_bytes()
        output = Path(command[4])
        self.found_output = output.exists()
        if self.expires:
            raise subprocess.TimeoutExpired(command, options["timeout"])
        if self.writes:
            write_vectors(output, **self.vectors)
        report = json.dumps({"version": VERSION, "status": 0, "log": list(self.log)}) + "\n"
        return subprocess.CompletedProcess(
            command, self.returncode, report if self.stdout is None else self.stdout, self.stderr
        )


@pytest.fixture
def child(monkeypatch: pytest.MonkeyPatch) -> Child:
    stand_in = Child()
    monkeypatch.setattr(subprocess, "run", stand_in)
    return stand_in


@pytest.fixture
def bare_machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A machine without ngspice: no variable, no KiCad, no library of the system."""
    for variable in (LIBRARY_VARIABLE, CODE_MODELS_VARIABLE, "LD_LIBRARY_PATH"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(shutil, "which", lambda command: None)
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: None)
    monkeypatch.setattr("circuit_sim.engine._LIBRARY_FOLDERS", ())
    monkeypatch.chdir(tmp_path)


def result_with(*names: str) -> RunResult:
    """A result whose vectors hold their place in the file: the first holds 0, the next 1."""
    vectors = {name: np.array([float(place)]) for place, name in enumerate(names)}
    return RunResult(vectors=vectors, log=(), version=VERSION, library_sha256="", seconds=0.0)


def test_a_vector_is_found_by_the_name_of_its_node() -> None:
    result = result_with("tran1/@r101[i]", "tran1/v1#branch", "tran1/out", "tran1/time")

    assert result.vector("out")[0] == 2.0
    assert result.vector("v(out)")[0] == 2.0
    assert result.vector("V(OUT)")[0] == 2.0
    assert result.vector("Time")[0] == 3.0
    assert result.vector("v1#branch")[0] == 1.0
    assert result.vector("@R101[i]")[0] == 0.0


def test_a_plot_is_chosen_by_the_start_of_its_name() -> None:
    result = result_with("ac1/out", "tran1/out", "op1/out")

    assert result.vector("out", plot="ac")[0] == 0.0
    assert result.vector("out", plot="tran")[0] == 1.0
    assert result.vector("out", plot="TRAN1")[0] == 1.0
    assert result.vector("out", plot="op")[0] == 2.0


@pytest.mark.parametrize(
    "plots",
    [
        # As ngspice lists them, the newest first, and the other way around.
        ("op12", "op11", "op10", "op2", "op1"),
        ("op1", "op2", "op10", "op11", "op12"),
    ],
)
def test_a_plot_named_in_full_is_that_plot_alone(plots: tuple[str, ...]) -> None:
    result = result_with(*[f"{plot}/out" for plot in plots])

    assert result.vector("out", plot="op1")[0] == float(plots.index("op1"))
    assert result.vector("out", plot="OP1")[0] == float(plots.index("op1"))
    assert result.vector("out", plot="op10")[0] == float(plots.index("op10"))
    assert result.vector("out", plot="op2")[0] == float(plots.index("op2"))


def test_among_several_plots_the_one_listed_last_answers() -> None:
    # ngspice lists the newest plot first: the last one is the first analysis.
    result = result_with("tran2/out", "tran2/time", "tran1/out", "tran1/time", "op1/in")

    assert result.vector("out")[0] == 2.0
    assert result.vector("out", plot="tran")[0] == 2.0
    assert result.vector("out", plot="tran2")[0] == 0.0
    assert result.vector("in")[0] == 4.0


def test_a_vector_that_the_run_does_not_have_is_an_error() -> None:
    result = result_with(*[f"tran1/n{number:02}" for number in range(14)])

    with pytest.raises(EngineError, match=r"the run has no vector 'v\(out\)'") as failure:
        result.vector("v(out)")
    with pytest.raises(EngineError, match="the run has no vector 'n03'"):
        result.vector("n03", plot="ac")

    # The message names a dozen of the vectors that are there.
    assert "tran1/n00, tran1/n01," in str(failure.value)
    assert "tran1/n11 ..." in str(failure.value)
    assert "tran1/n12" not in str(failure.value)


def test_a_complex_vector_gives_its_real_part() -> None:
    result = RunResult(
        vectors={
            "ac1/frequency": np.array([10.0 + 0j, 100.0 + 0j]),
            "ac1/out": np.array([0.5 - 0.5j, 0.1 - 0.3j]),
            "op1/out": np.array([2]),
        },
        log=(),
        version=VERSION,
        library_sha256="",
        seconds=0.0,
    )

    assert result.real("frequency").tolist() == [10.0, 100.0]
    assert result.real("out", plot="ac").tolist() == [0.5, 0.1]
    assert result.real("frequency").dtype == np.float64
    assert result.real("out", plot="op").dtype == np.float64
    assert result.vector("out", plot="ac").dtype == np.complex128


def test_the_variable_names_the_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bare_machine: None
) -> None:
    library = tmp_path / "anywhere" / "libngspice.so.0"
    library.parent.mkdir()
    library.write_bytes(b"library")
    monkeypatch.setenv(LIBRARY_VARIABLE, str(library))
    monkeypatch.setattr(shutil, "which", lambda command: pytest.fail("the search path was read"))

    assert find_library() == library


def test_a_variable_that_names_no_file_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bare_machine: None
) -> None:
    monkeypatch.setenv(LIBRARY_VARIABLE, str(tmp_path))

    with pytest.raises(EngineError, match=r"NGSPICE_LIBRARY names .*, which is not a file"):
        find_library()


@pytest.mark.parametrize(
    "name", ["ngspice.dll", "libngspice-0.dll", "libngspice.so.0", "libngspice.0.dylib"]
)
def test_the_library_is_looked_for_beside_kicad(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bare_machine: None, name: str
) -> None:
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / name).write_bytes(b"library")
    asked: list[str] = []

    def which(command: str) -> str:
        asked.append(command)
        return str(tmp_path / "bin" / "kicad-cli.exe")

    monkeypatch.setattr(shutil, "which", which)
    monkeypatch.setattr(
        ctypes.util, "find_library", lambda name: pytest.fail("the system was asked")
    )
    # A variable that is set to nothing counts as not set.
    monkeypatch.setenv(LIBRARY_VARIABLE, "")

    assert find_library() == tmp_path / "bin" / name
    assert asked == ["kicad-cli"]


def test_the_library_of_the_system_is_taken_when_kicad_ships_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bare_machine: None
) -> None:
    library = tmp_path / "system" / "ngspice.dll"
    library.parent.mkdir()
    library.write_bytes(b"library")
    asked: list[str] = []

    def find(name: str) -> str:
        asked.append(name)
        return str(library)

    monkeypatch.setattr(shutil, "which", lambda command: str(tmp_path / "bin" / "kicad-cli"))
    monkeypatch.setattr(ctypes.util, "find_library", find)

    assert find_library() == library
    assert asked == ["ngspice"]


def test_a_library_that_the_system_names_without_its_folder_is_looked_for_in_the_library_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bare_machine: None
) -> None:
    # Linux answers with a name such as libngspice.so.0, which is no file to
    # load and to take a checksum of.
    first, second = tmp_path / "opt" / "lib", tmp_path / "home" / "lib"
    for folder in (first, second):
        folder.mkdir(parents=True)
    (second / "libngspice.so.0").write_bytes(b"library")
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: "libngspice.so.0")
    monkeypatch.setenv("LD_LIBRARY_PATH", os.pathsep.join(["", str(first), str(second)]))

    assert find_library() == second / "libngspice.so.0"
    assert default_engine() == Engine(second / "libngspice.so.0")


def test_the_usual_folders_of_a_system_are_looked_at_after_the_library_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bare_machine: None
) -> None:
    usual = [tmp_path / "usr" / "lib", tmp_path / "usr" / "lib64", tmp_path / "usr" / "local"]
    named = tmp_path / "named"
    for folder in (*usual[1:], named):
        folder.mkdir(parents=True)
    for folder in usual[1:]:
        (folder / "libngspice.so.0").write_bytes(b"library")
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: "libngspice.so.0")
    monkeypatch.setattr(
        "circuit_sim.engine._LIBRARY_FOLDERS", tuple(str(folder) for folder in usual)
    )

    # The first usual folder does not exist and the second holds the library.
    assert find_library() == usual[1] / "libngspice.so.0"

    (named / "libngspice.so.0").write_bytes(b"library")
    monkeypatch.setenv("LD_LIBRARY_PATH", str(named))

    assert find_library() == named / "libngspice.so.0"


def test_the_folders_in_which_a_system_usually_keeps_its_libraries() -> None:
    assert engine_module._LIBRARY_FOLDERS == (
        "/usr/lib",
        "/usr/lib64",
        "/usr/local/lib",
        "/usr/lib/x86_64-linux-gnu",
        "/usr/lib/aarch64-linux-gnu",
        "/opt/homebrew/lib",
    )


def test_a_library_named_without_its_folder_is_tried_as_it_is_named_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bare_machine: None
) -> None:
    (tmp_path / "libngspice.so.0").write_bytes(b"library")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "libngspice.so.0").write_bytes(b"library")
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: "libngspice.so.0")
    monkeypatch.setenv("LD_LIBRARY_PATH", str(tmp_path / "lib"))

    # The working folder of the test holds a file of that name.
    assert find_library() == Path("libngspice.so.0")


@pytest.mark.parametrize("found", [None, "libngspice.so.0", "/nowhere/lib/libngspice.so.0"])
def test_a_machine_without_the_library_is_told_how_to_name_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bare_machine: None, found: str | None
) -> None:
    (tmp_path / "lib").mkdir()
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: found)
    monkeypatch.setenv("LD_LIBRARY_PATH", str(tmp_path / "lib"))
    monkeypatch.setattr("circuit_sim.engine._LIBRARY_FOLDERS", (str(tmp_path / "usr" / "lib"),))

    with pytest.raises(EngineError) as failure:
        find_library()
    with pytest.raises(EngineError, match="no ngspice shared library found"):
        default_engine()

    assert str(failure.value) == (
        "no ngspice shared library found: set NGSPICE_LIBRARY to its path "
        "(KiCad ships one beside kicad-cli)"
    )


def test_the_code_models_are_looked_for_beside_the_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bare_machine: None
) -> None:
    library = tmp_path / "bin" / "ngspice.dll"

    assert find_code_models(library) is None

    (tmp_path / "lib" / "ngspice").mkdir(parents=True)

    assert find_code_models(library) == tmp_path / "lib" / "ngspice"

    monkeypatch.setenv(CODE_MODELS_VARIABLE, str(tmp_path / "elsewhere"))

    assert find_code_models(library) == tmp_path / "elsewhere"


def test_the_engine_of_the_machine_is_the_library_with_its_code_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bare_machine: None
) -> None:
    library = tmp_path / "bin" / "ngspice.dll"
    library.parent.mkdir()
    library.write_bytes(b"library")
    (tmp_path / "lib" / "ngspice").mkdir(parents=True)
    monkeypatch.setenv(LIBRARY_VARIABLE, str(library))

    assert default_engine() == Engine(library, tmp_path / "lib" / "ngspice", 1800.0)

    monkeypatch.setenv(CODE_MODELS_VARIABLE, str(tmp_path / "cm"))

    assert default_engine() == Engine(library=library, code_models=tmp_path / "cm")
    assert Engine(library).code_models is None


@pytest.mark.parametrize(
    "line",
    [
        "Error on line 5 or its substitute:",
        "ERROR: fatal error in ngspice, exit(1)",
        "tran simulation(s) aborted",
        "Warning: singular matrix:  check node a",
        "doAnalyses: TRAN:  Timestep too small; time = 1.2e-09, timestep = 1e-21",
        "Error: no such vector v(out)",
        "unknown subckt: x1 a b opa365",
        "Could not find include file opamps.lib",
        "Warning: can't find model 'bav199' from line",
        "cannot find the file models.lib",
        "Model not found: irlml0030",
        "unrecognized parameter (tc3) - ignored",
        "too few parameters for subcircuit type opa197",
        "Warning: source stepping failed",
        "Transient op started",
        "Note: Transient op started",
    ],
)
def test_a_line_that_says_the_run_went_wrong_is_found(line: str) -> None:
    assert failures(["Circuit: * a deck", line, "No. of Data Rows : 1"]) == [line]
    assert failures([line.upper()]) == [line.upper()]


def test_the_log_of_a_good_run_has_no_such_line() -> None:
    assert failures(QUIET_LOG) == []
    assert failures([]) == []
    # The words are looked for as words: a count of errors is not an error.
    assert failures(["Total errors: 0", "terror", "error_amp = 2.5", "abortedly"]) == []


def test_a_line_that_is_harmless_for_a_deck_can_be_allowed() -> None:
    log = [
        "Warning: Model issue on line 13 : .model dz d(bv=5.1) error in level",
        "Warning: singular matrix:  check node a",
    ]

    assert failures(log) == log
    assert failures(log, allowed=[r"model issue on line \d+"]) == [log[1]]
    assert failures(log, allowed=["MODEL ISSUE", "check node a$"]) == []
    # The line that the bundle of KiCad always prints needs no permission.
    assert failures(["Warning: can't find the initialization file spinit."]) == []


@pytest.mark.parametrize(
    "title",
    [
        "* gentle error amplifier",
        "* the model could not find its datasheet: an error in the title, not found in the run",
        "* singular matrix, timestep too small and transient op started",
        "",
    ],
)
def test_the_line_that_echoes_the_title_of_a_deck_is_not_judged(title: str) -> None:
    # A title says what the deck is about, in any words; what ngspice prints
    # about the run comes on the lines after it.
    log = [
        "Note: No compatibility mode selected!",
        f"Circuit: {title}",
        "Doing analysis at TEMP = 27.000000 and TNOM = 27.000000",
    ]

    assert failures(log) == []
    assert failures([*log, "Error on line 3 or its substitute:"]) == [
        "Error on line 3 or its substitute:"
    ]


@pytest.mark.parametrize(
    "line",
    [
        "Error: Circuit: * gentle error amplifier",
        " Circuit: * gentle error amplifier",
        "circuit: * gentle error amplifier",
        "Circuits: an error",
        "Circuit * gentle error amplifier",
        "Warning: the Circuit: line is not the only one with an error",
    ],
)
def test_only_the_echo_of_the_title_is_left_out_of_the_judgement(line: str) -> None:
    assert failures(["Circuit: * a deck", line]) == [line]


def test_a_deck_runs_in_a_child_process_of_its_own(
    tmp_path: Path, engine: Engine, child: Child
) -> None:
    workdir = tmp_path / ".work" / "ladder"
    deck = "* divider\nV1 in 0 10\nR1 in out 3k\nR2 out 0 1k\n.control\nop\n.endc\n.end\n"

    run_deck(engine, deck, workdir, "ranges.r0")

    assert child.command == [
        sys.executable,
        "-m",
        "circuit_sim._worker",
        str(workdir / "ranges.r0.cir"),
        str(workdir / "ranges.r0.npz"),
        str(engine.library),
    ]
    assert child.options == {
        "capture_output": True,
        "text": True,
        "timeout": 1800.0,
        "check": False,
    }
    # The deck is on file before the child starts, with the line ends of SPICE.
    assert child.deck == deck.encode("utf-8")
    assert (workdir / "ranges.r0.cir").read_bytes() == deck.encode("utf-8")


def test_the_modes_of_a_run_reach_the_child(tmp_path: Path, engine: Engine, child: Child) -> None:
    models = tmp_path / "lib" / "ngspice"
    with_models = Engine(engine.library, code_models=models, timeout=90.0)

    run_deck(engine, "* deck\n.end\n", tmp_path, "plain", pspice=True)
    compatible = list(child.command)
    run_deck(with_models, "* deck\n.end\n", tmp_path, "digital")
    digital = list(child.command)
    run_deck(with_models, "* deck\n.end\n", tmp_path, "both", pspice=True)

    assert compatible[6:] == ["--psa"]
    assert digital[6:] == ["--codemodels", str(models)]
    assert child.command[6:] == ["--psa", "--codemodels", str(models)]
    assert child.options["timeout"] == 90.0


def test_the_vectors_of_the_child_come_back_with_its_log(
    tmp_path: Path, engine: Engine, child: Child
) -> None:
    child.vectors = {
        "tran1/time": np.array([0.0, 1e-6, 3e-6]),
        "tran1/out": np.array([0.0, 0.5, 1.0]),
        "ac1/out": np.array([1.0 + 0j, 0.5 - 0.5j]),
    }

    result = run_deck(engine, "* deck\n.end\n", tmp_path, "step")

    assert list(result.vectors) == ["tran1/time", "tran1/out", "ac1/out"]
    assert result.real("out", plot="tran").tolist() == [0.0, 0.5, 1.0]
    assert result.vector("out", plot="ac").tolist() == [1.0 + 0j, 0.5 - 0.5j]
    assert result.log == QUIET_LOG
    assert result.version == VERSION
    assert result.library_sha256 == hashlib.sha256(b"not a library").hexdigest()
    assert 0.0 <= result.seconds < 60.0


def test_the_checksum_of_the_library_is_taken_once(
    tmp_path: Path, engine: Engine, child: Child
) -> None:
    first = run_deck(engine, "* deck\n.end\n", tmp_path, "first")
    engine.library.write_bytes(b"another build")
    second = run_deck(engine, "* deck\n.end\n", tmp_path, "second")

    assert second.library_sha256 == first.library_sha256


def test_the_output_of_an_earlier_run_is_removed_before_the_child_starts(
    tmp_path: Path, engine: Engine, child: Child
) -> None:
    write_vectors(tmp_path / "step.npz", **{"op1/out": np.array([99.0])})
    child.writes = False

    with pytest.raises(EngineError, match="step: the simulator process died"):
        run_deck(engine, "* deck\n.end\n", tmp_path, "step")

    assert not child.found_output
    assert not (tmp_path / "step.npz").exists()


@pytest.mark.parametrize(
    ("seconds", "said"), [(5.0, "5 s"), (1800.0, "1800 s"), (0.5, "0.5 s"), (90.25, "90.25 s")]
)
def test_a_child_that_does_not_end_is_given_up(
    tmp_path: Path, engine: Engine, child: Child, seconds: float, said: str
) -> None:
    child.expires = True
    slow = Engine(engine.library, timeout=seconds)

    with pytest.raises(EngineError) as given_up:
        run_deck(slow, "* deck\n.end\n", tmp_path, "sweep")

    assert str(given_up.value) == f"sweep: no result after {said}"
    assert child.options["timeout"] == seconds


def test_a_child_that_dies_is_reported_with_the_end_of_what_it_printed(
    tmp_path: Path, engine: Engine, child: Child
) -> None:
    child.stdout = "x" * 700 + "\nloading the library\n"
    child.stderr = "Windows fatal exception: access violation\n\n"
    child.returncode = -1073741819
    child.writes = False

    with pytest.raises(EngineError) as failure:
        run_deck(engine, "* deck\n.end\n", tmp_path, "step")

    message = str(failure.value)
    assert message.startswith("step: the simulator process died (exit -1073741819): xxx")
    assert message.endswith("loading the library\nWindows fatal exception: access violation")
    assert len(message.split(": ", 2)[2]) == 600


def test_a_report_without_the_file_of_vectors_counts_as_a_child_that_died(
    tmp_path: Path, engine: Engine, child: Child
) -> None:
    child.writes = False

    with pytest.raises(EngineError, match=r"step: the simulator process died \(exit 0\)"):
        run_deck(engine, "* deck\n.end\n", tmp_path, "step")


def test_a_log_that_says_the_run_went_wrong_fails_the_run(
    tmp_path: Path, engine: Engine, child: Child
) -> None:
    child.log = (*QUIET_LOG, "Warning: singular matrix:  check node a", "op simulation(s) aborted")

    with pytest.raises(EngineError) as failure:
        run_deck(engine, "* deck\n.end\n", tmp_path, "float")

    assert str(failure.value) == (
        "float: the run failed: Warning: singular matrix:  check node a; op simulation(s) aborted"
    )


def test_at_most_six_lines_of_a_bad_log_are_shown(
    tmp_path: Path, engine: Engine, child: Child
) -> None:
    child.log = tuple(f"Error on line {number}" for number in range(1, 9))

    with pytest.raises(EngineError) as failure:
        run_deck(engine, "* deck\n.end\n", tmp_path, "typo")

    assert str(failure.value) == "typo: the run failed: " + "; ".join(
        f"Error on line {number}" for number in range(1, 7)
    )


def test_a_deck_that_the_library_refuses_fails_the_run(
    tmp_path: Path, engine: Engine, child: Child
) -> None:
    child.returncode = 3

    with pytest.raises(EngineError, match=r"^empty: the run failed: exit code 3$"):
        run_deck(engine, "* deck\n.end\n", tmp_path, "empty")


def test_a_line_allowed_for_a_deck_does_not_fail_its_run(
    tmp_path: Path, engine: Engine, child: Child
) -> None:
    child.log = (*QUIET_LOG, "Warning: Model issue on line 13 : error in level")

    with pytest.raises(EngineError, match="the run failed: Warning: Model issue"):
        run_deck(engine, "* deck\n.end\n", tmp_path, "vendor")
    result = run_deck(engine, "* deck\n.end\n", tmp_path, "vendor", allowed=["model issue on line"])

    assert result.log[-1] == "Warning: Model issue on line 13 : error in level"
    assert result.real("out").tolist() == [2.5]


def test_a_deck_whose_title_holds_a_word_of_failure_runs_like_any_other(
    tmp_path: Path, engine: Engine, child: Child
) -> None:
    child.log = (
        "Warning: can't find the initialization file spinit.",
        "Circuit: * gentle error amplifier",
        "No. of Data Rows : 1",
    )

    result = run_deck(engine, "* Gentle error amplifier\n.end\n", tmp_path, "gentle")

    assert result.log[1] == "Circuit: * gentle error amplifier"
    assert result.real("out").tolist() == [2.5]


def test_the_report_is_the_last_line_of_json_that_the_child_prints(
    tmp_path: Path, engine: Engine, child: Child
) -> None:
    older = json.dumps({"version": "an older line", "status": 0, "log": ["Error: stale"]})
    report = json.dumps({"version": VERSION, "status": 0, "log": ["Circuit: * deck"]})
    child.stdout = "\n".join(
        [
            "the library prints what it likes",
            older,
            report,
            '{"progress": 100}',
            "{this is not json}",
            "[1, 2, 3]",
            "",
        ]
    )

    result = run_deck(engine, "* deck\n.end\n", tmp_path, "step")

    assert result.version == VERSION
    assert result.log == ("Circuit: * deck",)


DIVIDER = """* divider
V1 in 0 10
R1 in out 3k
R2 out 0 1k
.control
op
.endc
.end
"""

RC_STEP = """* RC step: 1 kohm and 100 nF
V1 in 0 PWL(0 0 1u 0 1.001u 1)
R1 in out 1k
C1 out 0 100n
.control
tran 1u 1m
.endc
.end
"""

RC_LOW_PASS = """* RC low-pass: 1 kohm and 100 nF
V1 in 0 dc 0 ac 1
R1 in out 1k
C1 out 0 100n
.control
ac dec 50 10 1meg
.endc
.end
"""

RESISTOR_NOISE = """* thermal noise of 1 kohm
V1 in 0 dc 0 ac 1
R1 in out 1k
R2 out 0 1G
.control
noise v(out) V1 dec 10 10 100k
.endc
.end
"""

FLOATING = """* a resistor that hangs on nothing
V1 in 0 10
R1 in out 3k
R2 out 0 1k
R3 a b 220
.control
op
.endc
.end
"""

GAIN_BLOCK = """* a code model: the gain block of XSPICE
V1 in 0 2
A1 in out twice
.model twice gain(gain=2.0)
R1 out 0 1k
.control
op
.endc
.end
"""


@pytest.mark.needs_ngspice
def test_ngspice_solves_a_divider(tmp_path: Path, ngspice: Engine) -> None:
    result = run_deck(ngspice, DIVIDER, tmp_path, "divider")

    assert result.real("out") == pytest.approx([2.5], rel=1e-6)
    assert result.real("v(in)") == pytest.approx([10.0], rel=1e-6)
    assert result.real("v1#branch") == pytest.approx([-2.5e-3], rel=1e-6)
    assert result.version.startswith("ngspice-")
    assert result.library_sha256 == hashlib.sha256(ngspice.library.read_bytes()).hexdigest()
    assert any("divider" in line for line in result.log)
    assert (tmp_path / "divider.cir").read_text(encoding="utf-8") == DIVIDER


@pytest.mark.needs_ngspice
def test_ngspice_charges_a_capacitor_with_its_time_constant(
    tmp_path: Path, ngspice: Engine
) -> None:
    result = run_deck(ngspice, RC_STEP, tmp_path, "rc-step")
    time, volts = result.real("time"), result.real("out")
    tau = 1e3 * 100e-9

    reached = measure.first_crossing(time, volts, 1.0 - np.exp(-1.0), rising=True)

    assert reached - 1e-6 == pytest.approx(tau, rel=2e-3)
    assert measure.rise_time(time, volts, 0.1, 0.9) == pytest.approx(tau * np.log(9.0), rel=2e-3)
    assert measure.settling_time(time, volts, 1.0, 0.01, after=1e-6) == pytest.approx(
        tau * np.log(100.0), rel=2e-3
    )
    assert measure.overshoot(time, volts, 0.0, 1.0, after=1e-6) == 0.0
    assert volts[-1] == pytest.approx(1.0 - np.exp(-9.99), rel=1e-3)


@pytest.mark.needs_ngspice
def test_ngspice_finds_the_corner_of_a_low_pass(tmp_path: Path, ngspice: Engine) -> None:
    result = run_deck(ngspice, RC_LOW_PASS, tmp_path, "rc-ac")
    frequency = result.real("frequency")
    response = np.asarray(result.vector("out"), dtype=np.complex128)
    corner = 1.0 / (2.0 * np.pi * 1e3 * 100e-9)

    found = measure.corner_frequency(frequency, response, drop_db=10.0 * np.log10(2.0))

    assert result.vector("out").dtype == np.complex128
    assert found == pytest.approx(corner, rel=1e-3)
    assert measure.peaking_db(response) == 0.0
    # One decade above the corner the response has fallen by 20 dB and turned by 84 degrees.
    above = float(np.interp(10.0 * corner, frequency, measure.decibels(response)))
    assert above == pytest.approx(-10.0 * np.log10(101.0), abs=0.01)
    assert measure.phase_degrees(response)[-1] == pytest.approx(-90.0, abs=0.2)


@pytest.mark.needs_ngspice
def test_ngspice_gives_a_resistor_its_thermal_noise(tmp_path: Path, ngspice: Engine) -> None:
    result = run_deck(ngspice, RESISTOR_NOISE, tmp_path, "noise")
    frequency = result.real("frequency", plot="noise1")
    density = result.real("onoise_spectrum")
    # 4 k T R at the 27 degrees Celsius of the simulator.
    expected = np.sqrt(4.0 * 1.380649e-23 * 300.15 * 1e3)

    assert density == pytest.approx(expected, rel=1e-3)
    assert measure.integrated_noise(frequency, density, 10.0, 100e3) == pytest.approx(
        expected * np.sqrt(100e3 - 10.0), rel=1e-3
    )
    assert measure.integrated_noise(frequency, density, 10.0, 100e3) == pytest.approx(
        float(result.real("onoise_total")[0]), rel=1e-3
    )


@pytest.mark.needs_ngspice
def test_ngspice_cannot_solve_a_floating_node_and_the_run_fails(
    tmp_path: Path, ngspice: Engine
) -> None:
    with pytest.raises(EngineError, match=r"floating: the run failed: .*singular matrix"):
        run_deck(ngspice, FLOATING, tmp_path, "floating")


@pytest.mark.needs_ngspice
def test_ngspice_runs_a_deck_with_blanks_in_its_name_and_in_its_folder(
    tmp_path: Path, ngspice: Engine
) -> None:
    result = run_deck(ngspice, DIVIDER, tmp_path / "a folder with blanks", "divider at rest")

    assert result.real("out") == pytest.approx([2.5], rel=1e-6)


@pytest.mark.needs_ngspice
def test_ngspice_solves_the_divider_in_the_dialect_of_pspice_too(
    tmp_path: Path, ngspice: Engine
) -> None:
    plain = run_deck(ngspice, DIVIDER, tmp_path, "plain")
    compatible = run_deck(ngspice, DIVIDER, tmp_path, "compatible", pspice=True)

    assert compatible.real("out") == pytest.approx([2.5], rel=1e-6)
    assert compatible.version == plain.version
    # Where the library says which dialect it reads, the two runs do not say the same.
    said = [line for line in compatible.log if "ompatib" in line]
    said_plain = [line for line in plain.log if "ompatib" in line]
    assert not [line for line in said if "No compatibility mode" in line]
    assert said != said_plain or not said_plain


@pytest.mark.needs_ngspice
def test_ngspice_echoes_the_title_of_a_deck_and_a_word_of_failure_in_it_does_no_harm(
    tmp_path: Path, ngspice: Engine
) -> None:
    deck = DIVIDER.replace("* divider", "* Gentle error amplifier: singular matrix not found")

    result = run_deck(ngspice, deck, tmp_path, "gentle")

    echoes = [line for line in result.log if line.startswith("Circuit:")]
    assert len(echoes) == 1
    assert "error amplifier" in echoes[0].lower()
    assert result.real("out") == pytest.approx([2.5], rel=1e-6)


@pytest.mark.needs_ngspice
def test_ngspice_loads_its_code_models_from_a_folder_with_a_blank_in_its_name(
    tmp_path: Path, ngspice: Engine
) -> None:
    # KiCad installs itself under "Program Files" on Windows unless told otherwise.
    if ngspice.code_models is None:
        pytest.skip("the simulator of this machine names no folder of code models")
    models = tmp_path / "Program Files" / "ngspice"
    models.mkdir(parents=True)
    for file in ngspice.code_models.glob("*.cm"):
        shutil.copyfile(file, models / file.name)
    elsewhere = Engine(ngspice.library, code_models=models)

    result = run_deck(elsewhere, GAIN_BLOCK, tmp_path, "gain")

    assert result.real("out") == pytest.approx([4.0], rel=1e-6)
    assert run_deck(ngspice, GAIN_BLOCK, tmp_path, "gain-as-found").real("out") == pytest.approx(
        [4.0], rel=1e-6
    )
