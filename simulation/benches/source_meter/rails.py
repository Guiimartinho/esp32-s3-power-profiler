"""The source with a rail missing or falling, and the minimum load of the regulator."""

from __future__ import annotations

import numpy as np

from benches.source_meter import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_LOW = 0.8
_HIGH = 5.0

_QUIESCENT = {"typical": 0.29e-3, "low limit": 0.58e-3, "high limit": 0.81e-3}
"""Parameter iq of the regulator model for a quiescent current of 0.38 mA
(typical), 0.67 mA and 0.90 mA at 12.7 V between VCONTROL and the output: the
two currents with which section 4.2 calculates 0.87 V and 1.17 V."""

_SLOW_STOP = 0.4
"""Length of the runs without -4 V_A: an output above its set-point moves only with
the minimum load and the output capacitors, about 36 ms."""

_LEAKAGE = 2e-3
"""Reverse current of D11 at 100 C and 4 V, at the most (DS30217, page 2)."""

_OFF = 30e-3
"""Instant at which the rails begin to fall in the power-off runs."""

_FALLS = (1e-3, 10e-3)
"""Time in which the 5 V rail and the boost output fall to zero (assumption)."""

_OFF_STOP = 80e-3

_CONTROL_LIMIT = -0.3
"""Rating of the VCONTROL pin relative to the output (LT3080 Rev. E, page 2)."""

_HOLD = (0.18, 0.42)
"""Shortest and longest hold-off of the supervisor (section 3)."""

_HOLD_START = 60e-3
"""Instant at which the DAC loses its supply in the hold-off run."""


def _falling(volts: float, seconds: float, start: float, stop: float) -> str:
    """A rail that rises as in every power-up run and falls to zero later."""
    return f"PWL(0 0 {start:g} 0 {stop:g} {volts:g} {_OFF:g} {volts:g} {_OFF + seconds:g} 0)"


def _off_deck(ctx: Context, seconds: float) -> str:
    """The source at 5.00 V without load; then every rail falls."""
    circuit = common.source(
        ctx,
        _HIGH,
        with_dut=False,
        overrides={common.DAC: common.power_up_code(ctx, common.code_of(_HIGH))},
        scales={"C41": common.SETTLE_FILTER},
    )
    slow = max(seconds, 14e-3)
    rails = common.rails(
        p5=_falling(common.RAIL_5V, seconds, 10e-6, 110e-6),
        p13=_falling(common.RAIL_13V5, seconds, 20e-6, 150e-6),
        p3v3=_falling(common.RAIL_3V3, 5e-3, 160e-6, 260e-6),
        m4=_falling(common.RAIL_M4V, 5e-3, 250e-6, 300e-6),
        p12=_falling(common.RAIL_12V, slow, 300e-6, 400e-6),
        vref=_falling(common.REFERENCE, 5e-3, 400e-6, 450e-6),
    )
    controller = common.controller(
        _falling(common.LOGIC_VOLTS, 0.3e-3, 500e-6, 501e-6),
        _falling(common.OK_SHARE * common.RAIL_5V, 20e-6, 200e-6, 210e-6),
    )
    return ctx.deck(
        f"Power-off from 5.00 V, the 5 V rail and the boost output falling in {seconds * 1e3:g} ms",
        circuit,
        rails,
        controller,
        control=[f"tran 2u {_OFF_STOP:g} 0 20u"],
    )


def _hold_deck(ctx: Context) -> str:
    """The DAC with its filter alone: at 5.00 V, then without supply."""
    refs = ("U15", "R54", "C41", "R55", "R56", "C38")
    dac = common.part(ctx, common.DAC, code=common.code_of(_HIGH), code1=-1, t1=_HOLD_START)
    circuit = common.source(ctx, _HIGH, refs=refs, overrides={common.DAC: dac})
    stimulus = "\n".join(
        [
            "* the DAC and its filter; the input of the buffer takes no current that counts",
            f"Vp3v3a p3v3_a 0 {common.RAIL_3V3:g}",
            f"Vref vref 0 {common.REFERENCE:g}",
            "Rin dac_filt 0 1e12",
        ]
    )
    return ctx.deck(
        "Set-point filter during a hold-off of the supervisor",
        circuit,
        stimulus,
        control=[f"tran 0.1m {_HOLD_START + 0.5:g} 0 1m"],
    )


def _minimum_amps(run: RunResult) -> float:
    """The current of R69 at the end of a run."""
    return (common.last(run, "ldo_out") - common.last(run, "m4v_a")) / 1300.0


@bench(
    "source_meter",
    "rails",
    "A missing or falling rail, the minimum load and the set-point filter in a hold-off",
    "section 4.2 (clamps, minimum load, set-point filter), decision D-57, rules F-3 and F-7",
)
def rails(ctx: Context) -> Outcome:
    """The source is brought to rest with one rail absent, and then every rail falls.

    Without -4 V_A the minimum load R69 ends on a rail at 0 V: runs with the
    typical quiescent current of the regulator and with the two values that
    section 4.2 calculates with give the output at a set-point of 0.80 V.
    Without the boost output the regulator has no control supply and R69
    pulls its output below ground, where D12 holds it. A run with 2 mA
    forced into the output stands for the leakage of a hot D11. Two
    power-off runs let the 5 V rail and the boost output fall within 1 ms
    and within 10 ms and show the VCONTROL pin against the output. One run
    of the DAC with its filter alone shows what C41 holds during a
    hold-off of the supervisor.
    """
    decks = {
        "nominal-low": common.settle_deck(ctx, "0.80 V with every rail", _LOW),
        "nominal-high": common.settle_deck(ctx, "5.00 V with every rail", _HIGH),
        "no-boost": common.settle_deck(
            ctx, "0.80 V without the boost output", _LOW, supplies={"p13": 0.0}
        ),
        "leakage": common.settle_deck(
            ctx,
            "0.80 V with 2 mA into the regulator output",
            _LOW,
            extra=f"Ileak 0 ldo_out {common.stepped(_LEAKAGE)}\n",
        ),
    }
    for name, value in _QUIESCENT.items():
        decks[f"no-m4-{name.split()[0]}"] = common.settle_deck(
            ctx,
            f"0.80 V without -4 V_A, quiescent current of the regulator: {name}",
            _LOW,
            supplies={"m4": 0.0},
            overrides={common.REGULATOR: common.part(ctx, common.REGULATOR, iq=value)},
            stop=_SLOW_STOP,
        )
    runs = ctx.run_many(decks)
    figures = [
        Figure(
            "minimum_low",
            "Current of the minimum load R69 at 0.80 V",
            _minimum_amps(runs["nominal-low"]),
            "A",
            expected=3.7e-3,
            low=3.6e-3,
            high=3.8e-3,
            source="section 4.2: 3.7 mA at 0.8 V",
        ),
        Figure(
            "minimum_high",
            "Current of the minimum load R69 at 5.00 V",
            _minimum_amps(runs["nominal-high"]),
            "A",
            expected=6.9e-3,
            low=6.8e-3,
            high=7.0e-3,
            source="section 4.2: 6.9 mA at 5.0 V",
        ),
        Figure(
            "no_m4_typical",
            "Without -4 V_A, typical regulator: output at a set-point of 0.80 V",
            common.last(runs["no-m4-typical"], "ldo_out"),
            "V",
            expected=0.8,
            low=0.79,
            high=0.81,
            source="section 4.2: 0.8 V with a typical regulator",
        ),
        Figure(
            "no_m4_low",
            "Without -4 V_A, quiescent current of 0.67 mA: output",
            common.last(runs["no-m4-low"], "ldo_out"),
            "V",
            expected=0.87,
            low=0.82,
            high=0.92,
            source="section 4.2: 0.87 V to 1.17 V at the limits",
        ),
        Figure(
            "no_m4_high",
            "Without -4 V_A, quiescent current of 0.90 mA: output",
            common.last(runs["no-m4-high"], "ldo_out"),
            "V",
            expected=1.17,
            low=1.12,
            high=1.22,
            source="section 4.2: 0.87 V to 1.17 V at the limits",
        ),
        Figure(
            "no_boost",
            "Without the boost output, -4 V_A present: regulator output",
            common.last(runs["no-boost"], "ldo_out"),
            "V",
            expected=-0.2,
            low=-0.3,
            high=0.0,
            source="section 4.2: D12 holds the output at about -0.2 V (estimate)",
        ),
        Figure(
            "no_boost_set",
            "In that state: SET pin above the output",
            common.last(runs["no-boost"], "ldo_set") - common.last(runs["no-boost"], "ldo_out"),
            "V",
        ),
        Figure(
            "leakage",
            "2 mA into the output at 0.80 V: rise of the output",
            common.last(runs["leakage"], "ldo_out") - common.last(runs["nominal-low"], "ldo_out"),
            "V",
            high=1e-3,
            source="section 4.2: the minimum load absorbs the leakage of D11, up to 2 mA at "
            "100 C; 1 mV is the limit of this bench",
        ),
    ]
    figures.append(
        Figure(
            "rest",
            "Largest movement of output and pre-regulator in the last 2 ms of these runs",
            max(common.at_rest(run) for run in runs.values()),
            "V",
            high=common.REST_LIMIT,
            source="limit of this bench: a run counts as at rest below 0.1 mV",
        )
    )
    graphs: list[Graph] = []
    for seconds in _FALLS:
        tag = f"{seconds * 1e3:g}ms"
        run = ctx.run(f"power-off-{tag}", _off_deck(ctx, seconds), keep=seconds == _FALLS[0])
        time = run.real("time")
        out = run.real("ldo_out")
        control = run.real("vctl") - out
        pin = run.real("ldo_in") - out
        figures += [
            Figure(
                f"off_control_{tag}",
                f"Power-off in {seconds * 1e3:g} ms: lowest voltage of VCONTROL above the output",
                measure.extremes(time, control, _OFF, _OFF_STOP)[0],
                "V",
                expected=0.88,
                low=_CONTROL_LIMIT,
                source="section 4.2: at least 0.88 V (simulated); the limit is the rating of "
                "the pin, 0.3 V below the output",
            ),
            Figure(
                f"off_in_{tag}",
                f"Power-off in {seconds * 1e3:g} ms: lowest voltage of the IN pin above the output",
                measure.extremes(time, pin, _OFF, _OFF_STOP)[0],
                "V",
                low=_CONTROL_LIMIT,
                source="LT3080 Rev. E, page 2 (D-57)",
            ),
            Figure(
                f"off_output_{tag}",
                f"Power-off in {seconds * 1e3:g} ms: lowest regulator output",
                measure.extremes(time, out, _OFF, _OFF_STOP)[0],
                "V",
                low=-0.3,
                source="section 4.2: D12 holds the output at about -0.2 V; 0.3 V is the limit "
                "of this bench",
            ),
        ]
        shown = time >= _OFF - 2e-3
        graphs.append(
            Graph(
                name=f"power-off-{tag}",
                title="Power-off from 5.00 V: 5 V rail and boost output fall in "
                f"{seconds * 1e3:g} ms",
                xlabel="Time (ms)",
                panels=(Panel("Voltage (V)"), Panel("Above the regulator output (V)")),
                traces=(
                    Trace(time[shown] * 1e3, out[shown], "regulator output", 0),
                    Trace(time[shown] * 1e3, run.real("vctl")[shown], "VCONTROL pin", 0),
                    Trace(time[shown] * 1e3, run.real("p13v5")[shown], "boost output", 0, "--"),
                    Trace(time[shown] * 1e3, run.real("v_pre")[shown], "pre-regulator output", 0),
                    Trace(time[shown] * 1e3, control[shown], "VCONTROL pin", 1),
                    Trace(time[shown] * 1e3, pin[shown], "IN pin", 1),
                ),
                xmarks=((_OFF * 1e3, "rails fall"),),
            )
        )
    hold = ctx.run("hold-off", _hold_deck(ctx))
    clock = hold.real("time")
    filtered = hold.real("dac_filt")
    before = measure.value_at(clock, filtered, _HOLD_START - 1e-3)
    for seconds, share in zip(_HOLD, (0.70, 0.44), strict=True):
        figures.append(
            Figure(
                f"hold_{seconds * 1e3:g}ms",
                f"Set-point filter {seconds * 1e3:g} ms after the DAC lost its supply: share "
                "of the last value",
                100.0 * measure.value_at(clock, filtered, _HOLD_START + seconds) / before,
                "%",
                expected=100.0 * share,
                low=100.0 * share - 3.0,
                high=100.0 * share + 3.0,
                source="section 4.2: C41 still holds 44 % to 70 % of the last value",
            )
        )
    graphs.append(
        Graph(
            name="hold-off",
            title="The set-point filter after the DAC output turns to 500 kohm",
            xlabel="Time (ms)",
            panels=(Panel("Voltage at C41 (V)"),),
            traces=(Trace(clock * 1e3, np.asarray(filtered), "input of the buffer U17", 0),),
            xmarks=tuple(
                ((_HOLD_START + seconds) * 1e3, f"{seconds * 1e3:g} ms") for seconds in _HOLD
            ),
        )
    )
    notes = (
        "A missing rail is a source at 0 V: -4 V_A with its clamp D8 and the boost "
        "output with its loads belong to another block, and how far below 0 V or above "
        "it such a rail rests is not simulated here.",
        "The two quiescent currents of the regulator, 0.67 mA and 0.90 mA, are the "
        "values behind the 0.87 V and 1.17 V of section 4.2. The datasheet guarantees "
        "0.5 mA at 10 V and 1 mA at 25 V between the supply pins and the output.",
        "The diode model for D11 and D12 leaks 4 uA; the leakage of a hot D11 is a "
        "current source of 2 mA into the output here.",
        "The fall times of the rails at power-off are assumptions: the 5 V rail and the "
        "boost output together in 1 ms or in 10 ms, 3V3_A, -4 V_A and the reference in "
        "5 ms, +12 V_A in 14 ms (section 3 gives 14 ms for +12 V_A and 4 ms to 6 ms for "
        "3V3_A). The paths to the device are open and the output carries only its "
        "minimum load.",
        "At power-off the diode D10 blocks, and the capacitors of the VCONTROL pin can "
        "only empty into the output through the regulator. They stop doing so where "
        "the model ends its quiescent current, near 0.55 V between the two pins, and "
        "that is the lowest value read here: a property of the model, as the 0.88 V of "
        "section 4.2 is one of the model used there. What the run shows is the sign: "
        "VCONTROL follows the output down from above and does not cross it.",
        "The DAC without supply is its model after power-on, 500 kohm to ground "
        "(datasheet value for the state after a reset).",
    )
    return Outcome(tuple(figures), tuple(graphs), notes)
