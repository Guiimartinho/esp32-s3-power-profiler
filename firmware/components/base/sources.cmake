# Manifest of the component, read by the ESP-IDF build (CMakeLists.txt) and by
# the host test build (test/host/CMakeLists.txt). Paths are relative to this
# directory.

set(PP_BASE_SOURCES
    src/pp_blockq.c
    src/pp_status.c
)

set(PP_BASE_REQUIRES)
