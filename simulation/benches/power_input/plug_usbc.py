"""Plugging a live USB-C source: the peak at the receptacle, the in-rush, the rail."""

from __future__ import annotations

import numpy as np

from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.engine import RunResult

_PLUG = 0.2e-3
"""Instant at which the contact closes."""

_END = 6e-3
"""End of a run: the rail and the output of the boost converter are up."""

_WEAK_END = 8e-3
"""End of the run on a weak source, which takes longer to bring the rail up."""

_PEAK_END = 0.3e-3
"""End of the short runs that look at the peak at the receptacle only."""

_SETTLE_SPAN = 0.3e-3
"""Time over which the settling of the priority input is read."""

_USB_INRUSH_COULOMBS = 50e-6
"""Charge above 100 mA that the in-rush test of the USB specification allows
(the figure that section 4.1 of the specification quotes)."""

_WEAK_AMPS = 0.9
"""Current of a source that gives no more than a USB 3 port has to."""

_WORST_PEAK = "peak-5p5v-0p08r-1p5u"
"""Name of the peak run with the highest source and the longest cable."""

_CABLES = {
    "0.15 ohm, 0.5 uH": (0.15, 0.5e-6),
    "0.08 ohm, 0.5 uH": (0.08, 0.5e-6),
    "0.08 ohm, 1.5 uH": (0.08, 1.5e-6),
}
"""Cables of the peak runs: the one of the long runs, the one that the earlier
estimate of the specification used, and a longer one of low resistance."""


def _deck(
    ctx: Context,
    volts: float,
    stop: float,
    step: float,
    title: str,
    *,
    ohms: float = common.CABLE_OHMS,
    henries: float = common.CABLE_HENRIES,
    amps: float | None = None,
) -> str:
    """The whole carrier on a USB-C source that is plugged in at 0.2 ms."""
    circuit = common.circuit(ctx, common.carrier_refs(ctx.netlist), bias=common.BIAS_CURVE)
    stimulus = (
        common.usb_c_source(volts, _PLUG, ohms=ohms, henries=henries, amps=amps)
        + common.boost_start()
        + common.idle_loads()
    )
    return ctx.deck(title, circuit, stimulus, control=[common.transient(step, stop)])


def _time_constant(time: np.ndarray, follower: np.ndarray, leader: np.ndarray, at: float) -> float:
    """The time constant with which a divided node settles after its input has.

    The input stands still from ``at`` on. What the follower lacks to its
    final share of the input falls exponentially; the constant is read
    between ``at`` and 0.3 ms later.
    """
    share = float(follower[-1] / leader[-1])
    lack = share * leader - follower
    first = measure.value_at(time, lack, at)
    second = measure.value_at(time, lack, at + _SETTLE_SPAN)
    return _SETTLE_SPAN / float(np.log(first / second))


def _fall_back(values: np.ndarray) -> float:
    """How far a rising waveform falls back below a level it had reached."""
    return float(np.max(np.maximum.accumulate(values) - values))


def _start_figures(result: RunResult) -> tuple[list[Figure], float]:
    """The figures of the typical start, and the instant the rail is at 90 %."""
    time = result.real("time")
    vin1, rail = result.real("vin1"), result.real("rail")
    amps = result.real("vusbc_i#branch")
    limiter_10 = measure.first_crossing(time, vin1, 0.5, rising=True, after=_PLUG)
    limiter_90 = measure.first_crossing(time, vin1, 4.5, rising=True, after=limiter_10)
    rail_10 = measure.first_crossing(time, rail, 0.5, rising=True, after=_PLUG)
    rail_90 = measure.first_crossing(time, rail, 4.5, rising=True, after=rail_10)
    boost_up = measure.first_crossing(time, result.real("p13v5"), 13.4, rising=True, after=_PLUG)
    ramp = common.cut(time, limiter_10, limiter_90)
    soft = common.cut(time, rail_10, float(time[-1]))
    figures = [
        Figure(
            "limiter_delay",
            "Limiter: from the plug to 10 % at its output",
            limiter_10 - _PLUG,
            "s",
            expected=0.25e-3,
            source="section 4.1: turn-on delay of about 0.25 ms",
        ),
        Figure(
            "limiter_ramp",
            "Limiter: slope of its output between 10 % and 90 %",
            4.0 / (limiter_90 - limiter_10),
            "V/s",
            expected=13e3,
            source="section 4.1: 13 V/ms with C4",
        ),
        Figure(
            "inrush_limiter",
            "Largest source current while the limiter ramps (damper and its own capacitor)",
            float(np.max(amps[ramp])),
            "A",
            low=0.3,
            high=0.9,
            source="section 14: ramps of 0.3 A to 0.9 A",
        ),
        Figure(
            "priority_lag",
            "Priority input of the multiplexer at 1.0 V after the output of the limiter "
            "has passed 2.37 V on its ramp",
            measure.first_crossing(time, result.real("pr1"), 1.0, rising=True, after=_PLUG)
            - measure.first_crossing(time, vin1, 2.37, rising=True, after=_PLUG),
            "s",
        ),
        near(
            "priority_time_constant",
            "Time constant with which the priority input follows the output of the limiter",
            _time_constant(time, result.real("pr1"), vin1, limiter_90 + 0.1e-3),
            "s",
            0.19e-3,
            0.05,
            "section 4.1: C8 delays it by 0.19 ms (the limits are the fit of the bench)",
        ),
        Figure(
            "rail_delay",
            "Rail at 10 % after the output of the limiter is at 10 %",
            rail_10 - limiter_10,
            "s",
            expected=1.0e-3,
            source="section 3, step 1: about 1 ms after the limiter has turned on",
        ),
        Figure(
            "rail_ramp",
            "Rail from 10 % to 90 %",
            rail_90 - rail_10,
            "s",
            expected=1.7e-3,
            source="section 3, step 1: ramp of 1.7 ms",
        ),
        Figure(
            "inrush_rail_only",
            "Source current while the rail rises, before the boost converter runs",
            measure.value_at(time, amps, rail_10 + 0.6e-3),
            "A",
            low=0.3,
            high=0.9,
            source="section 14: ramps of 0.3 A to 0.9 A",
        ),
        Figure(
            "inrush_peak",
            "Largest source current after the first microseconds (the boost converter starts)",
            float(np.max(amps[soft])),
            "A",
        ),
        Figure(
            "boost_up",
            "Output of the boost converter at 13.4 V after the plug",
            boost_up - _PLUG,
            "s",
            expected=3e-3,
            source="section 3, step 2: charged about 3 ms after the start",
        ),
        Figure(
            "rail_fall_back",
            "Largest fall-back of the rail during its rise",
            _fall_back(rail[soft]),
            "V",
        ),
        Figure(
            "charge",
            "Charge that the source gives above 100 mA",
            common.charge_above(time, amps, 0.1, _PLUG, _END),
            "C",
            high=_USB_INRUSH_COULOMBS,
            source="the 50 uC of the USB in-rush test (section 4.1 states that it is not met)",
        ),
        Figure("rail_end", "Rail at the end of the run", float(rail[-1]), "V"),
        Figure(
            "ok_glitch",
            "Highest level of 5V_OK during the run (the supervisor holds the carrier off)",
            float(np.max(result.real("ok5v"))),
            "V",
        ),
        Figure(
            "ok_low",
            "5V_OK at the end of the run",
            float(result.real("ok5v")[-1]),
            "V",
            high=0.4,
            source="section 3, step 3: hold-off of 0.18 s to 0.42 s",
        ),
    ]
    return figures, rail_90


@bench(
    "power_input",
    "plug-usbc",
    "Plugging a live USB-C source: peak at the receptacle, in-rush, soft start, the 5 V rail",
    "section 3 (order of the rails, steps 1 and 2), section 4.1 (input stage, hot plug), "
    "section 11",
)
def plug_usbc(ctx: Context) -> Outcome:
    """A live source is plugged into the USB-C receptacle of a carrier without power.

    The circuit is the whole power input with the logic supplies, the
    capacitors of the other sheets on the rails, the passive parts of the
    boost converter and the controller module on its diode. The cable of the
    module is not plugged. The run with a 5.0 V source shows the delay and
    the ramp of the limiter, the delay and the soft start of the multiplexer
    and the current that the source has to give. A run with 5.5 V looks for
    the highest voltages behind the limiter, a run on a source that gives no
    more than 0.9 A for a start on a weak port, and six short runs for the
    peak that the cable and the capacitors at the receptacle ring up to.
    """
    weak_title = "USB-C plugged, 5.0 V source of 0.9 A"
    long_decks = {
        "plug-5v0": _deck(ctx, 5.0, _END, 0.5e-6, "USB-C plugged, 5.0 V source"),
        "plug-5v5": _deck(ctx, 5.5, _END, 0.5e-6, "USB-C plugged, 5.5 V source"),
        "plug-weak": _deck(ctx, 5.0, _WEAK_END, 0.5e-6, weak_title, amps=_WEAK_AMPS),
    }
    decks = {}
    for volts in (5.25, 5.5):
        for label, (ohms, henries) in _CABLES.items():
            title = f"Hot plug of a {volts:g} V source through {label}: the peak"
            name = f"peak-{volts:g}v-{ohms:g}r-{henries * 1e6:g}u".replace(".", "p")
            decks[(volts, label, name)] = _deck(
                ctx, volts, _PEAK_END, 10e-9, title, ohms=ohms, henries=henries
            )
    runs = common.run_all(
        ctx,
        {**long_decks, **{key[2]: deck for key, deck in decks.items()}},
        keep=(*long_decks, _WORST_PEAK),
    )
    result, high, weak = runs["plug-5v0"], runs["plug-5v5"], runs["plug-weak"]
    time = result.real("time")
    milli = time * 1e3
    figures, _ = _start_figures(result)
    after_ring = common.cut(high.real("time"), _PLUG + 80e-6, _END)
    t_weak = weak.real("time")
    weak_rail, weak_p13 = weak.real("rail"), weak.real("p13v5")
    weak_up = float(np.max(weak_p13)) > 13.4
    weak_time = (
        measure.first_crossing(t_weak, weak_p13, 13.4, rising=True, after=_PLUG) - _PLUG
        if weak_up
        else float("nan")
    )
    peaks = runs
    worst = runs[_WORST_PEAK]
    expected = {(5.25, "0.08 ohm, 0.5 uH"): 11.4, (5.5, "0.08 ohm, 0.5 uH"): 12.2}
    for volts, label, name in decks:
        run = peaks[name]
        figures.append(
            Figure(
                f"peak_{name[5:]}",
                f"Peak at the receptacle, {volts:g} V source, cable {label}",
                float(np.max(run.real("vbus_c"))),
                "V",
                expected=expected.get((volts, label)),
                high=21.0,
                source="section 4.1: 11.4 V and 12.2 V (simulated); limiter rated for 21 V",
            )
        )
    figures += [
        Figure(
            "suppressor_peak",
            "Largest current of the suppressor, 5.5 V source, cable 0.08 ohm, 1.5 uH",
            float(np.max(worst.real("v.xd2.vz#branch"))),
            "A",
        ),
        Figure(
            "behind_limiter_5v5",
            "Highest voltage behind the limiter, 5.5 V source, whole start",
            float(np.max(high.real("vin1"))),
            "V",
            high=5.51,
            source="section 4.1: 5.51 V or below",
        ),
        Figure(
            "rail_over_source",
            "Highest rail voltage above the source, 5.5 V source, whole start",
            float(np.max(high.real("rail")[after_ring])) - 5.5,
            "V",
            high=0.0,
            source="section 4.1: the rail never rises above the source",
        ),
        Figure(
            "weak_boost_up",
            "Source of 0.9 A: output of the boost converter at 13.4 V after the plug",
            weak_time,
            "s",
        ),
        Figure(
            "weak_rail_fall_back",
            "Source of 0.9 A: largest fall-back of the rail during its rise",
            _fall_back(weak_rail[common.cut(t_weak, _PLUG, float(t_weak[-1]))]),
            "V",
        ),
        Figure(
            "weak_receptacle_low",
            "Source of 0.9 A: lowest voltage at the receptacle once the limiter is on",
            float(np.min(weak.real("vbus_c")[common.cut(t_weak, _PLUG + 1e-3, t_weak[-1])])),
            "V",
            low=3.09,
            source="section 4.1: a limiter turns off at 2.67 V to 2.87 V and on at up to 3.09 V",
        ),
        Figure(
            "weak_rail_end",
            "Source of 0.9 A: rail at the end of the run",
            float(weak_rail[-1]),
            "V",
            low=4.12,
            source="section 4.1: highest release level of the supervisor",
        ),
    ]
    whole = Graph(
        name="start",
        title="USB-C plugged at 0.2 ms, 5.0 V source: the rail comes up",
        xlabel="Time (ms)",
        panels=(Panel("Voltage (V)"), Panel("Output of the boost converter (V)"), Panel("A")),
        traces=(
            Trace(milli, result.real("vbus_c"), "receptacle", 0),
            Trace(milli, result.real("vin1"), "behind the limiter (input 1)", 0),
            Trace(milli, result.real("rail"), "5 V rail", 0),
            Trace(milli, result.real("vsys"), "VSYS of the module", 0, "--"),
            Trace(milli, result.real("p13v5"), "+13.5 V", 1),
            Trace(milli, np.clip(result.real("vusbc_i#branch"), -0.5, 2.5), "source current", 2),
        ),
        xmarks=((_PLUG * 1e3, "plug"),),
    )
    weak_graph = Graph(
        name="weak",
        title="The same start on a source that gives no more than 0.9 A",
        xlabel="Time (ms)",
        panels=(Panel("Voltage (V)"), Panel("Output of the boost converter (V)"), Panel("A")),
        traces=(
            Trace(t_weak * 1e3, weak.real("vbus_c"), "receptacle", 0),
            Trace(t_weak * 1e3, weak.real("vin1"), "behind the limiter (input 1)", 0),
            Trace(t_weak * 1e3, weak_rail, "5 V rail", 0),
            Trace(t_weak * 1e3, weak_p13, "+13.5 V", 1),
            Trace(t_weak * 1e3, np.clip(weak.real("vusbc_i#branch"), -0.5, 2.5), "source", 2),
        ),
        xmarks=((_PLUG * 1e3, "plug"),),
    )
    t_short = worst.real("time")
    shown = common.cut(t_short, _PLUG - 5e-6, _PLUG + 90e-6)
    micro = (t_short[shown] - _PLUG) * 1e6
    ring = Graph(
        name="peak",
        title="The first microseconds: 5.5 V source, cable of 0.08 ohm and 1.5 uH",
        xlabel="Time after the plug (us)",
        panels=(Panel("Voltage (V)", marks=((11.1, "suppressor from 11.1 V"),)), Panel("A")),
        traces=(
            Trace(micro, worst.real("vbus_c")[shown], "receptacle", 0),
            Trace(micro, worst.real("vin1")[shown], "behind the limiter", 0),
            Trace(micro, worst.real("vusbc_i#branch")[shown], "source current", 1),
            Trace(micro, worst.real("v.xd2.vz#branch")[shown], "suppressor", 1),
        ),
    )
    notes = (
        "The source is ideal behind its cable, with 100 ohm across the inductance of the "
        "cable. The cable values are assumptions; the peak at the receptacle depends on "
        "them more than on anything on the board, so three cables are shown.",
        "The ceramic capacitors lose capacitance with voltage as the curves of their "
        "manufacturer show; the 4.7 uF at the receptacle has 39 % left at 10 V. The "
        "suppressor is a typical part: breakdown 11.7 V at 1 mA.",
        "The boost converter is a load that takes 1.5 A from 2.7 V on the rail until its "
        "output is at 13.5 V: an assumption. Its inductor, diode and capacitors are the "
        "ones of the schematic. The largest source current after the first microseconds "
        "is that load on top of the charging of the rail.",
        "The limiter and the multiplexer are typical parts at 25 C; the supervisor holds "
        "the carrier off during these runs, so the loads of the other blocks are zero.",
        "5V_OK rises to about 0.5 V while the rail passes 0.8 V: below that supply the "
        "output of the supervisor is not defined (datasheet) and the model lets go of it. "
        "The regulators have no input voltage to work with at that moment.",
        "The charge above 100 mA is compared with the USB in-rush test although that test "
        "belongs to a USB 2.0 port; the specification says the same of the module input.",
        "The source of 0.9 A stands for a port that gives no more than USB 3 asks of it and "
        "limits without switching off: an assumption.",
    )
    return Outcome(tuple(figures), (whole, weak_graph, ring), notes)
