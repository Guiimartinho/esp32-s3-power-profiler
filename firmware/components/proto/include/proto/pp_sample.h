/*
 * The 32-bit sample word (section 7.3 of the specification).
 *
 * Every sample carries its own context: the raw ADC code, the range that was
 * active, whether the sample falls in the settling window of a range change,
 * the fault latch and the eight logic inputs. Field positions come from
 * pp_proto_defs.h.
 *
 * These functions run once per sample in the acquisition path, so they are
 * inline and free of branches.
 */
#ifndef PP_SAMPLE_H
#define PP_SAMPLE_H

#include <stdbool.h>
#include <stdint.h>

#include "proto/pp_proto_defs.h"

/* The flag bits in their position inside the word. */
#define PP_SAMPLE_INVALID_BIT ((uint32_t)PP_SAMPLE_INVALID_MASK << PP_SAMPLE_INVALID_SHIFT)
#define PP_SAMPLE_FAULT_BIT ((uint32_t)PP_SAMPLE_FAULT_MASK << PP_SAMPLE_FAULT_SHIFT)

typedef struct {
    uint16_t adc;  /* raw ADC code */
    uint8_t range; /* active range, 0 to PP_RANGE_COUNT - 1 */
    bool invalid;  /* inside the settling window of a range change */
    bool fault;    /* over-current trip latched */
    uint8_t logic; /* digital inputs D0 to D7 */
} pp_sample_t;

/* Build the word. A value wider than its field is truncated to the field. */
static inline uint32_t pp_sample_pack(const pp_sample_t *sample)
{
    return (((uint32_t)sample->adc & PP_SAMPLE_ADC_MASK) << PP_SAMPLE_ADC_SHIFT) |
           (((uint32_t)sample->range & PP_SAMPLE_RANGE_MASK) << PP_SAMPLE_RANGE_SHIFT) |
           ((uint32_t)sample->invalid << PP_SAMPLE_INVALID_SHIFT) |
           ((uint32_t)sample->fault << PP_SAMPLE_FAULT_SHIFT) |
           (((uint32_t)sample->logic & PP_SAMPLE_LOGIC_MASK) << PP_SAMPLE_LOGIC_SHIFT);
}

static inline uint16_t pp_sample_adc(uint32_t word)
{
    return (uint16_t)((word >> PP_SAMPLE_ADC_SHIFT) & PP_SAMPLE_ADC_MASK);
}

static inline uint8_t pp_sample_range(uint32_t word)
{
    return (uint8_t)((word >> PP_SAMPLE_RANGE_SHIFT) & PP_SAMPLE_RANGE_MASK);
}

static inline bool pp_sample_is_invalid(uint32_t word)
{
    return (word & PP_SAMPLE_INVALID_BIT) != 0u;
}

static inline bool pp_sample_has_fault(uint32_t word)
{
    return (word & PP_SAMPLE_FAULT_BIT) != 0u;
}

static inline uint8_t pp_sample_logic(uint32_t word)
{
    return (uint8_t)((word >> PP_SAMPLE_LOGIC_SHIFT) & PP_SAMPLE_LOGIC_MASK);
}

/* Split the word into its fields. The reserved bits are ignored. */
static inline void pp_sample_unpack(uint32_t word, pp_sample_t *sample)
{
    sample->adc = pp_sample_adc(word);
    sample->range = pp_sample_range(word);
    sample->invalid = pp_sample_is_invalid(word);
    sample->fault = pp_sample_has_fault(word);
    sample->logic = pp_sample_logic(word);
}

#endif /* PP_SAMPLE_H */
