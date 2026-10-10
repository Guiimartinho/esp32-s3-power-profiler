"""The drop from each connector to the 5 V rail under the loads of the specification."""

from __future__ import annotations

from dataclasses import dataclass

from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_ON = 0.1e-3
"""Instant at which the supply comes up."""

_LOAD_AT = common.RUNNING_AT
"""Instant at which the load of the case is asked for."""

_END = _LOAD_AT + 2.5e-3
"""End of the runs: the rail has settled."""

_MOST = {"U3": "ron=115.3m", "U4": "ron=115.3m", "U5": "ron=55m"}
"""Largest on-resistance up to 85 C of the limiters and of the multiplexer
(datasheets SLVSET8A page 7 and SLVSFG1A page 6)."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One static load case.

    Attributes:
        label: What the case is, as the report shows it.
        usb_c: The USB-C input supplies; otherwise the module input.
        volts: Voltage at the connector.
        most: Parts at their largest on-resistance.
        watts: Load of constant power on the rail, beside the idle carrier.
        amps: Load of constant current on the rail, beside the idle carrier.
    """

    label: str
    usb_c: bool
    volts: float
    most: bool
    watts: float = 0.0
    amps: float = 0.0


_IDLE_WATTS = 0.6
"""What the idle carrier takes from the rail: the assumption of the idle loads."""

_CASES = {
    "typ-1a": _Case("USB-C 5.0 V, typical parts, 6.7 W on the rail", True, 5.0, False, watts=6.1),
    "low-0a6": _Case(
        "USB-C 4.5 V, largest resistance, 4.2 W on the rail", True, 4.5, True, watts=3.6
    ),
    "low-1a": _Case(
        "USB-C 4.53 V, largest resistance, 7.0 W on the rail", True, 4.53, True, watts=6.4
    ),
    "hot-1a7": _Case("USB-C 5.0 V, largest resistance, 1.7 A", True, 5.0, True, amps=1.58),
    "module": _Case("Module input 5.0 V, typical parts, 0.45 A", False, 5.0, False, amps=0.33),
}
"""The load cases. The loads are what section 4.1 names: 6.7 W for 5 V at 1 A
with typical parts, 4.2 W for 5 V at 0.6 A and 7.0 W for 5 V at 1 A in the
calculation behind its figures, 1.7 A and 0.45 A as the budgets of rule F-14.
The idle carrier (0.6 W, an assumption) is part of each."""


def _deck(ctx: Context, case: _Case) -> str:
    """A supply without cable at one connector and a static load on the rail."""
    params = {"U6": common.FAST_SUPERVISOR}
    if case.most:
        params.update(_MOST)
    circuit = common.circuit(ctx, common.carrier_refs(ctx.netlist), params=params)
    node = "vbus_c" if case.usb_c else "pico_vbus"
    stimulus = (
        "* a supply without cable at the connector (not in the schematic)\n"
        + common.ideal_supply("conn", node, case.volts, _ON)
        + common.boost_start()
        + common.idle_loads()
    )
    if case.watts:
        stimulus += f"Bextra rail 0 I = {case.watts:g}/max(v(rail), 3.0)"
        stimulus += f"*pwrin_hi((time - {_LOAD_AT:g})/50u)*pwrin_hi((v(rail) - 3.0)/0.1)\n"
    if case.amps:
        stimulus += common.step_load("extra", "rail", case.amps, _LOAD_AT, 0.2e-3)
    control = ["save all @rjp1[i]", common.transient(1e-6, _END)]
    return ctx.deck(f"Path drop: {case.label}", circuit, stimulus, control=control)


def _levels(run: RunResult, case: _Case) -> tuple[float, float, float, float]:
    """Connector voltage, input 1 or 2, rail and supply current at the end."""
    time = run.real("time")
    start, stop = _END - 0.3e-3, _END - 0.02e-3
    connector = "vbus_c" if case.usb_c else "pico_vbus"
    middle = "vin1" if case.usb_c else "vin2"
    return (
        measure.mean(time, run.real(connector), start, stop),
        measure.mean(time, run.real(middle), start, stop),
        measure.mean(time, run.real("rail"), start, stop),
        measure.mean(time, run.real("vconn_i#branch"), start, stop),
    )


@bench(
    "power_input",
    "path-drop",
    "The drop from each connector to the 5 V rail at the loads of the specification",
    "section 2 (R-14), section 4.1 (path from either connector to the rail, power budget)",
)
def path_drop(ctx: Context) -> Outcome:
    """A supply stands at one connector without a cable and the rail carries a static load.

    The run brings the carrier up, lets the supervisor release it and then
    asks for the load of the case; the levels are read when the rail has
    settled. Five cases: typical parts with the load that 5 V at 1 A at the
    output needs, the two cases with 4.5 V at the receptacle and the largest
    on-resistances that the specification calculates, the dissipation at the
    largest budget, and the module input at its budget.
    """
    runs = common.run_all(
        ctx, {name: _deck(ctx, case) for name, case in _CASES.items()}, keep=("typ-1a", "low-1a")
    )
    levels = {name: _levels(runs[name], case) for name, case in _CASES.items()}
    connector, middle, rail, amps = levels["typ-1a"]
    figures = [
        Figure(
            "path_ohms_typ",
            "USB-C, typical parts: resistance from the receptacle to the rail",
            (connector - rail) / amps,
            "ohm",
            expected=common.PATH_OHMS[0],
            high=common.PATH_OHMS[1],
            source="section 4.1: 0.126 ohm typical and 0.170 ohm at most (calculated)",
        ),
        Figure(
            "drop_typ",
            "USB-C 5.0 V, typical parts, 6.7 W on the rail: drop to the rail",
            connector - rail,
            "V",
        ),
        Figure(
            "amps_typ",
            "The same: current from the supply",
            amps,
            "A",
            expected=1.34,
            source="section 4.1: 6.7 W at 5.0 V on the rail is 1.34 A (calculated); here the "
            "5.0 V stand at the receptacle",
        ),
        Figure(
            "rail_typ",
            "The same: level of the rail",
            rail,
            "V",
            low=common.RAIL_FIRMWARE_LIMIT,
            source="section 4.1: firmware limit of the rail, 4.25 V (F-14)",
        ),
    ]
    connector, middle, rail, amps = levels["low-0a6"]
    figures += [
        Figure(
            "rail_low_0a6",
            "USB-C 4.5 V, largest resistance, 4.2 W on the rail: level of the rail",
            rail,
            "V",
            expected=4.34,
            low=common.RAIL_FIRMWARE_LIMIT,
            source="section 4.1: 4.34 V on the rail (calculated); firmware limit 4.25 V",
        ),
        Figure(
            "path_ohms_most",
            "Largest resistance: resistance from the receptacle to the rail",
            (connector - rail) / amps,
            "ohm",
            expected=common.PATH_OHMS[1],
            high=common.PATH_OHMS[1] * 1.01,
            source="section 4.1: 0.170 ohm at most (calculated)",
        ),
    ]
    connector, middle, rail, amps = levels["low-1a"]
    figures += [
        Figure(
            "rail_low_1a",
            "USB-C 4.53 V, largest resistance, 7.0 W on the rail: level of the rail",
            rail,
            "V",
            expected=4.25,
            low=common.SUPERVISOR_FALL[1],
            source="section 4.1: 5 V at 1 A needs about 4.53 V at the connector "
            "(calculated); highest supervisor threshold 4.00 V",
        ),
        Figure("amps_low_1a", "The same: current from the supply", amps, "A", expected=1.65),
    ]
    connector, middle, rail, amps = levels["hot-1a7"]
    figures += [
        Figure("amps_hot", "Largest budget: current from the supply", amps, "A", expected=1.7),
        Figure(
            "limiter_watts",
            "Largest budget, largest resistance: dissipation of the limiter",
            (connector - middle) * amps,
            "W",
            expected=0.33,
            high=0.33 * 1.05,
            source="section 4.1: 0.33 W at 1.7 A (calculated)",
        ),
        Figure(
            "mux_watts",
            "Largest budget, largest resistance: dissipation of the multiplexer",
            (middle - rail) * amps,
            "W",
            expected=0.16,
            high=0.16 * 1.05,
            source="section 4.1: 0.16 W at 1.7 A (calculated)",
        ),
    ]
    connector, middle, rail, amps = levels["module"]
    jumper = measure.mean(
        runs["module"].real("time"), runs["module"].real("@rjp1[i]"), _END - 0.3e-3, _END - 0.02e-3
    )
    figures += [
        Figure(
            "path_ohms_module",
            "Module input, typical parts: resistance from pin 40 to the rail",
            (connector - rail) / jumper,
            "ohm",
            expected=common.PATH_OHMS[0],
            high=common.PATH_OHMS[1],
            source="section 4.1: 0.126 ohm typical and 0.170 ohm at most (calculated)",
        ),
        Figure("amps_module", "Module input at its budget: current into the carrier", jumper, "A"),
        Figure(
            "rail_module",
            "Module input 5.0 V at its budget of 0.45 A: level of the rail",
            rail,
            "V",
            low=common.RAIL_FIRMWARE_LIMIT,
            source="section 4.1: firmware limit of the rail, 4.25 V (F-14)",
        ),
    ]
    typical = runs["typ-1a"]
    low = runs["low-1a"]
    time = typical.real("time")
    graph = Graph(
        name="levels",
        title="The rail under the load that 5 V at 1 A at the output needs",
        xlabel="Time (ms)",
        panels=(
            Panel(
                "Voltage (V)",
                marks=((common.RAIL_FIRMWARE_LIMIT, "firmware limit 4.25 V"),),
            ),
            Panel("Current from the supply (A)"),
        ),
        traces=(
            Trace(time * 1e3, typical.real("vbus_c"), "receptacle, 5.0 V", 0),
            Trace(time * 1e3, typical.real("rail"), "rail, typical parts, 6.7 W", 0),
            Trace(low.real("time") * 1e3, low.real("vbus_c"), "receptacle, 4.53 V", 0, "--"),
            Trace(
                low.real("time") * 1e3, low.real("rail"), "rail, largest resistance, 7.0 W", 0, "--"
            ),
            Trace(time * 1e3, typical.real("vconn_i#branch").clip(-0.2, 2.5), "5.0 V", 1),
            Trace(
                low.real("time") * 1e3,
                low.real("vconn_i#branch").clip(-0.2, 2.5),
                "4.53 V",
                1,
                "--",
            ),
        ),
        xmarks=((_LOAD_AT * 1e3, "load"),),
    )
    notes = (
        "The supply stands at the pads of the connector: no cable, no contact resistance "
        "and no copper, as in the calculation of section 4.1. A cable of 0.15 ohm takes "
        "another 0.2 V at 1.34 A.",
        "The loads are constant power on the rail, as the converters behind it are; the "
        "idle carrier of 0.6 W is an assumption and part of each load.",
        "The specification states no limit for the drop itself. Its budget is the level "
        "of the rail, 4.25 V, and the resistance of the path.",
        "With 5.0 V at the receptacle the rail stands 0.18 V lower, and the 6.7 W of the "
        "first case take 1.41 A with the 0.1 W of the module, which runs from the rail "
        "when its own cable is not plugged. That is 11 mA more than the 1.4 A that "
        "firmware allows on a 1.5 A source; the 1.34 A of the specification belong to "
        "5.0 V on the rail, which asks for about 5.17 V at the receptacle.",
        "The largest resistance is the datasheet limit up to 85 C; the typical one is at "
        "25 C. Nothing here has a temperature.",
        "The supervisor has its release delay shortened to 1 ms.",
    )
    return Outcome(tuple(figures), (graph,), notes)
