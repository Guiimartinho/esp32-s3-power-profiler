#include "unity.h"

#include <stddef.h>
#include <stdint.h>

#include "pp_proto_vectors.h"
#include "proto/pp_sample.h"

void setUp(void)
{
}

void tearDown(void)
{
}

static void test_sample_pack_matches_the_shared_vectors(void)
{
    for (size_t i = 0u; i < PP_SAMPLE_VECTOR_COUNT; i++) {
        const pp_sample_vector_t *vector = &pp_sample_vectors[i];
        pp_sample_t sample = {
            .adc = vector->adc,
            .range = vector->range,
            .invalid = (vector->invalid != 0u),
            .fault = (vector->fault != 0u),
            .logic = vector->logic,
        };

        TEST_ASSERT_EQUAL_HEX32_MESSAGE(vector->word, pp_sample_pack(&sample), vector->name);
    }
}

static void test_sample_unpack_matches_the_shared_vectors(void)
{
    for (size_t i = 0u; i < PP_SAMPLE_VECTOR_COUNT; i++) {
        const pp_sample_vector_t *vector = &pp_sample_vectors[i];
        pp_sample_t sample;

        pp_sample_unpack(vector->word, &sample);

        TEST_ASSERT_EQUAL_HEX16_MESSAGE(vector->adc, sample.adc, vector->name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(vector->range, sample.range, vector->name);
        TEST_ASSERT_EQUAL_MESSAGE(vector->invalid != 0u, sample.invalid, vector->name);
        TEST_ASSERT_EQUAL_MESSAGE(vector->fault != 0u, sample.fault, vector->name);
        TEST_ASSERT_EQUAL_HEX8_MESSAGE(vector->logic, sample.logic, vector->name);
    }
}

static void test_sample_field_readers_match_unpack(void)
{
    for (size_t i = 0u; i < PP_SAMPLE_VECTOR_COUNT; i++) {
        const pp_sample_vector_t *vector = &pp_sample_vectors[i];

        TEST_ASSERT_EQUAL_HEX16_MESSAGE(vector->adc, pp_sample_adc(vector->word), vector->name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(vector->range, pp_sample_range(vector->word), vector->name);
        TEST_ASSERT_EQUAL_MESSAGE(vector->invalid != 0u, pp_sample_is_invalid(vector->word),
                                  vector->name);
        TEST_ASSERT_EQUAL_MESSAGE(vector->fault != 0u, pp_sample_has_fault(vector->word),
                                  vector->name);
        TEST_ASSERT_EQUAL_HEX8_MESSAGE(vector->logic, pp_sample_logic(vector->word), vector->name);
    }
}

static void test_sample_fields_do_not_overlap(void)
{
    pp_sample_t only_adc = {.adc = 0xFFFFu};
    pp_sample_t only_range = {.range = 3u};
    pp_sample_t only_invalid = {.invalid = true};
    pp_sample_t only_fault = {.fault = true};
    pp_sample_t only_logic = {.logic = 0xFFu};

    uint32_t adc = pp_sample_pack(&only_adc);
    uint32_t range = pp_sample_pack(&only_range);
    uint32_t invalid = pp_sample_pack(&only_invalid);
    uint32_t fault = pp_sample_pack(&only_fault);
    uint32_t logic = pp_sample_pack(&only_logic);

    TEST_ASSERT_EQUAL_HEX32(0u, adc & range);
    TEST_ASSERT_EQUAL_HEX32(0u, (adc | range) & invalid);
    TEST_ASSERT_EQUAL_HEX32(0u, (adc | range | invalid) & fault);
    TEST_ASSERT_EQUAL_HEX32(0u, (adc | range | invalid | fault) & logic);
    TEST_ASSERT_EQUAL_HEX32(PP_SAMPLE_INVALID_BIT, invalid);
    TEST_ASSERT_EQUAL_HEX32(PP_SAMPLE_FAULT_BIT, fault);
}

static void test_sample_pack_leaves_the_reserved_bits_clear(void)
{
    pp_sample_t all = {.adc = 0xFFFFu, .range = 3u, .invalid = true, .fault = true, .logic = 0xFFu};
    uint32_t reserved = (uint32_t)PP_SAMPLE_RESERVED_MASK << PP_SAMPLE_RESERVED_SHIFT;

    TEST_ASSERT_EQUAL_HEX32(0u, pp_sample_pack(&all) & reserved);
}

static void test_sample_pack_truncates_a_range_that_does_not_fit(void)
{
    pp_sample_t sample = {.adc = 0u, .range = 0xFFu};

    uint32_t word = pp_sample_pack(&sample);

    TEST_ASSERT_EQUAL_UINT8(PP_SAMPLE_RANGE_MASK, pp_sample_range(word));
    TEST_ASSERT_FALSE(pp_sample_is_invalid(word));
    TEST_ASSERT_FALSE(pp_sample_has_fault(word));
}

static void test_sample_unpack_ignores_the_reserved_bits(void)
{
    pp_sample_t clean;
    pp_sample_t dirty;
    uint32_t word = 0xA5021234u;
    uint32_t reserved = (uint32_t)PP_SAMPLE_RESERVED_MASK << PP_SAMPLE_RESERVED_SHIFT;

    pp_sample_unpack(word, &clean);
    pp_sample_unpack(word | reserved, &dirty);

    TEST_ASSERT_EQUAL_HEX16(clean.adc, dirty.adc);
    TEST_ASSERT_EQUAL_UINT8(clean.range, dirty.range);
    TEST_ASSERT_EQUAL(clean.invalid, dirty.invalid);
    TEST_ASSERT_EQUAL(clean.fault, dirty.fault);
    TEST_ASSERT_EQUAL_HEX8(clean.logic, dirty.logic);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_sample_pack_matches_the_shared_vectors);
    RUN_TEST(test_sample_unpack_matches_the_shared_vectors);
    RUN_TEST(test_sample_field_readers_match_unpack);
    RUN_TEST(test_sample_fields_do_not_overlap);
    RUN_TEST(test_sample_pack_leaves_the_reserved_bits_clear);
    RUN_TEST(test_sample_pack_truncates_a_range_that_does_not_fit);
    RUN_TEST(test_sample_unpack_ignores_the_reserved_bits);
    return UNITY_END();
}
