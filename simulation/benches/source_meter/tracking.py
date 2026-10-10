"""The tracking pre-regulator at rest: its law, the head room and the dissipation."""

from __future__ import annotations

import numpy as np

from benches.source_meter import common
from circuit_sim import tolerance
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.engine import RunResult

_LAW_VOLTS = (0.8, 1.2, 2.0, 2.5, 3.3, 4.0, 4.5, 5.0, 5.05)
"""Output voltages of the run that gives the tracking law."""

_NETWORK = ("R63", "R64", "R65", "R66", "R67", "R68")
"""The resistors of the difference amplifier U19."""

_AMPLIFIER = (*_NETWORK, "U19", "C52", "C55", "D13", "C51")
"""The difference amplifier alone."""

_FEEDBACK_LOW = 0.495
"""Lowest feedback reference of the converter in forced PWM (SLVS916I, page 6)."""

_REFERENCE_SPREAD = 0.0005
"""Tolerance taken for the reference voltage (assumption for this bench)."""

_HEADROOM = {0.8: 0.637, 2.0: 0.584, 3.3: 0.527, 5.0: 0.452}
"""Nominal head room of the table of section 4.2, by output voltage."""

_MARGIN = {0.8: 0.085, 2.0: 0.025, 3.3: 0.015, 5.0: 0.002}
"""Worst-case margin of the same table."""

_LOST = 10e-3
"""Fall of the output at which the regulator counts as out of regulation (this bench)."""

_OVERLOAD_OHMS = 5.0
"""Load beyond the curve of requirement R-08 at 5.0 V (section 4.2)."""

_OVERLOAD_STOP = 0.25
"""Length of the run with that load: in dropout the output and the pre-regulator
climb together with about 15 ms, the sense filter over one minus the slope of the law."""


def _amplifier_deck(ctx: Context) -> str:
    """The difference amplifier with its three inputs held by sources."""
    circuit = common.source(ctx, 3.3, refs=_AMPLIFIER)
    stimulus = "\n".join(
        [
            "* the three inputs of the difference amplifier, one moved at a time",
            "Vpre v_pre 0 3.827",
            "Vldo ldo_out 0 3.3",
            f"Vref vref 0 {common.REFERENCE:g}",
            f"Vp3v3a p3v3_a 0 {common.RAIL_3V3:g}",
            "Rfb pre_fb 0 1e9",
        ]
    )
    control = [
        "op",
        "alter Vpre dc = 3.927",
        "op",
        "alter Vpre dc = 3.827",
        "alter Vldo dc = 3.4",
        "op",
        "alter Vldo dc = 3.3",
        f"alter Vref dc = {common.REFERENCE + 0.1:g}",
        "op",
    ]
    return ctx.deck(
        "Difference amplifier of the tracking",
        circuit,
        stimulus,
        common.nodeset(circuit, 3.3),
        control=control,
    )


def _headroom(run: RunResult) -> float:
    return common.last(run, "ldo_in") - common.last(run, "ldo_out")


def _error(run: RunResult, volts: float) -> float:
    return common.volts_of(common.code_of(volts)) - common.last(run, "ldo_out")


def _rail_watts(run: RunResult) -> float:
    return -common.last(run, "vp5#branch") * common.RAIL_5V


@bench(
    "source_meter",
    "tracking",
    "The tracking pre-regulator at rest: law, head room on the curve, dissipation",
    "section 4.2 (pre-regulator, table of the curve), requirement R-08, decisions D-55, D-56",
)
def tracking(ctx: Context) -> Outcome:
    """The source is powered up at a series of output voltages and loads and read at rest.

    Without load the output of the pre-regulator over the output of the
    linear regulator gives the tracking law, and the difference amplifier
    alone gives the three weights of its feedback voltage. At the four
    points of the curve of requirement R-08 the runs give the head room at
    the IN pin, the dissipation of the regulator and the power taken from
    the 5 V rail, with a typical regulator and with one at the guaranteed
    dropout. A corner run puts the six resistors of the amplifier, the
    feedback reference of the converter and the reference voltage at the
    limits that lower the pre-regulator. One more run loads the output with
    5 ohm at 5.0 V, beyond the curve.
    """
    limit = {common.REGULATOR: common.part(ctx, common.REGULATOR, **common.LIMIT_DROPOUT)}
    decks = {
        f"law-{volts:g}": common.settle_deck(ctx, f"Tracking at {volts:g} V, no load", volts)
        for volts in _LAW_VOLTS
    }
    for volts, amps in common.CURVE:
        decks[f"curve-{volts:g}"] = common.settle_deck(
            ctx, f"Curve point {volts:g} V, {amps:g} A", volts, amps=amps, index=3
        )
        decks[f"curve-limit-{volts:g}"] = common.settle_deck(
            ctx,
            f"Curve point {volts:g} V, {amps:g} A, regulator at the guaranteed dropout",
            volts,
            amps=amps,
            index=3,
            overrides=limit,
        )
        decks[f"amp-{volts:g}"] = common.settle_deck(
            ctx, f"{volts:g} V at 1 A, typical regulator", volts, amps=1.0, index=3
        )
    spread = tolerance.tolerances(ctx.netlist, _NETWORK)
    for ref in _NETWORK:
        decks[f"sense-{ref}"] = common.settle_deck(
            ctx,
            f"5.0 V at 0.6 A with {ref} at its upper limit",
            5.0,
            amps=0.6,
            index=3,
            scales=tolerance.corner_scales(spread, {ref: 1}),
        )
    decks["sense-vref"] = common.settle_deck(
        ctx,
        "5.0 V at 0.6 A with the reference at its upper limit",
        5.0,
        amps=0.6,
        index=3,
        supplies={"vref": common.REFERENCE * (1.0 + _REFERENCE_SPREAD)},
    )
    first = ctx.run_many(decks)

    base = common.last(first["curve-5"], "v_pre")
    signs = {
        ref: -1 if common.last(first[f"sense-{ref}"], "v_pre") > base else 1 for ref in _NETWORK
    }
    reference = common.REFERENCE * (
        1.0 - _REFERENCE_SPREAD
        if common.last(first["sense-vref"], "v_pre") > base
        else 1.0 + _REFERENCE_SPREAD
    )
    low_converter = common.part(ctx, common.CONVERTER, vref=_FEEDBACK_LOW)
    corner = tolerance.corner_scales(spread, signs)
    second = {}
    for volts, amps in common.CURVE:
        second[f"corner-{volts:g}"] = common.settle_deck(
            ctx,
            f"Curve point {volts:g} V, {amps:g} A, parts at the limits that lower the head room",
            volts,
            amps=amps,
            index=3,
            scales=corner,
            supplies={"vref": reference},
            overrides={common.CONVERTER: low_converter, **limit},
        )
    second["overload"] = common.settle_deck(
        ctx,
        "5.0 V into 5 ohm, regulator at the guaranteed dropout",
        5.0,
        overrides=limit,
        index=3,
        extra=f"Rover dut 0 {_OVERLOAD_OHMS:g}\n",
        stop=_OVERLOAD_STOP,
    )
    second["overload-typical"] = common.settle_deck(
        ctx,
        "5.0 V into 5 ohm, typical regulator",
        5.0,
        index=3,
        extra=f"Rover dut 0 {_OVERLOAD_OHMS:g}\n",
        stop=_OVERLOAD_STOP,
    )
    runs = {**first, **ctx.run_many(second)}
    kept = ctx.run(
        "curve-5v",
        common.settle_deck(ctx, "Curve point 5 V, 0.6 A", 5.0, amps=0.6, index=3),
    )
    amplifier = ctx.run("amplifier", _amplifier_deck(ctx))

    ldo = np.array([common.last(runs[f"law-{volts:g}"], "ldo_out") for volts in _LAW_VOLTS])
    pre = np.array([common.last(runs[f"law-{volts:g}"], "v_pre") for volts in _LAW_VOLTS])
    slope, offset = (float(value) for value in np.polyfit(ldo[:-1], pre[:-1], 1))
    feedback = [float(amplifier.real("pre_fb", f"op{i + 1}")[0]) for i in range(4)]
    weights = [(feedback[i] - feedback[0]) / 0.1 for i in (1, 2, 3)]
    figures = [
        near(
            "law_offset",
            "Tracking law: offset",
            offset,
            "V",
            common.LAW_OFFSET,
            0.01,
            "section 4.2",
        ),
        near("law_slope", "Tracking law: slope", slope, "", common.LAW_SLOPE, 0.005, "section 4.2"),
        near(
            "weight_pre",
            "Feedback voltage: weight of the pre-regulator output",
            weights[0],
            "",
            0.200,
            0.01,
            "section 4.2: 0.200 x V_PRE + 0.146 x VREF - 0.191 x V_LDO",
        ),
        near(
            "weight_ldo",
            "Feedback voltage: weight of the regulator output",
            weights[1],
            "",
            -0.191,
            0.01,
            "section 4.2",
        ),
        near(
            "weight_ref",
            "Feedback voltage: weight of the reference",
            weights[2],
            "",
            0.146,
            0.01,
            "section 4.2",
        ),
        near(
            "feedback",
            "Feedback pin at rest, 5.0 V without load",
            common.last(runs["law-5"], "pre_fb"),
            "V",
            0.5,
            0.002,
            "section 4.2: the converter holds 0.5 V",
        ),
        Figure(
            "law_end",
            "Pre-regulator output at 5.05 V of regulator output",
            float(pre[-1]),
            "V",
            expected=5.5,
            low=5.48,
            high=5.52,
            source="section 4.2: the law reaches 5.5 V at 5.05 V",
        ),
    ]
    curve_volts = np.array([volts for volts, _ in common.CURVE])
    headroom_nominal, headroom_corner, watts, need = [], [], [], []
    for volts, amps in common.CURVE:
        tag = f"{volts:g}v".replace(".", "p")
        nominal = runs[f"curve-{volts:g}"]
        worst = runs[f"corner-{volts:g}"]
        needed = common.DROPOUT_OFFSET + common.DROPOUT_OHMS * amps
        power = float(common.regulator_watts(nominal)[-1])
        headroom_nominal.append(_headroom(nominal))
        headroom_corner.append(_headroom(worst))
        watts.append(power)
        need.append(needed)
        figures += [
            near(
                f"pre_{tag}",
                f"{volts:g} V without load: pre-regulator output",
                common.last(runs[f"law-{volts:g}"], "v_pre"),
                "V",
                volts + _HEADROOM[volts],
                0.003,
                "section 4.2, table of the curve: V_PRE, nominal",
            ),
            Figure(
                f"pre_loaded_{tag}",
                f"{volts:g} V and {amps:g} A: pre-regulator output",
                common.last(nominal, "v_pre"),
                "V",
            ),
            Figure(
                f"headroom_{tag}",
                f"{volts:g} V and {amps:g} A: IN pin above the output, nominal parts",
                _headroom(nominal),
                "V",
                expected=_HEADROOM[volts],
                low=needed,
                source="section 4.2, table of the curve: head room, nominal; the limit is the "
                "dropout need of the same table",
            ),
            Figure(
                f"margin_{tag}",
                f"{volts:g} V and {amps:g} A: head room above the dropout need, parts at "
                "their limits",
                _headroom(worst) - needed,
                "V",
                expected=_MARGIN[volts],
                low=0.0,
                source="section 4.2, table of the curve: margin, worst case",
            ),
            Figure(
                f"regulates_{tag}",
                f"{volts:g} V and {amps:g} A: fall of the output, regulator at the "
                "guaranteed dropout, parts at their limits",
                _error(worst, volts) - _error(runs[f"law-{volts:g}"], volts),
                "V",
                high=_LOST,
                source="requirement R-08: no overload on the curve; 10 mV is the limit of "
                "this bench",
            ),
            Figure(
                f"typical_1a_{tag}",
                f"{volts:g} V at 1 A, typical regulator: fall of the output",
                _error(runs[f"amp-{volts:g}"], volts) - _error(runs[f"law-{volts:g}"], volts),
                "V",
                high=_LOST,
                source="section 4.2: a typical regulator delivers 1 A at every set-point",
            ),
        ]
    figures += [
        Figure(
            "watts_0v8",
            "Dissipation of the regulator at 0.8 V and 1.0 A, typical",
            watts[0],
            "W",
            expected=0.82,
            low=0.70,
            high=1.02,
            source="section 4.2: 0.82 W typical, 1.02 W worst case",
        ),
        Figure(
            "watts_5v",
            "Dissipation of the regulator at 5.0 V and 0.6 A, typical",
            watts[3],
            "W",
            expected=0.34,
            low=0.28,
            high=0.45,
            source="section 4.2: 0.34 W typical, 0.45 W worst case",
        ),
        *(
            Figure(
                f"watts_1a_{volts:g}v".replace(".", "p"),
                f"Dissipation of the regulator at {volts:g} V and 1 A, typical",
                float(common.regulator_watts(runs[f"amp-{volts:g}"])[-1]),
                "W",
            )
            for volts, _ in common.CURVE
        ),
        Figure(
            "rail_curve_5v",
            "Power the pre-regulator takes from the 5 V rail at 5.0 V and 0.6 A",
            _rail_watts(runs["curve-5"]),
            "W",
        ),
        Figure(
            "rail_1a_5v",
            "Power the pre-regulator takes from the 5 V rail at 5.0 V and 1 A",
            _rail_watts(runs["amp-5"]),
            "W",
        ),
        Figure(
            "rail_idle_0v8",
            "Power the pre-regulator takes from the 5 V rail at 0.8 V without load",
            _rail_watts(runs["law-0.8"]),
            "W",
        ),
        Figure(
            "rail_idle_5v",
            "Power the pre-regulator takes from the 5 V rail at 5.0 V without load",
            _rail_watts(runs["law-5"]),
            "W",
        ),
        Figure(
            "overload",
            "Output into 5 ohm at a set-point of 5.0 V, regulator at the guaranteed dropout",
            common.last(runs["overload"], "dut"),
            "V",
            expected=4.48,
            low=4.4,
            source="section 4.2: 4.48 V simulated; requirement R-08: a sag of up to 0.6 V",
        ),
        Figure(
            "overload_regulator",
            "Regulator output in that run",
            common.last(runs["overload"], "ldo_out"),
            "V",
        ),
        Figure(
            "overload_current",
            "Current into the 5 ohm in that run",
            common.last(runs["overload"], "dut") / _OVERLOAD_OHMS,
            "A",
        ),
        Figure(
            "overload_typical",
            "Output into 5 ohm at a set-point of 5.0 V, typical regulator",
            common.last(runs["overload-typical"], "dut"),
            "V",
            low=4.4,
            source="requirement R-08: a sag of up to 0.6 V beyond the curve",
        ),
        Figure(
            "rest",
            "Largest movement of output and pre-regulator in the last 2 ms of any run",
            max(common.at_rest(run) for run in runs.values()),
            "V",
            high=common.REST_LIMIT,
            source="limit of this bench: a run counts as at rest below 0.1 mV",
        ),
    ]
    time = kept.real("time") * 1e3
    graphs = (
        Graph(
            name="law",
            title="Tracking at rest: pre-regulator output and head room over the output",
            xlabel="Output of the linear regulator (V)",
            panels=(
                Panel("Pre-regulator output (V)", marks=((5.5, "end of the converter, 5.5 V"),)),
                Panel("IN pin above the output (mV)"),
                Panel("Dissipation of U18 on the curve (W)"),
            ),
            traces=(
                Trace(ldo, pre, "no load", 0),
                Trace(
                    ldo, common.LAW_OFFSET + common.LAW_SLOPE * ldo, "0.672 V + 0.956 x V", 0, ":"
                ),
                Trace(ldo, (pre - ldo) * 1e3, "no load", 1),
                Trace(curve_volts, np.array(headroom_nominal) * 1e3, "on the curve, nominal", 1),
                Trace(curve_volts, np.array(headroom_corner) * 1e3, "on the curve, limits", 1),
                Trace(curve_volts, np.array(need) * 1e3, "dropout need of section 4.2", 1, "--"),
                Trace(curve_volts, np.array(watts), "typical", 2),
            ),
        ),
        Graph(
            name="power-up",
            title="The run a curve point is read from: 5.0 V, 0.6 A applied at 9 ms",
            xlabel="Time (ms)",
            panels=(Panel("Voltage (V)"), Panel("IN pin above the output (V)")),
            traces=(
                Trace(time, kept.real("ldo_out"), "regulator output", 0),
                Trace(time, kept.real("v_pre"), "pre-regulator output", 0),
                Trace(time, kept.real("ldo_in") - kept.real("ldo_out"), "head room", 1),
            ),
        ),
    )
    notes = (
        "Every figure is the end of a run that starts with all rails at zero and ends at "
        "rest. C41 has one hundredth of its value in these runs, which changes no "
        "voltage at rest.",
        "The corner puts each of the six resistors of U19 at the limit of its 0.1 % that "
        "lowers the pre-regulator (found by one run per resistor), the feedback "
        "reference of the converter at 495 mV and the reference at its lower or upper "
        "limit of 0.05 % (assumption). It leaves out what the table of section 4.2 "
        "also counts: the drift of the resistors over 40 K and the copper between the "
        "converter and the bead, which the netlist does not hold.",
        "The dropout need is the straight line of section 4.2, 170 mV + 0.300 ohm x I, "
        "and the regulator at the guaranteed dropout is the model with the parameters "
        "that put it on that line. Both rest on two guaranteed points of the datasheet "
        "at 25 C and on an estimate between them.",
        "The converter is the averaged model: its load regulation of 4.4 mV per ampere "
        "at 3.3 V is fitted to the model of the manufacturer (4.5 mV), and its losses "
        "to four points of the datasheet at 3.6 V of input.",
        "The power figures are those of the pre-regulator alone. The control current "
        "of the regulator comes from the boost converter, which belongs to another "
        "block.",
    )
    return Outcome(tuple(figures), graphs, notes)
