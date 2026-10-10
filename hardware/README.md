# Hardware

The carrier board of the instrument: schematic, PCB layout, simulations and
fabrication outputs.

The instrument is two boards. A Raspberry Pi Pico 2, bought ready-made, is
the controller. It plugs into two rows of pin sockets on the carrier board
designed here, which holds everything else: power input, source meter, shunt
ladder, signal chain, side data and connectors. Sections 4.11 and 5 of the
[specification](../docs/specification.md) define the interface.

![Rendered view of the carrier board, draft A2](doc/images/board-3d.jpg)

The picture is a rendering from the KiCad files, with the Pico 2 on its
sockets. It is not a photograph: no board has been built.

## Status

Draft A2 with a reviewed layout, as of 2026-10-10. The KiCad project holds
the whole carrier board: the schematic with 428 parts on fifteen A4 pages
(the root sheet and fourteen sheets) and a four-layer board of
150 mm × 100 mm on which every connection is drawn. The board was placed by
a script and routed by an autorouter, which left 28 connections open. On
2026-10-10 its layout was reviewed with scripts: the open connections were
closed and the copper that an autorouter does not draw was drawn. Every
figure of the board in this guide is calculated from the drawn copper.
Nobody has looked at the layout in the KiCad editor yet, no board is built,
and nothing is measured.

| What | State |
| --- | --- |
| Schematic | Every sheet drawn: 428 parts, 225 nets, 15 pages; not changed by the layout review |
| Electrical rules check | 0 errors, 0 warnings |
| Netlist against datasheets | Checked independently; no blocker and no major defect found |
| Bill of materials | 151 lines, each with a part number and a maker; three lines without stock on 2026-10-09; not changed by the layout review |
| Component checks | 0 closed; every part is a candidate |
| Board, placement | 425 footprints placed by a script; 35 of them moved or turned in the layout review; not reviewed by a person |
| Board, routing | 984 of 984 connections, none open: 8.38 m of track, 694 vias, 42 copper zones |
| Design rules check with schematic parity | 0 violations, 0 unconnected pads, 0 footprint errors, against a rule file that asks more than the one of the autorouted board |
| Layout review | Done with scripts and checked by independent calculation; not yet looked at by a person in the KiCad editor |
| 1 A path, copper only | 19.5 squares (10.4 mΩ at 40 °C) in source mode and 23.3 squares (12.3 mΩ at 40 °C) in ampere mode, against a limit of 30 squares; calculated from the drawn copper |
| Surface leakage into the measured node | 5.1 nA against a budget of 10 nA; calculated from the drawn copper with the assumptions of section 10.3 of the specification |
| Deviations from the words of section 10 | Seven, each recorded as a decision of the specification on 2026-10-10: D-87 to D-93 ([list](#decisions-of-the-layout-review-d-87-to-d-93)) |
| Open items of the layout | Eleven that need parts moved or another footprint, and five points that the review did not touch ([list](#open-items)) |
| Thermal check of the linear regulator | Open: the temperature rise of U18 at full dissipation is read on the first board (D-93) |
| Calculation scripts | In [`tools/board/`](../tools/board/README.md): they calculate the figures of the board again from the board file ([how](#reproducing-the-figures)) |
| Simulations | Run for the figures that the specification marks "simulated"; the simulation files are not in this repository |
| PIO programs | Not written |
| Fabrication outputs | None |
| Measurements | None: no board has been built |

What the draft has behind it:

- The schematic passes the electrical rules check of KiCad with no errors
  and no warnings. The netlist that KiCad exports equals the netlist the
  drawings were generated from (428 parts, 225 nets), and every symbol pin
  has a pad in its footprint (65 pairs of symbol and footprint).
- The netlist was checked independently against the datasheets: symbol,
  footprint and ratings of every part type that is new in this draft, and
  six subsystems as a whole (power, source meter, ampere path, measuring
  chain, controller and logic, and the seams between the blocks). That
  check found no blocker and no major defect. It is not a component check:
  it closes no item of section 16 of the specification. Its notes are not
  filed in this repository, so the result can be read here but not
  inspected: it counts as a review, not as evidence.
- Every line of the bill of materials has a part number and a maker (151
  lines; section 17 of the specification).
- The board is fully connected: 984 of 984 connections. It passes the
  design rules check of KiCad with no rule violation, no unconnected pad
  and no difference between board and schematic ([Checks](#checks)).
- The layout was reviewed against the rules of section 10 of the
  specification: the 1 A path is drawn as pours, a guard surrounds the
  measured node, the Kelvin lines are drawn again, the 5 V rail is a pour
  and two layers carry ground fills. Each block was drawn with scripts and
  then calculated again by an independent check, and a final review of the
  whole board recorded 75 findings, of which 41 are open
  ([Layout Review](#layout-review)).
- The figures of the board are calculated from the drawn copper: squares
  and resistance of a pour, surface leakage with an assumed sheet
  resistance, lengths of tracks and distances between copper. None is a
  measurement. The scripts that calculate the resistance of the 1 A path,
  the lengths of the pairs, the vias on the sense nets and the surface
  leakage are in [`tools/board/`](../tools/board/README.md), so those
  figures can be calculated again from the board file
  ([Reproducing the Figures](#reproducing-the-figures)).
- The seven points in which the board departs from the words of section 10
  of the specification are decisions of the specification, D-87 to D-93,
  accepted by the owner on 2026-10-10 on the recommendation of the layout
  review. Sections 10.3, 10.4, 10.6 and 10.8 of the specification say what
  the board has
  ([list](#decisions-of-the-layout-review-d-87-to-d-93)).
- The notes on the sheets were compared with the specification figure by
  figure and corrected where they differed, and the pictures and the PDF of
  [`doc/`](doc/README.md) are plotted from the present files.

It is not a design to fabricate:

- Nothing has been built and nothing has been measured. Every figure in
  these documents is a datasheet value, a calculation, a simulation or an
  estimate; the specification says which.
- The parts are the candidates of the specification. No component check of
  [`docs/checks/`](../docs/checks/README.md) is closed, and the open checks
  of section 16 of the specification stand, the bench items among them.
- The layout review was done with scripts. Nobody has opened the board in
  the KiCad editor and looked at it as a person does before ordering
  boards.
- Eleven items of the layout are open because they need parts moved or
  another footprint, the loops of the converter capacitors among them, and
  five points of section 10 were not touched by the review, the legends of
  the silkscreen among them.
- The temperature rise of the linear regulator U18 at its full dissipation
  is an open check of section 16 of the specification, to be read on the
  first board: the island of output copper on the top layer is smaller
  than the one the datasheet figure stands for (D-93).
- The files of the simulations are not in `simulation/`, so nobody can
  repeat a figure that the specification marks "simulated".
- The helpers that drew the layout are not in this repository. The board
  file is the record of what was drawn.
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
| `doc/` | Pictures of every schematic sheet and of the board, the schematic as PDF, and the bill of materials of the draft as CSV |
| `simulation/` | Place of the simulation files behind the figures marked "simulated". Empty: none is filed yet ([Still to Do](#still-to-do) lists them) |
| `fabrication/` | Outputs of each revision: Gerber and drill files, bill of materials, placement (empty until a revision is fabricated) |

## KiCad Project

Open `kicad/power-profiler-carrier.kicad_pro` with KiCad 10. To look at the
design without KiCad, see [`doc/`](doc/README.md): every sheet with a
description and the board as pictures, and
[`doc/schematic.pdf`](doc/schematic.pdf).

The board carries the name of the project: the silkscreen text at its
bottom edge reads "Open Power Profiler - Carrier Board   rev A2 draft",
and the title blocks of the board file and of the root page of the
schematic read "Open Power Profiler - Carrier Board". The schematic PDF and
the picture of its root page were exported again with that title; the
other fourteen pages are unchanged.

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
| `+3V3_A` | Low-noise regulator | Converter, comparators, DAC, monitor, reference, buffer of the driver rail, tracking amplifier of the pre-regulator, temperature sensor |
| `+3V3_C` | Regulator | Logic of the carrier, rail monitor, power LED |
| `VREF` | 2.5 V reference, supplied from `+3V3_A` | Converter, DAC, monitor, thresholds, pedestal, driver rail |

A supervisor on `+5V` enables both 3.3 V regulators, the +12 V_A regulator,
the charge pump and, through a transistor, the pre-regulator: below 3.83 V
to 4.00 V on the rail (calculated) the carrier is off, with no firmware
involved (decision D-48). The power tree with its thresholds and its
start-up order is in section 3 of the specification.

The bill of materials is generated from the schematic, in which each of
its parts carries the fields `MPN` and `Manufacturer`: one line per part
number, 151 lines for 368 parts. The positions without parts, the test
points, the mounting holes, the fiducials and the solder jumpers are not
in it. The list of this draft is filed as [`doc/bom.csv`](doc/bom.csv);
to make it again, from `kicad/`:

```sh
kicad-cli sch export bom --output ../doc/bom.csv --fields 'Reference,Value,Footprint,MPN,Manufacturer,${QUANTITY}' --group-by 'Value,Footprint,MPN,Manufacturer' --exclude-dnp power-profiler-carrier.kicad_sch
```

### Board

`power-profiler-carrier.kicad_pcb` is linked to the schematic: every
footprint has its nets and its symbol. All 984 connections are drawn. The
figures of this section are counted or calculated from the board file;
none is measured.

- Outline 150 mm × 100 mm with a corner radius of 3 mm and four M3 holes
  (decision D-85).
- Four copper layers, used as the table below says. All 425 footprints are
  on the top side. The schematic has 428 parts: the two sockets of the
  module (MP1, MP2) sit in the holes of the module footprint, and the cover
  of the shield can (MP3) snaps onto its frame, so these three have no
  footprint of their own.
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
  cannot express ([Design rules check](#design-rules-check)). The classes
  are bound to the names of the nets: after a change to the schematic,
  check that the nets of the 1 A path still have their class.

![Placement of the functional blocks](doc/images/board-placement.png)

#### Placement

The parts were placed by a script, from the netlist and from a table that
gives each part the pin it serves and its largest distance from it.
Connectors, mounting holes, fiducials and the frame of the shield can stand
at fixed coordinates. The result of the run that placed this board:

- Every part is inside the rectangle of its block, no courtyard overlaps
  another, and nothing stands under the controller module.
- Only the 58 parts of the front end are inside the frame of the shield
  can.
- 95.9 % of the 370 distances of the table are kept, taken as the copper
  gap between the two pads, and so are those of all 47 decoupling
  capacitors.

The layout review moved or turned 35 of the 425 footprints, 33 of them by
2.75 mm or less. Two moved farther: the test point of VOUT, TP38, by
11.2 mm onto the pour of VOUT, and the suppressor of VOUT, D21, by 8.6 mm.
No part was added or removed. The reference designators of 123 parts are
hidden on the silkscreen, where no free place was left beside the part (115
after the placing run); they are on the fabrication layer. Nobody has
reviewed the placement by hand, and several
[open items](#open-items) of the layout are placement changes.

#### Routing

The board was first routed automatically with FreeRouting 2.5.0, through a
Specctra export of the placed board and an import of the session file
(decision D-86), in several runs that each continued from the board of the
run before. That autorouted board connected 956 of the 984 connections and
left 28 open, 25 of which broke a function: the 5 V rail was in pieces,
neither mode had a complete current path, and one Kelvin sense line of the
0.1 Ω shunt had no track. Its power nets were tracks of 0.4 mm and 0.5 mm.

The layout review of 2026-10-10 continued from that board. It closed the 28
connections and drew the copper that an autorouter does not draw
([Layout Review](#layout-review)). The board before and now:

| Item | Autorouted board | Now |
| --- | --- | --- |
| Connections | 956 of 984, 28 open | 984 of 984, none open |
| Tracks | 7.83 m in 3,228 segments | 8.38 m in 3,716 segments |
| Vias | 499, of which 26 of 0.8 mm with a 0.4 mm hole | 694: 594 of 0.6 mm with a 0.3 mm hole and 100 of 0.8 mm with a 0.4 mm hole; 336 of them on ground |
| Copper zones | 1, the ground plane | 42: the pours of the 1 A path, the pours of the converters, the 5 V rail, the guard, the ground fills |
| Ground plane | One piece | One piece of 14,205 mm², no track on its layer |
| Ground fills | None | 10,891 mm² on the second inner layer and 12,108 mm² on the bottom layer, stitched to the plane with 41 added vias |
| 5 V rail | Tracks of 0.4 mm | A pour of 1,623 mm² on the second inner layer, in three pieces |
| Reference designators hidden on the silkscreen | 115 | 123 |

The layers as they are used now:

| Layer | What it carries |
| --- | --- |
| `F.Cu`, top | All parts; the pours of the 1 A path and of the converters; the Kelvin lines; the guard ring and its pour; 3.76 m of track |
| `In1.Cu`, first inner layer | The ground plane: one piece, no track. The clearances of vias and through-hole pads open 787 mm² of it in all (593 mm² on the autorouted board, which had 499 vias) |
| `In2.Cu`, second inner layer | The pour of the 5 V rail; 2.84 m of track, among them rail trunks, 41 mm of the ladder output and 64.8 mm of the guard; a ground fill, which those tracks cut into 80 pieces |
| `B.Cu`, bottom | 1.79 m of track; the second layer of the supply band of the 1 A path; the output island of the linear regulator; the two pieces of the 1 A path that have no room on top; the output pour of the pre-regulator; four guard pours under the measured node; a ground fill |

![The four copper layers](doc/images/board-copper.png)

The picture shows the four copper layers side by side, plotted from the
board file: top, ground plane, second inner layer, bottom. Two details of
the top layer are in the next section: the measured node under the shield
can ([`board-front-end.png`](doc/images/board-front-end.png)) and the 1 A
path ([`board-1a-path.png`](doc/images/board-1a-path.png)). The rendered
views are in [`doc/`](doc/README.md); in the top view the gold line around
the front end is the guard under open solder mask.

#### Design Rules Check

The design rules check of KiCad, with schematic parity, reports on this
board 0 rule violations, 0 unconnected pads, 0 footprint errors and 0
differences between board and schematic. The commands are under
[Checks](#checks).

The rule file was rewritten in the layout review and has thirteen rules
now. It asks more than the file the autorouter ran against, so the result
above is not the same statement as "0 violations" on the autorouted board.
In plain words:

- Copper of different nets keeps 0.15 mm, except from pad to pad inside a
  footprint.
- The larger spacings (1 A path, switch nodes, measured node, gate nodes,
  VIN) still leave out a track that touches the courtyard of a footprint,
  because at the pins of a part the pad pitch decides. That exemption now
  applies on the top layer only. Before, it also freed copper on the other
  layers under a part, although every part is on the top side.
- The measured node keeps 0.5 mm from foreign nets on the bottom layer too,
  and there the rule also covers the ladder output.
- The copper fills of other nets keep 1.0 mm from the measured node on the
  two outer layers. On the inner layers a via of the measured node opens
  the ground plane by the normal clearance and not by a hole of 2.6 mm.
- The pours of the measured node keep 1.0 mm from ground and rail copper
  on the outer layers, pads included: a ground pad beside such a pour is a
  leakage path into the node.
- Gate nodes keep 0.5 mm from other nets on both outer layers.
- The VIN input keeps 1.0 mm from other nets on the outer layers and 0.5 mm
  on the inner layers. Section 10.4 of the specification says 1.0 mm from
  every other net.
- The guard may run 0.2 mm beside the measured node: it is driven to the
  potential of that node.

The rewritten rule file is decision D-87, the first of the
[decisions of the layout review](#decisions-of-the-layout-review-d-87-to-d-93).
Two things it does not check: no rule counts the vias on a sense net or on
a guarded net, and no rule spaces the measured node from other copper on
the inner layers, where 41 mm of the ladder output run with the ground fill
0.15 mm beside them. Both were checked by calculation instead.

The project ignores five checks of KiCad, the same five as on the
autorouted board: a footprint without a courtyard, a track end that is not
centered on a via, the tuning profiles, the footprint filters of the
symbols, and the component type of a footprint against its pads.

### Layout Review

The layout was reviewed on 2026-10-10 with scripts that work on the KiCad
board file, block by block. Each block was drawn against the rules of
section 10 of the specification and then checked by an independent check
that calculated every rule again. After that the whole board went through a
final review by rule group, with each finding checked by a second reviewer.
A repair round followed for the leakage paths into the measured node that
this review found, and a last pass calculated every finding again on the
final board.

The final review recorded 75 findings. On the final board 15 of them are
fixed, 16 are improved, 41 are open and 3 are not defects. The sections
below group them: the results by rule, the seven decisions that the review
led to, the open items, and what the review did not touch.

What the review is and is not:

- It is a drawn and calculated layout. Every figure below is calculated
  from the drawn copper with scripts; the level of evidence is a
  calculation, in a few places with stated assumptions.
- It is not a look at the board by a person. Nobody has opened it in the
  KiCad editor.
- Nothing is built and nothing is measured. Every part is still a
  candidate.
- The scripts that calculate the figures are in this repository
  ([Reproducing the Figures](#reproducing-the-figures)). The helpers that
  drew the layout are not.

#### Reproducing the Figures

The package [`tools/board/`](../tools/board/README.md) calculates the
figures of the layout from the board file: the resistance of the copper of
a net between pads, a path on one layer alone, the lengths of the two lines
of a pair along their center lines, the vias on the sense and guarded nets,
and the surface leakage into the measured node. What is specific to this
board (the pieces of the 1 A path, the three pairs, the nets of the
measured node, the assumed voltages, the rectangle of the shield can) is in
`tools/board/carrier.toml`. The package is tested on small synthetic
boards with answers known by hand, without KiCad and without hardware.

Three steps, each described in the
[README of the package](../tools/board/README.md):

1. Install the package into an environment of its own, from `tools/board/`.
2. Dump the board file to JSON with `tools/board/kicad/dump_board.py`. This
   step runs under the Python that KiCad installs, because it reads the
   board with KiCad's own module. Fill the zones and save the board first.
3. Run `board-figures report` on the dump.

From the root of the repository:

```sh
"$KICAD_PYTHON" tools/board/kicad/dump_board.py hardware/kicad/power-profiler-carrier.kicad_pcb tools/board/board.json
cd tools/board
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/board-figures report board.json
```

`KICAD_PYTHON` stands for the path of the Python interpreter of the KiCad
installation. On Linux and macOS the folder of the environment is
`.venv/bin/` in place of `.venv/Scripts/`. The report reads
`carrier.toml` from the working directory, which is why it runs in
`tools/board/`. On the board in this directory the report prints:

| Figure | Report |
| --- | --- |
| 1 A path, source mode | 19.5 squares, 10.4 mΩ at 40 °C, with its seven pieces |
| 1 A path, ampere mode | 23.3 squares, 12.3 mΩ at 40 °C, with its eight pieces |
| Surface leakage, top layer | 4.46 nA, of which 0.73 nA inside the shield can |
| Surface leakage, bottom layer | 0.67 nA, of which 0.00 nA under the can |
| Kelvin pair of range 3 | 46.31 mm and 45.42 mm, difference 0.89 mm |
| Kelvin pair of range 2 | 28.35 mm and 27.78 mm, difference 0.56 mm |
| Pair from the multiplexer to the amplifier | 17.01 mm and 17.89 mm, difference 0.88 mm |
| Sense and guarded nets | 10 of 11 without a via |

The report also gives the share of the track length at the class width,
the tracks near the mounting holes and the ground vias at the lands of the
shield can. The other figures of this guide (the loops of the converters,
the 5 V rail, the copper of the reference, distances between copper) are
calculated with the commands `squares` and `path` of the package, one net
at a time, or were calculated in the review and are not part of the report.

The limits of the calculation:

- The resistances are calculated on a grid of 0.1 mm. On a grid of 0.05 mm
  the two sums read about 2 % higher: 19.9 squares and 23.8 squares.
  Compare figures made with the same grid only.
- A via counts 1.7 squares for each step from one layer to the next. That
  overstates a via, so the figure errs to the high side.
- The resistances count copper only: the transistors, the shunt, the fuse
  and the terminal are not in them, nor are solder and the heating of the
  copper by its own current.
- The leakage figure is converged at its grid of 0.04 mm. It rests on an
  assumed sheet resistance of 10¹¹ Ω per square and on assumed voltages.
  It leaves out the solder mask, flux residue, moisture and dust, the
  leakage through the laminate to the inner layers, and the leakage of the
  parts themselves. A real surface can be orders of magnitude off the
  assumed value in either direction: the figure ranks layouts and shows
  where the current would come from, and it is not an error budget.
- Every figure compares one layout with another. None predicts what a
  bench will read, and a measurement replaces it.

The helpers that drew the layout (the routing and merging scripts of the
review) are not in this repository; the board file is their result. The
simulation files are not in the repository either
([File the Simulations](#3-file-the-simulations)).

#### Results by Rule

The column "Autorouted board" gives the figure of the board before the
review where one was calculated. Where it says "at the final review", the
figure is that of the board after the blocks were drawn and before the
repair round.

| Rule | Limit in the specification | Autorouted board | Now |
| --- | --- | --- | --- |
| 1 A path in source mode, output of the linear regulator to the VOUT terminal | 30 squares of 35 µm copper (10.4) | 397 squares, about 211 mΩ | 19.5 squares, 10.4 mΩ at 40 °C |
| 1 A path in ampere mode, VIN terminal to the VOUT terminal | 30 squares of 35 µm copper (10.4) | 217 squares, about 116 mΩ | 23.3 squares, 12.3 mΩ at 40 °C |
| Surface leakage into the measured node | Leakage budget of 10 nA (4.3, 10.3) | Not calculated; about 20 nA at the final review (top layer 11 nA, bottom layer 9 nA) | 5.1 nA: top layer 4.46 nA, bottom layer 0.67 nA |
| Sense and guarded nets without a via | No via (10.3) | Not counted; one sense line of the 0.1 Ω shunt had no track | 10 of 11 on the top layer without a via; the eleventh keeps two vias and 1.9 mm on the second inner layer |
| Kelvin pair of range 3, 0.1 Ω shunt to the multiplexer | Tracks of 0.2 mm at a gap of 0.2 mm, one layer, equal within 1 mm, no via (10.3) | One of the two lines open | 46.3 mm and 45.4 mm, 0.9 mm apart in length; side by side at 0.2 mm over 83 % of the run; one line has the two vias |
| Kelvin pair of range 2, 1 Ω shunt to the multiplexer | As above | Not calculated | 28.4 mm and 27.8 mm, 0.6 mm apart in length; top layer, no via; not side by side |
| Pair from the multiplexer to the amplifier | As above | Not calculated | 17.0 mm and 17.9 mm, 0.9 mm apart in length; side by side over about 4 mm only |
| Taps of range 0 (1 kΩ) and range 1 (33 Ω) | Sensed at the pads, the tap leaving the pad as its own track (10.3) | Not calculated | Each tap leaves its pad as its own track, then runs through a via and 12 mm and 10 mm on the second inner layer; not pairs |
| Guard | A closed track of 0.5 mm on the top layer, no solder mask over it (10.3) | None | One piece of copper: three arcs on the top layer, joined through 11 vias on the other layers; inside the can 109 mm at 0.5 mm, 24 mm at 0.25 mm and 7 mm at 0.15 mm; solder mask open over 160 of 190 mm (84 %); a guard pour of 227 mm² |
| Ground copper beside the pours of the measured node, outside the can | 1.0 mm (10.3) | Not calculated; 0.15 mm at the final review | None within 1.0 mm; the ground pad of the VOUT suppressor is 1.55 mm away |
| Gate node of the output switch to VOUT copper | 2 mm except at the gate pins (10.3) | Not calculated; 0.56 mm at the final review | 2.0 mm or more except at the two gate pins |
| Test point of VOUT, TP38 | 3 mm or more from any other pad (10.7) | Not calculated; 1.50 mm at the final review | On the VOUT pour, 3.03 mm from the nearest pad |
| Ground via at each land of the shield can | One beside each land (10.3) | Not counted | All 32 lands have a ground via within 1.5 mm |
| Pre-regulator, switch nodes and ground pad | Short pours from pad to pad; six vias in the power ground pad (10.5) | Tracks | Both switch nodes are pours without a via; six vias in the pad |
| Pre-regulator, feedback line | 20 mm or less (10.5) | Not calculated | 16.4 mm |
| Pre-regulator, copper from the output capacitors to the bead | 15 mΩ or less (10.5) | Not calculated | 13.4 squares, 7.1 mΩ, on the bottom layer through groups of vias |
| Pre-regulator, loops of its five capacitors | 5 mm or less on the top layer (10.5) | Not calculated | 8.2 mm to 17.1 mm: not kept |
| Pre-regulator, inductor to the switch pins | Within 3 mm (10.5) | Not calculated | 4.5 mm from its second pair of switch pins: not kept |
| Boost converter, loop of switch pin, diode, output capacitor and ground pin | Within 5 mm (10.5) | Not calculated | 6.8 mm through the 10 µF capacitor and 10.3 mm through the 100 nF capacitor: not kept |
| Boost converter, output to the filter resistor of the +12 V regulator | One track of 25 mm or more (10.5) | Not calculated | One track of 28.8 mm |
| Charge pump, capacitors to their pins | Within 2 mm (10.5) | Not calculated; two of its connections were open | Flying capacitor and supply sides 0.9 mm to 1.3 mm; the ground sides of two capacitors 3.4 mm and 4.4 mm: not kept |
| +12 V regulator | Output sense pin routed to the pad of the output capacitor; a guard track around the copper of the SET pin (10.5) | Not checked | Sense pin routed to the pad; +12 V copper faces 75 % of the contour of the SET copper and is open at the pins |
| 5 V rail, bulk capacitor to the input capacitors of the pre-regulator | 10 mΩ, a target of the layout review; the specification gives no figure (10.1) | Tracks of 0.4 mm, the rail in pieces | 2.7 mΩ and 3.0 mΩ |
| 5 V rail, bulk capacitor to the input capacitor of the boost converter | 25 mΩ, a target of the layout review; the specification gives no figure (10.1) | Tracks of 0.4 mm, the rail in pieces | 3.6 mΩ |
| Reference | The output pin is the star point; the branches share no track (10.5) | Not checked | Ten branches that share no track beyond the star copper; that copper, 5.7 mm long, is common to several: 2.2 mΩ between the branch of the ADC and the pedestal divider |
| Track widths | The width of the net class | Rails, guard nets and gate drivers 0.25 mm or less; power nets 0.4 mm and 0.5 mm | Share of the track length at the class width or wider: rails (0.4 mm) 62 %, gate drives (0.3 mm) 71 %, power input nets (1.0 mm) 34 %, sense nets (0.2 mm) 100 % |
| Thermal reliefs | Only on the ground pads of through-hole parts; none on a pad of the 1 A path (10.4, 10.6) | Not checked; 21 such pads joined solid into the plane at the final review | Reliefs on the through-hole ground pads of the connectors, the module sockets and the reset switch, in the plane and in the fills; the pads of the 1 A path joined solid |
| Mounting holes | No track on an outer layer within 4.0 mm of the center (10.1) | Not checked | Kept |

#### The 1 A Path

![The 1 A path on the top layer](doc/images/board-1a-path.png)

The picture is the top layer from the linear regulator at the bottom left,
along the supply band to the shunt branch, the output switch and the
terminal block on the right. The path is drawn as pours on the top layer.
The supply band, 38 mm from the source pair to the shunt branch, is doubled
on the bottom layer through groups of four to eight vias of 0.8 mm with a
0.4 mm hole. The linear regulator U18 stands on an island of output copper:
291 mm² on the bottom layer and 102 mm² on the top layer, joined by 22
vias.

The pieces, in squares of 35 µm copper, calculated from the drawn copper:

| Piece | Source mode | Ampere mode |
| --- | --- | --- |
| Output of the linear regulator to the source pair | 2.2 | |
| Common source of the source pair | 0.4 | |
| VIN terminal to the fuse | | 3.5 |
| Fuse to the ampere pair | | 8.0 |
| Common source of the ampere pair | | 0.3 |
| Supply node | 6.5 | 1.0 |
| Range 3 transistor to the 0.1 Ω shunt | 1.3 | 1.3 |
| Ladder output, from the shunt to the output switch | 5.6 | 5.6 |
| Common source of the output pair | 0.6 | 0.6 |
| VOUT to the terminal | 2.9 | 2.9 |
| Sum | 19.5 | 23.3 |
| Resistance at 40 °C | 10.4 mΩ | 12.3 mΩ |

The pieces are printed to one decimal. The pieces of ampere mode add to
23.25 squares before that rounding, which is 23.3 squares.

The figures count copper only: the transistors, the shunt, the fuse and
the contacts are not in them. They end at the poles of the terminal block,
where R-06 takes the path drop. The pin header is fed from the terminal
block through two tracks of 1.0 mm, 10.2 mΩ on VOUT and 11.2 mΩ on VIN
(calculated): a load on the pin header sees about 21 mΩ more copper than a
load on the terminal block.

The tracks of the 1 A net classes that remain on the board are taps and
links, not the path. In the last step of the review 1,069 tracks of the
board were widened toward the width of their net class where the copper
around them left room, and the 41 track ends that entered 19 pads wider
than the pad were necked down to the pad.

#### The Measured Node

![The measured node under the shield can](doc/images/board-front-end.png)

The picture is the top layer under the shield can in red, with the
openings of the solder mask in pink: the guard ring, the guard pour, the
Kelvin lines from the multiplexer to the shunts, and the lane of the
range 3 pair outside the can.

Surface leakage. The figure of 5.1 nA is calculated with the assumptions
that section 10.3 of the specification uses: 10¹¹ Ω per square on a clean
surface, 5 V to ground and logic, 7 V to the +12 V rail and to gate nodes,
9 V to the −4 V rail. Solder mask, cleanliness and humidity are not
modeled. Of the 4.46 nA on the top layer, 0.73 nA are inside the shield can
and 3.73 nA outside; of the 0.67 nA on the bottom layer, 0.00 nA are under
the can. The largest shares:

| From | Share |
| --- | --- |
| Gate of the output pair | 1.35 nA |
| Ground | 1.32 nA |
| Copper of the VIN terminal | 0.98 nA |
| Gate of the range 3 transistor | 0.62 nA |
| +12 V at pin 14 of the multiplexer | 0.47 nA |
| −4 V at pin 2 of the guard buffer | 0.26 nA |

Almost all of it is the pitch of pads: the gate beside the source in the
transistor package, the poles of the two DUT connectors, neighboring pins
of the multiplexer and of the guard buffer. No track can change that; what
is left is another footprint or cleaning. An estimate made before the board
was drawn gave 1.3 nA to 2.9 nA; section 10.3 of the specification now
carries the figure calculated from the board and names that estimate.

Sense lines. Ten of the eleven sense and guarded nets are on the top layer
without a via. The eleventh is the high-side sense line of the 0.1 Ω shunt:
with the pin order of the multiplexer and the pad order of the
four-terminal shunt, the two lines of that pair have to cross once, and no
rotation of a part changes that. The lengths in the table are taken along
the center lines from pad edge to pad edge. The pair of range 2 is equal in
length but not side by side, because the pair of range 3 runs between its
two lines under the multiplexer. The pair to the amplifier is side by side
over about 4 mm only, because its pins are on opposite sides of both
packages.

Guard. The guard is the buffered ladder output and is one piece of copper.
On the top layer it is three arcs around the measured node inside the can.
They are cut where the measured node itself leaves through the wall: the
ladder output, the supply node and the range 3 pair. A guard track runs on
both sides of each exit, and along both sides of the range 3 pair outside
the can as far as the shunt. The arcs are joined through 11 vias, with
12.8 mm of track on the bottom layer and 64.8 mm on the second inner layer,
of which 53 mm are the feed of the monitor. Four guard pours on the bottom
layer surround the via pads of the measured node. The solder mask stays
closed over the guard at the six wall crossings and between pads on
purpose, and no bare guard lies within 0.3 mm of a land of the can. The
free top copper inside the ring is a guard pour, under solder mask except
at the ring. Inside the ring there is no ground pour, but 29 pads of 10
foreign nets stand there, the supply, address and enable pins of the
multiplexer and their parts, and 18 vias.

Off the top layer. The ladder output has no track on the bottom layer any
more (37 mm at the final review). It has 41 mm on the second inner layer:
the two taps and the load track of the 1 Ω shunt, with the inner ground
fill 0.15 mm beside them, which is laminate and not a surface. Its six via
pads on the bottom layer stand in guard pours; the nearest foreign copper
to one of them is 0.81 mm away.

#### Decisions of the Layout Review (D-87 to D-93)

The reviewed board departs in seven points from what section 10 of the
specification said before the review. The owner accepted the
recommendation of the layout review on all seven on 2026-10-10. They are
recorded in the decision log of the specification (section 15) as D-87 to
D-93, and sections 10.3, 10.4, 10.6 and 10.8 of the specification now
describe the board as it is drawn. The log has 93 decisions.

Each point below quotes the sentence that section 10 carried before the
review, says what the board has and why, and names the decision. The
figures in the reasons are calculated from the drawn copper; a decision
accepts a drawn layout, not a measured one.

1. **The rule file (D-87).** `kicad/power-profiler-carrier.kicad_dru` was
   rewritten, as [Design Rules Check](#design-rules-check) says rule by
   rule. Section 10.4 said of the VIN copper that it "keeps 1.0 mm from
   every other net"; the rule file asks 1.0 mm on the outer layers and
   0.5 mm on the inner layers. Reason: an inner layer has no surface that
   joins the two nets, and the larger spacing there only opens the ground
   plane. The other changes make the file stricter, or let the guard run
   0.2 mm beside the node it guards. A custom rule that matches replaces
   the clearance of a zone and of a net class, and the old exemption near
   pins had hidden 32 places where the measured node or the VIN input
   stood too close to other copper. The decision: the rule file states
   every spacing that the layout needs. The exemption near pins applies on
   the top layer only; the 0.5 mm of the measured node apply on the bottom
   layer too, there also to the ladder output; gate nodes keep 0.5 mm on
   both outer layers; the VIN input keeps 1.0 mm on the outer layers and
   0.5 mm on the inner layers; copper fills keep 1.0 mm from the measured
   node on the outer layers; the pours of the measured node keep 1.0 mm
   from ground and rail copper, pads included; the guard may run 0.2 mm
   beside the measured node.
2. **Vias on one sense line (D-88).** Section 10.3 said "No via on a
   sense net or on a guarded net." The high-side sense line of the 0.1 Ω
   shunt R110 has two, with 1.9 mm on the second inner layer at the shunt.
   Reason: the pin order of the multiplexer against the pad order of the
   four-terminal shunt forces the two lines of the pair to cross once, and
   no rotation of a part changes that. The decision: that line keeps its
   two vias and its 1.9 mm on the second inner layer, and its two via pads
   on the bottom layer stand in a guard pour. It is the one sense net with
   a via.
3. **Kelvin pairs (D-89).** Section 10.3 asked for "a tightly coupled pair
   from each shunt to the multiplexer U24 and from there to the amplifier
   U27: tracks of 0.2 mm with a gap of 0.2 mm, on one layer, equal in
   length within 1 mm, without a via." The lengths are equal within 1 mm
   in the three pairs. But the taps of ranges 0 and 1 run through a via
   each and on the second inner layer, the pair of range 2 is not side by
   side, and the pair to the amplifier is side by side over a quarter of
   its length. Reason: the pin order of the multiplexer nests the pairs
   under its package, so only the innermost pair can run side by side,
   and the two pins of a pair are on opposite sides of the multiplexer and
   of the amplifier. The decision: the pair of R110 runs side by side at
   0.2 mm; the pair of R107 and the pair from U24 to U27 are equal in
   length within 1 mm and run side by side only where the pins allow; the
   taps of R101 and R104 leave their pads as tracks of their own and run
   through one via each on the second inner layer.
4. **The guard is not a closed ring on one layer (D-90).** Section 10.3
   said "It is a closed track of 0.5 mm on the top layer" and "The guard
   is on the top layer only." The guard is open at the three exits of the
   measured node, its arcs are joined on the other layers, parts of it are
   0.25 mm and 0.15 mm wide, and guard pours exist on the bottom layer.
   Reason: the measured node has to leave the ring on the top layer, the
   bottom pours shield the via pads of the node from the ground fill, and
   bare guard beside a soldered land of the can would bridge to ground at
   assembly. The decision: the guard is one piece of copper, open on the
   top layer at the three places where the measured node leaves the shield
   can, with a guard track on both sides of each exit and of the range 3
   pair outside the can as far as the shunt. Its arcs are joined through
   vias with tracks on the bottom layer and on the second inner layer, and
   guard pours on the bottom layer surround the via pads of the measured
   node. The solder mask is closed over the guard at the wall crossings
   and between pads.
5. **Foreign nets inside the ring (D-91).** Section 10.3 said "no ground
   pour and no foreign net inside the ring." There is no ground pour, but
   the supply, address and enable pins of the multiplexer and their parts
   are inside. Reason: the pins of the multiplexer are inside by
   necessity, and moving their parts outside would lead their nets across
   the guard on the top layer. Their share of the calculated leakage is
   0.47 nA, at pin 14 of the multiplexer. The decision: the supply,
   address and enable pins of U24 and the parts at those pins stand inside
   the guard, and no ground pour lies inside it.
6. **Width and layer of the 1 A pours (D-92).** Section 10.4 asked for
   "pours on the top layer, 4 mm to 8 mm wide". The sums are under
   30 squares, but pieces are narrower: 1.2 mm on top at the source pair,
   where the bottom band is 4.9 mm, and 2.0 mm to 2.9 mm at the poles of
   the terminal block and at test points. Two pieces run on the bottom
   layer because parts stand in the way on top: the output of the linear
   regulator to the source pair, and the fuse to the ampere pair. Clearing
   them is a change of placement. The decision: the 1 A path is judged by
   its resistance, 30 squares or less in either mode (the drawn path has
   19.5 squares and 23.3 squares). Its pours are 4 mm to 8 mm wide where
   the parts leave room and narrower at pins, test points and connector
   poles, and the two pieces named above run on the bottom layer through
   groups of vias.
7. **Top island of the linear regulator (D-93).** Section 10.6 asked for
   "an island of output copper of at least 15 mm × 15 mm on the top layer
   and the same on the bottom layer". The bottom layer has 291 mm²; the
   top layer has 102 mm². Reason: parts stand around the regulator on the
   top layer. The decision: the island under U18 is 291 mm² on the bottom
   layer, joined by 22 vias to 102 mm² on the top layer. The datasheet
   figure of 65 K/W is for 225 mm² of top copper, so the temperature rise
   of U18 at its full dissipation is an open check of section 16 of the
   specification, to be read on the first board
   ([Close the Open Checks](#4-close-the-open-checks)).

Three things that the decisions do not do. They do not close an
[open item](#open-items): those are places where the board does not keep a
rule that still stands. They do not replace the look of a person at the
board in the KiCad editor. And they rest on calculations: where a decision
quotes a leakage or a resistance, a measurement on the first board
replaces the figure.

#### Open Items

These need parts moved or another footprint, and the review did not do
that. Every figure is calculated from the drawn copper. Each item says
what would close it.

- **Loops of the converter capacitors.** Pre-regulator: the loops of its
  five capacitors close on the top layer only over 8.2 mm to 17.1 mm
  (limit 5 mm), because their ground pads face away from the converter;
  each has a ground via 0.15 mm to 0.20 mm from its pad into the plane.
  Boost converter: 6.8 mm and 10.3 mm (limit 5 mm). Charge pump: the ground
  sides of two capacitors are 3.4 mm and 4.4 mm from the pin (limit 2 mm).
  To close: turn or place the capacitors again so that their ground pads
  face the ground pad of the converter. The other way is a decision that
  the return runs through the vias and the plane, with the ripple measured
  on the phase 1 prototype.
- **Inductor of the pre-regulator.** 4.5 mm from its second pair of switch
  pins (limit 3 mm). To close: turn or move the inductor so that its pad
  faces those pins.
- **Temperature sensor U39.** 5.1 mm from pad to pad and 7.7 mm from
  center to center from the linear regulator (limit 5 mm). To close: move
  it 0.2 mm toward the regulator, or have section 10.6 say between which
  points the 5 mm are taken.
- **Suppressor of VOUT, D21.** Its cathode copper is 93 mm² (1 cm² asked),
  and it stands 8.6 mm from the VOUT pole, where section 10.4 describes it
  between the poles at 4.3 mm. It was moved away from the poles to keep
  ground 1.0 mm from the VOUT pour. To close: enlarge the VOUT pour by
  7 mm², and have section 10.4 describe the part where it stands, or place
  it again.
- **Ladder clamps Q10 and Q11.** 21 mm² and 28 mm² of supply-node copper
  lie within 5 mm of their drains (1 cm² asked), and the strip to one
  clamp is 0.6 mm wide. To close: more copper at the drains, which needs a
  resistor and a gate track moved, or a sentence in section 10.6 that the
  1 cm² is the whole supply pour.
- **Drain pad of the ampere pair on the VIN side.** The pad of that
  transistor lies in no top pour: the whole current of ampere mode enters
  through four vias of 0.6 mm with a 0.3 mm hole in the pad. To close:
  move the parts that stand between the pour and the pad, and use vias of
  0.8 mm with a 0.4 mm hole. It is the piece from the fuse to the ampere
  pair, which decision D-92 lets run on the bottom layer.
- **Openings of the ground plane.** Where the clearances of a group of
  vias merge, the plane opens: up to 4.7 mm × 2.3 mm under the island of
  the linear regulator. With 694 vias instead of 499 the plane has 787 mm²
  of openings in all, against 593 mm² on the autorouted board. To close: a
  via pitch of 1.5 mm in the groups keeps webs of plane between the vias.
- **Star of the reference.** The branches should leave the output pad
  itself; two parts stand in the way, and 5.7 mm of copper with 2.2 mΩ are
  common to the branch of the ADC and the pedestal divider. To close: move
  one of the two parts, or record the common 2.2 mΩ as a decision.
- **Distance of the +12 V regulator.** It is 22 mm, courtyard to
  courtyard, from the diode and the capacitor of the boost converter;
  25 mm are asked and are kept from center to center only. To close: move
  the regulator, or have section 10.1 say that the 25 mm are from center to
  center.
- **Vias in or at pads that get solder paste.** 4 via holes on a pad edge
  and 14 via rings on a pad; via holes also in the drain pads of two
  transistors of the 1 A path. To close: move the vias clear of the pads,
  or accept them in writing with a line in the assembly notes (holes
  filled and capped, or a stencil that allows for them).
- **Pads entered by a wider track.** 19 pads were entered by a track wider
  than the pad. The 41 track ends were necked down in the last step of the
  review; the item stays on this list until a person has looked at those
  pads.

Smaller findings of the final review stay open beside these, among them:
the pour of the 5 V rail is in three pieces and the three 3.3 V regulators
hang on two single vias; the six vias in the power ground pad of the
pre-regulator are of 0.6 mm with a 0.3 mm hole, where section 10.1 gives
0.8 mm with a 0.4 mm hole for power; and five tracks have an acute corner.

#### Not Touched by the Review

These points of section 10 of the specification are as they were on the
autorouted board:

- 32 of the 40 signal test points have no probe ground within 5 mm
  (section 10.7).
- The net names of the test points and the function of the two solder
  jumpers are not on the silkscreen (section 10.2), 123 reference
  designators are hidden, and there is no frame for a hand-written serial
  number (section 10.7).
- The three acquisition lines enter the shield can at three places on two
  layers instead of through one opening (section 10.1).
- 21 nets cross the wall of the can below the ground plane, where
  section 10.3 lets tracks cross only on the top layer. The second inner
  layer carries 2.84 m of track, so its ground fill is in 80 pieces.
- The two resistor pairs of the set-point path do not stand side by side
  (section 10.1).

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
is started, by hand only (decision D-22). It fails on any error of the
electrical rules check, on any rule violation of the board (warnings
count), on any footprint error and, since the layout review, on any
unconnected pad. The results below are from local runs.

```sh
kicad-cli sch erc --severity-all power-profiler-carrier.kicad_sch
kicad-cli pcb drc --schematic-parity --severity-all power-profiler-carrier.kicad_pcb
```

Results on the files of this draft, with KiCad 10.0.0 on 2026-10-10:

| Check | Result |
| --- | --- |
| Electrical rules check | 0 errors, 0 warnings |
| Design rules check, rule violations | 0 |
| Design rules check, footprint errors (difference between board and schematic) | 0 |
| Design rules check, unconnected pads | 0 |

The design rules check compares the board with its rules and with the
schematic. Before a board is ordered it must report no rule violation, no
difference between board and schematic and no unconnected pad. It reports
that now, against the rule file that the layout review rewrote
([Design Rules Check](#design-rules-check) says what the file asks and
which five checks the project ignores). On the autorouted board the same
check listed 28 unconnected items.

Three corrections stood behind the result of the autorouted board. The
autorouter had left five pairs of vias
0.493 mm to 0.499 mm apart; each pair was moved apart by less than 0.01 mm.
The pattern that binds one net to its net class was corrected. And the
stackup of the board file was set to the build of section 10.1 of the
specification.

Both checks were run with `kicad-cli` only. The project has not been opened
in the KiCad editor yet. The checks say that the files are consistent and
that the copper keeps the rules of the rule file. They do not say that the
layout is good: a rule file holds spacings, not the length of a converter
loop, the squares of a pour or the leakage into a node. Those were
calculated in the [layout review](#layout-review), and what that review
left open is listed there.

### Still to Do

This is the hardware part of the next steps that the
[README](../README.md#project-status) of the repository puts in order: the
board first (items 1 and 2 here), then the software, which the
[firmware guide](../firmware/README.md) and the
[host guide](../host/README.md) list, then the simulation files (item 3).
The checks that need parts or a bench (item 4) and the work that waits for
firmware (item 5) belong to the phases that follow.

Three steps of the earlier lists are done. The 28 connections that the
autorouter had left open were closed in the layout review of 2026-10-10;
this guide no longer carries their list and their map. The seven
deviations of the reviewed board are decided
([D-87 to D-93](#decisions-of-the-layout-review-d-87-to-d-93)). And the
scripts that calculate the figures of the board are filed in
[`tools/board/`](../tools/board/README.md).

#### 1. Review the Board in KiCad

- A person opens the project in the KiCad editor and reviews the board.
  Until now every check ran from the command line and every figure comes
  from a script.
- That review reads the placement and the copper against the rules of
  section 10 of the specification, and compares a 1:1 print with the
  module on its sockets, the USB-C connector, the terminal block, the frame
  of the can and one of the 1 A transistors (section 10.8).

#### 2. Close the Open Items and Finish the Silkscreen

- The [open items](#open-items) that the owner wants closed are placement
  changes with a local redraw: the capacitors of the three converters and
  the inductor of the pre-regulator, the temperature sensor, the suppressor
  of VOUT, the ladder clamps, the drain pad of the ampere pair, the star of
  the reference, the via groups over the ground plane, the vias at pasted
  pads.
- The points that the review [did not touch](#not-touched-by-the-review):
  probe grounds at the test points, the net names of the test points and
  the functions of the jumpers on the silkscreen, a frame for the serial
  number, one opening for the acquisition lines, the resistor pairs of the
  set-point path.
- Calculate again, after each change, the figures that the change touches
  ([Reproducing the Figures](#reproducing-the-figures)), and run both
  checks. A renamed net or a renumbered part also changes
  `tools/board/carrier.toml`. The board can be ordered only when the
  design rules check reports no violation, no difference between board and
  schematic and no unconnected pad, and when a person has reviewed it.

#### 3. File the Simulations

`simulation/` is empty. The figures that the specification marks
"simulated" rest on files that are not in this repository. Until the files
are here, such a figure can be read but not repeated, and nobody can see
which models, which assumptions and which corner cases stand behind it.
The scripts behind the figures that this guide marks "calculated from the
drawn copper" are filed, in [`tools/board/`](../tools/board/README.md);
they are no longer part of this step.

The simulations, block by block:

| Block | Section of the specification | Figures that rest on a simulation |
| --- | --- | --- |
| Rails, start and stop | 3, 4.7, 4.11 | Order of the rails at power-up with datasheet delays (+12 V_A above 9.85 V after 8 ms to 17 ms, PWR_GOOD about 24 ms after `5V_OK`); order at power-off; levels of the clamps between +12 V_A and −4 V_A (+0.24 V and −0.23 V, D-52); the capacitors at the inputs of the rail monitor, with an estimated pin capacitance; the instants at which firmware sees PWR_GOOD rise and fall |
| Input stage | 4.1 | Behavioral models of the limiters, the multiplexer and the supervisor (D-47, D-48). Hot plug of a live cable (11.4 V and 12.2 V at the connector, 5.51 V or less behind the limiter); a contact that opens and closes again (25 mV to 85 mV below the 6 V rating of the multiplexer inputs); in-rush on a computer port (0.71 A to 0.87 A, 0.44 mC to 0.96 mC); USB-C plugged while the module input supplies (dip to 4.0 V to 4.5 V); the recharge pulse when the multiplexer falls back to the module input |
| Pre-regulator loop and linear regulator | 4.2 | Phase margin of the tracking amplifier (73° to 77°, with the model of its maker) and of the converter loop (55° or more, with a behavioral model); fold-back at a short circuit (0.84 V); set-point step down (IN pin 0.44 V above the output); power returned to the 5 V rail (0.12 W to 0.20 W for about 5 ms, 0.06 W on a set-point step); the clamps D11 and D10 with C47 at power-off; source impedance at the IN pin with the damper (0.27 Ω to 0.37 Ω); the regulator on its control pin alone; sag in dropout (4.48 V into 5 Ω) |
| Mode switches and output switch | 4.2 | A mode pair closing as a follower (supply node at about 0.9 V/ms) and opening within 1 µs; ramp of the output switch (0.44 V/ms, 90 % after about 20 ms), in-rush of 0.39 A into 1000 µF and 0.85 A into 2200 µF, largest DUT capacitance without a trip; opening in 7 µs; the gate charging current in the reading (0.5 µA at 30 ms, 4 nA at 200 ms) |
| Shunt ladder, load step | 2 (R-07), 4.3 | Drop on a step from 1 µA to 500 mA (312 mV nominal and 422 mV worst case with 1 µF at the DUT, 169 mV and 186 mV with 10 µF); the damper of the supply node (node below 11.5 V at a trip, sag of 0.17 V to 0.21 V); the ladder clamp at a hot plug or a short circuit (8.8 A in each part, 14.2 A in one); the sweep of the multiplexer on-resistance, 125 Ω to 430 Ω |
| Range change and trip | 4.4 | Range 3 conducting 0.35 µs after the threshold (0.20 µs to 0.51 µs) with a sequencer of 100 ns; what the blanking of 2 µs has to cover; the times behind the trip qualification (8.6 µs of recharge after a step to 1.0 A, 12 µs to 29 µs with long leads, 2.1 µs with 100 µF at the VIN terminals) |
| Signal chain | 4.5, 4.10 | Settling after a range change (about 45 µs to 0.1 % and 65 µs to 1 LSB; 37 µs to 50 µs and 64 µs to 70 µs over the cases); phase margin of the buffer of the driver rail (54° with its 10 Ω); the converter input in overload (VREF + 0.20 V in the worst case); noise in range 0 (about 2.1 nA from a quiet supply, 26 nA to 27 nA in source mode, 1.1 nA to 3.9 nA for the mean of 100 samples) |
| VIN protection | 4.9 | The terminal at −20 V to +20 V with the ampere pair open (less than 1 mA; the 30 V rating reached for tens of nanoseconds at the plug-in edge); a supply that steps to ±20 V with the pair closed (9.2 V and −2.4 V at the DUT); the interlock with both requests high; a pair closing on a live supply; the supply node at a trip (0.5 V or more below +12 V_A); 125 µA taken from the supply in ampere mode |
| VOUT terminal | 4.9 | The suppressor at a trip (11.6 A forward, terminal at −0.8 V to −1.7 V, with an assumed forward curve); a charged DUT plugged into a live output (regulator input 0.32 V to 0.94 V below its output for 3 µs to 21 µs) |
| Digital inputs | 4.8 | Clamp of the translator supply (−0.40 V at 0 °C and at 27 °C; −0.44 V with 470 Ω in place of 1 kΩ) |
| Output switch, heat | 10.6 | About 25 mJ and 3.5 W in the output pair for milliseconds each time the output is switched on into a capacitive DUT |
| Converter lines | 15 (D-75) | The lines of the converter driven into a dead supply for up to 0.1 ms at power-off |

The list is made from a search of the specification for "simulated"; the
specification is the reference where the two differ. Each set of files
needs the circuit, the models with their source, the corner cases and the
result that the specification quotes, so that a run gives the figure again.
The models of the input stage and of the converter loop are behavioral:
section 16 keeps those figures open until they are measured.

#### 4. Close the Open Checks

Section 16 of the specification, tracked in
[`docs/checks/`](../docs/checks/README.md):

- Close the component checks, part by part, each with the comparison of
  pin numbers and land pattern with the datasheet. None is closed.
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
- On the first board, the thermal check of decision D-93: the temperature
  rise of the linear regulator U18 at its full dissipation. Its island of
  output copper is 291 mm² on the bottom layer and 102 mm² on the top
  layer, and the datasheet figure of 65 K/W is for 225 mm² of top copper,
  so the figure has to be read on the board.
- Decide the three positions without parts on the bench.

#### 5. With the Firmware

- Write the PIO programs of the range sequencer and of the acquisition, and
  test them in an emulator. Until they exist the pin assignment of the
  controller is provisional, and a change of it changes the Controller
  sheet and the board.
- The firmware rules that guard hardware (F-1 to F-36, section 6.6 of the
  specification) are part of this design: several limits of the carrier
  hold only with them. None is implemented; the
  [firmware guide](../firmware/README.md) says what exists.

#### After Every Change

- Plot the pictures of `doc/` again after every change to the schematic or
  the board; the commands are at the end of [`doc/README.md`](doc/README.md).
  Export the bill of materials again after a change to the schematic.
- After a change to the schematic, check that the nets of the 1 A path
  still have their net class, and run both checks.

## Design References

In the [specification](../docs/specification.md):

- Section 3: system architecture and power tree.
- Section 4: analog hardware design, from the power input to the error
  budget, and the controller module.
- Section 5: pin map.
- Section 6.6: firmware rules that guard hardware.
- Section 10: PCB and mechanical guidelines.
- Section 15: decisions, D-23 onwards for the drafts, D-47 to D-86 for
  draft A2 and D-87 to D-93 for its layout review.
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
- The layout of draft A2 was reviewed on 2026-10-10. The autorouted board
  had 956 of its 984 connections and 28 open. The review closed them and
  drew the pours of the 1 A path, the guard, the Kelvin lines, the pour of
  the 5 V rail and the ground fills, with scripts and with an independent
  check of every rule. The schematic and the bill of materials did not
  change, and the draft keeps its name. The board departs from the words
  that section 10 of the specification had in seven points; the owner
  accepted them the same day, and they are decisions D-87 to D-93. The
  review left a list of open items ([Layout Review](#layout-review)). The
  scripts that calculate its figures are in
  [`tools/board/`](../tools/board/README.md), and the silkscreen and both
  title blocks carry the name "Open Power Profiler - Carrier Board".

## License

Copyright (c) 2026 Luiz Guilherme Ito.

The design files in this directory are licensed under the CERN Open Hardware
Licence Version 2 - Permissive (CERN-OHL-P v2). See [LICENSE](LICENSE). They
are provided without any warranty, as stated in section 5 of the license.
