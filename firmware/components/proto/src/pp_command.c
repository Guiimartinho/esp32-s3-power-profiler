#include "proto/pp_command.h"

#include <string.h>

/*
 * The three payloads share one shape: a short fixed prefix followed by a body
 * of free length. The helpers below implement that shape once.
 */

static pp_status_t encode_envelope(const uint8_t *prefix, size_t prefix_len, const uint8_t *body,
                                   size_t body_len, size_t max_payload, uint8_t *out,
                                   size_t out_size, size_t *out_len)
{
    if ((out == NULL) || (out_len == NULL) || ((body == NULL) && (body_len > 0u))) {
        return PP_ERR_INVALID_ARG;
    }
    if (body_len > (max_payload - prefix_len)) {
        return PP_ERR_INVALID_ARG;
    }
    size_t total = prefix_len + body_len;
    if (total > out_size) {
        return PP_ERR_NO_SPACE;
    }

    memcpy(out, prefix, prefix_len);
    if (body_len > 0u) {
        memcpy(out + prefix_len, body, body_len);
    }
    *out_len = total;
    return PP_OK;
}

static bool envelope_fits(size_t payload_len, size_t prefix_len, size_t max_payload)
{
    return (payload_len >= prefix_len) && (payload_len <= max_payload);
}

pp_status_t pp_command_encode(const pp_command_t *command, uint8_t *out, size_t out_size,
                              size_t *out_len)
{
    if (command == NULL) {
        return PP_ERR_INVALID_ARG;
    }
    const uint8_t prefix[PP_COMMAND_HEADER_SIZE] = {command->id};
    return encode_envelope(prefix, sizeof(prefix), command->args, command->args_len,
                           PP_COMMAND_MAX_PAYLOAD, out, out_size, out_len);
}

pp_status_t pp_response_encode(const pp_response_t *response, uint8_t *out, size_t out_size,
                               size_t *out_len)
{
    if (response == NULL) {
        return PP_ERR_INVALID_ARG;
    }
    const uint8_t prefix[PP_RESPONSE_HEADER_SIZE] = {response->id, response->status};
    return encode_envelope(prefix, sizeof(prefix), response->data, response->data_len,
                           PP_FRAME_MAX_PAYLOAD, out, out_size, out_len);
}

pp_status_t pp_event_encode(const pp_event_t *event, uint8_t *out, size_t out_size, size_t *out_len)
{
    if (event == NULL) {
        return PP_ERR_INVALID_ARG;
    }
    const uint8_t prefix[PP_EVENT_HEADER_SIZE] = {event->id};
    return encode_envelope(prefix, sizeof(prefix), event->data, event->data_len,
                           PP_FRAME_MAX_PAYLOAD, out, out_size, out_len);
}

pp_status_t pp_command_decode(const uint8_t *payload, size_t payload_len, pp_command_t *command)
{
    if ((payload == NULL) || (command == NULL)) {
        return PP_ERR_INVALID_ARG;
    }
    if (!envelope_fits(payload_len, PP_COMMAND_HEADER_SIZE, PP_COMMAND_MAX_PAYLOAD)) {
        return PP_ERR_MALFORMED;
    }
    command->id = payload[0];
    command->args = payload + PP_COMMAND_HEADER_SIZE;
    command->args_len = payload_len - PP_COMMAND_HEADER_SIZE;
    return PP_OK;
}

pp_status_t pp_response_decode(const uint8_t *payload, size_t payload_len, pp_response_t *response)
{
    if ((payload == NULL) || (response == NULL)) {
        return PP_ERR_INVALID_ARG;
    }
    if (!envelope_fits(payload_len, PP_RESPONSE_HEADER_SIZE, PP_FRAME_MAX_PAYLOAD)) {
        return PP_ERR_MALFORMED;
    }
    response->id = payload[0];
    response->status = payload[1];
    response->data = payload + PP_RESPONSE_HEADER_SIZE;
    response->data_len = payload_len - PP_RESPONSE_HEADER_SIZE;
    return PP_OK;
}

pp_status_t pp_event_decode(const uint8_t *payload, size_t payload_len, pp_event_t *event)
{
    if ((payload == NULL) || (event == NULL)) {
        return PP_ERR_INVALID_ARG;
    }
    if (!envelope_fits(payload_len, PP_EVENT_HEADER_SIZE, PP_FRAME_MAX_PAYLOAD)) {
        return PP_ERR_MALFORMED;
    }
    event->id = payload[0];
    event->data = payload + PP_EVENT_HEADER_SIZE;
    event->data_len = payload_len - PP_EVENT_HEADER_SIZE;
    return PP_OK;
}

bool pp_command_is_known(uint8_t id)
{
    /* No default case: the compiler reports a command missing from the list. */
    switch ((pp_command_id_t)id) {
    case PP_CMD_GET_INFO:
    case PP_CMD_GET_STATUS:
    case PP_CMD_SET_MODE:
    case PP_CMD_SET_VOLTAGE:
    case PP_CMD_DUT_POWER:
    case PP_CMD_SET_RANGE:
    case PP_CMD_SET_DOWN_N:
    case PP_CMD_START:
    case PP_CMD_STOP:
    case PP_CMD_CAL_ZERO:
    case PP_CMD_CAL_WRITE:
    case PP_CMD_CLEAR_FAULT:
        return true;
    }
    return false;
}

bool pp_event_is_known(uint8_t id)
{
    /* No default case: the compiler reports an event missing from the list. */
    switch ((pp_event_id_t)id) {
    case PP_EVENT_FAULT_RAISED:
    case PP_EVENT_POWER_BUDGET_CHANGED:
    case PP_EVENT_STATE_CHANGED:
        return true;
    }
    return false;
}
