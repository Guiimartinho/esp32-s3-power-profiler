/*
 * Protocol frames: the container of every message between device and host.
 *
 * A frame on the wire, all fields little-endian (section 7.1 of the
 * specification):
 *
 *     magic     2 bytes  PP_FRAME_MAGIC
 *     type      1 byte   pp_frame_type_t
 *     flags     1 byte   reserved, zero
 *     length    2 bytes  payload length in bytes
 *     sequence  2 bytes  per-type counter
 *     payload   length bytes
 *     crc       2 bytes  CRC-16 over everything before it
 *
 * The functions here neither allocate nor keep hidden state. The caller
 * supplies every buffer.
 */
#ifndef PP_FRAME_H
#define PP_FRAME_H

#include <stddef.h>
#include <stdint.h>

#include "base/pp_status.h"
#include "proto/pp_proto_defs.h"

/* Bytes that a frame with the given payload length takes on the wire. */
#define PP_FRAME_SIZE(payload_len) (PP_FRAME_HEADER_SIZE + (payload_len) + PP_FRAME_CRC_SIZE)

/* A frame, with the payload referenced and not copied. */
typedef struct {
    uint8_t type;           /* pp_frame_type_t */
    uint8_t flags;          /* reserved, zero */
    uint16_t sequence;      /* per-type counter */
    const uint8_t *payload; /* may be NULL when payload_len is zero */
    size_t payload_len;
} pp_frame_t;

/* --- Encoding ---------------------------------------------------------- */

/*
 * Write a complete frame into out. The payload may already sit at
 * out + PP_FRAME_HEADER_SIZE. Returns PP_ERR_INVALID_ARG for a NULL pointer
 * or a payload above PP_FRAME_MAX_PAYLOAD, and PP_ERR_NO_SPACE when out is
 * too small.
 */
pp_status_t pp_frame_encode(const pp_frame_t *frame, uint8_t *out, size_t out_size,
                            size_t *out_len);

/*
 * Complete a frame whose payload is already in place at
 * buffer + PP_FRAME_HEADER_SIZE: write the header before it and the CRC after
 * it. This avoids copying a large payload.
 */
pp_status_t pp_frame_seal(uint8_t *buffer, size_t buffer_size, uint8_t type, uint8_t flags,
                          uint16_t sequence, size_t payload_len, size_t *frame_len);

/* --- Decoding ---------------------------------------------------------- */

/*
 * Incremental frame parser. It accepts the byte stream in pieces of any size,
 * finds the frames in it and skips everything else: noise between frames, a
 * frame with a wrong CRC, a length above the accepted maximum. After such an
 * error it searches again from the byte after the false start, so a good
 * frame hidden behind a damaged one is still found.
 */
typedef struct {
    uint8_t *buffer;        /* storage for one frame, owned by the caller */
    size_t buffer_size;     /* bytes in buffer */
    size_t max_payload;     /* longest payload accepted */
    size_t fill;            /* bytes of the stream held in buffer */
    size_t emitted;         /* length of the frame returned by the last call */
    uint32_t frames;        /* frames accepted */
    uint32_t crc_errors;    /* candidates rejected by the CRC */
    uint32_t length_errors; /* candidates rejected for their length */
    uint32_t discarded;     /* bytes skipped while looking for a frame */
} pp_frame_parser_t;

/*
 * Prepare a parser. The buffer must hold PP_FRAME_SIZE(max_payload) bytes.
 * Returns PP_ERR_INVALID_ARG for a NULL pointer or a max_payload above
 * PP_FRAME_MAX_PAYLOAD, and PP_ERR_NO_SPACE when the buffer is too small.
 */
pp_status_t pp_frame_parser_init(pp_frame_parser_t *parser, uint8_t *buffer, size_t buffer_size,
                                 size_t max_payload);

/* Forget the bytes received so far. The counters are kept. */
void pp_frame_parser_reset(pp_frame_parser_t *parser);

/*
 * Give the parser the next bytes of the stream.
 *
 * Returns PP_OK when a frame is complete. *frame then describes it, and its
 * payload points into the parser buffer until the next call. *consumed tells
 * how many bytes of data were used; call again with the rest.
 *
 * Returns PP_ERR_INCOMPLETE when all the data was used and no frame is
 * complete yet. *consumed then equals len.
 *
 * A call can return a frame without using any data, when a good frame was
 * already buffered behind a damaged one. Therefore keep calling until the
 * parser reports PP_ERR_INCOMPLETE:
 *
 *     size_t offset = 0;
 *     pp_status_t status;
 *     do {
 *         size_t used = 0;
 *         status = pp_frame_parser_feed(&parser, data + offset, len - offset, &used, &frame);
 *         offset += used;
 *         if (status == PP_OK) {
 *             handle(&frame);
 *         }
 *     } while (status == PP_OK);
 */
pp_status_t pp_frame_parser_feed(pp_frame_parser_t *parser, const uint8_t *data, size_t len,
                                 size_t *consumed, pp_frame_t *frame);

#endif /* PP_FRAME_H */
