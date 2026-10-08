#include "app/pp_fsm.h"

#include <stddef.h>
#include <stdint.h>

/*
 * The states are numbered from zero and FAULT is the last one. A state added
 * to the protocol definition stops the build at the switch in
 * pp_fsm_state_name(), which is the reminder to extend the table below.
 */
#define STATE_COUNT ((unsigned)PP_STATE_FAULT + 1u)

/* A table entry holds the next state plus one, so that zero means rejected. */
#define REJECTED 0u
#define TO(state) ((uint8_t)((unsigned)(state) + 1u))

/*
 * The whole behavior of the machine. Rows are states, columns are events, and
 * an entry that is not listed rejects the event.
 */
static const uint8_t transitions[STATE_COUNT][PP_FSM_EVENT_COUNT] = {
    [PP_STATE_BOOT] =
        {
            [PP_FSM_EVENT_BOOT_DONE] = TO(PP_STATE_SELFTEST),
            [PP_FSM_EVENT_HOST_CLOSED] = TO(PP_STATE_BOOT),
        },
    [PP_STATE_SELFTEST] =
        {
            [PP_FSM_EVENT_SELFTEST_PASSED] = TO(PP_STATE_IDLE),
            [PP_FSM_EVENT_SELFTEST_FAILED] = TO(PP_STATE_FAULT),
            [PP_FSM_EVENT_HOST_CLOSED] = TO(PP_STATE_SELFTEST),
            [PP_FSM_EVENT_FAULT_RAISED] = TO(PP_STATE_FAULT),
        },
    [PP_STATE_IDLE] =
        {
            [PP_FSM_EVENT_DUT_POWER_ON] = TO(PP_STATE_ARMED),
            [PP_FSM_EVENT_HOST_CLOSED] = TO(PP_STATE_IDLE),
            [PP_FSM_EVENT_FAULT_RAISED] = TO(PP_STATE_FAULT),
        },
    [PP_STATE_ARMED] =
        {
            [PP_FSM_EVENT_DUT_POWER_OFF] = TO(PP_STATE_IDLE),
            [PP_FSM_EVENT_START] = TO(PP_STATE_STREAMING),
            [PP_FSM_EVENT_HOST_CLOSED] = TO(PP_STATE_ARMED),
            [PP_FSM_EVENT_FAULT_RAISED] = TO(PP_STATE_FAULT),
        },
    [PP_STATE_STREAMING] =
        {
            [PP_FSM_EVENT_STOP] = TO(PP_STATE_ARMED),
            [PP_FSM_EVENT_HOST_CLOSED] = TO(PP_STATE_ARMED),
            [PP_FSM_EVENT_FAULT_RAISED] = TO(PP_STATE_FAULT),
        },
    [PP_STATE_FAULT] =
        {
            [PP_FSM_EVENT_HOST_CLOSED] = TO(PP_STATE_FAULT),
            [PP_FSM_EVENT_FAULT_RAISED] = TO(PP_STATE_FAULT),
            [PP_FSM_EVENT_FAULT_CLEARED] = TO(PP_STATE_IDLE),
        },
};

static bool state_is_valid(pp_device_state_t state)
{
    return (unsigned)state < STATE_COUNT;
}

static bool event_is_valid(pp_fsm_event_t event)
{
    return (unsigned)event < (unsigned)PP_FSM_EVENT_COUNT;
}

/* Table entry for the current state and the event, or REJECTED. */
static uint8_t lookup(const pp_fsm_t *fsm, pp_fsm_event_t event)
{
    if ((fsm == NULL) || !state_is_valid(fsm->state) || !event_is_valid(event)) {
        return REJECTED;
    }
    return transitions[fsm->state][event];
}

pp_status_t pp_fsm_init(pp_fsm_t *fsm, pp_fsm_observer_t observer, void *observer_ctx)
{
    if (fsm == NULL) {
        return PP_ERR_INVALID_ARG;
    }
    fsm->state = PP_STATE_BOOT;
    fsm->observer = observer;
    fsm->observer_ctx = observer_ctx;
    return PP_OK;
}

pp_device_state_t pp_fsm_state(const pp_fsm_t *fsm)
{
    return (fsm == NULL) ? PP_STATE_FAULT : fsm->state;
}

bool pp_fsm_accepts(const pp_fsm_t *fsm, pp_fsm_event_t event)
{
    return lookup(fsm, event) != REJECTED;
}

pp_status_t pp_fsm_dispatch(pp_fsm_t *fsm, pp_fsm_event_t event)
{
    if ((fsm == NULL) || !state_is_valid(fsm->state) || !event_is_valid(event)) {
        return PP_ERR_INVALID_ARG;
    }
    uint8_t entry = transitions[fsm->state][event];
    if (entry == REJECTED) {
        return PP_ERR_INVALID_STATE;
    }

    pp_device_state_t from = fsm->state;
    pp_device_state_t to = (pp_device_state_t)(entry - 1u);
    fsm->state = to;
    if (fsm->observer != NULL) {
        fsm->observer(fsm->observer_ctx, from, to, event);
    }
    return PP_OK;
}

const char *pp_fsm_state_name(pp_device_state_t state)
{
    switch (state) {
    case PP_STATE_BOOT:
        return "BOOT";
    case PP_STATE_SELFTEST:
        return "SELFTEST";
    case PP_STATE_IDLE:
        return "IDLE";
    case PP_STATE_ARMED:
        return "ARMED";
    case PP_STATE_STREAMING:
        return "STREAMING";
    case PP_STATE_FAULT:
        return "FAULT";
    }
    return "UNKNOWN";
}

const char *pp_fsm_event_name(pp_fsm_event_t event)
{
    switch (event) {
    case PP_FSM_EVENT_BOOT_DONE:
        return "BOOT_DONE";
    case PP_FSM_EVENT_SELFTEST_PASSED:
        return "SELFTEST_PASSED";
    case PP_FSM_EVENT_SELFTEST_FAILED:
        return "SELFTEST_FAILED";
    case PP_FSM_EVENT_DUT_POWER_ON:
        return "DUT_POWER_ON";
    case PP_FSM_EVENT_DUT_POWER_OFF:
        return "DUT_POWER_OFF";
    case PP_FSM_EVENT_START:
        return "START";
    case PP_FSM_EVENT_STOP:
        return "STOP";
    case PP_FSM_EVENT_HOST_CLOSED:
        return "HOST_CLOSED";
    case PP_FSM_EVENT_FAULT_RAISED:
        return "FAULT_RAISED";
    case PP_FSM_EVENT_FAULT_CLEARED:
        return "FAULT_CLEARED";
    case PP_FSM_EVENT_COUNT:
        break;
    }
    return "UNKNOWN";
}
