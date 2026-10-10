"""The small parts of the source meter against the figures of their datasheets."""

from __future__ import annotations

import numpy as np

from benches.source_meter import common
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_DIODE = "D11"
_FET = "Q1"
_BEAD = "FB1"
_INDUCTOR = "L2"

_DIODE_DOCUMENT = "Diodes Incorporated DS30217 Rev. 22-2"
_FET_DOCUMENT = "Diodes Incorporated DS30144 Rev. 25-2"
_BEAD_DOCUMENT = "Murata JENF243A-0006Z-01"
_INDUCTOR_DOCUMENT = "Coilcraft document 745-1"

_FORWARD = ((1e-4, 0.092), (1e-3, 0.150), (1e-2, 0.222), (0.1, 0.289), (1.0, 0.420))
"""Forward current and typical forward voltage at 25 C, read from figure 1 of page 3."""

_SATURATION = ((2.5, 0.19), (3.0, 0.36), (3.5, 0.545))
"""Gate voltage and drain current in saturation, read from figure 1 of page 3."""


def _diode_deck(ctx: Context, name: str = "") -> str:
    """Forward voltage at five currents."""
    found = ctx.netlist.component(_DIODE)
    aliases = {found.net_of("2"): "a", found.net_of("1"): "k"}
    overrides = {_DIODE: common.device(ctx, _DIODE, name)} if name else None
    circuit = ctx.circuit([_DIODE], aliases, overrides)
    stimulus = "* cathode grounded, forward current forced\nVk k 0 0\nIf 0 a 1m\n"
    control: list[str] = []
    for amps, _ in _FORWARD:
        control += [f"alter If dc = {amps:g}", "op"]
    return ctx.deck("1N5819HW: forward voltage", circuit, stimulus, control=control)


def _diode_capacitance_deck(ctx: Context) -> str:
    """4 V in reverse with a test voltage of 1 MHz on the cathode."""
    found = ctx.netlist.component(_DIODE)
    aliases = {found.net_of("2"): "a", found.net_of("1"): "k"}
    circuit = ctx.circuit([_DIODE], aliases)
    stimulus = (
        "* anode grounded, 4 V and the test voltage on the cathode\nVa a 0 0\nVk k 0 dc 4 ac 1\n"
    )
    return ctx.deck("1N5819HW: capacitance", circuit, stimulus, control=["ac lin 1 1meg 1meg"])


def _fet_deck(ctx: Context, name: str = "") -> str:
    """On-resistance at 10 V on the gate."""
    found = ctx.netlist.component(_FET)
    aliases = {found.net_of("3"): "d", found.net_of("1"): "g", found.net_of("2"): "s"}
    overrides = {_FET: common.device(ctx, _FET, name)} if name else None
    circuit = ctx.circuit([_FET], aliases, overrides)
    stimulus = (
        "* source grounded, 10 V on the gate, drain current forced\n"
        "Vs s 0 0\nVg g 0 10\nId 0 d 0.22\n"
    )
    return ctx.deck("BSS138: on-resistance", circuit, stimulus, control=["op"])


def _fet_threshold_deck(ctx: Context, name: str = "") -> str:
    found = ctx.netlist.component(_FET)
    aliases = {found.net_of("3"): "d", found.net_of("1"): "g", found.net_of("2"): "s"}
    overrides = {_FET: common.device(ctx, _FET, name)} if name else None
    circuit = ctx.circuit([_FET], aliases, overrides)
    stimulus = "* gate tied to drain, drain current forced\nVs s 0 0\nVgd g d 0\nId 0 d 250u\n"
    control = ["op", "alter Id dc = 1m", "op", "alter Id dc = 3.3m", "op"]
    return ctx.deck("BSS138: threshold", circuit, stimulus, control=control)


def _fet_curve_deck(ctx: Context) -> str:
    found = ctx.netlist.component(_FET)
    aliases = {found.net_of("3"): "d", found.net_of("1"): "g", found.net_of("2"): "s"}
    circuit = ctx.circuit([_FET], aliases)
    stimulus = "* drain at 5 V, gate swept\nVs s 0 0\nVd d 0 5\nVg g 0 2.5\n"
    return ctx.deck("BSS138: transfer curve", circuit, stimulus, control=["dc Vg 0.5 3.6 0.01"])


def _impedance_deck(ctx: Context, ref: str, title: str) -> str:
    """1 A of test current through a two-terminal part, over the frequency."""
    found = ctx.netlist.component(ref)
    aliases = {found.net_of("1"): "a", found.net_of("2"): "b"}
    circuit = ctx.circuit([ref], aliases)
    stimulus = "* 1 A through the part, the far end grounded\nVb b 0 0\nItest 0 a dc 0 ac 1\n"
    return ctx.deck(title, circuit, stimulus, control=["ac dec 40 100 300meg"])


@bench(
    "models",
    "source-meter-parts",
    "Diode, transistor, bead and inductor of the source meter against their datasheets",
    "the models of D11 and D12, Q1, FB1 and L2",
)
def parts(ctx: Context) -> Outcome:
    """Four parts of the schematic are put in the test conditions of their datasheets.

    The Schottky diode D11 carries a forced current, which gives its
    forward voltage from 0.1 mA to 1 A, and stands at 4 V in reverse for
    its capacitance. The transistor Q1 gives its threshold, its
    on-resistance and its current in saturation. The bead FB1 and the
    inductor L2 carry a test current over the frequency, which gives their
    impedance.
    """
    figures: list[Figure] = []
    diode = ctx.run("diode", _diode_deck(ctx))
    forward = np.array([float(diode.real("a", f"op{i + 1}")[0]) for i in range(len(_FORWARD))])
    for (amps, typical), volts in zip(_FORWARD, forward, strict=True):
        figures.append(
            near(
                f"forward_{amps * 1e3:g}ma".replace(".", "p"),
                f"1N5819HW: forward voltage at {amps * 1e3:g} mA",
                float(volts),
                "V",
                typical,
                0.10,
                f"{_DIODE_DOCUMENT}, page 3, figure 1, typical at 25 C",
            )
        )
    reverse = ctx.run("diode-capacitance", _diode_capacitance_deck(ctx), keep=False)
    capacitance = float(-np.imag(reverse.vector("vk#branch")[0]) / (2.0 * np.pi * 1e6))
    figures.append(
        near(
            "diode_capacitance",
            "1N5819HW: capacitance at 4 V in reverse",
            capacitance,
            "F",
            50e-12,
            0.20,
            f"{_DIODE_DOCUMENT}, page 2: 50 pF typical, 60 pF at the most",
        )
    )
    high = ctx.run("diode-high", _diode_deck(ctx, "SOURCE_METER_1N5819HW_HI"), keep=False)
    figures.append(
        near(
            "forward_high_100ma",
            "1N5819HW, variant at the limit: forward voltage at 100 mA",
            float(high.real("a", "op4")[0]),
            "V",
            0.32,
            0.05,
            f"{_DIODE_DOCUMENT}, page 2: 0.32 V at the most",
        )
    )

    on = ctx.run("fet-on", _fet_deck(ctx))
    figures.append(
        Figure(
            "fet_on",
            "BSS138: on-resistance at 10 V and 0.22 A",
            float(on.real("d")[0]) / 0.22,
            "ohm",
            expected=1.4,
            low=1.2,
            high=3.5,
            source=f"{_FET_DOCUMENT}, page 2: 1.4 ohm typical, 3.5 ohm at the most",
        )
    )
    for name, text, expected in (
        ("", "typical", 1.2),
        ("SOURCE_METER_BSS138_LO", "lower limit", 0.5),
        ("SOURCE_METER_BSS138_HI", "upper limit", 1.5),
    ):
        run = ctx.run(
            f"fet-threshold-{text.split()[0]}", _fet_threshold_deck(ctx, name), keep=False
        )
        figures.append(
            Figure(
                f"fet_threshold_{text.split()[0]}",
                f"BSS138, {text}: gate voltage at 250 uA",
                float(run.real("d", "op1")[0]),
                "V",
                expected=expected,
                low=expected - 0.16,
                high=expected + 0.05,
                source=f"{_FET_DOCUMENT}, page 2: 0.5 / 1.2 / 1.5 V; figure 4: 1.05 V typical",
            )
        )
        if not name:
            figures.append(
                Figure(
                    "fet_follower",
                    "BSS138, typical: gate voltage at 3.3 mA, the current of R53",
                    float(run.real("d", "op3")[0]),
                    "V",
                )
            )
    curve = ctx.run("fet-curve", _fet_curve_deck(ctx))
    gate = curve.real("g")
    drain_amps = -curve.real("vd#branch")
    for volts, amps in _SATURATION:
        figures.append(
            near(
                f"fet_saturation_{volts:g}v".replace(".", "p"),
                f"BSS138: drain current in saturation at {volts:g} V on the gate",
                float(np.interp(volts, gate, drain_amps)),
                "A",
                amps,
                0.10,
                f"{_FET_DOCUMENT}, page 3, figure 1",
            )
        )

    bead = ctx.run("bead", _impedance_deck(ctx, _BEAD, "BLM31SN500: impedance"))
    coil = ctx.run("inductor", _impedance_deck(ctx, _INDUCTOR, "XFL4020-152: impedance"))
    frequency = bead.real("frequency")
    bead_ohms = np.abs(bead.vector("a"))
    coil_ohms = np.abs(coil.vector("a"))
    resonance = float(frequency[int(np.argmax(coil_ohms))])
    figures += [
        near(
            "bead_100mhz",
            "BLM31SN500: impedance at 100 MHz",
            float(np.interp(100e6, frequency, bead_ohms)),
            "ohm",
            50.0,
            0.25,
            f"{_BEAD_DOCUMENT}, page 1: 50 ohm +/-25 %",
        ),
        Figure(
            "bead_dc",
            "BLM31SN500: resistance at 100 Hz",
            float(bead_ohms[0]),
            "ohm",
            high=1.6e-3 * 1.02,
            source=f"{_BEAD_DOCUMENT}, page 1: 1.6 mohm at the most",
        ),
        near(
            "inductance",
            "XFL4020-152: inductance at 100 kHz",
            float(np.interp(100e3, frequency, np.imag(coil.vector("a")))) / (2.0 * np.pi * 100e3),
            "H",
            1.5e-6,
            0.02,
            f"{_INDUCTOR_DOCUMENT}, page 1: 1.5 uH +/-20 %",
        ),
        near(
            "inductor_dc",
            "XFL4020-152: resistance at 100 Hz",
            float(coil_ohms[0]),
            "ohm",
            14.4e-3,
            0.02,
            f"{_INDUCTOR_DOCUMENT}, page 1: 14.4 mohm typical, 15.8 mohm at the most",
        ),
        near(
            "inductor_resonance",
            "XFL4020-152: self-resonance",
            resonance,
            "Hz",
            59e6,
            0.10,
            f"{_INDUCTOR_DOCUMENT}, page 1: 59 MHz typical",
        ),
    ]
    currents = np.array([amps for amps, _ in _FORWARD])
    graphs = (
        Graph(
            name="diode",
            title="1N5819HW model: forward voltage over the current",
            xlabel="Forward current (A)",
            panels=(Panel("Forward voltage (mV)"),),
            traces=(
                Trace(currents, forward * 1e3, "model", 0),
                Trace(
                    currents,
                    np.array([volts for _, volts in _FORWARD]) * 1e3,
                    "datasheet, typical at 25 C",
                    0,
                    ":",
                ),
            ),
            logx=True,
        ),
        Graph(
            name="impedance",
            title="Bead FB1 and inductor L2: impedance over the frequency",
            xlabel="Frequency (Hz)",
            panels=(Panel("Impedance (ohm)", log=True),),
            traces=(
                Trace(frequency, bead_ohms, "BLM31SN500", 0),
                Trace(frequency, coil_ohms, "XFL4020-152", 0),
            ),
            logx=True,
        ),
    )
    notes = (
        "The limits are the fit this project asks of a model: 10 % on a forward "
        "voltage and on a drain current. Limits of a datasheet are named as such.",
        "The diode model has 4 uA of reverse current where the datasheet states 10 uA "
        "typical at 4 V and up to 2 mA at 100 C: no leakage figure may be taken from it.",
        "The inductance of the bead below the frequency at which it turns resistive "
        "(0.2 uH) is an assumption: its reference specification has no curve.",
        "The BSS138 model is fitted for the use of Q1, a source follower at a few "
        "milliamperes; it is not fitted to the on-resistance at low gate voltage.",
    )
    return Outcome(tuple(figures), graphs, notes)
