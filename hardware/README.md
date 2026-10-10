# Hardware

The carrier board of the instrument: schematic, PCB layout, simulations and
fabrication outputs.

The instrument is two boards. A Raspberry Pi Pico 2, bought ready-made, is
the controller. It plugs into two rows of pin sockets on the carrier board
designed here, which holds everything else: power input, source meter, shunt
ladder, signal chain, side data and connectors. Sections 4.11 and 5 of the
[specification](../docs/specification.md) define the interface.

![Carrier board, draft A2](doc/images/board-3d.jpg)

## Status

Draft A2. The KiCad project holds the whole carrier board as a review draft:
the schematic with 428 parts on fifteen A4 pages (the root sheet and
fourteen sheets) and a four-layer board of 150 mm × 100 mm with every
footprint placed and the tracks drawn by an autorouter.

What the draft has behind it:

- The schematic passes the electrical rules check of KiCad with no errors
  and no warnings. The netlist that KiCad exports equals the netlist the
  drawings were generated from (428 parts, 225 nets), and every symbol pin
  has a pad in its footprint (65 pairs of symbol and footprint).
- The netlist was checked independently against the datasheets: symbol,
  footprint and ratings of every part type that is new in this draft, and
  six subsystems as a whole (power, source meter, ampere path, measuring
  chain, controller and logic, and the seams between the blocks). That
  check found no blocker and no major defect.
- Every line of the bill of materials has a part number and a maker (151
  lines; section 17 of the specification).

It is not a design to fabricate:

- Nothing has been built and nothing has been measured. Every figure in
  these documents is a datasheet value, a calculation, a simulation or an
  estimate; the specification says which.
- The parts are the candidates of the specification. No component check of
  [`docs/checks/`](../docs/checks/) is closed, and the open checks of
  section 16 of the specification stand, the bench items among them.
- The board is an autorouted draft that needs a layout review before
  fabrication ([Board](#board)).
- The range logic and the sampling clock are programs for the PIO blocks of
  the controller. They are not written yet; until they are, the pin
  assignment of the controller is provisional.
- Three positions carry no part. They are marked "do not populate" and are
  left out of the bill of materials: a voltage detector at the enable pin
  of the boost converter (U9) and the two parts of a damper on the
  module input (R14, C5). Each is the remedy for a bench item of
  section 16 (decision D-84).
- Three lines of the bill of materials had no stock at an authorized
  distributor on 2026-10-09: the 1.5 µH inductor of the pre-regulator
  (L2, Coilcraft XFL4020-152MEC; Würth 74438356015 fits the same pads)
  and the capacitors Samsung CL21A106KAYNNNE and CL31A226KAHNNNE.
- The land pattern of the pre-regulator (U16) is a library footprint
  whose lead pads agree with the drawing of the manufacturer; its center
  pad is larger than the drawing asks for (1.7 mm × 3.3 mm against
  1.58 mm × 2.85 mm), which is accepted.
- KiCad has no 3D model of the lever terminal block, so the pictures show
  only its pads. The side its wires enter from was taken from the
  footprint, not from the drawing of the manufacturer.

## Layout

| Path | Content |
| --- | --- |
| `kicad/` | KiCad 10 project: schematic sheets, board, design rules and library tables |
| `kicad/lib/` | Project symbol and footprint libraries |
| `doc/` | Pictures of every schematic sheet and of the board, and the schematic as PDF |
| `simulation/` | SPICE simulations: front end and regulator (empty in this draft) |
| `fabrication/` | Outputs of each revision: Gerber and drill files, bill of materials, placement (empty until a revision is fabricated) |

## KiCad Project

Open `kicad/power-profiler-carrier.kicad_pro` with KiCad 10. To look at the
design without KiCad, see [`doc/`](doc/README.md): every sheet with a
description and the board as pictures, and
[`doc/schematic.pdf`](doc/schematic.pdf).

### Schematic

| Page | Sheet | File | Content |
| --- | --- | --- | --- |
| 1 | Root | `power-profiler-carrier.kicad_sch` | One block per sheet and the wires between them |
| 2 | Controller | `controller.kicad_sch` | Raspberry Pi Pico 2 on its sockets, supply of the module, pull and series resistors of the SPI and acquisition lines, series resistors of the two status lines, reset button, console header |
| 3 | Power Input | `power_input.kicad_sch` | USB-C power connector, one current limiter per USB input, priority multiplexer that drives the 5 V rail |
| 4 | Logic Supplies | `logic_supplies.kicad_sch` | Supervisor of the 5 V rail, the two 3.3 V regulators, power LED, mounting holes, fiducials |
| 5 | Analog Rails | `analog_rails.kicad_sch` | +13.5 V boost, +12 V and −4 V rails with their clamps, 2.5 V reference |
| 6 | Rail Monitor | `rail_monitor.kicad_sch` | Four comparators that watch the analog rails and the reference: PWR_GOOD |
| 7 | Source Meter | `source_meter.kicad_sch` | Pre-regulator that tracks the output, linear regulator with its clamps, DAC and set-point amplifier |
| 8 | Path Switching | `path_switching.kicad_sch` | Source and ampere mode switches with their gate networks and interlock, VIN input and its protection |
| 9 | Shunt Ladder | `shunt_ladder.kicad_sch` | Four shunts, range switches with their drivers, ladder clamp, Kelvin multiplexer |
| 10 | Output Stage | `output_stage.kicad_sch` | Output switch with slow turn-on, DUT connectors and their suppressor, guard buffer |
| 11 | Signal Chain | `signal_chain.kicad_sch` | Instrumentation amplifier, pedestal, limiter on its own driver rail, filter, converter, shield can |
| 12 | Comparators | `comparators.kicad_sch` | Step up, over-current and jump thresholds |
| 13 | Side Data | `side_data.kicad_sch` | Two shift registers: status and logic inputs of every sample |
| 14 | Digital Inputs | `digital_inputs.kicad_sch` | Logic port, protection, series resistors and pull-downs, level translator |
| 15 | Monitors | `monitors.kicad_sch` | Eight slow channels and the temperature sensor |

Drawing conventions:

- Every page is A4.
- Connections inside a sheet are wires. Supply rails use power symbols.
- A signal that goes to another sheet ends on a hierarchical label, and the
  root sheet joins the sheets with wires.
- Reference designators are numbered as the annotation tool of KiCad does by
  default: one count per prefix (`R1`, `R2`, ... and `C1`, `C2`, ...), in the
  order of the sheets, and on a sheet by position (decision D-45).
- Each sheet carries notes with the design values of its block. In the
  notes, "range 0" to "range 3" are the four current ranges, so that they
  are not taken for resistors. On the Digital Inputs sheet, "D0" to "D7"
  are the logic inputs, named as on the logic port of the PPK2: they are
  not diodes.
- A part drawn with a cross is a position without a part.

Supply rails:

| Rail | Source | Feeds |
| --- | --- | --- |
| `+5V` | Priority multiplexer: the USB-C connector of the carrier through a 2.0 A limiter, or the USB connector of the Pico 2 through a jumper and a 0.76 A limiter | Every converter and regulator, the supervisor, and the Pico 2 through a diode |
| `+13V5` | Boost converter, running whenever `+5V` is present | +12 V_A regulator, control pin of the output regulator |
| `+12V_A` | Low-noise regulator | Amplifiers, multiplexer, gate drivers, buffers |
| `-4V_A` | Inverting charge pump with regulator | Amplifiers, multiplexer, buffers, minimum load of the output regulator |
| `+3V3_A` | Low-noise regulator | Converter, comparators, DAC, monitor, reference, buffer of the driver rail |
| `+3V3_C` | Regulator | Logic of the carrier, rail monitor, power LED |
| `VREF` | 2.5 V reference, supplied from `+3V3_A` | Converter, DAC, monitor, thresholds, pedestal, driver rail |

A supervisor on `+5V` enables both 3.3 V regulators, the +12 V_A regulator,
the charge pump and, through a transistor, the pre-regulator: below 3.83 V
to 4.00 V on the rail (calculated) the carrier is off, with no firmware
involved (decision D-48). The power tree with its thresholds and its
start-up order is in section 3 of the specification.

The bill of materials is generated from the schematic, in which each of
its parts carries the fields `MPN` and `Manufacturer`: one line per part
number, 151 lines. From `kicad/`:

```sh
kicad-cli sch export bom --output bom.csv --fields 'Reference,Value,Footprint,MPN,Manufacturer,${QUANTITY}' --group-by 'Value,Footprint,MPN,Manufacturer' --exclude-dnp power-profiler-carrier.kicad_sch
```

### Board

`power-profiler-carrier.kicad_pcb` is linked to the schematic: every
footprint has its nets and its symbol.

- Outline 150 mm × 100 mm with a corner radius of 3 mm and four M3 holes
  (decision D-85).
- Four copper layers: `F.Cu` carries signals and all parts, `In1.Cu` is the
  ground plane, `In2.Cu` carries power and signals, `B.Cu` signals. All 425
  footprints are on the top side.
- The stackup in the board setup is the build that section 10.1 of the
  specification assumes until a manufacturer is chosen: 1.6 mm, 35 µm
  outer and 17.5 µm inner copper, 0.2 mm of dielectric between each outer
  layer and the inner layer next to it, gold finish (ENIG).
- Back edge, on the left: the USB connector of the Pico 2, which lies along
  the top edge, and below it the USB-C power connector.
- Front edge, on the right, from the top: the logic port, the DUT pin header
  and the DUT lever terminal block, each with the names of its pins; the
  limits of VOUT and VIN are printed below the terminal block.
- The rectangles on the `Dwgs.User` layer are the areas of the sixteen
  functional blocks. They follow section 10.1 of the specification: the
  switching converters in the left third, the front end right of center
  under the frame of a shield can, the 1 A branch of the ladder between the
  can and the terminal block.
- Net classes for the 1 A path, the supply inputs, the switch nodes, the
  rails, the sense and guard nets, the gate nodes and the clocked lines are
  defined in the project file, thirteen with the default class. The file
  `power-profiler-carrier.kicad_dru` adds the clearances that a net class
  cannot express. The classes are bound to the names of the nets: after a
  change to the schematic, check that the nets of the 1 A path still have
  their class.

![Placement of the functional blocks](doc/images/board-placement.png)

Placement. The parts are placed by a script, from the netlist and from a
table that gives each part the pin it serves and its largest distance from
it. Connectors, mounting holes, fiducials and the frame of the shield can
stand at fixed coordinates. The result of the run that made this board:

- Every part is inside the rectangle of its block, no courtyard overlaps
  another, and nothing stands under the controller module.
- Only the 58 parts of the front end are inside the frame of the shield
  can.
- 95.9 % of the 370 distances of the table are kept, measured as the copper
  gap between the two pads, and so are those of all 47 decoupling
  capacitors.
- The reference designators of 115 parts are hidden on the silkscreen,
  where no free place was left beside the part. They are on the fabrication
  layer.

Nobody has reviewed that placement for routing by hand.

Routing. The board is routed automatically with FreeRouting 2.5.0, through
a Specctra export of the placed board and an import of the session file
(decision D-86). The ground plane on `In1.Cu` is given to the router as a
plane, so that ground pads reach it through vias and the layer stays free
of tracks.

The board of this draft is the result of several runs, each one continuing
from the board of the run before and routing only what was still open:

- 956 of the 984 connections are routed. 28 are open, and the design rules
  check lists them. Most lie where parts stand too close for a track or a
  via: at the input multiplexer, the pre-regulator, the charge pump, the
  ampere pair and the Kelvin multiplexer. Five belong to parts that
  came into the schematic after the first runs (two test points, a
  capacitor of the rail monitor, the position of the voltage detector): the
  router found no way to them through the tracks already laid. The other
  six are single connections: on `5V_OK`, on `PWR_GOOD`, at the output of
  the linear regulator, on one logic input, on the pedestal and on the
  sense line of the tracking amplifier.
- 7.83 m of track in 3,228 segments and 499 vias: 3.57 m on `F.Cu`, 2.66 m
  on `In2.Cu` and 1.60 m on `B.Cu`. `In1.Cu` is an unbroken ground plane.
- The tracks of the power nets are necks of 0.3 mm to 0.5 mm, and those of
  the rails, the guard nets and the gate drivers are 0.25 mm wide. The router
  did not finish the board with the widths of their classes, and section 10
  of the specification asks for pours on the power nets in any case.
- The bottom layer under the measured node carries tracks. With that area
  kept free the router did not reach the pins of the Kelvin multiplexer;
  the ground plane lies between those tracks and the node.
- The spacings of the rule file around gate nodes, switching nodes, the 1 A
  path, the measured node and VIN do not apply to a track that touches the
  courtyard of a footprint. At the pins of a part the pad pitch decides the
  spacing, and no track could leave a transistor otherwise.

An autorouted board is a draft: it needs a layout review before fabrication.
An autorouter connects pads. It does not draw the copper pours of the 1 A
path, the guard ring around the measured node or the coupled pairs of the
Kelvin sense lines, it does not keep the loops of the switching converters
small, and it places no vias for heat. Section 10.8 of the specification
lists what the review draws and checks by hand, with the rule of section 10
behind each item.

![The three routing layers](doc/images/board-copper.png)

### Connectors

Someone who faces the front edge reads the pins from left to right in the
order of the Nordic PPK2 (Figure 4 of its user guide, v1.0.1).

| Connector | Type | Pins |
| --- | --- | --- |
| DUT, pin header | 1×4, 2.54 mm, straight | GND, VIN, VOUT, GND |
| DUT, terminal block | Lever-operated, 3.5 mm (candidate: WAGO 2601-1104) | GND, VIN, VOUT, GND |
| Logic port | 1×10, 2.54 mm, straight | VCC, GND, D7 down to D0 |

The carrier also has the USB-C power connector at the back edge (power
only) and a 3-pin console header (TX, RX and GND at 3.3 V).

The two DUT connectors carry the same nets. VOUT delivers 0.8 V to 5.0 V in
source mode. VIN is the external supply of ampere mode: 0.8 V to 5.0 V in
use, and −20 V to +20 V withstood while the ampere switch is open
(simulated; decision D-60). The VCC pin of the logic port is used only when
the solder jumper beside the level translator (JP2) is moved: as built,
the logic inputs follow the output voltage of the instrument, and they are
valid for logic levels of 1.65 V to 5.5 V (R-10). The limits of every
terminal are in section 4.9 of the specification.

### Libraries

| Library | Item | Description |
| --- | --- | --- |
| `PowerProfiler` | Symbol `ADS8860xDGS` | 16-bit converter, from the datasheet SBAS569B |
| `PowerProfiler` | Symbol `MUX509xPW` | Dual 4:1 multiplexer, from the datasheet SBAS758C |
| `PowerProfiler` | Symbol `TPS63020DSJ` | Buck-boost converter, from the datasheet SLVS916I |
| `PowerProfiler` | Symbol `TPS2116DRL` | Priority power multiplexer, with the pin numbers of the KiCad symbol `Power_Management:TPS2116DRL`; its second output pin is passive |
| `PowerProfiler` | Footprint `TerminalBlock_WAGO_2601-1104_1x04_P3.50mm_Horizontal_Pad1.9mm` | Lever terminal block: the library footprint with pads of 1.9 mm × 2.3 mm |
| `PowerProfiler` | Footprint `RaspberryPi_Pico_Common_THT_NoKeepout` | Controller module: the library footprint without its antenna keep-out |
| `PowerRails` | Power symbols | One symbol per supply rail of the table above, and the ground symbol |

The symbols are in `kicad/lib/PowerProfiler.kicad_sym` and
`kicad/lib/PowerRails.kicad_sym`, the two footprints in
`kicad/lib/PowerProfiler.pretty` (decision D-85). Every other symbol and
footprint, the symbol of the Pico 2 among them, comes from the library that
KiCad 10 installs.

### Controller Module

The carrier takes a Raspberry Pi Pico 2 with its pin headers fitted, on two
1×20 pin sockets 17.78 mm apart (MP1, MP2). The sockets are soldered
into the holes of the module footprint (U1) and the module is plugged
into them; an RP2350 of stepping A3 or A4 is preferred (decision D-82). A
Pico 2 W fits the same sockets, but the firmware does not support it. The
pin map is in section 5 of the specification; every GPIO of the headers is
in use.

- Either USB connector powers the whole instrument, and USB-C is used
  whenever it is present. Each input has its own current limiter, and
  neither connector is fed back from the other. Cut the solder jumper on
  the Controller sheet (JP1) to keep the carrier off the USB port of the
  computer.
- With the data cable alone the instrument stays inside what a default USB
  port offers: the input current allowed is 0.45 A, about 1.5 W at the
  output (estimate). The whole current curve of R-08 needs a USB-C source
  that offers 1.5 A or more (section 4.1 of the specification, decision
  D-49).
- Every line that the module drives, except the console output, has a
  resistor to a rail on the carrier, and series resistors limit what a pin
  can push into an input whose supply is absent. With the module in reset,
  in its boot loader or out of its sockets every switch is open and the
  pre-regulator is off (section 5).
- Firmware is loaded through the USB connector of the Pico 2: hold its
  BOOTSEL button and press the reset button of the carrier.

### Checks

Run them from `kicad/`. The Hardware workflow runs the same commands when it
is started.

```sh
kicad-cli sch erc --severity-all power-profiler-carrier.kicad_sch
kicad-cli pcb drc --schematic-parity --severity-all power-profiler-carrier.kicad_pcb
```

The electrical rules check reports no errors and no warnings.

The design rules check compares the board with its rules and with the
schematic. Before a board is ordered it must report no rule violation, no
difference between board and schematic and no unconnected item. On the
board of this draft it reports:

- no rule violation;
- no footprint error and no difference between board and schematic;
- 28 unconnected items: the open connections named under "Board".

Both were run with `kicad-cli` only. The project has not been opened in the
KiCad editor yet.

### Still to Do

The board, before it can be ordered (section 10.8 of the specification):

- Review the placement and the routed board against the rules of
  section 10, and close every connection the autorouter left open.
- Draw the 1 A path as pours and count its squares; draw the output island
  of the linear regulator and the ground fills with their vias.
- Draw the guard ring with its mask opening and its pour, and keep foreign
  nets and ground fill away from the measured node.
- Route the Kelvin pairs and the amplifier inputs as pairs of equal length
  on one layer without vias.
- Lay the loops of the pre-regulator, the boost converter and the charge
  pump on the top layer without vias, and route the reference as a star.
- Take tracks through the wall of the shield can only at the openings of
  its frame; place the vias of the thermal pads, of the 1 A path and of the
  lands of the can.
- Compare a 1:1 print with the module on its sockets, the USB-C connector,
  the terminal block, the frame of the can and one of the 1 A transistors.

The open checks of section 16 of the specification:

- Close the component checks, part by part, each with the comparison of
  pin numbers and land pattern with the datasheet.
- Before a board is ordered, without a carrier board: the risk prototypes of
  phase 1 (reaction of the range sequencer, pre-regulator with its tracking
  amplifier, start of the boost converter from a supply limited to 0.7 A),
  the linear range of the amplifier near full scale with the output below
  0.2 V, and on loose parts the leakage of the VOUT suppressor, the leakage
  of the range and clamp transistors and the on-resistance of the
  multiplexer.
- Find stock for the three lines of the bill of materials that had none,
  and order the parts with long lead times first.
- On the first board, before a DUT is connected: every gate at or below
  0.3 V in the states that section 16 lists, then the gate ramp of the
  output switch and the in-rush with a capacitor in place of the DUT.
- Decide the three positions without parts on the bench.

The rest:

- Write the PIO programs of the range sequencer and of the acquisition, and
  test them in an emulator.
- Put the simulation files behind the figures of the specification into
  `simulation/`; the directory is empty.
- Plot the pictures of `doc/` again after every change to the schematic or
  the board; the commands are at the end of [`doc/README.md`](doc/README.md).

## Design References

In the [specification](../docs/specification.md):

- Section 3: system architecture and power tree.
- Section 4: analog hardware design, from the power input to the error
  budget, and the controller module.
- Section 5: pin map.
- Section 6.6: firmware rules that guard hardware.
- Section 10: PCB and mechanical guidelines.
- Section 15: decisions, D-23 onwards for the drafts and D-47 to D-86 for
  draft A2.
- Section 16: open checks.
- Section 17: bill of materials summary.

## Revisions

Board revisions are named with letters. Drafts A0, A1 and A2 are review
drafts; A2 is the one in this directory. Revision A is the first carrier
board to be fabricated (phase 5) and revision B corrects the issues found on
it (phase 7). Fabrication outputs are stored per revision, for example
`fabrication/rev-a/`.

- Draft A1 changed, against draft A0, the controller (a Raspberry Pi Pico 2
  in place of the ESP32-S3 development board and of the programmable logic
  device), the connectors of the DUT, the reference designators and the
  board (decisions D-39 to D-46).
- Draft A2 is draft A1 after a review of every part and every block, which
  recorded 432 findings, six of them blockers. The power input has a
  current limiter per USB input and a priority multiplexer in place of the
  fuse and the diode OR-ing, and a supervisor of the 5 V rail gives the
  carrier one off state. Four comparators make PWR_GOOD, the pre-regulator
  follows the output of the linear regulator, the switches of the path
  close slowly behind gate networks, the two mode switches cannot be closed
  together, and VIN withstands −20 V to +20 V. Clamps, pull resistors and
  series resistors protect the ladder, the terminals, the converter input
  and the lines of the controller. The schematic grew from 278 parts on
  13 pages to 428 parts on 15 and was numbered again, and every line of
  the bill of materials has a part number. Where the specification asked
  for more than an instrument of this class delivers, the requirement was
  restated (R-04, R-06 to R-10 and R-14). The board grew from
  130 mm × 100 mm to 150 mm × 100 mm and is placed and routed
  automatically, where draft A1 had placed footprints and no tracks
  (decisions D-47 to D-86).

## License

Copyright (c) 2026 Luiz Guilherme Ito.

The design files in this directory are licensed under the CERN Open Hardware
Licence Version 2 - Permissive (CERN-OHL-P v2). See [LICENSE](LICENSE). They
are provided without any warranty, as stated in section 5 of the license.
