"""The simulator: ngspice as a shared library, one process per deck.

KiCad ships ngspice as a shared library without an executable. The package
runs every deck in a child process (:mod:`circuit_sim._worker`) that loads
the library, sources the deck and writes every vector of every plot to a
file. This module finds the library, starts the child, reads the vectors
back and judges the log: ngspice goes on after many errors and still prints
numbers, so a run counts as failed when its log holds a line that says so.
"""

from __future__ import annotations

import ctypes.util
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from circuit_sim.errors import EngineError

LIBRARY_VARIABLE = "NGSPICE_LIBRARY"
"""Environment variable with the path of the ngspice shared library."""

CODE_MODELS_VARIABLE = "NGSPICE_CODEMODELS"
"""Environment variable with the folder of the XSPICE code models."""

_LIBRARY_NAMES = ("ngspice.dll", "libngspice-0.dll", "libngspice.so.0", "libngspice.0.dylib")

# Where a system usually keeps its shared libraries. A system that names a
# library without its folder, as Linux does, is looked through here.
_LIBRARY_FOLDERS = (
    "/usr/lib",
    "/usr/lib64",
    "/usr/local/lib",
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib/aarch64-linux-gnu",
    "/opt/homebrew/lib",
)

# Lines of the log that mean the numbers of a run cannot be trusted. ngspice
# does not stop at them. The last two belong to an operating point that did
# not converge: ngspice then runs a short transient with ramped sources and
# reports where it ended as the operating point, settled or not.
_FAILURE = re.compile(
    r"\berror\b|\baborted\b|singular matrix|timestep too small|no such vector"
    r"|unknown subckt|could not find|can't find|cannot find|not found"
    r"|unrecognized parameter|too few parameters|doanalyses"
    r"|source stepping failed|transient op started",
    re.IGNORECASE,
)

# Lines that match the list above and are known and harmless everywhere: the
# bundle of KiCad has no start-up file.
_HARMLESS = (r"initialization file spinit",)

# Start of the line in which ngspice repeats the title of a deck. A title
# says what the deck is about, in any words ("gentle error amplifier"): that
# line says nothing about the run.
_TITLE_ECHO = "Circuit:"

Vector = NDArray[np.float64] | NDArray[np.complex128]


@dataclass(frozen=True, slots=True)
class Engine:
    """Where the simulator is and how long a run may take.

    Attributes:
        library: The ngspice shared library.
        code_models: Folder with the XSPICE code models, or None when the
            decks use none.
        timeout: Seconds after which a run is given up.
    """

    library: pathlib.Path
    code_models: pathlib.Path | None = None
    timeout: float = 1800.0


@dataclass(frozen=True, slots=True)
class RunResult:
    """What one deck produced.

    Attributes:
        vectors: Every vector of every plot, named ``<plot>/<vector>``, for
            example ``tran1/v(out)``.
        log: The lines that ngspice printed.
        version: The version line of the library.
        library_sha256: Checksum of the library file, so that a result names
            the build it came from.
        seconds: Wall time of the run.
    """

    vectors: Mapping[str, Vector]
    log: tuple[str, ...]
    version: str
    library_sha256: str
    seconds: float

    def vector(self, name: str, plot: str | None = None) -> Vector:
        """One vector by its name: a node (``out`` or ``v(out)``), ``time``, ``v1#branch``.

        Args:
            name: Name of the vector without its plot; letter case is ignored.
            plot: The plot name (``op3``) or its start (``tran``, ``ac``,
                ``dc``, ``noise``, ``op``) when the deck ran more than one
                analysis. A plot of exactly that name wins. Otherwise, and
                without a plot, the last of the plots that have the vector
                answers, in the order in which the library lists them:
                ngspice lists the newest plot first, so that is the plot of
                the earliest analysis.

        Raises:
            EngineError: When no plot holds a vector of that name.
        """
        wanted = name.lower()
        if wanted.startswith("v(") and wanted.endswith(")"):
            wanted = wanted[2:-1]  # ngspice names a node voltage by its node
        hits = [
            key
            for key in self.vectors
            if key.split("/", 1)[1].lower() == wanted
            and (plot is None or key.lower().startswith(plot.lower()))
        ]
        if not hits:
            known = ", ".join(sorted(self.vectors)[:12])
            raise EngineError(f"the run has no vector {name!r} (it has: {known} ...)")
        # "op1" is also the start of "op10": the plot of that very name is meant.
        exact = [key for key in hits if key.split("/", 1)[0].lower() == (plot or "").lower()]
        return self.vectors[(exact or hits)[-1]]

    def real(self, name: str, plot: str | None = None) -> NDArray[np.float64]:
        """One vector as real numbers; a complex one gives its real part."""
        return np.real(self.vector(name, plot)).astype(np.float64)


def find_library() -> pathlib.Path:
    """The ngspice shared library of this machine.

    The environment variable ``NGSPICE_LIBRARY`` wins. Without it the library
    is looked for beside ``kicad-cli``, which ships it, and then among the
    libraries of the system. A system that names the library without its
    folder (``libngspice.so.0`` on Linux) has the folders of
    ``LD_LIBRARY_PATH`` and the usual library folders looked through for it.

    Raises:
        EngineError: When no library is found.
    """
    given = os.environ.get(LIBRARY_VARIABLE)
    if given:
        path = pathlib.Path(given)
        if not path.is_file():
            raise EngineError(f"{LIBRARY_VARIABLE} names {given}, which is not a file")
        return path
    kicad = shutil.which("kicad-cli")
    if kicad:
        for name in _LIBRARY_NAMES:
            candidate = pathlib.Path(kicad).parent / name
            if candidate.is_file():
                return candidate
    found = ctypes.util.find_library("ngspice")
    if found:
        folders = [*os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep), *_LIBRARY_FOLDERS]
        # The name as the system gives it first: a whole path on Windows and macOS.
        candidates = [pathlib.Path(found)]
        candidates += [pathlib.Path(folder) / found for folder in folders if folder]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
    raise EngineError(
        f"no ngspice shared library found: set {LIBRARY_VARIABLE} to its path "
        "(KiCad ships one beside kicad-cli)"
    )


def find_code_models(library: pathlib.Path) -> pathlib.Path | None:
    """The folder of the XSPICE code models that belongs to a library, if any."""
    given = os.environ.get(CODE_MODELS_VARIABLE)
    if given:
        return pathlib.Path(given)
    beside = library.parent.parent / "lib" / "ngspice"
    return beside if beside.is_dir() else None


def default_engine() -> Engine:
    """The engine of this machine, found through :func:`find_library`."""
    library = find_library()
    return Engine(library=library, code_models=find_code_models(library))


def failures(log: Sequence[str], allowed: Sequence[str] = ()) -> list[str]:
    """The lines of a log that say the run went wrong.

    The line in which ngspice repeats the title of the deck, which starts
    with ``Circuit:``, is not judged: a title may hold any word. Every other
    line is.

    Args:
        log: The lines that ngspice printed.
        allowed: Regular expressions of lines that are known and harmless for
            the deck at hand, for example a warning that a vendor model
            prints with the word "error" in it.
    """
    passes = [re.compile(pattern, re.IGNORECASE) for pattern in (*_HARMLESS, *allowed)]
    return [
        line
        for line in log
        if not line.startswith(_TITLE_ECHO)
        and _FAILURE.search(line)
        and not any(pattern.search(line) for pattern in passes)
    ]


def run_deck(
    engine: Engine,
    deck: str,
    workdir: pathlib.Path,
    name: str,
    *,
    pspice: bool = False,
    allowed: Sequence[str] = (),
) -> RunResult:
    """Run one deck and return its vectors.

    Args:
        engine: The simulator.
        deck: The whole deck, with a ``.control`` section that runs the
            analyses and with ``.end``.
        workdir: Folder for the deck file and its output; relative
            ``.include`` paths of the deck are resolved from it.
        name: File name of the deck without extension.
        pspice: Run in the PSpice compatibility mode, which most vendor
            models need. Without it such a model can give wrong numbers
            without any message.
        allowed: Regular expressions of log lines that would count as
            failures and are harmless for this deck.

    Raises:
        EngineError: When the run does not end, the library refuses the deck,
            or the log holds a line that says the run went wrong.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    deck_path = workdir / f"{name}.cir"
    out_path = workdir / f"{name}.npz"
    deck_path.write_text(deck, encoding="utf-8", newline="\n")
    out_path.unlink(missing_ok=True)
    command = [sys.executable, "-m", "circuit_sim._worker", str(deck_path), str(out_path)]
    command.append(str(engine.library))
    if pspice:
        command.append("--psa")
    if engine.code_models is not None:
        command += ["--codemodels", str(engine.code_models)]
    started = time.perf_counter()
    try:
        # The command is built here, not taken from input.
        done = subprocess.run(
            command, capture_output=True, text=True, timeout=engine.timeout, check=False
        )
    except subprocess.TimeoutExpired as error:
        raise EngineError(f"{name}: no result after {engine.timeout:g} s") from error
    seconds = time.perf_counter() - started
    report = _last_json(done.stdout)
    if report is None or not out_path.is_file():
        tail = (done.stdout + done.stderr).strip()[-600:]
        raise EngineError(f"{name}: the simulator process died (exit {done.returncode}): {tail}")
    log = tuple(str(line) for line in report["log"])
    bad = failures(log, allowed)
    if done.returncode != 0 or bad:
        shown = "; ".join(bad[:6]) if bad else f"exit code {done.returncode}"
        raise EngineError(f"{name}: the run failed: {shown}")
    with np.load(out_path) as stored:
        vectors = {key: stored[key] for key in stored.files}
    return RunResult(
        vectors=vectors,
        log=log,
        version=str(report["version"]),
        library_sha256=_sha256(engine.library),
        seconds=seconds,
    )


def _last_json(text: str) -> dict[str, Any] | None:
    """The report line of the worker: the last line of its output that is JSON."""
    for line in reversed(text.splitlines()):
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and "log" in parsed:
                return parsed
    return None


_CHECKSUMS: dict[pathlib.Path, str] = {}


def _sha256(path: pathlib.Path) -> str:
    """Checksum of a file, kept for the life of the process."""
    if path not in _CHECKSUMS:
        _CHECKSUMS[path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _CHECKSUMS[path]
