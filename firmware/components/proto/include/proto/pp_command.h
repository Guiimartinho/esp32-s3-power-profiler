/*
 * Payloads of command, response and event frames (section 7.4 of the
 * specification).
 *
 *     command   id (1 byte), then the arguments
 *     response  id of the command (1 byte), status (1 byte), then the data
 *     event     id (1 byte), then the data
 *
 * This module handles the envelope only. The layout of the arguments and of
 * the data depends on the command and is decoded by its handler.
 */
#ifndef PP_COMMAND_H
#define PP_COMMAND_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "base/pp_status.h"
#include "proto/pp_proto_defs.h"

#define PP_COMMAND_HEADER_SIZE 1u
#define PP_RESPONSE_HEADER_SIZE 2u
#define PP_EVENT_HEADER_SIZE 1u

typedef struct {
    uint8_t id;          /* pp_command_id_t */
    const uint8_t *args; /* may be NULL when args_len is zero */
    size_t args_len;
} pp_command_t;

typedef struct {
    uint8_t id;          /* pp_command_id_t of the command being answered */
    uint8_t status;      /* pp_proto_status_t */
    const uint8_t *data; /* may be NULL when data_len is zero */
    size_t data_len;
} pp_response_t;

typedef struct {
    uint8_t id;          /* pp_event_id_t */
    const uint8_t *data; /* may be NULL when data_len is zero */
    size_t data_len;
} pp_event_t;

/*
 * The encoders write the payload of the frame into out. They return
 * PP_ERR_INVALID_ARG for a NULL pointer or a payload above the protocol
 * limit (PP_COMMAND_MAX_PAYLOAD for a command, PP_FRAME_MAX_PAYLOAD for a
 * response or an event) and PP_ERR_NO_SPACE when out is too small.
 */
pp_status_t pp_command_encode(const pp_command_t *command, uint8_t *out, size_t out_size,
                              size_t *out_len);
pp_status_t pp_response_encode(const pp_response_t *response, uint8_t *out, size_t out_size,
                               size_t *out_len);
pp_status_t pp_event_encode(const pp_event_t *event, uint8_t *out, size_t out_size,
                            size_t *out_len);

/*
 * The decoders split a payload into its parts, which point into the payload.
 * They return PP_ERR_MALFORMED when the payload is shorter than the envelope
 * or longer than the protocol limit. An unknown id is not an error here: the
 * device answers it with PP_PROTO_STATUS_UNKNOWN_COMMAND.
 */
pp_status_t pp_command_decode(const uint8_t *payload, size_t payload_len, pp_command_t *command);
pp_status_t pp_response_decode(const uint8_t *payload, size_t payload_len, pp_response_t *response);
pp_status_t pp_event_decode(const uint8_t *payload, size_t payload_len, pp_event_t *event);

/* True when the id is one of the commands of the protocol definition. */
bool pp_command_is_known(uint8_t id);

/* True when the id is one of the events of the protocol definition. */
bool pp_event_is_known(uint8_t id);

#endif /* PP_COMMAND_H */
