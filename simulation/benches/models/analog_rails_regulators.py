"""The models of the +12V_A regulator and of the reference against their datasheets."""

from __future__ import annotations

import numpy as np

from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.engine import RunResult

_LIBRARY = ("analog_rails.lib",)
"""The model file of the analog rails."""

_REJECTION = ((120.0, 117.0), (10e3, 91.0), (100e3, 78.0), (1e6, 79.0))
"""Ripple rejection of the LT3042 by frequency (datasheet rev. C, page 4), in dB."""


def _nodeset(run: RunResult) -> str:
    """The end of a settled transient run as the start of an operating point."""
    lines = []
    for key in sorted(run.vectors):
        plot, name = key.split("/", 1)
        if plot.startswith("tran") and name != "time" and "#" not in name and "@" not in name:
            lines.append(f".nodeset v({name})={float(run.vectors[key].real[-1]):.9g}")
    return "\n".join(lines)


def _lt3042_start_deck(ctx: Context) -> str:
    """The two start-up circuits of the datasheet table and a slow sweep of the enable pin."""
    lines = [
        "* 5 V of output, 4.7 uF at SET, 25 ohm of load, 6 V of input (datasheet page 4)",
        "Vin in 0 PWL(0 0 1m 6)",
        "Ven en 0 PWL(0 0 5m 0 5.001m 3)",
        "* A: fast start-up to 90 % through 50 kohm and 700 kohm at PGFB",
        "Xa in en pga 0 fba seta 0 oa oa LT3042",
        "Rseta seta 0 49.9k",
        "Cseta seta 0 4.7u",
        "Rpa2 oa fba 700k",
        "Rpa1 fba 0 50k",
        "Coa oa 0 4.7u",
        "Rla oa 0 25",
        "* B: PGFB tied to the input, no fast start-up",
        "Xb in en pgb 0 in setb 0 ob ob LT3042",
        "Rsetb setb 0 49.9k",
        "Csetb setb 0 4.7u",
        "Cob ob 0 4.7u",
        "Rlb ob 0 25",
        "* C: the enable pin swept up and down, 3.3 V of output, no SET capacitor",
        "Vinc inc 0 PWL(0 0 1m 5)",
        "Venc enc 0 PWL(0 0 1.4 0 1.5 1.5 1.6 0)",
        "Xc inc enc pgc 0 inc setc 0 oc oc LT3042",
        "Rsetc setc 0 33.2k",
        "Coc oc 0 4.7u",
        "Rlc oc 0 330",
    ]
    return ctx.deck(
        "LT3042: start-up with and without fast start-up, enable thresholds",
        "\n".join(lines),
        control=["save oa ob oc seta setb en enc in", "tran 50u 1.62 0 50u"],
        libraries=_LIBRARY,
    )


def _lt3042_limit_deck(ctx: Context) -> str:
    """Dropout at two currents and the current limit at two voltages across the part."""
    lines = [
        "* dropout: the input falls slowly from 6 V, the load is a current sink",
        "Vd ind 0 PWL(0 0 1m 6 10m 6 0.21 4.5)",
        "Vend end 0 PWL(0 0 2m 3)",
        "Xd1 ind end pgd1 0 ind setd1 0 od1 od1 LT3042",
        "Rsetd1 setd1 0 49.9k",
        "Cod1 od1 0 4.7u",
        "Id1 od1 0 PWL(0 0 5m 0 6m 0.2)",
        "Xd2 ind end pgd2 0 ind setd2 0 od2 od2 LT3042",
        "Rsetd2 setd2 0 49.9k",
        "Cod2 od2 0 4.7u",
        "Id2 od2 0 PWL(0 0 5m 0 6m 0.05)",
        "* current limit: the output held at 0 V, 12 V and 20 V at the input",
        "Vl12 inl12 0 PWL(0 0 1m 12)",
        "Xl12 inl12 end pgl1 0 inl12 setl1 0 ol12 ol12 LT3042",
        "Rsetl1 setl1 0 49.9k",
        "Vs12 ol12 0 0",
        "Vl20 inl20 0 PWL(0 0 1m 20)",
        "Xl20 inl20 end pgl2 0 inl20 setl2 0 ol20 ol20 LT3042",
        "Rsetl2 setl2 0 49.9k",
        "Vs20 ol20 0 0",
    ]
    return ctx.deck(
        "LT3042: dropout and current limit",
        "\n".join(lines),
        control=["save ind od1 od2 i(Vs12) i(Vs20)", "tran 50u 0.21 0 50u"],
        libraries=_LIBRARY,
    )


def _lt3042_small_circuit() -> list[str]:
    return [
        "* 3.3 V of output, 2 V across the part, 200 mA, 4.7 uF at the output and at SET",
        "X1 in en pg 0 in set 0 out out LT3042",
        "Rset set 0 33.2k",
        "Cset set 0 4.7u",
        "Cout out 0 4.7u",
        "Rload out 0 16.5",
    ]


@bench(
    "models",
    "analog-rails-lt3042",
    "LT3042 model against its datasheet",
    "the model of the +12V_A regulator U13",
)
def lt3042(ctx: Context) -> Outcome:
    """The model is put in the test circuits of the datasheet table.

    Start-up with 4.7 uF at the SET pin, with and without the fast start-up;
    the thresholds of the enable pin; the dropout at 50 mA and 200 mA; the
    current limit at 12 V and 20 V across the part; the ripple rejection at
    four frequencies and the output noise, both with 4.7 uF at the output
    and at the SET pin and 200 mA of load.
    """
    start = ctx.run("start", _lt3042_start_deck(ctx))
    time = start.real("time")
    fast = measure.first_crossing(time, start.real("oa"), 4.5, rising=True) - 5e-3
    slow = measure.first_crossing(time, start.real("ob"), 4.5, rising=True) - 5e-3
    enable = start.real("enc")
    out_c = start.real("oc")
    rises = measure.first_crossing(time, out_c, 1.65, rising=True, after=1.4)
    falls = measure.first_crossing(time, out_c, 1.65, rising=False, after=1.5)
    limit = ctx.run("limits", _lt3042_limit_deck(ctx))
    t2 = limit.real("time")
    supply = limit.real("ind")

    def dropout(node: str) -> float:
        out = limit.real(node)
        level = measure.value_at(t2, out, 9e-3)
        lost = measure.first_crossing(t2, out, 0.99 * level, rising=False, after=10e-3)
        return float(np.interp(lost, t2, supply)) - 0.99 * level

    settle = ctx.run(
        "small-settle",
        ctx.deck(
            "LT3042: brought up for the small-signal run",
            "\n".join(
                [
                    "Vin in 0 PWL(0 0 1m 5.3)",
                    "Ven en 0 PWL(0 0 2m 0 2.001m 3)",
                    *_lt3042_small_circuit(),
                ]
            ),
            control=["save all", "tran 50u 1.5 0 100u"],
            libraries=_LIBRARY,
        ),
        keep=False,
    )
    small = ctx.run(
        "small-signal",
        ctx.deck(
            "LT3042: ripple rejection and noise",
            "\n".join(["Vin in 0 DC 5.3 AC 1", "Ven en 0 3", *_lt3042_small_circuit()]),
            _nodeset(settle),
            control=["op", "noise v(out) Vin dec 30 1 10meg", "ac dec 30 1 10meg"],
            libraries=_LIBRARY,
        ),
    )
    frequency = small.real("frequency", plot="ac")
    rejection = -measure.decibels(small.vector("out", plot="ac"))
    noise_f = small.real("frequency", plot="noise1")
    density = small.real("onoise_spectrum", plot="noise1")
    figures = [
        near(
            "start_fast",
            "Start to 90 % of 5 V with fast start-up, 4.7 uF at SET",
            fast,
            "s",
            10e-3,
            0.2,
            "datasheet rev. C page 4: 10 ms",
        ),
        near(
            "start_slow",
            "Start to 90 % of 5 V without fast start-up, 4.7 uF at SET",
            slow,
            "s",
            0.55,
            0.1,
            "datasheet rev. C page 4: 550 ms",
        ),
        near(
            "enable_on",
            "Enable pin at which the output comes",
            float(np.interp(rises, time, enable)),
            "V",
            1.24,
            0.03,
            "datasheet rev. C page 4: 1.24 V rising",
        ),
        near(
            "enable_off",
            "Enable pin at which the output goes",
            float(np.interp(falls, time, enable)),
            "V",
            1.07,
            0.05,
            "datasheet rev. C page 4: 170 mV of hysteresis",
        ),
        Figure(
            "dropout_50",
            "Dropout at 50 mA",
            dropout("od2"),
            "V",
            expected=0.22,
            high=0.30,
            source="datasheet rev. C page 3: 220 mV typical, 300 mV at most",
        ),
        near(
            "dropout_200",
            "Dropout at 200 mA",
            dropout("od1"),
            "V",
            0.35,
            0.2,
            "datasheet rev. C page 3: 350 mV typical",
        ),
        near(
            "limit_12",
            "Current limit with 12 V across the part",
            float(limit.real("vs12#branch")[-1]),
            "A",
            0.30,
            0.05,
            "datasheet rev. C page 4: 300 mA",
        ),
        near(
            "limit_20",
            "Current limit with 20 V across the part",
            float(limit.real("vs20#branch")[-1]),
            "A",
            0.18,
            0.05,
            "datasheet rev. C page 4: 180 mA",
        ),
    ]
    for hertz, expected in _REJECTION:
        figures.append(
            Figure(
                f"rejection_{hertz:g}".replace("+", ""),
                f"Ripple rejection at {hertz:g} Hz",
                float(np.interp(np.log10(hertz), np.log10(frequency), rejection)),
                "dB",
                expected=expected,
                low=expected - 4.0,
                high=expected + 4.0,
                source="datasheet rev. C page 4 (fit of the model: 4 dB)",
            )
        )
    figures += [
        near(
            "noise_10k",
            "Output noise density at 10 kHz",
            float(np.interp(1e4, noise_f, density)),
            "V/√Hz",
            2e-9,
            0.15,
            "datasheet rev. C page 3: 2 nV/rtHz",
        ),
        Figure(
            "noise_10",
            "Output noise density at 10 Hz, 4.7 uF at SET",
            float(np.interp(10.0, noise_f, density)),
            "V/√Hz",
            expected=60e-9,
            low=40e-9,
            high=90e-9,
            source="datasheet rev. C page 3: 60 nV/rtHz",
        ),
        near(
            "noise_rms",
            "Output noise from 10 Hz to 100 kHz, 4.7 uF at SET",
            measure.integrated_noise(noise_f, density, 10.0, 1e5),
            "V",
            0.8e-6,
            0.25,
            "datasheet rev. C page 3: 0.8 uV RMS",
        ),
    ]
    shown = (time >= 0.0) & (time <= 0.9)
    graph = Graph(
        name="start",
        title="LT3042: start to 5 V with 4.7 uF at SET",
        xlabel="Time (s)",
        panels=(Panel("Output (V)", marks=((4.5, "90 %"),)),),
        traces=(
            Trace(time[shown], start.real("oa")[shown], "fast start-up", 0),
            Trace(time[shown], start.real("ob")[shown], "no fast start-up", 0),
        ),
    )
    spectrum = Graph(
        name="rejection",
        title="LT3042: ripple rejection and output noise, 200 mA",
        xlabel="Frequency (Hz)",
        panels=(Panel("Ripple rejection (dB)"), Panel("Noise density (nV/√Hz)", log=True)),
        traces=(
            Trace(frequency, rejection, "model", 0),
            Trace(
                np.array([point[0] for point in _REJECTION]),
                np.array([point[1] for point in _REJECTION]),
                "datasheet",
                0,
                ":",
            ),
            Trace(noise_f, density * 1e9, "model", 1),
        ),
        logx=True,
    )
    notes = (
        "The limits are the fit this project asks of the model, not datasheet limits, "
        "except where the datasheet gives a maximum.",
        "Above the bandwidth of its output stage the model rejects more than the 56 dB "
        "that the datasheet gives at 10 MHz; that point is not checked.",
        "The loop of the regulator is one pole with an integral part: the model says "
        "nothing about stability with a given capacitor.",
    )
    return Outcome(tuple(figures), (graph, spectrum), notes)


def _ref_tran_deck(ctx: Context) -> str:
    lines = [
        "Vin vin 0 PWL(0 0 10u 0 12u 5)",
        "* A: 1 uF at the output, load stepped between -1 mA and +1 mA",
        "Xa vin 0 nra oa REF5025AID",
        "Ca oa 0 1u",
        "Ia oa 0 PWL(0 0 3m 0 3.001m -1m 4m -1m 4.001m 1m 5m 1m 5.001m -1m)",
        "* B: 10 uF at the output",
        "Xb vin 0 nrb ob REF5025AID",
        "Cb ob 0 10u",
        "* C: 1 uF at the noise pin",
        "Xc vin 0 nrc oc REF5025AID",
        "Cc oc 0 1u",
        "Cnr nrc 0 1u",
    ]
    return ctx.deck(
        "REF5025: start with 1 uF and 10 uF, with a noise capacitor, load step",
        "\n".join(lines),
        control=["save oa ob oc vin", "tran 0.2u 0.12 0 20u"],
        libraries=_LIBRARY,
        options=("reltol=1e-5",),
    )


def _ref_static_deck(ctx: Context) -> str:
    lines = [
        "Vin vin 0 DC 5 AC 0",
        "* without load, sourcing 10 mA, sinking 10 mA",
        "X0 vin 0 nr0 o0 REF5025AID",
        "C0 o0 0 1u",
        "Xp vin 0 nrp op REF5025AID",
        "Ip op 0 10m",
        "Xn vin 0 nrn on REF5025AID",
        "In 0 on 10m",
        "* line: 18 V at the input",
        "Vhi vhi 0 18",
        "Xh vhi 0 nrh oh REF5025AID",
        "* dropout: 10 mA from a supply 0.45 V above the nominal output",
        "Vlo vlo 0 2.95",
        "Xl vlo 0 nrl ol REF5025AID",
        "Il ol 0 10m",
        "* with the noise capacitor",
        "Xc vin 0 nrc oc REF5025AID",
        "Cc oc 0 1u",
        "Cnr nrc 0 1u",
    ]
    return ctx.deck(
        "REF5025: level, regulation, supply current and noise",
        "\n".join(lines),
        control=[
            "op",
            "noise v(o0) Vin dec 40 1 100k",
            "noise v(oc) Vin dec 40 1 100k",
        ],
        libraries=_LIBRARY,
    )


@bench(
    "models",
    "analog-rails-ref5025",
    "REF5025 model against its datasheet",
    "the model of the reference U12",
)
def ref5025(ctx: Context) -> Outcome:
    """The model is put in the conditions of the datasheet table and figures.

    Level, load and line regulation, dropout and supply current as an
    operating point; the noise from 10 Hz to 1 kHz with 1 uF at the output,
    with and without a capacitor at the noise pin; the start with 1 uF and
    with 10 uF at the output and with 1 uF at the noise pin; a load step
    between -1 mA and +1 mA.
    """
    static = ctx.run("static", _ref_static_deck(ctx))

    def at(node: str) -> float:
        return float(static.real(node, plot="op")[0])

    noise_f = static.real("frequency", plot="noise1")
    bare = static.real("onoise_spectrum", plot="noise1")
    quiet = static.real("onoise_spectrum", plot="noise3")
    floor = float(np.interp(1e3, noise_f, bare))
    tran = ctx.run("transient", _ref_tran_deck(ctx))
    time = tran.real("time")
    oa, ob, oc = tran.real("oa"), tran.real("ob"), tran.real("oc")
    figures = [
        near("level", "Output without load", at("o0"), "V", 2.5, 0.001, "SBOS410O page 7: 2.5 V"),
        near(
            "load_source",
            "Load regulation, sourcing 10 mA",
            (at("o0") - at("op")) / 10e-3 / 2.5 * 1e6 / 1e3,
            "ppm/mA",
            20.0,
            0.25,
            "SBOS410O page 7: 20 ppm/mA typical",
        ),
        near(
            "load_sink",
            "Load regulation, sinking 10 mA",
            (at("on") - at("o0")) / 10e-3 / 2.5 * 1e6 / 1e3,
            "ppm/mA",
            20.0,
            0.25,
            "SBOS410O page 7: 20 ppm/mA typical",
        ),
        near(
            "line",
            "Line regulation, 5 V to 18 V",
            (at("oh") - at("o0")) / 13.0 / 2.5 * 1e6,
            "ppm/V",
            1.0,
            0.25,
            "SBOS410O page 7: 1 ppm/V typical",
        ),
        Figure(
            "dropout",
            "Output with 10 mA and 0.45 V of head room: fall below 2.5 V",
            2.5 - at("ol"),
            "V",
            low=0.05,
            high=0.15,
            source="SBOS410O page 11, figure 6-6: 0.55 V of dropout at 10 mA, so 0.1 V are "
            "missing here",
        ),
        near(
            "supply_current",
            "Supply current without load",
            -float(static.real("vhi#branch", plot="op")[0]),
            "A",
            0.8e-3,
            0.1,
            "SBOS410O page 8: 0.8 mA typical",
        ),
        near(
            "noise_1k",
            "Noise from 10 Hz to 1 kHz, no capacitor at the noise pin",
            measure.integrated_noise(noise_f, bare, 10.0, 1e3),
            "V",
            2.25e-6,
            0.1,
            "SBOS410O page 7: 0.9 uV RMS per volt",
        ),
        near(
            "noise_ratio",
            "The same with 1 uF at the noise pin, as a share",
            measure.integrated_noise(noise_f, quiet, 20.0, 1e3)
            / measure.integrated_noise(noise_f, bare, 20.0, 1e3),
            "",
            0.5,
            0.2,
            "SBOS410O page 26: the capacitor halves the noise",
        ),
        Figure(
            "noise_peak",
            "Peak of the noise density over the density at 1 kHz, 1 uF at the output",
            float(np.max(bare)) / floor,
            "",
            expected=2.1,
            low=1.6,
            high=2.7,
            source="SBOS410O page 13, figure 6-14: about 58 over 27 nV/V/rtHz",
        ),
        Figure(
            "noise_peak_at",
            "Frequency of that peak",
            float(noise_f[int(np.argmax(bare))]),
            "Hz",
            expected=10e3,
            low=7e3,
            high=14e3,
            source="SBOS410O page 13, figure 6-14: about 10 kHz",
        ),
        near(
            "start_1u",
            "Start with 1 uF: from 10 % to 90 %",
            measure.rise_time(time, oa, 0.25, 2.25),
            "s",
            108e-6,
            0.3,
            "SBOS410O page 13, figure 6-15: 2.5 V in about 135 us",
        ),
        near(
            "start_10u",
            "Start with 10 uF: from 10 % to 90 %",
            measure.rise_time(time, ob, 0.25, 2.25),
            "s",
            0.96e-3,
            0.3,
            "SBOS410O page 13, figure 6-16: 2.5 V in about 1.2 ms",
        ),
        Figure(
            "settle_1u",
            "Start with 1 uF: within 0.1 % after the supply",
            measure.settling_time(time, oa, 2.5, 2.5e-3, 12e-6, 2.9e-3),
            "s",
            expected=200e-6,
            high=400e-6,
            source="SBOS410O page 8: 200 us typical",
        ),
        Figure(
            "start_nr",
            "Start with 1 uF at the noise pin: within 0.1 % after the supply",
            measure.settling_time(time, oc, 2.5, 2.5e-3, 12e-6),
            "s",
            expected=75e-3,
            low=55e-3,
            high=110e-3,
            source="SBOS410O pages 23 and 26: 11 kohm with 1 uF, a corner of 10 Hz to 20 Hz",
        ),
        Figure(
            "load_step",
            "Step from -1 mA to +1 mA with 1 uF: largest deviation",
            float(np.max(np.abs(oa[(time > 4e-3) & (time < 4.5e-3)] - 2.5))),
            "V",
            expected=8e-3,
            low=4e-3,
            high=16e-3,
            source="SBOS410O page 13, figure 6-17: about 8 mV (read from the figure)",
        ),
    ]
    shown = time <= 2e-3
    graph = Graph(
        name="start",
        title="REF5025: start after the supply is applied",
        xlabel="Time (ms)",
        panels=(Panel("Output (V)"),),
        traces=(
            Trace(time[shown] * 1e3, oa[shown], "1 uF at the output", 0),
            Trace(time[shown] * 1e3, ob[shown], "10 uF at the output", 0),
            Trace(time[shown] * 1e3, oc[shown], "1 uF at the noise pin", 0),
        ),
    )
    spectrum = Graph(
        name="noise",
        title="REF5025: noise density with 1 uF at the output",
        xlabel="Frequency (Hz)",
        panels=(Panel("Noise density (nV/√Hz)", log=True),),
        traces=(
            Trace(noise_f, bare * 1e9, "noise pin open", 0),
            Trace(noise_f, quiet * 1e9, "1 uF at the noise pin", 0),
        ),
        logx=True,
    )
    notes = (
        "The limits are the fit this project asks of the model. The figures read from "
        "graphs of the datasheet (start, load step, noise peak) carry the reading error "
        "of those graphs.",
        "The output impedance of the model is fitted to the noise peak and to the load "
        "step; the datasheet has no curve of it for this grade.",
        "The noise below 10 Hz (3 uV peak to peak per volt in the datasheet) is not in the model.",
    )
    return Outcome(tuple(figures), (graph, spectrum), notes)
