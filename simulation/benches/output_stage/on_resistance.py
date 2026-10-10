"""The closed output pair at 1 A: its resistance over the output range."""

from __future__ import annotations

import numpy as np

from benches.output_stage import common
from circuit_sim import measure
from circuit_sim.bench import OPEN_TIER, Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel

_VOLTS = (0.8, 1.2, 1.8, 2.5, 3.3, 4.2, 5.0, 5.5)
"""Voltages of the supply node: the output range and the ceiling above it."""

_LOAD_AMPS = 1.0
"""Load current at which the specification states the drop of the path."""

_LOW_RAIL = 11.4
"""Lowest +12 V_A at which the rails count as valid (rule F-12)."""

_END = 160e-6
"""End of a run; the values are read over its last 10 us."""

_WARM = 1.1
"""On-resistance at 50 C over that at 25 C (TI SLPS515A, figure 8)."""

_TYPICAL_OHMS = 4.8e-3
"""Share of one transistor in the typical drop of requirement R-06: 144 mV
less the 100 mV of the shunt and 20 mV of copper, over five transistors."""

_BOUND_OHMS = 7.2e-3
"""Share of one transistor in the drop at the bounds: 161 mV less 100 mV and
25 mV, over five transistors."""


def _deck(ctx: Context, volts: float, rail: float, models: dict[str, PartModel]) -> str:
    circuit = ctx.circuit(
        common.path_refs(ctx.netlist),
        common.ALIASES,
        {**common.path_models(ctx), **models},
    )
    ramp = common.QUICK_POWER_UP
    stimulus = "\n".join(
        [
            "* the device under test takes a constant current at the terminal",
            f"Iload vout 0 PWL(0 0 {ramp:g} 0 {2 * ramp:g} {_LOAD_AMPS:g})",
            "Rdut vout 0 1Meg",
        ]
    )
    return ctx.deck(
        f"Closed output pair at 1 A, supply node at {volts:g} V, +12 V_A at {rail:g} V",
        circuit,
        common.rails(p12=rail, ramp=ramp),
        common.controller(3, ramp=ramp),
        common.command((0.0, True)),
        common.source(volts, ramp=ramp),
        stimulus,
        common.closed_start(rail),
        control=[
            "save supply vout_s vout mid g_out out_gate sense_r3",
            f"tran 0.2u {_END:g} 0 0.5u uic",
        ],
        options=(*common.buffer_options(ctx), "method=gear"),
    )


@bench(
    "output_stage",
    "on-resistance",
    "The closed output pair at 1 A: burden behind the shunts, over the output range",
    "requirement R-06 and D-64 (drop of the path), section 4.2 (output switch)",
)
def on_resistance(ctx: Context) -> Outcome:
    """The output is on in range 3 and the terminal takes 1 A; the output voltage is stepped.

    The gates of the pair rest at +12 V_A and the two sources at the output
    voltage, so the gate drive falls as the output rises: 11.2 V at 0.8 V
    and 7 V at 5 V. The drop from the node after the shunts to the terminal
    is burden that the shunt does not measure. Each point is the end of a
    run that starts from zero and settles. The sweep is repeated with
    +12 V_A at its lower limit and, with the models written here, with both
    transistors at the upper limit of the on-resistance.
    """
    variants: dict[str, tuple[float, dict[str, PartModel]]] = {
        "typical": (12.0, {}),
        "rail": (_LOW_RAIL, {}),
    }
    if ctx.tier == OPEN_TIER:
        worst = common.transistor("RMAX")
        variants["bound"] = (_LOW_RAIL, {"Q15": worst, "Q16": worst})
    decks = {
        f"{name}-{volts:g}".replace(".", "p"): _deck(ctx, volts, rail, models)
        for name, (rail, models) in variants.items()
        for volts in _VOLTS
    }
    ctx.kept[f"{ctx.prefix}.typical-5.cir"] = decks["typical-5"]
    runs = ctx.run_many(decks)

    def drop(name: str, volts: float, high: str, low: str) -> float:
        run = runs[f"{name}-{volts:g}".replace(".", "p")]
        time = run.real("time")
        return measure.mean(time, run.real(high) - run.real(low), _END - 10e-6, _END)

    def pair(name: str) -> np.ndarray:
        return np.array([drop(name, volts, "vout_s", "vout") for volts in _VOLTS])

    typical = pair("typical")
    figures = []
    for volts in (0.8, 3.3, 5.0):
        index = _VOLTS.index(volts)
        tag = f"{volts:g}".replace(".", "p")
        figures += [
            Figure(
                f"pair_{tag}v",
                f"Typical parts, {volts:g} V: drop of the pair at 1 A and 25 C",
                float(typical[index]),
                "V",
                expected=2.0 * _TYPICAL_OHMS / _WARM * _LOAD_AMPS,
                high=2.0 * _TYPICAL_OHMS / _WARM * _LOAD_AMPS * 1.1,
                source="requirement R-06: 144 mV typical from the regulator at 50 C, of "
                "which two of five transistors, taken to 25 C; limit set here, 10 % above",
            ),
            Figure(
                f"drive_{tag}v",
                f"Typical parts, {volts:g} V: gate-source voltage of the pair",
                drop("typical", volts, "g_out", "mid"),
                "V",
            ),
            Figure(
                f"path_{tag}v",
                f"Typical parts, {volts:g} V: drop from the supply node to the terminal",
                drop("typical", volts, "supply", "vout"),
                "V",
            ),
        ]
    figures.append(
        Figure(
            "pair_rail_5v",
            "+12 V_A at 11.4 V, 5 V: drop of the pair at 1 A and 25 C",
            float(pair("rail")[_VOLTS.index(5.0)]),
            "V",
        )
    )
    figures.append(
        Figure(
            "pair_ceiling",
            "+12 V_A at 11.4 V, 5.5 V: drop of the pair at 1 A and 25 C",
            float(pair("rail")[_VOLTS.index(5.5)]),
            "V",
        )
    )
    traces = [
        Trace(np.asarray(_VOLTS), typical * 1e3 / _LOAD_AMPS, "typical parts", 0),
        Trace(np.asarray(_VOLTS), pair("rail") * 1e3 / _LOAD_AMPS, "+12 V_A at 11.4 V", 0, "--"),
        Trace(
            np.asarray(_VOLTS),
            np.array([drop("typical", volts, "g_out", "mid") for volts in _VOLTS]),
            "+12 V_A at 12 V",
            1,
        ),
        Trace(
            np.asarray(_VOLTS),
            np.array([drop("rail", volts, "g_out", "mid") for volts in _VOLTS]),
            "+12 V_A at 11.4 V",
            1,
            "--",
        ),
    ]
    if "bound" in variants:
        bound = pair("bound")
        warm = float(np.max(bound[: _VOLTS.index(5.0) + 1])) * _WARM
        figures.append(
            Figure(
                "pair_bound",
                "Largest on-resistance, +12 V_A at 11.4 V: largest drop of the pair up to "
                "5 V, taken to 50 C",
                warm,
                "V",
                expected=2.0 * _BOUND_OHMS * _LOAD_AMPS,
                high=2.0 * _BOUND_OHMS * _LOAD_AMPS,
                source="requirement R-06: 161 mV at the bounds from the regulator at 50 C, "
                "of which two of five transistors",
            )
        )
        traces.append(
            Trace(
                np.asarray(_VOLTS),
                bound * 1e3 / _LOAD_AMPS,
                "largest on-resistance, +12 V_A at 11.4 V",
                0,
                ":",
            )
        )
    graph = Graph(
        name="resistance",
        title="Closed output pair at 1 A and 25 C against the output voltage",
        xlabel="Voltage of the supply node (V)",
        panels=(
            Panel(
                "Resistance of the pair (mohm)",
                marks=((2e3 * _TYPICAL_OHMS / _WARM, "R-06 typical, at 25 C"),),
            ),
            Panel("Gate-source voltage (V)"),
        ),
        traces=tuple(traces),
    )
    notes = (
        "The transistor model has no temperature: every value is at 25 C. The "
        "specification counts the path at 50 C, where the datasheet shows 1.1 times "
        "the resistance (figure 8); the limits here are taken to 25 C with that factor, "
        "and the figure at the bounds is taken to 50 C with it.",
        "The specification states the drop of the whole path, not of one transistor. "
        "The share of the pair is derived here: the total less the shunt and the "
        "copper, over five transistors, times two.",
        "An ideal source behind 10 mohm stands for the source meter and its closed mode "
        "pair; the drop from the supply node to the terminal therefore leaves out the "
        "mode pair, the copper and the contacts.",
        "The values are the end of a run that starts from zero and has settled; the "
        "gate node is tied to +12 V_A while the circuit comes up.",
        "In the vendor tier the pair drops 10.3 mV to 10.8 mV. The model of the "
        "manufacturer has 5.2 mohm at 10 V on the gate, where the datasheet of the "
        "same part gives 4.0 mohm typical and 4.8 mohm at most: it is not a typical "
        "part by its own datasheet.",
    )
    return Outcome(tuple(figures), (graph,), notes)
