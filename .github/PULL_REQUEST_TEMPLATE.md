## Summary

<!-- What does this change, and why? Link the issue it closes: Closes #123 -->

## Area

- [ ] Firmware
- [ ] Hardware
- [ ] Host software
- [ ] Protocol
- [ ] Tools
- [ ] Documentation or specification
- [ ] Repository (workflows, templates, configuration)

## Verification

<!--
Which checks did you run, and with what result? The workflows do not start
by themselves: name the checks you ran locally and the workflows you started
by hand. Say what could not be run (sanitizers, other operating systems).
For a measurement, attach logs or captures or link the report. Do not call
anything verified or measured that was calculated, simulated or estimated.
-->

## Checklist

- [ ] The pull request title follows the Conventional Commits format.
- [ ] Tests are added or updated, and the checks of every changed area pass
      locally (commands in `CONTRIBUTING.md`, section "Quality Gates").
- [ ] `CHANGELOG.md` is updated, or the change is not notable.
- [ ] A deviation from the specification is recorded in its decision log.
- [ ] Figures cite their source: a check record for a datasheet value, a
      report for a measurement. Estimates, calculations and simulations are
      labeled as such.
- [ ] A protocol change starts in `protocol/definition.toml` and includes
      the generated files and the test vectors.
- [ ] A change to the schematic or the board includes the pictures and the
      PDF in `hardware/doc/`, plotted again.
- [ ] The guides of the changed area say what is true after this change.
- [ ] The documentation lint passes (`npx --yes markdownlint-cli2@0.23.3`).
