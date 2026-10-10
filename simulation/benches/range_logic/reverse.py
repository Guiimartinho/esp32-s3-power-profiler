"""Reverse current through the ladder: what the chain shows of it."""

from __future__ import annotations

import numpy as np

from benches import frontend
from benches.range_logic import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_UNDER_RANGE_CODE = 650
"""Code below which a sample is flagged as under-range (rule F-22)."""

_UNDER_RANGE_VOLTS = _UNDER_RANGE_CODE * 2.5 / 65536.0
"""The same as a voltage at the converter input, V."""

_RAMP_START = 0.1e-3
_RAMP_END = 3.1e-3
"""The reverse current rises from 0 to 30 mA between these instants, s."""

_RAMP_AMPS = 0.03
_STEP_AT = 3.4e-3
"""Instant at which the reverse current steps to 1 A, s."""

_END = 3.8e-3


def _deck(ctx: Context, index: int) -> str:
    """A range at rest, then a current that flows from the load into the output."""
    circuit = common.front_end(ctx)
    current = common.pwl(
        (
            (0.0, 0.0),
            (_RAMP_START, 0.0),
            (_RAMP_END, -_RAMP_AMPS),
            (_STEP_AT, -_RAMP_AMPS),
            (_STEP_AT + 1e-6, -1.0),
        )
    )
    return ctx.deck(
        f"Reverse current in range {index}: a ramp to 30 mA, then 1 A",
        circuit,
        frontend.rails(),
        common.source(5.0),
        common.controller(),
        common.dut(current, None),
        common.rest(circuit, index),
        control=[f"save {common.SAVED} adc_in @r90[i]", f"tran 0.5u {_END:g}"],
        options=common.options(ctx),
        libraries=frontend.SEQUENCER_LIBRARIES,
    )


def _settled(result: RunResult, name: str) -> float:
    """A waveform at the end of the run, with the reverse current at 1 A."""
    time = result.real("time")
    return measure.mean(time, result.real(name), _END - 50e-6, _END)


@bench(
    "range_logic",
    "reverse",
    "Reverse current through the ladder: under-range level and voltage across the ladder",
    "section 4.4 (reverse current, decision D-69), rule F-22",
)
def reverse(ctx: Context) -> Outcome:
    """A current flows from the load back into the output, in range 3 and in range 0.

    The comparators see forward current only, and the converter reads a
    reverse current as a code below the pedestal. The run lets the reverse
    current rise slowly to 30 mA and reads at which current the converter
    input falls below the level of code 650, from which firmware flags the
    samples as under-range. Then the current steps to 1 A, and the run reads
    the voltage across the ladder with range 3 selected, where the current
    flows through the channel of its switch, and with every range gate low,
    where it flows through the body diodes.
    """
    range_3 = ctx.run("range-3", _deck(ctx, 3))
    range_0 = ctx.run("range-0", _deck(ctx, 0))
    time = range_3.real("time")
    converter = range_3.real("adc_in")
    crossed = measure.first_crossing(
        time, converter, _UNDER_RANGE_VOLTS, rising=False, after=_RAMP_START
    )
    at_flag = -measure.value_at(time, range_3.real("@r110[i]"), crossed)
    changes = sum(common.range_changes(run)[0].size for run in (range_3, range_0))
    highest = max(
        float(np.max(run.real(name)))
        for run in (range_3, range_0)
        for name in ("cmp_up", "cmp_oc", "cmp_jump")
    )
    figures = [
        Figure(
            "flag_current",
            "Range 3: reverse current at which the converter input passes code 650",
            at_flag,
            "A",
            expected=0.013,
            low=0.0125,
            high=0.0135,
            source="rule F-22: about 13 mA backward, calculated; to its last digit",
        ),
        Figure(
            "ladder_range_3",
            "Range 3, 1 A backward: voltage across the ladder",
            -_settled(range_3, "supply") + _settled(range_3, "vout_s"),
            "V",
            expected=0.105,
            low=0.100,
            high=0.110,
            source="section 4.4: 105 mV per ampere, calculated",
        ),
        Figure(
            "converter_range_3",
            "Range 3, 1 A backward: converter input",
            _settled(range_3, "adc_in"),
            "V",
            high=_UNDER_RANGE_VOLTS,
            source="rule F-22: a code below 650 is flagged as under-range",
        ),
        Figure(
            "amplifier_range_3",
            "Range 3, 1 A backward: amplifier output",
            _settled(range_3, "amp_raw"),
            "V",
        ),
        Figure(
            "ladder_range_0",
            "Range gates low, 1 A backward: voltage across the ladder",
            -_settled(range_0, "supply") + _settled(range_0, "vout_s"),
            "V",
        ),
        Figure(
            "converter_range_0",
            "Range gates low, 1 A backward: converter input",
            _settled(range_0, "adc_in"),
            "V",
            high=_UNDER_RANGE_VOLTS,
            source="rule F-22: a code below 650 is flagged as under-range",
        ),
        Figure(
            "comparators",
            "Highest level of a comparator output in both runs",
            highest,
            "V",
            high=0.1,
            source="section 4.4: the comparators see forward current only",
        ),
        Figure(
            "range_changes",
            "Range changes in both runs",
            float(changes),
            "",
            high=0.0,
            source="section 4.4: a reverse current moves no range by itself",
        ),
    ]
    traces: list[Trace] = []
    for label, run in (("range 3", range_3), ("range gates low", range_0)):
        axis = run.real("time") * 1e3
        traces += [
            Trace(axis, -run.real("iprog") * 1e3, f"{label}", 0),
            Trace(axis, (run.real("vout_s") - run.real("supply")) * 1e3, label, 1),
            Trace(axis, run.real("amp_raw"), label, 2),
            Trace(axis, run.real("adc_in") * 1e3, label, 3),
        ]
    graph = Graph(
        name="reverse",
        title="A current from the load back into the output at 5 V",
        xlabel="Time (ms)",
        panels=(
            Panel("Reverse current (mA)", log=True),
            Panel("Load node above the supply node (mV)"),
            Panel("Amplifier output (V)"),
            Panel(
                "Converter input (mV)",
                marks=((_UNDER_RANGE_VOLTS * 1e3, "code 650"), (50.08, "pedestal")),
            ),
        ),
        traces=tuple(traces),
    )
    notes = (
        "The load is a current source into the output, and the source of the "
        "instrument takes that current at 5 V behind 20 mohm. The regulator of "
        "the source meter cannot sink current, and an external supply may not: "
        "what the supply node then does is not in this run.",
        "The converter is not in the circuit; code 650 is taken as 24.8 mV at "
        "its input. With 1 A backward that input rests at the lower limit of "
        "its driver: 2 mV in the model of the driver, 20 mV at the most by the "
        "datasheet figure in the head of that model. Both lie below the level "
        "of code 650.",
        "With every range gate low the current divides between the body diodes "
        "of the five transistors of the ladder by their models, which are "
        "typical parts at 25 C; the share of each and its heating are not "
        "figures to take from this run.",
        "No program is in the loop: that firmware selects range 3 and opens the "
        "output after 100 ms (rule F-22) is not simulated.",
        common.VENDOR_NOTE,
    )
    return Outcome(tuple(figures), (graph,), notes)
