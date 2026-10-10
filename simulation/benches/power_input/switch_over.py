"""USB-C is plugged while the module input supplies the rail: the change of input."""

from __future__ import annotations

import numpy as np

from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_PLUG_MODULE = 0.1e-3
"""Instant at which the cable of the module is connected."""

_PLUG_USBC = 7.0e-3
"""Instant at which the USB-C source is plugged: the carrier runs at idle."""

_END = 9.0e-3
"""End of the runs."""

_BUDGET_AMPS = 0.45
"""Input current that firmware allows on the module input (rule F-14)."""

_SLOW_RAMP = "idvdt=1.89u gdvdt=20.31"
"""The limiter of the USB-C input with the least charging current and the
least gain of its dVdt pin (datasheet limits, SLVSET8A page 7)."""

_C4_HIGH = 1.1
"""The capacitor C4 at the upper end of its 10 % tolerance."""


def _deck(ctx: Context, case: str) -> str:
    """The carrier runs from the module input when a USB-C source is plugged in."""
    params = {"U6": common.FAST_SUPERVISOR}
    scales = {}
    if "slow" in case:
        params["U4"] = _SLOW_RAMP
        scales["C4"] = _C4_HIGH
    circuit = common.circuit(ctx, common.carrier_refs(ctx.netlist), params=params, scales=scales)
    stimulus = (
        common.module_port(5.0, _PLUG_MODULE, switch_amps=None)
        + common.usb_c_source(5.0, _PLUG_USBC)
        + common.boost_start()
        + common.idle_loads()
    )
    if "budget" in case:
        extra = _BUDGET_AMPS - 0.12
        stimulus += "* the source meter up to the budget of the module input\n"
        stimulus += common.step_load("smu", "rail", extra, common.RUNNING_AT - 0.3e-3, 0.1e-3)
    save = "save all @b.xu5.b1[i] @b.xu5.b2[i]" if ctx.tier == "open" else "save all"
    control = [save, common.transient(0.5e-6, _END)]
    return ctx.deck(
        f"USB-C plugged while the module input supplies: {case}", circuit, stimulus, control=control
    )


def _figures(case: str, label: str, run: RunResult, expected: float | None) -> list[Figure]:
    """The dip of the rail and what hangs on it, for one run."""
    time = run.real("time")
    rail = run.real("rail")
    change = common.cut(time, _PLUG_USBC, _END)
    before = measure.mean(time, rail, _PLUG_USBC - 0.2e-3, _PLUG_USBC)
    key = case.replace("-", "_")
    return [
        Figure(
            f"rail_low_{key}",
            f"{label}: lowest level of the rail during the change",
            float(np.min(rail[change])),
            "V",
            expected=expected,
            low=common.SUPERVISOR_FALL[1],
            source="section 4.1: 4.0 V to 4.5 V (simulated), against the highest "
            "supervisor threshold of 4.00 V",
        ),
        Figure(f"rail_before_{key}", f"{label}: rail before the plug", before, "V"),
        Figure(
            f"ok_low_{key}",
            f"{label}: lowest level of 5V_OK during the change",
            float(np.min(run.real("ok5v")[change])),
            "V",
            low=1.2,
            source="the carrier keeps running (section 4.1); 1.2 V is the enable "
            "level of the regulators",
        ),
        Figure(
            f"v3a_low_{key}",
            f"{label}: lowest level of 3V3_A during the change",
            float(np.min(run.real("v3a")[change])),
            "V",
            low=3.3 * 0.98,
            source="LP5907 datasheet, page 5: 2 %",
        ),
    ]


@bench(
    "power_input",
    "switch-over",
    "USB-C plugged while the module input supplies: the change of input and the dip of the rail",
    "section 4.1 (when a cable is pulled or plugged), section 16, rule F-35",
)
def switch_over(ctx: Context) -> Outcome:
    """The carrier runs from the cable of the module when a USB-C source is plugged in.

    The limiter of the USB-C input starts and ramps its output up; when the
    priority input of the multiplexer has followed, the multiplexer opens
    the module input and closes USB-C as soon as the rail is no higher than
    that input. The rail is without supply in between. Four runs: at idle
    and with the input current that firmware allows on the module input,
    each with a typical limiter and with the slowest output ramp inside its
    datasheet limits.
    """
    cases = {
        "idle": ("Idle, typical ramp", 4.54),
        "idle-slow": ("Idle, slowest ramp", 4.28),
        "budget": ("0.45 A, typical ramp", None),
        "budget-slow": ("0.45 A, slowest ramp", None),
    }
    runs = common.run_all(ctx, {case: _deck(ctx, case) for case in cases}, keep=("idle",))
    figures: list[Figure] = []
    for case, (label, expected) in cases.items():
        figures += _figures(case, label, runs[case], expected)
    typical = runs["idle"]
    time = typical.real("time")
    change = common.cut(time, _PLUG_USBC, _END)
    port = typical.real("vport_i#branch")
    settled = _PLUG_USBC + 1.2e-3
    if ctx.tier == "open":
        # The currents of the two channels are sources inside the model written here.
        one, two = typical.real("@b.xu5.b1[i]"), typical.real("@b.xu5.b2[i]")
        opened = measure.first_crossing(time, two, 0.02, rising=False, after=_PLUG_USBC)
        closed = measure.first_crossing(time, one, 0.02, rising=True, after=opened)
        settled = closed + 0.2e-3
        figures += [
            Figure(
                "change_after",
                "Idle, typical ramp: the multiplexer opens the module input after the plug",
                opened - _PLUG_USBC,
                "s",
            ),
            Figure(
                "gap",
                "Idle, typical ramp: time without a closed channel",
                closed - opened,
                "s",
            ),
            Figure(
                "input1_at_change",
                "Idle, typical ramp: input 1 when the module input opens",
                measure.value_at(time, typical.real("vin1"), opened),
                "V",
            ),
        ]
    figures += [
        Figure(
            "port_ring",
            "Idle, typical ramp: largest current back into the port of the module while its "
            "cable rings",
            float(-np.min(port[change])),
            "A",
        ),
        Figure(
            "port_after",
            "Idle, typical ramp: mean current of the port of the module after the change",
            measure.mean(time, port, settled, _END),
            "A",
            low=0.0,
            source="section 4.11: neither connector feeds the other one back",
        ),
        Figure(
            "usbc_back",
            "Idle, typical ramp: largest current back into the USB-C source after its first 0.1 ms",
            float(
                -np.min(typical.real("vusbc_i#branch")[common.cut(time, _PLUG_USBC + 0.1e-3, _END)])
            ),
            "A",
            high=1e-3,
            source="section 4.11: neither connector feeds the other one back",
        ),
        Figure(
            "inrush_usbc",
            "Idle, typical ramp: largest current of the USB-C source after its first 0.1 ms",
            float(
                np.max(typical.real("vusbc_i#branch")[common.cut(time, _PLUG_USBC + 0.1e-3, _END)])
            ),
            "A",
            high=common.LIMIT_USB_C[1],
            source="section 4.1: least current limit of the USB-C input, 1.81 A",
        ),
        Figure(
            "status_before",
            "SRC_ST while the module input supplies",
            measure.value_at(time, typical.real("src_st"), _PLUG_USBC - 0.1e-3),
            "V",
            high=0.1,
            source="section 4.1: low while the input of the module supplies",
        ),
    ]
    shown = common.cut(time, _PLUG_USBC - 0.1e-3, _END - 0.5e-3)
    milli = time[shown] * 1e3
    usbc = typical.real("vusbc_i#branch")
    slow = runs["budget-slow"]
    t_slow = slow.real("time")
    shown_slow = common.cut(t_slow, _PLUG_USBC - 0.1e-3, _END - 0.5e-3)
    graph = Graph(
        name="change",
        title="USB-C plugged at 7 ms while the module input supplies the idle carrier",
        xlabel="Time (ms)",
        panels=(
            Panel("Voltage (V)", marks=((common.SUPERVISOR_FALL[1], "supervisor at most 4.00 V"),)),
            Panel("Current of each cable (A)"),
            Panel(
                "Rail, 0.45 A and slowest ramp (V)",
                marks=((common.SUPERVISOR_FALL[1], "supervisor at most 4.00 V"),),
            ),
        ),
        traces=(
            Trace(milli, typical.real("vbus_c")[shown], "USB-C receptacle", 0),
            Trace(milli, typical.real("vin1")[shown], "input 1 (USB-C)", 0),
            Trace(milli, typical.real("vin2")[shown], "input 2 (module)", 0),
            Trace(milli, typical.real("rail")[shown], "5 V rail", 0),
            Trace(milli, typical.real("pr1")[shown], "priority input PR1", 0, "--"),
            Trace(milli, np.clip(usbc[shown], -1, 3), "from the USB-C source", 1),
            Trace(milli, np.clip(port[shown], -1, 3), "from the port of the module", 1),
            Trace(t_slow[shown_slow] * 1e3, slow.real("vin1")[shown_slow], "input 1", 2),
            Trace(t_slow[shown_slow] * 1e3, slow.real("rail")[shown_slow], "5 V rail", 2),
        ),
        xmarks=((_PLUG_USBC * 1e3, "USB-C plugged"),),
    )
    notes = (
        "Both sources are stiff: 5.0 V behind their cables (assumptions: 0.15 ohm and "
        "0.5 uH on USB-C, 0.25 ohm and 0.8 uH on the module input). A higher voltage on "
        "the module port than on USB-C makes the dip deeper by the difference.",
        "The dip is set by where the output of the USB-C limiter stands when the priority "
        "input, behind R18, R19 and C8, passes 1.0 V: the rail falls to that level. The "
        "slower the ramp of the limiter, the lower that level.",
        "The multiplexer is a typical part: reference 1.0 V, 8 us without a channel. Its "
        "reference has a tolerance of 8 %, which moves the level at which it changes.",
        "The aluminum capacitor has the series resistance of its datasheet maximum at "
        "20 C; the ceramic capacitors have the capacitance they keep at 5 V. The run "
        "with a ramp slower than the datasheet allows and a cold capacitor, which the "
        "specification quotes with 4.02 V, was not repeated: neither is a datasheet value.",
        "The supervisor has its release delay shortened to 1 ms; its trip level and its "
        "filter are the ones of the model and of the schematic.",
    )
    return Outcome(tuple(figures), (graph,), notes)
