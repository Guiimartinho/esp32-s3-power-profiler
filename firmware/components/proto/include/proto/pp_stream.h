/*
 * Payload of a stream frame (section 7.2 of the specification).
 *
 *     first_index  4 bytes  index of the first sample since START
 *     dropped      2 bytes  blocks dropped since the previous frame
 *     count        2 bytes  number of sample words that follow
 *     samples      4 bytes each, see pp_sample.h
 *
 * All fields are little-endian.
 */
#ifndef PP_STREAM_H
#define PP_STREAM_H

#include <stddef.h>
#include <stdint.h>

#include "base/pp_status.h"
#include "proto/pp_proto_defs.h"

#define PP_STREAM_HEADER_SIZE 8u
#define PP_STREAM_SAMPLE_SIZE 4u

/* Payload bytes of a stream frame that carries count samples. */
#define PP_STREAM_PAYLOAD_SIZE(count) (PP_STREAM_HEADER_SIZE + (PP_STREAM_SAMPLE_SIZE * (count)))

/* Most samples that fit in one frame. */
#define PP_STREAM_MAX_SAMPLES                                                                      \
    ((PP_FRAME_MAX_PAYLOAD - PP_STREAM_HEADER_SIZE) / PP_STREAM_SAMPLE_SIZE)

typedef struct {
    uint32_t first_index; /* index of the first sample since START */
    uint16_t dropped;     /* blocks dropped since the previous frame */
    uint16_t count;       /* sample words that follow the header */
} pp_stream_header_t;

/*
 * Write only the header. Use it when the sample words are already in place
 * behind it. Returns PP_ERR_NO_SPACE when out is shorter than the header.
 */
pp_status_t pp_stream_encode_header(const pp_stream_header_t *header, uint8_t *out,
                                    size_t out_size);

/*
 * Write the header followed by header->count sample words taken from
 * samples. Returns PP_ERR_INVALID_ARG for a NULL pointer or a count above
 * PP_STREAM_MAX_SAMPLES, and PP_ERR_NO_SPACE when out is too small.
 */
pp_status_t pp_stream_encode(const pp_stream_header_t *header, const uint32_t *samples,
                             uint8_t *out, size_t out_size, size_t *out_len);

/*
 * Read the header and locate the sample words. Returns PP_ERR_MALFORMED when
 * the payload length does not match the count in the header.
 */
pp_status_t pp_stream_decode(const uint8_t *payload, size_t payload_len, pp_stream_header_t *header,
                             const uint8_t **samples);

/* Sample word number index of the samples located by pp_stream_decode(). */
uint32_t pp_stream_sample(const uint8_t *samples, size_t index);

#endif /* PP_STREAM_H */
