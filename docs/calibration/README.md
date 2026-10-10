# Calibration

How the instrument turns ADC codes into amperes and DAC codes into volts,
and how the values behind that are found for one board and stored.

## Status

The calibration procedure is not written. It is planned for phase 6
(section 13 of the [specification](../specification.md)), and it cannot be
written earlier: no board exists, and a procedure has to be tried on one.
Until then section 8 of the specification defines what is calibrated, how
the values are stored and which reference equipment is needed. This page
summarizes that section and says what is missing around it.

Nothing below is measured. Each figure is a datasheet value, a calculation,
a simulation or an estimate, as the specification marks it.

## What Section 8 Defines

The conversion runs on the host. The instrument sends raw ADC codes with
the range that was active, and the host computes
`I = (code − offset[r]) × gain[r]` with one gain and one offset per range.
Requirement R-12 asks for these values to be stored on the device.

- **Nominal values.** Before a board is calibrated the gain of a range is
  `VREF / (65536 × G × R[r])`, with the amplifier gain G = 19.93 and, for
  R[r], the shunt of the range in parallel with the shunt of range 0, which
  always stays in the path: 1 kΩ, 31.95 Ω, 0.999 Ω and 0.1 Ω for ranges 0
  to 3 (calculated, section 4.3). The set-point of the source is
  10 mV + code × 1.2817 mV before calibration (F-30). Nominal values are
  design targets, never a calibration.
- **The stored record.** Gain and offset of each range, gain and offset of
  the DAC, the length of the settling window and the calibration
  temperature, with a version field and a CRC. The record lives in the
  flash of the Pico 2, because the carrier board has no memory of its own
  (D-82).
- **What binds the record to a module and to a carrier.** The record
  carries the 64-bit chip identifier of the RP2350 and the serial number
  and revision of the carrier. The serial number is entered at calibration
  and written by hand into a frame on the silkscreen of the carrier
  (section 10.7). A record whose chip identifier does not match, which is a
  flash image copied to another module, is reported by GET_INFO as not
  calibrated, and so is a missing or corrupt record; nominal values are
  then used and flagged. A module moved to another carrier is not detected
  by firmware. For that case the host shows the stored serial number at
  every connection, to be compared with the label (section 9).
- **Open-switch zero.** With the output switch open the current is zero,
  so firmware measures the offset of every range, locked one by one. It
  runs at start-up and on the command CAL_ZERO, no earlier than 200 ms
  after the output switch opened or after a reset, because the gate of
  that switch needs this time to rest (F-36). The offsets are kept in RAM,
  not in flash. The zero of range 0 drifts by up to 0.7 nA/°C from the
  amplifier alone (datasheet maxima, calculated), so firmware takes the
  zero again whenever the output is off and the board temperature has
  moved by more than 2 °C.
- **Closed-switch zero (D-59).** The open-switch zero does not see what
  loads the node behind the shunts beyond the output switch. With the
  output on and the terminals open, at 5.0 V and at the working voltage,
  300 ms or more after the output was switched on (F-36), the reading of
  range 0 is stored and subtracted. The limit for a board is 50 nA at
  5.0 V and room temperature; the typical figures add up to 4 nA to 6 nA
  at 40 °C (estimate). The step needs the DUT disconnected once per
  calibration.
- **Gain calibration.** In source mode into precision resistors, with the
  output voltage read by a reference multimeter; two points per range,
  near 10 % and 90 % of full scale. It removes the tolerance of the
  shunts, 0.1 % to 0.5 % (D-68), the share of the range 0 shunt in the
  higher ranges and, at the calibration temperature, the leakage across
  the ladder. It does not remove the drift with temperature, 25 ppm/°C for
  ranges 0 to 2 and 50 ppm/°C for range 3 (datasheet values), which is why
  the calibration temperature is stored. After a reported sequencer fault
  (F-21) the gain of range 2 is calibrated again: its 1 Ω shunt has
  carried 6.3 W to 8.4 W for up to 2 ms (calculated).
- **DAC calibration.** Nine set-points or more, at room temperature,
  measured with the reference multimeter (D-58, F-30). Two points do not
  cover the integral non-linearity of the DAC, 15.4 mV at its limit and
  2.6 mV typical (datasheet values, calculated), against the criterion of
  10 mV in the test of R-08 (section 11).
- **Settling window.** After a range change the samples are flagged
  invalid for 7 samples by default (F-35; simulated: 45 µs to 0.1 % of
  range). The length is measured on the prototype with a fast load step
  and then stored as a constant.
- **Output settling.** For 250 ms after the output switch closes the
  samples read low by the charging current of its gate, 0.3 µA after 50 ms
  and 4 nA after 200 ms (simulated). The time is a constant of the host,
  which marks these samples and leaves them out of statistics below 1 µA
  (section 9).

Three more values are found on a board and stored, by the firmware rules of
section 6.6, and section 8 does not list them in the record. Where they are
kept is open, and section 16 lists it among the points to decide:

- the offset of the monitor channel that reads VIN, stored at calibration
  (F-26); before it a true 0.8 V can read 0.67 V (calculated);
- the constants of the input model behind the power budget, calibrated on
  the first board (F-14);
- the thermal limit, a constant taken from the first board (F-15).

## Reference Equipment

Section 8 names three things, and no model or accuracy class beyond the
tolerance of the resistors:

| Equipment | Used for |
| --- | --- |
| Precision resistors, 0.01 % | The loads of the gain calibration, two points per range |
| Reference multimeter | The output voltage in the gain calibration and the nine or more set-points of the DAC calibration |
| A fast load step | The length of the settling window, measured once on the prototype |

The DAC calibration is done at room temperature, and the calibration
temperature is stored with the record. Which multimeter is
good enough for the target of R-05, ±1 % of reading ±0.1 % of range, is
part of the procedure that is not written.

## What Is Not Written

- **The procedure.** The steps, the resistor values of each range, the
  order, the pass limits and the form of the result. It belongs on this
  page.
- **The tool.** The scripts under
  [`tools/calibration/`](../../tools/README.md) that drive the instrument
  and the reference equipment. The directory is empty.
- **Firmware support.** The `cal` component of the firmware has no code:
  no record, no storage in flash, no check of the chip identifier, no zero
  calibration. The firmware is not ported to the Pico 2 either (see the
  [firmware guide](../../firmware/README.md)).
- **Host support.** The host package converts codes with a nominal table,
  and its client can send CAL_ZERO and CAL_WRITE to the simulated
  instrument. The nominal table still uses the values of the first plan, a
  gain of 20 and shunts of 1 kΩ, 33 Ω, 1 Ω and 0.1 Ω, not the nominal
  values above. The host does not read a table from the instrument, does
  not show the carrier serial number, does not mark the output settling,
  and has no guided calibration (see the
  [host guide](../../host/README.md)).
- **Protocol support.** The command CAL_WRITE carries a target, a gain and
  an offset. How the other fields of the record reach the instrument (the
  settling window, the temperature, the serial number of the carrier, the
  DAC set-points beyond a gain and an offset) and how the host reads the
  record and its state back through GET_INFO is not defined; the response
  data of GET_INFO is provisional (section 7.4). See the
  [protocol page](../protocol/README.md).

The order of that work follows the next steps in the
[README](../../README.md#project-status) of the repository. First the
software, without a board: the nominal values of draft A2 in the host
package, the decision of section 16 on how the record travels, the record
in the `cal` component, and then the port of the firmware to the Pico SDK.
The procedure and the tool come in phase 6, on a carrier board of
revision A.

A change to the calibration format, once one exists, is a breaking change
(see the [contributing guide](../../CONTRIBUTING.md)).
