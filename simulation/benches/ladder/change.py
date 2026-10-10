"""A range change seen at the ladder: gates, branch currents, sense voltage."""

from __future__ import annotations

import numpy as np

from benches import frontend
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench

_LOAD = 2e-3
"""Load current of the run: inside range 1 and inside range 2."""

_UP = 15e-6
"""Instant of the step from range 1 to range 2."""

_DOWN = 30e-6
"""Instant of the step back to range 1."""

_END = 230e-6

_CDUT = 1e-6
"""Capacitance beside the load: the 1 uF of requirement R-07."""


def _deck(ctx: Context) -> str:
    circuit = ctx.circuit(frontend.ladder_refs(ctx.netlist), frontend.ALIASES)
    stimulus = "\n".join(
        [
            "* the source meter as an ideal 5 V source, the load as a current sink",
            "* with the 1 uF of requirement R-07 beside it",
            "Vsupply supply 0 5",
            f"Iload vout_s 0 PWL(0 50u 6u 50u 7u {_LOAD:g})",
            f"Cdut vout_s 0 {_CDUT:g}",
            "* commands: up to range 1 at 2 us, up to range 2, down to range 1",
            "Vup seq_up 0 PWL(0 0 2u 0 2.01u 3.3 2.5u 3.3 2.51u 0 "
            f"{_UP:g} 0 {_UP + 1e-8:g} 3.3 {_UP + 5e-7:g} 3.3 {_UP + 5.1e-7:g} 0)",
            f"Vdown seq_down 0 PULSE(0 3.3 {_DOWN:g} 10n 10n 0.5u 1)",
            "Vjump seq_jump 0 0",
            "Voc seq_oc 0 0",
            "Venable seq_enable 0 3.3",
            "Vouton seq_out_on 0 0",
        ]
    )
    control = [
        "save all @r101[i] @r104[i] @r107[i]",
        f"tran 5n {_END:g}",
    ]
    return ctx.deck(
        "Range change at the ladder: range 1 to range 2 and back at 2 mA",
        circuit,
        frontend.rails(vref=None),
        frontend.sequencer(comparators=False),
        stimulus,
        control=control,
        libraries=frontend.SEQUENCER_LIBRARIES,
    )


@bench(
    "ladder",
    "change",
    "A range change at the ladder: make-before-break of the range switches",
    "section 4.3 (make-before-break, gate drive), rule F-17",
)
def change(ctx: Context) -> Outcome:
    """The ladder carries 2 mA in range 1 and is stepped to range 2 and back.

    The model of the sequencer is told to step up and, later, to step down
    again. The run shows the
    lines of the controller, the gates behind the drivers, the currents of
    the three branches and the voltage that the multiplexer passes to the
    amplifier. The comparators and the amplifier are not in this circuit:
    the steps are commanded. The load has 1 uF beside it, so after a step the
    shunt carries the current that brings that capacitor to its new voltage:
    the reading follows the load with the time constant of shunt and
    capacitor.
    """
    result = ctx.run("up-down", _deck(ctx))
    time = result.real("time")
    micro = time * 1e6

    def node(name: str) -> np.ndarray:
        return result.real(name)

    gate_old, gate_new = node("gate_r1"), node("gate_r2")
    half = frontend.LOGIC_VOLTS / 2.0
    new_rises = measure.first_crossing(time, gate_new, half, rising=True, after=_UP)
    old_falls = measure.first_crossing(time, gate_old, half, rising=False, after=_UP)
    back_rises = measure.first_crossing(time, gate_old, half, rising=True, after=_DOWN)
    back_falls = measure.first_crossing(time, gate_new, half, rising=False, after=_DOWN)
    through_r2 = result.real("@r107[i]")
    through_r1 = result.real("@r104[i]")
    final_r2 = measure.mean(time, through_r2, _DOWN - 2e-6, _DOWN - 1e-6)
    conducts = measure.first_crossing(time, through_r2, 0.9 * final_r2, rising=True, after=_UP)
    sense = node("inp") - node("inn")
    burden = node("supply") - node("vout_s")
    sense_r2 = measure.mean(time, sense, _DOWN - 2e-6, _DOWN - 1e-6)
    sense_r1 = measure.mean(time, sense, _END - 2e-6, _END - 1e-6)
    before_up = measure.mean(time, sense, _UP - 2e-6, _UP - 1e-6)
    band_up = 0.001 * 0.1
    settled_up = measure.settling_time(time, sense, sense_r2, band_up, new_rises, _DOWN)
    tau_up = frontend.SHUNT_OHMS[2] * _CDUT
    expect_up = tau_up * float(np.log((before_up - sense_r2) / band_up))
    band_down = 0.01 * sense_r1
    settled_down = measure.settling_time(time, sense, sense_r1, band_down, back_rises)
    tau_down = frontend.SHUNT_OHMS[1] * _CDUT
    expect_down = tau_down * float(np.log(100.0))
    worst_burden = measure.extremes(time, burden, _UP, _END)[1]
    figures = (
        Figure(
            "overlap_up",
            "Step up: both gates commanded on together for",
            old_falls - new_rises,
            "s",
            expected=1e-6,
            low=0.8e-6,
            high=1.2e-6,
            source="rule F-17, about 1 us",
        ),
        Figure(
            "overlap_down",
            "Step down: both gates commanded on together for",
            back_falls - back_rises,
            "s",
            expected=1e-6,
            low=0.8e-6,
            high=1.2e-6,
            source="rule F-17, about 1 us",
        ),
        Figure(
            "new_branch_conducts",
            "Step up: new branch at 90 % of its current after the command",
            conducts - new_rises,
            "s",
            high=0.5e-6,
            source="section 4.4: a branch conducts well inside 0.55 us",
        ),
        Figure(
            "sense_r2",
            "Sense voltage in range 2 at 2 mA",
            sense_r2,
            "V",
            expected=_LOAD * frontend.SHUNT_OHMS[2],
            low=_LOAD * frontend.SHUNT_OHMS[2] * 0.995,
            high=_LOAD * frontend.SHUNT_OHMS[2] * 1.005,
            source="section 4.3",
        ),
        Figure(
            "sense_r1",
            "Sense voltage back in range 1 at 2 mA",
            sense_r1,
            "V",
            expected=_LOAD * frontend.SHUNT_OHMS[1],
            low=_LOAD * frontend.SHUNT_OHMS[1] * 0.995,
            high=_LOAD * frontend.SHUNT_OHMS[1] * 1.005,
            source="section 4.3",
        ),
        Figure(
            "settles_up",
            "Step up: sense voltage within 0.1 mV of its final value after",
            settled_up,
            "s",
            expected=expect_up,
            low=0.7 * expect_up,
            high=1.3 * expect_up,
            source="1 ohm with 1 uF: 6.4 time constants of 1 us, calculated here",
        ),
        Figure(
            "settles_down",
            "Step down: sense voltage within 1 % of its final value after",
            settled_down,
            "s",
            expected=expect_down,
            low=0.7 * expect_down,
            high=1.3 * expect_down,
            source="31.95 ohm with 1 uF: 4.6 time constants of 32 us, calculated here",
        ),
        Figure(
            "burden_during_change",
            "Largest burden from the step up to the end of the run",
            worst_burden,
            "V",
            high=_LOAD * 33.0 * 1.05,
            source="the burden of range 1 at this current, never more",
        ),
    )
    whole = Graph(
        name="settling",
        title="The whole run: the reading follows the load with shunt times capacitor",
        xlabel="Time (us)",
        panels=(Panel("At the multiplexer output (mV)"), Panel("Branch current (mA)")),
        traces=(
            Trace(micro, sense * 1e3, "sense, INP - INN", 0),
            Trace(micro, burden * 1e3, "burden, supply node to load", 0, "--"),
            Trace(micro, through_r1 * 1e3, "33 ohm branch", 1),
            Trace(micro, through_r2 * 1e3, "1 ohm branch", 1),
        ),
        xmarks=((_UP * 1e6, "step up"), (_DOWN * 1e6, "step down")),
    )
    shown = (time >= _UP - 2e-6) & (time <= _DOWN + 6e-6)
    micro, time_shown = micro[shown], time[shown]
    del time_shown

    def cut(values: np.ndarray) -> np.ndarray:
        return values[shown]

    graph = Graph(
        name="waveforms",
        title="Range 1 to range 2 and back at 2 mA, 1 uF at the load",
        xlabel="Time (us)",
        panels=(
            Panel("Controller lines (V)"),
            Panel("Gates of the switches (V)"),
            Panel("Branch current (mA)"),
            Panel("At the multiplexer output (mV)"),
        ),
        traces=(
            Trace(micro, cut(gate_old), "GATE_R1", 0),
            Trace(micro, cut(gate_new), "GATE_R2", 0),
            Trace(micro, cut(node("mux_a0")), "MUX_A0", 0, "--"),
            Trace(micro, cut(node("mux_a1")), "MUX_A1", 0, "--"),
            Trace(micro, cut(node("g_r1")), "gate of Q12 (R1)", 1),
            Trace(micro, cut(node("g_r2")), "gate of Q13 (R2)", 1),
            Trace(micro, cut(through_r1 * 1e3), "33 ohm branch", 2),
            Trace(micro, cut(through_r2 * 1e3), "1 ohm branch", 2),
            Trace(micro, cut(result.real("@r101[i]") * 1e3), "1 kohm branch", 2),
            Trace(micro, cut(sense * 1e3), "sense, INP - INN", 3),
            Trace(micro, cut(burden * 1e3), "burden, supply node to load", 3, "--"),
        ),
        xmarks=((_UP * 1e6, "step up"), (_DOWN * 1e6, "step down")),
    )
    notes = (
        "The sequencer is the model of rules F-16 to F-18, with a reaction time of "
        "100 ns; no program of the controller exists yet.",
        "The drivers and the multiplexer are behavioral models with typical delays "
        "(30 ns and 92 ns); the comparators and the amplifier are not in this run.",
        "With a capacitor at the load the shunt current is not the load current "
        "until that capacitor has reached its new voltage. In range 0 the same "
        "1 uF gives a time constant of 1 ms.",
    )
    return Outcome(figures, (graph, whole), notes)
