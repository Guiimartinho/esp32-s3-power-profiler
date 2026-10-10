"""The supervisor of the 5 V rail and the two 3.3 V rails it enables."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.netlist import Netlist

_RAMP_END = 0.05
"""End of the slow rise of the rail in the first run."""

_HOLD_END = 0.45
"""End of the hold at 5 V: the supervisor has released the carrier."""

_FALL_END = 0.55
"""End of the slow fall to 3 V."""

_SLOW_END = 0.56
"""End of the first run."""

_FAST_ON = 1e-3
"""Instant at which the rail steps to 5 V in the fast runs."""

_DIP_AT = 4e-3
"""Instant of the dip in the fast runs: the carrier runs."""

_FAST_END = 5.5e-3
"""End of the fast runs."""

_DIP_VOLTS = (3.7, 3.0)
"""Levels to which the rail dips: 5 % and 23 % below the nominal threshold."""

_DIP_TIMES = (5e-6, 10e-6, 20e-6, 30e-6, 50e-6, 100e-6)
"""Durations of the dips."""

_ABSMAX_OUT_OVER_IN = 0.3
"""Highest output of a regulator above its input (LP5907 datasheet, SNVS798Q
page 4, absolute maximum)."""

_CORNER_HOLD_END = 0.52
"""End of the hold at 5 V in the corner runs: the longest delay has passed."""

_CORNER_FALL_END = 0.62
"""End of the slow fall to 3 V in the corner runs."""

_CORNER_END = 0.63
"""End of the corner runs."""

_LEVEL_ROUNDING = 0.01
"""Half the last digit of the levels that the specification states."""


@dataclass(frozen=True)
class _Corner:
    """A supervisor and its divider at one end of their tolerances.

    Attributes:
        supervisor: Parameters of the supervisor U6.
        upper: Factor on the upper resistor of the divider, R21.
        lower: Factor on the lower resistor, R22.
    """

    supervisor: str
    upper: float
    lower: float


_LOW = _Corner("vit=0.3969 tdhi=0.18", 0.999, 1.001)
_HIGH = _Corner("vit=0.4131 vhys=3 tdhi=0.42", 1.001, 0.999)
"""The two ends: threshold 2 % below and above 0.405 V, hysteresis 3 % at the
upper end, delay 180 ms and 420 ms (TPS3808 datasheet SBVS050N, pages 6 and
7), with the 0.1 % resistors of the divider against it."""


def _refs(netlist: Netlist) -> tuple[str, ...]:
    """The logic supplies with the capacitors of their rails and the divider on 5V_OK."""
    return (
        *common.logic_refs(netlist),
        *common.decoupling_refs(netlist, "+3V3_C"),
        *common.decoupling_refs(netlist, "+3V3_A"),
        *common.OK_LOADS,
    )


def _deck(
    ctx: Context,
    title: str,
    rail: str,
    stop: float,
    step: float,
    fast: bool,
    corner: _Corner | None = None,
) -> str:
    """The logic supplies on a rail that a source draws."""
    params = {"U6": common.FAST_SUPERVISOR} if fast else {}
    scales = {}
    if corner is not None:
        params = {"U6": corner.supervisor}
        scales = {"R21": corner.upper, "R22": corner.lower}
    circuit = common.circuit(ctx, _refs(ctx.netlist), params=params, scales=scales)
    stimulus = (
        "* the 5 V rail as a source behind 50 mohm (not in the schematic)\n"
        f"Vrail rail_s 0 {rail}\n"
        "Rrail rail_s rail 50m\n"
        "* loads of the two rails at idle (assumptions)\n"
        f"Bload_c v3c 0 I = {common.LOGIC_3V3C_AMPS:g}*v(v3c)/3.3\n"
        f"Bload_a v3a 0 I = {common.LOGIC_3V3A_AMPS:g}*v(v3a)/3.3\n"
    )
    control = ["save all @dd5[id]", common.transient(step, stop)]
    return ctx.deck(title, circuit, stimulus, control=control)


def _dip(volts: float, seconds: float) -> str:
    """A rail that steps to 5 V, dips once and returns."""
    edge = 2e-6
    return (
        f"PWL(0 0 {_FAST_ON:g} 0 {_FAST_ON + 10e-6:g} 5 {_DIP_AT:g} 5 "
        f"{_DIP_AT + edge:g} {volts:g} {_DIP_AT + edge + seconds:g} {volts:g} "
        f"{_DIP_AT + 2 * edge + seconds:g} 5)"
    )


@bench(
    "power_input",
    "logic-rails",
    "The supervisor of the 5 V rail and the two 3.3 V rails: thresholds, delay, start and trip",
    "section 3 (supervisor, order of the rails steps 3 and 4, power-off), section 4.1 "
    "(thresholds of the 5 V rail, enforcement), section 4.11 (LED)",
)
def logic_rails(ctx: Context) -> Outcome:
    """The 5 V rail is a source; the supervisor and the two regulators are the circuit.

    In the first run the rail rises within 50 ms, stays at 5 V until the
    supervisor has released the carrier, and falls slowly to 3 V: this gives
    the two levels of the supervisor, its delay, the start of the 3.3 V
    rails and their end. Two more runs of that kind have the supervisor and
    its divider at the two ends of their tolerances. A further run lets the
    rail fall at 20 V/ms down to 0 V: as fast as it falls when the supply is
    pulled at full output, and all the way down, which only a short circuit
    of the rail does. Twelve short runs dip the rail to 3.7 V and to 3.0 V
    for 5 us to 100 us to find the shortest dip that trips the supervisor.
    """
    slow_rail = f"PWL(0 0 {_RAMP_END:g} 5 {_HOLD_END:g} 5 {_FALL_END:g} 3 {_SLOW_END:g} 3)"
    fall_rail = (
        f"PWL(0 0 {_FAST_ON:g} 0 {_FAST_ON + 10e-6:g} 5 {_DIP_AT:g} 5 {_DIP_AT + 0.25e-3:g} 0)"
    )
    decks = {
        "slow": _deck(
            ctx,
            "Supervisor and 3.3 V rails: slow edges of the rail",
            slow_rail,
            _SLOW_END,
            20e-6,
            False,
        ),
        "fall": _deck(
            ctx,
            "Supervisor and 3.3 V rails: the rail falls at 20 V/ms",
            fall_rail,
            _FAST_END,
            0.5e-6,
            True,
        ),
    }
    corner_rail = (
        f"PWL(0 0 {_RAMP_END:g} 5 {_CORNER_HOLD_END:g} 5 {_CORNER_FALL_END:g} 3 {_CORNER_END:g} 3)"
    )
    for name, corner in (("corner-low", _LOW), ("corner-high", _HIGH)):
        title = f"Supervisor at one end of its tolerances: {corner.supervisor}"
        decks[name] = _deck(ctx, title, corner_rail, _CORNER_END, 20e-6, False, corner)
    for volts in _DIP_VOLTS:
        for seconds in _DIP_TIMES:
            name = f"dip-{volts:g}v-{seconds * 1e6:g}us".replace(".", "p")
            title = f"Supervisor: a dip of the rail to {volts:g} V for {seconds * 1e6:g} us"
            decks[name] = _deck(ctx, title, _dip(volts, seconds), _FAST_END, 0.5e-6, True)
    runs = common.run_all(ctx, decks, keep=("slow", "fall"))

    slow = runs["slow"]
    time = slow.real("time")
    rail, ok5v = slow.real("rail"), slow.real("ok5v")
    v3c, v3a = slow.real("v3c"), slow.real("v3a")
    released = measure.first_crossing(time, ok5v, 1.2, rising=True, after=_RAMP_END * 0.5)
    rise_level = common.SUPERVISOR_TYP[1]
    passed = measure.first_crossing(time, rail, rise_level, rising=True)
    figures = [
        Figure(
            "release_delay",
            "5V_OK high after the rail has passed 3.97 V, rising",
            released - passed,
            "s",
            expected=0.30,
            low=0.18,
            high=0.42,
            source="section 3: 0.18 s to 0.42 s (calculated from datasheet limits)",
        ),
    ]
    if ctx.tier == "open":
        good = slow.real("xu6.good")
        flips = measure.first_crossing(time, good, 0.5, rising=True)
        figures.append(
            Figure(
                "release_level",
                "Level of the rail at which the supervisor starts its delay",
                measure.value_at(time, rail, flips),
                "V",
                expected=rise_level,
                high=common.SUPERVISOR_RISE_MOST,
                source="section 3: back above 4.12 V at most (calculated)",
            )
        )
    tripped = measure.first_crossing(time, ok5v, 1.2, rising=False, after=_HOLD_END)
    v3c_95 = measure.first_crossing(time, v3c, 0.95 * 3.3, rising=True, after=released - 1e-3)
    v3a_95 = measure.first_crossing(time, v3a, 0.95 * 3.3, rising=True, after=released - 1e-3)
    before = common.cut(time, 0.0, released - 0.2e-3)
    running = common.cut(time, released + 2e-3, _HOLD_END)
    led = slow.real("@dd5[id]")
    figures += [
        Figure(
            "trip_level",
            "Level of the rail at which 5V_OK falls, rail falling slowly",
            measure.value_at(time, rail, tripped),
            "V",
            expected=common.SUPERVISOR_TYP[0],
            low=common.SUPERVISOR_FALL[0],
            high=common.SUPERVISOR_FALL[1],
            source="section 3: 3.83 V to 4.00 V (calculated; nominal 3.91 V)",
        ),
        Figure(
            "v3c_start",
            "3V3_C at 95 % after 5V_OK has passed 1.2 V",
            v3c_95 - released,
            "s",
            expected=0.04e-3,
            high=150e-6,
            source="section 3, step 4: 0.04 ms after 5V_OK; LP5907 datasheet: 80 us "
            "typical, 150 us at most",
        ),
        Figure(
            "v3a_start",
            "3V3_A at 95 % after 5V_OK has passed 1.2 V",
            v3a_95 - released,
            "s",
            expected=0.04e-3,
            high=150e-6,
            source="section 3, step 4: 0.04 ms after 5V_OK; LP5907 datasheet: 80 us "
            "typical, 150 us at most",
        ),
        Figure(
            "v3_before",
            "Highest level of a 3.3 V rail before 5V_OK rises",
            float(max(np.max(v3c[before]), np.max(v3a[before]))),
            "V",
            high=0.1,
            source="section 3: the 3.3 V rails come 0.04 ms after 5V_OK, not before",
        ),
        Figure(
            "v3c_level",
            "3V3_C with 10 mA of load and 5 V on the rail",
            measure.mean(time, v3c, released + 2e-3, _HOLD_END),
            "V",
            expected=3.3,
            low=3.3 * 0.98,
            high=3.3 * 1.02,
            source="LP5907 datasheet, page 5: 2 %",
        ),
        Figure(
            "v3a_level",
            "3V3_A with 25 mA of load and 5 V on the rail",
            measure.mean(time, v3a, released + 2e-3, _HOLD_END),
            "V",
            expected=3.3,
            low=3.3 * 0.98,
            high=3.3 * 1.02,
            source="LP5907 datasheet, page 5: 2 %",
        ),
        Figure(
            "v3a_at_trip",
            "3V3_A just before the supervisor trips (rail at 3.93 V)",
            measure.value_at(time, v3a, tripped - 1e-3),
            "V",
            low=3.3 * 0.98,
            source="the regulator needs 3.3 V plus its dropout; LP5907 datasheet, page 5",
        ),
        Figure(
            "ok_high",
            "High level of 5V_OK with 5 V on the rail",
            float(np.mean(ok5v[running])),
            "V",
            low=1.2,
            source="LP5907 datasheet, page 6: enable high from 1.2 V",
        ),
        Figure(
            "led_amps",
            "Current of the LED",
            float(np.mean(led[running])),
            "A",
            expected=1.3e-3,
            source="section 4.11: 1.3 mA (calculated)",
        ),
        Figure(
            "ok_glitch",
            "Highest level of 5V_OK while the rail rises, before the release",
            float(np.max(ok5v[before])),
            "V",
        ),
    ]
    for name, label, expected in (
        ("corner-low", "lowest threshold", common.SUPERVISOR_FALL[0]),
        ("corner-high", "highest threshold", common.SUPERVISOR_FALL[1]),
    ):
        run = runs[name]
        c_time, c_rail, c_ok = run.real("time"), run.real("rail"), run.real("ok5v")
        c_trip = measure.first_crossing(c_time, c_ok, 1.2, rising=False, after=_CORNER_HOLD_END)
        figures.append(
            Figure(
                f"trip_level_{name[7:]}",
                f"Level of the rail at which 5V_OK falls, supervisor with the {label}",
                measure.value_at(c_time, c_rail, c_trip),
                "V",
                expected=expected,
                low=expected - _LEVEL_ROUNDING,
                high=expected + _LEVEL_ROUNDING,
                source="section 3: 3.83 V to 4.00 V (calculated from datasheet limits and "
                "the 0.1 % divider)",
            )
        )
    high_run = runs["corner-high"]
    h_time, h_ok = high_run.real("time"), high_run.real("ok5v")
    h_released = measure.first_crossing(h_time, h_ok, 1.2, rising=True, after=_RAMP_END * 0.5)
    h_passed = measure.first_crossing(
        h_time, high_run.real("rail"), common.SUPERVISOR_RISE_MOST, rising=True
    )
    figures.append(
        Figure(
            "release_delay_high",
            "5V_OK high after the rail has passed 4.12 V, supervisor with the highest "
            "threshold and the longest delay",
            h_released - h_passed,
            "s",
            expected=0.42,
            low=0.18,
            high=0.42 + 2e-3,
            source="section 3: 0.18 s to 0.42 s after the rail is back above 4.12 V at most",
        )
    )
    if ctx.tier == "open":
        h_flips = measure.first_crossing(h_time, high_run.real("xu6.good"), 0.5, rising=True)
        figures.append(
            Figure(
                "release_level_high",
                "Level of the rail at which the supervisor with the highest threshold "
                "starts its delay",
                measure.value_at(h_time, high_run.real("rail"), h_flips),
                "V",
                expected=common.SUPERVISOR_RISE_MOST,
                high=common.SUPERVISOR_RISE_MOST + _LEVEL_ROUNDING,
                source="section 3: back above 4.12 V at most (calculated)",
            )
        )
    fall = runs["fall"]
    t_fall = fall.real("time")
    f_rail, f_ok = fall.real("rail"), fall.real("ok5v")
    f_v3c, f_v3a = fall.real("v3c"), fall.real("v3a")
    crossed = measure.first_crossing(t_fall, f_rail, common.SUPERVISOR_TYP[0], False, _DIP_AT)
    low_at = measure.first_crossing(t_fall, f_ok, 1.2, rising=False, after=_DIP_AT)
    falling = common.cut(t_fall, _DIP_AT, _FAST_END)
    figures += [
        Figure(
            "fall_trip_delay",
            "Rail falling at 20 V/ms: 5V_OK below 1.2 V after the rail has passed 3.91 V",
            low_at - crossed,
            "s",
            high=0.1e-3,
            source="section 4.1: the pre-regulator is off within 0.1 ms (estimate)",
        ),
        Figure(
            "fall_v3c_3v0",
            "Rail falling at 20 V/ms: 3V3_C below 3.0 V after 5V_OK has fallen",
            measure.first_crossing(t_fall, f_v3c, 3.0, rising=False, after=_DIP_AT) - low_at,
            "s",
            expected=0.02e-3,
            source="section 3: 3V3_C is below 3.0 V after 0.02 ms (simulated)",
        ),
        Figure(
            "fall_v3a_1v0",
            "Rail falling at 20 V/ms: 3V3_A below 1.0 V after 5V_OK has fallen",
            measure.first_crossing(t_fall, f_v3a, 1.0, rising=False, after=_DIP_AT) - low_at,
            "s",
            expected=5e-3,
            source="section 3: 3V3_A is below 1.0 V after 4 ms to 6 ms (simulated, with "
            "the reference and its capacitors, which are not in this run)",
        ),
        Figure(
            "fall_v3a_over_rail",
            "Rail falling at 20 V/ms: highest level of 3V3_A above the rail",
            float(np.max((f_v3a - f_rail)[falling])),
            "V",
            high=_ABSMAX_OUT_OVER_IN,
            source="LP5907 datasheet, page 4: output at most 0.3 V above the input; the "
            "specification states no figure",
        ),
        Figure(
            "fall_v3c_over_rail",
            "Rail falling at 20 V/ms: highest level of 3V3_C above the rail",
            float(np.max((f_v3c - f_rail)[falling])),
            "V",
            high=_ABSMAX_OUT_OVER_IN,
            source="LP5907 datasheet, page 4: output at most 0.3 V above the input; the "
            "specification states no figure",
        ),
    ]
    for volts in _DIP_VOLTS:
        shortest = float("nan")
        for seconds in _DIP_TIMES:
            name = f"dip-{volts:g}v-{seconds * 1e6:g}us".replace(".", "p")
            run_time = runs[name].real("time")
            after = common.cut(run_time, _DIP_AT, _FAST_END)
            if float(np.min(runs[name].real("ok5v")[after])) < 1.2:
                shortest = seconds
                break
        figures.append(
            Figure(
                f"dip_{volts:g}v".replace(".", "p"),
                f"Shortest dip to {volts:g} V that takes 5V_OK low (of 5, 10, 20, 30, 50, 100 us)",
                shortest,
                "s",
                expected=30e-6,
                source="section 4.1: any dip below that level for more than about 30 us",
            )
        )
    slow_graph = Graph(
        name="slow",
        title="The rail rises within 50 ms, holds, and falls slowly",
        xlabel="Time (s)",
        panels=(Panel("Voltage (V)", marks=((common.SUPERVISOR_TYP[0], "3.91 V"),)),),
        traces=(
            Trace(time, rail, "5 V rail", 0),
            Trace(time, ok5v, "5V_OK", 0),
            Trace(time, v3a, "3V3_A", 0),
            Trace(time, v3c, "3V3_C", 0, "--"),
        ),
    )
    start = common.cut(time, released - 50e-6, released + 250e-6)
    start_graph = Graph(
        name="start",
        title="The 3.3 V rails start when 5V_OK rises",
        xlabel="Time after 5V_OK has passed 1.2 V (us)",
        panels=(Panel("Voltage (V)"),),
        traces=(
            Trace((time[start] - released) * 1e6, ok5v[start], "5V_OK", 0),
            Trace((time[start] - released) * 1e6, v3a[start], "3V3_A", 0),
            Trace((time[start] - released) * 1e6, v3c[start], "3V3_C", 0, "--"),
        ),
    )
    shown = common.cut(t_fall, _DIP_AT - 50e-6, _DIP_AT + 1.2e-3)
    fall_graph = Graph(
        name="fall",
        title="The rail falls at 20 V/ms from 5 V",
        xlabel="Time after the rail starts to fall (us)",
        panels=(Panel("Voltage (V)", marks=((common.SUPERVISOR_TYP[0], "3.91 V"),)),),
        traces=(
            Trace((t_fall[shown] - _DIP_AT) * 1e6, f_rail[shown], "5 V rail", 0),
            Trace((t_fall[shown] - _DIP_AT) * 1e6, f_ok[shown], "5V_OK", 0),
            Trace((t_fall[shown] - _DIP_AT) * 1e6, f_v3a[shown], "3V3_A", 0),
            Trace((t_fall[shown] - _DIP_AT) * 1e6, f_v3c[shown], "3V3_C", 0, "--"),
        ),
    )
    notes = (
        "The rail is a source behind 50 mohm, not the input stage: the levels of the "
        "supervisor do not depend on what feeds the rail.",
        "The supervisor is a typical part: 0.405 V at its input, 1.5 % of hysteresis, "
        "300 ms. The two corner runs take the 2 % of the datasheet, 3 % of hysteresis, "
        "180 ms and 420 ms, with the 0.1 % divider against them; their limits are the "
        "figures of the specification with half a digit of rounding. In the fast runs "
        "the delay is shortened to 1 ms, which does not change the reaction to a falling "
        "rail.",
        "The regulators start 80 us after their enable, the typical value of the "
        "datasheet, which is twice what the specification writes in step 4.",
        "The loads of the rails are assumptions: 10 mA on 3V3_C beside the LED and 25 mA "
        "on 3V3_A. The capacitors of the rails are the ones of the schematic, also the "
        "ones drawn on other sheets. The reference and its capacitors, which feed 3V3_A "
        "back through D7 at power-off, are not in this circuit.",
        "When the rail falls faster than the 3.3 V rails are discharged (230 ohm in the "
        "regulator), the output of a regulator stands above its input. The body diode "
        "that then conducts is an assumption of the model; the datasheet only gives the "
        "0.3 V of the absolute maximum. The run in which this happens takes the rail to "
        "0 V at 20 V/ms, which is a short circuit of the rail; when the supply is pulled "
        "at full output the rail stops falling once the load is shed, and the bench of "
        "the unplug finds 30 mV.",
        "5V_OK is pulled up to the rail through R25, so its high level is the rail less "
        "what the inputs on the line take.",
    )
    return Outcome(tuple(figures), (slow_graph, start_graph, fall_graph), notes)
