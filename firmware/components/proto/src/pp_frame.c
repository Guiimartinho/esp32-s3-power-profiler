#include "proto/pp_frame.h"

#include <stdbool.h>
#include <string.h>

#include "base/pp_bytes.h"
#include "proto/pp_crc16.h"

/* Offsets of the header fields. */
enum {
    OFFSET_MAGIC = 0,
    OFFSET_TYPE = 2,
    OFFSET_FLAGS = 3,
    OFFSET_LENGTH = 4,
    OFFSET_SEQUENCE = 6,
};

_Static_assert((OFFSET_SEQUENCE + 2) == PP_FRAME_HEADER_SIZE, "header fields must fill the header");
_Static_assert(PP_FRAME_CRC_SIZE == 2u, "the CRC is written as one 16-bit field");
_Static_assert(PP_FRAME_MAX_PAYLOAD <= UINT16_MAX, "the length field is 16 bits wide");

/* The magic word as it appears in the stream: low byte first. */
#define MAGIC_FIRST ((uint8_t)(PP_FRAME_MAGIC & 0xFFu))
#define MAGIC_SECOND ((uint8_t)(PP_FRAME_MAGIC >> 8))

/* --- Encoding ---------------------------------------------------------- */

pp_status_t pp_frame_seal(uint8_t *buffer, size_t buffer_size, uint8_t type, uint8_t flags,
                          uint16_t sequence, size_t payload_len, size_t *frame_len)
{
    if ((buffer == NULL) || (frame_len == NULL) || (payload_len > PP_FRAME_MAX_PAYLOAD)) {
        return PP_ERR_INVALID_ARG;
    }
    size_t body_len = PP_FRAME_HEADER_SIZE + payload_len;
    size_t total = body_len + PP_FRAME_CRC_SIZE;
    if (total > buffer_size) {
        return PP_ERR_NO_SPACE;
    }

    pp_put_u16le(buffer + OFFSET_MAGIC, (uint16_t)PP_FRAME_MAGIC);
    buffer[OFFSET_TYPE] = type;
    buffer[OFFSET_FLAGS] = flags;
    pp_put_u16le(buffer + OFFSET_LENGTH, (uint16_t)payload_len);
    pp_put_u16le(buffer + OFFSET_SEQUENCE, sequence);
    pp_put_u16le(buffer + body_len, pp_crc16(buffer, body_len));

    *frame_len = total;
    return PP_OK;
}

pp_status_t pp_frame_encode(const pp_frame_t *frame, uint8_t *out, size_t out_size, size_t *out_len)
{
    if ((frame == NULL) || (out == NULL) || (out_len == NULL)) {
        return PP_ERR_INVALID_ARG;
    }
    if ((frame->payload_len > PP_FRAME_MAX_PAYLOAD) ||
        ((frame->payload == NULL) && (frame->payload_len > 0u))) {
        return PP_ERR_INVALID_ARG;
    }
    if (PP_FRAME_SIZE(frame->payload_len) > out_size) {
        return PP_ERR_NO_SPACE;
    }
    if (frame->payload_len > 0u) {
        /* memmove, because the payload may already be inside out. */
        memmove(out + PP_FRAME_HEADER_SIZE, frame->payload, frame->payload_len);
    }
    return pp_frame_seal(out, out_size, frame->type, frame->flags, frame->sequence,
                         frame->payload_len, out_len);
}

/* --- Decoding ---------------------------------------------------------- */

/* Remove bytes from the front of the buffer without counting them. */
static void drop_front(pp_frame_parser_t *parser, size_t count)
{
    parser->fill -= count;
    if (parser->fill > 0u) {
        memmove(parser->buffer, parser->buffer + count, parser->fill);
    }
}

/* Remove bytes that belong to no frame and count them. */
static void discard(pp_frame_parser_t *parser, size_t count)
{
    drop_front(parser, count);
    parser->discarded += (uint32_t)count;
}

static size_t payload_length(const pp_frame_parser_t *parser)
{
    return pp_get_u16le(parser->buffer + OFFSET_LENGTH);
}

/*
 * Make the buffer start with a plausible frame prefix: the magic word and,
 * once the header is complete, a length the parser accepts. Bytes that cannot
 * start a frame are discarded.
 */
static void align_to_frame_start(pp_frame_parser_t *parser)
{
    for (;;) {
        size_t skip = 0u;
        while ((skip < parser->fill) && (parser->buffer[skip] != MAGIC_FIRST)) {
            skip++;
        }
        if (skip > 0u) {
            discard(parser, skip);
        }
        if (parser->fill < 2u) {
            return;
        }
        if (parser->buffer[1] != MAGIC_SECOND) {
            discard(parser, 1u);
            continue;
        }
        if (parser->fill < PP_FRAME_HEADER_SIZE) {
            return;
        }
        if (payload_length(parser) > parser->max_payload) {
            parser->length_errors++;
            discard(parser, 1u);
            continue;
        }
        return;
    }
}

/* Bytes still missing from the frame at the front of the buffer. */
static size_t bytes_missing(const pp_frame_parser_t *parser)
{
    if (parser->fill < PP_FRAME_HEADER_SIZE) {
        return PP_FRAME_HEADER_SIZE - parser->fill;
    }
    size_t total = PP_FRAME_SIZE(payload_length(parser));
    return (parser->fill < total) ? (total - parser->fill) : 0u;
}

static bool crc_matches(const pp_frame_parser_t *parser, size_t body_len)
{
    return pp_crc16(parser->buffer, body_len) == pp_get_u16le(parser->buffer + body_len);
}

pp_status_t pp_frame_parser_init(pp_frame_parser_t *parser, uint8_t *buffer, size_t buffer_size,
                                 size_t max_payload)
{
    if ((parser == NULL) || (buffer == NULL) || (max_payload > PP_FRAME_MAX_PAYLOAD)) {
        return PP_ERR_INVALID_ARG;
    }
    if (PP_FRAME_SIZE(max_payload) > buffer_size) {
        return PP_ERR_NO_SPACE;
    }
    parser->buffer = buffer;
    parser->buffer_size = buffer_size;
    parser->max_payload = max_payload;
    parser->fill = 0u;
    parser->emitted = 0u;
    parser->frames = 0u;
    parser->crc_errors = 0u;
    parser->length_errors = 0u;
    parser->discarded = 0u;
    return PP_OK;
}

void pp_frame_parser_reset(pp_frame_parser_t *parser)
{
    if (parser == NULL) {
        return;
    }
    parser->fill = 0u;
    parser->emitted = 0u;
}

pp_status_t pp_frame_parser_feed(pp_frame_parser_t *parser, const uint8_t *data, size_t len,
                                 size_t *consumed, pp_frame_t *frame)
{
    if ((parser == NULL) || (consumed == NULL) || (frame == NULL) ||
        ((data == NULL) && (len > 0u))) {
        return PP_ERR_INVALID_ARG;
    }

    /* The frame returned by the previous call is no longer needed. */
    if (parser->emitted > 0u) {
        drop_front(parser, parser->emitted);
        parser->emitted = 0u;
    }

    size_t used = 0u;
    for (;;) {
        align_to_frame_start(parser);

        size_t missing = bytes_missing(parser);
        if (missing == 0u) {
            size_t payload_len = payload_length(parser);
            size_t body_len = PP_FRAME_HEADER_SIZE + payload_len;
            if (crc_matches(parser, body_len)) {
                frame->type = parser->buffer[OFFSET_TYPE];
                frame->flags = parser->buffer[OFFSET_FLAGS];
                frame->sequence = pp_get_u16le(parser->buffer + OFFSET_SEQUENCE);
                frame->payload = parser->buffer + PP_FRAME_HEADER_SIZE;
                frame->payload_len = payload_len;
                parser->emitted = body_len + PP_FRAME_CRC_SIZE;
                parser->frames++;
                *consumed = used;
                return PP_OK;
            }
            /* Not a frame after all: search again from the next byte. */
            parser->crc_errors++;
            discard(parser, 1u);
            continue;
        }

        if (used == len) {
            *consumed = used;
            return PP_ERR_INCOMPLETE;
        }

        /* Take no more than the frame at the front needs. */
        size_t take = ((len - used) < missing) ? (len - used) : missing;
        memcpy(parser->buffer + parser->fill, data + used, take);
        parser->fill += take;
        used += take;
    }
}
