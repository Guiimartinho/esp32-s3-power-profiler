/*
 * Composition root of the firmware.
 *
 * This is the only place that knows both the hardware-independent code and
 * ESP-IDF. For now it creates the device state machine and reports its state;
 * the adapters for the acquisition, the analog front end and USB are added in
 * the development phases that bring up the hardware.
 */
#include "esp_app_desc.h"
#include "esp_log.h"

#include "app/pp_fsm.h"
#include "base/pp_status.h"
#include "proto/pp_proto_defs.h"

static const char *TAG = "main";

static void log_transition(void *ctx, pp_device_state_t from, pp_device_state_t to,
                           pp_fsm_event_t event)
{
    (void)ctx;
    ESP_LOGI(TAG, "state %s -> %s on %s", pp_fsm_state_name(from), pp_fsm_state_name(to),
             pp_fsm_event_name(event));
}

void app_main(void)
{
    static pp_fsm_t fsm;

    const esp_app_desc_t *app = esp_app_get_description();
    ESP_LOGI(TAG, "%s %s, protocol version %u", app->project_name, app->version,
             (unsigned)PP_PROTO_VERSION);

    pp_status_t status = pp_fsm_init(&fsm, log_transition, NULL);
    if (status != PP_OK) {
        ESP_LOGE(TAG, "state machine init failed: %s", pp_status_name(status));
        return;
    }
    ESP_LOGI(TAG, "state %s", pp_fsm_state_name(pp_fsm_state(&fsm)));
}
