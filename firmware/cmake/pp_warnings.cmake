# Warning flags for the hardware-independent code.
#
# Shared by the ESP-IDF component builds and by the host test build, so the
# same code is held to the same rules by both compilers.

set(PP_STRICT_WARNINGS
    -Wall
    -Wextra
    -Wconversion
    -Wshadow
    -Wstrict-prototypes
    -Wmissing-prototypes
    -Werror
)

if(NOT ESP_PLATFORM)
    # ESP-IDF wraps standard headers such as stdatomic.h with #include_next, a
    # GNU extension that -Wpedantic rejects. The pedantic check therefore runs
    # on the host build only, where the same sources meet the plain C library.
    list(APPEND PP_STRICT_WARNINGS -Wpedantic)
endif()

function(pp_target_strict_warnings target)
    target_compile_options(${target} PRIVATE ${PP_STRICT_WARNINGS})
endfunction()
