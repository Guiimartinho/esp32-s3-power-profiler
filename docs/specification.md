# System Specification: Open Power Profiler (Raspberry Pi Pico 2)

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
- Part numbers marked "candidate" are proposals that no check record has
  accepted. Section 16 lists what must be confirmed before the schematic is
  frozen; each check is filed as a record in [`checks/`](checks/). No value
  in this document has been measured: each figure is a datasheet value, a
  calculation, a simulation or an estimate, and says which. The files of
  the simulations are not in
  [`../hardware/simulation/`](../hardware/simulation/) yet: until they are
  filed, a figure marked "simulated" can be read but not repeated.
- The schematic in [`../hardware/kicad/`](../hardware/kicad/) is draft A2. Every
  sheet is drawn, 14 below the root sheet (D-83), so the design can be reviewed
  as a whole. It passes the electrical rules check, and an independent review of
  its netlist against the datasheets found no defect that blocks the draft; that
  review closes no check of section 16. Its parts are the candidates of this
  document, no check of section 16 is closed (D-37), and nothing has been built
  or measured. The board of the draft is placed by a generator and routed
  automatically (D-86, section 10): 956 of its 984 connections are drawn
  and 28 are open, 25 of which break a function, so the board does not
  work until they are closed.
  [`../hardware/README.md`](../hardware/README.md) lists them one by one.
  It is a review draft, not a design to fabricate.
- Names that look alike: R0 to R3 are the four current ranges and D0 to D7
  the logic inputs, as on the PPK2. The parts of the drawings are numbered
  as KiCad numbers them (D-45), so the drawings also hold resistors R1 to
  R3 and diodes D1 to D7. Where this document means one of those parts, it
  says so or gives the value of the part.
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
| R-04 | Resolution | 100 nA or better in the lowest range at full bandwidth; RMS noise in that range at most 5 nA in ampere mode from a quiet supply and at most 40 nA in source mode (D-59) |
| R-05 | Accuracy | ±1 % of reading ±0.1 % of range after calibration (target) |
| R-06 | Burden voltage | Shunt drop 100 mV maximum; total path drop 200 mV at 1 A (D-64) |
| R-07 | Range change | On a 1 µA to 500 mA step the instrument adds at most 0.5 V of drop between its supply node and VOUT with 1 µF (effective) at the output terminals, more than 0.2 V for at most 1 µs, and at most 0.25 V with 10 µF; no oscillation between ranges (D-65) |
| R-08 | Source mode | 0.8 V to 5.0 V in 1.3 mV steps; output current, design figure: 1.0 A up to 2.0 V, falling in a straight line to 0.6 A at 5.0 V (0.83 A at 3.3 V); beyond that curve the output may sag by up to 0.6 V and an overload is reported (D-56) |
| R-09 | Ampere mode | External supply 0.8 V to 5.0 V passed through the shunts; the VIN terminal withstands −20 V to +20 V while the ampere switch is open (D-60) |
| R-10 | Digital inputs | 8 channels, 1.65 V to 5.5 V logic at the supply of the level translator, sampled with the current (D-79) |
| R-11 | Host link | Native USB Full-Speed, CDC ACM, binary protocol |
| R-12 | Calibration | Per-range gain and offset stored on the device |
| R-13 | Protection | Over-current trip, reverse polarity, over-voltage, thermal |
| R-14 | Power input | USB-C 5 V on the carrier board, or the USB connector of the controller alone; input current limited to what the source in use offers (0.45 A, 1.4 A or 1.7 A); operation with 4.25 V or more on the 5 V rail (D-49) |
| R-15 | Host software | Capture, live view, statistics, export, on Windows/Linux/macOS |
| R-16 | Openness | Sources published: firmware and host software under MIT, hardware under CERN-OHL-P v2 |
| R-17 | Software quality | Automated tests with coverage gates, static analysis and continuous integration for firmware and host software (section 18) |

Seven requirements carry the figure that the architecture delivers, each
with the decision that set it. None of the figures is a measurement: each
is a datasheet value, a calculation, a simulation or an estimate, as
stated, and section 11 holds the test that has to confirm it. The yardstick
is the PPK2 User Guide v1.0.1.

- R-04 (D-59). The 100 nA resolution holds in both modes; the noise figure
  depends on the mode. From a quiet supply the signal chain alone gives
  about 2.1 nA RMS in R0, the lowest range (simulated with typical
  datasheet figures). In source mode the output noise of the linear
  regulator (125 nV/√Hz, a typical datasheet figure without a maximum)
  stands across the 1 kΩ shunt above 1.6 kHz, the corner of the shunt with
  the 100 nF at VOUT: 26 nA to 27 nA RMS at full bandwidth, 1.1 nA after a
  mean of 100 samples (simulated). The limit of 40 nA leaves room for a
  figure that is typical only. The PPK2 states a resolution of 0.2 µA in
  its lowest range and measurement down to about 200 nA.
- R-06 (D-64). At 1 A the current passes five switch transistors, the
  0.1 Ω shunt, copper, two contacts and, in ampere mode, the fuse of the
  VIN terminal. From the VIN terminal to the VOUT terminal that is 158 mV
  with typical parts and 181 mV at the bounds; from the regulator output
  144 mV and 161 mV (calculated from the on-resistance of the datasheet at
  50 °C; the tolerance of the fuse and 20 mΩ to 25 mΩ for copper and
  contacts are allowances without a source). The shunt limit of 100 mV is
  unchanged. The PPK2 guide states no burden voltage.
- R-07 (D-65). The requirement is the drop that the instrument adds between
  its supply node and VOUT. The jump comparator acts at 151 mV across the
  ladder and range 3 conducts 0.35 µs later (0.20 µs to 0.51 µs,
  section 4.4); until then the capacitor at the DUT supplies the step.
  Simulated drop: 312 mV nominal and 422 mV in the worst case with 1 µF,
  169 mV and 186 mV with 10 µF. The limits hold only if the range sequencer
  reacts within 100 ns (rule F-16 of section 6.6), which phase 1 measures
  (section 13). A limit of 0.2 V would need about 8 µF behind the shunts,
  whose leakage and charging current would be measured as DUT current. The
  PPK2 guide states no limit for a range change.
- R-08 (D-56). The curve follows from the dropout voltage of the linear
  regulator and from the 5.5 V at which the output of the pre-regulator
  ends (section 4.2). At the tolerance limits the head room exceeds the
  dropout limit by 2 mV at 5.0 V and 0.6 A, 15 mV at 3.3 V, 25 mV at 2.0 V
  and 85 mV at 0.8 V (calculated; the dropout limit is interpolated
  between the two points the datasheet guarantees). Typical parts deliver
  1 A at every set-point (calculated). The curve is a design figure until
  the test of section 11 has confirmed it on the first boards. It needs
  4.3 W at the input with typical parts and 4.9 W at the limits. The PPK2
  states 600 mA in source mode and a rated power of 5 W; the curve is at
  or above it at every voltage.
- R-09 (D-60). The range in use is that of the PPK2. The withstand figure
  holds while the ampere switch is open: without a request, with a request
  that hardware refuses, and without supply. Both transistors of the pair
  block, and less than 1 mA flows at the terminal (simulated). A detector
  refuses to close the switch above 5.46 V (5.41 V to 5.51 V, calculated).
  While the switch is closed the supply has to stay between 0.8 V and
  5.0 V. Above 22 V the suppressor of the terminal is lost; the fuse does
  not protect it (section 4.9). The PPK2 guide states no withstand
  voltage.
- R-10 (D-79). The level translator is specified from 1.65 V (datasheet
  value). With the supply jumper as built its supply is up to 10 mV below
  the output voltage, so the logic channels are valid for an output of
  1.67 V or more (calculated). The PPK2 states 1.65 V to 5.5 V for its
  logic port.
- R-14 (D-49). The budget is an input current for each source (section 4.1):
  0.45 A through the carrier on the USB port of a computer or on a USB-C
  source that advertises the default current, 1.4 A on a 1.5 A source and
  1.7 A on a 3 A source. Current limiters hold each input below 0.67 A to
  0.85 A and 1.81 A to 2.17 A (calculated from datasheet limits). The 5 V
  rail may fall to 4.25 V, which the −4 V rail still regulates from
  (calculated on typical curves); below 3.9 V a supervisor switches the
  carrier off. From 4.5 V at the receptacle, the lower limit of the PPK2
  supply, the instrument delivers 5 V at 0.6 A with 4.34 V on the rail
  (calculated). 5 V at 1 A needs 6.7 W to 7.6 W at the input and a 3 A
  source.

## 3. System Architecture

```text
USB-C 5 V ────► limiter ─┐
                         ├► multiplexer ─► 5 V rail ─► supplies of the carrier
Pico 2 VBUS ──► limiter ─┘

5 V rail ──► pre-regulator ──► LDO (source mode) ◄── DAC ◄── SPI
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
measurement stream and the commands, and firmware is loaded through it. It
is also the second power input of the instrument (Power Tree, below).

Design principles:

- Timing belongs to hardware. The sampling clock and the up-range reaction
  never depend on firmware latency: both are state machines in the PIO
  blocks of the controller, which run from the system clock whatever the
  processors do (D-40).
- Protection has three levels, and each fault is assigned to one of them.
  Firmware may request, hardware may refuse (D-43).
  - Hardware, with no program involved: an over-voltage on VIN holds the
    ampere switch open through one transistor (D-43), and a source-mode
    request holds it open through a second one, so the two mode switches
    cannot be closed together (D-62). A supervisor switches the supplies of
    the carrier and the pre-regulator off when the 5 V rail collapses
    (D-48). Each USB input has a current limiter (D-47). Fuses, clamps and
    the limits inside the regulators belong here too, and so do the pull
    resistors that open every switch when the pins of the controller are
    released (section 4.11).
  - State machines of the PIO: the up-range path and the over-current trip.
    They work with both processors halted, as long as the analog rails are
    valid. PWR_GOOD reports that 3V3_A, +12 V_A, −4 V_A and the reference
    are present and that the supervisor of the 5 V rail has released the
    carrier.
  - Firmware, guarded by the hardware watchdog of the RP2350 (D-81):
    everything else. Section 6.6 lists the firmware rules that protect
    hardware.
- The device sends raw data. Conversion to amperes happens on the host with
  the calibration table, which keeps the real-time path short.
- Every sample carries its own context (range, validity, fault, logic bits),
  so a capture can be interpreted without side channels.

### Power Tree

The carrier board has its own USB-C power connector, and the Pico 2 has its
USB connector. Each of the two inputs passes a current limiter, and a
priority power multiplexer connects one of them to the 5 V rail of the
carrier (D-47). Either cable therefore powers the whole instrument; USB-C
is used whenever it is present. A diode feeds the VSYS pin of the Pico 2
from the 5 V rail. Sections 4.1 and 4.11 have the details.

```text
USB-C VBUS ──────────────► limiter 2.0 A ──► damper ──┐ input 1 (priority)
(carrier)                  clamp 5.45 V               ├─► multiplexer ─► 5 V rail
Pico 2 VBUS ─► jumper ───► limiter 0.76 A ────────────┘ input 2
(pin 40)                   clamp 5.45 V

5 V rail ─┬─► diode ──► VSYS of the Pico 2 (pin 39)
          ├─► supervisor, 3.9 V and 0.3 s ──► 5V_OK
          ├─► boost (runs from the rail itself) ──► +13.5 V
          │        ├─► 0.47 Ω ─► LDO [5V_OK] ─► +12 V_A (in-amp, mux, gate
          │        │                            drivers, buffers)
          │        └─► VCONTROL of the output LDO
          ├─► 2.2 Ω ─► inverter with regulator [5V_OK] ─► −4 V_A (in-amp, mux,
          │                                    buffers, minimum load)
          ├─► low-noise LDO [5V_OK] ─► 3V3_A (ADC, comparators, DAC, monitor)
          │        ├─► 10 Ω ─► reference ─► VREF 2.5 V (ADC, DAC, monitor,
          │        │                        thresholds)
          │        └─► buffer ─► VDRV = 1.091 × VREF (ADC driver and its clamp)
          ├─► LDO [5V_OK] ─► 3V3_C (carrier logic, rail monitor)
          └─► buck-boost, tracking [SMU_ON and 5V_OK] ─► V_PRE ─► LDO IN
                   V_PRE = output of the LDO + 0.45 V to 0.64 V

[5V_OK]: enabled by the supervisor of the 5 V rail
```

Input stage:

- Each limiter is an electronic fuse (candidate: TPS259621, U4 at the USB-C
  connector and U3 behind the jumper of the Pico 2). It withstands 21 V at
  its input, limits the current and clamps its output at 5.28 V to 5.61 V when
  the input rises above 5.54 V to 5.83 V (datasheet values). The limit is 2.0 A
  on USB-C and 0.76 A on the input of the controller module, the Pico 2
  (calculated from the datasheet equation).
- The multiplexer (candidate: TPS2116, U5) blocks reverse current on both
  inputs, so neither connector is fed back from the rail (1 nA typical,
  datasheet value). It selects USB-C while the output of that limiter is above
  2.15 V to 2.59 V (calculated), which is below every other threshold of the
  rail: the input changes only while the carrier is held off.
- The 5 V rail carries about 74 µF, of which 47 µF is an electrolytic
  capacitor (C11); about 62 µF remain at 5 V (estimate from the bias
  curves of the ceramic parts).

Supervisor (D-48). A voltage supervisor on the 5 V rail (candidate:
TPS3808G01, U6) drives the open-drain signal 5V_OK:

- 5V_OK falls when the rail passes 3.83 V to 4.00 V and returns 0.18 s to 0.42 s
  after the rail is back above 4.12 V at most (calculated from datasheet limits
  and the 0.1 % divider R21, R22; nominal 3.91 V and 0.30 s).
- 5V_OK enables the two 3.3 V regulators, the +12 V_A regulator and the
  charge pump of −4 V_A, the last one through the divider R27,
  R28. Through a transistor it also gates the enable of the
  pre-regulator (section 4.11). The carrier has one off state, and it is
  reached without firmware.
- The boost converter is not gated. It runs from the rail itself, so
  +13.5 V and with it the VCONTROL pin of the output LDO are present while
  the supervisor holds everything else off.

Analog rails (D-51):

- The boost converter (candidate: LMR62014, U10) makes +13.5 V from the 5 V
  rail, 13.0 V to 14.1 V with the tolerances (calculated). Its inductor L1
  is 10 µH with a saturation current of 3 A (datasheet value), and 10 µF in 1210
  stands on its output (C27).
- R37, 0.47 Ω, and C29, 10 µF, stand between the boost output and the
  regulator of +12 V_A (candidate: LT3042, U13). R38 sets 12.0 V; C30
  at the same pin sets the noise and the slow approach of the last volt (step 6
  of the table below).
- The charge pump of −4 V_A (candidate: LM27761, U11) takes the 5 V rail
  through R30, 2.2 Ω, with C21, 22 µF. Its feedback resistors R34 and
  R36 are 0.1 % parts: the rail is −3.91 V to −4.05 V (calculated).
- The two 3.3 V regulators are of one type (candidate: LP5907): U7 for 3V3_C
  and U8 for 3V3_A.

Order of the rails at power-up (simulated, with datasheet delays):

| Step | Rail | Time |
| --- | --- | --- |
| 1 | 5 V rail | Ramp of 1.7 ms, about 1 ms after the limiter has turned on |
| 2 | +13.5 V | With the 5 V rail; charged about 3 ms after the start |
| 3 | Hold-off | 0.18 s to 0.42 s; only the 5 V rail and +13.5 V are present |
| 4 | 3V3_C and 3V3_A | 0.04 ms after 5V_OK |
| 5 | −4 V_A | 0.3 ms after 5V_OK |
| 6 | +12 V_A | Above 9.85 V after 8 ms to 17 ms; settles in about 0.8 s |
| 7 | VREF | Above 2.245 V after 24 ms; within 0.1 % after about 80 ms |
| 8 | PWR_GOOD | High about 24 ms after 5V_OK, 0.2 s to 0.46 s after power |
| 9 | V_PRE | When firmware raises SMU_ON (F-28, section 4.2) |

- No rail of a 12 V part is present before the 3.3 V rails, and the
  reference is never present without the rail of its loads: it is supplied
  from 3V3_A through R31, and the diode D7 keeps VREF within one Schottky
  drop of 3V3_A while the rails fall (D-53).
- Schottky diodes clamp −4 V_A to ground (D8) and ground to +12 V_A
  (D9), so that neither rail can be pulled to the wrong polarity
  through its loads while the other one is absent: −4 V_A stays below
  +0.24 V and +12 V_A above −0.23 V (simulated, D-52).
- At power-off, or when the supervisor trips, 3V3_C is below 3.0 V after
  0.02 ms, PWR_GOOD is below 0.8 V after 0.3 ms, 3V3_A is below 1.0 V
  after 4 ms to 6 ms and +12 V_A is below 3.6 V after about 14 ms
  (simulated). For about 10 ms +12 V_A is therefore still above 3.6 V
  while 3V3_A is below 1 V; the series resistors and clamps between the
  12 V parts and the 3.3 V parts bound the current in that interval
  (section 4.5).

Rail monitor (D-54). Four open-drain comparators in one package (candidate:
MCP6569, U14) share the line PWR_GOOD, which R51 pulls up to 3V3_C and
R52 pulls down to ground. Both thresholds of the monitor are fractions
of 3V3_C (R41, R43, R44). A 1 nF capacitor from each threshold node and
from the sense node of −4 V_A to ground (C32 to C34) keeps an edge of
the line from moving its own threshold: in the package every output pin is
the neighbor of an inverting input. PWR_GOOD is low when any of these
holds (calculated from the resistor values; the bands include the
tolerances and the drift of the parts):

| Rail | PWR_GOOD low when | Band |
| --- | --- | --- |
| 3V3_A | Below 2.97 V (90 % of 3V3_C) | 2.89 V to 3.05 V |
| +12 V_A | Below 9.85 V | 9.25 V to 10.48 V |
| −4 V_A | Above −2.57 V | −2.29 V to −2.86 V |
| VREF | Below 2.245 V | 2.14 V to 2.35 V |
| 3V3_C | Absent (no pull-up) | — |
| 5 V rail | 5V_OK low: every rail above is off | 3.83 V to 4.00 V |

- The flag reports presence, not tolerance. Firmware checks the tolerance of +12
  V_A, −4 V_A and the 5 V rail with the monitor converter (F-12, section 4.11).
- PWR_GOOD does not watch the level of 3V3_C: its thresholds and its
  pull-up follow that rail, so a 3V3_C that stands low still reads as
  good. Only a missing 3V3_C is detected.
- The line can show a burst of edges for up to about 1 ms while a slow rail
  crosses its threshold (estimate; the hysteresis of the comparators is 1 mV to
  5 mV, datasheet value). Firmware therefore counts PWR_GOOD as valid only after
  10 ms of uninterrupted high (F-2).
- PWR_GOOD goes to GP28 of the controller through R4 and to a side
  bit of every sample (section 4.7). TP17 is its test point.

## 4. Analog Hardware Design

### 4.1 Power Input

- The power connector is on the carrier board, separate from the USB
  connector of the Pico 2. That one is a micro-USB receptacle without CC
  pins, good for what a default USB port offers. Its VBUS pin (pin 40)
  feeds the second input of the multiplexer through a solder jumper
  (JP1, closed as built) and a current limiter, so the data cable
  alone is enough while the DUT draws little. USB-C is used whenever it
  is present (D-47).
- USB-C receptacle (J2) as a sink, power only: 5.1 kΩ pull-down on CC1 and
  CC2 (R7, R11). Both CC voltages are read through the monitor ADC to
  classify the source. An ESD array (candidate: TPD4E1U06, U2) sits on the
  two CC pins (D-50); its leakage of 10 nA at most (datasheet value at 2.5 V)
  moves a CC reading by 51 µV (calculated), against windows that are 90 mV
  apart.
- 4.7 µF (C2), 100 nF and a transient suppressor with a stand-off
  voltage of 10 V (D2) are at the connector, ahead of every current
  limit. There is no fuse: a short of one of these parts is limited by
  the source alone.

Input stage (D-47):

- Limiter of the USB-C input: an electronic fuse (candidate: TPS259621, U4).
  Input rated 21 V absolute; current limit 2.0 A, set by R15 (1.81 A to 2.17
  A with the tolerances, calculated from datasheet limits); output clamped at
  5.28 V to 5.61 V once the input is above 5.54 V to 5.83 V (datasheet values;
  R12 selects that level). The enable divider R9, R10 turns it on at
  2.92 V to 3.09 V and off at 2.67 V to 2.87 V at the connector (calculated).
  C4 sets the output ramp to 13 V/ms after a turn-on delay of about 0.25 ms
  (datasheet, typical).
- Damper: 2 × 22 µF behind 0.33 Ω (C9, C10, R20) and 1 µF at
  the output of that limiter, which is input 1 of the multiplexer.
- Limiter of the module input: the same part (U3) with a limit of 0.76 A,
  set by R13 (0.67 A to 0.85 A with the tolerances, calculated). It has the
  same enable thresholds, no ramp capacitor and a turn-on delay of about 0.08 ms
  (datasheet, typical). 1 µF and 100 kΩ (R17) are at its output, input 2 of
  the multiplexer; the resistor defines that node when the jumper is open.
- A Schottky diode lies across each limiter, anode on its output (D4,
  D3). When a cable is pulled it returns the charge behind the limiter, so
  that the output stays within 0.3 V of the input, which is the rating of the
  part (datasheet). It does so for the milliamperes of an unplug, not for an
  input that is shorted while the rail is charged.
- Multiplexer (candidate: TPS2116, U5) in priority mode: inputs rated 6 V
  absolute and 5.5 V in operation, reverse current 1 nA typical, soft start of
  1.7 ms after a delay of 1 ms (datasheet values). The divider R18, R19
  puts the priority threshold at 2.15 V to 2.59 V on input 1 (calculated), and
  C8 delays it by 0.19 ms. Its status output SRC_ST is open while USB-C
  supplies the rail and low while the input of the module does.
- Path from either connector to the 5 V rail: 0.126 Ω typical and 0.170 Ω at
  most (calculated from the datasheet on-resistances up to 85 °C; contacts and
  copper not counted). At 1.7 A the limiter dissipates 0.33 W and the
  multiplexer 0.16 W, a rise of 18 K each (calculated).
- Not reported to the controller: the limiters regulate the current in an
  overload and switch off only in thermal shutdown, with another attempt after
  cooling (datasheet). Their fault outputs are not connected; firmware learns of
  such an event through the 5 V rail and PWR_GOOD only.

Limits of the USB-C input:

- Supply range in operation: 4.5 V to 5.5 V at the connector, the range
  that the PPK2 states for its USB supply.
- A continuous input up to 10 V is tolerated: the limiter then regulates the
  rail at its clamp level and cycles thermally under load. From 11.1 V the
  suppressor conducts (datasheet value), and a source that delivers amperes
  destroys it.
- A source between 5.5 V and 5.83 V can reach the rail without being
  clamped in the worst unit. The charge pump of −4 V_A is rated for 5.8 V
  and the low-noise regulators for 6 V; the charge pump sits behind 2.2 Ω
  and 22 µF, which take the edges (section 16).
- Hot plug of a live cable: the connector node peaks at up to 11.4 V with
  a 5.25 V source and 12.2 V with 5.5 V, because the ceramic capacitor
  loses capacitance with voltage; the suppressor conducts for
  microseconds. Behind the limiter the voltage stays at 5.51 V or below
  and the rail never rises above the source (simulated with behavioral
  models of the parts).
- A contact that opens and closes again: the inputs of the multiplexer
  come within 25 mV to 85 mV of their 6 V rating in the worst simulated
  corners, with a 5.5 V source and a short cable. No rating is passed,
  but the margin is smaller than the uncertainty of the models. The
  module input has a position without parts for a second damper (R14,
  C5; D-84), to be fitted if the bench shows the need (section 16).
- In-rush on a computer port with the single cable: after the spike of the
  module itself the carrier draws 0.71 A to 0.87 A and the port stays at 4.94 V
  or above (simulated, port behind a 1 A switch). The charge drawn above 100 mA
  is 0.44 mC to 0.96 mC, of which the module alone draws 0.12 mC (simulated),
  more than the 50 µC of the USB in-rush test, which is not met.
- The boost converter has no under-voltage lock-out and no soft start
  (datasheet). On the module input the limiter delivers less than the converter
  asks for while its output charges; whether it starts cleanly there is an open
  check (section 16). A position without a part for a 3.08 V voltage detector at
  its enable pin (U9, D-84) is the remedy if it does not.

Thresholds of the 5 V rail, from the top:

| Level | What happens | Evidence |
| --- | --- | --- |
| 5.28 V to 5.61 V | Output of a limiter while it clamps a higher input | Datasheet |
| 5.50 V | Highest rail in operation | Supply range |
| 4.25 V | Firmware opens the output switch after 10 ms (F-14) | D-49 |
| 4.12 V | Highest release level of the supervisor | Calculated |
| 3.83 V to 4.00 V | Supervisor: 5V_OK low, supplies of the carrier off | Calculated |
| 2.92 V to 3.09 V | A limiter turns on (at its connector side) | Calculated |
| 2.67 V to 2.87 V | A limiter turns off | Calculated |
| 2.36 V to 2.58 V | Internal under-voltage lock-out of a limiter | Datasheet |
| 2.15 V to 2.59 V | The multiplexer leaves USB-C for the module input | Calculated |

The order is the design: the supervisor sheds the load first, while a
source in current limit can still recharge the rail through a limiter that
never turned off, and the multiplexer changes its input only after the
carrier has been off since 3.83 V. In an estimate of a load step beyond
what the source delivers (6.3 W on a source limited to 0.75 A to 1.6 A,
96 cases) the rail reaches a minimum of 2.99 V to 3.97 V, VSYS of the
module stays at 3.46 V or above and the controller is not reset.

Power budget (D-49). The curve of R-08 needs 4.3 W typical and 4.9 W with every
part at its limit on the 5 V rail: 0.99 A at 5.0 V and 1.16 A at 4.25 V. 5 V at
1 A, which typical parts deliver beyond that curve, needs 6.7 W to 7.6 W
(calculated, section 4.2). A default USB port does not deliver either, so the
budget follows the source. It is an input current through the carrier, which
firmware computes with a model of the input from the rail voltage and the output
that it reads (F-14):

| Source in use | CC voltage | Input current allowed | Hardware limit | At the output |
| --- | --- | --- | --- | --- |
| Input of the module | Any | 0.45 A | 0.67 A to 0.85 A | About 1.5 W (estimate) |
| USB-C, default port | Below 0.61 V | 0.45 A | 1.81 A to 2.17 A | About 1.5 W (estimate) |
| USB-C, 1.5 A | 0.70 V to 1.16 V | 1.4 A | 1.81 A to 2.17 A | The whole curve of R-08; 5 V at 1 A with typical parts and 5.0 V on the rail |
| USB-C, 3 A | 1.31 V to 2.04 V | 1.7 A | 1.81 A to 2.17 A | The whole curve of R-08; 5 V at 1 A while the rail is above 4.5 V |

- The two entries for 5 V at 1 A are calculated: 6.7 W at 5.0 V is
  1.34 A, and 7.6 W at 1.7 A is 4.47 V.
- With no USB-C source both CC voltages read near zero, and the budget is that
  of a default USB port. A budget above the default is granted only while USB-C
  supplies the rail, whatever CC reads (F-14).
- The firmware limit of the rail is 4.25 V. The charge pump of −4 V_A
  needs 4.19 V on the rail at its deepest set-point (calculated on
  typical curves, with 0.1 % feedback resistors; section 16). The limit
  is read through a divider of 1 % resistors, so a reading of 4.25 V is a
  rail of 4.20 V to 4.30 V before calibration (calculated).
- Compared with the PPK2: its user guide states a USB supply of 4.5 V to
  5.5 V and recommends a second supply that delivers 1 A or more when the
  DUT draws more than 400 mA. With 4.5 V at the USB-C connector this
  instrument delivers 5 V at 0.6 A with 4.34 V on the rail at the largest
  path resistance (calculated), which leaves 85 mV for contacts and
  copper. 5 V at 1 A needs about 4.53 V at the connector (calculated).

What firmware reads:

- CC1 and CC2 on two channels of the monitor converter, at 100 SPS. The class
  changes only after three consecutive samples in the same window, so a lower
  advertisement is followed within 60 ms; a reading above 2.04 V is invalid
  (F-13).
- The 5 V rail on one channel, whose scale also tells which input supplies the
  rail (D-80). The divider is R142 over R151; SRC_ST adds R143 in
  parallel with the lower resistor while the input of the module supplies. The
  channel reads 0.4545 × the rail on USB-C (1.93 V to 2.50 V for 4.25 V to 5.50
  V) and 0.2524 × the rail on the module input (1.07 V to 1.39 V); the threshold
  between the two is 1.67 V (calculated). A reading below it that would mean a
  rail above 5.7 V is inconsistent and is treated as a rail below the limit
  (F-11).
- PWR_GOOD (sections 3 and 4.11).
- The monitor converter runs from 3V3_A. While the supervisor holds the
  carrier off, firmware reads none of these channels and sees only
  PWR_GOOD low.

Enforcement:

- Firmware averages the input current of the budget and the rail voltage over 10
  ms. Above the budget, or with the 5 V rail below 4.25 V, it opens the output
  switch and reports a power-limit fault (F-14).
- Hardware, without firmware: the two limiters (0.76 A and 2.0 A) and the
  supervisor, which switches the supplies of the carrier and the pre-regulator
  off below 3.83 V to 4.00 V. The pre-regulator is off within 0.1 ms of the rail
  passing that level (estimate from typical datasheet delays). The carrier comes
  back 0.2 s to 0.45 s after the rail has recovered; the controller and the USB
  link stay up and report the loss of the carrier supply (F-7). Any dip of the
  rail below that level for more than about 30 µs has the same effect.
- Samples are marked as not valid for 5 ms when the input in use changes or the
  rail steps by more than 0.3 V (F-35).
- The USB configuration descriptor declares 500 mA (F-14).

When a cable is pulled or plugged:

- USB-C pulled, data cable in: the rail falls, the supervisor switches the
  carrier off and the DUT loses its supply. The multiplexer changes to the
  module input when the output of the USB-C limiter has decayed to 2.15 V to
  2.59 V, up to about 0.2 s later at idle (estimate). It does so without soft
  start, because the rail is above 1 V (datasheet); the recharge is a pulse of
  several amperes for some microseconds, until the limiter of the module input
  acts (simulated). The carrier restarts after the delay of the supervisor: the
  output is off for about 0.3 s to 0.7 s (estimate), or longer, because the
  priority input has no hysteresis. The controller keeps running throughout and
  reports the loss of PWR_GOOD.
- USB-C plugged while the module input supplies: the multiplexer opens the
  module input and closes USB-C when the rail has fallen to that input. The rail
  dips to 4.0 V to 4.5 V (simulated: 4.54 V with the typical ramp of the
  limiter, 4.28 V with the slowest ramp inside its datasheet limits, 4.02 V
  with a ramp slower still and a cold bulk capacitor), against a highest
  supervisor threshold of 4.00 V: the carrier keeps running, with little
  margin (section 16).
- Data cable pulled, USB-C in: nothing changes on the rail. The Pico 2
  stays supplied through its VSYS pin; the host link is lost.
- USB-C pulled, no data cable: the instrument is off. The VBUS pins of
  the connector follow the damper down through the diode D4 and are below
  0.8 V about 0.4 s after the unplug (estimate).
- A USB-C source that stands between about 3 V and 4.1 V keeps the
  instrument off although the computer port is good, because USB-C has
  priority from 2.59 V at most and the carrier needs up to 4.12 V. The
  remedy is to unplug it; firmware cannot read the cause.

For bring-up: test points on the USB-C input (TP1), on both inputs of the
multiplexer (TP2, TP4), on the 5 V rail (TP6), on SRC_ST (TP5)
and on 5V_OK (TP9). TP3 shows the current of the USB-C input, 0.297 V
per ampere behind 10 kΩ (calculated from the datasheet gain). With TP9 held
to ground only the 5 V rail and +13.5 V are up.

### 4.2 Source Meter Block (SMU)

- Main Regulator: LT3080 (candidate, U18; 1.1 A, low noise, output
  follows the SET pin down to 0 V). The MIC29302 is not suitable: its minimum
  output is about 1.24 V, above the 0.8 V requirement.
  - IN pin from the tracking pre-regulator (D-30, D-55); VCONTROL pin from
    the +13.5 V output of the boost converter, ahead of the +12 V_A
    regulator, so its load-dependent current stays off the clean rail
    (D-31). Feeding both pins from one rail 1.5 V above the output would
    dissipate 1.5 W, too much for the DFN package.
  - Dissipation on the current curve of R-08 (calculated; 40 °C ambient, 64 K/W
    to 68 K/W from the datasheet): highest at 0.8 V and 1.0 A, 0.82 W typical
    and 1.02 W worst case, junction 93 °C and 110 °C; lowest at 5.0 V and 0.6 A,
    0.34 W and 0.45 W.
  - Short circuit: the pre-regulator follows the collapsed output down to about
    0.8 V (simulated 0.84 V), so the regulator takes 1.5 W to 2.0 W with its
    control current counted (calculated) and not the full input voltage times
    its current limit. The over-current trip of section 4.4 opens the output
    switch. In a short that lasts ahead of that switch the regulator runs at its
    own thermal limit, which its datasheet allows for an indefinite time.
  - Clamps (D-57). The datasheet rates the IN pin and the VCONTROL pin at −0.3 V
    relative to the output. D11, a Schottky diode from the output to the IN
    pin, holds the IN pin 0.15 V to 0.18 V below the output while the
    pre-regulator is disabled and the output is alive (simulated). One diode of
    D10 sits in the VCONTROL feed behind R61 (10 Ω), with C47 (1 µF) at
    the pin: at power-off the capacitor keeps the pin at least 0.88 V above the
    output while the +13.5 V rail falls (simulated). D12, a Schottky diode
    from ground to the output, holds the output at about −0.2 V (estimate) in
    the states in which the minimum load would pull it below ground: VCONTROL
    absent while −4 V_A is present, or the SET pin driven below ground.
  - Minimum load: R69, 1.3 kΩ in 0805 from the regulator output to −4 V_A,
    draws 3.7 mA at 0.8 V and 6.9 mA at 5.0 V (calculated). The datasheet asks
    for 0.5 mA at 10 V and 1 mA at 25 V; the rest absorbs the leakage of D11,
    up to 2 mA at 100 °C (datasheet value), which flows into the output where
    the regulator cannot take it away. The resistor sits before the shunts, so
    it is not measured. Without −4 V_A a 0.8 V set-point gives 0.8 V with a
    typical regulator and 0.87 V to 1.17 V at the limits (calculated); PWR_GOOD
    watches that rail (section 4.11) and firmware opens the output on its loss
    (F-7).
  - Output capacitor at the regulator, before the shunts: C53, 22 µF (13.6 µF
    at 5 V, typical bias curve of the maker), with C54 (100 nF). It sets how
    fast a released output falls: 0.7 V/ms to 0.8 V/ms at 5 V (calculated), slow
    enough that the pre-regulator returns 0.12 W to 0.20 W to the 5 V rail for
    about 5 ms (simulated). That is less than the instrument takes from the rail
    in source mode without load (0.54 W to 0.60 W, estimate); the condition is
    0.25 W or more and is an open check of section 16. After the shunts keep the
    capacitance on VOUT at or below 100 nF (C0G, C71), because its charging
    current is measured as DUT current.
  - Noise: in source mode the noise of the regulator, divided by the shunt, is
    measured as current. In R0 that is 26 nA to 27 nA RMS at full bandwidth with
    a typical regulator, against about 2.1 nA from a quiet external supply in
    ampere mode (both simulated with typical datasheet figures). Section 11
    states the pass level of R-04 per mode (D-59).
- Pre-regulator: buck-boost converter (candidate: TPS63020, U16) from the 5 V
  rail with L2 (1.5 µH), in forced PWM at 2.4 MHz (datasheet value). The
  tracking is analog, with no firmware in the loop, and it follows the output of
  the linear regulator, not the set-point (D-55). A difference amplifier (U19
  with the 0.1 % resistors R63 to R68) drives the feedback pin
  with 0.200 × V_PRE + 0.146 × VREF − 0.191 × V_LDO, where V_LDO is the output
  of the linear regulator, and the converter holds that at its 0.5 V reference
  (calculated):

  ```text
  V_PRE = 0.672 V + 0.956 × V_LDO
  ```

  - Reason for following the output: the linear regulator cannot sink
    current. When the set-point falls with a light load, or a DUT holds the
    output up, the output stays high; a pre-regulator that followed the
    set-point would pull the IN pin volts below the output. With this law
    the IN pin stays at least 0.44 V above the output on a full-scale
    set-point step down (simulated).
  - Sense path: R65 (6.65 kΩ) and C55 (100 nF), with R64 (93.1 kΩ) as
    their load, are a low-pass of 0.62 ms (calculated), and one diode of
    D13 lies across R65. The pre-regulator therefore follows a rise of
    the output at once and a fall slowly. The slow fall keeps the
    converter from returning the charge of its output capacitors to the
    5 V rail when a short circuit empties the regulator output; the fast
    rise does the same when a charged DUT lifts the output.
  - Loop: C52 (10 pF) across the feedback resistor R63 gives the
    amplifier a phase margin of 73° to 77° (simulated with the model of its
    maker). The loop of the converter with this amplifier shows 55° or
    more (simulated with a behavioral model whose compensation is an
    assumption): a risk prototype settles it before the board is ordered
    (sections 13 and 16).
  - Range: the converter output covers 1.2 V to 5.5 V and its over-voltage
    protection starts between 5.5 V and 7 V (datasheet values). The law reaches
    5.5 V at an output of 5.05 V (calculated), which limits the set-point to
    5.0 V; firmware enforces 0.80 V to 5.00 V (F-30).
  - Output: C42, C45 and C50 (three times 22 µF, 38 µF left at 5.5 V by
    the typical bias curve) and the bleeder R62 (1 kΩ). A converter in
    forced PWM that is enabled with its output capacitors charged above
    its target returns that charge to the 5 V rail, and the input stage of
    section 4.1 cannot absorb it. The bleeder empties the capacitors in
    about 0.2 s after the converter is disabled (calculated; no rise of
    the 5 V rail after 100 ms off in simulation).
  - Filter toward the regulator: the ferrite bead FB1 (1.6 mΩ maximum,
    datasheet value), C46 (10 µF) and the damper C43 (22 µF) in series
    with R59 (0.33 Ω) at the IN pin. The source impedance at the IN pin is
    0.27 Ω to 0.37 Ω with the damper (simulated). The LDO rejects the remaining
    ripple. The copper from the converter capacitors to the bead is held to
    15 mΩ or less (section 10): every 10 mΩ more costs 6 mV of headroom at
    0.6 A.
- Enable: the enable pin of the pre-regulator has R53 (1 kΩ) to ground and is
  driven by the controller line SMU_ON through Q1, whose gate is the output
  5V_OK of the supervisor of section 4.1 (D-48). The converter runs only while
  the controller asks for it and the 5 V rail is valid, so a collapsing rail
  sheds the source without firmware. With the rail at 4.25 V the pin still
  reaches 2.36 V, and 1.96 V at the lowest supervisor threshold (calculated; the
  gate threshold of the transistor is an estimate), against a threshold of 1.2 V
  (datasheet value). After its hold-off of 180 ms to 420 ms (datasheet values)
  the supervisor enables the converter again if the controller still asks for
  it; the bleeder has emptied the capacitors by then. The linear regulator has
  no enable: with the pre-regulator off it runs from VCONTROL alone, follows the
  set-point and supplies only the milliamperes of its control path (simulated).
- Voltage Control (DAC): MCP4921-E/SN (U15, 12-bit, SPI) at gain 2, with its
  reference input in buffered mode on VREF / 2 = 1.25 V from the divider R55,
  R56 (2.00 kΩ, 0.1 %) (D-58). Its output spans 0 V to 2.5 V. A buffer
  amplifier with gain 2.1 (U17, R57, R58), powered from +12 V_A and
  −4 V_A, drives the SET pin through R60 (1 kΩ). The output is the SET drive
  plus about 10 mV, the SET pin current in that resistor (datasheet value):
  0.01 V to 5.26 V in 1.28 mV steps, nominal codes 616 for 0.80 V and 3893 for
  5.00 V (calculated).
  - Ceiling: the DAC cannot deliver more than twice its reference input,
    so no SPI frame can command more than 5.26 V nominal and 5.39 V at
    the tolerance limits (calculated); a wrong gain bit halves the output.
    The ceiling is below the 5.5 V that the level translator of
    section 4.8 accepts. The DAC and its reference run from 3V3_A and
    VREF, so the range does not depend on the 5 V rail.
  - Set-point filter: R54 (10 kΩ) with C41 (1 µF), 10 ms. After a
    full-scale step the set-point moves at 0.52 V/ms at most (calculated).
    A set-point step then makes the pre-regulator return at most 0.27 W
    to the 5 V rail for some milliseconds (calculated bound; 0.06 W
    simulated), and a DUT of up to 2300 µF cannot reach the over-current
    trip through a set-point step (calculated).
  - Temperature: the two resistor pairs R55, R56 and R57, R58 are
    25 ppm/K parts; if a pair drifts apart the output moves by up to 5 mV per
    pair at 5 V over 40 K (calculated). The parts of a pair are placed side by
    side. The set-point calibration uses nine points or more at room temperature
    (F-30).
  - After a hold-off of the supervisor the DAC wakes with a high-impedance
    output and C41 still holds 44 % to 70 % of the last value (calculated).
    Firmware writes the DAC before anything else when PWR_GOOD returns (F-3).
- Output current (R-08, D-56): 1.0 A up to 2.0 V, falling in a straight line to
  0.6 A at 5.0 V. The limit is the headroom at the IN pin: the converter ends at
  5.5 V, and the dropout of the regulator rises with the current. Its datasheet
  guarantees two points, 200 mV at 100 mA and 500 mV at 1.1 A; the need in
  between is taken on the straight line 170 mV + 0.300 Ω × I, which is an
  estimate. All other figures of the table are calculated; the margin counts
  every tolerance, 25 ppm/K over 40 K, and the line and load regulation of the
  converter.

| Output | Current of the curve | V_PRE, nominal | Headroom, nominal | Dropout need | Margin, worst case |
| --- | --- | --- | --- | --- | --- |
| 0.8 V | 1.00 A | 1.437 V | 637 mV | 470 mV | 85 mV |
| 2.0 V | 1.00 A | 2.584 V | 584 mV | 470 mV | 25 mV |
| 3.3 V | 0.83 A | 3.827 V | 527 mV | 418 mV | 15 mV |
| 5.0 V | 0.60 A | 5.452 V | 452 mV | 350 mV | 2 mV |

- Up to about 1.9 V the curve also holds against the guaranteed 500 mV
  (55 mV to spare at 0.8 V, 5 mV short at 2.0 V, calculated); above that
  it rests on the interpolation. The curve is therefore a design figure
  until the sweep of section 11 is done on several boards. A typical
  regulator delivers 1 A at every set-point with nominal headroom; with
  the lowest headroom it delivers 0.99 A at 5.0 V and 125 °C (calculated).
  The curve needs 4.3 W typical and 4.9 W at the limits from the 5 V rail,
  and 5 V at 1 A needs 6.7 W to 7.6 W (calculated; section 4.1 has the
  budget per source). The PPK2 states 600 mA in source mode and 5 W; the
  curve is at or above that at every voltage.
- Beyond the curve the regulator is in dropout and the output sags by 10 to 22
  times the missing headroom, up to 0.6 V, because the pre-regulator follows the
  sagging output (simulated: 4.48 V into 5 Ω at a 5.0 V set-point with a
  regulator at the guaranteed dropout, without oscillation). With a
  constant-power DUT the state feeds itself: the output collapses and restarts.
  Firmware reports an overload and opens the output switch when the VOUT monitor
  reads more than 0.3 V below an unchanged set-point for 20 ms (F-32).
- Voltage changes are ramped by firmware (default 1 V/ms). The protection
  against in-rush does not rest on that ramp: the set-point filter bounds the
  slope in hardware and the output switch closes with its own ramp. A set-point
  counts as settled when three consecutive monitor readings are inside the band
  (F-30), not after a fixed time: without load the output falls only as fast as
  the minimum load empties the output capacitor.
- Output sag: the regulator senses its own output, ahead of the shunts and
  switches, so the DUT sees up to 200 mV less at 1 A (R-06; 144 mV typical
  in source mode, calculated). A slow firmware loop (about 10 Hz, using
  the VOUT monitor) may trim the set-point; it is optional and off by
  default.
- Start and stop of the source (F-28 and F-29 of section 6.6). Start, with
  PWR_GOOD high, every switch open and SMU_ON low: DAC to the 0.80 V code;
  200 ms, in which the regulator runs from VCONTROL alone and brings the
  capacitors of the pre-regulator to its output voltage; SMU_ON high; 5 ms; DAC
  to the working value, 80 ms; range 3 and the source pair; after 60 ms the VOUT
  monitor within 100 mV of the set-point, else a fault; the output switch last.
  Stop: output switch, source pair, SMU_ON low, DAC to zero. SMU_ON never goes
  low while a path from the regulator to a DUT is closed.
- Mode switch: back-to-back N-MOSFET pairs select the LDO (source mode, Q4,
  Q8) or the VIN input (ampere mode, Q5, Q9); both off at reset. The
  text names each back-to-back pair by its function: the source pair and the
  ampere pair are the two mode switches, and the output pair is the output
  switch. Each pair closes as a source follower behind its gate network, 100 kΩ
  and 100 nF (D-61): the gate rises with 10.7 ms (calculated) and the supply
  node of the ladder with about 0.9 V/ms (simulated); a pair counts as closed
  40 ms after its request (F-24). It opens through a diode within 1 µs
  (simulated: the current is below 10 % after 0.1 µs to 0.3 µs), and a
  transistor at its gate holds it open while its common source is below ground.
  A transistor driven by the source-mode request holds the input of the ampere
  driver low, so both pairs can never be closed together (D-62).
  Break-before-make follows from the slow closing and the fast opening; firmware
  leaves 5 ms between lowering one request and raising either, and changes mode
  with the output switch open (F-23). Section 4.9 describes the gate networks
  and the interlock.
  - The gate lines are separate from the gate line of the output switch,
    so the selected pair closes without the output switch: the zero
    calibration then runs with the ladder at its real voltage and no load
    (D-29).
  - With the output switch open the supply node of the ladder keeps its voltage
    after a pair opens and falls with 0.57 s only (R90, 100 kΩ, with the
    5.7 µF of section 4.3; calculated). Closed onto a lower voltage, the ampere
    pair would push that charge into the supply of the user: 3.1 V on a 0.8 V
    supply with 4.7 µF (calculated). Firmware therefore raises the ampere
    request only when the VOUT monitor reads below the VIN monitor plus 0.1 V,
    or below 0.3 V, and reports a fault after 3 s without that (F-25).
- Output switch: back-to-back N-MOSFET pair at VOUT (Q15, Q16), off at
  reset, opened by hardware on a fault (D-71). It closes as a source follower
  behind R117 (2.2 MΩ) and C74 (10 nF): the output rises with 0.44 V/ms,
  falling to 0.21 V/ms near 5 V, and reaches 90 % after about 20 ms at 5.0 V; it
  starts to rise 6 ms to 7 ms after the request (simulated). That limits the
  in-rush in both modes, with the trip armed and no blanking: 0.39 A into
  1000 µF and 0.85 A into 2200 µF at 5 V, and about 2200 µF nominal is the
  largest DUT capacitance that starts without a trip (simulated); 1800 µF is the
  figure for a capacitor with a tolerance of 20 % (section 11). The output
  switch is the last switch to close and the first to open (F-23). It opens
  through one diode of D20 and R116 (220 Ω): the gate is below 2 V within
  7 µs (simulated), slowly enough for the pair to absorb the energy of the
  supply leads at a trip. After the turn-off the gate rests at a diode drop and
  decays with 31 ms (calculated), and a transistor with a low threshold passes
  microamperes meanwhile (simulated): readings with the output open are taken
  200 ms or more after it opened (F-36). R120 (10 Ω) at the gate pins damps
  the follower phase, and R115 (100 kΩ) on the driver side holds the gate low
  while the driver has no supply. No resistor goes from the gate to ground or to
  the common source: it would divide the gate voltage with the 2.2 MΩ.
  - For 250 ms after the switch closes the samples read low by the
    charging current of the gate (0.5 µA at 30 ms, 4 nA at 200 ms,
    simulated). The host marks these samples (sections 8 and 9).
- Slow monitors: an external 8-channel, 12-bit SPI converter (candidate:
  MCP3208, U40) on the SPI bus of the DAC, with VREF as its reference, reads
  eight channels at 100 SPS (D-80, F-10). The internal ADC of the controller is
  not used: an external converter is the more accurate one, has eight channels
  and shares the SPI bus of the DAC (section 5). All scale factors are
  calculated from the nominal resistor values.

| Channel | Signal | Scale at the converter |
| --- | --- | --- |
| 0 | Ladder output, buffered (VOUT monitor) | × 0.4545 |
| 1 | VIN, behind the fuse | × 1/44, for −20 V to +20 V at the terminal |
| 2 | 5 V rail, with the source tag | × 0.4545 on USB-C, × 0.2524 on the module input |
| 3, 4 | CC1, CC2 | × 1 behind 10 kΩ |
| 5 | Board temperature sensor U39, next to the LDO | × 1 behind 1 kΩ |
| 6 | +12 V_A | × 0.1754 |
| 7 | −4 V_A, against VREF | 0.333 × V + 1.667 V |

- The status output of the input multiplexer of section 4.1 switches a resistor
  into the divider of channel 2, so one channel reads the rail and tells which
  input supplies it: the bands are 1.93 V to 2.50 V with USB-C in use and 1.07 V
  to 1.39 V with the module input in use, and firmware separates them at 1.67 V
  (calculated; F-11).
- The VOUT channel has a source resistance of 54.5 kΩ and a filter of 5.5 ms
  (calculated); at 100 SPS the charge step of the converter costs 0.97 LSB,
  1.3 mV at VOUT, and at 1 kSPS 4.9 LSB (calculated). Rule F-33 for an external
  voltage on the source output (section 4.9) asks for a reaction within 0.5 ms.
  While the source output is on, firmware therefore reads this channel more
  often, as the exception of F-10 allows; those readings carry the larger error
  and serve the comparison with 5.3 V alone. The filter of 5.5 ms stays in front
  of them: the rule covers a voltage that rises slowly and not a step.

### 4.3 Shunt Ladder

Two shunts cannot cover seven decades: 10 mA in a 100 Ω shunt drops 1 V and
saturates a fixed-gain amplifier. Use four ranges, each limited to 100 mV,
with a fixed gain of 20 into a 2.5 V ADC full scale (23 % headroom: with the
gain of 19.93 and the pedestal of section 4.5 the converter reads full scale
at 122.9 mV across the shunt, calculated).

| Range | Shunt | Full scale | Resolution (1 LSB) | Switch up above | Switch down below |
| --- | --- | --- | --- | --- | --- |
| R0 | 1 kΩ | 100 µA | 1.9 nA | 91 µA | (lowest range) |
| R1 | 33 Ω | 3 mA | 60 nA | 2.85 mA | 60 µA |
| R2 | 1 Ω | 100 mA | 1.9 µA | 91 mA | 1.8 mA |
| R3 | 0.1 Ω | 1 A | 19 µA | 1.15 A (trip) | 60 mA |

The resolution and the switch-up levels are calculated from the gain, the
step-up threshold of 90.95 mV and the trip threshold of 115 mV (section
4.4). R0 stays in parallel with the active shunt: R1 measures with 31.95 Ω,
which the figures of its row include. The switch-down levels are firmware
thresholds.

- Shunt resistors (D-68), all candidates. R0 R101: 1 kΩ thin film, 0.1 %,
  25 ppm/°C, 0805. R1 R104: 33 Ω thin film, 0.1 %, 25 ppm/°C, 0805, rated
  0.1 W. R2 R107: 1 Ω thin film, 0.5 %, 25 ppm/°C, a two-terminal 1206
  chip on a four-pad Kelvin land pattern; each end cap bridges the force
  pad and the sense pad of its end. R3 R110: 0.1 Ω, 0.25 %, 50 ppm/°C, a
  four-terminal part with a single source. Tolerances and temperature
  coefficients are datasheet values.
  - The tolerance is removed by the per-range gain calibration (R-12,
    section 8); the temperature coefficient is what the error budget
    counts. For R3 that is 0.10 % over 20 K (calculated) plus 0.055 % of
    self-heating at 1 A (estimate).
  - The end caps of R2 are inside its measurement: about 0.1 % of 1 Ω with
    the drift of copper, about 4 ppm/°C of the range (estimate).
  - Dissipation (calculated): 23 mW in R2 at the jump level of 151 mV and
    0.14 W in R3 at 1.19 A, against ratings of 0.27 W and 0.5 W (datasheet
    values).
- Topology: parallel branches between the supply node and the node after
  the shunts, which the output switch connects to VOUT. Each switched
  branch is a MOSFET on the supply side followed by its shunt; the junction
  between them is the sense node. R0 has no switch and is always in
  circuit. The supply node has the test point TP33.
- Supply node: 1 µF C62 and a damped branch of 4.7 µF C63 in series
  with 0.47 Ω R87, ahead of the shunts (D-63). They take the current of
  the supply leads when the trip opens the output in ampere mode, so that
  the node stays below 11.5 V, under the +12 V_A supply of the multiplexer
  (simulated). Behind 0.5 µH to 1 µH of supply lead they also limit the sag
  of the node after a 500 mA step to 0.17 V to 0.21 V (simulated).
- Idle level: 100 kΩ R90 from the supply node to ground, the only resistor
  from that node to ground (D-63). With every path switch open the ladder
  rests at 0 V, below 0.3 V with every blocking MOSFET at its leakage limit
  (calculated), and the amplifier inputs have their bias return. The resistor
  is ahead of the shunts: its current, 50 µA at 5 V, is not measured; in
  ampere mode it comes from the external supply. Once the path switches are
  open the node falls with a time constant of 0.57 s (calculated); the rule
  for closing the ampere switch that follows from it is in section 4.2
  (F-25).
- Node after the shunts: it carries the 100 nF C0G capacitor C71 and
  the 10 kΩ resistor R114 into the buffer of D-32, and nothing resistive
  to another potential (section 4.2).
- One-hot selection: only one switched branch is on at a time. The current
  through R0 in parallel is then about 3 % in R1 and is part of the
  calibrated gain. A thermometer scheme (all lower branches on) is rejected:
  the current split would depend on the MOSFET on-resistance and drift with
  temperature.
- Make-before-break: when changing range the new branch turns on about 1 µs
  before the old one turns off, so the DUT is never left on R0 alone (F-17).
- Range switches: N-channel MOSFETs, Q12 for R1 and Q13 for R2 in
  SOT-23 and Q14 for R3 in a 3.3 mm power package (candidates). Switch
  and shunt of R3 together drop 105 mV to 107 mV at 1 A (calculated). The
  gates are driven from +12 V_A by the gate drivers U22 and U23
  through 47 Ω (R102, R105) and 10 Ω (R108); test points TP34 to
  TP36 are on the gates.
  - There are no gate-to-source resistors: on a branch that is off such a
    resistor would draw its current through a shunt. Each range gate has
    100 kΩ to ground instead (R103, R106, R109; D-67): it holds the switch
    open without a driver and draws its 120 µA from the driver, not through
    a shunt.
  - Each driver input has 1 kΩ in series at the driver (R96 to R99) and
    1 kΩ to ground on the controller side (R88, R89, R93, R94). The inputs are
    rated for the driver supply plus 0.3 V (datasheet value); the series
    resistor limits the current to 2.7 mA, 2.9 mA at the tolerance limits,
    when a line is high while +12 V_A is absent (calculated).
  - The IRLML6402 P-MOSFET driven by a GPIO does not work here: with the
    rail at 0.8 V there is no gate drive to turn it on, with the rail at
    5 V a 3.3 V GPIO cannot turn it off, and its 65 mΩ is comparable to
    the 0.1 Ω shunt.
- Kelvin sensing: the amplifier measures across the shunt element only. A
  low-leakage dual 4:1 analog multiplexer U24 (candidate: MUX509)
  selects both sense taps of the active shunt, the positive and the
  negative one (D-27). The switch resistance and the copper between the
  shunts therefore add burden but no measurement error.
  - Address 0 selects R0, sensed between the supply node and the node
    after the shunts; address 1 the sense node of R1 and the node after
    the shunts; addresses 2 and 3 the two Kelvin pads of R2 and of R3.
  - The multiplexer runs from +12 V_A and −4 V_A. Its enable input is
    pulled up to +12 V_A through 10 kΩ R113, so it never stands above its
    own supply (D-67); the multiplexer is therefore on whenever its rails
    are.
  - Each address input has 1 kΩ in series at the multiplexer (R112,
    R111) and 5.1 kΩ to ground on the controller side (R95, R91):
    range 0 is selected while the controller pins float or the sockets are
    empty (D-67).
  - The on-resistance at +12 V and −4 V is not in the datasheet, which gives
    125 Ω typical at ±15 V and 235 Ω typical, 340 Ω at most at 12 V
    (datasheet values). The simulations sweep 125 Ω to 430 Ω (estimate); the
    resistance sets the delay of the sense path (section 4.5).
- Ladder clamp (D-66): two MOSFETs of the type of the R1 switch in
  parallel, Q10 and Q11, each with its gate tied to its drain on the
  supply node through 22 Ω (R92, R100) and its source on the node
  after the shunts. They conduct when the ladder voltage passes their
  threshold: 1.3 V to 2.3 V at 25 µA (datasheet value), 2.5 V to 3.5 V at
  amperes (read from a typical curve). They carry the surge of a hot plug
  or a short circuit until range 3 conducts and bound the ladder at about
  4 V, so that the shunts stay inside their pulse ratings; below the
  threshold each is an off MOSFET like the range switches. Their body
  diodes carry the pulse when a charged DUT is connected to a lower output
  voltage.
  - Hot plug of 100 µF or a short circuit, worst delays (simulated): 8.8 A
    in each part, or 14.2 A in one part when their thresholds are at
    opposite limits, above 5 A for at most 0.54 µs, ladder at most 3.9 V.
    The pulsed rating is 21 A (datasheet value).
  - A capacitor charged to 5.0 V to 5.5 V connected to an output at 0.8 V:
    10.8 A to 12.5 A in each body diode for about 2 µs, against the same
    21 A. These figures are estimates: the simulation had less capacitance
    behind the source switch than the board.
  - R3 carries up to 27 A for microseconds in the same events, above the
    14.1 A and 20 A its datasheet gives for 10 ms. That is accepted on the
    energy, about 1 mJ against 200 mJ (calculated), and checked by the
    pulse series of section 11.
  - The two parts do not share a sustained current: one carries nearly all of
    it and would heat by 104 K at 3 A and by 144 K at 4 A in 5 ms
    (calculated). The clamp is a surge path only; section 4.4 has the rule
    that keeps a load current out of it (F-21).
  - The clamp is not part of the R-07 budget: with 470 nF or more at the
    DUT it never conducts on a load step (simulated).
- Leakage budget (D-66, D-59), in two parts, because the two kinds of
  leakage act differently:
  - Offset part: everything that loads VOUT or a sense node from another
    potential (multiplexer, amplifier bias current, guard buffer, terminal
    suppressor, output switch, gate oxide of the range switches). The
    design figure is 10 nA at 40 °C as a typical value; the sum of the
    typical figures is 4 nA to 6 nA at 40 °C and 5 V (estimate). No part on
    that node has a guaranteed leakage of this size, so each board is
    measured with the output on and the terminals open at 5.0 V, with a
    limit of 50 nA at room temperature, and the value is subtracted
    (section 8). The zero calibration removes the constant part; what
    stays is the drift.
  - Gain part: leakage across the ladder (drain to source of the three off
    range switches and of the two clamps, gate oxide of the clamps). It flows
    only with a burden voltage, is zero at zero current and acts as a
    resistance in parallel with the active shunt. The limit is 100 nA in
    total at 100 mV and 40 °C; no datasheet figure bounds the leakage of the
    five MOSFETs at this voltage (their limit is stated at 24 V), so the
    measurement of section 16 decides. At the limit the error is 0.1 % of
    reading at the full scale of R0 and at most 0.4 % at small currents
    (estimate); the gain calibration removes it at the calibration
    temperature. The clamp stays a candidate until the leakage of the whole
    ladder is on record (section 16).
  - Gate leakage of the range switches appears as an offset and is removed
    by the zero calibration.

### 4.4 Range Control Logic

Firmware is too slow to protect the DUT: samples arrive in DMA blocks with
milliseconds of latency. The range state lives in hardware.

- State: the range sequencer is a state machine in a PIO block of the
  controller (D-40). A PIO state machine executes one instruction in every
  cycle of the 150 MHz system clock, whatever the processors do, and its
  inputs pass a two-stage synchronizer (RP2350 datasheet). The sequencer
  holds the range, the blanking times, the make-before-break sequencing of
  the gates and the multiplexer address. Its programs are to be written, run
  in an emulator and measured on the controller in phase 3; none exists yet
  (section 6). Until firmware starts them, every pin of the controller is an
  input with a weak pull-down, and the resistors of section 4.3 keep every
  switch open and the multiplexer on range 0.
- Reaction time: the sequencer forces range 3 within 100 ns of an edge at the
  pin of the jump comparator (F-16). This is a requirement, because the R-07
  limit rests on it. By instruction count the reaction is 20 ns to 80 ns
  without the pad delays (estimate); phase 1 measures it.
- Comparators: three, U31 and U32, on the amplifier output divided
  by 4.01 (R136, R137), with thresholds from one resistor string on
  the reference, R132 to R135 (D-28). All six resistors are 0.1 %
  parts (D-74). Their outputs are active high, go to the controller and to
  the side data of section 4.7, and have the test points TP45 to
  TP47. Calculated from the resistor values, the tolerances and the
  10 mV offset limit of the comparators:

| Comparator | Threshold at its input | At the shunt | With tolerances |
| --- | --- | --- | --- |
| Step up | 0.464 V | 91 mV | 87.5 mV to 94.4 mV |
| Over-current | 0.584 V | 115 mV | 111.4 mV to 118.7 mV |
| Jump up | 0.764 V | 151 mV | 147.2 mV to 155.1 mV |

- Step up: the 91 mV comparator (91 % of full scale) moves the sequencer
  one range up, and a further step is allowed after the blanking time, so
  a slow rise climbs range by range.
- Jump up: the 151 mV comparator forces R3 at once. It is never blanked and
  acts in every state of the sequencer, also in a locked range. The new
  branch conducts 0.35 µs after the ladder voltage crosses the threshold,
  0.20 µs with the best and 0.51 µs with the worst delays (simulated, with
  a sequencer of 100 ns); the target is 0.55 µs at the most. The R-07 limit
  of 0.5 V corresponds to 0.77 µs with 1 µF at the DUT (calculated).
- Blanking: after every range change, up or down, the step-up comparator is
  ignored from the first change of a gate or address line until 2.0 µs (300
  clock cycles) after the last one (D-76, F-17). The time covers the old
  voltage that the comparators still see after the address changes, 0.6 µs to
  1.0 µs, and the pulse that the gate charge of the R3 switch causes on a
  step down, which reaches the lowest step-up threshold at 5.5 V with the
  fastest multiplexer (both simulated).
- Step down: only on a request from firmware to the sequencer, and only if
  the step-up comparator is not active. Firmware issues it when the current
  stays below the "switch down" threshold for N consecutive samples (N
  configurable, default 100). After a request it waits until the range bits
  change, or for a hold-off of four blocks, before it evaluates the rule
  again, so that one request never becomes two.
- Lock: firmware can hold a fixed range. The jump-up path, the over-current
  trip and the under-range rule below stay active even when locked. In a
  locked range a shunt voltage between 123 mV and 151 mV reads as full scale;
  such samples are flagged as over-range, by the full-scale code or by the
  jump bit of the same sample (F-35).
- Over-current: in R3 the 115 mV comparator means 1.15 A, 1.114 A to
  1.187 A with tolerances (D-74). The level lies below the full scale of
  the converter on every board, with 3.6 mV to spare in the worst case
  (calculated), so a trip is always preceded by valid samples. In the lower
  ranges the same level is only passed on the way up and is ignored.
  - Qualification: a state machine opens the output switch when the
    comparator has been high without interruption for 12 µs (1800 clock
    cycles) in R3, and keeps it open until firmware clears the fault (D-76).
    The time is a constant of the build, never below 10 µs and never above
    20 µs (F-18): the short-circuit figures of the output switch hold up to
    20 µs (simulated). It lets the recharge of the DUT capacitor after a step
    to 1.0 A pass, which holds the comparator high for up to 8.6 µs
    (simulated, 56 µF at the DUT, lowest threshold).
  - The trip is armed before the output switch closes and has no blanking
    window at DUT power on. The slow turn-on of the output switch (section
    4.2) keeps the in-rush below the trip level for a DUT of up to about
    2200 µF nominal (simulated), 1800 µF for a capacitor with a tolerance of
    20 %. After a trip, DUT power on is refused for 100 ms, and nothing
    closes the output again by itself: there is no automatic retry (F-19).
  - Ampere mode with long supply leads: the leads ring against the capacitor
    at the DUT, and a step to 1.0 A can hold the current above the trip level
    for 12 µs to 29 µs with 1 µH to 3 µH of leads and 10 µF to 100 µF at the
    DUT; the trip then acts. With 100 µF at the VIN terminals the longest
    time is 2.1 µs (all simulated). The trip can act on load steps above
    about 0.7 A; the user documentation asks for that capacitor with leads
    longer than about 0.5 m and load steps above 0.5 A (section 4.9).
  - With the output below 0.2 V the linear range of the amplifier near
    full scale is not established (section 4.5). Range 3 above 1 A, the
    trip level and the jump level are specified for output voltages of
    0.2 V or more.
- Reverse current (D-69): it is not measured; the PPK2 does not measure it
  either. The comparators see forward current only. While a mode switch is
  closed, a code below 650, half the pedestal, for 100 samples (a stored
  constant) is flagged as under-range. Firmware then selects R3 at once, at
  the latest 2 ms after the first such sample and also in a locked range, and
  issues no step-down request until 1 s after the flag clears (F-22). If the
  code stays below that level in R3 (more than about 13 mA backward) for
  100 ms, firmware opens the output switch, which blocks both ways, and
  reports a reverse-current fault. With R3 selected the reverse current flows
  through the channel of its switch, 105 mV per ampere (calculated); with the
  range gates low it flows through the body diodes of the range switches and
  of the ladder clamp.
- Sequencer not acting: if the jump comparator reads high while range 3 is
  not selected, firmware opens the output switch at most 2 ms after the first
  such reading and reports a fault (F-21). The ladder clamp then carries the
  load current, at 2.5 V to 2.9 V (inside the range of section 4.3). A
  full-scale code alone is not the criterion, because a locked range may
  sit there.
- Other faults: an over-voltage on VIN holds the ampere switch open in
  hardware (section 4.9, D-43); firmware opens the output switch on it and on
  the loss of PWR_GOOD (F-27, F-7). The comparators run from 3V3_A and read
  low without it, so they never step up or trip while that rail is missing;
  PWR_GOOD reports the rail (section 4.11).
- Reset state: every switch open, multiplexer on range 0, ladder at 0 V.
  Firmware drives no line of the ladder before PWR_GOOD is high (F-2, section
  4.11). It starts the sequencer and the trip and selects R3 before it closes
  a mode switch; the output switch closes last, and only through the
  sequencer, never by a plain write to its pin (F-20, F-23). A mode switch
  counts as closed 40 ms after its request (F-24, section 4.2).
- Without firmware. In reset, or with no program started, the pull-down
  resistors hold every switch open, and the over-voltage detector of VIN acts
  on its own. Once the state machines run, the step up, the jump up, the
  blanking and the over-current trip need no processor, as long as the analog
  rails are valid. The step down, the under-range rule, the check of the
  sequencer and the reaction to PWR_GOOD are firmware. A hung processor is
  bounded by the watchdog of the controller, 100 ms or less while a path is
  closed: the reset releases the pins and the pull-downs open every switch
  (D-81, F-8). For that case the ladder carries a reverse current of 1 A
  continuously and of 4 A for 100 ms (estimates).

### 4.5 Signal Chain

- Instrumentation Amplifier: AD8421 (candidate) U27 at G = 20. The gain
  resistor R123 is 523 Ω, 0.1 %, 25 ppm/°C, which gives G = 19.93
  (calculated from the gain equation of the datasheet). The amplifier
  itself settles within one sample period (10 µs) after a range change;
  the chain behind it does not, see the item on settling below. The INA188
  is too slow for this rate.
  - Supplies +12 V_A and −4 V_A, so the 0.8 V to 5 V common mode stays inside
    the input range. The negative rail is −4 V and not −5 V because an
    inverting charge pump cannot regulate −5 V from a USB supply that may
    sag (D-26).
  - Reference pin at +50 mV, the pedestal: a divider from the reference,
    49.9 kΩ R121 and 1.02 kΩ R122 with 1 µF C78, and the buffer
    U26; test point TP41. Zero current then reads about 1313 codes
    (calculated), so offset, noise and small reverse currents are not
    clipped. Codes below half the pedestal are treated as under-range
    (section 4.4).
  - The amplifier offset is larger than the 100 µV that 100 nA produces in
    R0, so per-range offset calibration is mandatory. The offset drifts by
    up to 0.7 µV/°C referred to the input, which is 0.7 nA/°C in R0
    (datasheet maxima, calculated), and the bias current of the inverting
    input, 2 nA at the most (datasheet value), flows in the shunt.
  - Near full scale with the output below about 0.2 V the input stage has
    little head room to the −4 V rail: two curves of the datasheet give
    different limits and the design sits between them. Until a bench
    result exists, range 3 above 1 A and the trip and jump levels are
    specified for output voltages of 0.2 V or more (section 16).
- Input filter (D-65): 220 pF C77 across the amplifier inputs and 22 pF
  from each input to ground (C76, C75), behind the multiplexer. With
  250 Ω of switch resistance the time constant is 0.12 µs, 0.06 µs to
  0.20 µs over 125 Ω to 430 Ω; the differential corner is 1.35 MHz and the
  common-mode corner 20 MHz (all calculated). The time constant is part of
  the delay of the up-range path, so the values are a compromise between
  that delay and the pulse a step down couples into the comparators
  (section 4.4). The two inputs are routed as a pair: with 22 pF the stray
  capacitance of the tracks counts.
- Limiter (D-73): the amplifier output can reach 10 V while a range change
  is in progress. A series resistor of 3.9 kΩ R125 and a low-leakage
  diode pair D22 to ground and to the driver rail limit the input of the
  ADC driver U29.
  - Driver rail VDRV: the driver and the cathode of the clamp are supplied
    from 1.091 × VREF by a buffer amplifier U28 on 3V3_A, with a gain set
    by 1 kΩ R127 and 11 kΩ R124, an input resistor of 10 kΩ R126 from
    the reference, and 10 Ω R129 into 100 nF C88. The buffer output is
    2.73 V; the rail at the test point TP42 is about 2.68 V after the
    drop in the 10 Ω (calculated). The 10 Ω is needed: with it the loop of
    the buffer has 54° of phase margin, without it the loop is unstable
    (simulated).
  - While the buffer is supplied the ADC input cannot pass VREF + 0.25 V
    (calculated bound; VREF + 0.20 V in the worst simulated case), against
    a rating of VREF + 0.3 V (datasheet value), and no current flows into
    the reference. The driver is linear up to 126.8 mV at the shunt
    (calculated), above the full scale of the converter.
  - During an over-range the ADC input stands at about VREF + 0.2 V: inside
    the absolute maximum, outside the operating range. The samples are
    flagged (section 4.4).
  - With 3V3_A off and +12 V_A on, as during every start, no path is closed
    and the amplifier output is at 0 V, so no clamp current flows. Two
    states are not bounded by construction and are bench items: 3V3_A
    between about 1 V and 2.2 V, below the supply range of the buffer, and
    an amplifier output held high while 3V3_A is off, which needs a failed
    part or a missing −4 V_A.
  - Power-off: +12 V_A stays above 3.6 V for about 10 ms after 3V3_A has
    fallen below 1 V (section 3). Firmware opens the output within 50 µs of
    the falling PWR_GOOD (F-7), 0.3 ms or more before 3V3_A reaches 2.2 V
    (estimate), so the amplifier output rests at the pedestal and no clamp
    current flows in that interval. If the output stays high, R125 limits
    the current into the driver rail to 2.3 mA and R136 the current into
    the clamp of the comparator inputs to 2.3 mA to 2.8 mA (calculated).
  - The buffer adds 4.8 mA to the load of 3V3_A, 5.3 mA at the most
    (datasheet values, calculated).
- Comparator inputs (D-76): the divider by 4.01 of section 4.4 and a diode
  pair D23 to 3V3_A and to ground keep the comparator inputs inside
  their rating of 1.0 V beyond the supply (datasheet value) while 3V3_A is
  off and the amplifier output is high. The node cannot pass 3V3_A + 0.95 V
  at 25 °C (calculated from the datasheet limit of the diode); the margin
  of 50 mV is gone near 0 °C, where a typical part still keeps about 0.2 V
  (estimate).
- Anti-alias filter: two poles at 40 kHz with Q = 0.74 around the ADC
  driver (calculated): 3.9 kΩ R125 and R128, 1.5 nF C85 and 680 pF
  C87, both C0G. The converter input has the network its datasheet
  requires, 22 Ω R130 and 10 nF C0G C90; test point TP43.
- Settling after a range change (D-76): the chain with its filter settles to
  0.1 % of full scale in about 45 µs and to 1 LSB in about 65 µs; over the
  simulated cases 37 µs to 50 µs and 64 µs to 70 µs. The long end contains
  5 µs of overload recovery of the amplifier, which its datasheet does not
  state (estimate). Seven samples are flagged as invalid after every change
  of the range bits (F-35), so the first valid sample is taken 70 µs to 80 µs
  after the change (sections 6.3 and 8). The host filters of the PPK2 do the
  same job after its range switches.
- Test points: amplifier output TP44, pedestal TP41, driver rail
  TP42, converter input TP43.

### 4.6 Data Acquisition (ADC)

- Main ADC: 16-bit single-ended SAR, at least 500 kSPS. Candidate: ADS8860
  U30 (the MCP33131D-10 is the differential 1 Msps version, and the
  ADS8326 tops out at 250 kSPS). Its analog supply is 3V3_A and its digital
  supply 3V3_C, each with 1 µF at the pin (C91, C92); the negative
  input is on ground at the part.
- Reference: 2.5 V precision reference (candidate: REF5025) U12. The
  set-point DAC takes half of it (section 4.2, D-58), so both scale
  together. The monitor converter, the comparator thresholds, the pedestal
  and the driver rail of section 4.5 use it too.
  - Supply of the reference (D-53): from 3V3_A through 10 Ω R31 and
    4.7 µF C20, with a Schottky diode D7 from its output to 3V3_A.
    Every receiver of the reference is supplied from 3V3_A; the reference
    then cannot be present without them, and its line stays at most a
    diode drop above that rail while the rail falls.
  - Capacitors on the reference line: at the reference 10 µF C26 behind
    1 Ω R35, and 1 µF C24 at its noise-reduction pin; at the REF pin
    of the ADC one 22 µF capacitor C89 behind 0.22 Ω R131 and no
    second, smaller capacitor (D-75). The datasheet of the converter asks
    for both: a series resistor of 0.1 Ω to 0.47 Ω and no additional small
    capacitor at that pin. The 22 µF part keeps about 14 µF at 2.5 V and
    10.8 µF in the worst case (estimates from the bias curve), against a
    minimum of 10 µF (datasheet value).
  - The 100 nF C113 at the monitor converter is on the same line. The
    reference is the star point of that line: the branch to the ADC and
    the branch to the monitor converter leave it there and share no track
    (section 10).
  - The reference is the lower limit of the range the converter accepts at
    its REF pin (section 16). The rail monitor reports a reference below
    about 2.25 V through PWR_GOOD (section 4.11).
- Interface mode: three-wire mode with the DIN pin tied to 3V3_C. The
  rising edge of the convert-start line is the sampling instant; the result
  is shifted out by 16 clock cycles while that line is still high.
- Digital lines (D-75): 220 Ω in each of the three lines at the converter,
  RN5: convert-start, clock and data. The clock and the convert-start
  line have 47 Ω at the controller as well (RN4) and 4.7 kΩ to ground
  (RN3), which holds them low while the controller pins float
  (section 4.11).
  - The resistors damp the edges, and they limit the current into the
    converter when its digital supply is absent and a line is high: 6 mA to
    10 mA peak with nominal values and the output resistance of the pad, up
    to 11.3 mA at the tolerance limits (calculated). The pins are rated for
    0.3 V beyond the supply and the datasheet gives no current figure, so
    this is a mitigation and not a rating that is kept; firmware releases the
    lines when PWR_GOOD falls (F-7, section 4.11).
  - Cost in timing: about 1 ns on the two inputs and about 3 ns on the
    data line (estimates).
- Conversion timing: a PIO state machine of the controller makes the
  convert-start pulse and the 16 clock pulses of every sample from the system
  clock (D-40), never an interrupt handler. Sampling jitter then does not
  depend on firmware. What the converter fixes (datasheet values):
  convert-start high for at least 710 ns, which is 108 cycles of the system
  clock, and still high at the end of the conversion; then 16 clock cycles;
  at least 20 ns of quiet, 4 cycles, before the next rising edge. Rule F-34
  holds these figures for the program.
- Clocking: at 100 kSPS a sample period is 1500 cycles of the 150 MHz system
  clock. Keep the clock divider of the state machine an integer; a fractional
  divider adds sampling jitter. The shift clock takes 16 or more system clock
  cycles per bit at 100 kSPS, 9.375 MHz or less, and is 15 MHz at the most:
  converter data and side data (section 4.7) are read in one window, which is
  36.9 ns wide at 9.375 MHz and 16.9 ns at 15 MHz (calculated from the
  datasheet delays; the 4 ns of the 220 Ω in the data line are an estimate).
- Oversampling option: 500 kSPS (300 cycles per sample, still an integer)
  decimated by 5 in firmware, with 10 system clock cycles per bit, 15 MHz. It
  improves noise and relaxes the anti-alias filter. Phase 1 records the noise
  of the converter and the CPU load at both rates; the decision is taken at
  the end of phase 2, with the noise of the whole chain (section 13).

### 4.7 Synchronous Side Data

- Two 8-bit parallel-load shift registers (candidate: SN74LV165A), U33
  and U34, are loaded by a pulse at the convert-start edge and shifted
  by the clock of the converter (D-41). They carry the 2 range bits (the
  multiplexer address), the state of the output switch, the over-voltage
  detector, the three comparators, PWR_GOOD and the 8 digital inputs.
- Capture: the state machine that clocks the converter reads the data pin of
  the converter and the data pin of the registers at the same instants, two
  bits per clock. One 32-bit word per sample then holds the conversion result
  and its 16 side bits, and the two cannot lose alignment.
- Firmware separates the two bit streams when it builds the sample word of
  section 7.3.
- Chain: the serial output of U33 feeds the serial input of U34,
  and the output of U34 reaches GP17 through R138, 33 Ω. The serial
  input of U33 is tied to 3V3_C and both clock-inhibit pins to ground.
  The registers run from 3V3_C, with C98 and C99 at their supply
  pins.

The registers put the highest input of U34 on the data line first. The
order of the 16 side bits of a sample is therefore:

| Bit | Register input | Signal | Meaning of a 1 |
| --- | --- | --- | --- |
| 1 (first) | U34 D7 | MUX_A1 | Range, bit 1 |
| 2 | U34 D6 | MUX_A0 | Range, bit 0 |
| 3 | U34 D5 | GATE_OUT | Output switch requested on |
| 4 | U34 D4 | VIN_OV | VIN above the over-voltage level |
| 5 | U34 D3 | CMP_OC | Amplifier output above the over-current level |
| 6 | U34 D2 | CMP_JUMP | Amplifier output above the jump-up level |
| 7 | U34 D1 | CMP_UP | Amplifier output above the step-up level |
| 8 | U34 D0 | PWR_GOOD | Carrier rails present |
| 9 to 16 | U33 D7 to D0 | DIN7 to DIN0 | Logic inputs D7 down to D0 |

- Range bits and output bit: the three lines are tapped at the controller
  side of the 1 kΩ series resistors of the multiplexer and of the gate
  driver (section 5). They report what the range sequencer commands, not
  what the switches have done: the multiplexer follows within its
  switching time, and the DUT voltage starts to rise 6 ms to 7 ms after
  the output bit (simulated, D-71). With the pins of the controller
  released the pull-downs R95, R91 and R93 make the three bits
  read 0: range 0, output off.
- Comparator bits: the push-pull outputs of U31 and U32, powered
  from 3V3_A, go straight to the registers and to GP8 to GP10. They show
  the comparators at the load instant of the sample, so a sample whose
  jump-up bit is set is over-range whatever its code says (rule F-35).
- VIN_OV: the register reads the output of the detector U21 on the
  interlock node itself, ahead of the 4.7 kΩ resistor R1 that leads to
  GP11 (D-78). No state of the controller pin can falsify the bit: behind
  the resistor a pin moves the node by 0.14 V at the most (calculated).
- PWR_GOOD is the wired AND of four open-drain comparators in U14
  (candidate: MCP6569), pulled up to 3V3_C through R51, 1.5 kΩ, with
  R52, 6.8 kΩ, to ground (D-54). It is low while 3V3_A is below 2.97 V,
  +12 V_A below 9.85 V, −4 V_A above −2.57 V or the reference below
  2.245 V, while 3V3_C is absent, and while the supervisor of the 5 V rail
  holds the carrier off (section 4.11). The thresholds are fractions of
  3V3_C set by 1 % resistors (calculated; 2.89 V to 3.05 V, 9.25 V to
  10.48 V, −2.86 V to −2.29 V and 2.14 V to 2.35 V at the tolerance
  limits). The flag reports that the rails are present, not that they are
  in tolerance, and it cannot see a 3V3_C that stands low: firmware checks
  the rails on the monitor converter (rule F-12). C32, C33 and
  C34 at the comparator inputs keep an edge of the flag from moving its
  own thresholds (simulated with an estimated pin capacitance).
- Levels of PWR_GOOD: the divider puts the high level at 0.82 of 3V3_C at
  the register, and at 0.79 with the pad pull-down of GP28 on, against the
  0.7 that the register needs (calculated; datasheet). The controller
  reads the flag through R4, 1 kΩ: 2.50 V at the pin at the low limit
  of the rail (calculated). The same resistor limits a pin driven by
  mistake to 3.3 mA, against 25 mA at the comparator outputs (datasheet).
  R4 and R52 together are 7.8 kΩ from the pad to ground, under the
  8.2 kΩ that erratum E9 of RP2350 stepping A2 asks for; R52 must not
  be raised. TP17 is the test point of the flag.
- Logic inputs: the eight lines come from the 3.3 V side of the level
  translator (section 4.8). RN6 and RN7, 100 kΩ to ground, hold
  them low while the DUT side of the translator has no supply.
- Clock and load: both registers take the converter clock behind its 47 Ω
  element of RN4 and ahead of the 220 Ω resistors of the converter
  (section 4.6), and the load pulse through another element of RN4,
  with no further resistor. The load input is active low and is pulsed
  low for three cycles of the system clock or longer; with the pins
  released its pull-down keeps the registers loading, which harms
  nothing. The shift clock has 16 or more system clock cycles per bit at
  100 kSPS (9.375 MHz or less) and 10 cycles per bit (15 MHz) for the
  500 kSPS option. At 15 MHz the common sampling window of converter data
  and side data is 16.9 ns, against two system clock cycles of 13.3 ns;
  at 9.375 MHz it is 36.9 ns (calculated from the propagation delay of
  the register, 18 ns at the most, and the data delay of the converter,
  datasheet values; the 4 ns of the 220 Ω in the data line are an
  estimate).

### 4.8 Digital Inputs

- 8 logic channels, D0 to D7, through a level translator U38
  (candidate: SN74LVC8T245) whose DUT-side supply is a buffered copy of
  the ladder output, so they follow the DUT logic level from 1.65 V to
  5.5 V. The buffer U25, an amplifier with picoampere input current,
  senses the ladder ahead of the output switch (D-32).
- Translator supply (D-72): it comes from the output of that buffer
  through its own resistor R118, 1 kΩ, and is clamped by the dual
  Schottky diode D24 (candidate: BAT54S) to ground and to the 5 V
  rail. The buffer runs from +12 V_A and −4 V_A and can stand at either
  rail; the supply pin of the translator then stays between −0.40 V and
  the 5 V rail plus 0.4 V (simulated at 0 °C and at 27 °C), 6.0 V at the
  most with the 5 V rail at the upper end of its clamp (calculated),
  inside the −0.5 V and 6.5 V of the part (datasheet). The 1 kΩ must not
  be lowered: 470 Ω gives −0.44 V at 0 °C (simulated). The supply current
  comes from the buffer and not from the DUT, and it does not flow in the
  resistor that feeds the guard and the monitor.
- The translator supply is a soft copy of the output voltage. At rest it
  sits up to 10 mV below it (8 µA of the translator and the leakage of the
  clamp in 1 kΩ, calculated), and C100, 100 nF, gives it a time
  constant of 100 µs. Switching inputs draw more: eight lines at 1 MHz
  lower it by about 30 mV at 1.8 V and 120 mV at 5 V, eight lines at
  10 MHz by 0.3 V and 1.2 V (calculated from the typical power-dissipation
  capacitance of the datasheet). Signals that fast are not resolved at
  100 kSPS in any case.
- With the jumper as built the logic channels are valid for an output
  voltage of 1.67 V or more (R-10 asks for 1.65 V at the supply of the
  translator, the figure of the part and of the logic port of the PPK2).
  Below that the bits are not specified, and below 0.1 V on the supply the
  translator switches its outputs off (datasheet) and all eight bits read
  0. No controller pin is free to blank the bits in hardware: the host
  marks the logic channels invalid while the monitored output voltage is
  below 1.67 V.
- The control pins of the translator are referenced to its 3.3 V side, so
  they stay valid while the DUT supply is off (D-33). Direction and enable
  are tied to ground: the DUT side is always the input. The 3.3 V side
  runs from 3V3_C, with C101 at its pin.
- Series resistors and ESD protection on every pin of the port, the VCC
  pin included (D-50, D-79). Seen from the connector, each logic line
  meets one channel of an ESD array (candidate: TPD4E1U06; U36 for D0
  to D3, U37 for D4 to D7), then 330 Ω in series (RN8,
  RN9), then a 470 kΩ pull-down (RN11, RN10) at the pin of
  the translator. The VCC pin has one channel of a third array, U35.
- Load on the DUT: a channel held high loads the DUT with its voltage
  across 470 kΩ, which is 3.5 µA at 1.65 V, 7.0 µA at 3.3 V and 10.6 µA
  at 5.0 V (calculated), plus the leakage of its ESD channel: 1 nA
  typical and 10 nA at the most at 2.5 V; between 2.5 V and 5.5 V the
  datasheet gives no closer bound than 10 µA at 5.5 V, so the figure at
  5 V is an open check of section 16. This is real DUT current and is
  measured.
- An unconnected channel reads 0 for a pin leakage of up to 1 µA, the
  limit of the translator at 25 °C: 0.47 V against a low threshold of
  0.58 V at 1.65 V (calculated; datasheet). At the 2 µA limit of its full
  temperature range that holds only for a translator supply of 4.5 V or
  more. Channels that are not used are switched off in the host.
- Edges: 330 Ω with the 10 pF of a translator pin shapes a clean edge to
  2.6 ns/V to 3.3 ns/V at 5 V, 4.0 ns/V to 5.0 ns/V at 3.3 V and 7.3 ns/V
  to 9.2 ns/V at 1.8 V (calculated), inside the 5 ns/V, 10 ns/V and
  20 ns/V that the translator allows (datasheet). A DUT edge slower than
  those limits is outside the recommended conditions and can show as
  several transitions.
- ESD: the arrays are rated for contact discharges of 15 kV (datasheet).
  What an 8 kV contact discharge leaves behind an array reaches the
  translator through 330 Ω: about 50 mA to 95 mA for tens of nanoseconds
  (estimate).
- The same buffer drives the guard ring of section 10 and the VOUT channel
  of the monitor, through R119, 47 Ω. TP40 is the test point of the
  guard and TP48 that of the translator supply.
- Logic port J5: a 1×10 pin header in the pin order of the PPK2: VCC,
  GND, D7 down to D0 (D-44). The solder jumper JP2 selects the supply
  of the DUT side of the translator. Position 1-2, as built: the clamped
  copy of the ladder output. Position 2-3: the VCC pin of the port,
  through R139, 100 Ω, for a DUT whose logic runs on another voltage
  than its supply. The bridge 1-2 is cut before 2-3 is closed; with both
  closed the rail of the DUT is tied to the clamp.
- The VCC pin is not needed in position 1-2. When it is wired it loads the
  DUT with the leakage of its ESD channel; in position 2-3 it also
  supplies the translator (8 µA at rest, more with switching inputs). It
  takes 5.5 V at the most: in position 2-3 nothing clamps the supply pin
  of the translator below its 6.5 V rating.
- Pull-down resistors hold the eight lines at the shift register while the
  DUT side of the translator has no supply (section 4.7).

### 4.9 Protection & Grounding

- VIN (D-60, D-43): the instrument works with 0.8 V to 5.0 V on VIN (R-09), and
  the ampere switch itself is the protection. While it is open (no request, a
  request refused by hardware, source mode running, instrument without supply)
  the terminal withstands −20 V to +20 V for any time: both transistors of the
  pair block, a transistor at their gates keeps them off while the terminal is
  below ground, and less than 1 mA flows (simulated: 0.64 mA at −20 V, 0.19 mA
  at +20 V). Nothing has to be replaced afterward. The transistors are rated
  30 V (datasheet value) and see 20 V; with source mode running at its ceiling
  and a reversed 20 V supply the transistor on the ladder side sees 25.3 V
  (calculated), and for tens of nanoseconds at the plug-in edge its 30 V rating
  (simulated).
  - Suppressor and fuse: D14, a 20 V bidirectional suppressor behind the fuse
    F1 (4 A, fast), takes hot-plug rings, discharges and the energy of the
    supply leads when the over-current trip opens the output. It conducts from
    22.2 V (datasheet value). The fuse cannot protect it: above 22 V the
    suppressor is lost first, and the fuse only ends the current of a suppressor
    that has failed short. A 24 V supply therefore destroys the suppressor; the
    marking at the terminal and the user documentation say 20 V at most.
  - Over-voltage detector: U21 compares VIN, divided by R73 (115 kΩ) and
    R74 (100 kΩ), with VREF; R76 (3.3 MΩ) gives the hysteresis and C58
    (1 nF) the filter. It trips at 5.46 V (5.41 V to 5.51 V) and releases at
    5.35 V (5.30 V to 5.40 V), both calculated with the tolerances of the
    resistors, of the reference and of the comparator; it is not latched. Its
    output drives Q3, which pulls the input of the gate driver low, so the
    switch stays open above the threshold whatever the controller asks. The
    controller reads the output through R1 (4.7 kΩ), so that no state of its
    pin can move the interlock node (D-78), and reports the fault (F-27); the
    side data of section 4.7 carry it as well. D15 clamps the detector input
    to 3V3_A and to ground: the clamp current is 0.17 mA at 20 V (calculated),
    and the detector survives the fault it reports, with and without its supply.
    Without 3V3_A it reports nothing; PWR_GOOD covers that rail.
  - While the switch is closed the supply has to stay between 0.8 V and 5.0 V;
    no part protects the DUT from a supply that jumps out of that range. The
    detector opens the switch 4 µs to 45 µs after the terminal passes the
    threshold. A reversal opens it through the transistor at the gates within
    5 µs to 35 µs from 5 V, within 2 ms from 1.5 V, and near 1 V possibly not at
    all. What arrives in that time reaches the DUT: 9.2 V for a supply that
    steps to 20 V in 1 µs and −2.4 V for one that steps to −20 V (all
    simulated). Firmware closes the switch only while the detector is low and
    the VIN monitor has read 0.6 V to 5.4 V for 100 ms (a true 0.8 V can read
    0.67 V before calibration, calculated), opens it within 20 ms when the
    monitor reads below 0.6 V, and reports the fault as "over-voltage" or "out
    of range" (F-26).
  - The instrument takes 35 µA from a 5 V supply on VIN while the switch
    is open (the detector and monitor dividers, calculated) and about
    125 µA while it is closed (simulated). This current flows ahead of
    the shunts and is not part of the reading.
  - A load that steps above 0.5 A behind supply leads longer than about 0.5 m
    needs 100 µF across the VIN terminals; the user documentation says so. The
    capacitor keeps the dip of the supply small and keeps the leads from holding
    the current above the trip level for longer than the trip waits (2.1 µs with
    100 µF, simulated; section 4.4). The board carries none: it would ring to
    twice the voltage at every hot plug of the supply and load a battery with
    its leakage.
- Mode switches (D-61, D-62): each pair has the same gate network; the
  parts of the ampere pair are named, those of the source pair are
  R78, C60, R81, D16, R77, R83, Q6, R85 and
  D18.
  - Closing: the driver U20 charges the gate through R80 (100 kΩ),
    and C61 (100 nF) with R82 (6.8 kΩ) to ground sets the ramp:
    10.7 ms, with a first step of 0.76 V, below the lowest threshold of
    the transistors (calculated). The pair closes as a source follower,
    so the supply node of the ladder does not ring when a pair closes on
    a live supply (simulated: 5.00 V and no current in the ladder clamp).
    R84 (2.2 MΩ) from gate to common source leaves 95.7 % of the
    drive, at least 6.2 V of gate-source voltage (calculated).
  - Opening: one diode of D17 and R79 (22 Ω) discharge the gate into the
    driver. The turn-off diode is a low-leakage type: a Schottky diode would
    leak as much as the ramp charges with. A closure that follows an opening
    within about 3 ms is not fully ramped; the 5 ms dead time of firmware (F-23)
    covers it.
  - Bound: the second diode of D17 ties the gate to +12 V_A. A
    follower cannot lift its source above its gate, so the kick of the
    supply leads at a trip leaves the supply node 0.5 V or more below
    the +12 V_A supply of the multiplexer, with the damper of section 4.3
    and the suppressor on VIN (simulated).
  - Hold-off below ground: Q7, with its base on R86 (100 kΩ) to ground
    and D19 across base and emitter, joins gate and common source as soon as
    the common source is 0.6 V to 0.7 V below ground (datasheet value of the
    base-emitter voltage). A reversed VIN or a negative regulator output cannot
    turn an open pair on.
  - Interlock: Q2, driven by the source-mode request, pulls the input of the
    ampere driver low, the same node on which Q3 acts. With both requests
    high the source pair is closed and VIN stays isolated (simulated: no time
    with both pairs conducting, also with no dead time). R72 (1 kΩ) decouples
    the controller pin from that node, R71 (4.7 kΩ) and R70 (1 kΩ) hold
    the two requests low while the controller pins float, and R75 (1 kΩ)
    limits the current into the driver input to 2.7 mA, 2.9 mA at the tolerance
    limits, when +12 V_A is absent (calculated).
  - Limits: the output of the driver below 4.5 V of supply is not specified in
    its datasheet (open check of section 16), and the interlock assumes a
    request at a logic level.
- VOUT (D-70): one unidirectional suppressor, D21 (15 V stand-off, 1 nA
  typical and 0.1 µA maximum at 15 V and 25 °C, datasheet values), from VOUT to
  ground, at the VOUT pole of the terminal block J4: 4.3 mm from pad edge to
  pad edge (calculated, section 10.4). Anything with more leakage would be
  measured as DUT current; there is no clamp near the working voltage. Its
  leakage at 5 V and at 40 °C to 50 °C is in no datasheet (2.8 nA typical at
  40 °C is an estimate) and is an open check of section 16: the guaranteed
  figure equals the resolution of R-04.
  - At a trip the suppressor carries the current of the DUT cable in the forward
    direction: at most 11.6 A against a surge rating of 50 A (simulated;
    datasheet value), and the terminal goes to −0.8 V to −1.7 V for microseconds
    (simulated with an assumed forward curve).
  - Output off: the terminal withstands −0.8 V from a source limited to 0.5 A,
    and +15 V. A positive strike beyond that ends in the avalanche rating of the
    output transistor (39 mJ, datasheet value). A stiff reversed source destroys
    the suppressor: VOUT has no reverse-polarity protection.
  - Output on: VOUT must not be driven above the set voltage. No part bounds it
    below 16.7 V, the lowest breakdown voltage of the suppressor (datasheet
    value).
  - Output switch (D-71): its slow closing limits the in-rush and its
    opening through 220 Ω lets the pair absorb the energy of the supply
    leads (section 4.2). R115 holds its gate low without supply.
- Source output (D-57): a DUT that holds VOUT above the set-point is tolerated.
  The pre-regulator follows the output, D11 clamps the input of the
  regulator, and firmware brings the set-point to 0.2 V below the measured
  voltage within 100 ms and follows it down (F-31). The instrument then draws
  about 11 mA from the DUT, up to 14 mA warm, ahead of the shunts and so
  unmeasured (calculated).
  - A charged DUT must not be plugged into a live output: connect and disconnect
    with the output off. Plugged in live, it sends 3 A to 17 A through D11
    for microseconds and takes the input of the regulator 0.32 V to 0.94 V below
    its output for 3 µs to 21 µs, outside the −0.3 V of the datasheet
    (simulated). Switched on in the order of section 4.2, the same DUT meets the
    ramp of the output switch and gives 14 mA (simulated).
  - External voltage: above about 5.7 V a voltage on the terminal reaches the
    output of the pre-regulator through D11. The over-voltage level of that
    converter lies between 5.5 V and 7 V and the absolute maximum of its output
    pin is 7 V (datasheet values); no part cuts the voltage off. Firmware opens
    the output switch within 0.5 ms of the VOUT monitor crossing 5.3 V (F-33).
    The monitor sees the terminal through a filter of 5.5 ms: the rule covers a
    voltage that rises slowly, not a step (section 4.2). The user documentation
    states 5.5 V as the limit for a voltage applied to VOUT in source mode.
- Reverse current (D-69): a current from VOUT into the instrument passes the
  body diodes of the range switches and of the ladder clamps. It is not
  measured; the PPK2 does not measure it either. Firmware flags the samples,
  selects range 3 within 2 ms, in which the range switch conducts both ways, and
  opens the output switch, which blocks both ways, after 100 ms (F-22). The
  watchdog of the controller (D-81, F-8) bounds a hung controller to 100 ms.
  Without firmware the parts carry 1 A continuously and 4 A for 100 ms
  (estimates).
- Ladder clamp: when the clamp of section 4.3 conducts and the range logic does
  not act, firmware opens the output switch at most 2 ms later (F-21). The two
  clamp transistors do not share the current: one carries nearly all of it and
  would heat by 104 K at 3 A and by 144 K at 4 A in 5 ms (calculated).
- Instrument without supply: every switch is open, because the gate drivers have
  no supply and resistors hold the gates low. VIN withstands −20 V to +20 V as
  above, and a 5 V supply left on it gives about 49 µA: the clamp D15 of the
  detector then conducts into the dead 3V3_A (calculated). A live DUT on VOUT is
  loaded with about 1 nA typical; the sum of the datasheet maxima of the
  suppressor and of the output transistor is 1.1 µA. The controller has supply
  whenever the 5 V rail has (section 4.11), so a powered carrier never meets an
  unpowered module; section 4.8 describes the logic port.
- ESD protection on the terminals a user touches in operation (D-50):

| Terminal | Part | Rating |
| --- | --- | --- |
| VOUT, on J3 and J4 | D21 | 30 kV contact (datasheet value) |
| VIN, on J3 and J4 | D14 | 400 W suppressor; its datasheet states no ESD rating |
| Logic port J5, D0 to D7 | U36, U37 | ESD arrays (candidate: TPD4E1U06; section 4.8) |
| Logic port J5, VCC | U35 | ESD array of the same type |
| USB-C, VBUS | D2 | 400 W suppressor (section 4.1) |
| USB-C, CC1 and CC2 | U2 | ESD array of the same type |
| USB connector of the Pico 2 | On the module | As the module is built |

- The console header J1 and the reset button SW1 are service
  points without protection parts.
- Inside the instrument the inputs of the range comparators have a diode
  pair to 3V3_A and ground (D23, D-76), as the detector input has.
- Thermal: firmware opens the output above a limit of the board temperature
  sensor next to the LDO (F-15); the limit comes from a measurement on the first
  board. The watchdog covers a firmware that stops. The regulators keep their
  own thermal limits.
- The DUT ground is the USB ground: there is no galvanic isolation. State
  this in the documentation and recommend a USB isolator when the DUT is also
  grounded elsewhere.

### 4.10 Error & Noise Budget (Estimates)

Estimated from typical datasheet figures at G = 19.93 and 50 kHz bandwidth:
amplifier about 1.2 µV RMS referred to input, ADC about 1.0 µV RMS, R0
thermal noise about 1.1 µV RMS. A simulation of the chain of section 4.5
with its filter gives about 2.1 µV RMS at the shunt, which is the figure of
the table. Every value of this section is a datasheet value, a calculation,
a simulation or an estimate, as stated; all are to be replaced by
measurements in phase 2.

| Range | Noise of the chain (RMS, full bandwidth) | Offset drift at the datasheet limits, input stage alone / with the output stage | Dominant gain error |
| --- | --- | --- | --- |
| R0 | About 2.1 nA | About 0.4 nA/°C / 0.7 nA/°C | Shunt TCR, leakage across the ladder (0.1 % to 0.4 % at the 100 nA limit) |
| R1 | About 65 nA | About 12 nA/°C / 21 nA/°C | Shunt TCR, R0 in parallel |
| R2 | About 2.1 µA | About 0.4 µA/°C / 0.7 µA/°C | Shunt TCR |
| R3 | About 21 µA | About 4 µA/°C / 7 µA/°C | Shunt TCR 50 ppm/°C (0.10 % over 20 °C), self-heating 0.055 % at 1 A (estimate) |

The gain resistor R123 (25 ppm/°C) and the gain drift of the amplifier
(50 ppm/°C, datasheet value) act on every range alike.

Noise in R0 by mode (R-04, D-59):

| Mode | Noise in R0 (RMS, full bandwidth) | Mean of 100 samples | Limit of the test (section 11) |
| --- | --- | --- | --- |
| Ampere mode, quiet supply | About 2.1 nA (simulated) | Not simulated | 5 nA |
| Source mode | 26 nA to 27 nA (simulated) | 1.1 nA with the output open, up to 3.9 nA with a DUT (simulated) | 40 nA; 5 nA for the mean of 100 samples |

- In source mode the output noise of the linear regulator (125 nV/√Hz, a
  typical datasheet figure; no maximum is stated) stands across the shunt
  above 1 / (2π R C). With the 1 kΩ of R0 and the 100 nF of C71 that
  corner is 1.6 kHz, so nearly the whole band is read as current. A DUT with
  100 nF or more of its own brings the same figure whatever C71 is; a
  smaller C71 helps only with nothing connected.
- In R1 to R3 the same term depends on the capacitance at the DUT. It is not
  simulated; phase 2 measures it with 100 nF, 1 µF and 10 µF at the
  terminals.
- Averaging on the host lowers the noise with the square root of the number
  of samples; the 100 nA requirement (R-04) is met at full bandwidth in R0
  in both modes.

Leakage on the node behind the shunts at 5 V and 40 °C. Whatever flows from
VOUT or from a sense node to another potential is read as DUT current. It is
an offset; the zero calibration removes its constant part.

| Part | Typical | Datasheet limit | Evidence |
| --- | --- | --- | --- |
| Suppressor D21, VOUT to ground | 2.8 nA | 100 nA at 15 V and 25 °C; no figure at 5 V or above 25 °C | Estimate from 1 nA typical at 15 V and 25 °C |
| Output pair Q15, Q16, junctions | 0.07 nA to 0.2 nA | 1 µA at 24 V and 25 °C | Estimate from the body diode curve |
| Output pair, gate oxide, output on | No typical figure; 1.3 nA in the vendor model | 100 nA each at 20 V | Datasheet value; simulated |
| Guard buffer U25, input behind R114 | Below 0.05 nA | 20 pA at 25 °C | Datasheet value |
| C71, insulation | Below 0.5 nA | 0.5 nA to 1 nA | Estimate (10 GΩ, a distributor attribute) |
| Multiplexer U24 and amplifier U27 | 1 nA to 2 nA | 9.6 nA at 25 °C | Datasheet values |
| Sum | About 4 nA to 6 nA | Not provable from the limits | Estimate |

- Budget of this node: 10 nA is the typical design figure. Each board is
  measured with the output on and the terminals open at 5.0 V; the limit
  is 50 nA at room temperature, and the value is subtracted (closed-switch
  zero, section 8). The parts behind the output switch are outside the
  zero that runs with the switch open.
- The suppressor D21 is the largest term and the least certain one. Its
  only guaranteed figure, 100 nA at 15 V and 25 °C, equals the resolution
  of R-04; a part at that limit would leak about 0.28 µA at 40 °C and
  0.57 µA at 50 °C (estimate, doubling every 10 °C). The measurement of
  section 16 decides whether the part stays.
- No diode of the BAV199 type is on VOUT. The ones on the board act
  elsewhere (datasheet of the part ordered: about 0.5 nA typical, 5 nA
  maximum; effects calculated). The limiter clamp D22 leaks into the
  3.9 kΩ of R125: 2.3 µV at the ADC driver with 0.6 nA, which is 0.06 LSB
  or 0.12 nA in R0, and 0.5 LSB or 1 nA in R0 at the 5 nA limit, an offset
  that the zero calibration removes. The clamp D23 at the comparator
  inputs loads a divider of 750 Ω and moves no threshold. The diode D20
  of the output gate leaks into the 2.2 MΩ of R117 and lowers the gate
  by 1.3 mV. The diodes D15 to D19 of the mode pairs and of the VIN
  detector, and D13 and D10 of the source, are ahead of the shunts.
- Leakage across the ladder, from the supply node to VOUT, is a gain
  term and not an offset: it flows only with a burden voltage and is zero
  at zero current. It passes the three open range switches Q12 to
  Q14 and the two clamp transistors Q10 and Q11, whose gates are
  on the supply node through R92 and R100. The budget is 100 nA at
  100 mV and 40 °C in total: 0.1 % of reading at the full scale of R0 and
  at most 0.4 % at small currents; the gain calibration removes it at the
  calibration temperature. The datasheet of these transistors bounds the
  leakage at 24 V only (1 µA), so no figure at 100 mV follows from it: the
  measurement of section 16 decides, and one clamp can be left out if it
  fails. In R1 to R3 the term is below 0.01 % (calculated).

Currents that the instrument draws for itself are taken ahead of the
shunts, or from its own rails, and are not part of the reading:

- The bleed resistor R90 (100 kΩ from the supply node of the ladder to
  ground): 50 µA at 5 V. In ampere mode it comes from the external supply.
- The dividers on VIN (R73 with R74, R141 with R150): 35 µA
  at 5 V with ampere mode off (calculated); about 125 µA with it on, with
  the bleed resistor and the gate networks of the pair (simulated).
- The minimum load R69 of the regulator and the gate-to-source
  resistors R83 and R84 of the mode pairs.
- The pull-down resistors R103, R106 and R109 at the range gates and R115
  at the driver of the output gate: their current comes from the gate
  driver. No range switch has a resistor from gate to source.
- The supply of the level translator: it comes from the guard buffer
  through R118.

Two currents are measured although the instrument causes them:

- A logic input held high loads the DUT with its voltage across 470 kΩ
  (RN11, RN10): 7 µA at 3.3 V, plus the leakage of the ESD array of
  the line (datasheet: 1 nA typical and 10 nA maximum at 2.5 V, no figure
  above; section 4.8).
- For 250 ms after the output switch closes, the samples read low by the
  charging current of its gate through R117: 0.5 µA after 30 ms, 0.3 µA
  after 50 ms, 60 nA after 100 ms, 4 nA after 200 ms (simulated). The host
  marks these samples and keeps them out of statistics below 1 µA
  (section 9).

Zero of R0 over temperature:

- Amplifier U27: offset drift of 0.4 µV/°C at the input and 6 µV/°C at
  the output (datasheet limits), 0.70 µV/°C referred to the input at
  G = 19.93, which is 0.7 nA/°C across 1 kΩ (calculated). The second
  figure of the drift column of the table scales it to the other shunts;
  the first figure is the input stage alone.
- The bias current of the inverting input of U27 flows through the
  shunt: 1 nA typical, 2 nA maximum, 50 pA/°C (datasheet values).
- The leakage of the table above changes by about 7 % per °C: 0.2 nA/°C
  to 0.35 nA/°C (estimate).
- After a change of 5 °C a reading of 100 nA can therefore be off by up to
  3.5 nA from the amplifier alone, until the zero is taken again. The
  open-switch zero is repeated when the output is off and the board
  temperature has moved by more than 2 °C since the last one (section 8).

Limits of the budget:

- R3 above 1 A, the over-current level and the jump level are specified
  for an output voltage of 0.2 V or more. Below that the amplifier, on its
  −4 V rail, may leave its linear range near full scale: the two readings
  of its datasheet put the end at 130 mV and at 210 mV across the shunt,
  and the trip could then act at up to about 1.26 A instead of 1.15 A
  (estimate). Section 16 holds the measurement that settles it.
- Samples inside the settling window after a range change (7 samples by
  default, F-35) are flagged; mean, charge and energy use the first valid
  sample after the window in their place.

### 4.11 Controller Module & Power Domains

The carrier board has two 1×20 pin sockets at 2.54 mm pitch, 17.78 mm apart
(MP1, MP2), soldered into the holes of the module footprint
(U1), and the Raspberry Pi Pico 2 plugs into them (section 5 has the
pin assignment). The supported module is the Pico 2 with its pin headers
fitted; an RP2350 of stepping A3 or A4 is preferred (D-39, D-82). A
Pico 2 W fits the same sockets, but the firmware does not support it
(section 5).

- One supply domain (D-42, D-47). The VBUS pin of the Pico 2 (pin 40) feeds the
  second input of the power multiplexer through a solder jumper (JP1, closed
  as built) and a current limiter of 0.76 A (section 4.1). The 5 V rail feeds
  the VSYS pin (pin 39) through a Schottky diode (D1). Either USB connector
  therefore powers the whole instrument, and neither feeds the other one back:
  the multiplexer blocks reverse current on both inputs (1 nA typical, datasheet
  value).
- With the data cable alone the module is supplied from its own
  connector and the carrier through the jumper; the controller then does
  not depend on the 5 V rail. With USB-C alone the module is supplied
  through the diode D1. The carrier does not feed its VBUS pin, so the VBUS
  sense of the module (GP24) is expected to read low and to tell firmware
  whether the data cable brings power (estimate; the leakage of the
  diode of the module into that pin is not quantified). With the jumper
  cut the carrier runs from USB-C only.
- R23 loads the 5 V rail with 10 kΩ. It carries the reverse current of the
  diode D1 when the module is powered and the rail is not, which is the case
  with the jumper open: the rail then stays at 0.5 V or below (calculated
  from the datasheet maximum of 50 µA at 25 °C).
- The 3.3 V regulator of the Pico 2 powers the Pico 2 only; its 3V3,
  3V3_EN and ADC_VREF pins are not connected. The carrier logic runs
  from its own 3.3 V rail, 3V3_C, at the same level. The analog ground
  pin of the module joins the ground plane through a link (R2).
- A green LED on the carrier (D5, with R26, 1 kΩ) is on 3V3_C and takes
  1.3 mA (calculated). It is lit while the supervisor has released the carrier
  and dark while the carrier is held off; it says nothing about the analog
  rails. The status indicator of the firmware is the LED of the Pico 2 (section
  5).
- Pads of the RP2350 (datasheet): GP0 to GP22 are fault-tolerant pads, which
  take 3.3 V without supply and 5.5 V with it. GP26 to GP28 are standard pads
  with a diode to the 3.3 V rail of the module. On the carrier these three are
  two outputs and PWR_GOOD behind a resistor, and no source of the carrier
  reaches them without one.
- Reset state: out of reset every pin of the RP2350 is a high-impedance input
  with its input buffer off and a weak pull-down (RP2350 datasheet). Every line
  that the controller drives, except the console output, has a resistor to a
  rail on the carrier, so with
  the module in reset, in the boot loader or out of its sockets every switch is
  open, range 0 is selected, the pre-regulator is off and neither converter of
  the SPI bus is selected:
  - 1 kΩ to ground at the inputs of the gate drivers (R70, R88, R89,
    R93, R94), 4.7 kΩ at the request of the ampere switch (R71) and
    5.1 kΩ at the two address lines of the multiplexer (R95, R91);
    D-67.
  - 4.7 kΩ at the pins of the module for the SPI and acquisition lines
    (RN2, RN3): to 3V3_A for the two chip selects, to ground for
    the others (D-77). The selects rest high in reset; the pad pull-down
    of 36 kΩ to 113 kΩ cannot pull them below 2.8 V (calculated).
  - 1 kΩ to ground at the enable of the pre-regulator (R53). The
    request SMU_ON reaches that pin through a transistor that 5V_OK
    turns on (Q1), so the supervisor can refuse it (D-48).
- Pins without supply. With one supply domain the module is powered
  whenever the 5 V rail is, but the supplies of the carrier are off
  while the supervisor holds them (below). Series resistors limit what a
  pin of the module can push into a carrier input whose supply is
  absent:
  - 1 kΩ at each input of a gate driver and at each address input of the
    multiplexer (R72, R75, R96 to R99, R111, R112): a pin that is high while +12
    V_A is absent drives 2.7 mA, 2.9 mA at the tolerance limits (calculated).
  - 2.2 kΩ in the slow SPI lines (RN1); the select of the DAC has 47 Ω
    (RN4) and 1.5 kΩ (R3) instead. The slow SPI bus runs at 500 kHz
    or less (F-6).
  - 47 Ω at the module (RN4) and 220 Ω at the converter (RN5) in
    the acquisition lines, 33 Ω in the data line of the shift registers
    (R138).
  - The status lines reach the controller through 4.7 kΩ (VIN_OV, R1) and 1
    kΩ (PWR_GOOD, R4); D-78. The table of section 5 gives the pull resistor
    and the series resistor of every pin.
- Supervisor (D-48, section 3). The signal 5V_OK of the supervisor on the 5 V
  rail enables the two 3.3 V regulators, the +12 V_A regulator and the charge
  pump, and gates SMU_ON. It is low below 3.83 V to 4.00 V on the rail and for
  0.18 s to 0.42 s after the rail has returned (calculated from datasheet
  limits). The controller therefore runs with the carrier off at every start,
  after every dip of the rail below that level, and while the test point of
  5V_OK is held to ground: the 5 V rail and +13.5 V are up, everything else is
  off, PWR_GOOD is low.
- With 5V_OK high the enable pin of the pre-regulator follows SMU_ON up to the
  smaller of 3.3 V and 0.943 × the rail − 1.65 V: 2.36 V with 4.25 V on the rail
  and 1.96 V at the lowest supervisor threshold, against an input threshold of
  1.2 V (calculated; the 1.65 V of the transistor is an estimate, the threshold
  a datasheet value). While SMU_ON is high GP18 drives 3.3 mA into R53.
  TP18 is the test point of the enable pin.
- PWR_GOOD (D-54, section 3) is pulled up to 3V3_C through 1.5 kΩ with 6.8 kΩ to
  ground and is driven by the four comparators of the rail monitor. It is high
  when 3V3_A, +12 V_A, −4 V_A and the reference are above the thresholds of
  their comparators and 3V3_C is present; it is low while the supervisor holds
  the carrier off. Its high level is 0.82 × 3V3_C, 2.50 V at the pin of the
  controller in the worst case against the 2.0 V that the pin needs
  (calculated). The pad of GP28 sees 7.8 kΩ to ground, inside the 8.2 kΩ that
  erratum E9 of stepping A2 asks for.
- What firmware does with PWR_GOOD (section 6.6 has the rules):
  - GP28 is an input and is never driven (F-4). PWR_GOOD counts as high after 10
    ms without interruption, which arrives 0.2 s to 0.46 s after power is
    applied (simulated). No carrier input is driven before that; after 1 s
    without it firmware reports a carrier supply fault (F-2).
  - The rails count as valid when, in addition, the monitor reads +12 V_A inside
    11.4 V to 12.6 V, −4 V_A inside −4.3 V to −3.7 V and the 5 V rail between
    4.25 V and 5.50 V, with no rail channel at code 0 or 4095. The test starts
    200 ms after PWR_GOOD and must pass within 3 s; no path is closed before it
    has passed. Firmware repeats it in every monitor cycle (F-3, F-12).
  - On a falling edge of PWR_GOOD firmware takes the request of the output
    switch low, stops the state machines and releases every pin toward the
    carrier within 50 µs; the chip selects are released without being driven.
    The fault "carrier supply" is latched and reported (F-7). The same reaction
    follows the loss of the VBUS sense of the module while the module input
    supplies the rail. The edge comes 0.05 ms to 0.07 ms after the rails begin
    to fall (simulated): it shortens the exposure of the carrier inputs, and the
    series resistors bound it.
  - PWR_GOOD returns 0.2 s to 0.7 s after a trip of the supervisor (estimate).
    The carrier has then been off: firmware initializes the DAC, the monitor
    converter and the range state again (F-3).
  - PWR_GOOD says nothing about the level of 3V3_C, and no monitor
    channel reads a 3.3 V rail: the self-test does not cover it.
- A push button (SW1) pulls the RUN pin low. With the BOOTSEL button
  of the Pico 2 held, that reset opens its USB mass-storage boot loader,
  which is how firmware is loaded: no programmer and no vendor tool is
  needed.
- UART0 of the controller is on a 3-pin header (J1), for a console.
- The Pico 2, with its switching regulator, stays away from the shunt
  ladder and the amplifier (section 10).

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
- The supported module is the Raspberry Pi Pico 2 with headers (SC1632),
  U1, with an RP2350 of stepping A3 or A4 preferred (D-82). It is
  plugged, not soldered: the two 1×20 sockets MP1 and MP2 are
  soldered into the holes of its footprint. A Pico 2 W fits the sockets,
  but its LED, its regulator mode pin and its VBUS sense are pins of the
  radio chip; the firmware does not support it.

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
| 28 | 34 | PWR_GOOD | In | Carrier rails present (section 4.7) |

- Power and ground: VBUS (pin 40) and VSYS (pin 39) as section 4.11
  describes; ground on pins 3, 8, 13, 18, 23, 28 and 38, and the analog
  ground pin 33 through the link R2. 3V3 (pin 36), 3V3_EN (pin 37) and
  ADC_VREF (pin 35) are not connected. RUN (pin 30) goes to the reset
  button SW1.
- The groups follow what a PIO state machine needs: its output pins and its
  input pins are runs of consecutive GPIO numbers. GP2 to GP7 are the
  outputs of the range sequencer and GP8 to GP10 its inputs; GP16 and GP17
  are the inputs of the acquisition state machine and GP19 to GP21 its
  outputs.
- The acquisition pins have the ground pins 23 and 28 among them.
- Every GPIO of the headers is in use. A further signal means giving up the
  console or sharing the SPI bus.
- The status indicator is the LED of the Pico 2 (GP25).

A line that the controller drives has a resistor to a rail on the carrier,
which defines it while the pin is released or the sockets are empty, and a
series resistor sized for whatever receives it (D-67, D-77, D-78). The
console output has neither, and SMU_ON has no series resistor. The table
gives both for every pin, and the level of the line while the controller is
in reset, in its boot loader or absent. Where the drawing
labels a line behind its series resistor with another name than the signal,
the name is in brackets.

| GPIO | Signal | Resistor to a rail | Series resistor | Pins released |
| --- | --- | --- | --- | --- |
| 0 | DBG_TX | None | None; straight to the console header J1 | Header pin open |
| 1 | DBG_RX | None; firmware turns the pad pull-up on | None; straight to J1 | Open until firmware starts |
| 2 | GATE_R1 | R89, 1 kΩ to ground | R97, 1 kΩ at the gate driver U23 | Low: R1 off |
| 3 | GATE_R2 | R94, 1 kΩ to ground | R99, 1 kΩ at U23 | Low: R2 off |
| 4 | GATE_R3 | R88, 1 kΩ to ground | R96, 1 kΩ at the gate driver U22 | Low: R3 off |
| 5 | MUX_A0 | R95, 5.1 kΩ to ground | R112, 1 kΩ at the multiplexer U24 | Low: taps of R0 selected |
| 6 | MUX_A1 | R91, 5.1 kΩ to ground | R111, 1 kΩ at U24 | Low: taps of R0 selected |
| 7 | GATE_OUT | R93, 1 kΩ to ground | R98, 1 kΩ at U22 | Low: output switch open |
| 8 | CMP_UP | None | None; push-pull output of U32 | Driven by the comparator |
| 9 | CMP_JUMP | None | None; push-pull output of U31 | Driven by the comparator |
| 10 | CMP_OC | None | None; push-pull output of U31 | Driven by the comparator |
| 11 | VIN_OV | None | R1, 4.7 kΩ from the interlock node | Driven by the detector U21 |
| 12 | SPI_MISO (C_MISO) | One element of RN2, 4.7 kΩ to ground, at the monitor ADC U40 | One element of RN1, 2.2 kΩ | Driven by U40, or low |
| 13 | MON_CS (C_MON_CS) | One element of RN2, 4.7 kΩ to 3V3_A | One element of RN1, 2.2 kΩ | High: U40 not selected |
| 14 | SPI_SCK (C_SCK) | One element of RN2, 4.7 kΩ to ground | One element of RN1, 2.2 kΩ | Low |
| 15 | SPI_MOSI (C_MOSI) | One element of RN2, 4.7 kΩ to ground | One element of RN1, 2.2 kΩ | Low |
| 16 | ADC_DOUT | None | One element of RN5, 220 Ω, at the ADC U30 | Driven by the ADC while it is read, open between frames |
| 17 | SIDE_DOUT | None | R138, 33 Ω, at the register U34 | Driven by the register |
| 18 | SMU_ON | R53, 1 kΩ to ground, behind the transistor Q1 | None; Q1 passes the line while the 5 V rail is good | Enable pin of U16 low: pre-regulator off |
| 19 | ADC_SCK | One element of RN3, 4.7 kΩ to ground | One element of RN4, 47 Ω; then 220 Ω of RN5 at U30 | Low |
| 20 | ADC_CNV | One element of RN3, 4.7 kΩ to ground | One element of RN4, 47 Ω; then 220 Ω of RN5 at U30 | Low: no conversion |
| 21 | SIDE_LOAD | One element of RN3, 4.7 kΩ to ground | One element of RN4, 47 Ω | Low: registers loading |
| 22 | DAC_CS (C_DAC_CS) | One element of RN3, 4.7 kΩ to 3V3_A | One element of RN4, 47 Ω, and R3, 1.5 kΩ | High: DAC U15 not selected |
| 26 | GATE_SRC | R70, 1 kΩ to ground | R75, 1 kΩ at the gate driver U20 | Low: source pair open |
| 27 | GATE_AMP | R71, 4.7 kΩ to ground | R72, 1 kΩ, to the input of the gate driver U20, which Q2 and Q3 can pull low | Low: ampere pair open |
| 28 | PWR_GOOD | R51, 1.5 kΩ to 3V3_C, and R52, 6.8 kΩ to ground, on the flag | R4, 1 kΩ | Driven by the flag |

- Reset state: out of reset every pin of the RP2350 is a high-impedance
  input with its input buffer off and a weak pull-down of 36 kΩ to 113 kΩ
  (RP2350 datasheet). The resistors of the table then open every switch,
  select the taps of R0, keep the pre-regulator off and leave neither
  converter of the SPI bus selected. The same holds in the USB boot loader
  and with the sockets empty.
- Levels with the pins released (calculated): the two chip selects stand
  at 2.80 V or more against the strongest pad pull-down, where the
  converters need 0.7 of their supply (datasheet); the gate, address and
  clock lines stand at 0 V. On an RP2350 of stepping A2 a released pad can
  source about 120 µA (erratum E9, RP2350 datasheet): the lines then stand
  at 0.12 V behind 1 kΩ, 0.56 V on GATE_AMP and 0.61 V on the address
  lines, still low for their receivers, and the erratum is why no
  pull-down is above 8.2 kΩ.
- Pull on the controller side: every pull resistor of the SPI and
  acquisition lines sits at the pin of the module, ahead of the series
  resistor, so the low level of a driven line is that of the pad and not
  of a divider. The one exception is the pull-down of SPI_MISO, which sits
  at the output of the monitor converter.
- What the series resistors limit: a pin driven high while the rail of its
  receiver is absent pushes 2.7 mA, 2.9 mA at the tolerance limits, into a
  gate driver or multiplexer input, 1.39 mA into a slow SPI input and
  1.90 mA into the select of the DAC, whose inputs are rated for 2 mA
  (calculated at the tolerance limits; datasheet). The resistor R3 is a
  1 % part for that reason. Into the two clock inputs of the ADC a pin can push
  6 mA to 10 mA peak with nominal values and the output resistance of the
  pad, up to 11.3 mA at the tolerance limits (calculated); those inputs
  are rated by voltage only, and rule F-7 keeps the state short.
- Inputs: GP1, GP8 to GP12, GP16, GP17 and GP28 are driven by carrier
  outputs and are never configured as outputs (rule F-4). The three
  comparator lines and the console input are the only ones of them without
  a series resistor.
- GP0 to GP22 are fault-tolerant pads: they take 3.3 V without supply and
  5.5 V with it. GP26 to GP28 are standard pads with a diode to the 3.3 V
  rail of the module (RP2350 datasheet); on the carrier they are two
  outputs and PWR_GOOD behind R4, and no carrier source reaches them
  without a resistor.
- SMU_ON has no resistor on the controller side of Q1. The transistor
  is open while the supervisor holds the carrier off (D-48), and nothing
  but its drain sees the pin then.
- Slow SPI bus: mode 0,0 at 500 kHz or less (rule F-6). The monitor
  converter has no timing figures at 3.3 V beyond a clock of 1 MHz at
  2.7 V (datasheet), and the edges behind 2.2 kΩ take 156 ns
  (calculated).
- Drive strength, pad pulls and the order in which firmware takes the
  lines over are rules F-1 to F-5 of section 6.6.

## 6. Firmware Architecture & Execution Strategy

To guarantee uninterrupted 100 kSPS sampling without dropping frames, the
firmware uses the two cores of the RP2350 combined with PIO and DMA. There
is no per-sample interrupt and no per-sample driver call: a PIO state machine
clocks the converter, and DMA moves its words to memory. The firmware is
built with the Pico SDK (C and CMake); the USB stack is TinyUSB, which the
SDK brings.

Status: the firmware in the repository still has the ESP-IDF adapters of the
first plan. The hardware-independent code of every component is unchanged by
D-39; its adapters and its build are ported in phase 1 (section 13). The
rules of section 6.6 are requirements for that port; none of them is
implemented yet.

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
| `smu` | DAC, start and stop sequence of the source, regulator enable, power budget enforcement |
| `monitor` | Slow channels of the monitor ADC: VOUT, VIN, the 5 V rail with its source tag, CC, temperature, rails; rails test |
| `cal` | Calibration table in flash, zero calibration routine |
| `usb_link` | TinyUSB CDC ACM, host-open detection |
| `app` | Device state machine, command handlers, start-up self-test, supervision and watchdog |

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
| Monitor | 0 | Timer, 10 ms cycle | Eight slow channels at 100 SPS each, rails test, power budget, thermal, watchdog reload |
| Power fail | 0 | Edges of PWR_GOOD and VIN_OV | Interrupt handlers in RAM: rules F-7 and F-27 |
| Application | 0 | Events | State machine, LED |

Core 1 runs the acquisition loop and nothing else. Core 0 runs the other
work as a cooperative loop; whether a real-time kernel is added is decided
in phase 1, from measured latencies.

The monitor work is the supervision task of the instrument. It alone
reloads the hardware watchdog of the RP2350, once per completed monitor
cycle, so a program that stops supervising releases every pin within
100 ms (rule F-8, D-81). The two interrupt handlers do not wait for that
cycle: their reaction times are 50 µs and less.

### 6.3 Acquisition Pipeline

1. The acquisition state machine starts a conversion, pulses the load line
   of the shift registers, and clocks the converter and the registers
   (timing in rule F-34).
2. It pushes one 32-bit word per sample. DMA fills a block of 256 words and
   signals core 1.
3. The acquisition loop separates the conversion result from the side bits,
   optionally decimates, builds 32-bit sample words and marks the settling
   window (7 samples by default) after any change of the range bits. The
   window starts at the first sample that shows the new range. A decimated
   sample carries the side bits of the oldest raw sample of its group.
4. It evaluates the step-down rule and the under-range rule (F-22) on the
   block and asks the range sequencer for a step down or for R3.
5. The block goes into the ring buffer. If the buffer is full the block is
   dropped and counted; acquisition never blocks.

Budgets:

- CPU: the acquisition loop must use under 30 % of core 1 at 100 kSPS.
- Memory: ring buffer of 64 blocks (about 66 kB, 164 ms of data), out of
  520 kB of RAM.
- Latency from sample to host: under 20 ms typical.
- Flash writes are forbidden while streaming, because they stall code that
  runs from flash. They are also forbidden while a path is closed: the
  power-fail handler of rule F-7 must never wait for one.

### 6.4 Device State Machine

```text
BOOT ─► SELFTEST ─► IDLE ◄──────────────┐
                     │  ▲               │
           DUT_POWER │  │ DUT_POWER off │ CLEAR_FAULT
                     ▼  │               │
                    ARMED ─► FAULT ─────┘
                     │  ▲       ▲
               START │  │ STOP  │ trip, rails, VIN, power limit, thermal
                     ▼  │       │
                   STREAMING ───┘
```

- BOOT: the first code that touches a pin resets the PIO blocks, the pads
  and the IO banks and leaves every pin toward the carrier released (F-1).
  Firmware then waits for PWR_GOOD, which arrives 0.2 s to 0.46 s after
  power (simulated), and drives nothing before it has been high for 10 ms
  (F-2). After that it brings the carrier up in the order of F-3: chip
  selects, SPI, DAC at zero, monitor scan, rails test, and only then the
  PIO programs and the gate lines, all low, with R3 selected.
- SELFTEST: the rails test of F-12 passes within 3 s of PWR_GOOD, the ADC
  responds, the range logic steps through all ranges, and the zero
  calibration runs with the output open once monitor channel 6 is stable
  (F-36). A failed self-test goes to FAULT. No test covers the level of
  3V3_C: PWR_GOOD takes its thresholds from that rail and no monitor
  channel reads it, so only its absence is detected.
- IDLE: at rest every switch is open, the pre-regulator is off (SMU_ON
  low) and the DAC is at zero. SET_MODE acts here and nowhere else, so the
  mode never changes with the output pair closed (F-23).
- DUT_POWER on in source mode runs the one start sequence of F-28: the
  DAC at the code of 0.80 V for 200 ms, SMU_ON high, 5 ms, the DAC at the
  working value for 80 ms, R3 and the source pair, 60 ms, a check of
  monitor channel 0 against the set-point within 100 mV, and the output
  pair last.
- DUT_POWER on in ampere mode: VIN_OV low and VIN read inside 0.6 V to
  5.4 V for 100 ms (F-26); R3 selected and the trip armed (F-20); the
  ladder node no higher than VIN plus 0.1 V (F-25, up to 3 s); the ampere
  pair; 40 ms; the output pair last (F-24).
- The response to DUT_POWER on is sent, and the state becomes ARMED, when
  the output counts as on: 50 ms after GATE_OUT rose (F-24). A check of
  the sequence that fails goes to FAULT with every switch open.
- DUT_POWER off opens the output pair first, then the mode pair. In source
  mode SMU_ON goes low after the source pair is open and the DAC goes to
  zero last (F-29); a DUT that holds the output above the set-point is
  followed first (F-31). After a request line fell, 5 ms pass before a
  mode request is raised (F-23).
- STREAMING stops by itself when the host closes the port.
- FAULT always opens the output switch first and reports second. A fault can
  be raised in every state after BOOT. Its causes: the over-current trip
  (F-18, F-19), a sequencer that does not act (F-21), a reverse current
  (F-22), the loss of PWR_GOOD or a failed rails test (F-7, F-12), VIN
  over-voltage or VIN out of range (F-26, F-27), the power limit (F-14),
  the thermal limit (F-15), an overload or an external voltage on the
  source output (F-32, F-33), a failed start check and a failed self-test.
- After the loss of PWR_GOOD the bring-up of BOOT runs again when the flag
  returns, 0.2 s to 0.7 s later (estimate): the DAC, the monitor converter
  and the range state are initialized again before any path can close.
- A restart by the watchdog passes BOOT and SELFTEST like any other start,
  ends in IDLE with the DAC at zero and is reported with its own fault
  flag (F-8).
- After an over-current trip DUT_POWER on is refused for 100 ms, and
  nothing closes the output again by itself (F-19).
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
- The configuration descriptor declares 500 mA (F-14).

### 6.6 Rules That Guard Hardware

The carrier is built so that no state of the controller pins damages it:
the lines that the controller drives have a resistor to a rail and a series
resistor, with the exceptions that the table of section 5 shows.
What the parts cannot do is left to firmware, and this section is the one
list of it (D-81). Each rule states what firmware does or never does, the
figure, and what the rule guards. The hardware-independent logic of every
rule has a unit test before a board is powered for the first time.

Each protective action lives on one of the three levels of section 3.
The table gives the watchdog a row of its own: it is what is left of the
third level when the program hangs.

| Level | Actions | Needs | Works with a hung program |
| --- | --- | --- | --- |
| Hardware | VIN over-voltage holds the ampere pair open; interlock of the two mode requests; load shed when the 5 V rail collapses; fuses, clamps and current limiters; limits inside the regulators; every switch open, the pre-regulator off and both SPI converters deselected whenever the pins are released | Nothing | Yes |
| PIO state machines | Step up, jump up, make-before-break of the range switches, over-current trip with its latch, acquisition timing | Programs loaded once, system clock | Yes |
| Watchdog of the RP2350 | Release of every pin within 100 ms when the supervision task stops | Enabled once, system clock, no isolated pad (F-5) | Yes; not with the clock stopped |
| Firmware | Everything in the tables below that is not a PIO program | A running program | No: covered by the watchdog |

With the clock of the controller stopped only the first level is left: the
current and thermal limits of the linear regulator in source mode, the
fuse of VIN in ampere mode. That is a failure of the module, and no part
is spent on it.

In the tables, channel n is channel n of the monitor converter U40:
0 the ladder output, 1 VIN, 2 the 5 V rail, 3 and 4 the CC pins, 5 the
temperature sensor, 6 +12 V_A, 7 −4 V_A. A clock is one cycle of the
150 MHz system clock.

#### Controller Pins and Start

| Rule | Firmware | Guards |
| --- | --- | --- |
| F-1 | After every start (power-on, RUN, watchdog, debugger or core-only reset) the first code that touches IO resets the PIO blocks and the pad and IO banks and leaves every pin toward the carrier released. | Every carrier input: a level left from before the restart would hold a gate line or a chip select. |
| F-2 | No pin toward the carrier is driven while PWR_GOOD is low. PWR_GOOD counts as high after 10 ms without interruption. Without it 1 s after start the fault "carrier supply" is reported and the wait goes on. Firmware cannot read why the carrier is off: a USB-C source too weak to start it looks the same. | Inputs of the gate drivers, the multiplexer, the DAC, the monitor converter and the ADC while their rails are absent. The series resistors are the second barrier: 2.9 mA at the most per gate or address line, 1.39 mA per slow SPI line, 1.90 mA into the DAC select against its 2 mA limit (calculated; limit from the datasheet). The clock lines of the ADC are not bounded that far: up to 11.3 mA peak at the tolerance limits, and 3V3_C lifted to about 1.6 V (calculated). |
| F-3 | Order after PWR_GOOD: (1) both chip selects driven high as plain outputs, then the SPI function, the DAC at code zero, the monitor scan; (2) from 200 ms after PWR_GOOD the rails test of F-12 runs in every monitor cycle, and no pass within 3 s is the fault "analog rails"; (3) after the first pass the PIO programs start and the gate, address and enable lines are driven, first all low, then R3; (4) the zero calibration waits as F-36 says. | The DAC code, the comparator thresholds and every reading before the reference has settled: the reference is within 0.1 % about 80 ms after the supervisor releases the carrier (simulated), and +12 V_A is at 11 V 18 ms after that release, approaches 12 V with 0.18 s and is inside its window after about 0.1 s (calculated). |
| F-4 | GP1, GP8 to GP12, GP16, GP17 and GP28 are never outputs. A unit test checks the pin table of the build. | The interlock node of VIN (behind the resistor R1 a pin moves it by 0.14 V at most, calculated), the PWR_GOOD flag (3.3 mA through R4 against the 25 mA of the comparators), the data outputs of the registers, the ADC and the monitor converter. The three comparator lines have no series resistor: a pin driven against them fights a push-pull output and falsifies its side bit. |
| F-5 | Drive strength 12 mA on GP2, GP3, GP4, GP7 and GP26, 4 mA on every other output. Pad pull-downs off on GP13, GP22 and GP28 after start. Pad pull-up on GP1. No pad toward the carrier is ever isolated (ISO bit) while it is an output, and no low-power state that powers the switched core domain down is entered while a path is closed. | The input-high level of the gate drivers behind 1 kΩ pull-downs. The watchdog: its reset frees a pad only through the pad registers, and an isolated pad keeps its level (RP2350 datasheet). The console input, which otherwise floats on an open header pin. |
| F-6 | GP13 and GP22 are plain outputs, both high before the first clock and never both low. SPI1 runs in mode 0,0 at 500 kHz or less. The DAC frame is `0x5000 \| code` (reference input buffered, gain 2, output active); a unit test shows that no other upper nibble can be sent. | The DAC code: with both selects low a monitor frame is read as a DAC word. The monitor converter, whose only timing figure below 5 V is 1 MHz at 2.7 V (datasheet); the edges behind RN1 take 156 ns (calculated). The set-point scale: the reference divider R55, R56 is a 1 kΩ source, and the unbuffered reference input would load it by 0.6 %, 30 mV at 5.0 V (calculated). |
| F-7 | A falling edge of PWR_GOOD (interrupt on GP28, handler in RAM at the highest priority), or the loss of the VBUS sense of the module while the input of the module supplies: within 50 µs GATE_OUT is low, both groups of state machines are stopped, and every output toward the carrier is driven low and then released. The two chip selects are released without being driven. The interrupt is armed only once PWR_GOOD is valid (F-2); its first edge latches the fault "carrier supply" and masks the interrupt until the flag has been valid again. Then the start begins again at F-2. Where the sequencer program has room, a low PWR_GOOD also forces GATE_OUT low inside the PIO block. | The digital inputs of the ADC (DVDD + 0.3 V, datasheet) and every other carrier input while the module outlives the rails: the flag falls 0.05 ms to 0.07 ms after the rails begin to fall and does not lead them (simulated), so the reaction shortens the exposure and the series resistors bound it. A chip select driven high would feed 3V3_A through the pull-up and hold it at 0.76 V, above the 0.7 V the ADC needs before it is powered again (calculated; datasheet). |
| F-8 | The watchdog of the RP2350 is enabled before any gate line is driven, with a time-out of 100 ms or less and a reset that includes the pad and IO registers. Only the supervision task reloads it, after a complete monitor cycle. The two debug pause bits are cleared in release builds. A watchdog restart sets a fault flag and leaves the instrument in IDLE with the DAC at zero. | Everything that only firmware guards: with a hung program the output would stay on with the thermal limit, the budget and the rails test gone. After the reset R93 pulls GATE_OUT low and the gate of the output pair is below 2 V within 7 µs (simulated). The rule does not replace F-21: the 1 Ω shunt and the ladder clamp do not last 100 ms. A development build halted in a debugger keeps the output on. |
| F-9 | A restart into the USB boot loader never names a GPIO of the headers as activity indicator. | The gate lines: the boot loader would toggle one. |

#### Monitor, Supplies and Budget

| Rule | Firmware | Guards |
| --- | --- | --- |
| F-10 | The monitor scan reads each of the eight channels at 100 SPS, and never faster on channels 0, 2 and 7. One exception: in source mode with the output pair closed, channel 0 is read in addition as often as the 0.5 ms of F-33 asks; these readings serve the comparison with 5.3 V alone and enter no other rule. | The accuracy of the channels behind 54.5 kΩ and 66.7 kΩ: 0.97 LSB of error at the sampled instant at 100 SPS, 4.9 LSB at 1 kSPS and more at the rate of the exception (calculated), which a comparison with 5.3 V bears. Every other limit below rests on the readings at 100 SPS. |
| F-11 | Channel 2 above 1.67 V: the USB-C input supplies and the 5 V rail is the reading divided by 0.4545. At or below 1.67 V: the input of the module supplies and the rail is the reading divided by 0.2524; a result above 5.7 V is inconsistent and counts as a rail below its limit. | The budget of F-14 and the rail limits of F-12. The two bands are 1.93 V to 2.50 V and 1.07 V to 1.39 V (calculated from R142, R151 and R143). |
| F-12 | Rails valid means: PWR_GOOD valid (F-2), channel 6 inside 11.4 V to 12.6 V, channel 7 inside −4.3 V to −3.7 V, the 5 V rail (F-11) at 4.25 V or more as a 10 ms average and below 5.50 V, channel 5 between 0.3 V and 1.5 V, and no rail channel at code 0 or 4095. A converter that does not answer is a failure. The test runs every 10 ms. A failure opens the output switch and both mode pairs, takes SMU_ON low after them and sets the rails flag. A 5 V rail below 4.25 V alone is reported as the power-limit fault of F-14 and does not set the rails flag. | The DUT and the measurement when a rail is present but out of tolerance: PWR_GOOD reports presence only (section 4.7). The over-voltage detector of VIN, which runs from 3V3_A and the reference. A sagging supply, which the supervisor catches only at about 3.9 V (calculated). |
| F-13 | CC1 and CC2 are read at 100 SPS. The class changes after three equal consecutive classifications, so a lower advertisement is followed within 60 ms. A reading above 2.04 V is invalid. | The class of the budget against noise and against a source that lowers its offer. |
| F-14 | The budget is an input current, computed from the set-point, the measured output current and the measured rail: 0.45 A through the carrier while the input of the module supplies or CC is below 0.61 V, 1.4 A with CC at 0.70 V to 1.16 V, 1.7 A with CC at 1.31 V to 2.04 V. More than the default is granted only while the USB-C input supplies (F-11). The output opens with a power-limit fault when the current averaged over 10 ms passes the budget or the rail averages below 4.25 V over 10 ms. The USB configuration descriptor declares 500 mA. The status record reports the input in use and the CC class. | The USB source (R-14). Behind the rule stand the current limiters of the two inputs and the supervisor (section 4.1); they act later and switch the whole carrier off. The constants of the input model are calibrated on the first board. |
| F-15 | Channel 5 is evaluated at 10 SPS or more. Above the thermal limit the output switch opens, SMU_ON goes low after the source pair and the thermal flag is set. The limit is a constant taken from the first board. | The linear regulator U18: 1.5 W to 2.0 W in a sustained short (calculated). Its own thermal limit is the second barrier. |

#### Range Sequencer and Over-Current Trip

| Rule | Program or firmware | Guards |
| --- | --- | --- |
| F-16 | CMP_JUMP is never blanked. It forces R3 (GATE_R3 high and address 11, the lower gates low after the overlap) within 100 ns of its pin, in every state of the sequencer and with the range locked. | R-07: the droop limit rests on this figure. The ladder clamp, which carries the step until R3 conducts. |
| F-17 | CMP_UP is ignored from the first change of a gate or address line of a range change until 2.0 µs (300 clocks) after the last one, up and down. Every range change is make-before-break: the gate of the new branch rises about 1 µs before the gate of the old one falls. | The range logic against a bounce after its own step. The DUT, which is never left on R0 alone during a change (section 4.3). |
| F-18 | The over-current trip acts in R3 only: GATE_OUT goes low when CMP_OC has been high without interruption for T_OC = 12 µs (1800 clocks) and stays low until firmware clears the latch. T_OC is a build constant, never below 10 µs and never above 20 µs, changed only by a build after the measurement of phase 3. The trip is armed whenever a path can close, with no blanking at a start. | The 0.1 Ω shunt R110, the ladder clamp and the DUT. Below about 9 µs the trip would act on the recharge of the DUT capacitor after a range step (simulated need 8.6 µs); the short-circuit figures of the output switch hold up to 20 µs (simulated). |
| F-19 | After a trip R3 stays selected, in source mode the source is stopped in the order of F-29, GATE_OUT stays low until the fault is cleared and DUT_POWER on is refused for 100 ms. There is no automatic retry. Consecutive trips are counted and reported. A trip within 100 ms of GATE_OUT is reported as "start over-current". | R110 and the clamp against repeated surges. A start trips with more than about 2200 µF at the DUT (simulated; 1800 µF for a capacitor with a tolerance of 20 %) or with a DUT that draws more at low voltage. |
| F-20 | The sequencer and the trip are started in step 3 of F-3 and never with PWR_GOOD low. R3 is selected before a mode pair closes, and the trip is armed once R3 has settled, 2 µs after the last gate change. GATE_OUT goes high only through the sequencer program, never by a plain write to the pin. | The comparators before their rails and their reference are valid. The in-rush through the shunt, which must meet R3 and an armed trip. |
| F-21 | CMP_JUMP read high for more than 1 ms while R3 is not selected means that the sequencer is not acting: firmware forces GATE_OUT low no later than 2 ms after the first such reading and reports a fault. A code of 65535 alone is not the criterion: a locked range may sit between the full scale of the converter and the jump level. | The ladder clamp Q10, Q11: one of the two carries nearly all the current and heats by 96 K in 2 ms at 4 A (144 K in 5 ms, calculated). The 1 Ω shunt R107, which takes 6.3 W to 8.4 W in that state (calculated); range 2 is calibrated again after such a fault. |
| F-22 | While a mode pair is closed, a code below 650 for 100 samples (a stored constant) is flagged as under-range. R3 is requested at once, at the latest 2 ms after the first such sample and also with the range locked, and no step down is requested until 1 s after the flag clears. If the code stays below 650 in R3 (about 13 mA backward, calculated) for 100 ms, the output switch opens and a reverse-current fault is reported. | The body diodes of the clamp transistors and of Q14, and R110, with a current that flows backward through the ladder (D-69). |

#### Path Switches

| Rule | Firmware | Guards |
| --- | --- | --- |
| F-23 | The output pair is the last switch to close and the first to open; in normal operation a mode pair opens only after it. The two mode requests are never high together, and after a request fell 5 ms pass before either is raised. The mode is changed with the output pair open. GATE_SRC and GATE_AMP are driven low before their pins are released. | The linear regulator, whose input must not fall below its output, and the external supply. The hardware interlock keeps source mode if both requests are high (D-62); the rule keeps that case out of normal operation. The paths of F-7, F-26 and F-27 open a mode pair under load: VIN then rises to 20 V to 24 V at 0.5 A to 1 A with 0.5 µH of leads, inside the ratings (estimate). |
| F-24 | DUT power on, both modes: R3 selected and the trip armed (F-20); the set-point at its working value (F-28) or VIN in its window (F-26); the mode pair; 40 ms, after which the path counts as closed for the range logic, the calibration and the result of DUT_POWER; then GATE_OUT. The output counts as on 50 ms after GATE_OUT. | The in-rush, which the slow gate networks of both pairs limit only in this order (D-61, D-71). The GATE_OUT bit of a sample reports the command; the DUT voltage starts to rise 6 ms to 7 ms later (simulated). |
| F-25 | GATE_AMP is raised only when channel 0 reads below the voltage of VIN (channel 1) plus 0.1 V, or below 0.3 V. After 3 s without that a fault is reported. | The supply of the user. With the output switch open the ladder node keeps its voltage and falls only with 0.57 s (R90 with C62 and C63, calculated); closing the ampere pair on a lower voltage pushes that charge into the supply and lifts a rail that cannot sink current. |
| F-26 | The ampere pair is closed only while VIN_OV is low and after channel 1 has read 0.6 V to 5.4 V for 100 ms. It is opened within 20 ms when the reading falls below 0.6 V. VIN is the reading times 44 (27 mV per count); the offset of the channel is stored at calibration. A VIN fault is reported as out of range (absent or reversed) or as over-voltage. | The DUT and the ampere pair on a supply outside 0.8 V to 5.0 V (R-09). The lower limit is 0.6 V because a true 0.8 V can read 0.67 V before calibration; an absent or reversed supply reads below 0.13 V (calculated). |
| F-27 | VIN_OV is an interrupt source. When it goes high the output switch is opened, GATE_AMP goes low and stays low for 5 ms or more, and the fault is reported. | The DUT: the detector holds the pair open in hardware (D-43), but when it releases while the request is still high the pair closes again without its ramp. |

#### Source

| Rule | Firmware | Guards |
| --- | --- | --- |
| F-28 | Start of the source, the only sequence. With PWR_GOOD valid, channel 7 in its window, the output pair and both mode pairs open and SMU_ON low: (1) the DAC to the code of 0.80 V; (2) 200 ms; (3) SMU_ON high; (4) 5 ms; (5) the DAC to the working value, 80 ms; (6) R3, the source pair closed; (7) 60 ms, then channel 0 within 100 mV of the set-point, or a fault; (8) the output pair closed, last. No other path sets SMU_ON. A unit test covers the sequencer. | The pre-regulator, which is never asked for less than 1.2 V and never enabled on a charged output capacitor: its bleeder needs the 200 ms. The 5 V rail, into which the converter would return that charge. The check of step 7 allows for the filter of channel 0, which is 43 mV behind after 30 ms (calculated). |
| F-29 | Stop: the output pair open (after F-31 when it applies), the source pair open, SMU_ON low, the DAC at zero. SMU_ON is never taken low while a path from the regulator output to a DUT is closed, except in F-7 and in a watchdog reset, where all lines fall together. | The linear regulator U18 with its input collapsing under a charged output. |
| F-30 | SET_VOLTAGE is limited to 0.80 V to 5.00 V in calibrated codes. Before calibration the output is 10 mV + code × 1.2817 mV. The set-point is calibrated at nine points or more, at room temperature. A set-point is reported as settled when three consecutive readings of channel 0 are inside the band, not after a fixed time. The DAC at zero with SMU_ON low is the idle state. | The DUT. The hardware ceiling is 5.26 V nominal and 5.39 V at the tolerance limits for any DAC frame (calculated, D-58); the limit of 5.00 V is firmware. The integral error of the DAC, 15.4 mV at its limit, needs the nine points (datasheet). |
| F-31 | Channel 0 more than 0.3 V above the DAC value for 100 ms with the output on: firmware writes the code of the reading minus 0.2 V (never above the code of 5.00 V), reports "DUT above the set-point" and follows the reading down in each monitor cycle until the set-point of the user is reached. A command opens no switch between the regulator output and the DUT while channel 0 is more than 0.3 V above the DAC value: first the DAC goes to the reading minus 0.2 V and 30 ms pass. Trips open at once. | The linear regulator against an output above its input, and the 5 V rail: it has no path back to the source and no clamp below 6 V, so a set-point must not fall faster than the rail absorbs what the pre-regulator returns. |
| F-32 | With the set-point unchanged for 100 ms, channel 0 more than 0.3 V below it for 20 ms is an overload: the output pair opens and the fault is reported. | The linear regulator and the DUT when the regulator limits below the trip level, beyond the curve of R-08 or with a constant-power load. |
| F-33 | In source mode the output pair opens within 0.5 ms of channel 0 crossing 5.3 V, read as the exception of F-10 allows, and an external voltage is reported. | The pre-regulator U16: above about 5.7 V a voltage on the terminal reaches its output through D11 and it pumps into the 5 V rail (estimate). The channel sees the terminal through its filter of 5.5 ms (R140, R149, C103): the rule covers a voltage that rises slowly (0.9 ms from 5.3 V to 5.7 V on the ramp of the output switch, calculated) and not a DUT plugged into the live output; no part covers that case (section 4.9). The user documentation states 5.5 V as the limit for a voltage applied to VOUT in source mode. |

#### Acquisition and Samples

| Rule | Program or firmware | Guards |
| --- | --- | --- |
| F-34 | Acquisition program: convert-start high for 108 clocks or more and still high at the end of the conversion; 16 clock pulses; 4 clocks or more between the last falling edge and the next convert-start; 16 clocks or more per bit at 100 kSPS (9.375 MHz or less) and 10 clocks per bit (15 MHz) for the 500 kSPS option; the load line of the registers low for 3 clocks or more; clock divider 1. The program never runs with PWR_GOOD low (F-3, F-7). | Converter data and side data in one sampling window: 16.9 ns at 15 MHz against two clocks, 13.3 ns (calculated). The conversion time of the ADC, 710 ns at the most (datasheet), against 720 ns. |
| F-35 | Seven samples are flagged invalid from the first sample whose range bits differ from the sample before; the count is a stored constant and every change restarts it. Samples are flagged for 5 ms when the supplying input changes or the 5 V rail steps by more than 0.3 V. A sample is flagged over-range when its code is 65535 or its CMP_JUMP bit is set. | The meaning of the samples while the chain settles (45 µs to 0.1 % of range, simulated) and while −4 V_A may leave regulation for milliseconds. |
| F-36 | A zero calibration waits for a stable channel 6, 5 s after PWR_GOOD at the most. Readings with the output open (start-up zero, CAL_ZERO, leakage) are taken 200 ms or more after GATE_OUT fell or after a reset. The zero with the output on and the terminals open is taken 300 ms or more after GATE_OUT rose. | The calibration on rails and gates that still move: +12 V_A creeps from 11 V to 12 V with 0.18 s, and the gate of the output pair decays with 31 ms (calculated). |

Rules for the host that follow from the same hardware (logic channels
invalid below 1.67 V of output voltage, samples after DUT power on marked
as settling, flagged samples filled in statistics) are in sections 4.8, 8
and 9. What these rules send to the host is not in the protocol of
section 7 yet: a mark for over-range and under-range samples (F-22,
F-35), the invalid mark for the 5 ms after a change of supply (F-35;
section 7.3 defines it for a range change only), the fault flags of
section 6.4 beyond the four of section 7.4, the input in use and the CC
class (F-14). Section 16 lists it as an open item.

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
| GET_STATUS | `0x02` | None | State, faults, dropped blocks, VOUT, VIN, the 5 V rail, temperature, power budget |
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
  nominal gain `VREF / (65536 × G × R[r])`. Nominal values: G = 19.93, and
  for R[r] the shunt with R0 in parallel, 1 kΩ, 31.95 Ω, 0.999 Ω and
  0.1 Ω (calculated, section 4.3).
- Storage: per-range gain and offset, DAC gain and offset, the settling
  window length and the calibration temperature, in the flash of the module,
  with a version field, a CRC, the 64-bit chip identifier of the RP2350 and
  the serial number and revision of the carrier, entered at calibration and
  written on the carrier (D-82, section 10.7). A missing or corrupt table
  falls back to nominal values and is flagged in GET_INFO. A record whose
  chip identifier does not match, a flash image copied to another module, is
  reported by GET_INFO as not calibrated; nominal values are then used and
  flagged. The carrier has no memory: a module moved to another carrier is
  not detected by firmware, and the host shows the stored carrier serial
  number at every connection for comparison with the label.
- Zero calibration: with the output switch open the current is zero, so the
  firmware measures the offset of every range (locked one by one). It runs at
  start-up and on CAL_ZERO, no earlier than 200 ms after the output switch
  was opened or after a reset (F-36), because the gate of that switch needs
  this time to rest (section 4.2). Run-time offsets are kept in RAM, not
  flash. The zero of R0 drifts by up to 0.7 nA/°C from the amplifier alone
  (datasheet maxima, calculated, section 4.5), so firmware takes the
  open-switch zero again whenever the output is off and the board temperature
  (monitor channel 5) has moved by more than 2 °C since the last one;
  CAL_ZERO does the same on request.
- Closed-switch zero (D-59): the open-switch zero does not see what loads the
  node after the shunts beyond the output switch. With the output on and the
  terminals open, at 5.0 V and at the working voltage, 300 ms or more after
  the output was switched on (F-36), the reading of R0 is stored and
  subtracted. The limit for a board is 50 nA at 5.0 V and room temperature;
  the typical figures add up to 4 nA to 6 nA at 40 °C (estimate, section
  4.3). The step needs the DUT disconnected once per calibration.
- Gain calibration: source mode into precision resistors (0.01 %), with VOUT
  read by a reference multimeter; two points per range, near 10 % and 90 % of
  full scale. It removes the tolerance of the shunts, 0.1 % to 0.5 % (D-68),
  the share of R0 in the higher ranges and, at the calibration temperature,
  the leakage across the ladder (section 4.3). What it does not remove is the
  drift with temperature: 25 ppm/°C for R0 to R2 and 50 ppm/°C for R3
  (datasheet values), which is why the calibration temperature is stored.
  After a reported sequencer fault (F-21) the gain of R2 is calibrated again:
  its 1 Ω shunt has carried 6.3 W to 8.4 W for up to 2 ms (calculated).
- DAC calibration: nine set-points or more, at room temperature, measured
  with the reference multimeter (D-58, F-30). Two points do not cover the
  integral non-linearity of the DAC, 15.4 mV at its limit and 2.6 mV typical
  (datasheet values, calculated), against the 10 mV criterion of section 11.
- Settling window: 7 samples by default (F-35; simulated: 45 µs to 0.1 % of
  range, 65 µs to 1 LSB, section 4.5), measured on the prototype with a fast
  load step, then stored as a constant.
- Output settling: for 250 ms after the output switch closes the samples
  read low by the charging current of its gate, 0.3 µA after 50 ms and
  4 nA after 200 ms (simulated). The time is a constant of the host, which
  marks these samples and leaves them out of statistics below 1 µA
  (section 9).

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
- Marks that follow from the hardware; the firmware rules behind them are in
  section 6.6:
  - Logic channels: with the jumper JP2 as built the eight logic bits are
    shown as invalid while the monitored output voltage is below 1.67 V (section
    4.8). A setting covers jumper position 2-3, where the VCC pin of the logic
    port supplies the translator. The channels are off by default.
  - Output settling: the samples of the first 250 ms after the output is
    switched on are marked and kept out of statistics below 1 µA (sections 4.2
    and 8). The time is a constant of the host.
  - Flagged samples (settling window of a range change, over-range, under-range)
    are not dropped: plot, mean, charge and energy use the first valid sample
    after them in their place (section 4.10).
  - The mean of 100 samples is offered in R0; it is the figure that the test of
    R-04 uses in source mode (section 11).
  - At every connection the host shows the serial number of the carrier that the
    calibration record holds, for comparison with the number written on the
    board (section 8).

## 10. PCB & Mechanical Guidelines

These are the guidelines for the carrier board of draft A2. The generator
of the project places the parts, and the board is routed automatically
with FreeRouting (D-86). A board made this way is a draft: section 10.8
names what has to be drawn and reviewed by hand before fabrication. No
figure in this section is a measurement; each is marked as a datasheet
value, a calculation, a simulation or an estimate, and the results of a
routing run are in [`../hardware/README.md`](../hardware/README.md).

### 10.1 Board and Floor Plan

- Four layers: signal, solid ground, power, signal. No ground-plane splits;
  partition by placement, with the switching converters and the controller
  module away from the front end.
- Layer use: the top layer carries all parts, the converter loops, the pours of
  the 1 A path, the sense pairs and the guard; the first inner layer is ground
  and stays solid; the second inner layer holds the pour of the 5 V rail, the
  rail trunks and ground fill; the bottom layer holds crossings, the second
  layer of pieces of the 1 A path and ground fill. All parts are on the top
  side: one stencil and one reflow pass.
- Build assumed until a manufacturer is chosen: 1.6 mm FR-4, 35 µm outer
  and 17.5 µm inner copper, about 0.2 mm of dielectric between an outer
  layer and its plane, vias tented, gold finish (ENIG) for flat lands and
  a guard ring that does not tarnish. Smallest clearance 0.127 mm, forced
  by the pad gap of 0.14 mm in the footprint of the 1 A transistors
  (library value); smallest track 0.15 mm; vias of 0.6 mm with a 0.3 mm
  hole for signals and 0.8 mm with 0.4 mm for power.
- Outline: 150 mm × 100 mm with a corner radius of 3 mm and four M3 holes,
  H1 to H4, 5.5 mm from both edges of each corner (D-85). The
  back is the left edge, with the USB connector of the Pico 2 and the
  USB-C power connector J2. The front is the right edge, with the
  logic port J5 and the DUT connectors J3 and J4 in the order
  of the PPK2 (D-44). The switching converters are in the left third, the
  front end right of center.
- No track on an outer layer within 4.0 mm of the center of a mounting
  hole, so that a metal spacer touches only the grounded pad.

The blocks, from the back edge to the front edge:

| Block | Where | Why there |
| --- | --- | --- |
| Controller | Top left, along the top edge | USB connector at the back edge; its resistors in the strips beside the two pin rows |
| Monitors | Top, at the far end of the module | Next to the SPI pins |
| Side data | Top, right of the monitors | Between the controller and the level translator |
| Logic inputs | Top right, at the logic port | Short lines from J5 to the translator |
| Reference | Above the left end of the shield can | At the converter, outside the can |
| Comparators | Above the shield can | Where the amplifier output leaves the can |
| Power input | Left, below the controller | From J2 to the right: limiter, multiplexer, bulk capacitor, supervisor, 3.3 V regulators |
| Pre-regulator | Left, below the power input | Away from the front end; its tracking amplifier at the end toward the regulator |
| Analog rails | Bottom left | Boost converter and charge pump at the back edge; +12 V regulator at the far corner of the block |
| Source meter | Bottom, left of center | DAC and set-point amplifier above, linear regulator below, next to the source pair |
| Front end | Right of center, under the shield can | Converter at the left end, shunts of ranges 0 to 2 at the right end |
| Gate drivers | Below the shield can | Short gate lines into the can and to the 1 A branch |
| 1 A branch | Between the shield can and J4 | Range 3 transistor and shunt, ladder clamps: wide pours, heat outside the can |
| Output switch | Above J4 | Last element before the VOUT terminal |
| Mode switches | Bottom band | Source pair at the regulator, ampere pair at the terminal block |
| VIN entry | Below J4 | Fuse and suppressor at the VIN terminal |

Distances that the placement keeps:

- U16, L2, U10, L1 and U11 at least 30 mm from the fence
  of the shield can.
- The +12 V regulator U13 at least 25 mm from L1, the diode D6, C27 and
  L2: it filters what the boost converter sends it.
- The linear regulator U18 at least 40 mm from the range 0 shunt R101
  and from the reference U12; the range 3 shunt R110 at least 15 mm
  from R101, with the wall of the can between them.
- The mode pairs side by side (Q4 with Q8, Q5 with Q9),
  the source pair next to the output pins of U18; Q15 next to
  Q16.
- The resistor pairs of the set-point path, R55 with R56 and R57 with
  R58, side by side in the same orientation, so that each pair sees one
  temperature (section 4.2).
- Clocked lines (acquisition, side data, logic inputs) stay in the top
  band and do not cross the shield can. The acquisition lines run over
  the ground plane beside the far end of the module and enter the can
  through one opening of its wall.

### 10.2 Controller Module and Connectors

- Controller module U1: on sockets, lying along the top edge with its
  USB connector at the back edge; no carrier parts under it; the front end
  right of center, away from it.
- Module footprint: a project footprint, the Raspberry Pi Pico footprint
  of the KiCad library with two rows of 20 holes 17.78 mm apart, without
  its antenna keep-out (D-85). The ground plane is closed under the whole
  module, between the acquisition pins and the SPI pins. A Pico 2 W fits
  the sockets, but no function uses its radio and the copper under its
  antenna is not cleared.
- The two sockets MP1 and MP2 are soldered into the holes of that
  footprint and the module is plugged into them; the sockets are 8.5 mm
  high (datasheet). The assembly data says so, because the module is the
  only footprint (D-82).
- Connectors on the carrier: USB-C J2 (power only); the two sockets of
  the Pico 2; for the DUT a 1×4 pin header J3 and a lever terminal
  block J4 in parallel, both GND, VIN, VOUT, GND; the 1×10 logic port
  J5 (VCC, GND, D7 to D0); a 3-pin console header J1.
- J4 has a project footprint with pads of 1.9 mm × 2.3 mm on its
  1.2 mm holes: an annular ring of 0.35 mm, and 1.6 mm between the pads of
  two poles (calculated; D-85).
- Legends on the silkscreen use the names of the PPK2 where the function
  is the same: GND, VIN, VOUT, GND at both DUT connectors; VCC, GND, D7 to
  D0 at the logic port. Every test point carries its net name, the two
  solder jumpers their function, and the terminals their limits (VOUT
  0.8 V to 5 V; VIN 0.8 V to 5 V, 20 V at most). No silkscreen over pads,
  over the guard ring or between the pads of the DUT connectors.

### 10.3 Measured Node, Guard and Shield

Every current that leaves the copper after the shunts without going to the
DUT is read as DUT current; in range 0 a leak of 1 nA is 1 µV across the
shunt. That copper, the measured node, is VOUT and the ladder output, the
sense nodes of the three switched branches with their Kelvin taps, the
amplifier inputs and the input of the guard buffer. The supply node of
the ladder is on the other side of the shunts and within the burden
voltage of the measured node: it is a harmless neighbor.

- Guard ring driven by the buffered ladder output (section 4.8) through
  R119, around the range 0 sense node, the multiplexer pins of the sense
  nets, the Kelvin pairs and the amplifier inputs. It is a closed track of
  0.5 mm on the top layer; no solder mask over the guard; clean flux
  residue. The free top copper inside the ring is a pour on the guard
  net; no ground pour and no foreign net inside the ring. TP40 is its
  test point, outside the can.
- The guard is on the top layer only. The ground plane under it is not
  cut: the leakage through 0.2 mm of laminate to the plane is tens of
  picoamperes (estimate with an assumed volume resistivity of
  10¹³ Ω·cm).
- Surface leakage into the measured node is 1.3 nA to 2.9 nA (estimate
  for a clean board with 10¹¹ Ω per square), against the 10 nA of the
  leakage budget (section 4.3). About four fifths of it sit between
  neighboring pads of one package, at U24, U25, Q15 and Q16,
  where no guard fits: cleaning decides, and flux residue or moisture can
  raise the figure a hundredfold. The board is washed after reflow and
  after every rework near the can, and the cover goes on afterward.
- Outside the can the ground fill of an outer layer keeps 1.0 mm from the
  pours of the measured node; its neighbors are the pour of the supply
  node and bare laminate under solder mask.
- No via on a sense net or on a guarded net. Gate lines reach a transistor
  from the side of its gate pin and do not run along the measured node;
  the gate node of the output switch behind its 2.2 MΩ resistor keeps
  2 mm from VOUT copper except at the gate pins.
- Kelvin routing as a tightly coupled pair from each shunt to the
  multiplexer U24 and from there to the amplifier U27: tracks of
  0.2 mm with a gap of 0.2 mm, on one layer, equal in length within 1 mm,
  without a via. R110 is a four-terminal part; R107 is a two-terminal
  chip on a four-pad Kelvin land, where each end cap bridges the force
  pad and the sense pad of its end; R101 and R104 are sensed at their
  pads, the tap leaving the pad as its own track. The ladder clamps
  Q10 and Q11 and the idle resistor R90 connect to the force
  copper, never to a sense track.
- Shield can: a two-piece can, frame SH1 of 44.0 mm × 30.5 mm soldered
  on ground and cover MP3 pressed on by hand, 3.2 mm high when
  assembled (datasheet; D-85). It covers the shunts of ranges 0 to 2 with
  their transistors, the multiplexer, the amplifier with its pedestal
  buffer, the ADC driver with its rail buffer, the ADC and the guard
  buffer: 58 parts, none of which dissipates more than a few milliwatts.
  The clearance under the frame is 2.8 mm (calculated) for parts of at
  most 1.75 mm.
- Outside the can: the 1 A branch of the ladder (Q14, R110) with the
  ladder clamps, the gate drivers, the reference, the comparators, every
  test point and every connector. The 1 A branch needs wide pours and is
  the heat source that has to stay away from range 0; its signal of
  100 mV across 0.1 Ω gains nothing from a shield.
- Between the feet of the frame the wall has openings 3.0 mm wide and
  0.5 mm high (datasheet), with 2.2 mm between the lands. Tracks cross
  the wall only through these openings, on the
  top layer under solder mask; the rails come up through vias inside the
  can; the pours of the 1 A path do not cross the wall. One ground via
  sits beside each land of the frame.

### 10.4 The 1 A Path

- The path from the linear regulator U18, or from the VIN pole of
  J4, through the mode pair, the supply node, Q14, R110 and the
  output switch to the VOUT pole is drawn as pours on the top layer, 4 mm
  to 8 mm wide, not as tracks. Target: 30 squares of copper or less in
  either mode, which is 15.9 mΩ at 40 °C with 35 µm copper (calculated)
  and leaves 4 mΩ of the 20 mΩ that the budget of R-06 gives to copper
  and contacts (D-64).
- Three pieces may be doubled on the bottom layer through groups of four
  or more vias, because their ends are through-hole pads or wide pours:
  the band of the supply node, the neck to the VOUT pole and the copper
  from the VIN pole to the fuse F1. No thermal relief on a pad of
  the path.
- The path drop of R-06 is taken at the poles of J4; the pin header
  J3 is fed from the same pours and adds its own contacts.
- VIN copper ahead of the ampere pair may carry −20 V to +20 V (D-60):
  it stays outside the shield can and keeps 1.0 mm from every other net.
  F1 and the suppressor D14 stand at the terminal block.
- The suppressor D21 stands between the rear pads of the VOUT pole and the
  neighboring ground pole of J4, 4.3 mm from pad edge to pad edge and 6 mm
  between pad centers, the least that the courtyard of the terminal block allows
  (calculated), its cathode on at least 1 cm² of VOUT copper and its anode on a
  short track to the ground pole.
- The damped branch R87 with C63, the capacitor C62 and the idle
  resistor R90 stand where the supply node enters the ladder, at the
  ampere pair.

### 10.5 Switching Converters

Every loop named here closes on the top layer without a via; the ground
plane under the three parts is solid; a rail enters and leaves a stage at
its capacitor, not at the pin; no track of another block passes under
these parts.

- Pre-regulator U16 (2.4 MHz, switch limit 4 A, datasheet): L2 within
  3 mm of the switch pins, the two switch nodes as short pours from pad to pad;
  input capacitors C39 and C40 and output capacitors C42, C45 and C50 each
  in a loop of 5 mm or less to the power ground pad; six vias in that pad; the
  feedback line from the tracking amplifier U19 20 mm or less, away from
  L2. The copper from the output capacitors to the bead FB1 is a pour of
  15 mΩ or less (section 4.2); as a pour of 4 mm over about 43 mm it has 6 mΩ at
  40 °C (calculated).
- Boost converter U10 (1.6 MHz, datasheet): the loop of switch pin,
  diode D6, C25 and ground pin within 5 mm, C27 beside C25; the
  feedback parts on the side of the feedback pin, away from the switch
  copper. The boost output reaches R37 at the +12 V regulator as one
  track of 25 mm or more, whose inductance is part of the filter.
- Charge pump U11 (2 MHz, datasheet): C21, C19 and C22 within
  2 mm of their pins, short and wide.
- +12 V regulator U13: its input capacitor C29 behind R37; the output
  sense pin routed to the pad of the output capacitor C31; a guard track on
  +12 V_A around the copper of its SET pin.
- Reference U12: its output is the star point of the reference net. The
  branches to the ADC U30, to the divider of the DAC, to the monitor
  converter U40 and to the dividers of the thresholds and of the pedestal
  start there and share no track (section 4.6).

### 10.6 Thermal Points

- Linear regulator U18: 0.82 W typical and 1.02 W at the limits at
  0.8 V and 1.0 A, and 1.5 W to 2.0 W in a sustained short circuit
  (calculated). Its exposed pad is the output, not ground. It sits on an
  island of output copper of at least 15 mm × 15 mm on the top layer and
  the same on the bottom layer, joined by vias in and around the pad that
  pass the inner layers without a connection; the datasheet gives 65 K/W
  for 225 mm² of top copper.
- The heat of the linear regulator and of the range 3 shunt is kept from
  range 0 and from the reference by distance (section 10.1) and by the
  wall of the can; no slot is cut into a plane.
- The temperature sensor U39 stands within 5 mm of U18, at the edge
  of the island, with its ground pin on vias into the ground plane. It
  reads the board at the regulator, not the shunts.
- Current limiters U4 and U3: thermal pad into the ground plane
  through the vias of the footprint; U4 dissipates 0.33 W at 1.70 A,
  a rise of 18 K (calculated).
- R110: 0.10 W at 1 A (calculated), spread by the pours at its pads.
- Q15: about 25 mJ and 3.5 W for milliseconds each time the output is
  switched on into a capacitive DUT (simulated); the pours of the path
  are its heat sink.
- Ladder clamps Q10 and Q11: no dissipation in normal use, 8 W to
  11 W if they conduct 3 A to 4 A (calculated); drains side by side on at
  least 1 cm² of supply-node copper.
- Thermal reliefs only on the ground pads of through-hole parts, so that
  an iron can solder them.

### 10.7 Test Points, Fiducials and Assembly

- Test points on every rail, comparator output and range gate, and on the
  nodes that the bring-up needs: the stages of the power input, 5V_OK,
  PWR_GOOD, VREF and the reference of the DAC TP19, the enable of the
  pre-regulator TP18, its feedback pin, the input, output and SET pin
  of the linear regulator, the gates of both mode pairs and of the output
  switch, the detector output, the amplifier output, the ADC input and
  its driver rail, and the DUT-side supply of the translator TP48.
  They are round pads of 1.5 mm: 40 on signals and three on ground.
- A probe ground within 5 mm of every test point. Five square ground pads
  of 2 mm, TP15, TP25, TP20, TP28 and TP29, stand at the
  boost converter, the linear regulator, the pre-regulator and the two
  mode pairs; square, so that ground is told from a signal by its shape.
  The test points along the shield can use its fence as probe ground.
- No test point on a switch node, and only one on the measured node:
  TP38 on VOUT, 3 mm or more from any other pad. The acquisition lines
  are probed at the resistor arrays RN4 and RN5.
- TP9 on 5V_OK holds the whole carrier off when it is clipped to
  ground: it is the switch of the first power-up. The links of the first
  power-up, L1, R37, R31, R27, R61 and FB1, stand
  where an iron reaches them, none under the can. Without R61 the
  Schottky diode to ground holds the output of the linear regulator;
  without FB1 the regulator runs from its control supply alone.
- Three fiducials FID1 to FID3, 1 mm of copper in a mask opening
  of 2 mm, at three corners of the top side; the fourth corner stays
  empty so that the board cannot be turned. No tooling holes.
- The leadless packages and the thermal pads cannot be soldered with an
  iron alone: a paste stencil for the top side is part of an order.
- The carrier has no memory (D-82): a frame on the silkscreen takes a
  hand-written serial number.

### 10.8 Automatic Placement and Routing

The generator places every part from the netlist: the connectors, the holes, the
fiducials and the frame of the shield can at fixed coordinates, every other part
in the area of its block, each decoupling capacitor at the pin it serves and
parts turned toward their connections. FreeRouting then connects the pads, with
the track widths and clearances that the net classes of the board file give it
(D-86). The result is a board file to inspect and a starting point for a
layout; the connections that a run leaves open are among its figures. It is
not a reviewed layout, and it is not to be fabricated as it is. An autorouter
connects pads. It does not do the following, and a layout review does each of
them by hand before fabrication:

| An autorouter does not | What the review draws or checks | Section |
| --- | --- | --- |
| Draw pours | The 1 A path as pours with the count of squares; the output island of the linear regulator; ground fills and their vias | 10.1, 10.4, 10.6 |
| Know the measured node | Guard ring with its mask opening, guard pour, no foreign net inside the ring, 1.0 mm from ground fill to the node | 10.3 |
| Couple sense tracks | Kelvin pairs and amplifier inputs as pairs of equal length on one layer without vias; taps that leave a shunt pad separately from the force copper | 10.3 |
| Minimize loop area | The loops of the pre-regulator, the boost converter and the charge pump on the top layer without vias; star routing of the reference | 10.5 |
| Respect a wall | Tracks cross the shield can only through the openings of its frame | 10.3 |
| Place vias for heat or current | Vias in thermal pads, groups of vias in the 1 A path, a via at every land of the can | 10.3, 10.4, 10.6 |
| Keep distances that are not net-class rules | The gate node of the output switch 2 mm from VOUT; converters 30 mm from the can; VIN copper 1.0 mm from pads of other nets | 10.1, 10.3, 10.4 |

Exit check before a board is ordered: the electrical rules check of the
schematic and the design rules check of the board with schematic parity
report nothing, no connection is open, the distances of section 10.1 are
read on the board, the squares of the 1 A path are counted from the
plotted copper, and a 1:1 print is compared with the module on its
sockets, J2, J4, the frame of the can and one of the 1 A
transistors.

## 11. Verification Plan

Nothing in this table has been run. The pass criteria are the figures of
section 2 and the calculated or simulated figures behind them; where a
criterion is a range, it is the calculated tolerance of the parts.

| Requirement | Test | Pass criterion |
| --- | --- | --- |
| R-01, R-02 | 10 minute capture, check sample index | No gaps, dropped count zero |
| R-01 | Capture a 1 kHz reference sine, FFT | Sample rate within 100 ppm (crystal of the module: 65 ppm worst case), no jitter spurs |
| R-04 | Noise in R0 at full bandwidth, output open and with a 1 MΩ load, then with 100 nF and with 1 µF at the terminals; in ampere mode from a battery and in source mode | RMS noise at or below 5 nA in ampere mode; in source mode at or below 40 nA, and 5 nA for the mean of 100 samples |
| R-04 | Closed-switch zero: output on, terminals open, 5.0 V; at room temperature and at 40 °C to 50 °C | At or below 50 nA at room temperature; repeated within 1 nA; value and drift at temperature recorded |
| R-05 | Precision loads at 10 points per range | Within the accuracy target |
| R-05 | Leakage across the ladder at 100 mV and 40 °C with every gate low, from the supply node (TP33) to the node behind the shunts | At or below 100 nA |
| R-05 | Gain and zero of each range at 20 °C and at 40 °C | Change within the budget of section 4.10 |
| R-05, R-13 | Output shorted at the terminals, 0.9 A to 1.2 A forced: amplifier output (TP44) against a reference shunt; current at which the over-current comparator (TP46) and the jump comparator (TP45) switch | Amplifier linear up to the full scale of R3; over-current level between 1.114 A and 1.187 A |
| R-06 | Drop from the supplying node (VIN terminal, or regulator output at TP26) to the VOUT terminal at 1 A, at the lever terminal block J4, in both modes; drop across the shunt | At or below 200 mV in both modes; at or below 100 mV across the shunt |
| R-07 | Load step 1 µA to 500 mA, edge 100 ns or faster; 1 µF effective at the test voltage (C0G, film, or an X7R part whose capacitance was measured at that bias; 0.9 µF to 1.1 µF) at the DUT connector on leads under 20 mm; at 0.8 V, 3.3 V and 5.0 V; in source mode, and in ampere mode with at least 47 µF of low-ESR capacitance at the VIN terminals; differential measurement from the supply node (TP33) to VOUT | Drop at most 0.5 V; above 0.2 V for at most 1 µs; within 50 mV of its final value 5 µs after the step |
| R-07 | Same step with 10 µF effective (9 µF to 11 µF) | Drop at most 0.25 V; within 50 mV of its final value 10 µs after the step |
| R-07 | Step down from R3 at 59 mA, no capacitor at the terminals, at 5.0 V in source mode and in ampere mode with the supply just below the level at which the detector of VIN opens the switch; step-up comparator (TP47) recorded | One change of the range bits, no step back up |
| R-07 | Slow ramp across every threshold | No oscillation between ranges |
| R-08 | Sweep 0.8 V to 5.0 V at 0 A, at 0.1 A and at the current of the R-08 curve (1.0 A at 2.0 V, 0.83 A at 3.3 V, 0.6 A at 5.0 V), warm, on several units | Set-point error within 10 mV plus sag at the calibration temperature; no overload reported on the curve |
| R-08 | 1 A at 5.0 V | Recorded as a check of typical parts; no criterion |
| R-09 | Ampere mode from an external supply of 0.8 V, 3.3 V and 5.0 V: the load points of the R-05 test and the drop test of R-06 | Within R-05 and R-06; current taken from the supply ahead of the shunts recorded (at 5.0 V: 35 µA with ampere mode off, calculated, and about 125 µA with it on, simulated) |
| R-10 | Square wave on D0 to D7 at 10 kHz, at logic levels of 1.70 V, 3.3 V and 5.0 V | Edges aligned with current within 1 sample; below 1.67 V of output voltage the logic channels are marked invalid |
| R-13 | Reversed supply of 1 V, 5 V and 20 V on VIN from a supply set to 5 A, 10 min each: instrument off, idle, and with source mode running at 5 V | Less than 1 mA at the terminal; TP33 and VOUT unchanged; ampere mode refused, fault VIN out of range; nothing to replace |
| R-13 | 6 V, 12 V and 20 V on VIN in the same three states | Switch stays open, fault VIN over-voltage; less than 1 mA; nothing to replace |
| R-13 | Ampere mode at 5.0 V and 0.5 A, supply raised slowly to 6 V and lowered again | Switch opens between 5.41 V and 5.51 V, fault reported; the detector output (TP30) releases between 5.30 V and 5.40 V |
| R-13 | Short circuit at the end of 1 m of cable from the on state: source mode at 5.0 V; ampere mode from a 5 V supply of 10 A or more through leads of 0.5 m and of 2 m | Trip, fault reported; VOUT above −2.5 V; in ampere mode TP33 below 11.5 V and TP27 below 36 V; terminal leakage unchanged afterward; no damage |
| R-13 | DUT power on into 100 µF, 1000 µF and 1800 µF at 0.8 V, 3.3 V and 5.0 V in both modes; 2200 µF recorded | No trip, no overshoot, peak below 1.0 A |
| R-13 | DUT power on into a short circuit | Trip near 1.15 A after about 7 ms; fault reported |
| R-13 | Step to 1.0 A with 10 µF to 100 µF at the DUT: source mode, and ampere mode with 100 µF at the VIN terminals | No trip; over-current comparator (TP46) high for less than 10 µs |
| R-13 | Pulse series, 100 times each, in source mode at 5.0 V unless stated: hot plug of a discharged 100 µF capacitor in range 0 and in range 2; short circuit at the terminals in range 0 and in range 2; a 100 µF capacitor charged to 5.0 V connected to the output at 0.8 V | No damage; leakage across the ladder at 100 mV and the gain of R2 and R3 within 0.1 % of the values before the series |
| R-13 | Reverse current of 100 mA and of 2 A from VOUT to VIN in ampere mode (F-22) | Samples flagged; range 3 within 2 ms; fault and open output within 0.2 s; no damage |
| R-13 | Source mode at 0.8 V: a 5.0 V source connected to VOUT and removed; then an external voltage raised slowly through 5.3 V, not above 5.5 V (F-31, F-33) | Set-point follows within 100 ms; the 5 V rail (TP6) moves less than 100 mV; output switch open within 0.5 ms of 5.3 V; no damage |
| R-13 | Source mode at 5.0 V, then ampere mode from a 0.8 V supply that cannot sink current (F-25) | The ampere switch closes only when the supply node reads below VIN + 0.1 V or below 0.3 V; the VIN terminal rises by less than 0.1 V; fault after 3 s otherwise |
| R-13 | Instrument off with 5.0 V on VOUT; 15 V on VOUT with the output off | Below 1 µA into the terminal; no damage |
| R-13 | Processors halted with a path closed; restart through the watchdog and into the boot loader (F-8, F-9) | Output open within 100 ms; every gate line low across the restart |
| R-13 | Source mode at 0.8 V and 1.0 A until the board temperature settles, case temperature of U18 recorded; then the thermal limit of firmware set below the reading | Thermal resistance on this board recorded; output opens and the thermal fault is reported (F-15) |
| R-13 | PWR_GOOD (TP17) at start and at stop, with C32 to C34 fitted | One edge per event, no burst of edges |
| R-14 | Sources defined by voltage and series resistance (5.1 V with 0.15 Ω, 4.75 V with 0.25 Ω, a 0.5 A port) that advertise 500 mA, 1.5 A and 3 A; a 5 V and 1 A load step on a source limited to 0.75 A, 1.0 A and 1.6 A | Budget respected in steady state; a load step beyond what the source delivers ends in a reported fault, power limit (F-14) or carrier supply (F-7), whichever acts first: pre-regulator off within 0.1 ms of the rail passing 3.9 V, controller not reset, carrier back 0.2 s to 0.45 s after the rail has recovered |
| R-14 | Start from a supply limited to 0.7 A, through the USB connector of the module alone | One start, no repetition; boost output (TP13) between 13.0 V and 14.1 V; PWR_GOOD high |
| R-14 | Hot plug of a live 5.25 V and 5.5 V source into the USB-C connector through a short cable | TP1 below 12.5 V; the 5 V rail (TP6) never more than 0.1 V above the source |
| R-14 | Data cable of the module plugged again after 1 ms and after 3 ms, 5.25 V and 5.5 V source, short cable (0.3 µH) | TP4 below 6.0 V |
| R-14 | USB-C cable pulled with both cables in, at idle and at 0.3 A of output current | Carrier restarts on the other input; port current at or below 0.9 A once the limiter acts, the pulse before it and the edges of SRC_ST (TP5) recorded |
| R-14 | 5 V rail lowered to 4.25 V with 17 mA of load on the −4 V rail | −4 V rail (TP12) in regulation |
| R-17 | Run every continuous integration workflow on the release commit | All jobs pass, coverage at or above the gates of section 18 |
| R-17 | Run the shared protocol vectors through the firmware and host codecs | Byte-for-byte agreement in both directions |

Notes on the tests:

- R-04. The limit in source mode follows from the noise of the regulator
  across the 1 kΩ shunt (section 4.10); the simulated figure is 26 nA to
  27 nA. The closed-switch zero is also the release test for the
  suppressor D21, whose leakage at 5 V has no datasheet figure
  (section 16).
- R-05 and R-13, shorted output. Until this test has a result, R3 above
  1 A, the over-current level and the jump level are specified for an
  output voltage of 0.2 V or more (section 4.10).
- R-06. The criterion is defined at the lever terminal block; the pin
  header J3 adds two mated contacts. The margin is 19.5 mV at the
  bounds of the calculation, and it is lost if copper and contacts pass
  about 44 mΩ.
- R-07. The drop is measured between the supply node and VOUT, so the
  response of the regulator or of the external supply is not part of it.
  In ampere mode the leads of the supply add a dip of their own, hence the
  capacitor at the VIN terminals.
- R-07, step down. The simulated worst case is 5.5 V (section 4.4). No
  mode reaches it: the set-point ends at 5.00 V (F-30), and the detector
  of VIN opens the ampere switch at 5.41 V to 5.51 V.
- R-08. The curve is published as guaranteed only after this test. Over a
  change of 40 °C the set-point moves by up to 10 mV more at 5 V (two
  resistor pairs of 25 ppm/°C, calculated).
- R-13, VIN. The supply is never set above 20 V: above 22 V the suppressor
  D14 is lost, and the fuse F1 does not protect it.
- R-13, DUT power on. The largest capacitance that starts without a trip
  is about 2200 µF nominal (simulated); it moves with the transistors of
  the output pair and with the +12 V_A rail, so 1800 µF is the figure with
  a capacitor tolerance of 20 %.
- R-13, PWR_GOOD. The flag does not watch the 3V3_C rail; a test of the
  flag says nothing about that rail.
- R-14. If the start from 0.7 A repeats or hangs, the detector position
  U9 at the enable pin of the boost converter is fitted. If TP4
  passes 6.0 V, the damper R14 with C5 is fitted. The peak at the
  USB-C connector is up to 11.4 V with a 5.25 V source and 12.2 V with
  5.5 V (simulated); the current limiter behind it is rated for 21 V.

## 12. Repository Structure

```text
hardware/     KiCad project of the carrier board (kicad/), the draft in
              pictures with its bill of materials (doc/), simulations
              and fabrication outputs (both empty in draft A2)
firmware/     Firmware project, one directory per component of section 6.1
host/         Python package: protocol, transports, device client,
              capture, simulator, command line (viewer and analysis are
              not written)
protocol/     Protocol definition, generator and shared test vectors
docs/         This specification, component checks, test reports, and the
              pages for the protocol reference and the calibration
              procedure (both not written)
tools/        Calibration and production-test scripts (not started)
```

## 13. Development Phases & Exit Criteria

1. Risk prototypes. On a Pico 2 with an ADC evaluation module, exit:
   firmware ported to the Pico SDK; ADC captured through PIO and DMA at
   100 kSPS (and 500 kSPS) for 10 minutes with no lost samples; side data
   read in the same word; reaction time of a PIO state machine to an input
   edge measured, with 100 ns or less from the pin of the jump comparator to
   the gate line of range 3 (F-16), on which the limits of R-07 rest (D-65);
   USB throughput of at least 500 kB/s sustained; CPU load recorded.

   On an evaluation module of the pre-regulator with the tracking
   amplifier, its sense network and the linear regulator on an adapter
   (D-55), exit: a load step of 0 A to 0.6 A in 1 µs at 0.8 V, 3.3 V and
   5.0 V of output and 4.25 V, 5.0 V and 5.5 V of input moves V_PRE by
   less than 100 mV and rings for no more than two cycles; a short circuit
   and the recovery from it, and the enabling of the converter with its
   output capacitors charged, end without a latched state; the 5 V rail
   moves by less than 50 mV when a 5.0 V source is pulled off a 0.8 V
   set-point and when the converter is enabled 100 ms after it was
   disabled, and by less than 100 mV on a short circuit at an unloaded
   5.0 V output. Every figure of section 4.2 on the stability of this loop
   and on the charge it returns to the 5 V rail comes from a behavioral
   model; this prototype is the gate before the carrier board is ordered.

   On the boost converter with 10 µF at its output, exit: the start from a
   supply limited to 0.7 A recorded, since the converter has neither an
   under-voltage lock-out nor a soft start; the result decides whether the
   detector position at its enable pin is fitted (D-84).
2. Analog front end with one fixed range on a test board. Exit: noise in
   both modes (from a battery, and behind the linear regulator, R-04 and
   D-59), offset, drift and settling measured and the budget of section
   4.10 updated; settling window confirmed with a fast load step
   (7 samples by default); linear range of the amplifier near full scale
   with the output below 0.2 V measured; leakage of the suppressor of VOUT
   at 5 V measured at 25 °C and at 40 °C to 50 °C; oversampling decision
   taken.
3. Shunt ladder and range logic. Exit: verification tests for R-06 and R-07
   passed; programs of the range sequencer verified in an emulator and on
   the controller; leakage across the ladder at 100 mV and 40 °C measured
   against 100 nA; pulse series of section 11 passed; time for which the
   over-current comparator stays high after a load step measured with supply
   leads of 1 m in ampere mode, and the qualification time of the trip
   (12 µs by default, F-18) confirmed; reverse-current test passed.
4. Source mode and power. Exit: tests for R-08, R-09, R-13 and R-14
   passed; the current curve of R-08 confirmed warm on several units, the
   condition for publishing it as guaranteed (D-56); thermal measurements
   at 1 A and in a sustained short circuit recorded (1.5 W to 2.0 W in
   the linear regulator, calculated).
5. Carrier board, revision A, with the Pico 2 plugged in. Entry: the open
   checks of section 16 that precede fabrication are closed, and the
   layout is reviewed (D-86). Exit: first power-up done in the order
   below; full verification plan executed, issues listed.
6. Calibration, protocol freeze and host software. Exit: R-05 and R-15
   demonstrated end to end.
7. Revision B and release: sources, documentation and test reports
   published.

Firmware and host software start in phase 1 and grow with each phase; the
protocol of section 7 is implemented from the first prototype.

First power-up of a carrier board. The order is reasoned from the netlist,
not tried. Six parts are links and are not fitted at the start: L1,
R37, R31, R27, R61 and FB1. The Pico 2 is out of its
sockets. The test point TP9 of the supervisor output is the switch:
held to ground, nothing but the boost converter can run (D-48).

1. 5 V from a current-limited supply with TP9 held low: only the 5 V
   rail is present. Released: 3V3_C and 3V3_A at once, or 0.18 s to 0.42 s
   after the 5 V rail came up if that time has not passed, because the
   test point holds the output of the supervisor and not its timer;
   PWR_GOOD (TP17) low.
2. R31 fitted: the reference reads 2.5 V at TP14; PWR_GOOD low.
3. L1 fitted, TP9 held low: the boost converter alone,
   13.0 V to 14.1 V at TP13.
4. R37 fitted, TP9 released: 12.0 V at TP16; the −4 V rail
   rests at about +0.24 V in its clamp diode D8; PWR_GOOD low.
5. R27 fitted: −3.91 V to −4.05 V at TP12; PWR_GOOD high about 24 ms
   after the supervisor output.
6. R61, then FB1: without R61 the diode D12 holds the output
   of the linear regulator at ground, and without FB1 the regulator
   runs from its control pin alone. Then the Pico 2.

To hold the boost converter off for a step, its enable pin is tied to
ground; R29 limits the current to 0.1 mA. The levels above are calculated
or simulated. No DUT is connected before the items of section 16 that are
marked for it are done.

The schematic of the carrier board exists as draft A2, drawn ahead of
these phases (D-37), with a board whose parts are placed by a script and
whose tracks come from an autorouter (D-86), which left 28 of the 984
connections open. The draft is the hypothesis that the phases test: the
checks of section 16 and the results of phases 1 to 4 change it, and the
open connections are closed and the layout is reviewed before revision A
is fabricated in phase 5.

## 14. Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Timing of the PIO capture does not match the ADC interface | No hardware-timed capture | Phase 1 prototype; the program places every edge on a cycle of the system clock |
| Side data and conversion result misaligned | Wrong range per sample | One state machine reads both into one word; load pulse at the convert-start edge |
| USB Full-Speed throughput too low | R-01 not met | 3-byte packing; larger writes; last resort lower rate |
| Up-range too slow, DUT brown-out | R-07 not met | Jump-up comparator; 0.12 µs time constant at the amplifier input; sequencer reaction of 100 ns or less as a requirement (F-16), measured in phase 1; R-07 stated as a drop figure (D-65); DUTs with less than 1 µF at their supply are documented |
| Range oscillation at thresholds | Unusable data near thresholds | Wide hysteresis, firmware-only step down, step-up comparator ignored for 2 µs after a range change (F-17), ramp test |
| Leakage and offset dominate R0 | R-04, R-05 not met | Guarding, low-leakage parts, zero calibration with the output switch open and closed, temperature record |
| Suppressor of VOUT D21 leaks more than its typical figure (guaranteed: 100 nA at 15 V and 25 °C only) | Zero of R0 moves with temperature by more than R-04 allows | Closed-switch zero on every board with a limit of 50 nA; leakage at 5 V at 25 °C and at 40 °C to 50 °C measured before the budget is published (section 16) |
| Leakage across the ladder above 100 nA at 100 mV (three range switches, two clamp transistors; no datasheet bound at that voltage) | Gain of R0 drifts with temperature | Measured in phase 3; one clamp can be left out (Q11 with R100); gain calibration removes the constant part |
| Zero of R0 drifts with the amplifier (up to 0.7 nA/°C, datasheet limits, calculated) | Readings near 100 nA off by several nanoamperes after a temperature change | Open-switch zero repeated when the output is off and the board temperature has moved by more than 2 °C (section 8); budget of section 4.10 |
| Noise in source mode above the 27 nA predicted from a typical figure | R-04 criterion of 40 nA not met | Measured in phase 2; mean of 100 samples; a quieter source stage would be a design change |
| Amplifier leaves its linear range near full scale with the output below 0.2 V | Top of R3 compressed; trip at up to about 1.26 A instead of 1.15 A (estimate) | R3 above 1 A and the trip level specified for 0.2 V or more; measured before the layout is frozen (section 16); the short-circuit current is bounded by the qualification time, not by the level |
| LDO or shunt overheating | Drift, shutdown | Split LDO supply, tracking pre-regulator that folds back in a short circuit, current curve of R-08 (D-56), thermal limit in firmware (F-15) |
| Head room of the linear regulator at 5.0 V: 2 mV of margin at the tolerance limits (calculated, dropout limit interpolated) | Output sags at the end of the R-08 curve | The curve is a design figure until measured on several units; copper from the output capacitors of the pre-regulator to FB1 at or below 15 mΩ; fallback: a flat 0.6 A |
| Pre-regulator returns charge to the 5 V rail, which cannot absorb it | 5 V rail above the 6 V rating of the 3.3 V regulators | Tracking of the regulator output with a slow fall and a fast rise (D-55); 10 ms set-point filter (D-58); 22 µF at the regulator output and a bleeder on V_PRE (D-57); start sequence in firmware (F-28); open: the rail has to consume 0.25 W or more in source mode; prototype in phase 1 |
| Model of the pre-regulator rests on assumptions (loop compensation, operation below its minimum duty cycle, current limit below 1.2 V, negative current limit, over-voltage behavior) | Loop unstable or fold-back different on the board | Phase 1 prototype as a gate before the board is ordered |
| External voltage above about 5.7 V on the live source output reaches the pre-regulator through D11 | Pre-regulator destroyed, 5 V rail lifted | Firmware opens the output switch within 0.5 ms of 5.3 V on the VOUT monitor (F-33), which covers a slow rise and not a step; 5.5 V stated as the limit in the user documentation; no part bounds it |
| Switching noise in the measurement | Noise above budget | LC filters, placement, shield, converter frequency above 1 MHz |
| USB source too weak | Brown-out of the instrument | CC detection, input current budget per source, monitor of the 5 V rail; in hardware a current limiter at each input and a supervisor that switches the pre-regulator off below 3.9 V (D-47, D-48, D-49) |
| A dip of the 5 V rail below 3.9 V, or the USB-C cable pulled while the data cable stays | Carrier restarts; the DUT loses its supply for 0.3 s to 0.7 s | Accepted and documented; the controller and the USB link stay up and report the loss of the carrier supply (F-7) |
| A weak USB-C source (about 3 V to 4.1 V) keeps the carrier off although the computer port is good; firmware cannot read the cause | Instrument does not start, no hint | User documentation; PWR_GOOD low is reported |
| Boost converter starts on an input limited to 0.67 A to 0.85 A without under-voltage lock-out or soft start | Start hangs or repeats on the data cable alone | Measured in phase 1; position for a voltage detector at its enable pin (U9, not fitted, D-84) |
| Inputs of the input multiplexer come within 25 mV to 85 mV of their 6 V absolute maximum when the data cable is plugged again (simulated) | Multiplexer stressed at every plug | Position for a damper on that input (R14, C5, not fitted, D-84); measured with a short cable (section 16) |
| In-rush of the carrier on the USB port of the computer | The port shuts down at plug-in | 10 µF or less directly at each connector; ramps of 0.3 A to 0.9 A and a hardware limit of 0.85 A on the computer port (D-47); the 50 µC of the USB in-rush test is not met (the carrier adds 0.3 mC to 0.8 mC to the 0.12 mC of the module, simulated); check of section 16; the jumper can be cut and the USB-C input used |
| PWR_GOOD does not watch the 3V3_C rail | A weak logic rail shows as data errors, not as a supply fault | Stated in section 4.11; the self-test does not claim to cover that rail |
| Candidate part unsuitable or unavailable | Redesign | Section 16 checks first; second sources named for passives, diodes, the reference and the regulator grades; stock read on 2026-10-09; parts with long lead times bought with the first order |
| Parts without a released part of another maker: every integrated circuit except the ESD arrays, the transistors CSD17577Q3A and IRLML0030, the 1 A Schottky diode, the suppressor of VOUT, the ferrite bead, the 0.1 Ω shunt, the lever terminal block; the boost inductor has no alternate on its land pattern | A block is redesigned if one cannot be bought | Named in section 17; other grades of the same maker exist for the instrumentation amplifier, the reference and the two linear regulators; the supervisor has a fixed 3.07 V version on the same pads, which sheds the carrier at 3.07 V instead of 3.9 V; the suppressor of VOUT gets a second source once its leakage is known |
| Parts without stock at an authorized distributor on 2026-10-09: inductor L2 of the pre-regulator, 10 µF 25 V X5R in 0805, 22 µF 25 V X5R in 1206 | First boards late | Second source of the inductor on the same pads (Würth 74438356015, also short); the capacitors are listed at other sellers; stock is read again before the order |
| Controller module differs from the reference design | Wrong pin or mechanical misfit | Raspberry Pi Pico 2 with headers as the supported module (D-82); project footprint with the hole pattern of the module; checks of section 16 on the board in hand |
| Calibration is stored on the module, not on the carrier | Wrong calibration after a module is moved to another carrier | The record carries the serial number of the carrier and the host shows it |
| Range sequencer wrong or not started | No range switching; the ladder clamps and the 1 Ω shunt carry the load current | Pull-downs keep every switch open after reset and select R0; programs tested in an emulator and on the bench; firmware opens the output within 2 ms when the jump comparator stays high outside R3 (F-21); watchdog of 100 ms (D-81, F-8); an over-voltage on VIN is blocked with no program involved |
| The two ladder clamps do not share the current: one would rise by 104 K at 3 A and 144 K at 4 A in 5 ms (calculated) | Clamp degraded, leakage across the ladder | Only with the sequencer and the trip both failing; output opened by firmware within 2 ms; range 2 recalibrated after a reported sequencer fault |
| Reaction of the sequencer slower than estimated | R-07 not met above about 300 ns (472 mV to 519 mV simulated) | Measured in phase 1; the jump-up comparator reaches the highest range in one step |
| Supply leads ring against the DUT capacitor in ampere mode: trip on steps above 0.7 A | Nuisance trip | 100 µF at the VIN terminals with leads longer than about 0.5 m and load steps above 0.5 A (user documentation, section 4.9); measured in phase 3 |
| Charge left on the supply node of the ladder (0.57 s through R90) is pushed into the external supply when the ampere switch closes on a lower voltage | A low-voltage rail of the user is lifted for about 10 ms | Firmware closes the switch only when the supply node reads below VIN + 0.1 V or below 0.3 V, and reports a fault after 3 s (F-25); no part discharges the node |
| External supply leaves 0.8 V to 5.0 V while the ampere switch is closed, faster than the detector opens it (4 µs to 45 µs) | The DUT sees the excursion: 9.2 V for a step to 20 V, −2.4 V for a step to −20 V (simulated) | Written limit in the user documentation; the PPK2 guide promises nothing for this case |
| More than 20 V on VIN | Suppressor D14 lost above 22 V; the fuse does not protect it | Limit on the silkscreen and in the user documentation; the part is replaced |
| Stiff reversed source or a voltage above the set-point on VOUT with the output on | Suppressor D21 destroyed; no part bounds VOUT below 16.7 V | Documented limits; connect and disconnect with the output off; firmware reports reverse current and opens the output |
| Reverse current through the ladder with firmware not acting | Body diodes of the range switches and clamps overheat above about 1 A (estimate) | Firmware selects R3 within 2 ms and opens the output after 100 ms (F-22); watchdog of 100 ms (F-8); 4 A for 100 ms tolerated (estimate, to be measured) |
| A firmware rule that guards hardware is missing or late (the PIO programs are not written) | Part overstressed in a fault | One list of the rules in section 6.6 (D-81), each with a test; series resistors and pull resistors as the second barrier; watchdog; two rules have no part behind them: the clock lines of the ADC and the return of energy to the 5 V rail |
| Leakage of the ESD arrays of the logic port between 2.5 V and 5.5 V has no datasheet limit | Reading of a sleeping DUT carries tens of nanoamperes per high line | Measured at 1.8 V to 5.5 V before the first release; accepted at or below 0.5 µA at 5.0 V; an alternate fits the same pads |
| Draft schematic taken as a finished design | Boards built with unchecked parts | Draft marked A2 on every sheet; section 16 lists the open checks; fabrication only in phase 5 |
| Autorouted board fabricated without a layout review (D-86) | Noise, leakage and burden outside their budgets: R-06 is missed if copper and contacts pass about 44 mΩ | Layout rules of section 10; review of the routed board before fabrication; resistance of the 1 A path as a check of section 16 |
| Noise and ground bounce through the board sockets | Jitter on the convert-start signal | Acquisition signals next to a ground pin, series resistors, low drive strength, measurement in phase 1 |
| Firmware and host disagree on the protocol | Corrupt or misread data | One definition file, generated constants, shared test vectors, stale-file check in continuous integration |
| Firmware port to the new controller takes longer than planned | Phase 1 starts late | The hardware-independent code and its tests carry over; only adapters and build change |

Faults that draft A2 bounds with parts, with no program involved. Each is
shown by calculation or simulation and stays a bench item of section 16:

- Both mode switches closed together: a transistor holds the request of
  the ampere switch low while source mode is requested (D-62).
- Controller lines undefined in reset or with empty sockets: pull
  resistors hold both chip selects inactive and every gate line low, and
  series resistors bound the current into parts without supply (D-67,
  D-77).
- ADC input beyond its rating: the driver and its clamp run from
  1.091 × VREF, so the input cannot pass VREF + 0.25 V (D-73).
- A set-point above the output range: no DAC frame commands more than
  5.26 V nominal, 5.39 V at the tolerance limits (D-58).
- An over-current level outside the range of the ADC: the trip is at
  1.15 A (1.114 A to 1.187 A), below the full scale of 122.9 mV on every
  board (D-74).
- Transients on the USB inputs: a current limiter with an output clamp at
  each input (D-47); clamp diodes keep −4 V_A and +12 V_A from reversing
  (D-52).
- A reversed or excessive supply on VIN with the ampere switch open
  (D-60), and the surge of a hot plug or a short circuit through the
  ladder (D-66).

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
| D-30 | Pre-regulator headroom of 0.45 V, set by a difference amplifier at the feedback pin (amended by D-55: the headroom is 0.45 V at 5.0 V and rises to 0.64 V at 0.8 V) | The converter output ends at 5.5 V, so 0.6 V above a 5.0 V set-point is out of range; a gain of 0.2 keeps the loop gain of the converter near its usual value |
| D-31 | VCONTROL of the output LDO from the boost output ahead of the +12 V_A regulator | The control current follows the load current and would modulate the analog rail |
| D-32 | A buffer copies the ladder output for the guard ring, the level translator and the monitor (amended by D-72: the translator has its own branch from the buffer) | Nothing resistive may hang on the node after the shunts; taken ahead of the output switch so the guard is valid during the zero calibration |
| D-33 | Level translator with the DUT on the side that has no control pins | Direction and enable stay valid while the DUT supply is off |
| D-34 | Request lines active high with pull-downs on the carrier; clock and data lines on the pull-ups of the logic device | The power-up glitches of the MCU pins are low pulses; fewer parts |
| D-35 | VIN protected by a fuse with reverse clamp and by an over-voltage detector that keeps the ampere switch open (superseded by D-60) | A clamp at 5.5 V on a terminal that may see a bench supply would have to absorb its full current; the open switch blocks 30 V |
| D-36 | Candidate parts chosen for the draft: MAX II EPM240, MUX509, MCP3208, LT3042, LM27761, LMR62014, TC4427, MCP6561 and MCP6562, OPA197, OPA365, SN74LVC8T245, CSD17577Q3A, IRLML0030, BAV199 | Needed to draw the schematic; each one stays a candidate until its check record is closed |
| D-37 | Schematic and part placement drawn as draft A0 before the checks of section 16 are closed | Requested by the project owner, to review the design as a whole and to start the layout work early |
| D-38 | Draft outline of 160 mm × 100 mm with four M3 holes | A standard size with room for a first layout; to be reduced when the placement is final |
| D-39 | Controller is a Raspberry Pi Pico 2 (RP2350) on pin sockets; it replaces the ESP32-S3 development board of D-14 and D-23 | Requested by the project owner: one controller of known price and stock, developed with open tools inside the repository; its PIO blocks give hardware timing (D-40) |
| D-40 | Range sequencer, over-current trip and acquisition timing are PIO programs of the controller; no separate logic device (replaces D-24 and the I2S clocking of D-07) | A PIO state machine executes one instruction per cycle of the system clock, independently of the processors; the programs are built and tested from the repository, where the logic device needed the tools and the programmer of its vendor |
| D-41 | Side data in two discrete parallel-load shift registers, read into the same word as the conversion result (returns to D-08) | The module has 26 GPIO pins; one state machine reading both data pins makes the alignment a property of the hardware |
| D-42 | One supply domain: either USB connector powers both boards through diodes (replaces D-25 and D-34; the diodes between the inputs are superseded by D-47, the one supply domain stays) | With one controller on the carrier there is no second domain to isolate; the data cable alone runs the instrument at low DUT current; the pins of the RP2350 tolerate 3.3 V without supply |
| D-43 | An over-voltage on VIN holds the ampere switch open through a transistor at its gate driver | The one fault that must not wait for a program; keeps the rule that hardware may refuse a request |
| D-44 | DUT connectors and logic port in the pin order of the PPK2: a 1×4 pin header (GND, VIN, VOUT, GND) in parallel with a lever terminal block, and a 1×10 logic port (VCC, GND, D7 to D0) whose VCC pin can supply the translator | Requested by the project owner, in place of screw terminals; order taken from Figure 4 of the PPK2 User Guide v1.0.1 |
| D-45 | Reference designators numbered as the annotation tool of KiCad does by default: one count per prefix, by sheet, then by position | Requested by the project owner; a new annotation in KiCad then changes nothing |
| D-46 | Draft outline of 130 mm × 100 mm (replaces D-38); parts placed by connectivity, block by block (superseded by D-85; placement and routing by D-86) | The controller module and 33 parts fewer need less room; the placement of D-37 put the parts in rows and was not a basis for routing |
| D-47 | Input stage: each USB input has its own current limiter (TPS259621, candidate: 2.0 A on USB-C and 0.76 A on the input from the controller module, calculated; output clamp 5.45 V and input rating 21 V, datasheet), and a priority multiplexer (TPS2116, candidate) drives the 5 V rail from USB-C whenever it is present. A 10 V suppressor sits at the USB-C connector and a damper of 0.33 Ω in series with 44 µF at the multiplexer input. Replaces the diode OR-ing of D-42 and the resettable fuse; the single supply domain of D-42, its jumper and its diode into VSYS stay | The diode OR fed the USB-C pins back from the other input, shared the load between both sources, charged about 150 µF at plug-in and left the parts rated 5.8 V and 6 V to a suppressor that conducts at 6.4 V (datasheet) |
| D-48 | A supervisor on the 5 V rail (TPS3808G01, candidate; threshold 3.9 V, calculated from its 0.1 % divider; release delay about 0.3 s, datasheet) makes 5V_OK. 5V_OK enables both 3.3 V regulators and the +12 V regulator directly, the charge pump through a divider and the pre-regulator through a transistor in its enable line | One off state for the whole carrier and a load shed that needs no firmware: the converter supply must start from 0 V after a dip (datasheet), no 12 V part may run while the 3.3 V rails are off, and a current-limited source recovers only when the load is shed early (estimate) |
| D-49 | R-14 re-baselined: the power budget is an input current per source class, 0.45 A, 1.4 A and 1.7 A, and the minimum of the 5 V rail is 4.25 V (4.4 V before). The test passes when an overload of the source ends in a reported fault with the controller alive, power limit or carrier supply | With the input stage of D-47, 4.4 V on the rail needs 4.68 V at the receptacle (calculated), more than the 4.5 V the PPK2 asks for; 4.25 V is what the charge pump needs (calculated); a 10 ms firmware rule cannot keep a current-limited source from sagging |
| D-50 | ESD arrays TPD4E1U06 (candidate) at the CC pins of the USB-C receptacle and at the logic port, two for D0 to D7 and one for its VCC pin | Section 4.9 promises ESD protection on every external terminal, and the CC pins and the VCC pin had none |
| D-51 | Analog rails: 10 µF 25 V X7R capacitors in 1210 on the boost output and on +12 V_A, 0.47 Ω between the boost output and the +12 V regulator, a 10 µH boost inductor with 3 A saturation current, 22 µF X7R behind 2.2 Ω at the input of the charge pump, and 0.1 % feedback resistors for −4 V_A | A 4.7 µF part in 0805 keeps a third of its value at 12 V (datasheet curve); the regulator datasheet asks for series resistance behind a ceramic-decoupled supply; the inductor must not saturate at the switch limit; with 1 % resistors −4 V_A needs 4.26 V on the 5 V rail at the tolerance corner, more than the 4.25 V of D-49 (calculated) |
| D-52 | Schottky diodes clamp −4 V_A to ground and ground to +12 V_A | The amplifiers between the two rails pull either rail beyond ground while its converter is off |
| D-53 | The 2.5 V reference is supplied from 3V3_A through 10 Ω with 4.7 µF, a Schottky diode ties VREF to 3V3_A, and the 10 µF output capacitor sits behind 1 Ω (a tuning position, 0 Ω to 1.5 Ω) | Every receiver of the reference is on 3V3_A, so the reference cannot be present without the parts it drives; the series resistor damps the output capacitor |
| D-54 | PWR_GOOD is the wired AND of four open-drain comparators (MCP6569, candidate) on 3V3_C that watch 3V3_A, +12 V_A, −4 V_A and VREF, drawn on a sheet of their own, with 1 nF at the three comparator input nodes that lie next to an output pin. The 5 V rail is watched by the supervisor of D-48, 3V3_C is not watched, and the PG pin of the +12 V regulator is not used | The PG pin reported one rail and released without input voltage; without the capacitors an edge of PWR_GOOD moves its own threshold and a slow rail gives a burst of edges (datasheet; simulated with an estimated pin capacitance) |
| D-55 | The pre-regulator tracks the output of the linear regulator, V_PRE = 0.672 V + 0.956 × V_LDO (calculated; V_LDO is the output of the linear regulator, ahead of the shunts), through a low-pass of 0.62 ms that a diode bypasses for rising edges. Amends D-30: the headroom is 0.45 V at 5.0 V and rises to 0.64 V at 0.8 V, referred to the regulator output; the gain of 0.2 stays | The regulator cannot sink: tracking the set-point drove its IN pin up to 3.5 V below OUT (rating 0.3 V) and made the converter return charge to the 5 V rail; slow down and fast up keep that from happening on a short circuit and on a charged DUT (simulated) |
| D-56 | R-08 re-baselined: source mode is designed for 1.0 A up to 2.0 V, falling in a straight line to 0.6 A at 5.0 V. It is a design figure, published as guaranteed after measurement; the worst-case headroom margin at 5.0 V is 2 mV (calculated) | The linear regulator needs up to 0.5 V and the pre-regulator ends at 5.5 V (datasheet); the curve asks 4.3 W typical and 4.9 W at the limits from the source (calculated); the PPK2 offers 600 mA |
| D-57 | Linear regulator: Schottky diodes from OUT to IN and from ground to OUT, a diode in the VCONTROL feed, a minimum load of 1.3 kΩ to −4 V_A, 22 µF at the output and in the damper of the IN pin, and a 1 kΩ bleeder on V_PRE. The VINA and PS/SYNC pins of the pre-regulator sit on their own 100 nF, as its current datasheet asks | Both supply pins are rated 0.3 V below OUT, and the output must not go below ground or rise when −4 V_A is absent (datasheet); with 22 µF a released output falls slowly enough that the converter returns at most 0.2 W to the 5 V rail (calculated); the bleeder lets hardware enable the converter without returning stored charge |
| D-58 | The set-point DAC takes VREF / 2 from a 0.1 % divider on its buffered reference input and runs at gain 2, so that no SPI frame commands more than about 5.26 V (5.39 V at the limits, calculated; 6.85 V before); its output filter is 10 ms | A hardware ceiling for the output voltage; the slope limit keeps a set-point step from making the converter return more charge to the 5 V rail than the instrument consumes and from tripping the output on a capacitive DUT (simulated) |
| D-59 | R-04 re-baselined per mode: the 100 nA resolution stands; the noise criterion in range 0 at full bandwidth is 5 nA RMS in ampere mode from a quiet supply and 40 nA RMS in source mode. The leakage of the node after the shunts is budgeted at 10 nA typical and taken out on every board by a closed-switch zero, with a limit of 50 nA at 5.0 V | The output noise of the linear regulator stands across the 1 kΩ shunt above 1.6 kHz whatever the capacitor after the shunts is: 26 nA to 27 nA RMS (simulated); no part on that node has a guaranteed leakage as small as the budget (datasheet values); the PPK2 resolves 0.2 µA |
| D-60 | VIN: 0.8 V to 5.0 V in use, −20 V to +20 V withstood with the ampere pair open. A 20 V bidirectional suppressor takes transients, a 4 A fuse is the last resort, and the detector holds the pair open above 5.46 V (5.41 V to 5.51 V; release at 5.35 V; not latched; calculated). Replaces D-35; D-43 stays; R-09 re-baselined with these limits | The clamp diode of D-35 turned a reversed supply into a short circuit that only a soldered fuse could end; 30 V is the absolute maximum of the switch transistor (datasheet); the PPK2 promises nothing outside 0.8 V to 5.0 V |
| D-61 | Each mode pair has one gate network: 100 kΩ with 100 nF for a ramp of about 10 ms, a low-leakage double diode for a fast turn-off and a bound of the gate at +12 V_A, and a transistor that holds the pair open while its common source is below ground | Closing a pair on a live supply rang the supply node to 1.3 to 1.9 times the supply voltage, an open pair conducted for any negative voltage, and the kick of the supply leads lifted the gate, and with it the supply node, above the rail of the multiplexer (simulated) |
| D-62 | Interlock: a transistor driven by the source-mode request holds the input of the ampere driver low, and 1 kΩ sits in series with both inputs of that driver | With both pairs on, VIN would be tied to the regulator output through 17 mΩ (calculated), and section 3 leaves no protection to a program; the driver inputs are rated VDD + 0.3 V on a rail that may be absent (datasheet) |
| D-63 | The supply node of the ladder has a damped branch of 0.47 Ω in series with 4.7 µF beside its 1 µF, and one 100 kΩ bleed resistor to ground | When the trip opens the output on a short circuit in ampere mode, 15 A to 34 A of lead current lifted the node above the supply of the multiplexer and took the ampere switch to its 30 V limit (simulated); the bleed resistor gives an idle level below 0.3 V and the bias return of the amplifier with every switch open, ahead of the shunts and therefore not measured |
| D-64 | R-06 re-baselined: total path drop 200 mV at 1 A (150 mV before); the shunt drop stays 100 mV | Five switches, the shunt, the fuse and copper take 158 mV typical and 181 mV at the datasheet limits (calculated; the fuse tolerance and the copper are allowances without a source); the PPK2 states no figure |
| D-65 | R-07 restated as the drop the instrument adds on a step from 1 µA to 500 mA: at most 0.5 V with 1 µF effective at the DUT, above 0.2 V for at most 1 µs, and at most 0.25 V with 10 µF. The input filter of the amplifier is 220 pF between the inputs and 22 pF from each input to ground | 200 mV with 1 µF needs the range change 108 ns after the threshold; the architecture reaches 0.35 µs, 0.51 µs with the worst delays (simulated), against a target of 0.55 µs; the smaller filter shortens the largest delay of the up-range path; the PPK2 states no limit |
| D-66 | Ladder clamp: two IRLML0030 (candidate) in parallel, each with its gate on its drain through 22 Ω, in place of the anti-parallel diode pair. Leakage budget of the ladder: 10 nA from the sense nodes to other potentials, and 100 nA across the ladder at 100 mV and 40 °C. Firmware opens the output switch at most 2 ms after the clamp starts to conduct | The diode pair was above its repetitive and surge ratings in a hot plug or a short circuit; a single MOSFET would be at its 21 A pulsed rating when a charged DUT meets a lower output voltage (simulated), hence two. In steady conduction the two parts do not share the current: one would rise by 104 K at 3 A within 5 ms (calculated). Leakage across the ladder is a gain term, not an offset |
| D-67 | 100 kΩ from each range gate to ground; 1 kΩ in series with the four gate-driver inputs and the two address inputs of the multiplexer; 5.1 kΩ pull-downs on the address lines; the enable of the multiplexer tied to +12 V_A | The off state and the reset state must not depend on the unpowered output of a gate driver or on firmware; the inputs are rated VDD + 0.3 V on a rail that may be absent (datasheet) |
| D-68 | Shunt parts: thin-film resistors of 1 kΩ and 33 Ω, 0.1 % and 25 ppm/°C, in 0805 for ranges 0 and 1; a two-terminal 1 Ω chip, 0.5 % and 25 ppm/°C, on the four-pad Kelvin land for range 2; a four-terminal 0.1 Ω part, 0.25 % and 50 ppm/°C, for range 3 (single source) | The four-terminal 0.1 % parts that sections 4.3 and 17 asked for do not exist at 1 Ω and 0.1 Ω; the tolerance is calibrated per range and the drift stays inside R-05 (calculated) |
| D-69 | Reverse current through the ladder is not measured: firmware flags it, selects range 3 at once and opens the output switch after 100 ms above about 13 mA. Without firmware the ladder tolerates 1 A continuously and 4 A for the 100 ms of the watchdog (estimates) | The same limit as the PPK2; the stress is thermal and slow, so a firmware reaction is fast enough |
| D-70 | VOUT is protected by one unidirectional 15 V suppressor to ground (PTVS15VS1UR, candidate, single source) in place of the diode clamp to a 5.6 V node | The clamp was the free-wheel path of the cable at every trip, 2.4 A to 6.6 A through a 160 mA diode (simulated), had no ESD rating and loaded a live DUT with 0.27 mA to 0.45 mA while the instrument was off (calculated) |
| D-71 | The output switch turns on through 2.2 MΩ and 10 nF, about 20 ms to 90 % at 5 V (simulated), and is the last switch to close; it turns off through a diode and 220 Ω, the gate below 2 V within 7 µs (simulated). It has a 10 Ω stopper at its gates and a 100 kΩ pull-down on the driver side, and no resistor from gate to source | Closing in 0.1 µs was a hot plug of the DUT capacitor, answered by the trip; opening in 0.1 µs lowered no current and threw the energy of the supply leads into the ladder; a resistor from gate to source would draw its current from the measured node |
| D-72 | The DUT-side supply of the level translator comes from the output of the guard buffer through its own 1 kΩ and is held between ground and the 5 V rail by a Schottky pair; the 47 Ω branch of the buffer serves the guard and the monitor only (amends D-32) | The buffer can reach −4 V and +12 V while the supply pin of the translator is rated −0.5 V to 6.5 V (datasheet), and the supply current of the translator shifted the monitor reading |
| D-73 | The ADC driver and the cathode of its clamp are supplied from VDRV = 1.091 × VREF, 2.73 V (calculated), made by a buffer amplifier of its own (replaces the 3V3_A supply of the driver) | The converter input is rated REF + 0.3 V (datasheet); a rail derived from the reference cannot pass that while the buffer is supplied, and it puts no current into the reference |
| D-74 | Over-current trip at 115 mV across the shunt, 1.15 A in range 3 (1.2 A before); the threshold string and the divider are 0.1 % resistors | With the ±10 mV of the comparators the trip has to stay below the full scale of the converter, 122.3 mV at the least, and above 1 A: it lies between 111.4 mV and 118.7 mV (calculated) |
| D-75 | Converter interface: 220 Ω in the clock, convert-start and data lines at the converter, and one 22 µF reference capacitor behind 0.22 Ω at its REF pin | Layout rule of the converter datasheet; the lines are driven into a dead supply for up to 0.1 ms at power-off (simulated) |
| D-76 | Settling window of 7 samples after a range change; the step-up comparator ignored until 2.0 µs after the last line change of a range change; over-current qualification time of 12 µs, a constant of the build between 10 µs and 20 µs; a diode pair clamps the comparator input node to 3V3_A and ground; the comparator outputs stay active high | After a range change the chain needs 45 µs to 0.1 % of range and 65 µs to 1 LSB, and the longest overshoot that is no fault lasts 8.6 µs (simulated); the comparator inputs are rated VDD + 1.0 V (datasheet); the loss of 3V3_A is reported by PWR_GOOD |
| D-77 | SPI and acquisition lines: 4.7 kΩ pull resistors at the module pins hold both chip selects inactive and the other lines low while the controller pins float; 2.2 kΩ sits in the slow SPI lines and 1.5 kΩ, behind 47 Ω, in the DAC select; SPI1 runs at 500 kHz or less | With the controller in reset or out of its sockets both converters were selected and the lines floated, and a pin could push 27 mA to 57 mA into an unpowered input (calculated) |
| D-78 | The status lines reach the controller through series resistors: VIN_OV through 4.7 kΩ and PWR_GOOD through 1 kΩ; the taps of the shift register stay on the carrier side | A pin set as an output by mistake could override the interlock of D-43 or overload an open-drain flag |
| D-79 | Logic inputs: 330 Ω in series and 470 kΩ to ground per line (1 kΩ and 1 MΩ before); R-10 re-baselined to 1.65 V to 5.5 V at the supply of the level translator | The transition time at the translator input, and an open input that has to read low at the leakage limit (datasheet); 1.65 V is the datasheet limit of the translator and the figure of the PPK2 |
| D-80 | Monitor channels: the VIN divider is 430 kΩ / 10 kΩ (1/44), so that −20 V to +20 V at VIN stays inside the ratings of the converter input (calculated); the status output of the input multiplexer is coded on the channel of the 5 V rail through 68.1 kΩ, read with a threshold of 1.67 V (calculated); all channels run at 100 SPS | No pin of the controller is free for the status line, and firmware has to know which input supplies the instrument to apply the budget of D-49; the source resistance of the dividers sets the channel rate |
| D-81 | The hardware watchdog of the controller is mandatory as the last line of defense: time-out of 100 ms or less, served by the supervision task only, with a reset that reaches the pads; no pad toward the carrier is isolated and no core is powered down while a path is closed. The firmware rules that guard hardware are kept as one list (section 6.6) | A hung processor is the one case that neither the sequencer nor the trip covers; rules spread over eight blocks are not implemented reliably |
| D-82 | The controller module is a Raspberry Pi Pico 2 with headers (SC1632), plugged into two bought 1×20 pin sockets that are soldered into the holes of its footprint; RP2350 stepping A3 or A4 is preferred, and A2 works with the pull resistors of D-67 and D-77. The calibration record carries the chip identifier and a serial number of the carrier, which has no memory of its own in revision A | The sockets were not parts of the bill of materials; erratum E9 of stepping A2 asks for 8.2 kΩ or less at a pulled-down input (datasheet); a memory on the carrier needs a pin, and every pin of the headers is in use |
| D-83 | Drawing: the power input is split into two sheets, Power Input and Logic Supplies; the rail monitor of D-54 has a sheet of its own; the input multiplexer has a project symbol, the one of the KiCad library with one output pin made passive; 14 sheets below the root sheet. The numbering stays as D-45 says | The parts of D-47, D-48 and D-54 do not fit on the A4 sheets of draft A1; the library symbol of the multiplexer declares both output pins as power outputs, which the electrical rules check reports |
| D-84 | Positions without parts: a voltage detector (803 type, 3.08 V) at the enable pin of the boost converter, and a damper of 0.33 Ω with 10 µF on the input from the controller module. Three more test points: the reference of the set-point DAC, the enable of the pre-regulator and the DUT-side supply of the translator | The boost converter has no under-voltage lock-out and no soft start, and the limiter of that input gives 0.67 A to 0.85 A (calculated), less than the converter asks for while its output charges; the multiplexer inputs come within 25 mV to 85 mV of their 6 V rating when the data cable is plugged again (simulated). Both are bench items, and the positions cost nothing |
| D-85 | Board outline of 150 mm × 100 mm with four M3 holes (replaces D-46). Board-level parts: a two-piece shield can of 44.0 mm × 30.5 mm over the front end, three fiducials, five square probe grounds. Project footprints for the lever terminal block, with pads of 1.9 mm × 2.3 mm, and for the controller module, without the antenna keep-out of the library footprint | The parts of draft A2, the shield can and the pours of the 1 A path load several blocks to 44 % or more of their area on 130 mm × 100 mm (calculated); the library pads of the terminal block leave an annular ring of 0.15 mm; the keep-out opens the ground plane between the acquisition pins and the SPI pins, and no function uses the radio of a Pico 2 W |
| D-86 | The generator of the project places the parts, and the board is routed automatically with FreeRouting. A board made this way is a draft that needs a layout review before fabrication (section 10). Replaces the placement of D-46 | Requested by the project owner on 2026-10-09, to have a complete board file early; an autorouter connects pads and knows nothing of pours, guard rings, sense pairs or converter loops |

## 16. Open Checks Before Freezing the Schematic

The draft schematic uses the parts below. No check record is filed yet, so
every part is a candidate, the parts of draft A2 included. The comparison
of pin numbers and land patterns with the datasheets is part of every
check. Three symbols were drawn for the project from the manufacturer's
datasheet (ADS8860, MUX509 and TPS63020); the symbol of the TPS2116 is the
one of the KiCad library with one output pin made passive (D-83). Two
footprints belong to the project (the lever terminal block and the
controller module, D-85).

Where an item says "calculated" or "simulated", that part of the check has
a figure and its measurement is what stays open. Test points are named by
their reference.

Parts and blocks:

- AD8421 (U27): input common-mode range with +12 V / −4 V, settling time
  and noise at G = 19.93, bias current against the leakage budget. Linear
  range near full scale with the output below 0.2 V: output shorted at the
  terminals, 0.9 A to 1.2 A forced, TP44 against a reference shunt, and
  the currents at which TP46 and TP45 switch. Overload recovery and
  output polarity after a differential overdrive of up to 3.9 V for 1 µs
  (expected: under 5 µs, no inversion). Offset with a transmitting DUT
  (868 MHz, 2.4 GHz) on its cable.
- ADS8860 (U30): convert-start and data timing against the program of
  the acquisition state machine at 100 kSPS and 500 kSPS, with
  convert-start still high at the end of the conversion so that no busy
  indicator appears on the data line; input driver and reference drive
  requirements; operation at a 2.5 V reference, the lower limit of its
  range, where the datasheet gives typical figures only; noise with
  R131 at 0 Ω, 0.22 Ω and 0.47 Ω (D-75). Driver rail (D-73): about
  2.68 V at TP42, 2.73 V at the output of its buffer (calculated), and
  its step response; TP43 never above VREF + 0.25 V in overload, at
  power-up, at power-down and while 3V3_A is between 1 V and 2.2 V.
- RP2350 PIO: size of the acquisition program and of the range sequencer
  against the 32 instructions of a block; reaction time from the pin of the
  jump comparator to the gate line of range 3, 100 ns or less (20 ns to
  80 ns by instruction count, estimate); blanking of 2 µs (F-17) and trip
  qualification of 12 µs (F-18) as programs; DMA pacing from the state
  machine.
- LT3080 (U18): dropout on both supply pins on the R-08 curve (answered
  by calculation with a limit interpolated between the two guaranteed
  points, margin 2 mV at 5.0 V; measurement on several warm units open),
  minimum load (3.7 mA to 6.9 mA through R69, calculated), output noise
  with that load, operation from the control pin alone, thermal
  resistance of the package on the planned copper.
- Pre-regulator (TPS63020, U16): stability with the difference amplifier
  U19 in its feedback path over 1.2 V to 5.5 V and the charge it returns
  to the 5 V rail (both from a behavioral model only; phase 1 prototype),
  the power the 5 V rail takes in source mode without load, which has to be
  0.25 W or more (0.54 W to 0.60 W estimated), behavior below 1.2 V of
  output and at the 5.5 V end against its over-voltage protection, ripple
  after the filter. Land pattern: the lead pads agree with the drawing of
  the manufacturer; center pad 1.7 mm × 3.3 mm against 1.58 mm × 2.85 mm
  accepted, with a via array. Inductor L2: saturation current of 4.6 A
  at 30 % drop (datasheet value) against the current limit of the converter;
  no stock on 2026-10-09, second source on the same pads. Bead FB1:
  inductance below 1 MHz.
- Set-point path (D-58): ceiling of 5.26 V (calculated) at TP23 with
  the DAC at full scale; half the reference at TP19.
- Range MOSFETs, ladder clamps (Q10, Q11) and multiplexer: leakage
  across the whole ladder at 100 mV and 40 °C against 100 nA, one
  measurement between TP33 and the node behind the shunts with every gate
  low (if it fails: repeated with Q11 removed); leakage of the node
  behind the shunts to ground at 5 V and 40 °C against 10 nA; on-resistance
  of the multiplexer at +12 V / −4 V (125 Ω to 340 Ω expected from the
  datasheet figures at other supplies; the simulations cover up to 430 Ω);
  gate-charge injection into VOUT; pulse series of section 11 with leakage
  and gain compared before and after, and the case temperature of both
  clamps.
- Shunts (R101, R104, R107, R110): gain of each range at 20 °C and 40 °C; seat
  of the two-terminal part R107 on its four-pad land; pulse rating of
  R107 and R110 in the surge of a hot plug (survival by datasheet
  curve; calibration compared in the pulse series). R104 was read in a
  distributor's copy of its datasheet.
- Suppressor of VOUT (PTVS15VS1UR, D21): leakage at 5 V at 25 °C and at
  40 °C to 50 °C (guaranteed: 100 nA at 15 V and 25 °C only), forward
  voltage at 1 A and 10 A, capacitance. With it: closed-switch leakage of
  the terminal at 25 °C and 40 °C against 50 nA, and the insulation
  resistance of C71.
- Output switch (D-71): gate ramp at TP37, in-rush into 100 µF to
  2200 µF, absence of oscillation while the pair works as a follower;
  readings with the output open 200 ms or more after it opened.
- Mode switches (D-61, D-62): gate ramps at TP32 and TP31 and the
  supply node at TP33 when a pair closes on a live 5 V supply
  (conduction after about 1 ms, 95 % after about 9 ms, full gate drive
  after 40 ms, simulated); both requests high: input of the ampere driver
  below 0.1 V and less than 50 µA at the VIN terminal; −5 V on VIN with
  the ampere request held high by test firmware, from a supply limited to
  1 A: TP33 above −0.1 V after 35 µs.
- VIN protection (D-60): detector U21 trips between 5.41 V and 5.51 V
  and releases between 5.30 V and 5.40 V (calculated); TP30 steady
  high with +20 V on VIN and power on, at 0 °C and 40 °C if possible;
  its input pin above −1.0 V with −20 V; TP33 and TP27 at a short
  circuit in ampere mode from a 10 A supply through 0.5 m and 2 m leads
  (expected 8 V to 11 V and below 34 V); short-pulse rating of D14
  (up to 16.9 A for microseconds simulated, against 12.3 A for the
  10/1000 µs wave of the datasheet).
- Reverse current (D-69): with the range gates held low, 1 A, 1.5 A and
  2 A for 60 s and 4 A for 100 ms: temperatures of both clamps and of
  Q14, and whether the clamps stay within 10 °C of each other.
- Comparators (U31, U32): propagation delay and input range;
  thresholds and tolerances are answered by calculation (87.5 mV to
  94.4 mV, 111.4 mV to 118.7 mV, 147.2 mV to 155.1 mV at the shunt);
  hysteresis and offset at 0.46 V to 0.76 V of common mode; inputs at or
  below 3V3_A + 1.0 V with 3V3_A off and the amplifier output at +10 V.
- Rail monitor (MCP6569, U14, D-54): trip level of each comparator at
  TP17; edges of PWR_GOOD at start and stop with C32 to C34
  fitted; rise time of PWR_GOOD against the slowest edge the shift
  register accepts.
- Shift registers (SN74LV165A): timing of the load pulse against the
  convert-start edge, maximum clock at 3.3 V against the 500 kSPS option.
- Interlock transistors (BSS138: Q3, Q2, and Q1 at the enable
  of the pre-regulator): threshold and on-resistance with 3.3 V at the
  gate.
- Gate drivers (TC4427): input thresholds with 3.3 V logic behind 1 kΩ,
  propagation delay, supply current, output state without supply and
  with a supply below 4.5 V, where the datasheet states nothing.
- Analog rails: load of each rail against the converters (LMR62014, LT3042,
  LM27761). Capacitance under bias is answered from the bias curves of the
  parts. Start-up order by simulation: 5 V, the boost converter, then after
  0.18 s to 0.42 s the 3.3 V rails, −4 V_A and +12 V_A, the reference last;
  to be measured, with the order at power-off. Start current of the boost
  converter (expected 1.5 A to 2.5 A for 0.15 ms to 0.2 ms; no soft start)
  and its start from a supply limited to 0.7 A. The −4 V rail at 4.25 V on
  the 5 V rail (answered on typical curves with 0.1 % feedback resistors).
  Noise of the boost converter after the +12 V_A regulator, with 0.47 Ω, 0 Ω
  and a bead in R37. Clamp levels at power-off at TP12 and TP16.
- Input stage (D-47, D-48): current limiters TPS259621 (U4, U3),
  multiplexer TPS2116 (U5), supervisor TPS3808G01 (U6); all figures
  come from behavioral models with typical delays. Open: hot plug into the
  USB-C connector (TP1 below 12.5 V; nothing behind the limiter more
  than 0.1 V above the source); contact interrupted for 20 µs to 20 ms
  (TP2 below 5.8 V); data cable plugged again with a short cable
  (TP4 below 6.0 V); in-rush on a hub port (0.9 A or less after the
  spike of the module; 0.71 A to 0.87 A simulated); supervisor at 3.83 V to
  4.00 V with a release after 0.18 s to 0.42 s; 3V3_A (TP10) from below
  0.7 V at a re-plug after 0.2 s, 1 s and 5 s; behavior of the multiplexer
  when its priority input falls with the other input absent. A supply raised
  from 5 V to 10 V at the USB-C connector, from a source limited to 1 A: the
  5 V rail (TP6) at the clamp level of 5.28 V to 5.61 V, and the input
  of the charge pump (C21) against its 5.8 V rating with a source between
  5.5 V and 5.83 V. USB-C plugged while the module input supplies: lowest
  level of the 5 V rail against the highest supervisor threshold of 4.00 V
  (4.0 V to 4.5 V simulated). USB-C pulled with both cables in: time until
  the carrier is back and edges of SRC_ST (TP5).
- Level translator: supply current drawn from the buffer through R118,
  clamp levels of D24, state of the bits and supply current with the
  DUT-side supply between 0.1 V and 1.65 V; level of an open logic input at
  25 °C and 40 °C with the cable fitted and neighbors toggling (confirms
  470 kΩ or decides for 330 kΩ or 220 kΩ on the same pads). Sag of the
  DUT-side supply (TP48) with eight lines at 1 MHz and at 10 MHz at
  1.8 V (30 mV and 0.3 V calculated).
- ESD arrays (TPD4E1U06: U2, U36, U37, U35, D-50): leakage
  of a logic line and of the VCC pin at 1.8 V, 3.3 V, 5.0 V and 5.5 V at
  25 °C and 40 °C; 0.5 µA or less at 5.0 V, else the alternate part.
- USB-C: CC thresholds and behavior on 500 mA, 1.5 A and 3 A sources; a
  source on a C-to-C cable plugged after the cable of the module.
- Pico 2 in hand: stepping of the RP2350 (erratum E9 of stepping A2 concerns
  pull-downs with the input buffer on; stepping A3 or A4 is preferred,
  D-82), pin headers fitted, height on the sockets. Levels of every
  controller line with empty sockets and with the module in reset; current
  into the select pins of the DAC and of the monitor converter with 3V3_A at
  0 V and the pin high; gate lines across a watchdog restart and a restart
  into the boot loader.
- Lever terminal block (WAGO 2601-1104): footprint with pads of
  1.9 mm × 2.3 mm, side of the wire entry and current rating against the
  drawing of the manufacturer.
- Monitor ADC (MCP3208): input range and source impedance of each
  channel, SPI mode shared with the DAC, clock edge at 500 kHz. Channel 2
  against a meter with both scale factors (0.4545 on the USB-C input,
  0.2524 on the input of the module, calculated) and channel 1 at
  VIN / 44; its input within ±0.5 V with −20 V and +20 V on VIN.
- Path resistance: switches, shunt, fuse and connectors against the 200 mV
  limit of R-06 in both modes; resistance of samples of F1, whose
  datasheet states no tolerance; copper and contacts of the 1 A path at
  or below 20 mΩ.
- Supply node of the ladder: TP33 below 0.3 V with the instrument idle
  and 5 V on VIN and on VOUT; TP33 against TP16 while the USB cable
  is pulled with the source on at 5 V (the node follows the rail down
  within 1 V).
- USB device stack: TinyUSB as the Pico SDK brings it; sustained CDC
  throughput on the RP2350 before phase 1 ends.
- Protocol (section 7, `protocol/definition.toml`): draft A2 reports more
  than the definition holds. Missing are a mark for over-range and for
  under-range samples (F-22, F-35), the invalid mark for the 5 ms after a
  change of supply (F-35), the fault flags that section 6.4 names
  beyond the four of section 7.4, the input in use and the CC class in the
  status record (F-14), the power budget as a current (D-49; the event of
  section 7.4 carries milliwatts), and the instant from which the host
  counts the 250 ms of output settling (section 9). They are added to the
  definition file, with the generated files and the test vectors, before the
  firmware of phase 1 reports them.
- Sections 6 to 8, not decided yet; each point is settled, with a decision,
  before the software of phase 1 builds on it:
  - how the record of section 8 travels. CAL_WRITE carries one gain and
    one offset for a range or for the DAC; no command or field carries
    the chip identifier, the serial number and revision of the carrier,
    the calibration temperature, the settling window, the closed-switch
    zero or the nine or more set-points of the DAC (D-58, D-59, D-82);
  - the content that the table of section 7.4 names for GET_INFO and
    GET_STATUS beyond the provisional data: range table, calibration,
    VOUT, VIN, the 5 V rail, temperature and power budget;
  - the reports that rules name without a place in the protocol: the
    count of consecutive trips and "start over-current" (F-19), the
    settled set-point (F-30) and "DUT above the set-point" (F-31);
  - where the constants are stored that rules take from a board and
    section 8 does not list: the offset of the VIN channel (F-26), the
    constants of the input model (F-14) and the thermal limit (F-15);
  - the step in which firmware evaluates F-21 and F-22: both ask for a
    reaction within 2 ms, and section 6.3 evaluates the under-range rule
    once per block of 256 samples, which is 2.56 ms at 100 kSPS;
  - how a fault is reported while firmware still waits in BOOT (F-2),
    and the transition by which the bring-up runs again when PWR_GOOD
    returns: the diagram of section 6.4 has neither.

Before the board is ordered. These items need no carrier board:

- The risk prototypes of phase 1 (section 13) that concern the carrier:
  reaction of the sequencer, pre-regulator with its tracking amplifier,
  start of the boost converter from 0.7 A.
- Linear range of the AD8421 near full scale with the output below 0.2 V,
  on the test board of phase 2. Until the result exists, R3 above 1 A,
  the trip level and the jump level are specified for output voltages of
  0.2 V or more.
- On loose parts: leakage of the suppressor PTVS15VS1UR at 5 V and at
  40 °C to 50 °C; leakage of the IRLML0030 at 100 mV and 40 °C;
  on-resistance of the MUX509 at +12 V / −4 V.
- Review of the routed board (D-86) against the rules of section 10, with
  the resistance of the 1 A path and of the copper from the pre-regulator
  to FB1 (15 mΩ or less).
- Stock of the parts that had none on 2026-10-09 (L2, 10 µF and 22 µF
  25 V X5R), and the order of the parts with long lead times.

Before a DUT is connected to a board:

- With +12 V_A held between 1 V and 4.5 V (boost converter disabled), while
  5 V is applied and removed, with 5 V on VIN, and with 5 V on VOUT and
  the instrument off: every gate at or below 0.3 V (TP32, TP31,
  TP34 to TP36, TP37).
- Carrier without supply and 3.3 V through 1 kΩ on a gate-driver input:
  level of +12 V_A and of the gate.
- Output open within 100 ms of a halted supervision task (F-8); gate lines
  low across a restart.
- Then the gate ramp of the output switch, the in-rush and the absence of
  oscillation, with a capacitor in place of the DUT.

## 17. Master Component Bill of Materials (BOM) Summary

One row per function, with the part number that the schematic of draft A2
carries. Ratings in the last column are datasheet values; limits and
thresholds set by resistors are calculated. A part marked "candidate"
stays one until a record in [`checks/`](checks/) accepts it.

| Category | Component Part Number | Package | Key Attribute |
| --- | --- | --- | --- |
| Controller | Raspberry Pi Pico 2 with pin headers, SC1632 | 2 × 20 pins | RP2350, USB Full-Speed, three PIO blocks; plugged, not soldered |
| Board sockets | Würth 61302011821, 1×20 pin socket, 2.54 mm, two parts | Through-hole | Rows 17.78 mm apart, soldered into the holes of the module footprint |
| Power connector | GCT USB4125-GF-A-0190 (candidate) | 6 pins, top mount | USB-C receptacle, power only, with CC sense |
| Current limiters | TPS259621DDAR (candidate), two parts | HSOP-8 with thermal pad | One per USB input: 2.0 A on USB-C, 0.76 A on the module input; output clamp 5.45 V |
| Input multiplexer | TPS2116DRLR (candidate) | SOT-583 | Priority to USB-C, reverse blocking, status output |
| Input damper | 0.33 Ω ERJ-6RQFR33V with 2 × 22 µF 10 V X7R CL31B226KPHNNNE | 0805, 1206 | Hot-plug damping at the multiplexer input |
| Bulk capacitor | Würth 865060343004, 47 µF 16 V | 6.3 mm × 5.4 mm | Reservoir on the 5 V rail |
| Supervisor | TPS3808G01DBVR (candidate) | SOT-23-6 | 5V_OK at 3.9 V on the 5 V rail; enables the rails and the pre-regulator; a fixed 3.07 V version fits the same pads and would shed the carrier at 3.07 V instead of 3.9 V |
| Logic and analog 3.3 V | LP5907MFX-3.3/NOPB (candidate), two parts | SOT-23-5 | 3V3_C and 3V3_A |
| Carrier indicator | Würth 150060VS75000, green LED | 0603 | On 3V3_C through 1 kΩ: lit while the supervisor has released the carrier |
| Rail monitor | MCP6569-E/SL (candidate) | SOIC-14 | Four open-drain comparators: PWR_GOOD from 3V3_A, +12 V_A, −4 V_A and VREF |
| Analog rails | LMR62014XMF/NOPB boost, LT3042EMSE#PBF +12 V, LM27761DSGT −4 V (candidates) | SOT-23-5, MSOP-10, WSON-8 | Filtered analog supplies |
| Boost inductor | Würth 74438357100 (candidate) | 4 mm × 4 mm | 10 µH, 3 A saturation current |
| Reference | REF5025AID (candidate) | SOIC-8 | 2.5 V, shared by ADC, DAC, monitor and thresholds |
| Regulator | LT3080EDD#PBF (candidate) | DFN-8 | 1.1 A, low noise linear regulator |
| Pre-regulator | TPS63020DSJR (candidate) | VSON-14 | Tracks the regulator output with 0.45 V to 0.64 V of headroom |
| Pre-regulator inductor | Coilcraft XFL4020-152MEC (candidate) | 4 mm × 4 mm | 1.5 µH, 4.6 A saturation current at 30 % drop |
| Ferrite bead | BLM31SN500SN1L (candidate) | 1206 | 50 Ω at 100 MHz, 12 A; between pre-regulator and regulator |
| DAC | MCP4921-E/SN | SOIC-8 | 12-bit voltage output DAC, SPI |
| Precision op-amp | OPA197IDBVR (candidate), three parts | SOT-23-5 | Set-point gain, pedestal, guard buffer |
| Fast op-amp | OPA365AIDBVR (candidate), three parts | SOT-23-5 | Tracking amplifier, ADC driver, driver rail VDRV |
| In-amp | AD8421ARZ (candidate) | SOIC-8 | Fast settling, low noise, G = 19.93 with 523 Ω |
| ADC | ADS8860IDGS (candidate) | MSOP-10 | 16-bit, single-ended, 1 Msps |
| Comparators | MCP6562-E/SN and MCP6561T-E/OT, two parts (candidates) | SOIC-8, SOT-23-5 | Jump up and over-current; step up; VIN over-voltage |
| Side data | SN74LV165ADR (candidate), two parts | SOIC-16 | Status and logic inputs of every sample |
| Multiplexer | MUX509IPWR (candidate) | TSSOP-16 | Dual 4:1, Kelvin sense selection |
| Gate drivers | TC4427EOA713 (candidate), three parts | SOIC-8 | Six gate lines from +12 V_A, non-inverting |
| Switch FETs, 1 A | CSD17577Q3A (candidate), seven parts | SON 3.3 mm | Two mode pairs, range 3 branch, output switch |
| Switch FETs, small | IRLML0030TRPBF (candidate), four parts | SOT-23 | Range 1 and range 2 branches; ladder clamp (two) |
| Ladder clamp | IRLML0030TRPBF, the two parts above, gate on drain through 22 Ω | SOT-23 | Surge path across the ladder |
| Interlock | BSS138-7-F (candidate), three parts | SOT-23 | Holds the ampere switch open on over-voltage and while source mode is requested; gates the pre-regulator enable with 5V_OK |
| Gate clamp | BC847B-7-F (candidate), two parts | SOT-23 | Holds a mode pair open below ground |
| Shunt R0 | 1 kΩ, 0.1 %, 25 ppm/°C, thin film, TNPW08051K00BEEA | 0805 | 100 µA range |
| Shunt R1 | 33 Ω, 0.1 %, 25 ppm/°C, thin film, CPF0805B33RE1 | 0805 | 3 mA range |
| Shunt R2 | 1 Ω, 0.5 %, 25 ppm/°C, TNPW12061R00DEEA, two-terminal on a four-pad land | 1206 | 100 mA range |
| Shunt R3 | 0.1 Ω, 0.25 %, 50 ppm/°C, 4-terminal, LVK12R100CER (single source) | 1206 | 1 A range |
| SUPPLY damper | 0.47 Ω 0.5 W RCWE1206R470FKEA with 4.7 µF 25 V X7R CL21B475KAFNNNE | 1206, 0805 | Lead energy at a trip |
| VIN fuse | Littelfuse 0466004.NR (candidate) | 1206 | 4 A fast, 32 V; last resort at the VIN terminal |
| Suppressors | SMAJ10A-E3/61 at USB-C, SMAJ20CA-E3/61 at VIN, PTVS15VS1UR,115 at VOUT (candidates) | SMA, SMA, SOD-123W | Transients at the three power terminals; the VOUT part is low leakage and single source |
| ESD arrays | TPD4E1U06DBVR (candidate), four parts | SOT-23-6 | CC pins; D0 to D7; VCC pin of the logic port |
| Low-leakage diodes | BAV199-7-F (candidate), ten parts | SOT-23 | Turn-off and gate bound of the mode pairs (two), base clamp (two), detector input, gate turn-off of the output switch, limiter clamp, comparator input clamp, tracking fast path, VCONTROL feed |
| Schottky diodes, 1 A | 1N5819HW-7-F (candidate), five parts | SOD-123 | VSYS feed, across each current limiter (two), regulator OUT to IN and ground to OUT |
| Schottky diodes, 0.5 A | B0530W-7-F (candidate), four parts | SOD-123 | Boost rectifier, clamps of −4 V_A and +12 V_A, VREF to 3V3_A |
| Schottky pair | BAT54SLT1G (candidate) | SOT-23 | Bounds the DUT-side supply of the translator between ground and the 5 V rail |
| Level shifter | SN74LVC8T245PWR (candidate) | TSSOP-24 | Digital inputs D0 to D7, DUT side on the buffered output |
| Monitor ADC | MCP3208T-BI/SL (candidate) | SOIC-16 | VOUT, VIN, the 5 V rail with the source tag, CC, temperature, rails |
| Temperature sensor | MCP9700AT-E/TT (candidate) | SOT-23 | Next to the linear regulator |
| DUT connectors | Würth 61300411121, 1×4 pin header, and WAGO 2601-1104 lever terminal block (candidate) | 2.54 mm, 3.5 mm | GND, VIN, VOUT, GND |
| Logic port | Würth 61301011121, 1×10 pin header | 2.54 mm | VCC, GND, D7 to D0 |
| Console and reset | Würth 61300311121, 1×3 pin header; B3F-1000 push button | 2.54 mm, 6 mm | UART0; RUN pin |
| Shield can | Laird BMI-S-210-F frame and BMI-S-210-C cover (candidates) | 44.0 mm × 30.5 mm, surface mount | Over the front end; the cover comes off for probing |
| Decoupling capacitors | KEMET C0603C104K5RACTU, 100 nF 50 V X7R (51 parts); C0603C105K3RACTU, 1 µF 25 V X7R (20 parts) | 0603 | One part number per value |
| Rail capacitors | Samsung CL32B106KAJNNNE, 10 µF 25 V X7R; CL31A226KAHNNNE, 22 µF 25 V X5R; CL21A106KAYNNNE, 10 µF 25 V X5R | 1210, 1206, 0805 | Chosen on their DC-bias curves |
| Measured-node capacitor | TDK C3216C0G1H104J160AA, 100 nF 50 V C0G | 1206 | The only capacitor after the shunts |
| Resistors | Vishay CRCW0603 at 1 %; Vishay TNPW0603 thin film at 0.1 % and 25 ppm/°C; Bourns CAY16 arrays | 0603, 4 × 0603 | Thresholds, dividers and gains use the 0.1 % parts |

Ordering: every part of the bill of materials has a part number and a maker in
its fields in the schematic, and the full list, one line per part number, is
generated from the schematic ([`../hardware/README.md`](../hardware/README.md)).
Test points, fiducials, mounting holes and solder jumpers are not in it; the two
sockets and the cover of the shield can are, although they have no footprint.
Three positions carry no part and no part number (D-84). Three lines had no
stock at an authorized distributor on 2026-10-09, as read on distributor pages
that day: the pre-regulator inductor XFL4020-152MEC, whose second source Würth
74438356015 fits the same pads (datasheet) and was itself short; the 10 µF 25 V
X5R capacitor CL21A106KAYNNNE, with Murata GRM21BR61E106KA73L as alternate; and
the 22 µF 25 V X5R capacitor CL31A226KAHNNNE, with Murata GRM31CR61E226KE15L or
TDK C3216X5R1E226M160AB as alternates. A capacitor alternate is released only
after its DC-bias curve has been compared with the one the design was calculated
with. The stock of the cover of the shield can was not confirmed. No part of
another maker is released for any integrated circuit of the table except the ESD
arrays, nor for the transistors CSD17577Q3A and IRLML0030, the 1 A Schottky
diode, the suppressor of VOUT, the ferrite bead, the 0.1 Ω shunt and the lever
terminal block; the boost inductor has no alternate on its land pattern. Other
grades of the same maker exist for the instrumentation amplifier, the reference
and the two linear regulators (ordering data of 2026-10-09).

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
