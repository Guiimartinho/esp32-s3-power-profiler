"""The interlock of the two mode pairs and a change of mode."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.path_switching import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_EVENT = 1e-3
"""Instant of the first change of a request."""

_END = 41e-3

_VIN = 5.0
"""Voltage of the external supply, V."""

_VLDO = 3.3
"""Voltage of the stand-in for the regulator, V: different from the supply, so
that a current between the two would show."""

_DEAD = 5e-3
"""Dead time of firmware between lowering one request and raising the other (rule F-23)."""

_CONDUCTS = 10e-3
"""Current above which a pair counts as conducting, A."""

_THRESHOLD_LEAST = 1.1
"""Lowest gate threshold of the CSD17577Q3A at 250 uA, V (TI SLPS515A, page 3)."""

_DRIVER_LOW = 0.8
"""Highest input voltage the gate driver reads as low, V (Microchip DS20001422G, page 3)."""

Edges = tuple[tuple[float, bool], ...]


@dataclass(frozen=True, slots=True)
class _Case:
    """One run: what the two requests do.

    Attributes:
        name: Short name of the run.
        text: The case as the labels name it.
        source: Levels of GATE_SRC over time.
        ampere: Levels of GATE_AMP over time.
        weak: Use the interlock transistor with the highest threshold.
    """

    name: str
    text: str
    source: Edges
    ampere: Edges
    weak: bool = False


_CASES = (
    _Case(
        "both",
        "both requests raised together from idle",
        ((0.0, False), (_EVENT, True)),
        ((0.0, False), (_EVENT, True)),
    ),
    _Case(
        "both-weak",
        "both requests raised together, interlock transistor with the highest threshold",
        ((0.0, False), (_EVENT, True)),
        ((0.0, False), (_EVENT, True)),
        weak=True,
    ),
    _Case(
        "added",
        "ampere mode running, source request added",
        ((0.0, False), (_EVENT, True)),
        ((0.0, True),),
    ),
    _Case(
        "to-source",
        "ampere to source with no dead time",
        ((0.0, False), (_EVENT, True)),
        ((0.0, True), (_EVENT, False)),
    ),
    _Case(
        "to-source-5ms",
        "ampere to source with 5 ms of dead time",
        ((0.0, False), (_EVENT + _DEAD, True)),
        ((0.0, True), (_EVENT, False)),
    ),
    _Case(
        "to-ampere",
        "source to ampere with no dead time",
        ((0.0, True), (_EVENT, False)),
        ((0.0, False), (_EVENT, True)),
    ),
    _Case(
        "to-ampere-5ms",
        "source to ampere with 5 ms of dead time",
        ((0.0, True), (_EVENT, False)),
        ((0.0, False), (_EVENT + _DEAD, True)),
    ),
)


def _deck(ctx: Context, case: _Case) -> str:
    """Both supplies present, the output open, the requests of a case."""
    overrides: dict[str, PartModel] = {"Q2": common.interlock("HI")} if case.weak else {}
    stimulus = (
        common.supply(_VIN, henries=1e-6)
        + common.regulator(_VLDO)
        + common.requests(source=case.source, ampere=case.ampere)
    )
    control = [
        "save g_src s_src g_amp s_amp supply vin_p ldo_out gate_src gate_amp amp_in "
        "drv_src drv_amp vlead#branch vldo#branch @mq4[id] @mq5[id] @d.xd14.d1[id]",
        f"tran 10u {_END:g} 0 20u",
    ]
    return common.deck(
        ctx,
        f"Interlock: {case.text}",
        common.circuit(ctx, overrides=overrides),
        common.rails(),
        common.range_lines(3),
        stimulus,
        control=control,
    )


def _overlap(ctx: Context, run: RunResult) -> float:
    """The time for which both pairs carry more than the conduction level."""
    time = run.real("time")
    source = np.abs(common.through(ctx, run, "source"))
    ampere = np.abs(common.through(ctx, run, "ampere"))
    both = (source > _CONDUCTS) & (ampere > _CONDUCTS)
    return float(np.sum(np.diff(time)[both[:-1] & both[1:]]))


def _held(case: _Case, run: RunResult) -> list[Figure]:
    """The figures of a run in which both requests end high."""
    time = run.real("time")
    node = run.real("amp_in")
    drive = run.real("g_amp") - run.real("s_amp")
    terminal = run.real("vlead#branch")
    settled = _EVENT + 1e-6
    quiet = _EVENT + 10e-6 if case.name == "added" else settled
    key = case.name.replace("-", "_")
    return [
        Figure(
            f"input_{key}",
            f"Input of the ampere driver at the most, 1 us after the edge: {case.text}",
            measure.extremes(time, node, settled, _END)[1],
            "V",
            high=0.1,
            source="section 16: input of the ampere driver below 0.1 V",
        ),
        Figure(
            f"glitch_{key}",
            f"Input of the ampere driver at the most, at the edge: {case.text}",
            measure.extremes(time, node, _EVENT - 1e-7, settled)[1],
            "V",
            high=None if case.name == "added" else _DRIVER_LOW,
            source=""
            if case.name == "added"
            else "the driver reads 0.8 V or less as low (Microchip DS20001422G, page 3)",
        ),
        Figure(
            f"gate_{key}",
            f"Gate-source voltage of the ampere pair at the most, 10 us after the edge: "
            f"{case.text}",
            measure.extremes(time, drive, quiet, _END)[1],
            "V",
            high=_THRESHOLD_LEAST,
            source="lowest threshold of the transistors, 1.1 V (TI SLPS515A, page 3)",
        ),
        Figure(
            f"terminal_{key}",
            f"Current at the VIN terminal at the most, 5 ms after the edge: {case.text}",
            measure.extremes(time, np.abs(terminal), _EVENT + 5e-3, _END)[1],
            "A",
            high=50e-6,
            source="section 16: less than 50 uA at the VIN terminal",
        ),
        Figure(
            f"node_{key}",
            f"Supply node at the end, which follows the regulator at {_VLDO:g} V: {case.text}",
            measure.mean(time, run.real("supply"), _END - 1e-3, _END),
            "V",
            low=_VLDO - 0.02,
            high=_VLDO + 0.02,
            source="section 4.9: with both requests high the source pair is closed; within "
            "20 mV asked here",
        ),
    ]


def _change(ctx: Context, case: _Case, run: RunResult) -> list[Figure]:
    """The figures of a run in which one pair opens and the other closes."""
    time = run.real("time")
    to_source = run.real("gate_src")[-1] > common.LOGIC_VOLTS / 2.0
    old, new = ("amp", "src") if to_source else ("src", "amp")
    old_drive = run.real(f"g_{old}") - run.real(f"s_{old}")
    new_drive = run.real(f"g_{new}") - run.real(f"s_{new}")
    opened = measure.first_crossing(time, old_drive, 2.0, rising=False, after=_EVENT - 1e-6)
    closes = measure.first_crossing(time, new_drive, _THRESHOLD_LEAST, rising=True, after=_EVENT)
    key = case.name.replace("-", "_")
    return [
        Figure(
            f"overlap_{key}",
            f"Time with both pairs conducting: {case.text}",
            _overlap(ctx, run),
            "s",
            high=0.0,
            source="section 4.9: no time with both pairs conducting, also with no dead time",
        ),
        Figure(
            f"opens_{key}",
            f"Old pair below 2 V of gate-source voltage after the edge: {case.text}",
            opened - _EVENT,
            "s",
            high=1e-6,
            source="section 4.2: a pair opens within 1 us",
        ),
        Figure(
            f"break_{key}",
            f"From there to the lowest threshold at the gate of the new pair: {case.text}",
            closes - opened,
            "s",
            low=0.0,
            source="section 4.2: break-before-make from the slow closing and the fast opening",
        ),
    ]


@bench(
    "path_switching",
    "interlock",
    "The interlock of the two mode pairs and a change of mode",
    "sections 4.2 and 4.9 (interlock, D-62), rule F-23, the open check of section 16",
)
def interlock(ctx: Context) -> Outcome:
    """Both supplies are present, at different voltages, and the requests change.

    The external supply stands at 5 V and the stand-in for the regulator at
    3.3 V, so that a current between the two would show at once. In the
    first runs both requests end high: together from idle, with the
    interlock transistor at its highest threshold, and with the source
    request added while ampere mode runs. In the others the mode changes in
    either direction, without dead time and with the 5 ms of rule F-23. A
    pair counts as conducting above 10 mA. The output pair is open in every
    run, as rule F-23 orders it for a change of mode.
    """
    runs = ctx.run_many({case.name: _deck(ctx, case) for case in _CASES[1:]})
    first = _CASES[0]
    runs[first.name] = ctx.run(first.name, _deck(ctx, first))
    figures: list[Figure] = []
    for case in _CASES:
        run = runs[case.name]
        if case.name in ("both", "both-weak", "added"):
            figures += _held(case, run)
        if case.name not in ("both", "both-weak"):
            figures += _change(ctx, case, run)

    def millis(run: RunResult) -> np.ndarray:
        return (run.real("time") - _EVENT) * 1e3

    both = runs["both"]
    held = Graph(
        name="both",
        title="Both requests raised together: the source pair closes, VIN stays isolated",
        xlabel="Time after the requests (ms)",
        panels=(Panel("Lines and gates (V)"), Panel("Path (V)"), Panel("Current (mA)")),
        traces=(
            Trace(millis(both), both.real("gate_src"), "request GATE_SRC", 0, "--"),
            Trace(millis(both), both.real("gate_amp"), "request GATE_AMP", 0, ":"),
            Trace(millis(both), both.real("amp_in"), "input of the ampere driver", 0),
            Trace(millis(both), both.real("g_src"), "gate of the source pair (TP31)", 0),
            Trace(millis(both), both.real("g_amp"), "gate of the ampere pair (TP32)", 0),
            Trace(millis(both), both.real("vin_p"), "VIN behind the fuse (TP27)", 1, "--"),
            Trace(millis(both), both.real("ldo_out"), "regulator output", 1, ":"),
            Trace(millis(both), both.real("supply"), "supply node (TP33)", 1),
            Trace(millis(both), both.real("vlead#branch") * 1e3, "from the VIN terminal", 2),
            Trace(millis(both), -both.real("vldo#branch") * 1e3, "from the regulator", 2),
        ),
    )
    added = runs["added"]
    time = added.real("time")
    near = (time >= _EVENT - 0.1e-6) & (time <= _EVENT + 0.6e-6)
    micro = (time[near] - _EVENT) * 1e6
    edge = Graph(
        name="added",
        title="Ampere mode running and the source request is added: the first 0.6 us",
        xlabel="Time after the source request (us)",
        panels=(Panel("Lines (V)"), Panel("Ampere pair (V)")),
        traces=(
            Trace(micro, added.real("gate_src")[near], "request GATE_SRC", 0),
            Trace(micro, added.real("gate_amp")[near], "request GATE_AMP", 0, "--"),
            Trace(micro, added.real("amp_in")[near], "input of the ampere driver", 0),
            Trace(micro, added.real("drv_amp")[near], "driver output", 1, ":"),
            Trace(micro, added.real("g_amp")[near], "gate (TP32)", 1),
            Trace(micro, added.real("s_amp")[near], "common source", 1),
        ),
    )
    change = runs["to-source"]
    handover = Graph(
        name="to-source",
        title="Ampere at 5 V to source at 3.3 V with no dead time",
        xlabel="Time after the change (ms)",
        panels=(Panel("Gates (V)"), Panel("Path (V)"), Panel("Current into the pairs (mA)")),
        traces=(
            Trace(millis(change), change.real("g_amp"), "gate of the ampere pair", 0),
            Trace(millis(change), change.real("g_src"), "gate of the source pair", 0),
            Trace(millis(change), change.real("supply"), "supply node (TP33)", 1),
            Trace(millis(change), change.real("ldo_out"), "regulator output", 1, "--"),
            Trace(millis(change), common.through(ctx, change, "ampere") * 1e3, "from VIN (Q5)", 2),
            Trace(
                millis(change),
                common.through(ctx, change, "source") * 1e3,
                "from the regulator (Q4)",
                2,
            ),
        ),
    )
    notes = (
        "The requests are pins behind 33 ohm with edges of 10 ns that arrive "
        "together; a request at a level between the logic levels is not covered, as "
        "the specification says.",
        "The driver is a behavioral model with a threshold of 1.5 V and no input "
        "current. The interlock transistors carry the largest capacitances of their "
        "datasheet, which delays the input of the ampere driver by about 40 ns.",
        "The regulator is a voltage source that also takes current. After a change "
        "to a lower voltage the charge of the supply node flows back through the new "
        "pair, at the pace of its gate ramp: some milliamperes, shown as a negative "
        "current. What a regulator that cannot take current does with it is the "
        "matter of the bench hand-over.",
        "With no dead time the new pair begins to carry current about 4 ms after "
        "the old pair has opened: its gate has to pass the voltage of its supply "
        "first. The pair that opened rests near its lowest threshold for about 3 ms "
        "(bench open), without a path to conduct into.",
    )
    return Outcome(tuple(figures), (held, edge, handover), notes)
