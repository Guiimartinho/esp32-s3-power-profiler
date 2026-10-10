"""Head room of the amplifier input stage near full scale at a low output voltage."""

from __future__ import annotations

import numpy as np

from benches import frontend
from benches.signal_chain import common
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_READINGS = (
    ("tool", 1.58, "range tool of the manufacturer and figure 13"),
    ("fig14", 2.38, "figure 14 of the datasheet"),
)
"""The two readings of the limit of the first stage: key, room above the negative
supply that its outputs need (the parameter hlo of the model), and where it is from."""

_OUTPUTS = (0.0, 0.05, 0.2, 0.8)
"""Voltages of the node after the shunts at which the sweep is run."""

_SWEEP = (0.0, 0.45, 1e-3)
"""Shunt voltage of the sweep: start, stop, step."""

_DIVIDER = 4.01
"""Division of the amplifier output in front of the comparators (section 4.4)."""

_TRIP = 0.584
"""Over-current threshold at the comparator input (section 4.4)."""

_JUMP = 0.764
"""Jump threshold at the comparator input (section 4.4)."""

_TRIP_BAND = (111.4e-3, 118.7e-3)
"""Shunt voltage of the over-current level with tolerances (section 4.4)."""

_JUMP_BAND = (147.2e-3, 155.1e-3)
"""Shunt voltage of the jump level with tolerances (section 4.4)."""

_LINEAR = 0.001 * common.VREF
"""Distance from the straight line that ends the linear range: 0.1 % of the range."""

_WORSE_ROOM = 2.58
"""The reading of figure 14 with 0.2 V less room: a case of this bench, not of the
specification. The datasheet moves the lower end of the input range up by 0.2 V from
25 C to -40 C (AD8421, page 4), and the -4 V rail at -3.91 V takes 0.09 V more."""


def _deck(ctx: Context, room: float, output: float) -> str:
    start, stop, step = _SWEEP
    return ctx.deck(
        f"Signal chain: shunt voltage swept in range 3, node after the shunts at {output:g} V",
        common.chain(ctx, overrides={"U27": common.with_params(ctx, "U27", hlo=room)}),
        frontend.rails(),
        common.taps({}, f"{output:g}"),
        common.address(3),
        control=[f"dc Vsh3 {start:g} {stop:g} {step:g}"],
        libraries=common.LIBRARIES,
    )


def _reaches(shunt: common.Vector, output: common.Vector, level: float) -> float:
    """The shunt voltage at which the amplifier output reaches a level; NaN when it never does."""
    if float(output.max()) < level:
        return float("nan")
    return float(np.interp(level, output, shunt))


def _linear_to(run: RunResult) -> float:
    """The shunt voltage up to which the amplifier output follows its gain."""
    shunt = run.real("v-sweep")
    output = run.real("amp_raw")
    line = float(output[0]) + common.GAIN * shunt
    off = np.flatnonzero(np.abs(output - line) > _LINEAR)
    return float(shunt[off[0]]) if off.size else float(shunt[-1])


@bench(
    "signal_chain",
    "head-room",
    "Head room of the amplifier near full scale with the output voltage near 0 V",
    "section 4.5 (head room to the -4 V rail), section 4.10 (limits of the budget), "
    "section 4.4 (trip and jump level), section 16",
)
def head_room(ctx: Context) -> Outcome:
    """The shunt voltage is swept with the node after the shunts at 0 V to 0.8 V.

    Range 3 is held. With the output voltage near 0 V the inputs of the
    amplifier sit near ground, and its first stage needs room below them
    that grows with the signal: one of its two outputs moves down by half
    the amplified signal. The model takes that room as a parameter. It is
    run with the two readings that the specification names: the one of the
    range tool of the manufacturer, which figure 13 of the datasheet
    supports, and the one of figure 14. For each the sweep gives where the
    amplifier leaves its straight line, and at which shunt voltage its
    output reaches the over-current level and the jump level of the
    comparators. One more sweep takes the reading of figure 14 with 0.2 V
    less room, a case of this bench: it shows where the over-current level
    is reached once the linear range ends below it, which section 4.10
    estimates as 1.26 A.
    """
    decks = {
        f"{key}-{output:g}v".replace(".", "p"): _deck(ctx, room, output)
        for key, room, _ in _READINGS
        for output in _OUTPUTS
    }
    decks["worse-0v"] = _deck(ctx, _WORSE_ROOM, 0.0)
    ctx.run("fig14-0v", decks["fig14-0v"])
    runs = ctx.run_many(decks)
    figures: list[Figure] = []
    traces: list[Trace] = []
    trip_level = _TRIP * _DIVIDER
    jump_level = _JUMP * _DIVIDER
    expected_linear = {("tool", 0.0): 0.210, ("fig14", 0.0): 0.130}
    for key, _room, origin in _READINGS:
        for output in _OUTPUTS:
            tag = f"{key}-{output:g}v".replace(".", "p")
            run = runs[tag]
            shunt = run.real("v-sweep")
            amplifier = run.real("amp_raw")
            name = tag.replace("-", "_")
            specified = output >= 0.2
            figures += [
                Figure(
                    f"linear_{name}",
                    f"Output voltage {output:g} V, {origin}: the amplifier is linear up to",
                    _linear_to(run),
                    "V",
                    expected=expected_linear.get((key, output)),
                    low=_JUMP_BAND[1] if specified else None,
                    source="section 4.5: trip and jump level are specified from 0.2 V on"
                    if specified
                    else "section 4.10: the two readings end at 130 mV and at 210 mV",
                ),
                Figure(
                    f"trip_{name}",
                    f"Output voltage {output:g} V, {origin}: over-current level reached at",
                    _reaches(shunt, amplifier, trip_level),
                    "V",
                    expected=0.115,
                    low=_TRIP_BAND[0] if specified else None,
                    high=_TRIP_BAND[1] if specified else None,
                    source="section 4.4: 115 mV, 111.4 mV to 118.7 mV",
                ),
                Figure(
                    f"jump_{name}",
                    f"Output voltage {output:g} V, {origin}: jump level reached at",
                    _reaches(shunt, amplifier, jump_level),
                    "V",
                    expected=0.151,
                    low=_JUMP_BAND[0] if specified else None,
                    high=_JUMP_BAND[1] if specified else None,
                    source="section 4.4: 151 mV, 147.2 mV to 155.1 mV",
                ),
            ]
            if output in (0.0, 0.2):
                traces.append(
                    Trace(
                        shunt * 1e3,
                        amplifier,
                        f"{output:g} V, {origin}",
                        0,
                        "-" if key == "tool" else "--",
                    )
                )
    worst = runs["fig14-0v"]
    shunt = worst.real("v-sweep")
    amplifier = worst.real("amp_raw")
    beyond = shunt > _linear_to(worst) + 0.02
    slope = float(np.polyfit(shunt[beyond][:40], amplifier[beyond][:40], 1)[0])
    figures.append(
        Figure(
            "gain_beyond",
            "Gain of the amplifier beyond the limit (output voltage 0 V, figure 14)",
            slope,
            "",
        )
    )
    worse = runs["worse-0v"]
    figures += [
        Figure(
            "linear_worse_0v",
            "Output voltage 0 V, figure 14 with 0.2 V less room: the amplifier is linear up to",
            _linear_to(worse),
            "V",
        ),
        Figure(
            "trip_worse_0v",
            "Output voltage 0 V, figure 14 with 0.2 V less room: over-current level reached at",
            _reaches(worse.real("v-sweep"), worse.real("amp_raw"), trip_level),
            "V",
            expected=0.126,
            source="section 4.10: the trip could then act at up to about 1.26 A (estimate)",
        ),
    ]
    graph = Graph(
        name="transfer",
        title="Amplifier output against the shunt voltage with the output voltage near 0 V",
        xlabel="Voltage across the shunt (mV)",
        panels=(
            Panel(
                "Amplifier output (V)",
                marks=(
                    (jump_level, "jump level"),
                    (trip_level, "over-current level"),
                    (common.VREF, "converter full scale"),
                ),
            ),
        ),
        traces=tuple(traces),
        xmarks=((151.0, "151 mV"),),
    )
    notes = (
        "The limit is a parameter of the amplifier model, not a result: the simulation "
        "shows what each reading of the datasheet does to the chain, and cannot say "
        "which reading is right. That stays a measurement on the first board "
        "(section 16).",
        "Beyond the limit the model stops one half of its first stage. The gain then "
        "falls to about 2, not to half: the level of a comparator is reached only far "
        "above its shunt voltage, or not at all inside the sweep (no value). A level "
        "does not move little by little: it stays where it is while the linear range "
        "ends above it, and moves far once the range ends below it. With 0.2 V less "
        "room than figure 14 the over-current level of 115 mV is reached at about "
        "180 mV, which is 1.8 A in range 3 where section 4.10 estimates 1.26 A. How a "
        "real part behaves beyond its limit is not in its datasheet.",
        "The reading of figure 14 is a line with a slope of 0.41 V of common mode per volt "
        "of output; the model has 0.5, which follows from its structure. The parameter is "
        "matched at the converter full scale. At the jump level the line of the figure "
        "leaves 6 mV more at the shunt than the model (calculated): 156 mV in place of "
        "150 mV at an output voltage of 0.2 V. Against a jump level of up to 155.1 mV "
        "neither leaves a margin.",
        "With a short circuit at the terminals the node after the shunts stands some tens "
        "of millivolts above ground in range 3, the drop of the output switch and of the "
        "contacts: between the first two rows of each reading.",
        "The comparators are not in this circuit: the levels are their thresholds times "
        "the division of 4.01, nominal values.",
        "The -4 V rail is at its nominal value. The specification allows -3.91 V to "
        "-4.05 V; each 0.1 V of it moves the limit by 11 mV at the shunt.",
        "The model is a part at 25 C. The datasheet moves the lower end of the input "
        "range up by 0.2 V at -40 C and down by 0.2 V at 85 C (page 4), about 3 mV for "
        "each kelvin: 8 mV less at the shunt at 0 C than at 25 C (calculated).",
    )
    return Outcome(tuple(figures), (graph,), notes)
