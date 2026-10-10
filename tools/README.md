# Tools

Scripts used to build and check the instrument, as opposed to the host
software its users run.

## Status

One tool exists: the board figures in `board/`, which calculate the figures
of the carrier board layout from its KiCad file. They are tested without
hardware and measure nothing.

The circuit simulations of the carrier board are not a tool of this
directory. They are a package of their own at the root of the repository,
in [`../simulation/`](../simulation/README.md) (decision D-94 of the
specification): the board figures judge the copper of the board, the
simulations the circuits of the schematic.

The calibration tool and the production test are not started. Their two
directories are empty, and nothing they would drive exists yet: no
board is built, the firmware is not ported to the Raspberry Pi Pico 2, and
the calibration commands of the protocol are provisional. Calibration is
the work of phase 6, and a production test needs the carrier board of
phase 5 (section 13 of the [specification](../docs/specification.md)).

| Path | State | What the tool does, or will have to do |
| --- | --- | --- |
| `board/` | Exists, tested without hardware | Calculate the layout figures that the documents quote from the board file of the carrier: the 1 A path in squares, a path on one layer, the lengths of the Kelvin pairs, the surface leakage into the measured node. See the [board figures guide](board/README.md) |
| `calibration/` | Empty | Run the calibration of section 8 of the specification on one instrument against reference equipment, and write the record into the flash of its Pico 2 |
| `production-test/` | Empty | Check every assembled carrier board before it is calibrated and before a DUT is connected. The specification has no section for this test yet; the checks it already asks of every board are listed below |

What comes next here: the figures are calculated again after every change
of the board, and the `Tools` workflow is started when the owner asks for
it. The calibration tool and the production test wait for the software
step and for a board, as their sections below say.

The form of the calibration and production-test scripts is not decided.
The host package already holds the link to the instrument (see the
[host guide](../host/README.md)); a tool built on it keeps the wire
protocol in one place.

## Board Figures

`board/` is a Python package, `board-figures`, with a command of the same
name. It answers the layout rules of section 10 of the specification that
a design rules check does not: the resistance of the 1 A path in squares of
copper and in milliohms, whether a loop closes on the top layer without a
via, the center-line lengths of the three Kelvin pairs, the vias of the
sense nets, and the surface leakage into the measured node. Every figure is
calculated from the drawn copper. None is measured, and no board is built.

- An adapter that runs under the Python of KiCad writes the board as JSON.
  The package reads that file and needs numpy, scipy and shapely, not
  KiCad.
- The nets, pads and assumptions of the carrier board are in
  `board/carrier.toml`, not in the code.
- The calculations are pure functions on an immutable model of the board.
  Their 260 tests run on small synthetic boards with answers known by hand
  and need neither KiCad nor the board file; lines and branches are covered
  to 100 %, above the floor of 90 %.
- On the board in `hardware/kicad/` the package gives the figures that the
  documents quote: 19.5 squares (10.4 mΩ) in source mode and 23.3 squares
  (12.3 mΩ) in ampere mode for the copper of the 1 A path, against a limit
  of 30 squares (D-92), and a surface leakage into the measured node of
  4.46 nA on the top layer and 0.67 nA on the bottom layer, against a
  budget of 10 nA.
- Not in the repository: the scripts that drew the layout. The
  simulations of the circuits are filed, in
  [`../simulation/`](../simulation/README.md).
- The checks (ruff, mypy in strict mode, pytest with coverage on Linux,
  Windows and macOS, a build of the wheel) are the workflow `Tools`,
  started by hand like the others (D-22). It has not been started yet: so
  far the checks ran on one Windows machine.

How to make the dump, each command with an example on the carrier board,
the method and the assumptions of each calculation and its limits are in
the [board figures guide](board/README.md).

## Calibration Tool

Section 8 of the specification defines the calibration; the
[calibration page](../docs/calibration/README.md) summarizes it. What it
asks of a tool:

- Ask for the serial number and the revision of the carrier, which the
  operator also writes into the frame on the silkscreen (section 10.7).
  The carrier has no memory, so the record in the module is the only place
  the instrument keeps the number (D-82).
- Closed-switch zero: with the output on and the terminals open, at 5.0 V
  and at the working voltage, 300 ms or more after the output was switched
  on, read range 0 and store the value. Fail the board above 50 nA at 5.0 V
  and room temperature (D-59).
- Gain of each range: in source mode into precision resistors of 0.01 %,
  two points near 10 % and 90 % of full scale, with the output voltage read
  by a reference multimeter.
- DAC: nine set-points or more at room temperature, each measured with the
  reference multimeter (D-58, F-30).
- Write the record: gain and offset of each range, the DAC values, the
  length of the settling window, the calibration temperature, a version
  field, a CRC, the 64-bit chip identifier of the RP2350, and the serial
  number and revision of the carrier.
- Repeat the gain of range 2 on request: the specification asks for it
  after a reported sequencer fault (F-21).

Section 8 does not ask for a read-back in so many words. It follows from
what the section says of GET_INFO, which flags a missing, corrupt or
foreign record as not calibrated: a tool that ends by reading the state
back shows that the record it wrote is the one in use.

The open-switch zero is not a job of the tool: firmware runs it at every
start and on the command CAL_ZERO.

Three values are found on a board and stored, and section 8 does not list
them in the record. Where they are kept is not decided (an open point of
section 16), so the tool cannot be written around them yet:

- the offset of the monitor channel that reads VIN, "stored at
  calibration" (F-26);
- the constants of the input model behind the power budget, "calibrated on
  the first board" (F-14);
- the thermal limit, "a constant taken from the first board" (F-15).

What stands between today and a first version of the tool, in order: the
way the record travels in the protocol (CAL_WRITE carries a target, a gain
and an offset, nothing else; an open point of section 16), the `cal`
component of the firmware (it has no code), the firmware port to the Pico
SDK, and a board to try the procedure on. The first three are part of the
software step in the next steps of the
[README](../README.md#project-status) of the repository; the board is
revision A of phase 5.

## Production Test

The specification names the directory (section 12) and does not define the
test. What it does define for every board, and what a production test will
have to cover, is spread over several sections:

- The first power-up of section 13: the Pico 2 out of its sockets, six
  links not fitted, the test point TP9 as the switch, and the rails
  brought up one by one with the level expected at each test point
  (calculated or simulated levels). The simulations of the analog rails
  in [`../simulation/`](../simulation/results/analog_rails/README.md) give
  the order and the times of that power-up from the final netlist; they
  are simulated too, and the test replaces them.
- The items of section 16 that come before a DUT is connected to a board:
  every gate at or below 0.3 V in the states listed there, the output open
  within 100 ms of a halted supervision task (F-8), the gate lines low
  across a restart, then the gate ramp of the output switch and the in-rush
  with a capacitor in place of the DUT.
- The self-test of the firmware (section 6.4): the rails test of F-12, the
  ADC answering, the range logic stepping through all ranges and the zero
  calibration with the output open.
- The closed-switch zero against 50 nA (section 8), which is also the
  release test for the suppressor of VOUT, whose leakage at 5 V has no
  datasheet figure (section 11).
- The serial number written on the carrier and stored in the record
  (D-82, section 10.7).

Which of the tests of the verification plan (section 11) are run on every
board and which on the first boards only is not decided. That decision,
and a section of the specification for the production test, come before
the tool is written.
