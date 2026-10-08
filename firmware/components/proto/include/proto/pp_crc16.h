/*
 * CRC-16/CCITT-FALSE, the checksum of every protocol frame.
 *
 * Polynomial, initial value and check value come from pp_proto_defs.h. The
 * CRC is neither reflected nor inverted at the end.
 */
#ifndef PP_CRC16_H
#define PP_CRC16_H

#include <stddef.h>
#include <stdint.h>

/*
 * Continue a CRC over more data. Start with PP_CRC16_INIT and feed the pieces
 * in order; the result after the last piece is the CRC of the whole.
 */
uint16_t pp_crc16_update(uint16_t crc, const uint8_t *data, size_t len);

/* CRC of one contiguous buffer. */
uint16_t pp_crc16(const uint8_t *data, size_t len);

#endif /* PP_CRC16_H */
