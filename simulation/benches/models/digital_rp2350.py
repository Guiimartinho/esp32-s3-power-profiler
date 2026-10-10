"""The models of the controller module against the figures of its datasheets."""

from __future__ import annotations

import numpy as np

from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near

_PAD = "RP2350 datasheet, table 1683 (page 1336)"
_ERRATUM = "RP2350 datasheet, erratum E9 (pages 1358 and 1359)"
_MODULE = "Pico 2 datasheet, figure 7 (page 15)"
_DIODE = "Nexperia PMEG6010ELR of 1 January 2023, page 4"


def _static_deck(ctx: Context) -> str:
    lines = [
        "* pads at the 4 mA setting with 4 mA drawn and fed; a released pad with",
        "* its pull-down; a standard pad pulled above the 3.3 V of the module",
        "Viovdd iovdd 0 3.3",
        "Vhi hi 0 1",
        "Vlo lo 0 0",
        "X1 p1 hi hi iovdd 0 DIGITAL_RP2350_PAD",
        "I1 p1 0 4m",
        "X2 p2 lo hi iovdd 0 DIGITAL_RP2350_PAD",
        "I2 0 p2 4m",
        "X3 p3 lo lo iovdd 0 DIGITAL_RP2350_PAD rpd=36k",
        "V3 p3 0 3.3",
        "X4 p4 lo lo iovdd 0 DIGITAL_RP2350_PAD_STD",
        "I4 0 p4 1m",
        "* a released pad of stepping A2 with its input enabled: the voltage is",
        "* stepped and the current out of the pad is read",
        "X5 p5 lo lo iovdd 0 DIGITAL_RP2350_PAD e9=1",
        "V5 p5 0 0",
    ]
    return ctx.deck(
        "RP2350 pad: levels, pull-down and the current of erratum E9",
        "\n".join(lines),
        control=["dc V5 0 3.3 0.02"],
        libraries=("digital.lib",),
    )


def _release_deck(ctx: Context) -> str:
    """Pads of stepping A2 that are driven high and then released onto a pull-down."""
    lines = ["Viovdd iovdd 0 3.3", "Vhi hi 0 1", "Voe oe 0 PWL(0 1 1u 1 1.001u 0)"]
    for name, ohms in (("a", 4.7e3), ("b", 8.2e3), ("c", 47e3)):
        lines += [
            f"X{name} p{name} hi oe iovdd 0 DIGITAL_RP2350_PAD e9=1",
            f"R{name} p{name} 0 {ohms:g}",
            f"C{name} p{name} 0 10p",
        ]
    return ctx.deck(
        "RP2350 pad of stepping A2: released onto 4.7 kohm, 8.2 kohm and 47 kohm",
        "\n".join(lines),
        control=["tran 2n 12u"],
        libraries=("digital.lib",),
    )


def _supply_deck(ctx: Context) -> str:
    lines = [
        "* module fed from its own connector: 5 V on VBUS, nothing else on VSYS",
        "Vbus vbus 0 5",
        "X1 vbus vsys 0 DIGITAL_PICO2_SUPPLY",
        "* module fed at VSYS: its diode blocks and its divider holds VBUS low",
        "Vsys wsys 0 5",
        "X2 wbus wsys 0 DIGITAL_PICO2_SUPPLY",
        "* the diode alone at the currents of its datasheet",
        "Id 0 da 0.1",
        "Dd da 0 DIGITAL_PMEG6010",
        "Ie 0 ea 1",
        "De ea 0 DIGITAL_PMEG6010",
    ]
    return ctx.deck(
        "Pico 2: supply side of the module",
        "\n".join(lines),
        control=["tran 10u 20m"],
        libraries=("digital.lib",),
    )


@bench(
    "models",
    "digital-rp2350",
    "Controller module: pad and supply models against the datasheets",
    "the pad model that the benches write for the controller, and the model of U1",
)
def rp2350(ctx: Context) -> Outcome:
    """A pad drives 4 mA, rests on its pull-down and is released onto a resistor.

    The pad model is set to the limits of the 4 mA drive setting. A pad of
    stepping A2 has the current of erratum E9: its voltage is stepped to
    show that current, and three such pads are driven high and released
    onto 4.7 kohm, 8.2 kohm and 47 kohm. The supply side of the module is
    fed once at VBUS and once at VSYS.
    """
    static = ctx.run("static", _static_deck(ctx))
    volts = static.real("p5")
    leak = static.real("v5#branch")
    first = 0
    figures: list[Figure] = [
        Figure(
            "high",
            "Pad high with 4 mA at the 4 mA setting",
            float(static.real("p1")[first]),
            "V",
            expected=2.62,
            low=2.61,
            high=2.63,
            source=_PAD + ": 2.62 V at the least; the model sits at the limit",
        ),
        Figure(
            "low",
            "Pad low with 4 mA at the 4 mA setting",
            float(static.real("p2")[first]),
            "V",
            expected=0.5,
            low=0.49,
            high=0.51,
            source=_PAD + ": 0.5 V at the most; the model sits at the limit",
        ),
        near(
            "pull_down",
            "Current of the strongest pull-down at 3.3 V",
            -float(static.real("v3#branch")[first]),
            "A",
            3.3 / 36e3,
            0.02,
            _PAD + ": 36 kohm at the least",
        ),
        near(
            "standard_diode",
            "Standard pad above the 3.3 V of the module with 1 mA into it",
            float(static.real("p4")[first]) - 3.3,
            "V",
            0.6,
            0.05,
            "Pico 2 datasheet, section 5.2: a diode to the 3.3 V rail; 0.6 V is an assumption",
        ),
        near(
            "e9_peak",
            "Stepping A2: largest current out of a released pad",
            float(np.max(leak)),
            "A",
            115e-6,
            0.05,
            _ERRATUM + ": about 120 uA; 115 uA in figure 157",
        ),
        Figure(
            "e9_starts",
            "Stepping A2: pad voltage at which that current starts",
            float(volts[np.argmax(leak > 1e-6)]),
            "V",
            low=1.15,
            high=1.3,
            source=_ERRATUM + ", figure 157 (read from the graph)",
        ),
        Figure(
            "e9_ends",
            "Stepping A2: pad voltage above which that current has gone",
            float(volts[len(leak) - 1 - np.argmax(leak[::-1] > 1e-6)]),
            "V",
            low=2.2,
            high=2.45,
            source=_ERRATUM + ", figure 157 (read from the graph)",
        ),
    ]
    release = ctx.run("release", _release_deck(ctx))
    time = release.real("time")
    ends = {name: float(release.real(f"p{name}")[-1]) for name in ("a", "b", "c")}
    figures += [
        Figure(
            "released_4k7",
            "Stepping A2: pad released from high onto 4.7 kohm ends at",
            ends["a"],
            "V",
            high=0.1,
            source=_ERRATUM + ": 8.2 kohm or less overcomes the current",
        ),
        Figure(
            "released_8k2",
            "Stepping A2: pad released from high onto 8.2 kohm ends at",
            ends["b"],
            "V",
            high=0.1,
            source=_ERRATUM + ": 8.2 kohm or less overcomes the current",
        ),
        Figure(
            "released_47k",
            "Stepping A2: pad released from high onto 47 kohm ends at",
            ends["c"],
            "V",
            low=2.0,
            high=2.4,
            source=_ERRATUM + ": a weak pull-down leaves the pad at about 2.2 V",
        ),
    ]
    supply = ctx.run("supply", _supply_deck(ctx))
    figures += [
        Figure(
            "module_vsys",
            "Module fed with 5 V at VBUS: voltage at VSYS",
            float(supply.real("vsys")[-1]),
            "V",
            low=4.4,
            high=4.7,
            source=_MODULE + ": VBUS less the drop of the Schottky diode",
        ),
        near(
            "sense_divider",
            "Module fed at VBUS: level of the VBUS sense pin",
            float(supply.real("x1.gp24")[-1]),
            "V",
            5.0 * 10.0 / 15.6,
            0.01,
            _MODULE + ": 5.6 kohm and 10 kohm",
        ),
        Figure(
            "vbus_fed_at_vsys",
            "Module fed with 5 V at VSYS: voltage at its VBUS pin",
            float(supply.real("wbus")[-1]),
            "V",
            high=1e-3,
            source=_DIODE + ": 5 nA typical at 5 V, into 15.6 kohm",
        ),
        near(
            "diode_0a1",
            "Diode of the module: forward voltage at 0.1 A",
            float(supply.real("da")[-1]),
            "V",
            0.475,
            0.05,
            _DIODE + ", typical",
        ),
        near(
            "diode_1a",
            "Diode of the module: forward voltage at 1 A",
            float(supply.real("ea")[-1]),
            "V",
            0.605,
            0.05,
            _DIODE + ", typical",
        ),
    ]
    micro = time * 1e6
    graph = Graph(
        name="release",
        title="Pad of stepping A2, driven high and released at 1 us onto a pull-down",
        xlabel="Time (us)",
        panels=(Panel("Pad (V)", marks=((2.0, "high above 2.0 V"), (0.8, "low below 0.8 V"))),),
        traces=(
            Trace(micro, release.real("pa"), "4.7 kohm", 0),
            Trace(micro, release.real("pb"), "8.2 kohm", 0),
            Trace(micro, release.real("pc"), "47 kohm", 0),
        ),
    )
    curve = Graph(
        name="erratum",
        title="Current out of a released pad of stepping A2 with its input enabled",
        xlabel="Pad voltage (V)",
        panels=(Panel("Current out of the pad (uA)"),),
        traces=(Trace(volts, leak * 1e6, "", 0),),
    )
    notes = (
        "The datasheet gives limits for the output levels and no typical value: "
        "the pad model takes the limits of the 4 mA setting, 170 ohm high and "
        "125 ohm low, and the benches also run a strong pad of 30 ohm, which is an "
        "assumption.",
        "The current of erratum E9 is the static curve of figure 157 for a typical "
        "part; a real pad shows it only with its input enabled, and stepping A3 "
        "does not have it.",
        "The capacitance of a pad, 5 pF with its pin and the socket, is an "
        "assumption; the load of the module, 0.1 W, is one as well.",
    )
    return Outcome(tuple(figures), (graph, curve), notes)
