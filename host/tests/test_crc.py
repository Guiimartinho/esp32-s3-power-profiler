from __future__ import annotations

import binascii
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from s3_power_profiler.protocol._defs import CRC16_CHECK, CRC16_INIT, CRC16_POLYNOMIAL
from s3_power_profiler.protocol.crc import crc16

# binascii.crc_hqx implements this polynomial, which makes it an independent oracle.
STANDARD_LIBRARY_POLYNOMIAL = 0x1021


def test_reproduces_shared_vector(crc_vector: dict[str, Any]) -> None:
    assert crc16(bytes.fromhex(crc_vector["data"])) == crc_vector["crc"]


def test_check_string_gives_the_check_value_of_the_definition() -> None:
    assert crc16(b"123456789") == CRC16_CHECK


def test_empty_input_gives_the_initial_value() -> None:
    assert crc16(b"") == CRC16_INIT


@pytest.mark.skipif(
    CRC16_POLYNOMIAL != STANDARD_LIBRARY_POLYNOMIAL,
    reason="the standard library implements a different polynomial",
)
@given(data=st.binary(max_size=512))
def test_agrees_with_the_standard_library(data: bytes) -> None:
    assert crc16(data) == binascii.crc_hqx(data, CRC16_INIT)


@given(head=st.binary(max_size=128), tail=st.binary(max_size=128))
def test_continues_from_the_crc_of_a_previous_chunk(head: bytes, tail: bytes) -> None:
    assert crc16(tail, crc16(head)) == crc16(head + tail)


@given(data=st.binary(min_size=1, max_size=128), position=st.integers(min_value=0))
def test_detects_any_single_bit_error(data: bytes, position: int) -> None:
    bit = position % (8 * len(data))
    corrupted = bytearray(data)
    corrupted[bit // 8] ^= 1 << (bit % 8)
    assert crc16(corrupted) != crc16(data)


@given(data=st.binary(max_size=64))
def test_result_fits_in_16_bits(data: bytes) -> None:
    assert 0 <= crc16(data) <= 0xFFFF


def test_accepts_bytearray_and_memoryview() -> None:
    data = b"power profiler"
    assert crc16(bytearray(data)) == crc16(data)
    assert crc16(memoryview(data)) == crc16(data)
