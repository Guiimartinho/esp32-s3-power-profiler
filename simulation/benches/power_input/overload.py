"""A load on the rail beyond what the source gives: the supervisor sheds the carrier."""

from __future__ import annotations

import numpy as np

from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_PLUG = 0.1e-3
"""Instant at which the source is connected."""

_STEP = common.RUNNING_AT
"""Instant at which the pre-regulator starts to take its power."""

_END = _STEP + 1.2e-3
"""End of the runs."""

_WATTS = 6.3
"""Power that the pre-regulator takes from the rail in the estimate of
section 4.1 (5 V at 1 A needs 6.7 W to 7.6 W with the idle carrier)."""

_WEAK_AMPS = 0.9
"""Current of a USB-C source that gives no more than a USB 3 port has to."""

_MODULE_LOW_VOLTS = 1.8
"""Lowest VSYS at which the controller module works (Pico 2 datasheet, page 12)."""


def _deck(ctx: Context, case: str) -> str:
    """The running carrier takes 6.3 W more than at idle, on one of three supplies."""
    params = {"U6": common.FAST_SUPERVISOR}
    if case == "module-wide-foldback":
        params["U3"] = "vfold=4.5"
    if case.startswith("module"):
        source = common.module_port(5.0, _PLUG, switch_amps=None)
        title = "Overload of the module input: 6.3 W on a limit of 0.76 A"
    else:
        source = common.usb_c_source(5.0, _PLUG, amps=_WEAK_AMPS)
        title = "Overload of a USB-C source that gives 0.9 A: 6.3 W"
    circuit = common.circuit(ctx, common.carrier_refs(ctx.netlist), params=params)
    stimulus = (
        source
        + common.boost_start()
        + common.idle_loads()
        + "* the pre-regulator as a load of constant power, shed with 5V_OK\n"
        + common.power_load("smu", "rail", _WATTS, _STEP, _STEP + 0.6e-3)
    )
    return ctx.deck(title, circuit, stimulus, control=[common.transient(0.5e-6, _END)])


def _figures(case: str, label: str, run: RunResult) -> list[Figure]:
    """Lowest rail, reaction of the supervisor and recovery of one run."""
    time = run.real("time")
    rail, ok5v = run.real("rail"), run.real("ok5v")
    after = common.cut(time, _STEP, _END)
    low_at = float(time[after][np.argmin(rail[after])])
    passed = measure.first_crossing(time, rail, common.SUPERVISOR_TYP[0], False, after=_STEP)
    tripped = measure.first_crossing(time, ok5v, 1.5, rising=False, after=_STEP)
    back = measure.first_crossing(time, rail, 4.5, rising=True, after=low_at)
    return [
        Figure(
            f"rail_low_{case}",
            f"{label}: lowest level of the rail",
            float(np.min(rail[after])),
            "V",
            low=2.99,
            high=3.97,
            source="section 4.1: a minimum of 2.99 V to 3.97 V (estimate, 96 cases)",
        ),
        Figure(
            f"trip_after_{case}",
            f"{label}: 5V_OK low after the load has stepped",
            tripped - _STEP,
            "s",
        ),
        Figure(
            f"trip_delay_{case}",
            f"{label}: 5V_OK low after the rail has passed 3.91 V",
            tripped - passed,
            "s",
            high=0.1e-3,
            source="section 4.1: the pre-regulator is off within 0.1 ms (estimate)",
        ),
        Figure(
            f"below_{case}",
            f"{label}: time the rail spends below 3.91 V",
            back - passed,
            "s",
        ),
        Figure(
            f"vsys_low_{case}",
            f"{label}: lowest VSYS of the module",
            float(np.min(run.real("vsys")[after])),
            "V",
            expected=3.46,
            low=_MODULE_LOW_VOLTS,
            source="section 4.1: VSYS stays at 3.46 V or above (estimate); the module "
            "works from 1.8 V",
        ),
        Figure(
            f"v3a_low_{case}",
            f"{label}: 3V3_A when 5V_OK falls",
            measure.value_at(time, run.real("v3a"), tripped),
            "V",
            low=3.3 * 0.98,
            source="the regulator holds 3.3 V within 2 % until it is switched off "
            "(LP5907 datasheet, page 5)",
        ),
    ]


@bench(
    "power_input",
    "overload",
    "A load beyond what the source gives: the rail falls and the supervisor sheds the carrier",
    "section 4.1 (thresholds of the 5 V rail, enforcement), section 3 (supervisor), rule F-7",
)
def overload(ctx: Context) -> Outcome:
    """The running carrier is asked for 6.3 W more than a current-limited supply gives.

    The load stands for the pre-regulator of the source meter: a constant
    power that follows 5V_OK, so that it is shed when the supervisor trips.
    Three runs: on the module input with its limiter of 0.76 A, the same
    with a limiter whose fold-back reaches over the whole output range, and
    on the USB-C input from a source that gives no more than 0.9 A. The load
    is asked for during 0.6 ms; firmware, which would latch the fault
    (rule F-7), is not in the circuit.
    """
    cases = {
        "module": "Module input",
        "module-wide-foldback": "Module input, fold-back up to 4.5 V",
        "usbc-weak": "USB-C source of 0.9 A",
    }
    runs = {
        case: ctx.run(case, _deck(ctx, case), keep=case != "module-wide-foldback") for case in cases
    }
    figures: list[Figure] = []
    for case, label in cases.items():
        figures += _figures(case.replace("-", "_"), label, runs[case])
    module, weak = runs["module"], runs["usbc-weak"]
    t_m, t_w = module.real("time"), weak.real("time")
    shown_m = common.cut(t_m, _STEP - 0.1e-3, _END)
    shown_w = common.cut(t_w, _STEP - 0.1e-3, _END)
    figures.append(
        Figure(
            "receptacle_low_usbc_weak",
            "USB-C source of 0.9 A: lowest voltage at the receptacle",
            float(np.min(weak.real("vbus_c")[shown_w])),
            "V",
            low=2.87,
            source="section 4.1: a limiter turns off at 2.67 V to 2.87 V",
        )
    )
    graph = Graph(
        name="shed",
        title="6.3 W asked from a supply that cannot give it, at 6.5 ms",
        xlabel="Time (ms)",
        panels=(
            Panel(
                "Module input (V)",
                marks=((common.SUPERVISOR_TYP[0], "supervisor 3.91 V"),),
            ),
            Panel(
                "USB-C source of 0.9 A (V)",
                marks=((common.SUPERVISOR_TYP[0], "supervisor 3.91 V"),),
            ),
            Panel("Current of the supply (A)"),
        ),
        traces=(
            Trace(t_m[shown_m] * 1e3, module.real("rail")[shown_m], "5 V rail", 0),
            Trace(t_m[shown_m] * 1e3, module.real("ok5v")[shown_m], "5V_OK", 0),
            Trace(t_m[shown_m] * 1e3, module.real("v3a")[shown_m], "3V3_A", 0),
            Trace(t_m[shown_m] * 1e3, module.real("vsys")[shown_m], "VSYS", 0, "--"),
            Trace(t_w[shown_w] * 1e3, weak.real("rail")[shown_w], "5 V rail", 1),
            Trace(t_w[shown_w] * 1e3, weak.real("ok5v")[shown_w], "5V_OK", 1),
            Trace(t_w[shown_w] * 1e3, weak.real("vbus_c")[shown_w], "receptacle", 1),
            Trace(t_w[shown_w] * 1e3, weak.real("vsys")[shown_w], "VSYS", 1, "--"),
            Trace(t_m[shown_m] * 1e3, module.real("vport_i#branch")[shown_m], "module port", 2),
            Trace(t_w[shown_w] * 1e3, weak.real("vusbc_i#branch")[shown_w], "USB-C source", 2),
        ),
        xmarks=((_STEP * 1e3, "load"),),
    )
    notes = (
        "The load of 6.3 W is the one of the estimate in section 4.1. It follows 5V_OK "
        "with a delay of 50 us, which stands for the transistor at the enable pin and the "
        "converter: an assumption. With a longer delay the rail falls further.",
        "The supervisor has its release delay shortened to 1 ms so that the carrier runs "
        "at 6.5 ms; its reaction to the falling rail is that of the model, with the "
        "filter of the schematic at its input. The load is not asked for again when "
        "5V_OK returns: the run ends before.",
        "The source of 0.9 A limits without switching off: an assumption. A port that "
        "switches off at its limit ends the run differently.",
        "On the module input the module has its own supply through its diode, so VSYS "
        "does not follow the rail there. On USB-C alone it does, through D1.",
        "The idle loads are assumptions (0.12 A in all); they are shed with 5V_OK too.",
    )
    return Outcome(tuple(figures), (graph,), notes)
