"""Plugging the cable of the controller module: the in-rush on the port of a computer."""

from __future__ import annotations

import numpy as np

from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_PLUG = 0.2e-3
"""Instant at which the contact closes."""

_END = 8e-3
"""End of the runs."""

_SPIKE = 0.5e-3
"""Time after the plug that belongs to the spike of the module itself: its
47 uF are charged through the switch of the port within 0.25 ms."""

_ROUNDING = 0.005
"""Half the last digit of the port voltage that the specification states."""

_USB_INRUSH_COULOMBS = 50e-6
"""Charge above 100 mA that the in-rush test of the USB specification allows."""

_LIMIT_PARAMS = {
    "least": "vref=0.5229 vreffb=0.196",
    "typical": "",
    "most": "vref=0.6658 vreffb=0.2495",
}
"""Parameters of the limiter U3 for a limit of 0.67 A, 0.76 A and 0.85 A:
the tolerance band of section 4.1."""

_OPEN = PartModel(kind="skip")


def _deck(
    ctx: Context,
    title: str,
    *,
    limit: str = "typical",
    carrier: bool = True,
    boost_amps: float = common.BOOST_START_AMPS,
) -> str:
    """The carrier on the port of a computer, plugged at 0.2 ms.

    Args:
        ctx: The bench context.
        title: First line of the deck.
        limit: Which current limit the limiter of this input has.
        carrier: False opens the jumper JP1: the module alone.
        boost_amps: Input current of the boost converter while it starts.
    """
    params = {"U3": _LIMIT_PARAMS[limit]} if _LIMIT_PARAMS[limit] else {}
    overrides = {} if carrier else {"JP1": _OPEN}
    circuit = common.circuit(
        ctx,
        common.carrier_refs(ctx.netlist),
        bias=common.BIAS_CURVE,
        params=params,
        overrides=overrides,
    )
    stimulus = common.module_port(5.0, _PLUG) + common.boost_start(boost_amps) + common.idle_loads()
    if not carrier:
        stimulus += "* the jumper is open: a resistor keeps the limiter input defined\n"
        stimulus += "Ropen pico_5v 0 1e6\n"
    return ctx.deck(title, circuit, stimulus, control=[common.transient(0.5e-6, _END)])


def _port_figures(result: RunResult) -> tuple[float, float, float]:
    """Largest port current after the spike, lowest port voltage, charge above 100 mA."""
    time = result.real("time")
    amps = result.real("vport_i#branch")
    later = common.cut(time, _PLUG + _SPIKE, _END)
    return (
        float(np.max(amps[later])),
        float(np.min(result.real("port_b")[later])),
        common.charge_above(time, amps, 0.1, _PLUG, _END),
    )


def _plateau(result: RunResult) -> tuple[float, float]:
    """Port current and port voltage while the limiter holds its limit.

    The limiter limits from the moment the boost converter starts until the
    output of that converter is charged; the first 0.15 ms, in which the
    limiter still finds its limit, are left out.
    """
    time = result.real("time")
    amps = result.real("vport_i#branch")
    output = result.real("p13v5")
    if float(np.max(output)) <= 13.4:
        return float("nan"), float("nan")
    later = common.cut(time, _PLUG + _SPIKE, _END)
    start = float(time[later][np.argmax(amps[later])]) + 0.15e-3
    stop = measure.first_crossing(time, output, 13.4, rising=True, after=_PLUG) - 0.05e-3
    if stop <= start:
        return float("nan"), float("nan")
    held = common.cut(time, start, stop)
    return measure.mean(time, amps, start, stop), float(np.min(result.real("port_b")[held]))


@bench(
    "power_input",
    "plug-module",
    "Plugging the cable of the controller module: in-rush on the port of a computer",
    "section 4.1 (limits of the input: in-rush on a computer port, start of the boost "
    "converter), section 14, section 16",
)
def plug_module(ctx: Context) -> Outcome:
    """The cable of the controller module is plugged into the port of a computer.

    Nothing is plugged into the USB-C receptacle. The port is a 5 V supply
    behind a power switch that limits at 1 A, with 120 uF. The module takes
    its own spike through its diode; the carrier follows through the jumper,
    the limiter of 0.76 A and the multiplexer. The boost converter starts as
    soon as the rail allows it and asks for more than the limiter gives. The
    run is repeated with the limiter at the two ends of its tolerance, with
    the boost converter taking 2 A, and with the jumper open, which leaves
    the module alone.
    """
    names = {
        "typical": ("typical limiter, 0.76 A", "typical", common.BOOST_START_AMPS),
        "least": ("limiter at 0.67 A", "least", common.BOOST_START_AMPS),
        "most": ("limiter at 0.85 A", "most", common.BOOST_START_AMPS),
        "boost-2a": ("typical limiter, boost converter takes 2 A", "typical", 2.0),
    }
    decks: dict[str, str] = {}
    for name, (label, limit, boost_amps) in names.items():
        title = f"Module cable plugged into a computer port: {label}"
        decks[name] = _deck(ctx, title, limit=limit, boost_amps=boost_amps)
    decks["module-alone"] = _deck(
        ctx, "Module cable plugged, jumper JP1 open: the module alone", carrier=False
    )
    runs = common.run_all(ctx, decks, keep=("typical", "module-alone"))
    alone = runs["module-alone"]
    result = runs["typical"]
    time = result.real("time")
    milli = time * 1e3
    rail, p13 = result.real("rail"), result.real("p13v5")
    amps = result.real("vport_i#branch")

    figures: list[Figure] = []
    for name, (label, _, _) in names.items():
        peak, port_low, charge = _port_figures(runs[name])
        run_time, run_p13 = runs[name].real("time"), runs[name].real("p13v5")
        run_amps = runs[name].real("vport_i#branch")
        started = float(np.max(run_p13)) > 13.4
        plateau, plateau_volts = _plateau(runs[name])
        figures += [
            Figure(
                f"carrier_amps_{name}",
                f"Largest port current after the spike of the module, {label}",
                peak,
                "A",
                low=0.71 if name == "least" else None,
                high=0.9,
                source="section 4.1: 0.71 A to 0.87 A (simulated); section 16: 0.9 A or less",
            ),
            Figure(
                f"carrier_time_{name}",
                f"Time the port current is above 0.9 A after the spike, {label}",
                common.time_above(run_time, run_amps, 0.9, _PLUG + _SPIKE, _END),
                "s",
            ),
            Figure(
                f"plateau_amps_{name}",
                f"Port current while the limiter limits, {label}",
                plateau,
                "A",
                high=0.9,
                source="section 4.1: 0.71 A to 0.87 A (simulated); section 16: 0.9 A or less",
            ),
            Figure(
                f"port_low_{name}",
                f"Lowest voltage of the port after the spike, {label}",
                port_low,
                "V",
                low=4.94,
                source="section 4.1: the port stays at 4.94 V or above (simulated)",
            ),
            Figure(
                f"plateau_volts_{name}",
                f"Voltage of the port while the limiter limits, {label}",
                plateau_volts,
                "V",
                expected=4.94,
                low=4.94 - _ROUNDING,
                source="section 4.1: the port stays at 4.94 V or above (simulated); the limit "
                "is that figure less half its last digit",
            ),
            Figure(
                f"charge_{name}",
                f"Charge above 100 mA, {label}",
                charge,
                "C",
                low=0.44e-3,
                high=0.96e-3,
                source="section 4.1: 0.44 mC to 0.96 mC (simulated)",
            ),
            Figure(
                f"boost_up_{name}",
                f"Output of the boost converter at 13.4 V after the plug, {label}",
                measure.first_crossing(run_time, run_p13, 13.4, rising=True, after=_PLUG) - _PLUG
                if started
                else float("nan"),
                "s",
                high=_END - _PLUG,
                source="the converter has to start on this input (section 4.1: an open check)",
            ),
            Figure(
                f"rail_end_{name}",
                f"Rail at the end of the run, {label}",
                float(runs[name].real("rail")[-1]),
                "V",
                low=common.SUPERVISOR_RISE_MOST,
                source="section 4.1: highest release level of the supervisor, 4.12 V",
            ),
        ]
    rail_10 = measure.first_crossing(time, rail, 0.5, rising=True, after=_PLUG)
    held = common.cut(time, rail_10, _END)
    _, _, alone_charge = _port_figures(alone)
    figures += [
        Figure(
            "rail_fall_back",
            "Typical limiter: largest fall-back of the rail during its rise",
            float(np.max(np.maximum.accumulate(rail[held]) - rail[held])),
            "V",
        ),
        Figure(
            "limiter_input_low",
            "Typical limiter: lowest voltage at the input of the limiter after the spike",
            float(np.min(result.real("pico_5v")[common.cut(time, _PLUG + _SPIKE, _END)])),
            "V",
            low=3.09,
            source="section 4.1: a limiter turns off at 2.67 V to 2.87 V and on at up to 3.09 V",
        ),
        Figure(
            "limiter_watts",
            "Typical limiter: largest dissipation of the limiter while it limits",
            float(np.max(((result.real("pico_5v") - result.real("vin2")) * amps)[held])),
            "W",
        ),
        Figure(
            "module_charge",
            "Charge above 100 mA with the jumper open (the module alone)",
            alone_charge,
            "C",
            expected=0.12e-3,
            source="section 4.1: the module alone draws 0.12 mC (simulated)",
        ),
        Figure(
            "usb_inrush",
            "Charge above 100 mA against the USB in-rush test, typical limiter",
            _port_figures(result)[2],
            "C",
            high=_USB_INRUSH_COULOMBS,
            source="the 50 uC of the USB in-rush test (section 4.1 states that it is not met)",
        ),
        Figure(
            "module_spike",
            "Peak of the port current in the spike of the module",
            float(np.max(amps[common.cut(time, _PLUG, _PLUG + _SPIKE)])),
            "A",
        ),
    ]
    graph = Graph(
        name="start",
        title="Module cable plugged at 0.2 ms into a port behind a 1 A switch",
        xlabel="Time (ms)",
        panels=(Panel("Voltage (V)"), Panel("Output of the boost converter (V)"), Panel("A")),
        traces=(
            Trace(milli, result.real("port_b"), "port", 0),
            Trace(milli, result.real("pico_5v"), "input of the limiter", 0),
            Trace(milli, result.real("vin2"), "behind the limiter (input 2)", 0),
            Trace(milli, rail, "5 V rail", 0),
            Trace(milli, result.real("vsys"), "VSYS of the module", 0, "--"),
            Trace(milli, p13, "+13.5 V", 1),
            Trace(milli, np.clip(amps, -0.5, 2.5), "port current, typical limiter", 2),
            Trace(
                runs["boost-2a"].real("time") * 1e3,
                np.clip(runs["boost-2a"].real("vport_i#branch"), -0.5, 2.5),
                "boost converter takes 2 A",
                2,
                "--",
            ),
            Trace(
                alone.real("time") * 1e3,
                np.clip(alone.real("vport_i#branch"), -0.5, 2.5),
                "jumper open",
                2,
                ":",
            ),
        ),
        xmarks=((_PLUG * 1e3, "plug"),),
    )
    notes = (
        "The port, its switch (70 mohm, 1 A) and its 120 uF are assumptions, the ones of "
        "the earlier estimate of the specification; so is the cable of 0.25 ohm and 0.8 uH.",
        "The module is the model of the digital block: its diode, 47 uF at their nominal "
        "value on VSYS and a load of 0.1 W. The real capacitor has less under bias, so the "
        "spike and the charge of the module are upper bounds.",
        "The boost converter is a load that takes 1.5 A (2 A in one run) from 2.7 V on the "
        "rail until its output is at 13.5 V: an assumption. With the limiter giving less, "
        "the rail stops rising near 2.7 V until the converter has charged its output. A "
        "real converter at the edge of its input range can behave less evenly than this "
        "load: the run shows that the energy balance allows the start, not how the "
        "converter behaves while it starves.",
        "The fold-back of the limiter does not act here, because its output stays above "
        "1 V; with a fold-back over the whole output range (the datasheet gives no curve) "
        "the limiter would give less at 2.7 V and the start would take longer.",
        "The supervisor holds the carrier off during these runs.",
        "The charge above 100 mA is larger than the 0.44 mC to 0.96 mC of the "
        "specification because the limiter holds the rail near 2.7 V while the boost "
        "converter charges its output: the energy of that output is then taken at 2.7 V "
        "and not at 5 V, for about 0.9 ms at the limit. The figure rests on the load that "
        "stands for the converter. The lowest voltage of the port belongs to the short "
        "peak; while the limiter holds its limit the port is at 4.94 V.",
        "The largest port current after the spike is a peak of some tens of microseconds "
        "at the moment the boost converter starts: the limiter needs its reaction time "
        "(87 us typical for an overload below 1.5 times the limit, datasheet) to find its "
        "limit, and passes up to 1.5 times the limit until then. The current while it "
        "holds the limit is the second figure. The earlier simulation of the "
        "specification had a limiter without that reaction time.",
    )
    return Outcome(tuple(figures), (graph,), notes)
