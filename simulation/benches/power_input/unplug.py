"""The USB-C cable is pulled: with the cable of the module in, and without it."""

from __future__ import annotations

import numpy as np

from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench

_PLUG = 0.1e-3
"""Instant at which the sources are connected."""

_PULL = 7.0e-3
"""Instant at which the USB-C contact opens: the carrier runs at idle."""

_END_BOTH = 0.14
"""End of the run with the cable of the module in."""

_END_ALONE = 0.75
"""End of the run without it."""

_END_LOADED = _PULL + 1.5e-3
"""End of the run in which the cable is pulled at full output."""

_LOAD_WATTS = 6.3
"""Power of the pre-regulator at full output (the estimate of section 4.1)."""

_REGULATOR_OVER = 0.3
"""Highest output of a 3.3 V regulator above its input (LP5907 datasheet,
SNVS798Q page 4, absolute maximum)."""

_MUX_PULSE_AMPS = 4.0
"""Largest pulse current of the multiplexer (TPS2116 datasheet, page 4)."""


def _loaded_deck(ctx: Context) -> str:
    """The carrier delivers its full output from USB-C alone when the cable is pulled."""
    circuit = common.circuit(
        ctx, common.carrier_refs(ctx.netlist), params={"U6": common.FAST_SUPERVISOR}
    )
    stimulus = (
        common.usb_c_source(5.0, _PLUG, unplug_at=_PULL)
        + common.boost_start()
        + common.idle_loads()
        + "* the pre-regulator as a load of constant power, shed with 5V_OK\n"
        + common.power_load("smu", "rail", _LOAD_WATTS, common.RUNNING_AT - 0.3e-3, _END_LOADED)
    )
    return ctx.deck(
        "USB-C pulled at full output, without the cable of the module",
        circuit,
        stimulus,
        control=[common.transient(0.5e-6, _END_LOADED)],
    )


def _deck(ctx: Context, module_in: bool) -> str:
    """The idle carrier runs from USB-C, which is pulled at 7 ms."""
    circuit = common.circuit(
        ctx, common.carrier_refs(ctx.netlist), params={"U6": common.FAST_SUPERVISOR}
    )
    stimulus = common.usb_c_source(5.0, _PLUG, unplug_at=_PULL)
    if module_in:
        stimulus += common.module_port(5.0, _PLUG, switch_amps=None)
        title = "USB-C pulled with the cable of the module in"
        control = [
            "save all @b.xu5.b1[i] @b.xu5.b2[i] @rjp1[i]",
            common.transient(5e-6, _END_BOTH),
        ]
    else:
        title = "USB-C pulled without the cable of the module"
        control = [common.transient(20e-6, _END_ALONE)]
    stimulus += common.boost_start() + common.idle_loads()
    return ctx.deck(title, circuit, stimulus, control=control)


@bench(
    "power_input",
    "unplug",
    "The USB-C cable is pulled: the rail falls, the multiplexer changes to the module input",
    "section 4.1 (when a cable is pulled or plugged), section 16",
)
def unplug(ctx: Context) -> Outcome:
    """The idle carrier runs from USB-C when that cable is pulled.

    In the first run the cable of the module is in. The rail falls with the
    load, the supervisor sheds the carrier, and the rail and the output of
    the USB-C limiter go on falling together until the priority input of the
    multiplexer has passed its threshold. The multiplexer then closes the
    module input onto a rail of about 2.4 V without soft start. In the
    second run the cable of the module is not in, and the question is how
    long the pins of the receptacle keep a voltage. In the third run the
    cable is pulled while the source meter takes its full power, again
    without the cable of the module: the rail then falls faster than the
    3.3 V rails are discharged.
    """
    runs = common.run_all(
        ctx,
        {"both": _deck(ctx, True), "alone": _deck(ctx, False), "loaded": _loaded_deck(ctx)},
        keep=("both", "alone", "loaded"),
    )
    both, alone, loaded = runs["both"], runs["alone"], runs["loaded"]
    t_load = loaded.real("time")
    l_rail = loaded.real("rail")
    falling = common.cut(t_load, _PULL, _END_LOADED)
    l_trip = measure.first_crossing(t_load, loaded.real("ok5v"), 1.5, rising=False, after=_PULL)
    l_pass = measure.first_crossing(t_load, l_rail, common.SUPERVISOR_TYP[0], False, after=_PULL)
    time = both.real("time")
    rail, vin1 = both.real("rail"), both.real("vin1")
    two = both.real("@b.xu5.b2[i]")
    port = both.real("@rjp1[i]")
    tripped = measure.first_crossing(time, both.real("ok5v"), 1.5, rising=False, after=_PULL)
    changed = measure.first_crossing(time, two, 0.05, rising=True, after=_PULL)
    pulse = common.cut(time, changed - 5e-6, changed + 0.5e-3)
    pulse_ends = changed + 0.5e-3
    back = measure.first_crossing(time, rail, 4.5, rising=True, after=changed)
    t_alone = alone.real("time")
    vbus_alone = alone.real("vbus_c")
    figures = (
        Figure(
            "trip_after",
            "5V_OK low after the pull, idle carrier",
            tripped - _PULL,
            "s",
        ),
        Figure(
            "rail_at_trip",
            "Rail when 5V_OK falls",
            measure.value_at(time, rail, tripped),
            "V",
            low=3.7,
            high=common.SUPERVISOR_FALL[1],
            source="section 3: 5V_OK falls at 3.83 V to 4.00 V; the rail goes on falling "
            "while the supervisor reacts",
        ),
        Figure(
            "change_after",
            "The multiplexer closes the module input after the pull",
            changed - _PULL,
            "s",
            expected=0.2,
            source="section 4.1: up to about 0.2 s later at idle (estimate)",
        ),
        Figure(
            "input1_at_change",
            "Output of the USB-C limiter when the multiplexer changes",
            measure.value_at(time, vin1, changed - 20e-6),
            "V",
            expected=2.37,
            low=2.15,
            high=2.59,
            source="section 4.1: 2.15 V to 2.59 V (calculated)",
        ),
        Figure(
            "rail_at_change",
            "Rail when the multiplexer changes",
            measure.value_at(time, rail, changed - 20e-6),
            "V",
            low=1.0,
            source="section 4.1: without soft start, because the rail is above 1 V",
        ),
        Figure(
            "pulse_port",
            "Largest current from the port of the module in the recharge",
            float(np.max(port[pulse])),
            "A",
        ),
        Figure(
            "pulse_port_time",
            "Time the port current is above 0.85 A in the recharge",
            common.time_above(time, port, common.LIMIT_MODULE[2], changed - 5e-6, pulse_ends),
            "s",
        ),
        Figure(
            "pulse_mux",
            "Largest current through the multiplexer in the recharge",
            float(np.max(two[pulse])),
            "A",
            high=_MUX_PULSE_AMPS,
            source="TPS2116 datasheet, page 4: 4 A for a pulse; the specification says "
            "several amperes for some microseconds",
        ),
        Figure(
            "pulse_mux_time",
            "Time the multiplexer carries more than 4 A in the recharge",
            common.time_above(time, two, _MUX_PULSE_AMPS, changed - 5e-6, pulse_ends),
            "s",
        ),
        Figure(
            "recharged",
            "Rail back at 4.5 V after the change",
            back - changed,
            "s",
        ),
        Figure(
            "input2_low",
            "Lowest level of the module input of the multiplexer in the recharge",
            float(np.min(both.real("vin2")[pulse])),
            "V",
        ),
        Figure(
            "receptacle_dead",
            "Without the cable of the module: receptacle below 0.8 V after the pull",
            measure.first_crossing(t_alone, vbus_alone, 0.8, rising=False, after=_PULL) - _PULL,
            "s",
            expected=0.4,
            source="section 4.1: about 0.4 s after the unplug (estimate)",
        ),
        Figure(
            "limiter_out_over_in",
            "Without the cable of the module: largest output of the USB-C limiter above its input",
            float(
                np.max((alone.real("vin1") - vbus_alone)[common.cut(t_alone, _PULL, _END_ALONE)])
            ),
            "V",
            high=0.3,
            source="section 4.1: within 0.3 V of the input, the rating of the part",
        ),
        Figure(
            "loaded_fall",
            "Pulled at full output: fall of the rail until the supervisor trips",
            (measure.value_at(t_load, l_rail, _PULL + 5e-6) - common.SUPERVISOR_TYP[0])
            / (l_pass - _PULL - 5e-6),
            "V/s",
        ),
        Figure(
            "loaded_trip",
            "Pulled at full output: 5V_OK low after the rail has passed 3.91 V",
            l_trip - l_pass,
            "s",
            high=0.1e-3,
            source="section 4.1: the pre-regulator is off within 0.1 ms (estimate)",
        ),
        Figure(
            "loaded_rail_low",
            "Pulled at full output: level of the rail 0.2 ms after 5V_OK has fallen",
            measure.value_at(t_load, l_rail, l_trip + 0.2e-3),
            "V",
        ),
        Figure(
            "loaded_v3a_over",
            "Pulled at full output: highest level of 3V3_A above the rail",
            float(np.max((loaded.real("v3a") - l_rail)[falling])),
            "V",
            high=_REGULATOR_OVER,
            source="LP5907 datasheet, page 4: output at most 0.3 V above the input; the "
            "specification states no figure",
        ),
        Figure(
            "loaded_v3c_over",
            "Pulled at full output: highest level of 3V3_C above the rail",
            float(np.max((loaded.real("v3c") - l_rail)[falling])),
            "V",
            high=_REGULATOR_OVER,
            source="LP5907 datasheet, page 4: output at most 0.3 V above the input; the "
            "specification states no figure",
        ),
        Figure(
            "loaded_vsys",
            "Pulled at full output: VSYS of the module 1 ms after the pull",
            measure.value_at(t_load, loaded.real("vsys"), _PULL + 1e-3),
            "V",
        ),
    )
    shown = common.cut(time, _PULL - 1e-3, _END_BOTH)
    milli = time[shown] * 1e3
    whole = Graph(
        name="decay",
        title="USB-C pulled at 7 ms with the cable of the module in",
        xlabel="Time (ms)",
        panels=(Panel("Voltage (V)", marks=((2.37, "priority threshold 2.37 V"),)),),
        traces=(
            Trace(milli, both.real("vbus_c")[shown], "USB-C receptacle", 0),
            Trace(milli, vin1[shown], "input 1 (USB-C limiter)", 0),
            Trace(milli, rail[shown], "5 V rail", 0),
            Trace(milli, both.real("vin2")[shown], "input 2 (module)", 0, "--"),
            Trace(milli, both.real("ok5v")[shown], "5V_OK", 0, ":"),
        ),
        xmarks=((_PULL * 1e3, "pull"),),
    )
    near = common.cut(time, changed - 20e-6, changed + 0.4e-3)
    micro = (time[near] - changed) * 1e6
    recharge = Graph(
        name="recharge",
        title="The multiplexer closes the module input onto the fallen rail",
        xlabel="Time after the change (us)",
        panels=(Panel("Voltage (V)"), Panel("Current (A)")),
        traces=(
            Trace(micro, both.real("vin2")[near], "input 2 (module)", 0),
            Trace(micro, rail[near], "5 V rail", 0),
            Trace(micro, both.real("pico_5v")[near], "input of the module limiter", 0, "--"),
            Trace(micro, np.clip(two[near], -1, 12), "through the multiplexer", 1),
            Trace(micro, np.clip(port[near], -1, 12), "from the port of the module", 1),
        ),
    )
    notes = (
        "After the supervisor has shed the carrier, the rail falls with what is left on "
        "it: the 10 kohm load, the dividers, the supply current of the limiter and what "
        "the boost converter needs to hold its output. The boost converter here is a load "
        "that only refills its output; its own supply current (2 mA while it switches, "
        "datasheet) is not in the run, so the real decay is faster than this one.",
        "The pulse of the recharge is the charge of the 1 uF at the module input and what "
        "the limiter lets through before it acts. Its peak through the multiplexer is "
        "set by ideal capacitors without series inductance and by a limiter model without "
        "saturation current: an upper bound.",
        "The supervisor has its release delay shortened to 1 ms; after the change it "
        "releases the carrier again 1 ms after the rail is back, not 0.3 s.",
        "Sources and cables as in the other benches; the port of the module is stiff.",
    )
    return Outcome(figures, (whole, recharge), notes)
