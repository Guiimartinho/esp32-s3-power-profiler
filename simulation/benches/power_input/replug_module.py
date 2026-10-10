"""The cable of the module is pulled and plugged again: input 2 of the multiplexer."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.power_input import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_PLUG_FIRST = 0.1e-3
"""Instant at which the first source is plugged."""

_PLUG_MODULE = 3.5e-3
"""Instant at which the cable of the module is plugged first while USB-C
supplies: the rail is up."""

_PULL = 4.5e-3
"""Instant at which the contact of that cable opens in those runs."""

_SINGLE_PULL = 1.6e-3
"""Instant at which the contact opens in the runs with the cable of the
module alone: the multiplexer is charging the rail, which stands near 1 V."""

_AFTER = 0.4e-3
"""Time a run goes on after the contact has closed again."""

_GAPS = (20e-6, 0.5e-3, 1e-3, 1.5e-3, 2e-3, 2.3e-3, 2.6e-3, 3e-3, 5e-3)
"""Times for which the contact stays open while USB-C supplies. The limiter
turns off between 2.6 ms and 3 ms; a longer gap ends like a first plug."""

_FEW_GAPS = (2e-3, 2.3e-3, 2.6e-3)
"""The gaps around the worst one, for the other corners."""

_SINGLE_GAPS = (4e-6, 7e-6, 10e-6, 14e-6)
"""Gaps of the runs with the cable of the module alone: the multiplexer takes
its charging current from 1.1 uF, which lasts for microseconds."""

_DAMPER = ("R14", "C5")
"""The position for a damper at input 2, which the schematic leaves without
parts (decision D-84): 0.33 ohm and 10 uF."""

_DAMPER_SHARE = 0.5
"""Share of its capacitance that the capacitor of the damper keeps at 5 V: an
assumption, the figure of a 10 uF 25 V part in 0805 (49.7 % for the one on
the rail). The position names no part number."""

_INPUT_RATING = 6.0
"""Absolute maximum of the inputs of the multiplexer (TPS2116 datasheet
SLVSFG1A, page 4), and the level that TP4 has to stay below (section 16)."""

_VSYS_MOST = 5.5
"""Highest supply of the controller module at its VSYS pin (Pico 2 datasheet,
section 4.5: 1.8 V to 5.5 V)."""

_STEP = 0.5e-6
"""Longest time step; the tolerance below makes the solver take shorter ones
where the cable rings."""

_OPTIONS = ("reltol=1e-4",)
"""A tighter tolerance of the solver: the figure of this bench is the peak
of a ring with a period of 4 us, less than 0.1 V below a limit."""

_SAVE = "save pico_vbus pico_5v vin2 vin1 rail vsys en_p ok5v i(Vport_i)"
"""What a run keeps."""

_LATE_CLAMP = "vovc=5.83 vclamp=5.61"
"""A limiter that clamps as late as its datasheet allows (SLVSET8A page 6)."""

_SLOW = _LATE_CLAMP + " tsc=15u"
"""The same with a reaction to a short circuit of 15 us instead of 5 us. The
datasheet states the typical 5 us only (page 8): the factor is an assumption."""

_RATING_SOURCE = (
    "section 16: data cable plugged again, TP4 below 6.0 V; TPS2116 datasheet, page 4: 6 V"
)


@dataclass(frozen=True)
class _Corner:
    """One combination of sources, cable and limiter.

    Attributes:
        label: What the figures call it.
        volts: Voltage of the port of the module and of the USB-C source.
        ohms: Resistance of the cable of the module with its contacts.
        henries: Inductance of that cable.
        limiter: Parameters of the limiter U3, empty for the typical part.
        gaps: Times for which the contact stays open.
        damper: True with the damper at input 2 fitted.
        single: True with the cable of the module alone, bouncing while the
            multiplexer charges the rail.
    """

    label: str
    volts: float
    ohms: float
    henries: float
    limiter: str
    gaps: tuple[float, ...]
    damper: bool = False
    single: bool = False

    @property
    def pull(self) -> float:
        """Instant at which the contact opens."""
        return _SINGLE_PULL if self.single else _PULL


_SHORT = "5.5 V, cable of 0.08 ohm and 0.3 uH"

_CORNERS = {
    "short": _Corner(_SHORT, 5.5, 0.08, 0.3e-6, _LATE_CLAMP, _GAPS),
    "slow": _Corner(f"{_SHORT}, limiter reacts in 15 us", 5.5, 0.08, 0.3e-6, _SLOW, _FEW_GAPS),
    "long": _Corner(
        "5.5 V, cable of 0.15 ohm and 1.5 uH", 5.5, 0.15, 1.5e-6, _LATE_CLAMP, _FEW_GAPS
    ),
    "usb": _Corner(
        "5.25 V, cable of 0.08 ohm and 0.3 uH", 5.25, 0.08, 0.3e-6, _LATE_CLAMP, _FEW_GAPS
    ),
    "typical": _Corner("5.0 V, cable of 0.25 ohm and 0.8 uH", 5.0, 0.25, 0.8e-6, "", _FEW_GAPS),
    "damped": _Corner(f"{_SHORT}, damper fitted", 5.5, 0.08, 0.3e-6, _SLOW, _FEW_GAPS, damper=True),
    "single": _Corner(
        f"Module cable alone, {_SHORT}", 5.5, 0.08, 0.3e-6, _SLOW, _SINGLE_GAPS, single=True
    ),
}
"""The corner of the specification (5.5 V and a short cable); the same with a
limiter that reacts more slowly; a long cable of low resistance; the highest
voltage of a standard USB port; a typical case; the slow corner again with
the damper fitted; and the cable of the module alone. All but the typical
case have a limiter with the late clamp."""


def _text(seconds: float) -> str:
    """A time with its unit."""
    return f"{seconds * 1e6:g} us" if seconds < 1e-3 else f"{seconds * 1e3:g} ms"


def _name(key: str, gap: float) -> str:
    """The name of a run."""
    return f"{key}-{_text(gap).replace(' ', '').replace('.', 'p')}"


def _deck(ctx: Context, corner: _Corner, gap: float) -> str:
    """The cable of the module is plugged, pulled and plugged again."""
    params = {"U3": corner.limiter} if corner.limiter else {}
    refs = list(common.carrier_refs(ctx.netlist))
    scales = {}
    if corner.damper:
        refs += _DAMPER
        scales["C5"] = _DAMPER_SHARE
    circuit = common.circuit(ctx, refs, params=params, scales=scales)
    first = _PLUG_FIRST if corner.single else _PLUG_MODULE
    stimulus = common.module_port(
        corner.volts,
        first,
        unplug_at=corner.pull,
        replug_at=corner.pull + gap,
        ohms=corner.ohms,
        henries=corner.henries,
        switch_amps=None,
    )
    if not corner.single:
        stimulus = common.usb_c_source(corner.volts, _PLUG_FIRST) + stimulus
    stimulus += common.boost_start() + common.idle_loads()
    return ctx.deck(
        f"Cable of the module open for {_text(gap)}: {corner.label}",
        circuit,
        stimulus,
        control=[_SAVE, common.transient(_STEP, corner.pull + gap + _AFTER)],
        options=_OPTIONS,
    )


def _peak(run: RunResult, name: str, start: float, stop: float) -> float:
    """The highest level of a node between two instants."""
    return float(np.max(run.real(name)[common.cut(run.real("time"), start, stop)]))


def _ring_graph(name: str, title: str, run: RunResult, closes: float) -> Graph:
    """The first microseconds after the contact has closed."""
    time = run.real("time")
    shown = common.cut(time, closes - 5e-6, closes + 45e-6)
    micro = (time[shown] - closes) * 1e6
    return Graph(
        name=name,
        title=title,
        xlabel="Time after the contact has closed (us)",
        panels=(
            Panel("Voltage (V)", marks=((_INPUT_RATING, "rating 6 V"),)),
            Panel("Current of the cable (A)"),
        ),
        traces=(
            Trace(micro, run.real("pico_5v")[shown], "input of the limiter", 0),
            Trace(micro, run.real("vin2")[shown], "input 2 (TP4)", 0),
            Trace(micro, run.real("vsys")[shown], "VSYS of the module", 0, "--"),
            Trace(micro, run.real("vport_i#branch")[shown], "cable", 1),
        ),
    )


@bench(
    "power_input",
    "replug-module",
    "The cable of the module is plugged again: what reaches input 2 of the multiplexer",
    "section 4.1 (a contact that opens and closes again), section 14 (inputs of the "
    "multiplexer near their rating), section 16 (data cable plugged again, TP4 below 6.0 V), "
    "decision D-84",
)
def replug_module(ctx: Context) -> Outcome:
    """The cable of the module is pulled and plugged again with its limiter still on.

    The limiter of the module input has 100 nF at its input and 1 uF at its
    output, which is input 2 of the multiplexer. While USB-C supplies the
    rail, input 2 carries no load: with the cable pulled, the two capacitors
    empty through the enable divider and the dividers of the module within
    milliseconds, and the limiter stays on down to 2.76 V at its input. A
    contact that closes in that time puts the port voltage on the cable with
    the limiter conducting: the cable rings with the two capacitors, and the
    diode of the module to its VSYS capacitor is what bounds the peak. In
    the last runs the cable of the module is alone and its contact bounces
    while the multiplexer charges the rail, which empties the capacitors
    within microseconds.
    """
    decks: dict[str, str] = {}
    closes_of: dict[str, float] = {}
    for key, corner in _CORNERS.items():
        for gap in corner.gaps:
            decks[_name(key, gap)] = _deck(ctx, corner, gap)
            closes_of[_name(key, gap)] = corner.pull + gap
    keep = (_name("short", 2e-3), _name("slow", 2.6e-3), _name("damped", 2.6e-3))
    runs = common.run_all(ctx, decks, keep=keep)
    figures: list[Figure] = []
    best: dict[str, tuple[float, str]] = {}
    for key, corner in _CORNERS.items():
        for gap in corner.gaps:
            name = _name(key, gap)
            peak = _peak(runs[name], "vin2", closes_of[name], closes_of[name] + _AFTER)
            if key not in best or peak > best[key][0]:
                best[key] = (peak, name)
            figures.append(
                Figure(
                    f"input2_{name.replace('-', '_')}",
                    f"{corner.label}: highest level of input 2 after a gap of {_text(gap)}",
                    peak,
                    "V",
                    high=_INPUT_RATING,
                    source=_RATING_SOURCE,
                )
            )
    for key in ("short", "single"):
        corner = _CORNERS[key]
        for gap in corner.gaps:
            run = runs[_name(key, gap)]
            at = corner.pull + gap - 1e-6
            figures.append(
                Figure(
                    f"before_{_name(key, gap).replace('-', '_')}",
                    f"{corner.label}: input of the limiter when the contact closes after "
                    f"{_text(gap)}",
                    measure.value_at(run.real("time"), run.real("pico_5v"), at),
                    "V",
                )
            )
    typical_peak, _ = best["short"]
    slow_peak, slow_name = best["slow"]
    worst = runs[slow_name]
    closes = closes_of[slow_name]
    after = common.cut(worst.real("time"), closes, closes + _AFTER)
    first = runs[_name("short", _GAPS[0])]
    figures += [
        Figure(
            "input2_highest",
            "Highest level of input 2 with a limiter of typical reaction time, USB-C supplies",
            typical_peak,
            "V",
            expected=5.945,
            high=_INPUT_RATING,
            source="section 4.1: within 25 mV to 85 mV of the 6 V rating in the worst corners "
            "(simulated before); TPS2116 datasheet, page 4: 6 V",
        ),
        Figure(
            "input2_slow",
            "Highest level of input 2 with a limiter that reacts in 15 us, USB-C supplies",
            slow_peak,
            "V",
            high=_INPUT_RATING,
            source=_RATING_SOURCE + "; the 15 us are an assumption",
        ),
        Figure(
            "input2_damped",
            "Highest level of input 2 with the damper fitted (limiter that reacts in 15 us)",
            best["damped"][0],
            "V",
            high=_INPUT_RATING,
            source="decision D-84: a damper of 0.33 ohm with 10 uF on the input from the "
            "controller module; TPS2116 datasheet, page 4: 6 V",
        ),
        Figure(
            "input2_single",
            "Highest level of input 2 with the cable of the module alone, bouncing while "
            "the multiplexer charges the rail",
            best["single"][0],
            "V",
            high=_INPUT_RATING,
            source=_RATING_SOURCE,
        ),
        Figure(
            "limiter_input_highest",
            "Highest voltage at the input of the limiter in the run with the highest input 2",
            _peak(worst, "pico_5v", closes, closes + _AFTER),
            "V",
            high=21.0,
            source="section 4.1: input of the limiter rated 21 V",
        ),
        Figure(
            "vsys_highest",
            "Highest level of VSYS of the module in all runs",
            max(
                _peak(run, "vsys", closes_of[name] - 1e-6, closes_of[name] + _AFTER)
                for name, run in runs.items()
            ),
            "V",
            high=_VSYS_MOST,
            source="Pico 2 datasheet, section 4.5: VSYS from 1.8 V to 5.5 V",
        ),
        Figure(
            "cable_highest",
            "Largest current of the cable in the run with the highest input 2",
            _peak(worst, "vport_i#branch", closes, closes + _AFTER),
            "A",
        ),
        Figure(
            "first_plug",
            f"{_SHORT}: highest level of input 2 at the first plug, with this input empty",
            _peak(first, "vin2", _PLUG_MODULE, _PULL),
            "V",
            high=_INPUT_RATING,
            source="TPS2116 datasheet, page 4: 6 V",
        ),
        Figure(
            "first_plug_input",
            f"{_SHORT}: highest voltage at the input of the limiter at the first plug",
            _peak(first, "pico_5v", _PLUG_MODULE, _PULL),
            "V",
            high=21.0,
            source="section 4.1: input of the limiter rated 21 V",
        ),
        Figure(
            "rail_moves",
            "Largest change of the 5 V rail while the cable of the module is plugged again "
            "and USB-C supplies",
            float(np.ptp(worst.real("rail")[after])),
            "V",
            high=0.3,
            source="rule F-35: a step of the rail of more than 0.3 V marks samples",
        ),
    ]
    damped_name = best["damped"][1]
    single_name = best["single"][1]
    whole_run = runs[_name("short", 3e-3)]
    t_whole = whole_run.real("time")
    window = common.cut(t_whole, _PLUG_MODULE - 0.2e-3, _PULL + 3e-3 + _AFTER)
    milli = t_whole[window] * 1e3
    whole = Graph(
        name="gap",
        title=f"First plug at 3.5 ms, contact open from 4.5 ms to 7.5 ms: {_SHORT}",
        xlabel="Time (ms)",
        panels=(Panel("Voltage (V)", marks=((2.76, "limiter off at 2.76 V"),)),),
        traces=(
            Trace(milli, whole_run.real("pico_5v")[window], "input of the limiter", 0),
            Trace(milli, whole_run.real("vin2")[window], "input 2 (TP4)", 0),
            Trace(milli, whole_run.real("vsys")[window], "VSYS of the module", 0, "--"),
            Trace(milli, whole_run.real("rail")[window], "5 V rail", 0, ":"),
        ),
        xmarks=((_PULL * 1e3, "opens"), ((_PULL + 3e-3) * 1e3, "closes")),
    )
    graphs = (
        _ring_graph(
            "close",
            f"The contact closes: {_CORNERS['slow'].label}, USB-C supplies",
            worst,
            closes,
        ),
        _ring_graph(
            "damped",
            f"The same with the damper fitted: {_CORNERS['damped'].label}",
            runs[damped_name],
            closes_of[damped_name],
        ),
        _ring_graph(
            "single",
            f"The contact closes: {_CORNERS['single'].label}",
            runs[single_name],
            closes_of[single_name],
        ),
        whole,
    )
    notes = (
        "The port is an ideal source behind its cable, and the contact a conductance "
        "that opens within 1 us and closes within 50 ns: assumptions, as are the cables. "
        "The USB-C source has the same voltage as the port.",
        "The module is the model of the digital block: the diode of the module from VBUS "
        "to VSYS (475 mV at 0.1 A, 605 mV at 1 A), 47 uF at their nominal value on VSYS, "
        "5.6 kohm and 10 kohm from VBUS to ground, and a load of 0.1 W. The peak at input 2 "
        "rests on that diode and on the level of VSYS, which the carrier holds through its "
        "own diode from the rail.",
        "The limiter is ohmic when the contact closes. Its clamp and its reaction to a "
        "short circuit need 5 us (typical; the datasheet states no limit), which is about "
        "as long as the first peak of the ring takes: after the longest gaps the typical "
        "reaction cuts the peak, a slower one does not. A limiter that clamps from 5.54 V "
        "or 5.69 V instead of 5.83 V gives the same peak within 20 mV.",
        "The 100 nF and the 1 uF on this input are in 0603 and stay at their nominal "
        "value: no bias curve of theirs was read. Less capacitance gives a faster ring.",
        "The position for a damper on this input (R14, 0.33 ohm, and C5, 10 uF; decision "
        "D-84) is without parts, as the schematic has it, except in the runs that say "
        "otherwise. There the capacitor has half its value, an assumption for what a "
        "10 uF 25 V part in 0805 keeps at 5 V; the position names no part number.",
        "While USB-C supplies, the supervisor holds the carrier off during these runs "
        "(its delay is 0.3 s), so the rail carries no load; input 2 does not depend on it.",
    )
    return Outcome(tuple(figures), graphs, notes)
