/*
 * The analog front end port, exercised through its test double.
 *
 * The port has no code of its own. These tests pin down what callers may
 * rely on, and show how hardware-independent code is tested against the fake
 * instead of the board.
 */
#include "unity.h"

#include <stddef.h>
#include <stdint.h>

#include "acq/pp_downrange.h"
#include "afe/pp_afe_port.h"
#include "fake_afe.h"
#include "proto/pp_sample.h"

static fake_afe_t fake;
static pp_afe_port_t port;

void setUp(void)
{
    fake_afe_init(&fake);
    port = fake_afe_port(&fake);
}

void tearDown(void)
{
}

static void test_afe_port_starts_in_the_reset_state_of_the_board(void)
{
    TEST_ASSERT_FALSE(fake.range_locked);
    TEST_ASSERT_FALSE(fake.output_enabled);
    TEST_ASSERT_FALSE(port.fault_latched(port.ctx));
}

static void test_afe_port_locks_and_releases_the_range(void)
{
    TEST_ASSERT_EQUAL(PP_OK, port.set_range_lock(port.ctx, true, 2u));
    TEST_ASSERT_TRUE(fake.range_locked);
    TEST_ASSERT_EQUAL_UINT8(2u, fake.locked_range);

    TEST_ASSERT_EQUAL(PP_OK, port.set_range_lock(port.ctx, false, 0u));
    TEST_ASSERT_FALSE(fake.range_locked);
    TEST_ASSERT_EQUAL_UINT(2u, fake.set_range_lock_calls);
}

static void test_afe_port_selects_the_mode(void)
{
    TEST_ASSERT_EQUAL(PP_OK, port.set_mode(port.ctx, PP_MODE_SOURCE_METER));

    TEST_ASSERT_EQUAL(PP_MODE_SOURCE_METER, fake.mode);
    TEST_ASSERT_EQUAL_UINT(1u, fake.set_mode_calls);
}

static void test_afe_port_switches_the_output(void)
{
    TEST_ASSERT_EQUAL(PP_OK, port.set_output(port.ctx, true));
    TEST_ASSERT_TRUE(fake.output_enabled);

    TEST_ASSERT_EQUAL(PP_OK, port.set_output(port.ctx, false));
    TEST_ASSERT_FALSE(fake.output_enabled);
}

static void test_afe_port_fault_keeps_the_output_open_until_cleared(void)
{
    TEST_ASSERT_EQUAL(PP_OK, port.set_output(port.ctx, true));

    fake_afe_trip(&fake);

    TEST_ASSERT_TRUE(port.fault_latched(port.ctx));
    TEST_ASSERT_FALSE(fake.output_enabled);
    /* A request cannot override the latch. */
    TEST_ASSERT_EQUAL(PP_OK, port.set_output(port.ctx, true));
    TEST_ASSERT_FALSE(fake.output_enabled);

    TEST_ASSERT_EQUAL(PP_OK, port.clear_fault(port.ctx));
    TEST_ASSERT_FALSE(port.fault_latched(port.ctx));
    TEST_ASSERT_EQUAL(PP_OK, port.set_output(port.ctx, true));
    TEST_ASSERT_TRUE(fake.output_enabled);
}

static void test_afe_port_reports_a_failing_adapter(void)
{
    fake.next_status = PP_ERR_INVALID_STATE;

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_STATE, port.set_range_lock(port.ctx, true, 1u));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_STATE, port.step_down(port.ctx));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_STATE, port.set_mode(port.ctx, PP_MODE_SOURCE_METER));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_STATE, port.set_output(port.ctx, true));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_STATE, port.clear_fault(port.ctx));

    /* Nothing changed. */
    TEST_ASSERT_FALSE(fake.range_locked);
    TEST_ASSERT_EQUAL(PP_MODE_AMPERE_METER, fake.mode);
    TEST_ASSERT_FALSE(fake.output_enabled);
}

/*
 * The step-down rule and the port together, the way the acquisition task
 * will use them: one pulse per block in which the rule fires.
 */
static void test_afe_port_gets_one_step_down_per_request_of_the_rule(void)
{
    const pp_downrange_config_t config = {
        .threshold = {0u, 200u, 200u, 200u},
        .consecutive = 4u,
        .holdoff = 16u,
    };
    pp_downrange_t rule;
    uint32_t block[8];
    pp_sample_t low = {.adc = 50u, .range = 3u};
    for (size_t i = 0u; i < 8u; i++) {
        block[i] = pp_sample_pack(&low);
    }
    TEST_ASSERT_EQUAL(PP_OK, pp_downrange_init(&rule, &config));

    for (unsigned blocks = 0u; blocks < 2u; blocks++) {
        if (pp_downrange_process(&rule, block, 8u)) {
            TEST_ASSERT_EQUAL(PP_OK, port.step_down(port.ctx));
        }
    }

    /* The second block is still inside the hold-off: no second pulse. */
    TEST_ASSERT_EQUAL_UINT(1u, fake.step_down_calls);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_afe_port_starts_in_the_reset_state_of_the_board);
    RUN_TEST(test_afe_port_locks_and_releases_the_range);
    RUN_TEST(test_afe_port_selects_the_mode);
    RUN_TEST(test_afe_port_switches_the_output);
    RUN_TEST(test_afe_port_fault_keeps_the_output_open_until_cleared);
    RUN_TEST(test_afe_port_reports_a_failing_adapter);
    RUN_TEST(test_afe_port_gets_one_step_down_per_request_of_the_rule);
    return UNITY_END();
}
