# Manifest of the component, read by the ESP-IDF build (CMakeLists.txt) and by
# the host test build (test/host/CMakeLists.txt). Paths are relative to this
# directory.

set(PP_ACQ_SOURCES
    src/pp_downrange.c
    src/pp_range_tracker.c
)

set(PP_ACQ_REQUIRES base proto)
