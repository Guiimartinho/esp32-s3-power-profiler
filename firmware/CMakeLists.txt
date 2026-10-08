# ESP-IDF project of the instrument firmware.
#
# The three lines below must stay in this order.
cmake_minimum_required(VERSION 3.22)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
# Build only the main component and what it depends on.
idf_build_set_property(MINIMAL_BUILD ON)
project(power_profiler)
