# Manifest of the component, read by the ESP-IDF build (CMakeLists.txt) and by
# the host test build (test/host/CMakeLists.txt). Paths are relative to this
# directory.

set(PP_PROTO_SOURCES
    src/pp_command.c
    src/pp_crc16.c
    src/pp_frame.c
    src/pp_stream.c
)

set(PP_PROTO_REQUIRES base)
