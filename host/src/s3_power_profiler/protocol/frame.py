"""Frame encoding and incremental decoding.

A frame is a header, a payload and a CRC, with every field little-endian::

    magic u16 | type u8 | flags u8 | length u16 | sequence u16 | payload | crc u16

``length`` counts the payload bytes and the CRC covers the header and the payload.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from s3_power_profiler.protocol._defs import (
    FRAME_CRC_SIZE,
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    FRAME_MAX_PAYLOAD,
    FrameType,
)
from s3_power_profiler.protocol.crc import crc16

_HEADER = struct.Struct("<HBBHH")
_CRC = struct.Struct("<H")
_MAGIC_BYTES = struct.pack("<H", FRAME_MAGIC)
_VALID_TYPES = frozenset(int(frame_type) for frame_type in FrameType)

SEQUENCE_MODULO = 1 << 16
"""Number of values of the 16-bit sequence field; the counter wraps to zero."""

_FLAGS_LIMIT = 1 << 8


@dataclass(frozen=True, slots=True)
class Frame:
    """One protocol frame.

    Attributes:
        frame_type: Kind of frame.
        sequence: Counter of the frame, from 0 to ``SEQUENCE_MODULO - 1``.
        payload: Payload bytes, at most ``FRAME_MAX_PAYLOAD`` of them.
        flags: Reserved byte, zero in this protocol version.

    Raises:
        ValueError: If a field is outside its range.
    """

    frame_type: FrameType
    sequence: int
    payload: bytes = b""
    flags: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.sequence < SEQUENCE_MODULO:
            raise ValueError(f"sequence {self.sequence} does not fit in 16 bits")
        if not 0 <= self.flags < _FLAGS_LIMIT:
            raise ValueError(f"flags {self.flags} do not fit in 8 bits")
        if len(self.payload) > FRAME_MAX_PAYLOAD:
            raise ValueError(
                f"payload of {len(self.payload)} bytes exceeds the limit of {FRAME_MAX_PAYLOAD}"
            )
        object.__setattr__(self, "frame_type", FrameType(self.frame_type))
        object.__setattr__(self, "payload", bytes(self.payload))


def encode_frame(frame: Frame) -> bytes:
    """Serialize a frame, CRC included."""
    body = (
        _HEADER.pack(FRAME_MAGIC, frame.frame_type, frame.flags, len(frame.payload), frame.sequence)
        + frame.payload
    )
    return body + _CRC.pack(crc16(body))


class FrameDecoder:
    """Incremental frame decoder.

    Feed it the received bytes in chunks of any size. It returns the complete
    frames found so far and keeps an unfinished tail for the next call. It never
    raises on malformed input: bytes that do not belong to a valid frame are
    skipped and counted, and decoding resumes at the next magic word.

    A header is accepted when it starts with the magic word, names a known frame
    type and announces a payload within the limit. The frame is then delivered
    only if its CRC matches. The header has no checksum of its own, so a false
    header inside noise holds back the following bytes until the payload it
    announces has arrived.

    Args:
        max_payload: Largest payload to accept, at most ``FRAME_MAX_PAYLOAD``.

    Raises:
        ValueError: If ``max_payload`` is outside the protocol limit.
    """

    def __init__(self, max_payload: int = FRAME_MAX_PAYLOAD) -> None:
        if not 0 <= max_payload <= FRAME_MAX_PAYLOAD:
            raise ValueError(f"max_payload must be between 0 and {FRAME_MAX_PAYLOAD}")
        self._max_payload = max_payload
        self._buffer = bytearray()
        self._frames_decoded = 0
        self._discarded_bytes = 0
        self._crc_errors = 0

    @property
    def frames_decoded(self) -> int:
        """Number of valid frames returned so far."""
        return self._frames_decoded

    @property
    def discarded_bytes(self) -> int:
        """Number of received bytes that were not part of a valid frame."""
        return self._discarded_bytes

    @property
    def crc_errors(self) -> int:
        """Number of frames rejected because their CRC did not match."""
        return self._crc_errors

    @property
    def pending_bytes(self) -> int:
        """Number of bytes held while waiting for the rest of a frame."""
        return len(self._buffer)

    def reset(self) -> None:
        """Forget the pending bytes and clear the counters."""
        self._buffer.clear()
        self._frames_decoded = 0
        self._discarded_bytes = 0
        self._crc_errors = 0

    def feed(self, data: bytes | bytearray | memoryview) -> list[Frame]:
        """Add received bytes and return the frames completed by them.

        Args:
            data: The next bytes of the stream, in any amount.

        Returns:
            The complete frames, in the order received. The list is empty when
            the bytes did not complete a frame.
        """
        self._buffer += data
        frames = []
        while (frame := self._next_frame()) is not None:
            frames.append(frame)
        return frames

    def _next_frame(self) -> Frame | None:
        """Extract one frame from the buffer, or return None if more bytes are needed."""
        buffer = self._buffer
        while True:
            start = buffer.find(_MAGIC_BYTES)
            if start < 0:
                # A trailing first magic byte may be completed by the next chunk.
                keep = 1 if buffer.endswith(_MAGIC_BYTES[:1]) else 0
                self._discard(len(buffer) - keep)
                return None
            self._discard(start)
            if len(buffer) < FRAME_HEADER_SIZE:
                return None
            _magic, type_id, flags, length, sequence = _HEADER.unpack_from(buffer)
            if type_id not in _VALID_TYPES or length > self._max_payload:
                self._discard(1)
                continue
            body_size = FRAME_HEADER_SIZE + length
            if len(buffer) < body_size + FRAME_CRC_SIZE:
                return None
            body = bytes(buffer[:body_size])
            (received_crc,) = _CRC.unpack_from(buffer, body_size)
            if crc16(body) != received_crc:
                self._crc_errors += 1
                self._discard(1)
                continue
            del buffer[: body_size + FRAME_CRC_SIZE]
            self._frames_decoded += 1
            return Frame(FrameType(type_id), sequence, body[FRAME_HEADER_SIZE:], flags)

    def _discard(self, count: int) -> None:
        """Drop ``count`` bytes from the front of the buffer and count them."""
        if count:
            del self._buffer[:count]
            self._discarded_bytes += count
