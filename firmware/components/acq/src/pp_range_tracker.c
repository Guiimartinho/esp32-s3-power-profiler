#include "acq/pp_range_tracker.h"

#include "proto/pp_sample.h"

pp_status_t pp_range_tracker_init(pp_range_tracker_t *tracker, uint16_t settle_samples)
{
    if (tracker == NULL) {
        return PP_ERR_INVALID_ARG;
    }
    tracker->settle_samples = settle_samples;
    pp_range_tracker_reset(tracker);
    return PP_OK;
}

void pp_range_tracker_reset(pp_range_tracker_t *tracker)
{
    if (tracker == NULL) {
        return;
    }
    tracker->remaining = 0u;
    tracker->last_range = 0u;
    tracker->primed = false;
}

void pp_range_tracker_set_settle(pp_range_tracker_t *tracker, uint16_t settle_samples)
{
    if (tracker == NULL) {
        return;
    }
    tracker->settle_samples = settle_samples;
}

bool pp_range_tracker_update(pp_range_tracker_t *tracker, uint8_t range)
{
    if (tracker == NULL) {
        return false;
    }
    if (tracker->primed && (range != tracker->last_range)) {
        tracker->remaining = tracker->settle_samples;
    }
    tracker->primed = true;
    tracker->last_range = range;

    if (tracker->remaining == 0u) {
        return false;
    }
    tracker->remaining--;
    return true;
}

pp_status_t pp_range_tracker_apply(pp_range_tracker_t *tracker, uint32_t *words, size_t count)
{
    if ((tracker == NULL) || ((words == NULL) && (count > 0u))) {
        return PP_ERR_INVALID_ARG;
    }
    for (size_t i = 0u; i < count; i++) {
        if (pp_range_tracker_update(tracker, pp_sample_range(words[i]))) {
            words[i] |= PP_SAMPLE_INVALID_BIT;
        }
    }
    return PP_OK;
}
