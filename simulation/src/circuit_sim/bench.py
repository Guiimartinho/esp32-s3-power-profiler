"""Benches: a circuit, a stimulus, the figures taken from it and their limits.

A bench is a function that receives a :class:`Context`, builds its circuit
from the netlist of the schematic, runs it and returns an :class:`Outcome`:
figures, each beside the value the specification states and the limits it
has to keep, and graphs of the waveforms. Benches register themselves with
the :func:`bench` decorator; :func:`discover` imports the modules of a
folder so that they do.
"""

from __future__ import annotations

import importlib
import os
import pathlib
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from circuit_sim.circuit import Circuit, ModelMap, PartModel, build_circuit
from circuit_sim.engine import Engine, RunResult, run_deck
from circuit_sim.errors import BenchError
from circuit_sim.netlist import Netlist
from circuit_sim.vendor import is_vendor, prepared_copy

PASS = "pass"
FAIL = "fail"
INFO = "info"

OPEN_TIER = "open"
VENDOR_TIER = "vendor"

_WORKERS = 6
"""Decks of one sweep that run at the same time."""

# A block is a folder and a Python package; the name of a bench is the start
# of the names of its files, in which a dot sets the bench apart from its
# graphs, its decks and its vendor record.
_BLOCK_NAME = re.compile(r"[a-z0-9_]+")
_BENCH_NAME = re.compile(r"[a-z0-9-]+")


@dataclass(frozen=True, slots=True)
class Figure:
    """One number that a bench took from a simulation.

    Attributes:
        key: Name of the figure inside its bench, stable between runs.
        label: What the figure is, as the report shows it.
        value: The simulated value in the base unit.
        unit: The base unit: ``V``, ``A``, ``s``, ``Hz``, ``ohm``, ``dB`` ...
        expected: The value the specification states, when it states one.
        low: Lower limit, when there is one.
        high: Upper limit, when there is one.
        source: Where the expected value and the limits come from: a
            section, a requirement or a decision of the specification.
    """

    key: str
    label: str
    value: float
    unit: str
    expected: float | None = None
    low: float | None = None
    high: float | None = None
    source: str = ""

    @property
    def verdict(self) -> str:
        """``pass`` or ``fail`` against the limits, ``info`` without limits."""
        if self.low is None and self.high is None:
            return INFO
        if not np.isfinite(self.value):
            return FAIL
        if self.low is not None and self.value < self.low:
            return FAIL
        if self.high is not None and self.value > self.high:
            return FAIL
        return PASS

    @property
    def deviation(self) -> float | None:
        """The distance from the expected value as a fraction of it."""
        if self.expected is None or self.expected == 0.0:
            return None
        return (self.value - self.expected) / abs(self.expected)


def near(
    key: str,
    label: str,
    value: float,
    unit: str,
    expected: float,
    tolerance: float,
    source: str = "",
) -> Figure:
    """A figure that has to lie within a fraction of the value expected."""
    span = abs(expected) * tolerance
    return Figure(key, label, value, unit, expected, expected - span, expected + span, source)


@dataclass(frozen=True, slots=True)
class Trace:
    """One curve of a graph, in the units of its axes.

    Attributes:
        x: The horizontal values.
        y: The vertical values.
        label: Legend entry.
        panel: Index of the panel the curve is drawn in.
        style: Line style of matplotlib (``-``, ``--``, ``:``).
    """

    x: NDArray[np.float64]
    y: NDArray[np.float64]
    label: str
    panel: int = 0
    style: str = "-"


@dataclass(frozen=True, slots=True)
class Panel:
    """One set of axes of a graph.

    Attributes:
        ylabel: Label of the vertical axis, with the unit.
        log: Logarithmic vertical axis.
        marks: Horizontal lines with their labels, for limits and levels.
    """

    ylabel: str
    log: bool = False
    marks: tuple[tuple[float, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Graph:
    """Waveforms of a bench, drawn as panels over one horizontal axis.

    Attributes:
        name: Short name, part of the file name.
        title: Title above the graph.
        xlabel: Label of the horizontal axis, with the unit.
        panels: The axes, from top to bottom.
        traces: The curves.
        logx: Logarithmic horizontal axis.
        xmarks: Vertical lines with their labels, for events.
    """

    name: str
    title: str
    xlabel: str
    panels: tuple[Panel, ...]
    traces: tuple[Trace, ...]
    logx: bool = False
    xmarks: tuple[tuple[float, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Outcome:
    """What a bench returns.

    Attributes:
        figures: The numbers, with what they are compared with.
        graphs: The waveforms.
        notes: What the reader has to know to weigh the result: what the
            models leave out, which values are assumptions.
    """

    figures: tuple[Figure, ...]
    graphs: tuple[Graph, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Bench:
    """A registered bench.

    Attributes:
        block: The block of the instrument it belongs to; the name of its folder.
        name: Short name inside the block.
        title: One line that says what is simulated.
        covers: The sections, requirements and decisions it answers.
        summary: What the bench does, from the docstring of its function.
        run: The function.
    """

    block: str
    name: str
    title: str
    covers: str
    summary: str
    run: Callable[[Context], Outcome]

    @property
    def ident(self) -> str:
        """``<block>/<name>``."""
        return f"{self.block}/{self.name}"


_REGISTRY: dict[str, Bench] = {}
_BLOCKS: dict[str, str] = {}


def block(name: str, title: str) -> None:
    """Give a block its title; called by the package of the block."""
    _BLOCKS[name] = title


def block_title(name: str) -> str:
    """The title of a block, or its name when it gave none."""
    return _BLOCKS.get(name, name)


def bench(
    block: str, name: str, title: str, covers: str = ""
) -> Callable[[Callable[[Context], Outcome]], Callable[[Context], Outcome]]:
    """Register the decorated function as a bench.

    Args:
        block: The block of the bench: lower case letters, digits and
            underscores, as its folder is named.
        name: Short name inside the block: lower case letters, digits and
            hyphens. The files of the bench start with it.
        title: One line that says what is simulated.
        covers: The sections, requirements and decisions the bench answers.

    Raises:
        BenchError: When the block or the name is not written like that, or
            a bench of the same block and name exists already.
    """
    if _BLOCK_NAME.fullmatch(block) is None:
        raise BenchError(
            f"the block {block!r} of the bench {name!r} has to be named in lower case "
            "letters, digits and underscores"
        )
    if _BENCH_NAME.fullmatch(name) is None:
        raise BenchError(
            f"the bench {name!r} of the block {block!r} has to be named in lower case "
            "letters, digits and hyphens"
        )

    def register(function: Callable[[Context], Outcome]) -> Callable[[Context], Outcome]:
        summary = " ".join((function.__doc__ or "").split())
        entry = Bench(block, name, title, covers, summary, function)
        if entry.ident in _REGISTRY and _REGISTRY[entry.ident].run is not function:
            raise BenchError(f"two benches are named {entry.ident}")
        _REGISTRY[entry.ident] = entry
        return function

    return register


def registered() -> tuple[Bench, ...]:
    """Every registered bench, by block and name."""
    return tuple(_REGISTRY[key] for key in sorted(_REGISTRY))


def clear_registry() -> None:
    """Forget every registered bench and block title."""
    _REGISTRY.clear()
    _BLOCKS.clear()


def discover(directory: pathlib.Path) -> tuple[Bench, ...]:
    """Import the bench modules of a folder and return what they registered.

    The folder is a Python package (``benches``) with one package per block.
    Its parent goes on the module search path, so that the modules of a
    block can import each other.

    Raises:
        BenchError: When the folder is not such a package or a module fails
            to import.
    """
    if not (directory / "__init__.py").is_file():
        raise BenchError(f"{directory} is not a package of benches (no __init__.py)")
    parent = str(directory.parent.resolve())
    if parent not in sys.path:
        sys.path.insert(0, parent)
    for path in sorted(directory.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        relative = path.relative_to(directory.parent).with_suffix("")
        module = ".".join(relative.parts)
        try:
            importlib.import_module(module)
        except Exception as error:
            raise BenchError(f"cannot import the bench module {module}: {error!r}") from error
    return registered()


@dataclass
class Context:
    """What a bench works with: the schematic, the models and the simulator.

    Attributes:
        engine: The simulator.
        netlist: The schematic.
        models: The model map.
        models_dir: Folder of the model files.
        workdir: Folder in which the decks of this bench run.
        prefix: Start of the file names of this bench.
        tier: ``open`` for the models of the repository alone, ``vendor`` to
            take the model of the manufacturer where the map names one.
        kept: The decks that are kept with the results, by file name.
        origins: The models used so far, as (designator, model, origin).
        engine_version: Version line of the simulator, known after a run.
        library_sha256: Checksum of the simulator library, known after a run.
    """

    engine: Engine
    netlist: Netlist
    models: ModelMap
    models_dir: pathlib.Path
    workdir: pathlib.Path
    prefix: str
    tier: str = OPEN_TIER
    kept: dict[str, str] = field(default_factory=dict)
    origins: set[tuple[str, str, str]] = field(default_factory=set)
    engine_version: str = ""
    library_sha256: str = ""
    _pspice: bool = False

    def circuit(
        self,
        refs: Iterable[str],
        aliases: Mapping[str, str] | None = None,
        overrides: Mapping[str, PartModel] | None = None,
        scales: Mapping[str, float] | None = None,
    ) -> Circuit:
        """The SPICE elements of some parts of the schematic.

        Args:
            refs: Reference designators of the parts.
            aliases: Shorter node names for nets, by net name.
            overrides: Models that replace the model map for single parts.
            scales: Factors on the values of single passive parts, for
                tolerance runs.
        """
        built = build_circuit(
            self.netlist, self.models, refs, aliases, overrides, scales, tier=self.tier
        )
        self.origins.update(built.origins)
        if any(origin == "vendor" for _, _, origin in built.origins):
            self._pspice = True
        return built

    def deck(
        self,
        title: str,
        *parts: Circuit | str,
        control: Sequence[str],
        options: Sequence[str] = (),
        libraries: Sequence[str] = (),
    ) -> str:
        """Put a deck together.

        Args:
            title: First line of the deck.
            *parts: Circuits and blocks of SPICE lines, in order.
            control: The commands of the ``.control`` section.
            options: Arguments of ``.options`` lines.
            libraries: Model files to include beside the ones the circuits
                need, relative to the models folder.
        """
        wanted: list[str] = list(libraries)
        for part in parts:
            if isinstance(part, Circuit):
                wanted.extend(name for name in part.libraries if name not in wanted)
        relative = pathlib.PurePosixPath(
            pathlib.Path(os.path.relpath(self.models_dir, self.workdir)).as_posix()
        )
        lines = [f"* {title}"]
        for name in dict.fromkeys(wanted):
            if is_vendor(name):
                # The file of a manufacturer is read through a copy in the
                # form that ngspice accepts, kept beside the decks.
                copy = prepared_copy(self.models_dir, name, self.workdir)
                lines.append(f'.include "{copy.relative_to(self.workdir).as_posix()}"')
            else:
                lines.append(f'.include "{relative / name}"')
        texts = (part.text() if isinstance(part, Circuit) else part for part in parts)
        lines += [text.rstrip("\n") for text in texts]
        lines += [f".options {option}" for option in options]
        lines += [".control", *control, ".endc", ".end"]
        return "\n".join(lines) + "\n"

    def run(
        self, name: str, deck: str, *, keep: bool = True, allowed: Sequence[str] = ()
    ) -> RunResult:
        """Run one deck of this bench.

        Args:
            name: Short name of the deck inside the bench.
            deck: The whole deck.
            keep: Keep the deck with the results. Decks of a sweep are
                better left out.
            allowed: Regular expressions of log lines that would count as
                failures and are harmless for this deck.
        """
        file_name = f"{self.prefix}.{name}"
        if keep:
            self.kept[f"{file_name}.cir"] = deck
        result = run_deck(
            self.engine, deck, self.workdir, file_name, pspice=self._pspice, allowed=allowed
        )
        self.engine_version = result.version
        self.library_sha256 = result.library_sha256
        return result

    def run_many(
        self, decks: Mapping[str, str], *, keep: bool = False, allowed: Sequence[str] = ()
    ) -> dict[str, RunResult]:
        """Run the decks of a sweep side by side.

        Args:
            decks: The decks, by their short names inside the bench.
            keep: Keep the decks with the results, as :meth:`run` does. The
                many decks of a sweep are better left out: unless asked,
                none of them is kept.
            allowed: Regular expressions of log lines that would count as
                failures and are harmless for these decks.
        """
        if keep:
            # Noted here, in the order given: the runs below end in any order.
            self.kept.update({f"{self.prefix}.{name}.cir": deck for name, deck in decks.items()})
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            futures = {
                name: pool.submit(self.run, name, deck, keep=False, allowed=allowed)
                for name, deck in decks.items()
            }
            return {name: future.result() for name, future in futures.items()}
