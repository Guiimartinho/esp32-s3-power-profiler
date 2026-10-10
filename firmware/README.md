# Firmware

Firmware of the controller of the instrument, a Raspberry Pi Pico 2
(RP2350). It acquires the samples, controls the analog front end and streams
the data to the host over USB.

## Status

In short: this directory holds a hardware-independent core with unit tests
that run on a PC, and the build project of the first plan, for another
controller. It does not hold firmware for the Pico 2. No file here
includes a header of the Pico SDK, no PIO program is written, and none of
the 36 firmware rules that guard the carrier board of draft A2 is
implemented.

What exists:

| Part | State | Where |
| --- | --- | --- |
| Wire protocol | Done and unit-tested: CRC-16, frame encoder and incremental parser, sample word, stream payload, envelopes of commands, responses and events. It holds what `protocol/definition.toml` holds today, which is less than draft A2 reports (see below) | `components/proto` |
| Block queue between the two cores | Done and unit-tested, also under two real threads | `components/base` |
| Settling window after a range change | Done and unit-tested as an algorithm. The window length is an argument: the core holds no default of seven samples | `components/acq/src/pp_range_tracker.c` |
| Step-down rule of the ranging | Done and unit-tested: N consecutive samples (default 100), hold-off of four blocks. The thresholds are an argument; no value is stored | `components/acq/src/pp_downrange.c` |
| Device state machine | Done and unit-tested: the six states of section 6.4 and the transitions between them. One fault event without a cause | `components/app/src/pp_fsm.c` |
| Port to the analog front end | Declared, with a test double. It has six calls and predates draft A2 | `components/afe/include/afe/pp_afe_port.h` |
| ESP-IDF project of the first plan | Builds for the ESP32-S3. Its `main` logs a banner and the first state of the state machine and drives no hardware. The port replaces it | `CMakeLists.txt`, `main/`, `sdkconfig.defaults` |

What does not exist:

| Part | State |
| --- | --- |
| Target build for the Pico 2 | Not started. It will use the Pico SDK (C and CMake) and the TinyUSB stack the SDK brings, and produce a `.uf2` image |
| PIO programs | None written: sampling clock and capture, range sequencer, over-current trip (D-40) |
| Adapters (`port/` directories) | None written: capture through PIO and DMA, analog front end, SPI to the DAC and the monitor converter, USB, flash, watchdog |
| Pin table | Not written. Section 5 of the specification has the pin map; rule F-4 asks for a unit test of the table |
| Components `smu`, `monitor`, `cal`, `usb_link` | Empty directories with a placeholder file |
| Command handlers, self-test, supervision | Not started in `app` |
| Firmware rules F-1 to F-36 | None implemented. The core holds a piece of F-35 and the step-down rule that F-22 refers to |

The controller changed from the ESP32-S3 to the Pico 2 with decision D-39 of
the [specification](../docs/specification.md). The core does not depend on
the controller, so it and its tests carry over as they are; sections 5 and 6
of the specification describe the pins and the execution model the port
follows.

Nothing here has run on a board, neither on a Pico 2 nor on a carrier:
timing, throughput and loss figures are design targets of the
specification, and the figures quoted below are its calculated, simulated
or datasheet values, not measurements.

What the core is worth today: its logic is checked on a PC by the unit
tests, the coverage floors and the static analysis described under
[Host Tests](#host-tests) and
[Formatting and Static Analysis](#formatting-and-static-analysis). The
sanitizer builds need Linux or macOS. That shows that the code does what
its tests say; it shows nothing about timing or about the hardware.

## What Draft A2 Asks of the Firmware

The specification was rewritten for draft A2 of the carrier board, and the
firmware it describes is much larger than the code here. This section
follows sections 5 to 8 and 16 of the specification and compares each item
with the tree. "In the core" means hardware-independent code with a unit
test; it never means code that has run on a controller.

### Pins and PIO Blocks (Section 5)

Section 5 fixes the 26 GPIO pins of the headers; every one is in use. No
file here holds a pin number yet. The pin table of the port takes these
groups from that section, and nothing else decides a pin:

| Pins | Signals | Peripheral |
| --- | --- | --- |
| GP0, GP1 | DBG_TX, DBG_RX | Console, UART0 |
| GP2 to GP7 | GATE_R1 to GATE_R3, MUX_A0, MUX_A1, GATE_OUT | Outputs of the range sequencer, PIO 1 |
| GP8 to GP10 | CMP_UP, CMP_JUMP, CMP_OC | Inputs of the range sequencer, PIO 1 |
| GP11 | VIN_OV | Input, interrupt source (F-27) |
| GP12 to GP15, GP22 | SPI_MISO, MON_CS, SPI_SCK, SPI_MOSI, DAC_CS | SPI1 to the monitor converter and the DAC; the two chip selects are plain outputs (F-6) |
| GP16, GP17 | ADC_DOUT, SIDE_DOUT | Inputs of the acquisition state machine, PIO 0 |
| GP18 | SMU_ON | Output, enable of the pre-regulator |
| GP19 to GP21 | ADC_SCK, ADC_CNV, SIDE_LOAD | Outputs of the acquisition state machine, PIO 0 |
| GP26, GP27 | GATE_SRC, GATE_AMP | Outputs, the two mode requests |
| GP28 | PWR_GOOD | Input, interrupt source (F-7) |

The status indicator is the LED of the Pico 2 on GP25. GP1, GP8 to GP12,
GP16, GP17 and GP28 are driven by the carrier and are never outputs
(F-4). The supported module is the Pico 2 with headers; a Pico 2 W fits
the sockets, but the firmware does not support it, because its LED and its
VBUS sense are pins of the radio chip. Pin numbers, like protocol numbers,
are a breaking change when they move.

### Execution Model (Section 6)

| Item of the specification | State | What shows it |
| --- | --- | --- |
| Built with the Pico SDK, TinyUSB as the USB stack | Not started | `CMakeLists.txt` is an ESP-IDF project file |
| Core 1 runs the acquisition loop and nothing else; core 0 runs USB, commands, the monitor and the state machine as a cooperative loop (section 6.2) | Not started | `main/app_main.c` creates the state machine and returns |
| No interrupt and no driver call per sample: a PIO state machine clocks the converter and DMA moves blocks of 256 words (section 6.3, timing in F-34) | Not started. The block size exists as the protocol constant `PP_BLOCK_SAMPLES` | No `.pio` file in the tree |
| Range sequencer and over-current trip as PIO state machines (section 4.4, D-40, F-16 to F-20) | Not started | No `.pio` file in the tree |
| Separation of the conversion result from the side bits, decimation for the 500 kSPS option | Not started | `components/acq/src` holds two files, neither does this |
| Sample word assembly | In the core | `components/proto/include/proto/pp_sample.h` |
| Settling window after a change of the range bits | In the core, without its default | `components/acq/src/pp_range_tracker.c` |
| Step-down rule evaluated on the block | In the core | `components/acq/src/pp_downrange.c` |
| Under-range rule evaluated on the block (F-22) | Not started | |
| Ring buffer between the cores; a full buffer drops the block and counts it | In the core. The capacity is an argument; the 64 blocks of section 6.3 are not set anywhere | `components/base/src/pp_blockq.c` |
| Stream frames with the count of dropped blocks | In the core | `components/proto/src/pp_stream.c`, `pp_frame.c` |
| Command frames parsed from a byte stream | In the core, envelope only. No command is executed | `components/proto/src/pp_frame.c`, `pp_command.c` |
| Monitor work every 10 ms: eight slow channels, rails test, budget, thermal limit, watchdog reload | Not started | `components/monitor` is empty |
| Interrupt handlers in RAM for PWR_GOOD and VIN_OV (F-7, F-27) | Not started | |
| USB CDC ACM with host-open detection; 500 mA declared in the descriptor (section 6.5, F-14) | Not started | `components/usb_link` is empty |

Whether a real-time kernel is added on core 0 is open: section 6.2 leaves
it to phase 1, to be decided from measured latencies.

Section 6.3 also sets budgets for this model: the acquisition loop under
30 % of core 1 at 100 kSPS, a ring buffer of 64 blocks (about 66 kB,
164 ms of data) and under 20 ms from sample to host as a typical value.
They are design targets; none is measured, and the first figures come from
the prototypes of phase 1.

### Device State Machine and Fault Causes (Section 6.4)

`components/app/include/app/pp_fsm.h` declares ten events, and
`components/app/src/pp_fsm.c` holds the transition table for the six states
BOOT, SELFTEST, IDLE, ARMED, STREAMING and FAULT. The table agrees with the
diagram of section 6.4: a fault can be raised in every state after BOOT,
only CLEAR_FAULT leaves FAULT, the output cannot be switched off while
STREAMING, and a host that closes the port ends the stream. An event that
the state does not allow is refused.

What section 6.4 describes around that table is not written:

| Item of section 6.4 | State |
| --- | --- |
| BOOT: release of every pin, wait for PWR_GOOD, bring-up in the order of F-3 | Not started |
| SELFTEST: rails test, ADC response, a pass through all ranges, start-up zero | Not started. The machine has the two events for its result |
| SET_MODE only in IDLE, and the other command rules of section 7.4 | Not started. They are decisions of the command handlers; today only the device simulator of the host package applies them |
| DUT_POWER on: the start sequence of F-28 in source mode, the checks of F-24 to F-26 in ampere mode, ARMED only 50 ms after GATE_OUT rose, FAULT when a check fails | Not started. The machine goes from IDLE to ARMED on one event; the handler will have to dispatch it at the end of the sequence |
| DUT_POWER off: output pair first, then the mode pair, the source stopped as F-29 and F-31 say | Not started |
| FAULT opens the output switch first and reports second | Not started. The machine calls an observer after each accepted event; the observer that opens the switch is not written |
| Bring-up of BOOT again after PWR_GOOD was lost and returned | Not started. The table has no event for it |
| Watchdog restart reported with its own fault flag (F-8) | Not started |
| DUT_POWER on refused for 100 ms after an over-current trip (F-19) | Not started |

Fault causes. The machine has one event for every fault,
`PP_FSM_EVENT_FAULT_RAISED`, without a cause, plus
`PP_FSM_EVENT_SELFTEST_FAILED`. The cause travels as a set of fault flags,
and the generated header `proto/pp_proto_defs.h` defines four of them:
over-current, power limit, thermal and self-test. Section 6.4 lists ten
entries, three of which join two conditions, so thirteen conditions in all,
and adds the flag of a watchdog restart. Nine conditions and that flag have
no bit yet:

| Cause in section 6.4 | Rules | Flag in the protocol today |
| --- | --- | --- |
| Over-current trip | F-18, F-19 | Over-current |
| Sequencer that does not act | F-21 | None |
| Reverse current | F-22 | None |
| Loss of PWR_GOOD ("carrier supply") | F-2, F-7 | None |
| Failed rails test ("analog rails") | F-3, F-12 | None |
| VIN over-voltage | F-27 | None |
| VIN out of range (absent or reversed) | F-26 | None |
| Power limit | F-14 | Power limit |
| Thermal limit | F-15 | Thermal |
| Overload of the source output | F-32 | None |
| External voltage on the source output | F-33 | None |
| Failed start check (ladder node in ampere mode, output of the source) | F-25, F-28 | None |
| Failed self-test | F-3, F-12, F-36 | Self-test |
| Watchdog restart | F-8 | None |

The rules also name reports that are not in the protocol: a trip within
100 ms of GATE_OUT as "start over-current" and the count of consecutive
trips (F-19), a set-point reported as settled after three readings inside
the band (F-30), and "DUT above the set-point" (F-31).

The state machine and its header were written before draft A2. The comment
of `PP_FSM_EVENT_FAULT_RAISED` still names three causes, over-current trip,
power limit and thermal; the list above is the one of the specification.

### The 36 Rules That Guard Hardware (Section 6.6)

The carrier is built so that no state of the controller pins damages it.
What the parts cannot do is left to firmware, and section 6.6 is the one
list of it (D-81): rules F-1 to F-36, each with its figure and with what it
guards. The section also asks that the hardware-independent logic of every
rule has a unit test before a board is powered for the first time. The
groups below are the six tables of that section.

| Group | Rules | What they ask | State |
| --- | --- | --- | --- |
| Controller pins and start | F-1 to F-9 | Every pin released after any restart (F-1); nothing driven while PWR_GOOD is low, valid after 10 ms (F-2); the bring-up order after PWR_GOOD (F-3); the pins that are never outputs, with a unit test of the pin table (F-4); drive strengths and pad pulls (F-5); the two chip selects and the DAC frame `0x5000 \| code`, with a unit test (F-6); the reaction to a falling PWR_GOOD within 50 µs (F-7); the watchdog with a time-out of 100 ms or less (F-8); no header pin as activity indicator of the boot loader (F-9) | Not started |
| Monitor, supplies and budget | F-10 to F-15 | Eight monitor channels at 100 SPS (F-10); which input supplies, read from the channel of the 5 V rail at 1.67 V (F-11); the rails test every 10 ms (F-12); the CC class after three equal readings (F-13); the budget as an input current of 0.45 A, 1.4 A or 1.7 A and the 4.25 V limit of the rail (F-14); the thermal limit (F-15) | Not started |
| Range sequencer and over-current trip | F-16 to F-22 | R3 forced within 100 ns of the jump comparator, never blanked (F-16); the step-up comparator ignored for 2.0 µs after a range change, make-before-break (F-17); the trip after 12 µs in R3, latched (F-18); no retry, 100 ms of refusal, trips counted (F-19); the sequencer started after the rails test, GATE_OUT only through its program (F-20); a sequencer that does not act found within 2 ms (F-21); under-range below a code of 650 for 100 samples, R3 requested, no step down for 1 s, reverse-current fault after 100 ms (F-22) | Not started. F-16 to F-18 are PIO programs; F-19 and F-20 are what firmware does around them (refusal, counting, the order of the start); F-21 and F-22 are firmware (section 4.4) |
| Path switches | F-23 to F-27 | The output pair closes last and opens first, 5 ms between mode requests (F-23); the order and the times of DUT power on, 40 ms and 50 ms (F-24); the ladder node no higher than VIN plus 0.1 V before the ampere pair closes (F-25); VIN inside 0.6 V to 5.4 V for 100 ms (F-26); the VIN_OV interrupt (F-27) | Not started |
| Source | F-28 to F-33 | The one start sequence of the source, with a unit test (F-28); the stop order (F-29); the set-point limited to 0.80 V to 5.00 V and calibrated at nine points (F-30); a DUT above the set-point followed down (F-31); overload (F-32); an external voltage above 5.3 V within 0.5 ms (F-33) | Not started |
| Acquisition and samples | F-34 to F-36 | The timing of the acquisition program (F-34); which samples are flagged: the settling window, 5 ms after a change of supply, over-range (F-35); when a zero calibration may read (F-36) | F-34 and F-36 not started; F-35 partly, see below |

The figures in the table are those of the specification: calculated,
simulated or taken from datasheets, as each rule says. None is measured.

The circuit simulations of 2026-10-10 ran against these rules without any
firmware: the [simulation guide](../simulation/README.md) has the account.
The range sequencer and the trip are a model of F-16 to F-18 in them,
because no program exists. The 100 ns of F-16, the blanking of F-17 and
the 12 µs of F-18 are inputs of those runs and not results. Phase 1
measures the reaction time of a PIO state machine (F-16); phase 3 runs
the programs of the sequencer and the trip and confirms the qualification
time (F-18). Where a run steps down or closes a switch, the instants are
written into it as the rules give them.

The simulations touch the text of these rules. Nothing is changed in
section 6.6 until the project owner decides, and section 16 of the
specification lists the places as open; the reading window at 15 MHz
under F-34 and the 0.38 V under F-35 are in the simulation guide only.
The four decisions that followed
the simulations on 2026-10-10, D-95 to D-98, change hardware and no rule.
All figures are simulated:

- **F-18.** While a large capacitor at the DUT recharges after a step to
  1.0 A, the over-current comparator is high for up to 12.83 µs, longer
  than the 12 µs of the rule, of which 8.174 µs at the most in R3. No run
  trips, because the model counts in R3 only. Proposed: the rule says
  that the 12 µs count in R3, the program counts the same way, and the
  criterion of section 11 is read in R3.
- **F-7.** PWR_GOOD is below 2.0 V at the controller pin 145.1 µs after
  the supervisor falls, not 0.05 ms to 0.07 ms after the rails begin to
  fall, and below 0.8 V after 604.5 µs, not 0.3 ms. The flag still does
  not lead the rails. These times are those of the rail monitor with
  1 nF at its comparator inputs. Decision D-95 makes the three capacitors
  10 nF, which is not drawn yet: the nodes become ten times slower, and
  the times are simulated again when the change is drawn.
- **F-8 and F-24.** The gate of the output pair is below 2 V within 7 µs
  at 5 V (6.288 µs). At 0.8 V it takes 7.274 µs to 7.448 µs, and 8.109 µs
  in the slow corner. With 100 µF the DUT voltage is at 10 % 6.458 ms
  after GATE_OUT at 5 V and 5.381 ms at 0.8 V, where F-24 says that it
  starts to rise 6 ms to 7 ms later.
- **F-23.** A mode pair that opens under load lifts VIN to 16.01 V to
  25.12 V, where the rule estimates 20 V to 24 V.
- **F-26 and F-28.** With the input leakage of the monitor converter at
  its datasheet maximum of 1 µA, the VIN channel reads 430 mV off, where
  F-26 allows 130 mV before calibration, and the channel of the ladder
  output 120 mV off, where F-28 asks for 100 mV.
- **F-34.** By its datasheet the converter shifts its result out after
  convert-start has fallen, where section 4.6 says "while that line is
  still high". With one reading instant for weak and for strong pads the
  reading window at 15 MHz, the 500 kSPS option, is 11.43 ns against the
  13.33 ns of two system clocks; at 100 kSPS the window is far wider.
- **F-35.** A step of the 5 V rail of more than 0.3 V flags samples for
  5 ms. A load step of 1 A moves the rail by 282.3 mV behind a cable of
  0.15 Ω, which is an assumption, so ordinary load steps come close to
  that level: the 1.34 A that section 4.1 calculates for 5 V at 1 A would
  move the rail by about 0.38 V (calculated from the 0.28 V per ampere of
  that run).

What the core already holds of these rules:

- **F-35, settling window: partly.** `pp_range_tracker_update` flags the
  sample whose range bits differ from the sample before it and the ones
  that follow, the first one included, and a new change restarts the count.
  That is the rule. The length is the argument `settle_samples` of
  `pp_range_tracker_init`: the default of seven samples (D-76) is not a
  constant of the core, and nothing stores it. A test uses seven as one of
  its lengths, no more. The second and third sentence of F-35 are not
  started: the 5 ms after a change of the supplying input or a step of the
  5 V rail, and the over-range mark for a code of 65535 or a set CMP_JUMP
  bit. The sample word has no bit for an over-range mark (see the protocol
  items below).
- **Step-down rule (section 4.4): in the core.** `pp_downrange.h` has the
  default of 100 consecutive samples and the hold-off of four blocks that
  section 4.4 gives, and SET_DOWN_N maps to
  `pp_downrange_set_consecutive`. The thresholds are a table of ADC codes
  the caller supplies. Section 4.3 gives the levels as currents, 60 µA for
  R1, 1.8 mA for R2 and 60 mA for R3, and calls them firmware thresholds;
  neither these values nor their conversion to codes is in the code.
- **F-22, under-range: not started, and it changes the step-down rule.**
  F-22 asks for R3 on codes below 650 and forbids a step-down request
  until 1 s after the flag clears. `pp_downrange_update` has no input that
  blocks it: on the same low codes it would ask for a step down. The rule
  needs that input and a test before F-22 is called done. One point is to
  be settled with it: section 6.3 evaluates the rule on a block of 256
  samples, which is 2.56 ms at 100 kSPS, and F-22 asks for R3 at the latest
  2 ms after the first sample below the level. F-21 has the same limit of
  2 ms and does not say where firmware reads CMP_JUMP.
- **Port to the front end.** `pp_afe_port.h` has six calls: range lock,
  step down, mode, output, fault latch read and clear. Draft A2 needs more
  behind it: the request for R3 of F-22, the trip count of F-19, the times
  of F-23 and F-24, the checks of F-25 and F-26. The port is to be reviewed
  against section 6.6 when the `afe` logic is written.

### Calibration Record (Section 8)

`components/cal` is empty: no record layout, no flash access, no zero
routine. The device sends raw codes and the host converts them, so the
firmware side of calibration is storage, identity and the zero
measurements.

| Item of section 8 | State |
| --- | --- |
| Record in the flash of the module: gain and offset per range, gain and offset of the DAC, settling window length, calibration temperature, version field, CRC | Not started |
| The 64-bit chip identifier of the RP2350 in the record; a record with another identifier is reported as not calibrated and nominal values are used (D-82) | Not started |
| Serial number and revision of the carrier, entered at calibration, so that the host can show them at every connection | Not started |
| A missing or corrupt record falls back to nominal values and is flagged in GET_INFO | Not started |
| Open-switch zero of every range at start-up and on CAL_ZERO, 200 ms or more after the output opened (F-36), kept in RAM; taken again when the board temperature has moved by more than 2 °C with the output off | Not started |
| Closed-switch zero of R0 with the output on and the terminals open, 300 ms or more after GATE_OUT rose, stored and subtracted (D-59, F-36) | Not started |
| DAC set-points: nine points or more (D-58, F-30) | Not started |
| No flash write while streaming or while a path is closed (section 6.3); only `cal` writes flash (section 6.1) | Not started |

The protocol has the commands CAL_ZERO and CAL_WRITE, and CAL_WRITE
carries one gain and one offset for a range or for the DAC (section 7.4).
How the other fields of the record reach the device and the host (chip
identifier, carrier serial number and revision, calibration temperature,
closed-switch zero, nine set-points) is not defined in section 7; the
response data of GET_INFO is provisional until the protocol is frozen in
phase 6.

The rules of section 6.6 name constants that are stored as well and that
the list of section 8 does not mention: the offset of the VIN channel,
stored at calibration (F-26), and the constants of the input model and the
thermal limit, both taken from the first board (F-14, F-15). Where they
are kept is not decided; section 16 lists it as an open point.

### What the Protocol Does Not Hold Yet (Section 16)

Draft A2 reports more to the host than
[`protocol/definition.toml`](../protocol/definition.toml) defines. The
protocol item of section 16 lists what is missing:

- a mark for over-range and for under-range samples (F-22, F-35); the
  sample word has an invalid bit, a fault bit and four reserved bits;
- the invalid mark for the 5 ms after a change of supply (F-35); section
  7.3 defines the invalid bit for a range change only;
- the fault flags that section 6.4 names beyond the four that exist (the
  table of fault causes above);
- the input in use and the CC class in the status record (F-14);
- the power budget as a current (D-49); the event of section 7.4 carries
  milliwatts;
- the instant from which the host counts the 250 ms of output settling
  (section 9).

The status record itself is short of its own description. Section 7.4
gives GET_STATUS the state, the faults, the dropped blocks, VOUT, VIN, the
5 V rail, the temperature and the power budget; the provisional response
holds the first three only. The core encodes no response data at all: it
has the envelope, and the handlers that fill it are not written.

Section 16 also lists what sections 6 to 8 leave undecided, and the port
cannot build on these points before each has a decision: how the
calibration record travels, the reports that rules name without a place
in the protocol (F-19, F-30, F-31), where the constants of F-14, F-15 and
F-26 are stored, the step in which F-21 and F-22 are evaluated, and how a
fault is reported while firmware still waits in BOOT.

The order is fixed by the specification: these items go into the
definition file first, with the generated files and the shared test
vectors, before the firmware of phase 1 reports them. No protocol number
is ever typed in C. The header `proto/pp_proto_defs.h` is generated; a new
state or command then stops the build where the code has to follow, for
instance at the list of known commands in `pp_command.c`. A change that an
older peer cannot read is a breaking change and raises the protocol
version.

## Next Steps for the Firmware

In this order. The phases are those of section 13 of the specification; a
phase is closed by a report with measurements, and none is closed.

1. **Protocol items of section 16 (before phase 1 reports them).** Add the
   marks, fault flags and status fields listed above to the definition
   file, regenerate, and extend the codec of `proto` and its tests. The
   host package changes in the same step.
2. **Core for draft A2, on the PC (phase 1 onward).** No board is needed
   for: the default of the settling window as a stored constant, the
   under-range rule and its effect on the step-down rule (F-22), the
   over-range mark (F-35), fault causes in `app`, the command handlers
   with the rules of section 7.4, the pin table with its test (F-4), the
   DAC frame with its test (F-6), the start sequencer of the source with
   its test (F-28), the input and budget arithmetic (F-11, F-13, F-14) and
   the record of `cal`. Each comes with its unit test.
3. **Port to the Pico SDK (phase 1).** A CMake project for the Pico 2 that
   builds the components from their `sources.cmake`, with `main` rewritten
   for two cores. The ESP-IDF project, `sdkconfig.defaults` and the
   ESP-IDF lines of the component `CMakeLists.txt` files go. The Pico SDK
   and the `arm-none-eabi-gcc` compiler are prerequisites.
4. **Risk prototypes on a Pico 2 with an ADC evaluation module
   (phase 1).** Exit criteria of the phase: the converter captured through
   PIO and DMA at 100 kSPS and at 500 kSPS for 10 minutes with no lost
   sample; the side data read in the same word; the reaction of a PIO
   state machine to an input edge measured, 100 ns or less from the pin of
   the jump comparator to the gate line of range 3 (F-16); USB throughput
   of 500 kB/s or more sustained; CPU load recorded. The decision on a
   real-time kernel for core 0 follows from the measured latencies. If the
   sustained rate stays below 500 kB/s, section 6.5 packs a sample into
   3 bytes before the sample rate is lowered, which is a change of the
   protocol. The emulator for the PIO programs is chosen in this phase
   (section 18.2), and the test application on the controller module
   starts here.
5. **Acquisition on the analog front end (phase 2).** Settling window
   confirmed with a fast load step; the oversampling decision, which
   decides whether `acq` decimates.
6. **Range sequencer and trip (phase 3).** The PIO programs of the
   sequencer and the trip (F-16 to F-18, started and used as F-19 and F-20
   say) run in an emulator and on the controller; the qualification time
   of the trip confirmed (12 µs by default, F-18); F-21 and F-22 with the
   reverse-current test.
7. **Source and supplies (phase 4).** `smu` and `monitor`: start and stop
   of the source, set-point, budget, rails test, thermal limit (F-10 to
   F-15, F-23 to F-33), against the tests of R-08, R-09, R-13 and R-14.
8. **Carrier board (phase 5).** Start-up rules F-1 to F-9 on the real
   board. Before a DUT is connected, section 16 asks for the output open
   within 100 ms of a halted supervision task (F-8) and for gate lines
   that stay low across a restart.
9. **Calibration and protocol freeze (phase 6).** The zero routines, the
   record in flash and the final response data of GET_INFO, GET_STATUS
   and CAL_ZERO.

## Architecture

The firmware follows the ports and adapters pattern. The logic of the
instrument is plain C11 that knows nothing about the SDK of the controller
or about the board. It reaches the hardware only through small interfaces,
the ports. Adapters implement the ports with the drivers of the SDK, and
`main` wires the two together.

```text
main                 composition root: creates adapters, injects them
 │
 ├──► app            device state machine
 ├──► acq            settling window, step-down rule
 ├──► afe            port to the analog front end
 │     │
 │     ▼
 ├──► proto          CRC, frames, sample word, stream and command payloads
 │     │
 │     ▼
 └──► base           status codes, byte access, lock-free block queue
```

Dependencies point downward only. `base` depends on nothing, and no
component below `main` includes an SDK header in its hardware-independent
part.

| Component | Hardware-independent part | Depends on | State |
| --- | --- | --- | --- |
| `base` | Status codes, little-endian access, block queue | Nothing | Done |
| `proto` | CRC-16, frame encoder and parser, sample word, stream payload, command, response and event envelopes | `base` | Done |
| `acq` | Settling window after a range change, step-down rule | `base`, `proto` | Those two done. Separation of result and side bits, decimation, the under-range and over-range marks and the PIO capture adapter not started |
| `afe` | Port to the analog front end | `base`, `proto` | Port declared, no source file. Range lock and fault logic, the PIO programs of the sequencer and the trip and the GPIO adapter not started |
| `app` | Device state machine | `base`, `proto` | State machine done. Command handlers, start-up self-test, supervision and watchdog not started |
| `smu`, `monitor`, `cal`, `usb_link` | As in section 6.1 of the specification | | Not started: each directory holds a placeholder file only, and the builds do not list them |
| `main` | Composition root | `base`, `proto`, `acq`, `afe`, `app` | ESP-IDF `app_main`: banner and state machine |

`base` holds what every other component shares, so that none of them has to
depend on a sibling for a status code or for the queue. The components are
the ones of section 6.1 of the specification.

### Rules for the Hardware-Independent Code

- C11, compiled with warnings as errors.
- No SDK header, no dynamic allocation, no global variable. Every function
  works on a context structure and on buffers the caller supplies.
- Every number of the wire protocol comes from `proto/pp_proto_defs.h`, which
  is generated from [`protocol/definition.toml`](../protocol/definition.toml).
  Do not edit the header; change the definition and run
  `python protocol/generate.py`.
- Public names start with `pp_`.
- Each module has a unit test, and the coverage gate below applies to it.

### Patterns and Why They Are Used

- **Ports and adapters.** The core is tested on a PC in milliseconds, without
  a board, and before the board exists. It is also why the change of
  controller left the core untouched. `afe/pp_afe_port.h` is the first port;
  `test/host/support/fake_afe.c` is its test double.
- **Lock-free single-producer, single-consumer queue** (`pp_blockq`). The
  acquisition side must never wait for the USB side. Each index has one
  writer, a full queue refuses the block and counts the drop, and the storage
  belongs to the caller.
- **Incremental parser** (`pp_frame_parser_feed`). Bytes arrive from USB in
  pieces of any size. The parser keeps its own state, does no input or
  output, and resynchronizes after noise or a damaged frame.
- **Table-driven state machine with an observer** (`pp_fsm`). The states and
  transitions of section 6.4 are one table that can be compared with the
  specification. The machine decides the next state; the observer performs
  the actions, so the machine itself touches no hardware.
- **Caller-owned memory.** No heap means no fragmentation and no allocation
  failure in the real-time path, and it makes the memory budget visible.
- **One manifest per component** (`sources.cmake`). The target build and the
  host test build read the same list of sources and dependencies, so they
  cannot drift apart.

## Layout

```text
firmware/
├── CMakeLists.txt        Target project file (ESP-IDF, until the port)
├── sdkconfig.defaults    Configuration of the ESP-IDF build, each entry with its reason
├── cmake/                Warning flags shared by both builds
├── main/                 Composition root (app_main of the ESP-IDF build)
├── components/
│   └── <name>/
│       ├── CMakeLists.txt    Component of the target build, built from sources.cmake
│       ├── sources.cmake     Sources and dependencies of the component
│       ├── include/<name>/   Public headers
│       ├── src/              Hardware-independent sources
│       └── port/             Adapters for the SDK of the controller (none yet)
├── test/
│   ├── .clang-tidy       Static analysis checks relaxed for the tests
│   └── host/
│       ├── CMakeLists.txt    Host test project
│       ├── CMakePresets.json Presets: debug, coverage, sanitize, tsan
│       ├── generated/        Protocol test vectors (generated)
│       ├── support/          Test doubles
│       └── tests/            One test file per module
├── gcovr.cfg             Coverage filters and thresholds
├── .clang-format         Code format
├── .clang-format-ignore  Generated protocol files, which the formatter skips
├── .clang-tidy           Static analysis checks
└── .clangd               Editor support: points clangd at the host test build
```

The components `base`, `proto`, `acq`, `afe` and `app` have this
structure; `afe` has no `src/` yet. `smu`, `monitor`, `cal` and `usb_link`
are empty directories.

## Building the Firmware

### For the Pico 2

There is no target build for the Pico 2 yet. The port adds a Pico SDK
project to this directory (step 3 of the next steps above): one CMake
project that builds the components from their `sources.cmake`, the
adapters in `port/` and the PIO programs, and produces a `.uf2` image.
That image is copied to the USB drive the Pico 2 shows when it starts with
its BOOTSEL button held; no programmer is needed. This section gets its
commands when that project exists.

### ESP-IDF Build of the First Plan

Kept until the port replaces it. It shows only that the core compiles for a
target: the image is for the ESP32-S3, not for the controller of the
instrument, and it drives no pin. It needs
[ESP-IDF](https://github.com/espressif/esp-idf) v6.0. Load the ESP-IDF
environment in the shell first, then run these from the root of the
repository:

```sh
idf.py -C firmware set-target esp32s3
idf.py -C firmware build
idf.py -C firmware -p PORT flash monitor
```

In PowerShell the environment is loaded with
`. "$env:IDF_PATH\export.ps1"`, and on Linux and macOS with
`. $IDF_PATH/export.sh`.

`set-target` is needed once per checkout. `sdkconfig` and `build/` are
generated and are not committed; `sdkconfig.defaults` is.

## Host Tests

The unit tests compile the hardware-independent sources with a native
compiler and run them with [Unity](https://github.com/ThrowTheSwitch/Unity),
which CMake downloads at the first configuration. They need CMake 3.20 or
later, Ninja and gcc. They do not depend on the controller.

Run these from `firmware/test/host`:

```sh
cmake --preset debug
cmake --build --preset debug
ctest --preset debug
```

How the tests are organized:

- One executable per module, `tests/test_<module>.c`, registered with CTest
  under the name of the module.
- The CRC, the frames and the sample word are checked against the vectors in
  `generated/pp_proto_vectors.h`. The host software checks the same vectors,
  so both ends of the protocol agree byte for byte.
- The frame parser is also tested with every chunk size, with noise, with
  damaged and truncated frames, and with frames hidden inside a false frame.
- `blockq_threads` runs the queue under two real threads. It is built when
  POSIX threads are available.

### Coverage

```sh
cmake --preset coverage
cmake --build --preset coverage
ctest --preset coverage
cmake --build --preset coverage --target coverage
```

The last command runs [gcovr](https://gcovr.com/) with `firmware/gcovr.cfg`
and writes `build/coverage/coverage.html`. It measures the code under
`components/` only and fails below 90 % line coverage or 80 % branch
coverage. Running `gcovr` in `firmware/` prints the same report.

### Sanitizers

```sh
cmake --preset sanitize && cmake --build --preset sanitize && ctest --preset sanitize
cmake --preset tsan && cmake --build --preset tsan && ctest --preset tsan
```

`sanitize` builds with AddressSanitizer and UndefinedBehaviorSanitizer and
`tsan` with ThreadSanitizer. Both need Linux or macOS: MinGW on Windows ships
no sanitizer runtime. If ThreadSanitizer stops with "unexpected memory
mapping", run the tests with address space randomization disabled, for
example `setarch $(uname -m) -R ctest --preset tsan`.

## Formatting and Static Analysis

These targets belong to the host test project. Run them from
`firmware/test/host` after `cmake --preset debug`:

| Command | What it does |
| --- | --- |
| `cmake --build --preset debug --target format` | Formats every C file with clang-format |
| `cmake --build --preset debug --target format-check` | Fails if a C file is not formatted |
| `cmake --build --preset debug --target tidy` | Runs clang-tidy on the sources and the tests |
| `cmake --build --preset debug --target cppcheck` | Runs cppcheck on `components/`, `main/` and the test doubles |

- `.clang-format`: four spaces, 100 columns, the brace of a function on its
  own line, the star next to the name.
- `.clang-tidy`: the bugprone, cert, clang-analyzer, misc, performance,
  portability and readability groups, with every finding an error. The file
  lists each disabled check with its reason. `test/.clang-tidy` relaxes one
  check for the tests.
- cppcheck runs with the warning, style, performance and portability checks
  at the exhaustive level, and any finding fails the run.
- The generated protocol headers are excluded from all three.
- `main/app_main.c` needs the headers of the target SDK, so clang-tidy does
  not analyze it; the target build compiles it with warnings as errors.

## Adding Code

- **A hardware-independent module:** put the header in
  `components/<name>/include/<name>/`, the source in `src/`, add the source
  to `sources.cmake`, write `test/host/tests/test_<module>.c` and register it
  with `pp_add_test` in `test/host/CMakeLists.txt`.
- **An adapter:** it belongs to the port to the Pico 2 and goes in
  `components/<name>/port/`, listed in the `CMakeLists.txt` of the component
  only, never in `sources.cmake`. It implements a port declared in a public
  header and is created in `main`. Do not add adapters for ESP-IDF: that
  build is being replaced.
- **A protocol constant:** change `protocol/definition.toml` at the root of
  the repository and regenerate. The compiler then points at the code that
  has to follow, for instance the list of known commands.
- **A firmware rule of section 6.6:** put its hardware-independent logic in
  the component that section 6.1 names for it, as a module with its unit
  test like any other. The specification asks for that test before a board
  is powered for the first time. Refer to the rule by its ID (F-22, not
  "the under-range rule" alone), so that the code can be compared with the
  specification.
- **A PIO program:** it belongs to the port to the Pico 2. Where the
  `.pio` files live in the tree is decided with the port. Section 13 asks
  that the programs of the range sequencer are verified in an emulator and
  on the controller.
