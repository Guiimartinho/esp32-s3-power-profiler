"""A load profile through the whole path, with the ranges changing by themselves."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from benches import frontend
from benches.range_logic import common as range_logic
from benches.system import common
from circuit_sim import measure
from circuit_sim.bench import Context, Figure, Graph, Outcome, Panel, Trace, bench

_PROFILE = (
    (0.0, 3e-6),
    (1.000e-3, 3e-6),
    (1.020e-3, 8e-3),
    (2.500e-3, 8e-3),
    (2.505e-3, 180e-3),
    (3.100e-3, 180e-3),
    (3.105e-3, 8e-3),
    (4.000e-3, 8e-3),
    (4.010e-3, 3e-6),
    (12.0e-3, 3e-6),
)
"""Load current against time: sleep, wake, a radio burst, sleep again."""

_CDUT = 1e-6
"""Capacitance beside the load: the 1 uF of requirement R-07."""

_SOURCE_OHMS = 0.05
"""Output resistance assumed for the source in front of the ladder."""

_DOWN_AFTER = 1e-3
"""Time below the switch-down level after which firmware asks for a step down.

The specification asks for 100 consecutive samples, 1 ms at 100 kSPS, and
counts again after every change of the range.
"""

_BURST_ENDS = 3.105e-3
"""Instant at which the load is back below the switch-down level of range 3."""

_REQUESTS = tuple(_BURST_ENDS + _DOWN_AFTER * (step + 1) for step in range(3))
"""Instants of the three requests to step down that the rule gives for this profile."""


def _firmware() -> str:
    """The requests to step down, at the instants the firmware rule gives.

    The rule is firmware and no firmware runs here: the requests are written
    into the deck as pulses, one for each step from range 3 to range 0.
    """
    points = ["0 0"]
    for instant in _REQUESTS:
        points += [
            f"{instant:.7g} 0",
            f"{instant + 1e-8:.7g} {frontend.LOGIC_VOLTS:g}",
            f"{instant + 1e-6:.7g} {frontend.LOGIC_VOLTS:g}",
            f"{instant + 1.01e-6:.7g} 0",
        ]
    return "\n".join(
        [
            "* requests to step down, 1 ms after the load fell below the level of",
            "* range 3 and 1 ms after each step, as the firmware rule would make them",
            f"Vdown seq_down 0 PWL({' '.join(points)})",
        ]
    )


def _deck(ctx: Context) -> str:
    points = " ".join(f"{time:g} {current:g}" for time, current in _PROFILE)
    stimulus = "\n".join(
        [
            "* the source meter as an ideal 5 V source with a small resistance; the",
            "* load as a current sink with a capacitor beside it",
            "Vsource source 0 5",
            f"Rsource source supply {_SOURCE_OHMS:g}",
            f"Iload vout_s 0 PWL({points})",
            f"Cdut vout_s 0 {_CDUT:g}",
            "Venable seq_enable 0 3.3",
            "Vouton seq_out_on 0 3.3",
        ]
    )
    saved = (
        "adc_in amp_raw ped inp inn supply vout_s mux_a0 mux_a1 gate_r1 gate_r2 gate_r3 "
        "cmp_up cmp_jump cmp_oc seq_down @r101[i] @r104[i] @r107[i] @r110[i] @mq10[id] @mq11[id]"
    )
    circuit = common.front_end(ctx)
    return ctx.deck(
        "Whole measuring path with the sequencer: sleep, wake, burst, sleep",
        circuit,
        frontend.rails(),
        frontend.sequencer(),
        # The loop through the comparators and the sequencer has several
        # stable states; without this the run can start in range 3.
        range_logic.rest(circuit, 0, output_on=False),
        _firmware(),
        stimulus,
        control=[f"save {saved}", f"tran 1u {_PROFILE[-1][0]:g}"],
        libraries=frontend.SEQUENCER_LIBRARIES,
        # A switch of a few milliohms that carries microamperes cannot meet
        # the current tolerance of 1 pA that the solver asks of a device by
        # default: the noise of the node voltages times its conductance is
        # larger. 1 nA is half a code of range 0.
        options=("abstol=1e-9",),
    )


def _samples(
    time: NDArray[np.float64],
    adc: NDArray[np.float64],
    a0: NDArray[np.float64],
    a1: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.int64], NDArray[np.float64], NDArray[np.bool_]]:
    """What the host gets at 100 kSPS: instants, ranges, readings and the valid flag."""
    instants = np.arange(0.0, time[-1], common.SAMPLE_PERIOD)
    half = frontend.LOGIC_VOLTS / 2.0
    index = (np.interp(instants, time, a0) > half).astype(np.int64) + 2 * (
        np.interp(instants, time, a1) > half
    ).astype(np.int64)
    code = common.codes(np.interp(instants, time, adc))
    valid = np.ones(instants.size, dtype=np.bool_)
    left = 0
    for position in range(1, instants.size):
        if index[position] != index[position - 1]:
            left = common.FLAGGED_SAMPLES
        if left:
            valid[position] = False
            left -= 1
    valid &= code < common.CODES - 1
    current = common.reading(code, index)
    # A flagged sample takes the first valid one after it (section 9).
    for position in range(instants.size - 2, -1, -1):
        if not valid[position]:
            current[position] = current[position + 1]
    return instants, index, current, valid


@bench(
    "system",
    "profile",
    "A load profile with automatic ranging: sleep, wake, burst, sleep",
    "sections 4.3 to 4.5, rules F-16, F-17 and F-35, requirement R-07, section 9 (flagged samples)",
)
def profile(ctx: Context) -> Outcome:
    """The whole measuring path follows a load that sleeps, wakes and transmits.

    Ladder, multiplexer, amplifier chain and comparators are the circuit as
    drawn; the sequencer is the model of the rules, and the requests to step
    down are written in at the instants the firmware rule gives. The load draws 3 uA, wakes
    to 8 mA, takes 180 mA for 0.6 ms and sleeps again, with 1 uF beside it.
    The converter input is sampled at 100 kSPS and turned into a current with
    the nominal calibration, with the samples after a range change flagged
    as the specification says. The reading is compared with the load current
    and with the current that really flowed through the shunts, which differ
    while the capacitor at the load changes its voltage.
    """
    result = ctx.run("sleep-wake", _deck(ctx))
    time = result.real("time")
    adc = result.real("adc_in")
    shunt = (
        result.real("@r101[i]")
        + result.real("@r104[i]")
        + result.real("@r107[i]")
        + result.real("@r110[i]")
        + result.real("@mq10[id]")
        + result.real("@mq11[id]")
    )
    instants, index, current, valid = _samples(
        time, adc, result.real("mux_a0"), result.real("mux_a1")
    )
    profile_time = np.array([point[0] for point in _PROFILE])
    profile_amps = np.array([point[1] for point in _PROFILE])
    load = np.interp(instants, profile_time, profile_amps)
    through = np.interp(instants, time, shunt)
    end = float(instants[-1])
    charge_load = measure.integral(profile_time, profile_amps, 0.0, end)
    charge_shunt = measure.integral(time, shunt, 0.0, end)
    charge_read = float(np.sum(current[:-1]) * common.SAMPLE_PERIOD)
    difference = np.abs(current - through)
    relative = difference[valid] / np.maximum(
        np.abs(through[valid]), np.asarray(common.LSB_AMPS)[index[valid]]
    )
    of_range = difference[valid] / np.asarray(frontend.FULL_SCALE_AMPS)[index[valid]]
    changes = int(np.count_nonzero(np.diff(index)))
    lowest = measure.extremes(time, result.real("vout_s"), 0.9e-3, 4.0e-3)[0]
    final = float(np.mean(current[-50:]))
    figures = (
        Figure(
            "charge_against_shunt",
            "Charge read over the profile against the charge through the shunts",
            100.0 * (charge_read - charge_shunt) / charge_shunt,
            "%",
            low=-1.0,
            high=1.0,
            source="limit of this bench: the reading follows the shunt current within 1 %",
        ),
        Figure(
            "charge_against_load",
            "Charge read over the profile against the charge the load drew",
            100.0 * (charge_read - charge_load) / charge_load,
            "%",
            low=-1.0,
            high=1.0,
            source="limit of this bench: 1 %",
        ),
        Figure(
            "worst_valid_sample",
            "Largest deviation of a valid sample from the shunt current, of its range",
            100.0 * float(np.max(of_range)),
            "%",
        ),
        Figure(
            "median_valid_sample",
            "Median deviation of the valid samples from the shunt current",
            100.0 * float(np.median(relative)),
            "%",
            high=0.5,
            source="limit of this bench: 0.5 %",
        ),
        Figure(
            "start_range",
            "Range in which the run starts, at 3 uA",
            float(index[0]),
            "",
            expected=0.0,
            low=0.0,
            high=0.0,
            source="the run has to start at rest in range 0",
        ),
        Figure("range_changes", "Range changes over the profile", float(changes), ""),
        Figure(
            "flagged_share",
            "Samples flagged invalid",
            100.0 * float(np.count_nonzero(~valid)) / valid.size,
            "%",
        ),
        Figure(
            "wake_ladder_peak",
            "Highest ladder voltage at the wake edge",
            measure.extremes(time, result.real("supply") - result.real("vout_s"), 1.0e-3, 1.1e-3)[
                1
            ],
            "V",
            high=0.151,
            source="section 4.4: below the jump level of 151 mV, so the steps are single",
        ),
        Figure(
            "lowest_output",
            "Lowest voltage at the load during wake and burst (set to 5 V)",
            lowest,
            "V",
            low=4.5,
            source="requirement R-07: a drop of 0.5 V at the most",
        ),
        Figure(
            "sleep_reading",
            "Reading at the end, back in sleep at 3 uA",
            final,
            "A",
            expected=3e-6,
            low=2.9e-6,
            high=3.1e-6,
            source="the load current of the profile",
        ),
    )
    milli = instants * 1e3
    floor = 1e-7
    whole = Graph(
        name="profile",
        title="Sleep, wake, burst, sleep: load, shunt current and reading",
        xlabel="Time (ms)",
        panels=(
            Panel("Current (A)", log=True),
            Panel("Range"),
            Panel("Voltage at the load (V)"),
        ),
        traces=(
            Trace(milli, np.maximum(load, floor), "load", 0, "--"),
            Trace(milli, np.maximum(through, floor), "through the shunts", 0, ":"),
            Trace(milli, np.maximum(current, floor), "reading at 100 kSPS", 0),
            Trace(milli, index.astype(float), "range of each sample", 1),
            Trace(time * 1e3, result.real("vout_s"), "", 2),
        ),
    )
    zoom = (time >= 0.98e-3) & (time <= 1.10e-3)
    micro = (time[zoom] - 1.0e-3) * 1e6
    wake = Graph(
        name="wake",
        title="The wake edge, 3 uA to 8 mA in 20 us with 1 uF at the load: two steps up",
        xlabel="Time after the start of the edge (us)",
        panels=(
            Panel("Ladder voltage (V)", marks=((0.151, "jump 151 mV"),)),
            Panel("Comparators and gates (V)"),
            Panel("Converter input (V)", marks=((2.5, "full scale"),)),
        ),
        traces=(
            Trace(micro, (result.real("supply") - result.real("vout_s"))[zoom], "", 0),
            Trace(micro, result.real("cmp_up")[zoom], "CMP_UP", 1),
            Trace(micro, result.real("cmp_jump")[zoom], "CMP_JUMP", 1),
            Trace(micro, result.real("gate_r1")[zoom], "GATE_R1", 1, "--"),
            Trace(micro, result.real("gate_r2")[zoom], "GATE_R2", 1, "--"),
            Trace(micro, adc[zoom], "", 2),
        ),
    )
    notes = (
        "The sequencer is the model of rules F-16 to F-18 with a reaction time of "
        "100 ns. The requests to step down are written into the deck at the "
        "instants the firmware rule gives for this profile: 1 ms after the load "
        "fell below the level of range 3 and 1 ms after each step. The latency "
        "of the sample blocks, up to 2.56 ms per step, is not in it.",
        "The source in front of the ladder is an ideal 5 V source with 50 mohm, "
        "an assumption; the output switch is not in this circuit.",
        "The reading follows the current through the shunts. That current is "
        "the load current plus what charges the capacitor at the load, so after "
        "a step down the reading approaches the load current with the time "
        "constant of shunt and capacitor: 1.1 ms in range 0 with 1 uF.",
        "At the wake edge the capacitor at the load supplies the current first, "
        "so the ladder voltage rises slowly enough for the step-up comparator: "
        "range 0 to range 1 at 91 mV, range 2 after the blanking time, and the "
        "jump level is not reached. At the burst, in range 2, the jump takes "
        "the path to range 3.",
        "The converter is ideal arithmetic; amplifier offsets and noise are zero.",
    )
    return Outcome(figures, (whole, wake), notes)
