# Firmware

Firmware of the controller of the instrument. It acquires the samples,
controls the analog front end and streams the data to the host over USB.

> [!IMPORTANT]
> The controller changed from the ESP32-S3 to the Raspberry Pi Pico 2
> (decision D-39 of the specification). This directory is not ported yet:
> it is still the ESP-IDF project of the first plan, and everything below
> describes it. The hardware-independent core and its unit tests do not
> depend on the controller and carry over as they are; the build, `main`
> and the adapters move to the Pico SDK in phase 1.

## Status

The hardware-independent core exists and is tested on the host: the wire
protocol, the block queue between the two cores, the ranging rules and the
device state machine. The ESP-IDF project builds for the `esp32s3` target and
boots into a banner; it drives no hardware yet.

The adapters for the acquisition, the analog front end and USB are added in
the development phases that bring up the hardware. Nothing here has run on a
board: timing, throughput and loss figures are still design targets of the
[specification](../docs/specification.md).

## Architecture

The firmware follows the ports and adapters pattern. The logic of the
instrument is plain C11 that knows nothing about ESP-IDF or the board. It
reaches the hardware only through small interfaces, the ports. Adapters
implement the ports with ESP-IDF drivers, and `main` wires the two together.

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
component below `main` includes an ESP-IDF header in its hardware-independent
part.

| Component | Hardware-independent part | Depends on | State |
| --- | --- | --- | --- |
| `base` | Status codes, little-endian access, block queue | Nothing | Done |
| `proto` | CRC-16, frame encoder and parser, sample word, stream payload, command, response and event envelopes | `base` | Done |
| `acq` | Settling window after a range change, step-down rule | `base`, `proto` | Core done; I2S capture adapter to come |
| `afe` | Port to the analog front end | `base`, `proto` | Port declared; GPIO adapter to come |
| `app` | Device state machine | `base`, `proto` | State machine done; command handling to come |
| `smu`, `monitor`, `cal`, `usb_link` | As in section 6.1 of the specification | | Not started |
| `main` | Composition root | All of the above | Banner and state machine |

`base` holds what every other component shares, so that none of them has to
depend on a sibling for a status code or for the queue. The components are
the ones of section 6.1 of the specification.

### Rules for the Hardware-Independent Code

- C11, compiled with warnings as errors.
- No ESP-IDF header, no dynamic allocation, no global variable. Every
  function works on a context structure and on buffers the caller supplies.
- Every number of the wire protocol comes from `proto/pp_proto_defs.h`, which
  is generated from [`protocol/definition.toml`](../protocol/definition.toml).
  Do not edit the header; change the definition and run
  `python protocol/generate.py`.
- Public names start with `pp_`.
- Each module has a unit test, and the coverage gate below applies to it.

### Patterns and Why They Are Used

- **Ports and adapters.** The core is tested on a PC in milliseconds, without
  a board, and before the board exists. `afe/pp_afe_port.h` is the first
  port; `test/host/support/fake_afe.c` is its test double.
- **Lock-free single-producer, single-consumer queue** (`pp_blockq`). The
  acquisition task must never wait for the USB task. Each index has one
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
- **One manifest per component** (`sources.cmake`). The ESP-IDF build and the
  host test build read the same list of sources and dependencies, so they
  cannot drift apart.

## Layout

```text
firmware/
├── CMakeLists.txt        ESP-IDF project file
├── sdkconfig.defaults    Project configuration defaults, each with its reason
├── cmake/                Warning flags shared by both builds
├── main/                 Composition root (app_main)
├── components/
│   └── <name>/
│       ├── CMakeLists.txt    ESP-IDF component, built from sources.cmake
│       ├── sources.cmake     Sources and dependencies of the component
│       ├── include/<name>/   Public headers
│       ├── src/              Hardware-independent sources
│       └── port/             ESP-IDF adapters (none yet)
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

The project is developed against
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
later, Ninja and gcc.

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
- `main/app_main.c` needs the ESP-IDF headers, so clang-tidy does not analyze
  it; the ESP-IDF build compiles it with warnings as errors.

## Adding Code

- **A hardware-independent module:** put the header in
  `components/<name>/include/<name>/`, the source in `src/`, add the source
  to `sources.cmake`, write `test/host/tests/test_<module>.c` and register it
  with `pp_add_test` in `test/host/CMakeLists.txt`.
- **An adapter:** put it in `components/<name>/port/` and list it in the
  `CMakeLists.txt` of the component only, never in `sources.cmake`. It
  implements a port declared in a public header and is created in `main`.
- **A protocol constant:** change `protocol/definition.toml` at the root of
  the repository and regenerate. The compiler then points at the code that
  has to follow, for instance the list of known commands.
