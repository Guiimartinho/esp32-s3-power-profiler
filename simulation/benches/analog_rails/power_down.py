"""The order of the rails at power-off and when the supervisor trips."""

from __future__ import annotations

import numpy as np

from benches.analog_rails import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.engine import RunResult

_DELAY = 0.02
"""Release delay of the supervisor in these runs: shortened, to reach the on state sooner."""

_EVENT = 0.6
"""Instant of the event: +12V_A is then within 50 mV of its final value."""

_DIP_VOLTS = 3.4
"""Level of the source during the dip that trips the supervisor."""

_DIP_TIME = 3e-3
"""Length of that dip."""

_AFTER = 0.09
"""Time simulated after the event."""

_STEP = 50e-6
"""Longest time step (see the power-up bench)."""

_SAVED = "p5v p13v5 p12v_a m4v_a p3v3_a p3v3_c vref ok5v pwr_good gp28 set12 src @dd7[id] @dd8[id]"
"""The vectors a run keeps."""

_CASES = {
    "off": f"{_EVENT:g} 5 {_EVENT + 1e-5:g} 0",
    "trip": (
        f"{_EVENT:g} 5 {_EVENT + 1e-5:g} {_DIP_VOLTS:g} "
        f"{_EVENT + _DIP_TIME:g} {_DIP_VOLTS:g} {_EVENT + _DIP_TIME + 1e-5:g} 5"
    ),
}
"""The source of the 5 V rail after the start: removed, or lowered for a moment."""


def _deck(ctx: Context, case: str) -> str:
    circuit = common.whole_rails(ctx, {"U6": common.supervisor(_DELAY)})
    return ctx.deck(
        f"Rails switched off: case {case}",
        circuit,
        common.source_5v(events=_CASES[case]),
        common.loads(),
        control=[f"save {_SAVED}", f"tran 20u {_EVENT + _AFTER:g} 0 {_STEP:g}"],
        options=("method=gear", "reltol=1e-4"),
    )


def _figures(case: str, label: str, run: RunResult) -> tuple[list[Figure], float]:
    """The figures of one case and the instant at which the supervisor fell."""
    time = run.real("time")

    def wave(name: str) -> common.Real:
        return run.real(name)

    fell = common.crossing_after(time, wave("ok5v"), 2.5, False, _EVENT)

    def after(name: str, level: float) -> float:
        return common.crossing_after(time, wave(name), level, False, fell - 1e-3) - fell

    late = time >= fell
    below_3v3a = after("p3v3_a", 1.0)
    below_12v = after("p12v_a", 3.6)
    figures = [
        Figure(
            f"{case}_trip",
            f"{label}: the supervisor falls after the event",
            fell - _EVENT,
            "s",
            source="the rail falls through 3.91 V under its loads",
        ),
        Figure(
            f"{case}_3v3c",
            f"{label}: 3V3_C below 3.0 V after the supervisor fell",
            after("p3v3_c", 3.0),
            "s",
            expected=0.02e-3,
            high=0.03e-3,
            source="section 3: 0.02 ms (taken as at most 0.03 ms)",
        ),
        Figure(
            f"{case}_good_2v",
            f"{label}: PWR_GOOD below 2.0 V at the controller pin after the supervisor fell",
            after("gp28", 2.0),
            "s",
            low=0.0,
            high=0.07e-3,
            source="rule F-7: 0.05 ms to 0.07 ms after the rails begin to fall, not before them",
        ),
        Figure(
            f"{case}_good_0v8",
            f"{label}: PWR_GOOD below 0.8 V at the controller pin after the supervisor fell",
            after("gp28", 0.8),
            "s",
            expected=0.3e-3,
            high=0.4e-3,
            source="section 3: 0.3 ms (taken as at most 0.4 ms)",
        ),
        Figure(
            f"{case}_3v3a",
            f"{label}: 3V3_A below 1.0 V after the supervisor fell",
            below_3v3a,
            "s",
            low=4e-3,
            high=6e-3,
            source="section 3: 4 ms to 6 ms",
        ),
        near(
            f"{case}_12v",
            f"{label}: +12V_A below 3.6 V after the supervisor fell",
            below_12v,
            "s",
            14e-3,
            0.3,
            "section 3: about 14 ms",
        ),
        near(
            f"{case}_window",
            f"{label}: time with +12V_A above 3.6 V and 3V3_A below 1.0 V",
            below_12v - below_3v3a,
            "s",
            10e-3,
            0.4,
            "section 3: about 10 ms",
        ),
        Figure(
            f"{case}_vref_above",
            f"{label}: VREF above 3V3_A at the most",
            float(np.max((wave("vref") - wave("p3v3_a"))[late])),
            "V",
            high=0.6,
            source="section 4.6 and D-53: at most a diode drop; the monitor converter is "
            "rated for its supply plus 0.6 V (datasheet), the lowest rating on the line",
        ),
        Figure(
            f"{case}_d7_amps",
            f"{label}: largest current through D7",
            float(np.max(run.real("@dd7[id]")[late])),
            "A",
            high=0.5,
            source="datasheet of the diode: 0.5 A average",
        ),
        Figure(
            f"{case}_m4_high",
            f"{label}: -4V_A at its highest while the rails fall",
            float(np.max(wave("m4v_a")[late])),
            "V",
            high=0.24,
            source="section 3 and D-52: below +0.24 V",
        ),
        Figure(
            f"{case}_12v_low",
            f"{label}: +12V_A at its lowest while the rails fall",
            float(np.min(wave("p12v_a")[late])),
            "V",
            low=-0.23,
            source="section 3 and D-52: above -0.23 V",
        ),
    ]
    return figures, fell


def _rails_graph(case: str, label: str, run: RunResult, fell: float) -> Graph:
    """Every rail from 2 ms before the supervisor fell to 30 ms after."""
    time = run.real("time")
    shown = (time >= fell - 2e-3) & (time <= fell + 30e-3)
    milli = (time[shown] - fell) * 1e3
    names = (
        ("p5v", "5 V rail", 0),
        ("p13v5", "+13V5", 0),
        ("p12v_a", "+12V_A", 0),
        ("m4v_a", "-4V_A", 0),
        ("p3v3_a", "3V3_A", 1),
        ("p3v3_c", "3V3_C", 1),
        ("vref", "VREF", 1),
        ("ok5v", "5V_OK", 2),
        ("gp28", "PWR_GOOD at the pin", 2),
    )
    return Graph(
        name=case,
        title=f"{label}: every rail on one time axis",
        xlabel="Time after the supervisor fell (ms)",
        panels=(
            Panel("Rails of the 12 V parts (V)", marks=((3.6, "3.6 V"),)),
            Panel("3.3 V rails and reference (V)", marks=((1.0, "1.0 V"),)),
            Panel("Supervisor and flag (V)", marks=((2.0, "2.0 V"), (0.8, "0.8 V"))),
        ),
        traces=tuple(Trace(milli, run.real(key)[shown], text, panel) for key, text, panel in names),
    )


@bench(
    "analog_rails",
    "power-down",
    "Power-off and supervisor trip: the order in which the rails fall",
    "section 3 (power-off), section 4.6 (D-53), section 4.11, rule F-7, decisions D-48 and D-52",
)
def power_down(ctx: Context) -> Outcome:
    """The rails run, then the 5 V source is removed, or lowered for 3 ms.

    The circuit and the loads are those of the power-up bench. The supervisor
    has a release delay of 20 ms here, so that the rails are up and +12V_A
    has settled when the event comes at 0.6 s. In the first run the source
    disappears and the 5 V rail falls under its loads until the supervisor
    trips. In the second the source falls to 3.4 V for 3 ms and returns: the
    supervisor trips, the rails fall, and the carrier starts again.
    """
    figures: list[Figure] = []
    graphs: list[Graph] = []
    runs = {case: ctx.run(case, _deck(ctx, case)) for case in _CASES}
    labels = {"off": "Source removed", "trip": "Dip to 3.4 V"}
    for case, run in runs.items():
        found, fell = _figures(case, labels[case], run)
        figures += found
        graphs.append(_rails_graph(case, labels[case], run, fell))
    trip = runs["trip"]
    time = trip.real("time")
    fell = common.crossing_after(time, trip.real("ok5v"), 2.5, False, _EVENT)
    back = common.crossing_after(time, trip.real("ok5v"), 2.5, True, fell)
    good = common.crossing_after(time, trip.real("gp28"), 2.0, True, back)
    figures.append(
        near(
            "trip_good_again",
            "Dip to 3.4 V: PWR_GOOD returns after the supervisor has released again",
            good - back,
            "s",
            24e-3,
            0.3,
            "section 3, step 8: about 24 ms after 5V_OK, also after a trip",
        )
    )
    first = (time >= fell - 1e-4) & (time <= fell + 1e-3)
    graphs.append(
        Graph(
            name="edge",
            title="Dip to 3.4 V: the first millisecond after the supervisor fell",
            xlabel="Time after the supervisor fell (ms)",
            panels=(Panel("Voltage (V)", marks=((2.0, "2.0 V"), (0.8, "0.8 V"))),),
            traces=(
                Trace((time[first] - fell) * 1e3, trip.real("ok5v")[first], "5V_OK", 0),
                Trace((time[first] - fell) * 1e3, trip.real("p3v3_c")[first], "3V3_C", 0),
                Trace((time[first] - fell) * 1e3, trip.real("p3v3_a")[first], "3V3_A", 0),
                Trace(
                    (time[first] - fell) * 1e3, trip.real("gp28")[first], "PWR_GOOD at the pin", 0
                ),
            ),
        )
    )
    final = measure.mean(time, trip.real("p12v_a"), _EVENT - 0.01, _EVENT)
    figures.append(
        Figure(
            "start_level",
            "+12V_A when the event comes",
            final,
            "V",
            low=11.9,
            high=12.1,
            source="the rail has settled: within 0.1 V of 12 V (limit of this bench)",
        )
    )
    notes = (
        "Source, loads and models are those of the power-up bench. The times of the two "
        "3.3 V rails and of PWR_GOOD follow from the discharge of 230 ohm of the regulators "
        "and from the loads assumed here: 0.5 mA and the LED on 3V3_C, 10 mA on 3V3_A. The "
        "flag has no edge of its own: its thresholds and its pull-up fall with 3V3_C, so "
        "it falls as 0.82 times that rail.",
        "3V3_C and the flag fall about half as fast as the specification says. The rail "
        "carries 2.4 uF in the netlist (C16 and C92 of 1 uF, four capacitors of 0.1 uF) "
        "and is emptied by the 230 ohm of its regulator and about 2 mA of load: 2.4 uF "
        "times 0.3 V over 15.6 mA is the 46 us of the figure. The 0.02 ms of the "
        "specification fit a rail of 1 uF, the capacitor at the regulator alone. The "
        "flag still does not lead the rails.",
        "+12V_A carries 10 uF at the regulator and 4.8 uF at the supply pins, and the "
        "loads assumed here take 6.6 mA from it; that is the 20 ms of the figure. The "
        "capacitors of 1 uF have no bias curve in the model and stay at their value; "
        "at 12 V they hold less, so the rail of the board falls somewhat faster.",
        "The clamp diodes are the typical variant of the model (0.335 V at 0.1 A, an "
        "assumption); the bench of the clamps has the datasheet maximum.",
        "The +12V_A regulator has no discharge in shutdown in its model, and its SET "
        "capacitor empties into the output through the clamp of the part: both are "
        "readings of the datasheet, not statements of it.",
    )
    return Outcome(tuple(figures), tuple(graphs), notes)
