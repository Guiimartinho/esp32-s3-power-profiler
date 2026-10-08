/*
 * Single-producer, single-consumer queue of fixed-size blocks.
 *
 * The acquisition task on one core produces blocks and the streaming task on
 * the other core consumes them. No lock is taken: each index has exactly one
 * writer, and the other side only reads it. The producer never waits. When
 * the queue is full the block is refused and counted as a drop, as required
 * by section 6.3 of the specification.
 *
 * Rules for the caller:
 * - Only one task calls the producer functions and only one task calls the
 *   consumer functions.
 * - The caller owns the storage and keeps it alive while the queue is in use.
 * - The capacity is a power of two.
 */
#ifndef PP_BLOCKQ_H
#define PP_BLOCKQ_H

#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "base/pp_status.h"

typedef struct {
    uint8_t *storage;              /* capacity * block_size bytes, owned by the caller */
    size_t block_size;             /* bytes in one block */
    size_t capacity;               /* blocks the queue can hold, a power of two */
    atomic_size_t head;            /* blocks published so far; written by the producer */
    atomic_size_t tail;            /* blocks consumed so far; written by the consumer */
    atomic_uint_least32_t dropped; /* blocks refused so far; written by the producer */
    uint32_t dropped_seen;         /* drops already reported; used by the consumer only */
    bool reserved;                 /* a reservation is open; used by the producer only */
} pp_blockq_t;

/*
 * Prepare a queue. The storage must hold at least capacity * block_size
 * bytes. Returns PP_ERR_INVALID_ARG for a NULL pointer, a zero block size or
 * a capacity that is not a power of two, and PP_ERR_NO_SPACE when the storage
 * is too small.
 */
pp_status_t pp_blockq_init(pp_blockq_t *queue, void *storage, size_t storage_size,
                           size_t block_size, size_t capacity);

/* Blocks waiting in the queue. A snapshot: the other side may change it. */
size_t pp_blockq_count(const pp_blockq_t *queue);

/* Blocks refused since pp_blockq_init(). */
uint32_t pp_blockq_dropped_total(const pp_blockq_t *queue);

/* --- Producer side ----------------------------------------------------- */

/*
 * Copy one block into the queue. Returns PP_ERR_NO_SPACE and counts a drop
 * when the queue is full.
 */
pp_status_t pp_blockq_push(pp_blockq_t *queue, const void *block);

/*
 * Zero-copy variant of pp_blockq_push(). Returns the address where the next
 * block must be written, or NULL when the queue is full, in which case a drop
 * is counted. The block becomes visible to the consumer on pp_blockq_commit().
 */
void *pp_blockq_reserve(pp_blockq_t *queue);

/*
 * Publish the block written after pp_blockq_reserve(). Returns
 * PP_ERR_INVALID_STATE when no reservation is open.
 */
pp_status_t pp_blockq_commit(pp_blockq_t *queue);

/* --- Consumer side ----------------------------------------------------- */

/* Copy the oldest block out of the queue. Returns PP_ERR_EMPTY when empty. */
pp_status_t pp_blockq_pop(pp_blockq_t *queue, void *block);

/*
 * Zero-copy variant of pp_blockq_pop(). Returns the address of the oldest
 * block, or NULL when the queue is empty. The block stays in the queue until
 * pp_blockq_release().
 */
const void *pp_blockq_peek(const pp_blockq_t *queue);

/* Remove the oldest block. Returns PP_ERR_EMPTY when the queue is empty. */
pp_status_t pp_blockq_release(pp_blockq_t *queue);

/*
 * Blocks refused since the previous call. The stream frame reports this
 * number in its "dropped" field.
 */
uint32_t pp_blockq_take_dropped(pp_blockq_t *queue);

#endif /* PP_BLOCKQ_H */
