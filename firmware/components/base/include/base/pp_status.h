/*
 * Status codes returned by the hardware-independent code.
 *
 * Adapters translate them to esp_err_t at the boundary with ESP-IDF.
 */
#ifndef PP_STATUS_H
#define PP_STATUS_H

typedef enum {
    PP_OK = 0,
    PP_ERR_INVALID_ARG,   /* An argument is NULL or out of range. */
    PP_ERR_NO_SPACE,      /* The destination buffer or queue cannot take the data. */
    PP_ERR_EMPTY,         /* There is nothing to read. */
    PP_ERR_INCOMPLETE,    /* More input is needed before a result exists. */
    PP_ERR_MALFORMED,     /* The input does not follow the expected format. */
    PP_ERR_INVALID_STATE, /* The operation is not allowed in the current state. */
} pp_status_t;

/* Name of a status code, for logs. Never returns NULL. */
const char *pp_status_name(pp_status_t status);

#endif /* PP_STATUS_H */
