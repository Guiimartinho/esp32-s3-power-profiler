/*
 * Port to the analog front end (sections 4.2 and 4.4 of the specification).
 *
 * The hardware-independent code controls the front end only through this
 * interface. The adapter that drives the real pins implements it for the
 * board, and the tests implement it with a fake. Protection does not depend
 * on it: the over-current trip and the step up act in hardware.
 *
 * Every function receives the ctx pointer of the port as its first argument.
 */
#ifndef PP_AFE_PORT_H
#define PP_AFE_PORT_H

#include <stdbool.h>
#include <stdint.h>

#include "base/pp_status.h"
#include "proto/pp_proto_defs.h"

typedef struct {
    void *ctx; /* state of the implementation, passed back on every call */

    /*
     * Range lock. With locked true the front end holds the given range; the
     * jump up and the over-current trip stay active. With locked false the
     * range follows the current and the range argument is ignored.
     */
    pp_status_t (*set_range_lock)(void *ctx, bool locked, uint8_t range);

    /* Ask for one step down. The hardware refuses it while a step up is due. */
    pp_status_t (*step_down)(void *ctx);

    /* Select the supply of the DUT. Both paths are open during the change. */
    pp_status_t (*set_mode)(void *ctx, pp_mode_t mode);

    /* Request the output switch on or off. A latched fault keeps it open. */
    pp_status_t (*set_output)(void *ctx, bool enabled);

    /* True while the over-current latch is set. */
    bool (*fault_latched)(void *ctx);

    /* Reset the over-current latch. */
    pp_status_t (*clear_fault)(void *ctx);
} pp_afe_port_t;

#endif /* PP_AFE_PORT_H */
