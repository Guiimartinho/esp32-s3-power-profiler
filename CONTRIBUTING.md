# Contributing

Thank you for your interest in the project. This guide describes how changes
are proposed, written and merged.

## Where the Project Stands

The project is in early development, and a contribution has to fit that
state:

- The controller is a Raspberry Pi Pico 2 (RP2350) on a carrier board
  designed here. The carrier exists as draft A2: a complete schematic and
  an autorouted board that needs a layout review before fabrication.
- Nothing has been built and nothing has been measured. Every figure in
  the repository is a datasheet value, a calculation, a simulation or an
  estimate. The parts are candidates until their checks are closed.
- The protocol definition, the hardware-independent core of the firmware
  and the host package exist and are tested without hardware. The firmware
  is not ported to the Pico SDK yet: the target build in `firmware/` is
  still the one of the first plan, for the ESP32-S3.
- `tools/` holds a guide and no script. `hardware/simulation/` and
  `hardware/fabrication/` are empty, so the figures that the specification
  marks "simulated" have no file in the repository behind them yet.

The [documentation index](docs/README.md) lists every document with its
state and the work that comes next.

## Ground Rules

- **English everywhere.** Code, comments, documentation, commit messages,
  issues and pull requests are written in English.
- **The specification is the baseline.** The
  [system specification](docs/specification.md) defines the architecture and
  the plan. A change that deviates from it updates the specification and adds
  an entry to its decision log in the same pull request.
- **Numbers need a source.** A figure taken from a datasheet cites the
  document, revision and page in a record under
  [`docs/checks/`](docs/checks/). A measured figure cites its report under
  [`docs/reports/`](docs/reports/). Estimates, calculations and simulations
  are labeled as such. No record and no report is filed yet, so nothing in
  the repository is called verified, and a change does not introduce that
  word for a design that was not built.
- **Tests come with the change.** New logic arrives with its tests, and a fix
  arrives with the test that would have caught the defect. The checks of
  every area a change touches pass before a merge. They are run locally;
  the continuous integration workflows run the same checks when they are
  started by hand (see [Quality Gates](#quality-gates)).
- **One logical change per commit and per pull request.**

## Repository Layout

The repository holds every part of the instrument. The area a change belongs
to is also the scope of its commit message and the label of its changelog
entry.

| Path | Content | Commit scope | Changelog area |
| --- | --- | --- | --- |
| `firmware/` | Firmware of the controller: hardware-independent core with its unit tests; the target build is not ported to the Pico 2 yet | `firmware` | `firmware` |
| `hardware/` | KiCad project of the carrier board (draft A2) and its pictures; the folders for simulations and fabrication outputs are empty | `hardware` | `hardware` |
| `host/` | Python package: protocol, transports, device client, capture helpers, simulator | `host` | `host` |
| `protocol/` | Protocol definition, generator and shared test vectors | `protocol` | `protocol` |
| `tools/` | Calibration and production-test scripts; not started | `tools` | `tools` |
| `docs/specification.md` | System specification | `spec` | `docs` |
| Other documentation: `docs/`, the README files | Guides, component checks, test reports | none | `docs` |
| Anything else | Repository-wide files: this guide, workflows, issue and pull request templates, lint and editor configuration, licenses | none | `repo` |

## Workflow

1. Open an issue for anything larger than a small fix, so the approach can be
   discussed before work starts.
2. Create a branch from `main` named `<type>/<short-description>`, for
   example `feat/pio-capture` or `docs/protocol-reference`.
3. Make the change in small commits that follow the format below.
4. Run the checks of every area the change touches, as listed under
   [Quality Gates](#quality-gates).
5. Update [`CHANGELOG.md`](CHANGELOG.md) when the change is notable.
6. Open a pull request and fill in the template. The pull request title uses
   the same format as a commit message. State the results of the checks you
   ran; no workflow starts by itself on a pull request.

Some changes touch more than one place, and all of them belong to the same
pull request:

- A change to the protocol starts in `protocol/definition.toml` and carries
  the generated files of the firmware and of the host, the test vectors and
  section 7 of the specification. See the
  [protocol guide](protocol/README.md).
- A change to the schematic or to the board carries the pictures and the
  PDF in `hardware/doc/`, plotted again, and the figures of the
  [hardware guide](hardware/README.md).
- A part that replaces a candidate, or a value that changes, carries the
  sections of the specification that name it: design section, pin map, bill
  of materials, verification plan and open checks.
- A check record or a phase report carries the update of its index
  ([`docs/checks/README.md`](docs/checks/README.md) or
  [`docs/reports/README.md`](docs/reports/README.md)) and of the
  specification.

## Commit Messages

Commit messages follow
[Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):

```text
<type>(<scope>): <subject>

<body>

<footer>
```

### Type

| Type | Use for |
| --- | --- |
| `feat` | A new capability |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `refactor` | A code change that neither fixes a bug nor adds a capability |
| `perf` | A change that improves performance |
| `test` | Adding or correcting tests |
| `build` | Build system, toolchain or dependency changes |
| `ci` | Continuous integration workflows |
| `chore` | Maintenance that does not change sources or documentation content |
| `revert` | Reverting an earlier commit |

### Scope

The scope is the area from the table in
[Repository Layout](#repository-layout): `firmware`, `hardware`, `host`,
`protocol`, `tools` or `spec`. Release commits use `release`. Leave the
scope out for repository-wide changes.

### Subject, Body and Footer

- Write the subject in the imperative mood: "add", not "added" or "adds".
- Start the subject with a lowercase letter, unless the first word is a
  proper noun or an acronym, and do not end it with a period.
- Keep the first line at 72 characters or fewer.
- Use the body to explain what changed and why. Wrap it at 72 characters.
- Reference issues in the footer: `Refs: #12` or `Closes #12`.
- Mark a breaking change with `!` after the type or scope and explain it in
  a `BREAKING CHANGE:` footer. Changes to the host protocol, the pin map or
  the calibration format are breaking: each one makes a firmware, a host
  program, a carrier board or a stored calibration record that was right
  before the change wrong after it. A change to the protocol that an older
  firmware or host cannot understand also raises the protocol version in
  `protocol/definition.toml`.

### Examples

```text
feat(firmware): add PIO capture at 100 kSPS
fix(host): resync after a corrupted frame
docs(spec): record decision D-14
perf(firmware): assemble sample words in place
chore: add editor and lint configuration
```

```text
feat(firmware)!: add sample index to the stream frame

The host could not tell how many samples were lost when a block was
dropped. The stream payload now starts with the index of its first
sample.

BREAKING CHANGE: the stream payload layout changes; protocol version 2.
Closes #31
```

## Changelog

[`CHANGELOG.md`](CHANGELOG.md) follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Add notable changes
under `Unreleased`, in the matching section (`Added`, `Changed`,
`Deprecated`, `Removed`, `Fixed` or `Security`), and start each entry with
the area in bold, for example `**firmware:**`. The areas are `firmware`,
`hardware`, `host`, `protocol`, `tools`, `docs` and `repo`; the table in
[Repository Layout](#repository-layout) says which one a path belongs to.
An entry for a breaking change puts `**BREAKING**` after the area. Write
for a reader who uses the instrument, not for one who reads the code, and
give the evidence level of a figure there too: an entry does not turn a
calculated value into a measured one.

## Quality Gates

Section 18 of the specification defines the engineering rules. Each area
documents the commands that run its checks locally: run the ones your change
touches before you commit, and state the results in the pull request.

The same checks exist as continuous integration workflows, one per area.
No workflow starts on a push or on a pull request: by decision D-22 of the
specification they are started by hand, to save processing time while the
project is in early development. Start one from the Actions tab, or with
`gh workflow run <file> --ref <branch>`. A pull request is merged only with
the checks of its areas passing, and its description says how they were
run: locally, by a workflow, or both. Section 18.3 of the specification
provides for a run of the workflows on the head of a pull request before it
is merged and on the release commit; the maintainer starts those runs, and
a contributor is not expected to.

| Area | Workflow | Checks | Commands |
| --- | --- | --- | --- |
| Firmware | `Firmware` (`firmware.yml`) | Unit tests on the PC, coverage floors of 90 % of lines and 80 % of branches, the tests under the address, undefined-behavior and thread sanitizers, clang-format, clang-tidy, cppcheck, and the target build | [`firmware/README.md`](firmware/README.md) |
| Host software | `Host` (`host.yml`) | Tests on Windows, Linux and macOS on the oldest and the newest supported Python, coverage floor of 90 % of lines and branches, ruff, mypy in strict mode, and the package built and installed | [`host/README.md`](host/README.md) |
| Protocol | `Protocol` (`protocol.yml`) | Generated files up to date; ruff and mypy on the generator | [`protocol/README.md`](protocol/README.md) |
| Hardware | `Hardware` (`hardware.yml`) | Electrical rules check of the schematic with no error; design rules check of the board with schematic parity, whose report shows no rule violation and no difference between board and schematic | [`hardware/README.md`](hardware/README.md) |
| Documentation | `Docs` (`docs.yml`) | markdownlint | [Documentation](#documentation) |

What these checks are today, and what they are not:

- The target build of the firmware is still the ESP-IDF build for the
  ESP32-S3. It becomes the build for the Pico 2 when the firmware is ported
  to the Pico SDK; the unit tests do not depend on the controller.
- The sanitizer runs need a toolchain with the sanitizer runtimes, which
  MinGW on Windows does not have, and the host tests on three operating
  systems need three machines. Where a check cannot run locally, say so in
  the pull request and start the workflow for it.
- The board of draft A2 is an autorouted draft with 28 connections open.
  The design rules check therefore reports unconnected items, and its exit
  code is not used: the report itself must show no rule violation and no
  footprint error. Before a board is ordered it must also show no
  unconnected item (section 10.8 of the specification).
- A passing hardware check says that the drawings are consistent. It is not
  a layout review, and it closes no component check.

The rules that hold for every area:

- Coverage floors are minimums. A change does not lower the coverage of the
  code it touches.
- A check is never silenced to make a pull request pass. A suppression needs
  a comment that says why the finding does not apply.
- The gates cover logic. Timing, throughput and analog behavior are verified
  on the bench and recorded in a report under
  [`docs/reports/`](docs/reports/).

## Versioning

- The repository uses one [semantic version](https://semver.org/) for
  firmware, host software and tools, tagged as `vMAJOR.MINOR.PATCH`. Versions
  stay at `0.y.z` until the first complete instrument is released. No
  version is tagged yet: every change is under `Unreleased` in the
  changelog.
- Hardware revisions are named with letters: revision A, revision B. A
  revision is a board that is fabricated. What is drawn before that is a
  draft with a number, and the carrier board is at draft A2: a review draft
  on the way to revision A, not a design to fabricate.
- The host protocol has its own integer version, reported by the device.
  It is 1, and the protocol is not frozen: the freeze is part of phase 6.

## Documentation

Markdown files are checked with
[markdownlint](https://github.com/DavidAnson/markdownlint). Prose wraps at
80 columns; tables and code blocks are exempt. Run the check from the
repository root before opening a pull request:

```sh
npx --yes markdownlint-cli2@0.23.3
```

What a document of this repository has to do, beyond passing the lint:

- Say what exists today and what does not. A guide states the state of its
  area ("not started", "not written", "open") and what comes next in it,
  and it is updated in the pull request that changes that state.
- Give the evidence level of every figure: estimate, calculation,
  simulation, datasheet value or measurement. Nothing of this design is
  measured yet.
- Refer to requirements, decisions and firmware rules of the specification
  by ID (`R-08`, `D-55`, `F-16`). Sections and IDs of the specification are
  never renumbered, because other files point to them.
- Use SI units with a space between the number and the unit (`100 mV`,
  `4.7 µF`, `10 kΩ`), and write "datasheet" as one word.
- Keep relative links and picture paths pointing at files that exist.

The [documentation index](docs/README.md) lists every document and how the
documents relate.

## Licensing of Contributions

By contributing, you agree that your contribution is licensed under the
license of the area it changes: CERN-OHL-P v2 for files under `hardware/` and
MIT for everything else.
