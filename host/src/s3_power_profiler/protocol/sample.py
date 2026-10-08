"""The 32-bit sample word.

Every sample carries its own context: the ADC code, the range that was active,
whether the sample is inside the settling window of a range change, the fault
latch and the eight logic inputs. The reserved bits are written as zero and
ignored when reading.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass

from s3_power_profiler.errors import PayloadError
from s3_power_profiler.protocol._defs import (
    SAMPLE_ADC_MASK,
    SAMPLE_ADC_SHIFT,
    SAMPLE_FAULT_MASK,
    SAMPLE_FAULT_SHIFT,
    SAMPLE_INVALID_MASK,
    SAMPLE_INVALID_SHIFT,
    SAMPLE_LOGIC_MASK,
    SAMPLE_LOGIC_SHIFT,
    SAMPLE_RANGE_MASK,
    SAMPLE_RANGE_SHIFT,
)

_WORD = struct.Struct("<I")

SAMPLE_WORD_SIZE = _WORD.size
"""Size of one sample word on the wire, in bytes."""

_WORD_LIMIT = 1 << (8 * SAMPLE_WORD_SIZE)


@dataclass(frozen=True, slots=True)
class Sample:
    """One decoded sample.

    Attributes:
        adc: Raw ADC code.
        range_index: Range that was active, 0 for R0 up to 3 for R3.
        invalid: True inside the settling window of a range change.
        fault: True while the over-current trip is latched.
        logic: Digital inputs, D0 in bit 0 up to D7 in bit 7.

    Raises:
        ValueError: If a field does not fit in its bits of the sample word.
    """

    adc: int
    range_index: int
    invalid: bool = False
    fault: bool = False
    logic: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.adc <= SAMPLE_ADC_MASK:
            raise ValueError(f"adc {self.adc} is outside 0 to {SAMPLE_ADC_MASK}")
        if not 0 <= self.range_index <= SAMPLE_RANGE_MASK:
            raise ValueError(f"range_index {self.range_index} is outside 0 to {SAMPLE_RANGE_MASK}")
        if not 0 <= self.logic <= SAMPLE_LOGIC_MASK:
            raise ValueError(f"logic {self.logic} is outside 0 to {SAMPLE_LOGIC_MASK}")


@dataclass(frozen=True, slots=True)
class SampleColumns:
    """The fields of a run of samples, one tuple per field.

    All tuples have the same length and the same order as the samples.

    Attributes:
        adc: Raw ADC codes.
        range_index: Active range of each sample.
        invalid: Settling-window flag of each sample.
        fault: Fault-latch flag of each sample.
        logic: Digital inputs of each sample.
    """

    adc: tuple[int, ...]
    range_index: tuple[int, ...]
    invalid: tuple[bool, ...]
    fault: tuple[bool, ...]
    logic: tuple[int, ...]

    def __len__(self) -> int:
        return len(self.adc)


def pack_sample(sample: Sample) -> int:
    """Return the 32-bit word of a sample."""
    return (
        (sample.adc << SAMPLE_ADC_SHIFT)
        | (sample.range_index << SAMPLE_RANGE_SHIFT)
        | (int(sample.invalid) << SAMPLE_INVALID_SHIFT)
        | (int(sample.fault) << SAMPLE_FAULT_SHIFT)
        | (sample.logic << SAMPLE_LOGIC_SHIFT)
    )


def unpack_sample(word: int) -> Sample:
    """Decode one 32-bit sample word.

    Raises:
        ValueError: If ``word`` does not fit in 32 bits.
    """
    if not 0 <= word < _WORD_LIMIT:
        raise ValueError(f"sample word {word} does not fit in 32 bits")
    return Sample(
        adc=(word >> SAMPLE_ADC_SHIFT) & SAMPLE_ADC_MASK,
        range_index=(word >> SAMPLE_RANGE_SHIFT) & SAMPLE_RANGE_MASK,
        invalid=bool((word >> SAMPLE_INVALID_SHIFT) & SAMPLE_INVALID_MASK),
        fault=bool((word >> SAMPLE_FAULT_SHIFT) & SAMPLE_FAULT_MASK),
        logic=(word >> SAMPLE_LOGIC_SHIFT) & SAMPLE_LOGIC_MASK,
    )


def pack_words(words: Sequence[int]) -> bytes:
    """Serialize sample words, little-endian.

    Raises:
        ValueError: If a word does not fit in 32 bits.
    """
    try:
        return struct.pack(f"<{len(words)}I", *words)
    except struct.error as error:
        raise ValueError(f"sample word does not fit in 32 bits: {error}") from error


def unpack_words(data: bytes | bytearray | memoryview, offset: int = 0) -> tuple[int, ...]:
    """Read every sample word from ``offset`` to the end of ``data``.

    The whole block is converted in one call, which is what keeps a 100 kSPS
    stream affordable without third-party libraries.

    Raises:
        PayloadError: If the bytes after ``offset`` are not a whole number of words.
    """
    size = len(data) - offset
    if size < 0 or size % SAMPLE_WORD_SIZE:
        raise PayloadError(f"{size} bytes are not a whole number of sample words")
    return struct.unpack_from(f"<{size // SAMPLE_WORD_SIZE}I", data, offset)


def split_words(words: Sequence[int]) -> SampleColumns:
    """Split sample words into one column per field."""
    return SampleColumns(
        adc=tuple((word >> SAMPLE_ADC_SHIFT) & SAMPLE_ADC_MASK for word in words),
        range_index=tuple((word >> SAMPLE_RANGE_SHIFT) & SAMPLE_RANGE_MASK for word in words),
        invalid=tuple(bool((word >> SAMPLE_INVALID_SHIFT) & SAMPLE_INVALID_MASK) for word in words),
        fault=tuple(bool((word >> SAMPLE_FAULT_SHIFT) & SAMPLE_FAULT_MASK) for word in words),
        logic=tuple((word >> SAMPLE_LOGIC_SHIFT) & SAMPLE_LOGIC_MASK for word in words),
    )
