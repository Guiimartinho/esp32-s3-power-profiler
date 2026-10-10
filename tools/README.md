# Tools

Scripts used to build and check the instrument, as opposed to the host
software its users run.

## Status

Not started. The two directories below are empty, and nothing they would
drive exists yet: no board is built, the firmware is not ported to the
Raspberry Pi Pico 2, and the calibration commands of the protocol are
provisional. Calibration is the work of phase 6, and a production test
needs the carrier board of phase 5 (section 13 of the
[specification](../docs/specification.md)).

| Path | State | What the tool will have to do |
| --- | --- | --- |
| `calibration/` | Empty | Run the calibration of section 8 of the specification on one instrument against reference equipment, and write the record into the flash of its Pico 2 |
| `production-test/` | Empty | Check every assembled carrier board before it is calibrated and before a DUT is connected. The specification has no section for this test yet; the checks it already asks of every board are listed below |

The form of the scripts is not decided. The host package already holds the
link to the instrument (see the [host guide](../host/README.md)); a tool
built on it keeps the wire protocol in one place.

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
  (calculated or simulated levels).
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
