"""The levels at which the input stage switches, and what the monitor reads."""

from __future__ import annotations

from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_UP_END = 0.10
"""End of the rise of the USB-C voltage from 0 V to 5 V."""

_HOLD_END = 0.15
"""End of the hold at 5 V."""

_DOWN_END = 0.25
"""End of the fall back to 0 V."""

_END = 0.29
"""End of the runs."""

_CC_STEP = 0.02
"""Time each pull-up of the CC run stays connected."""

_CC_CASES = (
    ("default, nominal", 56e3, 5.0),
    ("default, highest", 44.8e3, 5.5),
    ("default, lowest", 67.2e3, 4.75),
    ("1.5 A, nominal", 22e3, 5.0),
    ("1.5 A, highest", 20.9e3, 5.5),
    ("1.5 A, lowest", 23.1e3, 4.75),
    ("3 A, nominal", 10e3, 5.0),
    ("3 A, highest", 9.5e3, 5.5),
    ("3 A, lowest", 10.5e3, 4.75),
)
"""Pull-up resistors of a USB-C source to its VBUS, with their tolerances and
the range of VBUS (USB Type-C specification, release 2.0, table 4-24: 56 kohm
20 %, 22 kohm 5 %, 10 kohm 5 %, to 4.75 V to 5.5 V)."""

_CC_WINDOWS = {
    "default": (None, 0.61),
    "1.5 A": (0.70, 1.16),
    "3 A": (1.31, 2.04),
}
"""Windows of the CC voltage by which firmware tells the sources apart
(specification, section 4.1 and rule F-14)."""


def _ramp_deck(ctx: Context, module_in: bool) -> str:
    """The USB-C voltage rises slowly to 5 V and falls again; the module input is on or off."""
    circuit = common.circuit(
        ctx, common.carrier_refs(ctx.netlist), params={"U6": common.FAST_SUPERVISOR}
    )
    stimulus = (
        "* a supply without cable at the receptacle that rises and falls slowly\n"
        f"Vconn conn_s 0 PWL(0 0 {_UP_END:g} 5 {_HOLD_END:g} 5 {_DOWN_END:g} 0)\n"
        "Vconn_i conn_s conn_o 0\n"
        "Rconn conn_o vbus_c 1m\n"
    )
    if module_in:
        stimulus += common.ideal_supply("mod", "pico_vbus", 5.0, 1e-3)
    stimulus += common.boost_start() + common.idle_loads()
    name = "with" if module_in else "without"
    return ctx.deck(
        f"Slow rise and fall of the USB-C voltage, {name} the module input",
        circuit,
        stimulus,
        control=[common.transient(10e-6, _END)],
    )


def _cc_deck(ctx: Context) -> str:
    """The pull-ups of the three kinds of source, one after the other, on CC1."""
    refs = ("R7", "R11", "U2", "R144", "R145", "C106", "C107")
    circuit = common.circuit(ctx, refs)
    conductance = " + ".join(
        f"{1 / ohms:g}*pwrin_hi((time - {index * _CC_STEP + 1e-3:g})/10u)"
        f"*pwrin_hi(({(index + 1) * _CC_STEP + 1e-3:g} - time)/10u)"
        for index, (_, ohms, _) in enumerate(_CC_CASES)
    )
    points = " ".join(
        f"{index * _CC_STEP + 1e-3:g} {volts:g} {(index + 1) * _CC_STEP + 0.99e-3:g} {volts:g}"
        for index, (_, _, volts) in enumerate(_CC_CASES)
    )
    stimulus = (
        "* VBUS of the source and its pull-up to CC1 (not in the schematic)\n"
        f"Vsrc src 0 PWL(0 0 {points})\n"
        f"Bpull src cc1 I = v(src,cc1)*({conductance})\n"
        "Rcc2 cc2 0 1e9\n"
    )
    stop = len(_CC_CASES) * _CC_STEP + 2e-3
    return ctx.deck(
        "CC1 with the pull-ups of the three kinds of USB-C source",
        circuit,
        stimulus,
        control=[common.transient(20e-6, stop)],
    )


def _level_at(run: RunResult, name: str, instant: float) -> float:
    """The receptacle voltage at an instant of a ramp run."""
    return measure.value_at(run.real("time"), run.real(name), instant)


@bench(
    "power_input",
    "thresholds",
    "The levels at which the limiter and the multiplexer switch, and what the monitor reads",
    "section 4.1 (input stage, thresholds of the 5 V rail, what firmware reads), "
    "rules F-11, F-13 and F-14",
)
def thresholds(ctx: Context) -> Outcome:
    """The voltage at the USB-C receptacle rises to 5 V within 0.1 s and falls again.

    The dVdt pin of the limiter shows when the limiter is on, the status
    output when the multiplexer has left USB-C. The run is done without and
    with a supply on the module input; with it, the monitor channel of the
    rail shows both of its scales. A third run puts the pull-ups of the
    three kinds of USB-C source on CC1, at the ends of their tolerance.
    """
    runs = common.run_all(
        ctx,
        {"alone": _ramp_deck(ctx, False), "both": _ramp_deck(ctx, True), "cc": _cc_deck(ctx)},
        keep=("both", "cc"),
    )
    alone, both = runs["alone"], runs["both"]
    time = alone.real("time")
    dvdt = alone.real("dvdt_c")
    turned_on = measure.first_crossing(time, dvdt, 0.05, rising=True)
    turned_off = measure.first_crossing(time, dvdt, 0.05, rising=False, after=_HOLD_END)
    t_both = both.real("time")
    status = both.real("src_st")
    left = measure.first_crossing(t_both, status, 0.3, rising=False, after=_HOLD_END)
    on_usbc = _HOLD_END - 2e-3
    on_module = _END - 2e-3
    figures = [
        Figure(
            "limiter_on",
            "Receptacle voltage at which the limiter turns on",
            _level_at(alone, "vbus_c", turned_on),
            "V",
            expected=3.005,
            low=2.92,
            high=3.09,
            source="section 4.1: on at 2.92 V to 3.09 V (calculated)",
        ),
        Figure(
            "limiter_off",
            "Receptacle voltage at which the limiter turns off",
            _level_at(alone, "vbus_c", turned_off),
            "V",
            expected=2.755,
            low=2.67,
            high=2.87,
            source="section 4.1: off at 2.67 V to 2.87 V (calculated)",
        ),
        Figure(
            "mux_leaves",
            "Input 1 of the multiplexer when it leaves USB-C for the module input",
            _level_at(both, "vin1", left),
            "V",
            expected=2.37,
            low=2.15,
            high=2.59,
            source="section 4.1: 2.15 V to 2.59 V (calculated)",
        ),
        Figure(
            "order",
            "Receptacle voltage at which the multiplexer leaves, less the one at which "
            "the limiter turns off",
            _level_at(both, "vbus_c", left) - _level_at(alone, "vbus_c", turned_off),
            "V",
            high=0.0,
            source="section 4.1: the multiplexer threshold is below every other threshold",
        ),
        Figure(
            "monitor_usbc",
            "Monitor channel of the rail as a share of the rail, USB-C supplies",
            _level_at(both, "mon_5v", on_usbc) / _level_at(both, "rail", on_usbc),
            "",
            expected=0.4545,
            low=0.4545 * 0.98,
            high=0.4545 * 1.02,
            source="section 4.1: 0.4545 x the rail (calculated; 1 % resistors)",
        ),
        Figure(
            "monitor_module",
            "Monitor channel of the rail as a share of the rail, the module input supplies",
            _level_at(both, "mon_5v", on_module) / _level_at(both, "rail", on_module),
            "",
            expected=0.2524,
            low=0.2524 * 0.98,
            high=0.2524 * 1.02,
            source="section 4.1: 0.2524 x the rail (calculated; 1 % resistors)",
        ),
        Figure(
            "monitor_usbc_volts",
            "Monitor channel of the rail, USB-C supplies",
            _level_at(both, "mon_5v", on_usbc),
            "V",
            low=1.67,
            source="rule F-11: above 1.67 V means USB-C",
        ),
        Figure(
            "monitor_module_volts",
            "Monitor channel of the rail, the module input supplies",
            _level_at(both, "mon_5v", on_module),
            "V",
            high=1.67,
            source="rule F-11: at or below 1.67 V means the module input",
        ),
        Figure(
            "status_high",
            "Status output while USB-C supplies",
            _level_at(both, "src_st", on_usbc),
            "V",
        ),
        Figure(
            "status_low",
            "Status output while the module input supplies",
            _level_at(both, "src_st", on_module),
            "V",
            high=0.1,
            source="section 4.1: low while the input of the module supplies",
        ),
    ]
    cc_run = runs["cc"]
    t_cc = cc_run.real("time")
    reading = cc_run.real("mon_cc1")
    for index, (label, ohms, volts) in enumerate(_CC_CASES):
        low, high = _CC_WINDOWS[label.split(",")[0]]
        figures.append(
            Figure(
                f"cc_{index}",
                f"CC reading, {label} ({ohms / 1e3:g} kohm to {volts:g} V)",
                measure.value_at(t_cc, reading, (index + 1) * _CC_STEP),
                "V",
                low=low,
                high=high,
                source="section 4.1 and rule F-14: windows of the CC voltage",
            )
        )
    shown = common.cut(time, 0.04, _END)
    graph = Graph(
        name="ramp",
        title="The USB-C voltage rises to 5 V and falls; a supply stands on the module input",
        xlabel="Time (s)",
        panels=(Panel("Voltage (V)"), Panel("Monitor and status (V)", marks=((1.67, "1.67 V"),))),
        traces=(
            Trace(t_both, both.real("vbus_c"), "USB-C receptacle", 0),
            Trace(t_both, both.real("vin1"), "input 1", 0),
            Trace(t_both, both.real("rail"), "5 V rail", 0),
            Trace(
                time[shown], alone.real("rail")[shown], "5 V rail without the module input", 0, "--"
            ),
            Trace(t_both, both.real("mon_5v"), "monitor channel of the rail", 1),
            Trace(t_both, status, "status output", 1),
        ),
    )
    cc_graph = Graph(
        name="cc",
        title="CC1 with the pull-ups of a default, a 1.5 A and a 3 A source",
        xlabel="Time (ms)",
        panels=(
            Panel(
                "Voltage (V)",
                marks=((0.61, "0.61 V"), (0.70, "0.70 V"), (1.16, "1.16 V"), (1.31, "1.31 V")),
            ),
        ),
        traces=(
            Trace(t_cc * 1e3, cc_run.real("cc1"), "CC1", 0),
            Trace(t_cc * 1e3, reading, "at the monitor converter", 0, "--"),
        ),
    )
    notes = (
        "The supply at the receptacle has no cable and can take current back, so that "
        "the receptacle follows it down; with a cable that is pulled the receptacle "
        "follows the capacitors behind the limiter instead.",
        "The limiter and the multiplexer are typical parts with nominal resistors; the "
        "bands of the specification come from their tolerances. The multiplexer model has "
        "10 mV of hysteresis at its priority input, which the datasheet does not state.",
        "On the way up the multiplexer finds its priority input above the threshold as "
        "soon as the limiter has turned on, so only the way down shows its threshold.",
        "The monitor converter is not in the circuit: the channel is the voltage on its "
        "filter capacitor. The share of the rail is read 48 ms after USB-C has taken "
        "over and 38 ms after the module input has; the filter has 5 ms.",
        "The protection array on the CC pins is in the circuit; its leakage is not "
        "modelled, and the 51 uV that the specification calculates from it cannot be "
        "confirmed by a simulation.",
    )
    return Outcome(tuple(figures), (graph, cc_graph), notes)
