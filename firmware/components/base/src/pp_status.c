#include "base/pp_status.h"

const char *pp_status_name(pp_status_t status)
{
    switch (status) {
    case PP_OK:
        return "PP_OK";
    case PP_ERR_INVALID_ARG:
        return "PP_ERR_INVALID_ARG";
    case PP_ERR_NO_SPACE:
        return "PP_ERR_NO_SPACE";
    case PP_ERR_EMPTY:
        return "PP_ERR_EMPTY";
    case PP_ERR_INCOMPLETE:
        return "PP_ERR_INCOMPLETE";
    case PP_ERR_MALFORMED:
        return "PP_ERR_MALFORMED";
    case PP_ERR_INVALID_STATE:
        return "PP_ERR_INVALID_STATE";
    }
    return "PP_ERR_UNKNOWN";
}
