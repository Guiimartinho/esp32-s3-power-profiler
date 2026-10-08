#include "unity.h"

#include <stddef.h>
#include <stdint.h>

#include "acq/pp_range_tracker.h"
#include "proto/pp_sample.h"

#define SETTLE 3u

static pp_range_tracker_t tracker;

void setUp(void)
{
    TEST_ASSERT_EQUAL(PP_OK, pp_range_tracker_init(&tracker, SETTLE));
}

void tearDown(void)
{
}

/* Feed a run of samples in one range and count how many get flagged. */
static unsigned flagged_in_run(uint8_t range, unsigned samples)
{
    unsigned flagged = 0u;
    for (unsigned i = 0u; i < samples; i++) {
        if (pp_range_tracker_update(&tracker, range)) {
            flagged++;
        }
    }
    return flagged;
}

static uint32_t word_in_range(uint8_t range, uint16_t adc)
{
    pp_sample_t sample = {.adc = adc, .range = range, .logic = 0x5Au};
    return pp_sample_pack(&sample);
}

static void test_range_tracker_init_rejects_null(void)
{
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_range_tracker_init(NULL, SETTLE));
}

static void test_range_tracker_flags_nothing_while_the_range_is_steady(void)
{
    TEST_ASSERT_EQUAL_UINT(0u, flagged_in_run(2u, 1000u));
}

static void test_range_tracker_never_flags_the_first_sample(void)
{
    /* Whatever the first range is, there is no earlier sample to differ from. */
    for (uint8_t range = 0u; range < 4u; range++) {
        pp_range_tracker_reset(&tracker);
        TEST_ASSERT_FALSE(pp_range_tracker_update(&tracker, range));
    }
}

static void test_range_tracker_flags_the_window_after_a_change(void)
{
    (void)flagged_in_run(0u, 10u);

    /* The sample that shows the new range is the first one of the window. */
    TEST_ASSERT_TRUE(pp_range_tracker_update(&tracker, 1u));
    TEST_ASSERT_TRUE(pp_range_tracker_update(&tracker, 1u));
    TEST_ASSERT_TRUE(pp_range_tracker_update(&tracker, 1u));
    TEST_ASSERT_FALSE(pp_range_tracker_update(&tracker, 1u));
    TEST_ASSERT_EQUAL_UINT(0u, flagged_in_run(1u, 100u));
}

static void test_range_tracker_flags_changes_in_both_directions(void)
{
    (void)flagged_in_run(3u, 5u);
    TEST_ASSERT_EQUAL_UINT(SETTLE, flagged_in_run(2u, 20u));
    TEST_ASSERT_EQUAL_UINT(SETTLE, flagged_in_run(3u, 20u));
    TEST_ASSERT_EQUAL_UINT(SETTLE, flagged_in_run(0u, 20u));
}

static void test_range_tracker_restarts_the_window_on_a_new_change(void)
{
    (void)flagged_in_run(0u, 5u);

    /* Two steps up, one sample apart: 0 -> 1, then 1 -> 2. */
    TEST_ASSERT_TRUE(pp_range_tracker_update(&tracker, 1u));
    TEST_ASSERT_EQUAL_UINT(SETTLE, flagged_in_run(2u, 20u));
}

static void test_range_tracker_with_no_window_flags_nothing(void)
{
    TEST_ASSERT_EQUAL(PP_OK, pp_range_tracker_init(&tracker, 0u));

    (void)flagged_in_run(0u, 5u);
    TEST_ASSERT_EQUAL_UINT(0u, flagged_in_run(3u, 20u));
}

static void test_range_tracker_reset_forgets_the_previous_range(void)
{
    (void)flagged_in_run(0u, 5u);
    TEST_ASSERT_TRUE(pp_range_tracker_update(&tracker, 2u));

    pp_range_tracker_reset(&tracker);

    /* An open window is closed, and the next sample starts from scratch. */
    TEST_ASSERT_EQUAL_UINT(0u, flagged_in_run(3u, 20u));
}

static void test_range_tracker_new_window_length_applies_to_the_next_change(void)
{
    (void)flagged_in_run(0u, 5u);
    TEST_ASSERT_TRUE(pp_range_tracker_update(&tracker, 1u));

    pp_range_tracker_set_settle(&tracker, 7u);

    /* The window that is already open keeps its length. */
    TEST_ASSERT_EQUAL_UINT(SETTLE - 1u, flagged_in_run(1u, 20u));
    TEST_ASSERT_EQUAL_UINT(7u, flagged_in_run(2u, 20u));
}

static void test_range_tracker_apply_marks_the_words_of_the_window(void)
{
    uint32_t words[8];
    for (size_t i = 0u; i < 8u; i++) {
        words[i] = word_in_range((i < 3u) ? 1u : 2u, (uint16_t)(0x1000u + i));
    }

    TEST_ASSERT_EQUAL(PP_OK, pp_range_tracker_apply(&tracker, words, 8u));

    for (size_t i = 0u; i < 8u; i++) {
        bool expected = (i >= 3u) && (i < (3u + SETTLE));
        TEST_ASSERT_EQUAL(expected, pp_sample_is_invalid(words[i]));
        /* Every other field is untouched. */
        TEST_ASSERT_EQUAL_HEX16(0x1000u + i, pp_sample_adc(words[i]));
        TEST_ASSERT_EQUAL_UINT8((i < 3u) ? 1u : 2u, pp_sample_range(words[i]));
        TEST_ASSERT_EQUAL_HEX8(0x5Au, pp_sample_logic(words[i]));
    }
}

static void test_range_tracker_apply_carries_the_window_across_blocks(void)
{
    uint32_t first[2] = {word_in_range(0u, 1u), word_in_range(3u, 2u)};
    uint32_t second[3] = {word_in_range(3u, 3u), word_in_range(3u, 4u), word_in_range(3u, 5u)};

    TEST_ASSERT_EQUAL(PP_OK, pp_range_tracker_apply(&tracker, first, 2u));
    TEST_ASSERT_EQUAL(PP_OK, pp_range_tracker_apply(&tracker, second, 3u));

    TEST_ASSERT_FALSE(pp_sample_is_invalid(first[0]));
    TEST_ASSERT_TRUE(pp_sample_is_invalid(first[1]));
    TEST_ASSERT_TRUE(pp_sample_is_invalid(second[0]));
    TEST_ASSERT_TRUE(pp_sample_is_invalid(second[1]));
    TEST_ASSERT_FALSE(pp_sample_is_invalid(second[2]));
}

static void test_range_tracker_apply_keeps_a_flag_that_is_already_set(void)
{
    uint32_t words[2] = {word_in_range(1u, 1u) | PP_SAMPLE_INVALID_BIT, word_in_range(1u, 2u)};

    TEST_ASSERT_EQUAL(PP_OK, pp_range_tracker_apply(&tracker, words, 2u));

    TEST_ASSERT_TRUE(pp_sample_is_invalid(words[0]));
    TEST_ASSERT_FALSE(pp_sample_is_invalid(words[1]));
}

static void test_range_tracker_apply_checks_its_arguments(void)
{
    uint32_t words[1] = {0u};

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_range_tracker_apply(NULL, words, 1u));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_range_tracker_apply(&tracker, NULL, 1u));
    TEST_ASSERT_EQUAL(PP_OK, pp_range_tracker_apply(&tracker, NULL, 0u));
}

static void test_range_tracker_functions_tolerate_null(void)
{
    pp_range_tracker_reset(NULL);
    pp_range_tracker_set_settle(NULL, 5u);
    TEST_ASSERT_FALSE(pp_range_tracker_update(NULL, 1u));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_range_tracker_init_rejects_null);
    RUN_TEST(test_range_tracker_flags_nothing_while_the_range_is_steady);
    RUN_TEST(test_range_tracker_never_flags_the_first_sample);
    RUN_TEST(test_range_tracker_flags_the_window_after_a_change);
    RUN_TEST(test_range_tracker_flags_changes_in_both_directions);
    RUN_TEST(test_range_tracker_restarts_the_window_on_a_new_change);
    RUN_TEST(test_range_tracker_with_no_window_flags_nothing);
    RUN_TEST(test_range_tracker_reset_forgets_the_previous_range);
    RUN_TEST(test_range_tracker_new_window_length_applies_to_the_next_change);
    RUN_TEST(test_range_tracker_apply_marks_the_words_of_the_window);
    RUN_TEST(test_range_tracker_apply_carries_the_window_across_blocks);
    RUN_TEST(test_range_tracker_apply_keeps_a_flag_that_is_already_set);
    RUN_TEST(test_range_tracker_apply_checks_its_arguments);
    RUN_TEST(test_range_tracker_functions_tolerate_null);
    return UNITY_END();
}
