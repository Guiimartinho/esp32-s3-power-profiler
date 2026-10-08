#include "unity.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "pp_proto_vectors.h"
#include "proto/pp_command.h"

void setUp(void)
{
}

void tearDown(void)
{
}

/* Payload of the shared frame vector with the given name. */
static const pp_frame_vector_t *find_vector(const char *name)
{
    for (size_t i = 0u; i < PP_FRAME_VECTOR_COUNT; i++) {
        if (strcmp(pp_frame_vectors[i].name, name) == 0) {
            return &pp_frame_vectors[i];
        }
    }
    TEST_FAIL_MESSAGE(name);
    return NULL;
}

/* --- Shared vectors ---------------------------------------------------- */

static void test_command_without_arguments_matches_the_shared_vector(void)
{
    const pp_frame_vector_t *vector = find_vector("command_get_info");
    const pp_command_t command = {.id = PP_CMD_GET_INFO, .args = NULL, .args_len = 0u};
    uint8_t out[8];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_OK, pp_command_encode(&command, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL_size_t(vector->payload_len, len);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(vector->payload, out, len);

    pp_command_t decoded;
    TEST_ASSERT_EQUAL(PP_OK, pp_command_decode(vector->payload, vector->payload_len, &decoded));
    TEST_ASSERT_EQUAL_HEX8(PP_CMD_GET_INFO, decoded.id);
    TEST_ASSERT_EQUAL_size_t(0u, decoded.args_len);
    TEST_ASSERT_NOT_NULL(decoded.args);
}

static void test_command_with_arguments_matches_the_shared_vector(void)
{
    const pp_frame_vector_t *vector = find_vector("command_set_voltage_3300mv");
    const uint8_t args[2] = {0xE4u, 0x0Cu}; /* 3300 mV, little-endian */
    const pp_command_t command = {.id = PP_CMD_SET_VOLTAGE, .args = args, .args_len = 2u};
    uint8_t out[8];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_OK, pp_command_encode(&command, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL_size_t(vector->payload_len, len);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(vector->payload, out, len);

    pp_command_t decoded;
    TEST_ASSERT_EQUAL(PP_OK, pp_command_decode(vector->payload, vector->payload_len, &decoded));
    TEST_ASSERT_EQUAL_HEX8(PP_CMD_SET_VOLTAGE, decoded.id);
    TEST_ASSERT_EQUAL_size_t(2u, decoded.args_len);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(args, decoded.args, 2u);
}

static void test_response_matches_the_shared_vectors(void)
{
    const pp_frame_vector_t *ok = find_vector("response_start_ok");
    const pp_frame_vector_t *refused = find_vector("response_set_mode_wrong_state");
    const pp_response_t start_ok = {.id = PP_CMD_START, .status = PP_PROTO_STATUS_OK};
    const pp_response_t wrong_state = {.id = PP_CMD_SET_MODE,
                                       .status = PP_PROTO_STATUS_WRONG_STATE};
    uint8_t out[8];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_OK, pp_response_encode(&start_ok, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL_size_t(ok->payload_len, len);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(ok->payload, out, len);

    TEST_ASSERT_EQUAL(PP_OK, pp_response_encode(&wrong_state, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL_size_t(refused->payload_len, len);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(refused->payload, out, len);

    pp_response_t decoded;
    TEST_ASSERT_EQUAL(PP_OK, pp_response_decode(refused->payload, refused->payload_len, &decoded));
    TEST_ASSERT_EQUAL_HEX8(PP_CMD_SET_MODE, decoded.id);
    TEST_ASSERT_EQUAL_HEX8(PP_PROTO_STATUS_WRONG_STATE, decoded.status);
    TEST_ASSERT_EQUAL_size_t(0u, decoded.data_len);
}

static void test_event_matches_the_shared_vector(void)
{
    const pp_frame_vector_t *vector = find_vector("event_fault_overcurrent");
    const uint8_t data[2] = {(uint8_t)PP_FAULT_OVERCURRENT, 0x00u}; /* fault flags, little-endian */
    const pp_event_t event = {.id = PP_EVENT_FAULT_RAISED, .data = data, .data_len = 2u};
    uint8_t out[8];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_OK, pp_event_encode(&event, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL_size_t(vector->payload_len, len);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(vector->payload, out, len);

    pp_event_t decoded;
    TEST_ASSERT_EQUAL(PP_OK, pp_event_decode(vector->payload, vector->payload_len, &decoded));
    TEST_ASSERT_EQUAL_HEX8(PP_EVENT_FAULT_RAISED, decoded.id);
    TEST_ASSERT_EQUAL_size_t(2u, decoded.data_len);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(data, decoded.data, 2u);
}

/* --- Limits ------------------------------------------------------------ */

static void test_command_encode_enforces_the_command_payload_limit(void)
{
    static uint8_t args[PP_COMMAND_MAX_PAYLOAD];
    static uint8_t out[PP_COMMAND_MAX_PAYLOAD + 8u];
    pp_command_t command = {.id = PP_CMD_CAL_WRITE, .args = args};
    size_t len = 0u;
    memset(args, 0x3C, sizeof(args));

    command.args_len = PP_COMMAND_MAX_PAYLOAD - PP_COMMAND_HEADER_SIZE;
    TEST_ASSERT_EQUAL(PP_OK, pp_command_encode(&command, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL_size_t(PP_COMMAND_MAX_PAYLOAD, len);

    command.args_len = PP_COMMAND_MAX_PAYLOAD;
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_command_encode(&command, out, sizeof(out), &len));
}

static void test_response_and_event_encode_enforce_the_frame_payload_limit(void)
{
    static uint8_t data[PP_FRAME_MAX_PAYLOAD];
    static uint8_t out[PP_FRAME_MAX_PAYLOAD + 8u];
    pp_response_t response = {.id = PP_CMD_GET_INFO, .status = PP_PROTO_STATUS_OK, .data = data};
    pp_event_t event = {.id = PP_EVENT_STATE_CHANGED, .data = data};
    size_t len = 0u;
    memset(data, 0x3C, sizeof(data));

    response.data_len = PP_FRAME_MAX_PAYLOAD - PP_RESPONSE_HEADER_SIZE;
    TEST_ASSERT_EQUAL(PP_OK, pp_response_encode(&response, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL_size_t(PP_FRAME_MAX_PAYLOAD, len);
    response.data_len++;
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_response_encode(&response, out, sizeof(out), &len));

    event.data_len = PP_FRAME_MAX_PAYLOAD - PP_EVENT_HEADER_SIZE;
    TEST_ASSERT_EQUAL(PP_OK, pp_event_encode(&event, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL_size_t(PP_FRAME_MAX_PAYLOAD, len);
    event.data_len++;
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_event_encode(&event, out, sizeof(out), &len));
}

static void test_encoders_need_room_for_the_whole_payload(void)
{
    const uint8_t body[3] = {1u, 2u, 3u};
    const pp_command_t command = {.id = PP_CMD_SET_RANGE, .args = body, .args_len = 3u};
    const pp_response_t response = {.id = PP_CMD_GET_STATUS, .data = body, .data_len = 3u};
    const pp_event_t event = {.id = PP_EVENT_STATE_CHANGED, .data = body, .data_len = 3u};
    uint8_t out[8];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_ERR_NO_SPACE, pp_command_encode(&command, out, 3u, &len));
    TEST_ASSERT_EQUAL(PP_OK, pp_command_encode(&command, out, 4u, &len));
    TEST_ASSERT_EQUAL(PP_ERR_NO_SPACE, pp_response_encode(&response, out, 4u, &len));
    TEST_ASSERT_EQUAL(PP_OK, pp_response_encode(&response, out, 5u, &len));
    TEST_ASSERT_EQUAL(PP_ERR_NO_SPACE, pp_event_encode(&event, out, 3u, &len));
    TEST_ASSERT_EQUAL(PP_OK, pp_event_encode(&event, out, 4u, &len));
}

/* --- Argument checks --------------------------------------------------- */

static void test_encoders_check_their_arguments(void)
{
    const uint8_t body[1] = {0u};
    pp_command_t command = {.id = PP_CMD_START, .args = body, .args_len = 1u};
    pp_response_t response = {.id = PP_CMD_START, .data = body, .data_len = 1u};
    pp_event_t event = {.id = PP_EVENT_STATE_CHANGED, .data = body, .data_len = 1u};
    uint8_t out[8];
    size_t len = 0u;

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_command_encode(NULL, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_command_encode(&command, NULL, sizeof(out), &len));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_command_encode(&command, out, sizeof(out), NULL));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_response_encode(NULL, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_event_encode(NULL, out, sizeof(out), &len));

    /* A length without a pointer. */
    command.args = NULL;
    response.data = NULL;
    event.data = NULL;
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_command_encode(&command, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_response_encode(&response, out, sizeof(out), &len));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_event_encode(&event, out, sizeof(out), &len));
}

static void test_decoders_check_their_arguments(void)
{
    const uint8_t payload[2] = {0x20u, 0x00u};
    pp_command_t command;
    pp_response_t response;
    pp_event_t event;

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_command_decode(NULL, 2u, &command));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_command_decode(payload, 2u, NULL));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_response_decode(NULL, 2u, &response));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_response_decode(payload, 2u, NULL));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_event_decode(NULL, 2u, &event));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_event_decode(payload, 2u, NULL));
}

static void test_decoders_reject_a_payload_shorter_than_the_envelope(void)
{
    const uint8_t payload[2] = {0x20u, 0x00u};
    pp_command_t command;
    pp_response_t response;
    pp_event_t event;

    TEST_ASSERT_EQUAL(PP_ERR_MALFORMED, pp_command_decode(payload, 0u, &command));
    TEST_ASSERT_EQUAL(PP_ERR_MALFORMED, pp_response_decode(payload, 1u, &response));
    TEST_ASSERT_EQUAL(PP_ERR_MALFORMED, pp_event_decode(payload, 0u, &event));
}

static void test_decoders_reject_a_payload_above_the_limit(void)
{
    static uint8_t payload[PP_FRAME_MAX_PAYLOAD + 1u];
    pp_command_t command;
    pp_response_t response;
    pp_event_t event;

    TEST_ASSERT_EQUAL(PP_OK, pp_command_decode(payload, PP_COMMAND_MAX_PAYLOAD, &command));
    TEST_ASSERT_EQUAL(PP_ERR_MALFORMED,
                      pp_command_decode(payload, PP_COMMAND_MAX_PAYLOAD + 1u, &command));
    TEST_ASSERT_EQUAL(PP_OK, pp_response_decode(payload, PP_FRAME_MAX_PAYLOAD, &response));
    TEST_ASSERT_EQUAL(PP_ERR_MALFORMED,
                      pp_response_decode(payload, PP_FRAME_MAX_PAYLOAD + 1u, &response));
    TEST_ASSERT_EQUAL(PP_OK, pp_event_decode(payload, PP_FRAME_MAX_PAYLOAD, &event));
    TEST_ASSERT_EQUAL(PP_ERR_MALFORMED,
                      pp_event_decode(payload, PP_FRAME_MAX_PAYLOAD + 1u, &event));
}

/* --- Known identifiers ------------------------------------------------- */

static void test_command_decode_accepts_an_unknown_id(void)
{
    const uint8_t payload[1] = {0xEEu};
    pp_command_t command;

    TEST_ASSERT_EQUAL(PP_OK, pp_command_decode(payload, sizeof(payload), &command));
    TEST_ASSERT_EQUAL_HEX8(0xEEu, command.id);
    TEST_ASSERT_FALSE(pp_command_is_known(command.id));
}

static void test_command_is_known_for_every_command_of_the_definition(void)
{
    const pp_command_id_t known[] = {
        PP_CMD_GET_INFO,  PP_CMD_GET_STATUS, PP_CMD_SET_MODE,   PP_CMD_SET_VOLTAGE,
        PP_CMD_DUT_POWER, PP_CMD_SET_RANGE,  PP_CMD_SET_DOWN_N, PP_CMD_START,
        PP_CMD_STOP,      PP_CMD_CAL_ZERO,   PP_CMD_CAL_WRITE,  PP_CMD_CLEAR_FAULT,
    };
    size_t known_count = sizeof(known) / sizeof(known[0]);
    size_t accepted = 0u;

    for (size_t i = 0u; i < known_count; i++) {
        TEST_ASSERT_TRUE(pp_command_is_known((uint8_t)known[i]));
    }
    /* Nothing else is accepted. */
    for (unsigned id = 0u; id <= 0xFFu; id++) {
        if (pp_command_is_known((uint8_t)id)) {
            accepted++;
        }
    }
    TEST_ASSERT_EQUAL_size_t(known_count, accepted);
}

static void test_event_is_known_for_every_event_of_the_definition(void)
{
    const pp_event_id_t known[] = {
        PP_EVENT_FAULT_RAISED,
        PP_EVENT_POWER_BUDGET_CHANGED,
        PP_EVENT_STATE_CHANGED,
    };
    size_t known_count = sizeof(known) / sizeof(known[0]);
    size_t accepted = 0u;

    for (size_t i = 0u; i < known_count; i++) {
        TEST_ASSERT_TRUE(pp_event_is_known((uint8_t)known[i]));
    }
    for (unsigned id = 0u; id <= 0xFFu; id++) {
        if (pp_event_is_known((uint8_t)id)) {
            accepted++;
        }
    }
    TEST_ASSERT_EQUAL_size_t(known_count, accepted);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_command_without_arguments_matches_the_shared_vector);
    RUN_TEST(test_command_with_arguments_matches_the_shared_vector);
    RUN_TEST(test_response_matches_the_shared_vectors);
    RUN_TEST(test_event_matches_the_shared_vector);
    RUN_TEST(test_command_encode_enforces_the_command_payload_limit);
    RUN_TEST(test_response_and_event_encode_enforce_the_frame_payload_limit);
    RUN_TEST(test_encoders_need_room_for_the_whole_payload);
    RUN_TEST(test_encoders_check_their_arguments);
    RUN_TEST(test_decoders_check_their_arguments);
    RUN_TEST(test_decoders_reject_a_payload_shorter_than_the_envelope);
    RUN_TEST(test_decoders_reject_a_payload_above_the_limit);
    RUN_TEST(test_command_decode_accepts_an_unknown_id);
    RUN_TEST(test_command_is_known_for_every_command_of_the_definition);
    RUN_TEST(test_event_is_known_for_every_event_of_the_definition);
    return UNITY_END();
}
