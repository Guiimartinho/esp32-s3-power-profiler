# Hardware

The carrier board of the instrument: schematic, PCB layout, simulations and
fabrication outputs.

The instrument is two boards. A Raspberry Pi Pico 2, bought ready-made, is
the controller. It plugs into two rows of pin sockets on the carrier board
designed here, which holds everything else: power input, source meter, shunt
ladder, signal chain, side data and connectors. Sections 4.11 and 5 of the
[specification](../docs/specification.md) define the interface.

![Carrier board, draft A1](doc/images/board-3d.jpg)

## Status

Draft A1. The KiCad project holds the whole carrier board as a review draft:
the schematic on thirteen A4 sheets and a board file with every footprint
placed and no tracks. It exists so that the design can be read as a whole
and the layout work can start. It is not a design to fabricate:

- The parts are the candidates of the specification. No component check of
  [`docs/checks/`](../docs/checks/) is closed, nothing was simulated and
  nothing was measured.
- The pin numbers of the symbols taken from the KiCad library were not
  compared with the datasheets yet. The three symbols drawn for this project
  were.
- The range logic is a set of programs for the PIO blocks of the controller.
  They are not written yet; until they are, the pin assignment of the
  controller is provisional.
- The parts were placed by a script, from the netlist: each one near the pin
  it serves, turned towards its connections. Nobody has reviewed that
  placement for routing, and three groups of parts lie just outside the
  outline of their block.
- The footprint of the pre-regulator is a generic one of the same size.
- KiCad has no 3D model of the lever terminal block, so the pictures show
  only its pads. The side its wires enter from was taken from the footprint,
  not from the drawing of the manufacturer.

What changed from draft A0: the controller (a Raspberry Pi Pico 2 in place
of the ESP32-S3 development board and of the programmable logic device), the
connectors of the DUT, the reference designators and the board (decisions
D-39 to D-46 of the specification).

## Layout

| Path | Content |
| --- | --- |
| `kicad/` | KiCad 10 project: schematic sheets, board and library tables |
| `kicad/lib/` | Project symbol libraries |
| `doc/` | Pictures of every schematic sheet and of the board, and the schematic as PDF |
| `simulation/` | SPICE simulations: front end and regulator |
| `fabrication/` | Outputs of each revision: Gerber and drill files, bill of materials, placement |

## KiCad Project

Open `kicad/power-profiler-carrier.kicad_pro` with KiCad 10. To look at the
design without KiCad, see [`doc/`](doc/README.md): every sheet and the board
as pictures, and [`doc/schematic.pdf`](doc/schematic.pdf).

### Schematic

| Page | Sheet | File | Content |
| --- | --- | --- | --- |
| 1 | Root | `power-profiler-carrier.kicad_sch` | One block per sheet and the wires between them |
| 2 | Controller | `controller.kicad_sch` | Raspberry Pi Pico 2 on its sockets, supply joining, series resistors, reset button, console header |
| 3 | Power Input | `power_input.kicad_sch` | USB-C power connector, fuse, 3.3 V regulators, mounting holes |
| 4 | Analog Rails | `analog_rails.kicad_sch` | +13.5 V boost, +12 V_A, −4 V_A, 2.5 V reference |
| 5 | Source Meter | `source_meter.kicad_sch` | Tracking pre-regulator, linear regulator, DAC and set-point amplifier |
| 6 | Path Switching | `path_switching.kicad_sch` | Source and ampere mode switches, VIN input and its protection |
| 7 | Shunt Ladder | `shunt_ladder.kicad_sch` | Four shunts, range switches with their drivers, clamp, Kelvin multiplexer |
| 8 | Output Stage | `output_stage.kicad_sch` | Output switch, DUT connectors, guard buffer |
| 9 | Signal Chain | `signal_chain.kicad_sch` | Instrumentation amplifier, pedestal, limiter, filter, converter |
| 10 | Comparators | `comparators.kicad_sch` | Step up, over-current and jump thresholds |
| 11 | Side Data | `side_data.kicad_sch` | Two shift registers: status and logic inputs of every sample |
| 12 | Digital Inputs | `digital_inputs.kicad_sch` | Logic port, protection, level translator |
| 13 | Monitors | `monitors.kicad_sch` | Eight slow channels and the temperature sensor |

Drawing conventions:

- Every page is A4.
- Connections inside a sheet are wires. Supply rails use power symbols.
- A signal that goes to another sheet ends on a hierarchical label, and the
  root sheet joins the sheets with wires.
- Reference designators are numbered as the annotation tool of KiCad does by
  default: one count per prefix (`R1`, `R2`, ... and `C1`, `C2`, ...), in the
  order of the sheets, and on a sheet from left to right.
- Each sheet carries notes with the design values of its block. In the
  notes, "range 0" to "range 3" are the four current ranges and "logic
  input 0" to "7" the digital inputs, so that they are not taken for
  resistors or diodes.

Supply rails:

| Rail | Source | Feeds |
| --- | --- | --- |
| `+5V` | USB-C connector of the carrier, after the fuse, or the USB connector of the Pico 2, through a jumper and a diode | Every converter and regulator, and the Pico 2 through a diode |
| `+13V5` | Boost converter | +12 V_A regulator, control pin of the output regulator |
| `+12V_A` | Low-noise regulator | Amplifiers, multiplexer, gate drivers, reference |
| `-4V_A` | Inverting charge pump with regulator | Amplifiers, multiplexer, minimum load |
| `+3V3_A` | Low-noise regulator | Converter, its driver, comparators, DAC, monitor |
| `+3V3_C` | Regulator | Logic of the carrier |
| `VREF` | 2.5 V reference | Converter, DAC, monitor, thresholds |

### Board

`power-profiler-carrier.kicad_pcb` is linked to the schematic: every
footprint has its nets and its symbol.

- Outline 130 mm × 100 mm, four copper layers, four M3 holes.
- Back edge, on the left: the Pico 2 lying along the edge with its USB
  connector, and below it the USB-C power connector.
- Front edge, on the right, from the top: the logic port, the DUT pin header
  and the DUT lever terminal block, each with the names of its pins.
- The rectangles on the `Dwgs.User` layer are the areas of the functional
  blocks. They follow section 10 of the specification: the switching
  converters in the left third, the front end in the right third.
- The reference designators of 23 parts are hidden on the silkscreen, where
  no free place was left beside the part. They are on the fabrication layer.
- Net classes for the 1 A path and for the supply rails are defined in the
  project file. They are bound to the names of the nets, most of which KiCad
  derives from the schematic: after a change to the schematic, check that
  the nets of the 1 A path still have their class.

![Placement of the functional blocks](doc/images/board-placement.png)

### Connectors

Someone who faces the front edge reads the pins from left to right in the
order of the Nordic PPK2 (Figure 4 of its user guide, v1.0.1).

| Connector | Type | Pins |
| --- | --- | --- |
| DUT, pin header | 1×4, 2.54 mm, straight or angled | GND, VIN, VOUT, GND |
| DUT, terminal block | Lever-operated, 3.5 mm (candidate: WAGO 2601-1104) | GND, VIN, VOUT, GND |
| Logic port | 1×10, 2.54 mm, straight or angled | VCC, GND, D7 down to D0 |

The two DUT connectors carry the same nets. VIN is the external supply of
ampere mode. The VCC pin of the logic port is used only when the solder
jumper beside the level translator is moved: as built, the logic inputs
follow the output voltage of the instrument.

### Libraries

| Library | Item | Description |
| --- | --- | --- |
| `PowerProfiler` | Symbol `ADS8860xDGS` | 16-bit converter, from the datasheet SBAS569B |
| `PowerProfiler` | Symbol `MUX509xPW` | Dual 4:1 multiplexer, from the datasheet SBAS758C |
| `PowerProfiler` | Symbol `TPS63020DSJ` | Buck-boost converter, from the datasheet SLVS916I |
| `PowerRails` | Power symbols | One symbol per supply rail of the table above |

Every footprint, and the symbol and footprint of the Pico 2, come from the
library that KiCad 10 installs.

### Controller Module

The carrier takes a Raspberry Pi Pico 2 with its pin headers fitted, on two
1×20 pin sockets 17.78 mm apart. A Pico 2 W fits the same sockets. The pin
map is in section 5 of the specification; every GPIO of the headers is in
use.

- Either USB connector powers the whole instrument. Cut the solder jumper on
  the Controller sheet to keep the carrier off the USB port of the computer.
- Firmware is loaded through the USB connector of the Pico 2: hold its
  BOOTSEL button and press the reset button of the carrier.

### Checks

Run them from `kicad/`. The Hardware workflow runs the same commands when it
is started.

```sh
kicad-cli sch erc --severity-all power-profiler-carrier.kicad_sch
kicad-cli pcb drc --schematic-parity --severity-all power-profiler-carrier.kicad_pcb
```

The electrical rules check reports no errors and no warnings. The design
rules check must report no rule violation and no difference between board
and schematic; the unconnected items it lists are the missing tracks.

Both were run with `kicad-cli` only. The project has not been opened in the
KiCad editor yet.

### Still to Do

- Close the component checks, part by part, and compare every library
  symbol with its datasheet.
- Write the PIO programs of the range sequencer and of the acquisition, and
  test them in an emulator.
- Simulate the front end and the regulator (`simulation/`).
- Draw the land pattern of the pre-regulator from the package drawing.
- Review the placement, route the board, add the guard ring and the shield.
- Plot the pictures of `doc/` again after every change to the schematic or
  the board; the commands are at the end of [`doc/README.md`](doc/README.md).

## Design References

In the [specification](../docs/specification.md):

- Section 4: analog hardware design, from the power input to the error
  budget, and the controller module.
- Section 5: pin map.
- Section 10: PCB and mechanical guidelines.
- Section 15: decisions, D-23 onwards for the drafts.
- Section 16: open checks.
- Section 17: bill of materials summary.

## Revisions

Board revisions are named with letters. Drafts A0 and A1 are review drafts;
A1 is the one in this directory. Revision A is the first carrier board to be
fabricated (phase 5) and revision B corrects the issues found on it
(phase 7). Fabrication outputs are stored per revision, for example
`fabrication/rev-a/`.

## License

Copyright (c) 2026 Luiz Guilherme Ito.

The design files in this directory are licensed under the CERN Open Hardware
Licence Version 2 - Permissive (CERN-OHL-P v2). See [LICENSE](LICENSE). They
are provided without any warranty, as stated in section 5 of the license.
