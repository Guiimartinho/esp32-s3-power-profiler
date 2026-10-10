# Documentation

The index of every document of the repository, with the state of each one.

The project is in early development. The carrier board exists as draft A2:
a complete schematic and a board whose layout was reviewed on 2026-10-10.
All 984 connections are routed, and the copper that an autorouter does not
draw is drawn: the pours of the 1 A path, the guard, the Kelvin pairs, the
copper of the converters, the 5 V rail and the ground fills. That review
was done with scripts and checked by independent calculation; the board has
not yet been looked at by a person in the KiCad editor, and it is not a
design to fabricate. The seven points in which it deviates from the earlier
guidelines of section 10 of the specification are recorded as decisions
D-87 to D-93. The circuits of the schematic were simulated on 2026-10-10
from its netlist, in a package of their own in `simulation/` (D-94): 134
benches, whose results are filed. The central design figures of the
specification come out again. The simulations raised four points for a
decision before boards are ordered, and the project owner decided them the
same day: decisions D-95 to D-98. Three of them change the schematic and
are not drawn yet, so the schematic, the board, the bill of materials and
the results of the simulations still show the earlier state. In fourteen
places the simulations differ from the text of the specification; those
are not decided, and no requirement, figure or rule of the specification
was changed on their account. The software foundations exist and are
tested without hardware, and so do the package that calculates the
figures of the board layout and the package that runs the simulations.

Nothing has been built and nothing has been measured: every figure in these
documents is a datasheet value, a calculation, a simulation or an estimate,
and says which. Every figure of the board is calculated from the drawn
copper, and the package in `tools/board/` calculates them again from the
board file. A figure of the circuit simulations of 2026-10-10 comes from
a circuit whose parts are taken from the netlist, with models written
from datasheets, and the package in `simulation/` runs it again. The
figures that the specification marks "simulated" are older: they were
taken from simulations made while the draft was designed, whose files are
not filed.

## In This Directory

| Document | Content | State |
| --- | --- | --- |
| [specification.md](specification.md) | The baseline: requirements R-01 to R-17, architecture and analog design, pin map, firmware with the rules F-1 to F-36 that guard hardware, host protocol, calibration, board guidelines, verification plan, development phases, risk register, decision log, open checks and bill of materials | Written for draft A2 of the carrier board, with decisions D-01 to D-98. No value in it is measured. The seven points in which the reviewed board deviates from the earlier guidelines of section 10 are decisions D-87 to D-93, and sections 10.3, 10.4, 10.6 and 10.8 describe the board as it is drawn. D-94 places the circuit simulations in `simulation/`, and D-95 to D-98 are the decisions of the project owner on the four points that the simulations raised: it states them as the design, and three of them are not drawn yet. Where those simulations differ from a figure or a rule in other places, the text is unchanged: the end of section 16 lists fourteen such places as open |
| [checks/](checks/README.md) | Component checks: each candidate part, and each peripheral of the controller, against the documentation of its manufacturer. The tables mirror section 16 of the specification, the open points of the circuit simulations included | Every check is open; no record is filed, so every part is a candidate. The fourteen places where the simulations and the specification differ wait for the project owner; the four points of the simulations are decided (D-95 to D-98) and have left the list, and drawing them is the first item before the board is ordered |
| [checks/TEMPLATE.md](checks/TEMPLATE.md) | Form of a check record | In use from the first record |
| [reports/](reports/README.md) | Test reports: the measurements that close each development phase of section 13 | No report is filed; no phase is closed |
| [reports/TEMPLATE.md](reports/TEMPLATE.md) | Form of a phase report | In use from the first report |
| [protocol/](protocol/README.md) | Host protocol: where it is defined, its state against draft A2, and what the user reference will hold | Pointer page. The protocol is at version 1 and not frozen; the reference is planned for phase 6 |
| [calibration/](calibration/README.md) | Calibration: what section 8 of the specification defines, the reference equipment, and what is missing | Summary page. The procedure is not written; planned for phase 6 |

## In the Rest of the Repository

| Document | Content | State |
| --- | --- | --- |
| [README](../README.md) | The project in one page: the state of every area and the next steps, target specifications with a comparison with the PPK2, how it works, connections, the hardware draft in pictures, the circuit simulations with two of their graphs, roadmap | Follows draft A2 with the reviewed layout, the simulations of 2026-10-10 and the four decisions that followed them |
| [Hardware guide](../hardware/README.md) | The carrier board: status of the draft, schematic, board, connectors, libraries, checks and the work still to do | Draft A2: 428 parts on 15 schematic pages; a board of 150 mm × 100 mm on four layers with 984 of 984 connections routed and a design rules check with no violation and no unconnected pad. The layout is reviewed with scripts; its figures are calculated from the drawn copper. Its seven deviations from the earlier guidelines are recorded decisions (D-87 to D-93). A review by a person, the open items of the layout and the thermal check of D-93 stand before fabrication. It carries the four decisions that follow the simulations (D-95 to D-98) with what each changes on the schematic, the board or the bill of materials; none is drawn yet, and drawing them is its first step |
| [The draft in pictures](../hardware/doc/README.md) | Every schematic sheet and the board as pictures, with the design values of each block; the schematic is also a [PDF](../hardware/doc/schematic.pdf), and the bill of materials a [CSV file](../hardware/doc/bom.csv) | Plotted and exported from draft A2; the board pictures are plotted from the reviewed board file, and the views of the assembled board are renderings, not photographs. The pictures show the state before decisions D-95, D-96 and D-98; the text under the sheets says where they differ |
| [Simulation guide](../simulation/README.md) | The circuit simulations: the state of the results block by block, what they reproduce, the four points that are decided, where they differ from the text of the specification, what stays for the bench, the limits of the models, the traps of the simulator, setup, commands and checks | The package `circuit-sim` exists: 134 benches run in the ngspice library of KiCad 10, 93 that take the parts of their circuits from a snapshot of the netlist and 41 that put the models into the test circuits of their datasheets. 1834 figures pass, 122 fail and 1206 carry no limit. 777 tests, 100 % of lines and branches covered outside the one module that loads the simulator (floor 90 %), ruff and mypy in strict mode, run locally on Windows. Its workflow has not been started yet. It simulates with models written from datasheets and measures nothing. Its results are those of the circuit before decisions D-95, D-96 and D-98 |
| [Simulation results](../simulation/results/README.md) | One line for every bench, and a page for each block with every figure beside the value that the specification states and its limit, the graphs of the waveforms and the decks, the circuit files that the simulator ran | Written by the package from the result files of 2026-10-10; not edited by hand. Everything in them is simulated |
| [Firmware guide](../firmware/README.md) | Architecture of the firmware, its layout, the unit tests on the PC, coverage and static analysis | The hardware-independent core exists and is unit-tested. The port to the Pico SDK is not started; the target build in the directory is still the one for the ESP32-S3 |
| [Host guide](../host/README.md) | The Python package: layers, setup, the simulated instrument, checks | Protocol codec, transports, device client, capture helpers and simulator exist and are tested. Viewer, export and the marks that draft A2 asks for are not written |
| [Protocol directory](../protocol/README.md) | The definition of the wire protocol, the generator, the shared test vectors, and how a change is made | Version 1, generated files up to date. The items that draft A2 reports are not in the definition yet |
| [Tools](../tools/README.md) | The tools of the repository: the board figures, and what the calibration tool and the production test will have to do | The board figures exist and are tested without hardware. The calibration tool and the production test are not started; their directories are empty |
| [Board figures guide](../tools/board/README.md) | The package `board-figures`: how to install it, dump the board from KiCad and run each command; the method, the assumptions and the limits of each calculation; its checks | The package exists: 260 tests on synthetic boards, 100 % of lines and branches covered (floor 90 %), ruff and mypy in strict mode, run locally on Windows. Its workflow has not been started yet. It calculates from the drawn copper and measures nothing |
| [Contributing guide](../CONTRIBUTING.md) | Workflow, commit message format, quality gates, versioning | Current |
| [Changelog](../CHANGELOG.md) | Notable changes by release | Everything is under "Unreleased"; no release exists |

One directory of the hardware area is empty and has no document:
`hardware/fabrication/`, for the outputs of a board that is ordered. The
directory `hardware/simulation/` is gone: the simulations are in
`simulation/`, at the root of the repository (D-94). The scripts that
calculate the figures of the reviewed board (resistance of a pour in
squares, a path on one layer, surface leakage into the measured node,
lengths of the pairs) are filed in `tools/board/`, so a reader can repeat
those figures from the board file. The scripts that drew the copper of the
board are not in the repository, and neither are the model files of the
manufacturers, whose licenses do not allow it.

## What Comes Next

The first part of the board step is done: the 28 connections that the
autorouter left open are closed, and the layout is drawn against section 10
of the specification. The seven points in which the drawn board deviates
from the earlier text of that section are decided: the project owner
accepted them on 2026-10-10, and they are decisions D-87 to D-93 of the
log. The scripts that calculate the figures of the board are filed in
`tools/board/`. The simulation step is done as well: the circuits are
simulated from the final netlist, and the package, the models, the benches
and the results are filed in `simulation/`. The rest is not started. It is
the work that stands between the draft and the phases of section 13 of the
specification:

1. The decisions that follow the simulations, drawn. The project owner
   decided the four points on 2026-10-10 (D-95 to D-98). Three change the
   schematic and are not drawn yet: 10 nF at three capacitors of the rail
   monitor, a position for a capacitor at the buffer of the driver rail,
   which adds a footprint to the board, and the two parts of the damper on
   the module input. Then the two rule checks, the bill of materials and
   the pictures exported again, the netlist snapshot of the simulations
   written again and the benches of the changed blocks run again. The
   [hardware guide](../hardware/README.md#still-to-do) has the steps.
2. Decisions of the project owner that are still open:
   - The fourteen places where the simulation and the text of the
     specification differ, listed in the
     [simulation guide](../simulation/README.md#what-the-simulations-say)
     and at the end of section 16 of the specification. A change of the
     text is an entry in the decision log.
   - Whether proof-of-concept boards are ordered on this state.
3. Board, four things, with the lists in the
   [hardware guide](../hardware/README.md):
   - A person opens the board in KiCad and reviews it.
   - The open items that need a part moved or another footprint: a
     placement change with a local redraw. The capacitor loops of the
     pre-regulator, the boost converter and the charge pump are the
     largest of them.
   - The silkscreen and the test points: net names, the function of the two
     jumpers, a frame for the serial number, a probe ground near each test
     point.
   - The thermal check of D-93: the temperature rise of the linear
     regulator U18 at full dissipation on its island of copper, read on
     the first board.
4. Software: bring the host package and the firmware core to what the
   specification of draft A2 asks (the nominal calibration values of
   section 8, the fault causes of section 6.4, the protocol items of
   section 16), and port the firmware to the Pico SDK.
5. The open checks of section 16 and the risk prototypes of phase 1, each
   closed by a record in `checks/` or a report in `reports/`. No check is
   closed. The prototypes also settle what the simulations take as an
   input or leave open: the reaction time of the range sequencer, the loop
   of the pre-regulator and the start of the boost converter.

## How the Documents Relate

- The specification is the baseline. It names requirements `R-xx`,
  decisions `D-xx` and the firmware rules `F-xx` of its section 6.6; other
  documents refer to them by ID, and the IDs and section numbers are never
  renumbered.
- Section 16 of the specification lists the open checks. Each one is closed
  by a record in `checks/`, and the tables in `checks/` mirror the section.
- Section 13 lists the development phases. Each one is closed by a report in
  `reports/`, with recorded measurements.
- A change that deviates from the specification adds a row to its decision
  log (section 15).
- Every protocol number lives in `protocol/definition.toml`; section 7 of
  the specification describes the protocol, and the definition decides it.
- The hardware guide and the picture guide describe the KiCad project as it
  is; the reasons behind its values are in the specification.
- The figures of the board layout in every document come from the package
  in `tools/board/`, run on the board file in `hardware/kicad/`. A change
  of the board is followed by a new run and by the figures in the
  documents.
- A figure of the circuit simulations in any document comes from the
  result pages in `simulation/results/`, which the package in
  `simulation/` writes from its runs on a snapshot of the netlist. A
  change of the schematic is followed by a new snapshot, a new run of the
  blocks it touches and the figures in the documents.
- The figures that the specification marks "simulated" were taken from
  simulations made while draft A2 was designed, with circuits typed by
  hand, whose files are not filed. The simulations in `simulation/` were
  made again from the final netlist. Where the two differ, the
  specification is unchanged until the project owner decides, and
  section 16 lists the place. Four such points are decided (D-95 to
  D-98), and the specification states them as the design.
- The specification is ahead of the drawings in three decisions: D-95,
  D-96 and D-98 are not drawn yet. Until they are, the hardware guide,
  the pictures, the bill of materials and the results of the simulations
  describe the drawn state and say so.
- A simulation result is not a check record and not a phase report. It
  closes no item of section 16 and no phase of section 13.

## Conventions

- American English.
- Prose wraps at 80 columns; tables and code blocks are exempt.
- SI units, with a space between the number and the unit: `100 mV`.
- Estimates, calculations, simulations, datasheet values and measurements
  are labeled as such. A datasheet value cites its check record and a
  measurement its report; until those exist, parts stay "candidate" and no
  figure is called verified.
- "Datasheet" is one word. The board is "draft A2" until it is fabricated
  as "revision A". A figure of its layout is "calculated from the drawn
  copper", and a picture of the assembled board is a rendering. A figure
  of a circuit simulation is "simulated", and a graph of a run is a plot
  of a simulation, not a capture from an instrument.
- Check the Markdown from the repository root before committing:

  ```sh
  npx --yes markdownlint-cli2@0.23.3
  ```
