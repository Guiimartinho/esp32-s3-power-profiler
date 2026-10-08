#include "unity.h"

#include <stddef.h>
#include <stdint.h>

#include "acq/pp_downrange.h"
#include "proto/pp_sample.h"

#define CONSECUTIVE 5u
#define HOLDOFF 8u
#define LOW 100u  /* an ADC code below every threshold */
#define HIGH 900u /* an ADC code above every threshold */

static const pp_downrange_config_t config = {
    .threshold = {0u, 200u, 300u, 400u},
    .consecutive = CONSECUTIVE,
    .holdoff = HOLDOFF,
};

static pp_downrange_t rule;

void setUp(void)
{
    TEST_ASSERT_EQUAL(PP_OK, pp_downrange_init(&rule, &config));
}

void tearDown(void)
{
}

static uint32_t word(uint8_t range, uint16_t adc)
{
    pp_sample_t sample = {.adc = adc, .range = range};
    return pp_sample_pack(&sample);
}

/* Feed the same sample repeatedly and count the requests. */
static unsigned requests_in_run(uint8_t range, uint16_t adc, unsigned samples)
{
    unsigned requests = 0u;
    for (unsigned i = 0u; i < samples; i++) {
        if (pp_downrange_update(&rule, word(range, adc))) {
            requests++;
        }
    }
    return requests;
}

/* --- Initialization ---------------------------------------------------- */

static void test_downrange_defaults_follow_the_specification(void)
{
    TEST_ASSERT_EQUAL_UINT(100u, PP_DOWNRANGE_DEFAULT_CONSECUTIVE);
    TEST_ASSERT_TRUE(PP_DOWNRANGE_DEFAULT_HOLDOFF > PP_BLOCK_SAMPLES);
}

static void test_downrange_init_checks_its_arguments(void)
{
    pp_downrange_config_t zero_n = config;
    zero_n.consecutive = 0u;

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_downrange_init(NULL, &config));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_downrange_init(&rule, NULL));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_downrange_init(&rule, &zero_n));
}

/* --- The rule ---------------------------------------------------------- */

static void test_downrange_requests_after_n_samples_below_the_threshold(void)
{
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(2u, LOW, CONSECUTIVE - 1u));
    TEST_ASSERT_TRUE(pp_downrange_update(&rule, word(2u, LOW)));
}

static void test_downrange_never_requests_from_the_lowest_range(void)
{
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(0u, 0u, 1000u));
}

static void test_downrange_does_not_request_above_the_threshold(void)
{
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(3u, HIGH, 1000u));
}

static void test_downrange_threshold_itself_does_not_count(void)
{
    /* "Below" is strict: a code equal to the threshold keeps the range. */
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(1u, 200u, 1000u));
    TEST_ASSERT_EQUAL_UINT(1u, requests_in_run(1u, 199u, CONSECUTIVE));
}

static void test_downrange_uses_the_threshold_of_the_active_range(void)
{
    /* 250 is below the threshold of range 2 and above the one of range 1. */
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(1u, 250u, 100u));
    TEST_ASSERT_EQUAL_UINT(1u, requests_in_run(2u, 250u, CONSECUTIVE));
}

static void test_downrange_one_sample_above_restarts_the_count(void)
{
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(3u, LOW, CONSECUTIVE - 1u));
    TEST_ASSERT_FALSE(pp_downrange_update(&rule, word(3u, HIGH)));

    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(3u, LOW, CONSECUTIVE - 1u));
    TEST_ASSERT_TRUE(pp_downrange_update(&rule, word(3u, LOW)));
}

static void test_downrange_an_invalid_sample_restarts_the_count(void)
{
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(3u, LOW, CONSECUTIVE - 1u));
    TEST_ASSERT_FALSE(pp_downrange_update(&rule, word(3u, LOW) | PP_SAMPLE_INVALID_BIT));

    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(3u, LOW, CONSECUTIVE - 1u));
    TEST_ASSERT_TRUE(pp_downrange_update(&rule, word(3u, LOW)));
}

static void test_downrange_a_range_change_restarts_the_count(void)
{
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(3u, LOW, CONSECUTIVE - 1u));

    /* The hardware stepped up or down by itself: count again from one. */
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(2u, LOW, CONSECUTIVE - 1u));
    TEST_ASSERT_TRUE(pp_downrange_update(&rule, word(2u, LOW)));
}

/* --- Hold-off ---------------------------------------------------------- */

static void test_downrange_waits_for_the_range_to_change_after_a_request(void)
{
    TEST_ASSERT_EQUAL_UINT(1u, requests_in_run(3u, LOW, CONSECUTIVE));

    /* The old range is still reported: nothing more is requested. */
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(3u, LOW, HOLDOFF));
}

static void test_downrange_resumes_at_once_when_the_range_changes(void)
{
    TEST_ASSERT_EQUAL_UINT(1u, requests_in_run(3u, LOW, CONSECUTIVE));
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(3u, LOW, 2u));

    /* The step happened. The count for the new range starts immediately. */
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(2u, LOW, CONSECUTIVE - 1u));
    TEST_ASSERT_TRUE(pp_downrange_update(&rule, word(2u, LOW)));
}

static void test_downrange_requests_again_when_the_holdoff_runs_out(void)
{
    TEST_ASSERT_EQUAL_UINT(1u, requests_in_run(3u, LOW, CONSECUTIVE));

    /* The range never changed, for instance because it is locked. */
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(3u, LOW, HOLDOFF + CONSECUTIVE - 1u));
    TEST_ASSERT_TRUE(pp_downrange_update(&rule, word(3u, LOW)));
}

static void test_downrange_without_holdoff_requests_every_n_samples(void)
{
    pp_downrange_config_t no_wait = config;
    no_wait.holdoff = 0u;
    TEST_ASSERT_EQUAL(PP_OK, pp_downrange_init(&rule, &no_wait));

    TEST_ASSERT_EQUAL_UINT(4u, requests_in_run(3u, LOW, 4u * CONSECUTIVE));
}

/* --- Configuration at run time ----------------------------------------- */

static void test_downrange_set_consecutive_changes_n(void)
{
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(3u, LOW, CONSECUTIVE - 1u));

    TEST_ASSERT_EQUAL(PP_OK, pp_downrange_set_consecutive(&rule, 2u));

    /* The samples counted so far are dropped with the old CONSECUTIVE. */
    TEST_ASSERT_FALSE(pp_downrange_update(&rule, word(3u, LOW)));
    TEST_ASSERT_TRUE(pp_downrange_update(&rule, word(3u, LOW)));
}

static void test_downrange_set_consecutive_checks_its_arguments(void)
{
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_downrange_set_consecutive(NULL, 3u));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_downrange_set_consecutive(&rule, 0u));
    TEST_ASSERT_EQUAL_UINT16(CONSECUTIVE, rule.config.consecutive);
}

static void test_downrange_n_of_one_requests_on_the_first_low_sample(void)
{
    TEST_ASSERT_EQUAL(PP_OK, pp_downrange_set_consecutive(&rule, 1u));

    TEST_ASSERT_TRUE(pp_downrange_update(&rule, word(1u, LOW)));
}

static void test_downrange_reset_starts_over(void)
{
    TEST_ASSERT_EQUAL_UINT(1u, requests_in_run(3u, LOW, CONSECUTIVE));

    pp_downrange_reset(&rule);

    /* No hold-off is pending any more, and the count starts from one. */
    TEST_ASSERT_EQUAL_UINT(0u, requests_in_run(3u, LOW, CONSECUTIVE - 1u));
    TEST_ASSERT_TRUE(pp_downrange_update(&rule, word(3u, LOW)));
}

/* --- Blocks ------------------------------------------------------------ */

static void test_downrange_process_reports_a_request_inside_the_block(void)
{
    uint32_t quiet[CONSECUTIVE - 1u];
    uint32_t block[CONSECUTIVE + 3u];
    for (size_t i = 0u; i < (CONSECUTIVE - 1u); i++) {
        quiet[i] = word(3u, LOW);
    }
    for (size_t i = 0u; i < (CONSECUTIVE + 3u); i++) {
        block[i] = word(3u, LOW);
    }

    TEST_ASSERT_FALSE(pp_downrange_process(&rule, quiet, CONSECUTIVE - 1u));
    pp_downrange_reset(&rule);
    TEST_ASSERT_TRUE(pp_downrange_process(&rule, block, CONSECUTIVE + 3u));
    /* The next block is still in the old range: the rule is waiting. */
    TEST_ASSERT_FALSE(pp_downrange_process(&rule, quiet, CONSECUTIVE - 1u));
}

static void test_downrange_functions_tolerate_null(void)
{
    const uint32_t words[1] = {0u};

    pp_downrange_reset(NULL);
    TEST_ASSERT_FALSE(pp_downrange_update(NULL, 0u));
    TEST_ASSERT_FALSE(pp_downrange_process(NULL, words, 1u));
    TEST_ASSERT_FALSE(pp_downrange_process(&rule, NULL, 1u));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_downrange_defaults_follow_the_specification);
    RUN_TEST(test_downrange_init_checks_its_arguments);
    RUN_TEST(test_downrange_requests_after_n_samples_below_the_threshold);
    RUN_TEST(test_downrange_never_requests_from_the_lowest_range);
    RUN_TEST(test_downrange_does_not_request_above_the_threshold);
    RUN_TEST(test_downrange_threshold_itself_does_not_count);
    RUN_TEST(test_downrange_uses_the_threshold_of_the_active_range);
    RUN_TEST(test_downrange_one_sample_above_restarts_the_count);
    RUN_TEST(test_downrange_an_invalid_sample_restarts_the_count);
    RUN_TEST(test_downrange_a_range_change_restarts_the_count);
    RUN_TEST(test_downrange_waits_for_the_range_to_change_after_a_request);
    RUN_TEST(test_downrange_resumes_at_once_when_the_range_changes);
    RUN_TEST(test_downrange_requests_again_when_the_holdoff_runs_out);
    RUN_TEST(test_downrange_without_holdoff_requests_every_n_samples);
    RUN_TEST(test_downrange_set_consecutive_changes_n);
    RUN_TEST(test_downrange_set_consecutive_checks_its_arguments);
    RUN_TEST(test_downrange_n_of_one_requests_on_the_first_low_sample);
    RUN_TEST(test_downrange_reset_starts_over);
    RUN_TEST(test_downrange_process_reports_a_request_inside_the_block);
    RUN_TEST(test_downrange_functions_tolerate_null);
    return UNITY_END();
}
