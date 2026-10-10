"""The order of the rails at power-up."""

from __future__ import annotations

import numpy as np

from benches.analog_rails import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.engine import RunResult

_DELAYS = {"min": 0.18, "typ": 0.30, "max": 0.42}
"""Release delay of the supervisor: the limits and the typical value of its datasheet."""

_AFTER_RELEASE = 0.09
"""Time simulated after the release in the two runs at the limits of the delay."""

_SETTLE = 1.25
"""Time simulated after the release in the typical run, for the last volt of +12V_A."""

_STEP = 50e-6
"""Longest time step. With a longer one the solver steps over the release of
the supervisor in one go, and the attempt that fails leaves it in a state from
which it does not recover."""

_SAVED = (
    "p5v p13v5 p12v_a m4v_a p3v3_a p3v3_c vref ok5v pwr_good gp28 set12 pgfb "
    "ldo_in cpout ref_in ref_nr src i(Vsrc)"
)
"""The vectors a run keeps."""


def _deck(ctx: Context, delay: float, stop: float) -> str:
    circuit = common.whole_rails(ctx, {"U6": common.supervisor(delay)})
    return ctx.deck(
        f"Power-up of the rails, supervisor delay {delay:g} s",
        circuit,
        common.source_5v(),
        common.loads(),
        control=[f"save {_SAVED}", f"tran 20u {stop:g} 0 {_STEP:g}"],
        options=("method=gear", "reltol=1e-4"),
    )


def _release(result: RunResult) -> float:
    time = result.real("time")
    return measure.first_crossing(time, result.real("ok5v"), 2.5, rising=True)


@bench(
    "analog_rails",
    "power-up",
    "Power-up: the order in which the rails arrive",
    "section 3 (order of the rails at power-up, steps 1 to 8), section 4.11, rules F-2 and "
    "F-3, decisions D-48 and D-53",
)
def power_up(ctx: Context) -> Outcome:
    """The 5 V source ramps up and every rail of the carrier starts by itself.

    The circuit is the two sheets of the analog rails and the rail monitor
    with the supervisor and the 3.3 V regulators of the logic supplies and
    every capacitor of the schematic on a rail. The run is made three times:
    with the typical release delay of the supervisor and with its two
    limits. The two converters are their averaged models here, so that a run
    of more than a second is possible; their switching is in the benches of
    the boost converter and of the ripple.
    """
    runs: dict[str, RunResult] = {}
    for name, delay in _DELAYS.items():
        after = _SETTLE if name == "typ" else _AFTER_RELEASE
        stop = common.RAMP_START + common.RAMP_TIME + delay + after
        runs[name] = ctx.run(name, _deck(ctx, delay, stop), keep=name == "typ")
    typ = runs["typ"]
    time = typ.real("time")
    release = _release(typ)

    def wave(name: str) -> common.Real:
        return typ.real(name)

    def after_release(name: str, level: float, rising: bool = True) -> float:
        return common.crossing_after(time, wave(name), level, rising, release - 1e-3) - release

    power = common.RAMP_START
    hold = (time > 0.0) & (time < release - 1e-3)
    final_12 = measure.mean(time, wave("p12v_a"), time[-1] - 0.02, time[-1])
    at_11 = after_release("p12v_a", 11.0)
    tau = after_release("p12v_a", 11.0 + (final_12 - 11.0) * (1.0 - np.exp(-1.0))) - at_11
    settled_12 = measure.settling_time(time, wave("p12v_a"), final_12, 0.001 * 12.0, release)
    final_ref = measure.mean(time, wave("vref"), time[-1] - 0.02, time[-1])
    ref_settled = measure.settling_time(time, wave("vref"), final_ref, 0.001 * 2.5, release)
    good = after_release("gp28", 2.0)
    arrivals = {
        "3V3_A": after_release("p3v3_a", 3.0),
        "3V3_C": after_release("p3v3_c", 3.0),
        "-4V_A": after_release("m4v_a", -3.5, rising=False),
        "+12V_A": after_release("p12v_a", 9.85),
    }
    figures = [
        Figure(
            "rail_5v",
            "5 V rail above 4.75 V after the source starts to rise",
            measure.first_crossing(time, wave("p5v"), 4.75, rising=True) - power,
            "s",
            source="section 3, step 1: a ramp of 1.7 ms (the ramp is the stimulus here)",
        ),
        Figure(
            "boost_charged",
            "+13V5 above 12.2 V after the source starts to rise",
            measure.first_crossing(time, wave("p13v5"), 12.2, rising=True) - power,
            "s",
            expected=3e-3,
            high=4.5e-3,
            source="section 3, step 2: charged about 3 ms after the start",
        ),
        Figure(
            "boost_level",
            "+13V5 at the end of the hold-off",
            measure.value_at(time, wave("p13v5"), release - 1e-3),
            "V",
            expected=13.53,
            low=13.0,
            high=14.1,
            source="section 3: 13.0 V to 14.1 V",
        ),
        Figure(
            "hold_off",
            "Release of the supervisor after the rail is above 4.12 V, typical",
            release - measure.first_crossing(time, wave("p5v"), 4.12, rising=True),
            "s",
            expected=0.30,
            low=0.18,
            high=0.42,
            source="section 3, step 3: 0.18 s to 0.42 s",
        ),
    ]
    for key, label in (
        ("p3v3_a", "3V3_A"),
        ("p3v3_c", "3V3_C"),
        ("p12v_a", "+12V_A"),
        ("vref", "VREF"),
        ("gp28", "PWR_GOOD at the controller pin"),
    ):
        figures.append(
            Figure(
                f"held_{key}",
                f"{label}: highest level during the hold-off",
                float(np.max(wave(key)[hold])),
                "V",
                high=0.1,
                source="section 3, step 3: only the 5 V rail and +13.5 V are present "
                "(0.1 V taken as absent)",
            )
        )
    figures.append(
        Figure(
            "held_m4v_a",
            "-4V_A: lowest level during the hold-off",
            float(np.min(wave("m4v_a")[hold])),
            "V",
            low=-0.1,
            source="section 3, step 3 (0.1 V taken as absent)",
        )
    )
    figures += [
        Figure(
            "t_3v3_a",
            "3V3_A above 3.0 V after the release",
            arrivals["3V3_A"],
            "s",
            expected=0.04e-3,
            high=0.15e-3,
            source="section 3, step 4: 0.04 ms; 150 us is the datasheet limit of the regulator",
        ),
        Figure(
            "t_3v3_c",
            "3V3_C above 3.0 V after the release",
            arrivals["3V3_C"],
            "s",
            expected=0.04e-3,
            high=0.15e-3,
            source="section 3, step 4: 0.04 ms; 150 us is the datasheet limit of the regulator",
        ),
        Figure(
            "t_m4v_a",
            "-4V_A below -3.5 V after the release",
            arrivals["-4V_A"],
            "s",
            expected=0.3e-3,
            low=0.2e-3,
            high=0.4e-3,
            source="section 3, step 5: 0.3 ms (taken as 0.2 ms to 0.4 ms)",
        ),
        Figure(
            "t_12v_985",
            "+12V_A above 9.85 V after the release",
            arrivals["+12V_A"],
            "s",
            low=8e-3,
            high=17e-3,
            source="section 3, step 6: 8 ms to 17 ms",
        ),
        near(
            "t_12v_11",
            "+12V_A at 11 V after the release",
            at_11,
            "s",
            18e-3,
            0.15,
            "rule F-3: 18 ms",
        ),
        near(
            "tau_12v",
            "+12V_A: time constant of the approach from 11 V",
            tau,
            "s",
            0.18,
            0.2,
            "rules F-3 and F-36: 0.18 s",
        ),
        near(
            "t_12v_window",
            "+12V_A inside its window (11.4 V) after the release",
            after_release("p12v_a", 11.4),
            "s",
            0.1,
            0.25,
            "rule F-3: about 0.1 s",
        ),
        near(
            "t_12v_settled",
            "+12V_A within 0.1 % of its final value after the release",
            settled_12,
            "s",
            0.8,
            0.25,
            "section 3, step 6: settles in about 0.8 s",
        ),
        Figure(
            "v_12v",
            "+12V_A, final value",
            final_12,
            "V",
            expected=12.0,
            low=11.4,
            high=12.6,
            source="rule F-12: 11.4 V to 12.6 V",
        ),
        near(
            "t_vref_2v245",
            "VREF above 2.245 V after the release",
            after_release("vref", 2.245),
            "s",
            24e-3,
            0.15,
            "section 3, step 7: 24 ms",
        ),
        near(
            "t_vref_settled",
            "VREF within 0.1 % of its final value after the release",
            ref_settled,
            "s",
            80e-3,
            0.2,
            "section 3, step 7 and rule F-3: about 80 ms",
        ),
        near(
            "t_good",
            "PWR_GOOD above 2.0 V at the controller pin after the release",
            good,
            "s",
            24e-3,
            0.2,
            "section 3, step 8: about 24 ms",
        ),
        Figure(
            "reference_last",
            "VREF settles after the last other rail has passed its monitor threshold by",
            ref_settled - max(arrivals.values()),
            "s",
            low=0.0,
            source="section 16: the reference last",
        ),
        Figure(
            "analog_after_logic",
            "+12V_A passes 1 V after 3V3_A has passed 3.0 V by",
            after_release("p12v_a", 1.0) - arrivals["3V3_A"],
            "s",
            low=0.0,
            source="section 3: no rail of a 12 V part before the 3.3 V rails",
        ),
        near(
            "good_level",
            "PWR_GOOD high level at the controller pin",
            measure.mean(time, wave("gp28"), time[-1] - 0.02, time[-1]),
            "V",
            0.8193 * 3.3,
            0.03,
            "section 4.11: 0.82 x 3V3_C",
        ),
    ]
    early = (time >= release - 1e-3) & (time <= release + 0.5 * good)
    figures.append(
        Figure(
            "good_early",
            "PWR_GOOD at the controller pin: highest level before the flag is valid",
            float(np.max(wave("gp28")[early])) if np.any(early) else float("nan"),
            "V",
            high=2.0,
            source="the controller pin reads high from 2.0 V; rule F-2 asks for 10 ms of "
            "high level before anything is driven",
        )
    )
    for name in ("min", "max"):
        run = runs[name]
        t = run.real("time")
        figures.append(
            Figure(
                f"good_after_power_{name}",
                f"PWR_GOOD after power is applied, supervisor delay {_DELAYS[name]:g} s",
                common.crossing_after(t, run.real("gp28"), 2.0, True, 0.0) - power,
                "s",
                low=0.2,
                high=0.46,
                source="sections 3 (step 8) and 6.4: 0.2 s to 0.46 s",
            )
        )
    figures.append(
        Figure(
            "good_after_power_typ",
            "PWR_GOOD after power is applied, supervisor delay 0.3 s",
            release + good - power,
            "s",
            low=0.2,
            high=0.46,
            source="sections 3 (step 8) and 6.4: 0.2 s to 0.46 s",
        )
    )

    def rails(scale: float, start: float, stop: float, origin: float) -> tuple[Trace, ...]:
        shown = (time >= start) & (time <= stop)
        axis = (time[shown] - origin) * scale
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
        return tuple(Trace(axis, wave(key)[shown], label, panel) for key, label, panel in names)

    panels = (
        Panel("Rails of the 12 V parts (V)"),
        Panel("3.3 V rails and reference (V)"),
        Panel("Supervisor and flag (V)"),
    )
    whole = Graph(
        name="whole",
        title="Power-up with the typical supervisor delay: every rail on one time axis",
        xlabel="Time after power is applied (s)",
        panels=panels,
        traces=rails(1.0, 0.0, release + 0.25, power),
        xmarks=((release - power, "5V_OK"),),
    )
    zoom = Graph(
        name="release",
        title="The 60 ms after the supervisor releases the carrier",
        xlabel="Time after the release (ms)",
        panels=panels,
        traces=rails(1e3, release - 2e-3, release + 60e-3, release),
        xmarks=((at_11 * 1e3, "+12V_A at 11 V"), (good * 1e3, "PWR_GOOD")),
    )
    first = (time >= 0.0) & (time <= 8e-3)
    start = Graph(
        name="start",
        title="The first 8 ms: the 5 V rail and the boost converter",
        xlabel="Time (ms)",
        panels=(Panel("Voltage (V)"), Panel("Current of the 5 V source (A)")),
        traces=(
            Trace(time[first] * 1e3, wave("src")[first], "source", 0, "--"),
            Trace(time[first] * 1e3, wave("p5v")[first], "5 V rail", 0),
            Trace(time[first] * 1e3, wave("p13v5")[first], "+13V5", 0),
            Trace(time[first] * 1e3, -typ.real("vsrc#branch")[first], "source current", 1),
        ),
    )
    notes = (
        "The source of the 5 V rail is a ramp of 1.7 ms to 5 V behind 0.2 ohm with a limit "
        "of 2 A and no path back; the limiters and the multiplexer of the input belong to "
        "the power input block. The loads are current sinks of datasheet supply currents: "
        "5.1 mA from +12V_A to -4V_A, 1.5 mA from +12V_A, 10 mA from 3V3_A, 0.5 mA and the "
        "LED from 3V3_C, 1 mA from +13V5, 25 mA of the controller module from the 5 V rail.",
        "The two converters are averaged models: no ripple, and the end of the start of "
        "the boost converter is that of an error amplifier that is an assumption. The "
        "ceramic capacitors with a bias curve lose capacitance with their voltage; the "
        "SET capacitor C30 of +12V_A is 4.7 uF at 0 V and 1.45 uF at 12 V, which is where "
        "the 18 ms and the 0.18 s of the specification come from.",
        "The -4V_A rail arrives later than the 0.3 ms of the specification: the datasheet "
        "of the charge pump shows 0.32 ms before its output moves and 0.14 ms of ramp "
        "(figure 5-10), and the model follows that. The order of the rails does not change.",
        "While 3V3_C rises, PWR_GOOD follows its pull-up for some microseconds until "
        "the comparators have enough supply to hold it low. The level it reaches depends "
        "on the supply from which their outputs work, which is an assumption (1.2 V; the "
        "datasheet begins at 1.8 V). Rule F-2 makes the pulse harmless.",
        "The supervisor and the 3.3 V regulators are the models of the power input block. "
        "Times of the regulators inside the rise of a rail are those of first-order "
        "models; no statement about overshoot can be taken from them.",
    )
    return Outcome(tuple(figures), (whole, zoom, start), notes)
