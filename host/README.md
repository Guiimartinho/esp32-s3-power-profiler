# Host Software

Python package that talks to the instrument: the wire protocol, the
transports, a device client, capture helpers and a simulated instrument for
working without hardware.

The package knows the instrument only through the wire protocol, so the
change of controller from the ESP32-S3 to the Raspberry Pi Pico 2 (D-39 of
the [specification](../docs/specification.md)) did not touch it. Its names,
`s3-power-profiler` and the `s3pp` command, date from the first controller
and are kept for now; see [Names](#names).

The package was written before draft A2 of the carrier board. The
specification was rewritten for that draft, and the package has not followed
yet. [What Draft A2 Asks of the Host Software](#what-draft-a2-asks-of-the-host-software)
lists the differences one by one, and [Next Steps](#next-steps) puts the
work in order.

## Status

In one sentence: the communication stack is written and tested against a
simulated instrument, the application on top of it is not written, and
nothing has run against hardware, because no hardware exists yet.

What exists, at version `0.1.0.dev0`, classified as pre-alpha in
`pyproject.toml`. Every module below has its own test module, except the
`Transport` interface in `transport/base.py`, which holds no logic, and the
client is tested end to end against the simulator:

| Layer | What it does today | Source |
| --- | --- | --- |
| `protocol` | CRC, frame encoder and incremental decoder with resynchronization, sample word, stream payload, the twelve commands, the three events | `protocol/crc.py`, `frame.py`, `sample.py`, `stream.py`, `commands.py` |
| `transport` | The `Transport` interface, an in-memory pipe and a serial port adapter | `transport/base.py`, `memory.py`, `serial.py` |
| `device` | `DeviceClient`: one method per command, responses matched by sequence number, stream frames and events queued, link counters | `device/client.py` |
| `capture` | Gap detection from the sample index, conversion of codes into current with one gain and one offset per range, mean, minimum and maximum of a capture | `capture/reader.py`, `calibration.py`, `statistics.py` |
| `sim` | The instrument side of the protocol with the state rules of section 7.4, and a synthetic waveform | `sim/simulator.py`, `loopback.py` |
| `cli` | `s3pp --version` and `s3pp simulate` | `cli.py` |

What is not written, all of it asked by sections 8 and 9 of the
specification:

- A capture command for a real instrument. `s3pp` has one subcommand,
  `simulate`. The serial adapter exists, but no command opens a port.
- The desktop viewer: live plot with min/max decimation, digital channels
  below the trace, controls for mode, voltage, DUT power, range and
  calibration. Its toolkit is not chosen.
- Selection statistics with charge and energy, and the mean of 100 samples
  in range 0.
- Export to CSV and to a compact binary format.
- Burst detection and the battery-life estimate.
- The marks that follow from the hardware of draft A2: over-range,
  under-range, output settling, logic channels invalid at a low output
  voltage.
- The guided calibration procedure, and reading the calibration record of
  an instrument. The scripts planned in [`tools/`](../tools/README.md) are
  not started either.

What the results are worth:

- The tests show that the code does what its tests say, against a simulator
  written from the same specification. They say nothing about the firmware,
  which has no command handler yet, and nothing about the instrument.
- The serial adapter is tested only with the loopback port of pyserial. The
  throughput of the 100 kSPS stream through it has not been measured.
- Every current that the package prints comes from the nominal calibration
  table, a set of design targets. No value in this package is a measurement,
  and the nominal table does not match the nominal values of draft A2 yet.

## What Draft A2 Asks of the Host Software

This section follows sections 7, 8, 9 and 16 of the specification and
compares each with the code. Paths are relative to
`src/s3_power_profiler/`. Where a figure is marked "calculated", it was
computed for this comparison from the constants named beside it; nothing
here is measured.

### Nominal Calibration

The host converts a code into a current with
`I = (code − offset[r]) × gain[r]`, and the nominal gain is
`VREF / (65536 × G × R[r])` (section 8). `nominal_table()` in
`capture/calibration.py` implements that formula, with constants that
predate draft A2:

| Constant in `capture/calibration.py` | Code | Draft A2 | Where the specification says it |
| --- | --- | --- | --- |
| `NOMINAL_VREF` | 2.5 V | 2.5 V | Section 4.6 |
| `NOMINAL_AMPLIFIER_GAIN` | 20.0 | 19.93, set by the 523 Ω gain resistor R123 | Sections 4.5 and 8 |
| `NOMINAL_SHUNTS`, range 0 | 1000 Ω | 1 kΩ | Section 8 |
| `NOMINAL_SHUNTS`, range 1 | 33 Ω | 31.95 Ω: 33 Ω with the 1 kΩ of range 0 in parallel | Sections 4.3 and 8 |
| `NOMINAL_SHUNTS`, range 2 | 1 Ω | 0.999 Ω, for the same reason | Section 8 |
| `NOMINAL_SHUNTS`, range 3 | 0.1 Ω | 0.1 Ω | Section 8 |
| `NOMINAL_PEDESTAL` | 0.050 V, 1310.7 codes | About 1313 codes at zero current, from the divider R121 and R122 | Section 4.5 |

Range 0 has no switch and stays in circuit, so in ranges 1 to 3 the current
divides between the selected shunt and the 1 kΩ. That is why the nominal
resistance of a range is the parallel value and not the value printed on
the part.

The effect on the current of one code (calculated from both sets of
constants):

| Range | Code today | With the values of draft A2 | The code reads low by |
| --- | --- | --- | --- |
| R0 | 1.907 nA | 1.914 nA | 0.35 % |
| R1 | 57.80 nA | 59.91 nA | 3.5 % |
| R2 | 1.907 µA | 1.916 µA | 0.45 % |
| R3 | 19.07 µA | 19.14 µA | 0.35 % |

An error of 3.5 % in range 1 is larger than the accuracy target of R-05,
±1 % of reading ±0.1 % of range, which is 1.1 % of reading at full scale.
R-05 is a target after calibration, so the comparison shows the size of the
error and is not a test of the requirement. A real instrument is meant to
report its own calibrated table, so the nominal table matters in three
places: the simulator, the first look at an uncalibrated board, and the
fallback when the stored record is missing or corrupt (section 8).

The tests in `tests/test_calibration.py` hold the old values too and change
together with the constants:

- `FULL_SCALE_CURRENTS` is 100 µA, 3.03 mA, 100 mA and 1 A for 2.0 V above
  the pedestal. With the values of draft A2 that is 100.4 µA, 3.141 mA,
  100.5 mA and 1.004 A (calculated).
- `test_nominal_resolution_matches_the_specification` expects 58 nA per code
  in range 1; the table of section 4.3 says 60 nA.
- `test_nominal_offset_is_the_pedestal_in_codes` expects about 1300 codes;
  section 4.5 says about 1313.

The circuit simulations of 2026-10-10 give the values of draft A2 again,
from the netlist of the schematic: a gain of 19.93, a code of 1313 at zero
current, and 1.914 nA, 59.91 nA, 1.916 µA and 19.14 µA for one code in
ranges 0 to 3 (simulated;
[`signal_chain/transfer`](../simulation/results/signal_chain/README.md#signal_chaintransfer)).
With the whole path as one circuit the values are the same within the
last digit, 59.92 nA in range 1
([`system/accuracy`](../simulation/results/system/README.md#systemaccuracy)).
The simulations do not run this package: a bench converts codes with
arithmetic of its own and the nominal values of the specification, so its
result says nothing about `capture/calibration.py`.

### Calibration Record

Section 8 defines what an instrument stores in the flash of its module, and
section 9 what the host does with it. The package can send calibration
values. It cannot read any back.

| Item of section 8 | In the package today |
| --- | --- |
| Gain and offset of each range | Sent with `DeviceClient.write_calibration` (CAL_WRITE). Not readable: `DeviceInfo` in `protocol/commands.py` has three fields, the protocol version, the hardware revision and the firmware version |
| DAC gain and offset | Sent with CAL_WRITE and the target `CAL_TARGET_DAC` |
| DAC calibration at nine set-points or more (D-58, F-30) | No message carries it: CAL_WRITE takes one gain and one offset per target |
| Closed-switch zero of range 0 (D-59) | No message and no code. `RangeCalibration` has one offset per range |
| Settling window length, calibration temperature | No message carries them |
| Version field and CRC of the record | Not visible to the host |
| 64-bit chip identifier of the RP2350; "not calibrated" when it does not match | No field in GET_INFO; the host cannot tell a calibrated instrument from one on nominal values |
| Serial number and revision of the carrier, shown at every connection (D-82) | No field and no code |
| Fallback to nominal values, flagged in GET_INFO | `CalibrationTable.nominal` exists as a flag on the host side; nothing sets it from an instrument |

Section 7.4 names "range table, calibration" as content of GET_INFO and
says that its response data is provisional until the protocol is frozen in
phase 6. The layout that the specification gives for now, and that
`_INFO` in `protocol/commands.py` implements, is five bytes. `s3pp simulate`
therefore always uses `nominal_table()` (`run_simulate` in `cli.py`).

The zero calibration (CAL_ZERO) is a command without data in both
directions. The waits that guard it (200 ms after the output opened, 300 ms
after it closed, F-36) belong to firmware; the simulator answers at once.

### Simulator Constants

`SimulatorConfig` in `sim/simulator.py` holds the behavior of the simulated
instrument. Its defaults against the specification:

| Field | Default | Specification of draft A2 | Agrees |
| --- | --- | --- | --- |
| `settle_samples` | 4 | Seven samples flagged invalid after a range change, a stored constant (F-35; 45 µs to 0.1 % of range, simulated, section 4.5) | No |
| `down_n` | 100 | 100 samples for the step-down rule (section 4.4) | Yes |
| `min_voltage_mv`, `max_voltage_mv` | 800, 5000 | SET_VOLTAGE from 800 mV to 5000 mV (section 7.4, F-30) | Yes |
| `block_samples` | 256 | 256 samples in a stream frame (section 7.2) | Yes |
| `adc_low`, `adc_high` | 1311, 53740 | No requirement: the pedestal and 2.0 V above it, used as the ends of a triangle | Arbitrary |
| `waveform_period`, `range_dwell` | 2000, 1000 | No requirement: the simulator steps through the four ranges on a fixed schedule, whatever the code is | Arbitrary |

The host itself holds no settling constant: it trusts the invalid bit of
each sample. The seven samples matter for the simulator, and later for the
calibration record that carries the measured length.

What the simulator does not model, because the protocol cannot carry it yet
or because it is timing of the firmware:

- Over-range and under-range samples, and the 5 ms of invalid samples after
  a change of supply (F-22, F-35).
- The fault bit of the sample word: `_sample_word` never sets it.
- Fault causes beyond the four of `Fault`; see
  [Protocol Items](#protocol-items).
- The start sequences behind DUT_POWER (F-24, F-28), which take tens to
  hundreds of milliseconds, and the 100 ms for which DUT_POWER on is refused
  after an over-current trip (F-19). The simulator changes state at once.
- A capture paced in real time. `Simulator.serve` sends one frame per turn.

The docstring of the module says what follows from this: the simulator
models the behavior of the protocol, and says nothing about the performance
of the instrument.

### Statistics, Marks and Display

Section 9 asks for more than `capture/statistics.py` does, and on one point
for something different.

| Section 9 asks | In the package today |
| --- | --- |
| Flagged samples (settling window, over-range, under-range) are not dropped: plot, mean, charge and energy use the first valid sample after them in their place (section 4.10) | Different. `StatisticsAccumulator.add` filters the words with the invalid bit out and computes on the rest; `test_invalid_samples_are_counted_and_left_out` fixes that behavior. Leaving samples out shortens the time base: a mean moves little, but charge and energy, which are sums over time, would come out too small |
| Average, maximum, charge (µC and mAh) and energy of a selection | Mean, minimum and maximum of a whole capture. No charge and no energy: the package holds no sample period, and no message carries the output voltage. No selection: statistics run over everything that was added |
| Mark for over-range samples: code 65535 or the jump comparator bit set (F-35) | Not written. The sample word has no such bit yet |
| Mark for under-range samples: code below 650 for 100 samples (F-22) | Not written. The sample word has no such bit yet |
| Output settling: the samples of the first 250 ms after the output is switched on are marked and kept out of statistics below 1 µA; the time is a constant of the host (sections 4.2 and 8) | Not written. No constant, and the protocol does not give the instant from which the 250 ms count |
| Logic channels shown as invalid while the monitored output voltage is below 1.67 V, with a setting for jumper position 2-3 of JP2; channels off by default (section 4.8) | Not written. The eight bits are decoded (`Sample.logic`, `SampleColumns.logic`), without any validity. GET_STATUS does not carry the output voltage in its present layout |
| Mean of 100 samples in range 0, the figure of the test of R-04 in source mode (section 11) | Not written |
| Serial number of the carrier shown at every connection | Not written; see [Calibration Record](#calibration-record) |
| Live plot with min/max decimation, digital channels below the trace | Not written |
| Controls for mode, voltage, DUT power, range and calibration | `DeviceClient` has a method for each command. No user interface |
| Export to CSV and a compact binary format | Not written |
| Burst detection and battery-life estimate | Not written |

What section 9 asks and the package has: the protocol layer without I/O,
transports behind one interface, the simulator, resynchronization on the
magic word, the CRC check and gap detection from the sample index
(`capture/reader.py`).

Samples with the fault bit are counted and kept in the statistics
(`fault_samples`). The specification does not say whether they count; that
is settled when the fault causes below reach the protocol.

Two things that the circuit simulations of 2026-10-10 show concern what the
host presents to a user. Both are simulated, and neither is in section 9
([simulation guide](../simulation/README.md#what-the-runs-show-about-the-instrument)):

- The reading of range 0 follows the load with the time constant of shunt
  and capacitor: 100 µs with the 100 nF of the instrument alone, and
  1.1 ms with 1 µF beside the load. A sample taken after the settling
  window is valid and can still be on its way to the load current.
- After a fast step with a capacitor beside the load the instrument can
  rest one range above the one that the current asks for, and it stays
  there: the step down from range 3 comes only below 60 mA (the table of
  section 4.3). 80 mA is then read in range 3, where one code is 19.14 µA
  in place of the 1.916 µA of range 2.

### Protocol Items

Draft A2 reports more than the protocol holds. Section 16 of the
specification lists the missing items as an open check, and they are
missing in [`protocol/definition.toml`](../protocol/definition.toml), from
which `protocol/_defs.py` is generated:

| Item of section 16 | State of the definition | What the host needs it for |
| --- | --- | --- |
| A mark for over-range and for under-range samples (F-22, F-35) | The sample word has the bits `invalid` and `fault`; bits 20 to 23 are reserved | The marks of the table above |
| The invalid mark for the 5 ms after a change of supply (F-35) | Section 7.3 defines the invalid bit for a range change only | Statistics that fill these samples like the others |
| The fault flags that section 6.4 names beyond the four of section 7.4 | `Fault` has `OVERCURRENT`, `POWER_LIMIT`, `THERMAL` and `SELFTEST` | Telling the user why the output opened: a sequencer that does not act (F-21), reverse current (F-22), carrier supply or analog rails (F-7, F-12), VIN over-voltage or out of range (F-26, F-27), overload or external voltage on the source output (F-32, F-33), a failed start check, a watchdog restart (F-8) |
| The input in use and the CC class in the status record (F-14) | `DeviceStatus` has the state, the fault flags and the dropped blocks | Showing which supply feeds the instrument and how much it may draw |
| The power budget as a current (D-49) | The event POWER_BUDGET_CHANGED carries milliwatts, 2 bytes (`build_power_budget_changed` in `protocol/commands.py`) | The budget is 0.45 A, 1.4 A or 1.7 A of input current |
| The instant from which the host counts the 250 ms of output settling | Nothing | The output-settling mark |

Two more gaps follow from sections 7.4, 8 and 9, and section 16 lists them
among the points of sections 6 to 8 that are not decided yet:
the fields of GET_INFO and GET_STATUS that the calibration record and the
logic-channel mark need (see above), and a way to carry the nine DAC
set-points, the closed-switch zero, the settling window and the
calibration temperature.

The rule for all of them, from section 7.5: the definition file changes
first. Nobody types a protocol number in Python or in C.

1. Edit `protocol/definition.toml`, and `protocol/vectors.toml` when a
   vector should cover the change.
2. Run `python protocol/generate.py` from the root of the repository. It
   rewrites `protocol/_defs.py` here, the C header of the firmware and the
   shared vectors.
3. Update section 7 of the specification and record the decision in its
   log. A change that an older peer cannot understand raises the protocol
   version, which is 1 today.
4. Change the layouts in `protocol/commands.py`, then the simulator and the
   client, with their tests. The firmware codec follows in the same change.

The steps are described in full in the
[protocol guide](../protocol/README.md). Section 16 sets the deadline: the
items are in the definition before the firmware of phase 1 reports them.

### Names

The distribution is `s3-power-profiler`, the module `s3_power_profiler` and
the command `s3pp` (`pyproject.toml`). "s3" stands for the ESP32-S3, the
controller that D-39 replaced, and the repository itself was renamed to
`open-power-profiler`. The description, the keywords and the help text of
the command no longer name the old controller; the three names still do.

No new names are chosen, and no decision on them is in the decision log.
A rename is a change of its own, because the names are used outside this
directory: in the path that `protocol/generate.py` writes to, in the Host
and Protocol workflows, in the protocol guide and in the changelog. Until
the owner of the project picks names, every command in this guide uses the
present ones.

## Next Steps

In order. Section 13 says that firmware and host software start in phase 1
and grow with each phase; the phase named with each step is the one whose
work needs it. None of these steps has started.

1. **Nominal values of draft A2** (before phase 1). Gain 19.93, shunts
   1 kΩ, 31.95 Ω, 0.999 Ω and 0.1 Ω and the pedestal of section 4.5 in
   `capture/calibration.py`, with the tests that hold the old values, and
   seven settling samples as the default of the simulator. This needs no
   protocol change and no hardware.
2. **Protocol items of section 16** (before the firmware of phase 1 reports
   them). Definition first, then the generated files, the vectors, the
   layouts in `protocol/commands.py`, the simulator and the client; the
   firmware codec in the same change.
3. **Statistics that follow section 9** (phase 1). Flagged samples filled
   with the first valid sample after them, charge and energy, the
   over-range, under-range and output-settling marks, the validity of the
   logic channels, the mean of 100 samples in range 0. The simulator learns
   to produce each case, so that the tests cover it.
4. **Capture from a real port** (phase 1). A capture command in `s3pp`
   beside `simulate`, and the first run against the firmware on a Pico 2.
   The exit criteria of phase 1 include a sustained USB throughput of at
   least 500 kB/s; the serial adapter has to keep up with it, which is not
   measured.
5. **Recording and export** (phases 2 to 4). CSV and the compact binary
   format, so that the measurements of the analog phases are kept as files
   and can go into their reports.
6. **Calibration** (phase 6). Reading the calibration record, the
   "not calibrated" flag, the carrier serial number, and the guided
   procedure of section 8 together with the scripts of `tools/`: per-range
   gain at two points, closed-switch zero, DAC at nine set-points or more.
7. **Desktop viewer** (phase 6). Live plot with min/max decimation, digital
   channels, controls, selection statistics, burst detection and the
   battery-life estimate. The toolkit and any numeric library are open
   choices; the package has one runtime dependency today, pyserial.
8. **Protocol freeze** (phase 6). The provisional layouts of
   `protocol/commands.py` become final. Phase 6 ends when R-05 (accuracy)
   and R-15 (capture, live view, statistics and export on Windows, Linux
   and macOS) are demonstrated end to end, with a report in
   `docs/reports/`.

## Architecture

The package is `s3_power_profiler`. It is built in layers, and each layer
depends only on what the table lists.

| Package | Role | Depends on |
| --- | --- | --- |
| `protocol` | Frames, CRC, sample word, stream payload, command, response and event envelopes | Nothing |
| `transport` | The `Transport` interface and its adapters: `SerialTransport` and `MemoryTransport` | Nothing |
| `device` | `DeviceClient`: sends commands, matches responses, collects stream frames and events | `protocol`, the `Transport` interface |
| `capture` | `StreamReader` with gap detection, calibration, statistics | `protocol` |
| `sim` | `Simulator`, a deterministic fake instrument, and `connect_simulator` | `protocol`, the `Transport` interface; `connect_simulator` also uses `MemoryTransport` |
| `cli` | The `s3pp` command | `sim`, `device`, `capture`, `protocol` |

`errors` holds every exception of the package and is used by all layers.

```text
                 cli
                  │
      ┌───────────┼───────────┐
      ▼           ▼           ▼
     sim        device     capture
      │           │           │
      ├───────────┤           │
      ▼           ▼           ▼
  Transport    protocol ◄─────┘
  interface
      ▲
      │ implemented by
  SerialTransport, MemoryTransport
```

The design rules behind it:

- **The protocol does no I/O.** Encoders return bytes and decoders take
  bytes. `FrameDecoder` accepts chunks of any size, resynchronizes on the
  magic word and counts what it discards, so it can be tested with plain byte
  strings.
- **Ports and adapters.** `DeviceClient` and `Simulator` receive a
  `Transport` through their constructors and never import a concrete one. A
  serial port, an in-memory pipe or a test double are interchangeable.
- **Value objects are immutable.** Frames, samples, payloads and messages are
  frozen dataclasses that validate their fields when created.
- **One source for the protocol numbers.** `protocol/_defs.py` is generated
  from [`protocol/definition.toml`](../protocol/definition.toml) at the root
  of the repository. Do not edit it; change the definition and run
  `python protocol/generate.py`.
- **One place for the provisional layouts.** The arguments of the commands
  and the data of the responses and events are not frozen yet. They are
  defined only in `protocol/commands.py`, which the client and the simulator
  share.
- **Typed errors.** Everything the package raises derives from
  `ProfilerError`. A wrong argument from the caller raises `ValueError`.

## Setup

Python 3.10 or later is required. From this directory:

```sh
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Windows
.venv/bin/python -m pip install -e ".[dev]"       # Linux and macOS
```

Activate the environment, or call its `python` directly, for the commands
below.

## Try It Without Hardware

The `simulate` command runs the client against the simulated instrument and
prints the statistics of the capture:

```sh
s3pp --version
s3pp simulate --blocks 100
s3pp simulate --blocks 100 --drop-every 10
s3pp simulate --blocks 20 --range 3
```

| Option | Meaning | Default |
| --- | --- | --- |
| `--blocks` | Stream frames to read, 256 samples each | 100 |
| `--drop-every N` | The instrument drops one block after every N frames, to show the gap detection | 0, never |
| `--range` | Lock one range, 0 to 3, instead of automatic ranging | Automatic |

`python -m s3_power_profiler` is the same command. It exits with 0, or with
1 if the stream stopped before all blocks were read. The currents in its
last line come from the nominal table and a synthetic waveform: they show
that the stack works, and are not readings of anything.

The same from Python:

```python
from s3_power_profiler.capture import StatisticsAccumulator, StreamReader, nominal_table
from s3_power_profiler.device import DeviceClient
from s3_power_profiler.sim import connect_simulator

transport, simulator = connect_simulator()
reader = StreamReader(start_index=0)
statistics = StatisticsAccumulator(nominal_table())

with DeviceClient(transport) as client:
    print(client.get_info())
    client.set_dut_power(True)
    client.start()
    for _ in range(10):
        payload = client.read_stream()
        if payload is None:
            break
        statistics.add(reader.push(payload).words)
    client.stop()

print(reader.gaps)
print(statistics.result())
```

For a real instrument, replace the first line of the session with
`transport = SerialTransport.open("COM5")`, using the port name of the
instrument (`SerialTransport` is in `s3_power_profiler.transport`), and
leave the simulator out. That path is tested only with the loopback port of
pyserial: no instrument and no firmware with command handlers exists to
answer it.

## Checks

Run these from this directory:

| Check | Command |
| --- | --- |
| Tests | `python -m pytest` |
| Tests with coverage | `python -m pytest --cov` |
| Type check, strict | `python -m mypy` |

Run these from the root of the repository, where the shared `ruff.toml` is:

| Check | Command |
| --- | --- |
| Lint | `python -m ruff check host` |
| Formatting | `python -m ruff format --check host` |

ruff and mypy are pinned in the `dev` extra of `pyproject.toml`, because
their findings change between releases. mypy runs in strict mode over `src`
and `tests`.

The Host workflow runs the tests on Windows, Linux and macOS with the
oldest and the newest supported Python (3.10 and 3.14), and on Linux with
the versions in between. Lint, formatting and the type check run once, on
Linux, and one more job builds the wheel, installs it in a clean
environment and runs `s3pp simulate`. The workflow starts by hand only
(D-22), so run the checks locally before a pull request. A local run covers
one system and one Python version.

How the tests are organized:

- One test module per source module, in `tests/`. The generated
  `protocol/_defs.py` and the `Transport` interface have none of their own,
  and `__main__.py` is run by the tests of the command.
- The CRC, the frames and the sample word are checked against
  [`protocol/vectors.json`](../protocol/vectors.json), the vectors shared
  with the firmware tests. The codec has to reproduce them byte for byte in
  both directions.
- Property tests cover the round trips, decoding with arbitrary chunk
  boundaries and resynchronization after noise and after a corrupted frame.
  They run with a fixed set of examples, so a run is repeatable.
- The client is tested end to end against the simulator, error paths
  included.
- Coverage is measured with branches. The run fails below 90 %; the
  configuration is in `pyproject.toml`. The floor is not a target: a change
  does not lower the coverage of the code it touches (section 18.3).
- No test needs an instrument. When such tests exist, they are kept apart
  from the ones that run anywhere (section 18.2).

## Layout

```text
host/
├── pyproject.toml           Package metadata and tool configuration
├── src/s3_power_profiler/
│   ├── protocol/            crc, frame, sample, stream, commands, _defs
│   ├── transport/           base (interface), memory, serial
│   ├── device/              client
│   ├── capture/             reader, calibration, statistics
│   ├── sim/                 simulator, loopback
│   ├── cli.py               The s3pp command
│   ├── __main__.py          python -m s3_power_profiler
│   └── errors.py            Every exception of the package
└── tests/                   One module per source module
```
