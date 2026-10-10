"""The rail monitor: its thresholds, their hysteresis, and an edge that moves its threshold."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.analog_rails import common
from circuit_sim import measure, tolerance
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_SETTLE = 5e-3
"""Time for the thresholds to stand before the first rail is moved."""

_SLOPE = 40e-3
"""Time a rail takes for one direction of its sweep."""

_RUNS = 36
"""Number of random sets of tolerances."""

_OFFSET = 10e-3
"""Largest input offset of a comparator (datasheet)."""

_SUPPLY_TOLERANCE = 0.02
"""Tolerance of the 3.3 V regulators (datasheet)."""

_MIDDLE = 1.35
"""Half the high level of PWR_GOOD: the level at which an edge is counted."""

_EDGE_SPAN = 0.06
"""How far +12V_A moves in a crossing run: 30 mV to either side of its threshold."""

NL = "\n"
"""Line break between the lines of a deck."""


@dataclass(frozen=True, slots=True)
class _Rail:
    """One watched rail and its sweep.

    Attributes:
        key: Short name, part of the figure keys.
        label: Name of the rail in the report.
        node: Node of the rail.
        good: Level of the rail when it is good.
        bad: Level at the far end of the sweep, beyond the threshold.
        nominal: Threshold that the specification states.
        low: Lower end of the band of the specification.
        high: Upper end of that band.
    """

    key: str
    label: str
    node: str
    good: float
    bad: float
    nominal: float
    low: float
    high: float


_RAILS = (
    _Rail("3v3a", "3V3_A", "p3v3_a", 3.3, 2.7, 2.97, 2.89, 3.05),
    _Rail("12v", "+12V_A", "p12v_a", 12.0, 8.5, 9.85, 9.25, 10.48),
    _Rail("m4v", "-4V_A", "m4v_a", -4.0, -1.5, -2.57, -2.86, -2.29),
    _Rail("vref", "VREF", "vref", 2.5, 2.0, 2.245, 2.14, 2.35),
)
"""The four rails with the thresholds and bands of section 3."""


def _comparators(hysteresis: float, offset: float) -> PartModel:
    """The four comparators with a chosen hysteresis and offset."""
    return PartModel(
        kind="subckt",
        name="MCP6569_OD",
        units=(
            ("3", "2", "1", "4", "11"),
            ("5", "6", "7", "4", "11"),
            ("10", "9", "8", "4", "11"),
            ("12", "13", "14", "4", "11"),
        ),
        library=common.LIBRARY,
        origin="written here",
        params=f"vhy={hysteresis:g} vos={offset:g}",
    )


def _refs(ctx: Context) -> tuple[str, ...]:
    return (*ctx.netlist.on_sheet(common.MONITOR_SHEET), "R4")


def _sweep_deck(ctx: Context, scales: dict[str, float], offset: float, supply: float) -> str:
    """Every rail in turn falls through its threshold and comes back."""
    circuit = ctx.circuit(_refs(ctx), common.ALIASES, {"U14": _comparators(3.5e-3, offset)}, scales)
    lines = ["* 3V3_C stands, the four watched rails are moved one after the other"]
    lines.append(f"V3c p3v3_c 0 PWL(0 0 1m {supply:g})")
    for index, rail in enumerate(_RAILS):
        begin = _SETTLE + 2.0 * _SLOPE * index
        lines.append(
            f"V{rail.key} {rail.node} 0 PWL(0 0 1m {rail.good:g} {begin:g} {rail.good:g} "
            f"{begin + _SLOPE:g} {rail.bad:g} {begin + 2 * _SLOPE:g} {rail.good:g})"
        )
    lines.append("Cgp28 gp28 0 5p")
    stop = _SETTLE + 2.0 * _SLOPE * len(_RAILS) + 2e-3
    return ctx.deck(
        "Rail monitor: every rail through its threshold and back",
        circuit,
        "\n".join(lines),
        control=[
            "save p3v3_c p3v3_a p12v_a m4v_a vref pwr_good gp28 th_low th_high",
            f"tran 10u {stop:g} 0 10u",
        ],
    )


def _thresholds(run: RunResult) -> dict[str, tuple[float, float]]:
    """For each rail the level at which the flag fell and the level at which it returned."""
    time = run.real("time")
    flag = run.real("gp28")
    found: dict[str, tuple[float, float]] = {}
    for index, rail in enumerate(_RAILS):
        begin = _SETTLE + 2.0 * _SLOPE * index
        wave = run.real(rail.node)
        fell = common.crossing_after(time, flag, _MIDDLE, False, begin)
        rose = common.crossing_after(time, flag, _MIDDLE, True, begin + _SLOPE)
        found[rail.key] = (
            float(np.interp(fell, time, wave)) if np.isfinite(fell) else float("nan"),
            float(np.interp(rose, time, wave)) if np.isfinite(rose) else float("nan"),
        )
    return found


def _edge_deck(
    ctx: Context, hysteresis: float, coupling: float, capacitors: float, slope: float
) -> str:
    """+12V_A crosses its threshold, with the capacitance between neighboring pins.

    Args:
        ctx: The bench context.
        hysteresis: Hysteresis of the comparators.
        coupling: Capacitance between an output pin and the input beside it.
        capacitors: Factor on C32 to C34: 1 as drawn, close to 0 for none.
        slope: Slope of +12V_A in volts per second.
    """
    scales = {"C32": capacitors, "C33": capacitors, "C34": capacitors}
    circuit = ctx.circuit(
        _refs(ctx), common.ALIASES, {"U14": _comparators(hysteresis, 0.0)}, scales
    )
    # +12V_A crosses 9.854 V in the middle of the ramp
    ramp = _EDGE_SPAN / slope
    lines = [
        "* every rail good, +12V_A rising through its threshold",
        "V3c p3v3_c 0 PWL(0 0 1m 3.3)",
        "V3a p3v3_a 0 PWL(0 0 1m 3.3)",
        "Vm4 m4v_a 0 PWL(0 0 1m -4)",
        "Vref vref 0 PWL(0 0 1m 2.5)",
        f"V12 p12v_a 0 PWL(0 0 1m {9.854 - _EDGE_SPAN / 2:g} 3m {9.854 - _EDGE_SPAN / 2:g} "
        f"{3e-3 + ramp:g} {9.854 + _EDGE_SPAN / 2:g})",
        "* capacitance between each output pin and the inverting input beside it:",
        "* pins 1 and 2, 7 and 6, 8 and 9, 14 and 13 of the package",
        f"Cpin12 pwr_good th_low {coupling:g}",
        f"Cpin76 pwr_good sense_m4 {coupling:g}",
        f"Cpin89 pwr_good th_high {coupling:g}",
        f"Cpin1413 pwr_good th_low {coupling:g}",
        "Cgp28 gp28 0 5p",
    ]
    return ctx.deck(
        f"Rail monitor: crossing at {slope:g} V/s, hysteresis {hysteresis * 1e3:g} mV, "
        f"{coupling * 1e12:g} pF between pins, capacitors times {capacitors:g}",
        circuit,
        NL.join(lines),
        control=[
            "save p12v_a pwr_good th_low sense_p12",
            f"tran 1u {3e-3 + ramp:g} 0 {min(ramp / 2000, 5e-6):g}",
        ],
    )


def _edges(run: RunResult) -> tuple[int, float, float]:
    """Number of edges of the flag, the time they span, the largest step of the threshold."""
    time = run.real("time")
    flag = run.real("pwr_good")
    found = measure.crossings(time, flag, _MIDDLE)
    found = found[found > 2.9e-3]
    if found.size == 0:
        return 0, 0.0, 0.0
    threshold = run.real("th_low")
    # the level of the threshold just before the edge: with larger capacitors it
    # has not settled when the run begins
    rest = measure.mean(time, threshold, found[0] - 0.3e-3, found[0] - 0.02e-3)
    near_edge = (time >= found[0] - 1e-6) & (time <= found[0] + 20e-6)
    step = float(np.max(np.abs(threshold[near_edge] - rest)))
    return int(found.size), float(found[-1] - found[0]), step


@bench(
    "analog_rails",
    "monitor",
    "Rail monitor: thresholds with tolerances, hysteresis, and the edge of PWR_GOOD",
    "section 3 (rail monitor, table of thresholds), section 4.11, decision D-54",
)
def monitor(ctx: Context) -> Outcome:
    """The four watched rails cross their thresholds, slowly, one at a time.

    The circuit is the sheet of the rail monitor with the series resistor of
    the controller pin. 3V3_C stands at 3.3 V and each rail falls through its
    threshold and returns; the level of the rail at the two edges of PWR_GOOD
    is its threshold in each direction. The same run is made with random
    sets of tolerances: every resistor inside its 1 %, the offset of the
    comparators inside 10 mV, 3V3_C inside 2 %.

    Then +12V_A crosses its threshold at 2 V/s and at 400 V/s, the pace of
    its start, with a capacitance between each output pin of the package and
    the inverting input beside it. The run is made with the capacitors C32
    to C34 as drawn, ten times larger and left out, and counts the edges of
    PWR_GOOD.
    """
    nominal = ctx.run("thresholds", _sweep_deck(ctx, {}, 0.0, 3.3))
    found = _thresholds(nominal)
    resistors = tolerance.tolerances(ctx.netlist, _refs(ctx))
    resistors = {ref: limit for ref, limit in resistors.items() if ref.startswith("R")}
    rng = np.random.default_rng(20261010)
    decks = {}
    for index in range(_RUNS):
        scales = tolerance.draw_scales(resistors, rng)
        offset = float(rng.uniform(-_OFFSET, _OFFSET))
        supply = 3.3 * (1.0 + float(rng.uniform(-_SUPPLY_TOLERANCE, _SUPPLY_TOLERANCE)))
        decks[f"mc{index:02d}"] = _sweep_deck(ctx, scales, offset, supply)
    spread = [_thresholds(run) for run in ctx.run_many(decks).values()]
    figures: list[Figure] = []
    for rail in _RAILS:
        fell, rose = found[rail.key]
        every = np.array([[item[rail.key][0], item[rail.key][1]] for item in spread])
        figures += [
            near(
                f"th_{rail.key}",
                f"{rail.label}: PWR_GOOD falls at",
                fell,
                "V",
                rail.nominal,
                0.005,
                "section 3, table of the rail monitor",
            ),
            Figure(
                f"hys_{rail.key}",
                f"{rail.label}: hysteresis, referred to the rail",
                abs(rose - fell),
                "V",
            ),
            Figure(
                f"th_{rail.key}_low",
                f"{rail.label}: lowest threshold over {_RUNS} sets of tolerances",
                float(np.min(every)),
                "V",
                low=rail.low,
                high=rail.high,
                source=f"section 3: band {rail.low:g} V to {rail.high:g} V",
            ),
            Figure(
                f"th_{rail.key}_high",
                f"{rail.label}: highest threshold over {_RUNS} sets of tolerances",
                float(np.max(every)),
                "V",
                low=rail.low,
                high=rail.high,
                source=f"section 3: band {rail.low:g} V to {rail.high:g} V",
            ),
        ]
    time = nominal.real("time")
    figures.append(
        near(
            "high_level",
            "PWR_GOOD high level at the controller pin",
            measure.mean(time, nominal.real("gp28"), 3e-3, 4.5e-3),
            "V",
            0.8193 * 3.3,
            0.01,
            "section 4.11: 0.82 x 3V3_C",
        )
    )
    figures.append(
        Figure(
            "low_level",
            "PWR_GOOD low level while one comparator pulls",
            float(np.min(nominal.real("gp28")[time > _SETTLE])),
            "V",
            high=0.6,
            source="datasheet of the comparators: at most 0.6 V at 3 mA; the pin of the "
            "controller reads low below 0.8 V",
        )
    )
    cases = {
        "drawn-typ": ("capacitors as drawn, 3.5 mV, 0.5 pF, 2 V/s", 3.5e-3, 0.5e-12, 1.0, 2.0),
        "drawn-worst": ("capacitors as drawn, 1 mV, 1 pF, 20 V/s", 1e-3, 1e-12, 1.0, 20.0),
        "drawn-start": ("capacitors as drawn, 1 mV, 1 pF, 400 V/s", 1e-3, 1e-12, 1.0, 400.0),
        "larger": ("capacitors of 10 nF, 1 mV, 1 pF, 2 V/s", 1e-3, 1e-12, 10.0, 2.0),
        "bare": ("no capacitors, 3.5 mV, 0.5 pF, 400 V/s", 3.5e-3, 0.5e-12, 1e-6, 400.0),
    }
    traces: list[Trace] = []
    for index, (key, (label, hysteresis, coupling, factor, slope)) in enumerate(cases.items()):
        deck = _edge_deck(ctx, hysteresis, coupling, factor, slope)
        run = ctx.run(key, deck, keep=index == 0)
        count, lasted, step = _edges(run)
        tag = key.replace("-", "_")
        drawn = factor == 1.0
        figures += [
            Figure(
                f"edges_{tag}",
                f"Edges of PWR_GOOD at one crossing ({label})",
                float(count),
                "",
                high=1.0 if drawn else None,
                source="decision D-54: the capacitors keep an edge from moving its own "
                "threshold; one crossing, one edge"
                if drawn
                else "",
            ),
            Figure(f"burst_{tag}", f"Time from the first edge to the last ({label})", lasted, "s"),
            Figure(
                f"kick_{tag}",
                f"Largest movement of the threshold at the first edge ({label})",
                step,
                "V",
            ),
        ]
        t = run.real("time")
        edges = measure.crossings(t, run.real("pwr_good"), _MIDDLE)
        edges = edges[edges > 2.9e-3]
        if edges.size:
            shown = (t >= edges[0] - 20e-6) & (t <= edges[0] + 180e-6)
            micro = (t[shown] - edges[0]) * 1e6
            traces += [
                Trace(micro, run.real("pwr_good")[shown], label, 0),
                Trace(micro, (run.real("th_low")[shown] - 1.645) * 1e3, label, 1),
            ]
    sweep = Graph(
        name="thresholds",
        title="Every rail through its threshold and back, typical parts",
        xlabel="Time (ms)",
        panels=(Panel("Watched rails (V)"), Panel("PWR_GOOD at the controller pin (V)")),
        traces=(
            *(
                Trace(time[::4] * 1e3, nominal.real(rail.node)[::4], rail.label, 0)
                for rail in _RAILS
            ),
            Trace(time[::4] * 1e3, nominal.real("gp28")[::4], "PWR_GOOD", 1),
        ),
    )
    edge = Graph(
        name="edge",
        title="+12V_A crossing its threshold: the edge of PWR_GOOD and the threshold node",
        xlabel="Time after the first edge (us)",
        panels=(Panel("PWR_GOOD (V)"), Panel("Low threshold around 1.645 V (mV)")),
        traces=tuple(traces),
    )
    notes = (
        "The comparators are one model with an offset and a hysteresis as parameters; "
        "the four of a package take the same offset in a run, so the bands hold for each "
        "threshold alone and not for combinations. The bands of the specification also "
        "hold drift, which is not in these runs.",
        "The hysteresis referred to a rail is that of the comparator, 3.5 mV, divided by "
        "the share of the rail that reaches its input.",
        "The capacitance between an output pin and the input beside it is an assumption, "
        "0.5 pF and 1 pF: the datasheet names the hazard (section 4.7 of it) and gives no "
        "figure, and the board adds its own. With 1 nF at the threshold the step is that "
        "capacitance times the 2.7 V of the edge over 1 nF: comparable with the "
        "hysteresis, whose least value is 1 mV.",
        "The delay of the comparator is a fixed 45 ns here; a real part is slower close "
        "to its threshold, which makes a burst last longer, not shorter.",
    )
    return Outcome(tuple(figures), (sweep, edge), notes)
