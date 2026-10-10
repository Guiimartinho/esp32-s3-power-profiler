"""The Schottky clamps of the two analog rails while one of them is absent."""

from __future__ import annotations

from benches.analog_rails import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench
from circuit_sim.circuit import PartModel
from circuit_sim.engine import RunResult

_REFS = ("D8", "D9", "R69")
"""The two clamp diodes and the minimum load of the source regulator on -4V_A."""

_HIGH_DROP = PartModel(
    kind="device",
    name="B0530W_HI",
    ports=("2", "1"),
    letter="D",
    library=common.LIBRARY,
    origin="written here",
)
"""The diode at the largest forward voltage of its datasheet."""

_LOADS = {"typical": 5.06e-3, "largest": 6.3e-3}
"""Current of the amplifiers between the rails: typical supply currents, and
their datasheet limits (AD8421 2.3 mA, three OPA197 at 1.3 mA, the multiplexer)."""

_RATING = 0.3
"""How far the output pin of either regulator may be taken across ground (datasheets)."""

_END = 30e-3
"""Length of a run."""


def _deck(ctx: Context, missing: str, diode: str, load: float, celsius: float) -> str:
    refs = (*_REFS, *common.capacitors_on(ctx.netlist, ("+12V_A", "-4V_A")))
    overrides = {"D8": _HIGH_DROP, "D9": _HIGH_DROP} if diode == "largest" else None
    circuit = ctx.circuit(refs, common.ALIASES, overrides)
    present = "Vp12 p12v_a 0 PWL(0 0 2m 12)" if missing == "m4" else "Vm4 m4v_a 0 PWL(0 0 2m -4)"
    stimulus = "\n".join(
        [
            "* one rail is present, the other one has no converter; the amplifiers",
            "* between the two rails draw their supply current through both",
            present,
            f"Bamp p12v_a m4v_a I = {load:g}*tanh(max(v(p12v_a,m4v_a), 0)/3)",
            "Vldo ldo_out 0 0",
            "Rp12 p12v_a 0 100meg",
            "Rm4 m4v_a 0 100meg",
        ]
    )
    return ctx.deck(
        f"Clamp of the absent rail: {missing} absent, {diode} diode, {load * 1e3:g} mA",
        circuit,
        stimulus,
        control=["save p12v_a m4v_a @dd8[id] @dd9[id]", f"tran 20u {_END:g}"],
        options=(f"temp={celsius:g}",),
    )


def _held(run: RunResult, node: str) -> float:
    time = run.real("time")
    return measure.mean(time, run.real(node), _END - 2e-3, _END)


@bench(
    "analog_rails",
    "clamps",
    "Clamp diodes D8 and D9: one analog rail present, the other one absent",
    "section 3 (Schottky clamps), decision D-52",
)
def clamps(ctx: Context) -> Outcome:
    """One of the two analog rails is brought up while the other has no converter.

    The amplifiers that sit between +12V_A and -4V_A draw their supply
    current through both rails, so the rail without a converter is pulled
    across ground until its clamp diode conducts. The bench holds that state
    and reads the voltage of the absent rail: with the typical diode and the
    typical supply currents, with the diode at the largest forward voltage
    of its datasheet and the largest supply currents, and with that diode in
    the cold.
    """
    cases = {
        "typ": ("typical", "typical", 27.0),
        "max": ("largest", "largest", 27.0),
        "cold": ("largest", "largest", -40.0),
    }
    labels = {
        "typ": "typical diode, typical load",
        "max": "largest forward voltage, largest load",
        "cold": "largest forward voltage, largest load, -40 C",
    }
    figures: list[Figure] = []
    traces: list[Trace] = []
    for case, (diode, load, celsius) in cases.items():
        low = ctx.run(f"m4-absent-{case}", _deck(ctx, "m4", diode, _LOADS[load], celsius))
        high = ctx.run(f"p12-absent-{case}", _deck(ctx, "p12", diode, _LOADS[load], celsius))
        typical = case == "typ"
        figures += [
            Figure(
                f"m4_{case}",
                f"-4V_A with its converter absent ({labels[case]})",
                _held(low, "m4v_a"),
                "V",
                expected=0.24 if typical else None,
                high=0.24 if typical else _RATING,
                source="section 3 and D-52: below +0.24 V"
                if typical
                else "datasheet of the charge pump: its output at most 0.3 V above ground",
            ),
            Figure(
                f"p12_{case}",
                f"+12V_A with its converter absent ({labels[case]})",
                _held(high, "p12v_a"),
                "V",
                expected=-0.23 if typical else None,
                low=-0.23 if typical else -_RATING,
                source="section 3 and D-52: above -0.23 V"
                if typical
                else "datasheet of the +12V_A regulator: its output at most 0.3 V below ground",
            ),
            Figure(
                f"current_{case}",
                f"Current through D8 in that state ({labels[case]})",
                _held(low, "@dd8[id]"),
                "A",
            ),
        ]
        time = low.real("time") * 1e3
        traces += [
            Trace(time, low.real("m4v_a") * 1e3, f"-4V_A, {labels[case]}", 0),
            Trace(high.real("time") * 1e3, high.real("p12v_a") * 1e3, f"+12V_A, {labels[case]}", 1),
        ]
    graph = Graph(
        name="clamp",
        title="The absent rail while the other one comes up in 2 ms",
        xlabel="Time (ms)",
        panels=(
            Panel(
                "-4V_A, converter absent (mV)",
                marks=((240.0, "0.24 V of the specification"), (300.0, "0.3 V rating")),
            ),
            Panel(
                "+12V_A, converter absent (mV)",
                marks=((-230.0, "-0.23 V of the specification"), (-300.0, "-0.3 V rating")),
            ),
        ),
        traces=tuple(traces),
    )
    notes = (
        "The load is one current sink between the two rails for the supply currents of "
        "the amplifiers; it fades out below 3 V between the rails. The minimum load R69 "
        "of the source regulator hangs on -4V_A from a regulator output held at 0 V.",
        "The 0.24 V and 0.23 V of the specification are met by the typical diode, whose "
        "forward voltage is an assumption 40 mV below the datasheet maximum. With the "
        "diode at that maximum the rail stands closer to the 0.3 V that the datasheets of "
        "the two regulators allow at their output pins.",
        "The cold run uses the temperature law of the diode equation with the barrier "
        "height usual for a Schottky diode; the datasheet of the diode gives no forward "
        "voltage in the cold, so that figure is a trend and not a datasheet value.",
    )
    return Outcome(tuple(figures), (graph,), notes)
