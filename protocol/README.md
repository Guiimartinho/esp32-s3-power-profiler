# Protocol

The single definition of the wire protocol between the instrument and the
host. Section 7 of the [specification](../docs/specification.md) describes
the protocol; the files in this directory decide it.

| File | Content |
| --- | --- |
| `definition.toml` | Every constant: frame layout, CRC parameters, sample word fields, and the type, command, status, event and state codes |
| `vectors.toml` | Inputs of the shared test vectors |
| `generate.py` | Generator, with its own reference encoder |
| `vectors.json` | Generated: the encoded vectors, read by the host tests |

The generator also writes these files in other directories. They are
committed, and they are never edited by hand:

| Generated file | Used by |
| --- | --- |
| `firmware/components/proto/include/proto/pp_proto_defs.h` | Firmware: constants |
| `firmware/test/host/generated/pp_proto_vectors.h` | Firmware tests: vectors |
| `host/src/s3_power_profiler/protocol/_defs.py` | Host package: constants |

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
   raises `version` and is a breaking change.
4. Run the firmware host tests and the host tests. Both codecs must reproduce
   the new vectors.
5. Commit the edited files and the generated files together.

Continuous integration runs `python protocol/generate.py --check` and fails
when a generated file is stale.

## Reference Encoder

The vectors are not produced by the code they test. The generator has a small
bit-by-bit CRC and frame encoder of its own, and it checks that CRC against
`binascii.crc_hqx` from the Python standard library and against the check
value in `definition.toml` before writing anything.
