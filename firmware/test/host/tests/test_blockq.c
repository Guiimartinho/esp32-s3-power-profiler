#include "unity.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "base/pp_blockq.h"

#define BLOCK_SIZE 16u
#define CAPACITY 4u

static uint8_t storage[BLOCK_SIZE * CAPACITY];
static pp_blockq_t queue;

/* A block whose every byte is the tag, so mixed-up blocks are easy to spot. */
static void make_block(uint8_t *block, uint8_t tag)
{
    memset(block, tag, BLOCK_SIZE);
}

static void assert_block_is(const uint8_t *block, uint8_t tag)
{
    uint8_t expected[BLOCK_SIZE];
    make_block(expected, tag);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(expected, block, BLOCK_SIZE);
}

static void push_tagged(uint8_t tag, pp_status_t expected)
{
    uint8_t block[BLOCK_SIZE];
    make_block(block, tag);
    TEST_ASSERT_EQUAL(expected, pp_blockq_push(&queue, block));
}

static void pop_expecting(uint8_t tag)
{
    uint8_t block[BLOCK_SIZE];
    memset(block, 0, sizeof(block));
    TEST_ASSERT_EQUAL(PP_OK, pp_blockq_pop(&queue, block));
    assert_block_is(block, tag);
}

void setUp(void)
{
    memset(storage, 0, sizeof(storage));
    TEST_ASSERT_EQUAL(PP_OK,
                      pp_blockq_init(&queue, storage, sizeof(storage), BLOCK_SIZE, CAPACITY));
}

void tearDown(void)
{
}

/* --- Initialization ---------------------------------------------------- */

static void test_blockq_init_rejects_null_pointers(void)
{
    pp_blockq_t q;

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG,
                      pp_blockq_init(NULL, storage, sizeof(storage), BLOCK_SIZE, CAPACITY));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG,
                      pp_blockq_init(&q, NULL, sizeof(storage), BLOCK_SIZE, CAPACITY));
}

static void test_blockq_init_rejects_zero_block_size(void)
{
    pp_blockq_t q;

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG,
                      pp_blockq_init(&q, storage, sizeof(storage), 0u, CAPACITY));
}

static void test_blockq_init_rejects_capacity_that_is_not_a_power_of_two(void)
{
    pp_blockq_t q;
    const size_t bad[] = {0u, 3u, 5u, 6u, 7u, 12u};

    for (size_t i = 0u; i < (sizeof(bad) / sizeof(bad[0])); i++) {
        TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG,
                          pp_blockq_init(&q, storage, sizeof(storage), 1u, bad[i]));
    }
}

static void test_blockq_init_rejects_size_overflow(void)
{
    pp_blockq_t q;
    size_t huge = (SIZE_MAX / 2u) + 1u; /* a power of two */

    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_blockq_init(&q, storage, SIZE_MAX, 4u, huge));
}

static void test_blockq_init_rejects_storage_that_is_too_small(void)
{
    pp_blockq_t q;

    TEST_ASSERT_EQUAL(PP_ERR_NO_SPACE,
                      pp_blockq_init(&q, storage, sizeof(storage) - 1u, BLOCK_SIZE, CAPACITY));
}

static void test_blockq_init_accepts_a_single_block(void)
{
    pp_blockq_t q;
    uint8_t one[BLOCK_SIZE];
    uint8_t block[BLOCK_SIZE];

    TEST_ASSERT_EQUAL(PP_OK, pp_blockq_init(&q, one, sizeof(one), BLOCK_SIZE, 1u));
    make_block(block, 0x11u);
    TEST_ASSERT_EQUAL(PP_OK, pp_blockq_push(&q, block));
    TEST_ASSERT_EQUAL(PP_ERR_NO_SPACE, pp_blockq_push(&q, block));
    TEST_ASSERT_EQUAL(PP_OK, pp_blockq_pop(&q, block));
    TEST_ASSERT_EQUAL(PP_ERR_EMPTY, pp_blockq_pop(&q, block));
}

/* --- Empty queue ------------------------------------------------------- */

static void test_blockq_new_queue_is_empty(void)
{
    uint8_t block[BLOCK_SIZE];

    TEST_ASSERT_EQUAL_size_t(0u, pp_blockq_count(&queue));
    TEST_ASSERT_EQUAL_UINT32(0u, pp_blockq_dropped_total(&queue));
    TEST_ASSERT_EQUAL_UINT32(0u, pp_blockq_take_dropped(&queue));
    TEST_ASSERT_NULL(pp_blockq_peek(&queue));
    TEST_ASSERT_EQUAL(PP_ERR_EMPTY, pp_blockq_pop(&queue, block));
    TEST_ASSERT_EQUAL(PP_ERR_EMPTY, pp_blockq_release(&queue));
}

/* --- Order and capacity ------------------------------------------------ */

static void test_blockq_delivers_blocks_in_order(void)
{
    push_tagged(0x01u, PP_OK);
    push_tagged(0x02u, PP_OK);
    push_tagged(0x03u, PP_OK);
    TEST_ASSERT_EQUAL_size_t(3u, pp_blockq_count(&queue));

    pop_expecting(0x01u);
    pop_expecting(0x02u);
    pop_expecting(0x03u);
    TEST_ASSERT_EQUAL_size_t(0u, pp_blockq_count(&queue));
}

static void test_blockq_holds_exactly_its_capacity(void)
{
    for (uint8_t i = 0u; i < CAPACITY; i++) {
        push_tagged((uint8_t)(0x10u + i), PP_OK);
    }
    TEST_ASSERT_EQUAL_size_t(CAPACITY, pp_blockq_count(&queue));

    for (uint8_t i = 0u; i < CAPACITY; i++) {
        pop_expecting((uint8_t)(0x10u + i));
    }
}

static void test_blockq_refuses_and_counts_a_push_when_full(void)
{
    for (uint8_t i = 0u; i < CAPACITY; i++) {
        push_tagged(i, PP_OK);
    }

    push_tagged(0xAAu, PP_ERR_NO_SPACE);
    push_tagged(0xBBu, PP_ERR_NO_SPACE);

    TEST_ASSERT_EQUAL_UINT32(2u, pp_blockq_dropped_total(&queue));
    TEST_ASSERT_EQUAL_size_t(CAPACITY, pp_blockq_count(&queue));
    /* The blocks already queued are untouched. */
    for (uint8_t i = 0u; i < CAPACITY; i++) {
        pop_expecting(i);
    }
}

static void test_blockq_accepts_blocks_again_after_a_pop(void)
{
    for (uint8_t i = 0u; i < CAPACITY; i++) {
        push_tagged(i, PP_OK);
    }
    push_tagged(0xAAu, PP_ERR_NO_SPACE);

    pop_expecting(0u);
    push_tagged(0x55u, PP_OK);

    pop_expecting(1u);
    pop_expecting(2u);
    pop_expecting(3u);
    pop_expecting(0x55u);
}

static void test_blockq_keeps_order_over_many_wraps(void)
{
    uint8_t next_in = 0u;
    uint8_t next_out = 0u;

    for (unsigned round = 0u; round < 100u; round++) {
        /* Uneven bursts move the indices through every slot alignment. */
        unsigned burst = (round % CAPACITY) + 1u;
        for (unsigned i = 0u; i < burst; i++) {
            push_tagged(next_in, PP_OK);
            next_in++;
        }
        for (unsigned i = 0u; i < burst; i++) {
            pop_expecting(next_out);
            next_out++;
        }
    }
    TEST_ASSERT_EQUAL_UINT32(0u, pp_blockq_dropped_total(&queue));
}

static void test_blockq_works_across_the_counter_wrap(void)
{
    /* Start just before the counters overflow, as after weeks of operation. */
    atomic_store(&queue.head, SIZE_MAX - 1u);
    atomic_store(&queue.tail, SIZE_MAX - 1u);

    for (uint8_t i = 0u; i < CAPACITY; i++) {
        push_tagged((uint8_t)(0x40u + i), PP_OK);
    }
    push_tagged(0xEEu, PP_ERR_NO_SPACE);
    TEST_ASSERT_EQUAL_size_t(CAPACITY, pp_blockq_count(&queue));

    for (uint8_t i = 0u; i < CAPACITY; i++) {
        pop_expecting((uint8_t)(0x40u + i));
    }
    TEST_ASSERT_EQUAL_size_t(0u, pp_blockq_count(&queue));
    TEST_ASSERT_NULL(pp_blockq_peek(&queue));
}

/* --- Drop accounting --------------------------------------------------- */

static void test_blockq_take_dropped_reports_only_new_drops(void)
{
    for (uint8_t i = 0u; i < CAPACITY; i++) {
        push_tagged(i, PP_OK);
    }
    push_tagged(0xAAu, PP_ERR_NO_SPACE);
    push_tagged(0xAAu, PP_ERR_NO_SPACE);
    push_tagged(0xAAu, PP_ERR_NO_SPACE);

    TEST_ASSERT_EQUAL_UINT32(3u, pp_blockq_take_dropped(&queue));
    TEST_ASSERT_EQUAL_UINT32(0u, pp_blockq_take_dropped(&queue));

    push_tagged(0xAAu, PP_ERR_NO_SPACE);
    TEST_ASSERT_EQUAL_UINT32(1u, pp_blockq_take_dropped(&queue));
    TEST_ASSERT_EQUAL_UINT32(4u, pp_blockq_dropped_total(&queue));
}

/* --- Zero-copy producer ------------------------------------------------ */

static void test_blockq_reserved_block_is_hidden_until_commit(void)
{
    uint8_t *slot = pp_blockq_reserve(&queue);
    TEST_ASSERT_NOT_NULL(slot);
    make_block(slot, 0x77u);

    TEST_ASSERT_EQUAL_size_t(0u, pp_blockq_count(&queue));
    TEST_ASSERT_NULL(pp_blockq_peek(&queue));

    TEST_ASSERT_EQUAL(PP_OK, pp_blockq_commit(&queue));
    TEST_ASSERT_EQUAL_size_t(1u, pp_blockq_count(&queue));
    pop_expecting(0x77u);
}

static void test_blockq_reserve_twice_returns_the_same_slot(void)
{
    void *first = pp_blockq_reserve(&queue);
    void *second = pp_blockq_reserve(&queue);

    TEST_ASSERT_NOT_NULL(first);
    TEST_ASSERT_EQUAL_PTR(first, second);
    TEST_ASSERT_EQUAL(PP_OK, pp_blockq_commit(&queue));
    TEST_ASSERT_EQUAL_size_t(1u, pp_blockq_count(&queue));
}

static void test_blockq_commit_without_reserve_is_rejected(void)
{
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_STATE, pp_blockq_commit(&queue));

    TEST_ASSERT_NOT_NULL(pp_blockq_reserve(&queue));
    TEST_ASSERT_EQUAL(PP_OK, pp_blockq_commit(&queue));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_STATE, pp_blockq_commit(&queue));
    TEST_ASSERT_EQUAL_size_t(1u, pp_blockq_count(&queue));
}

static void test_blockq_reserve_on_a_full_queue_counts_a_drop(void)
{
    for (uint8_t i = 0u; i < CAPACITY; i++) {
        push_tagged(i, PP_OK);
    }

    TEST_ASSERT_NULL(pp_blockq_reserve(&queue));
    TEST_ASSERT_EQUAL_UINT32(1u, pp_blockq_dropped_total(&queue));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_STATE, pp_blockq_commit(&queue));
}

/* --- Zero-copy consumer ------------------------------------------------ */

static void test_blockq_peek_leaves_the_block_in_the_queue(void)
{
    push_tagged(0x21u, PP_OK);
    push_tagged(0x22u, PP_OK);

    const uint8_t *first = pp_blockq_peek(&queue);
    TEST_ASSERT_NOT_NULL(first);
    assert_block_is(first, 0x21u);
    TEST_ASSERT_EQUAL_PTR(first, pp_blockq_peek(&queue));
    TEST_ASSERT_EQUAL_size_t(2u, pp_blockq_count(&queue));

    TEST_ASSERT_EQUAL(PP_OK, pp_blockq_release(&queue));
    const uint8_t *second = pp_blockq_peek(&queue);
    TEST_ASSERT_NOT_NULL(second);
    assert_block_is(second, 0x22u);
    TEST_ASSERT_EQUAL(PP_OK, pp_blockq_release(&queue));
    TEST_ASSERT_EQUAL(PP_ERR_EMPTY, pp_blockq_release(&queue));
}

/* --- Argument checks --------------------------------------------------- */

static void test_blockq_functions_tolerate_a_null_queue(void)
{
    uint8_t block[BLOCK_SIZE];
    make_block(block, 0u);

    TEST_ASSERT_EQUAL_size_t(0u, pp_blockq_count(NULL));
    TEST_ASSERT_EQUAL_UINT32(0u, pp_blockq_dropped_total(NULL));
    TEST_ASSERT_EQUAL_UINT32(0u, pp_blockq_take_dropped(NULL));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_blockq_push(NULL, block));
    TEST_ASSERT_NULL(pp_blockq_reserve(NULL));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_blockq_commit(NULL));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_blockq_pop(NULL, block));
    TEST_ASSERT_NULL(pp_blockq_peek(NULL));
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_blockq_release(NULL));
}

static void test_blockq_push_and_pop_reject_a_null_block(void)
{
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_blockq_push(&queue, NULL));
    push_tagged(0x01u, PP_OK);
    TEST_ASSERT_EQUAL(PP_ERR_INVALID_ARG, pp_blockq_pop(&queue, NULL));
    TEST_ASSERT_EQUAL_size_t(1u, pp_blockq_count(&queue));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_blockq_init_rejects_null_pointers);
    RUN_TEST(test_blockq_init_rejects_zero_block_size);
    RUN_TEST(test_blockq_init_rejects_capacity_that_is_not_a_power_of_two);
    RUN_TEST(test_blockq_init_rejects_size_overflow);
    RUN_TEST(test_blockq_init_rejects_storage_that_is_too_small);
    RUN_TEST(test_blockq_init_accepts_a_single_block);
    RUN_TEST(test_blockq_new_queue_is_empty);
    RUN_TEST(test_blockq_delivers_blocks_in_order);
    RUN_TEST(test_blockq_holds_exactly_its_capacity);
    RUN_TEST(test_blockq_refuses_and_counts_a_push_when_full);
    RUN_TEST(test_blockq_accepts_blocks_again_after_a_pop);
    RUN_TEST(test_blockq_keeps_order_over_many_wraps);
    RUN_TEST(test_blockq_works_across_the_counter_wrap);
    RUN_TEST(test_blockq_take_dropped_reports_only_new_drops);
    RUN_TEST(test_blockq_reserved_block_is_hidden_until_commit);
    RUN_TEST(test_blockq_reserve_twice_returns_the_same_slot);
    RUN_TEST(test_blockq_commit_without_reserve_is_rejected);
    RUN_TEST(test_blockq_reserve_on_a_full_queue_counts_a_drop);
    RUN_TEST(test_blockq_peek_leaves_the_block_in_the_queue);
    RUN_TEST(test_blockq_functions_tolerate_a_null_queue);
    RUN_TEST(test_blockq_push_and_pop_reject_a_null_block);
    return UNITY_END();
}
