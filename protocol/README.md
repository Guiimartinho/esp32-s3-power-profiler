# Protocol

The single definition of the wire protocol between the instrument and the
host. Section 7 of the [specification](../docs/specification.md) describes
the protocol; the files in this directory decide it.

| File | Content |
| --- | --- |
| `definition.toml` | Every constant: protocol version, frame layout and size limits, CRC parameters, sample word fields, the type, command, status, event, state and mode codes, the bits of the fault flags, and the constants of the command arguments |
| `vectors.toml` | Inputs of the shared test vectors: CRC inputs, frames and sample words |
| `generate.py` | Generator, with its own reference encoder |
| `vectors.json` | Generated: the encoded vectors, read by the host tests |

The generator also writes these files in other directories. They are
committed, and they are never edited by hand:

| Generated file | Used by |
| --- | --- |
| `firmware/components/proto/include/proto/pp_proto_defs.h` | Firmware: constants |
| `firmware/test/host/generated/pp_proto_vectors.h` | Firmware tests: vectors |
| `host/src/s3_power_profiler/protocol/_defs.py` | Host package: constants |

## Status

The definition is at protocol version 1, and the generated files are up to
date with it. Both codecs, the C one of the firmware core and the Python one
of the host package, reproduce the shared vectors in their unit tests. No
frame has passed between a controller and a PC yet: the firmware is not
ported to the Raspberry Pi Pico 2, and nothing of the instrument is built.

What the definition holds and what it does not:

- It holds the numbers: codes, bit positions, sizes and limits.
- It does not hold the layout of the command arguments or of the response
  and event data. Section 7.4 of the specification describes them, and they
  are provisional until the protocol is frozen in phase 6. The host keeps
  them in one module, `host/src/s3_power_profiler/protocol/commands.py`,
  which its client and its simulator share. The firmware core encodes and
  decodes the envelopes only; its command handlers are not written.
- It is behind draft A2 of the carrier board. The next section lists what
  is missing.

## State Against Draft A2

Draft A2 gave the firmware 36 rules that guard hardware (F-1 to F-36,
section 6.6 of the specification). Several of them end in something the
instrument has to tell the host, and the protocol has no place for it yet.
Section 16 of the specification lists that as an open check, and the
paragraph that closes section 6.6 says the same from the side of the rules.
None of the items below is in `definition.toml`, and so none is in a
generated file, in the firmware core or in the host package:

| Missing | Behind it | What the definition holds today |
| --- | --- | --- |
| A mark for an over-range sample: the code is 65535, or the jump comparator is high | F-35 | The sample word has the `invalid` and `fault` bits only; bits 20 to 23 are `reserved` and sent as zero |
| A mark for an under-range sample: the code stays below 650, which means a current that flows backward through the ladder | F-22, D-69 | As above |
| The invalid mark for the 5 ms after the supplying input changes or the 5 V rail steps by more than 0.3 V | F-35 | The `invalid` bit exists, and section 7.3 gives it one meaning: a sample inside the settling window of a range change |
| The fault flags beyond the four that exist. Section 6.4 names as causes: a sequencer that does not act (F-21), a reverse current (F-22), the loss of PWR_GOOD or a failed rails test (F-7, F-12), VIN over-voltage and VIN out of range (F-26, F-27), an overload and an external voltage on the source output (F-32, F-33), a failed start check, and a restart by the watchdog (F-8) | Section 6.4 | `[faults]` has `OVERCURRENT`, `POWER_LIMIT`, `THERMAL` and `SELFTEST`, bits 0 to 3 of a 16-bit field |
| The input in use (USB-C connector or the USB connector of the Pico 2) and the CC class of the source, in the status record | F-14, with F-11 and F-13 | No code for either. The data of GET_STATUS is provisional: state, fault flags and dropped blocks |
| The power budget as a current: 0.45 A, 1.4 A or 1.7 A at the input | D-49, F-14 | The event `POWER_BUDGET_CHANGED` exists as a code; section 7.4 gives its data as milliwatts in 2 bytes |
| The instant from which the host counts the 250 ms of output settling after the output is switched on | Sections 8 and 9, F-24 | Nothing marks it. The carrier puts the request line of the output switch among the 16 side bits of every sample (section 4.7), but the sample word has no field for it |

Section 8 of the specification asks two more things of the provisional data
of GET_INFO, which today is the protocol version, the hardware revision and
the firmware version: whether the instrument is calibrated or runs on
nominal values, and the serial number of the carrier that the calibration
record holds. They come with the calibration support, which is not written
(see the [calibration page](../docs/calibration/README.md)).

How these items are encoded is not decided. Section 16 sets the deadline:
they are in the definition, with the generated files and the test vectors,
before the firmware of phase 1 reports them.

### How an Item Enters

The definition comes first, and the rest follows from it in one change:

1. `definition.toml`: the new bit, code or constant. A sample mark takes
   one of the reserved bits of `[sample_word]`; a fault cause takes a bit of
   `[faults]`; a new set of codes is a new table.
2. `generate.py`, where the definition gains something the generator does
   not render or check yet. A new table of codes needs an entry in its list
   of enumerations. A new bit of `[faults]` is rendered without a change,
   but the generator does not reject a bit used twice there, so that check
   comes with it. A new field of the sample word reaches the constants
   without a change, but the structure of the sample vectors in the C
   header names its fields one by one and has to gain the new one.
3. `vectors.toml`: a vector that exercises the new item, so that both
   codecs are held to it.
4. The generated files of the firmware and of the host, written by the
   generator, and the code and the tests on both sides that use the item.
5. Section 7 of the specification, with the entry of section 16 updated
   and the decision recorded.

`version` in `[protocol]` is raised where the frame, the sample word or a
command changes, because an older firmware or host would read the new data
wrongly. Data appended to a response or to an event does not need it by
itself: a receiver ignores the bytes after the fields it knows (section
7.4). The steps are spelled out in the next section.

## Changing the Protocol

1. Edit `definition.toml`, and `vectors.toml` when a vector should cover the
   change.
2. Run the generator from the repository root. It needs Python 3.11 or later
   and nothing outside the standard library:

   ```sh
   python protocol/generate.py
   ```

3. Update section 7 of the specification and record the decision in its
   decision log. A change that an older firmware or host cannot understand
   raises `version` and is a breaking change: its commit carries `!` and a
   `BREAKING CHANGE:` footer, as the
   [contributing guide](../CONTRIBUTING.md) describes.
4. Run the firmware host tests and the host tests. Both codecs must reproduce
   the new vectors. The commands are in the
   [firmware guide](../firmware/README.md) and the
   [host guide](../host/README.md).
5. Commit the edited files and the generated files together.

The generator refuses a definition that contradicts itself: a header size
that does not match the frame layout, CRC parameters that do not give the
check value, a code used twice in one of the six tables of codes (frame
types, commands, status, events, states and modes), sample word fields that
overlap or do not add up to 32 bits, a full stream frame that does not fit
in the largest payload, or two vectors with one name. It does not check the
bits of `[faults]` or the values of `[constants]`: two fault causes on one
bit pass today, so the check for it is added to the generator together with
the first new fault bit.

## Checks

Run this from the repository root before you commit. It writes nothing and
fails when a generated file is stale:

```sh
python protocol/generate.py --check
```

The Protocol workflow runs the same command, and it lints the generator
with ruff and with mypy in strict mode. Like every workflow of the
repository it starts by hand only (decision D-22 of the specification), so
the local run is the one that counts day to day. The lint commands of the
workflow, also from the repository root:

```sh
ruff check protocol
ruff format --check protocol
mypy --strict protocol/generate.py
```

ruff and mypy are installed with the development tools of the host package
(see the [host guide](../host/README.md)).

## Reference Encoder

The vectors are not produced by the code they test. The generator has a small
bit-by-bit CRC and frame encoder of its own, and it checks that CRC against
`binascii.crc_hqx` from the Python standard library and against the check
value in `definition.toml` before writing anything.
