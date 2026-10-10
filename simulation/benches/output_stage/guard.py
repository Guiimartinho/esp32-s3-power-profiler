"""The guard buffer: its loop, the error it leaves, and how it follows the node."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.output_stage import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import Circuit, PartModel

_REFS = (
    "U25", "R114", "R118", "R119", "C70", "C72", "C73", "C71",
    "R101", "R140", "R149", "C103", "C100", "JP2", "D24",
)  # fmt: skip
"""The buffer with what it drives: the guard with C73, the divider of the
monitor channel (monitors sheet), the branch of the translator supply with
its jumper and capacitor (digital inputs sheet), and in front of it R114,
C71 and the 1 kohm shunt of range 0."""

_TRANSLATOR_AMPS = 8e-6
"""Supply current of the level translator at rest (specification, section 4.8)."""

_MARGIN_LEAST = 45.0
"""Phase margin asked of the loop here; the specification states none."""

_STEP_AT = 100e-6
"""Instant of the first event of a transient run."""


@dataclass(frozen=True, slots=True)
class _Ring:
    """A guard ring as the loop sees it, and the state of C73.

    Attributes:
        key: Short name, part of the keys of its figures.
        label: What the case is, as the report shows it.
        ground: Capacitance from the guard copper to the ground plane, F.
        node: Capacitance from the guard to the measured node, F.
        entry: Capacitance from the guard to the input of the buffer, F.
        scale: Factor on C73.
    """

    key: str
    label: str
    ground: float
    node: float
    entry: float
    scale: float = 1.0


_ASSUMED = _Ring("assumed", "assumed ring: 100 pF, 10 pF, 2 pF", 100e-12, 10e-12, 2e-12)
"""The ring as assumed for the board: 300 mm2 of guard copper 0.2 mm above
the ground plane give about 60 pF, and the pours on the bottom layer the
rest; the two smaller values are estimates of the coupling to the copper
that the ring encloses."""

_RINGS = (
    _Ring("bare", "no ring capacitance", 0.0, 0.0, 0.0),
    _ASSUMED,
    _Ring("large", "ten times the assumed ring", 1e-9, 100e-12, 20e-12),
    _Ring("half", "assumed ring, C73 at half its value", 100e-12, 10e-12, 2e-12, 0.5),
    _Ring("missing", "assumed ring, C73 not fitted", 100e-12, 10e-12, 2e-12, 1e-6),
)
"""The cases of the loop."""


def _circuit(ctx: Context, models: dict[str, PartModel], scale: float = 1.0) -> Circuit:
    overrides = {
        "JP2": PartModel(kind="short", ports=("1", "2")),
        "D24": PartModel(kind="skip"),
        **models,
    }
    return ctx.circuit(_REFS, common.ALIASES, overrides, {"C73": scale})


def _surroundings(ring: _Ring) -> str:
    lines = [
        "* ideal rails; the translator takes its supply current from the buffer",
        "Vp12 p12v_a 0 12",
        "Vm4 m4v_a 0 -4",
        f"Itranslator vccb 0 {_TRANSLATOR_AMPS:g}",
        "* the guard ring: capacitance to the ground plane, to the measured node",
        "* and to the input of the buffer (assumptions)",
    ]
    for name, node, farads in (
        ("ground", "0", ring.ground),
        ("node", "vout_s", ring.node),
        ("entry", "buf_in", ring.entry),
    ):
        if farads > 0.0:
            lines.append(f"Cring_{name} guard {node} {farads:g}")
    return "\n".join(lines)


def _loop_deck(ctx: Context, ring: _Ring, **probe: float) -> str:
    """Small-signal run with the measured node behind the 1 kohm of range 0."""
    return ctx.deck(
        f"Guard buffer, loop gain: {ring.label}",
        _circuit(ctx, common.buffer_probe(ctx, **probe), ring.scale),
        _surroundings(ring),
        "* range 0 with the output off: the supply node is held, the measured node",
        "* hangs on it through R101",
        "Vsupply supply 0 dc 5 ac 0",
        control=["ac dec 60 10 100meg"],
        options=common.buffer_options(ctx),
        libraries=common.buffer_libraries(ctx),
    )


def _transfer_deck(ctx: Context, ring: _Ring) -> str:
    """Small-signal run from the measured node to the guard."""
    return ctx.deck(
        "Guard buffer, from the measured node to the guard",
        _circuit(ctx, common.buffer_model(ctx)),
        _surroundings(ring),
        "Vnode vout_s 0 dc 5 ac 1",
        "Rsupply supply 0 1Meg",
        control=["ac dec 60 10 100meg"],
        options=common.buffer_options(ctx),
    )


def _transient_deck(ctx: Context, title: str, node: str, stop: float, most: str) -> str:
    """The measured node is driven by a source and the guard is watched."""
    return ctx.deck(
        f"Guard buffer, {title}",
        _circuit(ctx, common.buffer_model(ctx)),
        _surroundings(_ASSUMED),
        f"Vnode vout_s 0 {node}",
        "Rsupply supply 0 1Meg",
        control=[
            "save vout_s buf_in buf_out guard vccb mon_ch0",
            f"tran {most} {stop:.9g} 0 {most}",
        ],
        options=common.buffer_options(ctx),
    )


@bench(
    "output_stage",
    "guard",
    "The guard buffer: stability with the guard ring, static error, range change, output off",
    "sections 4.3, 4.8 and 10.3 (node after the shunts, buffer, guard ring), D-32 and D-72",
)
def guard(ctx: Context) -> Outcome:
    """The buffer copies the node after the shunts onto the guard ring through R119.

    The loop gain of the buffer is taken by double injection at the output
    of the amplifier, with the measured node behind the 1 kohm of range 0
    and C71, which is its highest impedance: without a ring, with the ring
    assumed for the board, with ten times that ring, with C73 at half its
    value and with C73 left out. One injection at the inverting input
    checks the method. A small-signal run gives the frequency up to which
    the guard follows the node. Then the node is driven: a step of 100 mV
    as a range change gives it, a dip to 1.1 V for 15 us as a short
    circuit gives it, and a fall to 0 V at 0.8 V/ms as a released output
    gives it; and it rests at 5 V and at 0.8 V, where the difference that
    is left between guard and node is read.
    """
    decks = {}
    for ring in _RINGS:
        decks[f"series-{ring.key}"] = _loop_deck(ctx, ring, vac=1.0)
        decks[f"shunt-{ring.key}"] = _loop_deck(ctx, ring, iac=1.0)
    decks["feedback"] = _loop_deck(ctx, _ASSUMED, vfb=1.0)
    decks["transfer"] = _transfer_deck(ctx, _ASSUMED)
    step = f"PWL(0 4.9 {_STEP_AT:g} 4.9 {_STEP_AT + 1e-7:g} 5.0)"
    dip = (
        f"PWL(0 5 {_STEP_AT:g} 5 {_STEP_AT + 5e-8:g} 1.1 {_STEP_AT + 15e-6:g} 1.1 "
        f"{_STEP_AT + 15.3e-6:g} 5)"
    )
    release = f"PWL(0 5 {_STEP_AT:g} 5 {_STEP_AT + 6.25e-3:g} 0)"
    decks["step"] = _transient_deck(ctx, "a step of 100 mV", step, _STEP_AT + 150e-6, "20n")
    decks["dip"] = _transient_deck(ctx, "a dip to 1.1 V", dip, _STEP_AT + 150e-6, "20n")
    decks["release"] = _transient_deck(ctx, "a released output", release, 60e-3, "5u")
    decks["rest-5"] = _transient_deck(ctx, "at rest at 5 V", "5", 50e-3, "20u")
    decks["rest-0p8"] = _transient_deck(ctx, "at rest at 0.8 V", "0.8", 50e-3, "20u")
    for key in ("series-assumed", "shunt-assumed", "step", "dip"):
        ctx.kept[f"{ctx.prefix}.{key}.cir"] = decks[key]
    runs = ctx.run_many(decks)

    figures: list[Figure] = []
    loop_traces: list[Trace] = []
    margins: dict[str, float] = {}
    for ring in _RINGS:
        frequency, loop = common.loop_gain(runs[f"series-{ring.key}"], runs[f"shunt-{ring.key}"])
        crossover, margin = measure.stability_margins(frequency, loop)
        margins[ring.key] = margin
        fitted = ring.key != "missing"
        figures += [
            Figure(
                f"margin_{ring.key}",
                f"Phase margin, {ring.label}",
                margin,
                "deg",
                low=_MARGIN_LEAST if fitted else None,
                source="limit set here: 45 degrees; the specification states none"
                if fitted
                else "",
            ),
            Figure(f"crossover_{ring.key}", f"Crossover, {ring.label}", crossover, "Hz"),
        ]
        loop_traces.append(Trace(frequency, measure.decibels(loop), ring.label, 0))
        loop_traces.append(Trace(frequency, measure.phase_degrees(loop) + 180.0, ring.label, 1))
    frequency, single = common.feedback_loop_gain(runs["feedback"])
    _, margin_single = measure.stability_margins(frequency, single)
    # The two phases are counted from their first points, which lie a turn apart.
    apart = (margin_single - margins["assumed"] + 180.0) % 360.0 - 180.0
    figures.append(
        Figure(
            "method",
            "Assumed ring: phase margin by one injection at the inverting input, less "
            "the one by double injection",
            apart,
            "deg",
            low=-3.0,
            high=3.0,
            source="check of the method; limit set here",
        )
    )

    transfer = runs["transfer"]
    hertz = transfer.real("frequency")
    follow = transfer.vector("guard") / transfer.vector("vout_s")
    corner = measure.corner_frequency(hertz, follow)
    expected_corner = 1.0 / (2.0 * np.pi * 47.0 * (100e-9 + _ASSUMED.ground))
    figures += [
        Figure(
            "follow_corner",
            "Frequency up to which the guard follows the node within 3 dB",
            corner,
            "Hz",
            expected=expected_corner,
            low=0.9 * expected_corner,
            high=1.1 * expected_corner,
            source="R119 with C73 and the ring, calculated here; limit 10 % around it",
        ),
        Figure(
            "follow_peaking",
            "Peaking of the guard over the node",
            measure.peaking_db(follow),
            "dB",
            high=1.0,
            source="limit set here",
        ),
    ]

    for key, volts in (("rest-5", 5.0), ("rest-0p8", 0.8)):
        run = runs[key]
        time = run.real("time")
        difference = run.real("guard") - run.real("vout_s")
        expected = -volts * 47.0 / (120e3 + 100e3 + 47.0)
        tag = f"{volts:g}".replace(".", "p")
        figures.append(
            Figure(
                f"error_{tag}v",
                f"Node at {volts:g} V and at rest: guard less node",
                measure.mean(time, difference, 49e-3, 50e-3),
                "V",
                expected=expected,
                low=1.2 * expected,
                high=0.8 * expected,
                source="the current of the monitor divider in R119, calculated here; "
                "limit 20 % around it; the amplifier model has no offset",
            )
        )
        figures.append(
            Figure(
                f"translator_{tag}v",
                f"Node at {volts:g} V and at rest: translator supply less node",
                measure.mean(time, run.real("vccb") - run.real("vout_s"), 49e-3, 50e-3),
                "V",
                low=-10e-3,
                source="section 4.8: up to 10 mV below the output voltage at rest",
            )
        )

    stepped = runs["step"]
    time = stepped.real("time")
    after = _STEP_AT + 1e-7
    figures += [
        Figure(
            "step_overshoot",
            "Step of 100 mV: overshoot at the output of the amplifier",
            100.0 * measure.overshoot(time, stepped.real("buf_out"), 4.9, 5.0, _STEP_AT),
            "%",
            high=25.0,
            source="limit set here: the overshoot that goes with 45 degrees",
        ),
        Figure(
            "step_guard_overshoot",
            "Step of 100 mV: overshoot at the guard",
            100.0 * measure.overshoot(time, stepped.real("guard"), 4.9, 5.0, _STEP_AT),
            "%",
        ),
        Figure(
            "step_settled",
            "Step of 100 mV: guard within 1 mV of its final value after",
            measure.settling_time(
                time, stepped.real("guard"), float(stepped.real("guard")[-1]), 1e-3, after
            ),
            "s",
            expected=47.0 * 100.1e-9 * float(np.log(100.0)),
            source="4.6 time constants of R119 with C73, calculated here",
        ),
    ]

    dipped = runs["dip"]
    time = dipped.real("time")
    difference = dipped.real("guard") - dipped.real("vout_s")
    back = _STEP_AT + 15.3e-6
    current = (dipped.real("buf_out") - dipped.real("guard")) / 47.0
    figures += [
        Figure(
            "dip_error",
            "Dip to 1.1 V for 15 us: largest distance of the guard from the node",
            float(np.max(np.abs(difference))),
            "V",
        ),
        Figure(
            "dip_left",
            "Dip to 1.1 V: distance of the guard from the node at the end of the dip",
            abs(measure.value_at(time, difference, _STEP_AT + 14.9e-6)),
            "V",
        ),
        Figure(
            "dip_back",
            "Dip to 1.1 V: guard within 10 mV of the node after the node is back",
            measure.settling_time(time, difference, float(difference[-1]), 10e-3, back),
            "s",
        ),
        Figure(
            "dip_current",
            "Dip to 1.1 V: largest current of the amplifier into R119",
            float(np.max(np.abs(current))),
            "A",
            expected=65e-3,
            source="TI SBOS737C, page 8: short-circuit current 65 mA, which the "
            "amplifier may deliver without a time limit (page 5)",
        ),
        Figure(
            "dip_input",
            "Dip to 1.1 V: lowest voltage at the input of the buffer",
            float(np.min(dipped.real("buf_in"))),
            "V",
            low=-4.5,
            source="TI SBOS737C, page 5: inputs to 0.5 V beyond the rails",
        ),
    ]

    released = runs["release"]
    time = released.real("time")
    difference = released.real("guard") - released.real("vout_s")
    figures += [
        Figure(
            "release_error",
            "Released output, 5 V to 0 V at 0.8 V/ms: largest distance of the guard",
            float(np.max(np.abs(measure.window(time, difference, _STEP_AT, 6.3e-3)[1]))),
            "V",
        ),
        Figure(
            "off_error",
            "Node at 0 V with the output off: guard less node",
            measure.mean(time, difference, 59e-3, 60e-3),
            "V",
            low=-1e-3,
            high=1e-3,
            source="limit set here: 1 mV, the size of the error at 5 V",
        ),
    ]

    loop_graph = Graph(
        name="loop",
        title="Guard buffer: loop gain by double injection at the amplifier output",
        xlabel="Frequency (Hz)",
        panels=(
            Panel("Loop gain (dB)", marks=((0.0, "0 dB"),)),
            Panel("Phase above -180 (deg)", marks=((_MARGIN_LEAST, "45 degrees"),)),
        ),
        traces=tuple(loop_traces),
        logx=True,
    )
    step_time = stepped.real("time")
    step_shown = (step_time >= _STEP_AT - 2e-6) & (step_time <= _STEP_AT + 40e-6)
    dip_time = dipped.real("time")
    dip_shown = (dip_time >= _STEP_AT - 2e-6) & (dip_time <= _STEP_AT + 60e-6)
    events = Graph(
        name="events",
        title="Guard buffer: a range change and a short circuit seen at the node",
        xlabel="Time after the event (us)",
        panels=(Panel("Step of 100 mV (V)"), Panel("Dip to 1.1 V for 15 us (V)")),
        traces=(
            Trace(
                (step_time[step_shown] - _STEP_AT) * 1e6,
                stepped.real("vout_s")[step_shown],
                "node after the shunts",
                0,
            ),
            Trace(
                (step_time[step_shown] - _STEP_AT) * 1e6,
                stepped.real("buf_out")[step_shown],
                "amplifier output",
                0,
            ),
            Trace(
                (step_time[step_shown] - _STEP_AT) * 1e6,
                stepped.real("guard")[step_shown],
                "guard",
                0,
            ),
            Trace(
                (dip_time[dip_shown] - _STEP_AT) * 1e6,
                dipped.real("vout_s")[dip_shown],
                "node after the shunts",
                1,
            ),
            Trace(
                (dip_time[dip_shown] - _STEP_AT) * 1e6,
                dipped.real("buf_out")[dip_shown],
                "amplifier output",
                1,
            ),
            Trace(
                (dip_time[dip_shown] - _STEP_AT) * 1e6, dipped.real("guard")[dip_shown], "guard", 1
            ),
        ),
    )
    follow_graph = Graph(
        name="follow",
        title="Guard over node after the shunts, assumed ring",
        xlabel="Frequency (Hz)",
        panels=(Panel("Guard over node (dB)", marks=((-3.0, "-3 dB"),)),),
        traces=(Trace(hertz, measure.decibels(follow), "", 0),),
        logx=True,
    )
    notes = (
        "The ring is an assumption: 100 pF from the guard copper to the ground plane, "
        "10 pF to the measured node and 2 pF to the input of the buffer. C73, 100 nF "
        "behind R119, holds the guard still above 34 kHz, so the ring cannot feed the "
        "buffer back at the frequencies at which its loop closes; ten times the ring "
        "changes nothing.",
        "The margin rests on the output impedance of the amplifier model. Against "
        "table 3 of its datasheet that model is close where the table gives 45 degrees "
        "and 15 to 30 degrees too optimistic where it gives 60 degrees (bench "
        "output-stage-buffer of the model block), so the margins here are too high by "
        "about that much. The table itself gives 60 degrees for 100 nF behind "
        "15.8 ohm; the board has three times that resistance.",
        "One injection at the inverting input agrees with the double injection at the "
        "crossover and above. Below about 10 kHz it does not: the ring also feeds the "
        "non-inverting input, and an injection in one branch leaves that path closed. "
        "The double injection at the amplifier output cuts both.",
        "The guard follows the node up to 34 kHz. A faster change of the node leaves "
        "the guard behind for some microseconds; what flows through the ring "
        "capacitance then is charge of picocoulombs beside the 100 nF of C71.",
        "In the dip the amplifier model delivers about 25 mA at most, because its "
        "output resistance stands between its rails and its output at every level; "
        "the datasheet gives 65 mA, and the model of the manufacturer delivers that "
        "in the vendor tier. The guard of the board comes back faster than the model "
        "written here shows.",
        "The static difference is the current of the monitor divider (R140, R149) in "
        "R119. The model has no offset voltage; the datasheet gives 25 uV typical and "
        "100 uV at most, which adds to it.",
        "The clamp D24 of the translator supply is left out: it does not conduct "
        "between 0 V and the 5 V rail. The translator takes 8 uA. Its branch belongs "
        "to the digital inputs block.",
        "The input bias current of the buffer flows out of the measured node. The "
        "model has 5 pA; no leakage figure may be taken from it.",
    )
    return Outcome(tuple(figures), (loop_graph, events, follow_graph), notes)
