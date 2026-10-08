# Hardware

The carrier board of the instrument: schematic, PCB layout, simulations and
fabrication outputs.

The instrument is two boards. An ESP32-S3-DevKitC-1 compatible development
board, bought ready-made, is the controller. It plugs into two rows of pin
sockets on the carrier board designed here, which holds everything else:
power input, source meter, shunt ladder, range logic, signal chain and
connectors. Sections 4.11 and 5 of the
[specification](../docs/specification.md) define the interface.

![Carrier board, draft A0](doc/images/board-3d.jpg)

## Status

Draft A0. The KiCad project holds the whole carrier board as a review draft:
the schematic on thirteen A4 sheets and a board file with every footprint
placed and no tracks. It exists so that the design can be read as a whole
and the layout work can start. It is not a design to fabricate:

- The parts are the candidates of the specification. No component check of
  [`docs/checks/`](../docs/checks/) is closed, nothing was simulated and
  nothing was measured.
- The pin numbers of the symbols taken from the KiCad library were not
  compared with the datasheets yet. The four symbols drawn for this project
  were.
- The logic device that holds the range logic has no description yet. Until
  it is written and simulated, its pin assignment is provisional.
- The board has an outline, the fixed parts and one area per functional
  block. Inside an area the parts are only packed, not arranged for
  routing.
- The footprint of the pre-regulator is a generic one of the same size.

## Layout

| Path | Content |
| --- | --- |
| `kicad/` | KiCad 10 project: schematic sheets, board and library tables |
| `kicad/lib/` | Project symbol libraries and footprint library |
| `doc/` | Pictures of every schematic sheet and of the board, and the schematic as PDF |
| `simulation/` | SPICE simulations: front end, range logic and regulator |
| `fabrication/` | Outputs of each revision: Gerber and drill files, bill of materials, placement |

## KiCad Project

Open `kicad/power-profiler-carrier.kicad_pro` with KiCad 10. To look at the
design without KiCad, see [`doc/`](doc/README.md): every sheet and the board
as pictures, and [`doc/schematic.pdf`](doc/schematic.pdf).

### Schematic

| Page | Sheet | File | Content |
| --- | --- | --- | --- |
| 1 | Root | `power-profiler-carrier.kicad_sch` | One block per sheet and the wires between them |
| 2 | MCU Interface | `mcu_interface.kicad_sch` | Development board on its sockets, series resistors, buffer towards the MCU, debug header |
| 3 | Power Input | `power_input.kicad_sch` | USB-C power connector, fuse, 3.3 V regulators, mounting holes |
| 4 | Analog Rails | `analog_rails.kicad_sch` | +13.5 V boost, +12 V_A, −4 V_A, 2.5 V reference |
| 5 | Source Meter | `source_meter.kicad_sch` | Tracking pre-regulator, linear regulator, DAC and set-point amplifier |
| 6 | Path Switching | `path_switching.kicad_sch` | Source and ampere mode switches, VIN terminal and its protection |
| 7 | Shunt Ladder | `shunt_ladder.kicad_sch` | Four shunts, range switches with their drivers, clamp, Kelvin multiplexer |
| 8 | Output Stage | `output_stage.kicad_sch` | Output switch, VOUT terminal, guard buffer |
| 9 | Signal Chain | `signal_chain.kicad_sch` | Instrumentation amplifier, pedestal, limiter, filter, converter |
| 10 | Comparators | `comparators.kicad_sch` | Step up, over-current and jump thresholds |
| 11 | Range Logic | `range_logic.kicad_sch` | Logic device with its programming header |
| 12 | Digital Inputs | `digital_inputs.kicad_sch` | Logic header, protection, level translator |
| 13 | Monitors | `monitors.kicad_sch` | Eight slow channels and the temperature sensor |

Drawing conventions:

- Every page is A4.
- Connections inside a sheet are wires. Supply rails use power symbols.
- A signal that goes to another sheet ends on a hierarchical label, and the
  root sheet joins the sheets with wires.
- A reference designator starts with the page number: `R201` is on page 2,
  `U1101` on page 11.
- Each sheet carries notes with the design values of its block.

Supply rails:

| Rail | Source | Feeds |
| --- | --- | --- |
| `+5V` | USB-C connector of the carrier, after the fuse | Every converter and regulator |
| `+13V5` | Boost converter | +12 V_A regulator, control pin of the output regulator |
| `+12V_A` | Low-noise regulator | Amplifiers, multiplexer, gate drivers, reference |
| `-4V_A` | Inverting charge pump with regulator | Amplifiers, multiplexer, minimum load |
| `+3V3_A` | Low-noise regulator | Converter, its driver, comparators, DAC, monitor |
| `+3V3_C` | Regulator | Logic of the carrier |
| `+3V3_D` | 3V3 pin of the development board | Buffer towards the MCU only |
| `VREF` | 2.5 V reference | Converter, DAC, monitor, thresholds |

### Board

`power-profiler-carrier.kicad_pcb` is linked to the schematic: every
footprint has its nets and its symbol.

- Outline 160 mm × 100 mm, four copper layers, four M3 holes.
- Fixed: the sockets of the development board at the left with the USB end
  at the bottom edge, the USB-C power connector beside them, the VIN and
  VOUT terminals and the logic header on the right edge.
- The rectangles on the `Dwgs.User` layer are the areas of the functional
  blocks. They follow section 10 of the specification: converters and the
  development board away from the front end.
- The area under the antenna of the development board is kept free.
- Net classes for the 1 A path and for the supply rails are defined in the
  project file.

![Placement of the functional blocks](doc/images/board-placement.png)

### Libraries

| Library | Item | Description |
| --- | --- | --- |
| `PowerProfiler` | Symbol `ESP32-S3-DevKitC-1` | 44 pins. Pin numbers give header and position, `J1_1` to `J3_22` |
| `PowerProfiler` | Symbol `ADS8860xDGS` | 16-bit converter, from the datasheet SBAS569B |
| `PowerProfiler` | Symbol `MUX509xPW` | Dual 4:1 multiplexer, from the datasheet SBAS758C |
| `PowerProfiler` | Symbol `TPS63020DSJ` | Buck-boost converter, from the datasheet SLVS916I |
| `PowerProfiler` | Footprint `ESP32-S3-DevKitC-1_Socket` | Sockets of the development board, see below |
| `PowerRails` | Power symbols | One symbol per supply rail of the table above |

### Development Board

The board in use is the common ESP32-S3-DevKitC-1 clone with two USB-C
ports, with an N8R2 or N16R2 module. Its headers have the pin order of the
Espressif board. Seen from the top with the antenna up, J1 is the left row
and pin 1 of both rows is at the antenna end.

| | Board in use | Espressif v1.1 |
| --- | --- | --- |
| Outline | 27.94 mm × 57.15 mm, antenna 6.2 mm beyond | 25.40 mm × 62.74 mm |
| Distance between the rows | 25.40 mm | 22.86 mm |
| RGB LED | GPIO 48 | GPIO 38 |

The socket footprint has one row of holes for J1 and two for J3, so both
widths fit. Both outlines are drawn in the footprint, the board in use on
the fabrication layer and the Espressif board on `Dwgs.User`. Measure the
board in hand before fabricating the carrier.

Modules with octal PSRAM (R8, R16V) do not work on this carrier: it uses
GPIO 35 and 36.

### Checks

Run them from `kicad/`. The Hardware workflow runs the same commands when it
is started.

```sh
kicad-cli sch erc --severity-all power-profiler-carrier.kicad_sch
kicad-cli pcb drc --schematic-parity --severity-all power-profiler-carrier.kicad_pcb
```

The electrical rules check reports no errors and no warnings. The design
rules check must report no difference between board and schematic; the
unconnected items it lists are the missing tracks.

### Still to Do

- Close the component checks, part by part, and compare every library
  symbol with its datasheet.
- Simulate the front end, the range logic and the regulator
  (`simulation/`).
- Write and simulate the description of the range logic.
- Draw the land pattern of the pre-regulator from the package drawing.
- Arrange the parts inside each area, route the board, add the guard ring
  and the shield.
- Plot the pictures of `doc/` again after every change to the schematic or
  the board; the commands are at the end of [`doc/README.md`](doc/README.md).

## Design References

In the [specification](../docs/specification.md):

- Section 4: analog hardware design, from the power input to the error
  budget, and the interface to the development board.
- Section 5: pin map.
- Section 10: PCB and mechanical guidelines.
- Section 15: decisions, D-23 onwards for this draft.
- Section 16: open checks.
- Section 17: bill of materials summary.

## Revisions

Board revisions are named with letters. Draft A0 is the review draft in this
directory. Revision A is the first carrier board to be fabricated (phase 5)
and revision B corrects the issues found on it (phase 7). Fabrication
outputs are stored per revision, for example `fabrication/rev-a/`.

## License

Copyright (c) 2026 Luiz Guilherme Ito.

The design files in this directory are licensed under the CERN Open Hardware
Licence Version 2 - Permissive (CERN-OHL-P v2). See [LICENSE](LICENSE). They
are provided without any warranty, as stated in section 5 of the license.
