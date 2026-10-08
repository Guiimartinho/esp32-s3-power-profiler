/*
 * Test double for the analog front end port.
 *
 * It records what the code under test asked for and imitates the two
 * behaviors of the hardware that matter to the logic: a latched fault keeps
 * the output switch open, and clearing the latch releases it. A test can make
 * every call fail by setting next_status.
 */
#ifndef FAKE_AFE_H
#define FAKE_AFE_H

#include <stdbool.h>
#include <stdint.h>

#include "afe/pp_afe_port.h"

typedef struct {
    /* State set through the port. */
    bool range_locked;
    uint8_t locked_range;
    pp_mode_t mode;
    bool output_enabled;
    bool fault;

    /* Call counters. */
    unsigned set_range_lock_calls;
    unsigned step_down_calls;
    unsigned set_mode_calls;
    unsigned set_output_calls;
    unsigned clear_fault_calls;

    /* Status returned by the calls that report one. */
    pp_status_t next_status;
} fake_afe_t;

/* Put the fake in the reset state of the board: automatic range, output open. */
void fake_afe_init(fake_afe_t *fake);

/* Port whose calls end in the given fake. */
pp_afe_port_t fake_afe_port(fake_afe_t *fake);

/* Imitate the hardware trip: latch the fault and open the output. */
void fake_afe_trip(fake_afe_t *fake);

#endif /* FAKE_AFE_H */
