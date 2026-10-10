"""The MCP4921 model of the source meter against the figures of its datasheet."""

from __future__ import annotations

from benches.source_meter import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench, near
from circuit_sim.circuit import Circuit

_REF = common.DAC

_DOCUMENT = "Microchip DS22248A"
"""The datasheet the figures are taken from."""

_VDD = 5.0
_VREF = 2.048
"""Supply and reference of the electrical characteristics (page 3)."""

_LOAD = "Rl vout 0 5k\nCl vout 0 100p"
"""Load of the electrical characteristics: 5 kohm and 100 pF (page 3)."""

_STEP_AT = 2e-6
"""Instant of the code change in the settling run."""


def _part(ctx: Context, **params: float | str) -> Circuit:
    """The DAC alone, its supply, reference and output on short node names."""
    found = ctx.netlist.component(_REF)
    aliases = {found.net_of("1"): "vdd", found.net_of("6"): "vref", found.net_of("8"): "vout"}
    return ctx.circuit([_REF], aliases, {_REF: common.part(ctx, _REF, **params)})


def _supply(vdd: float = _VDD, vref: float = _VREF) -> str:
    return f"* supply and reference as ideal sources\nVdd vdd 0 {vdd:g}\nVref vref 0 {vref:g}\n"


def _static_deck(ctx: Context, title: str, load: str = _LOAD, **params: float | str) -> str:
    return ctx.deck(f"MCP4921: {title}", _part(ctx, **params), _supply(), load, control=["op"])


@bench(
    "models",
    "source-meter-mcp4921",
    "MCP4921 model of the source meter against its datasheet",
    "the model of the set-point DAC U15",
)
def mcp4921(ctx: Context) -> Outcome:
    """The DAC U15 of the schematic is put in the test conditions of its datasheet.

    With 5 V of supply, a reference of 2.048 V, gain 2 and a load of 5 kohm
    with 100 pF, operating points give the transfer at four codes and at
    gain 1, the short-circuit current, the output after power-on and the
    current of the buffered reference input. One transient run steps the
    code from one quarter to three quarters of the range and gives the
    slew rate and the settling time.
    """
    decks = {
        "zero": _static_deck(ctx, "code 0", code=0),
        "one": _static_deck(ctx, "code 1", code=100),
        "two": _static_deck(ctx, "code 2", code=101),
        "mid": _static_deck(ctx, "mid-scale", code=2048),
        "full": _static_deck(ctx, "full scale", code=4095),
        "gain1": _static_deck(ctx, "gain 1", code=4095, gain=1),
        "short": _static_deck(ctx, "output shorted", load="Rl vout 0 1m", code=4095),
        "off": _static_deck(ctx, "after power-on", load="Itest 0 vout 1u", code=-1),
        "error": _static_deck(
            ctx, "gain, offset and bow as parameters", code=2048, gerr=-0.001, offs=0.8e-3, inl=2
        ),
    }
    runs = ctx.run_many(decks)
    out = {name: common.last(run, "vout") for name, run in runs.items()}
    step = 2.0 * _VREF / 4096.0
    reference_amps = abs(common.last(runs["mid"], "vref#branch"))
    figures = [
        Figure(
            "zero",
            "Output at code 0: the lower end of the swing",
            out["zero"],
            "V",
            expected=0.01,
            low=0.0,
            high=0.011,
            source=f"{_DOCUMENT}, page 4: output swing from 0.01 V",
        ),
        near(
            "step",
            "Step from code 100 to code 101",
            out["two"] - out["one"],
            "V",
            step,
            0.001,
            f"{_DOCUMENT}, page 19: VREF x G / 4096",
        ),
        near(
            "mid",
            "Output at code 2048, gain 2",
            out["mid"],
            "V",
            _VREF,
            0.0005,
            f"{_DOCUMENT}, page 19",
        ),
        near(
            "full",
            "Output at code 4095, gain 2",
            out["full"],
            "V",
            2.0 * _VREF * 4095.0 / 4096.0,
            0.0005,
            f"{_DOCUMENT}, page 19",
        ),
        near(
            "gain1",
            "Output at code 4095, gain 1",
            out["gain1"],
            "V",
            _VREF * 4095.0 / 4096.0,
            0.0005,
            f"{_DOCUMENT}, pages 19 and 24: the frame bit GA",
        ),
        Figure(
            "short_circuit",
            "Current into a short circuit at code 4095",
            out["short"] / 1e-3,
            "A",
            expected=15e-3,
            low=13e-3,
            high=24e-3,
            source=f"{_DOCUMENT}, page 4: 15 mA typical, 24 mA at the most",
        ),
        near(
            "off_resistance",
            "Resistance of the output after power-on",
            out["off"] / 1e-6,
            "ohm",
            500e3,
            0.02,
            f"{_DOCUMENT}, page 20: 500 kohm, typical",
        ),
        Figure(
            "reference_current",
            "Current of the buffered reference input",
            reference_amps,
            "A",
            high=1e-9,
            source=f"{_DOCUMENT}, page 20: a very high input impedance, no figure",
        ),
        near(
            "error_terms",
            "Mid-scale with -0.1 % of gain, 0.8 mV of offset and a bow of 2 steps",
            out["error"] - out["mid"],
            "V",
            -0.001 * _VREF + 0.8e-3 + 2.0 * step,
            0.01,
            f"{_DOCUMENT}, pages 3 and 4: the typical errors, as parameters of the model",
        ),
    ]

    settle = ctx.deck(
        "MCP4921: one quarter to three quarters of the range",
        _part(ctx, code=1024, code1=3072, t1=_STEP_AT),
        _supply(),
        _LOAD,
        control=["tran 5n 12u 0 5n"],
    )
    run = ctx.run("settling", settle)
    time, wave = run.real("time"), run.real("vout")
    start, final = float(wave[0]), float(wave[-1])
    figures += [
        near(
            "slew_rate",
            "Slew rate, 20 % to 80 % of the step",
            0.6
            * (final - start)
            / measure.rise_time(
                time, wave, start + 0.2 * (final - start), start + 0.8 * (final - start)
            ),
            "V/s",
            0.55e6,
            0.10,
            f"{_DOCUMENT}, page 4: 0.55 V/us",
        ),
        near(
            "settling",
            "Settling to half a step, one quarter to three quarters of the range",
            measure.settling_time(time, wave, final, step / 2.0, _STEP_AT),
            "s",
            4.5e-6,
            0.20,
            f"{_DOCUMENT}, page 4: 4.5 us",
        ),
    ]
    graph = Graph(
        name="settling",
        title="MCP4921 model: code 1024 to code 3072, 5 kohm and 100 pF",
        xlabel="Time (us)",
        panels=(Panel("Output (V)"),),
        traces=(Trace(time * 1e6, wave, "output", 0),),
        xmarks=((_STEP_AT * 1e6, "new code"),),
    )
    notes = (
        "The serial interface is not modelled: the code is a parameter of the model, "
        "and a code change is a step without the glitch of the real part.",
        "The limits are the fit this project asks of the model. The bandwidth of the "
        "output amplifier is fitted to the settling time, so that figure is not an "
        "independent check.",
        "The datasheet states no output resistance and no noise; the model has 1 ohm "
        "(assumption) and no noise.",
    )
    return Outcome(tuple(figures), (graph,), notes)
