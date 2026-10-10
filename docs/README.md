# Documentation

| Document | Content |
| --- | --- |
| [specification.md](specification.md) | System specification: requirements, architecture, host protocol, calibration, verification plan, development phases, risk register and decision log |
| [checks/](checks/) | Component checks: the candidate parts against their datasheets; every check is open and no record is filed yet |
| [reports/](reports/) | Test reports that close each development phase; none is filed yet |
| [protocol/](protocol/) | Host protocol: where it is defined; user reference planned |
| [calibration/](calibration/) | Calibration procedure (planned) |

## How the Documents Relate

- The specification is the baseline. It names requirements `R-xx` and
  decisions `D-xx`; other documents refer to them by ID.
- Section 16 of the specification lists the open checks. Each one is closed
  by a record in `checks/`.
- Section 13 lists the development phases. Each one is closed by a report in
  `reports/`.
- A change that deviates from the specification adds a row to its decision
  log (section 15).

## Conventions

- American English.
- Prose wraps at 80 columns; tables and code blocks are exempt.
- SI units, with a space between the number and the unit: `100 mV`.
- Estimates, calculations, simulations, datasheet values and measurements
  are labeled as such.
- Check the Markdown from the repository root before committing:

  ```sh
  npx --yes markdownlint-cli2@0.23.3
  ```
