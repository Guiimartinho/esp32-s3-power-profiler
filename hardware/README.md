# Hardware

Schematic, PCB layout, simulations and fabrication outputs of the
instrument.

Status: not started. The component choices in the specification are
candidates until their records in [`docs/checks/`](../docs/checks/) are
closed.

## Layout

| Path | Content |
| --- | --- |
| `kicad/` | KiCad project: schematic, PCB layout and project libraries |
| `simulation/` | SPICE simulations: front end, range logic and regulator |
| `fabrication/` | Outputs of each revision: Gerber and drill files, bill of materials, placement |

## Design References

In the [specification](../docs/specification.md):

- Section 4: analog hardware design, from the power input to the error
  budget.
- Section 5: microcontroller connections and pin map.
- Section 10: PCB and mechanical guidelines.
- Section 17: bill of materials summary.

## Revisions

Board revisions are named with letters. Revision A is the first integrated
board (phase 5) and revision B corrects the issues found on it (phase 7).
Fabrication outputs are stored per revision, for example
`fabrication/rev-a/`.

## License

Copyright (c) 2026 Luiz Guilherme Ito.

The design files in this directory are licensed under the CERN Open Hardware
Licence Version 2 - Permissive (CERN-OHL-P v2). See [LICENSE](LICENSE). They
are provided without any warranty, as stated in section 5 of the license.
