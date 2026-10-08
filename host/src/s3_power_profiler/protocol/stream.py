"""Payload of a stream frame.

The payload is a small header followed by the sample words, little-endian::

    first_index u32 | dropped u16 | count u16 | count sample words
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from s3_power_profiler.errors import PayloadError
from s3_power_profiler.protocol._defs import FRAME_MAX_PAYLOAD
from s3_power_profiler.protocol.sample import SAMPLE_WORD_SIZE, pack_words, unpack_words

_HEADER = struct.Struct("<IHH")

STREAM_HEADER_SIZE = _HEADER.size
"""Size of the header that precedes the sample words, in bytes."""

MAX_STREAM_SAMPLES = (FRAME_MAX_PAYLOAD - STREAM_HEADER_SIZE) // SAMPLE_WORD_SIZE
"""Largest number of samples that fit in one stream frame."""

INDEX_MODULO = 1 << 32
"""Number of values of the 32-bit sample index; the index wraps to zero."""

_DROPPED_LIMIT = 1 << 16


@dataclass(frozen=True, slots=True)
class StreamPayload:
    """Payload of a stream frame.

    Attributes:
        first_index: Index of the first sample since START, modulo ``INDEX_MODULO``.
        dropped: Blocks the instrument dropped since the previous frame.
        words: Raw sample words, in sampling order.

    Raises:
        ValueError: If a field is outside its range or there are too many samples.
    """

    first_index: int
    dropped: int
    words: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.first_index < INDEX_MODULO:
            raise ValueError(f"first_index {self.first_index} does not fit in 32 bits")
        if not 0 <= self.dropped < _DROPPED_LIMIT:
            raise ValueError(f"dropped {self.dropped} does not fit in 16 bits")
        if len(self.words) > MAX_STREAM_SAMPLES:
            raise ValueError(
                f"{len(self.words)} samples exceed the limit of {MAX_STREAM_SAMPLES} per frame"
            )
        object.__setattr__(self, "words", tuple(self.words))

    @property
    def count(self) -> int:
        """Number of samples in the payload."""
        return len(self.words)


def encode_stream_payload(payload: StreamPayload) -> bytes:
    """Serialize a stream payload.

    Raises:
        ValueError: If a sample word does not fit in 32 bits.
    """
    header = _HEADER.pack(payload.first_index, payload.dropped, payload.count)
    return header + pack_words(payload.words)


def decode_stream_payload(data: bytes | bytearray | memoryview) -> StreamPayload:
    """Parse the payload of a stream frame.

    Raises:
        PayloadError: If the payload is shorter than its header or its length
            does not match the announced number of samples.
    """
    if len(data) < STREAM_HEADER_SIZE:
        raise PayloadError(
            f"stream payload of {len(data)} bytes is shorter than its "
            f"{STREAM_HEADER_SIZE}-byte header"
        )
    first_index, dropped, count = _HEADER.unpack_from(data)
    words = unpack_words(data, STREAM_HEADER_SIZE)
    if len(words) != count:
        raise PayloadError(f"stream payload announces {count} samples but carries {len(words)}")
    return StreamPayload(first_index=first_index, dropped=dropped, words=words)
