#include "unity.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "pp_proto_vectors.h"
#include "proto/pp_frame.h"

/* --- Fixture ----------------------------------------------------------- */

#define MAX_CAPTURED 32u

typedef struct {
    uint8_t type;
    uint8_t flags;
    uint16_t sequence;
    uint8_t payload[PP_FRAME_MAX_PAYLOAD];
    size_t payload_len;
} captured_frame_t;

static uint8_t parser_buffer[PP_FRAME_SIZE(PP_FRAME_MAX_PAYLOAD)];
static pp_frame_parser_t parser;
static captured_frame_t captured[MAX_CAPTURED];
static size_t captured_count;

/* The payload of a parsed frame is only valid until the next call: copy it. */
static void capture(const pp_frame_t *frame)
{
    TEST_ASSERT_LESS_THAN_size_t(MAX_CAPTURED, captured_count);
    captured_frame_t *slot = &captured[captured_count];
    slot->type = frame->type;
    slot->flags = frame->flags;
    slot->sequence = frame->sequence;
    slot->payload_len = frame->payload_len;
    TEST_ASSERT_NOT_NULL(frame->payload);
    memcpy(slot->payload, frame->payload, frame->payload_len);
    captured_count++;
}

/* Feed one piece of the stream the way the header tells callers to. */
static void feed(const uint8_t *data, size_t len)
{
    size_t offset = 0u;
    pp_status_t status;
    do {
        size_t used = 0u;
        pp_frame_t frame;
        status = pp_frame_parser_feed(&parser, data + offset, len - offset, &used, &frame);
        offset += used;
        if (status == PP_OK) {
            capture(&frame);
        }
    } while (status == PP_OK);
    TEST_ASSERT_EQUAL(PP_ERR_INCOMPLETE, status);
    TEST_ASSERT_EQUAL_size_t(len, offset);
}

static void feed_in_chunks(const uint8_t *data, size_t len, size_t chunk)
{
    for (size_t offset = 0u; offset < len; offset += chunk) {
        size_t piece = ((len - offset) < chunk) ? (len - offset) : chunk;
        feed(data + offset, piece);
    }
}

static void restart_parser(size_t max_payload)
{
    TEST_ASSERT_EQUAL(
        PP_OK, pp_frame_parser_init(&parser, parser_buffer, sizeof(parser_buffer), max_payload));
    captured_count = 0u;
}

static void assert_captured_equals_vector(size_t index, const pp_frame_vector_t *vector)
{
    TEST_ASSERT_LESS_THAN_size_t_MESSAGE(captured_count, index, vector->name);
    const captured_frame_t *frame = &captured[index];
    TEST_ASSERT_EQUAL_HEX8_MESSAGE(vector->type, frame->type, vector->name);
    TEST_ASSERT_EQUAL_HEX8_MESSAGE(0u, frame->flags, vector->name);
    TEST_ASSERT_EQUAL_HEX16_MESSAGE(vector->sequence, frame->sequence, vector->name);
    TEST_ASSERT_EQUAL_size_t_MESSAGE(vector->payload_len, frame->payload_len, vector->name);
    if (vector->payload_len > 0u) {
        TEST_ASSERT_EQUAL_HEX8_ARRAY_MESSAGE(vector->payload, frame->payload, vector->payload_len,
                                             vector->name);
    }
}

/* Encode a frame with a payload of counting bytes that never hits the magic. */
static size_t make_frame(uint8_t *out, size_t out_size, uint8_t type, uint16_t sequence,
                         size_t payload_len)
{
    static uint8_t payload[PP_FRAME_MAX_PAYLOAD];
    for (size_t i = 0u; i < payload_len; i++) {
        payload[i] = (uint8_t)(i % 0x50u);
    }
    pp_frame_t frame = {
        .type = type,
        .flags = 0u,
        .sequence = sequence,
        .payload = payload,
        .payload_len = payload_len,
    };
    size_t len = 0u;
    TEST_ASSERT_EQUAL(PP_OK, pp_frame_encode(&frame, out, out_size, &len));
    return len;
}

/* All shared vectors, one after the other, as one stream. */
static size_t make_vector_stream(uint8_t *out, size_t out_size)
{
    size_t len = 0u;
    for (size_t i = 0u; i < PP_FRAME_VECTOR_COUNT; i++) {
        TEST_ASSERT_TRUE((len + pp_frame_vectors[i].frame_len) <= out_size);
        memcpy(out + len, pp_frame_vectors[i].frame, pp_frame_vectors[i].frame_len);
        len += pp_frame_vectors[i].frame_len;
    }
    return len;
}

void setUp(void)
{
    restart_parser(PP_FRAME_MAX_PAYLOAD);
}

void tearDown(void)
{
}

/* --- Encoding ---------------------------------------------------------- */

static void test_frame_size_counts_header_payload_and_crc(void)
{
    TEST_ASSERT_EQUAL_size_t(10u, PP_FRAME_SIZE(0u));
    TEST_ASSERT_EQUAL_size_t(14u, PP_FRAME_SIZE(4u));
}

static void test_frame_encode_matches_the_shared_vectors(void)
{
    for (size_t i = 0u; i < PP_FRAME_VECTOR_COUNT; i++) {
        const pp_frame_vector_t *vector = &pp_frame_vectors[i];
        pp_frame_t frame = {
            .type = vector->type,
            .flags = 0u,
            .sequence = vector->sequence,
            .payload = vector->payload,
            .payload_len = vector->payload_len,
        };
        uint8_t out[64];
        size_t len = 0u;

        TEST_ASSERT_EQUAL_MESSAGE(PP_OK, pp_frame_encode(&frame, out, sizeof(out), &len),
                                  vector->name);
        TEST_ASSERT_EQUAL_size_t_MESSAGE(vector->frame_len, len, vector->name);
        TEST_ASSERT_EQUAL_HEX8_ARRAY_MESSAGE(vector->frame, out, vector->frame_len, vector->name);
    }
}

static void test_frame_seal_matches_the_shared_vectors(void)
{
    for (size_t i = 0u; i < PP_FRAME_VECTOR_COUNT; i++) {
        const pp_frame_vector_t *vector = &pp_frame_vectors[i];
        uint8_t out[64];
        size_t len = 0u;
        memset(out, 0xEE, sizeof(out));
        memcpy(out + PP_FRAME_HEADER_SIZE, vector->payload, vector->payload_len);

        TEST_ASSERT_EQUAL_MESSAGE(PP_OK,
                                  pp_frame_seal(out, sizeof(out), vector->type, 0u,
                                                vector->sequence, vector->payload_len, &len),
                                  vector->name);
        TEST_ASSERT_EQUAL_size_t_MESSAGE(vector->frame_len, len, vector->name);
        TEST_ASSERT_EQUAL_HEX8_ARRAY_MESSAGE(vector->frame, out, vector->frame_len, vector->name);
    }
}

static void test_frame_encode_accepts_an_empty_payload_without_a_pointer(void)
{
    pp_frame_t frame = {.type = 0x02u, .sequence = 5u, .payload = NULL, .payload_len = 0u};
    uint8_t out[PP_FRAME_SIZE(0u)];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_OK, pp_frame_encode(&frame, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL_size_t(sizeof(out), len);
}

static void test_frame_encode_accepts_a_payload_already_in_place(void)
{
    const uint8_t payload[] = {0x10u, 0x20u, 0x30u, 0x40u, 0x50u};
    pp_frame_t frame = {.type = 0x03u, .sequence = 9u, .payload_len = sizeof(payload)};
    uint8_t copied[32];
    uint8_t in_place[32];
    size_t copied_len = 0u;
    size_t in_place_len = 0u;

    frame.payload = payload;
    TEST_ASSERT_EQUAL(PP_OK, pp_frame_encode(&frame, copied, sizeof(copied), &copied_len));

    memcpy(in_place + PP_FRAME_HEADER_SIZE, payload, sizeof(payload));
    frame.payload = in_place + PP_FRAME_HEADER_SIZE;
    TEST_ASSERT_EQUAL(PP_OK, pp_frame_encode(&frame, in_place, sizeof(in_place), &in_place_len));

    TEST_ASSERT_EQUAL_size_t(copied_len, in_place_len);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(copied, in_place, copied_len);
}

static void test_frame_encode_checks_its_arguments(void)
{
    const uint8_t payload[4] = {1u, 2u, 3u, 4u};
    pp_frame_t frame = {.type = 1u, .payload = payload, .payload_len = sizeof(payload)};
    uint8_t out[PP_FRAME_SIZE(sizeof(payload))];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_frame_encode(NULL, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_frame_encode(&frame, NULL, sizeof(out), &len));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_frame_encode(&frame, out, sizeof(out), NULL));

    frame.payload = NULL;
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_frame_encode(&frame, out, sizeof(out), &len));

    frame.payload = payload;
    frame.payload_len = PP_FRAME_MAX_PAYLOAD + 1u;
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_frame_encode(&frame, out, sizeof(out), &len));
}

static void test_frame_encode_needs_room_for_the_whole_frame(void)
{
    const uint8_t payload[4] = {1u, 2u, 3u, 4u};
    pp_frame_t frame = {.type = 1u, .payload = payload, .payload_len = sizeof(payload)};
    uint8_t out[PP_FRAME_SIZE(sizeof(payload))];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_ERR_NO_SPACE, pp_frame_encode(&frame, out, sizeof(out) - 1u, &len));
    TEST_ASSERT_EQUAL(PP_OK, pp_frame_encode(&frame, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL_size_t(sizeof(out), len);
}

static void test_frame_seal_checks_its_arguments(void)
{
    uint8_t out[PP_FRAME_SIZE(4u)];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_frame_seal(NULL, sizeof(out), 1u, 0u, 0u, 4u, &len));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_frame_seal(out, sizeof(out), 1u, 0u, 0u, 4u, NULL));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG,
                      pp_frame_seal(out, sizeof(out), 1u, 0u, 0u, PP_FRAME_MAX_PAYLOAD + 1u, &len));
    TEST_ASSERT_EQUAL(PP_ERR_NO_SPACE, pp_frame_seal(out, sizeof(out) - 1u, 1u, 0u, 0u, 4u, &len));
}

/* --- Decoding: good streams -------------------------------------------- */

static void test_frame_parser_decodes_the_shared_vectors(void)
{
    for (size_t i = 0u; i < PP_FRAME_VECTOR_COUNT; i++) {
        const pp_frame_vector_t *vector = &pp_frame_vectors[i];
        restart_parser(PP_FRAME_MAX_PAYLOAD);

        feed(vector->frame, vector->frame_len);

        TEST_ASSERT_EQUAL_size_t_MESSAGE(1u, captured_count, vector->name);
        assert_captured_equals_vector(0u, vector);
        TEST_ASSERT_EQUAL_UINT32_MESSAGE(1u, parser.frames, vector->name);
        TEST_ASSERT_EQUAL_UINT32_MESSAGE(0u, parser.discarded, vector->name);
        TEST_ASSERT_EQUAL_UINT32_MESSAGE(0u, parser.crc_errors, vector->name);
        TEST_ASSERT_EQUAL_UINT32_MESSAGE(0u, parser.length_errors, vector->name);
    }
}

static void test_frame_parser_handles_any_chunk_size(void)
{
    uint8_t stream[512];
    size_t stream_len = make_vector_stream(stream, sizeof(stream));

    for (size_t chunk = 1u; chunk <= stream_len; chunk++) {
        restart_parser(PP_FRAME_MAX_PAYLOAD);

        feed_in_chunks(stream, stream_len, chunk);

        TEST_ASSERT_EQUAL_size_t(PP_FRAME_VECTOR_COUNT, captured_count);
        for (size_t i = 0u; i < PP_FRAME_VECTOR_COUNT; i++) {
            assert_captured_equals_vector(i, &pp_frame_vectors[i]);
        }
        TEST_ASSERT_EQUAL_UINT32(0u, parser.discarded);
    }
}

static void test_frame_parser_keeps_type_flags_and_sequence(void)
{
    const uint8_t payload[] = {0xDEu, 0xADu};
    pp_frame_t frame = {
        .type = 0x7Fu,
        .flags = 0x81u,
        .sequence = 0xBEEFu,
        .payload = payload,
        .payload_len = sizeof(payload),
    };
    uint8_t encoded[32];
    size_t len = 0u;
    TEST_ASSERT_EQUAL(PP_OK, pp_frame_encode(&frame, encoded, sizeof(encoded), &len));

    feed(encoded, len);

    TEST_ASSERT_EQUAL_size_t(1u, captured_count);
    TEST_ASSERT_EQUAL_HEX8(0x7Fu, captured[0].type);
    TEST_ASSERT_EQUAL_HEX8(0x81u, captured[0].flags);
    TEST_ASSERT_EQUAL_HEX16(0xBEEFu, captured[0].sequence);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(payload, captured[0].payload, sizeof(payload));
}

static void test_frame_parser_accepts_the_largest_payload(void)
{
    static uint8_t encoded[PP_FRAME_SIZE(PP_FRAME_MAX_PAYLOAD)];
    size_t len = make_frame(encoded, sizeof(encoded), 0x01u, 77u, PP_FRAME_MAX_PAYLOAD);

    feed_in_chunks(encoded, len, 100u);

    TEST_ASSERT_EQUAL_size_t(1u, captured_count);
    TEST_ASSERT_EQUAL_size_t(PP_FRAME_MAX_PAYLOAD, captured[0].payload_len);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(encoded + PP_FRAME_HEADER_SIZE, captured[0].payload,
                                 PP_FRAME_MAX_PAYLOAD);
    TEST_ASSERT_EQUAL_UINT32(0u, parser.discarded);
}

/* --- Decoding: damaged streams ----------------------------------------- */

static void test_frame_parser_skips_noise_around_frames(void)
{
    const uint8_t noise[] = {0x00u, 0xFFu, 0x12u, 0xA5u, 0x34u};
    const pp_frame_vector_t *first = &pp_frame_vectors[0];
    const pp_frame_vector_t *second = &pp_frame_vectors[1];

    feed(noise, sizeof(noise));
    feed(first->frame, first->frame_len);
    feed(noise, sizeof(noise));
    feed(second->frame, second->frame_len);
    feed(noise, sizeof(noise));

    TEST_ASSERT_EQUAL_size_t(2u, captured_count);
    assert_captured_equals_vector(0u, first);
    assert_captured_equals_vector(1u, second);
    TEST_ASSERT_EQUAL_UINT32(3u * sizeof(noise), parser.discarded);
    TEST_ASSERT_EQUAL_UINT32(0u, parser.crc_errors);
}

static void test_frame_parser_skips_bytes_that_only_look_like_a_start(void)
{
    /* The first magic byte alone, twice in a row, and followed by other bytes. */
    const uint8_t noise[] = {0x5Au, 0x00u, 0x5Au, 0x5Au, 0x11u};
    const pp_frame_vector_t *vector = &pp_frame_vectors[0];

    feed(noise, sizeof(noise));
    feed(vector->frame, vector->frame_len);

    TEST_ASSERT_EQUAL_size_t(1u, captured_count);
    assert_captured_equals_vector(0u, vector);
    TEST_ASSERT_EQUAL_UINT32(sizeof(noise), parser.discarded);
}

static void test_frame_parser_rejects_a_header_with_an_impossible_length(void)
{
    /* Magic, type, flags, then a length far above the protocol limit. */
    const uint8_t false_header[] = {0x5Au, 0xA5u, 0x02u, 0x00u, 0xFFu, 0xFFu, 0x00u, 0x00u};
    const pp_frame_vector_t *vector = &pp_frame_vectors[0];

    feed(false_header, sizeof(false_header));
    feed(vector->frame, vector->frame_len);

    TEST_ASSERT_EQUAL_size_t(1u, captured_count);
    assert_captured_equals_vector(0u, vector);
    TEST_ASSERT_EQUAL_UINT32(1u, parser.length_errors);
    TEST_ASSERT_EQUAL_UINT32(sizeof(false_header), parser.discarded);
}

static void test_frame_parser_honors_its_own_payload_limit(void)
{
    uint8_t too_long[PP_FRAME_SIZE(17u)];
    uint8_t fits[PP_FRAME_SIZE(16u)];
    size_t too_long_len = make_frame(too_long, sizeof(too_long), 0x02u, 1u, 17u);
    size_t fits_len = make_frame(fits, sizeof(fits), 0x02u, 2u, 16u);
    restart_parser(16u);

    feed(too_long, too_long_len);
    feed(fits, fits_len);

    TEST_ASSERT_EQUAL_size_t(1u, captured_count);
    TEST_ASSERT_EQUAL_HEX16(2u, captured[0].sequence);
    TEST_ASSERT_EQUAL_size_t(16u, captured[0].payload_len);
    TEST_ASSERT_EQUAL_UINT32(1u, parser.length_errors);
    TEST_ASSERT_EQUAL_UINT32(too_long_len, parser.discarded);
}

static void test_frame_parser_recovers_after_a_corrupted_frame(void)
{
    uint8_t damaged[PP_FRAME_SIZE(8u)];
    uint8_t good[PP_FRAME_SIZE(8u)];
    size_t damaged_len = make_frame(damaged, sizeof(damaged), 0x03u, 10u, 8u);
    size_t good_len = make_frame(good, sizeof(good), 0x03u, 11u, 8u);
    damaged[PP_FRAME_HEADER_SIZE + 3u] ^= 0x01u;

    feed(damaged, damaged_len);
    feed(good, good_len);

    TEST_ASSERT_EQUAL_size_t(1u, captured_count);
    TEST_ASSERT_EQUAL_HEX16(11u, captured[0].sequence);
    TEST_ASSERT_EQUAL_UINT32(1u, parser.crc_errors);
    TEST_ASSERT_EQUAL_UINT32(damaged_len, parser.discarded);
    TEST_ASSERT_EQUAL_UINT32(1u, parser.frames);
}

static void test_frame_parser_recovers_after_a_corrupted_crc(void)
{
    uint8_t damaged[PP_FRAME_SIZE(4u)];
    uint8_t good[PP_FRAME_SIZE(4u)];
    size_t damaged_len = make_frame(damaged, sizeof(damaged), 0x02u, 20u, 4u);
    size_t good_len = make_frame(good, sizeof(good), 0x02u, 21u, 4u);
    damaged[damaged_len - 1u] ^= 0x80u;

    feed_in_chunks(damaged, damaged_len, 3u);
    feed_in_chunks(good, good_len, 3u);

    TEST_ASSERT_EQUAL_size_t(1u, captured_count);
    TEST_ASSERT_EQUAL_HEX16(21u, captured[0].sequence);
    TEST_ASSERT_EQUAL_UINT32(1u, parser.crc_errors);
}

static void test_frame_parser_recovers_after_a_truncated_frame(void)
{
    const pp_frame_vector_t *cut = &pp_frame_vectors[1];
    const pp_frame_vector_t *whole = &pp_frame_vectors[0];
    size_t kept = 5u; /* the stream lost the rest of this frame */

    feed(cut->frame, kept);
    feed(whole->frame, whole->frame_len);

    TEST_ASSERT_EQUAL_size_t(1u, captured_count);
    assert_captured_equals_vector(0u, whole);
    TEST_ASSERT_EQUAL_UINT32(kept, parser.discarded);
}

/*
 * A false frame start can swallow real frames: its length field makes the
 * parser collect the bytes that follow as payload. When the CRC then fails,
 * the frames inside that payload must still come out, in order.
 */
static void test_frame_parser_finds_frames_hidden_in_a_false_frame(void)
{
    uint8_t first[PP_FRAME_SIZE(3u)];
    uint8_t second[PP_FRAME_SIZE(6u)];
    size_t first_len = make_frame(first, sizeof(first), 0x04u, 100u, 3u);
    size_t second_len = make_frame(second, sizeof(second), 0x04u, 101u, 6u);
    const uint8_t filler[] = {0x01u, 0x02u, 0x03u, 0x04u};

    /* The false frame claims everything after its header as payload and CRC. */
    size_t claimed = (first_len + second_len + sizeof(filler)) - PP_FRAME_CRC_SIZE;
    uint8_t stream[128];
    size_t len = 0u;
    stream[len++] = 0x5Au;
    stream[len++] = 0xA5u;
    stream[len++] = 0x01u;
    stream[len++] = 0x00u;
    stream[len++] = (uint8_t)(claimed & 0xFFu);
    stream[len++] = (uint8_t)(claimed >> 8);
    stream[len++] = 0x00u;
    stream[len++] = 0x00u;
    memcpy(stream + len, first, first_len);
    len += first_len;
    memcpy(stream + len, second, second_len);
    len += second_len;
    memcpy(stream + len, filler, sizeof(filler));
    len += sizeof(filler);

    size_t used = 0u;
    pp_frame_t frame;

    /* The whole stream is taken, and the first hidden frame comes out. */
    TEST_ASSERT_EQUAL(PP_OK, pp_frame_parser_feed(&parser, stream, len, &used, &frame));
    TEST_ASSERT_EQUAL_size_t(len, used);
    TEST_ASSERT_EQUAL_HEX16(100u, frame.sequence);
    TEST_ASSERT_EQUAL_UINT32(1u, parser.crc_errors);

    /* The second one was buffered already: it comes out without new data. */
    TEST_ASSERT_EQUAL(PP_OK, pp_frame_parser_feed(&parser, stream, 0u, &used, &frame));
    TEST_ASSERT_EQUAL_size_t(0u, used);
    TEST_ASSERT_EQUAL_HEX16(101u, frame.sequence);
    TEST_ASSERT_EQUAL_size_t(6u, frame.payload_len);

    TEST_ASSERT_EQUAL(PP_ERR_INCOMPLETE, pp_frame_parser_feed(&parser, stream, 0u, &used, &frame));
    TEST_ASSERT_EQUAL_size_t(0u, used);
    TEST_ASSERT_EQUAL_UINT32(2u, parser.frames);
    TEST_ASSERT_EQUAL_UINT32(PP_FRAME_HEADER_SIZE + sizeof(filler), parser.discarded);
}

static void test_frame_parser_reset_drops_a_partial_frame(void)
{
    const pp_frame_vector_t *partial = &pp_frame_vectors[1];
    const pp_frame_vector_t *whole = &pp_frame_vectors[2];

    feed(whole->frame, whole->frame_len);
    feed(partial->frame, partial->frame_len - 2u);
    pp_frame_parser_reset(&parser);
    feed(whole->frame, whole->frame_len);

    TEST_ASSERT_EQUAL_size_t(2u, captured_count);
    assert_captured_equals_vector(0u, whole);
    assert_captured_equals_vector(1u, whole);
    /* The counters survive a reset. */
    TEST_ASSERT_EQUAL_UINT32(2u, parser.frames);
}

/* --- Decoding: argument checks ----------------------------------------- */

static void test_frame_parser_init_checks_its_arguments(void)
{
    pp_frame_parser_t p;
    uint8_t buffer[PP_FRAME_SIZE(32u)];

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_frame_parser_init(NULL, buffer, sizeof(buffer), 32u));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_frame_parser_init(&p, NULL, sizeof(buffer), 32u));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG,
                      pp_frame_parser_init(&p, buffer, sizeof(buffer), PP_FRAME_MAX_PAYLOAD + 1u));
    TEST_ASSERT_EQUAL(PP_ERR_NO_SPACE, pp_frame_parser_init(&p, buffer, sizeof(buffer) - 1u, 32u));
    TEST_ASSERT_EQUAL(PP_OK, pp_frame_parser_init(&p, buffer, sizeof(buffer), 32u));
}

static void test_frame_parser_feed_checks_its_arguments(void)
{
    const uint8_t data[1] = {0u};
    size_t used = 0u;
    pp_frame_t frame;

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_frame_parser_feed(NULL, data, 1u, &used, &frame));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_frame_parser_feed(&parser, data, 1u, NULL, &frame));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_frame_parser_feed(&parser, data, 1u, &used, NULL));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_frame_parser_feed(&parser, NULL, 1u, &used, &frame));
}

static void test_frame_parser_feed_accepts_no_data(void)
{
    size_t used = 99u;
    pp_frame_t frame;

    TEST_ASSERT_EQUAL(PP_ERR_INCOMPLETE, pp_frame_parser_feed(&parser, NULL, 0u, &used, &frame));
    TEST_ASSERT_EQUAL_size_t(0u, used);
}

static void test_frame_parser_reset_tolerates_null(void)
{
    pp_frame_parser_reset(NULL);
    TEST_PASS();
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_frame_size_counts_header_payload_and_crc);
    RUN_TEST(test_frame_encode_matches_the_shared_vectors);
    RUN_TEST(test_frame_seal_matches_the_shared_vectors);
    RUN_TEST(test_frame_encode_accepts_an_empty_payload_without_a_pointer);
    RUN_TEST(test_frame_encode_accepts_a_payload_already_in_place);
    RUN_TEST(test_frame_encode_checks_its_arguments);
    RUN_TEST(test_frame_encode_needs_room_for_the_whole_frame);
    RUN_TEST(test_frame_seal_checks_its_arguments);
    RUN_TEST(test_frame_parser_decodes_the_shared_vectors);
    RUN_TEST(test_frame_parser_handles_any_chunk_size);
    RUN_TEST(test_frame_parser_keeps_type_flags_and_sequence);
    RUN_TEST(test_frame_parser_accepts_the_largest_payload);
    RUN_TEST(test_frame_parser_skips_noise_around_frames);
    RUN_TEST(test_frame_parser_skips_bytes_that_only_look_like_a_start);
    RUN_TEST(test_frame_parser_rejects_a_header_with_an_impossible_length);
    RUN_TEST(test_frame_parser_honors_its_own_payload_limit);
    RUN_TEST(test_frame_parser_recovers_after_a_corrupted_frame);
    RUN_TEST(test_frame_parser_recovers_after_a_corrupted_crc);
    RUN_TEST(test_frame_parser_recovers_after_a_truncated_frame);
    RUN_TEST(test_frame_parser_finds_frames_hidden_in_a_false_frame);
    RUN_TEST(test_frame_parser_reset_drops_a_partial_frame);
    RUN_TEST(test_frame_parser_init_checks_its_arguments);
    RUN_TEST(test_frame_parser_feed_checks_its_arguments);
    RUN_TEST(test_frame_parser_feed_accepts_no_data);
    RUN_TEST(test_frame_parser_reset_tolerates_null);
    return UNITY_END();
}
