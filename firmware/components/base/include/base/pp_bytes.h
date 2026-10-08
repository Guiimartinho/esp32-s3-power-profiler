/*
 * Little-endian byte access.
 *
 * Every multi-byte field of the wire protocol is little-endian. These helpers
 * read and write them one byte at a time, so the code does not depend on the
 * byte order or the alignment rules of the processor.
 */
#ifndef PP_BYTES_H
#define PP_BYTES_H

#include <stdint.h>

static inline void pp_put_u16le(uint8_t *dst, uint16_t value)
{
    dst[0] = (uint8_t)(value & 0xFFu);
    dst[1] = (uint8_t)(value >> 8);
}

static inline void pp_put_u32le(uint8_t *dst, uint32_t value)
{
    dst[0] = (uint8_t)(value & 0xFFu);
    dst[1] = (uint8_t)((value >> 8) & 0xFFu);
    dst[2] = (uint8_t)((value >> 16) & 0xFFu);
    dst[3] = (uint8_t)(value >> 24);
}

static inline uint16_t pp_get_u16le(const uint8_t *src)
{
    return (uint16_t)((uint16_t)src[0] | ((uint16_t)src[1] << 8));
}

static inline uint32_t pp_get_u32le(const uint8_t *src)
{
    return (uint32_t)src[0] | ((uint32_t)src[1] << 8) | ((uint32_t)src[2] << 16) |
           ((uint32_t)src[3] << 24);
}

#endif /* PP_BYTES_H */
