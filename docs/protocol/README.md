# Host Protocol

The wire protocol between the instrument and the PC: binary frames over the
USB serial port (CDC ACM), the same frame format in both directions.

## Where It Is Defined

The protocol has two sources that are kept in agreement:

- Section 7 of the [specification](../specification.md) describes the frame
  format, the sample word and the commands.
- [`protocol/definition.toml`](../../protocol/definition.toml) holds every
  number. The constants used by the firmware and by the host are generated
  from it, together with the shared test vectors. See the
  [protocol directory](../../protocol/README.md).

## Status

- The protocol is at version 1 and is not frozen. The layouts of the command
  arguments and of the response and event data are provisional (section 7.4
  of the specification).
- Both codecs exist and reproduce the shared test vectors: the C one in the
  firmware core and the Python one in the host package, which also has a
  simulated instrument. No frame has passed between a controller and a PC:
  the firmware is not ported to the Raspberry Pi Pico 2, and no hardware is
  built.
- The protocol is behind draft A2 of the carrier board. Section 16 of the
  specification lists what the instrument has to report and the definition
  does not hold yet: marks for over-range and under-range samples (F-22,
  F-35), the invalid mark for the 5 ms after a change of supply (F-35), the
  fault flags that section 6.4 names beyond the four that exist, the input
  in use and the CC class of the source (F-14), the power budget as a
  current (D-49), and the instant from which the host counts the 250 ms of
  output settling. None of them is in the definition. The
  [protocol directory](../../protocol/README.md) gives the list with what
  the definition holds today, and the way an item enters: the definition
  first, then the generated files and the test vectors in the same change.

## What Comes Here

A reference written for users of the protocol, for someone who writes a
client of their own. It is added when the protocol is frozen in phase 6
(section 13 of the specification); until then section 7 is the description,
and it can still change. The reference will hold:

- the frame, byte by byte, with the CRC and the way a receiver finds the
  next frame after a damaged one;
- the stream payload and the sample word, with the meaning of every flag
  and how flagged samples are treated in statistics;
- every command with its arguments, its response data and the states that
  accept it, and every event with its data;
- the status record and the fault flags, with the cause behind each flag
  and what clears it;
- the conversion from ADC codes to current with the calibration table that
  the instrument reports (see [calibration](../calibration/README.md));
- the version rule: what a client checks at connection, and which changes
  raise the protocol version;
- a worked example of a capture, with the bytes on the wire.
