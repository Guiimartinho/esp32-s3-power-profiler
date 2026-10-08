/*
 * Settling window after a range change (sections 4.5 and 6.3 of the
 * specification).
 *
 * When the range bits of a sample differ from those of the sample before it,
 * the analog chain is still settling. The tracker flags that sample and the
 * ones that follow as invalid, for a number of samples that is a calibrated
 * constant of the board. A new change inside the window restarts it.
 */
#ifndef PP_RANGE_TRACKER_H
#define PP_RANGE_TRACKER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "base/pp_status.h"

typedef struct {
    uint16_t settle_samples; /* samples flagged after a change, the first one included */
    uint16_t remaining;      /* samples of the current window still to flag */
    uint8_t last_range;      /* range of the previous sample */
    bool primed;             /* false until the first sample is seen */
} pp_range_tracker_t;

/* Prepare a tracker. A window of zero samples flags nothing. */
pp_status_t pp_range_tracker_init(pp_range_tracker_t *tracker, uint16_t settle_samples);

/*
 * Forget the previous sample, for instance when a capture starts. The first
 * sample after a reset has no predecessor and is never flagged.
 */
void pp_range_tracker_reset(pp_range_tracker_t *tracker);

/* Change the window length. Takes effect at the next range change. */
void pp_range_tracker_set_settle(pp_range_tracker_t *tracker, uint16_t settle_samples);

/* Process the range of one sample. Returns true when it must be flagged. */
bool pp_range_tracker_update(pp_range_tracker_t *tracker, uint8_t range);

/*
 * Process a block of sample words in place: read the range bits of each word
 * and set its invalid bit where needed. A bit that is already set stays set.
 */
pp_status_t pp_range_tracker_apply(pp_range_tracker_t *tracker, uint32_t *words, size_t count);

#endif /* PP_RANGE_TRACKER_H */
