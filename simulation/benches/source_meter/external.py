"""A voltage from outside on the output of the source: a device above the set-point."""

from __future__ import annotations

import numpy as np

from benches.source_meter import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_SET = 0.8
"""Set-point of the source in every run."""

_CONNECT = 15e-3
"""Instant at which the device is connected, after the source has come to rest."""

_REST_START = 45e-3
_REST_STOP = 60e-3
"""The slow source stands at 5.0 V between these instants."""

_RAMP_STOP = 75e-3
"""The slow source reaches its highest voltage at this instant."""

_HELD = 5.0
"""Voltage of a device that holds the output up (section 4.9)."""

_HIGHEST = 6.5
"""Highest voltage of the slow source, beyond the 5.5 V of the user documentation."""

_OVP_LEAST = 5.5
"""Lowest over-voltage level of the converter (SLVS916I, page 6)."""

_PLUG_FARADS = 100e-6
_PLUG_VOLTS = 5.0
"""The charged capacitor of the hot-plug run (section 11)."""

_PLUG_LEADS = ((0.2e-6, 20e-3), (1.0e-6, 50e-3))
"""Inductance and resistance of the leads of that capacitor (assumptions)."""

_PLUG_STOP = _CONNECT + 3e-3

_REVERSE_LIMIT = -0.3
"""Rating of the IN pin relative to the output (LT3080 Rev. E, page 2)."""

_SET_LIMIT = 10e-3
"""Rating of the current of the SET pin (LT3080 Rev. E, page 2)."""


def _slow_deck(ctx: Context, ovp: float | None) -> str:
    """A source at the terminal that rises to 5.0 V, rests there and rises to 6.5 V."""
    overrides = {common.DAC: common.power_up_code(ctx, common.code_of(_SET))}
    if ovp is not None:
        overrides[common.CONVERTER] = common.part(ctx, common.CONVERTER, vovp=ovp)
    circuit = common.source(ctx, _SET, overrides=overrides, scales={"C41": common.SETTLE_FILTER})
    external = "\n".join(
        [
            "* a device that holds the terminal: a source behind 50 mohm, connected at",
            "* the voltage of the output, raised slowly, held at 5.0 V and raised again",
            f"Vext ext 0 PWL(0 {_SET:g} {_CONNECT:g} {_SET:g} {_REST_START:g} {_HELD:g} "
            f"{_REST_STOP:g} {_HELD:g} {_RAMP_STOP:g} {_HIGHEST:g})",
            f"Bext ext dut I = v(ext,dut)/0.05*0.5*(1 + tanh((time - {_CONNECT:g})/20u))",
        ]
    )
    return ctx.deck(
        "A voltage from outside on the output, raised slowly",
        circuit,
        common.power_up_rails(),
        common.power_up_controller(),
        common.dut(3, 0.0),
        external,
        control=[f"tran 2u {_RAMP_STOP:g} 0 20u"],
    )


def _plug_deck(ctx: Context, henries: float, ohms: float) -> str:
    """A capacitor charged to 5 V that is connected to the live output."""
    circuit = common.source(
        ctx,
        _SET,
        overrides={common.DAC: common.power_up_code(ctx, common.code_of(_SET))},
        scales={"C41": common.SETTLE_FILTER},
    )
    plug = "\n".join(
        [
            "* a charged capacitor behind its leads, connected within 0.1 us",
            f"Cplug plug_c 0 {_PLUG_FARADS:g} ic={_PLUG_VOLTS:g}",
            f"Rplug plug_c plug_r {ohms:g}",
            f"Lplug plug_r plug {henries:g}",
            f"Bplug plug dut I = v(plug,dut)/1m*0.5*(1 + tanh((time - {_CONNECT:g})/50n))",
            "Rkeep plug_c 0 1e9",
            f".ic v(plug_c)={_PLUG_VOLTS:g}",
        ]
    )
    return ctx.deck(
        "A charged capacitor connected to the live output",
        circuit,
        common.power_up_rails(),
        common.power_up_controller(),
        common.dut(3, 0.0),
        plug,
        control=[f"tran 20n {_PLUG_STOP:g} 0 2u"],
    )


def _held(run: RunResult, name: str) -> float:
    """A vector at the end of the rest of the slow source at 5.0 V."""
    return measure.value_at(run.real("time"), run.real(name), _REST_STOP - 0.5e-3)


def _pump_volts(run: RunResult) -> float:
    """The outside voltage at which the 5 V rail begins to take current back."""
    time = run.real("time")
    rail = -run.real("vp5#branch")
    instant = measure.first_crossing(time, rail, 0.0, rising=False, after=_CONNECT + 1e-3)
    return measure.value_at(time, run.real("ext"), instant)


@bench(
    "source_meter",
    "external",
    "A device above the set-point: current drawn from it, clamps, the 5 V rail",
    "sections 4.2 and 4.9 (external voltage on the source output), rules F-31 and F-33",
)
def external(ctx: Context) -> Outcome:
    """The source stands at 0.80 V and a device lifts its output from outside.

    In the first runs a source behind 50 mohm is connected at the terminal
    in range 3, raised slowly to 5.0 V, held there for 15 ms and raised to
    6.5 V. They give the current that the instrument takes from a device at
    rest at 5.0 V, the current through the clamp
    of the SET pin, the IN pin against the output, and the voltage at which
    the pre-regulator starts to return current to the 5 V rail, with the
    over-voltage level of the converter model and with the lowest one of
    its datasheet. In the last runs a capacitor of 100 uF charged to 5.0 V
    is connected to the live output at once, through leads of two lengths.
    """
    slow = ctx.run("slow", _slow_deck(ctx, None))
    least = ctx.run("slow-least", _slow_deck(ctx, _OVP_LEAST), keep=False)
    time = slow.real("time")
    drawn = slow.real("vext#branch") * -1.0
    headroom = slow.real("ldo_in") - slow.real("ldo_out")
    clamp = (slow.real("ldo_set") - slow.real("set_drv")) / 1000.0
    rail = -slow.real("vp5#branch")
    at_5v3 = measure.first_crossing(time, slow.real("ext"), 5.3, rising=True, after=_CONNECT)
    figures = [
        Figure(
            "drawn",
            "Current that the instrument takes from a device at rest at 5.0 V, set-point 0.80 V",
            _held(slow, "vext#branch") * -1.0,
            "A",
            expected=11e-3,
            low=9e-3,
            high=14e-3,
            source="section 4.9: about 11 mA, up to 14 mA warm (calculated)",
        ),
        Figure(
            "drawn_moved",
            "The same current while the device rises through 4.9 V with 0.14 V/ms",
            measure.value_at(
                time,
                drawn,
                measure.first_crossing(time, slow.real("ext"), 4.9, rising=True, after=_CONNECT),
            ),
            "A",
        ),
        Figure(
            "drawn_rest",
            "Movement of that current in the last 2 ms of the rest at 5.0 V",
            measure.peak_to_peak(time, drawn, _REST_STOP - 2.5e-3, _REST_STOP - 0.5e-3),
            "A",
            high=10e-6,
            source="limit of this bench: the current counts as at rest below 10 uA",
        ),
        Figure(
            "clamp",
            "In that state: current through the clamp of the SET pin into R60",
            measure.value_at(time, clamp, _REST_STOP - 0.5e-3),
            "A",
            high=_SET_LIMIT,
            source="LT3080 Rev. E, page 2: 10 mA at the most",
        ),
        Figure(
            "set_volts",
            "In that state: output above the SET pin",
            _held(slow, "ldo_out") - _held(slow, "ldo_set"),
            "V",
        ),
        Figure(
            "pre",
            "In that state: pre-regulator output",
            _held(slow, "v_pre"),
            "V",
            expected=common.law(_HELD),
        ),
        Figure(
            "in_pin",
            "Slow rise up to 5.3 V: lowest voltage of the IN pin relative to the output",
            measure.extremes(time, headroom, _CONNECT, at_5v3)[0],
            "V",
            low=_REVERSE_LIMIT,
            source="LT3080 Rev. E, page 2 (D-57); rule F-33 opens the output at 5.3 V",
        ),
        Figure(
            "returned",
            "Slow rise up to 5.3 V: most power returned to the 5 V rail",
            -measure.extremes(time, rail, _CONNECT, at_5v3)[0] * common.RAIL_5V,
            "W",
            high=0.25,
            source="section 4.2 and section 16: less than the instrument takes from the "
            "rail, for which 0.25 W is the condition",
        ),
        Figure(
            "pump",
            "Outside voltage at which the 5 V rail takes current back, model of the converter",
            _pump_volts(slow),
            "V",
        ),
        Figure(
            "pump_least",
            "The same with the lowest over-voltage level of the converter, 5.5 V",
            _pump_volts(least),
            "V",
            expected=5.7,
            low=5.3,
            source="rule F-33: above about 5.7 V (estimate); the output opens at 5.3 V",
        ),
    ]
    shown = time >= _CONNECT - 2e-3
    graphs = [
        Graph(
            name="slow",
            title="A voltage from outside on the output at a set-point of 0.80 V",
            xlabel="Voltage of the outside source (V)",
            panels=(
                Panel("Voltage (V)"),
                Panel("Current (mA)", marks=((0.0, "0"),)),
            ),
            traces=(
                Trace(slow.real("ext")[shown], slow.real("ldo_out")[shown], "regulator output", 0),
                Trace(
                    slow.real("ext")[shown], slow.real("v_pre")[shown], "pre-regulator output", 0
                ),
                Trace(slow.real("ext")[shown], drawn[shown] * 1e3, "taken from the device", 1),
                Trace(slow.real("ext")[shown], rail[shown] * 1e3, "taken from the 5 V rail", 1),
                Trace(slow.real("ext")[shown], clamp[shown] * 1e3, "clamp of the SET pin", 1, "--"),
            ),
            xmarks=((5.3, "rule F-33"),),
        )
    ]
    plug_traces: list[Trace] = []
    for henries, ohms in _PLUG_LEADS:
        tag = f"{henries * 1e9:g}nh"
        run = ctx.run(
            f"plug-{tag}", _plug_deck(ctx, henries, ohms), keep=henries == _PLUG_LEADS[0][0]
        )
        clock = run.real("time")
        pin = run.real("ldo_in") - run.real("ldo_out")
        below = (clock >= _CONNECT) & (pin < _REVERSE_LIMIT)
        seconds = float(np.sum(np.diff(clock)[below[:-1]])) if np.any(below) else 0.0
        surge = run.real("lplug#branch")
        text = f"leads of {henries * 1e6:g} uH and {ohms * 1e3:g} mohm"
        figures += [
            Figure(
                f"plug_in_{tag}",
                f"Charged 100 uF connected, {text}: lowest voltage of the IN pin relative "
                "to the output",
                measure.extremes(clock, pin, _CONNECT, _PLUG_STOP)[0],
                "V",
                expected=-0.63,
                low=_REVERSE_LIMIT,
                source="LT3080 Rev. E, page 2: not more than 0.3 V below the output; "
                "section 4.9: 0.32 V to 0.94 V below for 3 us to 21 us (simulated), which "
                "no part covers",
            ),
            Figure(
                f"plug_time_{tag}",
                f"Charged 100 uF connected, {text}: time the IN pin spends more than 0.3 V "
                "below the output",
                seconds,
                "s",
                expected=12e-6,
            ),
            Figure(
                f"plug_surge_{tag}",
                f"Charged 100 uF connected, {text}: highest current into the terminal",
                float(np.max(np.abs(surge))),
                "A",
            ),
            Figure(
                f"plug_output_{tag}",
                f"Charged 100 uF connected, {text}: highest regulator output",
                measure.extremes(clock, run.real("ldo_out"), _CONNECT, _PLUG_STOP)[1],
                "V",
            ),
        ]
        window = (clock >= _CONNECT - 5e-6) & (clock <= _CONNECT + 150e-6)
        axis = (clock[window] - _CONNECT) * 1e6
        plug_traces += [
            Trace(axis, run.real("ldo_out")[window], f"regulator output, {text}", 0),
            Trace(axis, run.real("ldo_in")[window], f"IN pin, {text}", 0, "--"),
            Trace(axis, pin[window], text, 1),
            Trace(axis, np.abs(surge[window]), text, 2),
        ]
    graphs.append(
        Graph(
            name="plug",
            title="A capacitor of 100 uF at 5.0 V connected to the output at 0.80 V",
            xlabel="Time after the connection (us)",
            panels=(
                Panel("Voltage (V)"),
                Panel("IN pin above the output (V)", marks=((_REVERSE_LIMIT, "rating -0.3 V"),)),
                Panel("Current into the terminal (A)"),
            ),
            traces=tuple(plug_traces),
        )
    )
    notes = (
        "Nothing reacts in these runs: rules F-31 and F-33 are firmware, and the output "
        "switch, the range logic and the over-current trip belong to other blocks. The "
        "path from the terminal to the regulator output is three resistors, 145 mohm in "
        "range 3, without the inductance of the board.",
        "At rest at 5.0 V the device feeds the minimum load R69, 6.9 mA, and the clamp "
        "between OUT and SET of the regulator, which carries 3.5 mA into R60, less the "
        "0.3 mA that the regulator delivers itself. While the device rises it also "
        "charges the capacitors at the output, 28 uF at the capacitance that these "
        "runs take at 0.8 V: 3.5 mA more at 0.14 V/ms.",
        "The voltage at which the converter starts to return current depends on its "
        "over-voltage level, which the datasheet gives as 5.5 V to 7 V: the model has "
        "6.2 V, and one run takes 5.5 V. The rail is an ideal source, so it shows the "
        "current and not what the rail does with it.",
        "The hot-plug runs fail the rating of the IN pin, as section 4.9 says they "
        "would: the specification states that no part covers a charged device "
        "connected to the live output. The figures depend on the leads of the "
        "capacitor, which are assumptions, on the diode model of D11 and on the "
        "capacitors of the filter, which have no series inductance here.",
        "The diode D11 is the typical model at 27 C; the regulator model has no "
        "junction from the output to the IN pin other than its pass transistor, whose "
        "reverse behavior is an assumption.",
    )
    return Outcome(tuple(figures), tuple(graphs), notes)
