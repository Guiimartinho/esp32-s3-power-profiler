# Component Checks

A component check confirms that a candidate part, or a peripheral of the
microcontroller, does what the design asks of it. The answers come from the
manufacturer's documentation, never from memory.

## Open Checks

The lists mirror section 16 of the [specification](../specification.md):
the same items, under the same names and in the same order. Section 16
holds the full text of every item; the tables give its questions in short.
A check is closed when its record is merged and the specification is
updated.

No record is filed for any part of draft A2, so every item is open and
every part is a candidate. The comparison of pin numbers and land patterns
with the datasheet is part of every check; that includes the three symbols
drawn for the project (ADS8860, MUX509 and TPS63020), the symbol of the
TPS2116, which is the one of the KiCad library with one output pin made
passive (D-83), and the two footprints of the project (the lever terminal
block and the controller module, D-85).

Where an item says "calculated" or "simulated", that part of the question
has a figure, and its measurement is what stays open. Nothing in the tables
is measured.

### Parts and Blocks

| Subject | Questions | Record | Status |
| --- | --- | --- | --- |
| AD8421 (U27) | Common-mode range with +12 V / −4 V, settling time and noise at G = 19.93, bias current against the leakage budget; linear range near full scale with the output below 0.2 V; overload recovery and output polarity after an overdrive of up to 3.9 V for 1 µs; offset with a transmitting DUT on its cable | — | Open |
| ADS8860 (U30) | Convert-start and data timing against the acquisition program at 100 kSPS and 500 kSPS, input driver and reference drive, operation at a 2.5 V reference, noise with R131 at 0 Ω, 0.22 Ω and 0.47 Ω (D-75); driver rail of about 2.68 V at TP42 (calculated, D-73); TP43 never above VREF + 0.25 V | — | Open |
| RP2350 PIO | Size of the acquisition program and of the range sequencer against 32 instructions, reaction time from the jump comparator to the gate line of range 3 of 100 ns or less (20 ns to 80 ns, estimate), blanking of 2 µs (F-17) and trip qualification of 12 µs (F-18) as programs, DMA pacing | — | Open |
| LT3080 (U18) | Dropout on both supply pins on the R-08 curve (calculated, margin 2 mV at 5.0 V; measurement on several warm units open), minimum load of 3.7 mA to 6.9 mA through R69 (calculated), output noise with that load, operation from the control pin alone, thermal resistance | — | Open |
| Pre-regulator (TPS63020, U16) | Stability with the difference amplifier U19 in the feedback path over 1.2 V to 5.5 V and the charge returned to the 5 V rail (behavioral model only; phase 1 prototype), power taken in source mode without load, behavior below 1.2 V and at the 5.5 V end, ripple after the filter, land pattern, inductor L2 and bead FB1 | — | Open |
| Set-point path (D-58) | Ceiling of 5.26 V (calculated) at TP23 with the DAC at full scale; half the reference at TP19 | — | Open |
| Range MOSFETs, ladder clamps (Q10, Q11) and multiplexer | Leakage across the whole ladder at 100 mV and 40 °C against 100 nA, leakage of the node behind the shunts to ground at 5 V and 40 °C against 10 nA, on-resistance of the multiplexer at +12 V / −4 V, gate-charge injection into VOUT, pulse series of section 11 with the case temperature of both clamps | — | Open |
| Shunts (R101, R104, R107, R110) | Gain of each range at 20 °C and 40 °C, seat of the two-terminal part R107 on its four-pad land, pulse rating of R107 and R110 in the surge of a hot plug; the datasheet of R104 from its manufacturer | — | Open |
| Suppressor of VOUT (PTVS15VS1UR, D21) | Leakage at 5 V at 25 °C and at 40 °C to 50 °C (guaranteed: 100 nA at 15 V and 25 °C only), forward voltage at 1 A and 10 A, capacitance; closed-switch leakage of the terminal against 50 nA and the insulation resistance of C71 | — | Open |
| Output switch (D-71) | Gate ramp at TP37, in-rush into 100 µF to 2200 µF, absence of oscillation while the pair works as a follower, readings with the output open 200 ms or more after it opened | — | Open |
| Mode switches (D-61, D-62) | Gate ramps at TP32 and TP31 and the supply node at TP33 when a pair closes on a live 5 V supply (simulated); both requests high; −5 V on VIN with the ampere request held high | — | Open |
| VIN protection (D-60) | Detector U21 trips between 5.41 V and 5.51 V and releases between 5.30 V and 5.40 V (calculated); TP30 with +20 V on VIN; the input pin of the detector with −20 V; TP33 and TP27 at a short circuit in ampere mode; short-pulse rating of D14 | — | Open |
| Reverse current (D-69) | With the range gates held low, 1 A, 1.5 A and 2 A for 60 s and 4 A for 100 ms: temperatures of both clamps and of Q14, and whether the clamps stay within 10 °C of each other | — | Open |
| Comparators (U31, U32) | Propagation delay and input range; hysteresis and offset at 0.46 V to 0.76 V of common mode; inputs with 3V3_A off and the amplifier output at +10 V. Thresholds and tolerances are calculated: 87.5 mV to 94.4 mV, 111.4 mV to 118.7 mV, 147.2 mV to 155.1 mV at the shunt | — | Open |
| Rail monitor (MCP6569, U14, D-54) | Trip level of each comparator at TP17, edges of PWR_GOOD at start and stop with C32 to C34 fitted, rise time of PWR_GOOD against the slowest edge the shift register accepts | — | Open |
| Shift registers (SN74LV165A) | Timing of the load pulse against the convert-start edge, maximum clock at 3.3 V against the 500 kSPS option | — | Open |
| Interlock transistors (BSS138: Q3, Q2, and Q1 at the enable of the pre-regulator) | Threshold and on-resistance with 3.3 V at the gate | — | Open |
| Gate drivers (TC4427) | Input thresholds with 3.3 V logic behind 1 kΩ, propagation delay, supply current, output state without supply and with a supply below 4.5 V | — | Open |
| Analog rails | Load of each rail against the converters (LMR62014, LT3042, LM27761), start-up order (simulated) and the order at power-off, start current of the boost converter and its start from a supply limited to 0.7 A, the −4 V rail at 4.25 V on the 5 V rail, noise of the boost converter after the +12 V_A regulator with 0.47 Ω, 0 Ω and a bead in R37, clamp levels at power-off at TP12 and TP14 | — | Open |
| Input stage (D-47, D-48) | Current limiters TPS259621 (U4, U3), multiplexer TPS2116 (U5), supervisor TPS3808G01 (U6); every figure is from behavioral models. Hot plug into USB-C (TP1 below 12.5 V), interrupted contact (TP2 below 5.8 V), data cable plugged again with a short cable (TP4 below 6.0 V), in-rush on a hub port, supervisor thresholds and release, 3V3_A at a re-plug, a supply raised from 5 V to 10 V, USB-C plugged while the module input supplies and pulled with both cables in | — | Open |
| Level translator | Supply current drawn from the buffer through R118, clamp levels of D24, behavior with the DUT-side supply between 0.1 V and 1.65 V, level of an open logic input at 25 °C and 40 °C (confirms 470 kΩ), sag of the DUT-side supply at TP48 with eight lines at 1 MHz and at 10 MHz | — | Open |
| ESD arrays (TPD4E1U06: U2, U36, U37, U35, D-50) | Leakage of a logic line and of the VCC pin at 1.8 V, 3.3 V, 5.0 V and 5.5 V at 25 °C and 40 °C; 0.5 µA or less at 5.0 V, else the alternate part | — | Open |
| USB-C | CC thresholds and behavior on 500 mA, 1.5 A and 3 A sources; a source on a C-to-C cable plugged after the cable of the module | — | Open |
| Pico 2 in hand | Stepping of the RP2350 (erratum E9 of stepping A2; A3 or A4 preferred, D-82), pin headers fitted, height on the sockets; levels of every controller line with empty sockets and in reset; current into the select pins with 3V3_A at 0 V; gate lines across a watchdog restart and a restart into the boot loader | — | Open |
| Lever terminal block (WAGO 2601-1104) | Footprint with pads of 1.9 mm × 2.3 mm, side of the wire entry and current rating against the drawing of the manufacturer | — | Open |
| Monitor ADC (MCP3208) | Input range and source impedance of each channel, SPI mode shared with the DAC, clock edge at 500 kHz; channel 2 with both scale factors (0.4545 and 0.2524, calculated) and channel 1 at VIN / 44, its input within ±0.5 V with −20 V and +20 V on VIN | — | Open |
| Path resistance | Switches, shunt, fuse and connectors against the 200 mV limit of R-06 in both modes; resistance of samples of F1; copper and contacts of the 1 A path at or below 20 mΩ | — | Open |
| Supply node of the ladder | TP33 below 0.3 V with the instrument idle and 5 V on VIN and on VOUT; TP33 against TP16 while the USB cable is pulled with the source on at 5 V | — | Open |
| USB device stack | TinyUSB as the Pico SDK brings it: sustained CDC throughput on the RP2350 before phase 1 ends | — | Open |
| Protocol (section 7, `protocol/definition.toml`) | What draft A2 reports and the definition does not hold yet: marks for over-range and under-range samples (F-22, F-35), the invalid mark for the 5 ms after a change of supply (F-35), the fault flags of section 6.4, the input in use and the CC class (F-14), the power budget as a current (D-49), the instant from which the output settling is counted | — | Open |

### Before the Board Is Ordered

These items need no carrier board.

| Item | Record | Status |
| --- | --- | --- |
| The risk prototypes of phase 1 that concern the carrier: reaction of the sequencer, pre-regulator with its tracking amplifier, start of the boost converter from 0.7 A | — | Open |
| Linear range of the AD8421 near full scale with the output below 0.2 V, on the test board of phase 2. Until the result exists, range 3 above 1 A, the trip level and the jump level are specified for output voltages of 0.2 V or more | — | Open |
| On loose parts: leakage of the suppressor PTVS15VS1UR at 5 V and at 40 °C to 50 °C; leakage of the IRLML0030 at 100 mV and 40 °C; on-resistance of the MUX509 at +12 V / −4 V | — | Open |
| Review of the routed board (D-86) against the rules of section 10, with the resistance of the 1 A path and of the copper from the pre-regulator to FB1 (15 mΩ or less) | — | Open |
| Stock of the parts that had none on 2026-10-09 (L2, 10 µF and 22 µF 25 V X5R), and the order of the parts with long lead times | — | Open |

### Before a DUT Is Connected to a Board

| Item | Record | Status |
| --- | --- | --- |
| With +12 V_A held between 1 V and 4.5 V, while 5 V is applied and removed, with 5 V on VIN, and with 5 V on VOUT and the instrument off: every gate at or below 0.3 V (TP32, TP31, TP34 to TP36, TP37) | — | Open |
| Carrier without supply and 3.3 V through 1 kΩ on a gate-driver input: level of +12 V_A and of the gate | — | Open |
| Output open within 100 ms of a halted supervision task (F-8); gate lines low across a restart | — | Open |
| Then the gate ramp of the output switch, the in-rush and the absence of oscillation, with a capacitor in place of the DUT | — | Open |

The schematic in [`hardware/kicad/`](../../hardware/kicad/) is draft A2,
drawn with these candidates before any record was closed (decision D-37 of
the specification). It passes the electrical rules check, and its netlist
was reviewed independently against the datasheets of its parts. That review
is not a check record and closes no item above. A closed record can
therefore change the schematic.

## Writing a Record

1. Copy [`TEMPLATE.md`](TEMPLATE.md) to a file named after the subject in
   lowercase, for example `ad8421.md`.
2. Use the current datasheet from the manufacturer. Record its title,
   document number, revision and date.
3. For every question, quote the parameter with its test condition, the
   minimum, typical and maximum values, and the page, table or figure.
4. Compare the worst-case values with the design value and state the margin.
5. Give a verdict and list the changes the specification needs.
6. Update the tables above and section 16 of the specification.

Datasheet files are not added to the repository. Link to the manufacturer's
page instead.
