"""The jump path: from the ladder voltage at the jump threshold to range 3 conducting."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from benches.range_logic import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_TARGET = 0.55e-6
"""Longest time from the threshold to the conducting branch (section 4.4)."""

_END = 6e-6

_LOAD = common.Load(before=1e-6, after=0.5, capacitance=1e-6)
"""The step of requirement R-07: 1 uA to 500 mA with 1 uF at the terminals."""

_JUMP_INPUT = common.THRESHOLD_SHUNT["jump"] * common.GAIN + common.PEDESTAL
"""Amplifier output at which the jump comparator switches, V (nominal)."""


def _cases(ctx: Context) -> dict[str, tuple[common.Delays, float, dict[str, PartModel]]]:
    """Every run of the bench: the delays, the output voltage, further models."""
    nominal = common.NOMINAL
    return {
        "nominal": (nominal, 5.0, {}),
        "best": (common.BEST, 5.0, {}),
        "worst": (common.WORST, 5.0, {}),
        "nominal-0v8": (nominal, 0.8, {}),
        "worst-0v8": (common.WORST, 0.8, {}),
        "mux-125": (replace(nominal, mux_ohms=125.0), 5.0, {}),
        "mux-430": (replace(nominal, mux_ohms=430.0), 5.0, {}),
        "comparator-80n": (replace(nominal, comparator=80e-9), 5.0, {}),
        "sequencer-20n": (replace(nominal, reaction=20e-9), 5.0, {}),
        "driver-20n": (replace(nominal, driver=20e-9), 5.0, {}),
        "driver-40n": (replace(nominal, driver=40e-9, driver_ohms=10.0), 5.0, {}),
        "worst-slow-amplifier": (common.WORST, 5.0, common.slow_amplifier(ctx)),
    }


def _deck(ctx: Context, name: str) -> str:
    delays, volts, more = _cases(ctx)[name]
    return common.step_deck(
        ctx,
        f"Jump path, {name}: 1 uA to 500 mA with 1 uF at {volts:g} V",
        _LOAD,
        volts=volts,
        delays=delays,
        more=more,
        end=_END,
    )


def _instants(result: RunResult) -> dict[str, float]:
    """The instants of the path, counted from the ladder crossing the threshold."""
    time = result.real("time")
    start = common.STEP_AT

    def rise(name: str, level: float) -> float:
        return measure.first_crossing(time, result.real(name), level, rising=True, after=start)

    crossed = measure.first_crossing(
        time, common.ladder(result), common.THRESHOLD_SHUNT["jump"], rising=True, after=start
    )
    found = {
        "amplifier": rise("amp_raw", _JUMP_INPUT),
        "comparator": rise("cmp_jump", common.HALF_LOGIC),
        "line": rise("gate_r3", common.HALF_LOGIC),
        "conducts": measure.first_crossing(
            time, common.branch_r3(result), common.CONDUCTS_AMPS, rising=True, after=start
        ),
    }
    return {"crossed": crossed, **{key: value - crossed for key, value in found.items()}}


@bench(
    "range_logic",
    "jump",
    "The jump path: from the jump threshold at the ladder to range 3 conducting",
    "section 4.4 (jump up, reaction time), rule F-16, requirement R-07",
)
def jump(ctx: Context) -> Outcome:
    """A load steps from 1 uA to 500 mA in range 0 with 1 uF at the terminals.

    The capacitor supplies the step, so the ladder voltage rises at about
    0.45 V per microsecond. The run measures the time from the instant the
    ladder voltage passes the jump threshold, 151 mV, to the instant the
    0.1 ohm branch carries 50 mA. The loop is closed through the real
    comparators and the model of the sequencer. The delays on the way are
    varied one at a time and together: the on-resistance of the multiplexer,
    which with the capacitors at the amplifier inputs delays the sense
    voltage, the delay of the comparators, the reaction of the sequencer,
    and the delay and output resistance of the gate driver.
    """
    names = list(_cases(ctx))
    results = {name: ctx.run(name, _deck(ctx, name)) for name in ("nominal", "best", "worst")}
    results.update(ctx.run_many({name: _deck(ctx, name) for name in names if name not in results}))
    found = {name: _instants(result) for name, result in results.items()}
    source = "section 4.4, simulated; target 0.55 us at the most"

    def delay(name: str, label: str, expected: float | None = None) -> Figure:
        key = "delay_" + name.replace("-", "_")
        value = found[name]["conducts"]
        return Figure(key, label, value, "s", expected=expected, high=_TARGET, source=source)

    budget = found["nominal"]
    figures = [
        delay("nominal", "Threshold to conducting branch, nominal delays", 0.35e-6),
        delay("best", "Threshold to conducting branch, best delays", 0.20e-6),
        delay("worst", "Threshold to conducting branch, worst delays", 0.51e-6),
        delay("nominal-0v8", "The same at 0.8 V, nominal delays"),
        delay("worst-0v8", "The same at 0.8 V, worst delays"),
        delay("mux-125", "Multiplexer at 125 ohm, the rest nominal"),
        delay("mux-430", "Multiplexer at 430 ohm, the rest nominal"),
        delay("comparator-80n", "Comparators at 80 ns, the rest nominal"),
        delay("sequencer-20n", "Sequencer at 20 ns, the rest nominal"),
        delay("driver-20n", "Gate driver at 20 ns, the rest nominal"),
        delay("driver-40n", "Gate driver at 40 ns and 10 ohm, the rest nominal"),
        Figure(
            "delay_worst_slow_amplifier",
            "Worst delays and the amplifier at half the bandwidth of its model",
            found["worst-slow-amplifier"]["conducts"],
            "s",
            source="no limit: the datasheet of the amplifier gives no spread of its bandwidth",
        ),
        Figure(
            "part_filter_amplifier",
            "Nominal, of which: input filter and amplifier",
            budget["amplifier"],
            "s",
        ),
        Figure(
            "part_comparator",
            "Nominal, of which: divider and comparator",
            budget["comparator"] - budget["amplifier"],
            "s",
        ),
        Figure(
            "part_sequencer",
            "Nominal, of which: sequencer",
            budget["line"] - budget["comparator"],
            "s",
            expected=100e-9,
            high=100e-9 * 1.1,
            source="rule F-16: within 100 ns; a parameter of the model, read between "
            "the middles of two edges, hence 10 % of allowance",
        ),
        Figure(
            "part_driver",
            "Nominal, of which: driver, gate resistor and switch",
            budget["conducts"] - budget["line"],
            "s",
        ),
        Figure(
            "ladder_at_conduction",
            "Nominal: ladder voltage when the branch conducts",
            measure.value_at(
                results["nominal"].real("time"),
                common.ladder(results["nominal"]),
                budget["crossed"] + budget["conducts"],
            ),
            "V",
        ),
    ]
    nominal = results["nominal"]
    time = nominal.real("time")
    shown = (time >= common.STEP_AT - 0.1e-6) & (time <= common.STEP_AT + 1.4e-6)
    micro = (time[shown] - common.STEP_AT) * 1e6

    def cut(name: str) -> np.ndarray:
        return nominal.real(name)[shown]

    crossed = (budget["crossed"] - common.STEP_AT) * 1e6
    conducts = crossed + budget["conducts"] * 1e6
    waveforms = Graph(
        name="waveforms",
        title="1 uA to 500 mA with 1 uF at 5 V, nominal delays: the jump to range 3",
        xlabel="Time after the load step (us)",
        panels=(
            Panel("At the ladder (mV)", marks=((151.2, "jump threshold 151 mV"),)),
            Panel(
                "Comparator inputs (V)",
                marks=((0.764, "jump"), (0.584, "over-current"), (0.464, "step up")),
            ),
            Panel("Comparators and controller (V)"),
            Panel("Gate of the range 3 switch (V)"),
            Panel("Branch current (A)"),
        ),
        traces=(
            Trace(micro, common.ladder(nominal)[shown] * 1e3, "ladder, supply node to load", 0),
            Trace(micro, (cut("inp") - cut("inn")) * 1e3, "at the amplifier inputs", 0, "--"),
            Trace(micro, cut("cmp_in"), "amplifier output divided by 4.01", 1),
            Trace(micro, cut("cmp_up"), "CMP_UP", 2),
            Trace(micro, cut("cmp_oc"), "CMP_OC", 2),
            Trace(micro, cut("cmp_jump"), "CMP_JUMP", 2),
            Trace(micro, cut("gate_r1"), "GATE_R1", 2, "--"),
            Trace(micro, cut("gate_r3"), "GATE_R3", 2, "--"),
            Trace(micro, cut("g_r3"), "gate of Q14", 3),
            Trace(micro, cut("g_r1"), "gate of Q12", 3, "--"),
            Trace(micro, common.branch_r3(nominal)[shown], "0.1 ohm branch", 4),
            Trace(micro, cut("@r110[i]"), "in its shunt, with the gate current", 4, ":"),
            Trace(micro, cut("@r104[i]"), "33 ohm branch", 4, "--"),
            Trace(micro, cut("iprog"), "load", 4, ":"),
        ),
        xmarks=((crossed, "threshold"), (conducts, "conducts")),
    )
    traces = []
    for name in ("best", "nominal", "worst", "worst-slow-amplifier"):
        result = results[name]
        axis = (result.real("time") - found[name]["crossed"]) * 1e6
        part = (axis >= -0.2) & (axis <= 1.0)
        traces.append(Trace(axis[part], common.branch_r3(result)[part], name, 0))
        traces.append(Trace(axis[part], common.ladder(result)[part] * 1e3, name, 1))
    delays = Graph(
        name="delays",
        title="The 0.1 ohm branch after the ladder passes 151 mV, by set of delays",
        xlabel="Time after the ladder voltage passes the jump threshold (us)",
        panels=(Panel("Current in the 0.1 ohm branch (A)"), Panel("Ladder voltage (mV)")),
        traces=tuple(traces),
        xmarks=((0.55, "target 0.55 us"),),
    )
    notes = (
        "The branch counts as conducting from 50 mA, the level of the earlier "
        "simulations of the design; the specification names none. The charging "
        "current of the gate of the range 3 switch flows through the same shunt, "
        "about 0.6 A for 30 ns, before the channel conducts; it is taken out of the "
        "branch current with the current of the gate resistor. Counted in, the "
        "branch would seem to conduct about 30 ns earlier.",
        "Nominal: multiplexer 250 ohm, comparators 47 ns, sequencer 100 ns, driver "
        "30 ns and 7 ohm. Best: 125 ohm, 47 ns, 20 ns, 20 ns. Worst: 430 ohm, 80 ns, "
        "100 ns, 40 ns and 10 ohm. The driver figures are the limits of its "
        "datasheet at 18 V; at 12 V with a 3.3 V input it is slower by an amount "
        "the datasheet shows in a curve only.",
        "The sequencer is the model of rule F-16 with its reaction time as a "
        "parameter: the 100 ns are an input of this bench, not a result.",
        "The comparator model has one delay whatever the overdrive. Here the input "
        "rises by about 2.2 V per microsecond, so the overdrive passes 100 mV, the "
        "condition of the datasheet figure, within 45 ns.",
        "The amplifier model has 6.4 MHz of bandwidth at this gain and no spread; "
        "the last delay figure halves it to show what a slower part would cost.",
        "The source is 5 V or 0.8 V behind 20 mohm and holds its voltage; the load "
        "is a current sink with an edge of 10 ns beside 1 uF with 5 mohm.",
        common.VENDOR_NOTE,
    )
    return Outcome(tuple(figures), (waveforms, delays), notes)
