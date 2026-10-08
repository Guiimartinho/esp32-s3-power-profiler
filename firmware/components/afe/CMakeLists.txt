include(${CMAKE_CURRENT_LIST_DIR}/sources.cmake)

idf_component_register(
    INCLUDE_DIRS include
    REQUIRES ${PP_AFE_REQUIRES}
)
