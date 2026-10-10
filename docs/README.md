# Documentation

The index of every document of the repository, with the state of each one.

The project is in early development. The carrier board exists as draft A2,
a review draft with an autorouted board; the software foundations exist and
are tested without hardware. Nothing has been built and nothing has been
measured: every figure in these documents is a datasheet value, a
calculation, a simulation or an estimate, and says which.

## In This Directory

| Document | Content | State |
| --- | --- | --- |
| [specification.md](specification.md) | The baseline: requirements R-01 to R-17, architecture and analog design, pin map, firmware with the rules F-1 to F-36 that guard hardware, host protocol, calibration, board guidelines, verification plan, development phases, risk register, decision log, open checks and bill of materials | Written for draft A2 of the carrier board, with decisions D-01 to D-86. No value in it is measured |
| [checks/](checks/README.md) | Component checks: each candidate part, and each peripheral of the controller, against the documentation of its manufacturer. The tables mirror section 16 of the specification | Every check is open; no record is filed, so every part is a candidate |
| [checks/TEMPLATE.md](checks/TEMPLATE.md) | Form of a check record | In use from the first record |
| [reports/](reports/README.md) | Test reports: the measurements that close each development phase of section 13 | No report is filed; no phase is closed |
| [reports/TEMPLATE.md](reports/TEMPLATE.md) | Form of a phase report | In use from the first report |
| [protocol/](protocol/README.md) | Host protocol: where it is defined, its state against draft A2, and what the user reference will hold | Pointer page. The protocol is at version 1 and not frozen; the reference is planned for phase 6 |
| [calibration/](calibration/README.md) | Calibration: what section 8 of the specification defines, the reference equipment, and what is missing | Summary page. The procedure is not written; planned for phase 6 |

## In the Rest of the Repository

| Document | Content | State |
| --- | --- | --- |
| [README](../README.md) | The project in one page: the state of every area and the next steps, target specifications with a comparison with the PPK2, how it works, connections, the hardware draft in pictures, roadmap | Follows draft A2 |
| [Hardware guide](../hardware/README.md) | The carrier board: status of the draft, schematic, board, connectors, libraries, checks and the work still to do | Draft A2: 428 parts on 15 schematic pages; a board of 150 mm × 100 mm with 956 of 984 connections routed by an autorouter and 28 open. It needs a layout review before fabrication |
| [The draft in pictures](../hardware/doc/README.md) | Every schematic sheet and the board as pictures, with the design values of each block; the schematic is also a [PDF](../hardware/doc/schematic.pdf), and the bill of materials a [CSV file](../hardware/doc/bom.csv) | Plotted and exported from draft A2 |
| [Firmware guide](../firmware/README.md) | Architecture of the firmware, its layout, the unit tests on the PC, coverage and static analysis | The hardware-independent core exists and is unit-tested. The port to the Pico SDK is not started; the target build in the directory is still the one for the ESP32-S3 |
| [Host guide](../host/README.md) | The Python package: layers, setup, the simulated instrument, checks | Protocol codec, transports, device client, capture helpers and simulator exist and are tested. Viewer, export and the marks that draft A2 asks for are not written |
| [Protocol directory](../protocol/README.md) | The definition of the wire protocol, the generator, the shared test vectors, and how a change is made | Version 1, generated files up to date. The items that draft A2 reports are not in the definition yet |
| [Tools](../tools/README.md) | What the calibration tool and the production test will have to do | Not started; both directories are empty |
| [Contributing guide](../CONTRIBUTING.md) | Workflow, commit message format, quality gates, versioning | Current |
| [Changelog](../CHANGELOG.md) | Notable changes by release | Everything is under "Unreleased"; no release exists |

Two directories of the hardware area are empty and have no document:
`hardware/simulation/`, where the files behind the figures marked
"simulated" belong, and `hardware/fabrication/`, for the outputs of a board
that is ordered.

## What Comes Next

None of this is started. It is the work that stands between the draft and
the phases of section 13 of the specification:

1. Board: close the 28 open connections and review the layout against
   section 10 of the specification (the pours of the 1 A path, the guard
   ring, the Kelvin pairs, the loops of the converters). The list is in the
   [hardware guide](../hardware/README.md).
2. Software: bring the host package and the firmware core to what the
   specification of draft A2 asks (the nominal calibration values of
   section 8, the fault causes of section 6.4, the protocol items of
   section 16), and port the firmware to the Pico SDK.
3. Simulations: put the files behind the figures marked "simulated" into
   `hardware/simulation/`.
4. The open checks of section 16 and the risk prototypes of phase 1, each
   closed by a record in `checks/` or a report in `reports/`.

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

## Conventions

- American English.
- Prose wraps at 80 columns; tables and code blocks are exempt.
- SI units, with a space between the number and the unit: `100 mV`.
- Estimates, calculations, simulations, datasheet values and measurements
  are labeled as such. A datasheet value cites its check record and a
  measurement its report; until those exist, parts stay "candidate" and no
  figure is called verified.
- "Datasheet" is one word. The board is "draft A2" until a reviewed layout
  is fabricated as "revision A".
- Check the Markdown from the repository root before committing:

  ```sh
  npx --yes markdownlint-cli2@0.23.3
  ```
