"""The supply node with every path switch open, and what its charge does at a change of mode."""

from __future__ import annotations

import numpy as np

from benches.path_switching import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench

_RELEASE = 10e-3
"""Instant at which the request of the closed pair goes low."""

_DECAY_END = 1.61

_LEAKAGE = 1e-6
"""Largest drain-source leakage of a CSD17577Q3A at 24 V and 25 C, A (TI SLPS515A, page 3)."""

_LEAK_STEPS = (0.0, 0.1e-6, 0.25e-6, 0.5e-6, 1e-6)
"""Leakage of each blocking transistor in the steps of the idle run, A."""

_CEILING = 5.26
"""Highest output of the regulator that the set-point path can command, V (section 4.2)."""

_LEAKS = {
    "the ampere pair": "Ileak_amp vin_p s_amp",
    "the source pair": "Ileak_src ldo_out s_src",
    "the output pair": "Ileak_out vout s_out",
}
"""The blocking transistor of each open pair, as a current source across it."""


def _decay_deck(ctx: Context) -> str:
    """Source mode at 5 V with the output open; then the source pair opens."""
    stimulus = (
        common.regulator(5.0)
        + common.no_supply()
        + common.requests(source=((0.0, True), (_RELEASE, False)))
    )
    return common.deck(
        ctx,
        "Supply node after the last path switch has opened",
        common.circuit(ctx),
        common.rails(),
        common.range_lines(3),
        stimulus,
        control=["save supply vout_s g_src s_src ldo_out", f"tran 0.5m {_DECAY_END:g} 0 1m"],
    )


def _level_deck(ctx: Context, which: tuple[str, ...]) -> str:
    """Every switch open, a voltage on every outer terminal, leakage stepped.

    Args:
        ctx: The context of the bench.
        which: The pairs whose blocking transistor leaks.
    """
    lines = [
        "* a voltage on every terminal that a blocking transistor faces",
        "Vin vin_raw 0 20",
        "Vdut dut_src 0 5",
        "Rdut dut_src vout 1",
        "* the detector output held high in place of the comparator, as it is at 20 V",
        "Vov vin_ov 0 3.3",
        "* leakage of the blocking transistors, as current sources across them",
    ]
    lines += [f"{element} 0" for element in _LEAKS.values()]
    control = []
    for amps in _LEAK_STEPS:
        control += [
            f"alter {element.split()[0]} dc = {amps if name in which else 0.0:g}"
            for name, element in _LEAKS.items()
        ]
        control.append("op")
    return common.deck(
        ctx,
        "Supply node at idle with leaking transistors: " + ", ".join(which),
        common.circuit(ctx, output=True, leave_out=("U21",)),
        common.rails(),
        common.range_lines(0),
        common.regulator(_CEILING),
        common.requests(),
        "\n".join(lines) + "\n",
        control=control,
        options=("gmin=1e-14",),
    )


@bench(
    "path_switching",
    "idle",
    "The supply node with every path switch open: idle level and decay",
    "sections 4.2 and 4.3 (idle level, bleed resistor R90, D-63), rule F-25",
)
def idle(ctx: Context) -> Outcome:
    """Every path switch is open and the supply node rests on its bleed resistor.

    The first run opens the source pair on 5 V with the output open and
    follows the node for 1.6 s: it falls through R90 alone. The other runs
    hold every switch open with 20 V on the VIN terminal, the regulator at
    its highest output and a device under test that holds 5 V on the output
    terminal, and give each blocking transistor a leakage, stepped up to the
    1 uA that its datasheet allows at 24 V. The leakage is a current source
    across the transistor, because no transistor model gives a leakage that
    can be believed.
    """
    decay = ctx.run("decay", _decay_deck(ctx))
    time, node = decay.real("time"), decay.real("supply")
    start = measure.value_at(time, node, _RELEASE)
    falls = measure.first_crossing(time, node, start * np.exp(-1.0), rising=False, after=_RELEASE)
    upper = measure.first_crossing(time, node, 0.8 * start, rising=False, after=_RELEASE)
    lower = measure.first_crossing(time, node, 0.2 * start, rising=False, after=_RELEASE)
    everything = tuple(_LEAKS)
    sets = {"all": everything, **{name.split()[1]: (name,) for name in _LEAKS}}
    levels = ctx.run_many(
        {key: _level_deck(ctx, which) for key, which in sets.items() if key != "all"}
    )
    levels["all"] = ctx.run("level", _level_deck(ctx, everything))
    last = len(_LEAK_STEPS)

    def level(key: str, step: int) -> float:
        return float(levels[key].real("supply", plot=f"op{step}")[0])

    figures = [
        Figure(
            "time_constant",
            "Supply node at 37 % of its voltage after the source pair has opened",
            falls - _RELEASE,
            "s",
            expected=0.57,
            low=0.54,
            high=0.60,
            source="sections 4.2 and 4.3: 0.57 s, calculated; 5 % asked here",
        ),
        Figure(
            "time_constant_slope",
            "Time constant from 80 % to 20 % of the voltage",
            (lower - upper) / float(np.log(4.0)),
            "s",
            expected=0.57,
            source="sections 4.2 and 4.3: 0.57 s, calculated",
        ),
        Figure(
            "kept",
            "Share of its voltage that the node keeps 5 ms after the pair has opened",
            100.0 * measure.value_at(time, node, _RELEASE + 5e-3) / start,
            "%",
            source="",
        ),
        Figure(
            "rest",
            "Supply node at idle without leakage",
            level("all", 1),
            "V",
            low=-1e-3,
            high=1e-3,
            source="section 4.3: the ladder rests at 0 V; within 1 mV asked here",
        ),
        Figure(
            "leaking",
            "Supply node at idle with 1 uA in the blocking transistor of each pair",
            level("all", last),
            "V",
            high=0.3,
            source="section 4.3: below 0.3 V with every blocking MOSFET at its leakage "
            "limit, calculated",
        ),
    ]
    figures += [
        Figure(
            f"leaking_{key}",
            f"Supply node at idle with 1 uA in the blocking transistor of {name} alone",
            level(key, last),
            "V",
            source="",
        )
        for key, name in ((name.split()[1], name) for name in _LEAKS)
    ]
    milli = time * 1e3
    decay_graph = Graph(
        name="decay",
        title="The source pair opens on 5 V with the output open: the supply node on R90",
        xlabel="Time (ms)",
        panels=(Panel("Supply node (TP33) (V)", log=True, marks=((0.3, "0.3 V"),)),),
        traces=(Trace(milli, np.maximum(node, 1e-3), "", 0),),
        xmarks=((_RELEASE * 1e3, "pair opens"),),
    )
    steps = np.asarray(_LEAK_STEPS) * 1e6
    traces = [
        Trace(steps, np.array([level(key, step + 1) for step in range(last)]) * 1e3, text, 0)
        for key, text in (
            ("all", "all three pairs"),
            ("ampere", "ampere pair alone, 20 V on VIN"),
            ("source", "source pair alone, regulator at 5.26 V"),
            ("output", "output pair alone, 5 V on the output terminal"),
        )
    ]
    level_graph = Graph(
        name="level",
        title="Idle level of the supply node against the leakage of the blocking transistors",
        xlabel="Leakage of each blocking transistor (uA)",
        panels=(Panel("Supply node (TP33) (mV)", marks=((300.0, "0.3 V"),)),),
        traces=tuple(traces),
    )
    notes = (
        "The leakage is not simulated: it is a current source of the datasheet "
        "maximum across the transistor that faces the outer voltage in each open "
        "pair (1 uA at 24 V and 25 C). The datasheet states no figure at a higher "
        "temperature, where leakage is larger.",
        "The current of such a source reaches the common source of its pair and "
        "leaves it two ways: through the body diode of the second transistor into "
        "the supply node and R90, or through the diode at the base of the hold-off "
        "transistor and its 100 kohm. How it divides rests on the forward voltage "
        "of two diode models at a microampere, which no datasheet states; if all of "
        "it reached R90, three pairs at 1 uA would give exactly 0.3 V.",
        "The decay counts what the netlist holds on the node: C62, C63, the 100 nF "
        "behind the 1 kohm shunt, and R90. Leakage of the capacitors and of the "
        "amplifier inputs is not in the circuit.",
    )
    return Outcome(tuple(figures), (decay_graph, level_graph), notes)


_HAND_REQUEST = 1e-3
"""Instant at which the request of the first pair goes low."""

_HAND_DEAD = 5e-3
"""Dead time of firmware before the other request is raised (rule F-23)."""

_HAND_END = 60e-3

_USER_FARADS = 4.7e-6
"""Capacitor at the supply of the user in the example of the specification."""


_ONE_WAY = ".model ONE_WAY D(IS=1e-9 N=0.02 RS=0.05)\n"
"""A diode that drops millivolts: what makes a source deliver current and take none back."""


def _one_way(name: str, node_from: str, node_to: str) -> str:
    """A source path that delivers current and takes none back."""
    return f"D{name} {node_from} {node_to} ONE_WAY\n"


def _to_ampere_deck(ctx: Context, node_volts: float, user_volts: float) -> str:
    """Source mode leaves the node charged; then the ampere pair closes on a lower supply."""
    stimulus = (
        common.regulator(node_volts)
        + "* the supply of the user: it delivers current and takes none back, with\n"
        "* 4.7 uF at its output and 0.5 uH of leads to the terminal\n"
        + _ONE_WAY
        + f"Vuser usr 0 {user_volts:g}\n"
        + _one_way("user", "usr", "usr_out")
        + f"Cuser usr_out 0 {_USER_FARADS:g}\n"
        "Vlead usr_out vin_a 0\n"
        "Rlead vin_a vin_b 0.02\n"
        "Llead vin_b vin_raw 0.5u\n"
        + common.requests(
            source=((0.0, True), (_HAND_REQUEST, False)),
            ampere=((0.0, False), (_HAND_REQUEST + _HAND_DEAD, True)),
        )
    )
    control = [
        "save supply vin_raw vin_p usr_out g_amp s_amp g_src ldo_out vlead#branch",
        f"tran 10u {_HAND_END:g} 0 20u",
    ]
    return common.deck(
        ctx,
        f"Ampere pair closes with the node at {node_volts:g} V on a supply of {user_volts:g} V",
        common.circuit(ctx),
        common.rails(),
        common.range_lines(3),
        stimulus,
        control=control,
    )


def _to_source_deck(ctx: Context, node_volts: float, set_volts: float) -> str:
    """Ampere mode leaves the node charged; then the source pair closes on a lower output."""
    stimulus = (
        common.supply(node_volts, henries=0.5e-6)
        + "* the regulator: it delivers current and takes none back; its output\n"
        "* capacitors and its minimum load are the parts of the schematic\n"
        + _ONE_WAY
        + f"Vset reg 0 {set_volts:g}\n"
        + _one_way("reg", "reg", "ldo_out")
        + common.requests(
            ampere=((0.0, True), (_HAND_REQUEST, False)),
            source=((0.0, False), (_HAND_REQUEST + _HAND_DEAD, True)),
        )
    )
    control = [
        "save supply vin_p ldo_out g_amp g_src s_src",
        f"tran 10u {_HAND_END:g} 0 20u",
    ]
    return common.deck(
        ctx,
        f"Source pair closes with the node at {node_volts:g} V on a regulator at {set_volts:g} V",
        common.circuit(ctx, extra=common.REGULATOR_OUTPUT),
        common.rails(),
        common.range_lines(3),
        stimulus,
        control=control,
    )


@bench(
    "path_switching",
    "hand-over",
    "A pair closes while the supply node still holds a higher voltage",
    "section 4.2 (charge of the supply node), rule F-25, the test of section 11",
)
def hand_over(ctx: Context) -> Outcome:
    """A mode pair closes on a supply that stands below the voltage left on the node.

    With the output open the supply node keeps its voltage for a long time.
    In the first run source mode at 5 V ends and, 5 ms later, the ampere
    pair closes on a supply of 0.8 V that has 4.7 uF at its output and
    cannot take current back: the example of the specification. In the
    second run the node holds only 0.1 V more than that supply, which is
    what rule F-25 allows. The third run is the other direction, which no
    rule names: ampere mode at 5 V ends and the source pair closes on a
    regulator at 0.8 V that cannot take current back either, with its
    output capacitors and its minimum load from the schematic.
    """
    push = ctx.run("to-ampere", _to_ampere_deck(ctx, 5.0, 0.8))
    allowed = ctx.run("allowed", _to_ampere_deck(ctx, 0.9, 0.8), keep=False)
    back = ctx.run("to-source", _to_source_deck(ctx, 5.0, 0.8))
    closes = _HAND_REQUEST + _HAND_DEAD

    def lifted(run_name: str) -> tuple[float, float]:
        run = {"push": push, "allowed": allowed}[run_name]
        time, terminal = run.real("time"), run.real("vin_p")
        before = measure.mean(time, terminal, 0.0, closes)
        return before, measure.extremes(time, terminal, closes, _HAND_END)[1]

    before, peak = lifted("push")
    low_before, low_peak = lifted("allowed")
    time = push.real("time")
    terminal = push.real("vin_p")
    reached = measure.first_crossing(time, terminal, before + 0.9 * (peak - before), rising=True)
    time_b = back.real("time")
    output = back.real("ldo_out")
    figures = (
        Figure(
            "pushed",
            "Supply of the user at 0.8 V with 4.7 uF, node at 5 V: highest voltage at the terminal",
            peak,
            "V",
            expected=3.1,
            low=2.9,
            high=3.3,
            source="section 4.2: 3.1 V on a 0.8 V supply with 4.7 uF, calculated; 0.2 V asked here",
        ),
        Figure(
            "pushed_after",
            "Time from the ampere request to 90 % of that rise",
            reached - closes,
            "s",
            source="",
        ),
        Figure(
            "pushed_current",
            "Largest current pushed back into the leads",
            float(np.max(-push.real("vlead#branch"))),
            "A",
            source="",
        ),
        Figure(
            "allowed",
            "Node at 0.9 V, supply of the user at 0.8 V: rise of the terminal",
            low_peak - low_before,
            "V",
            high=0.1,
            source="rule F-25 and section 11: the VIN terminal rises by less than 0.1 V",
        ),
        Figure(
            "regulator_lifted",
            "Regulator at 0.8 V, node at 5 V: highest voltage at the regulator output",
            measure.extremes(time_b, output, closes, _HAND_END)[1],
            "V",
            source="no rule of the specification names this direction",
        ),
        Figure(
            "regulator_back",
            "Time from the source request until the regulator output is within 0.1 V again",
            measure.settling_time(time_b, output, float(output[-1]), 0.1, closes),
            "s",
            source="",
        ),
    )
    milli = (time - closes) * 1e3
    shown = milli >= -6.0
    to_ampere = Graph(
        name="to-ampere",
        title="The ampere pair closes on 0.8 V with 4.7 uF while the node still holds 5 V",
        xlabel="Time after the ampere request (ms)",
        panels=(Panel("Voltage (V)"), Panel("Current of the supply leads (mA)")),
        traces=(
            Trace(milli[shown], push.real("supply")[shown], "supply node (TP33)", 0),
            Trace(milli[shown], terminal[shown], "VIN behind the fuse (TP27)", 0),
            Trace(
                milli[shown], push.real("g_amp")[shown], "gate of the ampere pair (TP32)", 0, "--"
            ),
            Trace(milli[shown], push.real("vlead#branch")[shown] * 1e3, "", 1),
        ),
    )
    milli_b = (time_b - closes) * 1e3
    shown_b = milli_b >= -6.0
    to_source = Graph(
        name="to-source",
        title="The source pair closes on a regulator at 0.8 V while the node still holds 5 V",
        xlabel="Time after the source request (ms)",
        panels=(Panel("Voltage (V)"),),
        traces=(
            Trace(milli_b[shown_b], back.real("supply")[shown_b], "supply node (TP33)", 0),
            Trace(milli_b[shown_b], output[shown_b], "regulator output (TP26)", 0),
            Trace(
                milli_b[shown_b],
                back.real("g_src")[shown_b],
                "gate of the source pair (TP31)",
                0,
                "--",
            ),
        ),
    )
    notes = (
        "The supply of the user and the regulator are sources that deliver current "
        "and take none back, which is the case the specification describes. A "
        "supply that sinks current is not lifted.",
        "The charge moves at the pace of the gate ramp once the gate has passed the "
        "lower voltage by a threshold: some milliseconds after the request, with "
        "tens of milliamperes at the most.",
        "In the other direction the regulator output is lifted above its set-point "
        "until its minimum load of 1.3 kohm to -4 V_A has taken the charge away. "
        "The specification tolerates an output above the set-point (section 4.9, "
        "source output) and its start sequence checks the output 60 ms after the "
        "pair has closed; it has no rule like F-25 for the source pair. In the start "
        "sequence of rule F-28 at least 285 ms pass before the source pair closes, "
        "in which the node falls to about 60 % of its voltage.",
    )
    return Outcome(figures, (to_ampere, to_source), notes)
