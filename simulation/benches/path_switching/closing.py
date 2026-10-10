"""A mode pair closes on a live supply: gate ramp, follower, in-rush."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.path_switching import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_REQUEST = 1e-3
"""Instant at which the request of the pair goes high."""

_END = 61e-3
"""End of the run: 60 ms after the request."""

_CLOSED_AFTER = 40e-3
"""Time after which firmware counts the path as closed (rule F-24)."""

_LEADS = 1e-6
"""Inductance of the supply leads in the ampere mode runs: about 1 m."""

_SLOPE_STEP = 0.1e-3
"""Window over which the slope of the supply node is taken."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One run: a pair and the voltage it closes on.

    Attributes:
        pair: ``ampere`` or ``source``.
        volts: Voltage of the supply or of the regulator output.
    """

    pair: str
    volts: float

    @property
    def tag(self) -> str:
        """Short name of the run, also part of the figure keys."""
        return f"{self.pair}_{self.volts:g}v".replace(".", "p")

    @property
    def suffix(self) -> str:
        """The suffix of the node names of this pair."""
        return "amp" if self.pair == "ampere" else "src"

    @property
    def text(self) -> str:
        """The case as the labels name it."""
        return f"{self.pair} pair on {self.volts:g} V"


_CASES = (_Case("ampere", 5.0), _Case("ampere", 0.8), _Case("source", 5.0), _Case("source", 0.8))


def _deck(ctx: Context, case: _Case) -> str:
    """The pair of a case closes with the output open and range 3 selected."""
    edge = ((0.0, False), (_REQUEST, True))
    if case.pair == "ampere":
        stimulus = (
            common.supply(case.volts, henries=_LEADS)
            + common.no_regulator()
            + common.requests(ampere=edge)
        )
        current = "vlead#branch"
    else:
        stimulus = common.regulator(case.volts) + common.no_supply() + common.requests(source=edge)
        current = "vldo#branch"
    suffix = case.suffix
    control = [
        f"save g_{suffix} s_{suffix} ramp_{suffix} drv_{suffix} b_{suffix} supply vout_s "
        f"vin_p ldo_out gate_src gate_amp amp_in {current} @mq10[id] @mq11[id]",
        f"tran 10u {_END:g} 0 20u",
    ]
    return common.deck(
        ctx,
        f"Closing of the {case.text}: output open, range 3 selected",
        common.circuit(ctx),
        common.rails(),
        common.range_lines(3),
        stimulus,
        control=control,
    )


def _figures(case: _Case, run: RunResult) -> list[Figure]:
    """The figures of one run."""
    suffix = case.suffix
    time = run.real("time")
    gate, source, node = run.real(f"g_{suffix}"), run.real(f"s_{suffix}"), run.real("supply")
    sign = 1.0 if case.pair == "ampere" else -1.0
    current = sign * run.real("vlead#branch" if case.pair == "ampere" else "vldo#branch")
    clamp = run.real("@mq10[id]") + run.real("@mq11[id]")
    final_gate = measure.mean(time, gate, _END - 1e-3, _END)
    # The gate climbs its first step in tens of microseconds and then ramps;
    # two points of the ramp, carried back to the request, give the step.
    early, later = _REQUEST + 0.3e-3, _REQUEST + 0.6e-3
    gate_early = measure.value_at(time, gate, early)
    gate_later = measure.value_at(time, gate, later)
    step = gate_early - (gate_later - gate_early)
    reaches = measure.first_crossing(
        time, gate, step + 0.632 * (final_gate - step), rising=True, after=_REQUEST
    )
    conducts = measure.first_crossing(time, node, 0.05 * case.volts, rising=True, after=_REQUEST)
    grid = np.arange(_REQUEST, _REQUEST + 15e-3, _SLOPE_STEP)
    slope = float(np.max(np.diff(np.interp(grid, time, node)) / _SLOPE_STEP))
    nearly = measure.first_crossing(time, node, 0.95 * case.volts, rising=True, after=_REQUEST)
    at_closed = _REQUEST + _CLOSED_AFTER
    gate_closed = measure.value_at(time, gate, at_closed)
    drive_closed = gate_closed - measure.value_at(time, source, at_closed)
    drive_final = final_gate - measure.mean(time, source, _END - 1e-3, _END)
    tag, text = case.tag, case.text
    section = "sections 4.2 and 4.9"
    return [
        Figure(
            f"step_{tag}",
            f"First step of the gate, {text}",
            step,
            "V",
            expected=0.76,
            high=1.1,
            source=f"{section}: 0.76 V, below the lowest threshold of 1.1 V, calculated",
        ),
        Figure(
            f"ramp_{tag}",
            f"Gate at 63 % of its way after, {text}",
            reaches - _REQUEST,
            "s",
            expected=10.7e-3,
            low=9.6e-3,
            high=11.8e-3,
            source=f"{section}: the gate rises with 10.7 ms, calculated; 10 % asked here",
        ),
        Figure(
            f"conducts_{tag}",
            f"Supply node at 5 % after, {text}",
            conducts - _REQUEST,
            "s",
            expected=1e-3 if case.volts == 5.0 else None,
            source="section 16: conduction after about 1 ms on 5 V" if case.volts == 5.0 else "",
        ),
        Figure(
            f"slope_{tag}",
            f"Largest slope of the supply node, {text}",
            slope,
            "V/s",
            expected=900.0,
            low=700.0,
            high=1100.0,
            source="section 4.2: about 0.9 V/ms; 0.7 V/ms to 1.1 V/ms taken as about",
        ),
        Figure(
            f"nearly_{tag}",
            f"Supply node at 95 % after, {text}",
            nearly - _REQUEST,
            "s",
            expected=9e-3 if case.volts == 5.0 else None,
            source="section 16: 95 % after about 9 ms on 5 V" if case.volts == 5.0 else "",
        ),
        Figure(
            f"closed_{tag}",
            f"Gate-source voltage 40 ms after the request, share of its final value, {text}",
            100.0 * drive_closed / drive_final,
            "%",
            low=95.0,
            source="rule F-24: the path counts as closed after 40 ms; 95 % asked here",
        ),
        Figure(
            f"drive_{tag}",
            f"Final gate-source voltage, {text}",
            drive_final,
            "V",
            expected=0.957 * (common.RAIL_VOLTS - case.volts),
            low=6.2,
            source="section 4.9: 95.7 % of the drive, at least 6.2 V",
        ),
        Figure(
            f"inrush_{tag}",
            f"Largest current into the pair while it closes, {text}",
            float(np.max(current[time >= _REQUEST])),
            "A",
            source="",
        ),
        Figure(
            f"overshoot_{tag}",
            f"Supply node above its final value at the most, {text}",
            measure.extremes(time, node, _REQUEST, _END)[1]
            - measure.mean(time, node, _END - 1e-3, _END),
            "V",
            high=0.01,
            source="section 4.9: the supply node does not ring, simulated; 10 mV asked here",
        ),
        Figure(
            f"clamp_{tag}",
            f"Largest current in the ladder clamp, {text}",
            float(np.max(np.abs(clamp))),
            "A",
            high=1e-6,
            source="section 4.9: no current in the ladder clamp, simulated; 1 uA asked here",
        ),
    ]


@bench(
    "path_switching",
    "close",
    "A mode pair closes on a live supply: gate ramp and source follower",
    "sections 4.2 and 4.9 (mode switches, D-61), rule F-24, the open check of section 16",
)
def close(ctx: Context) -> Outcome:
    """Each mode pair closes on a supply that is already there, at 5 V and at 0.8 V.

    The request of the pair goes high with the output pair open and range 3
    selected, as rule F-24 orders it. The run shows the gate behind its
    network, the common source of the pair, the supply node of the ladder
    and the current that the pair takes from the supply while the
    capacitors of that node charge. The ampere pair closes on an external
    supply behind 1 uH of leads, the source pair on a voltage source that
    stands for the regulator.
    """
    runs = ctx.run_many({case.tag: _deck(ctx, case) for case in _CASES[1:]})
    first = _CASES[0]
    runs[first.tag] = ctx.run(first.tag, _deck(ctx, first))
    figures: list[Figure] = []
    for case in _CASES:
        figures += _figures(case, runs[case.tag])

    def millis(run: RunResult) -> np.ndarray:
        return (run.real("time") - _REQUEST) * 1e3

    shown = runs[first.tag]
    graph = Graph(
        name="ampere-5v",
        title="The ampere pair closes on a live 5 V supply behind 1 uH of leads",
        xlabel="Time after the request (ms)",
        panels=(
            Panel("Gate network (V)", marks=((common.RAIL_VOLTS, "+12 V_A"),)),
            Panel("Path (V)"),
            Panel("Current from the supply (mA)"),
        ),
        traces=(
            Trace(millis(shown), shown.real("drv_amp"), "driver output", 0, "--"),
            Trace(millis(shown), shown.real("g_amp"), "gate (TP32)", 0),
            Trace(millis(shown), shown.real("ramp_amp"), "node between C61 and R82", 0, ":"),
            Trace(millis(shown), shown.real("vin_p"), "VIN behind the fuse (TP27)", 1, "--"),
            Trace(millis(shown), shown.real("s_amp"), "common source of the pair", 1),
            Trace(millis(shown), shown.real("supply"), "supply node (TP33)", 1),
            Trace(millis(shown), shown.real("vlead#branch") * 1e3, "", 2),
        ),
        xmarks=((_CLOSED_AFTER * 1e3, "counts as closed (F-24)"),),
    )
    traces = []
    for case in _CASES:
        run = runs[case.tag]
        traces.append(Trace(millis(run), run.real(f"g_{case.suffix}"), case.text, 0))
        traces.append(Trace(millis(run), run.real("supply"), case.text, 1))
    every = Graph(
        name="all",
        title="Both pairs at 5 V and at 0.8 V: gate and supply node",
        xlabel="Time after the request (ms)",
        panels=(Panel("Gate of the pair (V)"), Panel("Supply node (V)")),
        traces=tuple(traces),
        xmarks=((_CLOSED_AFTER * 1e3, "counts as closed (F-24)"),),
    )
    notes = (
        "The regulator is a voltage source behind 20 mohm and the external supply a "
        "voltage source behind 1 uH and 40 mohm of leads: neither sags, and the "
        "response of the regulator is not in these runs.",
        "The transistors are the typical model at 25 C and the driver a behavioral "
        "model; the first step of the gate is taken from the ramp carried back to "
        "the instant of the request.",
        "The capacitors have their nominal values: an X7R part of 4.7 uF keeps less "
        "under bias, which makes the in-rush smaller, not larger.",
        "The limit of 6.2 V for the gate-source voltage is the figure of the "
        "specification; at 0.8 V the drive is larger and the limit is not at stake.",
    )
    return Outcome(tuple(figures), (graph, every), notes)
