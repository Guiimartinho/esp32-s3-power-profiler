# System Specification: OpenSource Power Profiler (Raspberry Pi Pico 2)

Target Performance: 100 kSPS Sampling Rate | Range: 100 nA to 1 A | Dual-Mode:
Source Meter & Ampere Meter.

## 1. Purpose, Scope & How to Use This Document

Goal: an open-source instrument in the class of the Nordic PPK2, built around
the RP2350 microcontroller of the Raspberry Pi Pico 2. The project started on
the ESP32-S3; decision D-39 changed the controller. It was inspired by
<https://github.com/Gedankenn/power_profiller> (ESP32 + INA226 over I2C, about
50 Hz, single range, WiFi dashboard). That design is the starting idea only;
this specification replaces its architecture.

The instrument is built from two boards. The controller is a Raspberry Pi
Pico 2, bought ready-made. The instrument's own electronics are on a carrier
board, designed in this project, that the Pico 2 plugs into through its two
pin headers (sections 4.11 and 5).

This is the architecture and planning baseline. It fixes the structure, the
interfaces, the budgets and the order of work. It does not replace the
schematic, the simulations or the bench measurements.

- Work phase by phase (section 13). A phase is finished only when its exit
  criteria are met with recorded measurements, filed as a report in
  [`reports/`](reports/).
- Part numbers marked "candidate" are proposals from memory of the
  datasheets. Section 16 lists what must be confirmed before the schematic is
  frozen; each check is filed as a record in [`checks/`](checks/). No value
  in this document has been simulated or measured yet.
- The schematic in [`../hardware/kicad/`](../hardware/kicad/) is draft A1.
  Every sheet is drawn, so the design can be reviewed as a whole, but its
  parts are the candidates of this document and no check of section 16 is
  closed yet (D-37). It is a review draft, not a design to fabricate.
- The firmware in [`../firmware/`](../firmware/) still builds for the
  ESP32-S3. Its hardware-independent code is not affected by D-39; the port
  of its adapters and of its build to the Pico SDK is not done yet
  (section 6).
- Every deviation from this document is recorded as a new entry in the
  decision log (section 15), with the reason.

Out of scope for the first hardware revision: galvanic isolation, voltages
above 5 V, currents above 1 A, four-quadrant (sinking) operation, WiFi
streaming and battery emulation.

## 2. Requirements

| ID | Item | Requirement |
| --- | --- | --- |
| R-01 | Sampling rate | 100 kSPS delivered to the host, hardware-timed |
| R-02 | Data integrity | Zero lost samples in a 10 minute capture; any loss is reported |
| R-03 | Current range | 100 nA to 1 A, automatic range switching |
| R-04 | Resolution | 100 nA or better in the lowest range at full bandwidth |
| R-05 | Accuracy | ±1 % of reading ±0.1 % of range after calibration (target) |
| R-06 | Burden voltage | Shunt drop 100 mV maximum; total path drop 150 mV at 1 A |
| R-07 | Range change | No DUT brown-out on a 1 µA to 500 mA step with 1 µF at the DUT |
| R-08 | Source mode | 0.8 V to 5.0 V, 1.3 mV steps, up to 1 A |
| R-09 | Ampere mode | External supply 0.8 V to 5.0 V passed through the shunts |
| R-10 | Digital inputs | 8 channels, 1.6 V to 5.5 V logic, sampled with the current |
| R-11 | Host link | Native USB Full-Speed, CDC ACM, binary protocol |
| R-12 | Calibration | Per-range gain and offset stored on the device |
| R-13 | Protection | Over-current trip, reverse polarity, over-voltage, thermal |
| R-14 | Power input | USB-C 5 V on the carrier board; output power limited to what the source offers |
| R-15 | Host software | Capture, live view, statistics, export, on Windows/Linux/macOS |
| R-16 | Openness | Sources published: firmware and host software under MIT, hardware under CERN-OHL-P v2 |
| R-17 | Software quality | Automated tests with coverage gates, static analysis and continuous integration for firmware and host software (section 18) |

## 3. System Architecture

```text
USB-C 5 V ──► pre-regulator ──► LDO (source mode) ◄── DAC ◄── SPI
                                    │
VIN (ampere mode) ──► protection ──►├── mode switch
                                    │
                         shunt ladder + range FETs ◄── range logic
                                    │         │ Kelvin sense   ▲
                         output switch     in-amp ──┬──► comparators
                                    │               └──► ADC ──► Pico 2
                                  VOUT ──► DUT          D0..D7 ──► level shift
```

Everything in the diagram except the controller is on the carrier board. The
controller is a Raspberry Pi Pico 2 on sockets. Its USB connector carries the
measurement stream and the commands, and firmware is loaded through it.

Design principles:

- Timing belongs to hardware. The sampling clock and the up-range reaction
  never depend on firmware latency: both are state machines in the PIO
  blocks of the controller, which run from the system clock whatever the
  processors do (D-40).
- Protection belongs to hardware. Firmware may request, hardware may refuse:
  the over-current trip and the up-range path work with both processors
  halted, and an over-voltage on VIN holds its switch open through one
  transistor, with no programmable part involved (D-43).
- The device sends raw data. Conversion to amperes happens on the host with
  the calibration table, which keeps the real-time path short.
- Every sample carries its own context (range, validity, fault, logic bits),
  so a capture can be interpreted without side channels.

### Power Tree

The carrier board has its own USB-C power connector, and the Pico 2 has its
USB connector. Two diodes join them, so either cable powers the whole
instrument (section 4.11).

```text
USB-C VBUS 5 V ─┬─► buck-boost (tracking) ─► V_PRE = VSET + 0.45 V ─► LDO IN
(carrier)       ├─► boost ─► +13.5 V ─┬─► LDO ─► +12 V_A (in-amp, mux, gates, VREF)
                │                     └─► VCONTROL of the output LDO
                ├─► inverter with regulator ─► −4 V_A (in-amp, mux, minimum load)
                ├─► low-noise LDO ─► 3V3_A (ADC, driver, comparators, DAC)
                └─► LDO ─► 3V3_C (carrier logic)

Pico 2 VBUS pin ──► jumper ──► diode ──► 5 V rail of the carrier
5 V rail of the carrier ──► diode ──► VSYS pin of the Pico 2
```

## 4. Analog Hardware Design

### 4.1 Power Input

- The power connector is on the carrier board, separate from the USB
  connector of the Pico 2. That one is a micro-USB receptacle without CC
  pins, good for what a default USB port offers. Its VBUS pin feeds the 5 V
  rail of the carrier through a solder jumper and a Schottky diode, so the
  data cable alone is enough while the DUT draws little; the USB-C
  connector takes over when it is plugged in (D-42).
- USB-C receptacle as a sink, power only: 5.1 kΩ pull-down on CC1 and CC2.
  Both CC voltages are read through the monitor ADC to classify the source.
- A resettable fuse and a transient suppressor follow the connector. Two of
  the parts on this rail are rated for 5.8 V and 6 V only, so the suppressor
  and the bulk capacitor must hold a hot-plug transient below that
  (section 16).
- 5 V at 1 A on the output needs about 7 W at the input, more than a default
  USB port delivers. The output power budget follows the source:

| CC voltage | Source offers | Output power budget |
| --- | --- | --- |
| 0.25 V to 0.61 V | Default USB (500 mA) | About 1.5 W |
| 0.70 V to 1.16 V | 1.5 A | Full range (little margin at 5 V / 1 A) |
| 1.31 V to 2.04 V | 3 A | Full range |

- With no USB-C source both CC voltages read near zero, and the budget is
  that of a default USB port.
- Enforcement: firmware averages the measured current over 10 ms; above the
  budget, or with VBUS below 4.4 V, it opens the output switch and reports a
  power-limit fault.

### 4.2 Source Meter Block (SMU)

- Main Regulator: LT3080 (candidate; 1.1 A, low noise, output follows the SET
  pin down to 0 V). The MIC29302 is not suitable: its minimum output is about
  1.24 V, above the 0.8 V requirement.
  - IN pin from the tracking pre-regulator at about VSET + 0.45 V (D-30);
    VCONTROL pin from the +13.5 V output of the boost converter, ahead of
    the +12 V_A regulator, so its load-dependent current stays off the clean
    rail (D-31). This split keeps the dissipation near 0.7 W at 1 A. Feeding
    both pins from one rail 1.5 V above the output would dissipate 1.5 W,
    too much for the DFN package.
  - Minimum load: about 1 mA, provided by a 4.3 kΩ resistor from the
    regulator output to −4 V_A. It sits before the shunts, so it is not
    measured.
  - Output capacitor at the regulator, before the shunts. After the shunts
    keep the capacitance on VOUT at or below 100 nF (C0G), because its
    charging current is measured as DUT current.
- Pre-regulator: buck-boost converter (candidate: TPS63020) from VBUS, in
  forced PWM at 2.4 MHz. The tracking is analog, with no firmware in the
  loop: a difference amplifier drives the feedback pin with
  0.2 × (V_PRE − VSET) + 0.41 V, and the converter holds that at its 0.5 V
  reference, so V_PRE stays 0.45 V to 0.49 V above the set-point. The
  converter output covers 1.2 V to 5.5 V, which limits the set-point to
  0.75 V to 5.0 V; firmware enforces it. A ferrite bead and a capacitor
  follow the converter; the LDO rejects the remaining ripple.
- Voltage Control (DAC): MCP4921-E/SN (12-bit, SPI), 1x gain, 2.5 V reference.
  A buffer amplifier with gain 2.1, powered from +12 V_A and −4 V_A, drives
  the SET pin: 0 V to 5.25 V in 1.28 mV steps. The DAC is not run at 2x gain
  from VBUS, because VBUS can be below 5 V.
- Voltage changes are ramped by firmware (default 1 V/ms) to limit inrush.
- Output sag: the regulator senses its own output, ahead of the shunts and
  switches, so the DUT sees up to 150 mV less at 1 A. A slow firmware loop
  (about 10 Hz, using the VOUT monitor) may trim the set-point; it is
  optional and off by default.
- Mode switch: back-to-back N-MOSFET pairs select the LDO (source mode) or
  the VIN input (ampere mode); break-before-make, both off at reset. Its
  gate lines are separate from the gate line of the output switch, so the
  selected pair closes without the output switch: the zero calibration then
  runs with the ladder at its real voltage and no load (D-29).
- Output switch: back-to-back N-MOSFET pair at VOUT, off at reset, opened by
  hardware on a fault.
- Slow monitors: an external 8-channel, 12-bit SPI converter (candidate:
  MCP3208) on the SPI bus of the DAC reads the buffered ladder output at
  about 1 kSPS and, at 100 SPS or less, VIN, VBUS, CC1, CC2, a board
  temperature sensor next to the LDO and shunts, and the +12 V_A and −4 V_A
  rails. The internal ADC of the controller is not used: an external
  converter is the more accurate one, has eight channels and shares the SPI
  bus of the DAC (section 5).

### 4.3 Shunt Ladder

Two shunts cannot cover seven decades: 10 mA in a 100 Ω shunt drops 1 V and
saturates a fixed-gain amplifier. Use four ranges, each limited to 100 mV,
with a fixed gain of 20 into a 2.5 V ADC full scale (25 % headroom).

| Range | Shunt | Full scale | Resolution (1 LSB) | Switch up above | Switch down below |
| --- | --- | --- | --- | --- | --- |
| R0 | 1 kΩ | 100 µA | 1.9 nA | 90 µA | (lowest range) |
| R1 | 33 Ω | 3 mA | 58 nA | 2.7 mA | 60 µA |
| R2 | 1 Ω | 100 mA | 1.9 µA | 90 mA | 1.8 mA |
| R3 | 0.1 Ω | 1 A | 19 µA | 1.2 A (trip) | 60 mA |

- Shunt resistors: 0.1 % tolerance, 25 ppm/°C or better, four-terminal
  (Kelvin) parts for 1 Ω and 0.1 Ω.
- Topology: parallel branches between the supply node and VOUT. Each branch
  is a MOSFET on the supply side followed by its shunt; the junction between
  them is the sense node. R0 has no switch and is always in circuit.
- One-hot selection: only one switched branch is on at a time. The current
  through R0 in parallel is then at most 3 % in R1 and is part of the
  calibrated gain. A thermometer scheme (all lower branches on) is rejected:
  the current split would depend on the MOSFET on-resistance and drift with
  temperature.
- Make-before-break: when changing range the new branch turns on about 1 µs
  before the old one turns off, so the DUT is never left on R0 alone.
- Range switches: N-channel MOSFETs, a few mΩ, gates driven from +12 V_A
  through gate drivers, with no gate-to-source resistors: on a branch that
  is off such a resistor would draw its current through a shunt. The
  IRLML6402 P-MOSFET driven by a GPIO does not work here: with the rail at
  0.8 V there is no gate drive to turn it on, with the rail at 5 V a 3.3 V
  GPIO cannot turn it off, and its 65 mΩ is comparable to the 0.1 Ω shunt.
- Kelvin sensing: the amplifier measures across the shunt element only. A
  low-leakage dual 4:1 analog multiplexer (candidate: MUX509) selects both
  sense taps of the active shunt, the positive and the negative one (D-27).
  The switch resistance and the copper between the shunts therefore add
  burden but no measurement error.
- Transient clamp: two low-leakage diodes in anti-parallel across the ladder
  carry a current step during the first microseconds, before the range logic
  reacts. Their leakage at 100 mV must fit the leakage budget.
- Leakage budget: everything that bypasses R0 or loads the sense nodes must
  total below 10 nA at 40 °C. An off MOSFET sees only the burden voltage
  across it, so its channel leakage is small; gate leakage appears as an
  offset and is removed by the zero calibration.

### 4.4 Range Control Logic

Firmware is too slow to protect the DUT: samples arrive in DMA blocks with
milliseconds of latency. The range state lives in hardware.

- State: the range sequencer is a state machine in a PIO block of the
  controller (D-40). A PIO state machine executes one instruction in every
  cycle of the 150 MHz system clock, whatever the processors do, and its
  inputs pass a two-stage synchronizer (RP2350 datasheet). Its reaction to a
  comparator is therefore a few tens of nanoseconds; this figure is an
  estimate until phase 1 measures it. The sequencer holds the range, the
  blanking times, the make-before-break sequencing of the gates and the
  multiplexer address. Its programs are written, tested in an emulator and
  measured in phase 3. Until firmware starts them, every pin of the
  controller is an input with a weak pull-down, and pull-down resistors at
  the gate drivers keep every switch open.
- Comparators: three, on the amplifier output divided by four, with
  thresholds taken from the reference (D-28). Referred to the shunt they
  trip at 90 mV, 120 mV and 150 mV.
- Step up: the 90 mV comparator (90 % of full scale) moves the sequencer one
  range up. Target: under 2 µs from threshold crossing to the new branch
  conducting. A blanking time of about 2 µs follows each step, then a
  further step is allowed, so a large step climbs range by range.
- Jump up: the 150 mV comparator forces R3 at once.
- Step down: only on a request from firmware to the sequencer, and only if
  the step-up comparator is not active. Firmware issues it when the current
  stays below the "switch down" threshold for N consecutive samples (N
  configurable, default 100). After a request it waits until the range bits
  change, or for a hold-off of four blocks, before it evaluates the rule
  again, so that one request never becomes two.
- Lock: firmware can hold a fixed range. The jump-up path and the
  over-current trip stay active even when locked.
- Over-current: in R3 the 120 mV comparator means 1.2 A; a state machine
  opens the output switch and keeps it open until firmware clears the fault.
  In the lower ranges the same level is only passed on the way up and is
  ignored.
- Other faults: an over-voltage on VIN holds the ampere switch open in
  hardware (sections 4.9 and D-43); firmware opens the output switch on it
  and on the loss of PWR_GOOD.
- Reset state: every switch open. Firmware selects R3 before it closes the
  output switch.

### 4.5 Signal Chain

- Instrumentation Amplifier: AD8421 (candidate) at G = 20 (gain resistor
  523 Ω, 0.1 %, 10 ppm/°C). It must settle within one sample period (10 µs)
  after a range change. The INA188 is too slow for this rate.
  - Supplies +12 V_A and −4 V_A, so the 0.8 V to 5 V common mode stays inside
    the input range. The negative rail is −4 V and not −5 V because an
    inverting charge pump cannot regulate −5 V from a USB supply that may
    sag to 4.4 V (D-26).
  - Reference pin at +50 mV (buffered). Zero current then reads about 1300
    codes, so offset, noise and small reverse currents are not clipped.
  - The amplifier offset is larger than the 100 µV that 100 nA produces in
    R0, so per-range offset calibration is mandatory.
- Limiter: the amplifier output can reach 10 V while a range change is in
  progress. A series resistor and a low-leakage diode clamp, followed by an
  ADC driver powered from 3V3_A, keep the ADC input inside its ratings; the
  divider by four does the same for the comparators.
- Anti-alias filter: two poles near 40 kHz around the ADC driver, plus the RC
  network the ADC input requires.

### 4.6 Data Acquisition (ADC)

- Main ADC: 16-bit single-ended SAR, at least 500 kSPS. Candidate: ADS8860
  (the MCP33131D-10 from the first draft is the differential 1 Msps version,
  and the ADS8326 tops out at 250 kSPS).
- Reference: 2.5 V precision reference (candidate: REF5025), shared with the
  DAC so both scale together. The monitor converter and the comparator
  thresholds use it too.
- Conversion timing: a PIO state machine of the controller makes the
  convert-start pulse and the 16 clock pulses of every sample from the
  system clock (D-40), never an interrupt handler. Sampling jitter then does
  not depend on firmware. Series resistors at the controller and at the
  converter damp the edges.
- Clocking: at 100 kSPS a sample period is 1500 cycles of the 150 MHz system
  clock. Keep the clock divider of the state machine an integer; a
  fractional divider adds sampling jitter.
- Oversampling option: 500 kSPS (300 cycles per sample, still an integer)
  decimated by 5 in firmware. It improves noise and relaxes the anti-alias
  filter. Decide in phase 1 from measured noise and CPU load.

### 4.7 Synchronous Side Data

- Two 8-bit parallel-load shift registers (candidate: SN74LV165A) are loaded
  by a pulse at the convert-start edge and shifted by the clock of the
  converter (D-41). They carry the 2 range bits (the multiplexer address),
  the state of the output switch, the over-voltage detector, the three
  comparators, PWR_GOOD and the 8 digital inputs.
- Capture: the state machine that clocks the converter reads the data pin of
  the converter and the data pin of the registers at the same instants, two
  bits per clock. One 32-bit word per sample then holds the conversion result
  and its 16 side bits, and the two cannot lose alignment.
- Firmware separates the two bit streams when it builds the sample word of
  section 7.3.

### 4.8 Digital Inputs

- 8 logic channels, D0 to D7, through a level translator whose DUT-side
  supply is a buffered copy of the ladder output, so they follow the DUT
  logic level from 1.65 V to 5.5 V. The buffer, an amplifier with picoampere
  input current, senses the ladder ahead of the output switch (D-32); the
  translator supply current comes from it and not from the DUT.
- The control pins of the translator are referenced to its 3.3 V side, so
  they stay valid while the DUT supply is off (D-33).
- Series resistors and ESD protection on every pin, and a 1 MΩ pull-down:
  a channel driven high therefore loads the DUT with a few microamperes,
  which is real DUT current and is measured.
- The same buffer drives the guard ring of section 10 and the VOUT channel
  of the monitor.
- Logic port: a 1×10 pin header in the pin order of the PPK2: VCC, GND, D7
  down to D0 (D-44). A solder jumper selects the supply of the DUT side of
  the translator: the buffered ladder output as built, or the VCC pin of
  the port, for a DUT whose logic runs on another voltage than its supply.
- Pull-down resistors hold the eight lines at the shift register while the
  DUT side of the translator has no supply.

### 4.9 Protection & Grounding

- VIN: a fuse with a reverse clamp diode takes a reversed supply. The
  ampere-mode switch blocks up to 30 V while it is open, and an
  over-voltage detector keeps it open above 5.5 V: its output pulls the
  input of the gate driver low through a transistor and is read by
  firmware, which reports the fault (D-35, D-43).
- VOUT: low-leakage clamp diodes to ground and to a 5.6 V node. Anything
  with more leakage would be measured as DUT current.
- ESD protection on all external terminals.
- Thermal: the board temperature sensor derates the output current and shuts
  the output down above a limit.
- The DUT ground is the USB ground: there is no galvanic isolation. State
  this in the documentation and recommend a USB isolator when the DUT is also
  grounded elsewhere.

### 4.10 Error & Noise Budget (Estimates)

Estimated from typical datasheet figures at G = 20 and 50 kHz bandwidth:
amplifier about 1.2 µV RMS referred to input, ADC about 1.0 µV RMS, R0
thermal noise about 1.1 µV RMS. To be replaced by measurements in phase 2.

| Range | Noise (RMS, full bandwidth) | Offset drift | Dominant gain error |
| --- | --- | --- | --- |
| R0 | About 2 nA | About 0.4 nA/°C | Shunt TCR, leakage |
| R1 | About 50 nA | About 12 nA/°C | Shunt TCR, R0 in parallel |
| R2 | About 1.6 µA | About 0.4 µA/°C | Shunt TCR |
| R3 | About 16 µA | About 4 µA/°C | Shunt TCR, self-heating (0.1 W) |

- Averaging on the host lowers the noise with the square root of the number
  of samples; the 100 nA requirement (R-04) is met at full bandwidth in R0.
- Samples inside the settling window after a range change are excluded from
  statistics.

### 4.11 Controller Module & Power Domains

The carrier board has two 1×20 pin sockets at 2.54 mm pitch, 17.78 mm apart,
and the Raspberry Pi Pico 2 plugs into them (section 5 has the pin
assignment). The Pico 2 needs its pin headers fitted; a Pico 2 W fits the same
sockets (D-39).

- One supply domain (D-42). The VBUS pin of the Pico 2 feeds the 5 V rail of
  the carrier through a solder jumper, closed as built, and a Schottky
  diode. The 5 V rail feeds the VSYS pin of the Pico 2 through a second
  diode. Either USB connector therefore powers the whole instrument, and
  neither feeds the other one back.
- The 3.3 V regulator of the Pico 2 powers the Pico 2 only. The carrier
  logic runs from its own 3.3 V rail, 3V3_C, at the same level.
- The pins of the RP2350 are, in the words of its datasheet, "5 V-tolerant
  (powered) and 3.3 V-failsafe (unpowered)": a carrier output drives no
  current into a controller that has no supply.
- Reset state: out of reset every pin of the RP2350 is a high-impedance
  input with its input buffer off and a weak pull-down (RP2350 datasheet).
  Pull-down resistors at the inputs of the gate drivers and at the enable of
  the pre-regulator keep every switch open and the regulator off until
  firmware and its state machines take over.
- Series resistors at the Pico 2 sit in the slow SPI lines and in the
  acquisition outputs.
- PWR_GOOD is pulled up to 3V3_C. Firmware drives no carrier input until it
  reports the analog rails valid, and treats its loss as a fault.
- A push button pulls the RUN pin low. With the BOOTSEL button of the Pico 2
  held, that reset opens its USB mass-storage boot loader, which is how
  firmware is loaded: no programmer and no vendor tool is needed.
- UART0 of the controller is on a 3-pin header, for a console.
- The Pico 2, with its switching regulator, stays away from the shunt ladder
  and the amplifier (section 10).

## 5. Microcontroller, Connectivity & Pin Map

- Controller: a Raspberry Pi Pico 2, plugged into sockets on the carrier
  board (D-39). Its RP2350 has two Cortex-M33 cores at 150 MHz, 520 kB of
  RAM and three PIO blocks with four state machines each; the board adds
  4 MB of flash.
- Reference data, from the Pico 2 datasheet of Raspberry Pi Ltd: board of
  51 mm × 21 mm, 40 pins at 2.54 mm pitch in two rows 17.78 mm apart, and a
  micro-USB connector that overhangs one short edge. 26 GPIO pins are on
  the headers, GP0 to GP22 and GP26 to GP28; GP23, GP24, GP25 and GP29 are
  used on the board itself (regulator mode, VBUS sense, LED, VSYS
  measurement).
- USB: one Full-Speed device port (12 Mbit/s), for the measurement stream,
  the command channel and firmware updates.
- A Pico 2 W may be plugged in instead. Its radio stays off while capturing,
  to keep supply noise down, and no function depends on it.

Pin map. Pin numbers are those of the 40-pin interface of the Pico 2; pin 1
is beside the USB connector.

| GPIO | Pin | Signal | Direction | Function |
| --- | --- | --- | --- | --- |
| 0 | 1 | DBG_TX | Out | Console (UART0) |
| 1 | 2 | DBG_RX | In | Console (UART0) |
| 2 | 4 | GATE_R1 | Out | Range switch R1 (PIO 1) |
| 3 | 5 | GATE_R2 | Out | Range switch R2 (PIO 1) |
| 4 | 6 | GATE_R3 | Out | Range switch R3 (PIO 1) |
| 5 | 7 | MUX_A0 | Out | Multiplexer address, bit 0 (PIO 1) |
| 6 | 9 | MUX_A1 | Out | Multiplexer address, bit 1 (PIO 1) |
| 7 | 10 | GATE_OUT | Out | Output switch (PIO 1) |
| 8 | 11 | CMP_UP | In | Step-up comparator (PIO 1) |
| 9 | 12 | CMP_JUMP | In | Jump-up comparator (PIO 1) |
| 10 | 14 | CMP_OC | In | Over-current comparator (PIO 1) |
| 11 | 15 | VIN_OV | In | Over-voltage on VIN |
| 12 | 16 | SPI_MISO | In | Data from the monitor ADC (SPI1) |
| 13 | 17 | MON_CS | Out | Monitor ADC chip select |
| 14 | 19 | SPI_SCK | Out | Clock of the DAC and the monitor ADC (SPI1) |
| 15 | 20 | SPI_MOSI | Out | Data to the DAC and the monitor ADC (SPI1) |
| 16 | 21 | ADC_DOUT | In | Converter data (PIO 0) |
| 17 | 22 | SIDE_DOUT | In | Shift-register data (PIO 0) |
| 18 | 24 | SMU_ON | Out | Pre-regulator enable |
| 19 | 25 | ADC_SCK | Out | Clock of the converter and the shift registers (PIO 0) |
| 20 | 26 | ADC_CNV | Out | Convert-start (PIO 0) |
| 21 | 27 | SIDE_LOAD | Out | Load pulse of the shift registers (PIO 0) |
| 22 | 29 | DAC_CS | Out | DAC chip select |
| 26 | 31 | GATE_SRC | Out | Mode switch, source side |
| 27 | 32 | GATE_AMP | Out | Mode switch, ampere side |
| 28 | 34 | PWR_GOOD | In | Analog rails valid |

- Power and ground: VBUS (pin 40) and VSYS (pin 39) as section 4.11
  describes; ground on pins 3, 8, 13, 18, 23, 28 and 38, and the analog
  ground pin 33 through a link. 3V3 (pin 36), 3V3_EN (pin 37) and ADC_VREF
  (pin 35) are not connected. RUN (pin 30) goes to the reset button.
- The groups follow what a PIO state machine needs: its output pins and its
  input pins are runs of consecutive GPIO numbers. GP2 to GP7 are the
  outputs of the range sequencer and GP8 to GP10 its inputs; GP16 and GP17
  are the inputs of the acquisition state machine and GP19 to GP21 its
  outputs.
- The acquisition pins have the ground pins 23 and 28 among them.
- Every GPIO of the headers is in use. A further signal means giving up the
  console or sharing the SPI bus.
- The status indicator is the LED of the Pico 2 (GP25).

## 6. Firmware Architecture & Execution Strategy

To guarantee uninterrupted 100 kSPS sampling without dropping frames, the
firmware uses the two cores of the RP2350 combined with PIO and DMA. There
is no per-sample interrupt and no per-sample driver call: a PIO state machine
clocks the converter, and DMA moves its words to memory. The firmware is
built with the Pico SDK (C and CMake); the USB stack is TinyUSB, which the
SDK brings.

Status: the firmware in the repository still has the ESP-IDF adapters of the
first plan. The hardware-independent code of every component is unchanged by
D-39; its adapters and its build are ported in phase 1 (section 13).

```text
                  ┌──────────────────────────────────────────┐
                  │           RP2350 DUAL-CORE MCU           │
                  └────────────────────┬─────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
┌───────────────────────┐                             ┌───────────────────────┐
│        CORE 1         │                             │        CORE 0         │
│  (Real-Time Engine)   │                             │  (Data Communication) │
├───────────────────────┤                             ├───────────────────────┤
│ • PIO: converter      │                             │ • USB CDC Driver      │
│   clock, range logic  │                             │ • Frame Building      │
│ • DMA from the PIO    │───[ Shared RingBuffer ]────>│ • Command Handling    │
│ • Down-range Decision │                             │ • Slow Monitors       │
│ • Block Hand-off      │                             │ • Diagnostics/LED     │
└───────────────────────┘                             └───────────────────────┘
```

### 6.1 Components

| Component | Responsibility |
| --- | --- |
| `base` | Primitives shared by every component: status codes, byte-order helpers, block queue |
| `proto` | Frame encoding/decoding, sample word, command envelopes, error codes |
| `acq` | PIO capture with DMA, separation of result and side bits, decimation, sample-word assembly |
| `afe` | Range sequencer and trip state machines, range lock and step-down, mode switch, output switch, fault state |
| `smu` | DAC, voltage ramp, regulator enable, power budget enforcement |
| `monitor` | Slow channels of the monitor ADC: VOUT, VIN, VBUS, CC, temperature, rails |
| `cal` | Calibration table in flash, zero calibration routine |
| `usb_link` | TinyUSB CDC ACM, host-open detection |
| `app` | Device state machine, command handlers, start-up self-test |

Rules: `base` and `proto` are libraries that any component may use. Among
the others, only `app` calls across components, and no component other than
`cal` writes flash. Every component keeps its hardware-independent logic
apart from its code for the SDK of the controller, as section 18 describes.

### 6.2 Tasks

| Work | Core | Trigger | What it does |
| --- | --- | --- | --- |
| Acquisition | 1 | DMA block ready (2.56 ms) | Separate the bit streams, assemble words, range decision, push block |
| USB transmit | 0 | Block in ring buffer | Build frame, write to CDC |
| USB stack | 0 | USB events | TinyUSB device task |
| Commands | 0 | Bytes from CDC | Parse and execute commands |
| Monitor | 0 | 1 ms timer | Slow channels, power budget, thermal |
| Application | 0 | Events | State machine, LED |

Core 1 runs the acquisition loop and nothing else. Core 0 runs the other
work as a cooperative loop; whether a real-time kernel is added is decided
in phase 1, from measured latencies.

### 6.3 Acquisition Pipeline

1. The acquisition state machine starts a conversion, pulses the load line
   of the shift registers, and clocks the converter and the registers.
2. It pushes one 32-bit word per sample. DMA fills a block of 256 words and
   signals core 1.
3. The acquisition loop separates the conversion result from the side bits,
   optionally decimates, builds 32-bit sample words and marks the settling
   window after any change of the range bits. The window starts at the first
   sample that shows the new range.
4. It evaluates the step-down rule on the block and asks the range sequencer
   for a step down.
5. The block goes into the ring buffer. If the buffer is full the block is
   dropped and counted; acquisition never blocks.

Budgets:

- CPU: the acquisition loop must use under 30 % of core 1 at 100 kSPS.
- Memory: ring buffer of 64 blocks (about 66 kB, 164 ms of data), out of
  520 kB of RAM.
- Latency from sample to host: under 20 ms typical.
- Flash writes are forbidden while streaming, because they stall code that
  runs from flash.

### 6.4 Device State Machine

```text
BOOT ─► SELFTEST ─► IDLE ◄──────────────┐
                     │  ▲               │
           DUT_POWER │  │ DUT_POWER off │ CLEAR_FAULT
                     ▼  │               │
                    ARMED ─► FAULT ─────┘
                     │  ▲       ▲
               START │  │ STOP  │ trip, power limit, thermal
                     ▼  │       │
                   STREAMING ───┘
```

- SELFTEST: analog rails valid, ADC responds, range logic steps through all
  ranges, zero calibration with the output open. A failed self-test goes to
  FAULT.
- STREAMING stops by itself when the host closes the port.
- FAULT always opens the output switch first and reports second. A fault can
  be raised in every state after BOOT.
- An event that the current state does not allow is refused, and the command
  behind it answers "wrong state". The output cannot be switched off while
  STREAMING: the stream is stopped first.

### 6.5 USB Streaming

- USB Stack: TinyUSB as CDC ACM, so no driver is needed on Windows, Linux or
  macOS.
- Throughput: 100 kSPS × 4 bytes is 400 kB/s, plus headers. Full-Speed bulk
  tops out near 1 MB/s in theory, so the margin is small. If the measured
  sustained rate is below 500 kB/s, pack samples into 3 bytes (dropping the
  reserved bits and four logic channels) before lowering the sample rate.

## 7. Host Protocol

All multi-byte fields are little-endian. The same frame format is used in
both directions.

### 7.1 Frame

| Field | Size | Meaning |
| --- | --- | --- |
| magic | 2 bytes | `0xA55A`, synchronization |
| type | 1 byte | Stream, command, response or event |
| flags | 1 byte | Reserved, zero |
| length | 2 bytes | Payload length in bytes |
| sequence | 2 bytes | Per-type counter; reveals lost frames |
| payload | length | See below |
| crc16 | 2 bytes | CRC-16/CCITT-FALSE over header and payload |

- The magic word is sent little-endian like every other field, so a frame
  starts with the bytes `0x5A`, `0xA5`.
- The CRC is CRC-16/CCITT-FALSE: polynomial `0x1021`, initial value `0xFFFF`,
  no reflection, no final XOR. The CRC of the ASCII string "123456789" is
  `0x29B1`.
- A payload is at most 2048 bytes, and a command payload at most 256.
- A receiver that finds an impossible length or a wrong CRC drops the first
  byte of the candidate frame and searches for the next magic word.
- A receiver skips a frame whose type it does not know.

| Type | Code | Direction |
| --- | --- | --- |
| Stream | `0x01` | Device to host |
| Command | `0x02` | Host to device |
| Response | `0x03` | Device to host |
| Event | `0x04` | Device to host |

### 7.2 Stream Payload

| Field | Size | Meaning |
| --- | --- | --- |
| first_index | 4 bytes | Index of the first sample since START |
| dropped | 2 bytes | Blocks dropped since the previous frame |
| count | 2 bytes | Number of samples (normally 256) |
| samples | 4 × count | Sample words |

### 7.3 Sample Word (32-bit)

| Bits | Field | Meaning |
| --- | --- | --- |
| 15:0 | adc | Raw ADC code |
| 17:16 | range | Active range, R0 to R3 |
| 18 | invalid | Sample inside the settling window of a range change |
| 19 | fault | Over-current trip latched |
| 23:20 | reserved | Zero |
| 31:24 | logic | Digital inputs D0 to D7 |

### 7.4 Commands

A command payload is the command code followed by its arguments. Every
command gets a response frame with the same sequence number, whose payload is
the command code, a status code and the response data.

| Command | Code | Arguments | Purpose |
| --- | --- | --- | --- |
| GET_INFO | `0x01` | None | Protocol version, firmware version, hardware revision, range table, calibration |
| GET_STATUS | `0x02` | None | State, faults, dropped blocks, VOUT, VIN, VBUS, temperature, power budget |
| SET_MODE | `0x10` | Mode, 1 byte: 0 ampere meter, 1 source meter | Select the mode (only in IDLE) |
| SET_VOLTAGE | `0x11` | Millivolts, 2 bytes | Output voltage in source mode |
| DUT_POWER | `0x12` | On, 1 byte: 0 or 1 | Turn the output switch on or off |
| SET_RANGE | `0x13` | Range, 1 byte: 0 to 3, or `0xFF` for automatic | Lock one range, or return to automatic |
| SET_DOWN_N | `0x14` | Samples, 2 bytes | Number of samples for the step-down rule |
| START | `0x20` | None | Start the sample stream |
| STOP | `0x21` | None | Stop the sample stream |
| CAL_ZERO | `0x30` | None | Run the zero calibration (output open) |
| CAL_WRITE | `0x31` | Target, 1 byte: 0 to 3 for a range, `0x10` for the DAC; gain and offset, 4-byte floats | Store gain and offset values |
| CLEAR_FAULT | `0x40` | None | Reset the over-current latch |

| Status | Code |
| --- | --- |
| OK | 0 |
| Bad argument | 1 |
| Wrong state | 2 |
| Fault active | 3 |
| Busy | 4 |
| Unknown command | 5 |

Which commands a state accepts, checked in this order:

- GET_INFO and GET_STATUS are answered in every state.
- During BOOT and SELFTEST every other command answers "busy".
- In FAULT every other command answers "fault active", except CLEAR_FAULT,
  which returns to IDLE.
- SET_MODE and CAL_ZERO are accepted only in IDLE.
- DUT_POWER on moves IDLE to ARMED. DUT_POWER off moves ARMED to IDLE and is
  refused while STREAMING. Asking for the present state changes nothing and
  answers OK.
- START is accepted only in ARMED and STOP only in STREAMING.
- SET_VOLTAGE needs source meter mode and a value from 800 mV to 5000 mV.
  CAL_WRITE is refused while STREAMING.
- Any other request answers "wrong state". A command code the device does
  not know answers "unknown command", and a command frame without a payload
  answers "bad argument" with command code 0.

An event payload is the event code followed by its data. Events are sent by
the device without a request. Every change of state is announced with a
"state changed" event, sent after the response when a command caused it.

| Event | Code | Data |
| --- | --- | --- |
| Fault raised | `0x01` | Fault flags, 2 bytes |
| Power budget changed | `0x02` | Budget in mW, 2 bytes |
| State changed | `0x03` | State, 1 byte |

- Fault flags: bit 0 over-current, bit 1 power limit, bit 2 thermal, bit 3
  self-test.
- States are numbered 0 to 5 in the order BOOT, SELFTEST, IDLE, ARMED,
  STREAMING, FAULT.
- The response data of GET_INFO, GET_STATUS and CAL_ZERO is provisional
  until the protocol is frozen in phase 6. For now GET_INFO returns the
  protocol version, the hardware revision and the firmware major, minor and
  patch numbers, one byte each; GET_STATUS returns the state (1 byte), the
  fault flags (2 bytes) and the dropped blocks (4 bytes); CAL_ZERO returns
  no data. A receiver ignores bytes after the fields it knows, so fields can
  be appended.

### 7.5 Single Definition

Every number in this section lives in `protocol/definition.toml`. A generator
turns that file into the C header used by the firmware and the Python module
used by the host, and encodes a set of shared test vectors that both codecs
must reproduce byte for byte. A check, run locally and in continuous
integration, fails when a generated file is stale. This section describes
the protocol; the definition file decides it.

## 8. Calibration

- Conversion on the host: `I = (code − offset[r]) × gain[r]`, with the
  nominal gain `VREF / (65536 × G × R[r])`.
- Storage: per-range gain and offset, DAC gain and offset, the settling
  window length and the calibration temperature, in NVS with a version field
  and CRC. A missing or corrupt table falls back to nominal values and is
  flagged in GET_INFO.
- Zero calibration: with the output switch open the current is zero, so the
  firmware measures the offset of every range (locked one by one). It runs
  at start-up and on CAL_ZERO. Run-time offsets are kept in RAM, not flash.
- Gain calibration: source mode into precision resistors (0.01 %), with VOUT
  read by a reference multimeter; two points per range, near 10 % and 90 % of
  full scale.
- DAC calibration: two set-points measured with the reference multimeter.
- Settling window: measured on the prototype with a fast load step, then
  stored as a constant.

## 9. Host Software

- Python package with a command-line capture tool and a desktop viewer.
- Architecture: the protocol layer does no I/O and is shared by every front
  end; transports are adapters behind one interface; a device simulator
  implements the instrument side of the protocol, so the package is developed
  and tested without hardware (section 18).
- Device layer: protocol codec, resynchronization on the magic word, CRC
  check, gap detection from the sample index.
- Live plot of current against time with min/max decimation, so short pulses
  stay visible when zoomed out; digital channels below the trace.
- Selection statistics: average, maximum, charge (µC/mAh) and energy.
- Controls for mode, voltage, DUT power, range and calibration.
- Export to CSV and a compact binary format; a guided calibration procedure.
- Burst detection and battery-life estimate, carried over from the
  `scripts/plot.py` of the reference project.

## 10. PCB & Mechanical Guidelines

- Four layers: signal, solid ground, power, signal. No ground-plane splits;
  partition by placement, with the switching converters and the controller
  module away from the front end.
- Controller module: on sockets, lying along the back edge with its USB
  connector at the edge; no carrier parts under it; the front end at the
  opposite edge. For a Pico 2 W, keep copper away from under its antenna
  end.
- Socket footprint: the Raspberry Pi Pico footprint of the KiCad library,
  two rows of 20 holes 17.78 mm apart.
- Outline of the draft: 130 mm × 100 mm with four M3 holes (D-46). The back
  is the left edge, with the USB connector of the Pico 2 and the USB-C
  power connector. The front is the right edge, with the logic port and
  the DUT connectors in the order of the PPK2 (D-44). The switching
  converters are in the left third, the front end in the right third.
- Placement of the draft: worked out from the netlist, block by block:
  each decoupling capacitor at the pin it serves, parts turned towards
  their connections (D-46). It is a starting point for routing, not a
  reviewed layout.
- Guard ring driven by the buffered ladder output (section 4.8) around the
  R0 sense node and the amplifier inputs; no solder mask over the guard;
  clean flux residue.
- Kelvin routing as a tightly coupled pair from each shunt to the
  multiplexer. R2 and R3 are four-terminal parts; R0 and R1 are sensed at
  their pads.
- Shield can over the shunt ladder, multiplexer, amplifier and ADC.
- Thermal relief for the LDO and R3 away from R0 and the reference.
- Test points on every rail, comparator output and range gate.
- Connectors on the carrier: USB-C (power only); the two sockets of the
  Pico 2; for the DUT a 1×4 pin header and a lever terminal block in
  parallel, both GND, VIN, VOUT, GND; the 1×10 logic port (VCC, GND, D7 to
  D0); a 3-pin console header.

## 11. Verification Plan

| Requirement | Test | Pass criterion |
| --- | --- | --- |
| R-01, R-02 | 10 minute capture, check sample index | No gaps, dropped count zero |
| R-01 | Capture a 1 kHz reference sine, FFT | Sample rate within 50 ppm, no jitter spurs |
| R-04 | Output open and 1 MΩ load, record noise | RMS noise in R0 at or below 5 nA |
| R-05 | Precision loads at 10 points per range | Within the accuracy target |
| R-06 | Measure terminal-to-terminal drop per range | Within the burden limits |
| R-07 | Electronic load step 1 µA to 500 mA, scope on VOUT | Droop below 200 mV, recovery under 5 µs |
| R-07 | Slow ramp across every threshold | No oscillation between ranges |
| R-08 | Sweep 0.8 V to 5.0 V at 0, 0.1 and 1 A | Set-point error within 10 mV plus sag |
| R-10 | Square wave on D0 to D7 at 10 kHz | Edges aligned with current within 1 sample |
| R-13 | Short circuit, reverse supply, over-voltage | Trip, no damage, fault reported |
| R-14 | 500 mA, 1.5 A and 3 A sources | Budget respected, no VBUS collapse |
| R-17 | Run every continuous integration workflow on the release commit | All jobs pass, coverage at or above the gates of section 18 |
| R-17 | Run the shared protocol vectors through the firmware and host codecs | Byte-for-byte agreement in both directions |

## 12. Repository Structure

```text
hardware/     KiCad project of the carrier board, simulations, fabrication
              outputs
firmware/     Firmware project, one directory per component of section 6.1
host/         Python package: protocol, CLI, viewer, analysis
protocol/     Protocol definition, generator and shared test vectors
docs/         This specification, component checks, test reports, protocol
              reference, calibration procedure
tools/        Calibration and production-test scripts
```

## 13. Development Phases & Exit Criteria

1. Risk prototypes on a Pico 2 with an ADC evaluation module. Exit:
   firmware ported to the Pico SDK; ADC captured through PIO and DMA at
   100 kSPS (and 500 kSPS) for 10 minutes with no lost samples; side data
   read in the same word; reaction time of a PIO state machine to an input
   edge measured; USB throughput of at least 500 kB/s sustained; CPU load
   recorded.
2. Analog front end with one fixed range on a test board. Exit: noise,
   offset, drift and settling measured and the budget of section 4.10
   updated; oversampling decision taken.
3. Shunt ladder and range logic. Exit: verification tests for R-06 and R-07
   passed; programs of the range sequencer verified in an emulator and on
   the controller.
4. Source mode and power. Exit: tests for R-08, R-13 and R-14 passed;
   thermal measurements at 1 A recorded.
5. Carrier board, revision A, with the Pico 2 plugged in. Exit:
   full verification plan executed, issues listed.
6. Calibration, protocol freeze and host software. Exit: R-05 and R-15
   demonstrated end to end.
7. Revision B and release: sources, documentation and test reports
   published.

Firmware and host software start in phase 1 and grow with each phase; the
protocol of section 7 is implemented from the first prototype.

The schematic of the carrier board and a placement of its parts exist as
draft A1, drawn ahead of these phases (D-37). The draft is the hypothesis
that the phases test: the checks of section 16 and the results of phases 1
to 4 change it before revision A is fabricated in phase 5.

## 14. Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Timing of the PIO capture does not match the ADC interface | No hardware-timed capture | Phase 1 prototype; the program places every edge on a cycle of the system clock |
| Side data and conversion result misaligned | Wrong range per sample | One state machine reads both into one word; load pulse at the convert-start edge |
| USB Full-Speed throughput too low | R-01 not met | 3-byte packing; larger writes; last resort lower rate |
| Up-range too slow, DUT brown-out | R-07 not met | Jump-up comparator, transient clamp, simulation before layout |
| Range oscillation at thresholds | Unusable data near thresholds | Wide hysteresis, firmware-only step down, ramp test |
| Leakage and offset dominate R0 | R-04, R-05 not met | Guarding, low-leakage parts, zero calibration, temperature record |
| LDO or shunt overheating | Drift, shutdown | Split LDO supply, tracking pre-regulator, thermal derating |
| Switching noise in the measurement | Noise above budget | LC filters, placement, shield, converter frequency above 1 MHz |
| USB source too weak | Brown-out of the instrument | CC detection, power budget, VBUS monitor |
| Candidate part unsuitable or unavailable | Redesign | Section 16 checks first; second source noted in the BOM |
| Controller module differs from the reference design | Wrong pin or mechanical misfit | Raspberry Pi Pico 2 or a board with the same 40-pin interface; footprint of the KiCad library; checks of section 16 on the board in hand |
| Range sequencer wrong or not started | No range switching | Pull-downs keep every switch open after reset; programs tested in an emulator and on the bench; an over-voltage on VIN is blocked with no program involved |
| Reaction of the sequencer slower than estimated | R-07 not met | Measured in phase 1; the jump-up comparator reaches the highest range in one step |
| Draft schematic taken as a finished design | Boards built with unchecked parts | Draft marked A1 on every sheet; section 16 lists the open checks; fabrication only in phase 5 |
| Noise and ground bounce through the board sockets | Jitter on the convert-start signal | Acquisition signals next to a ground pin, series resistors, low drive strength, measurement in phase 1 |
| Firmware and host disagree on the protocol | Corrupt or misread data | One definition file, generated constants, shared test vectors, stale-file check in continuous integration |
| In-rush of the carrier on the USB port of the computer | The port shuts down at plug-in | Check of section 16; the jumper can be cut and the USB-C input used |
| Firmware port to the new controller takes longer than planned | Phase 1 starts late | The hardware-independent code and its tests carry over; only adapters and build change |

## 15. Decision Log

| ID | Decision | Reason |
| --- | --- | --- |
| D-01 | Discrete front end instead of INA226 | 100 kSPS and seven decades are out of reach of an integrated monitor |
| D-02 | Four ranges at 100 mV burden | Two shunts saturate the amplifier and drop 1 V on the DUT |
| D-03 | High-side sensing | DUT ground stays common with instrument and logic inputs |
| D-04 | Range state in hardware, step down by firmware | Block latency makes firmware too slow to protect the DUT |
| D-05 | One-hot branches with Kelvin multiplexer | Switch resistance must not enter the measurement |
| D-06 | N-MOSFET switches on a +12 V gate rail | P-MOSFET on a GPIO cannot switch a 0.8 V to 5 V rail |
| D-07 | Convert-start from the I2S word clock | Per-sample interrupts cannot hold 10 µs under ESP-IDF |
| D-08 | Side data through a shift register | Range and logic bits must be sample-accurate |
| D-09 | LT3080 with split supply and tracking pre-regulator | Headroom above 5 V and dissipation at low output voltage |
| D-10 | CDC ACM with framed binary protocol | Driverless on all hosts; frames give loss detection |
| D-11 | Raw codes to the host, calibration on the host | Short real-time path; recalibration without reflashing |
| D-12 | WiFi and Bluetooth off during capture | Interrupt latency and supply noise |
| D-13 | MIT for firmware and host software, CERN-OHL-P v2 for hardware | Permissive licenses, chosen by the project owner |
| D-14 | ESP32-S3-DevKitC-1 compatible board on sockets, with the instrument on a carrier board | No module, USB or UART-bridge layout on the first boards, and firmware work starts before any PCB exists; chosen by the project owner |
| D-15 | Separate USB-C power connector on the carrier; the 5 V pin of the development board is unused | The development board does not bring CC to its headers and feeds its 5 V pin through a 1 A diode |
| D-16 | Slow monitors on an external SPI converter instead of the internal ADC | The development board leaves 19 usable pins once USB, UART, PSRAM, strapping, LED and JTAG pins are set aside |
| D-17 | Hardware-independent logic kept apart from ESP-IDF code in every firmware component | The logic is unit-tested on a PC with coverage, and the hardware code stays thin |
| D-18 | A `base` component for shared primitives; `base` and `proto` usable by every component | The block queue and the status codes are shared by components that must not call each other |
| D-19 | Protocol constants generated from one definition file, with shared test vectors | Firmware and host cannot drift apart unnoticed |
| D-20 | Quality gates in continuous integration: tests, coverage floors, static analysis, formatting | Defects are found before bench time is spent on them; required by R-17 |
| D-21 | Host package with an I/O-free protocol layer, transports behind one interface and a device simulator | Development and end-to-end tests without the instrument |
| D-22 | Continuous integration workflows are started by hand instead of on every push and pull request | Requested by the project owner, to save processing time while the project is in early development; the gates of D-20 stay, run locally and on demand |
| D-23 | Development board with an N8R2 or N16R2 module; socket footprint for rows 25.40 mm or 22.86 mm apart | The board of the project owner is the common two-port clone, 27.94 mm wide; R2 modules leave GPIO 35 to 37 free; the second row of holes costs nothing |
| D-24 | Range register, timers, fault latch, mode interlock and side-data shift register in one programmable logic device with its own oscillator | The timing is too tight and too likely to change for discrete logic, and the protection must not depend on a clock from the MCU; replaces the two shift registers of D-08 |
| D-25 | Every signal between the boards is received by a part powered from the receiving side; the carrier has its own 3.3 V logic rail | Either board can be powered alone without current through input protection diodes, and the unknown regulator of the development board carries almost no load |
| D-26 | Negative rail of −4 V instead of −5 V | A charge pump cannot regulate −5 V from a 5 V supply that sags; −4 V covers the amplifier input range and the minimum load of the LDO |
| D-27 | Dual 4:1 multiplexer: both sense taps of the active shunt are selected | With a common negative tap the copper between the shunts would be inside the measurement of the 0.1 Ω range |
| D-28 | All three comparators on the amplifier output divided by four | A comparator across the floating ladder needs a high-side differential stage; the amplifier is fast enough and one threshold string from the reference serves all three |
| D-29 | Separate request lines for the mode switch (PATH_EN) and the output switch (OUT_EN) | The zero calibration needs the ladder at its working voltage with the DUT disconnected |
| D-30 | Pre-regulator headroom of 0.45 V, set by a difference amplifier at the feedback pin | The converter output ends at 5.5 V, so 0.6 V above a 5.0 V set-point is out of range; a gain of 0.2 keeps the loop gain of the converter near its usual value |
| D-31 | VCONTROL of the output LDO from the boost output ahead of the +12 V_A regulator | The control current follows the load current and would modulate the analog rail |
| D-32 | A buffer copies the ladder output for the guard ring, the level translator and the monitor | Nothing resistive may hang on the node after the shunts; taken ahead of the output switch so the guard is valid during the zero calibration |
| D-33 | Level translator with the DUT on the side that has no control pins | Direction and enable stay valid while the DUT supply is off |
| D-34 | Request lines active high with pull-downs on the carrier; clock and data lines on the pull-ups of the logic device | The power-up glitches of the MCU pins are low pulses; fewer parts |
| D-35 | VIN protected by a fuse with reverse clamp and by an over-voltage detector that keeps the ampere switch open | A clamp at 5.5 V on a terminal that may see a bench supply would have to absorb its full current; the open switch blocks 30 V |
| D-36 | Candidate parts chosen for the draft: MAX II EPM240, MUX509, MCP3208, LT3042, LM27761, LMR62014, TC4427, MCP6561 and MCP6562, OPA197, OPA365, SN74LVC8T245, CSD17577Q3A, IRLML0030, BAV199 | Needed to draw the schematic; each one stays a candidate until its check record is closed |
| D-37 | Schematic and part placement drawn as draft A0 before the checks of section 16 are closed | Requested by the project owner, to review the design as a whole and to start the layout work early |
| D-38 | Draft outline of 160 mm × 100 mm with four M3 holes | A standard size with room for a first layout; to be reduced when the placement is final |
| D-39 | Controller is a Raspberry Pi Pico 2 (RP2350) on pin sockets; it replaces the ESP32-S3 development board of D-14 and D-23 | Requested by the project owner: one controller of known price and stock, developed with open tools inside the repository; its PIO blocks give hardware timing (D-40) |
| D-40 | Range sequencer, over-current trip and acquisition timing are PIO programs of the controller; no separate logic device (replaces D-24 and the I2S clocking of D-07) | A PIO state machine executes one instruction per cycle of the system clock, independently of the processors; the programs are built and tested from the repository, where the logic device needed the tools and the programmer of its vendor |
| D-41 | Side data in two discrete parallel-load shift registers, read into the same word as the conversion result (returns to D-08) | The module has 26 GPIO pins; one state machine reading both data pins makes the alignment a property of the hardware |
| D-42 | One supply domain: either USB connector powers both boards through diodes (replaces D-25 and D-34) | With one controller on the carrier there is no second domain to isolate; the data cable alone runs the instrument at low DUT current; the pins of the RP2350 tolerate 3.3 V without supply |
| D-43 | An over-voltage on VIN holds the ampere switch open through a transistor at its gate driver | The one fault that must not wait for a program; keeps the rule that hardware may refuse a request |
| D-44 | DUT connectors and logic port in the pin order of the PPK2: a 1×4 pin header (GND, VIN, VOUT, GND) in parallel with a lever terminal block, and a 1×10 logic port (VCC, GND, D7 to D0) whose VCC pin can supply the translator | Requested by the project owner, in place of screw terminals; order taken from Figure 4 of the PPK2 User Guide v1.0.1 |
| D-45 | Reference designators numbered as the annotation tool of KiCad does by default: one count per prefix, by sheet, then by position | Requested by the project owner; a new annotation in KiCad then changes nothing |
| D-46 | Draft outline of 130 mm × 100 mm (replaces D-38); parts placed by connectivity, block by block | The controller module and 33 parts fewer need less room; the placement of D-37 put the parts in rows and was not a basis for routing |

## 16. Open Checks Before Freezing the Schematic

The draft schematic uses the parts below. Pin numbers of the symbols from the
KiCad library were not compared with the datasheets yet; that comparison is
part of every check. Three symbols were drawn for the project from the
manufacturer's datasheet (ADS8860, MUX509 and TPS63020).

- AD8421: input common-mode range with +12 V / −4 V, settling time and noise
  at G = 20, bias current against the leakage budget.
- ADS8860: convert-start and data timing against the program of the
  acquisition state machine at 100 kSPS and 500 kSPS; input driver and
  reference drive requirements.
- RP2350 PIO: size of the acquisition program and of the range sequencer
  against the 32 instructions of a block; reaction time from a comparator
  edge to a gate; DMA pacing from the state machine.
- LT3080: dropout on both supply pins (0.45 V of headroom at 1 A is close
  to it), minimum load, thermal resistance of the package on the planned
  copper.
- Pre-regulator (TPS63020): stability with the difference amplifier in its
  feedback path over 1.2 V to 5.5 V, behavior at the 5.5 V end against its
  over-voltage protection, ripple after the filter, land pattern of the
  package (the draft uses a generic 14-pin footprint).
- Range MOSFETs, multiplexer and clamp: leakage at 40 °C; gate-charge
  injection into VOUT when switching; surge current of the clamp diodes.
- Comparators: propagation delay, input range, thresholds and hysteresis in
  simulation.
- Shift registers (SN74LV165A): timing of the load pulse against the
  convert-start edge, maximum clock at 3.3 V against the 500 kSPS option.
- Interlock transistor (BSS138): threshold and on-resistance with 3.3 V at
  its gate.
- Gate drivers: input thresholds with 3.3 V logic, propagation delay,
  supply current, output state without supply.
- Analog rails: load of each rail against the converters (LMR62014,
  LT3042, LM27761), start-up order, noise of the boost converter after the
  +12 V_A regulator, the −4 V rail at the lowest USB voltage.
- VBUS transients: the charge pump is rated for 5.8 V and the low-noise
  regulators for 6 V; hot-plug overshoot with the chosen suppressor and
  bulk capacitor.
- Level translator: supply current drawn from the buffer and behavior when
  VOUT is off or below 1.65 V.
- USB-C: CC thresholds and behavior on 500 mA, 1.5 A and 3 A sources.
- Pico 2 in hand: revision of the RP2350 (erratum E9 of revision A2
  concerns pull-downs with the input buffer on; revision A4 corrects it),
  pin headers fitted, height on the sockets.
- Lever terminal block (WAGO 2601-1104): footprint, side of the wire entry
  and current rating against the drawing of the manufacturer.
- Monitor ADC (MCP3208): input range and source impedance of each channel,
  SPI mode shared with the DAC.
- Supply joining: in-rush current on the USB port of the computer when the
  jumper feeds the carrier, diode drops against the 4.4 V minimum of the
  rails, and series resistor values against the clock edges.
- Path resistance: switches, shunt, fuse and connectors against the 150 mV
  limit of R-06 in ampere mode.
- USB device stack: TinyUSB as the Pico SDK brings it; sustained CDC
  throughput on the RP2350 before phase 1 ends.

## 17. Master Component Bill of Materials (BOM) Summary

| Category | Component Part Number | Package | Key Attribute |
| --- | --- | --- | --- |
| Controller | Raspberry Pi Pico 2 with pin headers | 2 × 20 pins | RP2350, USB Full-Speed, three PIO blocks |
| Board sockets | 1×20 pin socket, 2.54 mm, two parts | Through-hole | Rows 17.78 mm apart |
| Power connector | USB-C receptacle, power only | 6 pins | Instrument supply with CC sense |
| Monitor ADC | MCP3208 (candidate) | SOIC-16 | VOUT, VIN, VBUS, CC, temperature, rails |
| Temperature sensor | MCP9700A (candidate) | SOT-23 | Next to the LDO |
| ADC | ADS8860 (candidate) | MSOP-10 | 16-bit, single-ended, 1 Msps |
| ADC driver | OPA365 (candidate) | SOT-23-5 | Limiter, filter and ADC drive |
| Reference | REF5025 (candidate) | SOIC-8 | 2.5 V, shared by ADC, DAC, monitor and thresholds |
| In-amp | AD8421 (candidate) | SOIC-8 | Fast settling, low noise, G = 20 |
| Precision op-amp | OPA197 (candidate), three parts | SOT-23-5 | Set-point gain, pedestal, guard buffer |
| Comparators | MCP6562 and MCP6561 (candidates) | SOIC-8, SOT-23-5 | Step up, over-current, jump up; VIN over-voltage |
| Side data | SN74LV165A (candidate), two parts | SOIC-16 | Status and logic inputs of every sample |
| Multiplexer | MUX509 (candidate) | TSSOP-16 | Dual 4:1, Kelvin sense selection |
| Gate drivers | TC4427 (candidate), three parts | SOIC-8 | Six gate lines from +12 V_A |
| DAC | MCP4921-E/SN | SOIC-8 | 12-bit voltage output DAC, SPI |
| Regulator | LT3080EDD#PBF (candidate) | DFN-8 | 1.1A, Low Noise Linear Reg |
| Pre-regulator | TPS63020 (candidate) | VSON-14 | Tracks VSET + 0.45 V |
| Analog rails | LMR62014 boost, LT3042 +12 V, LM27761 −4 V, LP5907 3.3 V (candidates) | — | Filtered analog supplies |
| Interlock | BSS138 (candidate) | SOT-23 | Holds the ampere switch open on over-voltage |
| Shunt R0 | 1 kΩ, 0.1 %, 25 ppm/°C | 0805 | 100 µA range |
| Shunt R1 | 33 Ω, 0.1 %, 25 ppm/°C | 0805 | 3 mA range |
| Shunt R2 | 1 Ω, 0.1 %, 4-terminal | 1206 | 100 mA range |
| Shunt R3 | 0.1 Ω, 0.1 %, 4-terminal | 1206 | 1 A range |
| Switch FETs | CSD17577Q3A and IRLML0030 (candidates) | SON 3.3 mm, SOT-23 | Branch, mode and output switches |
| Clamp | BAV199 (candidate) | SOT-23 | Transient path across the ladder, terminal and limiter clamps |
| Level shifter | SN74LVC8T245 (candidate) | TSSOP-24 | Digital inputs D0 to D7, DUT side on the buffered output |
| DUT connectors | 1×4 pin header and WAGO 2601-1104 lever terminal block (candidate) | 2.54 mm, 3.5 mm | GND, VIN, VOUT, GND |
| Logic port | 1×10 pin header | 2.54 mm | VCC, GND, D7 to D0 |

## 18. Software Engineering Practices

These rules apply to the firmware, the host software and every script in the
repository. They are the baseline behind requirement R-17.

### 18.1 Architecture

- Ports and adapters. Logic that does not need hardware is written against
  small interfaces and knows nothing about the SDK of the controller,
  serial ports or files.
  Hardware and I/O code implements those interfaces and stays thin.
- Firmware: every component of section 6.1 keeps its pure C sources apart
  from its adapters for the SDK. Pure code is C11, allocates nothing, keeps its
  state in structures passed by the caller, and compiles for the PC and for
  the target from the same files.
- Host: the protocol layer does no I/O. Transports implement one interface,
  and the device client depends on that interface, never on a concrete
  transport. A simulator implements the instrument side of the protocol.
- The wire protocol has one definition (section 7.5). No protocol number is
  typed by hand in C or in Python.

Patterns in use, each for a stated reason:

| Pattern | Where | Reason |
| --- | --- | --- |
| Ports and adapters | Every firmware component, host transports | Logic is tested without hardware |
| Table-driven state machine | Device states of section 6.4 | Every transition is listed, reviewed and tested |
| Single-producer, single-consumer queue | Block hand-off between the cores | No lock in the real-time path |
| Incremental parser | Frame decoders | Bytes arrive in arbitrary chunks |
| Dependency injection | Interface structures in C, protocols in Python | Fakes and the simulator replace hardware in tests |
| Immutable value objects | Frames, samples and tables on the host | No hidden state between layers |

### 18.2 Tests

| Level | Firmware | Host |
| --- | --- | --- |
| Unit | Unity on the PC, for all pure code | pytest, for every module |
| Property | — | hypothesis on the codec: round trip, chunking, resynchronization |
| Contract | Shared protocol vectors | Shared protocol vectors |
| Integration | Test application on the controller module, from phase 1 | Client against the simulator, end to end |
| System | Verification plan of section 11 | Verification plan of section 11 |

- A defect gets a failing test before its fix.
- The PIO programs of the controller run in an emulator on the PC before
  they run on hardware; the emulator is chosen in phase 1.
- Tests that need the instrument are kept apart from the ones that run
  anywhere.

### 18.3 Quality Gates

The gates run locally with the commands documented in each area, and as
continuous integration workflows. The workflows are started by hand for now
(D-22); they run on the head of a pull request before it is merged and on
the release commit. A failing gate blocks the merge.

| Gate | Firmware | Host |
| --- | --- | --- |
| Build | Firmware build for the controller, warnings as errors (the ESP-IDF build for `esp32s3` until the port of D-39 is done) | Package builds and installs |
| Unit tests | All pass, also under the address and undefined-behavior sanitizers | All pass on Windows, Linux and macOS, on the oldest and the newest supported Python |
| Coverage of pure code | Lines 90 %, branches 80 % | Lines and branches 90 % |
| Static analysis | clang-tidy and cppcheck clean | mypy in strict mode clean |
| Format and lint | clang-format | ruff |
| Protocol | Generated files up to date | Generated files up to date |
| Documentation | markdownlint | markdownlint |

The coverage figures are floors, not targets. A change does not lower the
coverage of the code it touches.

### 18.4 What the Gates Do Not Cover

Timing, throughput, noise and every analog property are verified on the bench
(sections 11 and 13). A passing pipeline shows that the logic does what its
tests say. It shows nothing about the hardware.
