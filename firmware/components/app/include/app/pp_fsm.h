/*
 * Device state machine (section 6.4 of the specification).
 *
 *     BOOT -> SELFTEST -> IDLE <-> ARMED <-> STREAMING
 *                           ^        |           |
 *                           +----- FAULT <-------+
 *
 * The machine only decides which state follows an event. It touches no
 * hardware: an observer is told about every accepted event and performs the
 * actions that belong to the new state, such as opening the output switch on
 * entry to FAULT. An event that the current state does not allow is rejected
 * with PP_ERR_INVALID_STATE and changes nothing.
 *
 * The states are the ones of the wire protocol, so the state reported to the
 * host needs no translation.
 */
#ifndef PP_FSM_H
#define PP_FSM_H

#include <stdbool.h>

#include "base/pp_status.h"
#include "proto/pp_proto_defs.h"

typedef enum {
    PP_FSM_EVENT_BOOT_DONE = 0,   /* start-up finished, the self-test begins */
    PP_FSM_EVENT_SELFTEST_PASSED, /* the self-test found no problem */
    PP_FSM_EVENT_SELFTEST_FAILED, /* the self-test found a problem */
    PP_FSM_EVENT_DUT_POWER_ON,    /* command DUT_POWER on */
    PP_FSM_EVENT_DUT_POWER_OFF,   /* command DUT_POWER off */
    PP_FSM_EVENT_START,           /* command START */
    PP_FSM_EVENT_STOP,            /* command STOP */
    PP_FSM_EVENT_HOST_CLOSED,     /* the host closed the port */
    PP_FSM_EVENT_FAULT_RAISED,    /* over-current trip, power limit or thermal */
    PP_FSM_EVENT_FAULT_CLEARED,   /* command CLEAR_FAULT */
    PP_FSM_EVENT_COUNT,
} pp_fsm_event_t;

/*
 * Called after every accepted event, with the state before and after it. The
 * two are equal when the event is allowed but changes nothing.
 */
typedef void (*pp_fsm_observer_t)(void *ctx, pp_device_state_t from, pp_device_state_t to,
                                  pp_fsm_event_t event);

typedef struct {
    pp_device_state_t state;
    pp_fsm_observer_t observer; /* may be NULL */
    void *observer_ctx;
} pp_fsm_t;

/* Prepare a machine in the BOOT state. The observer is optional. */
pp_status_t pp_fsm_init(pp_fsm_t *fsm, pp_fsm_observer_t observer, void *observer_ctx);

/* Current state. Returns PP_STATE_FAULT for a NULL machine. */
pp_device_state_t pp_fsm_state(const pp_fsm_t *fsm);

/* True when the current state allows the event. */
bool pp_fsm_accepts(const pp_fsm_t *fsm, pp_fsm_event_t event);

/*
 * Apply an event. Returns PP_ERR_INVALID_STATE when the current state does
 * not allow it and PP_ERR_INVALID_ARG for a NULL machine, an unknown event or
 * a corrupted state.
 */
pp_status_t pp_fsm_dispatch(pp_fsm_t *fsm, pp_fsm_event_t event);

/* Names for logs. Never return NULL. */
const char *pp_fsm_state_name(pp_device_state_t state);
const char *pp_fsm_event_name(pp_fsm_event_t event);

#endif /* PP_FSM_H */
