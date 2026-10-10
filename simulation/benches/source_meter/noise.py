"""The noise that the source puts across the shunt of the lowest range."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from benches.source_meter import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.engine import RunResult

_SHUNT = common.RANGE_OHMS[0]
"""The shunt of range 0, across which the noise is read as current."""

_SWEEP = "dec 40 1 10meg"
"""Frequencies of the noise run."""

_BAND = (1.0, 10e6)
"""Band over which the filtered density is summed."""

_MEAN_SAMPLES = 100
_SAMPLE_RATE = 100e3
"""The mean of 100 samples at 100 kSPS (requirement R-04, section 11)."""

_LIMIT = 40e-9
"""Noise limit of requirement R-04 in source mode."""

_MEAN_LIMIT = 5e-9
"""Limit of section 11 for the mean of 100 samples in source mode."""


@dataclass(frozen=True, slots=True)
class _Case:
    """One state in which the noise is read.

    Attributes:
        volts: Set-point.
        farads: Capacitance at the terminal beside the 100 nF of C71.
    """

    volts: float
    farads: float

    @property
    def tag(self) -> str:
        return f"{self.volts:g}v_{self.farads * 1e9:g}nf".replace(".", "p")

    @property
    def text(self) -> str:
        beside = "output open" if not self.farads else f"{self.farads * 1e6:g} uF at the terminal"
        return f"{self.volts:g} V, {beside}"


_CASES = (
    _Case(5.0, 0.0),
    _Case(5.0, 100e-9),
    _Case(5.0, 1e-6),
    _Case(0.8, 0.0),
)


def _settle(ctx: Context, case: _Case) -> str:
    return common.settle_deck(
        ctx, f"State for the noise run: {case.text}", case.volts, index=0, farads=case.farads
    )


def _noise_deck(ctx: Context, case: _Case, settled: RunResult, across: str) -> str:
    """The state as an operating point, and the noise between two nodes."""
    circuit = common.source(
        ctx,
        case.volts,
        overrides={common.DAC: common.part(ctx, common.DAC, code=common.code_of(case.volts))},
    )
    return ctx.deck(
        f"Noise at {case.text}",
        circuit,
        common.rails(vref=f"dc {common.REFERENCE:g} ac 1"),
        common.controller(),
        common.dut(0, 0.0, case.farads),
        common.nodeset_from(settled),
        control=[f"noise {across} Vref {_SWEEP}"],
    )


def _density(run: RunResult) -> tuple[np.ndarray, np.ndarray]:
    return run.real("frequency", "noise1"), run.real("onoise_spectrum")


def _mean_weight(frequency: np.ndarray) -> np.ndarray:
    """Magnitude of the mean of 100 samples as a filter."""
    span = _MEAN_SAMPLES / _SAMPLE_RATE
    return np.asarray(np.abs(np.sinc(frequency * span)), dtype=np.float64)


@bench(
    "source_meter",
    "noise",
    "Noise of the source across the 1 kohm shunt of range 0",
    "requirement R-04, sections 4.2 and 4.10 (noise in source mode), decision D-59",
)
def noise(ctx: Context) -> Outcome:
    """The source stands at rest in range 0 and its noise is read as the chain reads it.

    The noise voltage between the supply node and the node after the shunts
    is the noise that the 1 kohm of range 0 turns into current. Its density
    is weighted with the filter in front of the converter, two poles at
    40 kHz, and summed; the mean of 100 samples adds its own weight. The
    run is made at 5.0 V with the output open, with 100 nF and with 1 uF
    at the terminal, and at 0.8 V. A second noise run gives the density at
    the regulator output itself.
    """
    settled = ctx.run_many(
        {f"state-{case.tag}".replace("_", "-"): _settle(ctx, case) for case in _CASES}
    )
    decks = {}
    for case in _CASES:
        state = settled[f"state-{case.tag}".replace("_", "-")]
        decks[f"shunt-{case.tag}".replace("_", "-")] = _noise_deck(
            ctx, case, state, "v(supply,vout_s)"
        )
    first = _CASES[0]
    decks["output"] = _noise_deck(
        ctx, first, settled[f"state-{first.tag}".replace("_", "-")], "v(ldo_out)"
    )
    kept = {f"shunt-{first.tag}".replace("_", "-")}
    runs = {name: ctx.run(name, decks[name]) for name in kept}
    runs.update(ctx.run_many({name: deck for name, deck in decks.items() if name not in kept}))

    figures: list[Figure] = []
    traces: list[Trace] = []
    for case in _CASES:
        frequency, volts = _density(runs[f"shunt-{case.tag}".replace("_", "-")])
        amps = volts / _SHUNT
        weighted = amps * common.anti_alias(frequency)
        total = measure.integrated_noise(frequency, weighted, *_BAND)
        mean = measure.integrated_noise(frequency, weighted * _mean_weight(frequency), *_BAND)
        figures += [
            Figure(
                f"noise_{case.tag}",
                f"{case.text}: noise current in range 0 behind the filter of the converter",
                total,
                "A",
                expected=26.5e-9,
                high=_LIMIT,
                source="requirement R-04: 40 nA at the most in source mode; section 4.2: "
                "26 nA to 27 nA simulated",
            ),
            Figure(
                f"mean_{case.tag}",
                f"{case.text}: noise of the mean of 100 samples",
                mean,
                "A",
                expected=1.1e-9 if not case.farads else None,
                high=_MEAN_LIMIT,
                source="section 11: 5 nA for the mean of 100 samples; section 4.10: 1.1 nA "
                "with the output open, up to 3.9 nA with a device",
            ),
        ]
        traces.append(Trace(frequency, amps * 1e12, case.text, 0))
    frequency, volts = _density(runs["output"])
    figures += [
        Figure(
            "output_density",
            "Noise density at the regulator output at 10 kHz, 5.0 V",
            float(np.interp(10e3, frequency, volts)),
            "V/√Hz",
            expected=125e-9,
            source="section 4.10: 125 nV/rtHz, a typical datasheet figure without a maximum",
        ),
        Figure(
            "output_noise",
            "Noise at the regulator output from 10 Hz to 100 kHz, 5.0 V",
            measure.integrated_noise(frequency, volts, 10.0, 100e3),
            "V",
            expected=40e-6,
            source="LT3080 Rev. E, page 4: 40 uV RMS with 10 uF and 1.1 A",
        ),
    ]
    traces.append(Trace(frequency, volts * 1e9, "regulator output, 5.0 V", 1))
    graph = Graph(
        name="density",
        title="Noise of the source in range 0",
        xlabel="Frequency (Hz)",
        panels=(
            Panel("Across the shunt, as current (pA/rtHz)", log=True),
            Panel("At the regulator output (nV/rtHz)", log=True),
        ),
        traces=tuple(traces),
        logx=True,
    )
    notes = (
        "The noise of the regulator is the 125 nV/rtHz of its datasheet, flat, as the "
        "model holds it: a typical figure without a maximum, and without the 1/f part. "
        "Below the loop bandwidth it stands at the output unchanged; near the crossover "
        "the loop of the model raises it, and that part rests on the fitted loop.",
        "The DAC and the reference are sources without noise here: the datasheet of the "
        "DAC states none, and the reference belongs to another block. The buffer U17 "
        "and every resistor of the netlist carry their noise.",
        "The shunt of range 0 is the 1 kohm resistor that stands for it, with its own "
        "thermal noise, which the chain reads in either mode. The amplifier chain and "
        "the converter are not in this circuit: only their filter is, as a weight of "
        "two poles at 40 kHz with Q = 0.74 (section 4.5).",
        "The regulator carries only its minimum load in these runs. A behavioral source "
        "makes no noise, so the pre-regulator adds none: its switching ripple is not in "
        "the averaged model at all.",
    )
    return Outcome(tuple(figures), (graph,), notes)
