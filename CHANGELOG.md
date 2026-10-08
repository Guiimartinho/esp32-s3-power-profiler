# Changelog

All notable changes to this project are documented in this file.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each entry starts with the area it affects: **firmware**, **hardware**,
**host**, **tools**, **docs** or **repo**.

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

### Removed

- **hardware:** the symbol and the socket footprint of the ESP32-S3
  development board, the programmable logic device and the buffer between
  the two boards.

[Unreleased]: https://github.com/Guiimartinho/open-power-profiler/commits/main
