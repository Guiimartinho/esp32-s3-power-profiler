"""The two paths at rest: drop at 1 A, gate drive, current taken from the VIN terminal."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.path_switching import common
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_LOAD_AMPS = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
"""Load currents of each run, A: none first, then up to the 1 A of requirement R-06."""

_BUDGET = 0.200
"""Total path drop at 1 A that requirement R-06 allows, V."""

_COPPER = (0.020, 0.025)
"""Resistance the specification allows for copper and contacts, ohm: typical and
at the bounds (notes on requirement R-06; allowances without a source)."""

_RAIL_LOW = 11.4
"""Lower limit of +12 V_A in the rails test of firmware, V (rule F-12)."""

_PATH_TRANSISTORS = {"ampere": ("Q5", "Q9"), "source": ("Q4", "Q8")}

_OTHER_TRANSISTORS = ("Q14", "Q15", "Q16")
"""The range 3 switch and the output pair: the same part type on other sheets."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One run: a mode, the voltage that feeds it and the parts.

    Attributes:
        mode: ``ampere`` or ``source``.
        volts: Voltage at the VIN terminal or at the regulator output.
        bounds: Every transistor of the path at its largest on-resistance
            and +12 V_A at its lower limit.
    """

    mode: str
    volts: float
    bounds: bool = False

    @property
    def tag(self) -> str:
        """Short name of the run."""
        text = f"{self.mode}_{self.volts:g}v" + ("_bounds" if self.bounds else "")
        return text.replace(".", "p")

    @property
    def text(self) -> str:
        """The case as the labels name it."""
        parts = ", largest on-resistance and +12 V_A at 11.4 V" if self.bounds else ""
        return f"{self.mode} mode at {self.volts:g} V{parts}"


_CASES = (
    _Case("ampere", 5.0),
    _Case("ampere", 5.0, bounds=True),
    _Case("ampere", 3.3),
    _Case("ampere", 0.8),
    _Case("source", 5.0),
    _Case("source", 5.0, bounds=True),
    _Case("source", 0.8),
    _Case("ampere", 5.4),
    _Case("ampere", 5.4, bounds=True),
)
"""The last two stand just below the lowest trip level of the detector, where
the pair has the least gate drive."""


def _deck(ctx: Context, case: _Case, closed: bool = True) -> str:
    """One mode held, the load current stepped from zero to 1 A.

    The detector comparator is left out and its output held low: a
    comparator with hysteresis has two stable states inside its band, and
    every run here is below the trip level.
    """
    overrides: dict[str, PartModel] = {}
    if case.bounds:
        refs = (*_PATH_TRANSISTORS[case.mode], *_OTHER_TRANSISTORS)
        overrides = {ref: common.transistor("RMAX") for ref in refs}
    if case.mode == "ampere":
        feed = (
            "* the external supply on the terminal, without leads\n"
            f"Vin vin_src 0 {case.volts:g}\n"
            "Vlead vin_src vin_raw 0\n" + common.no_regulator()
        )
        requests = common.requests(ampere=((0.0, closed),))
    else:
        feed = common.regulator(case.volts, ohms=1e-6) + common.no_supply()
        requests = common.requests(source=((0.0, closed),))
    stimulus = (
        feed + requests + "* the detector output held low in place of the comparator\n"
        "Vov vin_ov 0 0\n"
        "* the load: a current sink at the output terminal\n"
        "Iload vout 0 0\n"
    )
    control = []
    for amps in _LOAD_AMPS:
        control += [f"alter Iload dc = {amps:g}", "op"]
    return common.deck(
        ctx,
        f"Path at rest: {case.text}" + ("" if closed else ", pair open"),
        common.circuit(ctx, output=True, leave_out=("U21",), overrides=overrides),
        common.rails(p12=_RAIL_LOW if case.bounds else common.RAIL_VOLTS),
        common.range_lines(3, output=closed),
        stimulus,
        control=control,
    )


def _node(run: RunResult, name: str, step: int) -> float:
    """A node voltage at one load step."""
    return float(run.real(name, plot=f"op{step + 1}")[0])


@bench(
    "path_switching",
    "drop",
    "The two paths at rest: drop at 1 A, gate drive and current taken from VIN",
    "requirement R-06 (D-64), sections 4.9 (gate drive, current of the terminal) and 11",
)
def drop(ctx: Context) -> Outcome:
    """Each mode is held with the output pair closed and the load is stepped to 1 A.

    The run gives the voltage from the feeding point, the VIN terminal or
    the regulator output, to the output terminal, and the share of each
    part of the path: fuse, mode pair, range 3 with its shunt, output pair.
    It is made with typical transistors and with every transistor of the
    path at its largest on-resistance while +12 V_A stands at its lower
    limit. The step without load gives the gate-source voltage of the pair
    and the current that the instrument itself takes from the VIN terminal.
    """
    runs = ctx.run_many({case.tag: _deck(ctx, case) for case in _CASES[1:]})
    first = _CASES[0]
    runs[first.tag] = ctx.run(first.tag, _deck(ctx, first))
    opened = ctx.run("open", _deck(ctx, first, closed=False), keep=False)
    last = len(_LOAD_AMPS) - 1
    figures: list[Figure] = []
    traces: list[Trace] = []
    for case in _CASES:
        run = runs[case.tag]
        feed = "vin_raw" if case.mode == "ampere" else "ldo_out"
        suffix = "amp" if case.mode == "ampere" else "src"
        total = _node(run, feed, last) - _node(run, "vout", last)
        copper = _COPPER[1] if case.bounds else _COPPER[0]
        drive = _node(run, f"g_{suffix}", 0) - _node(run, f"s_{suffix}", 0)
        if case.volts == 5.4:
            figures.append(
                Figure(
                    f"drive_{case.tag}",
                    f"Gate-source voltage of the pair without load: {case.text}",
                    drive,
                    "V",
                    low=6.2,
                    source="section 4.9: at least 6.2 V of gate-source voltage, calculated",
                )
            )
            continue
        expected = {
            ("ampere", False): 0.158,
            ("ampere", True): 0.181,
            ("source", False): 0.144,
            ("source", True): 0.161,
        }
        stated = expected[(case.mode, case.bounds)] if case.volts == 5.0 else None
        pair = _node(run, "vin_p" if case.mode == "ampere" else "ldo_out", last) - _node(
            run, "supply", last
        )
        figures += [
            Figure(
                f"drop_{case.tag}",
                f"Drop at 1 A from the feeding point to the output terminal, parts alone: "
                f"{case.text}",
                total,
                "V",
                source="",
            ),
            Figure(
                f"budget_{case.tag}",
                f"The same with the {copper * 1e3:g} mohm that the specification allows for "
                f"copper and contacts: {case.text}",
                total + copper,
                "V",
                expected=stated,
                high=_BUDGET,
                source="requirement R-06: 200 mV at 1 A"
                + (f"; {stated * 1e3:g} mV calculated at 50 C" if stated is not None else ""),
            ),
            Figure(
                f"pair_{case.tag}",
                f"Drop of the mode pair at 1 A: {case.text}",
                pair,
                "V",
                source="",
            ),
        ]
        if case.volts == 5.0:
            figures.append(
                Figure(
                    f"drive_{case.tag}",
                    f"Gate-source voltage of the pair without load: {case.text}",
                    drive,
                    "V",
                    expected=None if case.bounds else 0.957 * (common.RAIL_VOLTS - 5.0),
                    low=6.2,
                    source="section 4.9: 95.7 % of the drive, at least 6.2 V, calculated",
                )
            )
        if case.mode == "ampere" and not case.bounds:
            figures.append(
                Figure(
                    f"fuse_{case.tag}",
                    f"Drop of the fuse at 1 A: {case.text}",
                    _node(run, "vin_raw", last) - _node(run, "vin_p", last),
                    "V",
                    source="",
                )
            )
            taken = float(run.real("vlead#branch", plot="op1")[0])
            stated_current = 125e-6 if case.volts == 5.0 else None
            figures.append(
                Figure(
                    f"taken_{case.tag}",
                    f"Current the instrument takes from the terminal, pair closed, no load: "
                    f"{case.text}",
                    taken,
                    "A",
                    expected=stated_current,
                    low=115e-6 if stated_current else None,
                    high=135e-6 if stated_current else None,
                    source="section 4.9: about 125 uA at 5 V, simulated; 8 % asked here"
                    if stated_current
                    else "",
                )
            )
        amps = np.asarray(_LOAD_AMPS)
        drops = np.array(
            [_node(run, feed, step) - _node(run, "vout", step) for step in range(len(_LOAD_AMPS))]
        )
        if case.volts != 3.3:
            traces.append(Trace(amps, drops * 1e3, case.text, 0))
    first_run = runs[first.tag]
    shares = {
        "fuse F1": ("vin_raw", "vin_p"),
        "ampere pair Q5, Q9": ("vin_p", "supply"),
        "range 3: Q14 and the 0.1 ohm shunt": ("supply", "vout_s"),
        "output pair Q15, Q16": ("vout_s", "vout"),
    }
    for text, (high, low) in shares.items():
        key = text.split(":")[0].split(" Q")[0].split(" F")[0].replace(" ", "_")
        figures.append(
            Figure(
                f"share_{key}",
                f"Share of the 200 mV of requirement R-06 at 1 A, ampere mode at 5 V: {text}",
                100.0 * (_node(first_run, high, last) - _node(first_run, low, last)) / _BUDGET,
                "%",
                source="",
            )
        )
    source_run = runs[_Case("source", 5.0).tag]
    bounds_run = runs[_Case("ampere", 5.0, bounds=True).tag]
    both_pairs = (
        _node(first_run, "vin_p", last)
        - _node(first_run, "supply", last)
        + _node(source_run, "ldo_out", last)
        - _node(source_run, "supply", last)
    )
    bounds_drop = _node(bounds_run, "vin_raw", last) - _node(bounds_run, "vout", last)
    figures += [
        Figure(
            "both_pairs",
            "Resistance of the two mode pairs in series at 5 V, from their drops at 1 A",
            both_pairs / _LOAD_AMPS[-1],
            "ohm",
            expected=0.017,
            source="section 15, D-62: with both pairs on, VIN would be tied to the "
            "regulator output through 17 mohm, calculated",
        ),
        Figure(
            "copper_left",
            "Copper and contacts that the 200 mV leave in ampere mode, parts at their "
            "largest on-resistance",
            (_BUDGET - bounds_drop) / _LOAD_AMPS[-1],
            "ohm",
            expected=0.044,
            source="section 11: the margin is lost if copper and contacts pass about "
            "44 mohm, calculated at 50 C",
        ),
        Figure(
            "terminal_5v",
            "Voltage at the output terminal with 5.0 V at the VIN terminal and 1 A, parts alone",
            _node(first_run, "vout", last),
            "V",
            source="",
        ),
        Figure(
            "taken_open",
            "Current the instrument takes from the terminal at 5 V, pair open",
            float(opened.real("vlead#branch", plot="op1")[0]),
            "A",
            expected=35e-6,
            low=33e-6,
            high=37e-6,
            source="section 4.9: 35 uA, calculated; 5 % asked here",
        ),
    ]
    graph = Graph(
        name="drop",
        title="Drop from the feeding point to the output terminal against the load, parts alone",
        xlabel="Load current (A)",
        panels=(Panel("Drop (mV)", marks=((_BUDGET * 1e3, "200 mV of R-06, copper included"),)),),
        traces=tuple(traces),
    )
    notes = (
        "The circuit holds no copper and no contacts: the board is not in the "
        "netlist. The specification allows 20 mohm to 25 mohm for them, without a "
        "source; that allowance is added to the simulated drop before it is "
        "compared with requirement R-06. The layout calculation of the board gives "
        "10.4 mohm and 12.3 mohm for the copper alone.",
        "The transistors are typical parts at 25 C, or parts at the largest "
        "on-resistance of their datasheet at 25 C. The specification calculates "
        "with 50 C, where the on-resistance is about 9 % higher (datasheet curve), "
        "and with allowances for the fuse that this run does not have: its bounds "
        "are 15 mV higher than the ones here, and the copper that the budget "
        "leaves is 44 mohm in its calculation against 59 mohm here. The fuse is "
        "its cold resistance of 14 mohm; its datasheet states no tolerance.",
        "The range 3 switch, the shunt and the output pair are parts of other "
        "sheets, taken from the netlist to close the path.",
        "The detector comparator is left out and its output held low, because a "
        "comparator with hysteresis has two stable states inside its band. The "
        "runs at 5.4 V stand just below the lowest trip level of 5.41 V: there the "
        "pair has the least gate drive it can have while it is closed.",
    )
    return Outcome(tuple(figures), (graph,), notes)
