# Carrier Board, Draft A2 in Pictures

The schematic and the board of [`../kicad/`](../kicad/), plotted so that the
design can be read without KiCad. The complete schematic is also in
[`schematic.pdf`](schematic.pdf).

Draft A2 is a review draft. Its schematic passes the electrical rules check
of KiCad, and its netlist was checked independently against datasheets.
The parts are candidates, no component check is closed, and nothing was
built or measured: every figure below is a datasheet value, a calculation, a
simulation or an estimate, as marked. The board is an autorouted draft that
needs a layout review before fabrication. The status and the open work are
in the [hardware README](../README.md); the reasons behind every value are
in the [specification](../../docs/specification.md), whose sections are
named with each sheet.

## Schematic

Fifteen A4 pages: the root sheet and fourteen sheets with 428 parts. Inside
a sheet every connection is a wire; supply rails use power symbols; a signal
that leaves a sheet ends on a hierarchical label, and the root sheet joins
the labels with wires. Each sheet carries notes with the design values of
its block. A part drawn with a cross is a position without a part.

### 1. Root

One block per sheet and the 48 signals between them. The supply rails are
not on this page: they are power symbols on the sheets.

The controller is in the middle. To its left are the sheets of the
measurement: the signal chain with the comparators above it, and the side
data, which collect the logic inputs, the comparator outputs and the status
lines for every sample. Below the controller are the shunt ladder and the
output stage. To its right are the source meter, the monitors and the path
switching, which joins the regulator output or the VIN terminal to the
supply node of the ladder. Of the three supply sheets at the right edge, the
logic supplies and the analog rails share the signal `5V_OK` with the source
meter. The digital inputs and the rail monitor are at the left edge; the rail
monitor has one output, `PWR_GOOD`.

![Root sheet](images/schematic-01-root.png)

### 2. Controller

The Raspberry Pi Pico 2 (U1) on its two sockets (MP1, MP2), the
only programmable part of the instrument. Sections 4.11 and 5 of the
specification describe it.

- Left side of the module: the console header J1 on GP0 and GP1, the
  reset button SW1 on the RUN pin, and the lines of the range sequencer,
  a state machine in PIO block 1. GP2 to GP7 drive the three range gates,
  the two address bits of the Kelvin multiplexer and the output switch; GP8
  to GP10 read the three comparators. GP11 reads the over-voltage detector
  of VIN through R1.
- Below it, GP12 to GP15 are the slow SPI bus of the DAC and of the monitor
  converter, with 2.2 kΩ in each line (RN1).
- Right side: PIO block 0 clocks the converter and reads its data and the
  side data in the same word, on GP16, GP17 and GP19 to GP21, with 47 Ω in
  each output (RN4). GP18 asks for the pre-regulator, GP22 selects the
  DAC through 47 Ω and R3, GP26 and GP27 ask for the two mode switches,
  and GP28 reads `PWR_GOOD` through R4.
- Top: the supply. The 5 V rail of the carrier feeds the VSYS pin through
  the Schottky diode D1. The VBUS pin leaves the sheet through the
  solder jumper JP1 as `PICO_5V`, the second power input of the
  carrier. The 3.3 V pins of the module are not connected, and its analog
  ground joins the ground plane through the link R2.

Every line that the module drives, except the console output, has a
resistor to a rail on the carrier. RN2 and RN3, 4.7 kΩ, pull the two chip
selects up to `+3V3_A` and the other SPI and acquisition lines down, so that
with the module in reset, in its boot loader or out of its sockets no
converter is selected and none converts; against the pull-down of a pad a
select stays at 2.8 V or more (calculated). The pull resistors of the gate
and address lines are on the sheets of their receivers.

The series resistors limit what a pin can push into an input whose supply
is absent: 1.39 mA into a slow SPI input and 1.90 mA into the select of the
DAC at the tolerance limits, against a rating of 2 mA (calculated; datasheet
value). R1 and R4 keep the two status lines true if a pin is set as
an output by mistake.

![Controller](images/schematic-02-controller.png)

### 3. Power Input

Two USB inputs, a current limiter for each, and a priority multiplexer that
connects one of them to the 5 V rail (section 4.1, decision D-47).

- Top row, from the left: the USB-C receptacle J2, a sink for 5 V, with
  the suppressor D2 and the capacitors C2 and C3 at its pins,
  then the limiter U4, an electronic fuse. The divider R9, R10
  turns it on at 2.92 V to 3.09 V and off at 2.67 V to 2.87 V; R15 sets
  the limit to 2.0 A, 1.81 A to 2.17 A with the tolerances (calculated).
  With an input above 5.54 V to 5.83 V it clamps its output at 5.28 V to
  5.61 V (datasheet values; R12 selects that level), and C4 sets the
  ramp of its output. TP3 shows the input current, 0.297 V per ampere
  (calculated).
- Behind the limiter: the damper R20, C9, C10 and C7, which
  take the ring of a contact that closes, and the Schottky diode D4
  across the limiter, which returns their charge when the plug is pulled.
- Middle: the two CC lines with their 5.1 kΩ pull-downs (R7, R11) and
  the ESD array U2. They leave the sheet to the monitor converter, where
  firmware reads what the source offers.
- Bottom row: `PICO_5V`, the USB voltage of the controller module, with the
  second limiter U3. It is the same circuit with a limit of 0.76 A,
  0.67 A to 0.85 A with the tolerances (calculated, R13), and without a
  ramp capacitor. R17 defines its output while the jumper is open. The
  crossed parts R14 and C5 are a position for a second damper, to be
  fitted if the bench shows the need (decision D-84).
- Right: the multiplexer U5. It drives `+5V` from the USB-C limiter
  while that output is above 2.15 V to 2.59 V (calculated; R18, R19,
  delayed by C8), otherwise from the module input, and it blocks reverse
  current into both inputs. Its status output `SRC_ST` is open while USB-C
  supplies the rail and low while the module input does. C11, 47 µF, is
  the bulk capacitor of the rail.

There is no fuse: the parts ahead of the limiter are protected by the source
alone. A live cable plugged into the receptacle lifts its pins to as much as
11.4 V with a 5.25 V source and 12.2 V with a 5.5 V source for microseconds,
while the rail never rises above the source (simulated); the limiter
withstands 21 V at its input (datasheet value). Test points: TP1 on the
receptacle, TP2 and TP4 on the two inputs of the multiplexer,
TP5 on `SRC_ST`.

![Power input](images/schematic-03-power-input.png)

### 4. Logic Supplies

The supervisor of the 5 V rail and the two 3.3 V regulators that it enables
(section 3, decision D-48).

- U6 compares the rail, divided by the 0.1 % resistors R21 and
  R22 and filtered by C12, with its internal reference. Its
  open-drain output `5V_OK`, pulled up by R25, goes low when the rail
  falls below 3.91 V, 3.83 V to 4.00 V with the tolerances, and returns
  0.18 s to 0.42 s after the rail is back above 4.12 V at the most
  (calculated from datasheet limits; R24 selects the delay).
- `5V_OK` is the enable input of U7, which makes `+3V3_C` for the logic
  of the carrier, and of U8, which makes `+3V3_A` for the converter, the
  comparators, the DAC and the reference. It leaves the sheet to the
  +12 V regulator, to the charge pump and to the transistor at the enable
  pin of the pre-regulator. The carrier therefore has one off state, which
  it reaches without firmware and in which only `+5V` and `+13V5` are up.
- TP9, held to ground, keeps the carrier in that state during
  bring-up.
- The green LED D5 on `+3V3_C` is lit while the supervisor has released
  the carrier. R23 loads the 5 V rail with 10 kΩ, so that the reverse
  current of the diode to the module cannot lift a rail that has no source.
- The four mounting holes H1 to H4, tied to ground, the three
  fiducials FID1 to FID3 and the test points of the rails are drawn
  here.

![Logic supplies](images/schematic-04-logic-supplies.png)

### 5. Analog Rails

The rails of the analog parts and the reference (section 3, decisions D-51
to D-53).

- Top left: the boost converter U10 with L1 and D6 makes `+13V5`,
  13.0 V to 14.1 V with the tolerances (calculated; feedback R32,
  R33). Its enable pin is pulled up to `+5V` by R29: it is not gated
  by `5V_OK` and runs whenever the rail is present. The crossed part U9
  is a position for a 3.08 V voltage detector at that pin. The converter has
  no under-voltage lock-out and no soft start (datasheet); the detector is
  the remedy if it does not start from the current-limited module input,
  which is a bench item (decision D-84).
- Top right: R37, 0.47 Ω, and C29 filter the boost output for the
  low-noise regulator U13, which makes `+12V_A`. R38 sets 12.0 V and
  C30 at the same pin sets the noise and the slow approach of the last
  volt: the rail is above 9.85 V after 8 ms to 17 ms and settles in about
  0.8 s (simulated). The Schottky diode D9 keeps the rail from being
  pulled below ground through its loads.
- Middle: the charge pump U11 makes `-4V_A` from the 5 V rail behind
  R30, 2.2 Ω, and C21, which take the edges of the rail. The 0.1 %
  feedback resistors R34 and R36 put the rail at −3.91 V to −4.05 V
  (calculated). `5V_OK` enables it through the divider R27, R28, and
  D8 keeps the rail from being pulled above ground.
- Bottom: the 2.5 V reference U12. It is supplied from `+3V3_A` through
  R31 and C20, and D7 ties its output to that rail by a Schottky
  drop, so that the reference is never present without the rail of the
  parts that receive it. C26 behind R35 is its damped output
  capacitor and C24 its noise filter.

With the clamps, `-4V_A` stays below +0.24 V and `+12V_A` above −0.23 V
while the other rail is absent (simulated). L1, R37, R31 and
R27 are the links of the first power-up: each starts one stage. Test
points TP12 to TP14 and TP16 are on the three rails and on the reference,
and TP15 is a probe ground at the boost converter.

![Analog rails](images/schematic-05-analog-rails.png)

### 6. Rail Monitor

Four open-drain comparators in one package (U14) share the line
`PWR_GOOD`, so that the line is high only while every rail they watch is
present (section 3, decision D-54).

- R41, R43 and R44 make the two thresholds as fractions of
  `+3V3_C`: 2.97 V and 1.645 V.
- From the left: `+3V3_A` against the upper threshold; `+12V_A`, divided by
  R45 and R46; `-4V_A`, lifted toward `+3V3_C` by R47 and R48;
  and the reference, divided by R49 and R50. The flag is low while
  `+3V3_A` is below 2.97 V, `+12V_A` below 9.85 V, `-4V_A` above −2.57 V or
  the reference below 2.245 V (calculated).
- R51 pulls the line up to `+3V3_C` and R52 pulls it down: the high
  level is 0.82 of the rail, and the line is low without supply.
- C32, C33 and C34 at the comparator inputs keep an edge of the
  flag from moving its own thresholds: in the package every output pin is
  the neighbor of an inverting input.

The flag reports that the rails are present, not that they are in
tolerance, and it cannot see a `+3V3_C` that stands low; firmware checks the
levels on the monitor converter. It is also low while the supervisor of the
5 V rail holds the carrier off. `PWR_GOOD` goes to the controller and to a
side bit of every sample; TP17 is its test point.

![Rail monitor](images/schematic-06-rail-monitor.png)

### 7. Source Meter

The supply of source mode: a switching pre-regulator, a linear regulator
behind it and the DAC that sets the output (section 4.2, decisions D-55 to
D-58).

- Top left: the buck-boost converter U16 with L2 makes `V_PRE` from
  the 5 V rail, in forced PWM. Its enable pin has R53 to ground and gets
  the request `SMU_ON` of the controller through Q1, whose gate is
  `5V_OK`: the converter runs only while the controller asks for it and the
  5 V rail is valid.
- Top right: the difference amplifier U19 with the 0.1 % resistors R63
  to R68 drives the feedback pin of the converter, so that
  `V_PRE` = 0.672 V + 0.956 × the output of the linear regulator
  (calculated). The pre-regulator follows the output, not the set-point,
  because the linear regulator cannot sink current: its input stays above
  its output also when a DUT holds the output up. R65 with C55 is a
  low-pass of 0.62 ms in the sense path, and one diode of D13 across
  R65 lets a rise of the output through at once.
- `V_PRE` carries C42, C45 and C50 and the bleeder R62, which empties
  them while the converter is off. The bead FB1, C46 and the damper
  C43 with R59 filter it for the linear regulator.
- Bottom right: the linear regulator U18. Its control pin is fed from
  `+13V5` through R61 and one diode of D10, with C47 at the pin.
  D11 clamps its input to its output and D12 its output to ground.
  R69 to `-4V_A` is the minimum load, 3.7 mA at 0.8 V and 6.9 mA at 5.0 V
  (calculated); it sits ahead of the shunts and is not measured. C53 and
  C54 are the output capacitors.
- Bottom left: the 12-bit DAC U15 on the slow SPI bus. Its reference
  input is half the reference, from R55 and R56. R54 with C41
  filters its output with 10 ms, and the amplifier U17 with a gain of
  2.1 (R57, R58) drives the SET pin of the regulator through R60.
  The output is 0.01 V to 5.26 V in steps of 1.28 mV; no SPI frame can
  command more than 5.26 V nominal and 5.39 V at the tolerance limits
  (calculated).

The source delivers 1.0 A up to 2.0 V, falling in a straight line to 0.6 A
at 5.0 V (R-08; calculated, a design figure until it is measured on several
boards). Test points: TP21 on `V_PRE`, TP22 on the regulator input,
TP26 on its output, TP23 on its SET pin, TP24 on the feedback pin,
TP19 on the reference of the DAC, TP18 on the enable pin, and the
probe grounds TP25 and TP20.

![Source meter](images/schematic-07-source-meter.png)

### 8. Path Switching

Two back-to-back MOSFET pairs connect either the regulator output or the
VIN terminal to the supply node of the ladder (sections 4.2 and 4.9,
decisions D-60 to D-63).

- Upper half: the source pair Q4, Q8 between `LDO_OUT` and
  `SUPPLY`. Lower half: the ampere pair Q5, Q9 between the VIN input
  and `SUPPLY`. The gate driver U20 in the middle drives both from
  `+12V_A`.
- Each pair has the same gate network; the parts of the ampere pair are
  named here. The driver charges the gate through R80, 100 kΩ, and
  C61 with R82 sets the ramp to 10.7 ms (calculated), so the pair
  closes as a source follower and the supply node rises with about 0.9 V/ms
  (simulated). One diode of D17 and R79 discharge the gate at once:
  the pair opens within 1 µs (simulated). The second diode ties the gate to
  `+12V_A`. R84 returns the gate to the common source. Q7 with
  R86 and D19 joins gate and common source when the common source
  goes below ground, so that a reversed supply cannot turn an open pair on.
- Interlock, left of the driver: Q2, driven by the source-mode request,
  and Q3, driven by the over-voltage detector, both pull the input of
  the ampere driver low. The two pairs can never be closed together, and
  the ampere pair stays open above the over-voltage level, whatever the
  controller asks. R70 and R71 hold both requests low while the pins
  of the controller float.
- Bottom left: the VIN input with the fuse F1, the bidirectional
  suppressor D14 and the detector U21. The detector compares VIN,
  divided by R73 and R74, with the reference; R76 gives the
  hysteresis and D15 clamps its input. It trips at 5.46 V, 5.41 V to
  5.51 V with the tolerances, and releases at 5.35 V (calculated).
- Right: the supply node with C62 and the damped branch C63, R87,
  which take the current of the supply leads when the over-current trip
  opens the output.

VIN works with 0.8 V to 5.0 V. While the ampere pair is open the terminal
withstands −20 V to +20 V and takes less than 1 mA (simulated). The
suppressor conducts from 22.2 V (datasheet value) and the fuse cannot
protect it: 20 V is the limit of the terminal. Test points: TP33 on the
supply node, TP27 on VIN behind the fuse, TP32 and TP31 on the
gates, TP30 on the detector output, and the probe grounds TP28 and
TP29.

![Path switching](images/schematic-08-path-switching.png)

### 9. Shunt Ladder

Four shunts for four ranges between the supply node and the node after the
shunts (sections 4.3 and 4.4, decisions D-66 to D-68).

- The shunts are along the bottom of the drawing: 1 kΩ for range 0
  (R101), always in circuit, 33 Ω for range 1 (R104), 1 Ω for range 2
  (R107) and 0.1 Ω for range 3 (R110). Each drops about 100 mV at its
  full scale of 100 µA, 3 mA, 100 mA and 1 A. R107 is a two-terminal chip
  on a four-pad Kelvin land and R110 a four-terminal part.
- Above each switched shunt is its MOSFET, on the supply side: Q12,
  Q13 and Q14. One branch is on at a time, on top of range 0, and two
  overlap for about 1 µs during a range change.
- Top left: the gate drivers U22 and U23 on `+12V_A`. Each input has
  1 kΩ to ground and 1 kΩ in series, so that every switch is open without
  the controller and a line that is high without `+12V_A` feeds 2.7 mA into
  an input (calculated). Each range gate has 100 kΩ to ground (R103, R106
  and R109) and no resistor to its source, which would bypass a shunt. The
  second half of U22 drives the output switch of the next sheet.
- Left: the ladder clamp Q10, Q11, two MOSFETs with gate and drain on
  the supply node and the source on the node after the shunts. Below their
  threshold they are off; in a hot plug or a short circuit they carry the
  surge until range 3 conducts and bound the ladder at about 4 V. R90,
  100 kΩ from the supply node to ground, sets the idle level and is the
  bias return of the amplifier.
- Right: the dual multiplexer U24 takes both sense taps of the active
  shunt to the amplifier (`INP`, `INN`), so the switches and the copper
  between the shunts add burden but no measurement error. Its address lines
  have 5.1 kΩ to ground (R95, R91): range 0 is selected while the
  pins of the controller float. R113 pulls its enable input up to its own
  supply.

The range state lives in the controller as a PIO state machine; this sheet
is what it drives. The leakage across the ladder has a budget of 100 nA at
100 mV and 40 °C, which no datasheet figure bounds: it is an open check,
and the clamp type stays a candidate until it is closed. Test points TP34
to TP36 are on the three range gates.

![Shunt ladder](images/schematic-09-shunt-ladder.png)

### 10. Output Stage

The output switch after the shunts, the two DUT connectors and the buffer
that copies the ladder output (sections 4.2, 4.8 and 4.9, decisions D-70 to
D-72).

- Middle: the output pair Q15, Q16 between the node after the shunts
  and VOUT. C71, 100 nF C0G, is the only capacitor on that node, and
  nothing resistive hangs on it: its current would be read as DUT current.
- Below it, the gate network. The driver charges the gate through R117,
  2.2 MΩ, against C74: the pair closes as a source follower and VOUT
  rises with 0.44 V/ms, 90 % of 5 V after about 20 ms. That limits the
  in-rush to 0.39 A into 1000 µF and 0.85 A into 2200 µF, below the trip
  level (simulated). One diode of D20 with R116 opens the pair: the
  gate is below 2 V within 7 µs (simulated). R120 damps the gates and
  R115 holds them low while the driver has no supply.
- Right: the pin header J3 and the lever terminal block J4 carry
  the same four nets in the order of the PPK2: GND, VIN, VOUT, GND. The
  unidirectional suppressor D21 is the only protection part on VOUT; its
  leakage adds to the reading and is an open check.
- Top: the buffer U25 senses the node after the shunts through R114.
  Behind R119 its output is `VOUT_BUF`, which drives the guard ring and
  the VOUT channel of the monitor. Behind R118 it is `VCCB_SRC`, the
  supply of the DUT side of the level translator, so that this current does
  not come from the DUT.

For 250 ms after the switch closes, the charging current of its gate lowers
the reading, by 0.5 µA at 30 ms and 4 nA at 200 ms (simulated); the host
marks those samples. VOUT has no reverse-polarity protection. Test points:
TP38 on VOUT, TP40 on the guard, TP39 on ground and TP37 on the
gate node.

![Output stage](images/schematic-10-output-stage.png)

### 11. Signal Chain

From the sense taps of the active shunt to the 16-bit converter (sections
4.5 and 4.6, decisions D-65, D-73 and D-75).

- Left: the input filter C77, C76, C75 and the instrumentation
  amplifier U27 on `+12V_A` and `-4V_A`. R123 sets its gain to 19.93
  (calculated from the datasheet equation).
- Bottom left: the pedestal. R121 and R122 divide the reference to
  50 mV, and the buffer U26 puts it on the reference pin of the
  amplifier. Zero current then reads about 1313 codes (calculated), so that
  offset, noise and small reverse currents are not clipped.
- Middle: the limiter and the filter. The amplifier output can reach 10 V
  during a range change; R125 and the diode pair D22 limit the input
  of the ADC driver U29. With R128, C85 and C87 the driver is a
  two-pole filter at 40 kHz.
- Top: the driver rail `VDRV`. The buffer U28 with R127 and R124
  makes 1.091 × the reference, 2.73 V, and feeds the driver and the cathode
  of the clamp through R129. While the buffer is supplied the converter
  input cannot pass the reference by more than 0.25 V, against a rating of
  0.3 V, and no clamp current flows into the reference (calculated;
  datasheet value).
- Right: the converter U30 with the input network R130, C90 and one
  reference capacitor, C89, behind R131. RN5 puts 220 Ω in its
  clock, data and convert-start lines. A PIO state machine of the
  controller makes the convert-start pulse and the 16 clock pulses of every
  sample; the rising edge of convert-start is the sampling instant.
- Top right: the frame SH1 and the cover MP3 of the shield can over
  the multiplexer, the amplifier, the converter and the shunts of ranges 0
  to 2.

The converter reads full scale at 122.9 mV across the shunt (calculated).
After a range change the chain settles to 0.1 % of full scale in about
45 µs and to 1 LSB in about 65 µs (simulated); seven samples are flagged.
Test points: TP44 on the amplifier output, TP41 on the pedestal,
TP42 on the driver rail and TP43 on the converter input.

![Signal chain](images/schematic-11-signal-chain.png)

### 12. Comparators

Three thresholds on the amplifier output, for the range sequencer in the
controller (section 4.4, decisions D-74 and D-76).

- Top: R136 and R137 divide the amplifier output by 4.01, and the
  diode pair D23 keeps the comparator inputs inside their rating while
  `+3V3_A` is off and the amplifier output is high.
- Left: one resistor string on the reference, R132 to R135, makes the
  three thresholds, each with a 100 nF capacitor. All six resistors are
  0.1 % parts.
- Right, from the top: the jump comparator and the over-current comparator
  (the two halves of U31) and the step-up comparator (U32).

| Comparator | At the shunt | With tolerances | What the sequencer does |
| --- | --- | --- | --- |
| Step up | 91 mV | 87.5 mV to 94.4 mV | One range up |
| Over-current | 115 mV | 111.4 mV to 118.7 mV | In range 3, at 1.15 A: opens the output switch |
| Jump | 151 mV | 147.2 mV to 155.1 mV | Range 3 at once |

The levels are calculated from the resistor values, the tolerances and the
offset limit of the comparators. The over-current level lies below the full
scale of the converter on every board, so a trip is preceded by valid
samples. The outputs are active high and read low without `+3V3_A`. The
blanking of 2 µs after a range change, the qualification of the trip for
12 µs and its latch are in the sequencer, not on this sheet. Test points
TP45 to TP47 are on the three outputs.

![Comparators](images/schematic-12-comparators.png)

### 13. Side Data

Two shift registers give every sample sixteen bits of context (section 4.7,
decision D-41).

- U33, at the top, takes the eight logic inputs from the level
  translator. RN6 and RN7 hold them low while the DUT side of the
  translator has no supply.
- U34, below it, takes the status: the two address bits of the
  multiplexer, which are the range, the request of the output switch, the
  over-voltage detector of VIN, the three comparators and `PWR_GOOD`.
- Both registers load their inputs on a pulse at the convert-start edge of
  the converter and shift with the clock of the converter. The output of
  U33 feeds the serial input of U34, whose output reaches the
  controller through R138.

The order on the data line is the range, the output switch, the detector,
the over-current, jump and step-up comparators and `PWR_GOOD`, then the
logic inputs D7 down to D0. The controller reads this line and the data pin
of the converter at the same instants, so one word holds a conversion
result with the range, the flags and the logic levels of its own instant,
and the two cannot lose alignment. The detector and `PWR_GOOD` are taken on
the carrier side of the series resistors of their controller pins: no state
of a pin can falsify the bits.

![Side data](images/schematic-13-side-data.png)

### 14. Digital Inputs

The logic port and the eight inputs that follow the logic level of the DUT
(section 4.8, decisions D-50, D-72 and D-79).

- Left: the port J5 in the pin order of the PPK2: VCC, ground, D7 down
  to D0.
- Seen from the port, each line meets one channel of an ESD array (U36
  for D0 to D3, U37 for D4 to D7), then 330 Ω in series (RN8,
  RN9), then a 470 kΩ pull-down (RN11, RN10) at the pin of the
  level translator U38. The VCC pin has one channel of a third array,
  U35.
- Right: the translator. Its DUT side runs from `VCC_B`, its other side
  from `+3V3_C`. Direction and enable are tied to ground, so the DUT side
  is always the input.
- Top: the solder jumper JP2 selects `VCC_B`. Bridged 1-2, as built,
  it is `VCCB_SRC`, the buffered copy of the ladder output from the Output
  Stage sheet, held between ground and `+5V` by the dual Schottky diode
  D24: the thresholds follow the supply of the DUT. Bridged 2-3 it is
  the VCC pin of the port through R139, for a DUT whose logic runs on
  another voltage than its supply. The bridge 1-2 is cut before 2-3 is
  closed.

The inputs work for logic levels of 1.65 V to 5.5 V (R-10). A line held
high loads the DUT with its voltage across 470 kΩ, which is 7.0 µA at 3.3 V
(calculated); that is real DUT current and is measured. An unconnected
line reads 0. TP48 is the test point of `VCC_B`.

![Digital inputs](images/schematic-14-digital-inputs.png)

### 15. Monitors

Eight slow channels for supervision, read at 100 SPS by a 12-bit converter
(U40) on the SPI bus of the DAC, with the reference of the instrument
(section 4.2, decision D-80). Each channel has a divider or a series
resistor and 100 nF at its pin.

| Channel | Signal | Scale at the converter |
| --- | --- | --- |
| 0 | Ladder output, buffered (R140, R149) | × 0.4545 |
| 1 | VIN behind the fuse (R141, R150) | × 1/44, for −20 V to +20 V |
| 2 | 5 V rail (R142, R151), with the source tag (R143) | × 0.4545 on USB-C, × 0.2524 on the module input |
| 3, 4 | CC1, CC2 | × 1 behind 10 kΩ |
| 5 | Temperature sensor U39, at the linear regulator | × 1 behind 1 kΩ |
| 6 | `+12V_A` (R147, R152) | × 0.1754 |
| 7 | `-4V_A` against the reference (R148, R153) | 0.333 × V + 1.667 V |

The scale factors are calculated from the nominal resistor values. Channel 2
also tells which input supplies the rail: the status output of the input
multiplexer switches R143 into the divider while the module input
supplies, and firmware separates the two bands at 1.67 V (calculated). No
channel reads a 3.3 V rail.

![Monitors](images/schematic-15-monitors.png)

## Board

Outline 150 mm × 100 mm, four copper layers, four M3 holes. All 425
footprints are on the top side, placed by a script inside the areas of
their functional blocks, and the tracks are drawn by an autorouter. It is a
draft that needs a layout review before fabrication: the
[hardware README](../README.md) describes how it was made and what the
review still has to do.

![Perspective view of the board](images/board-3d.jpg)

![Top view of the board](images/board-top.jpg)

The areas of the sixteen blocks, as drawn on the `Dwgs.User` layer. The back
of the instrument is the left edge: the Raspberry Pi Pico 2 lies along the
top edge with its USB connector at the back, and the USB-C power connector
is below it. The front is the right edge: the logic port, then the two DUT
connectors, in the pin order of the PPK2. The switching converters are on
the left. The front end is on the right, under the frame of the shield can,
with the 1 A branch of the ladder between the can and the terminal block.
KiCad has no 3D model of the lever terminal block, so the 3D views show its
pads only.

![Placement of the functional blocks](images/board-placement.png)

The three routing layers of the board: the top layer with all parts, the
inner layer for power and signals, and the bottom layer. The ground plane
on `In1.Cu` is solid and is left out of the picture, because it would
cover the others.

![The three routing layers](images/board-copper.png)

956 of the 984 connections are routed, with 7.83 m of track and 499 vias;
28 connections are open and are listed by the design rules check.

## Making the Pictures Again

Run from [`../kicad/`](../kicad/) after a change, with KiCad 10:

```sh
kicad-cli sch export pdf --output ../doc/schematic.pdf power-profiler-carrier.kicad_sch
kicad-cli pcb render --output ../doc/images/board-3d.jpg --width 1800 --height 1170 --rotate "-42,0,-25" --perspective --zoom 0.92 --quality high --background opaque power-profiler-carrier.kicad_pcb
kicad-cli pcb render --output ../doc/images/board-top.jpg --width 1800 --height 1420 --zoom 1.22 --quality high --background opaque power-profiler-carrier.kicad_pcb
kicad-cli pcb export svg --output board-placement.svg --layers F.SilkS,F.Fab,Edge.Cuts,Dwgs.User,F.CrtYd --page-size-mode 2 --exclude-drawing-sheet power-profiler-carrier.kicad_pcb
kicad-cli pcb export svg --output board-copper.svg --layers F.Cu,In2.Cu,B.Cu,Edge.Cuts --page-size-mode 2 --exclude-drawing-sheet power-profiler-carrier.kicad_pcb
```

The page images are the pages of the PDF at 160 dpi, for example from
`pdftoppm -r 160 -png`, named after their sheets. The placement drawing is
the exported SVG converted to PNG, and so is the copper drawing. The
pictures here were plotted with KiCad set to English: on the root page the
label "File:" of every sheet follows the language of KiCad.
