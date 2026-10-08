# Hardware

The carrier board of the instrument: schematic, PCB layout, simulations and
fabrication outputs.

The instrument is two boards. An ESP32-S3-DevKitC-1 compatible development
board, bought ready-made, is the controller. It plugs into two rows of pin
sockets on the carrier board designed here, which holds everything else:
power input, source meter, shunt ladder, range logic, signal chain and
connectors. Sections 4.11 and 5 of the
[specification](../docs/specification.md) define the interface.

## Status

The KiCad project exists with the part of the design that is already fixed:
the sockets of the development board and the 19 signals between the boards.

The analog blocks are not drawn yet. Their components are candidates until
the records in [`docs/checks/`](../docs/checks/) are closed, and the
specification requires those checks before the schematic is frozen. There is
no PCB layout.

## Layout

| Path | Content |
| --- | --- |
| `kicad/` | KiCad 10 project: schematic sheets and library tables |
| `kicad/lib/` | Project symbol library and footprint library |
| `simulation/` | SPICE simulations: front end, range logic and regulator |
| `fabrication/` | Outputs of each revision: Gerber and drill files, bill of materials, placement |

## KiCad Project

Open `kicad/power-profiler-carrier.kicad_pro` with KiCad 10.

| Sheet | File | Content |
| --- | --- | --- |
| Root | `power-profiler-carrier.kicad_sch` | Block level; lists the sheets still to come |
| MCU Interface | `mcu_interface.kicad_sch` | Development board on its sockets, with every signal of section 5 on a global label |

Project library `PowerProfiler`:

| Item | Description |
| --- | --- |
| Symbol `ESP32-S3-DevKitC-1` | 44 pins. Pin numbers give header and position, `J1_1` to `J3_22` |
| Footprint `ESP32-S3-DevKitC-1_Socket` | Two rows of 22 holes, 2.54 mm pitch, 22.86 mm apart, 1.0 mm drill |

The pinout and the dimensions come from the Espressif user guide, schematic
and layout drawing of the ESP32-S3-DevKitC-1 v1.1. Seen from the top with the
antenna up, J1 is the left row and pin 1 of both rows is at the antenna end.
The outline on the fabrication layer is the reference board, 25.40 mm by
62.74 mm. A clone can be longer or wider: measure the board in hand before
fabricating the carrier.

### Checks

Run the electrical rules check from `kicad/`:

```sh
kicad-cli sch erc --severity-all power-profiler-carrier.kicad_sch
```

It reports no errors and 20 warnings of one kind, "label connected to only
one pin": the signals end at the edge of the MCU sheet until the sheets that
use them exist. Each new sheet removes some of these warnings, and the count
must reach zero before layout starts.

### Sheets Still to Come

Each one is drawn after the component checks of its parts are closed:

| Sheet | Specification |
| --- | --- |
| Power input and analog rails | 4.1 and the power tree |
| Source meter: pre-regulator, LDO, DAC | 4.2 |
| Mode switch, output switch and protection | 4.2, 4.9 |
| Shunt ladder with Kelvin multiplexer | 4.3 |
| Range control logic and fault latch | 4.4 |
| Signal chain, ADC and side data | 4.5 to 4.7 |
| Digital inputs | 4.8 |
| Slow monitors | 4.2 |

## Design References

In the [specification](../docs/specification.md):

- Section 4: analog hardware design, from the power input to the error
  budget, and the interface to the development board.
- Section 5: pin map.
- Section 10: PCB and mechanical guidelines.
- Section 17: bill of materials summary.

## Revisions

Board revisions are named with letters. Revision A is the first complete
carrier board (phase 5) and revision B corrects the issues found on it
(phase 7). Fabrication outputs are stored per revision, for example
`fabrication/rev-a/`.

## License

Copyright (c) 2026 Luiz Guilherme Ito.

The design files in this directory are licensed under the CERN Open Hardware
Licence Version 2 - Permissive (CERN-OHL-P v2). See [LICENSE](LICENSE). They
are provided without any warranty, as stated in section 5 of the license.
