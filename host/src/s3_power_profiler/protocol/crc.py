"""CRC-16/CCITT-FALSE, the checksum that closes every frame.

The polynomial and the initial value come from the protocol definition. The
algorithm processes the most significant bit first, without reflection and
without a final XOR.
"""

from __future__ import annotations

from s3_power_profiler.protocol._defs import CRC16_INIT, CRC16_POLYNOMIAL

_WIDTH = 16
_MASK = (1 << _WIDTH) - 1
_TOP_BIT = 1 << (_WIDTH - 1)


def _build_table(polynomial: int) -> tuple[int, ...]:
    """Return the CRC of every possible byte, used to process one byte per step."""
    table = []
    for byte in range(256):
        crc = byte << (_WIDTH - 8)
        for _ in range(8):
            crc = ((crc << 1) ^ polynomial) if crc & _TOP_BIT else (crc << 1)
        table.append(crc & _MASK)
    return tuple(table)


_TABLE = _build_table(CRC16_POLYNOMIAL)


def crc16(data: bytes | bytearray | memoryview, initial: int = CRC16_INIT) -> int:
    """Compute the CRC of ``data``.

    Args:
        data: The bytes to check.
        initial: Starting value. Pass the CRC of a previous chunk to continue it.

    Returns:
        The 16-bit CRC.
    """
    crc = initial
    for byte in data:
        crc = ((crc << 8) & _MASK) ^ _TABLE[(crc >> 8) ^ byte]
    return crc
