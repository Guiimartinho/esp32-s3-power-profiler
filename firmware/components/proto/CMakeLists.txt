include(${CMAKE_CURRENT_LIST_DIR}/sources.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/pp_warnings.cmake)

idf_component_register(
    SRCS ${PP_PROTO_SOURCES}
    INCLUDE_DIRS include
    REQUIRES ${PP_PROTO_REQUIRES}
)

pp_target_strict_warnings(${COMPONENT_LIB})
