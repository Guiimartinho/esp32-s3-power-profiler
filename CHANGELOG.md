# Changelog

All notable changes to this project are documented in this file.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each entry starts with the area it affects: **firmware**, **hardware**,
**host**, **protocol**, **tools**, **docs** or **repo**.

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

### Removed

- **hardware:** the symbol and the socket footprint of the ESP32-S3
  development board, the programmable logic device and the buffer between
  the two boards.
- **hardware:** the resettable fuse and the OR-ing diode of the power
  input, replaced by the input stage of D-47.
- **hardware:** the reverse clamp diode of the VIN terminal (D-60), the
  anti-parallel diode pair across the shunt ladder (D-66) and the diode
  clamp of VOUT to a 5.6 V node (D-70).

[Unreleased]: https://github.com/Guiimartinho/open-power-profiler/commits/main
