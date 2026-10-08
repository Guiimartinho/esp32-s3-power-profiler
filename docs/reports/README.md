# Test Reports

A report records the measurements that close a development phase. The phases
and their exit criteria are in section 13 of the
[specification](../specification.md).

## Rules

- A criterion passes only with evidence from a run that took place: the
  numbers, the setup that produced them and the location of the raw data.
- A criterion that was not run is marked "Not run", never "Pass".
- Record the firmware and host software commits, the board revision and the
  instruments with their settings, so the run can be repeated.
- Small data files live next to the report in `data/phase-<n>/`. Large
  captures stay out of the repository; link to where they are stored.

## Writing a Report

1. Copy [`TEMPLATE.md`](TEMPLATE.md) to `phase-<n>-<short-title>.md`, for
   example `phase-1-risk-prototypes.md`.
2. Quote the exit criteria of the phase from the specification.
3. Fill in one measurement section per criterion.
4. List the decisions taken and the sections of the specification that
   changed.
5. Update the roadmap table in the repository [README](../../README.md).
