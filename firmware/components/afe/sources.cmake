# Manifest of the component, read by the ESP-IDF build (CMakeLists.txt) and by
# the host test build (test/host/CMakeLists.txt). Paths are relative to this
# directory.
#
# The component has no hardware-independent source yet: it declares the port
# that the analog front end adapter will implement.

set(PP_AFE_SOURCES)

set(PP_AFE_REQUIRES base proto)
