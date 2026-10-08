# Host Protocol

The protocol has two sources that are kept in agreement:

- Section 7 of the [specification](../specification.md) describes the frame
  format, the sample word and the commands.
- [`protocol/definition.toml`](../../protocol/definition.toml) holds every
  number. The constants used by the firmware and by the host are generated
  from it, together with the shared test vectors. See the
  [protocol directory](../../protocol/README.md).

A reference written for users of the protocol will be added here when the
protocol is frozen in phase 6.
