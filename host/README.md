# Host Software

Python package that talks to the instrument: protocol codec, command-line
capture tool, desktop viewer and analysis.

Status: not started. The package grows together with the firmware from
phase 1, and the protocol in section 7 of the
[specification](../docs/specification.md) is implemented from the first
prototype.

## Planned Layout

| Path | Content |
| --- | --- |
| `src/` | The Python package: device layer, capture tool, viewer, analysis |
| `tests/` | Unit tests, including the protocol frames shared with the firmware |

## Planned Features

From section 9 of the specification:

- Device layer with the protocol codec, resynchronization on the magic word,
  CRC check and gap detection from the sample index.
- Live plot of current against time with min/max decimation, with the
  digital channels below the trace.
- Statistics over a selection: average, maximum, charge and energy.
- Controls for mode, voltage, DUT power, range and calibration.
- Export to CSV and to a compact binary format.
- Burst detection and battery-life estimate.
