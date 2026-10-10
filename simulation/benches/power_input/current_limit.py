"""The current limits of the two inputs, and a short circuit of the 5 V rail."""

from __future__ import annotations

import numpy as np

from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_PLUG = 0.1e-3
"""Instant at which the source is connected."""

_RAMP_START = common.RUNNING_AT
"""Start of the load ramp: the carrier has been released and runs at idle."""

_RAMP_TIME = 5e-3
"""Duration of the load ramp."""

_END = 13e-3
"""End of the ramp runs."""

_SHORT_AT = common.RUNNING_AT
"""Instant of the short circuit of the rail."""

_SHORT_END = common.RUNNING_AT + 0.2e-3
"""End of the short-circuit runs."""

_SHORT_OHMS = 0.01
"""Resistance of the short circuit: a probe or a screwdriver on the rail."""

_MUX_PULSE_AMPS = 4.0
"""Largest pulse current of the multiplexer: 4 A for at most 1 ms at a duty
cycle of 2 % (TPS2116 datasheet, SLVSFG1A page 4, absolute maximum)."""

_REGULATOR_OVER = 0.3
"""Highest output of a 3.3 V regulator above its input (LP5907 datasheet,
SNVS798Q page 4, absolute maximum)."""

_SAVE = "save all @rjp1[i] @b.xu5.b1[i] @b.xu5.b2[i]"
"""The current of the jumper JP1, which is the current of the limiter of the
module input with its divider, and the currents of the two channels of the
multiplexer."""


def _source(usb_c: bool) -> str:
    """A stiff 5 V source on one of the two inputs."""
    if usb_c:
        return common.usb_c_source(5.0, _PLUG)
    return common.module_port(5.0, _PLUG, switch_amps=None)


def _ramp_deck(ctx: Context, usb_c: bool, top: float) -> str:
    """One input supplies; a load on the rail rises until the limiter limits."""
    circuit = common.circuit(
        ctx, common.carrier_refs(ctx.netlist), params={"U6": common.FAST_SUPERVISOR}
    )
    slope = top / _RAMP_TIME
    stimulus = (
        _source(usb_c)
        + common.boost_start()
        + common.idle_loads()
        + "* a load on the rail that rises slowly and takes nothing from a rail near zero\n"
        + f"Bramp rail 0 I = {slope:g}*pwrin_pos(time - {_RAMP_START:g}, 1u)"
        + "*pwrin_hi((v(rail) - 0.15)/0.05)\n"
    )
    name = "USB-C" if usb_c else "module"
    return ctx.deck(
        f"Current limit of the {name} input: a load ramp on the rail",
        circuit,
        stimulus,
        control=[_SAVE, common.transient(1e-6, _END)],
    )


def _short_deck(ctx: Context, usb_c: bool) -> str:
    """One input supplies the idle carrier; the rail is shorted to ground."""
    circuit = common.circuit(
        ctx, common.carrier_refs(ctx.netlist), params={"U6": common.FAST_SUPERVISOR}
    )
    stimulus = (
        _source(usb_c)
        + common.boost_start()
        + common.idle_loads()
        + "* the short circuit: 10 mohm from the rail to ground within 0.2 us\n"
        + f"Bshort rail 0 I = v(rail)*{1 / _SHORT_OHMS:g}*pwrin_hi((time - {_SHORT_AT:g})/50n)\n"
    )
    name = "USB-C" if usb_c else "module"
    control = [_SAVE, common.transient(1e-6, _SHORT_END, _SHORT_AT - 20e-6)]
    return ctx.deck(
        f"Short circuit of the 5 V rail, {name} input supplies", circuit, stimulus, control=control
    )


def _limiter_amps(result: RunResult, usb_c: bool) -> np.ndarray:
    """The current into the limiter of the input in use."""
    if usb_c:
        return result.real("vusbc_i#branch")
    return result.real("@rjp1[i]")


def _plateau(result: RunResult, usb_c: bool) -> tuple[float, float]:
    """The limit, and the mean current after the rail has given way."""
    time = result.real("time")
    rail = result.real("rail")
    amps = _limiter_amps(result, usb_c)
    falls = measure.first_crossing(time, rail, 3.5, rising=False, after=_RAMP_START)
    low = measure.first_crossing(time, rail, 1.5, rising=False, after=falls)
    limit = measure.mean(time, amps, falls, low)
    after = measure.mean(time, amps, low + 0.2e-3, _END)
    return limit, after


@bench(
    "power_input",
    "current-limit",
    "The current limits of the two inputs and a short circuit of the 5 V rail",
    "section 2 (R-14), section 4.1 (limiters, power budget, bring-up), section 3 (power tree)",
)
def current_limit(ctx: Context) -> Outcome:
    """Each input supplies the carrier alone under a rising load; then the rail is shorted.

    The carrier runs at idle on a stiff 5 V source. A load on the 5 V rail
    rises within 5 ms to more than the limiter of that input gives, so the
    rail gives way and ends near ground, where the limiter folds its limit
    back. The current into the limiter while the rail falls is the limit
    that the resistor at its ILM pin sets. In two more runs the rail of the
    idle carrier is shorted to ground with 10 mohm.
    """
    decks = {
        "ramp-module": _ramp_deck(ctx, False, 1.6),
        "ramp-usbc": _ramp_deck(ctx, True, 3.6),
        "short-usbc": _short_deck(ctx, True),
        "short-module": _short_deck(ctx, False),
    }
    runs = common.run_all(ctx, decks, keep=("ramp-module", "ramp-usbc", "short-usbc"))
    figures: list[Figure] = []
    ramps = {}
    for usb_c, name, nominal in (
        (False, "module", common.LIMIT_MODULE),
        (True, "usbc", common.LIMIT_USB_C),
    ):
        run = runs[f"ramp-{name}"]
        ramps[name] = run
        limit, mean_after = _plateau(run, usb_c)
        label = "USB-C input" if usb_c else "Module input"
        figures += [
            Figure(
                f"limit_{name}",
                f"{label}: current into the limiter while it limits",
                limit,
                "A",
                expected=nominal[0],
                low=nominal[1],
                high=nominal[2],
                source="section 4.1: limit with the tolerances (calculated)",
            ),
            Figure(
                f"mean_after_{name}",
                f"{label}: mean current into the limiter after the rail has collapsed",
                mean_after,
                "A",
            ),
        ]
    usbc = ramps["usbc"]
    t_c = usbc.real("time")
    at_one = measure.first_crossing(t_c, usbc.real("vusbc_i#branch"), 1.0, True, after=_RAMP_START)
    figures.append(
        Figure(
            "monitor_gain",
            "USB-C input: voltage at TP3 per ampere, at 1 A",
            measure.value_at(t_c, usbc.real("imon"), at_one) / 1.0,
            "V/A",
            expected=0.297,
            low=0.297 * 0.95,
            high=0.297 * 1.05,
            source="section 4.1: 0.297 V per ampere (calculated from the datasheet gain)",
        )
    )
    shorts = {}
    for usb_c, name in ((True, "usbc"), (False, "module")):
        run = runs[f"short-{name}"]
        shorts[name] = run
        time = run.real("time")
        channel = run.real("@b.xu5.b1[i]" if usb_c else "@b.xu5.b2[i]")
        source = _limiter_amps(run, usb_c)
        after = common.cut(time, _SHORT_AT, _SHORT_END)
        limit_amps = common.LIMIT_USB_C[0] if usb_c else common.LIMIT_MODULE[0]
        peak_at = float(time[after][np.argmax(source[after])])
        try:
            limited_after = (
                measure.first_crossing(time, source, limit_amps, rising=False, after=peak_at)
                - _SHORT_AT
            )
        except measure.MeasureError:
            limited_after = float("nan")
        label = "USB-C input" if usb_c else "Module input"
        figures += [
            Figure(
                f"short_mux_peak_{name}",
                f"Short circuit, {label}: largest current through the multiplexer",
                float(np.max(channel[after])),
                "A",
                high=_MUX_PULSE_AMPS,
                source="TPS2116 datasheet, page 4: 4 A for a pulse; the specification "
                "states no figure for a short circuit of the rail",
            ),
            Figure(
                f"short_mux_time_{name}",
                f"Short circuit, {label}: time the multiplexer carries more than 4 A",
                common.time_above(time, channel, _MUX_PULSE_AMPS, _SHORT_AT, _SHORT_END),
                "s",
            ),
            Figure(
                f"short_charge_{name}",
                f"Short circuit, {label}: charge through the multiplexer in the first 20 us",
                common.charge_above(time, channel, 0.0, _SHORT_AT, _SHORT_AT + 20e-6),
                "C",
            ),
            Figure(
                f"short_source_peak_{name}",
                f"Short circuit, {label}: largest current from the source",
                float(np.max(source[after])),
                "A",
            ),
            Figure(
                f"short_limited_{name}",
                f"Short circuit, {label}: source current back at the limit after",
                limited_after,
                "s",
            ),
            Figure(
                f"short_mean_{name}",
                f"Short circuit, {label}: mean source current from 20 us to 200 us",
                measure.mean(time, source, _SHORT_AT + 20e-6, _SHORT_END),
                "A",
                high=common.LIMIT_USB_C[2] if usb_c else common.LIMIT_MODULE[2],
                source="section 4.1: the limiters regulate the current in an overload",
            ),
            Figure(
                f"short_v3a_over_{name}",
                f"Short circuit, {label}: highest level of 3V3_A above the rail",
                float(np.max((run.real("v3a") - run.real("rail"))[after])),
                "V",
                high=_REGULATOR_OVER,
                source="LP5907 datasheet, page 4: output at most 0.3 V above the input; the "
                "specification states no figure",
            ),
        ]
    module = ramps["module"]
    t_m = module.real("time")
    ramp_graph = Graph(
        name="ramp",
        title="A load on the rail that rises until the limiter of the input limits",
        xlabel="Time (ms)",
        panels=(Panel("5 V rail (V)"), Panel("Current into the limiter (A)")),
        traces=(
            Trace(t_m * 1e3, module.real("rail"), "module input", 0),
            Trace(t_c * 1e3, usbc.real("rail"), "USB-C input", 0),
            Trace(t_m * 1e3, _limiter_amps(module, False), "module input", 1),
            Trace(t_c * 1e3, _limiter_amps(usbc, True), "USB-C input", 1),
        ),
        xmarks=((_RAMP_START * 1e3, "load ramp starts"),),
    )
    short = shorts["usbc"]
    t_s = short.real("time")
    shown = common.cut(t_s, _SHORT_AT - 5e-6, _SHORT_AT + 150e-6)
    micro = (t_s[shown] - _SHORT_AT) * 1e6
    short_graph = Graph(
        name="short",
        title="The 5 V rail shorted with 10 mohm while the USB-C input supplies",
        xlabel="Time after the short circuit (us)",
        panels=(
            Panel("Voltage (V)"),
            Panel("Current (A)", marks=((_MUX_PULSE_AMPS, "multiplexer: 4 A pulse rating"),)),
        ),
        traces=(
            Trace(micro, short.real("rail")[shown], "5 V rail", 0),
            Trace(micro, short.real("vin1")[shown], "input 1 of the multiplexer", 0),
            Trace(micro, short.real("damper")[shown], "damper capacitors", 0),
            Trace(micro, short.real("vbus_c")[shown], "receptacle", 0, "--"),
            Trace(micro, short.real("@b.xu5.b1[i]")[shown], "through the multiplexer", 1),
            Trace(micro, short.real("vusbc_i#branch")[shown], "from the source", 1),
        ),
    )
    notes = (
        "The sources are stiff: 5.0 V behind 0.15 ohm and 0.5 uH on USB-C, behind 0.25 ohm "
        "and 0.8 uH on the module input. The supervisor has its delay shortened to 1 ms "
        "in these runs, which changes nothing in the figures.",
        "The limit is that of typical parts: the model follows the equation of the "
        "datasheet with the resistor of the schematic. The band of the specification "
        "comes from the tolerances of the datasheet, which the run does not vary.",
        "The fold-back current of the module input (0.34 A) is an interpolation between "
        "the two resistor values that the datasheet shows, and so an assumption.",
        "In a short circuit the damper capacitors (2 x 22 uF behind 0.33 ohm) and the 1 uF "
        "at the input discharge through the multiplexer, which has no current limit of "
        "its own. The peak of that current is set by 0.33 ohm, the on-resistance and the "
        "short itself, not by a model limit.",
        "The peak of the source current in a short circuit is an upper bound: the model of "
        "the limiter has no saturation current, and the datasheet gives none.",
        "The multiplexer model opens its channel when its input has fallen below 1.4 V, "
        "which a short circuit of the rail does within a microsecond, and starts again "
        "with its soft start: the levels are assumptions for the reset that the datasheet "
        "describes without figures. A part that stays on carries the discharge of the "
        "damper, 13 A at first with a time constant of 11 us (calculated from 0.33 ohm, "
        "the on-resistance and 30 uF), and then the current of the limiter.",
        "With the rail at ground the 3.3 V rails stand above their input, by the forward "
        "voltage of a body diode that the regulator model assumes, until the 2.4 uF and "
        "3.8 uF on them are empty.",
        "The thermal shutdown of the limiters and its retry after 95 ms are not modelled: "
        "a sustained overload ends there, not at the fold-back current.",
    )
    return Outcome(tuple(figures), (ramp_graph, short_graph), notes)
