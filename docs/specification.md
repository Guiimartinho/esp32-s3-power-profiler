# System Specification: OpenSource Power Profiler (ESP32-S3)

Target Performance: 100 kSPS Sampling Rate | Range: 100 nA to 1 A | Dual-Mode:
Source Meter & Ampere Meter.

## 1. Purpose, Scope & How to Use This Document

Goal: an open-source instrument in the class of the Nordic PPK2, built around
the ESP32-S3. The project was inspired by
<https://github.com/Gedankenn/power_profiller> (ESP32 + INA226 over I2C, about
50 Hz, single range, WiFi dashboard). That design is the starting idea only;
this specification replaces its architecture.

The instrument is built from two boards. The controller is an
ESP32-S3-DevKitC-1 compatible development board, bought ready-made. The
instrument's own electronics are on a carrier board, designed in this
project, that the development board plugs into through its two pin headers
(sections 4.11 and 5).

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
                                    │               └──► ADC ──► ESP32-S3
                                  VOUT ──► DUT          D0..D7 ──► level shift
```

Everything in the diagram except the ESP32-S3 is on the carrier board. The
ESP32-S3 is on the development board, which brings its own USB ports: one
for the measurement stream and one for flashing and the console.

Design principles:

- Timing belongs to hardware. The sampling clock and the up-range reaction
  never depend on firmware latency.
- Protection belongs to hardware. Firmware may request, hardware may refuse:
  the over-current trip and the up-range path work with the MCU halted.
- The device sends raw data. Conversion to amperes happens on the host with
  the calibration table, which keeps the real-time path short.
- Every sample carries its own context (range, validity, fault, logic bits),
  so a capture can be interpreted without side channels.

### Power Tree

The carrier board has its own USB-C power connector. The development board is
powered through its own USB ports and lends only its 3.3 V rail to the
carrier logic (section 4.11).

```text
USB-C VBUS 5 V ─┬─► buck-boost (tracking) ─► V_PRE = VSET + 0.6 V ─► LDO IN
(carrier)       ├─► boost ─► LC + LDO ─► +12 V_A (in-amp, mux, gates, VCONTROL)
                ├─► inverter ─► LC ─► −5 V_A (in-amp, mux, minimum load)
                └─► low-noise LDO ─► 3V3_A (ADC, driver, comparators, VREF)

Devkit 3V3 pin ───► 3V3_D (carrier logic: shift registers, level translator)
```

## 4. Analog Hardware Design

### 4.1 Power Input

- The power connector is on the carrier board, separate from the USB ports of
  the development board. The development board cannot do this job: its CC
  pins are not on the headers, and on the reference design its 5 V pin sits
  behind a 1 A Schottky diode.
- USB-C receptacle as a sink, power only: 5.1 kΩ pull-down on CC1 and CC2.
  Both CC voltages are read through the monitor ADC to classify the source.
- 5 V at 1 A on the output needs about 7 W at the input, more than a default
  USB port delivers. The output power budget follows the source:

| CC voltage | Source offers | Output power budget |
| --- | --- | --- |
| 0.25 V to 0.61 V | Default USB (500 mA) | About 1.5 W |
| 0.70 V to 1.16 V | 1.5 A | Full range (little margin at 5 V / 1 A) |
| 1.31 V to 2.04 V | 3 A | Full range |

- Enforcement: firmware averages the measured current over 10 ms; above the
  budget, or with VBUS below 4.4 V, it opens the output switch and reports a
  power-limit fault.

### 4.2 Source Meter Block (SMU)

- Main Regulator: LT3080 (candidate; 1.1 A, low noise, output follows the SET
  pin down to 0 V). The MIC29302 is not suitable: its minimum output is about
  1.24 V, above the 0.8 V requirement.
  - IN pin from the tracking pre-regulator at VSET + 0.6 V; VCONTROL pin from
    +12 V_A. This split keeps the dissipation near 0.8 W at 1 A. Feeding both
    pins from one rail 1.5 V above the output would dissipate 1.5 W, too much
    for the DFN package.
  - Minimum load: about 1 mA, provided by a 5.6 kΩ resistor from the
    regulator output to −5 V_A. It sits before the shunts, so it is not
    measured.
  - Output capacitor at the regulator, before the shunts. After the shunts
    keep the capacitance on VOUT at or below 100 nF (C0G), because its
    charging current is measured as DUT current.
- Pre-regulator: buck-boost converter (candidate: TPS63020 class) from VBUS.
  The tracking is analog: the SET voltage is injected into the feedback node,
  so no firmware is in the loop. Minimum output 1.4 V. An LC filter follows
  it; the LDO rejects the remaining ripple.
- Voltage Control (DAC): MCP4921-E/SN (12-bit, SPI), 1x gain, 2.5 V reference.
  A buffer amplifier with gain 2.1, powered from +12 V_A, drives the SET pin:
  0 V to 5.25 V in 1.28 mV steps. The DAC is not run at 2x gain from VBUS,
  because VBUS can be below 5 V.
- Voltage changes are ramped by firmware (default 1 V/ms) to limit inrush.
- Output sag: the regulator senses its own output, ahead of the shunts and
  switches, so the DUT sees up to 150 mV less at 1 A. A slow firmware loop
  (about 10 Hz, using the VOUT monitor) may trim the set-point; it is
  optional and off by default.
- Mode switch: back-to-back N-MOSFET pairs select the LDO (source mode) or
  the VIN terminal (ampere mode); break-before-make, both off at reset.
- Output switch: back-to-back N-MOSFET pair at VOUT, off at reset, opened by
  hardware on a fault.
- Slow monitors: an external 8-channel, 12-bit SPI converter (to be
  selected) on the SPI bus of the DAC reads VOUT at about 1 kSPS and, at
  100 SPS or less, VIN, VBUS, CC1, CC2, a board temperature sensor next to
  the LDO and shunts, and the +12 V_A and −5 V_A rails. The internal ADC of
  the ESP32-S3 is not used: the development board leaves too few pins for it
  (section 5), and an external converter is the more accurate one.

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
  through level shifters. The IRLML6402 P-MOSFET driven by a GPIO does not
  work here: with the rail at 0.8 V there is no gate drive to turn it on,
  with the rail at 5 V a 3.3 V GPIO cannot turn it off, and its 65 mΩ is
  comparable to the 0.1 Ω shunt.
- Kelvin sensing: the amplifier measures across the shunt element only. A
  low-leakage 4:1 analog multiplexer on the positive input selects the sense
  node of the active branch (the supply node for R0); the negative input is
  the common VOUT node. The switch resistance therefore adds burden but no
  measurement error.
- Transient clamp: a low-leakage diode clamp across the ladder carries a
  current step during the first microseconds, before the range logic reacts.
  Its leakage at 100 mV must fit the leakage budget.
- Leakage budget: everything that bypasses R0 or loads the sense nodes must
  total below 10 nA at 40 °C. An off MOSFET sees only the burden voltage
  across it, so its channel leakage is small; gate leakage appears as an
  offset and is removed by the zero calibration.

### 4.4 Range Control Logic

Firmware is too slow to protect the DUT: samples arrive in DMA blocks with
milliseconds of latency. The range state lives in hardware.

- State: a 2-bit range register (R0 to R3) built from discrete logic or a
  small programmable mixed-signal device; the choice is made in phase 3.
- Step up: a comparator on the amplified signal at 90 % of full scale moves
  the register one range up. Target: under 2 µs from threshold crossing to
  the new branch conducting. A blanking time of about 2 µs follows each step,
  then a further step is allowed, so a large step climbs range by range.
- Jump up: a second comparator directly across the ladder trips at about
  150 mV and forces R3 at once, without waiting for the amplifier.
- Step down: only on a pulse from the MCU, and only if the step-up comparator
  is not active. Firmware issues it when the current stays below the "switch
  down" threshold for N consecutive samples (N configurable, default 100).
  After a request it waits until the range bits change, or for a hold-off of
  four blocks, before it evaluates the rule again, so that one request never
  becomes two.
- Lock: the MCU can force a fixed range. The jump-up path and the
  over-current trip stay active even when locked.
- Over-current: a comparator on R3 at about 1.2 A opens the output switch and
  sets a fault latch that only the MCU can clear.
- Reset state: R3 selected, output switch open, mode switch open.

### 4.5 Signal Chain

- Instrumentation Amplifier: AD8421 (candidate) at G = 20 (gain resistor
  523 Ω, 0.1 %, 10 ppm/°C). It must settle within one sample period (10 µs)
  after a range change. The INA188 is too slow for this rate.
  - Supplies +12 V_A and −5 V_A, so the 0.8 V to 5 V common mode stays inside
    the input range.
  - Reference pin at +50 mV (buffered). Zero current then reads about 1300
    codes, so offset, noise and small reverse currents are not clipped.
  - The amplifier offset is larger than the 100 µV that 100 nA produces in
    R0, so per-range offset calibration is mandatory.
- Limiter: the amplifier output can reach 10 V while a range change is in
  progress. A series resistor and clamp, followed by an ADC driver powered
  from 3V3_A, keep the ADC and comparator inputs inside their ratings.
- Anti-alias filter: two poles near 40 kHz around the ADC driver, plus the RC
  network the ADC input requires.

### 4.6 Data Acquisition (ADC)

- Main ADC: 16-bit single-ended SAR, at least 500 kSPS. Candidate: ADS8860
  (the MCP33131D-10 from the first draft is the differential 1 Msps version,
  and the ADS8326 tops out at 250 kSPS).
- Reference: 2.5 V precision reference (candidate: REF5025), shared with the
  DAC so both scale together.
- Conversion timing: the convert-start signal is the word clock of the I2S
  peripheral, never an interrupt handler. Sampling jitter then does not
  depend on firmware.
- Clocking: at 100 kSPS with 32 bit clocks per frame the bit clock is
  3.2 MHz, an integer division (50) of the 160 MHz source. Keep every divider
  in the chain an integer; a fractional divider adds sampling jitter.
- Oversampling option: 500 kSPS (bit clock 16 MHz, still an integer divider)
  decimated by 5 in firmware. It improves noise and relaxes the anti-alias
  filter. Decide in phase 1 from measured noise and CPU load.

### 4.7 Synchronous Side Data

- A 16-bit parallel-load shift register (two 74LVC165-class parts) is loaded
  by the same convert-start edge and shifted by the same bit clock as the
  ADC. It carries the 2 range bits, the fault bit, the 8 digital inputs and 5
  spare bits.
- Candidate capture: the second I2S port as a slave receiver on the same
  clocks. Both DMA streams are started before the clocks are enabled, so
  they stay aligned sample for sample.
- Fallback if alignment is not reliable: range changes time-stamped by the
  MCPWM capture unit, and the digital inputs captured at a lower rate.

### 4.8 Digital Inputs

- 8 logic channels, D0 to D7, through a level translator whose DUT-side
  supply is VOUT, so they follow the DUT logic level from 1.6 V to 5.5 V.
- Series resistors and ESD protection on every pin. Input leakage must not
  load the DUT; the translator supply current from VOUT is taken ahead of the
  shunts or accounted for in the zero calibration.

### 4.9 Protection & Grounding

- Reverse-polarity and over-voltage protection (clamp at about 5.5 V) on VIN
  and VOUT; ESD protection on all external terminals.
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

### 4.11 Development Board Interface & Power Domains

The carrier board has two 1×22 pin sockets at 2.54 mm pitch, 22.86 mm apart,
and the development board plugs into them (section 5 has the pin
assignment). The interface keeps the two boards independent:

- Domain D (digital): 3V3_D comes from the 3V3 pins of the development board
  and powers only the carrier logic that talks to the MCU. Budget: 100 mA,
  to be confirmed against the regulator of the board in hand.
- Domain A (analog and SMU): every other rail derives from the USB-C power
  connector of the carrier (section 4.1).
- The 5 V pin of the development board is not used. A solder jumper, open by
  default, may connect it to the carrier 5 V rail through a diode, so that
  one supply powers both boards.
- Either domain can be powered without the other. Every signal that crosses
  between them has a series resistor, and the parts on the boundary tolerate
  a voltage on their pins while unpowered.
- The carrier holds its control inputs in the safe state with pull-down
  resistors, whatever the MCU pins do during reset: output switch open,
  regulators off, range R3.
- Firmware drives no carrier input until PWR_GOOD reports the analog rails
  valid, and treats the loss of PWR_GOOD as a fault.
- The grounds of both boards join at the sockets. The development board,
  with its switching edges and its antenna, stays away from the shunt ladder
  and the amplifier (section 10).

## 5. Microcontroller, Connectivity & Pin Map

- Controller: an ESP32-S3-DevKitC-1 compatible development board with an
  ESP32-S3-WROOM-1 module (N8R8 or N16R8, both with 8 MB of octal PSRAM),
  plugged into sockets on the carrier board. The board in use is a clone
  with two USB-C ports; the pinout reference is the Espressif design.
- Reference data, taken from the Espressif user guide, schematic and layout
  drawing of the ESP32-S3-DevKitC-1 v1.1: two 1×22 headers at 2.54 mm pitch,
  22.86 mm between the rows, board outline 25.40 mm × 62.74 mm. A clone can
  differ in outline, regulator, LED pin and 5 V path, so the carrier depends
  on none of them. Section 16 lists what to confirm on the board in hand.
- USB: both ports are on the development board.
  - UART port (USB-to-UART bridge on GPIO 43 and 44): flashing and console.
  - Native USB port (GPIO 19 D- and GPIO 20 D+): the measurement stream and
    the command channel. The ESP32-S3 USB is Full-Speed only (12 Mbit/s).
- WiFi and Bluetooth stay disabled while capturing, to keep interrupt latency
  and supply noise down.

Pins the carrier does not use:

| GPIO | Reason |
| --- | --- |
| 19, 20 | Native USB |
| 43, 44 | UART0, wired to the USB-to-UART bridge |
| 35, 36, 37 | Octal PSRAM of the module |
| 0, 3, 45, 46 | Strapping pins, left to their boot function |
| 38, 48 | RGB LED of the development board: GPIO 38 on v1.1, GPIO 48 on v1.0 and on most clones |
| 39, 40, 41, 42 | JTAG, kept free for a debug probe |

Pin map of the 19 signals between the boards. J1 and J3 are the header names
of the reference design, and pin 1 of both is at the antenna end.

| GPIO | Header pin | Signal | Direction | Function |
| --- | --- | --- | --- | --- |
| 4 | J1-4 | RANGE_DOWN | Out | Step-down pulse |
| 5 | J1-5 | RANGE_LOCK | Out | Force fixed range |
| 6 | J1-6 | RANGE_SET0 | Out | Range to force, bit 0 |
| 7 | J1-7 | RANGE_SET1 | Out | Range to force, bit 1 |
| 15 | J1-8 | DAC_CS | Out | DAC chip select (SPI2) |
| 16 | J1-9 | SPI_SCK | Out | Clock of the DAC and the monitor ADC (SPI2) |
| 17 | J1-10 | SPI_MOSI | Out | Data to the DAC and the monitor ADC (SPI2) |
| 18 | J1-11 | SPI_MISO | In | Data from the monitor ADC (SPI2) |
| 8 | J1-12 | MON_CS | Out | Monitor ADC chip select (SPI2) |
| 9 | J1-15 | FAULT_CLR | Out | Clear the over-current latch |
| 10 | J1-16 | FAULT_N | In | Over-current latch, active low |
| 11 | J1-17 | SIDE_DOUT | In | Shift-register data (I2S1) |
| 12 | J1-18 | ADC_DOUT | In | ADC data (I2S0) |
| 13 | J1-19 | ACQ_BCLK | Out | ADC and shift-register clock (I2S0) |
| 14 | J1-20 | ACQ_WS | Out | Convert-start and load (I2S0) |
| 1 | J3-4 | MODE_SEL | Out | Source or ampere mode |
| 2 | J3-5 | OUT_EN | Out | Output switch request |
| 47 | J3-17 | PWR_GOOD | In | Analog rails valid |
| 21 | J3-18 | SMU_EN | Out | Pre-regulator and LDO enable |

- Power and ground: 3V3 (J1-1, J1-2) feeds 3V3_D, 5V (J1-21) goes to the
  optional jumper, and ground is J1-22, J3-1, J3-21 and J3-22. RST (J1-3) is
  not connected.
- The acquisition signals use the pins closest to the ground pin J1-22, to
  keep their return path short. The I2S and SPI peripherals reach any pin
  through the GPIO matrix, and the slow SPI bus does not need the dedicated
  SPI2 pins.
- The status indicator is the RGB LED of the development board, with its
  GPIO as a build option.
- No spare general-purpose pin is left without touching the JTAG pins, so a
  new signal means sharing the SPI bus or giving up the debug probe.

## 6. Firmware Architecture & Execution Strategy (ESP-IDF)

To guarantee uninterrupted 100 kSPS sampling without dropping frames, the
firmware uses the dual-core architecture of the ESP32-S3 combined with DMA.
There is no per-sample interrupt and no per-sample driver call: one SPI
transaction per timer interrupt at 100 kHz does not fit in 10 µs under
ESP-IDF.

```text
                  ┌──────────────────────────────────────────┐
                  │          ESP32-S3 DUAL-CORE MCU          │
                  └────────────────────┬─────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
┌───────────────────────┐                             ┌───────────────────────┐
│        CORE 0         │                             │        CORE 1         │
│  (Real-Time Engine)   │                             │  (Data Communication) │
├───────────────────────┤                             ├───────────────────────┤
│ • Hardware-timed CNV  │                             │ • USB CDC Driver      │
│   (I2S word clock)    │                             │ • Frame Building      │
│ • I2S RX + DMA        │───[ Shared RingBuffer ]────>│ • Command Handling    │
│ • Down-range Decision │                             │ • Slow Monitors       │
│ • Block Hand-off      │                             │ • Diagnostics/LEDs    │
└───────────────────────┘                             └───────────────────────┘
```

### 6.1 Components

| Component | Responsibility |
| --- | --- |
| `base` | Primitives shared by every component: status codes, byte-order helpers, block queue |
| `proto` | Frame encoding/decoding, sample word, command envelopes, error codes |
| `acq` | I2S capture, stream alignment, decimation, sample-word assembly |
| `afe` | Range lock and step-down, mode switch, output switch, fault latch |
| `smu` | DAC, voltage ramp, regulator enable, power budget enforcement |
| `monitor` | Slow channels of the monitor ADC: VOUT, VIN, VBUS, CC, temperature, rails |
| `cal` | Calibration table in NVS, zero calibration routine |
| `usb_link` | TinyUSB CDC ACM, host-open detection |
| `app` | Device state machine, command handlers, start-up self-test |

Rules: `base` and `proto` are libraries that any component may use. Among
the others, only `app` calls across components, and no component other than
`cal` writes flash. Every component keeps its hardware-independent logic
apart from its ESP-IDF code, as section 18 describes.

### 6.2 Tasks

| Task | Core | Priority | Trigger | Work |
| --- | --- | --- | --- | --- |
| `acq_task` | 0 | Highest | DMA block ready (2.56 ms) | Assemble words, range decision, push block |
| `usb_tx_task` | 1 | High | Block in ring buffer | Build frame, write to CDC |
| `tinyusb_task` | 1 | High | USB events | USB stack |
| `cmd_task` | 1 | Medium | Bytes from CDC | Parse and execute commands |
| `monitor_task` | 1 | Low | 1 ms timer | Slow channels, power budget, thermal |
| `app_task` | 1 | Low | Events | State machine, LEDs |

### 6.3 Acquisition Pipeline

1. The I2S word clock starts a conversion and loads the shift register.
2. DMA fills a block of 256 frames for each port; the driver signals
   `acq_task`.
3. `acq_task` checks alignment, optionally decimates, merges ADC code and
   side bits into 32-bit sample words and marks the settling window after
   any change of the range bits. The window starts at the first sample that
   shows the new range.
4. It evaluates the step-down rule on the block and pulses RANGE_DOWN.
5. The block goes into the ring buffer. If the buffer is full the block is
   dropped and counted; acquisition never blocks.

Budgets:

- CPU: `acq_task` must use under 30 % of Core 0 at 100 kSPS.
- Memory: ring buffer of 64 blocks (about 66 kB, 164 ms of data) in internal
  RAM. PSRAM is not used in the real-time path.
- Latency from sample to host: under 20 ms typical.
- Flash writes (NVS) are forbidden while streaming, because they stall both
  cores.

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
  partition by placement, with the switching converters and the development
  board away from the front end.
- Development board: on sockets, with its USB connectors at the edge of the
  carrier and within reach; no carrier copper or parts under its antenna
  end; the front end at the opposite end of the carrier.
- Socket footprint: two rows of 22 holes, 22.86 mm apart, as on the
  reference design. Confirm it on the board in hand before fabrication.
- Guard ring driven at VOUT potential around the R0 sense node and the
  amplifier inputs; no solder mask over the guard; clean flux residue.
- Kelvin routing as a tightly coupled pair from each shunt to the
  multiplexer.
- Shield can over the shunt ladder, multiplexer, amplifier and ADC.
- Thermal relief for the LDO and R3 away from R0 and the reference.
- Test points on every rail, sense node, comparator output and range bit.
- Connectors on the carrier: USB-C (power only), the two sockets of the
  development board, VIN, VOUT/GND and a 10-pin logic header.

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
firmware/     ESP-IDF project, one directory per component of section 6.1
host/         Python package: protocol, CLI, viewer, analysis
protocol/     Protocol definition, generator and shared test vectors
docs/         This specification, component checks, test reports, protocol
              reference, calibration procedure
tools/        Calibration and production-test scripts
```

## 13. Development Phases & Exit Criteria

1. Risk prototypes on a development board with an ADC evaluation module.
   Exit: ADC captured through I2S at 100 kSPS (and 500 kSPS) for 10 minutes
   with no lost samples; side data aligned with the ADC stream; USB
   throughput of at least 500 kB/s sustained; CPU load recorded.
2. Analog front end with one fixed range on a test board. Exit: noise,
   offset, drift and settling measured and the budget of section 4.10
   updated; oversampling decision taken.
3. Shunt ladder and range logic. Exit: verification tests for R-06 and R-07
   passed; range-logic implementation chosen.
4. Source mode and power. Exit: tests for R-08, R-13 and R-14 passed;
   thermal measurements at 1 A recorded.
5. Carrier board, revision A, with the development board plugged in. Exit:
   full verification plan executed, issues listed.
6. Calibration, protocol freeze and host software. Exit: R-05 and R-15
   demonstrated end to end.
7. Revision B and release: sources, documentation and test reports
   published.

Firmware and host software start in phase 1 and grow with each phase; the
protocol of section 7 is implemented from the first prototype.

## 14. Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| I2S timing does not match the ADC interface | No hardware-timed capture | Phase 1 prototype; fallback SPI slave with DMA and external framing |
| Two I2S streams lose alignment | Wrong range per sample | Common clocks, start before enabling; fallback MCPWM capture |
| USB Full-Speed throughput too low | R-01 not met | 3-byte packing; larger writes; last resort lower rate |
| Up-range too slow, DUT brown-out | R-07 not met | Jump-up comparator, transient clamp, simulation before layout |
| Range oscillation at thresholds | Unusable data near thresholds | Wide hysteresis, firmware-only step down, ramp test |
| Leakage and offset dominate R0 | R-04, R-05 not met | Guarding, low-leakage parts, zero calibration, temperature record |
| LDO or shunt overheating | Drift, shutdown | Split LDO supply, tracking pre-regulator, thermal derating |
| Switching noise in the measurement | Noise above budget | LC filters, placement, shield, converter frequency above 1 MHz |
| USB source too weak | Brown-out of the instrument | CC detection, power budget, VBUS monitor |
| Candidate part unsuitable or unavailable | Redesign | Section 16 checks first; second source noted in the BOM |
| Development board differs from the reference design | Wrong pin, weak 3.3 V rail or mechanical misfit | Checks of section 16 on the board in hand; the carrier uses neither the 5 V pin nor the LED and strapping pins |
| Noise and ground bounce through the board sockets | Jitter on the convert-start signal | Acquisition signals next to a ground pin, series resistors, low drive strength, measurement in phase 1 |
| Firmware and host disagree on the protocol | Corrupt or misread data | One definition file, generated constants, shared test vectors, stale-file check in continuous integration |

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

## 16. Open Checks Before Freezing the Schematic

- AD8421: input common-mode range with +12 V / −5 V, settling time and noise
  at G = 20, bias current against the leakage budget.
- ADS8860: convert-start and data timing against the I2S frame at 100 kSPS
  and 500 kSPS; input driver and reference drive requirements.
- ESP32-S3 I2S: integer clock dividers for the chosen rates, master and
  slave ports on shared clocks, DMA block callbacks.
- LT3080: dropout on both supply pins, minimum load, thermal resistance of
  the package on the planned copper.
- Pre-regulator: feedback injection range, stability over 1.4 V to 5.6 V,
  ripple after the filter.
- Range MOSFETs, multiplexer and clamp: leakage at 40 °C; gate-charge
  injection into VOUT when switching.
- Comparators: propagation delay, input range, thresholds and hysteresis in
  simulation.
- Level translator: supply current drawn from VOUT and behavior when VOUT
  is off.
- USB-C: CC thresholds and behavior on 500 mA, 1.5 A and 3 A sources.
- Development board in hand: header labels against the reference pinout,
  spacing between the rows (reported by the owner as 22.86 mm), module
  marking (N8R8 or N16R8), GPIO of the RGB LED, regulator type with its
  current rating, and how the 5 V pin connects to the USB ports.
- Monitor ADC: part selection, input range and source impedance of each
  channel, SPI mode shared with the DAC.
- Board interface: behavior of the boundary parts with one power domain off,
  and series resistor values against the clock edges at 3.2 MHz and 16 MHz.
- USB device stack: ESP-IDF v6.0 ships no TinyUSB component. Confirm the
  component to use from the component registry, its version and its license
  before phase 1.

## 17. Master Component Bill of Materials (BOM) Summary

| Category | Component Part Number | Package | Key Attribute |
| --- | --- | --- | --- |
| Controller | ESP32-S3-DevKitC-1 compatible board, N8R8 or N16R8 module | 2 × 22 pins | Native USB and USB-to-UART bridge on board |
| Board sockets | 1×22 pin socket, 2.54 mm, two parts | Through-hole | Rows 22.86 mm apart |
| Power connector | USB-C receptacle, power only | — | Instrument supply with CC sense |
| Monitor ADC | 8-channel, 12-bit SPI converter (to be selected) | — | VOUT, VIN, VBUS, CC, temperature, rails |
| ADC | ADS8860 (candidate) | MSOP-10 | 16-bit, single-ended, 1 Msps |
| ADC driver | Rail-to-rail op-amp, 3.3 V (to be selected) | — | Limiter, filter and ADC drive |
| Reference | REF5025 (candidate) | SOIC-8 | 2.5 V, shared by ADC and DAC |
| In-amp | AD8421 (candidate) | SOIC-8 | Fast settling, low noise, G = 20 |
| Comparators | Under 100 ns, three channels (to be selected) | — | Step up, jump up, over-current |
| Range logic | Discrete logic or programmable mixed-signal (phase 3) | — | Range register, blanking, interlock |
| Multiplexer | Low-leakage 4:1 analog mux (to be selected) | — | Kelvin sense selection |
| Shift register | 74LVC165 class, two parts | TSSOP-16 | Range, fault and logic bits |
| DAC | MCP4921-E/SN | SOIC-8 | 12-bit voltage output DAC, SPI |
| Regulator | LT3080EDD#PBF (candidate) | DFN-8 | 1.1A, Low Noise Linear Reg |
| Pre-regulator | TPS63020 class buck-boost (candidate) | — | Tracks VSET + 0.6 V |
| Analog rails | Boost to +12 V, inverter to −5 V, LDOs (to be selected) | — | Filtered analog supplies |
| Shunt R0 | 1 kΩ, 0.1 %, 25 ppm/°C | 0805 | 100 µA range |
| Shunt R1 | 33 Ω, 0.1 %, 25 ppm/°C | 0805 | 3 mA range |
| Shunt R2 | 1 Ω, 0.1 %, 4-terminal | 1206 | 100 mA range |
| Shunt R3 | 0.1 Ω, 0.1 %, 4-terminal | 1206 | 1 A range |
| Switch FETs | N-MOSFET, few mΩ, low leakage (to be selected) | — | Branch, mode and output switches |
| Clamp | Low-leakage diode clamp (to be selected) | — | Transient path across the ladder |
| Level shifter | 8-bit translator, DUT side on VOUT (to be selected) | — | Digital inputs D0 to D7 |

## 18. Software Engineering Practices

These rules apply to the firmware, the host software and every script in the
repository. They are the baseline behind requirement R-17.

### 18.1 Architecture

- Ports and adapters. Logic that does not need hardware is written against
  small interfaces and knows nothing about ESP-IDF, serial ports or files.
  Hardware and I/O code implements those interfaces and stays thin.
- Firmware: every component of section 6.1 keeps its pure C sources apart
  from its ESP-IDF adapters. Pure code is C11, allocates nothing, keeps its
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
| Integration | Test application on the development board, from phase 1 | Client against the simulator, end to end |
| System | Verification plan of section 11 | Verification plan of section 11 |

- A defect gets a failing test before its fix.
- Tests that need the instrument are kept apart from the ones that run
  anywhere.

### 18.3 Quality Gates

The gates run locally with the commands documented in each area, and as
continuous integration workflows. The workflows are started by hand for now
(D-22); they run on the head of a pull request before it is merged and on
the release commit. A failing gate blocks the merge.

| Gate | Firmware | Host |
| --- | --- | --- |
| Build | ESP-IDF build for `esp32s3`, warnings as errors | Package builds and installs |
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
