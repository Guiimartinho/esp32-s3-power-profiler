"""The -4V_A rail against the 5 V rail: level, tolerance and the point where it lets go."""

from __future__ import annotations

import numpy as np

from benches.analog_rails import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.engine import RunResult

_REFS = ("U11", "R27", "R28", "R30", "R34", "R36", "R69", "D8", "C19", "C21", "C22", "C28")
"""The charge pump with its parts, the clamp and the minimum load of the source regulator."""

_START = 5.5
"""Level of the 5 V rail at the start of the sweep: the highest rail in operation."""

_STOP = 3.6
"""Level at the end of the sweep, below every corner."""

_RAMP = 0.19
"""Length of the sweep: 10 V/s, slow against every time constant of the rail."""

_REFERENCE = {"low": 1.202, "typ": 1.22, "high": 1.238}
"""Feedback reference of the charge pump: the limits and the typical value of its datasheet."""


def _deck(
    ctx: Context, reference: float, tolerance: int, output: float, share: float = 0.001
) -> str:
    refs = (*_REFS, *common.capacitors_on(ctx.netlist, ("-4V_A",)))
    overrides = common.bias_models(ctx.netlist, refs)
    overrides["U11"] = common.with_params(common.AVERAGED_PUMP, f"vfb={reference:g}")
    # the divider at its tolerance: R34 up and R36 down give the most negative output
    scales = {"R34": 1.0 + share * tolerance, "R36": 1.0 - share * tolerance, "R30": 1.01}
    circuit = ctx.circuit(refs, common.ALIASES, overrides, scales)
    stimulus = "\n".join(
        [
            "* the 5 V rail as a source that comes up and then falls slowly; the enable",
            "* of the pump is held on, as the supervisor does above 4.0 V",
            f"Vp5 p5v 0 PWL(0 0 1m {_START:g} 10m {_START:g} {0.01 + _RAMP:g} {_STOP:g})",
            "Vok ok5v 0 PWL(0 0 2m 0 2.01m 4.7)",
            "* loads: the amplifiers between the rails as a sink, the source regulator at",
            f"* an output of {output:g} V behind its minimum load R69",
            f"Bamp 0 m4v_a I = {common.AMPLIFIER_AMPS:g}*tanh(max(-v(m4v_a), 0)/2)",
            f"Vldo ldo_out 0 {output:g}",
        ]
    )
    return ctx.deck(
        f"-4V_A against the 5 V rail, reference {reference:g} V, divider at "
        f"{share * tolerance * 100:+g} %, output at {output:g} V",
        circuit,
        stimulus,
        control=["save p5v m4v_a cpout pump_in i(Vp5)", f"tran 50u {0.01 + _RAMP:g} 0 50u"],
        options=("method=gear",),
    )


def _letting_go(run: RunResult) -> tuple[float, float]:
    """The regulated level and the 5 V rail at which the output has lost 1 % of it."""
    time = run.real("time")
    rail, out = run.real("p5v"), run.real("m4v_a")
    level = measure.mean(time, out, 8e-3, 10e-3)
    sweep = time >= 10e-3
    lost = np.flatnonzero(out[sweep] > 0.99 * level)
    if lost.size == 0:
        return level, float("nan")
    return level, float(rail[sweep][lost[0]])


@bench(
    "analog_rails",
    "negative-rail",
    "-4V_A: its level and the 5 V rail it needs",
    "section 3 (charge pump, -3.91 V to -4.05 V), decisions D-26, D-49 and D-51",
)
def negative_rail(ctx: Context) -> Outcome:
    """The charge pump runs from a 5 V rail that falls from 5.5 V to 3.6 V in 0.19 s.

    The rail feeds the pump through R30 with C21, as drawn. The pump is its
    averaged model: an inverter with the output resistance of the datasheet
    that keeps its output 2.7 % short of its supply at light load, and a
    regulator behind it. The load is the supply current of the amplifiers
    and the minimum load of the source regulator, once with that regulator
    at 0 V and once at 5 V. The run is repeated with the feedback reference
    and the 0.1 % divider at their limits, and once with a divider of 1 %
    parts, which is what the 0.1 % parts replaced.
    """
    runs = {
        "typ": ctx.run("typical", _deck(ctx, _REFERENCE["typ"], 0, 0.0)),
        "high": ctx.run("most-negative", _deck(ctx, _REFERENCE["high"], 1, 5.0), keep=False),
        "low": ctx.run("least-negative", _deck(ctx, _REFERENCE["low"], -1, 0.0), keep=False),
        "busy": ctx.run("typical-source-on", _deck(ctx, _REFERENCE["typ"], 0, 5.0), keep=False),
        "coarse": ctx.run("one-percent", _deck(ctx, _REFERENCE["high"], 1, 5.0, 0.01), keep=False),
    }
    found = {name: _letting_go(run) for name, run in runs.items()}
    typ = runs["typ"]
    time = typ.real("time")
    current = -measure.mean(time, typ.real("vp5#branch"), 8e-3, 10e-3)
    figures = [
        near(
            "level_typ",
            "-4V_A, typical parts",
            found["typ"][0],
            "V",
            -3.977,
            0.005,
            "datasheet equation of the pump with R34 and R36",
        ),
        Figure(
            "level_high",
            "-4V_A, reference and divider at the limits that make it most negative",
            found["high"][0],
            "V",
            low=-4.05,
            high=-3.91,
            source="section 3: -3.91 V to -4.05 V",
        ),
        Figure(
            "level_low",
            "-4V_A, reference and divider at the limits that make it least negative",
            found["low"][0],
            "V",
            low=-4.05,
            high=-3.91,
            source="section 3: -3.91 V to -4.05 V",
        ),
        Figure(
            "rail_typ",
            "5 V rail at which -4V_A has lost 1 %, typical parts, source off",
            found["typ"][1],
            "V",
            high=4.25,
            source="decision D-49: 4.25 V is what the charge pump needs",
        ),
        Figure(
            "rail_busy",
            "5 V rail at which -4V_A has lost 1 %, typical parts, source at 5 V",
            found["busy"][1],
            "V",
            high=4.25,
            source="decision D-49: 4.25 V is what the charge pump needs",
        ),
        Figure(
            "rail_high",
            "5 V rail at which -4V_A has lost 1 %, most negative output, source at 5 V",
            found["high"][1],
            "V",
            high=4.25,
            source="decisions D-49 and D-51: the 0.1 % divider keeps the need at 4.25 V",
        ),
        near(
            "rail_coarse",
            "The same with resistors of 1 % in the divider, as before decision D-51",
            found["coarse"][1],
            "V",
            4.26,
            0.02,
            "section 15, decision D-51: with 1 % resistors the corner needs 4.26 V",
        ),
        Figure(
            "supply_current",
            "Current the pump takes from the 5 V rail at 5.5 V, source off",
            current,
            "A",
        ),
    ]
    traces = []
    for name, label in (
        ("typ", "typical, source off"),
        ("busy", "typical, source at 5 V"),
        ("high", "most negative, source at 5 V"),
    ):
        run = runs[name]
        sweep = run.real("time") >= 10e-3
        traces += [
            Trace(run.real("p5v")[sweep], run.real("m4v_a")[sweep], label, 0),
            Trace(run.real("p5v")[sweep], run.real("cpout")[sweep], label, 1),
        ]
    graph = Graph(
        name="sweep",
        title="-4V_A while the 5 V rail falls from 5.5 V to 3.6 V",
        xlabel="5 V rail (V)",
        panels=(Panel("-4V_A (V)"), Panel("Output of the pump ahead of its regulator (V)")),
        traces=tuple(traces),
        xmarks=((4.25, "4.25 V"),),
    )
    notes = (
        "The pump is the averaged model. Its light-load level, 2.7 % short of the "
        "supply, is read from two figures of the datasheet (7-3 and 7-4) and is the "
        "figure that decides where the rail lets go; the datasheet does not state it in "
        "words or in its table.",
        "The load on -4V_A is 5.1 mA of the amplifiers and the minimum load R69 of the "
        "source regulator: 3.1 mA with that regulator at 0 V and 6.9 mA at 5 V.",
        "R30 is taken 1 % high. The capacitors lose capacitance under bias; no figure "
        "here depends on it.",
    )
    return Outcome(tuple(figures), (graph,), notes)
