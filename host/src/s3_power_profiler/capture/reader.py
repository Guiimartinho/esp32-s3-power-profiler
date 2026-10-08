"""From stream payloads to sample blocks, with gap detection.

Every stream payload carries the index of its first sample and the number of
blocks the instrument dropped since the previous frame. The reader compares
each payload with the one before it and records where samples are missing.
"""

from __future__ import annotations

from dataclasses import dataclass

from s3_power_profiler.protocol import (
    INDEX_MODULO,
    Sample,
    SampleColumns,
    StreamPayload,
    split_words,
    unpack_sample,
)

_BACKWARD_JUMP = INDEX_MODULO // 2


@dataclass(frozen=True, slots=True)
class SampleBlock:
    """Consecutive samples from one stream frame.

    Attributes:
        first_index: Index of the first sample since START.
        words: Raw sample words, in sampling order.
    """

    first_index: int
    words: tuple[int, ...]

    def __len__(self) -> int:
        return len(self.words)

    def samples(self) -> list[Sample]:
        """Return the samples as objects, one per word."""
        return [unpack_sample(word) for word in self.words]

    def columns(self) -> SampleColumns:
        """Return the samples as one tuple per field."""
        return split_words(self.words)


@dataclass(frozen=True, slots=True)
class Gap:
    """A place where the stream is not continuous.

    Attributes:
        expected_index: Index at which the next block should have started.
        actual_index: Index at which it started.
        missing_samples: Samples between the two indexes.
        dropped_blocks: Blocks the instrument reported as dropped in the frame
            that follows the gap. Samples missing beyond these blocks were lost
            between the instrument and the reader.
    """

    expected_index: int
    actual_index: int
    missing_samples: int
    dropped_blocks: int


class StreamReader:
    """Turns stream payloads into sample blocks and keeps track of gaps.

    Args:
        start_index: Index the first block is expected to start at, or None to
            accept any index, as when joining a stream that is already running.
    """

    def __init__(self, start_index: int | None = None) -> None:
        self._gaps: list[Gap] = []
        self.reset(start_index)

    @property
    def blocks(self) -> int:
        """Number of blocks received."""
        return self._blocks

    @property
    def samples(self) -> int:
        """Number of samples received."""
        return self._samples

    @property
    def gaps(self) -> tuple[Gap, ...]:
        """The gaps found so far, in order."""
        return tuple(self._gaps)

    @property
    def missing_samples(self) -> int:
        """Total number of samples missing in the gaps."""
        return self._missing_samples

    @property
    def dropped_blocks(self) -> int:
        """Total number of blocks the instrument reported as dropped."""
        return self._dropped_blocks

    @property
    def restarts(self) -> int:
        """Number of times the sample index went backwards."""
        return self._restarts

    def reset(self, start_index: int | None = None) -> None:
        """Forget everything, as before a new START.

        Args:
            start_index: Index the next block is expected to start at, or None
                to accept any index.
        """
        self._next_index = start_index
        self._gaps.clear()
        self._blocks = 0
        self._samples = 0
        self._missing_samples = 0
        self._dropped_blocks = 0
        self._restarts = 0

    def push(self, payload: StreamPayload) -> SampleBlock:
        """Account for one stream payload and return its samples.

        A block that starts later than expected, or that reports dropped
        blocks, is recorded as a gap. An index that goes backwards means the
        stream was restarted and is counted in ``restarts``.
        """
        expected = payload.first_index if self._next_index is None else self._next_index
        jump = (payload.first_index - expected) % INDEX_MODULO
        if jump >= _BACKWARD_JUMP:
            self._restarts += 1
        elif jump or payload.dropped:
            self._gaps.append(
                Gap(
                    expected_index=expected,
                    actual_index=payload.first_index,
                    missing_samples=jump,
                    dropped_blocks=payload.dropped,
                )
            )
            self._missing_samples += jump
        self._dropped_blocks += payload.dropped
        self._next_index = (payload.first_index + payload.count) % INDEX_MODULO
        self._blocks += 1
        self._samples += payload.count
        return SampleBlock(first_index=payload.first_index, words=payload.words)
