#include "unity.h"

#include "base/pp_status.h"

void setUp(void)
{
}

void tearDown(void)
{
}

static void test_status_ok_is_zero(void)
{
    TEST_ASSERT_EQUAL_INT(0, PP_OK);
}

static void test_status_name_of_every_code(void)
{
    TEST_ASSERT_EQUAL_STRING("PP_OK", pp_status_name(PP_OK));
    TEST_ASSERT_EQUAL_STRING("PP_ERR_INVALID_ARG", pp_status_name(PP_ERR_INVALID_ARG));
    TEST_ASSERT_EQUAL_STRING("PP_ERR_NO_SPACE", pp_status_name(PP_ERR_NO_SPACE));
    TEST_ASSERT_EQUAL_STRING("PP_ERR_EMPTY", pp_status_name(PP_ERR_EMPTY));
    TEST_ASSERT_EQUAL_STRING("PP_ERR_INCOMPLETE", pp_status_name(PP_ERR_INCOMPLETE));
    TEST_ASSERT_EQUAL_STRING("PP_ERR_MALFORMED", pp_status_name(PP_ERR_MALFORMED));
    TEST_ASSERT_EQUAL_STRING("PP_ERR_INVALID_STATE", pp_status_name(PP_ERR_INVALID_STATE));
}

static void test_status_name_of_unknown_code(void)
{
    TEST_ASSERT_EQUAL_STRING("PP_ERR_UNKNOWN", pp_status_name((pp_status_t)1000));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_status_ok_is_zero);
    RUN_TEST(test_status_name_of_every_code);
    RUN_TEST(test_status_name_of_unknown_code);
    return UNITY_END();
}
