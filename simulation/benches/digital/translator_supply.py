"""The supply of the user side of the level translator: clamp, drop at rest, sag."""

from __future__ import annotations

import numpy as np

from benches.digital import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel

_REFS = ("R118", "D24", "JP2", "C100", "C101", "U38", "RN8", "RN9", "RN10", "RN11")
"""The feed resistor (drawn on the output sheet), the clamp, the jumper, the
translator with its capacitors and the networks of the eight lines."""

_BUFFER_LOW = -4.0
"""Lowest level of the guard buffer: its negative rail (section 4.8)."""

_BUFFER_HIGH = 12.0
"""Highest level of the guard buffer: its positive rail (section 4.8)."""

_RAIL_CLAMP = 5.61
"""Upper end of the clamp level of the 5 V rail (section 4.1: 5.28 V to 5.61 V)."""

_PIN_LOW = -0.5
"""Lowest voltage that the supply pin of the translator is rated for (TI SCES584D, page 6)."""

_PIN_HIGH = 6.5
"""Highest voltage that the supply pin of the translator is rated for (TI SCES584D, page 6)."""

_SAG_END = 40e-6
"""Length of a sag run."""

_SAG_SCALE = 0.05
"""Factor on C100 in the sag runs, so that the supply settles within the run."""


def _diode(name: str) -> PartModel:
    """The clamp D24 with another variant of its model."""
    return PartModel(
        kind="device",
        letter="D",
        name=name,
        units=(("1", "3"), ("3", "2")),
        library=common.LIBRARY,
        origin="written here",
    )


def _static_deck(
    ctx: Context, celsius: float, diode: str, feed_scale: float, rail: float, title: str
) -> str:
    """The buffer output stepped from its negative to its positive rail."""
    circuit = ctx.circuit(
        _REFS, common.ALIASES, overrides={"D24": _diode(diode)}, scales={"R118": feed_scale}
    )
    stimulus = "\n".join(
        [
            "* the guard buffer as an ideal source that is stepped over its whole",
            "* output range; the 5 V rail and the 3.3 V rail as ideal sources",
            "Vbuf buf_out 0 0",
            f"Vrail v5 0 {rail:g}",
            "Vlogic v3c 0 3.3",
        ]
    )
    return ctx.deck(
        title,
        circuit,
        stimulus,
        control=["dc Vbuf -4 12 0.01"],
        options=(f"temp={celsius:g}", "gmin=1e-13"),
    )


def _sag_deck(ctx: Context, volts: float, hertz: float) -> str:
    """Eight lines driven with a square wave from the output voltage."""
    cpd = 3e-12 if volts > 4.0 else 2e-12
    circuit = ctx.circuit(
        _REFS,
        common.ALIASES,
        overrides={
            "U38": common.with_params(ctx.models.model_of(ctx.netlist.component("U38")), cpd=cpd)
        },
        scales={"C100": _SAG_SCALE},
    )
    half = 0.5 / hertz
    lines = [
        "* the buffer holds the output voltage; the device under test drives all",
        "* eight lines with a square wave from that voltage, the lines in step",
        f"Vbuf buf_out 0 {volts:g}",
        "Vrail v5 0 5",
        "Vlogic v3c 0 3.3",
    ]
    lines += [
        f"Vd{index} j_d{index} 0 PULSE(0 {volts:g} 2u 2n 2n {half - 2e-9:g} {2 * half:g})"
        for index in range(8)
    ]
    return ctx.deck(
        f"Translator supply: eight lines at {hertz / 1e6:g} MHz from {volts:g} V",
        circuit,
        "\n".join(lines),
        control=["save vccb buf_out j_d0 din0", f"tran 0.5n {_SAG_END:g} 0 2n"],
    )


@bench(
    "digital",
    "translator-supply",
    "Supply of the user side of the translator: clamp levels, drop at rest, sag",
    "section 4.8 (D-72), requirement R-10",
)
def translator_supply(ctx: Context) -> Outcome:
    """The translator supply is taken from the buffer output through R118 and D24.

    First the buffer output is stepped from -4 V to +12 V, the two rails it
    can stand at, and the voltage at the supply pin of the translator is
    read: at 27 C and at 0 C, with the clamp at its typical and at its
    largest forward voltage, with 470 ohm in place of the 1 kohm, and with
    the 5 V rail at the upper end of its clamp. The same sweep gives the
    drop at rest between the output voltage and the pin. Then eight logic
    lines are driven in step at 1 MHz and at 10 MHz and the sag of the pin
    is read.
    """
    cases = {
        "typical-27c": (27.0, "DIGITAL_BAT54S", 1.0, 5.0),
        "typical-0c": (0.0, "DIGITAL_BAT54S", 1.0, 5.0),
        "maximum-0c": (0.0, "DIGITAL_BAT54S_HI", 1.0, 5.0),
        "470r-0c": (0.0, "DIGITAL_BAT54S", 0.47, 5.0),
        "470r-0c-maximum": (0.0, "DIGITAL_BAT54S_HI", 0.47, 5.0),
        "rail-clamp": (27.0, "DIGITAL_BAT54S", 1.0, _RAIL_CLAMP),
        "leaky": (27.0, "DIGITAL_BAT54S_LEAKY", 1.0, 5.0),
    }
    sweeps = {}
    for name, (celsius, diode, scale, rail) in cases.items():
        title = f"Translator supply against the buffer output: {name}"
        run = ctx.run(
            name, _static_deck(ctx, celsius, diode, scale, rail, title), keep=name == "typical-27c"
        )
        sweeps[name] = (run.real("buf_out"), run.real("vccb"), -run.real("vbuf#branch"))

    def pin(name: str, buffer: float) -> float:
        volts, at_pin, _ = sweeps[name]
        return float(np.interp(buffer, volts, at_pin))

    def amps(name: str, buffer: float) -> float:
        volts, _, current = sweeps[name]
        return float(np.interp(buffer, volts, current))

    figures: list[Figure] = [
        Figure(
            "low_27c",
            "Buffer at -4 V, 27 C: supply pin of the translator",
            pin("typical-27c", _BUFFER_LOW),
            "V",
            expected=-0.40,
            low=-0.405,
            source="section 4.8: not below -0.40 V (simulated at 0 C and at 27 C)",
        ),
        Figure(
            "low_0c",
            "Buffer at -4 V, 0 C: supply pin of the translator",
            pin("typical-0c", _BUFFER_LOW),
            "V",
            expected=-0.40,
            low=-0.405,
            source="section 4.8: not below -0.40 V (simulated at 0 C and at 27 C)",
        ),
        Figure(
            "low_0c_maximum",
            "Buffer at -4 V, 0 C, clamp at its largest forward voltage: supply pin",
            pin("maximum-0c", _BUFFER_LOW),
            "V",
            low=_PIN_LOW,
            source="section 4.8: inside the -0.5 V of the part (datasheet)",
        ),
        Figure(
            "low_470r",
            "Buffer at -4 V, 0 C, 470 ohm in place of R118, typical clamp: supply pin",
            pin("470r-0c", _BUFFER_LOW),
            "V",
            expected=-0.44,
            source="section 4.8: 470 ohm gives -0.44 V at 0 C (simulated)",
        ),
        Figure(
            "low_470r_maximum",
            "Buffer at -4 V, 0 C, 470 ohm, clamp at its largest forward voltage: supply pin",
            pin("470r-0c-maximum", _BUFFER_LOW),
            "V",
            expected=-0.44,
            low=-0.46,
            high=-0.42,
            source="section 4.8: 470 ohm gives -0.44 V at 0 C (simulated); within 20 mV",
        ),
        Figure(
            "high_27c",
            "Buffer at +12 V, 5 V rail at 5.00 V: supply pin above the rail",
            pin("typical-27c", _BUFFER_HIGH) - 5.0,
            "V",
            expected=0.4,
            high=0.405,
            source="section 4.8: not above the 5 V rail plus 0.4 V (simulated)",
        ),
        Figure(
            "high_0c",
            "Buffer at +12 V, 0 C, 5 V rail at 5.00 V: supply pin above the rail",
            pin("typical-0c", _BUFFER_HIGH) - 5.0,
            "V",
            expected=0.4,
            high=0.405,
            source="section 4.8: not above the 5 V rail plus 0.4 V (simulated)",
        ),
        Figure(
            "high_rail_clamp",
            "Buffer at +12 V, 5 V rail at 5.61 V: supply pin",
            pin("rail-clamp", _BUFFER_HIGH),
            "V",
            expected=6.0,
            high=6.05,
            source="section 4.8: 6.0 V at the most (calculated)",
        ),
        Figure(
            "high_0c_maximum",
            "Buffer at +12 V, 0 C, clamp at its largest forward voltage, rail at 5.61 V",
            pin("maximum-0c", _BUFFER_HIGH) - 5.0 + _RAIL_CLAMP,
            "V",
            high=_PIN_HIGH,
            source="section 4.8: inside the 6.5 V of the part (datasheet)",
        ),
        Figure(
            "clamp_current_low",
            "Buffer at -4 V: current that R118 carries into the clamp",
            -amps("typical-27c", _BUFFER_LOW),
            "A",
            high=0.2,
            source="onsemi BAT54SLT1/D, page 1: 200 mA forward current",
        ),
        Figure(
            "clamp_current_high",
            "Buffer at +12 V: current that R118 carries into the 5 V rail",
            amps("typical-27c", _BUFFER_HIGH),
            "A",
            high=0.2,
            source="onsemi BAT54SLT1/D, page 1: 200 mA forward current",
        ),
    ]
    for volts in (1.67, 3.3, 5.0):
        tag = f"{volts:g}v".replace(".", "p")
        figures.append(
            Figure(
                f"drop_{tag}",
                f"Output at {volts:g} V, lines at rest, leakiest clamp: drop to the pin",
                volts - pin("leaky", volts),
                "V",
                expected=0.010,
                high=0.0105,
                source="section 4.8 and requirement R-10: up to 10 mV (calculated)",
            )
        )
    figures.append(
        Figure(
            "valid_from",
            "Supply pin with the output at 1.67 V",
            pin("leaky", 1.67),
            "V",
            low=1.65,
            source="requirement R-10: 1.65 V at the translator for an output of 1.67 V",
        )
    )
    traces = [
        Trace(sweeps["typical-27c"][0], sweeps["typical-27c"][1], "27 C, typical clamp", 0),
        Trace(
            sweeps["maximum-0c"][0],
            sweeps["maximum-0c"][1],
            "0 C, largest forward voltage",
            0,
            "--",
        ),
        Trace(sweeps["470r-0c"][0], sweeps["470r-0c"][1], "0 C, 470 ohm", 0, ":"),
        Trace(sweeps["typical-27c"][0], sweeps["typical-27c"][2] * 1e3, "27 C, typical clamp", 1),
        Trace(sweeps["470r-0c"][0], sweeps["470r-0c"][2] * 1e3, "0 C, 470 ohm", 1, ":"),
    ]
    clamp = Graph(
        name="clamp",
        title="Supply pin of the translator against the output of the guard buffer",
        xlabel="Buffer output (V)",
        panels=(
            Panel(
                "Supply pin of the translator (V)",
                marks=((_PIN_HIGH, "rating 6.5 V"), (_PIN_LOW, "rating -0.5 V")),
            ),
            Panel("Current in R118 (mA)"),
        ),
        traces=tuple(traces),
    )
    sag_cases = {
        "sag-1v8-1mhz": (1.8, 1e6, 0.030),
        "sag-5v-1mhz": (5.0, 1e6, 0.120),
        "sag-1v8-10mhz": (1.8, 10e6, 0.3),
        "sag-5v-10mhz": (5.0, 10e6, 1.2),
    }
    sag_traces: list[Trace] = []
    for name, (volts, hertz, stated) in sag_cases.items():
        run = ctx.run(name, _sag_deck(ctx, volts, hertz), keep=name == "sag-5v-1mhz")
        time, at_pin = run.real("time"), run.real("vccb")
        window = 10.0 / 1e6
        sag = volts - measure.mean(time, at_pin, _SAG_END - window, _SAG_END)
        at_rest = volts - measure.mean(time, at_pin, 1e-6, 1.9e-6)
        label = f"{volts:g} V, {hertz / 1e6:g} MHz"
        figures.append(
            Figure(
                name.replace("-", "_"),
                f"Eight lines at {hertz / 1e6:g} MHz from {volts:g} V: sag of the supply pin",
                sag - at_rest,
                "V",
                expected=stated,
                low=0.7 * stated,
                high=1.3 * stated,
                source="section 4.8: about this value (calculated); limits of 30 % here",
            )
        )
        sag_traces.append(Trace(time * 1e6, (volts - at_pin) * 1e3, label, 0))
    sag_graph = Graph(
        name="sag",
        title="Supply pin below the output voltage while eight lines switch (C100 at 5 nF)",
        xlabel="Time (us)",
        panels=(Panel("Output voltage less supply pin (mV)", log=True),),
        traces=tuple(sag_traces),
    )
    notes = (
        "The guard buffer is an ideal source at the level asked: its own output "
        "resistance and its current limit are not in this circuit, so the clamp "
        "currents are upper values. The 5 V rail is an ideal source that takes the "
        "clamp current.",
        "The supply current of the translator at rest is the 8 uA maximum of its "
        "datasheet. The charge that an input edge costs is its typical "
        "power-dissipation capacitance, 2 pF at 1.8 V and 3 pF at 5 V; the "
        "datasheet gives no maximum.",
        "In the sag runs C100 is at a twentieth of its value, so that the supply "
        "settles within 40 us; the mean sag does not depend on it, the ripple does. "
        "At 10 MHz from 5 V the supply settles about 1 V lower and the charge per "
        "edge falls with it, which the arithmetic of the specification leaves out.",
        "The figures of the specification were simulated with a clamp fitted to "
        "the largest forward voltage; the typical clamp of this bench holds the pin "
        "40 mV to 80 mV closer to ground and to the rail.",
    )
    return Outcome(tuple(figures), (clamp, sag_graph), notes)
