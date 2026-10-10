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
> are design targets, the circuits of the board are simulated from its
> netlist, and the figures of the board are calculated from the drawn
> copper. [Project Status](#project-status) says what exists, what it
> rests on and what comes next.

## Table of Contents

- [Project Status](#project-status)
- [Target Specifications](#target-specifications)
- [How It Works](#how-it-works)
- [Connections](#connections)
- [Hardware Draft](#hardware-draft)
- [Circuit Simulations](#circuit-simulations)
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
file.

On 2026-10-10 the circuits of the schematic were simulated as well, block
by block, from its netlist: 134 benches in ngspice, of which 93 run
circuits of the board and 41 put the models into the test circuits of
their datasheets. The central design figures of the specification come
out again. The simulations raised four points for a decision before
boards are ordered, and the project owner decided them the same day: they
are decisions D-95 to D-98 of the specification. Three of them change the
schematic and are not drawn yet, so the schematic, the board, the bill of
materials and the results of the simulations still show the earlier
state. In fourteen places the simulations differ from a figure or a rule
of the specification or show something that it does not state. Those are
not decided, and no requirement, figure or rule of the specification was
changed on their account. A simulation is not a measurement: every active
part in it is a model written from a datasheet, a typical part at room
temperature. [Circuit Simulations](#circuit-simulations) shows the state.

The software was written ahead of the hardware and is tested without it.

| Area | What exists | What is open |
| --- | --- | --- |
| [Specification](docs/specification.md) | The baseline of draft A2: requirements R-01 to R-17, analog and firmware design, pin map, host protocol, 98 recorded decisions and 36 firmware rules that guard hardware. The last four, D-95 to D-98, are the decisions of the project owner on the four points that the simulations raised | Every figure is a datasheet value, a calculation, a simulation or an estimate; the tests of its section 11 have to confirm them. Three of the four new decisions are stated here and not drawn yet. Where the simulations of 2026-10-10 differ from its text in fourteen other places, the text stands unchanged and its section 16 lists the place |
| [Schematic](hardware/doc/README.md) | 428 parts on 15 pages. It passes the electrical rules check, and its netlist was checked independently against the datasheets. Its circuits are simulated from that netlist | The [component checks](docs/checks/README.md): none is closed, so every part is a candidate. Three decisions that follow the simulations are not drawn yet: 10 nF in place of 1 nF at three capacitors of the rail monitor (D-95), a position for a capacitor at the buffer of the driver rail (D-96), and the two parts of the damper on the module input fitted (D-98) |
| [Board](hardware/README.md#board) | 150 mm × 100 mm, four layers, 425 footprints, 984 of 984 connections drawn, no violation in the design rules check. The layout was reviewed with scripts and checked by independent calculation. Calculated from the drawn copper: the 1 A path is 19.5 squares in source meter mode and 23.3 squares in ampere meter mode against a limit of 30, and the surface leakage into the measured node is 5.1 nA against a budget of 10 nA. The seven points where the layout departs from the first wording of section 10 of the specification are recorded as decisions D-87 to D-93 | No person has reviewed the board in the KiCad editor; open items need parts moved, the capacitor loops of the converters among them; names on the silkscreen and probe grounds at the test points are missing; the temperature rise of the linear regulator is an open check, read on the first board (D-93). The position for a capacitor of D-96 is not on the board yet: it adds one footprint |
| [Bill of materials](hardware/doc/bom.csv) | 151 lines, each with a part number and a maker, exported from the schematic | Three lines had no stock on 2026-10-09. The file still shows the state before the decisions of 2026-10-10, with three positions without parts: the two parts of the damper on the module input are fitted by D-98 and get their part numbers when the schematic is changed, the three capacitors of D-95 change their value, and the detector position at the boost converter stays empty (D-97) |
| [Circuit simulations](simulation/README.md) | The circuits of draft A2 simulated in ngspice from the netlist of the final schematic, in a package of their own (D-94): 134 benches, 93 on the circuits of the board in ten blocks and 41 that put the models written for the project into the test circuits of their datasheets. Of 3162 figures 1834 pass, 122 fail and 1206 carry no limit. The central design figures of the specification come out again block by block: shunt ladder, signal chain, range logic with requirement R-07, source meter, output stage, path switches, rails, power input and digital lines. The package has 777 tests; lines and branches are covered in full, the one module that loads the simulator excepted | The four points that the simulations raised are decided (D-95 to D-98): the capacitors of the rail monitor, the buffer of the driver rail, the detector position at the boost converter and the damper on the module input. The results are still those of the circuit before these decisions; the benches run again when the change is drawn. In fourteen places the simulation and the text of the specification differ; the text stands unchanged until the owner decides. What stays for the bench: leakage at the nanoampere level, the multiplexer at +12 V and −4 V, the programs of the controller, coupling through the board, temperature. Every active part is a model written from its datasheet, and nothing is measured. The simulations ran on one machine; the `Simulation` workflow has not been started yet |
| [Firmware](firmware/README.md) | Core in C that needs no hardware, with unit tests on the PC: wire protocol, block queue, settling window, step-down rule, device state machine. The build project is still the one of the first plan, for the ESP32-S3 | No build for the Pico 2, no PIO program, no adapter for any hardware, no command handler, none of the firmware rules of the specification |
| [Host software](host/README.md) | Python package with protocol, transports, device client, capture helpers and a device simulator, tested against that simulator | Its nominal calibration and its handling of flagged samples do not follow draft A2 yet; no command that captures from an instrument, no viewer and no export |
| [Protocol](protocol/README.md) | One definition; the constants of firmware and host and the shared test vectors are generated from it | What draft A2 reports beyond it, listed in section 16 of the specification |
| [Tools](tools/README.md) | [`tools/board/`](tools/board/README.md): a Python package that calculates the layout figures from a dump of the board file: copper resistance in squares and milliohms, lengths of the Kelvin pairs, surface leakage into the measured node. 260 tests on synthetic boards, lines and branches fully covered | Calibration and production test: two empty folders. The `Tools` workflow has not been started yet. The scripts that drew the layout are not in the repository |
| Measurements | None: no board has been built | The phases of the [roadmap](#roadmap) |

Next steps, in this order:

1. **Draw the decisions that follow the simulations.** The project owner
   decided the four points on 2026-10-10: decisions D-95 to D-98 of the
   specification. Three of them change the schematic and are not drawn
   yet: 10 nF in place of 1 nF at three capacitors of the rail monitor,
   the comparators that tell the controller that the analog supplies
   stand (D-95); a position for a capacitor at the buffer of the driver
   rail, the supply of the amplifier that drives the converter, which
   needs a footprint and so a change of the board (D-96); and the two
   parts of a damper, a resistor with a capacitor, on the module input,
   the supply that comes through the USB connector of the Pico 2, on pads
   that the board already has (D-98). The fourth leaves the position for
   a voltage detector at the boost converter, which makes the supply of
   the analog rails, without a part and changes only the text of that
   position (D-97). After the change come the
   electrical rules check and the design rules check, the bill of
   materials and the pictures exported again, the netlist snapshot of the
   simulations written again and the benches of the changed blocks run
   again. Until then the schematic, the board, the bill of materials and
   the results of the simulations show the earlier state.
2. **Decisions that are still open.** They are the project owner's. The
   fourteen places where the text of the specification and the simulation
   differ: each one that changes the text becomes an entry in its
   decision log. And whether proof-of-concept boards are ordered on this
   state. The
   [simulation guide](simulation/README.md#what-the-simulations-say) gives
   every place with the bench that shows it, and section 16 of the
   specification lists them as open.
3. **Board.** Four things stand between the reviewed layout and
   fabrication. First, a person opens the board in the KiCad editor and
   reviews it; so far it was drawn and checked with scripts only. Second,
   the open items that need parts moved are a change of placement with a
   local redraw: the capacitor loops of the converters, the inductor of
   the pre-regulator and the others. Third, the silkscreen and test point
   items: net names, jumper functions, probe grounds, a frame for the
   serial number. Fourth, the thermal check of D-93: the temperature rise
   of the linear regulator at full dissipation is read on the first board.
   The [hardware guide](hardware/README.md#still-to-do) lists the open
   items one by one. The simulations judge the circuits, not the copper:
   of their decisions only the position of D-96 touches it.
4. **Software.** Bring the host package and the firmware to what the
   specification of draft A2 asks: the nominal calibration, the fault
   causes and the protocol items of its section 16. Then port the firmware
   to the Pico SDK. The [firmware guide](firmware/README.md) and the
   [host guide](host/README.md) list the differences.

Until 2026-10-10 this list had a step to file the simulations. It is
done in another form. The files of the earlier simulations, from which
the specification took its figures marked "simulated", are not filed;
the circuits were simulated again from the netlist, and the package, the
benches and their results are in [`simulation/`](simulation/README.md),
where a reader can run them again.

The [component checks](docs/checks/README.md) follow, of which none is
closed, and the phases of the [roadmap](#roadmap), starting with the risk
prototypes of phase 1. Three of those prototypes settle what the
simulations leave open: the reaction time of the range sequencer, which is
an input of every simulation of the range logic, the loop of the
pre-regulator at its low end, and the start of the boost converter from a
supply limited to 0.7 A.

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
| Circuit simulations | The circuits of the schematic simulated from its netlist on 2026-10-10 in 93 benches: 1356 figures pass, 105 fail and 1136 carry no limit. The four points that they raised are decided (D-95 to D-98), and three of them are not drawn yet ([Circuit Simulations](#circuit-simulations)) |

The schematic was checked independently against the datasheets of its
parts. That closes none of the
[component checks](docs/checks/README.md): the parts are candidates. The
simulations close none either: they run on models written from those
datasheets.

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
them. A fifth came after the review: the three decisions that follow the
circuit simulations and are not drawn yet, of which the position for a
capacitor at the buffer of the driver rail adds a footprint to this board
(D-96; [Project Status](#project-status)).

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

## Circuit Simulations

The circuits of the carrier board are simulated from the netlist of the
schematic. A bench names parts of the schematic by their reference
designators, the package in [`simulation/`](simulation/README.md) writes
their elements from a snapshot of that netlist, and ngspice runs the
circuit: no part of the board is typed by hand. What stands around the
parts is typed by the bench and named in its notes: sources, loads,
cables, and in some benches a stand-in for a neighboring block of the
board. The simulator is the ngspice library that KiCad 10 ships. Every
active part is a model written for this project from its datasheet, a
typical part at room temperature. 41 benches put these models into the
test circuits of their datasheets; four models have no such bench, the
analog multiplexer among them. The models of the manufacturers may not be
copied into the repository; where a copy is present they give a second
value.

Everything in this section is simulated. Nothing is built and nothing is
measured: a figure that passes says that the circuit as drawn keeps its
limit with these models, not that a board will. Elsewhere on this page a
figure marked "simulated" is one of the specification, taken from the
earlier simulations of the draft.

| Block | Benches | Pass | Fail | No limit |
| --- | --- | --- | --- | --- |
| [Shunt ladder](simulation/results/ladder/README.md) | 2 | 20 | 0 | 6 |
| [Signal chain](simulation/results/signal_chain/README.md) | 11 | 113 | 8 | 111 |
| [Range control logic](simulation/results/range_logic/README.md) | 12 | 143 | 6 | 122 |
| [Source meter](simulation/results/source_meter/README.md) | 12 | 176 | 3 | 247 |
| [Output stage](simulation/results/output_stage/README.md) | 6 | 151 | 6 | 142 |
| [Path switching](simulation/results/path_switching/README.md) | 15 | 288 | 19 | 235 |
| [Power input and logic supplies](simulation/results/power_input/README.md) | 13 | 190 | 27 | 113 |
| [Analog rails and rail monitor](simulation/results/analog_rails/README.md) | 10 | 105 | 25 | 108 |
| [Digital lines and monitors](simulation/results/digital/README.md) | 10 | 145 | 11 | 49 |
| [Whole measuring path](simulation/results/system/README.md) | 2 | 25 | 0 | 3 |
| Circuits of the board, ten blocks | 93 | 1356 | 105 | 1136 |
| [Models against their datasheets](simulation/results/models/README.md) | 41 | 478 | 17 | 70 |
| All | 134 | 1834 | 122 | 1206 |

A bench is one circuit with its stimulus. It takes figures from the
waveforms and judges each one against its limit: a figure of the
specification where it states one; else a rating or a figure of a
datasheet, a value that the bench calculates, or a limit that the bench
sets and names. For a model the limit is the figure of its datasheet with
the tolerance that this project asks of a model. 1206 figures carry no
limit: they are values that nothing limits. A figure that fails is kept
as it is. Most of the 122 are of five kinds: a point that is decided
since and not drawn yet, a figure of the specification that the circuit
does not give, a rating that a fault case passes, an option that is not
in use, and a model that misses its datasheet. The guide
[sorts them by block](simulation/README.md#reading-the-failures).

How close the simulated values lie: for 595 figures of the board blocks
the pages print the distance from a stated value, in most cases the one
that the specification states. 368 lie less than 5 % from it, 434 less
than 10 % and 489 less than 25 %. The
[index of the results](simulation/results/README.md) has every bench, and
the page of each block has the values, the graphs and the decks, the
circuit files that the simulator ran. The whole suite ran on one Windows
machine and takes 29 minutes there.

### What the Simulations Say

**Reproduced.** The central design figures of the specification come out
of circuits taken from the netlist. That is a second calculation with
models, not a confirmation by measurement. Among them:

- Requirement R-07: on a step from 1 µA to 500 mA with 1 µF at the output
  the drop is 301.9 mV with nominal delays, and 388.2 mV with every delay
  at its limit and the capacitor 10 % low, against the limit of 500 mV.
  With 10 µF it is 168.3 mV and 179.2 mV, against 250 mV. An amplifier
  with half the bandwidth of its model, which is an assumption, takes the
  two worst cases to 400.3 mV and 180.8 mV.
- The jump to the 1 A range takes 360.8 ns from its threshold with
  nominal delays and 480.3 ns with the worst ones, against a target of
  550 ns. The 100 ns of the sequencer are an input of that run.
- Gain 19.93 and zero code 1313; one code is 1.914 nA in the lowest range
  and 19.14 µA in the highest. After a jump to the highest range the chain
  settles to 0.1 % of the range in 45.37 µs, and in 49.2 µs at the most
  over the cases that were run. The noise of one sample in the lowest
  range is 2.098 nA from a quiet supply.
- The source meter gives 799.5 mV and 5 V at its two nominal codes in
  steps of 1.282 mV, and its regulator keeps 449.2 mV to 631.9 mV of head
  room on the curve of R-08 with nominal parts.
- The in-rush into 2200 µF at the output is 856.1 mA, below the trip
  level, and the closed path drops 155.7 mV at 1 A in ampere meter mode,
  with the 20 mΩ that the specification allows for copper and contacts
  (limit 200 mV).
- With its switch open the external supply input takes 184.6 µA at +20 V
  and 597.9 µA at −20 V, against a limit of 1 mA.

**Four points, decided.** The simulations raised them for a decision
before boards are ordered, and the project owner decided them on
2026-10-10. Three are not drawn yet, so the results above are still those
of the circuit before them:

1. The capacitors of the rail monitor become 10 nF (D-95). With 1 nF as
   drawn and a comparator at its least hysteresis, an edge of PWR_GOOD
   moves its own threshold and gives a burst of edges on a slow rail.
   With 10 nF the threshold moves by 525 µV, below that hysteresis, where
   1 nF gives 3.149 mV to 3.606 mV; the one run made with 10 nF, at a
   slower slope, shows one edge. The capacitance between the pins that
   couples the edge is an assumption.
2. The buffer of the driver rail of the converter gets a position for a
   capacitor at its input, whose value is chosen on the bench (D-96). Its
   loop has 41.92° of phase margin as drawn, not the 54° that the
   specification stated, and it is stable. The model of the manufacturer
   gives 68.99°, with input capacitances that are not those of its
   datasheet. No run with the capacitor exists, and the position needs a
   footprint.
3. The position for a voltage detector at the boost converter stays
   without a part (D-97). As drawn the converter starts in one go from an
   input limited to 0.67 A to 0.85 A. A detector with a time-out of
   0.24 s in that position would stop that start and, with 1 mA of load,
   repeat it four times in the 1.1 s of the run without completing it.
   The result rests on a model of the converter below 2.7 V, where its
   datasheet says nothing, on a source with a flat current limit and on
   the 1 mA, so the start on a prototype stays a test of phase 1.
4. The damper on the module input is fitted (D-98). When the data cable
   is plugged again on a port at 5.5 V behind a short cable while USB-C
   supplies the instrument, the input of the power multiplexer reaches
   5.941 V with a limiter of typical reaction, and 6.002 V with one
   assumed to react in 15 µs, against a rating of 6.0 V. With the damper
   fitted the peak is 5.502 V in the runs made; the case that is worst
   with the damper, a longer gap of the contact, was not run, and neither
   was the recharge pulse at a change of input.

**Fourteen places where the simulation and the text differ.** The round
proposes no change of hardware for them; that is the owner's decision
too. They are figures and rules of the specification, and things on which
it is silent: how long the over-current comparator stays high while a
large capacitor recharges, the ladder clamp in a short circuit, the advice
on a capacitor at the VIN terminals, the times at power-off, the opening
time of the output switch at 0.8 V, the current in the output suppressor
at a trip, three figures of the mode switches, a check of section 16 that
the simulation does not meet, the list of terms of the noise budget, the
timing estimates of the converter lines, the leakage of the monitor
converter, figures of the source meter, the in-rush on a computer port
and the range that a logic input withstands. The text of the
specification stands until the owner decides. The fourteen are not every
difference: the guide names the further figures that fail against a
rating of a datasheet.

**What stays for the bench.** The simulations cannot settle the linear
range of the amplifier near the negative rail, the loop of the
pre-regulator at its low end, the linear regulator at light load, a supply
that leaves its range while the path is closed, leakage at the nanoampere
level, the programs of the controller, coupling through the board and
temperature.

The [simulation guide](simulation/README.md#what-the-simulations-say) gives
each of these with its figures, with the bench that shows it and with the
limits of the models behind it.

### Two of the Results

Both pictures are plots of simulation runs, not measurements.

![Simulated: a step from 1 µA to 500 mA with 1 µF at the terminals](simulation/results/range_logic/load-step.drop-1u.png)

Requirement R-07 in a simulation. The load steps from 1 µA to 500 mA in
the lowest range, with 1 µF at the terminals and 5 V at the output. From
the top: the drop between the supply node and the output terminal, the
voltage at the terminal, the current in the branch of the 0.1 Ω shunt, and
the selected range. The step-up comparator takes the next range, then the
jump comparator takes the path to the 1 A range. The drop peaks at 301.9 mV
with nominal delays and at 388.2 mV with every delay at its limit and the
capacitor 10 % low, against the limit of 500 mV. The requirement also
allows the drop above 0.2 V for 1 µs at the most, which is the dashed
line; the two curves are above it for 302 ns and 390 ns. The third curve
gives the sequencer 300 ns, three times what the specification allows it,
and reaches 445.1 mV. The reaction time of the sequencer is an input of
this run: the program that has to keep it is not written.

![Simulated: load current to code and to the reading, every range held](simulation/results/system/accuracy.transfer.png)

The whole measuring path in a simulation: ladder, multiplexer and
amplifier chain as one circuit from the netlist, each range held while the
load current rises to 120 % of its full scale. Above, the code of an ideal
16-bit converter at the converter input: the four ranges cover 100 nA to
1.2 A, with zero at code 1313. Below, the error of the reading with the
nominal calibration against the load current; at small currents it is the
rounding to one code. The amplifiers have no offset, no bias current and
no noise in this run, and the converter is arithmetic.

## Repository Structure

| Path | Content | License |
| --- | --- | --- |
| [`firmware/`](firmware/) | Firmware of the controller: hardware-independent core with its unit tests; target build not ported to the Pico 2 yet | MIT |
| [`hardware/`](hardware/) | KiCad project of the carrier board and its pictures; the folder for fabrication outputs is empty | CERN-OHL-P v2 |
| [`simulation/`](simulation/) | Circuit simulations of the carrier board: the package `circuit-sim` with its tests, a snapshot of the netlist of the schematic, the models written for the project, the benches and their results | MIT |
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
| 5 | Carrier board, revision A, with the Pico 2 plugged in. Entry: the open checks that precede fabrication are closed and the layout is reviewed | Not started; draft A2 of the schematic and a board with every connection drawn exist, drawn ahead of the phases. The layout was reviewed with scripts and by calculation, and its seven deviations from section 10 are recorded decisions (D-87 to D-93); three decisions that follow the simulations are still to be drawn (D-95, D-96 and D-98), and the review by a person in KiCad and the open items remain |
| 6 | Calibration, protocol freeze and host software | Not started |
| 7 | Revision B and release | Not started |

Draft A2 is the hypothesis that the phases test: the component checks and
the results of phases 1 to 4 change it before revision A is fabricated.
The circuit simulations test the same hypothesis ahead of the bench, with
models in place of parts. They are not a phase and close none: a phase is
closed by measurements. The work that comes first is listed under
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
| Circuit simulations | Python 3.10 or later; the ngspice shared library, which KiCad 10 ships | [`simulation/README.md`](simulation/README.md) |
| Documentation | Node.js, for `npx --yes markdownlint-cli2@0.23.3` | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

No instrument is needed to work on the software: the firmware logic runs in
unit tests on the PC, the host package talks to a simulator, the board
figures package is tested on small synthetic boards, and the circuit
simulations need only the ngspice library that KiCad installs.

## Engineering Practices

- Logic that does not need hardware is kept apart from the code that does,
  in firmware and in host software, and is covered by unit tests.
- The wire protocol has one definition. The constants of both sides are
  generated from it, and both codecs must reproduce the same test vectors.
- Seven continuous integration workflows, one per area (`Firmware`,
  `Host`, `Protocol`, `Tools`, `Simulation`, `Hardware`, `Docs`), build
  the firmware, run the tests with coverage floors, run the formatters and
  static analyzers and check the hardware project. The firmware build is
  still the one of the first plan, for the ESP32-S3, until the port to the
  Pico SDK. For now the workflows are started by hand, not on every push
  (D-22); the same checks run locally before a change is recorded.
- The board figures package in `tools/board/` has the gates of the host
  software: tests with a coverage floor of 90 % of lines and branches,
  ruff, mypy in strict mode, and the wheel built and installed. They ran
  locally on Windows; the `Tools` workflow, which repeats them on Linux
  and macOS too, has not been started yet.
- The simulation package in `simulation/` has those gates as well: 777
  tests, of which 11 need the ngspice library, ruff, and mypy in strict
  mode over the package, its tests and the benches. Lines and branches
  are covered in full against a floor of 90 %; the one module that loads
  the simulator runs in a child process and is outside that measurement.
  The gates ran locally on Windows with Python 3.11; the `Simulation`
  workflow has not been started yet. They cover the package, not the
  board: a figure that fails in a simulation breaks no gate. It is a
  finding, and it is kept.
- Timing, throughput and analog behavior are not claimed from tests. They
  are measured on the bench and recorded in a report. A simulation is
  filed as a simulation: it closes no check and no phase.

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
- [Simulation guide](simulation/README.md) and
  [simulation results](simulation/results/README.md): what the circuit
  simulations reproduce, the four points that are decided, where they
  differ from the text of the specification, the limits of the models, and
  every figure with its graph and its circuit file.
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
