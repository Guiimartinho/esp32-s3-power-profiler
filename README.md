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
> nothing has been measured. The performance figures in this repository
> are design targets, and the figures of the board are calculated from the
> drawn copper. [Project Status](#project-status) says what exists, what
> it rests on and what comes next.

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
the hardware: the whole schematic, a specification written for it, and a
board with every part placed and every one of its 984 connections drawn.
The board was first routed by an autorouter, which left 28 connections
open. Its layout has since been reviewed: the open connections are closed
and the copper that an autorouter does not draw is drawn, the pours of the
1 A path, the guard, the sense pairs and the copper of the converters. The
review was done with scripts and checked by independent calculation. The
seven points where the reviewed board departs from the first wording of
section 10 of the specification are recorded decisions, D-87 to D-93, and
the specification follows them. What is open is the review by a person in
the KiCad editor, a list of items that need parts moved, the silkscreen
and test point items, and the thermal check of D-93. Every figure of the
board is calculated from the drawn copper, none is measured; the package
in [`tools/board/`](tools/board/README.md) reproduces them from the board
file. The software was written ahead of the hardware and is tested without
it.

| Area | What exists | What is open |
| --- | --- | --- |
| [Specification](docs/specification.md) | The baseline of draft A2: requirements R-01 to R-17, analog and firmware design, pin map, host protocol, 93 recorded decisions and 36 firmware rules that guard hardware | Every figure is a datasheet value, a calculation, a simulation or an estimate; the tests of its section 11 have to confirm them |
| [Schematic](hardware/doc/README.md) | 428 parts on 15 pages. It passes the electrical rules check, and its netlist was checked independently against the datasheets | The [component checks](docs/checks/README.md): none is closed, so every part is a candidate |
| [Board](hardware/README.md#board) | 150 mm × 100 mm, four layers, 425 footprints, 984 of 984 connections drawn, no violation in the design rules check. The layout was reviewed with scripts and checked by independent calculation. Calculated from the drawn copper: the 1 A path is 19.5 squares in source meter mode and 23.3 squares in ampere meter mode against a limit of 30, and the surface leakage into the measured node is 5.1 nA against a budget of 10 nA. The seven points where the layout departs from the first wording of section 10 of the specification are recorded as decisions D-87 to D-93 | No person has reviewed the board in the KiCad editor; open items need parts moved, the capacitor loops of the converters among them; names on the silkscreen and probe grounds at the test points are missing; the temperature rise of the linear regulator is an open check, read on the first board (D-93) |
| [Bill of materials](hardware/doc/bom.csv) | 151 lines, each with a part number and a maker, exported from the schematic | Three lines had no stock on 2026-10-09; three positions carry no part until a bench test decides |
| Simulations and calculations | The specification marks every figure that comes from a simulation. The figures of the board are calculated from the drawn copper by the package in [`tools/board/`](tools/board/README.md), which is tested without hardware | The simulation files are not in the repository; the scripts that drew the layout are not in it either |
| [Firmware](firmware/README.md) | Core in C that needs no hardware, with unit tests on the PC: wire protocol, block queue, settling window, step-down rule, device state machine. The build project is still the one of the first plan, for the ESP32-S3 | No build for the Pico 2, no PIO program, no adapter for any hardware, no command handler, none of the firmware rules of the specification |
| [Host software](host/README.md) | Python package with protocol, transports, device client, capture helpers and a device simulator, tested against that simulator | Its nominal calibration and its handling of flagged samples do not follow draft A2 yet; no command that captures from an instrument, no viewer and no export |
| [Protocol](protocol/README.md) | One definition; the constants of firmware and host and the shared test vectors are generated from it | What draft A2 reports beyond it, listed in section 16 of the specification |
| [Tools](tools/README.md) | [`tools/board/`](tools/board/README.md): a Python package that calculates the layout figures from a dump of the board file: copper resistance in squares and milliohms, lengths of the Kelvin pairs, surface leakage into the measured node. 260 tests on synthetic boards, lines and branches fully covered | Calibration and production test: two empty folders. The `Tools` workflow has not been started yet |
| Measurements | None: no board has been built | The phases of the [roadmap](#roadmap) |

Next steps, in this order:

1. **Board.** Four things stand between the reviewed layout and
   fabrication. First, a person opens the board in the KiCad editor and
   reviews it; so far it was drawn and checked with scripts only. Second,
   the open items that need parts moved are a change of placement with a
   local redraw: the capacitor loops of the converters, the inductor of
   the pre-regulator and the others. Third, the silkscreen and test point
   items: net names, jumper functions, probe grounds, a frame for the
   serial number. Fourth, the thermal check of D-93: the temperature rise
   of the linear regulator at full dissipation is read on the first board.
   The [hardware guide](hardware/README.md#still-to-do) lists the open
   items one by one.
2. **Software.** Bring the host package and the firmware to what the
   specification of draft A2 asks: the nominal calibration, the fault
   causes and the protocol items of its section 16. Then port the firmware
   to the Pico SDK. The [firmware guide](firmware/README.md) and the
   [host guide](host/README.md) list the differences.
3. **Simulations.** File the simulations behind the figures marked
   "simulated" in `hardware/simulation/`, which is empty. Until then a
   reader cannot repeat those figures. The scripts behind the figures that
   are calculated from the board are filed in
   [`tools/board/`](tools/board/README.md). The
   [hardware guide](hardware/README.md#still-to-do) lists what has to be
   filed.

The [component checks](docs/checks/README.md) follow, of which none is
closed, and the phases of the [roadmap](#roadmap), starting with the risk
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

The carrier board is drawn in KiCad 10 as draft A2. Its layout was reviewed
on 2026-10-10.

| | Draft A2 after the layout review |
| --- | --- |
| Schematic | 428 parts on 15 A4 pages: the root page and 14 sheets; unchanged by the layout review |
| Electrical rules check | 0 errors, 0 warnings |
| Board | 150 mm × 100 mm, four layers, 425 footprints, all on the top side |
| Routing | 984 of the 984 connections: 8.38 m of track on three layers (top 3.76 m, second inner layer 2.84 m, bottom 1.79 m), 694 vias and 42 copper zones. The first inner layer is the ground plane, in one piece and with no track on it |
| Open connections | None. The autorouted board had 28, and 25 of them broke a function |
| Design rules check | 0 violations, 0 unconnected pads, 0 footprint errors, 0 differences between board and schematic. The rule file is stricter than the one the autorouter ran with: the exemption of the larger spacings near pins now holds on the top layer only. Decision D-87 records its spacings |
| Bill of materials | 151 lines, each with a part number and a maker: [`hardware/doc/bom.csv`](hardware/doc/bom.csv); unchanged by the layout review |

The schematic was checked independently against the datasheets of its
parts. That closes none of the
[component checks](docs/checks/README.md): the parts are candidates.

The board came about in three steps. A script placed every footprint
inside the area of its functional block. An autorouter drew a first set of
tracks: 956 of the 984 connections, with 28 left open, no pour and no
guard. Then the layout was reviewed with scripts on the board file, block
by block: the open connections were closed and the pours of the 1 A path,
the guard, the Kelvin pairs, the copper of the converters, the 5 V rail and
the ground fills were drawn. Each block was drawn against the rules of
section 10 of the specification and then checked by an independent check
that calculated every rule again. A final review of the whole board by rule
group followed, with 75 findings, then a repair round for the leakage paths
into the measured node that it found. No part was added or removed; 35 of
the 425 footprints moved or turned, 33 of them by 2.75 mm or less.

The result is a drawn and calculated layout, not a design to fabricate.
Nobody has opened it in the KiCad editor and looked at it as a person
would before ordering boards: every check ran from the command line. The
scripts that calculate the figures are in the repository, as the package
in [`tools/board/`](tools/board/README.md); the helpers that drew the
layout are not.

### What the Layout Review Reached

Every figure in the column "Now" is calculated from the drawn copper.
Nothing is built and nothing is measured. The resistances count 35 µm
copper at 40 °C and leave out the transistors, the shunt and the fuse.

| Rule, with its section of the specification | Limit | Autorouted board | Now |
| --- | --- | --- | --- |
| Connections drawn | 984 | 956 | 984 |
| 1 A path in source meter mode, regulator output to the VOUT terminal (10.4) | 30 squares | 397 squares, about 211 mΩ | 19.5 squares, 10.4 mΩ |
| 1 A path in ampere meter mode, VIN terminal to the VOUT terminal (10.4) | 30 squares | 217 squares, about 116 mΩ | 23.3 squares, 12.3 mΩ |
| Surface leakage into the measured node (10.3) | 10 nA | No figure | 5.1 nA; it was about 20 nA at the final review, before the repair round |
| Guard around the measured node (10.3) | A closed ring on the top layer | None | One piece of copper: three arcs on the top layer, open where the measured node leaves the shield can, joined through the other layers |
| Sense and guarded nets on the top layer without a via (10.3) | All 11 | No figure | 10 of 11 |
| 5 V rail from the bulk capacitor to the input capacitors of the converters (10.1) | 10 mΩ to the pre-regulator and 25 mΩ to the boost converter: targets of the layout review, the specification gives no figure | Tracks of 0.4 mm | A pour on the second inner layer: 2.7 mΩ and 3.0 mΩ to the pre-regulator, 3.6 mΩ to the boost converter |
| Copper from the output capacitors of the pre-regulator to the bead (10.5) | 15 mΩ | No figure | 7.1 mΩ |

The figures of the 1 A path, of the leakage, of the pairs and of the vias
on the sense nets are reproduced from the board file by the `report`
command of the package in `tools/board/`; its
[guide](tools/board/README.md#report-everything-the-definition-asks-for)
says how to install it, dump the board and run it. The resistances are
calculated on a grid of 0.1 mm; on a grid of 0.05 mm the two sums of the
1 A path read about 2 % higher, 19.9 squares and 23.8 squares, and a via
is counted in a way that errs to the high side.

The leakage figure rests on the assumptions that section 10.3 of the
specification itself uses: a clean surface of 10¹¹ Ω per square and the
voltages of the neighboring nets. Solder mask, cleanliness and humidity
are not modeled. Almost all of what is left comes from the pitch of pads:
the gate beside the source in a transistor package, the poles of the two
DUT connectors, neighboring pins of the multiplexer.

### Decisions of the Layout Review

In seven points the reviewed board departs from what section 10 of the
specification first asked. The owner accepted all seven on 2026-10-10.
They are recorded in the decision log of the
[specification](docs/specification.md) (section 15), and section 10 now
describes the board as it is drawn:

- **D-87.** The rule file of the board states every spacing that the
  layout needs.
- **D-88.** The high-side sense line of the 0.1 Ω shunt keeps two vias and
  1.9 mm on the second inner layer.
- **D-89.** The Kelvin pairs: one runs side by side, two are equal in
  length within 1 mm, and the taps of the two lowest ranges run through
  one via each.
- **D-90.** The guard is one piece of copper, open on the top layer at the
  three exits of the measured node and joined on other layers.
- **D-91.** The supply, address and enable pins of the multiplexer and
  their parts stand inside the guard.
- **D-92.** The 1 A path is judged by its resistance, 30 squares or less
  in either mode; two of its pieces run on the bottom layer.
- **D-93.** The island of output copper under the linear regulator is
  291 mm² on the bottom layer and 102 mm² on the top layer, joined by
  22 vias; its temperature rise is an open check, read on the first board.

A decision accepts a drawn layout, not a measured one: where it rests on
a resistance or a leakage, the figure is calculated from the drawn copper.
The [hardware guide](hardware/README.md#decisions-of-the-layout-review-d-87-to-d-93)
quotes, for each point, what section 10 said before, what the board has
and why.

### What the Layout Review Left Open

Four things stand before fabrication, and the component checks beside
them.

No person has reviewed the board in the KiCad editor: it was drawn and
checked with scripts only.

Eleven items need parts moved or another footprint and were left open. The
capacitor loops of the pre-regulator and of the boost converter close over
6.8 mm to 17.1 mm of top copper where the limit is 5 mm, and the inductor
of the pre-regulator stands 4.5 mm from its switch pins where the limit is
3 mm; nine more are smaller.

The legends of the silkscreen and the test points are as the autorouted
board had them; only the title text changed, to the name of the project.
32 of the 40
signal test points have no probe ground within 5 mm, and the net names of
the test points and the functions of the two jumpers are not printed.

The temperature rise of the linear regulator at full dissipation is an
open check, to be read on the first board (D-93).

The component checks are open too: none is closed. The hardware guide
lists the [open items](hardware/README.md#open-items) one by one, with
their figures and with what would close each.

### Pictures

All pictures are renderings and plots of the board file, not photographs.

The top side, rendered from the board file. The gold line around the front
end is the guard under open solder mask:

![Rendered top view of the carrier board](hardware/doc/images/board-top.jpg)

The four copper layers side by side. Top left, the top layer: the parts,
the pours of the 1 A path, the sense pairs and the guard. Top right, the
first inner layer: the ground plane, in one piece. Bottom left, the second
inner layer: the 5 V rail, the rail trunks and a ground fill. Bottom
right, the bottom layer: the crossings, the second layer of the 1 A path
and a ground fill:

![The four copper layers of the board](hardware/doc/images/board-copper.png)

The measured node under the shield can, top layer in red, openings of the
solder mask in pink. Look for the pink line that runs around the large red
area: it is the guard, bare of solder mask, around the copper of the
measured node and the guard pour. From the multiplexer in the middle, thin
lines run in pairs to the shunts: the Kelvin lines. At the lower right the
pair of the 1 A range leaves the can in a lane with a guard track on each
side:

![The measured node and its guard on the top layer](hardware/doc/images/board-front-end.png)

The 1 A path on the top layer. Follow the wide copper from the linear
regulator at the bottom left, along the supply band to the right, up to
the shunt branch and the output switch, and out to the terminal block at
the right edge. The dashed rectangle is made of the lands of the shield
can:

![The pours of the 1 A path on the top layer](hardware/doc/images/board-1a-path.png)

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
| [`tools/`](tools/) | [`tools/board/`](tools/board/): the package that calculates the layout figures from the board file, with its tests. The folders for the calibration and production-test scripts are empty | MIT |
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
| 5 | Carrier board, revision A, with the Pico 2 plugged in. Entry: the open checks that precede fabrication are closed and the layout is reviewed | Not started; draft A2 of the schematic and a board with every connection drawn exist, drawn ahead of the phases. The layout was reviewed with scripts and by calculation, and its seven deviations from section 10 are recorded decisions (D-87 to D-93); the review by a person in KiCad and the open items remain |
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
| Board figures | Python 3.10 or later; KiCad 10 to dump the board file | [`tools/board/README.md`](tools/board/README.md) |
| Documentation | Node.js, for `npx --yes markdownlint-cli2@0.23.3` | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

No instrument is needed to work on the software: the firmware logic runs in
unit tests on the PC, the host package talks to a simulator, and the board
figures package is tested on small synthetic boards.

## Engineering Practices

- Logic that does not need hardware is kept apart from the code that does,
  in firmware and in host software, and is covered by unit tests.
- The wire protocol has one definition. The constants of both sides are
  generated from it, and both codecs must reproduce the same test vectors.
- Six continuous integration workflows, one per area (`Firmware`, `Host`,
  `Protocol`, `Tools`, `Hardware`, `Docs`), build the firmware, run the
  tests with coverage floors, run the formatters and static analyzers and
  check the hardware project. The firmware build is still the one of the
  first plan, for the ESP32-S3, until the port to the Pico SDK. For now
  the workflows are started by hand, not on every push (D-22); the same
  checks run locally before a change is recorded.
- The board figures package in `tools/board/` has the gates of the host
  software: tests with a coverage floor of 90 % of lines and branches,
  ruff, mypy in strict mode, and the wheel built and installed. They ran
  locally on Windows; the `Tools` workflow, which repeats them on Linux
  and macOS too, has not been started yet.
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
- [Calibration](docs/calibration/README.md) and
  [protocol reference](docs/protocol/README.md): what the specification
  defines for each and what is not written.
- [Tools](tools/README.md): the board figures, which exist, and what the
  calibration tool and the production test will have to do; neither is
  started.
- [Board figures guide](tools/board/README.md): how the figures of the
  layout are calculated from the board file, with the method, the
  assumptions and the limits.
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
