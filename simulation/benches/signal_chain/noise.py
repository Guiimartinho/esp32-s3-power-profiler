"""Noise of the chain at the converter input, referred to the current of each range."""

from __future__ import annotations

import numpy as np

from benches import frontend
from benches.signal_chain import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_SHUNT_PARTS = ("R101", "R104", "R107", "R110")
"""The shunt of each range, from the netlist."""

_SHUNT_NODES = ("supply", "sense_r1", "sense_r2", "sense_r3")
"""Node of each shunt on the side of the supply."""

_BIAS_AMPS = (50e-6, 1.5e-3, 50e-3, 0.5)
"""Current through each shunt at the operating point: about 50 mV across it."""

_SPEC_AMPS = (2.1e-9, 65e-9, 2.1e-6, 21e-6)
"""Noise of each range that section 4.10 states."""

_LOWEST = 0.1
"""Lowest frequency of the analysis, Hz."""

_HIGHEST = 100e6
"""Highest frequency of the analysis, Hz."""

_SAMPLE_RATE = 100e3
"""Sample rate of the instrument."""

_CONVERTER_SNR_DB = 88.7
"""Signal-to-noise ratio of the converter with a reference of 2.5 V (ADS8860, figure 14)."""

_TRANSITION_CODES = 0.5
"""Transition noise that the datasheet states with a reference of 5 V, in codes (page 6)."""

_TEST_LIMIT = 5e-9
"""Limit of the noise test in range 0 from a quiet supply (section 4.10)."""

_GROUPS = (
    ("shunt", ("r101", "r104", "r107", "r110", "rr107", "rr110")),
    ("multiplexer channels", ("r.xu24.",)),
    ("amplifier U27 and R123", ("r.xu27.", "r123")),
    ("pedestal: U26, R121, R122", ("r.xu26.", "r121", "r122")),
    ("filter and driver: R125, R128, R130, U29", ("r125", "r128", "r130", "r.xu29.")),
)
"""Noise sources by what they belong to, as the start of their names."""


def _held(ctx: Context, index: int) -> PartModel:
    """The multiplexer with the channels of one range as resistors that make noise."""
    base = ctx.models.model_of(ctx.netlist.component("U24"))
    return PartModel(
        kind="subckt",
        name="SIGNAL_CHAIN_MUX509_HELD",
        ports=base.ports,
        library="signal_chain.lib",
        origin="written here",
        params=f"sel={index + 1}",
    )


def _deck(ctx: Context, index: int, *, with_c71: bool = False) -> str:
    refs = [*frontend.chain_refs(ctx.netlist), *common.MUX_PARTS, _SHUNT_PARTS[index]]
    if with_c71:
        refs.append("C71")
    aliases = {**common.ALIASES, "Net-(Q13-S)": "sense_r2", "Net-(Q14-S-Pad1)": "sense_r3"}
    circuit = ctx.circuit(refs, aliases, {"U24": _held(ctx, index)})
    node = _SHUNT_NODES[index]
    amps = _BIAS_AMPS[index]
    lines = ["* the taps of the ranges that are not measured rest on the node after the shunts"]
    if with_c71:
        lines += [
            "* a quiet supply on the supply node; the load draws from the node after the",
            "* shunts, which has its 100 nF",
            "Vsupply supply 0 3.35",
            f"Isig vout_s 0 dc {amps:g} ac 1",
        ]
    else:
        lines += [
            "* the node after the shunts is held; the test current flows through the shunt",
            "Vvout vout_s 0 3.3",
            f"Isig vout_s {node} dc {amps:g} ac 1",
        ]
    if index != 0:
        lines.append("Vsh0 supply vout_s 0")
    if index != 1:
        lines.append("Vsh1 sense_r1 vout_s 0")
    if index != 2:
        lines += ["Vsh2 s3a s3b 0", "Vk2 s3b vout_s 0"]
    if index != 3:
        lines += ["Vsh3 s4a s4b 0", "Vk3 s4b vout_s 0"]
    return ctx.deck(
        f"Signal chain: noise at the converter input, range {index}"
        + (", 100 nF on the node after the shunts" if with_c71 else ""),
        circuit,
        frontend.rails(),
        "\n".join(lines),
        control=[f"noise v(adc_in) Isig dec 40 {_LOWEST:g} {_HIGHEST:g} 1"],
    )


def _mean_of(frequency: common.Vector, density: common.Vector, samples: int) -> float:
    """RMS noise of the mean of consecutive samples, from the density at the converter.

    The mean of N samples taken at the sample rate weighs the spectrum with
    the square of sin(pi f N / fs) / (N sin(pi f / fs)), which repeats at
    every multiple of the sample rate: that is the noise folded down by the
    sampling. Near the multiples the weight is evaluated as it is, between
    them its mean over a lobe is taken.
    """
    lobe = _SAMPLE_RATE / samples
    grids = [np.geomspace(_LOWEST, 5e6, 6000)]
    for multiple in range(51):
        centre = multiple * _SAMPLE_RATE
        fine = centre + np.linspace(-20.0 * lobe, 20.0 * lobe, 4001)
        grids.append(fine[(fine >= _LOWEST) & (fine <= 5e6)])
    grid = np.unique(np.concatenate(grids))
    power = np.interp(np.log10(grid), np.log10(frequency), density) ** 2
    phase = np.pi * grid / _SAMPLE_RATE
    sine = np.sin(phase)
    distance = np.abs(grid - np.round(grid / _SAMPLE_RATE) * _SAMPLE_RATE)
    near_multiple = distance < 20.0 * lobe
    safe = np.where(np.abs(sine) < 1e-12, 1e-12, sine)
    exact = (np.sin(samples * phase) / (samples * safe)) ** 2
    exact = np.where(np.abs(sine) < 1e-9, 1.0, exact)
    average = 0.5 / (samples * safe) ** 2
    weight = np.where(near_multiple, exact, average)
    return float(np.sqrt(measure.integral(grid, power * weight, float(grid[0]), float(grid[-1]))))


def _shares(result: RunResult) -> dict[str, float]:
    """RMS noise at the converter input of each group of sources, in volts."""
    found: dict[str, float] = {name: 0.0 for name, _ in _GROUPS}
    found["other"] = 0.0
    for key, value in result.vectors.items():
        plot, _, name = key.partition("/")
        if not name.startswith("onoise_total_") or "_thermal" in name or "_1overf" in name:
            continue
        device = name[len("onoise_total_") :]
        squared = float(np.real(value)[0]) ** 2
        for group, starts in _GROUPS:
            if device.startswith(starts):
                found[group] += squared
                break
        else:
            found["other"] += squared
        del plot
    return {name: float(np.sqrt(value)) for name, value in found.items()}


@bench(
    "signal_chain",
    "noise",
    "Noise of the chain at the converter input, by range",
    "section 4.10 (noise budget), requirement R-04, section 4.5 (anti-alias filter)",
)
def noise(ctx: Context) -> Outcome:
    """A noise analysis from 0.1 Hz to 100 MHz with each range held.

    The shunt of the range is in the circuit as the resistor of the
    netlist, the two closed channels of the multiplexer as 250 ohm
    resistors, and the amplifiers carry the voltage and current noise of
    their datasheets with the 1/f part. A test current through the shunt
    gives the gain. The noise of one sample is the density at the converter
    input integrated over the whole analysis, because sampling folds every
    frequency down; divided by the gain and by the shunt it is the noise of
    the reading. The noise of the converter itself is not simulated: it is
    added from its datasheet. Range 0 is run a second time as the board has
    it, with the 100 nF of C71 on the node after the shunts and a quiet
    supply.
    """
    runs = {index: ctx.run(f"r{index}", _deck(ctx, index), keep=index == 0) for index in range(4)}
    loaded = ctx.run("r0-c71", _deck(ctx, 0, with_c71=True))
    converter = common.VREF / (2.0 * np.sqrt(2.0)) / 10.0 ** (_CONVERTER_SNR_DB / 20.0)
    optimistic = _TRANSITION_CODES * common.LSB
    figures: list[Figure] = []
    traces: list[Trace] = []
    totals: dict[int, float] = {}
    for index, run in runs.items():
        frequency = run.real("frequency")
        density = run.real("onoise_spectrum")
        total = measure.integrated_noise(frequency, density, _LOWEST, _HIGHEST)
        totals[index] = total
        ohms = frontend.SHUNT_OHMS[index]
        with_converter = float(np.hypot(total, converter))
        figures.append(
            Figure(
                f"chain_r{index}",
                f"R{index}: noise of one sample at the shunt, chain alone",
                total / common.GAIN,
                "V",
            )
        )
        figures.append(
            Figure(
                f"reading_r{index}",
                f"R{index}: noise of one sample with the converter, as a current",
                with_converter / common.GAIN / ohms,
                "A",
                expected=_SPEC_AMPS[index],
                high=_TEST_LIMIT if index == 0 else None,
                source="section 4.10: about 2.1 nA, limit of the test 5 nA"
                if index == 0
                else "section 4.10",
            )
        )
        traces.append(Trace(frequency, density / common.GAIN * 1e9, f"range {index}", 0))
    base = runs[0]
    frequency = base.real("frequency")
    density = base.real("onoise_spectrum")
    total = totals[0]
    shares = _shares(base)
    for position, (group, value) in enumerate(shares.items()):
        figures.append(
            Figure(
                f"share_{position}",
                f"R0: part of the noise at the shunt that comes from {group}",
                value / common.GAIN,
                "V",
            )
        )
    listed = float(np.sqrt(sum(value * value for value in shares.values())))
    figures += [
        Figure(
            "shares_add_up",
            "R0: the parts above together, over the integrated density",
            listed / total,
            "",
            low=0.97,
            high=1.03,
            source="check of this bench: the parts are those of the same analysis",
        ),
        Figure(
            "converter",
            "Noise of the converter at its input with a reference of 2.5 V, from its datasheet",
            converter,
            "V",
        ),
        Figure(
            "converter_at_shunt",
            "The same referred to the shunt",
            converter / common.GAIN,
            "V",
            expected=1.0e-6,
            source="section 4.10 estimates about 1.0 uV",
        ),
        Figure(
            "reading_r0_optimistic",
            "R0: noise of one sample if the converter had 0.5 code of noise at 2.5 V",
            float(np.hypot(total, optimistic)) / common.GAIN / frontend.SHUNT_OHMS[0],
            "A",
            expected=_SPEC_AMPS[0],
            source="section 4.10: about 2.1 nA",
        ),
        Figure(
            "density_1khz",
            "R0: density at the shunt at 1 kHz",
            float(np.interp(3.0, np.log10(frequency), density)) / common.GAIN,
            "V/√Hz",
        ),
        Figure(
            "density_1hz",
            "R0: density at the shunt at 1 Hz",
            float(np.interp(0.0, np.log10(frequency), density)) / common.GAIN,
            "V/√Hz",
        ),
        Figure(
            "below_10hz",
            "R0: noise at the shunt from 0.1 Hz to 10 Hz",
            measure.integrated_noise(frequency, density, _LOWEST, 10.0) / common.GAIN,
            "V",
        ),
        Figure(
            "above_nyquist",
            "R0: part of the chain noise that lies above half the sample rate",
            measure.integrated_noise(frequency, density, _SAMPLE_RATE / 2, _HIGHEST) / total,
            "",
        ),
    ]
    for samples, label in ((100, "100 samples (1 ms)"), (100000, "100000 samples (1 s)")):
        mean = float(np.hypot(_mean_of(frequency, density, samples), converter / np.sqrt(samples)))
        figures.append(
            Figure(
                f"mean_{samples}",
                f"R0: noise of the mean of {label}, with the converter",
                mean / common.GAIN / frontend.SHUNT_OHMS[0],
                "A",
                high=_TEST_LIMIT if samples == 100 else None,
                source="section 4.10: 5 nA for the mean of 100 samples" if samples == 100 else "",
            )
        )
    loaded_frequency = loaded.real("frequency")
    loaded_density = loaded.real("onoise_spectrum")
    loaded_total = measure.integrated_noise(loaded_frequency, loaded_density, _LOWEST, _HIGHEST)
    figures += [
        Figure(
            "chain_r0_c71",
            "R0 with C71 and a quiet supply: noise of one sample at the shunt, chain alone",
            loaded_total / common.GAIN,
            "V",
        ),
        Figure(
            "reading_r0_c71",
            "R0 with C71 and a quiet supply: noise of one sample with the converter",
            float(np.hypot(loaded_total, converter)) / common.GAIN / frontend.SHUNT_OHMS[0],
            "A",
            expected=_SPEC_AMPS[0],
            high=_TEST_LIMIT,
            source="section 4.10: about 2.1 nA, limit of the test 5 nA",
        ),
    ]
    traces.append(
        Trace(loaded_frequency, loaded_density / common.GAIN * 1e9, "range 0 with C71", 0, "--")
    )
    running = np.sqrt(
        np.concatenate(
            ([0.0], np.cumsum(0.5 * (density[1:] ** 2 + density[:-1] ** 2) * np.diff(frequency)))
        )
    )
    traces.append(Trace(frequency, running / common.GAIN * 1e6, "range 0, chain alone", 1))
    graph = Graph(
        name="density",
        title="Noise of the chain referred to the shunt",
        xlabel="Frequency (Hz)",
        panels=(
            Panel("Density at the shunt (nV/√Hz)", log=True),
            Panel("Noise from 0.1 Hz up to the frequency (uV RMS)"),
        ),
        traces=tuple(traces),
        logx=True,
        xmarks=((_SAMPLE_RATE / 2, "half the sample rate"),),
    )
    notes = (
        "Every noise source is typical: 3 nV/rtHz and 60 nV/rtHz of the two stages of U27 "
        "with 200 fA/rtHz at each input, the densities of the other amplifiers, the thermal "
        "noise of every resistor. The reference, the rails and the supply are ideal and "
        "quiet: what a switching converter adds behind the filter is not in these figures.",
        "The multiplexer channels are 250 ohm resistors here (a variant of the multiplexer "
        "model written for this bench); the datasheet states no noise for them.",
        "The converter is not simulated. Its noise comes from its datasheet at a reference "
        "of 2.5 V: 88.7 dB of signal-to-noise ratio (figure 14), which is 32 uV RMS or 0.85 "
        "code. The 0.5 code of its table holds for a reference of 5 V.",
        "The analysis starts at 0.1 Hz. A mean over 1 s also takes in what lies below "
        "that, where the 1/f noise keeps rising; drift is not noise in this sense.",
        "Without C71 the node after the shunts is held by an ideal source, so the whole "
        "thermal noise of the shunt is read. With C71 that noise is shunted above 1.6 kHz.",
    )
    return Outcome(tuple(figures), (graph,), notes)
