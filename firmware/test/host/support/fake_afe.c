#include "fake_afe.h"

#include <stddef.h>

static pp_status_t fake_set_range_lock(void *ctx, bool locked, uint8_t range)
{
    fake_afe_t *fake = ctx;
    fake->set_range_lock_calls++;
    if (fake->next_status == PP_OK) {
        fake->range_locked = locked;
        fake->locked_range = range;
    }
    return fake->next_status;
}

static pp_status_t fake_step_down(void *ctx)
{
    fake_afe_t *fake = ctx;
    fake->step_down_calls++;
    return fake->next_status;
}

static pp_status_t fake_set_mode(void *ctx, pp_mode_t mode)
{
    fake_afe_t *fake = ctx;
    fake->set_mode_calls++;
    if (fake->next_status == PP_OK) {
        fake->mode = mode;
    }
    return fake->next_status;
}

static pp_status_t fake_set_output(void *ctx, bool enabled)
{
    fake_afe_t *fake = ctx;
    fake->set_output_calls++;
    if (fake->next_status == PP_OK) {
        /* The fault latch overrides the request, as the hardware does. */
        fake->output_enabled = enabled && !fake->fault;
    }
    return fake->next_status;
}

/* The port fixes the signature: adapters get a context they may change. */
/* cppcheck-suppress constParameterCallback */
static bool fake_fault_latched(void *ctx)
{
    const fake_afe_t *fake = ctx;
    return fake->fault;
}

static pp_status_t fake_clear_fault(void *ctx)
{
    fake_afe_t *fake = ctx;
    fake->clear_fault_calls++;
    if (fake->next_status == PP_OK) {
        fake->fault = false;
    }
    return fake->next_status;
}

void fake_afe_init(fake_afe_t *fake)
{
    *fake = (fake_afe_t){
        .range_locked = false,
        .locked_range = 0u,
        .mode = PP_MODE_AMPERE_METER,
        .output_enabled = false,
        .fault = false,
        .next_status = PP_OK,
    };
}

pp_afe_port_t fake_afe_port(fake_afe_t *fake)
{
    return (pp_afe_port_t){
        .ctx = fake,
        .set_range_lock = fake_set_range_lock,
        .step_down = fake_step_down,
        .set_mode = fake_set_mode,
        .set_output = fake_set_output,
        .fault_latched = fake_fault_latched,
        .clear_fault = fake_clear_fault,
    };
}

void fake_afe_trip(fake_afe_t *fake)
{
    fake->fault = true;
    fake->output_enabled = false;
}
