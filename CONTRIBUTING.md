# Contributing

Thank you for your interest in the project. This guide describes how changes
are proposed, written and merged.

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
  [`docs/reports/`](docs/reports/). Estimates are labeled as estimates.
- **Tests come with the change.** New logic arrives with its tests, and a fix
  arrives with the test that would have caught the defect. Continuous
  integration passes before a merge.
- **One logical change per commit and per pull request.**

## Repository Layout

The repository holds every part of the instrument. The area a change belongs
to is also the scope of its commit message.

| Path | Content | Commit scope |
| --- | --- | --- |
| `firmware/` | Firmware of the controller | `firmware` |
| `hardware/` | KiCad project of the carrier board, simulations, fabrication outputs | `hardware` |
| `host/` | Python package: protocol, capture tool, viewer | `host` |
| `protocol/` | Protocol definition, generator and shared test vectors | `protocol` |
| `tools/` | Calibration and production-test scripts | `tools` |
| `docs/specification.md` | System specification | `spec` |
| Anything else | Repository-wide files and other documentation | none |

## Workflow

1. Open an issue for anything larger than a small fix, so the approach can be
   discussed before work starts.
2. Create a branch from `main` named `<type>/<short-description>`, for
   example `feat/pio-capture` or `docs/protocol-reference`.
3. Make the change in small commits that follow the format below.
4. Update [`CHANGELOG.md`](CHANGELOG.md) when the change is notable.
5. Open a pull request and fill in the template. The pull request title uses
   the same format as a commit message.

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
  the calibration format are breaking.

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
the area in bold, for example `**firmware:**`. Write for a reader who uses
the instrument, not for one who reads the code.

## Quality Gates

Section 18 of the specification defines the engineering rules. Each area
documents the commands that run its checks locally: run the ones your change
touches before you commit, and state the results in the pull request.

The same checks exist as continuous integration workflows, one per area.
For now they are started by hand, to save processing time (decision D-22):
from the Actions tab, or with `gh workflow run <file> --ref <branch>`. A
pull request is merged only with its checks passing, whichever way they
were run.

| Area | Checks | Commands |
| --- | --- | --- |
| Firmware | Target build, unit tests on the PC, coverage floors, clang-format, clang-tidy, cppcheck | [`firmware/README.md`](firmware/README.md) |
| Host software | Tests on Windows, Linux and macOS, coverage floor, ruff, mypy | [`host/README.md`](host/README.md) |
| Protocol | Generated files up to date | [`protocol/README.md`](protocol/README.md) |
| Hardware | Electrical rules check of the schematic; board checked against the schematic | [`hardware/README.md`](hardware/README.md) |
| Documentation | markdownlint | [Documentation](#documentation) |

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
  stay at `0.y.z` until the first complete instrument is released.
- Hardware revisions are named with letters: revision A, revision B.
- The host protocol has its own integer version, reported by the device.

## Documentation

Markdown files are checked with
[markdownlint](https://github.com/DavidAnson/markdownlint). Prose wraps at
80 columns; tables and code blocks are exempt. Run the check from the
repository root before opening a pull request:

```sh
npx --yes markdownlint-cli2@0.23.3
```

## Licensing of Contributions

By contributing, you agree that your contribution is licensed under the
license of the area it changes: CERN-OHL-P v2 for files under `hardware/` and
MIT for everything else.
