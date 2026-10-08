/*
 * The block queue under two real threads.
 *
 * A producer pushes numbered blocks as fast as it can and never waits, like
 * the acquisition task. A consumer pops them, like the streaming task. The
 * test checks what the lock-free design promises: every block that arrives
 * is intact, the blocks arrive in order, and each block was either delivered
 * or counted as dropped.
 */
#include "unity.h"

#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include "base/pp_blockq.h"

#define WORDS_PER_BLOCK 16u
#define CAPACITY 8u
#define BLOCKS_TO_PRODUCE 200000u

typedef struct {
    uint32_t words[WORDS_PER_BLOCK];
} block_t;

static block_t storage[CAPACITY];
static pp_blockq_t queue;
static atomic_bool producer_done;

/* Results of the consumer thread, read after it has been joined. */
static uint32_t received;
static uint32_t torn_blocks;
static uint32_t out_of_order;

void setUp(void)
{
}

void tearDown(void)
{
}

static void *producer(void *arg)
{
    (void)arg;
    for (uint32_t number = 1u; number <= BLOCKS_TO_PRODUCE; number++) {
        block_t block;
        for (size_t i = 0u; i < WORDS_PER_BLOCK; i++) {
            block.words[i] = number;
        }
        (void)pp_blockq_push(&queue, &block);
    }
    atomic_store(&producer_done, true);
    return NULL;
}

static void check_block(const block_t *block, uint32_t *last_number)
{
    uint32_t number = block->words[0];
    for (size_t i = 1u; i < WORDS_PER_BLOCK; i++) {
        if (block->words[i] != number) {
            torn_blocks++;
            return;
        }
    }
    if (number <= *last_number) {
        out_of_order++;
    }
    *last_number = number;
    received++;
}

static void *consumer(void *arg)
{
    (void)arg;
    uint32_t last_number = 0u;
    block_t block;

    for (;;) {
        /* Read the flag first: a block pushed before it was set is still seen. */
        bool done = atomic_load(&producer_done);
        if (pp_blockq_pop(&queue, &block) == PP_OK) {
            check_block(&block, &last_number);
        } else if (done) {
            break;
        }
    }
    return NULL;
}

static void test_blockq_threads_deliver_or_count_every_block(void)
{
    pthread_t producer_thread;
    pthread_t consumer_thread;

    TEST_ASSERT_EQUAL(PP_OK,
                      pp_blockq_init(&queue, storage, sizeof(storage), sizeof(block_t), CAPACITY));
    atomic_store(&producer_done, false);
    received = 0u;
    torn_blocks = 0u;
    out_of_order = 0u;

    TEST_ASSERT_EQUAL_INT(0, pthread_create(&consumer_thread, NULL, consumer, NULL));
    TEST_ASSERT_EQUAL_INT(0, pthread_create(&producer_thread, NULL, producer, NULL));
    TEST_ASSERT_EQUAL_INT(0, pthread_join(producer_thread, NULL));
    TEST_ASSERT_EQUAL_INT(0, pthread_join(consumer_thread, NULL));

    TEST_ASSERT_EQUAL_UINT32(0u, torn_blocks);
    TEST_ASSERT_EQUAL_UINT32(0u, out_of_order);
    TEST_ASSERT_EQUAL_UINT32(BLOCKS_TO_PRODUCE, received + pp_blockq_dropped_total(&queue));
    TEST_ASSERT_EQUAL_size_t(0u, pp_blockq_count(&queue));
    /* The run only means something if blocks actually crossed the queue. */
    TEST_ASSERT_GREATER_THAN_UINT32(0u, received);

    char report[80];
    (void)snprintf(report, sizeof(report), "delivered %lu blocks, dropped %lu",
                   (unsigned long)received, (unsigned long)pp_blockq_dropped_total(&queue));
    TEST_MESSAGE(report);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_blockq_threads_deliver_or_count_every_block);
    return UNITY_END();
}
