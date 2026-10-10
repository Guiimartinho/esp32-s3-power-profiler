# Host Software

Python package that talks to the instrument: the wire protocol, the
transports, a device client, capture helpers and a simulated instrument for
working without hardware.

The package knows the instrument only through the wire protocol, so the
change of controller from the ESP32-S3 to the Raspberry Pi Pico 2 did not
touch it. Its names, `s3-power-profiler` and the `s3pp` command, date from
the first controller and are kept for now.

## Status

The layers described below exist and are tested against the simulated
instrument. Nothing has run against real hardware, because the hardware does
not exist yet. The desktop viewer, the export formats, the burst analysis
and the marks that follow from the hardware, all in section 9 of the
[specification](../docs/specification.md), are not written.

The numbers the simulator and the nominal calibration produce are design
targets, not measurements. The nominal table is computed with a gain of 20
and shunts of 1 kΩ, 33 Ω, 1 Ω and 0.1 Ω. It does not follow the nominal
values of section 8 of the specification yet: a gain of 19.93, and 31.95 Ω
and 0.999 Ω for ranges 1 and 2, where range 0 stays in parallel with the
active shunt (calculated).

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
| `cli` | The `s3pp` command | All of the above |

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
instrument. That path is tested only with the loopback port of pyserial.

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

How the tests are organized:

- One test module per source module, in `tests/`.
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
  configuration is in `pyproject.toml`.

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
│   └── errors.py            Every exception of the package
└── tests/                   One module per source module
```
