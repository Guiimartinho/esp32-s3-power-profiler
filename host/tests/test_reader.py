from __future__ import annotations

from s3_power_profiler.capture.reader import Gap, SampleBlock, StreamReader
from s3_power_profiler.protocol import (
    INDEX_MODULO,
    Sample,
    StreamPayload,
    pack_sample,
    split_words,
)

BLOCK = 4


def payload(first_index: int, dropped: int = 0, count: int = BLOCK) -> StreamPayload:
    """Stream payload whose words are simply the sample indexes."""
    words = tuple((first_index + offset) % INDEX_MODULO for offset in range(count))
    return StreamPayload(first_index=first_index, dropped=dropped, words=words)


def test_push_returns_the_samples_of_the_payload() -> None:
    reader = StreamReader()

    block = reader.push(payload(8))

    assert block == SampleBlock(first_index=8, words=(8, 9, 10, 11))
    assert len(block) == BLOCK


def test_consecutive_blocks_have_no_gap() -> None:
    reader = StreamReader()

    for index in range(0, 5 * BLOCK, BLOCK):
        reader.push(payload(index))

    assert reader.gaps == ()
    assert reader.blocks == 5
    assert reader.samples == 5 * BLOCK
    assert reader.missing_samples == 0
    assert reader.dropped_blocks == 0
    assert reader.restarts == 0


def test_blocks_of_different_sizes_are_followed_by_their_real_length() -> None:
    reader = StreamReader()

    reader.push(payload(0, count=3))
    reader.push(payload(3, count=5))
    reader.push(payload(8, count=1))

    assert reader.gaps == ()
    assert reader.samples == 9


def test_blocks_dropped_by_the_instrument_are_a_gap() -> None:
    reader = StreamReader()
    reader.push(payload(0))

    reader.push(payload(3 * BLOCK, dropped=2))

    assert reader.gaps == (
        Gap(
            expected_index=BLOCK,
            actual_index=3 * BLOCK,
            missing_samples=2 * BLOCK,
            dropped_blocks=2,
        ),
    )
    assert reader.missing_samples == 2 * BLOCK
    assert reader.dropped_blocks == 2


def test_samples_lost_on_the_way_are_a_gap_without_dropped_blocks() -> None:
    reader = StreamReader()
    reader.push(payload(0))

    reader.push(payload(2 * BLOCK))

    assert reader.gaps == (
        Gap(expected_index=BLOCK, actual_index=2 * BLOCK, missing_samples=BLOCK, dropped_blocks=0),
    )
    assert reader.dropped_blocks == 0


def test_dropped_blocks_without_an_index_jump_are_still_recorded() -> None:
    reader = StreamReader()
    reader.push(payload(0))

    reader.push(payload(BLOCK, dropped=1))

    assert reader.gaps == (
        Gap(expected_index=BLOCK, actual_index=BLOCK, missing_samples=0, dropped_blocks=1),
    )
    assert reader.missing_samples == 0
    assert reader.dropped_blocks == 1


def test_gaps_accumulate() -> None:
    reader = StreamReader()
    for index, dropped in ((0, 0), (2 * BLOCK, 1), (3 * BLOCK, 0), (6 * BLOCK, 2)):
        reader.push(payload(index, dropped))

    assert [gap.missing_samples for gap in reader.gaps] == [BLOCK, 2 * BLOCK]
    assert reader.missing_samples == 3 * BLOCK
    assert reader.dropped_blocks == 3
    assert reader.blocks == 4


def test_first_block_may_start_anywhere_by_default() -> None:
    reader = StreamReader()

    reader.push(payload(123456))

    assert reader.gaps == ()


def test_first_block_is_checked_against_the_expected_start() -> None:
    reader = StreamReader(start_index=0)

    reader.push(payload(BLOCK))

    assert reader.gaps == (
        Gap(expected_index=0, actual_index=BLOCK, missing_samples=BLOCK, dropped_blocks=0),
    )


def test_index_wraps_around_without_a_gap() -> None:
    reader = StreamReader()

    reader.push(payload(INDEX_MODULO - BLOCK))
    reader.push(payload(0))
    reader.push(payload(BLOCK))

    assert reader.gaps == ()
    assert reader.restarts == 0


def test_gap_across_the_wrap_is_measured_correctly() -> None:
    reader = StreamReader()
    reader.push(payload(INDEX_MODULO - BLOCK))

    reader.push(payload(BLOCK, dropped=1))

    assert reader.gaps == (
        Gap(expected_index=0, actual_index=BLOCK, missing_samples=BLOCK, dropped_blocks=1),
    )


def test_index_going_backwards_is_a_restart_not_a_gap() -> None:
    reader = StreamReader()
    reader.push(payload(10 * BLOCK))

    reader.push(payload(0))
    reader.push(payload(BLOCK))

    assert reader.restarts == 1
    assert reader.gaps == ()
    assert reader.missing_samples == 0


def test_reset_forgets_everything() -> None:
    reader = StreamReader()
    reader.push(payload(0))
    reader.push(payload(5 * BLOCK, dropped=4))

    reader.reset(start_index=0)

    assert (reader.blocks, reader.samples, reader.gaps) == (0, 0, ())
    assert (reader.missing_samples, reader.dropped_blocks, reader.restarts) == (0, 0, 0)
    reader.push(payload(0))
    assert reader.gaps == ()


def test_reset_without_a_start_accepts_any_index_again() -> None:
    reader = StreamReader(start_index=0)

    reader.reset()
    reader.push(payload(77))

    assert reader.gaps == ()


def test_block_gives_samples_as_objects_and_as_columns() -> None:
    samples = [
        Sample(adc=100, range_index=0, logic=1),
        Sample(adc=200, range_index=3, invalid=True, fault=True, logic=2),
    ]
    words = tuple(pack_sample(sample) for sample in samples)

    block = StreamReader().push(StreamPayload(first_index=0, dropped=0, words=words))

    assert block.samples() == samples
    assert block.columns() == split_words(words)
    assert block.columns().adc == (100, 200)
