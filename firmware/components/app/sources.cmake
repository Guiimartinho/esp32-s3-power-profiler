# Manifest of the component, read by the ESP-IDF build (CMakeLists.txt) and by
# the host test build (test/host/CMakeLists.txt). Paths are relative to this
# directory.

set(PP_APP_SOURCES
    src/pp_fsm.c
)

set(PP_APP_REQUIRES base proto)
