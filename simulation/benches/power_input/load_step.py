"""A load step of 1 A on the 5 V rail: the dip and its recovery."""

from __future__ import annotations

import numpy as np

from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_PLUG = 0.1e-3
"""Instant at which the source is connected."""

_STEP = common.RUNNING_AT
"""Instant of the load step."""

_END = _STEP + 2.5e-3
"""End of the runs."""

_AMPS = 1.0
"""Height of the step: what the source meter takes from the rail when the
output steps to its full current."""

_CASES = {
    "typical": ("ESR 0.44 ohm, cable 0.5 uH, edge 1 us", "", common.CABLE_HENRIES, 1e-6),
    "low-esr": (
        "ESR 0.22 ohm, cable 0.5 uH, edge 1 us",
        "c=47u esr=0.22",
        common.CABLE_HENRIES,
        1e-6,
    ),
    "long-cable": ("ESR 0.44 ohm, cable 2 uH, edge 1 us", "", 2e-6, 1e-6),
    "slow-edge": ("ESR 0.44 ohm, cable 0.5 uH, edge 50 us", "", common.CABLE_HENRIES, 50e-6),
}
"""The runs: label, parameters of the aluminum capacitor C11, inductance of
the cable, rise time of the load. 0.44 ohm is the datasheet maximum of the
capacitor at 20 C; 0.22 ohm, 2 uH and the edges are assumptions."""


def _deck(ctx: Context, case: str) -> str:
    """The idle carrier on USB-C takes 1 A more from the rail at 6.5 ms."""
    label, c11, henries, edge = _CASES[case]
    params = {"U6": common.FAST_SUPERVISOR}
    if c11:
        params["C11"] = c11
    circuit = common.circuit(ctx, common.carrier_refs(ctx.netlist), params=params)
    stimulus = (
        common.usb_c_source(5.0, _PLUG, henries=henries)
        + common.boost_start()
        + common.idle_loads()
        + "* the step: a current sink on the rail (not in the schematic)\n"
        + common.step_load("step", "rail", _AMPS, _STEP, edge)
    )
    return ctx.deck(
        f"Load step of 1 A on the rail: {label}",
        circuit,
        stimulus,
        control=[common.transient(0.5e-6, _END)],
    )


def _figures(case: str, label: str, run: RunResult) -> list[Figure]:
    """Dip, recovery and what the 3.3 V rails see, for one run."""
    time = run.real("time")
    rail = run.real("rail")
    before = measure.mean(time, rail, _STEP - 0.2e-3, _STEP - 0.01e-3)
    final = measure.mean(time, rail, _END - 0.2e-3, _END)
    after = common.cut(time, _STEP, _END)
    lowest = float(np.min(rail[after]))
    key = case.replace("-", "_")
    v3a = run.real("v3a")
    return [
        Figure(
            f"low_{key}",
            f"{label}: lowest level of the rail",
            lowest,
            "V",
            low=common.RAIL_FIRMWARE_LIMIT,
            source="section 4.1: firmware limit of the rail, 4.25 V (F-14)",
        ),
        Figure(f"dip_{key}", f"{label}: dip below the level before the step", before - lowest, "V"),
        Figure(
            f"under_{key}",
            f"{label}: dip below the level the rail settles at",
            final - lowest,
            "V",
        ),
        Figure(
            f"settled_{key}",
            f"{label}: rail within 20 mV of its new level after",
            measure.settling_time(time, rail, final, 0.02, _STEP, _END),
            "s",
        ),
        Figure(
            f"v3a_{key}",
            f"{label}: largest excursion of 3V3_A",
            float(np.max(np.abs(v3a[after] - 3.3))),
            "V",
            high=3.3 * 0.02,
            source="LP5907 datasheet, page 5: 2 %",
        ),
    ]


@bench(
    "power_input",
    "load-step",
    "A load step of 1 A on the 5 V rail: the dip and its recovery with the capacitors as drawn",
    "section 3 (capacitance of the 5 V rail), section 4.1 (thresholds of the rail), rule F-35",
)
def load_step(ctx: Context) -> Outcome:
    """The idle carrier runs from USB-C and takes 1 A more from the rail within a microsecond.

    The step stands for the source meter when its output steps to full
    current. The rail holds 47 uF of aluminum capacitor with its series
    resistance and about 15 uF of ceramic capacitance under bias; the supply
    comes through the multiplexer, the limiter with its damper, and the
    cable. The run is repeated with half the series resistance, with a cable
    of four times the inductance, and with an edge of 50 us.
    """
    runs = common.run_all(ctx, {case: _deck(ctx, case) for case in _CASES}, keep=("typical",))
    figures: list[Figure] = []
    for case, (label, _, _, _) in _CASES.items():
        figures += _figures(case, label, runs[case])
    typical = runs["typical"]
    time = typical.real("time")
    rail = typical.real("rail")
    figures += [
        Figure(
            "level_before",
            "Rail before the step (0.12 A at idle)",
            measure.mean(time, rail, _STEP - 0.2e-3, _STEP - 0.01e-3),
            "V",
        ),
        Figure(
            "level_after",
            "Rail after the step (1.12 A)",
            measure.mean(time, rail, _END - 0.2e-3, _END),
            "V",
            low=common.RAIL_FIRMWARE_LIMIT,
            source="section 4.1: firmware limit of the rail, 4.25 V (F-14)",
        ),
        Figure(
            "step_height",
            "Fall of the rail from before the step to its new level",
            measure.mean(time, rail, _STEP - 0.2e-3, _STEP - 0.01e-3)
            - measure.mean(time, rail, _END - 0.2e-3, _END),
            "V",
            high=0.3,
            source="rule F-35: a step of more than 0.3 V marks samples as not valid",
        ),
        Figure(
            "ok_low",
            "Lowest level of 5V_OK",
            float(np.min(typical.real("ok5v")[common.cut(time, _STEP, _END)])),
            "V",
            low=1.2,
            source="the carrier keeps running; 1.2 V is the enable level of the regulators",
        ),
        Figure(
            "receptacle_low",
            "Lowest voltage at the receptacle",
            float(np.min(typical.real("vbus_c")[common.cut(time, _STEP, _END)])),
            "V",
        ),
    ]
    shown = common.cut(time, _STEP - 0.1e-3, _STEP + 1.2e-3)
    micro = (time[shown] - _STEP) * 1e6
    traces = [
        Trace(micro, rail[shown], "5 V rail", 0),
        Trace(micro, typical.real("vin1")[shown], "input 1 of the multiplexer", 0),
        Trace(micro, typical.real("vbus_c")[shown], "receptacle", 0, "--"),
        Trace(micro, (typical.real("v3a")[shown] - 3.3) * 1e3, "3V3_A", 2),
        Trace(micro, (typical.real("v3c")[shown] - 3.3) * 1e3, "3V3_C", 2),
        Trace(micro, typical.real("vusbc_i#branch")[shown], "from the source", 3),
    ]
    for case, (label, _, _, _) in _CASES.items():
        run_time = runs[case].real("time")
        part = common.cut(run_time, _STEP - 0.1e-3, _STEP + 1.2e-3)
        traces.append(
            Trace((run_time[part] - _STEP) * 1e6, runs[case].real("rail")[part], label, 1)
        )
    graph = Graph(
        name="step",
        title="1 A more on the 5 V rail of the idle carrier, supplied through USB-C",
        xlabel="Time after the step (us)",
        panels=(
            Panel("Voltage (V)"),
            Panel("5 V rail, the four runs (V)"),
            Panel("Deviation from 3.3 V (mV)"),
            Panel("Current (A)"),
        ),
        traces=tuple(traces),
    )
    notes = (
        "The source is 5.0 V behind 0.15 ohm of cable: an assumption. The new level of "
        "the rail is the old one less the step times the cable and the path, about 0.28 V "
        "per ampere; without the cable it is 0.13 V per ampere.",
        "The first part of the dip is the step in the series resistance of the aluminum "
        "capacitor, which carries most of it until the ceramic capacitors and the supply "
        "take over. The ceramic capacitors have the capacitance they keep at 5 V.",
        "The step is a current sink. The source meter is a converter and takes constant "
        "power, which draws a little more current as the rail falls.",
        "The regulators of the 3.3 V rails follow their datasheet in supply rejection up "
        "to 100 kHz; their response to load steps of their own is not modelled.",
        "The supervisor has its release delay shortened to 1 ms.",
    )
    return Outcome(tuple(figures), (graph,), notes)
