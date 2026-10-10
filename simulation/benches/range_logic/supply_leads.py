"""Ampere mode behind supply leads: the sag of the supply node and the ringing."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.range_logic import common
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_PATH_OHMS = 0.035
"""Fuse, closed ampere switch and copper from the VIN terminal to the supply node.

An assumption: the budget of requirement R-06 leaves about this much between
the terminal and the supply node (two switch transistors, the fuse, copper).
"""

_LEADS = {"thin": 0.05 / 1e-6, "heavy": 0.01 / 1e-6}
"""Resistance of the supply leads for every henry of their inductance.

Assumptions: 50 mohm per microhenry stands for laboratory leads of about
0.8 square millimeters, 10 mohm per microhenry for leads of 2.5 square
millimeters or a supply that senses at its terminals.
"""

_INDUCTANCES = (1e-6, 3e-6)
"""Inductance of the supply leads in the ringing runs, H (section 4.4)."""

_CAPACITORS = (10e-6, 22e-6, 47e-6, 100e-6)
"""Capacitors at the load in the ringing runs, F (section 4.4)."""

_TERMINAL_CAPACITOR = 100e-6
"""The capacitor the user documentation asks for at the VIN terminals, F."""

_TERMINAL_ESR = 0.02
"""Its series resistance, ohm (assumption)."""

_LEVEL = 1.15
"""Over-current level in range 3, A."""

_NEVER = 1.0
"""A qualification time that the trip of the model never reaches, s."""

_RINGING = "section 4.4: 12 us to 29 us with 1 uH to 3 uH and 10 uF to 100 uF, simulated"
"""Source of the expected ringing time."""

_STEPS = (0.7, 0.8, 0.9)
"""Load steps below 1.0 A of the last part, A."""


def _supply(henries: float, ohms: float, terminal: bool, volts: float = 5.0) -> str:
    """An external supply behind its leads, as the supply node sees it."""
    lines = [
        "* ampere mode: an external supply that holds its voltage, its leads, and",
        "* the fuse with the closed ampere switch as one resistance",
        f"Vext ext 0 {volts:g}",
        f"Rsupply ext ext_l {ohms:g}",
        f"Lsupply ext_l vin {henries:g}",
    ]
    if terminal:
        lines += [f"Cvin vin vin_c {_TERMINAL_CAPACITOR:g}", f"Rvin vin_c 0 {_TERMINAL_ESR:g}"]
    lines.append(f"Rpath vin supply {_PATH_OHMS:g}")
    return "\n".join(lines) + "\n"


def _sag_deck(ctx: Context, henries: float, ohms: float, delays: common.Delays) -> str:
    return common.step_deck(
        ctx,
        f"Ampere mode, 1 uA to 500 mA with 1 uF behind {henries * 1e6:g} uH of supply lead",
        common.Load(before=1e-6, after=0.5, capacitance=1e-6),
        delays=delays,
        end=60e-6,
        max_step=5e-9,
        supply=_supply(henries, ohms, terminal=False),
    )


@dataclass(frozen=True, slots=True)
class _Case:
    """One ringing run.

    Attributes:
        leads: Key of the lead resistance, ``thin`` or ``heavy``.
        henries: Inductance of the supply leads.
        farads: Capacitor at the load.
        terminal: 100 uF at the VIN terminals.
        active: The trip with its 12 us; without it the trip never acts.
        amps: Load current after the step.
    """

    leads: str
    henries: float
    farads: float
    terminal: bool
    active: bool
    amps: float = 1.0

    @property
    def name(self) -> str:
        """File name of the run."""
        return (
            f"{self.leads}-{self.henries * 1e6:g}uh-{self.farads * 1e6:g}uf-"
            f"{'terminal' if self.terminal else 'bare'}-{'trip' if self.active else 'free'}-"
            f"{self.amps * 1e3:g}ma"
        )


def _ring_deck(ctx: Context, case: _Case) -> str:
    where = "100 uF at VIN" if case.terminal else "no capacitor at VIN"
    return common.step_deck(
        ctx,
        f"Ampere mode, 1 uA to {case.amps:g} A with {case.farads * 1e6:g} uF behind "
        f"{case.henries * 1e6:g} uH of {case.leads} supply lead, {where}",
        common.Load(before=1e-6, after=case.amps, capacitance=case.farads),
        end=200e-6,
        max_step=20e-9,
        trip_time=12e-6 if case.active else _NEVER,
        supply=_supply(case.henries, case.henries * _LEADS[case.leads], case.terminal),
    )


@dataclass(frozen=True, slots=True)
class _Ring:
    """What one ringing run shows.

    Attributes:
        above: Longest time the current in the 0.1 ohm branch is above the level, s.
        tripped: Whether the output line went low.
    """

    above: float
    tripped: bool


def _ring(result: RunResult) -> _Ring:
    time = result.real("time")
    over = np.where(common.branch_r3(result) > _LEVEL, 3.3, 0.0)
    return _Ring(
        above=common.high_time(
            time, np.asarray(over, dtype=np.float64), common.STEP_AT, float(time[-1])
        ),
        tripped=bool(np.min(result.real("gate_out")) < common.HALF_LOGIC),
    )


def _cases() -> list[_Case]:
    """Every ringing run: without the trip to see the ringing, with it to count trips."""
    cases = [
        _Case(leads, henries, farads, terminal, active)
        for leads in _LEADS
        for henries in _INDUCTANCES
        for farads in _CAPACITORS
        for terminal in (False, True)
        for active in (False, True)
    ]
    cases += [
        _Case("heavy", 3e-6, farads, False, True, amps) for amps in _STEPS for farads in _CAPACITORS
    ]
    return cases


@bench(
    "range_logic",
    "supply-leads",
    "Ampere mode behind supply leads: sag of the supply node, ringing and the trip",
    "sections 4.3 (supply node, decision D-63), 4.4 (ampere mode with long leads) and 4.9",
)
def supply_leads(ctx: Context) -> Outcome:
    """The supply node is fed from an external supply through leads with inductance.

    In ampere mode the current of a load step has to come through the leads
    of the supply of the user. First the step of requirement R-07, 1 uA to
    500 mA with 1 uF at the load, behind 0.5 uH and 1 uH of lead: the run
    reads how far the supply node sags while the 1 uF and the damped 4.7 uF
    on it carry the step. Then a step to 1.0 A beside 10 uF to 100 uF behind
    1 uH and 3 uH: leads and load capacitor ring, and the run reads how long
    the current in the 0.1 ohm branch stays above the over-current level,
    with the trip made inactive, and whether the trip acts when it is
    active. That is done for thin and for heavy leads, and again with
    100 uF at the VIN terminals, as the user documentation asks. The last
    runs lower the step to find where the trip begins to act.
    """
    sags = {"0u5": (0.5e-6, 0.13), "1u": (1e-6, 0.05)}
    sag_runs = {
        (lead, kind): ctx.run(f"sag-{lead}-{kind}", _sag_deck(ctx, *sags[lead], delays))
        for lead in sags
        for kind, delays in (("nominal", common.NOMINAL), ("worst", common.WORST))
    }
    cases = _cases()
    # The run that goes against the specification is filed with its deck.
    filed = _Case("heavy", 3e-6, 100e-6, True, False)
    results = {filed.name: ctx.run(filed.name, _ring_deck(ctx, filed))}
    results.update(
        ctx.run_many({case.name: _ring_deck(ctx, case) for case in cases if case != filed})
    )
    rings = {case: _ring(results[case.name]) for case in cases}

    def sag(lead: str, kind: str) -> float:
        node = sag_runs[(lead, kind)].real("supply")
        return float(node[0] - np.min(node))

    limit = "section 4.3: 0.17 V to 0.21 V behind 0.5 uH to 1 uH, simulated; to its last digit"
    figures = [
        Figure(
            "sag_0u5_nominal",
            "Sag of the supply node, 500 mA step, 0.5 uH and 0.13 ohm of lead, nominal delays",
            sag("0u5", "nominal"),
            "V",
            expected=0.17,
            high=0.215,
            source=limit,
        ),
        Figure(
            "sag_0u5_worst",
            "The same with the worst delays",
            sag("0u5", "worst"),
            "V",
            high=0.215,
            source=limit,
        ),
        Figure(
            "sag_1u_nominal",
            "Sag of the supply node, 500 mA step, 1 uH and 0.05 ohm of lead, nominal delays",
            sag("1u", "nominal"),
            "V",
            high=0.215,
            source=limit,
        ),
        Figure(
            "sag_1u_worst",
            "The same with the worst delays",
            sag("1u", "worst"),
            "V",
            expected=0.21,
            high=0.215,
            source=limit,
        ),
        Figure(
            "sag_drop",
            "Drop from the supply node to the terminal in these four runs, largest",
            max(float(np.max(common.drop(run))) for run in sag_runs.values()),
            "V",
            high=0.5,
            source="requirement R-07: the leads do not enter the drop",
        ),
    ]
    full = [case for case in cases if case.amps == 1.0]
    for leads in _LEADS:
        bare = [case for case in full if case.leads == leads and not case.terminal]
        with_cap = [case for case in full if case.leads == leads and case.terminal]
        free = [case for case in bare if not case.active]
        longest = max(free, key=lambda case: rings[case].above)
        heavy = leads == "heavy"
        figures += [
            Figure(
                f"{leads}_longest",
                f"{leads.capitalize()} leads, no capacitor at VIN, trip inactive: "
                "longest time above 1.15 A",
                rings[longest].above,
                "s",
                expected=29e-6 if heavy else None,
                source=_RINGING if heavy else "",
            ),
            Figure(f"{leads}_longest_lead", "Supply lead of that run", longest.henries, "H"),
            Figure(f"{leads}_longest_cap", "Load capacitor of that run", longest.farads, "F"),
            Figure(
                f"{leads}_trips",
                f"{leads.capitalize()} leads, no capacitor at VIN: runs of 8 that trip",
                float(sum(rings[case].tripped for case in bare if case.active)),
                "",
            ),
            Figure(
                f"{leads}_terminal_longest",
                f"{leads.capitalize()} leads, 100 uF at VIN, trip inactive: "
                "longest time above 1.15 A",
                max(rings[case].above for case in with_cap if not case.active),
                "s",
                expected=2.1e-6,
                high=10e-6,
                source="section 4.4: 2.1 us with 100 uF at the VIN terminals; rule F-18: 10 us",
            ),
            Figure(
                f"{leads}_terminal_trips",
                f"{leads.capitalize()} leads, 100 uF at VIN: runs of 8 that trip",
                float(sum(rings[case].tripped for case in with_cap if case.active)),
                "",
                high=0.0,
                source="section 11: no trip on a step to 1.0 A with 100 uF at the VIN terminals",
            ),
        ]
    tripping = [case.amps for case in cases if case.leads == "heavy" and rings[case].tripped]
    tripping = [amps for amps in tripping if amps < 1.0] or [1.0]
    figures.append(
        Figure(
            "smallest_tripping_step",
            "Heavy leads of 3 uH, no capacitor at VIN: smallest step that trips, 0.7 A to 1.0 A",
            min(tripping),
            "A",
            expected=0.7,
            source="section 4.4: the trip can act on load steps above about 0.7 A",
        )
    )

    traces: list[Trace] = []
    for (lead, kind), run in sag_runs.items():
        time = run.real("time")
        shown = (time >= common.STEP_AT - 1e-6) & (time <= common.STEP_AT + 30e-6)
        micro = (time[shown] - common.STEP_AT) * 1e6
        label = f"{'0.5 uH' if lead == '0u5' else '1 uH'}, {kind} delays"
        traces += [
            Trace(micro, run.real("supply")[shown], label, 0),
            Trace(micro, run.real("vout")[shown], label, 1),
        ]
    sag_graph = Graph(
        name="sag",
        title="1 uA to 500 mA with 1 uF at the load, 5 V behind supply leads",
        xlabel="Time after the load step (us)",
        panels=(Panel("Supply node (V)"), Panel("Output terminal (V)")),
        traces=tuple(traces),
    )
    traces = []
    for case, label in (
        (_Case("heavy", 3e-6, 100e-6, False, False), "heavy leads, no capacitor at VIN"),
        (_Case("heavy", 3e-6, 100e-6, True, False), "heavy leads, 100 uF at VIN"),
        (_Case("thin", 3e-6, 100e-6, False, False), "thin leads, no capacitor at VIN"),
        (_Case("thin", 3e-6, 100e-6, True, False), "thin leads, 100 uF at VIN"),
    ):
        run = results[case.name]
        time = run.real("time")
        shown = (time >= common.STEP_AT - 5e-6) & (time <= common.STEP_AT + 190e-6)
        micro = (time[shown] - common.STEP_AT) * 1e6
        traces += [
            Trace(micro, common.branch_r3(run)[shown], label, 0),
            Trace(micro, run.real("supply")[shown], label, 1),
            Trace(micro, run.real("vout")[shown], label, 2),
        ]
    ring_graph = Graph(
        name="ring",
        title="1 uA to 1.0 A with 100 uF at the load behind 3 uH of supply lead, trip inactive",
        xlabel="Time after the load step (us)",
        panels=(
            Panel("Current in the 0.1 ohm branch (A)", marks=((_LEVEL, "over-current 1.15 A"),)),
            Panel("Supply node (V)"),
            Panel("Output terminal (V)"),
        ),
        traces=tuple(traces),
    )
    notes = (
        "Ampere mode is not drawn into this circuit: the fuse, the closed ampere "
        "switch and the copper to the supply node are one resistance of 35 mohm, "
        "and the external supply holds 5 V behind its leads. The 1 uF and the "
        "damped 4.7 uF on the supply node are the parts of the schematic.",
        "Lead resistance for the sag: 0.13 ohm with 0.5 uH and 0.05 ohm with "
        "1 uH, the pairs of the earlier simulations of the design. For the "
        "ringing two kinds of lead: thin, 50 mohm for every microhenry, and "
        "heavy, 10 mohm. The specification names inductances only; its 12 us to "
        "29 us are found again with the heavy leads.",
        "The leads and the capacitors ring together, and the current that "
        "recharges the load capacitor passes the shunt. A capacitor at the VIN "
        "terminals takes a share of that current in proportion to its size "
        "against the load capacitor. With thin leads the ringing is damped and "
        "100 uF at the terminals is enough; with heavy leads and 47 uF or more "
        "at the load it is not: the branch stays above the level for tens of "
        "microseconds and the trip acts.",
        "The time above 1.15 A is read with the qualification time of the trip "
        "set out of reach, so that the ringing can be seen whole; the trip count "
        "comes from the same runs with the 12 us of rule F-18.",
        "What happens to the supply node when the trip opens the output on a "
        "short circuit in ampere mode is not in this bench. The node is then "
        "bounded by the ampere switch acting as a source follower and by the "
        "suppressor of the VIN terminal, which are parts of the path switching "
        "sheet.",
        common.VENDOR_NOTE,
    )
    return Outcome(tuple(figures), (sag_graph, ring_graph), notes)
