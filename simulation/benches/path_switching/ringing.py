"""Ampere mode with long supply leads: a load step rings against the capacitor at the load."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.path_switching import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench

_EVENT = 5e-6
"""Instant of the load step."""

_END = 405e-6

_VIN = 5.0

_STEP_EDGE = 100e-9
"""Edge of the load step."""

_TRIP_AMPS = 1.15
"""Over-current level in range 3, A (section 4.4)."""

_TRIP_AMPS_LOW = 1.114
"""Lowest over-current level with the tolerances, A (section 4.4)."""

_QUALIFY_LEAST = 10e-6
"""Shortest qualification time of the trip that a build may have (rule F-18)."""

_SHUNT_OHMS = 0.1


@dataclass(frozen=True, slots=True)
class _Case:
    """One run: a load step to 1 A at a device under test with a capacitor.

    Attributes:
        henries: Inductance of the supply leads.
        farads: Capacitor at the device under test.
        terminal: A capacitor of 100 uF stands across the VIN terminals.
    """

    henries: float
    farads: float
    terminal: bool = False

    @property
    def tag(self) -> str:
        """Short name of the run."""
        text = f"{self.henries * 1e6:g}uh_{self.farads * 1e6:g}uf"
        return (text + ("_terminal" if self.terminal else "")).replace(".", "p")

    @property
    def text(self) -> str:
        """The case as the labels name it."""
        extra = ", 100 uF at the VIN terminals" if self.terminal else ""
        return f"{self.henries * 1e6:g} uH of leads, {self.farads * 1e6:g} uF at the load{extra}"


_CASES = (
    _Case(3e-6, 100e-6),
    _Case(1e-6, 10e-6),
    _Case(1e-6, 100e-6),
    _Case(2e-6, 47e-6),
    _Case(3e-6, 10e-6),
    _Case(3e-6, 100e-6, terminal=True),
    _Case(1e-6, 10e-6, terminal=True),
    _Case(1e-6, 100e-6, terminal=True),
    _Case(3e-6, 10e-6, terminal=True),
)
"""The first case is the one whose deck is kept."""


def _deck(ctx: Context, case: _Case) -> str:
    """Ampere mode with the output closed; the load beside a capacitor steps to 1 A."""
    stimulus = (
        common.supply(_VIN, henries=case.henries)
        + common.no_regulator()
        + common.requests(ampere=((0.0, True),))
        + "* device under test at the output terminal: a capacitor behind 20 mohm with\n"
        "* a current sink beside it, on a lead of 50 nH and 5 mohm\n"
        "Ldut vout dut_a 50n\n"
        "Rlead_dut dut_a dut 5m\n"
        "Resr dut dutc 20m\n"
        f"Cdut dutc 0 {case.farads:g}\n"
        f"Iload dut 0 PWL(0 10m {_EVENT:g} 10m {_EVENT + _STEP_EDGE:g} 1)\n"
    )
    if case.terminal:
        stimulus += (
            "* the capacitor that the user documentation asks for across the VIN\n"
            "* terminals: 100 uF behind 50 mohm\n"
            "Rterm vin_raw vin_c 50m\n"
            "Cterm vin_c 0 100u\n"
        )
    control = [
        "save supply vin_p vout_s vout dut sense_r3 vlead#branch",
        f"tran 20n {_END:g} 0 100n",
    ]
    return common.deck(
        ctx,
        f"Load step to 1 A in ampere mode: {case.text}",
        common.circuit(ctx, output=True),
        common.rails(),
        common.range_lines(3, output=True),
        stimulus,
        control=control,
    )


def _longest_above(time: common.Real, values: common.Real, level: float) -> float:
    """The longest time for which a waveform stays above a level without interruption."""
    ups = measure.crossings(time, values, level, rising=True)
    downs = measure.crossings(time, values, level, rising=False)
    longest = 0.0
    for start in ups:
        later = downs[downs > start]
        stop = float(later[0]) if later.size else float(time[-1])
        longest = max(longest, stop - float(start))
    return longest


@bench(
    "path_switching",
    "ring",
    "Ampere mode: a load step to 1 A rings on the supply leads against the capacitor at the load",
    "sections 4.4 and 4.9 (ampere mode with long supply leads; 100 uF at the VIN terminals)",
)
def ring(ctx: Context) -> Outcome:
    """Ampere mode runs on 5 V behind supply leads and the load steps from 10 mA to 1 A.

    The load has a capacitor beside it, so the step is first served by that
    capacitor and the current in the shunt then rings up on the supply leads
    and passes the load current. The run measures for how long the current
    in the 0.1 ohm shunt stays above the over-current level without
    interruption: the trip acts when that lasts 12 us. It is repeated with
    100 uF across the VIN terminals, which the user documentation asks for
    with long leads. Range 3 is held from the start, so this is the part of
    the event that the leads cause by themselves: the recharge of the
    capacitor after a range change, which the figures of the specification
    include, is not in it.
    """
    runs = ctx.run_many({case.tag: _deck(ctx, case) for case in _CASES[1:]})
    runs[_CASES[0].tag] = ctx.run(_CASES[0].tag, _deck(ctx, _CASES[0]))
    figures: list[Figure] = []
    traces: list[Trace] = []
    for case in _CASES:
        run = runs[case.tag]
        time = run.real("time")
        shunt = (run.real("sense_r3") - run.real("vout_s")) / _SHUNT_OHMS
        held = _longest_above(time, shunt, _TRIP_AMPS)
        if case.terminal:
            figures.append(
                Figure(
                    f"held_{case.tag}",
                    f"Longest time above 1.15 A in the shunt: {case.text}",
                    held,
                    "s",
                    high=_QUALIFY_LEAST,
                    source="rule F-18: the trip never acts before 10 us (section 4.4 states "
                    "2.1 us at the most for the whole event, with the range change)",
                )
            )
        else:
            figures.append(
                Figure(
                    f"held_{case.tag}",
                    f"Longest time above 1.15 A in the shunt: {case.text}",
                    held,
                    "s",
                    source="for comparison: the trip acts after 12 us; section 4.4 states "
                    "12 us to 29 us for the whole event, with the range change",
                )
            )
        figures += [
            Figure(
                f"held_low_{case.tag}",
                f"Longest time above the lowest level of 1.114 A: {case.text}",
                _longest_above(time, shunt, _TRIP_AMPS_LOW),
                "s",
                source="",
            ),
            Figure(
                f"peak_{case.tag}",
                f"Largest current in the shunt: {case.text}",
                float(np.max(shunt)),
                "A",
                source="",
            ),
        ]
        micro = (time - _EVENT) * 1e6
        shown = (micro >= -5.0) & (micro <= 200.0)
        traces.append(Trace(micro[shown], shunt[shown], case.text, 1 if case.terminal else 0))
    graph = Graph(
        name="shunt",
        title="Load step to 1 A in ampere mode on 5 V: current in the 0.1 ohm shunt",
        xlabel="Time after the step (us)",
        panels=(
            Panel("Without a capacitor at VIN (A)", marks=((_TRIP_AMPS, "trip level 1.15 A"),)),
            Panel("With 100 uF at VIN (A)", marks=((_TRIP_AMPS, "trip level 1.15 A"),)),
        ),
        traces=tuple(traces),
    )
    notes = (
        "The load is a current sink that steps within 100 ns beside its capacitor, "
        "which has 20 mohm in series; the supply is a voltage source behind its "
        "leads, 40 mohm per uH. These resistances set the damping and are "
        "assumptions. The capacitor across the VIN terminals has 50 mohm in series "
        "(assumption).",
        "The trip itself is not in the circuit: the figure is the time the "
        "over-current comparator would see, without the delay of the amplifier "
        "chain.",
        "The range is held at range 3. In the instrument such a step starts in a "
        "lower range: the capacitor at the load sags until the jump comparator has "
        "selected range 3, and its recharge then adds to the current in the shunt. "
        "The 12 us to 29 us and the 2.1 us of the specification are figures of "
        "that whole event, which needs the range logic in the loop and belongs to "
        "its block. With the range held, the leads alone keep the current above "
        "the level for 7 us to 14 us with 10 uF at the load and not at all with "
        "47 uF or more.",
        "The output pair is the part of the schematic with the model of its block.",
    )
    return Outcome(tuple(figures), (graph,), notes)
