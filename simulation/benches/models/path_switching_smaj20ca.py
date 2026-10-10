"""The SMAJ20CA model and the model of the fuse against their datasheets."""

from __future__ import annotations

import numpy as np

from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import Circuit, PartModel

_SUPPRESSOR = "D14"
_FUSE = "F1"

_DOCUMENT = "Vishay 88390 of 09-Jan-2024"
"""The datasheet of the suppressor."""

_FUSE_DOCUMENT = "Littelfuse 466 series, revised 05/18/15, page 1"
"""The datasheet of the fuse."""

_VARIANTS = {
    "typical": "PATH_SMAJ20CA",
    "low": "PATH_SMAJ20CA_LO",
    "high": "PATH_SMAJ20CA_HI",
}
"""The three models of the suppressor: middle and limits of the breakdown voltage."""

_PULSE_AMPS = 12.3
"""Peak pulse current at which the datasheet states the clamping voltage."""

_STEPS = (1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 0.1, 0.3, 1.0, 3.0, 6.0, _PULSE_AMPS, 20.0)
"""Currents of the curve, both directions."""

_TEST_HERTZ = 1e6


def suppressor_model(variant: str) -> PartModel:
    """The model of one variant of the suppressor, for the ``overrides`` of a circuit."""
    return PartModel(
        kind="subckt",
        name=_VARIANTS[variant],
        ports=("1", "2"),
        library="path_switching.lib",
        origin="written here",
    )


def _suppressor(ctx: Context, variant: str) -> Circuit:
    """The suppressor alone, between the node a and ground as in the schematic."""
    found = ctx.netlist.component(_SUPPRESSOR)
    overrides = {} if variant == "typical" else {_SUPPRESSOR: suppressor_model(variant)}
    return ctx.circuit([_SUPPRESSOR], {found.net_of("1"): "a"}, overrides)


def _curve_deck(ctx: Context, variant: str) -> str:
    """A forced current through the suppressor, stepped in both directions."""
    stimulus = "\n".join(["* current forced into the terminal", "Itest 0 a 1m"])
    control = []
    for sign in (1.0, -1.0):
        for amps in _STEPS:
            control += [f"alter Itest dc = {sign * amps:.6g}", "op"]
    return ctx.deck(
        f"SMAJ20CA, {variant} breakdown voltage: forced current",
        _suppressor(ctx, variant),
        stimulus,
        control=control,
    )


def _standoff_deck(ctx: Context) -> str:
    """The stand-off voltage held: residual current and capacitance."""
    stimulus = "\n".join(
        ["* the stand-off voltage of 20 V on the terminal", "Vtest a 0 dc 20 ac 1"]
    )
    return ctx.deck(
        "SMAJ20CA: stand-off voltage",
        _suppressor(ctx, "typical"),
        stimulus,
        control=["op", f"ac lin 1 {_TEST_HERTZ:g} {_TEST_HERTZ:g}"],
    )


@bench(
    "models",
    "path-switching-smaj20ca",
    "SMAJ20CA model against its datasheet",
    "the model of the suppressor D14 of the VIN terminal",
)
def smaj20ca(ctx: Context) -> Outcome:
    """The suppressor D14 of the schematic carries a forced current in both directions.

    The run is made with the three variants of the model: the middle of the
    breakdown voltage and its two limits. The voltage at 1 mA is the
    breakdown voltage and the voltage at 12.3 A the clamping voltage of the
    datasheet. A second run holds the stand-off voltage of 20 V and reads
    the capacitance.
    """
    figures: list[Figure] = []
    traces: list[Trace] = []
    count = len(_STEPS)
    for variant in _VARIANTS:
        run = ctx.run(f"curve-{variant}", _curve_deck(ctx, variant), keep=variant == "typical")
        volts = np.array(
            [float(run.real("a", plot=f"op{step + 1}")[0]) for step in range(2 * count)]
        )
        forward, backward = volts[:count], volts[count:]
        breakdown = float(forward[_STEPS.index(1e-3)])
        clamp = float(forward[_STEPS.index(_PULSE_AMPS)])
        figures += [
            Figure(
                f"breakdown_{variant}",
                f"Breakdown voltage at 1 mA, {variant} variant",
                breakdown,
                "V",
                expected={"typical": 23.35, "low": 22.2, "high": 24.5}[variant],
                low=22.15,
                high=24.55,
                source=f"{_DOCUMENT}, page 2: 22.2 V to 24.5 V",
            ),
            Figure(
                f"clamp_{variant}",
                f"Clamping voltage at 12.3 A, {variant} variant",
                clamp,
                "V",
                high=32.45,
                source=f"{_DOCUMENT}, page 2: 32.4 V at most",
            ),
        ]
        if variant == "typical":
            figures.append(
                Figure(
                    "symmetry",
                    "Difference between the two directions at 12.3 A",
                    float(abs(clamp + backward[_STEPS.index(_PULSE_AMPS)])),
                    "V",
                    high=0.01,
                    source=f"{_DOCUMENT}, page 1: the characteristics apply in both directions",
                )
            )
        traces.append(Trace(forward, np.asarray(_STEPS), f"{variant} breakdown voltage", 0))
    standoff = ctx.run("standoff", _standoff_deck(ctx))
    leakage = float(-standoff.real("vtest#branch", plot="op")[0])
    capacitance = float(
        -np.imag(standoff.vector("vtest#branch", plot="ac")[0]) / (2.0 * np.pi * _TEST_HERTZ)
    )
    figures += [
        Figure(
            "standoff_current",
            "Current at the stand-off voltage of 20 V",
            leakage,
            "A",
            high=1e-6,
            source=f"{_DOCUMENT}, page 2: 1 uA at most",
        ),
        Figure(
            "capacitance",
            "Capacitance at 20 V and 1 MHz",
            capacitance,
            "F",
            expected=300e-12,
            low=225e-12,
            high=375e-12,
            source=f"{_DOCUMENT}, page 4, figure 4, read from the curve; 25 % asked of the fit",
        ),
    ]
    graph = Graph(
        name="curve",
        title="SMAJ20CA: current against voltage, three breakdown voltages",
        xlabel="Voltage on the terminal (V)",
        panels=(Panel("Current (A)", log=True, marks=((_PULSE_AMPS, "12.3 A"),)),),
        traces=tuple(traces),
        xmarks=((22.2, "22.2 V"), (24.5, "24.5 V"), (32.4, "32.4 V")),
    )
    notes = (
        "The datasheet states the clamping voltage as a maximum after a pulse of a "
        "millisecond, which heats the part. Every variant rises by the same 7.9 V "
        "from 1 mA to 12.3 A, so the variant with the highest breakdown voltage "
        "clamps at the datasheet maximum; in a pulse of microseconds a real part "
        "clamps lower than these models.",
        "The current at the stand-off voltage is set by two resistors that keep the "
        "middle node of the model defined: it is no leakage figure.",
        "The models have no heating and no limit of pulse power; the benches compare "
        "the simulated pulses with figure 1 of the datasheet.",
    )
    return Outcome(tuple(figures), (graph,), notes)


def _fuse_deck(ctx: Context) -> str:
    """The fuse with a forced current, stepped up to its rated current."""
    found = ctx.netlist.component(_FUSE)
    circuit = ctx.circuit([_FUSE], {found.net_of("1"): "a", found.net_of("2"): "b"})
    stimulus = "\n".join(["* current forced through the fuse", "Vb b 0 0", "Itest 0 a 0.4"])
    return ctx.deck("0466004.NR: forced current", circuit, stimulus, control=["dc Itest 0 4 0.1"])


@bench(
    "models",
    "path-switching-fuse",
    "Model of the fuse 0466004.NR against its datasheet",
    "the model of the fuse F1 of the VIN terminal",
)
def fuse(ctx: Context) -> Outcome:
    """The fuse F1 of the schematic carries a current from zero to its rated 4 A.

    The model is the cold resistance of the datasheet and nothing else, so
    the run shows where it agrees with the datasheet and where it does not.
    """
    run = ctx.run("drop", _fuse_deck(ctx))
    amps = run.real("i-sweep")
    volts = run.real("a")
    figures = (
        Figure(
            "cold_resistance",
            "Resistance at 10 % of the rated current",
            float(np.interp(0.4, amps, volts)) / 0.4,
            "ohm",
            expected=0.014,
            low=0.0139,
            high=0.0141,
            source=f"{_FUSE_DOCUMENT}: nominal cold resistance",
        ),
        Figure(
            "drop_1a",
            "Voltage drop at 1 A, the largest current of the instrument",
            float(np.interp(1.0, amps, volts)),
            "V",
            source="",
        ),
        Figure(
            "drop_rated",
            "Voltage drop at the rated current of 4 A",
            float(np.interp(4.0, amps, volts)),
            "V",
            expected=0.0745,
            source=f"{_FUSE_DOCUMENT}: nominal voltage drop, with the fuse warm",
        ),
    )
    graph = Graph(
        name="drop",
        title="0466004.NR: voltage drop of the model against current",
        xlabel="Current (A)",
        panels=(Panel("Voltage drop (mV)", marks=((74.5, "datasheet at 4 A, warm"),)),),
        traces=(Trace(amps, volts * 1e3, "", 0),),
    )
    notes = (
        "The figures were read in the copy of the datasheet that a distributor "
        "holds; the site of the manufacturer did not answer.",
        "The model does not heat: at the rated current it reads a quarter less than "
        "the datasheet. At 1 A the heating is one sixteenth of that at 4 A, so the "
        "cold resistance is the right figure for the path drop of this instrument.",
        "The datasheet states no tolerance of the resistance, and the model does not "
        "open: the benches compare the simulated I2t with the melting figure of "
        "1.764 A2s.",
    )
    return Outcome(figures, (graph,), notes)
