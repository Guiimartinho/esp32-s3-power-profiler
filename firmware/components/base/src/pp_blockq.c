#include "base/pp_blockq.h"

#include <string.h>

/*
 * The head and tail counters run freely and wrap with the width of size_t.
 * Because the capacity is a power of two, "head - tail" is the fill level and
 * "counter & (capacity - 1)" is the slot, across the wrap as well.
 *
 * Memory ordering: a side reads its own counter relaxed, because nobody else
 * writes it. It reads the other counter with acquire and publishes its own
 * with release, so the block contents written before the store are visible to
 * the side that observes the new counter.
 */

static bool is_power_of_two(size_t value)
{
    return (value != 0u) && ((value & (value - 1u)) == 0u);
}

static uint8_t *slot_address(const pp_blockq_t *queue, size_t counter)
{
    return queue->storage + ((counter & (queue->capacity - 1u)) * queue->block_size);
}

pp_status_t pp_blockq_init(pp_blockq_t *queue, void *storage, size_t storage_size,
                           size_t block_size, size_t capacity)
{
    if ((queue == NULL) || (storage == NULL) || (block_size == 0u) || !is_power_of_two(capacity)) {
        return PP_ERR_INVALID_ARG;
    }
    if (capacity > (SIZE_MAX / block_size)) {
        return PP_ERR_INVALID_ARG;
    }
    if ((capacity * block_size) > storage_size) {
        return PP_ERR_NO_SPACE;
    }

    queue->storage = storage;
    queue->block_size = block_size;
    queue->capacity = capacity;
    atomic_init(&queue->head, 0u);
    atomic_init(&queue->tail, 0u);
    atomic_init(&queue->dropped, 0u);
    queue->dropped_seen = 0u;
    queue->reserved = false;
    return PP_OK;
}

size_t pp_blockq_count(const pp_blockq_t *queue)
{
    if (queue == NULL) {
        return 0u;
    }
    size_t tail = atomic_load_explicit(&queue->tail, memory_order_acquire);
    size_t head = atomic_load_explicit(&queue->head, memory_order_acquire);
    return head - tail;
}

uint32_t pp_blockq_dropped_total(const pp_blockq_t *queue)
{
    if (queue == NULL) {
        return 0u;
    }
    return (uint32_t)atomic_load_explicit(&queue->dropped, memory_order_relaxed);
}

void *pp_blockq_reserve(pp_blockq_t *queue)
{
    if (queue == NULL) {
        return NULL;
    }
    size_t head = atomic_load_explicit(&queue->head, memory_order_relaxed);
    size_t tail = atomic_load_explicit(&queue->tail, memory_order_acquire);
    if ((head - tail) == queue->capacity) {
        atomic_fetch_add_explicit(&queue->dropped, 1u, memory_order_relaxed);
        return NULL;
    }
    queue->reserved = true;
    return slot_address(queue, head);
}

pp_status_t pp_blockq_commit(pp_blockq_t *queue)
{
    if (queue == NULL) {
        return PP_ERR_INVALID_ARG;
    }
    if (!queue->reserved) {
        return PP_ERR_INVALID_STATE;
    }
    queue->reserved = false;
    size_t head = atomic_load_explicit(&queue->head, memory_order_relaxed);
    atomic_store_explicit(&queue->head, head + 1u, memory_order_release);
    return PP_OK;
}

pp_status_t pp_blockq_push(pp_blockq_t *queue, const void *block)
{
    if ((queue == NULL) || (block == NULL)) {
        return PP_ERR_INVALID_ARG;
    }
    void *slot = pp_blockq_reserve(queue);
    if (slot == NULL) {
        return PP_ERR_NO_SPACE;
    }
    memcpy(slot, block, queue->block_size);
    return pp_blockq_commit(queue);
}

const void *pp_blockq_peek(const pp_blockq_t *queue)
{
    if (queue == NULL) {
        return NULL;
    }
    size_t tail = atomic_load_explicit(&queue->tail, memory_order_relaxed);
    size_t head = atomic_load_explicit(&queue->head, memory_order_acquire);
    if (head == tail) {
        return NULL;
    }
    return slot_address(queue, tail);
}

pp_status_t pp_blockq_release(pp_blockq_t *queue)
{
    if (queue == NULL) {
        return PP_ERR_INVALID_ARG;
    }
    size_t tail = atomic_load_explicit(&queue->tail, memory_order_relaxed);
    size_t head = atomic_load_explicit(&queue->head, memory_order_acquire);
    if (head == tail) {
        return PP_ERR_EMPTY;
    }
    atomic_store_explicit(&queue->tail, tail + 1u, memory_order_release);
    return PP_OK;
}

pp_status_t pp_blockq_pop(pp_blockq_t *queue, void *block)
{
    if ((queue == NULL) || (block == NULL)) {
        return PP_ERR_INVALID_ARG;
    }
    const void *slot = pp_blockq_peek(queue);
    if (slot == NULL) {
        return PP_ERR_EMPTY;
    }
    memcpy(block, slot, queue->block_size);
    return pp_blockq_release(queue);
}

uint32_t pp_blockq_take_dropped(pp_blockq_t *queue)
{
    if (queue == NULL) {
        return 0u;
    }
    uint32_t total = (uint32_t)atomic_load_explicit(&queue->dropped, memory_order_relaxed);
    uint32_t fresh = total - queue->dropped_seen;
    queue->dropped_seen = total;
    return fresh;
}
