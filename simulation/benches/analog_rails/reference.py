"""The reference line: level under load, impedance with the capacitors as drawn, noise."""

from __future__ import annotations

import numpy as np

from benches.analog_rails import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.circuit import Circuit, PartModel
from circuit_sim.engine import RunResult

_REFS = ("U12", "R31", "C20", "C24", "R35", "C26", "D7", "R49", "R50", "C113")
"""The reference with its supply filter, its capacitors, the diode to 3V3_A,
the divider of the rail monitor and the capacitor at the monitor converter."""

_LOAD = common.REFERENCE_AMPS
"""Current into the dividers that are not in this circuit and into the converter."""

_CONVERSION_COULOMBS = 300e-12
"""Charge the converter takes from its REF pin per conversion.

Its datasheet gives 300 uA at 1 MHz of sample rate, which is 300 pC per
conversion.
"""

_SAMPLE_PERIOD = 10e-6
"""Sample period at 100 kSPS."""


def _reference(independent: bool) -> PartModel:
    """The reference model, with or without the change of its output stage with the load."""
    return PartModel(
        kind="subckt",
        name="REF5025AID",
        ports=("2", "4", "5", "6"),
        library=common.LIBRARY,
        origin="written here",
        params="i0=1" if independent else "",
    )


def _circuit(ctx: Context, independent: bool, scales: dict[str, float] | None = None) -> Circuit:
    refs = (*_REFS, *common.REFERENCE_LINE)
    overrides = common.bias_models(ctx.netlist, refs)
    if independent:
        overrides["U12"] = _reference(True)
    return ctx.circuit(refs, common.ALIASES, overrides, scales)


def _supplies() -> str:
    return "\n".join(
        [
            "* 3V3_A and -4V_A as sources; the loads of the line that are not in this",
            "* circuit as one current sink",
            "V3a p3v3_a 0 DC 3.3 AC 0",
            "Vm4 m4v_a 0 -4",
            f"Iload vref 0 {_LOAD:g}",
        ]
    )


def _small_signal_deck(ctx: Context, independent: bool, r35: float) -> str:
    """Operating point, impedance of the line and noise at the reference pin."""
    circuit = _circuit(ctx, independent, {"R35": r35})
    return ctx.deck(
        "Reference line: operating point, impedance and noise",
        circuit,
        _supplies(),
        "Iac 0 vref DC 0 AC 1",
        control=[
            "op",
            "noise v(vref) V3a dec 40 0.1 1meg",
            "ac dec 40 0.1 1meg",
        ],
    )


def _transient_deck(ctx: Context) -> str:
    """The converter takes its charge at 100 kSPS from the capacitor at its pin."""
    width = 0.5e-6
    amps = _CONVERSION_COULOMBS / width
    stimulus = "\n".join(
        [
            "V3a p3v3_a 0 PWL(0 0 0.1m 3.3)",
            "Vm4 m4v_a 0 PWL(0 0 0.1m -4)",
            f"Iload vref 0 {_LOAD - _CONVERSION_COULOMBS / _SAMPLE_PERIOD:g}",
            "* the reference input of the converter: 300 pC per conversion, from 250 ms on",
            f"Iadc ref_c89 0 PULSE(0 {amps:g} 0.25 20n 20n {width:g} {_SAMPLE_PERIOD:g})",
        ]
    )
    return ctx.deck(
        "Reference line: start and the conversions of the converter",
        _circuit(ctx, False),
        stimulus,
        control=[
            "save vref ref_c89 ref_in ref_nr p3v3_a",
            "tran 1u 0.2531 0 20u",
        ],
        # the ripple that is read is microvolts on 2.5 V: far below the default tolerances
        options=("reltol=1e-6", "vntol=10n", "abstol=1p"),
    )


def _impedance(run: RunResult) -> tuple[common.Real, common.Real]:
    frequency = run.real("frequency", plot="ac")
    return frequency, np.abs(run.vector("vref", plot="ac"))


@bench(
    "analog_rails",
    "reference",
    "Reference line: level under load, impedance with the capacitors as drawn, noise",
    "section 4.6 (reference, capacitors on the reference line), decisions D-53 and D-75",
)
def reference(ctx: Context) -> Outcome:
    """The reference runs from 3.3 V with every capacitor and divider of its line.

    The circuit is the reference with its supply filter R31 and C20, its
    noise capacitor C24, the capacitor C26 behind R35, the capacitor C89 of
    the converter behind R131, C113, the diode D7 and the dividers of the
    line that the netlist holds. An operating point gives the level and the
    head room; a current of 1 A injected at the pin of the reference gives
    the impedance of the line; a noise analysis gives the noise at that pin.
    A transient shows the start and what the conversions of the converter do
    at 100 kSPS.
    """
    drawn = ctx.run("small-signal", _small_signal_deck(ctx, False, 1.0))
    stiff = ctx.run("small-signal-no-load-change", _small_signal_deck(ctx, True, 1.0), keep=False)
    shorted = ctx.run("small-signal-r35-short", _small_signal_deck(ctx, False, 1e-3), keep=False)
    most = ctx.run("small-signal-r35-1r5", _small_signal_deck(ctx, False, 1.5), keep=False)
    level = float(drawn.real("vref", plot="op")[0])
    supply = float(drawn.real("ref_in", plot="op")[0])
    frequency, impedance = _impedance(drawn)
    _, impedance_stiff = _impedance(stiff)
    _, impedance_short = _impedance(shorted)
    _, impedance_most = _impedance(most)
    noise_f = drawn.real("frequency", plot="noise1")
    density = drawn.real("onoise_spectrum", plot="noise1")
    density_stiff = stiff.real("onoise_spectrum", plot="noise1")
    floor = float(np.interp(100.0, noise_f, density))

    def peak(values: common.Real) -> tuple[float, float]:
        index = int(np.argmax(values))
        return float(values[index]), float(frequency[index])

    z_peak, f_peak = peak(impedance)
    z_stiff, f_stiff = peak(impedance_stiff)
    figures = [
        near(
            "level",
            "VREF with the loads of its line",
            level,
            "V",
            2.5,
            0.001,
            "section 4.6: 2.5 V; initial accuracy of the part 0.1 % (datasheet)",
        ),
        Figure(
            "load_error",
            "VREF: change that the load of the line makes",
            level - 2.5,
            "V",
        ),
        Figure(
            "supply_pin",
            "Supply pin of the reference behind R31, 3V3_A at 3.3 V",
            supply,
            "V",
            low=2.7,
            source="datasheet of the reference: supply of 2.7 V at least",
        ),
        Figure(
            "supply_current",
            "Current the reference takes from 3V3_A",
            -float(drawn.real("v3a#branch", plot="op")[0]),
            "A",
        ),
        Figure(
            "z_dc",
            "Impedance of the line at 1 Hz",
            float(np.interp(1.0, frequency, impedance)),
            "ohm",
        ),
        Figure("z_peak", "Largest impedance of the line", z_peak, "ohm"),
        Figure("f_peak", "Frequency of the largest impedance", f_peak, "Hz"),
        Figure(
            "z_peak_stiff",
            "Largest impedance, output stage of the model without its change with load",
            z_stiff,
            "ohm",
        ),
        Figure("f_peak_stiff", "Frequency of that peak", f_stiff, "Hz"),
        Figure(
            "z_peak_r35_short",
            "Largest impedance with R35 at 0 ohm",
            float(np.max(impedance_short)),
            "ohm",
        ),
        Figure(
            "z_peak_r35_most",
            "Largest impedance with R35 at 1.5 ohm",
            float(np.max(impedance_most)),
            "ohm",
        ),
        Figure(
            "z_100k",
            "Impedance of the line at 100 kHz, the sample rate",
            float(np.interp(1e5, frequency, impedance)),
            "ohm",
        ),
        Figure(
            "noise_floor",
            "Noise density of VREF at 100 Hz",
            floor,
            "V/√Hz",
        ),
        Figure(
            "noise_peak",
            "Noise density of VREF at its peak over the density at 100 Hz",
            float(np.max(density[noise_f > 100.0]) / floor),
            "",
        ),
        Figure(
            "noise_peak_stiff",
            "The same ratio, output stage without its change with load",
            float(
                np.max(density_stiff[noise_f > 100.0]) / np.interp(100.0, noise_f, density_stiff)
            ),
            "",
        ),
        Figure(
            "noise_10_100k",
            "Noise of VREF from 10 Hz to 100 kHz",
            measure.integrated_noise(noise_f, density, 10.0, 1e5),
            "V",
        ),
        Figure(
            "noise_10_100k_stiff",
            "Noise of VREF from 10 Hz to 100 kHz, output stage without its change with load",
            measure.integrated_noise(noise_f, density_stiff, 10.0, 1e5),
            "V",
        ),
        Figure(
            "noise_01_10",
            "White noise of VREF from 0.1 Hz to 10 Hz (the 1/f noise is not in the model)",
            measure.integrated_noise(noise_f, density, 0.1, 10.0),
            "V",
        ),
    ]
    tran = ctx.run("conversions", _transient_deck(ctx))
    time = tran.real("time")
    vref = tran.real("vref")
    pin = tran.real("ref_c89")
    final = measure.mean(time, vref, 0.24, 0.2499)
    last = (time >= 0.2530) & (time <= 0.2531)
    before = measure.mean(time, pin, 0.2495, 0.2499)
    figures += [
        near(
            "start_0p1",
            "VREF within 0.1 % after 3V3_A is applied",
            measure.settling_time(time, vref, final, 0.001 * 2.5, 0.1e-3, 0.24),
            "s",
            80e-3,
            0.2,
            "section 3, step 7 and rule F-3: about 80 ms",
        ),
        Figure(
            "pin_ripple",
            "REF pin of the converter: peak to peak at 100 kSPS",
            float(np.ptp(pin[last])),
            "V",
            high=38e-6,
            source="one step of the converter at 2.5 V: 38 uV (limit of this bench)",
        ),
        Figure(
            "pin_mean",
            "REF pin of the converter: mean while converting against the level before",
            float(np.mean(pin[last])) - before,
            "V",
        ),
        Figure(
            "line_ripple",
            "VREF at the reference: peak to peak at 100 kSPS",
            float(np.ptp(vref[last])),
            "V",
        ),
    ]
    impedance_graph = Graph(
        name="impedance",
        title="Impedance of the reference line, seen at the pin of the reference",
        xlabel="Frequency (Hz)",
        panels=(Panel("Impedance (ohm)", log=True), Panel("Noise density (nV/√Hz)", log=True)),
        traces=(
            Trace(frequency, impedance, "as drawn", 0),
            Trace(frequency, impedance_stiff, "output stage without change with load", 0, "--"),
            Trace(frequency, impedance_short, "R35 at 0 ohm", 0, ":"),
            Trace(frequency, impedance_most, "R35 at 1.5 ohm", 0, ":"),
            Trace(noise_f, density * 1e9, "as drawn", 1),
            Trace(noise_f, density_stiff * 1e9, "output stage without change with load", 1, "--"),
        ),
        logx=True,
    )
    shown = time <= 0.12
    start = Graph(
        name="start",
        title="Start of the reference when 3V3_A is applied",
        xlabel="Time (ms)",
        panels=(Panel("Voltage (V)", marks=((2.4975, "0.1 % below 2.5 V"),)),),
        traces=(
            Trace(time[shown] * 1e3, tran.real("p3v3_a")[shown], "3V3_A", 0),
            Trace(time[shown] * 1e3, tran.real("ref_in")[shown], "supply pin behind R31", 0),
            Trace(time[shown] * 1e3, tran.real("ref_nr")[shown], "noise pin with C24", 0),
            Trace(time[shown] * 1e3, vref[shown], "VREF", 0),
        ),
    )
    micro = (time[last] - 0.2530) * 1e6
    conversions = Graph(
        name="conversions",
        title="The converter takes 300 pC per conversion at 100 kSPS",
        xlabel="Time (us)",
        panels=(Panel("Around the mean (uV)"),),
        traces=(
            Trace(micro, (pin[last] - np.mean(pin[last])) * 1e6, "REF pin of the converter", 0),
            Trace(micro, (vref[last] - np.mean(vref[last])) * 1e6, "VREF at the reference", 0),
        ),
    )
    notes = (
        "The output impedance of the reference model is a fit to two figures of the "
        "datasheet and not a datasheet curve: an inductance of 253 uH without load that "
        "falls as the load rises. With the 0.9 mA that the line draws it is about 33 uH, "
        "and the capacitors of the line resonate with it. The second set of figures "
        "holds the inductance at 253 uH whatever the load: the cautious case.",
        "A peak of the noise density above the level at 100 Hz is the gain peaking that "
        "the datasheet of the reference warns of when the capacitor has too little "
        "series resistance. C89 with its 0.22 ohm is the larger capacitor of the line, "
        "so R35 in front of C26 changes little.",
        "The line carries 0.63 mA into the divider of the set-point converter, the "
        "dividers of the monitors and 0.15 mA for the dividers that are not in this "
        "circuit. C89 is linear at 22 uF here; the specification expects about 14 uF "
        "under bias, which moves the peak up in frequency by about a quarter.",
        "The noise is white only: the 0.1 Hz to 10 Hz noise of the part (3 uV peak to "
        "peak per volt, datasheet) is not in the model.",
    )
    return Outcome(tuple(figures), (impedance_graph, start, conversions), notes)
