#include "proto/pp_stream.h"

#include "base/pp_bytes.h"

/* Offsets of the header fields. */
enum {
    OFFSET_FIRST_INDEX = 0,
    OFFSET_DROPPED = 4,
    OFFSET_COUNT = 6,
};

_Static_assert((OFFSET_COUNT + 2) == PP_STREAM_HEADER_SIZE, "header fields must fill the header");
_Static_assert(PP_STREAM_PAYLOAD_SIZE(PP_BLOCK_SAMPLES) <= PP_FRAME_MAX_PAYLOAD,
               "a full block must fit in one frame");

static void write_header(const pp_stream_header_t *header, uint8_t *out)
{
    pp_put_u32le(out + OFFSET_FIRST_INDEX, header->first_index);
    pp_put_u16le(out + OFFSET_DROPPED, header->dropped);
    pp_put_u16le(out + OFFSET_COUNT, header->count);
}

pp_status_t pp_stream_encode_header(const pp_stream_header_t *header, uint8_t *out, size_t out_size)
{
    if ((header == NULL) || (out == NULL) || (header->count > PP_STREAM_MAX_SAMPLES)) {
        return PP_ERR_INVALID_ARG;
    }
    if (out_size < PP_STREAM_HEADER_SIZE) {
        return PP_ERR_NO_SPACE;
    }
    write_header(header, out);
    return PP_OK;
}

pp_status_t pp_stream_encode(const pp_stream_header_t *header, const uint32_t *samples,
                             uint8_t *out, size_t out_size, size_t *out_len)
{
    if ((header == NULL) || (out == NULL) || (out_len == NULL)) {
        return PP_ERR_INVALID_ARG;
    }
    if ((header->count > PP_STREAM_MAX_SAMPLES) || ((samples == NULL) && (header->count > 0u))) {
        return PP_ERR_INVALID_ARG;
    }
    size_t total = PP_STREAM_PAYLOAD_SIZE((size_t)header->count);
    if (total > out_size) {
        return PP_ERR_NO_SPACE;
    }

    write_header(header, out);
    uint8_t *cursor = out + PP_STREAM_HEADER_SIZE;
    for (size_t i = 0u; i < header->count; i++) {
        pp_put_u32le(cursor, samples[i]);
        cursor += PP_STREAM_SAMPLE_SIZE;
    }

    *out_len = total;
    return PP_OK;
}

pp_status_t pp_stream_decode(const uint8_t *payload, size_t payload_len, pp_stream_header_t *header,
                             const uint8_t **samples)
{
    if ((payload == NULL) || (header == NULL) || (samples == NULL)) {
        return PP_ERR_INVALID_ARG;
    }
    if (payload_len < PP_STREAM_HEADER_SIZE) {
        return PP_ERR_MALFORMED;
    }
    uint16_t count = pp_get_u16le(payload + OFFSET_COUNT);
    if (payload_len != PP_STREAM_PAYLOAD_SIZE((size_t)count)) {
        return PP_ERR_MALFORMED;
    }

    header->first_index = pp_get_u32le(payload + OFFSET_FIRST_INDEX);
    header->dropped = pp_get_u16le(payload + OFFSET_DROPPED);
    header->count = count;
    *samples = payload + PP_STREAM_HEADER_SIZE;
    return PP_OK;
}

uint32_t pp_stream_sample(const uint8_t *samples, size_t index)
{
    if (samples == NULL) {
        return 0u;
    }
    return pp_get_u32le(samples + (index * PP_STREAM_SAMPLE_SIZE));
}
