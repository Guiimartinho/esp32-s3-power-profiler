"""DUT power on into a large capacitor: the in-rush against the armed trip."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches import frontend
from benches.range_logic import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_REQUEST_AT = 0.2e-3
"""Instant of the request to close the output switch, s."""

_END = 32e-3

_CAPACITOR_ESR = 0.02
"""Series resistance of the large capacitor, ohm (assumption, electrolytic)."""

_TRIP_LEVEL = 1.15
"""Over-current level in range 3, A."""

_CASES = {
    "1000uf": (1000e-6, 5.0),
    "1800uf": (1800e-6, 5.0),
    "2200uf": (2200e-6, 5.0),
    "2640uf": (2640e-6, 5.0),
    "3300uf": (3300e-6, 5.0),
    "2200uf-0v8": (2200e-6, 0.8),
    "2200uf-3v3": (2200e-6, 3.3),
}
"""Capacitor at the output and output voltage of each run."""


def _deck(ctx: Context, name: str) -> str:
    farads, volts = _CASES[name]
    circuit = common.front_end(ctx)
    load = "\n".join(
        [
            "* device under test: a discharged capacitor with its series resistance",
            "* and a leak that keeps it at 0 V while the output is off",
            f"Rlead vout dut {common.LEAD_OHMS:g}",
            f"Cdut dut dut_c {farads:g}",
            f"Resr dut_c 0 {_CAPACITOR_ESR:g}",
            "Rleak dut 0 100k",
        ]
    )
    request = common.pwl(
        ((0.0, 0.0), (_REQUEST_AT, 0.0), (_REQUEST_AT + 100e-9, frontend.LOGIC_VOLTS))
    )
    saved = " ".join(word for word in common.SAVED.split() if word != "iprog")
    return ctx.deck(
        f"DUT power on into {farads * 1e6:g} uF at {volts:g} V, range 3 selected",
        circuit,
        frontend.rails(),
        common.source(volts),
        common.controller(output_on=request),
        load + "\n",
        common.rest(circuit, 3, output_on=False),
        control=[f"save {saved} drv_out g_out_rc", f"tran 2u {_END:g}"],
        options=common.options(ctx),
        libraries=frontend.SEQUENCER_LIBRARIES,
    )


@dataclass(frozen=True, slots=True)
class _Start:
    """What one start shows.

    Attributes:
        peak: Largest current in the 0.1 ohm shunt, A.
        starts: Time from the request to 0.1 V at the output, s.
        most: Time from the request to 90 % of the output voltage, s; not a
            number when the output never gets there.
        slope: Slope of the output between 20 % and 40 % of its voltage, V/s.
        tripped: Whether the trip opened the output again.
    """

    peak: float
    starts: float
    most: float
    slope: float
    tripped: bool


def _start(result: RunResult, volts: float) -> _Start:
    time = result.real("time")
    output = result.real("vout")
    line = result.real("gate_out")
    after = _REQUEST_AT + 1e-6
    tripped = bool(np.min(line[time > after]) < common.HALF_LOGIC)

    def reaches(level: float) -> float:
        if float(np.max(output)) < level:
            return float("nan")
        return measure.first_crossing(time, output, level, rising=True, after=_REQUEST_AT)

    low, high = reaches(0.2 * volts), reaches(0.4 * volts)
    return _Start(
        peak=float(np.max(result.real("@r110[i]"))),
        starts=reaches(0.1) - _REQUEST_AT,
        most=reaches(0.9 * volts) - _REQUEST_AT,
        slope=0.2 * volts / (high - low),
        tripped=tripped,
    )


@bench(
    "range_logic",
    "power-on",
    "DUT power on into 1000 uF to 3300 uF: the in-rush against the armed trip",
    "sections 4.2 (output switch) and 4.4 (trip without blanking), rules F-19, F-20 and F-24",
)
def power_on(ctx: Context) -> Outcome:
    """Range 3 is selected, the trip is armed and the output switch is asked to close.

    The output switch closes as a source follower behind 2.2 Mohm and 10 nF,
    so the output voltage rises slowly and a discharged capacitor at the
    output draws a current in proportion to its size. The trip has no
    blanking at a start: the current has to stay below the over-current
    level by itself. The run takes 1000 uF, 1800 uF, 2200 uF, 2200 uF plus
    20 %, and 3300 uF at 5 V, and 2200 uF at 3.3 V and 0.8 V, and reads the
    largest current in the 0.1 ohm shunt, when the output begins to rise
    and how fast, and whether the trip acts.
    """
    results = {"2200uf": ctx.run("2200uf", _deck(ctx, "2200uf"))}
    results.update(ctx.run_many({name: _deck(ctx, name) for name in _CASES if name not in results}))
    found = {name: _start(result, _CASES[name][1]) for name, result in results.items()}
    test = "section 11: no trip, peak below 1.0 A up to 1800 uF"
    figures = [
        Figure(
            "peak_1000uf",
            "1000 uF at 5 V: largest current in the shunt",
            found["1000uf"].peak,
            "A",
            expected=0.39,
            high=1.0,
            source=f"section 4.2: 0.39 A into 1000 uF, simulated; {test}",
        ),
        Figure(
            "peak_1800uf",
            "1800 uF at 5 V: largest current in the shunt",
            found["1800uf"].peak,
            "A",
            high=1.0,
            source=test,
        ),
        Figure(
            "peak_2200uf",
            "2200 uF at 5 V: largest current in the shunt",
            found["2200uf"].peak,
            "A",
            expected=0.85,
            high=_TRIP_LEVEL,
            source="section 4.2: 0.85 A into 2200 uF, simulated; section 4.4: below the trip level",
        ),
        Figure(
            "peak_2640uf",
            "2200 uF plus 20 % at 5 V: largest current in the shunt",
            found["2640uf"].peak,
            "A",
        ),
        Figure(
            "peak_2200uf_3v3",
            "2200 uF at 3.3 V: largest current in the shunt",
            found["2200uf-3v3"].peak,
            "A",
            high=_TRIP_LEVEL,
            source="section 4.4: below the trip level up to about 2200 uF",
        ),
        Figure(
            "peak_2200uf_0v8",
            "2200 uF at 0.8 V: largest current in the shunt",
            found["2200uf-0v8"].peak,
            "A",
            high=_TRIP_LEVEL,
            source="section 4.4: below the trip level up to about 2200 uF",
        ),
        Figure(
            "trips_to_2200uf",
            "Starts into 2200 uF or less in which the trip acts, of 5",
            float(
                sum(
                    found[name].tripped
                    for name in ("1000uf", "1800uf", "2200uf", "2200uf-0v8", "2200uf-3v3")
                )
            ),
            "",
            high=0.0,
            source="section 4.4: no trip up to about 2200 uF",
        ),
        Figure(
            "trip_2640uf",
            "2200 uF plus 20 %: the trip acts (1 when so)",
            float(found["2640uf"].tripped),
            "",
        ),
        Figure(
            "trip_3300uf",
            "3300 uF: the trip acts (1 when so)",
            float(found["3300uf"].tripped),
            "",
            expected=1.0,
            source="rule F-19: a start trips with more than about 2200 uF",
        ),
        Figure(
            "starts",
            "2200 uF at 5 V: request to 0.1 V at the output",
            found["2200uf"].starts,
            "s",
            expected=6.5e-3,
            source="section 4.2: starts to rise 6 ms to 7 ms after the request, simulated",
        ),
        Figure(
            "slope",
            "2200 uF at 5 V: slope of the output between 1 V and 2 V",
            found["2200uf"].slope,
            "V/s",
            expected=440.0,
            source="section 4.2: 0.44 V/ms, simulated",
        ),
        Figure(
            "most",
            "2200 uF at 5 V: request to 90 % of the output voltage",
            found["2200uf"].most,
            "s",
            expected=20e-3,
            source="section 4.2: about 20 ms at 5.0 V, simulated",
        ),
    ]
    traces: list[Trace] = []
    for name in ("1000uf", "2200uf", "2640uf", "3300uf"):
        result = results[name]
        milli = (result.real("time") - _REQUEST_AT) * 1e3
        label = f"{_CASES[name][0] * 1e6:g} uF"
        traces += [
            Trace(milli, result.real("vout"), label, 0),
            Trace(milli, result.real("@r110[i]"), label, 1),
            Trace(milli, result.real("g_out"), label, 2),
        ]
    graph = Graph(
        name="start",
        title="DUT power on at 5 V in range 3 into a discharged capacitor",
        xlabel="Time after the request to close the output switch (ms)",
        panels=(
            Panel("Output terminal (V)"),
            Panel(
                "Current in the 0.1 ohm shunt (A)",
                marks=((_TRIP_LEVEL, "over-current 1.15 A"), (1.0, "1.0 A")),
            ),
            Panel("Gate of the output switch (V)"),
        ),
        traces=tuple(traces),
    )
    notes = (
        "The capacitor has 20 mohm in series and starts at 0 V; a leak of "
        "100 kohm stands for the rest of the device. A device that draws "
        "current while its supply rises adds to the in-rush.",
        "The slope of the output, and with it the current, follows the gate "
        "network and the capacitances of the two switch transistors; the "
        "instant at which the output begins to rise follows their threshold. "
        "The transistor model is a typical part.",
        "The trip is the model of rule F-18 and is armed from the start of the "
        "run; that range 3 is selected first is the order of rule F-24, set "
        "here through the state at rest.",
        "The source holds its voltage behind 20 mohm: what the regulator does "
        "with 0.9 A of in-rush is not in this run.",
        common.VENDOR_NOTE,
    )
    return Outcome(tuple(figures), (graph,), notes)
