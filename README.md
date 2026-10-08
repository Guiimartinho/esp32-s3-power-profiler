# ESP32-S3 Power Profiler

[![Docs][badge-docs]][workflow-docs]
[![Status: planning][badge-status]](#roadmap)
[![Software license: MIT][badge-mit]](LICENSE)
[![Hardware license: CERN-OHL-P v2][badge-ohl]](hardware/LICENSE)

Open-source power profiler in the class of the Nordic PPK2, built around the
ESP32-S3. It is designed to sample current at 100 kSPS from 100 nA to 1 A
with automatic range switching, to work either as a source meter that powers
the device under test or as an ampere meter in series with an external
supply, and to stream the samples to a PC over the native USB port.

> [!NOTE]
> The project is in the planning phase. The architecture and the work plan
> are defined in the [system specification](docs/specification.md). No
> hardware has been built and no firmware has been written yet, so every
> figure in this repository is a design target, not a measurement.

## Table of Contents

- [Target Specifications](#target-specifications)
- [How It Works](#how-it-works)
- [Repository Structure](#repository-structure)
- [Roadmap](#roadmap)
- [Getting Started](#getting-started)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Target Specifications

| Item | Target |
| --- | --- |
| Sampling rate | 100 kSPS, timed by hardware |
| Current range | 100 nA to 1 A in four ranges, switched automatically |
| Burden voltage | 100 mV maximum across the shunt |
| Source meter mode | Programmable output from 0.8 V to 5.0 V, up to 1 A |
| Ampere meter mode | External supply from 0.8 V to 5.0 V through the shunts |
| Digital inputs | 8 logic channels sampled together with the current |
| Host link | Native USB (Full-Speed), CDC ACM, binary protocol |
| Controller | ESP32-S3-WROOM-1 module, ESP-IDF firmware |
| Power input | USB-C, 5 V |

The complete list, with requirement IDs, is in section 2 of the
[specification](docs/specification.md).

## How It Works

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

- **Four shunt ranges.** Each range is limited to 100 mV of burden voltage.
  Comparators switch to a higher range in hardware within microseconds, so a
  current step does not brown out the device under test. The firmware decides
  when to step back down.
- **Hardware-timed sampling.** A 16-bit SAR ADC is clocked by the I2S
  peripheral of the ESP32-S3, so the sampling instant does not depend on
  firmware latency.
- **Self-describing samples.** Every sample is a 32-bit word that carries the
  ADC code, the active range, a validity flag, the fault flag and the eight
  logic inputs.
- **Two cores, two jobs.** Core 0 acquires data in DMA blocks. Core 1 frames
  the blocks and streams them over USB.
- **Programmable supply.** In source meter mode a DAC sets a low-noise linear
  regulator, fed by a pre-regulator that tracks the output voltage.

## Repository Structure

| Path | Content | License |
| --- | --- | --- |
| [`firmware/`](firmware/) | ESP-IDF firmware for the ESP32-S3 | MIT |
| [`hardware/`](hardware/) | KiCad project, simulations, fabrication outputs | CERN-OHL-P v2 |
| [`host/`](host/) | Python package: protocol, capture tool, viewer, analysis | MIT |
| [`tools/`](tools/) | Calibration and production-test scripts | MIT |
| [`docs/`](docs/) | Specification, component checks, test reports | MIT |

## Roadmap

The work is split into phases. Each phase is closed by a test report with
recorded measurements. The exit criteria are in section 13 of the
[specification](docs/specification.md).

| Phase | Goal | Status |
| --- | --- | --- |
| 1 | Risk prototypes: hardware-timed ADC capture and USB throughput | Not started |
| 2 | Analog front end with one fixed range | Not started |
| 3 | Shunt ladder and automatic range logic | Not started |
| 4 | Source meter mode and power input | Not started |
| 5 | Integrated board, revision A | Not started |
| 6 | Calibration, protocol freeze and host software | Not started |
| 7 | Revision B and release | Not started |

## Getting Started

Clone the repository and start with the specification:

```sh
git clone https://github.com/Guiimartinho/esp32-s3-power-profiler.git
cd esp32-s3-power-profiler
```

There is nothing to build yet. Build instructions will be added to
[`firmware/`](firmware/), [`hardware/`](hardware/) and [`host/`](host/) as
each part starts.

To check documentation changes before opening a pull request (needs
Node.js):

```sh
npx --yes markdownlint-cli2@0.23.3
```

## Documentation

- [System specification](docs/specification.md): requirements, analog and
  firmware architecture, host protocol, calibration, verification plan,
  risks and decision log.
- [Component checks](docs/checks/): candidate parts verified against their
  datasheets.
- [Test reports](docs/reports/): the measurements that close each phase.
- [Changelog](CHANGELOG.md): notable changes by release.

## Contributing

Contributions are welcome. Read the [contributing guide](CONTRIBUTING.md)
first: it covers the workflow, the commit message format and how changes to
the specification are recorded.

## License

- Hardware design files under [`hardware/`](hardware/):
  [CERN-OHL-P v2](hardware/LICENSE).
- Everything else, including firmware, host software, tools and
  documentation: [MIT](LICENSE).

## Acknowledgments

- Inspired by
  [Gedankenn/power_profiller](https://github.com/Gedankenn/power_profiller),
  an ESP32 and INA226 power profiler with a web dashboard.
- The feature set follows the Nordic Semiconductor Power Profiler Kit II
  (PPK2). This project is independent and is not affiliated with or endorsed
  by Nordic Semiconductor.

[badge-docs]: https://github.com/Guiimartinho/esp32-s3-power-profiler/actions/workflows/docs.yml/badge.svg
[workflow-docs]: https://github.com/Guiimartinho/esp32-s3-power-profiler/actions/workflows/docs.yml
[badge-status]: https://img.shields.io/badge/status-planning-orange
[badge-mit]: https://img.shields.io/badge/software-MIT-blue
[badge-ohl]: https://img.shields.io/badge/hardware-CERN--OHL--P%20v2-blue
