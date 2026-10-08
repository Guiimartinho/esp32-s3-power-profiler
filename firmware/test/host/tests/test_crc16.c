#include "unity.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "pp_proto_vectors.h"
#include "proto/pp_crc16.h"
#include "proto/pp_proto_defs.h"

void setUp(void)
{
}

void tearDown(void)
{
}

/* The CRC computed one bit at a time, straight from the definition. */
static uint16_t reference_crc16(uint16_t crc, const uint8_t *data, size_t len)
{
    for (size_t i = 0u; i < len; i++) {
        crc = (uint16_t)(crc ^ (uint16_t)((uint16_t)data[i] << 8));
        for (unsigned bit = 0u; bit < 8u; bit++) {
            if ((crc & 0x8000u) != 0u) {
                crc = (uint16_t)((uint16_t)(crc << 1) ^ (uint16_t)PP_CRC16_POLYNOMIAL);
            } else {
                crc = (uint16_t)(crc << 1);
            }
        }
    }
    return crc;
}

/* Deterministic pseudo-random bytes, so a failure can be reproduced. */
static void fill_pattern(uint8_t *buffer, size_t len, uint32_t seed)
{
    uint32_t state = seed;
    for (size_t i = 0u; i < len; i++) {
        state = (state * 1664525u) + 1013904223u;
        buffer[i] = (uint8_t)(state >> 24);
    }
}

static void test_crc16_check_value_of_the_definition(void)
{
    const uint8_t check[] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};

    TEST_ASSERT_EQUAL_HEX16(PP_CRC16_CHECK, pp_crc16(check, sizeof(check)));
}

static void test_crc16_shared_vectors(void)
{
    for (size_t i = 0u; i < PP_CRC_VECTOR_COUNT; i++) {
        const pp_crc_vector_t *vector = &pp_crc_vectors[i];
        TEST_ASSERT_EQUAL_HEX16_MESSAGE(vector->crc, pp_crc16(vector->data, vector->data_len),
                                        vector->name);
    }
}

static void test_crc16_of_no_data_is_the_initial_value(void)
{
    const uint8_t unused = 0u;

    TEST_ASSERT_EQUAL_HEX16(PP_CRC16_INIT, pp_crc16(&unused, 0u));
    TEST_ASSERT_EQUAL_HEX16(PP_CRC16_INIT, pp_crc16(NULL, 0u));
}

static void test_crc16_null_data_leaves_the_crc_unchanged(void)
{
    TEST_ASSERT_EQUAL_HEX16(0x1234u, pp_crc16_update(0x1234u, NULL, 8u));
}

static void test_crc16_table_matches_the_polynomial(void)
{
    for (unsigned value = 0u; value < 256u; value++) {
        uint8_t byte = (uint8_t)value;
        TEST_ASSERT_EQUAL_HEX16(reference_crc16(0u, &byte, 1u), pp_crc16_update(0u, &byte, 1u));
    }
}

static void test_crc16_matches_the_reference_on_random_data(void)
{
    uint8_t buffer[300];

    for (uint32_t round = 0u; round < 50u; round++) {
        size_t len = ((size_t)round * 37u) % sizeof(buffer);
        fill_pattern(buffer, len, round + 1u);
        TEST_ASSERT_EQUAL_HEX16(reference_crc16((uint16_t)PP_CRC16_INIT, buffer, len),
                                pp_crc16(buffer, len));
    }
}

static void test_crc16_in_pieces_equals_crc16_in_one_go(void)
{
    uint8_t buffer[64];
    fill_pattern(buffer, sizeof(buffer), 0xC0FFEEu);
    uint16_t whole = pp_crc16(buffer, sizeof(buffer));

    for (size_t split = 0u; split <= sizeof(buffer); split++) {
        uint16_t crc = pp_crc16_update((uint16_t)PP_CRC16_INIT, buffer, split);
        crc = pp_crc16_update(crc, buffer + split, sizeof(buffer) - split);
        TEST_ASSERT_EQUAL_HEX16(whole, crc);
    }
}

static void test_crc16_detects_every_single_bit_error(void)
{
    uint8_t buffer[32];
    fill_pattern(buffer, sizeof(buffer), 7u);
    uint16_t good = pp_crc16(buffer, sizeof(buffer));

    for (size_t bit = 0u; bit < (sizeof(buffer) * 8u); bit++) {
        buffer[bit / 8u] ^= (uint8_t)(1u << (bit % 8u));
        TEST_ASSERT_NOT_EQUAL(good, pp_crc16(buffer, sizeof(buffer)));
        buffer[bit / 8u] ^= (uint8_t)(1u << (bit % 8u));
    }
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_crc16_check_value_of_the_definition);
    RUN_TEST(test_crc16_shared_vectors);
    RUN_TEST(test_crc16_of_no_data_is_the_initial_value);
    RUN_TEST(test_crc16_null_data_leaves_the_crc_unchanged);
    RUN_TEST(test_crc16_table_matches_the_polynomial);
    RUN_TEST(test_crc16_matches_the_reference_on_random_data);
    RUN_TEST(test_crc16_in_pieces_equals_crc16_in_one_go);
    RUN_TEST(test_crc16_detects_every_single_bit_error);
    return UNITY_END();
}
