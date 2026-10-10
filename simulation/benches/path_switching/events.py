"""Fast events at the VIN terminal: plug-in edges, a supply that leaves its range."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.path_switching import common
from circuit_sim import measure
from circuit_sim.bench import VENDOR_TIER, Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult
from circuit_sim.errors import MeasureError

_EVENT = 20e-6
"""Instant of the edge at the terminal."""

_CEILING = 5.26
"""Highest output of the regulator that the set-point path can command, V (section 4.2)."""

_AVALANCHE_JOULES = 39e-3
"""Single-pulse avalanche energy of the CSD17577Q3A (TI SLPS515A, page 1)."""

_AVALANCHE_AMPS = 28.0
"""Current of that avalanche rating, A (TI SLPS515A, page 1)."""

_DUT_FARADS = 10e-6
"""Capacitor of the stand-in for the device under test (assumption, as in the
earlier simulations behind the figures of the specification)."""

_DUT_OHMS = 100.0
"""Load resistor of that stand-in: 50 mA at 5 V."""


def _dut() -> str:
    """A device under test at the output terminal: capacitor and resistor."""
    return (
        "* device under test at the output terminal: 10 uF behind 20 mohm with\n"
        "* 100 ohm beside it, on a lead of 50 nH\n"
        "Ldut vout dut 50n\n"
        "Resr dut dutc 20m\n"
        f"Cdut dutc 0 {_DUT_FARADS:g}\n"
        f"Rdut dut 0 {_DUT_OHMS:g}\n"
    )


def _clamp(run: RunResult) -> np.ndarray:
    """The current in the suppressor D14, as a magnitude."""
    return np.maximum(np.abs(run.real("@d.xd14.d1[id]")), np.abs(run.real("@d.xd14.d2[id]")))


# ---------------------------------------------------------------------------
# Plug-in edges with the pair open


@dataclass(frozen=True, slots=True)
class _Plug:
    """One plug-in edge with the ampere pair open.

    Attributes:
        volts: Voltage that is plugged in.
        henries: Inductance of the leads.
        source: Source mode is running at its ceiling.
        high_clamp: The suppressor has its highest breakdown voltage.
    """

    volts: float
    henries: float = 0.2e-6
    source: bool = False
    high_clamp: bool = False

    @property
    def tag(self) -> str:
        """Short name of the run."""
        sign = "plus" if self.volts > 0 else "minus"
        text = f"{sign}{abs(self.volts):g}v_{self.henries * 1e6:g}uh"
        text += "_source" if self.source else ""
        text += "_clamp" if self.high_clamp else ""
        return text.replace(".", "p")

    @property
    def text(self) -> str:
        """The case as the labels name it."""
        state = "source mode at 5.26 V" if self.source else "idle"
        clamp = ", suppressor at its upper limit" if self.high_clamp else ""
        return f"{self.volts:+g} V behind {self.henries * 1e6:g} uH, {state}{clamp}"


_PLUGS = (
    _Plug(-20.0, source=True),
    _Plug(-20.0),
    _Plug(-20.0, 1e-6),
    _Plug(-20.0, 1e-6, source=True),
    _Plug(-20.0, 1e-6, source=True, high_clamp=True),
    _Plug(20.0),
    _Plug(20.0, 1e-6),
    _Plug(20.0, 1e-6, source=True),
)


def _plug_deck(ctx: Context, case: _Plug) -> str:
    """A supply is plugged into the terminal within 100 ns; the ampere pair is open."""
    edge = common.pwl([(0.0, 0.0), (_EVENT, case.volts)], edge=100e-9)
    if case.source:
        mode = common.regulator(_CEILING) + common.requests(source=((0.0, True),))
    else:
        mode = common.no_regulator() + common.requests()
    control = [
        "save vin_raw vin_p det vin_ov g_amp s_amp b_amp supply ldo_out vout_s "
        "vlead#branch @qq7[ic] @mq5[id] @mq9[id] @d.xd14.d1[id] @d.xd14.d2[id]",
        "tran 1n 220u 0 20n",
    ]
    overrides: dict[str, PartModel] = {"D14": common.suppressor("HI")} if case.high_clamp else {}
    return common.deck(
        ctx,
        f"Plug-in edge with the ampere pair open: {case.text}",
        common.circuit(ctx, overrides=overrides),
        common.rails(),
        common.range_lines(3),
        common.supply(edge, henries=case.henries, ohms=0.02),
        mode,
        control=control,
    )


def _overdrive_deck(ctx: Context, variant: str) -> str:
    """The terminal is taken slowly from 20 V to 26 V: what the suppressor then takes."""
    overrides: dict[str, PartModel] = (
        {} if variant == "typical" else {"D14": common.suppressor(variant)}
    )
    stimulus = (
        "* the terminal driven by a source without leads, 20 V to 26 V in 60 ms\n"
        "Vin vin_src 0 PWL(0 20 60m 26)\n"
        "Vlead vin_src vin_raw 0\n" + common.no_regulator() + common.requests()
    )
    return common.deck(
        ctx,
        f"VIN terminal above 20 V, suppressor with its {variant} breakdown voltage",
        common.circuit(ctx, ladder=False, overrides=overrides),
        common.rails(),
        stimulus,
        control=["save vin_p vlead#branch @d.xd14.d1[id]", "tran 50u 60m 0 100u"],
    )


@bench(
    "path_switching",
    "plug",
    "A supply of +20 V or -20 V is plugged into VIN with the ampere pair open",
    "requirement R-09, section 4.9 (VIN, D-60: plug-in edge, suppressor and fuse)",
)
def plug(ctx: Context) -> Outcome:
    """A supply is plugged into the VIN terminal within 100 ns while the ampere pair is open.

    The supply stands behind 0.2 uH or 1 uH of leads, so the line rings
    against its own capacitance until the suppressor or the losses stop it.
    The instrument is idle, or source mode runs at the highest output the
    set-point path can command; in that state the transistor on the ladder
    side blocks the sum of both voltages. A last run takes the terminal
    slowly from 20 V to 26 V and shows what the suppressor and the fuse
    carry there.
    """
    runs = ctx.run_many({case.tag: _plug_deck(ctx, case) for case in _PLUGS[1:]})
    first = _PLUGS[0]
    runs[first.tag] = ctx.run(first.tag, _plug_deck(ctx, first))
    figures: list[Figure] = []
    for case in _PLUGS:
        run = runs[case.tag]
        time = run.real("time")
        terminal, source, node = run.real("vin_p"), run.real("s_amp"), run.real("supply")
        across = (node - source) if case.volts < 0 else (terminal - source)
        side = "ladder" if case.volts < 0 else "supply"
        above = across > 0.9 * common.TRANSISTOR_VOLTS
        figures += [
            Figure(
                f"across_{case.tag}",
                f"Largest voltage across the transistor on the {side} side: {case.text}",
                float(np.max(across)),
                "V",
                high=common.TRANSISTOR_VOLTS,
                source="rating of the CSD17577Q3A, 30 V (TI SLPS515A, page 1); section 4.9 "
                "states that it is reached for tens of nanoseconds at the plug-in edge",
            ),
            Figure(
                f"near_rating_{case.tag}",
                f"Time above 27 V across that transistor: {case.text}",
                float(np.sum(np.diff(time)[above[:-1]])),
                "s",
                source="",
            ),
            Figure(
                f"terminal_{case.tag}",
                f"Largest voltage on VIN behind the fuse, as a magnitude: {case.text}",
                float(np.max(np.abs(terminal))),
                "V",
                source="",
            ),
            Figure(
                f"drive_{case.tag}",
                f"Largest gate-source voltage of the ampere pair: {case.text}",
                float(np.max(run.real("g_amp") - source)),
                "V",
                source="for comparison: the lowest threshold of the transistors is 1.1 V",
            ),
            Figure(
                f"node_{case.tag}",
                f"Largest change of the supply node: {case.text}",
                float(np.max(np.abs(node - node[0]))),
                "V",
                high=0.1,
                source="section 11: TP33 unchanged (limit of this bench: 0.1 V)",
            ),
            Figure(
                f"suppressor_{case.tag}",
                f"Largest current in the suppressor: {case.text}",
                float(np.max(_clamp(run))),
                "A",
                high=common.SUPPRESSOR_PULSE_AMPS,
                source="peak pulse current of the SMAJ20CA, 12.3 A (Vishay 88390, page 2)",
            ),
        ]
    overdrive = ctx.run_many(
        {f"over-{variant.lower()}": _overdrive_deck(ctx, variant) for variant in ("LO", "typical")}
    )
    traces = []
    for name, variant in (("over-lo", "lowest"), ("over-typical", "typical")):
        run = overdrive[name]
        volts, amps = run.real("vin_p"), run.real("vlead#branch")
        at_24 = float(np.interp(24.0, volts, amps))
        figures += [
            Figure(
                f"over_amps_{variant}",
                f"Current of a steady 24 V supply into the terminal, suppressor with its "
                f"{variant} breakdown voltage",
                at_24,
                "A",
                source="",
            ),
            Figure(
                f"over_watts_{variant}",
                f"Power in the suppressor at a steady 24 V, {variant} breakdown voltage",
                24.0 * at_24,
                "W",
                source="for comparison: the SMAJ20CA bears 3.3 W on an infinite heat sink "
                "(Vishay 88390, page 1)",
            ),
        ]
        traces.append(Trace(volts, amps, f"{variant} breakdown voltage", 0))
    shown = runs[first.tag]
    time = shown.real("time")
    micro = (time - _EVENT) * 1e6
    near = (micro >= -0.5) & (micro <= 6.0)
    edge_graph = Graph(
        name="reverse",
        title=f"Plug-in edge: {first.text}",
        xlabel="Time after the edge (us)",
        panels=(
            Panel("Voltage (V)"),
            Panel(
                "Across the transistor on the ladder side (V)",
                marks=((common.TRANSISTOR_VOLTS, "rating"),),
            ),
            Panel("Current (A)"),
        ),
        traces=(
            Trace(micro[near], shown.real("vin_p")[near], "VIN behind the fuse (TP27)", 0),
            Trace(micro[near], shown.real("s_amp")[near], "common source of the pair", 0, "--"),
            Trace(micro[near], shown.real("g_amp")[near], "gate (TP32)", 0, ":"),
            Trace(micro[near], shown.real("supply")[near], "supply node (TP33)", 0),
            Trace(micro[near], (shown.real("supply") - shown.real("s_amp"))[near], "", 1),
            Trace(micro[near], shown.real("vlead#branch")[near], "supply leads", 2),
            Trace(micro[near], _clamp(shown)[near], "suppressor D14", 2, "--"),
        ),
    )
    over_graph = Graph(
        name="above-20v",
        title="A steady voltage above 20 V on VIN: the current the suppressor takes",
        xlabel="Voltage on VIN behind the fuse (V)",
        panels=(Panel("Current into the terminal (A)", marks=((4.0, "fuse rating 4 A"),)),),
        traces=tuple(traces),
    )
    notes = (
        "The supply is a voltage source that rises within 100 ns behind 20 mohm and "
        "its leads; the line rings against the capacitance of the suppressor and of "
        "the transistor, about 1 nF in the models. A plug with bouncing contacts is "
        "not simulated. The current of the suppressor at these edges is mostly the "
        "current of its own capacitance.",
        "At the negative edge the common source of the pair follows the terminal "
        "through the body diode of the transistor on the supply side, and the gate "
        "follows it through the gate capacitance before the hold-off transistor "
        "conducts. The figure for the gate-source voltage shows how far the gate "
        "lags; the change of the supply node shows what that costs.",
        "The transistor models have no avalanche: a voltage above 30 V in a figure "
        "is the voltage the part would have to block and does not.",
        "Above its breakdown voltage the suppressor takes amperes from a steady "
        "supply: tens of watts in a part made for 3.3 W, at a current below the 4 A "
        "of the fuse, which therefore does not open. This is what the "
        "specification says: 24 V destroys the suppressor and the fuse does not "
        "protect it.",
    )
    return Outcome(tuple(figures), (edge_graph, over_graph), notes)


# ---------------------------------------------------------------------------
# The supply leaves its range while the pair is closed


@dataclass(frozen=True, slots=True)
class _Leave:
    """One run: the supply steps away from its voltage while the pair is closed.

    Attributes:
        start: Voltage of the supply before the step.
        to: Voltage after the step.
        edge: Time the step takes.
        gain: Gain of the hold-off transistor: empty for typical, ``LO`` for
            the least gain of the datasheet at 2 mA, ``WEAK`` for a gain that
            falls to 25 at 10 uA.
        end: Length of the run after the step.
    """

    start: float
    to: float
    edge: float = 1e-6
    gain: str = ""
    end: float = 400e-6

    @property
    def tag(self) -> str:
        """Short name of the run."""
        text = f"{self.start:g}v_to_{self.to:g}v"
        if self.edge != 1e-6:
            text += f"_{self.edge * 1e6:g}us"
        if self.gain:
            text += f"_{self.gain.lower()}"
        return text.replace(".", "p").replace("-", "m")

    @property
    def text(self) -> str:
        """The case as the labels name it."""
        text = f"{self.start:g} V to {self.to:g} V"
        if self.edge != 1e-6:
            text += f" in {self.edge * 1e6:g} us"
        if self.gain:
            text += {
                "LO": ", hold-off transistor with the least gain at 2 mA",
                "WEAK": ", hold-off transistor with a gain of 25 at 10 uA",
            }[self.gain]
        return text


def _leave_deck(ctx: Context, case: _Leave) -> str:
    """Ampere mode with a device under test; then the supply steps."""
    overrides: dict[str, PartModel] = {"Q7": common.hold_off(case.gain)} if case.gain else {}
    if ctx.tier == VENDOR_TIER:
        overrides = {}
    step = common.pwl([(0.0, case.start), (_EVENT, case.to)], edge=case.edge)
    control = [
        "save vin_raw vin_p det vin_ov amp_in g_amp s_amp b_amp supply vout_s vout dut drv_amp "
        "vlead#branch @qq7[ic] @qq7[ib] @mq5[id] @mq9[id] @d.xd14.d1[id] @d.xd14.d2[id]",
        f"tran 2n {_EVENT + case.end:g} 0 {max(50e-9, case.end / 8000):g}",
    ]
    return common.deck(
        ctx,
        f"The supply leaves its range with the ampere pair closed: {case.text}",
        common.circuit(ctx, output=True, overrides=overrides),
        common.rails(),
        common.range_lines(3, output=True),
        common.supply(step, henries=1e-6, ohms=0.05),
        common.no_regulator(),
        common.requests(ampere=((0.0, True),)),
        _dut(),
        control=control,
    )


def _opened(run: RunResult, after: float) -> float:
    """The instant at which the gate-source voltage of the ampere pair falls below 1 V."""
    time = run.real("time")
    drive = run.real("g_amp") - run.real("s_amp")
    try:
        return measure.first_crossing(time, drive, 1.0, rising=False, after=after)
    except MeasureError:
        return float("nan")


def _pulse_figures(case: _Leave, run: RunResult) -> list[Figure]:
    """What the suppressor and the fuse take in one event, against their ratings."""
    time = run.real("time")
    end = float(time[-1])
    watts = _clamp(run) * np.abs(run.real("vin_p"))
    energy = common.joules(time, watts, _EVENT, end)
    peak = float(np.max(watts))
    # The datasheet states the pulse width as the time to half the peak; a
    # pulse that decays in a straight line has its energy over its peak power.
    width = energy / peak if peak > 1.0 else 0.0
    share = peak / common.suppressor_rating(width) if peak > 1.0 else 0.0
    leads = run.real("vlead#branch")
    melt = common.joules(time, leads * leads, _EVENT, end)
    return [
        Figure(
            f"pulse_{case.tag}",
            "Largest pulse power of the suppressor as a share of its rating at that "
            f"width: {case.text}",
            100.0 * share,
            "%",
            high=100.0,
            source="Vishay 88390, page 4, figure 1, read from the curve",
        ),
        Figure(
            f"fuse_{case.tag}",
            f"I2t of the event as a share of the melting figure of the fuse: {case.text}",
            100.0 * melt / common.FUSE_MELT,
            "%",
            high=100.0,
            source="Littelfuse 466 series, page 1: 1.764 A2s nominal",
        ),
    ]


def _stops(ctx: Context, run: RunResult, after: float) -> float:
    """The instant from which the pair no longer carries a backward current.

    The pair counts as open from the last instant at which it carries more
    than 1 % of the largest backward current of the run, and more than
    10 mA. A pair that still conducts at the end of the run gives no number.
    """
    time = run.real("time")
    backward = -common.through(ctx, run, "ampere")
    level = max(0.01 * float(np.max(backward)), 10e-3)
    carrying = np.flatnonzero((backward > level) & (time >= after))
    if carrying.size == 0:
        return after
    if carrying[-1] >= time.size - 2:
        return float("nan")
    return float(time[carrying[-1]])


_REVERSALS = (
    _Leave(5.0, -20.0),
    _Leave(5.0, -5.0),
    _Leave(5.0, -5.0, gain="WEAK"),
    _Leave(3.0, -3.0, end=1e-3),
    _Leave(3.0, -3.0, gain="WEAK", end=4e-3),
    _Leave(2.0, -2.0, end=4e-3),
    _Leave(2.0, -2.0, gain="WEAK", end=4e-3),
    _Leave(1.5, -1.5, end=4e-3),
    _Leave(1.5, -1.5, gain="LO", end=4e-3),
    _Leave(1.5, -1.5, gain="WEAK", end=4e-3),
    _Leave(1.0, -1.0, end=4e-3),
    _Leave(1.0, -1.0, gain="WEAK", end=4e-3),
)

_LIMIT_AMPS = 1.0
"""Current limit of the supply in the check of section 16, A."""


def _limited_deck(ctx: Context) -> str:
    """A reversed 5 V supply limited to 1 A is plugged in while the request is high.

    The terminal is open before, the output pair is open and nothing is
    connected to the output: the state that test firmware would set for the
    check of section 16.
    """
    stimulus = (
        "* a supply of -5 V that limits its current to 1 A, plugged in within 100 ns\n"
        "* behind 0.5 uH of leads; no output capacitor of the supply is assumed\n"
        f"Vin vin_src 0 {common.pwl([(0.0, 0.0), (_EVENT, -5.0)], edge=100e-9)}\n"
        f"Blimit vin_src vin_a I = {_LIMIT_AMPS:g}*tanh(v(vin_src,vin_a)/0.1)\n"
        "Rlimit vin_src vin_a 1e6\n"
        "Vlead vin_a vin_b 0\n"
        "Llead vin_b vin_raw 0.5u\n"
    )
    control = [
        "save vin_raw vin_p g_amp s_amp b_amp supply vout_s vout s_out out_gate "
        "vlead#branch @qq7[ic] @mq5[id] @mq15[id]",
        "tran 2n 420u 0 50n",
    ]
    return common.deck(
        ctx,
        "A reversed 5 V supply limited to 1 A is plugged in with the ampere request high",
        common.circuit(ctx, output=True),
        common.rails(),
        common.range_lines(3),
        stimulus,
        common.no_regulator(),
        common.requests(ampere=((0.0, True),)),
        control=control,
    )


def _limited(ctx: Context) -> tuple[list[Figure], list[Graph]]:
    """The run with the reversed supply that limits at 1 A: its figures and its graph.

    The subcircuit that the manufacturer publishes for the transistors does
    not get through this run, so the tier of those models leaves it out.
    """
    if ctx.tier == VENDOR_TIER:
        return [], []
    figures: list[Figure] = []
    limited = ctx.run("limited", _limited_deck(ctx))
    time_l = limited.real("time")
    node_l = limited.real("supply")
    figures += [
        Figure(
            "limited_opens",
            "Reversed 5 V supply limited to 1 A, request high: pair open after",
            _stops(ctx, limited, _EVENT) - _EVENT,
            "s",
            source="",
        ),
        Figure(
            "limited_lowest",
            "Reversed 5 V supply limited to 1 A, request high: lowest voltage of the supply node",
            float(np.min(node_l)),
            "V",
            source="",
        ),
        Figure(
            "limited_after",
            "Reversed 5 V supply limited to 1 A, request high: supply node 35 us after the plug-in",
            measure.value_at(time_l, node_l, _EVENT + 35e-6),
            "V",
            low=-0.1,
            source="section 16: TP33 above -0.1 V after 35 us",
        ),
    ]
    micro_l = (time_l - _EVENT) * 1e6
    near_l = (micro_l >= -2.0) & (micro_l <= 60.0)
    limited_graph = Graph(
        name="limited",
        title="A reversed 5 V supply limited to 1 A is plugged in with the ampere request high",
        xlabel="Time after the plug-in (us)",
        panels=(Panel("Voltage (V)"), Panel("Current of the supply leads (A)")),
        traces=(
            Trace(micro_l[near_l], limited.real("vin_p")[near_l], "VIN behind the fuse (TP27)", 0),
            Trace(micro_l[near_l], node_l[near_l], "supply node (TP33)", 0),
            Trace(micro_l[near_l], limited.real("g_amp")[near_l], "gate (TP32)", 0, "--"),
            Trace(micro_l[near_l], limited.real("s_amp")[near_l], "common source", 0, ":"),
            Trace(micro_l[near_l], limited.real("vlead#branch")[near_l], "", 1),
        ),
    )
    return figures, [limited_graph]


@bench(
    "path_switching",
    "reversal",
    "The supply reverses while the ampere pair is closed",
    "section 4.9 (VIN: a reversal with the switch closed; hold-off below ground, D-61), "
    "sections 14 and 16",
)
def reversal(ctx: Context) -> Outcome:
    """Ampere mode runs on a supply that reverses within 1 us.

    The pair and the output pair are closed, range 3 is selected and a
    device under test of 10 uF with 100 ohm hangs on the output terminal.
    Nothing but the hold-off transistor opens the pair: it joins gate and common source once
    the common source is a base-emitter voltage below ground, and it has to
    empty the ramp capacitor through 6.8 kohm with the base current that
    100 kohm leave it. The run shows how long that takes from 5 V and from
    low supply voltages, what reaches the device under test meanwhile, and
    what the transistors of the pair have to block when the pair opens with
    the current of the leads still flowing.
    """
    runs = ctx.run_many({case.tag: _leave_deck(ctx, case) for case in _REVERSALS[1:]})
    first = _REVERSALS[0]
    runs[first.tag] = ctx.run(first.tag, _leave_deck(ctx, first))
    figures: list[Figure] = []
    for case in _REVERSALS:
        run = runs[case.tag]
        time = run.real("time")
        opened = _stops(ctx, run, _EVENT)
        node, source = run.real("supply"), run.real("s_amp")
        from_five = case.start == 5.0
        slow = case.start == 1.5
        figures.append(
            Figure(
                f"opens_{case.tag}",
                f"Pair open after the step: {case.text}",
                opened - _EVENT,
                "s",
                low=5e-6 if from_five else None,
                high=35e-6 if from_five else (2e-3 if slow else None),
                source="section 4.9: within 5 us to 35 us from 5 V"
                if from_five
                else ("section 4.9: within 2 ms from 1.5 V" if slow else ""),
            )
        )
        figures.append(
            Figure(
                f"dut_{case.tag}",
                f"Lowest voltage at the device under test: {case.text}",
                float(np.min(run.real("dut"))),
                "V",
                expected=-2.4 if case.to == -20.0 else None,
                source="section 4.9: -2.4 V for a supply that steps to -20 V, simulated"
                if case.to == -20.0
                else "",
            )
        )
        if from_five:
            leads = run.real("vlead#branch")
            across = node - source
            through = common.through(ctx, run, "ampere")
            figures += [
                Figure(
                    f"amps_{case.tag}",
                    f"Largest current drawn backward through the leads: {case.text}",
                    float(np.max(-leads)),
                    "A",
                    source="",
                ),
                Figure(
                    f"across_{case.tag}",
                    f"Largest voltage across the transistor on the ladder side: {case.text}",
                    float(np.max(across)),
                    "V",
                    high=common.TRANSISTOR_VOLTS,
                    source="rating of the CSD17577Q3A, 30 V (TI SLPS515A, page 1)",
                ),
                Figure(
                    f"energy_{case.tag}",
                    f"Energy in that transistor while it blocks more than 20 V: {case.text}",
                    common.joules(
                        time,
                        np.where(across > 20.0, np.abs(across * through), 0.0),
                        _EVENT,
                        time[-1],
                    ),
                    "J",
                    high=_AVALANCHE_JOULES,
                    source="single-pulse avalanche energy of the CSD17577Q3A, 39 mJ at 28 A "
                    "(TI SLPS515A, page 1)",
                ),
                Figure(
                    f"terminal_{case.tag}",
                    f"Lowest voltage on VIN behind the fuse: {case.text}",
                    float(np.min(run.real("vin_p"))),
                    "V",
                    source="",
                ),
                Figure(
                    f"suppressor_{case.tag}",
                    f"Largest current in the suppressor: {case.text}",
                    float(np.max(_clamp(run))),
                    "A",
                    source="for comparison: 12.3 A for the 10/1000 us wave (Vishay 88390, page 2)",
                ),
                *_pulse_figures(case, run),
            ]
    limited_figures, limited_graphs = _limited(ctx)
    figures += limited_figures
    shown = runs[first.tag]
    time = shown.real("time")
    micro = (time - _EVENT) * 1e6
    near = (micro >= -2.0) & (micro <= 40.0)
    first_graph = Graph(
        name="to-minus-20v",
        title="The supply steps from 5 V to -20 V within 1 us, ampere pair closed, 1 uH of leads",
        xlabel="Time after the step (us)",
        panels=(Panel("Voltage (V)"), Panel("Ampere pair (V)"), Panel("Current (A)")),
        traces=(
            Trace(micro[near], shown.real("vin_p")[near], "VIN behind the fuse (TP27)", 0),
            Trace(micro[near], shown.real("supply")[near], "supply node (TP33)", 0),
            Trace(micro[near], shown.real("dut")[near], "device under test", 0, "--"),
            Trace(micro[near], shown.real("g_amp")[near], "gate (TP32)", 1),
            Trace(micro[near], shown.real("s_amp")[near], "common source", 1, "--"),
            Trace(
                micro[near],
                (shown.real("g_amp") - shown.real("s_amp"))[near],
                "gate-source",
                1,
                ":",
            ),
            Trace(micro[near], shown.real("vlead#branch")[near], "supply leads", 2),
            Trace(micro[near], _clamp(shown)[near], "suppressor D14", 2, "--"),
        ),
    )
    traces = []
    for case in _REVERSALS:
        if case.start > 2.0:
            continue
        run = runs[case.tag]
        axis = (run.real("time") - _EVENT) * 1e3
        traces.append(Trace(axis, run.real("g_amp") - run.real("s_amp"), case.text, 0))
        traces.append(Trace(axis, run.real("dut"), case.text, 1))
    low_graph = Graph(
        name="low-voltage",
        title="A low supply voltage reverses: the pair opens late or not at all",
        xlabel="Time after the step (ms)",
        panels=(
            Panel("Gate-source voltage of the ampere pair (V)"),
            Panel("Device under test (V)"),
        ),
        traces=tuple(traces),
    )
    notes = (
        "The supply is a voltage source that reverses within 1 us behind 1 uH and "
        "50 mohm, and it takes any current. The device under test is 10 uF behind "
        "20 mohm with 100 ohm beside it. Both are the assumptions of the earlier "
        "simulations behind the figures of the specification. The output pair and "
        "the suppressor of the output terminal are the parts of the schematic with "
        "the models of their block; below ground that suppressor conducts forward "
        "and bounds what the device under test sees.",
        "Until the pair opens, the reversed supply draws current backward through "
        "the ladder: the capacitor of the device under test, the capacitors of the "
        "supply node and, once a node is below ground, the body diodes on the way. "
        "When the pair then opens, the leads carry that current and their kick "
        "adds to the reversed voltage. The transistor on the ladder side has to "
        "block the difference between the supply node and the terminal. The "
        "model written here has no avalanche, so a figure above 30 V is the "
        "voltage the part would have to block and does not. The model of the "
        "manufacturer breaks down near 31 V: in the run with those models the "
        "transistor clamps there and takes the energy that the suppressor "
        "leaves, at a current that can pass the 28 A of its avalanche rating.",
        "How fast the pair opens from a low voltage rests on the gain of the "
        "hold-off transistor at microamperes, which its datasheet does not state. "
        "The model assumes about 220 at 10 uA and 160 for the part with the least "
        "gain at 2 mA. The variant with a gain of 25 at 10 uA is the other reading: "
        "the model that the manufacturer publishes for this transistor puts the "
        "gain there. Which one a real part follows is a measurement.",
        "In the last run the supply is a source that limits at 1 A and has no "
        "output capacitor. A real supply delivers the first microseconds from its "
        "output capacitor without any limit.",
    )
    return Outcome(tuple(figures), (first_graph, low_graph, *limited_graphs), notes)


_OVERVOLTAGES = (
    _Leave(5.0, 20.0),
    _Leave(5.0, 8.0),
    _Leave(5.0, 6.0),
    _Leave(5.0, 20.0, edge=100e-6),
    _Leave(5.0, 6.0, edge=1e-3, end=1.4e-3),
)


def _bump_deck(ctx: Context) -> str:
    """The supply passes the trip level for 0.3 ms and returns; the request stays high."""
    bump = "PWL(0 5 20u 5 21u 6 320u 6 321u 5)"
    control = [
        "save vin_raw vin_p det vin_ov amp_in g_amp s_amp ramp_amp supply vout_s vout dut "
        "drv_amp vlead#branch @mq5[id]",
        "tran 20n 3m 0 200n",
    ]
    return common.deck(
        ctx,
        "The supply passes the trip level for 0.3 ms and returns, request held high",
        common.circuit(ctx, output=True),
        common.rails(),
        common.range_lines(3, output=True),
        common.supply(bump, henries=1e-6, ohms=0.05),
        common.no_regulator(),
        common.requests(ampere=((0.0, True),)),
        _dut(),
        control=control,
    )


@bench(
    "path_switching",
    "overvoltage",
    "The supply rises above its range while the ampere pair is closed",
    "section 4.9 (over-voltage detector, D-43, D-60), rule F-27, sections 14 and 16",
)
def overvoltage(ctx: Context) -> Outcome:
    """Ampere mode runs on a supply that rises above the trip level of the detector.

    The pair and the output pair are closed, range 3 is selected and a
    device under test of 10 uF with 100 ohm hangs on the output terminal.
    The supply steps from 5 V to 6 V, 8 V and 20 V within 1 us, and rises
    more slowly. The
    detector opens the pair; the run shows what has reached the device under
    test by then and what the transistors have to block when the pair opens
    with the current of the leads flowing. A last run takes the supply to
    6 V for 0.3 ms and back with the request still high: the detector
    releases and the pair closes again, as rule F-27 describes.
    """
    runs = ctx.run_many({case.tag: _leave_deck(ctx, case) for case in _OVERVOLTAGES[1:]})
    first = _OVERVOLTAGES[0]
    runs[first.tag] = ctx.run(first.tag, _leave_deck(ctx, first))
    figures: list[Figure] = []
    for case in _OVERVOLTAGES:
        run = runs[case.tag]
        time = run.real("time")
        terminal, source = run.real("vin_p"), run.real("s_amp")
        passes = measure.first_crossing(time, terminal, 5.465, rising=True, after=_EVENT)
        opened = _opened(run, passes)
        across = terminal - source
        through = common.through(ctx, run, "ampere")
        fast = case.to == 20.0 and case.edge == 1e-6
        figures += [
            Figure(
                f"opens_{case.tag}",
                f"Gate-source voltage below 1 V after the terminal passes the trip level: "
                f"{case.text}",
                opened - passes,
                "s",
                low=4e-6,
                high=45e-6,
                source="section 4.9: the detector opens the switch 4 us to 45 us after the "
                "terminal passes the threshold",
            ),
            Figure(
                f"dut_{case.tag}",
                f"Highest voltage at the device under test: {case.text}",
                float(np.max(run.real("dut"))),
                "V",
                expected=9.2 if fast else None,
                source="section 4.9: 9.2 V for a supply that steps to 20 V in 1 us, simulated"
                if fast
                else "",
            ),
            Figure(
                f"amps_{case.tag}",
                f"Largest current of the supply leads: {case.text}",
                float(np.max(run.real("vlead#branch"))),
                "A",
                source="",
            ),
            Figure(
                f"across_{case.tag}",
                f"Largest voltage across the transistor on the supply side: {case.text}",
                float(np.max(across)),
                "V",
                high=common.TRANSISTOR_VOLTS,
                source="rating of the CSD17577Q3A, 30 V (TI SLPS515A, page 1)",
            ),
            Figure(
                f"energy_{case.tag}",
                f"Energy in that transistor while it blocks more than 20 V: {case.text}",
                common.joules(
                    time, np.where(across > 20.0, np.abs(across * through), 0.0), _EVENT, time[-1]
                ),
                "J",
                high=_AVALANCHE_JOULES,
                source="single-pulse avalanche energy of the CSD17577Q3A, 39 mJ at 28 A "
                "(TI SLPS515A, page 1)",
            ),
            Figure(
                f"terminal_{case.tag}",
                f"Highest voltage on VIN behind the fuse: {case.text}",
                float(np.max(terminal)),
                "V",
                source="",
            ),
            Figure(
                f"suppressor_{case.tag}",
                f"Largest current in the suppressor: {case.text}",
                float(np.max(_clamp(run))),
                "A",
                source="for comparison: 12.3 A for the 10/1000 us wave (Vishay 88390, page 2)",
            ),
            *_pulse_figures(case, run),
            Figure(
                f"node_{case.tag}",
                f"Highest voltage of the supply node: {case.text}",
                float(np.max(run.real("supply"))),
                "V",
                high=common.NODE_LIMIT,
                source="limit of this bench, taken from section 4.3: the node stays below "
                "11.5 V because the multiplexer runs from +12 V_A",
            ),
        ]
    bump = ctx.run("bump", _bump_deck(ctx))
    time = bump.real("time")
    node = bump.real("supply")
    released = measure.first_crossing(time, bump.real("vin_ov"), 1.65, rising=False, after=100e-6)
    grid = np.arange(released, time[-1], 5e-6)
    slope = float(np.max(np.diff(np.interp(grid, time, node)) / 5e-6))
    after = time >= released
    figures += [
        Figure(
            "reclose_slope",
            "Largest slope of the supply node when the pair closes again without its ramp",
            slope,
            "V/s",
            source="for comparison: about 0.9 V/ms with the full ramp (section 4.2); rule "
            "F-27 says that this case closes without the ramp",
        ),
        Figure(
            "reclose_amps",
            "Largest current of the supply leads when the pair closes again",
            float(np.max(bump.real("vlead#branch")[after])),
            "A",
            source="for comparison: 5 mA with the full ramp and no device under test",
        ),
        Figure(
            "reclose_ramp",
            "Voltage left on the ramp capacitor when the detector releases",
            measure.value_at(time, bump.real("g_amp") - bump.real("ramp_amp"), released),
            "V",
            source="",
        ),
    ]
    shown = runs[first.tag]
    time_a = shown.real("time")
    micro = (time_a - _EVENT) * 1e6
    near = (micro >= -1.0) & (micro <= 20.0)
    step_graph = Graph(
        name="to-20v",
        title="The supply steps from 5 V to 20 V within 1 us, ampere pair closed, 1 uH of leads",
        xlabel="Time after the step (us)",
        panels=(
            Panel("Voltage (V)", marks=((common.TRANSISTOR_VOLTS, "30 V"),)),
            Panel("Ampere pair and detector (V)"),
            Panel("Current (A)"),
        ),
        traces=(
            Trace(micro[near], shown.real("vin_p")[near], "VIN behind the fuse (TP27)", 0),
            Trace(micro[near], shown.real("supply")[near], "supply node (TP33)", 0),
            Trace(micro[near], shown.real("dut")[near], "device under test", 0, "--"),
            Trace(micro[near], shown.real("g_amp")[near], "gate (TP32)", 1),
            Trace(micro[near], shown.real("s_amp")[near], "common source", 1, "--"),
            Trace(micro[near], shown.real("vin_ov")[near], "detector output VIN_OV", 1, ":"),
            Trace(micro[near], shown.real("vlead#branch")[near], "supply leads", 2),
            Trace(micro[near], _clamp(shown)[near], "suppressor D14", 2, "--"),
        ),
    )
    milli = bump.real("time") * 1e3
    bump_graph = Graph(
        name="release",
        title="The supply at 6 V for 0.3 ms with the request held high: the pair closes again",
        xlabel="Time (ms)",
        panels=(
            Panel("Voltage (V)"),
            Panel("Ampere pair and detector (V)"),
            Panel("Current of the supply leads (A)"),
        ),
        traces=(
            Trace(milli, bump.real("vin_p"), "VIN behind the fuse (TP27)", 0, "--"),
            Trace(milli, bump.real("supply"), "supply node (TP33)", 0),
            Trace(milli, bump.real("dut"), "device under test", 0, ":"),
            Trace(milli, bump.real("g_amp"), "gate (TP32)", 1),
            Trace(milli, bump.real("vin_ov"), "detector output VIN_OV", 1, "--"),
            Trace(milli, bump.real("vlead#branch"), "", 2),
        ),
    )
    notes = (
        "The supply is a voltage source behind 1 uH and 50 mohm, and the device "
        "under test is 10 uF behind 20 mohm with 100 ohm beside it, at the output "
        "terminal behind the closed output pair: the assumptions of the earlier "
        "simulations behind the 9.2 V of the specification. A larger capacitor at "
        "the device under test sees less voltage and more current.",
        "After a fast step to 20 V the detector opens the pair while the leads "
        "carry tens of amperes. Their kick drives the VIN line into the "
        "suppressor, and the transistor on the supply side has to block that "
        "voltage less the voltage of its source, which falls to ground once the "
        "gate is pulled down. The transistor model written here has no "
        "avalanche: a figure above 30 V is the voltage the part would have to "
        "block and does not. The model of the manufacturer breaks down near "
        "31 V and clamps there in the run with those models. The suppressor "
        "model clamps at the datasheet maximum for a millisecond pulse, which is "
        "the cautious side.",
        "The time to open is counted from the instant the line behind the fuse "
        "passes 5.465 V. It depends on how far the step passes the trip level: the "
        "4 us to 45 us of the specification hold for steps to about 5.8 V or more.",
        "Rule F-27 exists for the last run: the detector is not latched, and when "
        "it releases with the request still high the pair closes on what is left "
        "on its ramp capacitor. Firmware has to lower the request within the time "
        "the over-voltage lasts.",
    )
    return Outcome(tuple(figures), (step_graph, bump_graph), notes)
