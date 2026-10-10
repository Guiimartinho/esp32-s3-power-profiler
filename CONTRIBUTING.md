# Contributing

Thank you for your interest in the project. This guide describes how changes
are proposed, written and merged.

## Where the Project Stands

The project is in early development, and a contribution has to fit that
state:

- The controller is a Raspberry Pi Pico 2 (RP2350) on a carrier board
  designed here. The carrier exists as draft A2: a complete schematic and
  a board with every connection routed, whose layout was reviewed against
  section 10 of the specification. That review was done with scripts and
  checked by independent calculation. The board has not yet been looked at
  by a person in the KiCad editor. The seven points in which it deviates
  from the earlier guidelines of section 10 are recorded as decisions D-87
  to D-93 of the specification; the [hardware guide](hardware/README.md)
  lists them with the open items of the layout. It is not a design to
  fabricate.
- Nothing has been built and nothing has been measured. Every figure in
  the repository is a datasheet value, a calculation, a simulation or an
  estimate. The figures of the board are calculated from the drawn copper.
  The parts are candidates until their checks are closed, and no check is
  closed.
- The protocol definition, the hardware-independent core of the firmware
  and the host package exist and are tested without hardware. The firmware
  is not ported to the Pico SDK yet: the target build in `firmware/` is
  still the one of the first plan, for the ESP32-S3.
- `tools/` holds one tool: the package in `tools/board/`, which calculates
  the figures of the board layout from the board file and is tested
  without hardware. The calibration tool and the production test are not
  started.
- `simulation/` holds the circuit simulations of the carrier board: a
  package that takes the parts of every circuit of the board from a
  snapshot of the netlist of the schematic and runs it in the ngspice
  library of KiCad 10, the models written for the project, 134 benches
  and their results. The central design figures of the specification come
  out again. The four points that the simulations raised are decided
  (D-95 to D-98 of the specification). Three of them change the schematic
  and are not drawn yet: the schematic, the board, the bill of materials,
  the netlist snapshot and the results still hold the state before them.
  In fourteen places the simulations differ from the text of the
  specification, which is unchanged until the owner decides. The
  [simulation guide](simulation/README.md) lists them. A simulated figure
  is not a measured one.
- `hardware/fabrication/` is empty. The scripts that drew the copper of
  the board are not in the repository, and neither are the model files of
  the manufacturers, whose licenses do not allow a copy.

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
  are labeled as such, and a simulated figure names the bench under
  [`simulation/results/`](simulation/results/README.md) that gives it. No
  record and no report is filed yet, so nothing in the repository is
  called verified, and a change does not introduce that word for a design
  that was not built. A simulation that passes is not a verification.
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
| `hardware/` | KiCad project of the carrier board (draft A2) and its pictures; the folder for fabrication outputs is empty | `hardware` | `hardware` |
| `simulation/` | Circuit simulations of the carrier board: the package `circuit-sim`, the snapshot of the netlist, the models, the benches and their results | `simulation` | `simulation` |
| `host/` | Python package: protocol, transports, device client, capture helpers, simulator | `host` | `host` |
| `protocol/` | Protocol definition, generator and shared test vectors | `protocol` | `protocol` |
| `tools/` | The board figures in `tools/board/`: a Python package that calculates the layout figures of the carrier board from its board file. The calibration and production-test scripts are not started | `tools` | `tools` |
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
  [hardware guide](hardware/README.md). The figures of the layout are
  calculated again from the changed board file with the package in
  `tools/board/`; the [board figures guide](tools/board/README.md) says
  how.
- A change to the schematic also carries the snapshot of its netlist in
  `simulation/netlist/`, written again, and a new run of the benches of
  the blocks that it touches, with their result files and pages. The
  [simulation guide](simulation/README.md#when-the-schematic-changes) has
  the steps. No check compares the snapshot with the schematic by itself.
- A change to a model or to a bench carries the result files, the graphs,
  the decks and the pages that it changes, and the documents that quote a
  changed figure. The pages are written by `circuit-sim report`, never by
  hand.
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
`protocol`, `tools`, `simulation` or `spec`. The scope `simulation` covers
everything under `simulation/`: the package, the models, the benches and
the results. Release commits use `release`. Leave the scope out for
repository-wide changes.

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
feat(simulation): add a bench for the guard buffer
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
`hardware`, `host`, `protocol`, `tools`, `simulation`, `docs` and `repo`;
the table in
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
| Hardware | `Hardware` (`hardware.yml`) | Electrical rules check of the schematic with no error; design rules check of the board with schematic parity, whose report shows no rule violation, no unconnected pad and no difference between board and schematic | [`hardware/README.md`](hardware/README.md) |
| Tools | `Tools` (`tools.yml`) | For the package in `tools/board/`: tests on Windows, Linux and macOS on the oldest and the newest supported Python, coverage floor of 90 % of lines and branches, ruff, mypy in strict mode, and the package built and installed | [`tools/board/README.md`](tools/board/README.md) |
| Simulation | `Simulation` (`simulation.yml`) | For the package in `simulation/`: ruff, and mypy in strict mode over the package, its tests and the benches; tests on Windows, Linux and macOS on the oldest and the newest supported Python, coverage floor of 90 % of lines and branches; the tests that run a circuit, with the ngspice library of a Linux distribution; the package built and installed. It does not run the benches | [`simulation/README.md`](simulation/README.md) |
| Documentation | `Docs` (`docs.yml`) | markdownlint | [Documentation](#documentation) |

The checks of the tools area, as an example of the commands of an area. In
`tools/board/`, with the environment that its guide sets up:

```sh
.venv/Scripts/python -m pytest --cov
.venv/Scripts/python -m mypy
```

From the repository root:

```sh
tools/board/.venv/Scripts/python -m ruff check tools/board
tools/board/.venv/Scripts/python -m ruff format --check tools/board
```

On Linux and macOS the interpreter is `.venv/bin/python`.

The checks of the simulation area. In `simulation/`, with the environment
that its guide sets up:

```sh
.venv/Scripts/python -m pytest --cov
.venv/Scripts/python -m mypy
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

The tests that run a circuit need the ngspice shared library, which
KiCad 10 ships. The variable `NGSPICE_LIBRARY` names it; without the
library those tests are skipped and the others run.

What these checks are today, and what they are not:

- The target build of the firmware is still the ESP-IDF build for the
  ESP32-S3. It becomes the build for the Pico 2 when the firmware is ported
  to the Pico SDK; the unit tests do not depend on the controller.
- The sanitizer runs need a toolchain with the sanitizer runtimes, which
  MinGW on Windows does not have, and the host tests on three operating
  systems need three machines. Where a check cannot run locally, say so in
  the pull request and start the workflow for it.
- The Tools workflow has not been started yet. The checks of the package
  in `tools/board/` ran locally, on Windows with Python 3.11: 260 tests,
  100 % of lines and branches covered. The adapter that dumps the board
  runs under the Python of KiCad and has no automated test.
- The Simulation workflow has not been started yet either. The checks of
  the package in `simulation/` ran locally, on Windows with Python 3.11
  and the ngspice 45.2 library of KiCad 10: 777 tests, of which 11 need
  the library, 100 % of lines and branches covered, no issue from mypy in
  172 source files, no finding from ruff. The module that loads the
  library runs in a child process and is outside the coverage measurement.
  Linux, macOS, other versions of Python and other versions of ngspice
  have not run the package.
- A passing gate of the simulation area says that the package builds the
  circuit it is asked for and measures what it says. It says nothing about
  the figures of the board: 122 of the filed figures fail, and they are
  kept. Do not widen a limit, drop a figure or change a stimulus to turn
  a failing figure into a passing one: say in the notes of the bench what
  the failure is, and bring a difference from the specification to an
  issue. A limit that a bench sets by itself is named as such in the
  column "Source" of its page.
- The filed results come from one machine and from version 45.2 of
  ngspice. A change that runs benches again states the version of the
  library, which the result files record. The model files of the
  manufacturers are not part of the repository, and no text of one is
  copied into a file of it; the values of a run with them may be filed
  beside the others, in a column of their own, and change no verdict.
- The board of draft A2 has all 984 connections routed since the layout
  review of 2026-10-10; the autorouted board before it had 28 open. The
  report of the design rules check shows no rule violation, no unconnected
  pad, no footprint error and no difference between board and schematic,
  against a rule file that the review made stricter. A change to the board
  keeps all four at zero. The Hardware workflow fails when the report shows
  a rule violation, an unconnected pad or a footprint error, which is how
  the report names a difference between board and schematic. State the
  four counts in the pull request.
- What a contributor may rely on: the board file, the rule file and the
  schematic agree with each other, and the pictures in `hardware/doc/` are
  plotted from that board file. The seven points in which the layout
  deviates from the earlier guidelines of section 10 are recorded
  decisions (D-87 to D-93), and sections 10.3, 10.4, 10.6 and 10.8 of the
  specification describe the board as it is drawn: a change may build on
  them, and a change that goes against one of them is a new decision. The
  figures of the layout (squares and milliohms of the pours, leakage into
  the measured node, lengths of the pairs) can be calculated again from
  the board file with the package in `tools/board/`. What not: that the
  layout keeps every rule of section 10, or that a figure is a
  measurement. The board has open items that need a part moved, nobody
  has reviewed it in the KiCad editor yet, and every figure is calculated
  from the drawn copper. The temperature rise of the linear regulator on
  its copper is an open check (D-93). Open an issue before moving parts or
  copper of the front end, the 1 A path or the converters.
- A passing hardware check says that the drawings are consistent. It is not
  a layout review, and it closes no component check.

The rules that hold for every area:

- Coverage floors are minimums. A change does not lower the coverage of the
  code it touches.
- A check is never silenced to make a pull request pass. A suppression needs
  a comment that says why the finding does not apply.
- A script whose result goes into a document is code of the repository:
  it lives under `tools/` or, for the circuit simulations, under
  `simulation/`, with its tests, its type and lint checks and a guide, and
  what is specific to one board or one instrument is data, not code.
  `tools/board/` is the example: its calculations are pure functions
  tested on small synthetic boards, and the nets, pads and assumptions of
  the carrier board are in `tools/board/carrier.toml`. In `simulation/`
  the circuit of a bench is not typed: it is written from the snapshot of
  the netlist.
- The gates cover logic. Timing, throughput and analog behavior are verified
  on the bench and recorded in a report under
  [`docs/reports/`](docs/reports/). A simulation is neither a gate nor a
  report: it is filed as a simulation, with the models it used.

## Versioning

- The repository uses one [semantic version](https://semver.org/) for
  firmware, host software and tools, tagged as `vMAJOR.MINOR.PATCH`. Versions
  stay at `0.y.z` until the first complete instrument is released. No
  version is tagged yet: every change is under `Unreleased` in the
  changelog.
- Hardware revisions are named with letters: revision A, revision B. A
  revision is a board that is fabricated. What is drawn before that is a
  draft with a number, and the carrier board is at draft A2: a review draft
  on the way to revision A, not a design to fabricate. The layout review
  of 2026-10-10 did not change the number of the draft.
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
