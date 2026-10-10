# Changelog

All notable changes to this project are documented in this file.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each entry starts with the area it affects: **firmware**, **hardware**,
**host**, **protocol**, **tools**, **simulation**, **docs** or **repo**.

## [Unreleased]

### Added

- **docs:** system specification with requirements, analog and firmware
  architecture, host protocol, calibration, verification plan, development
  phases, risk register and decision log.
- **docs:** templates and indexes for component checks and phase reports.
- **repo:** monorepo layout with `firmware/`, `hardware/`, `host/`, `tools/`
  and `docs/`.
- **repo:** contributing guide, issue and pull request templates, editor and
  lint configuration, documentation lint workflow.
- **repo:** MIT license for everything outside `hardware/` and CERN-OHL-P v2
  for the hardware design files.
- **protocol:** one definition of the wire protocol in
  `protocol/definition.toml`, with a generator for the firmware and host
  constants and for the test vectors that both codecs must reproduce.
- **firmware:** ESP-IDF project for the ESP32-S3 with the
  hardware-independent core, unit-tested on the PC: CRC, frame encoder and
  parser, sample word, stream payload, command envelopes, the block queue
  between the cores, the settling window, the step-down rule and the device
  state machine. It drives no hardware yet.
- **host:** Python package `s3-power-profiler` with the protocol codec,
  serial and in-memory transports, a device client, a capture reader with gap
  detection, nominal calibration and statistics, a device simulator and the
  `s3pp` command.
- **hardware:** KiCad 10 project of the carrier board with the sockets of the
  development board and the 19 signals between the boards.
- **hardware:** draft A0 of the carrier board: the complete schematic on
  thirteen A4 sheets drawn with wires, and a board file with every footprint
  placed by functional block and no tracks. A review draft with candidate
  parts, not a design to fabricate.
- **hardware:** project symbols for the ADS8860, the MUX509 and the TPS63020,
  and a power-symbol library for the supply rails.
- **hardware:** pictures of every schematic sheet and of the board, and the
  schematic as PDF, in `hardware/doc/`.
- **hardware:** draft A1 of the carrier board. A Raspberry Pi Pico 2 on
  sockets is the only programmable part; two shift registers carry the
  side data; the DUT connects through a pin header and a lever terminal
  block in the pin order of the PPK2, and the logic port has that order
  too. The board is 130 mm × 100 mm with every part placed near the pin it
  serves.
- **repo:** continuous integration for firmware, host software, protocol and
  hardware, with coverage floors and static analysis.
- **hardware:** draft A2 of the carrier schematic: 428 parts on 15 A4
  pages, 14 sheets below the root sheet (D-83). It passes the electrical
  rules check and was checked independently against datasheets; the parts
  stay candidates, and nothing is built or measured.
- **hardware:** input stage with a current limiter on each USB input and a
  priority multiplexer that supplies the 5 V rail from USB-C whenever it is
  present (D-47). A supervisor on the 5 V rail switches the supplies of the
  carrier off as one below 3.9 V (calculated, D-48).
- **hardware:** rail monitor on a sheet of its own: PWR_GOOD comes from
  four comparators that watch 3V3_A, +12 V_A, −4 V_A and the reference
  (D-54).
- **hardware:** VIN protection that withstands −20 V to +20 V while the
  ampere switch is open (simulated), with a bidirectional suppressor, a
  fuse and a detector that refuses to close the switch above 5.46 V
  (calculated, D-60). An interlock transistor keeps the two mode switches
  from closing together (D-62).
- **hardware:** ESD arrays at the CC pins and at the VCC pin of the logic
  port (D-50), test points on the nodes that draft A2 adds, and positions
  without parts for a voltage detector at the boost converter and for a
  damper on the input from the controller module (D-84).
- **hardware:** a project symbol for the input multiplexer TPS2116, and
  project footprints for the lever terminal block and for the controller
  module (D-83, D-85).
- **docs:** one list of the firmware rules that guard hardware, in section
  6.6 of the specification, with the hardware watchdog of the controller as
  the last line of defense (D-81).
- **docs:** the README states where every area of the project stands and
  the next steps in their order, and shows the routed layers, the open
  connections, the placement and the check results of draft A2.
- **hardware:** the bill of materials of draft A2 is filed as
  `hardware/doc/bom.csv`: 151 lines, each with a part number and a maker.
- **docs:** the hardware guide lists the 28 open connections of the
  board one by one, with what each breaks while it is open and a map of
  them, and the simulations whose files have to be filed.
- **docs:** the firmware, host and protocol guides compare the code with
  what the specification of draft A2 asks, item by item, and give the next
  steps of each area; the pages on calibration, tools and test reports say
  what the specification defines today and what is not written.
- **hardware:** two pictures of the reviewed board in
  `hardware/doc/images/`: `board-front-end.png`, the measured node under
  the shield can with the guard and the Kelvin lines, and
  `board-1a-path.png`, the pours from the linear regulator to the terminal
  block. Both are plots of the board file, not photographs.
- **docs:** the hardware guide lists, one by one, the seven points in which
  the reviewed board deviates from the layout guidelines that section 10
  of the specification had for draft A2, each recorded as a decision (D-87
  to D-93), and the open items of the layout that need a part moved or
  another footprint.
- **tools:** the package `board-figures` in `tools/board/`, with a command
  of the same name. It calculates the layout figures that the documents
  quote from a dump of the board file of the carrier: the resistance of
  the copper of a net between pads in squares and in milliohms, a path on
  one layer alone, the center-line lengths of the two lines of a pair, the
  surface leakage into the measured node, and all figures of the carrier
  in one report. What is specific to the carrier board is in
  `tools/board/carrier.toml`, and an adapter that runs under the Python of
  KiCad 10 writes the dump. Every figure it gives is calculated from the
  drawn copper; it measures nothing.
- **tools:** the package is tested without hardware and without KiCad: 260
  tests on small synthetic boards with answers known by hand, 100 % of
  lines and branches covered against a floor of 90 %, ruff, and mypy in
  strict mode. These checks ran locally on Windows. The package brings
  numpy, scipy and shapely as dependencies, for this package only.
- **repo:** the workflow `Tools` runs the checks of `tools/board/` on
  Windows, Linux and macOS and builds and installs the package. Like the
  other workflows it is started by hand (D-22); it has not been started
  yet.
- **docs:** a guide of the board figures in `tools/board/README.md`: how
  to install the package, make the dump and run each command, with the
  method, the assumptions and the limits of each calculation.
- **simulation:** the package `circuit-sim` in `simulation/`, with a
  command of the same name, simulates the circuits of the carrier board
  (D-94). A bench names parts of the schematic by their reference
  designators; the package writes their elements from a snapshot of the
  netlist that KiCad exports, runs the circuit in the ngspice shared
  library that KiCad 10 ships, takes figures from the waveforms, and
  judges each against its limit: a figure of the specification, a rating
  of a datasheet, or a limit that the bench sets and names. It files the
  figures, a graph of the waveforms and the decks, the circuit files
  that the simulator ran, and writes a page for each block from them. No
  part of the board is typed by hand; sources, loads and cables are.
- **simulation:** models of the parts, written for the project from their
  datasheets, each with the source of its figures and a list of what it
  leaves out. 41 benches put them into the test circuits of their
  datasheets; four models have no such bench, and the simulation guide
  names them. The model files of the manufacturers are not in the
  repository, because their licenses do not allow a copy; where a copy is
  present, a second run gives a second value beside the first.
- **simulation:** the results of 2026-10-10 on the netlist of draft A2, in
  `simulation/results/`: 134 benches, 93 on the circuits of the board in
  ten blocks (shunt ladder, signal chain, range logic, source meter,
  output stage, path switching, power input, analog rails, digital lines,
  whole measuring path) and 41 on the models. Of 3162 figures 1834 pass,
  122 fail and 1206 carry no limit; a figure that fails is kept as it is.
  The folder holds 251 graphs and 289 decks. Everything in it is
  simulated: no board is built and nothing is measured.
- **simulation:** what those results say. The central design figures of
  the specification come out again block by block, among them the drop of
  requirement R-07 on a step from 1 µA to 500 mA with 1 µF: 301.9 mV with
  nominal delays, and 388.2 mV with every delay at its limit and the
  capacitor 10 % low, against the limit of 500 mV (simulated). The
  simulations raised four points for a decision before boards are
  ordered: the capacitors of the rail monitor, the buffer of the driver
  rail, the detector position at the boost converter and the damper on
  the module input. The project owner decided them (D-95 to D-98, under
  "Changed"). In fourteen places the simulation and the text of the
  specification differ. Those are not decided, and the specification
  keeps its text there.
- **simulation:** the package is tested: 777 tests, of which 11 need the
  ngspice library, 100 % of lines and branches covered against a floor of
  90 %, the module that loads the simulator excepted, ruff, and mypy in
  strict mode over the package, its tests and the benches. These checks
  ran locally on Windows with Python 3.11 and ngspice 45.2. The package
  brings numpy and matplotlib as dependencies.
- **repo:** the workflow `Simulation` runs the checks of `simulation/` on
  Windows, Linux and macOS, runs the tests that need the simulator with
  the ngspice library of a Linux distribution, and builds and installs the
  package. It does not run the benches. Like the other workflows it is
  started by hand (D-22); it has not been started yet.
- **docs:** a guide of the simulations in `simulation/README.md`: the state
  of the results block by block, what they reproduce, the four points
  that are decided, the places where they differ from the text of the
  specification, what stays for the bench, what the 122 failing figures
  are, the limits of the models, the traps of the simulator, and how to
  set up, run and extend the package.
- **docs:** the README shows the circuit simulations on the front page: a
  row in the status table, the results by block, what they say, and two
  graphs of simulation runs, each called a simulation.

### Changed

- **docs:** the instrument is now two boards: an ESP32-S3-DevKitC-1
  compatible development board plugged into a carrier board (D-14). The
  carrier has its own USB-C power connector (D-15), the slow monitors move to
  an external converter (D-16), and the pin map is rewritten for the headers
  of the development board.
- **docs:** the host protocol gains its exact CRC parameters, the type,
  command, status and event codes, the command arguments and the rules for
  which state accepts which command.
- **docs:** software engineering practices and quality gates (section 18,
  requirement R-17, D-17 to D-21).
- **docs:** the development board is the two-port clone with an N8R2 or
  N16R2 module, 25.40 mm between its header rows; the pin map gains PATH_EN
  on GPIO 35 and a spare line on GPIO 36 (D-23, D-29).
- **docs:** the specification follows the draft schematic: range logic in a
  programmable logic device, −4 V negative rail, dual Kelvin multiplexer,
  comparators on the amplifier output, 0.45 V of pre-regulator headroom,
  buffered ladder output, candidate parts for every block (D-24 to D-38).
- **hardware:** the socket footprint of the development board accepts
  25.40 mm and 22.86 mm between the rows.
- **repo:** the Hardware workflow also checks the board against the
  schematic.
- **repo:** the continuous integration workflows are started by hand
  instead of on every push and pull request (D-22).
- **docs:** the controller is a Raspberry Pi Pico 2 in place of the
  ESP32-S3 development board and of the programmable logic device: range
  logic and sampling clock become PIO programs, the pin map, the firmware
  plan and the phases are rewritten (D-39 to D-43). The firmware in the
  repository is not ported yet.
- **hardware:** reference designators follow the default annotation of
  KiCad (D-45), and the outline shrinks from 160 mm × 100 mm to
  130 mm × 100 mm (D-46).
- **repo:** the repository is renamed to `open-power-profiler`. Its former
  address, `esp32-s3-power-profiler`, redirects to the new one.
- **docs:** the README presents the project as the Open Power Profiler,
  with its connections and the state of each part; the firmware guide
  separates what is valid for the Raspberry Pi Pico 2 from the ESP-IDF
  build of the first plan.
- **host:** the description of the package, its keywords and the help of
  the `s3pp` command no longer name the ESP32-S3.
- **docs:** the specification follows draft A2 of the schematic: decisions
  D-47 to D-86, the open checks of section 16, the phases of section 13
  with three risk prototypes in phase 1, and the layout guidelines of
  section 10.
- **docs:** **BREAKING** seven requirements are re-baselined to the
  figures that the architecture delivers. None of the figures is measured;
  section 2 of the specification states the evidence of each and compares
  it with the PPK2.
  - R-04: RMS noise in the lowest range at most 5 nA in ampere mode from a
    quiet supply and at most 40 nA in source mode (D-59).
  - R-06: total path drop of 200 mV at 1 A in place of 150 mV; the shunt
    drop stays at 100 mV (D-64).
  - R-07: on a step from 1 µA to 500 mA the instrument adds at most 0.5 V
    of drop with 1 µF at the output and at most 0.25 V with 10 µF (D-65).
  - R-08: 1.0 A up to 2.0 V, falling in a straight line to 0.6 A at 5.0 V,
    in place of 1 A at every voltage (D-56).
  - R-09: the VIN terminal withstands −20 V to +20 V while the ampere
    switch is open (D-60).
  - R-10: logic inputs from 1.65 V to 5.5 V in place of 1.6 V to 5.5 V
    (D-79).
  - R-14: the budget is an input current for each source, 0.45 A, 1.4 A or
    1.7 A, and the 5 V rail may fall to 4.25 V (D-49).
- **docs:** **BREAKING** the calibration record of section 8 is tied to
  the module and the carrier: it gains the chip identifier of the RP2350
  and the serial number and revision of the carrier (D-82), a
  closed-switch zero (D-59) and nine or more set-points of the DAC in
  place of two (D-58).
- **hardware:** source meter: the pre-regulator tracks the output of the
  linear regulator (D-55), and the set-point DAC is referenced to half the
  reference, which caps the output at about 5.26 V (calculated, D-58).
- **hardware:** the over-current trip is at 1.15 A in the highest range in
  place of 1.2 A (D-74), and the output switch closes slowly and opens fast
  (D-71).
- **hardware:** the ladder clamp is two diode-connected MOSFETs (D-66), and
  VOUT is protected by one 15 V suppressor to ground (D-70).
- **hardware:** the shunts of ranges 0 and 1 are thin-film resistors, range
  2 uses a two-terminal part on a Kelvin land and range 3 a four-terminal
  part (D-68).
- **hardware:** the board grows from 130 mm × 100 mm to 150 mm × 100 mm
  with a shield can over the front end (D-85). Its parts are placed by a
  script and its tracks come from an autorouter, which leaves 28 of the
  984 connections open (D-86): an autorouted draft that needs a layout
  review before fabrication.
- **hardware:** the pictures and the PDF in `hardware/doc/` show draft A2,
  and the reference designators are numbered anew for it by the rule of
  D-45.
- **docs:** the table of open component checks follows section 16 of the
  specification for draft A2, and the documentation index gives the state
  of every document and the work that comes next.
- **docs:** section 16 of the specification lists the points of its
  sections 6 to 8 that are not decided yet: how the calibration record
  travels, reports without a place in the protocol, where three stored
  constants live, the evaluation step of two firmware rules and a fault
  during start-up.
- **repo:** the contributing guide and the issue and pull request forms
  follow the present state: the Pico 2, draft A2, checks started by hand.
- **hardware:** the layout of the carrier board of draft A2 is reviewed
  against section 10 of the specification. All 984 connections are routed,
  where the autorouter had left 28 open, and the design rules check
  reports no violation, no unconnected pad, no footprint error and no
  difference from the schematic. The schematic and the bill of materials
  are unchanged; 35 of the 425 footprints moved or turned. The review was
  done with scripts and checked by independent calculation. Nobody has
  reviewed the board in the KiCad editor yet, the seven points in which it
  deviates from the earlier text of section 10 are recorded as decisions
  (D-87 to D-93), and the board is not a design to fabricate.
  Every figure of it is calculated from the drawn copper; nothing is built
  and nothing is measured.
- **hardware:** the 1 A path is drawn as pours on the top layer, with the
  supply band doubled on the bottom layer: 19.5 squares of copper in
  source mode and 23.3 squares in ampere mode against the limit of 30
  squares, 10.4 mΩ and 12.3 mΩ at 40 °C (calculated from the drawn copper,
  copper only). The autorouted tracks had 397 and 217 squares.
- **hardware:** the measured node has a guard around it under the shield
  can, with the solder mask open over 84 % of the guard track, and 10 of
  the 11 sense and guarded nets run on the top layer without a via. The
  Kelvin pair of the 0.1 Ω shunt runs side by side over 83 % of its
  length; the pair of the 1 Ω shunt and the pair to the amplifier are
  equal in length within 0.9 mm and not side by side throughout, and the
  taps of the 1 kΩ and 33 Ω shunts run through a via each on the second
  inner layer. The calculated surface leakage into the measured
  node is 5.1 nA against a budget of 10 nA, with the assumptions of
  section 10.3 (10¹¹ Ω per square on a clean surface; solder mask,
  cleanliness and humidity not modeled).
- **hardware:** the switch nodes and the output copper of the converters
  are pours, the 5 V rail is a pour on the second inner layer, and the
  reference leaves its output pin as a star of ten branches. The capacitor
  loops of the pre-regulator, the boost converter and the charge pump are
  longer than section 10.5 asks and stay open: their capacitors have to be
  placed again.
- **hardware:** ground fills on the second inner layer and on the bottom
  layer, stitched to the ground plane with 41 added vias; the ground plane
  stays one piece with no track on its layer. Through-hole ground pads
  have thermal reliefs, and the pads of the 1 A path are joined solid.
- **hardware:** the rule file of the board is rewritten and stricter. The
  exemption of the larger spacings near pins applies on the top layer
  only; the 0.5 mm of the measured node apply on the bottom layer too;
  copper fills keep 1.0 mm from the measured node on the outer layers; the
  pours of the measured node keep 1.0 mm from ground and rail copper, pads
  included; the VIN input keeps 1.0 mm on the outer layers and 0.5 mm on
  the inner layers; the guard may run 0.2 mm beside the measured node.
  These rules are recorded as decision D-87.
- **hardware:** the pictures of the board in `hardware/doc/images/` are
  plotted again from the reviewed board file. The views of the assembled
  board are renderings.
- **repo:** the Hardware workflow also fails on an unconnected pad of the
  board. It could not while the autorouted board had open connections;
  the design rules check of the reviewed board reports none.
- **docs:** the specification gives the state of the board after the
  layout review in its head, in section 10.8 and in the open checks of
  section 16, and section 10.3 carries the calculated leakage figure in
  place of the earlier estimate of 1.3 nA to 2.9 nA.
- **docs:** the specification records the seven points in which the
  reviewed board deviates from its layout guidelines as decisions, and
  sections 10.3, 10.4, 10.6, 10.8, 13, 14 and 16 follow them. The project
  owner accepted each on the recommendation of the layout review. With
  them the decision log reached D-93.
  - D-87: the rule file of the board states every spacing, among them
    1.0 mm from VIN on the outer layers and 0.5 mm on the inner layers.
  - D-88: the high-side sense line of the 0.1 Ω shunt keeps two vias and
    1.9 mm on the second inner layer.
  - D-89: the Kelvin pairs are routed as on draft A2: equal in length
    within 1 mm, and side by side only where the pins allow.
  - D-90: the guard is one piece of copper, open on the top layer at the
    three exits of the measured node and joined on the other layers.
  - D-91: the supply, address and enable pins of the multiplexer and their
    parts stand inside the guard, with no ground pour inside it.
  - D-92: the 1 A path is judged by its resistance, 30 squares or less in
    either mode, and two of its pieces run on the bottom layer.
  - D-93: the island of output copper under the linear regulator U18 is
    291 mm² on the bottom layer, joined by 22 vias to 102 mm² on the top
    layer. The temperature rise of U18 at full dissipation is an open
    check of section 16, to be read on the first board.
- **hardware:** the board carries the name of the project. The silkscreen
  and the title blocks of the board and of the schematic read "Open Power
  Profiler - Carrier Board". The schematic PDF and the picture of its root
  page are exported again; the other 14 pages are unchanged.
- **docs:** the README, the guides, the indexes of the checks and of the
  reports and the contributing guide describe the board after the layout
  review: what is drawn, which figures are calculated, what is decided,
  what is open and what comes next. The tools guide and the contributing
  guide name the board figures and their checks.
- **docs:** the specification records where the circuit simulations live
  and how they are made, as decision D-94 of the project owner: a package
  of their own in `simulation/`, circuits built from a snapshot of the
  netlist, models written for the project. Its head, the repository
  structure of section 12 and the practices of section 18 follow, and
  section 16 gains a list at its end: the fourteen places where the
  simulation and the text differ. In those places no requirement, figure,
  rule or earlier decision changes: the text stands until the owner
  decides.
- **hardware:** four decisions follow the circuit simulations, taken by
  the project owner on 2026-10-10 on their recommendation. The three
  capacitors C32 to C34 at the comparator inputs of the rail monitor are
  10 nF, not 1 nF (D-95, which changes the value of D-54). A position for
  a capacitor from the non-inverting input of the buffer U28 of the
  driver rail to ground is added; its value is chosen on the bench, and
  the position may stay empty (D-96). The position U9 at the enable pin
  of the boost converter stays without a part and is no longer meant for
  the 803 type with its time-out of 0.24 s (D-97, which changes D-84).
  The damper R14 with C5 on the input from the controller module is
  fitted (D-98, which changes D-84). None of this is drawn yet: the
  schematic, the board, the bill of materials and the netlist snapshot of
  the simulations hold the earlier state, and drawing D-95, D-96 and D-98
  is the next step of the hardware.
- **docs:** the specification records decisions D-95 to D-98 and follows
  them in its head and in sections 3, 4.1, 4.5, 4.7, 10.8, 11, 13, 14, 16
  and 17. The four points leave the list of open points at the end of
  section 16; what the decisions leave to check stays in its lists, and
  drawing them is the first item before the board is ordered. With them
  the decision log reached D-98.
- **docs:** the README, the hardware guide, the picture guide, the
  documentation index, the index of the checks and the pages on tools,
  firmware, host software, calibration and test reports describe the
  project after the simulations of 2026-10-10: what was simulated and
  with which models, what is reproduced, where the simulation and the
  specification differ, and what only a bench can settle. The README,
  the hardware guide, the picture guide, the documentation index, the
  index of the checks, the firmware guide and the page on test reports
  also carry the four decisions that followed and what is still to be
  drawn. The next steps begin with drawing decisions D-95, D-96 and
  D-98; the fourteen places and the order of proof-of-concept boards are
  the open decisions of the owner; filing the simulations is no longer a
  step.
- **repo:** the contributing guide and the issue and pull request forms
  name the simulation area: the commit scope and changelog area
  `simulation`, the four checks of the package, what a change of the
  schematic, of a model or of a bench has to carry, and the rule that a
  figure that fails in a simulation is kept.

### Removed

- **hardware:** the symbol and the socket footprint of the ESP32-S3
  development board, the programmable logic device and the buffer between
  the two boards.
- **hardware:** the resettable fuse and the OR-ing diode of the power
  input, replaced by the input stage of D-47.
- **hardware:** the reverse clamp diode of the VIN terminal (D-60), the
  anti-parallel diode pair across the shunt ladder (D-66) and the diode
  clamp of VOUT to a 5.6 V node (D-70).
- **hardware:** the picture `board-open-connections.png` and, in the
  hardware guide, the list and the map of the 28 open connections: no
  connection is open after the layout review.
- **hardware:** the empty folder `hardware/simulation/` and, in the
  hardware guide, the list of the simulations that had to be filed: the
  simulations are in `simulation/`, made again from the final netlist
  (D-94).

[Unreleased]: https://github.com/Guiimartinho/open-power-profiler/commits/main
