# Firmware

Firmware of the controller of the instrument, a Raspberry Pi Pico 2
(RP2350). It acquires the samples, controls the analog front end and streams
the data to the host over USB.

## Status

| Part | State |
| --- | --- |
| Hardware-independent core | Done for the wire protocol, the block queue between the two cores, the ranging rules and the device state machine. Unit-tested on the PC |
| Target build for the Pico 2 | Not started. It will use the Pico SDK (C and CMake), the TinyUSB stack the SDK brings, and PIO programs for the sampling clock and the range sequencer |
| Adapters for acquisition, analog front end and USB | Not started. They come with the target build, in phase 1 |
| Target build in this directory today | The ESP-IDF project of the first plan, for the ESP32-S3. It builds, boots into a banner and drives no hardware. The port replaces it |

The controller changed from the ESP32-S3 to the Pico 2 with decision D-39 of
the [specification](../docs/specification.md). The core does not depend on
the controller, so it and its tests carry over as they are; sections 5 and 6
of the specification describe the pins and the execution model the port
follows.

Nothing here has run on a board: timing, throughput and loss figures are
still design targets of the specification.

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
| `acq` | Settling window after a range change, step-down rule | `base`, `proto` | Core done; PIO capture adapter to come |
| `afe` | Port to the analog front end | `base`, `proto` | Port declared; range sequencer and GPIO adapter to come |
| `app` | Device state machine | `base`, `proto` | State machine done; command handling to come |
| `smu`, `monitor`, `cal`, `usb_link` | As in section 6.1 of the specification | | Not started |
| `main` | Composition root | All of the above | Banner and state machine |

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
- **Table-driven state machine with an observer** (`pp_fsm`). The whole
  behavior of section 6.4 is one table that can be compared with the
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
│   └── host/
│       ├── CMakeLists.txt    Host test project
│       ├── CMakePresets.json Presets: debug, coverage, sanitize, tsan
│       ├── generated/        Protocol test vectors (generated)
│       ├── support/          Test doubles
│       └── tests/            One test file per module
├── gcovr.cfg             Coverage filters and thresholds
├── .clang-format         Code format
├── .clang-tidy           Static analysis checks
└── .clangd               Editor support: points clangd at the host test build
```

## Building the Firmware

### For the Pico 2

There is no target build for the Pico 2 yet. The port adds a Pico SDK
project to this directory: one CMake project that builds the components
from their `sources.cmake`, the adapters in `port/` and the PIO programs,
and produces a `.uf2` image. That image is copied to the USB drive the
Pico 2 shows when it starts with its BOOTSEL button held; no programmer is
needed. This section gets its commands when that project exists.

### ESP-IDF Build of the First Plan

Kept until the port replaces it. It shows only that the core compiles for a
target. It needs [ESP-IDF](https://github.com/espressif/esp-idf) v6.0. Load
the ESP-IDF environment in the shell first, then run these from the root of
the repository:

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
