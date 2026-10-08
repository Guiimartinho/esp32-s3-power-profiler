# System Specification: OpenSource Power Profiler (ESP32-S3)

Target Performance: 100 kSPS Sampling Rate | Range: 100 nA to 1 A | Dual-Mode:
Source Meter & Ampere Meter.

## 1. Purpose, Scope & How to Use This Document

Goal: an open-source instrument in the class of the Nordic PPK2, built around
the ESP32-S3. The project was inspired by
<https://github.com/Gedankenn/power_profiller> (ESP32 + INA226 over I2C, about
50 Hz, single range, WiFi dashboard). That design is the starting idea only;
this specification replaces its architecture.

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
| R-14 | Power input | USB-C 5 V; output power limited to what the source offers |
| R-15 | Host software | Capture, live view, statistics, export, on Windows/Linux/macOS |
| R-16 | Openness | Sources published: firmware and host software under MIT, hardware under CERN-OHL-P v2 |

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

```text
USB-C VBUS 5 V ─┬─► buck-boost (tracking) ─► V_PRE = VSET + 0.6 V ─► LDO IN
                ├─► boost ─► LC + LDO ─► +12 V_A (in-amp, mux, gates, VCONTROL)
                ├─► inverter ─► LC ─► −5 V_A (in-amp, mux, minimum load)
                ├─► LDO ─► 3V3_D (ESP32-S3, logic)
                └─► low-noise LDO ─► 3V3_A (ADC, driver, comparators, VREF)
```

## 4. Analog Hardware Design

### 4.1 Power Input

- USB-C receptacle as a sink: 5.1 kΩ pull-down on CC1 and CC2. Both CC
  voltages are read by the MCU to classify the source.
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
- Slow monitors (ESP32-S3 internal ADC, about 1 kSPS): VOUT, VIN, VBUS, CC1,
  CC2 and a board temperature sensor next to the LDO and shunts.

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

## 5. Microcontroller, Connectivity & Pin Map

- MCU: ESP32-S3-WROOM-1-N8R8 (8 MB flash, 8 MB octal PSRAM). GPIO 35 to 37
  are used by the PSRAM. GPIO 0, 3, 45 and 46 are strapping pins and are left
  to their boot function.
- USB Interface: Dual-USB layout.
  - Port 1 (USB-UART): CH340K or CP2102 for flashing/debugging.
  - Port 2 (Native USB-OTG): GPIO 19 (D-) and GPIO 20 (D+). The ESP32-S3 USB
    is Full-Speed only (12 Mbit/s); it carries the measurement stream and the
    command channel.
- WiFi and Bluetooth stay disabled while capturing, to keep interrupt latency
  and supply noise down.

Proposed pin map, to be confirmed at schematic capture:

| GPIO | Signal | Direction | Function |
| --- | --- | --- | --- |
| 1 | VOUT_MON | Analog in | Output voltage monitor |
| 2 | VIN_MON | Analog in | External input voltage monitor |
| 4 | CC1_MON | Analog in | USB-C source capability |
| 5 | CC2_MON | Analog in | USB-C source capability |
| 6 | TEMP_MON | Analog in | Board temperature |
| 7 | VBUS_MON | Analog in | USB supply voltage |
| 8 | MODE_SEL | Out | Source or ampere mode |
| 9 | OUT_EN | Out | Output switch request |
| 10, 11, 12 | DAC_CS, MOSI, SCK | Out | DAC (SPI2) |
| 13 | SMU_EN | Out | Pre-regulator and LDO enable |
| 14 | PWR_GOOD | In | Analog rails valid |
| 15 | ACQ_BCLK | Out | ADC and shift-register clock (I2S0) |
| 16 | ACQ_WS | Out | Convert-start and load (I2S0) |
| 17 | ADC_DOUT | In | ADC data (I2S0) |
| 18 | SIDE_DOUT | In | Shift-register data (I2S1) |
| 19, 20 | USB D-, D+ | I/O | Native USB |
| 21 | RANGE_DOWN | Out | Step-down pulse |
| 38 | RANGE_LOCK | Out | Force fixed range |
| 39, 40 | RANGE_SET0, RANGE_SET1 | Out | Range to force |
| 41 | FAULT_N | In | Over-current latch |
| 42 | FAULT_CLR | Out | Clear the latch |
| 43, 44 | UART0 TX, RX | I/O | Debug port |
| 47, 48 | LED_STATUS, LED_RGB | Out | Indicators |

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
| `acq` | I2S capture, stream alignment, decimation, sample-word assembly |
| `afe` | Range lock and step-down, mode switch, output switch, fault latch |
| `smu` | DAC, voltage ramp, regulator enable, power budget enforcement |
| `monitor` | Slow ADC channels: VOUT, VIN, VBUS, CC, temperature |
| `cal` | Calibration table in NVS, zero calibration routine |
| `proto` | Frame encoding/decoding, command dispatch, error codes |
| `usb_link` | TinyUSB CDC ACM, host-open detection |
| `app` | Device state machine, start-up self-test |

Rules: `acq` depends on nothing but the driver layer; only `app` may call
across components; no component other than `cal` writes flash.

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
   any change of the range bits.
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
  ranges, zero calibration with the output open.
- STREAMING stops by itself when the host closes the port.
- FAULT always opens the output switch first and reports second.

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
| crc16 | 2 bytes | CRC-16/CCITT over header and payload |

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

Every command gets a response with the same sequence number and a status
code (OK, bad argument, wrong state, fault active, busy).

| Command | Purpose |
| --- | --- |
| GET_INFO | Protocol version, firmware version, hardware revision, range table, calibration |
| SET_MODE | Source meter or ampere meter (only in IDLE) |
| SET_VOLTAGE | Output voltage in mV (source mode) |
| DUT_POWER | Turn the output switch on or off |
| START / STOP | Start or stop the sample stream |
| SET_RANGE | Automatic, or locked to one range |
| SET_DOWN_N | Number of samples for the step-down rule |
| CAL_ZERO | Run the zero calibration (output open) |
| CAL_WRITE | Store gain/offset values for a range or the DAC |
| GET_STATUS | State, faults, dropped blocks, VOUT, VIN, VBUS, temperature, power budget |
| CLEAR_FAULT | Reset the over-current latch |

Events (device to host, unsolicited): fault raised, power budget changed,
state changed.

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
  partition by placement, with the switching converters and the MCU away
  from the front end.
- Guard ring driven at VOUT potential around the R0 sense node and the
  amplifier inputs; no solder mask over the guard; clean flux residue.
- Kelvin routing as a tightly coupled pair from each shunt to the
  multiplexer.
- Shield can over the shunt ladder, multiplexer, amplifier and ADC.
- Thermal relief for the LDO and R3 away from R0 and the reference.
- Test points on every rail, sense node, comparator output and range bit.
- Connectors: USB-C (data), USB-UART, VIN, VOUT/GND, 10-pin logic header.

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

## 12. Repository Structure

```text
hardware/     KiCad project, simulations, fabrication outputs
firmware/     ESP-IDF project, one directory per component of section 6.1
host/         Python package: protocol, CLI, viewer, analysis
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
5. Integrated board, revision A. Exit: full verification plan executed,
   issues listed.
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

## 17. Master Component Bill of Materials (BOM) Summary

| Category | Component Part Number | Package | Key Attribute |
| --- | --- | --- | --- |
| MCU | ESP32-S3-WROOM-1-N8R8 | Module | Native USB, Dual-Core, 8MB PSRAM |
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
| USB-UART | CH340K or CP2102 | — | Flashing/debugging port |
