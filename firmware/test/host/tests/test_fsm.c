#include "unity.h"

#include <stddef.h>
#include <string.h>

#include "app/pp_fsm.h"

#define STATE_COUNT 6u
#define NO (-1) /* the event is rejected */

/*
 * Section 6.4 of the specification as a table: the state that follows each
 * event in each state. It is written independently of the implementation.
 */
static const int expected[STATE_COUNT][PP_FSM_EVENT_COUNT] = {
    /*                 BOOT_DONE        PASSED          FAILED           POWER_ON        POWER_OFF
                       START            STOP            HOST_CLOSED      FAULT_RAISED FAULT_CLEARED
     */
    [PP_STATE_BOOT] = {PP_STATE_SELFTEST, NO, NO, NO, NO, NO, NO, PP_STATE_BOOT, NO, NO},
    [PP_STATE_SELFTEST] = {NO, PP_STATE_IDLE, PP_STATE_FAULT, NO, NO, NO, NO, PP_STATE_SELFTEST,
                           PP_STATE_FAULT, NO},
    [PP_STATE_IDLE] = {NO, NO, NO, PP_STATE_ARMED, NO, NO, NO, PP_STATE_IDLE, PP_STATE_FAULT, NO},
    [PP_STATE_ARMED] = {NO, NO, NO, NO, PP_STATE_IDLE, PP_STATE_STREAMING, NO, PP_STATE_ARMED,
                        PP_STATE_FAULT, NO},
    [PP_STATE_STREAMING] = {NO, NO, NO, NO, NO, NO, PP_STATE_ARMED, PP_STATE_ARMED, PP_STATE_FAULT,
                            NO},
    [PP_STATE_FAULT] = {NO, NO, NO, NO, NO, NO, NO, PP_STATE_FAULT, PP_STATE_FAULT, PP_STATE_IDLE},
};

/* --- Observer that records what it is told ------------------------------ */

typedef struct {
    unsigned calls;
    pp_device_state_t from;
    pp_device_state_t to;
    pp_fsm_event_t event;
} recorder_t;

static void record(void *ctx, pp_device_state_t from, pp_device_state_t to, pp_fsm_event_t event)
{
    recorder_t *recorder = ctx;
    recorder->calls++;
    recorder->from = from;
    recorder->to = to;
    recorder->event = event;
}

static pp_fsm_t fsm;
static recorder_t recorder;

void setUp(void)
{
    memset(&recorder, 0, sizeof(recorder));
    TEST_ASSERT_EQUAL(PP_OK, pp_fsm_init(&fsm, record, &recorder));
}

void tearDown(void)
{
}

static void dispatch_ok(pp_fsm_event_t event, pp_device_state_t next)
{
    TEST_ASSERT_EQUAL_MESSAGE(PP_OK, pp_fsm_dispatch(&fsm, event), pp_fsm_event_name(event));
    TEST_ASSERT_EQUAL_MESSAGE(next, pp_fsm_state(&fsm), pp_fsm_event_name(event));
}

/* --- Initialization ---------------------------------------------------- */

static void test_fsm_starts_in_boot(void)
{
    TEST_ASSERT_EQUAL(PP_STATE_BOOT, pp_fsm_state(&fsm));
    TEST_ASSERT_EQUAL_UINT(0u, recorder.calls);
}

static void test_fsm_init_rejects_null(void)
{
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_fsm_init(NULL, NULL, NULL));
}

static void test_fsm_works_without_an_observer(void)
{
    pp_fsm_t plain;

    TEST_ASSERT_EQUAL(PP_OK, pp_fsm_init(&plain, NULL, NULL));
    TEST_ASSERT_EQUAL(PP_OK, pp_fsm_dispatch(&plain, PP_FSM_EVENT_BOOT_DONE));
    TEST_ASSERT_EQUAL(PP_STATE_SELFTEST, pp_fsm_state(&plain));
}

/* --- Scenarios --------------------------------------------------------- */

static void test_fsm_normal_capture_session(void)
{
    dispatch_ok(PP_FSM_EVENT_BOOT_DONE, PP_STATE_SELFTEST);
    dispatch_ok(PP_FSM_EVENT_SELFTEST_PASSED, PP_STATE_IDLE);
    dispatch_ok(PP_FSM_EVENT_DUT_POWER_ON, PP_STATE_ARMED);
    dispatch_ok(PP_FSM_EVENT_START, PP_STATE_STREAMING);
    dispatch_ok(PP_FSM_EVENT_STOP, PP_STATE_ARMED);
    dispatch_ok(PP_FSM_EVENT_DUT_POWER_OFF, PP_STATE_IDLE);
}

static void test_fsm_failed_selftest_ends_in_fault(void)
{
    dispatch_ok(PP_FSM_EVENT_BOOT_DONE, PP_STATE_SELFTEST);
    dispatch_ok(PP_FSM_EVENT_SELFTEST_FAILED, PP_STATE_FAULT);
    dispatch_ok(PP_FSM_EVENT_FAULT_CLEARED, PP_STATE_IDLE);
}

static void test_fsm_streaming_stops_when_the_host_closes_the_port(void)
{
    dispatch_ok(PP_FSM_EVENT_BOOT_DONE, PP_STATE_SELFTEST);
    dispatch_ok(PP_FSM_EVENT_SELFTEST_PASSED, PP_STATE_IDLE);
    dispatch_ok(PP_FSM_EVENT_DUT_POWER_ON, PP_STATE_ARMED);
    dispatch_ok(PP_FSM_EVENT_START, PP_STATE_STREAMING);

    dispatch_ok(PP_FSM_EVENT_HOST_CLOSED, PP_STATE_ARMED);
}

static void test_fsm_fault_while_streaming_needs_a_clear_to_leave(void)
{
    dispatch_ok(PP_FSM_EVENT_BOOT_DONE, PP_STATE_SELFTEST);
    dispatch_ok(PP_FSM_EVENT_SELFTEST_PASSED, PP_STATE_IDLE);
    dispatch_ok(PP_FSM_EVENT_DUT_POWER_ON, PP_STATE_ARMED);
    dispatch_ok(PP_FSM_EVENT_START, PP_STATE_STREAMING);
    dispatch_ok(PP_FSM_EVENT_FAULT_RAISED, PP_STATE_FAULT);

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_STATE, pp_fsm_dispatch(&fsm, PP_FSM_EVENT_START));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_STATE, pp_fsm_dispatch(&fsm, PP_FSM_EVENT_DUT_POWER_ON));
    TEST_ASSERT_EQUAL(PP_STATE_FAULT, pp_fsm_state(&fsm));

    dispatch_ok(PP_FSM_EVENT_FAULT_CLEARED, PP_STATE_IDLE);
}

/* --- The whole table --------------------------------------------------- */

static void test_fsm_every_state_and_event_follows_the_specification(void)
{
    for (unsigned state = 0u; state < STATE_COUNT; state++) {
        for (unsigned event = 0u; event < (unsigned)PP_FSM_EVENT_COUNT; event++) {
            const char *name = pp_fsm_event_name((pp_fsm_event_t)event);
            int next = expected[state][event];
            fsm.state = (pp_device_state_t)state;
            recorder.calls = 0u;

            bool accepts = pp_fsm_accepts(&fsm, (pp_fsm_event_t)event);
            pp_status_t status = pp_fsm_dispatch(&fsm, (pp_fsm_event_t)event);

            if (next == NO) {
                TEST_ASSERT_FALSE_MESSAGE(accepts, name);
                TEST_ASSERT_EQUAL_MESSAGE(PP_ERR_INVALID_STATE, status, name);
                TEST_ASSERT_EQUAL_MESSAGE(state, pp_fsm_state(&fsm), name);
                TEST_ASSERT_EQUAL_UINT_MESSAGE(0u, recorder.calls, name);
            } else {
                TEST_ASSERT_TRUE_MESSAGE(accepts, name);
                TEST_ASSERT_EQUAL_MESSAGE(PP_OK, status, name);
                TEST_ASSERT_EQUAL_MESSAGE(next, pp_fsm_state(&fsm), name);
                TEST_ASSERT_EQUAL_UINT_MESSAGE(1u, recorder.calls, name);
            }
        }
    }
}

/* --- Observer ---------------------------------------------------------- */

static void test_fsm_observer_is_told_about_a_transition(void)
{
    dispatch_ok(PP_FSM_EVENT_BOOT_DONE, PP_STATE_SELFTEST);

    TEST_ASSERT_EQUAL_UINT(1u, recorder.calls);
    TEST_ASSERT_EQUAL(PP_STATE_BOOT, recorder.from);
    TEST_ASSERT_EQUAL(PP_STATE_SELFTEST, recorder.to);
    TEST_ASSERT_EQUAL(PP_FSM_EVENT_BOOT_DONE, recorder.event);
}

static void test_fsm_observer_is_told_about_an_event_that_changes_nothing(void)
{
    fsm.state = PP_STATE_FAULT;

    /* A second fault while one is latched: allowed, and worth reporting. */
    dispatch_ok(PP_FSM_EVENT_FAULT_RAISED, PP_STATE_FAULT);

    TEST_ASSERT_EQUAL_UINT(1u, recorder.calls);
    TEST_ASSERT_EQUAL(PP_STATE_FAULT, recorder.from);
    TEST_ASSERT_EQUAL(PP_STATE_FAULT, recorder.to);
}

static void test_fsm_observer_is_not_told_about_a_rejected_event(void)
{
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_STATE, pp_fsm_dispatch(&fsm, PP_FSM_EVENT_START));

    TEST_ASSERT_EQUAL_UINT(0u, recorder.calls);
    TEST_ASSERT_EQUAL(PP_STATE_BOOT, pp_fsm_state(&fsm));
}

/* --- Argument checks --------------------------------------------------- */

static void test_fsm_rejects_events_outside_the_enumeration(void)
{
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_fsm_dispatch(&fsm, PP_FSM_EVENT_COUNT));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_fsm_dispatch(&fsm, (pp_fsm_event_t)1000));
    TEST_ASSERT_FALSE(pp_fsm_accepts(&fsm, PP_FSM_EVENT_COUNT));
    TEST_ASSERT_EQUAL(PP_STATE_BOOT, pp_fsm_state(&fsm));
}

static void test_fsm_rejects_a_corrupted_state(void)
{
    fsm.state = (pp_device_state_t)STATE_COUNT;

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_fsm_dispatch(&fsm, PP_FSM_EVENT_HOST_CLOSED));
    TEST_ASSERT_FALSE(pp_fsm_accepts(&fsm, PP_FSM_EVENT_HOST_CLOSED));
}

static void test_fsm_functions_tolerate_null(void)
{
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_fsm_dispatch(NULL, PP_FSM_EVENT_BOOT_DONE));
    TEST_ASSERT_FALSE(pp_fsm_accepts(NULL, PP_FSM_EVENT_BOOT_DONE));
    /* Without a machine the safe answer is the state that allows nothing. */
    TEST_ASSERT_EQUAL(PP_STATE_FAULT, pp_fsm_state(NULL));
}

/* --- Names ------------------------------------------------------------- */

static void test_fsm_state_names(void)
{
    TEST_ASSERT_EQUAL_STRING("BOOT", pp_fsm_state_name(PP_STATE_BOOT));
    TEST_ASSERT_EQUAL_STRING("SELFTEST", pp_fsm_state_name(PP_STATE_SELFTEST));
    TEST_ASSERT_EQUAL_STRING("IDLE", pp_fsm_state_name(PP_STATE_IDLE));
    TEST_ASSERT_EQUAL_STRING("ARMED", pp_fsm_state_name(PP_STATE_ARMED));
    TEST_ASSERT_EQUAL_STRING("STREAMING", pp_fsm_state_name(PP_STATE_STREAMING));
    TEST_ASSERT_EQUAL_STRING("FAULT", pp_fsm_state_name(PP_STATE_FAULT));
    TEST_ASSERT_EQUAL_STRING("UNKNOWN", pp_fsm_state_name((pp_device_state_t)STATE_COUNT));
}

static void test_fsm_event_names(void)
{
    TEST_ASSERT_EQUAL_STRING("BOOT_DONE", pp_fsm_event_name(PP_FSM_EVENT_BOOT_DONE));
    TEST_ASSERT_EQUAL_STRING("SELFTEST_PASSED", pp_fsm_event_name(PP_FSM_EVENT_SELFTEST_PASSED));
    TEST_ASSERT_EQUAL_STRING("SELFTEST_FAILED", pp_fsm_event_name(PP_FSM_EVENT_SELFTEST_FAILED));
    TEST_ASSERT_EQUAL_STRING("DUT_POWER_ON", pp_fsm_event_name(PP_FSM_EVENT_DUT_POWER_ON));
    TEST_ASSERT_EQUAL_STRING("DUT_POWER_OFF", pp_fsm_event_name(PP_FSM_EVENT_DUT_POWER_OFF));
    TEST_ASSERT_EQUAL_STRING("START", pp_fsm_event_name(PP_FSM_EVENT_START));
    TEST_ASSERT_EQUAL_STRING("STOP", pp_fsm_event_name(PP_FSM_EVENT_STOP));
    TEST_ASSERT_EQUAL_STRING("HOST_CLOSED", pp_fsm_event_name(PP_FSM_EVENT_HOST_CLOSED));
    TEST_ASSERT_EQUAL_STRING("FAULT_RAISED", pp_fsm_event_name(PP_FSM_EVENT_FAULT_RAISED));
    TEST_ASSERT_EQUAL_STRING("FAULT_CLEARED", pp_fsm_event_name(PP_FSM_EVENT_FAULT_CLEARED));
    TEST_ASSERT_EQUAL_STRING("UNKNOWN", pp_fsm_event_name(PP_FSM_EVENT_COUNT));
    TEST_ASSERT_EQUAL_STRING("UNKNOWN", pp_fsm_event_name((pp_fsm_event_t)1000));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_fsm_starts_in_boot);
    RUN_TEST(test_fsm_init_rejects_null);
    RUN_TEST(test_fsm_works_without_an_observer);
    RUN_TEST(test_fsm_normal_capture_session);
    RUN_TEST(test_fsm_failed_selftest_ends_in_fault);
    RUN_TEST(test_fsm_streaming_stops_when_the_host_closes_the_port);
    RUN_TEST(test_fsm_fault_while_streaming_needs_a_clear_to_leave);
    RUN_TEST(test_fsm_every_state_and_event_follows_the_specification);
    RUN_TEST(test_fsm_observer_is_told_about_a_transition);
    RUN_TEST(test_fsm_observer_is_told_about_an_event_that_changes_nothing);
    RUN_TEST(test_fsm_observer_is_not_told_about_a_rejected_event);
    RUN_TEST(test_fsm_rejects_events_outside_the_enumeration);
    RUN_TEST(test_fsm_rejects_a_corrupted_state);
    RUN_TEST(test_fsm_functions_tolerate_null);
    RUN_TEST(test_fsm_state_names);
    RUN_TEST(test_fsm_event_names);
    return UNITY_END();
}
