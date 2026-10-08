#include "unity.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "pp_proto_vectors.h"
#include "proto/pp_stream.h"

/* The stream frame among the shared vectors: two samples from index 0x12345. */
static const pp_frame_vector_t *stream_vector;

void setUp(void)
{
    stream_vector = NULL;
    for (size_t i = 0u; i < PP_FRAME_VECTOR_COUNT; i++) {
        if (strcmp(pp_frame_vectors[i].name, "stream_two_samples") == 0) {
            stream_vector = &pp_frame_vectors[i];
        }
    }
    TEST_ASSERT_NOT_NULL_MESSAGE(stream_vector, "vector stream_two_samples is missing");
}

void tearDown(void)
{
}

static void test_stream_sizes(void)
{
    TEST_ASSERT_EQUAL_size_t(8u, PP_STREAM_PAYLOAD_SIZE(0u));
    TEST_ASSERT_EQUAL_size_t(8u + (4u * 256u), PP_STREAM_PAYLOAD_SIZE(256u));
    TEST_ASSERT_TRUE(PP_STREAM_MAX_SAMPLES >= PP_BLOCK_SAMPLES);
    TEST_ASSERT_TRUE(PP_STREAM_PAYLOAD_SIZE(PP_STREAM_MAX_SAMPLES) <= PP_FRAME_MAX_PAYLOAD);
}

static void test_stream_encode_matches_the_shared_vector(void)
{
    const pp_stream_header_t header = {.first_index = 0x00012345u, .dropped = 0u, .count = 2u};
    const uint32_t samples[2] = {0xA5021234u, 0x000FFFFFu};
    uint8_t out[32];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_OK, pp_stream_encode(&header, samples, out, sizeof(out), &len));

    TEST_ASSERT_EQUAL_size_t(stream_vector->payload_len, len);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(stream_vector->payload, out, stream_vector->payload_len);
}

static void test_stream_decode_matches_the_shared_vector(void)
{
    pp_stream_header_t header;
    const uint8_t *samples = NULL;

    TEST_ASSERT_EQUAL(PP_OK, pp_stream_decode(stream_vector->payload, stream_vector->payload_len,
                                              &header, &samples));

    TEST_ASSERT_EQUAL_HEX32(0x00012345u, header.first_index);
    TEST_ASSERT_EQUAL_UINT16(0u, header.dropped);
    TEST_ASSERT_EQUAL_UINT16(2u, header.count);
    TEST_ASSERT_EQUAL_PTR(stream_vector->payload + PP_STREAM_HEADER_SIZE, samples);
    TEST_ASSERT_EQUAL_HEX32(0xA5021234u, pp_stream_sample(samples, 0u));
    TEST_ASSERT_EQUAL_HEX32(0x000FFFFFu, pp_stream_sample(samples, 1u));
}

static void test_stream_encode_header_writes_only_the_header(void)
{
    const pp_stream_header_t header = {.first_index = 0xAABBCCDDu, .dropped = 0x1122u, .count = 3u};
    uint8_t out[12];
    memset(out, 0xEE, sizeof(out));

    TEST_ASSERT_EQUAL(PP_OK, pp_stream_encode_header(&header, out, sizeof(out)));

    const uint8_t expected[12] = {0xDDu, 0xCCu, 0xBBu, 0xAAu, 0x22u, 0x11u,
                                  0x03u, 0x00u, 0xEEu, 0xEEu, 0xEEu, 0xEEu};
    TEST_ASSERT_EQUAL_HEX8_ARRAY(expected, out, sizeof(expected));
}

static void test_stream_round_trip_of_a_full_block(void)
{
    static uint32_t samples[PP_BLOCK_SAMPLES];
    static uint8_t payload[PP_STREAM_PAYLOAD_SIZE(PP_BLOCK_SAMPLES)];
    const pp_stream_header_t header = {
        .first_index = 0xFFFFFF00u, .dropped = 0xFFFFu, .count = PP_BLOCK_SAMPLES};
    for (uint32_t i = 0u; i < PP_BLOCK_SAMPLES; i++) {
        samples[i] = (i * 0x01010101u) ^ 0xDEADBEEFu;
    }
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_OK, pp_stream_encode(&header, samples, payload, sizeof(payload), &len));
    TEST_ASSERT_EQUAL_size_t(sizeof(payload), len);

    pp_stream_header_t decoded;
    const uint8_t *words = NULL;
    TEST_ASSERT_EQUAL(PP_OK, pp_stream_decode(payload, len, &decoded, &words));
    TEST_ASSERT_EQUAL_HEX32(header.first_index, decoded.first_index);
    TEST_ASSERT_EQUAL_UINT16(header.dropped, decoded.dropped);
    TEST_ASSERT_EQUAL_UINT16(header.count, decoded.count);
    for (size_t i = 0u; i < PP_BLOCK_SAMPLES; i++) {
        TEST_ASSERT_EQUAL_HEX32(samples[i], pp_stream_sample(words, i));
    }
}

static void test_stream_encode_accepts_no_samples(void)
{
    const pp_stream_header_t header = {.first_index = 7u, .dropped = 1u, .count = 0u};
    uint8_t out[PP_STREAM_HEADER_SIZE];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_OK, pp_stream_encode(&header, NULL, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL_size_t(PP_STREAM_HEADER_SIZE, len);

    pp_stream_header_t decoded;
    const uint8_t *words = NULL;
    TEST_ASSERT_EQUAL(PP_OK, pp_stream_decode(out, len, &decoded, &words));
    TEST_ASSERT_EQUAL_UINT16(0u, decoded.count);
}

static void test_stream_encode_checks_its_arguments(void)
{
    pp_stream_header_t header = {.first_index = 0u, .dropped = 0u, .count = 1u};
    const uint32_t samples[1] = {0u};
    uint8_t out[PP_STREAM_PAYLOAD_SIZE(1u)];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_stream_encode(NULL, samples, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG,
                      pp_stream_encode(&header, samples, NULL, sizeof(out), &len));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG,
                      pp_stream_encode(&header, samples, out, sizeof(out), NULL));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_stream_encode(&header, NULL, out, sizeof(out), &len));

    header.count = (uint16_t)(PP_STREAM_MAX_SAMPLES + 1u);
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG,
                      pp_stream_encode(&header, samples, out, sizeof(out), &len));
}

static void test_stream_encode_needs_room_for_every_sample(void)
{
    const pp_stream_header_t header = {.first_index = 0u, .dropped = 0u, .count = 1u};
    const uint32_t samples[1] = {0x11223344u};
    uint8_t out[PP_STREAM_PAYLOAD_SIZE(1u)];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_ERR_NO_SPACE,
                      pp_stream_encode(&header, samples, out, sizeof(out) - 1u, &len));
    TEST_ASSERT_EQUAL(PP_OK, pp_stream_encode(&header, samples, out, sizeof(out), &len));
}

static void test_stream_encode_header_checks_its_arguments(void)
{
    pp_stream_header_t header = {.first_index = 0u, .dropped = 0u, .count = 1u};
    uint8_t out[PP_STREAM_HEADER_SIZE];

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_stream_encode_header(NULL, out, sizeof(out)));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_stream_encode_header(&header, NULL, sizeof(out)));
    TEST_ASSERT_EQUAL(PP_ERR_NO_SPACE, pp_stream_encode_header(&header, out, sizeof(out) - 1u));

    header.count = (uint16_t)(PP_STREAM_MAX_SAMPLES + 1u);
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_stream_encode_header(&header, out, sizeof(out)));
}

static void test_stream_decode_checks_its_arguments(void)
{
    pp_stream_header_t header;
    const uint8_t *samples = NULL;
    const uint8_t *payload = stream_vector->payload;
    size_t len = stream_vector->payload_len;

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_stream_decode(NULL, len, &header, &samples));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_stream_decode(payload, len, NULL, &samples));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_stream_decode(payload, len, &header, NULL));
}

static void test_stream_decode_rejects_a_payload_of_the_wrong_length(void)
{
    pp_stream_header_t header;
    const uint8_t *samples = NULL;
    const uint8_t *payload = stream_vector->payload;
    size_t len = stream_vector->payload_len;

    /* Shorter than the header. */
    TEST_ASSERT_EQUAL(PP_ERR_MALFORMED, pp_stream_decode(payload, 7u, &header, &samples));
    /* One sample word missing, one byte missing, one byte too many. */
    TEST_ASSERT_EQUAL(PP_ERR_MALFORMED, pp_stream_decode(payload, len - 4u, &header, &samples));
    TEST_ASSERT_EQUAL(PP_ERR_MALFORMED, pp_stream_decode(payload, len - 1u, &header, &samples));
    uint8_t longer[64];
    memcpy(longer, payload, len);
    longer[len] = 0u;
    TEST_ASSERT_EQUAL(PP_ERR_MALFORMED, pp_stream_decode(longer, len + 1u, &header, &samples));
}

static void test_stream_sample_of_null_is_zero(void)
{
    TEST_ASSERT_EQUAL_HEX32(0u, pp_stream_sample(NULL, 0u));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_stream_sizes);
    RUN_TEST(test_stream_encode_matches_the_shared_vector);
    RUN_TEST(test_stream_decode_matches_the_shared_vector);
    RUN_TEST(test_stream_encode_header_writes_only_the_header);
    RUN_TEST(test_stream_round_trip_of_a_full_block);
    RUN_TEST(test_stream_encode_accepts_no_samples);
    RUN_TEST(test_stream_encode_checks_its_arguments);
    RUN_TEST(test_stream_encode_needs_room_for_every_sample);
    RUN_TEST(test_stream_encode_header_checks_its_arguments);
    RUN_TEST(test_stream_decode_checks_its_arguments);
    RUN_TEST(test_stream_decode_rejects_a_payload_of_the_wrong_length);
    RUN_TEST(test_stream_sample_of_null_is_zero);
    return UNITY_END();
}
