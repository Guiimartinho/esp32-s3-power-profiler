"""What the qualification benches of the power input models share.

Each bench takes its part from the schematic, alone, on short node names,
so that the model map decides which model is tested: the one written here,
or the one of the manufacturer in the vendor tier.
"""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor

from circuit_sim.bench import Context
from circuit_sim.circuit import Circuit, PartModel
from circuit_sim.engine import RunResult
from circuit_sim.errors import SimulationError

LIBRARY = "power_input.lib"
"""Model file with the helper functions that the stimuli use."""

MODEL_FIT = 0.15
"""How close a model has to come to a typical value of its datasheet, as a
fraction: the fit this project asks of these models, not a datasheet limit."""

_WORKERS = 6
"""Decks that run at the same time."""


def part(
    ctx: Context, ref: str, pins: Mapping[str, str], model: PartModel | None = None
) -> Circuit:
    """One part of the schematic alone, with its pins on the node names given.

    Args:
        ctx: The bench context.
        ref: Reference designator of a part of the type under test.
        pins: Node name by pin number.
        model: A model that replaces the one of the model map.
    """
    found = ctx.netlist.component(ref)
    aliases = {found.net_of(number): node for number, node in pins.items()}
    return ctx.circuit([ref], aliases, {ref: model} if model is not None else None)


def transient(step: float, stop: float, start: float = 0.0) -> str:
    """A transient analysis that starts with every capacitor empty."""
    return f"tran {step:g} {stop:g} {start:g} {step:g} uic"


def try_runs(
    ctx: Context, decks: Mapping[str, str], keep: tuple[str, ...] = ()
) -> tuple[dict[str, RunResult], dict[str, str]]:
    """Run decks side by side and tell the ones that ran from the ones that did not.

    A model of a manufacturer does not run every test circuit. The figures
    of a deck that did not run are reported as missing, and the others stay.

    Returns:
        The results by deck name, and the error message of every deck that
        did not run.
    """
    for name in keep:
        ctx.kept[f"{ctx.prefix}.{name}.cir"] = decks[name]
    done: dict[str, RunResult] = {}
    failed: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = {
            name: pool.submit(ctx.run, name, deck, keep=False) for name, deck in decks.items()
        }
        for name, future in futures.items():
            result, message = _outcome(future)
            if result is None:
                failed[name] = message
            else:
                done[name] = result
    return done, failed


def _outcome(future: Future[RunResult]) -> tuple[RunResult | None, str]:
    """The result of a run, or the message of the error that ended it."""
    try:
        return future.result(), ""
    except SimulationError as error:
        return None, str(error)


def failure_note(failed: Mapping[str, str]) -> tuple[str, ...]:
    """A note that names the decks that did not run, or nothing."""
    if not failed:
        return ()
    text = "; ".join(f"{name}: {message[:160]}" for name, message in sorted(failed.items()))
    return (f"Decks that did not run with this model, so their figures are missing: {text}",)
