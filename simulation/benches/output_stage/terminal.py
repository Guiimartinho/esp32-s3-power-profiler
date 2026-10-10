"""The output terminal against what section 4.9 lets a user do to it."""

from __future__ import annotations

import numpy as np

from benches.output_stage import common
from circuit_sim import measure
from circuit_sim.bench import OPEN_TIER, Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_EVENT = 200e-6
"""Instant of the event of a fast run."""

_RAMP_START = 1e-3
"""Instant at which the reversed source begins to draw current."""

_RAMP_END = 21e-3
"""Instant at which the reversed source draws its full current."""

_RAMP_AMPS = 2.0
"""Largest current that the reversed source draws."""

_PLUG_FARADS = 100e-6
"""Capacitor that is plugged in charged (specification, section 4.3: 100 uF)."""

_PLUG_VOLTS = 5.5
"""Voltage of that capacitor: the upper end of the 5.0 V to 5.5 V of section 4.3."""

_LOW_THRESHOLD = 1.1
"""Lowest gate threshold of the CSD17577Q3A at 250 uA (TI SLPS515A, page 3)."""

_PULSED_AMPS = 239.0
"""Pulsed drain current of the CSD17577Q3A (TI SLPS515A, page 1)."""

_SUPPRESSOR_WATTS = 400.0
"""Peak pulse power of the suppressor for a millisecond (Nexperia PTVSxS1UR, page 3)."""

_SAVES = "save gate_out out_gate g_out mid vout_s vout dut supply guard @r110[i] vcab#branch"
"""What a run of this bench keeps, beside the currents of the suppressor."""


def _saves(ctx: Context) -> str:
    extra = " @mq15[id]" if ctx.tier == OPEN_TIER else ""
    return f"{_SAVES} {common.suppressor_saves(ctx)}{extra}"


def _off_deck(
    ctx: Context,
    title: str,
    stimulus: str,
    control: str,
    models: dict[str, PartModel] | None = None,
) -> str:
    """The source runs at 5 V in range 3 and the output switch is open."""
    circuit = ctx.circuit(
        common.path_refs(ctx.netlist),
        common.ALIASES,
        {**common.path_models(ctx), **(models or {})},
    )
    ramp = common.QUICK_POWER_UP
    return ctx.deck(
        title,
        circuit,
        common.rails(ramp=ramp),
        common.controller(3, ramp=ramp),
        common.command((0.0, False)),
        common.source(5.0, ramp=ramp),
        common.cable(),
        "Rdut dut 0 100Meg",
        stimulus,
        control=[_saves(ctx), control],
        options=(*common.buffer_options(ctx), "method=gear"),
    )


def _reverse_deck(ctx: Context, forward: float) -> str:
    stimulus = "\n".join(
        [
            "* a reversed source draws a rising current out of the terminal",
            f"Iext vout 0 PWL(0 0 {_RAMP_START:g} 0 {_RAMP_END:g} {_RAMP_AMPS:g})",
        ]
    )
    models = {"D21": common.suppressor(forward)} if forward != 0.03 else None
    return _off_deck(
        ctx,
        "Output off, a reversed source at the terminal",
        stimulus,
        f"tran 5u {_RAMP_END:g} 0 5u uic",
        models,
    )


def _plug_deck(ctx: Context, volts: float, ohms: float) -> str:
    stimulus = "\n".join(
        [
            "* a live source is connected to the open output through a short lead",
            f"Vhot hot 0 PWL(0 0 {_EVENT:g} 0 {_EVENT + 1e-8:g} {volts:g})",
            f"Rhot hot hotl {ohms:g}",
            "Lhot hotl vout 0.2u",
        ]
    )
    return _off_deck(
        ctx,
        f"Output off, {volts:g} V connected to the terminal",
        stimulus,
        f"tran 2n {_EVENT + 20e-6:.9g} 0 5n uic",
    )


def _unpowered_deck(ctx: Context) -> str:
    """The instrument has no supply and a live device is connected to the terminal."""
    models = dict(common.path_models(ctx))
    models["U22"] = PartModel(kind="skip")
    circuit = ctx.circuit(common.path_refs(ctx.netlist), common.ALIASES, models)
    stimulus = "\n".join(
        [
            "* every rail and every line of the controller is at 0 V; the gate driver U22",
            "* is left out, so that R115 alone holds its output",
            "Vp12 p12v_a 0 0",
            "Vm4 m4v_a 0 0",
            "Vsrc supply 0 0",
            "Rdut dut 0 100Meg",
            "* a live device of 5 V is connected through a short lead",
            f"Vhot hot 0 PWL(0 0 {_EVENT:g} 0 {_EVENT + 1e-8:g} 5)",
            "Rhot hot hotl 0.05",
            "Lhot hotl vout 0.2u",
        ]
    )
    return ctx.deck(
        "Instrument without supply, 5 V connected to the terminal",
        circuit,
        common.controller(0),
        "Vgate_out gate_out 0 0",
        common.cable(),
        stimulus,
        control=[_saves(ctx), f"tran 2n {_EVENT + 20e-6:.9g} 0 5n uic"],
        options=(*common.buffer_options(ctx), "method=gear"),
    )


def _charged_deck(ctx: Context, index: int, stiff: bool) -> str:
    """The output is on at 0.8 V and a capacitor charged to 5.5 V is plugged in."""
    refs = list(common.path_refs(ctx.netlist))
    if not stiff:
        refs += common.REGULATOR_REFS
    circuit = ctx.circuit(
        refs, {**common.ALIASES, **common.REGULATOR_ALIASES}, common.path_models(ctx)
    )
    ramp = common.QUICK_POWER_UP
    supply = common.source(0.8, ramp=ramp) if stiff else common.regulator(0.8, ramp)
    stimulus = "\n".join(
        [
            "* the device takes 1 mA; a charged capacitor is plugged in beside it",
            "Rload dut 0 800",
            f"Cplug plugc 0 {_PLUG_FARADS:g} ic={_PLUG_VOLTS:g}",
            f"Rplug plugc plug {common.ESR_OHMS:g}",
            ".model OUTPUT_PLUG SW(vt=0.5 vh=0.1 ron=1m roff=1e9)",
            f"Vplug plg 0 PWL(0 0 {_EVENT:g} 0 {_EVENT + 1e-8:g} 1)",
            "Splug plug dut plg 0 OUTPUT_PLUG",
        ]
    )
    return ctx.deck(
        f"Output on at 0.8 V in range {index}, a capacitor at {_PLUG_VOLTS:g} V plugged in",
        circuit,
        common.rails(ramp=ramp),
        common.controller(index, ramp=ramp),
        common.command((0.0, True)),
        supply,
        common.cable(henries=0.2e-6),
        stimulus,
        common.closed_start(),
        control=[_saves(ctx), f"tran 5n {_EVENT + 100e-6:.9g} 0 10n uic"],
        options=(*common.buffer_options(ctx), "method=gear"),
    )


def _reverse_figures(ctx: Context, run: RunResult, key: str, text: str) -> list[Figure]:
    time = run.real("time")
    terminal = run.real("vout")
    figures = []
    for amps in (0.5, 2.0):
        instant = _RAMP_START + (_RAMP_END - _RAMP_START) * amps / _RAMP_AMPS - 1e-5
        tag = f"{amps:g}".replace(".", "a")
        volts = measure.value_at(time, terminal, instant)
        limited = amps == 0.5 and key == "reverse"
        figures.append(
            Figure(
                f"{key}_{tag}",
                f"{text}: terminal with {amps:g} A drawn by a reversed source",
                volts,
                "V",
                expected=-0.8 if limited else None,
                low=-0.9 if limited else None,
                high=-0.7 if limited else None,
                source="section 4.9: -0.8 V from a source limited to 0.5 A; limit set "
                "here, 0.1 V around it"
                if limited
                else "",
            )
        )
        if amps == 0.5:
            figures.append(
                Figure(
                    f"{key}_power",
                    f"{text}: power in the suppressor D21 at 0.5 A",
                    -volts * amps,
                    "W",
                )
            )
        if ctx.tier == OPEN_TIER:
            figures.append(
                Figure(
                    f"{key}_pair_{tag}",
                    f"{text}: current through Q15 from the instrument at {amps:g} A",
                    measure.value_at(time, run.real("@mq15[id]"), instant),
                    "A",
                )
            )
    return figures


def _plug_figures(run: RunResult, key: str, text: str) -> list[Figure]:
    time = run.real("time")
    end = float(time[-1])
    mid, terminal = run.real("mid"), run.real("vout")
    drive = run.real("g_out") - mid
    node = run.real("vout_s")
    before = measure.value_at(time, node, _EVENT - 1e-6)
    return [
        Figure(
            f"{key}_terminal",
            f"{text}: highest voltage at the terminal",
            measure.extremes(time, terminal, _EVENT, end)[1],
            "V",
        ),
        Figure(
            f"{key}_drain",
            f"{text}: largest drain-source voltage of Q16",
            measure.extremes(time, terminal - mid, _EVENT, end)[1],
            "V",
            high=common.TRANSISTOR_VOLTS,
            source="section 4.9: the transistors are rated 30 V (datasheet value)",
        ),
        Figure(
            f"{key}_gate",
            f"{text}: largest gate-source voltage of the pair",
            measure.extremes(time, drive, _EVENT, end)[1],
            "V",
            high=_LOW_THRESHOLD,
            source="the pair stays off: lowest threshold 1.1 V (TI SLPS515A, page 3)",
        ),
        Figure(
            f"{key}_node",
            f"{text}: largest move of the node after the shunts",
            float(np.max(np.abs(measure.window(time, node - before, _EVENT, end)[1]))),
            "V",
        ),
    ]


def _charged_figures(ctx: Context, run: RunResult, key: str, text: str) -> list[Figure]:
    time = run.real("time")
    end = float(time[-1])
    pair = common.pair_current(ctx, run)
    mid, node, terminal = run.real("mid"), run.real("vout_s"), run.real("vout")
    backward = -pair
    loss = np.abs(node - terminal) * np.abs(pair)
    return [
        Figure(
            f"{key}_current",
            f"{text}: largest current backward through the pair",
            measure.extremes(time, backward, _EVENT, end)[1],
            "A",
            high=_PULSED_AMPS,
            source="TI SLPS515A, page 1: pulsed drain current 239 A",
        ),
        Figure(
            f"{key}_time",
            f"{text}: time for which more than 1 A flows backward",
            measure.integral(time, np.where(backward > 1.0, 1.0, 0.0), _EVENT, end),
            "s",
        ),
        Figure(
            f"{key}_energy",
            f"{text}: energy in the pair",
            common.energy(time, loss, _EVENT, end),
            "J",
            high=common.AVALANCHE_JOULES,
            source="TI SLPS515A, page 1: 39 mJ of avalanche energy, taken as the scale",
        ),
        Figure(
            f"{key}_node",
            f"{text}: highest voltage at the node after the shunts",
            measure.extremes(time, node, _EVENT, end)[1],
            "V",
        ),
        Figure(
            f"{key}_supply",
            f"{text}: supply node 100 us after the plug",
            float(run.real("supply")[-1]),
            "V",
        ),
        Figure(
            f"{key}_drive",
            f"{text}: lowest gate-source voltage of the pair",
            measure.extremes(time, run.real("g_out") - mid, _EVENT, end)[0],
            "V",
        ),
    ]


@bench(
    "output_stage",
    "terminal",
    "The output terminal under abuse: reversed source, live source on the open output, "
    "charged capacitor on a lower output",
    "section 4.9 (VOUT, D-70, D-71; source output, D-57), section 4.3 (charged device)",
)
def terminal(ctx: Context) -> Outcome:
    """Three things that a user can do to the terminal are simulated.

    With the output off, a reversed source draws a current out of the
    terminal that rises to 2 A: the suppressor carries it forward, and the
    run shows the voltage it leaves at the terminal and whether the open
    pair begins to conduct from the side of the instrument. With the
    output off, a live source of 5 V and of 15 V is connected through a
    short lead, and one of 24 V behind 1 ohm: the run shows the voltage at
    the terminal, across the transistor on the terminal side and between
    gate and source of the pair, which has to stay off. The source of 5 V is
    connected once more to an instrument without supply. With the output on
    at 0.8 V, a capacitor of 100 uF charged to 5.5 V is plugged in: the
    current runs backward through the pair and the ladder, in range 3, in
    range 0, and with a source that cannot take current back.
    """
    decks = {
        "reverse": _reverse_deck(ctx, 0.03),
        "hot-5": _plug_deck(ctx, 5.0, 0.05),
        "hot-15": _plug_deck(ctx, 15.0, 0.05),
        "strike": _plug_deck(ctx, 24.0, 1.0),
        "unpowered": _unpowered_deck(ctx),
        "charged-3": _charged_deck(ctx, 3, stiff=False),
        "charged-0": _charged_deck(ctx, 0, stiff=False),
        "charged-stiff": _charged_deck(ctx, 3, stiff=True),
    }
    if ctx.tier == OPEN_TIER:
        decks["reverse-high"] = _reverse_deck(ctx, 0.15)
    for key in ("reverse", "hot-15", "charged-3"):
        ctx.kept[f"{ctx.prefix}.{key}.cir"] = decks[key]
    runs = ctx.run_many(decks)

    figures = _reverse_figures(ctx, runs["reverse"], "reverse", "Output off")
    if "reverse-high" in runs:
        figures += _reverse_figures(
            ctx, runs["reverse-high"], "reverse_high", "Output off, suppressor with 0.15 ohm"
        )
    figures += _plug_figures(runs["hot-5"], "hot5", "Output off, 5 V connected")
    figures += _plug_figures(runs["hot-15"], "hot15", "Output off, 15 V connected")
    strike = runs["strike"]
    time = strike.real("time")
    end = float(time[-1])
    backward = -common.suppressor_current(ctx, strike)
    power = strike.real("vout") * backward
    figures += _plug_figures(strike, "strike", "Output off, 24 V behind 1 ohm")
    figures += [
        Figure(
            "strike_current",
            "Output off, 24 V behind 1 ohm: current in the suppressor D21",
            measure.extremes(time, backward, _EVENT, end)[1],
            "A",
        ),
        Figure(
            "strike_power",
            "Output off, 24 V behind 1 ohm: power in the suppressor D21",
            measure.extremes(time, power, _EVENT, end)[1],
            "W",
            high=_SUPPRESSOR_WATTS,
            source="Nexperia PTVSxS1UR, page 3: 400 W for a pulse of a millisecond",
        ),
    ]
    dead = runs["unpowered"]
    dead_time = dead.real("time")
    figures += _plug_figures(dead, "unpowered", "Instrument without supply, 5 V connected")
    figures.append(
        Figure(
            "unpowered_gate_node",
            "Instrument without supply, 5 V connected: highest voltage of the gate node, TP37",
            measure.extremes(dead_time, dead.real("out_gate"), _EVENT, float(dead_time[-1]))[1],
            "V",
            high=0.3,
            source="section 16: every gate at or below 0.3 V with 5 V on VOUT and the "
            "instrument off",
        )
    )
    for key, text in (
        ("charged-3", "Range 3, source that cannot sink"),
        ("charged-0", "Range 0, source that cannot sink"),
        ("charged-stiff", "Range 3, stiff source"),
    ):
        figures += _charged_figures(ctx, runs[key], key.replace("-", "_"), text)

    def against_current(run: RunResult, name: str) -> tuple[np.ndarray, np.ndarray]:
        """A waveform of a reverse run over the current that the source draws."""
        axis = run.real("time")
        part = (axis >= _RAMP_START) & (axis <= _RAMP_END)
        amps = (axis[part] - _RAMP_START) / (_RAMP_END - _RAMP_START) * _RAMP_AMPS
        return amps, run.real(name)[part]

    reverse = runs["reverse"]
    reverse_traces = [
        Trace(*against_current(reverse, "vout"), "terminal, suppressor with 0.03 ohm", 0),
        Trace(*against_current(reverse, "mid"), "common source", 0, "--"),
        Trace(*against_current(reverse, "out_gate"), "gate node", 0, ":"),
    ]
    if "reverse-high" in runs:
        high = runs["reverse-high"]
        reverse_traces.append(
            Trace(*against_current(high, "vout"), "terminal, suppressor with 0.15 ohm", 0)
        )
        for run, label in ((reverse, "0.03 ohm"), (high, "0.15 ohm")):
            amps, passed = against_current(run, "@mq15[id]")
            reverse_traces.append(Trace(amps, np.abs(passed) + 1e-12, label, 1))
    else:
        amps, passed = against_current(reverse, "@r110[i]")
        reverse_traces.append(Trace(amps, np.abs(passed) + 1e-12, "0.1 ohm shunt", 1))
    reversed_graph = Graph(
        name="reversed",
        title="Output off: a reversed source draws current out of the terminal",
        xlabel="Current drawn by the reversed source (A)",
        panels=(
            Panel("Voltage (V)", marks=((-0.8, "-0.8 V"),)),
            Panel("Current from the instrument through Q15 (A)", log=True),
        ),
        traces=tuple(reverse_traces),
        xmarks=((0.5, "0.5 A"),),
    )
    plug_traces = []
    for key, label in (("hot-5", "5 V"), ("hot-15", "15 V"), ("strike", "24 V behind 1 ohm")):
        run = runs[key]
        axis = (run.real("time") - _EVENT) * 1e6
        part = (axis >= -0.2) & (axis <= 3.0)
        plug_traces += [
            Trace(axis[part], run.real("vout")[part], label, 0),
            Trace(axis[part], (run.real("g_out") - run.real("mid"))[part], label, 1),
            Trace(axis[part], run.real("mid")[part], label, 2),
        ]
    plug_graph = Graph(
        name="live-source",
        title="Output off: a live source is connected to the terminal",
        xlabel="Time after the connection (us)",
        panels=(
            Panel("Terminal (V)", marks=((15.0, "stand-off 15 V"),)),
            Panel("Gate-source voltage of the pair (V)", marks=((_LOW_THRESHOLD, "1.1 V"),)),
            Panel("Common source (V)"),
        ),
        traces=tuple(plug_traces),
    )
    charged_traces = []
    for key, label in (
        ("charged-3", "range 3, source cannot sink"),
        ("charged-0", "range 0, source cannot sink"),
        ("charged-stiff", "range 3, stiff source"),
    ):
        run = runs[key]
        axis = (run.real("time") - _EVENT) * 1e6
        part = (axis >= -2.0) & (axis <= 60.0)
        charged_traces += [
            Trace(axis[part], -common.pair_current(ctx, run)[part], label, 0),
            Trace(axis[part], run.real("vout_s")[part], f"node after the shunts, {label}", 1),
            Trace(axis[part], run.real("supply")[part], f"supply node, {label}", 1, "--"),
        ]
    charged_graph = Graph(
        name="charged",
        title="Output on at 0.8 V: 100 uF charged to 5.5 V is plugged in",
        xlabel="Time after the plug (us)",
        panels=(Panel("Current backward through the pair (A)"), Panel("Voltage (V)")),
        traces=tuple(charged_traces),
    )
    notes = (
        "The forward curve of the suppressor is an assumption (0.75 V at 0.1 A, "
        "0.03 ohm, and 0.15 ohm in a second run); its datasheet has none. With it the "
        "terminal stands at -0.8 V with 0.5 A, which is 0.4 W in the suppressor: about "
        "50 K to 90 K of rise by the thermal resistance of its datasheet (130 K/W on "
        "1 cm2 of copper, 220 K/W on the standard footprint). That is why the "
        "reversed source has to be limited.",
        "With the output off the gate node rests at 0 V and the common source follows "
        "the terminal one body diode above it. The current that the open pair passes "
        "from the instrument is taken from the transistor model below its threshold; "
        "it shows that the pair stays off, and no value of nanoamperes may be taken "
        "from it.",
        "A live source on the open output lifts the gates through the drain of Q16. "
        "C74 and the 10 ohm of R120 hold them; the figure is the gate-source voltage "
        "against the lowest threshold of the datasheet.",
        "Without supply every rail and line is at 0 V and the gate driver U22 is left "
        "out of the circuit, so that R115 alone holds the gate network: what the output "
        "of the unpowered driver does is in no datasheet and is an open check of "
        "section 16.",
        "The live source is ideal behind 50 mohm and 0.2 uH (1 ohm for the 24 V case); "
        "the terminal rings against that inductance, and the suppressor bounds the "
        "ring from 16.7 V to 18.5 V.",
        "The source that cannot sink is a current source limited to 1.4 A on C53 and "
        "C54 of the schematic, with 10 mohm for the source pair. On the board the "
        "regulator and its diode D11 see this event too; they belong to the source "
        "meter block. The stiff source is ideal behind 10 mohm and takes current back, "
        "as an external supply in ampere mode may.",
        "The plugged capacitor has 20 mohm in series, behind 50 mohm and 0.2 uH of "
        "cable; these are assumptions. In range 0 the current passes the body diodes "
        "of the ladder clamp, which belong to the ladder block.",
    )
    return Outcome(tuple(figures), (reversed_graph, plug_graph, charged_graph), notes)
