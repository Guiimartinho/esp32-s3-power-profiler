"""Hot plug of a discharged capacitor and a short circuit at the output."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches import frontend
from benches.range_logic import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_TYPICAL = common.CLAMP_TYPICAL
_LOW = common.CLAMP_LOW
_HIGH = common.CLAMP_HIGH

_PAIRS = {
    "typical": (_TYPICAL, _TYPICAL),
    "low": (_LOW, _LOW),
    "opposite": (_LOW, _HIGH),
    "high": (_HIGH, _HIGH),
}
"""Thresholds of the two clamp transistors Q10 and Q11."""

_CAPACITOR = 100e-6
"""The capacitor that is plugged in, F (section 4.3)."""

_CAPACITOR_ESR = 0.01
"""Its series resistance, ohm (assumption, as in the earlier simulations)."""

_LEAD_OHMS = 0.03
_LEAD_HENRIES = 50e-9
"""The lead to the capacitor or to the short (assumption, as in the earlier simulations)."""

_CONTACT_SIEMENS = 100.0
"""Conductance of the closed contact: 10 mohm (assumption)."""

_RATING = 21.0
"""Pulsed drain current of a clamp transistor, A (datasheet value of section 4.3)."""

_SHUNT = 0.1
"""Nominal value of the range 3 shunt, ohm."""

_END = 30e-6


@dataclass(frozen=True, slots=True)
class _Case:
    """One run.

    Attributes:
        short: A short circuit in place of the capacitor.
        start: Range before the event.
        pair: Key of the clamp thresholds.
        delays: Delays between the shunt and the gate.
        volts: Output voltage.
        henries: Inductance of the lead.
    """

    short: bool
    start: int = 0
    pair: str = "typical"
    delays: common.Delays = common.WORST
    volts: float = 5.0
    henries: float = _LEAD_HENRIES


def _cases() -> dict[str, _Case]:
    cases: dict[str, _Case] = {}
    for short in (False, True):
        kind = "short" if short else "plug"
        for start in (0, 2):
            for pair in _PAIRS:
                cases[f"{kind}-r{start}-{pair}"] = _Case(short, start, pair)
        cases[f"{kind}-r0-typical-nominal"] = _Case(short, delays=common.NOMINAL)
    cases["short-r0-low-20nh"] = _Case(True, pair="low", henries=20e-9)
    cases["short-r0-opposite-20nh"] = _Case(True, pair="opposite", henries=20e-9)
    cases["short-r0-low-150nh"] = _Case(True, pair="low", henries=150e-9)
    cases["short-r0-low-5v5"] = _Case(True, pair="low", volts=5.5)
    cases["short-r0-opposite-5v5"] = _Case(True, pair="opposite", volts=5.5)
    cases["short-r0-opposite-5v5-20nh"] = _Case(True, pair="opposite", volts=5.5, henries=20e-9)
    return cases


_CASES = _cases()
_KEPT = ("plug-r0-typical", "short-r0-opposite")


def _event(case: _Case) -> str:
    """The lead and the contact that closes on a capacitor or on a short."""
    at = common.STEP_AT
    lines = [
        "* a lead and a contact that closes within 5 ns",
        f"Rlead vout lead {_LEAD_OHMS:g}",
        f"Llead lead plug {case.henries:g}",
        f"Vclose close 0 {common.pwl(((0.0, 0.0), (at, 0.0), (at + 5e-9, 1.0)))}",
        "Rclose close 0 1k",
    ]
    if case.short:
        lines.append(f"Bcontact plug 0 I = v(plug)*(1e-9 + {_CONTACT_SIEMENS:g}*v(close))")
    else:
        lines += [
            f"Bcontact plug dut I = v(plug,dut)*(1e-9 + {_CONTACT_SIEMENS:g}*v(close))",
            f"Cdut dut dut_c {_CAPACITOR:g}",
            f"Resr dut_c 0 {_CAPACITOR_ESR:g}",
            "Rbleed dut 0 10k",
        ]
    return "\n".join(lines) + "\n"


def _deck(ctx: Context, name: str) -> str:
    case = _CASES[name]
    circuit = common.front_end(ctx, case.delays, clamps=_PAIRS[case.pair])
    saved = " ".join(word for word in common.SAVED.split() if word not in ("dut", "iprog"))
    return ctx.deck(
        f"{'Short circuit' if case.short else 'Hot plug of 100 uF'}, {name}",
        circuit,
        frontend.rails(),
        common.source(case.volts),
        common.controller(case.delays),
        _event(case),
        common.rest(circuit, case.start),
        control=[f"save {saved} plug", f"tran 2n {_END:g}"],
        options=common.options(ctx),
        libraries=frontend.SEQUENCER_LIBRARIES,
    )


@dataclass(frozen=True, slots=True)
class _Surge:
    """What one event did.

    Attributes:
        clamp: Largest current in one clamp transistor, A.
        above: Longest time one of them carried more than 5 A, s.
        ladder: Largest ladder voltage, V.
        shunt: Largest current in the 0.1 ohm shunt, A.
        energy: Energy in that shunt over the run, J.
        one_ohm: Largest current in the 1 ohm shunt, A.
        lowest: Lowest voltage at the output terminal, V.
        opened: Time from the event to the output line going low, s.
    """

    clamp: float
    above: float
    ladder: float
    shunt: float
    energy: float
    one_ohm: float
    lowest: float
    opened: float


def _surge(result: RunResult) -> _Surge:
    time = result.real("time")
    start, stop = common.STEP_AT, float(time[-1])
    parts = (result.real("@mq10[id]"), result.real("@mq11[id]"))
    through = result.real("@r110[i]")
    line = result.real("gate_out")
    opened = float("nan")
    if float(np.min(line)) < common.HALF_LOGIC:
        opened = measure.first_crossing(time, line, common.HALF_LOGIC, rising=False) - start
    return _Surge(
        clamp=max(measure.extremes(time, part, start, stop)[1] for part in parts),
        above=max(common.time_above(time, part, 5.0, start, stop) for part in parts),
        ladder=measure.extremes(time, common.ladder(result), start, stop)[1],
        shunt=measure.extremes(time, through, start, stop)[1],
        energy=measure.integral(time, through * through * _SHUNT, start, stop),
        one_ohm=measure.extremes(time, result.real("@r107[i]"), start, stop)[1],
        lowest=measure.extremes(time, result.real("vout"), start, stop)[0],
        opened=opened,
    )


def _graph(name: str, title: str, result: RunResult, span: float) -> Graph:
    time = result.real("time")
    shown = (time >= common.STEP_AT - 0.1 * span) & (time <= common.STEP_AT + span)
    micro = (time[shown] - common.STEP_AT) * 1e6

    def cut(node: str) -> np.ndarray:
        return result.real(node)[shown]

    return Graph(
        name=name,
        title=title,
        xlabel="Time after the contact closes (us)",
        panels=(
            Panel("Voltage (V)"),
            Panel("Current in the ladder clamp (A)", marks=((5.0, "5 A"),)),
            Panel("Current in the shunts (A)"),
            Panel("Controller lines (V)"),
        ),
        traces=(
            Trace(micro, cut("supply"), "supply node", 0),
            Trace(micro, cut("vout_s"), "node after the shunts", 0),
            Trace(micro, cut("vout"), "output terminal", 0),
            Trace(micro, common.ladder(result)[shown], "ladder voltage", 0, "--"),
            Trace(micro, cut("@mq10[id]"), "Q10", 1),
            Trace(micro, cut("@mq11[id]"), "Q11", 1, "--"),
            Trace(micro, cut("@r110[i]"), "0.1 ohm shunt", 2),
            Trace(micro, cut("@r107[i]"), "1 ohm shunt", 2, "--"),
            Trace(micro, cut("cmp_jump"), "CMP_JUMP", 3),
            Trace(micro, cut("gate_r3"), "GATE_R3", 3),
            Trace(micro, cut("cmp_oc"), "CMP_OC", 3, "--"),
            Trace(micro, cut("gate_out"), "GATE_OUT", 3, ":"),
        ),
    )


@bench(
    "range_logic",
    "hot-plug",
    "Hot plug of 100 uF and a short circuit at the output: the surge in the ladder",
    "section 4.3 (ladder clamp, decision D-66), section 4.4 (jump, trip), section 11 (pulses)",
)
def hot_plug(ctx: Context) -> Outcome:
    """The output is on at 5 V and a contact closes on it.

    Behind 30 mohm and 50 nH of lead the contact connects a discharged
    100 uF capacitor, or a short circuit. The ladder is in range 0 or in
    range 2. Its voltage rises until the two clamp transistors carry the
    current; the jump comparator forces range 3, the 0.1 ohm branch takes
    over, and the over-current trip opens the output 12 us later. The run
    reads the current in each clamp transistor, the time it spends above
    5 A, the ladder voltage, and current and energy in the 0.1 ohm shunt.
    It is made with the worst delays and with the two clamp transistors at
    their typical curve, both at the low end of the threshold, both at the
    high end, and one at each end. Further runs change the lead to 20 nH
    and 150 nH and the output voltage to 5.5 V.
    """
    results = {name: ctx.run(name, _deck(ctx, name)) for name in _KEPT}
    results.update(ctx.run_many({name: _deck(ctx, name) for name in _CASES if name not in _KEPT}))
    found = {name: _surge(result) for name, result in results.items()}
    base = [
        name
        for name, case in _CASES.items()
        if case.volts == 5.0 and case.henries == _LEAD_HENRIES and case.delays == common.WORST
    ]
    equal = [name for name in base if _CASES[name].pair != "opposite"]
    opposite = [name for name in base if _CASES[name].pair == "opposite"]
    plugs = [name for name in base if not _CASES[name].short]
    shorts = [name for name in base if _CASES[name].short]

    def most(names: list[str], key: str) -> float:
        return max(float(getattr(found[name], key)) for name in names)

    rating = "section 4.3: pulsed rating 21 A (datasheet value)"
    figures = [
        Figure(
            "clamp_equal",
            "Largest current in a clamp transistor, both at the same threshold",
            most(equal, "clamp"),
            "A",
            expected=8.8,
            high=_RATING,
            source=f"section 4.3: 8.8 A in each part, simulated; {rating}",
        ),
        Figure(
            "clamp_opposite",
            "Largest current in one clamp transistor, thresholds at opposite ends",
            most(opposite, "clamp"),
            "A",
            expected=14.2,
            high=_RATING,
            source=f"section 4.3: 14.2 A in one part, simulated; {rating}",
        ),
        Figure(
            "above_plug",
            "Hot plug: longest time a clamp transistor carries more than 5 A",
            most(plugs, "above"),
            "s",
            expected=0.54e-6,
            high=0.54e-6,
            source="section 4.3: above 5 A for at most 0.54 us, simulated",
        ),
        Figure(
            "above_short",
            "Short circuit: longest time a clamp transistor carries more than 5 A",
            most(shorts, "above"),
            "s",
            expected=0.54e-6,
            high=0.54e-6,
            source="section 4.3: above 5 A for at most 0.54 us, simulated",
        ),
        Figure(
            "above_short_typical",
            "The same with both clamp transistors at their typical curve",
            most([name for name in shorts if _CASES[name].pair == "typical"], "above"),
            "s",
            expected=0.54e-6,
            high=0.54e-6,
            source="section 4.3: above 5 A for at most 0.54 us, simulated",
        ),
        Figure(
            "ladder",
            "Largest ladder voltage",
            most(base, "ladder"),
            "V",
            expected=3.9,
            high=3.9,
            source="section 4.3: ladder at most 3.9 V, simulated",
        ),
        Figure(
            "shunt_peak",
            "Largest current in the 0.1 ohm shunt",
            most(base, "shunt"),
            "A",
            expected=27.0,
            source="section 4.3: up to 27 A for microseconds; accepted on the energy",
        ),
        Figure(
            "shunt_energy",
            "Largest energy in the 0.1 ohm shunt in one event",
            most(base, "energy"),
            "J",
            expected=1e-3,
            high=0.2,
            source="section 4.3: about 1 mJ against 200 mJ, calculated",
        ),
        Figure(
            "one_ohm_peak",
            "Largest current in the 1 ohm shunt, events in range 2",
            most([name for name in base if _CASES[name].start == 2], "one_ohm"),
            "A",
        ),
        Figure(
            "opened",
            "Contact closed to the line of the output switch low, longest",
            float(np.nanmax([found[name].opened for name in base])),
            "s",
            high=20e-6 + 1e-6,
            source="rule F-18: at most 20 us of qualification; 1 us for the jump",
        ),
        Figure(
            "not_opened",
            "Events after which the output stayed on, of 16",
            float(sum(np.isnan(found[name].opened) for name in base)),
            "",
        ),
        Figure(
            "lowest_output",
            "Lowest voltage at the output terminal",
            min(found[name].lowest for name in base),
            "V",
            low=-2.5,
            source="section 11: VOUT above -2.5 V in a short circuit",
        ),
    ]
    for name, label in (
        ("short-r0-low-20nh", "Short, 20 nH of lead, both low: current in a clamp transistor"),
        ("short-r0-opposite-20nh", "Short, 20 nH of lead, opposite ends: current in one"),
        ("short-r0-low-150nh", "Short, 150 nH of lead, both low: current in a clamp transistor"),
        ("short-r0-low-5v5", "Short at 5.5 V, both low: current in a clamp transistor"),
        ("short-r0-opposite-5v5", "Short at 5.5 V, opposite ends: current in one"),
        ("short-r0-opposite-5v5-20nh", "Short at 5.5 V, 20 nH, opposite ends: current in one"),
    ):
        figures.append(
            Figure(
                "clamp_" + name.replace("-", "_"),
                label,
                found[name].clamp,
                "A",
                high=_RATING,
                source=rating,
            )
        )
    figures += [
        Figure(
            "delay_effect",
            "Hot plug, typical clamp: current with the nominal delays",
            found["plug-r0-typical-nominal"].clamp,
            "A",
        ),
        Figure(
            "delay_effect_worst",
            "Hot plug, typical clamp: current with the worst delays",
            found["plug-r0-typical"].clamp,
            "A",
        ),
    ]
    first = _graph(
        "plug",
        "Hot plug of 100 uF in range 0 at 5 V, typical clamp, worst delays: the first 2 us",
        results["plug-r0-typical"],
        2e-6,
    )
    whole = _graph(
        "short",
        "Short circuit in range 0 at 5 V, clamp thresholds at opposite ends, to the trip",
        results["short-r0-opposite"],
        22e-6,
    )
    notes = (
        "The surge is set by what stands around the instrument, and the "
        "specification does not say what its figures assumed. Here: a source "
        "that holds its voltage behind 20 mohm, 30 mohm and 50 nH of lead, a "
        "contact of 10 mohm that closes within 5 ns, and 10 mohm in the "
        "capacitor. The earlier simulations of the design had the same lead and "
        "5.6 V; the runs at 5.5 V come close to their 8.8 A and 14.2 A.",
        "The lead inductance sets how far the current rises before range 3 "
        "conducts: 20 nH in place of 50 nH adds about half to the clamp current.",
        "A source that holds 5 V through a short circuit is an external supply "
        "in ampere mode with short leads. The source meter cannot do that: its "
        "regulator limits its current, and the 22 uF at its output hold the "
        "charge of about 4 us at 27 A. For it the figures of the first "
        "microsecond hold and the ones up to the trip are an upper bound.",
        "In the short circuit the 0.1 ohm branch carries about 27 A until the "
        "trip, and the ladder stands at about 2.8 V. A clamp transistor at the "
        "low end of its threshold conducts at that voltage: it carries 5 A to "
        "8 A for the whole 15 us, not for the 0.54 us of the specification. The "
        "peak stays below the pulsed rating; the energy in that transistor is "
        "about 0.3 mJ.",
        "The clamp model is fitted to the typical output curve of the datasheet "
        "up to 10 A; the low and high variants move its threshold by the spread "
        "the datasheet states at 25 uA, which is an assumption about amperes. "
        "The transistors heat in such a pulse and the model does not.",
        "The amplifier sees up to 3.8 V between its inputs in these events. Its "
        "model has no input protection and no overload recovery; the datasheet "
        "limits of its inputs are not checked here.",
        common.VENDOR_NOTE,
    )
    return Outcome(tuple(figures), (first, whole), notes)
