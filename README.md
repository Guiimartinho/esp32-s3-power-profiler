# Open Power Profiler

[![Checks: run on demand][badge-checks]](CONTRIBUTING.md#quality-gates)
[![Status: early development][badge-status]](#roadmap)
[![Software license: MIT][badge-mit]](LICENSE)
[![Hardware license: CERN-OHL-P v2][badge-ohl]](hardware/LICENSE)

Open-source power profiler in the class of the Nordic PPK2, built around the
Raspberry Pi Pico 2. It is designed to sample current at 100 kSPS from
100 nA to 1 A with automatic range switching, to work either as a source
meter that powers the device under test or as an ampere meter in series
with an external supply, and to stream the samples to a PC over USB.

The instrument is two boards: a Raspberry Pi Pico 2, bought ready-made,
plugged into a carrier board designed in this project that holds the
measurement electronics.

![Rendered view of the carrier board, draft A2](hardware/doc/images/board-3d.jpg)

The picture is a rendering from the KiCad files of draft A2, with the
Pico 2 on its sockets. It is not a photograph: no board has been built.

> [!NOTE]
> The project is in early development. No hardware has been built and
> nothing has been measured, so every figure in this repository is a design
> target. [Project Status](#project-status) says what exists, what it rests
> on and what comes next.

## Table of Contents

- [Project Status](#project-status)
- [Target Specifications](#target-specifications)
- [How It Works](#how-it-works)
- [Connections](#connections)
- [Hardware Draft](#hardware-draft)
- [Repository Structure](#repository-structure)
- [Roadmap](#roadmap)
- [Getting Started](#getting-started)
- [Engineering Practices](#engineering-practices)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Project Status

As of 2026-10-10. Draft A2 of the carrier board is the present state of
the hardware: the whole schematic, a board with every part placed and most
tracks drawn, and a specification written for it. The software was written
ahead of the hardware and is tested without it.

| Area | What exists | What is open |
| --- | --- | --- |
| [Specification](docs/specification.md) | The baseline of draft A2: requirements R-01 to R-17, analog and firmware design, pin map, host protocol, 86 recorded decisions and 36 firmware rules that guard hardware | Every figure is a datasheet value, a calculation, a simulation or an estimate; the tests of its section 11 have to confirm them |
| [Schematic](hardware/doc/README.md) | 428 parts on 15 pages. It passes the electrical rules check, and its netlist was checked independently against the datasheets | The [component checks](docs/checks/README.md): none is closed, so every part is a candidate |
| [Board](hardware/README.md#board) | 150 mm × 100 mm, four layers, 425 footprints placed by a script and routed by an autorouter: 956 of the 984 connections. The design rules check reports no violation of the rules as they were relaxed for the autorouter | 28 connections are open, among them pieces of the 5 V rail and of the measured path, and nobody has reviewed the layout: no pours, no guard ring |
| [Bill of materials](hardware/doc/bom.csv) | 151 lines, each with a part number and a maker, exported from the schematic | Three lines had no stock on 2026-10-09; three positions carry no part until a bench test decides |
| Simulations | The specification marks every figure that comes from a simulation | The simulation files are not in the repository |
| [Firmware](firmware/README.md) | Core in C that needs no hardware, with unit tests on the PC: wire protocol, block queue, settling window, step-down rule, device state machine. The build project is still the one of the first plan, for the ESP32-S3 | No build for the Pico 2, no PIO program, no adapter for any hardware, no command handler, none of the firmware rules of the specification |
| [Host software](host/README.md) | Python package with protocol, transports, device client, capture helpers and a device simulator, tested against that simulator | Its nominal calibration and its handling of flagged samples do not follow draft A2 yet; no command that captures from an instrument, no viewer and no export |
| [Protocol](protocol/README.md) | One definition; the constants of firmware and host and the shared test vectors are generated from it | What draft A2 reports beyond it, listed in section 16 of the specification |
| [Tools](tools/README.md) | Nothing: two empty folders | Calibration and production test |
| Measurements | None: no board has been built | The phases of the [roadmap](#roadmap) |

Next steps, in this order:

1. **Board.** Close the 28 open connections in KiCad and review the
   layout: the pours of the 1 A path, the guard ring, the Kelvin pairs and
   the loops of the switching converters. The connections are listed one by
   one, with a map, in the [hardware guide](hardware/README.md#still-to-do):
   25 of them break a function, so the board does not work until they are
   closed. Section 10.8 of the specification names what the review draws
   by hand.
2. **Software.** Bring the host package and the firmware to what the
   specification of draft A2 asks: the nominal calibration, the fault
   causes and the protocol items of its section 16. Then port the firmware
   to the Pico SDK. The [firmware guide](firmware/README.md) and the
   [host guide](host/README.md) list the differences.
3. **Simulations.** File the simulations behind the figures marked
   "simulated" in `hardware/simulation/`, which is empty. The
   [hardware guide](hardware/README.md#3-file-the-simulations) lists,
   block by block, which figures of the specification rest on one.

The phases of the [roadmap](#roadmap) follow, starting with the risk
prototypes of phase 1.

## Target Specifications

| Item | Target | Requirement |
| --- | --- | --- |
| Sampling rate | 100 kSPS, timed by hardware | R-01 |
| Data integrity | No lost sample in a capture of 10 minutes; any loss is reported | R-02 |
| Current range | 100 nA to 1 A in four ranges, switched automatically | R-03 |
| Resolution | 100 nA or better in the lowest range; RMS noise there at most 5 nA in ampere meter mode from a quiet supply and 40 nA in source meter mode | R-04 |
| Accuracy | ±1 % of reading ±0.1 % of range after calibration | R-05 |
| Burden voltage | 100 mV maximum across the shunt; 200 mV from input to output at 1 A | R-06 |
| Range change | On a step from 1 µA to 500 mA the instrument adds at most 0.5 V of drop with 1 µF at its output and 0.25 V with 10 µF | R-07 |
| Source meter mode | Programmable output from 0.8 V to 5.0 V in 1.3 mV steps; 1.0 A up to 2.0 V, falling to 0.6 A at 5.0 V | R-08 |
| Ampere meter mode | External supply from 0.8 V to 5.0 V through the shunts; the input withstands −20 V to +20 V while its switch is open | R-09 |
| Digital inputs | 8 logic channels sampled together with the current, logic levels from 1.65 V to 5.5 V | R-10 |
| Host link | USB Full-Speed, CDC ACM, binary protocol | R-11 |
| Calibration | Gain and offset of each range, stored on the device | R-12 |
| Protection | Over-current trip, reverse polarity, over-voltage, thermal | R-13 |
| Power input | USB-C, 5 V, on the carrier board, used whenever it is present, or the USB cable of the Pico 2 alone; the input current is limited to what the source offers: 0.45 A, 1.4 A or 1.7 A | R-14 |
| Host software | Capture, live view, statistics and export on Windows, Linux and macOS | R-15 |
| Openness | Firmware and host software under MIT, hardware under CERN-OHL-P v2 | R-16 |
| Software quality | Automated tests with coverage gates, static analysis and continuous integration | R-17 |
| Controller | Raspberry Pi Pico 2 (RP2350) on pin sockets | D-39 |
| DUT connections | Pin header and lever terminal block, in the pin order of the PPK2 | D-44 |

These are design targets, not measurements. Draft A2 set seven of them
(R-04, R-06, R-07, R-08, R-09, R-10 and R-14) to what the architecture
delivers, with the PPK2 as the yardstick. Section 2 of the
[specification](docs/specification.md) gives the full wording of each
requirement and the evidence behind each figure: a datasheet value, a
calculation, a simulation or an estimate.

Where the specification compares a target with the PPK2, it quotes the
PPK2 User Guide v1.0.1:

| Item | This design, target | PPK2, as its user guide states |
| --- | --- | --- |
| Resolution in the lowest range | 100 nA or better (R-04) | 0.2 µA, with measurement down to about 200 nA |
| Current in source meter mode | 1.0 A up to 2.0 V, falling to 0.6 A at 5.0 V (R-08) | 600 mA, with a rated power of 5 W |
| External supply in ampere meter mode | 0.8 V to 5.0 V (R-09) | The same range |
| Logic levels of the digital inputs | 1.65 V to 5.5 V (R-10) | 1.65 V to 5.5 V |
| Burden voltage | 100 mV across the shunt, 200 mV in the whole path at 1 A (R-06) | Not stated |
| Drop at a range change | 0.5 V with 1 µF at the output, 0.25 V with 10 µF (R-07) | Not stated |
| Voltage that the supply input withstands | −20 V to +20 V with its switch open (R-09) | Not stated |

The middle column holds design targets, none of them measured; the right
column is taken from section 2 of the specification.

## How It Works

```text
USB-C 5 V ────► limiter ─┐
                         ├► multiplexer ─► 5 V rail ─► supplies of the carrier
Pico 2 USB ───► limiter ─┘

5 V rail ───► pre-regulator ──► LDO (source mode) ◄── DAC ◄── SPI
                                    │
VIN (ampere mode) ──► protection ──►├── mode switch
                                    │
                         shunt ladder + range FETs ◄── range sequencer
                                    │         │ Kelvin sense   ▲
                         output switch     in-amp ──┬──► comparators
                                    │               └──► ADC ──► Pico 2 ──► USB
                                  VOUT ──► DUT          D0..D7 ──► level shift
```

- **Two boards.** Everything in the diagram except the controller is on the
  carrier board. The Raspberry Pi Pico 2 brings the microcontroller and the
  USB port, and uses every one of its 26 GPIO pins.
- **One programmable part.** The range sequencer and the sampling clock are
  programs for the PIO blocks of the RP2350: small state machines that run
  from the system clock whatever the processors do. Firmware is loaded
  through USB; no programmer and no vendor tool is needed.
- **A supply that spares its source.** Each USB input has its own current
  limiter, and a multiplexer feeds the 5 V rail from USB-C whenever it is
  present. A supervisor switches the supplies of the carrier off when that
  rail collapses, and four comparators report through one line, PWR_GOOD,
  that the analog rails and the reference are present.
- **Four shunt ranges.** Shunts of 1 kΩ, 33 Ω, 1 Ω and 0.1 Ω, each limited
  to 100 mV of burden voltage. Three comparators drive the range
  sequencer, which switches to a higher range with no firmware involved:
  on a large step the 1 A range conducts 0.35 µs after its threshold
  (simulated, with a sequencer that reacts within 100 ns, which phase 1
  has to measure). A current step therefore costs the device under test
  only a short dip; requirement R-07 of the specification gives its size.
  The firmware decides when to step back down.
- **Hardware-timed sampling.** A 16-bit SAR ADC is clocked by a PIO state
  machine, so the sampling instant does not depend on firmware latency. The
  same state machine reads the range and the logic inputs with every
  conversion result.
- **Self-describing samples.** Every sample is a 32-bit word that carries the
  ADC code, the active range, a validity flag, the fault flag and the eight
  logic inputs.
- **Two cores, two jobs.** One core acquires data in DMA blocks. The other
  frames the blocks and streams them over USB.
- **Programmable supply.** In source meter mode a DAC sets a low-noise linear
  regulator, fed by a pre-regulator that tracks the output voltage.
- **Protection that does not wait for firmware.** The over-current trip is a
  PIO state machine. An over-voltage on the external supply input holds
  its switch open through one transistor, a second transistor keeps the two
  mode switches from closing together, and with its switch open that input
  withstands −20 V to +20 V (simulated).
- **A quiet front end.** The shunts of the three lower ranges, the
  amplifier and the converter are placed under a shield can, and the
  switching converters stand at least 30 mm away from it.

The reasons behind each choice, with the decision that records it, are in
sections 3 and 4 of the [specification](docs/specification.md).

## Connections

The back edge of the carrier has the USB connector of the Pico 2 (data, and
power for small loads) and a USB-C connector for power. Either one powers
the whole instrument. The front edge has the connections to the device under
test, in the pin order of the Nordic PPK2:

| Connector | Type | Pins, left to right |
| --- | --- | --- |
| DUT | 1×4 pin header, 2.54 mm | GND, VIN, VOUT, GND |
| DUT | Lever terminal block, 3.5 mm | GND, VIN, VOUT, GND |
| Logic port | 1×10 pin header, 2.54 mm | VCC, GND, D7 down to D0 |

- **Source meter mode:** the device under test connects to VOUT and GND.
- **Ampere meter mode:** the external supply connects to VIN and GND, the
  device under test to VOUT and GND.
- **Logic port:** as built, the logic inputs follow the output voltage, and
  the VCC pin is not needed. A solder jumper makes the VCC pin the reference
  instead, for a device whose logic runs on another voltage.

## Hardware Draft

The carrier board is drawn in KiCad 10 as draft A2.

| | Draft A2 |
| --- | --- |
| Schematic | 428 parts on 15 A4 pages: the root page and 14 sheets |
| Electrical rules check | 0 errors, 0 warnings |
| Board | 150 mm × 100 mm, four layers, 425 footprints, all on the top side |
| Routing | 956 of the 984 connections, drawn by an autorouter: 7.83 m of track and 499 vias on three layers; the fourth layer is an unbroken ground plane |
| Open connections | 28, listed one by one and drawn on a map in the [hardware guide](hardware/README.md#still-to-do) |
| Design rules check | 0 rule violations, 0 differences between board and schematic, 28 unconnected items: the open connections. The rules were relaxed for the autorouter: the larger spacings of the rule file do not apply to a track that touches a footprint, and the tracks are narrower than their net classes ask |
| Bill of materials | 151 lines, each with a part number and a maker: [`hardware/doc/bom.csv`](hardware/doc/bom.csv) |

The schematic was checked independently against the datasheets of its
parts. That closes none of the
[component checks](docs/checks/README.md): the parts are candidates.

On the board a script places every footprint inside the area of its
functional block, and an autorouter draws the tracks. It is an autorouted
draft that needs a layout review before fabrication, not a design to
fabricate: the open connections, the pours of the 1 A path, the guard
ring, the sense pairs and the loops of the switching converters are work
for that review. Every check ran from the command line; the project has
not been opened in the KiCad editor yet.

The top side, rendered from the board file:

![Rendered top view of the carrier board](hardware/doc/images/board-top.jpg)

The three routing layers: the top layer in red, the inner layer for power
and signals in orange, the bottom layer in blue. The ground plane lies
between them and is left out of the picture:

![The three routing layers of the board](hardware/doc/images/board-copper.png)

The 28 open connections. Each link joins the two ends of one connection
that the autorouter did not draw, over the pale copper of the board; the
numbers are those of the table in the
[hardware guide](hardware/README.md#still-to-do):

![The 28 open connections of the board](hardware/doc/images/board-open-connections.png)

The areas of the sixteen functional blocks and the parts inside them:

![Placement of the functional blocks](hardware/doc/images/board-placement.png)

The root page of the schematic, with one block for each of the 14 sheets:

![Block level of the schematic](hardware/doc/images/schematic-01-root.png)

Every sheet and the board are shown in
[`hardware/doc/`](hardware/doc/README.md), and the whole schematic is in
[`hardware/doc/schematic.pdf`](hardware/doc/schematic.pdf). The status, the
checks and the open work are in the [hardware guide](hardware/README.md).

## Repository Structure

| Path | Content | License |
| --- | --- | --- |
| [`firmware/`](firmware/) | Firmware of the controller: hardware-independent core with its unit tests; target build not ported to the Pico 2 yet | MIT |
| [`hardware/`](hardware/) | KiCad project of the carrier board and its pictures; the folders for simulations and fabrication outputs are empty | CERN-OHL-P v2 |
| [`host/`](host/) | Python package: protocol, transports, device client, capture helpers, simulator | MIT |
| [`protocol/`](protocol/) | Protocol definition, generator and shared test vectors | MIT |
| [`tools/`](tools/) | Calibration and production-test scripts; not started | MIT |
| [`docs/`](docs/) | Specification, component checks (all open), test reports (none yet) | MIT |

## Roadmap

The work is split into phases. Each phase is closed by a test report with
recorded measurements. The exit criteria are in section 13 of the
[specification](docs/specification.md).

| Phase | Goal | Status |
| --- | --- | --- |
| 1 | Risk prototypes. On a Pico 2 with an ADC evaluation module: firmware on the Pico SDK, hardware-timed ADC capture, reaction time of the range sequencer, USB throughput. On evaluation modules: the pre-regulator with its tracking amplifier, and the start of the boost converter from a supply limited to 0.7 A | Not started; the software foundations exist, written ahead of it and tested without hardware; the firmware port to the Pico SDK and the bench work are not started |
| 2 | Analog front end with one fixed range on a test board | Not started |
| 3 | Shunt ladder and range logic | Not started |
| 4 | Source mode and power | Not started |
| 5 | Carrier board, revision A, with the Pico 2 plugged in. Entry: the open checks that precede fabrication are closed and the layout is reviewed | Not started; draft A2 of the schematic and an autorouted draft of the board exist, drawn ahead of the phases |
| 6 | Calibration, protocol freeze and host software | Not started |
| 7 | Revision B and release | Not started |

Draft A2 is the hypothesis that the phases test: the component checks and
the results of phases 1 to 4 change it before revision A is fabricated.
The work that comes first is listed under
[Project Status](#project-status).

## Getting Started

```sh
git clone https://github.com/Guiimartinho/open-power-profiler.git
cd open-power-profiler
```

Start with the [specification](docs/specification.md). Each part of the
repository documents its own setup and commands:

| Part | Needs | Guide |
| --- | --- | --- |
| Firmware | CMake, Ninja and gcc for the unit tests | [`firmware/README.md`](firmware/README.md) |
| Host software | Python 3.10 or later | [`host/README.md`](host/README.md) |
| Protocol | Python 3.11 or later | [`protocol/README.md`](protocol/README.md) |
| Hardware | KiCad 10 | [`hardware/README.md`](hardware/README.md) |
| Documentation | Node.js, for `npx --yes markdownlint-cli2@0.23.3` | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

No instrument is needed to work on the software: the firmware logic runs in
unit tests on the PC, and the host package talks to a simulator.

## Engineering Practices

- Logic that does not need hardware is kept apart from the code that does,
  in firmware and in host software, and is covered by unit tests.
- The wire protocol has one definition. The constants of both sides are
  generated from it, and both codecs must reproduce the same test vectors.
- Continuous integration workflows build the firmware, run the tests with
  coverage floors, run the formatters and static analyzers and check the
  hardware project. The firmware build is still the one of the first plan,
  for the ESP32-S3, until the port to the Pico SDK. For now the workflows
  are started by hand, not on every push; the same checks run locally
  before a change is recorded.
- Timing, throughput and analog behavior are not claimed from tests. They
  are measured on the bench and recorded in a report.

The rules are in section 18 of the [specification](docs/specification.md)
and in the [contributing guide](CONTRIBUTING.md).

## Documentation

- [System specification](docs/specification.md): requirements, analog and
  firmware architecture, pin map, host protocol, calibration, verification
  plan, risks and decision log.
- [Hardware guide](hardware/README.md) and
  [the draft in pictures](hardware/doc/README.md): the carrier board, sheet
  by sheet.
- [Firmware guide](firmware/README.md), [host guide](host/README.md) and
  [protocol guide](protocol/README.md): architecture, commands and tests of
  each part.
- [Open checks](docs/checks/README.md): what has to be confirmed, part by
  part and on the bench, before the schematic is frozen, and the records
  that accept a candidate part against its datasheet; none is filed yet.
- [Test reports](docs/reports/README.md): the measurements that close each
  phase; no report is filed yet.
- [Calibration](docs/calibration/README.md),
  [protocol reference](docs/protocol/README.md) and
  [tools](tools/README.md): what the specification defines for each and
  what is not written.
- [Documentation index](docs/README.md): every document of the repository
  and how they relate.
- [Changelog](CHANGELOG.md): notable changes by release.

## Contributing

Contributions are welcome. Read the [contributing guide](CONTRIBUTING.md)
first: it covers the workflow, the commit message format, the quality gates
and how changes to the specification are recorded.

## License

- Hardware design files under [`hardware/`](hardware/):
  [CERN-OHL-P v2](hardware/LICENSE).
- Everything else, including firmware, host software, tools and
  documentation: [MIT](LICENSE).

## Acknowledgments

- Inspired by
  [Gedankenn/power_profiller](https://github.com/Gedankenn/power_profiller),
  an ESP32 and INA226 power profiler with a web dashboard. This project
  started on the ESP32-S3 too, and was called `esp32-s3-power-profiler`
  until its controller changed.
- The feature set and the pin order of the connectors follow the Nordic
  Semiconductor Power Profiler Kit II (PPK2). This project is independent
  and is not affiliated with or endorsed by Nordic Semiconductor.
- The controller module is a Raspberry Pi Pico 2. This project is
  independent and is not affiliated with or endorsed by Raspberry Pi Ltd.

[badge-checks]: https://img.shields.io/badge/checks-run%20on%20demand-lightgrey
[badge-status]: https://img.shields.io/badge/status-early%20development-orange
[badge-mit]: https://img.shields.io/badge/software-MIT-blue
[badge-ohl]: https://img.shields.io/badge/hardware-CERN--OHL--P%20v2-blue
