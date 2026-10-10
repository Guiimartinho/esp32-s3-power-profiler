# Test Reports

A report records the measurements that close a development phase. The phases
and their exit criteria are in section 13 of the
[specification](../specification.md).

## Status

No report is filed, and no phase is closed: nothing has been built and
nothing has been measured. Phase 1 is not started: the software that
exists was written ahead of it and is tested without hardware, and neither
the port to the Pico SDK nor the bench work has begun.

| Phase | What is measured | Report |
| --- | --- | --- |
| 1 | Risk prototypes. On a Raspberry Pi Pico 2 with an ADC evaluation module: the firmware on the Pico SDK, capture through PIO and DMA, the reaction time of a PIO state machine, USB throughput. On evaluation modules: the pre-regulator with its tracking amplifier, and the start of the boost converter from a supply limited to 0.7 A | None |
| 2 | Analog front end with one fixed range on a test board | None |
| 3 | Shunt ladder and range logic | None |
| 4 | Source mode and power | None |
| 5 | Carrier board, revision A, with the Pico 2 plugged in | None |
| 6 | Calibration, protocol freeze and host software | None |
| 7 | Revision B and release | None |

The carrier board exists as draft A2, drawn ahead of the phases. A draft is
not measured. Its layout was reviewed on 2026-10-10: all 984 connections
are routed, and the pours of the 1 A path, the guard, the Kelvin pairs and
the copper of the converters are drawn. The figures of that review, such as
19.5 and 23.3 squares of copper in the 1 A path and 5.1 nA of surface
leakage into the measured node, are calculated from the drawn copper. The
package in `tools/board/` calculates them again from the board file; its
tests show that the calculation does what it says, not that a board
behaves so. The figures are not evidence for a criterion, and no report
cites them as a result.

The circuits of the draft were simulated on 2026-10-10, from the netlist
of the schematic, and the results are filed in
[`simulation/results/`](../../simulation/results/README.md). Their pages
have a column "Verdict". A "pass" there says that a simulated circuit
keeps its limit with models written from datasheets: a limit of the
specification, a rating of a datasheet, or a limit that the bench sets
and names. It is not evidence for a criterion either, no report cites it
as a result, and it closes no phase. What the simulations give a report
is the figure to compare a measurement with, and a list of what only a
measurement can settle
([simulation guide](../../simulation/README.md#what-stays-for-the-bench)).
Three things that the simulations take as an input or leave open belong
to phase 1: the reaction time of the range sequencer, which every
simulation of the range logic takes as an input; the loop of the
pre-regulator at its low end; and the start of the boost converter from
a supply limited to 0.7 A, which decision D-97 leaves as the test that
says whether a remedy is needed at the position U9.

Phases 1 to 4 come before a carrier board is built: phase 1 runs on
evaluation modules and phase 2 on a test board, and the specification does
not name the hardware of phases 3 and 4 yet. The first report on a carrier
board belongs to revision A in phase 5. The layout review with scripts is
done, and the seven points in which the drawn board deviates from the
earlier text of section 10 of the specification are recorded as decisions
D-87 to D-93. What still precedes fabrication is the drawing of the
decisions that followed the circuit simulations (D-95, D-96 and D-98), a
review of the board by a person in the KiCad editor, the open items of the
layout that need a part moved, the silkscreen and test point items, and
the open checks (section 13 and section 16 of the specification). The
[hardware guide](../../hardware/README.md) lists them.

One measurement on that first board is already named: the temperature rise
of the linear regulator U18 at its full dissipation on the island of
copper of draft A2 (D-93, an open check of section 16). It belongs to the
report of phase 5.

The first report to expect is the one of phase 1. Its three prototypes need
no carrier board: a Pico 2 with an ADC evaluation module, an evaluation
module of the pre-regulator with the tracking amplifier and the linear
regulator on an adapter (D-55), and the boost converter with 10 µF at its
output. Before it can be written the firmware has to be
ported to the Pico SDK, which is not started.

## Rules

- A criterion passes only with evidence from a run that took place: the
  numbers, the setup that produced them and the location of the raw data.
- A criterion that was not run is marked "Not run", never "Pass".
- A datasheet value, a calculation, a simulation or an estimate is not
  evidence for a criterion. The specification holds many such figures;
  a report is where each one meets its measurement.
- Record the firmware and host software commits, what was measured
  (evaluation module, test board, or carrier board with its revision and
  serial number), the Pico 2 with the stepping of its RP2350, and the
  instruments with their settings, so the run can be repeated.
- The software gates of section 18 of the specification show that the
  logic does what its tests say. They are not a measurement, and a report
  does not cite them for timing, throughput or analog behavior.
- Small data files live next to the report in `data/phase-<n>/`. Large
  captures stay out of the repository; link to where they are stored.

## Writing a Report

1. Copy [`TEMPLATE.md`](TEMPLATE.md) to `phase-<n>-<short-title>.md`, for
   example `phase-1-risk-prototypes.md`.
2. Quote the exit criteria of the phase from the specification.
3. Fill in one measurement section per criterion.
4. List the decisions taken and the sections of the specification that
   changed. An item of section 16 that the measurement answers is updated
   there and in the [index of the checks](../checks/README.md).
5. Update the status table above, the roadmap table in the repository
   [README](../../README.md) and the changelog.
