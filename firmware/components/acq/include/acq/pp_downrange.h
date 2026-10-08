/*
 * Step-down rule of the automatic ranging (sections 4.4 and 6.3 of the
 * specification).
 *
 * The hardware steps up by itself. Stepping down is requested by the
 * firmware: when the ADC code stays below the threshold of the active range
 * for a number of consecutive valid samples, one step down is requested.
 *
 * After a request the rule waits. The samples that follow still show the old
 * range until the hardware has acted, and counting them again would ask for a
 * second step that the lower range may not be able to carry. Evaluation
 * resumes when the range bits change, or after a hold-off if they never do,
 * for instance because the range is locked.
 */
#ifndef PP_DOWNRANGE_H
#define PP_DOWNRANGE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "base/pp_status.h"
#include "proto/pp_proto_defs.h"

/* Default number of consecutive samples, N in section 4.4. */
#define PP_DOWNRANGE_DEFAULT_CONSECUTIVE 100u

/*
 * Default hold-off in samples. It must exceed the delay between a request and
 * the first sample taken in the new range, which is a few blocks.
 */
#define PP_DOWNRANGE_DEFAULT_HOLDOFF (4u * PP_BLOCK_SAMPLES)

typedef struct {
    /*
     * A step down is wanted while the ADC code is below threshold[range].
     * Entry 0 is unused: there is no range below the lowest one.
     */
    uint16_t threshold[PP_RANGE_COUNT];
    uint16_t consecutive; /* valid samples in a row needed for a request, at least 1 */
    uint16_t holdoff;     /* samples to wait for the range to change after a request */
} pp_downrange_config_t;

typedef struct {
    pp_downrange_config_t config;
    uint16_t run;  /* qualifying samples in a row so far */
    uint16_t wait; /* samples left in the hold-off; zero when evaluating */
    uint8_t range; /* range of the previous sample */
    bool primed;   /* false until the first sample is seen */
} pp_downrange_t;

/* Prepare the rule. Returns PP_ERR_INVALID_ARG when consecutive is zero. */
pp_status_t pp_downrange_init(pp_downrange_t *rule, const pp_downrange_config_t *config);

/* Start over, for instance when a capture starts. The configuration is kept. */
void pp_downrange_reset(pp_downrange_t *rule);

/* Change N (command SET_DOWN_N). Returns PP_ERR_INVALID_ARG for zero. */
pp_status_t pp_downrange_set_consecutive(pp_downrange_t *rule, uint16_t consecutive);

/* Process one sample word. Returns true when a step down must be requested. */
bool pp_downrange_update(pp_downrange_t *rule, uint32_t word);

/*
 * Process a block of sample words. Returns true when a step down must be
 * requested after this block.
 */
bool pp_downrange_process(pp_downrange_t *rule, const uint32_t *words, size_t count);

#endif /* PP_DOWNRANGE_H */
