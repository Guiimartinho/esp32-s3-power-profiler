"""The models of the diodes and capacitors of the power input against their datasheets."""

from __future__ import annotations

import numpy as np

from benches.models import power_input_parts as parts
from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.circuit import Circuit
from circuit_sim.engine import RunResult
from circuit_sim.values import parse_value

_STEP = 1e-3
"""Time each forced current or voltage is held."""


def _steps(values: tuple[float, ...]) -> str:
    """A waveform that holds each value for one step, with short ramps between."""
    points = ["0 0"]
    for index, value in enumerate(values):
        points.append(f"{index * _STEP + 0.05e-3:g} {value:g}")
        points.append(f"{(index + 1) * _STEP:g} {value:g}")
    return "PWL(" + " ".join(points) + ")"


def _held(run: RunResult, name: str, index: int) -> float:
    """The value of a waveform near the end of one step."""
    return measure.value_at(run.real("time"), run.real(name), (index + 0.9) * _STEP)


def _stepped(ctx: Context, title: str, circuit: Circuit, stimulus: str, count: int) -> str:
    """A deck that walks through forced values."""
    return ctx.deck(
        title,
        circuit,
        stimulus,
        control=[parts.transient(2e-6, count * _STEP)],
        libraries=(parts.LIBRARY,),
    )


_SCHOTTKY_FORWARD = ((1e-3, 0.150), (10e-3, 0.212), (0.1, 0.282), (1.0, 0.434), (3.0, 0.670))
"""Typical forward voltage of the 1N5819HW at 25 C (DS30217 Rev. 22-2, figure 1)."""

_SCHOTTKY_MOST = {0.1: 0.320, 1.0: 0.450, 3.0: 0.750}
"""Largest forward voltage of the 1N5819HW (page 2)."""


@bench(
    "models",
    "power-input-diodes",
    "1N5819HW, SMAJ10A, TPD4E1U06 and LED models against their datasheets",
    "the models of D3 and D4, of the suppressor D2, of the protection array U2 and of the LED D5",
)
def diodes(ctx: Context) -> Outcome:
    """Each diode of the schematic is put, alone, on forced currents and voltages.

    The Schottky diode across a limiter: forward voltage from 1 mA to 3 A and
    reverse current at 4 V and 10 V. The suppressor: breakdown at 1 mA,
    clamping voltage at 23.5 A, current at its stand-off voltage and forward
    voltage. One channel of the protection array: breakdown and clamping
    voltages. The LED: forward voltage at 20 mA and its current behind 1 kohm
    on 3.3 V.
    """
    vendor = common.VENDOR_DIODE if ctx.tier == "vendor" else None
    schottky = parts.part(ctx, "D3", {"2": "a", "1": "k"}, vendor)
    suppressor = parts.part(ctx, "D2", {"1": "k"})
    array = parts.part(ctx, "U2", {"1": "io1", "3": "io2"})
    led = parts.part(ctx, "D5", {"2": "a"})
    forward = tuple(amps for amps, _ in _SCHOTTKY_FORWARD)
    decks = {
        "schottky-forward": _stepped(
            ctx,
            "1N5819HW: forward voltage",
            schottky,
            f"Vk k 0 0\nIf 0 a {_steps(forward)}\nRa a 0 1e9\n",
            len(forward),
        ),
        "schottky-reverse": _stepped(
            ctx,
            "1N5819HW: reverse current",
            schottky,
            f"Va a 0 0\nVr k 0 {_steps((4.0, 10.0))}\n",
            2,
        ),
        "suppressor": _stepped(
            ctx,
            "SMAJ10A: breakdown, clamping, forward",
            suppressor,
            f"Ik 0 k {_steps((1e-3, 23.5, -25.0))}\nRk k 0 1e9\n",
            3,
        ),
        "suppressor-standoff": _stepped(
            ctx, "SMAJ10A: current at 10 V", suppressor, f"Vr k 0 {_steps((10.0,))}\n", 1
        ),
        "array": _stepped(
            ctx,
            "TPD4E1U06: breakdown and clamping",
            array,
            f"I1 0 io1 {_steps((1e-3, 1.0, 3.0))}\nR1 io1 0 1e9\n"
            f"I2 io2 0 {_steps((1.0,))}\nR2 io2 0 1e9\n",
            3,
        ),
        "led": _stepped(
            ctx,
            "LED: forward voltage",
            led,
            f"Il 0 a {_steps((20e-3, 0.0))}\nVs s 0 PWL(0 0 {_STEP:g} 0 {1.05 * _STEP:g} 3.3)\n"
            "Rs s a 1k\n",
            2,
        ),
    }
    runs, failed = parts.try_runs(ctx, decks, keep=("schottky-forward", "suppressor"))
    figures: list[Figure] = []
    graphs = []
    if "schottky-forward" in runs:
        run = runs["schottky-forward"]
        volts = [_held(run, "a", index) for index in range(len(forward))]
        for index, (amps, typical) in enumerate(_SCHOTTKY_FORWARD):
            figures.append(
                Figure(
                    f"schottky_{index}",
                    f"1N5819HW: forward voltage at {amps:g} A",
                    volts[index],
                    "V",
                    expected=typical,
                    low=typical * (1 - parts.MODEL_FIT),
                    high=_SCHOTTKY_MOST.get(amps, typical * (1 + parts.MODEL_FIT)),
                    source="Diodes DS30217 Rev. 22-2, figure 1 (typical) and page 2 (limits)",
                )
            )
        graphs.append(
            Graph(
                name="schottky",
                title="1N5819HW: forward voltage of the model and of the datasheet curve",
                xlabel="Forward current (A)",
                panels=(Panel("Forward voltage (V)"),),
                traces=(
                    Trace(np.array(forward), np.array(volts), "model", 0),
                    Trace(
                        np.array(forward),
                        np.array([typical for _, typical in _SCHOTTKY_FORWARD]),
                        "datasheet, typical at 25 C",
                        0,
                        "--",
                    ),
                ),
                logx=True,
            )
        )
    if "schottky-reverse" in runs:
        run = runs["schottky-reverse"]
        figures += [
            Figure(
                "schottky_leak_4v",
                "1N5819HW: reverse current at 4 V",
                -_held(run, "vr#branch", 0),
                "A",
                expected=10e-6,
                high=50e-6,
                source="Diodes DS30217 Rev. 22-2, page 2: 10 uA typical, 50 uA at most "
                "(figure 2 shows 6 uA)",
            ),
            Figure(
                "schottky_leak_10v",
                "1N5819HW: reverse current at 10 V",
                -_held(run, "vr#branch", 1),
                "A",
                expected=9e-6,
                source="Diodes DS30217 Rev. 22-2, figure 2",
            ),
        ]
    if "suppressor" in runs:
        run = runs["suppressor"]
        figures += [
            Figure(
                "suppressor_breakdown",
                "SMAJ10A: breakdown voltage at 1 mA",
                _held(run, "k", 0),
                "V",
                expected=11.7,
                low=11.1,
                high=12.3,
                source="Vishay 88390, page 2",
            ),
            Figure(
                "suppressor_clamp",
                "SMAJ10A: clamping voltage at 23.5 A",
                _held(run, "k", 1),
                "V",
                high=17.0,
                source="Vishay 88390, page 2",
            ),
            Figure(
                "suppressor_forward",
                "SMAJ10A: forward voltage at 25 A",
                -_held(run, "k", 2),
                "V",
                high=3.5,
                source="Vishay 88390, page 2, note 6",
            ),
        ]
    if "suppressor-standoff" in runs:
        figures.append(
            Figure(
                "suppressor_leak",
                "SMAJ10A: current at the stand-off voltage of 10 V",
                -_held(runs["suppressor-standoff"], "vr#branch", 0),
                "A",
                high=1.01e-6,
                source="Vishay 88390, page 2: 1 uA at most",
            )
        )
    if "array" in runs:
        run = runs["array"]
        figures += [
            Figure(
                "array_breakdown",
                "TPD4E1U06: breakdown voltage at 1 mA",
                _held(run, "io1", 0),
                "V",
                expected=7.5,
                low=6.5,
                high=8.5,
                source="TI SLVSBQ9D, page 5",
            ),
            near(
                "array_clamp_1a",
                "TPD4E1U06: clamping voltage at 1 A",
                _held(run, "io1", 1),
                "V",
                11.0,
                0.1,
                "TI SLVSBQ9D, page 5",
            ),
            near(
                "array_clamp_3a",
                "TPD4E1U06: clamping voltage at 3 A",
                _held(run, "io1", 2),
                "V",
                15.0,
                0.1,
                "TI SLVSBQ9D, page 5",
            ),
            Figure(
                "array_forward",
                "TPD4E1U06: voltage below ground at 1 A",
                -_held(run, "io2", 0),
                "V",
            ),
        ]
    if "led" in runs:
        run = runs["led"]
        time = run.real("time")
        behind = measure.value_at(time, run.real("a"), 1.9 * _STEP)
        figures += [
            Figure(
                "led_20ma",
                "LED: forward voltage at 20 mA",
                _held(run, "a", 0),
                "V",
                expected=2.0,
                high=2.4,
                source="Wurth 150060VS75000, page 2",
            ),
            Figure("led_volts", "LED: forward voltage behind 1 kohm on 3.3 V", behind, "V"),
            Figure("led_amps", "LED: current behind 1 kohm on 3.3 V", (3.3 - behind) / 1e3, "A"),
        ]
    notes = (
        f"The fit this project asks of a model is {parts.MODEL_FIT * 100:.0f} % on a typical "
        "value; where the datasheet states limits, the limits are the ones of the datasheet.",
        "The typical forward curve of the Schottky diode is read from figure 1 of its "
        "datasheet. Its reverse current doubles every 9 K (figure 2); the model stands at "
        "25 C.",
        "The suppressor and the protection array are static models: their capacitance is "
        "in the models and is not tested here.",
        "In the vendor tier the Schottky diode is the model of its manufacturer; the "
        "other parts of this bench have none. That file holds a line of plain text, the "
        "wrapped end of a comment, on which the simulator stops, so its two decks do not "
        "run.",
        *parts.failure_note(failed),
    )
    return Outcome(tuple(figures), tuple(graphs), notes)


_BIAS_POINTS = {
    "C2": ("4.7 uF 25 V X7R 0805", ((5.0, 0.715), (10.0, 0.393), (12.0, 0.327))),
    "C9": ("22 uF 10 V X7R 1206", ((2.5, 0.917), (5.0, 0.686), (10.0, 0.372))),
    "C39": ("10 uF 25 V X5R 0805", ((2.5, 0.807), (5.0, 0.497), (10.0, 0.225))),
    "C27": ("10 uF 25 V X7R 1210", ((5.0, 0.947), (12.0, 0.740), (13.5, 0.695))),
}
"""Share of the capacitance that is left at a bias voltage, from the curves
that Samsung Electro-Mechanics shows for each part (read on 9 October 2026)."""

_CHARGE_AMPS = 1e-3
"""Current that charges a capacitor in the bias run."""


@bench(
    "models",
    "power-input-capacitors",
    "Capacitor models of the power input against their datasheets",
    "the aluminum capacitor C11 and the ceramic capacitors under bias",
)
def capacitors(ctx: Context) -> Outcome:
    """The capacitors that set the transients of the 5 V rail are put on a current.

    A small signal gives the impedance of the aluminum capacitor at 120 Hz and
    100 kHz. A constant current charges four ceramic capacitors from 0 V with
    the bias model that the benches of the power input give them; the slope
    of the voltage is the capacitance that is left at that voltage.
    """
    aluminum = parts.part(ctx, "C11", {"1": "p"})
    bulk = ctx.deck(
        "C11: impedance",
        aluminum,
        "Iac 0 p DC 0 AC 1\nRdc p 0 1e6\n",
        control=["ac dec 20 10 1meg"],
        libraries=(parts.LIBRARY,),
    )
    refs = tuple(_BIAS_POINTS)
    nodes = {ref: f"n_{ref.lower()}" for ref in refs}
    aliases = {ctx.netlist.component(ref).net_of("1"): nodes[ref] for ref in refs}
    ceramic = ctx.circuit(refs, aliases, common.bias_models(ctx.netlist, refs))
    stimulus = "".join(
        f"I{ref} 0 {nodes[ref]} PWL(0 0 1u {_CHARGE_AMPS:g})\nR{ref}x {nodes[ref]} 0 1e9\n"
        for ref in refs
    )
    bias = ctx.deck(
        "Ceramic capacitors: capacitance against voltage",
        ceramic,
        stimulus,
        control=[parts.transient(20e-6, 0.3)],
        libraries=(parts.LIBRARY,),
    )
    runs, failed = parts.try_runs(ctx, {"bulk": bulk, "bias": bias}, keep=("bulk", "bias"))
    figures: list[Figure] = []
    graphs = []
    if "bulk" in runs:
        run = runs["bulk"]
        frequency = np.real(run.vector("frequency", plot="ac")).astype(np.float64)
        impedance = run.vector("p", plot="ac")
        at_120 = int(np.argmin(np.abs(frequency - 120.0)))
        at_100k = int(np.argmin(np.abs(frequency - 1e5)))
        figures += [
            Figure(
                "bulk_farads",
                "C11: capacitance at 120 Hz",
                float(-1.0 / (2 * np.pi * frequency[at_120] * np.imag(impedance[at_120]))),
                "F",
                expected=47e-6,
                low=47e-6 * 0.8,
                high=47e-6 * 1.2,
                source="Wurth 865060343004, page 1: 47 uF, 20 %",
            ),
            Figure(
                "bulk_ohms",
                "C11: impedance at 100 kHz",
                float(np.abs(impedance[at_100k])),
                "ohm",
                high=0.44 * 1.01,
                source="Wurth 865060343004, page 1: 440 mohm at most",
            ),
        ]
    if "bias" in runs:
        run = runs["bias"]
        time = run.real("time")
        traces = []
        for ref, (label, points) in _BIAS_POINTS.items():
            volts = run.real(nodes[ref])
            nominal = parse_value(ctx.netlist.component(ref).value)
            slope = np.gradient(volts, time)
            share = _CHARGE_AMPS / np.maximum(slope, 1e-9) / nominal
            rising = volts < 0.98 * float(np.max(volts))
            traces.append(Trace(volts[rising][5:], share[rising][5:] * 100.0, f"{ref}, {label}", 0))
            for bias_volts, left in points:
                if bias_volts > float(np.max(volts)):
                    continue
                figures.append(
                    near(
                        f"bias_{ref.lower()}_{bias_volts:g}v".replace(".", "p"),
                        f"{ref} ({label}): share of its capacitance at {bias_volts:g} V",
                        float(np.interp(bias_volts, volts[rising], share[rising])),
                        "",
                        left,
                        0.08,
                        "bias curve of Samsung Electro-Mechanics for the part, 25 C",
                    )
                )
        graphs.append(
            Graph(
                name="bias",
                title="Capacitance that the ceramic capacitors keep under bias, as modelled",
                xlabel="Voltage (V)",
                panels=(Panel("Share of the nominal capacitance (%)"),),
                traces=tuple(traces),
            )
        )
    notes = (
        "The series resistance of C11 is the impedance that its datasheet states as the "
        "maximum at 100 kHz and 20 C; a typical part has less, a cold one more, and the "
        "datasheet gives neither.",
        "The bias model is one curve per part number with one parameter, the voltage at "
        "which half the capacitance is left; 8 % is the fit this project asks of it. The "
        "10 uF 25 V part in 0805 (C39, C40) is 12 % below its curve at 10 V and fails that "
        "fit there; it stands on the 5 V rail, where the limiters hold it at 5.6 V or "
        "less. The model is used by the benches of the power input; the model map leaves "
        "the capacitors of the schematic at their nominal value.",
        "The 1 uF and 100 nF capacitors in 0603 have no bias model: no curve of theirs was read.",
        *parts.failure_note(failed),
    )
    return Outcome(tuple(figures), tuple(graphs), notes)
