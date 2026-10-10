"""The models of the charge pump and of the boost converter against their datasheets."""

from __future__ import annotations

import numpy as np

from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.engine import RunResult

_LIBRARY = ("analog_rails.lib",)
"""The model file of the analog rails."""

_PUMP_LEVEL = -1.22 * (237e3 + 500e3) / 500e3
"""Output of the datasheet circuit of the pump: R1 = 237 kohm, R2 = 500 kohm."""

_LIMITS = ((5.0, 2.6, 2.02), (3.3, 1.68, 1.49))
"""Typical switch current limit of the boost converter: supply, limit at a duty
cycle of 40 % and slope per unit of duty cycle (SNVS735B page 13, figure 21)."""

_CLAMP = 12.0
"""Output voltage that the limit runs are held at."""

_LOAD_LIMIT = {5.0: 0.57, 3.3: 0.16}
"""Largest load current of a typical part at 12 V by supply, in amperes: bench
data of the manufacturer (SNVS735B page 14, figure 22, read from the curve)."""


def _pump_deck(ctx: Context, model: str, step: str) -> str:
    """The typical application of the datasheet with a load that steps up, then the enable off."""
    lines = [
        "* SNVSA85D page 1: C1 1 uF, C2 4.7 uF, C3 4.7 uF, C4 2.2 uF; -1.8 V of output",
        "Vin vin 0 PWL(0 0 50u 5)",
        "Ven en 0 PWL(0 0 100u 0 101u 3 4m 3 4.001m 0)",
        "Cin vin 0 4.7u",
        f"X1 vin 0 cpo out fb en cn cp {model}",
        "Cfly cp cn 1u",
        "Ccp cpo 0 4.7u",
        "Cout out 0 2.2u",
        "R1 fb out 237k",
        "R2 fb 0 500k",
        "Iload 0 out PWL(0 0 1m 0 1.01m 10m 2m 10m 2.01m 100m 3m 100m 3.01m 200m 4m 200m 4.001m 0)",
    ]
    return ctx.deck(
        f"LM27761 ({model}): start, load steps, shutdown",
        "\n".join(lines),
        control=["save out cpo vin en", f"tran {step} 7m 0 {step}"],
        libraries=_LIBRARY,
    )


def _pump_lockout_deck(ctx: Context) -> str:
    lines = [
        "* the supply falls from 5 V to 2.2 V and returns, 10 mA of load",
        "Vin vin 0 PWL(0 0 50u 5 2m 5 30m 2.2 58m 5)",
        "Ven en 0 PWL(0 0 100u 0 101u 3)",
        "X1 vin 0 cpo out fb en cn cp LM27761_AVG",
        "Cfly cp cn 1u",
        "Ccp cpo 0 4.7u",
        "Cout out 0 2.2u",
        "R1 fb out 237k",
        "R2 fb 0 500k",
        "Rload out 0 180",
    ]
    return ctx.deck(
        "LM27761 (averaged): lock-out against the supply",
        "\n".join(lines),
        control=["save out cpo vin", "tran 10u 60m 0 10u"],
        libraries=_LIBRARY,
    )


def _pump_figures(run: RunResult, tag: str, label: str, band: float) -> list[Figure]:
    time = run.real("time")
    out, pump, supply = run.real("out"), run.real("cpo"), run.real("vin")

    def drop(start: float, stop: float) -> float:
        return measure.mean(time, supply, start, stop) + measure.mean(time, pump, start, stop)

    resistance = (drop(3.8e-3, 4e-3) - drop(2.8e-3, 3e-3)) / 0.1
    return [
        near(
            f"{tag}_level",
            f"{label}: output of the datasheet circuit, 10 mA",
            measure.mean(time, out, 1.8e-3, 2e-3),
            "V",
            _PUMP_LEVEL,
            0.005,
            "SNVSA85D page 13, equation 5",
        ),
        near(
            f"{tag}_light",
            f"{label}: pump output short of the supply at 10 mA",
            drop(1.8e-3, 2e-3),
            "V",
            0.027 * 5.0,
            0.25,
            "SNVSA85D page 15, figures 7-3 and 7-4: 2.7 % of the supply",
        ),
        near(
            f"{tag}_resistance",
            f"{label}: output resistance of the pump between 100 mA and 200 mA",
            resistance,
            "ohm",
            2.5,
            band,
            "SNVSA85D page 1: 2.5 ohm at 5 V",
        ),
        near(
            f"{tag}_moves",
            f"{label}: output at 10 % after the enable",
            measure.first_crossing(time, out, 0.1 * _PUMP_LEVEL, rising=False) - 0.1e-3,
            "s",
            0.33e-3,
            0.3,
            "SNVSA85D page 7, figure 5-10: 0.32 ms before the output moves",
        ),
        near(
            f"{tag}_there",
            f"{label}: output at 90 % after the enable",
            measure.first_crossing(time, out, 0.9 * _PUMP_LEVEL, rising=False) - 0.1e-3,
            "s",
            0.46e-3,
            0.3,
            "SNVSA85D page 7, figure 5-10: 0.14 ms of ramp after that",
        ),
        near(
            f"{tag}_discharge",
            f"{label}: output from 90 % to 10 % after the enable has fallen, no load",
            measure.rise_time(time, out, 0.9 * _PUMP_LEVEL, 0.1 * _PUMP_LEVEL, after=4e-3),
            "s",
            0.8 * abs(_PUMP_LEVEL) * 2.2e-6 / 1.85e-3,
            0.2,
            "SNVSA85D page 10: the output is pulled to ground with 1.85 mA",
        ),
    ]


@bench(
    "models",
    "analog-rails-lm27761",
    "LM27761 models against the datasheet",
    "the two models of the charge pump U11: switch by switch and averaged",
)
def lm27761(ctx: Context) -> Outcome:
    """Both models of the pump run the typical application of the datasheet.

    The supply is 5 V, the output is set to -1.8 V, and the load steps to
    10 mA, 100 mA and 200 mA before the enable falls. The run gives the
    output, the level of the pump at light load, its output resistance, the
    times of the start and the discharge in shutdown. A second run takes the
    supply of the averaged model down to 2.2 V and back for the lock-out.
    """
    switched = ctx.run("switched", _pump_deck(ctx, "LM27761", "25n"))
    averaged = ctx.run("averaged", _pump_deck(ctx, "LM27761_AVG", "2u"))
    figures = _pump_figures(switched, "switched", "Switch by switch", 0.2)
    figures += _pump_figures(averaged, "averaged", "Averaged", 0.05)
    lock = ctx.run("lockout", _pump_lockout_deck(ctx))
    time = lock.real("time")
    out, supply = lock.real("out"), lock.real("vin")
    off = measure.first_crossing(time, out, -0.9, rising=True, after=2e-3)
    back = measure.first_crossing(time, out, -0.9, rising=False, after=30e-3)
    figures += [
        Figure(
            "lockout_off",
            "Averaged: supply at which the output goes",
            float(np.interp(off, time, supply)),
            "V",
            low=2.3,
            high=2.7,
            source="SNVSA85D page 10: off at 2.4 V; the regulator runs out of head room first",
        ),
        near(
            "lockout_on",
            "Averaged: supply at which the output returns",
            float(np.interp(back - 0.4e-3, time, supply)),
            "V",
            2.6,
            0.04,
            "SNVSA85D page 10: on at 2.6 V (0.4 ms of start taken off)",
        ),
    ]
    t1, t2 = switched.real("time"), averaged.real("time")
    graph = Graph(
        name="run",
        title="LM27761 models in the typical application: start, 10 mA, 100 mA, 200 mA, off",
        xlabel="Time (ms)",
        panels=(Panel("Output (V)"), Panel("Pump output ahead of the regulator (V)")),
        traces=(
            Trace(t1[::40] * 1e3, switched.real("out")[::40], "switch by switch", 0),
            Trace(t2 * 1e3, averaged.real("out"), "averaged", 0, "--"),
            Trace(t1[::40] * 1e3, switched.real("cpo")[::40], "switch by switch", 1),
            Trace(t2 * 1e3, averaged.real("cpo"), "averaged", 1, "--"),
        ),
    )
    notes = (
        "The limits are the fit this project asks of the models. The times of the start "
        "are read from a scope picture of the datasheet.",
        "The level of the pump at light load is read from two figures of the datasheet; "
        "the hysteresis of the pulse skipping in the switched model (10 mV) is an "
        "assumption.",
        "The output ripple of the datasheet (0.8 mV to 3.2 mV, figure 5-1) is not "
        "reproduced: the model passes only what the pump ripple leaves through a "
        "feed-through fitted to the 35 dB at 2 MHz.",
    )
    return Outcome(tuple(figures), (graph,), notes)


def _limit_deck(ctx: Context, model: str, supply: float, step: str) -> str:
    """The converter at its current limit: feedback at ground, output held at 12 V."""
    inductor = "XL vin sw L_74438357100" if model == "LMR62014" else "* (no inductor: averaged)"
    lines = [
        f"Vin vin 0 PWL(0 0 20u {supply:g})",
        "Ren vin en 51k",
        inductor,
        f"X1 sw 0 fb en vin {model}",
        "Rfb fb 0 1k",
        "D1 sw o B0530W",
        f"Vclamp o 0 {_CLAMP:g}",
    ]
    return ctx.deck(
        f"{model}: current limit at {supply:g} V of supply, output held at {_CLAMP:g} V",
        "\n".join(lines),
        control=[
            "save sw vin i(Vclamp) i(Vin)" + (" @l.xl.l1[i]" if model == "LMR62014" else ""),
            f"tran {step} 0.6m 0 {step}",
        ],
        libraries=_LIBRARY,
    )


def _regulation_deck(ctx: Context) -> str:
    """The basic application of the datasheet: 5 V to 12 V."""
    lines = [
        "* SNVS735B page 2: R1 117 kohm, R2 13.3 kohm, CF 220 pF, L 10 uH, C2 4.7 uF",
        "Vin vin 0 PWL(0 0 0.2m 5)",
        "Cin vin 0 2.2u",
        "Ren vin en 51k",
        "XL vin sw L_74438357100",
        "X1 sw 0 fb en vin LMR62014",
        "D1 sw out B0530W",
        "R1 out fb 117k",
        "R2 fb 0 13.3k",
        "Cf out fb 220p",
        "Cout out 0 4.7u",
        "Rload out 0 240",
    ]
    return ctx.deck(
        "LMR62014: the basic application of the datasheet, 50 mA",
        "\n".join(lines),
        control=["save out sw vin @l.xl.l1[i]", "tran 5n 8m 0 20n"],
        libraries=_LIBRARY,
    )


@bench(
    "models",
    "analog-rails-lmr62014",
    "LMR62014 models against the datasheet",
    "the two models of the boost converter U10: cycle by cycle and averaged",
)
def lmr62014(ctx: Context) -> Outcome:
    """The converter models at their current limit and in the datasheet application.

    With the feedback pin at ground the converter asks for all the current
    it can; the output is held at 12 V by a source. The highest inductor
    current is then the switch current limit at the duty cycle that the
    supply and 12 V give, and it is compared with the curve of the
    datasheet at 5 V and at 3.3 V. The current into the 12 V source is
    compared between the cycle-by-cycle and the averaged model. A third
    circuit is the basic application of the datasheet, from 5 V to 12 V.
    """
    figures: list[Figure] = []
    traces: list[Trace] = []
    for supply, at_40, slope in _LIMITS:
        tag = f"{supply:g}v".replace(".", "p")
        cycle = ctx.run(f"limit-{tag}", _limit_deck(ctx, "LMR62014", supply, "5n"))
        mean = ctx.run(f"limit-averaged-{tag}", _limit_deck(ctx, "LMR62014_AVG", supply, "1u"))
        time = cycle.real("time")
        node = cycle.real("sw")
        late = time >= 0.4e-3
        edges = measure.crossings(time[late], node[late], 0.5 * _CLAMP, rising=True)
        period = float(np.median(np.diff(edges)))
        closed = float(edges.size) / ((time[-1] - 0.4e-3) * 1.6e6)
        high = float(np.mean(node[late] > 0.5 * _CLAMP))
        duty = 1.0 - high
        peak = float(np.max(cycle.real("@l.xl.l1[i]")[late]))
        expected = at_40 - slope * (duty - 0.4)
        t_mean = mean.real("time")
        out_cycle = measure.mean(time, cycle.real("vclamp#branch"), 0.4e-3, 0.6e-3)
        out_mean = measure.mean(t_mean, mean.real("vclamp#branch"), 0.4e-3, 0.6e-3)
        in_cycle = -measure.mean(time, cycle.real("vin#branch"), 0.4e-3, 0.6e-3)
        in_mean = -measure.mean(t_mean, mean.real("vin#branch"), 0.4e-3, 0.6e-3)
        figures += [
            near(
                f"frequency_{tag}",
                f"Switching frequency at {supply:g} V",
                1.0 / period,
                "Hz",
                1.6e6,
                0.02,
                "SNVS735B page 4: 1.6 MHz typical",
            ),
            Figure(
                f"closed_{tag}",
                f"Share of the periods in which the switch closes at {supply:g} V",
                closed,
                "",
                expected=1.0,
                low=0.99,
                high=1.01,
                source="a converter at its current limit closes its switch in every period "
                "(check of the model)",
            ),
            Figure(
                f"duty_{tag}", f"Duty cycle at {supply:g} V and {_CLAMP:g} V of output", duty, ""
            ),
            near(
                f"limit_{tag}",
                f"Highest inductor current at {supply:g} V",
                peak,
                "A",
                expected,
                0.05,
                "SNVS735B page 13, figure 21, at the duty cycle of the run",
            ),
            near(
                f"load_{tag}",
                f"Current into the output at {supply:g} V, cycle-by-cycle model",
                out_cycle,
                "A",
                _LOAD_LIMIT[supply],
                0.2,
                "SNVS735B page 14, figure 22: bench data of a typical part at 12 V",
            ),
            near(
                f"averaged_{tag}",
                f"Current into the output at {supply:g} V, averaged model",
                out_mean,
                "A",
                out_cycle,
                0.1,
                "the cycle-by-cycle model in the same circuit",
            ),
            near(
                f"averaged_in_{tag}",
                f"Current from the supply at {supply:g} V, averaged model",
                in_mean,
                "A",
                in_cycle,
                0.1,
                "the cycle-by-cycle model in the same circuit",
            ),
        ]
        shown = (time >= 0.6e-3 - 4e-6) & (time <= 0.6e-3)
        micro = (time[shown] - time[shown][0]) * 1e6
        traces += [
            Trace(micro, node[shown], f"{supply:g} V", 0),
            Trace(micro, cycle.real("@l.xl.l1[i]")[shown], f"{supply:g} V", 1),
        ]
    basic = ctx.run("application", _regulation_deck(ctx))
    time = basic.real("time")
    figures.append(
        near(
            "application",
            "Output of the basic application, 50 mA",
            measure.mean(time, basic.real("out"), 7.5e-3, 8e-3),
            "V",
            1.23 * (1.0 + 117.0 / 13.3),
            0.01,
            "SNVS735B page 11, equation 2",
        )
    )
    graph = Graph(
        name="limit",
        title="LMR62014 model at its current limit: the last 4 us",
        xlabel="Time (us)",
        panels=(Panel("Switch node (V)"), Panel("Inductor current (A)")),
        traces=tuple(traces),
    )
    step = slice(None, None, 50)
    start = Graph(
        name="application",
        title="LMR62014 model in the basic application of the datasheet",
        xlabel="Time (ms)",
        panels=(Panel("Output (V)"),),
        traces=(Trace(time[step] * 1e3, basic.real("out")[step], "", 0),),
    )
    notes = (
        "The current limit of the model is the curve of the datasheet by construction; "
        "the bench checks that the cycle-by-cycle circuit reproduces it at the duty "
        "cycle it runs at. The curve is typical; the datasheet gives 1.8 A at least at "
        "25 C and 1.4 A at least over temperature.",
        "The datasheet does not agree with itself: with the current limit of its "
        "figure 21 its own equation 10 gives more load current than the bench data of "
        "its figure 22 and than the row of its table for the output under load, by a "
        "fifth at 5 V and by half at 3.3 V. The model follows figure 21, so at a low "
        "supply it takes and delivers more than those bench data; that figure fails "
        "here and is left failed.",
        "The error amplifier and its compensation are assumptions. The models show no "
        "soft start and no lock-out because the datasheet names none; they work from "
        "2.0 V of supply, which is an assumption as well.",
        "The averaged model is checked against the cycle-by-cycle model, not against the "
        "datasheet: it is that model without its cycles.",
    )
    return Outcome(tuple(figures), (graph, start), notes)
