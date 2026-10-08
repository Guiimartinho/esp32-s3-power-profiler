#include "acq/pp_downrange.h"

#include "proto/pp_sample.h"

_Static_assert((PP_SAMPLE_RANGE_MASK + 1u) == PP_RANGE_COUNT,
               "the range field must index the threshold table exactly");

pp_status_t pp_downrange_init(pp_downrange_t *rule, const pp_downrange_config_t *config)
{
    if ((rule == NULL) || (config == NULL) || (config->consecutive == 0u)) {
        return PP_ERR_INVALID_ARG;
    }
    rule->config = *config;
    pp_downrange_reset(rule);
    return PP_OK;
}

void pp_downrange_reset(pp_downrange_t *rule)
{
    if (rule == NULL) {
        return;
    }
    rule->run = 0u;
    rule->wait = 0u;
    rule->range = 0u;
    rule->primed = false;
}

pp_status_t pp_downrange_set_consecutive(pp_downrange_t *rule, uint16_t consecutive)
{
    if ((rule == NULL) || (consecutive == 0u)) {
        return PP_ERR_INVALID_ARG;
    }
    rule->config.consecutive = consecutive;
    rule->run = 0u;
    return PP_OK;
}

bool pp_downrange_update(pp_downrange_t *rule, uint32_t word)
{
    if (rule == NULL) {
        return false;
    }

    uint8_t range = pp_sample_range(word);
    if (!rule->primed || (range != rule->range)) {
        /* A new range starts a new count and ends any hold-off. */
        rule->primed = true;
        rule->range = range;
        rule->run = 0u;
        rule->wait = 0u;
    }

    if (rule->wait > 0u) {
        rule->wait--;
        return false;
    }

    bool below = pp_sample_adc(word) < rule->config.threshold[range];
    if ((range == 0u) || pp_sample_is_invalid(word) || !below) {
        rule->run = 0u;
        return false;
    }

    rule->run++;
    if (rule->run < rule->config.consecutive) {
        return false;
    }
    rule->run = 0u;
    rule->wait = rule->config.holdoff;
    return true;
}

bool pp_downrange_process(pp_downrange_t *rule, const uint32_t *words, size_t count)
{
    if ((rule == NULL) || (words == NULL)) {
        return false;
    }
    bool requested = false;
    for (size_t i = 0u; i < count; i++) {
        if (pp_downrange_update(rule, words[i])) {
            requested = true;
        }
    }
    return requested;
}
