# Host unit tests of the hardware-independent firmware code.
#
# The components are compiled from the same source lists the ESP-IDF build
# uses (components/<name>/sources.cmake), with a native compiler, and tested
# with Unity. See firmware/README.md for the commands.
cmake_minimum_required(VERSION 3.20)

project(pp_firmware_host_tests LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(PP_COVERAGE "Instrument the code for coverage measurement with gcov" OFF)
option(PP_SANITIZE "Build with AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
option(PP_SANITIZE_THREAD "Build with ThreadSanitizer" OFF)

if(PP_SANITIZE AND PP_SANITIZE_THREAD)
    message(FATAL_ERROR "PP_SANITIZE and PP_SANITIZE_THREAD cannot be combined")
endif()

get_filename_component(PP_FIRMWARE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
include(${PP_FIRMWARE_DIR}/cmake/pp_warnings.cmake)

# --- Instrumentation -------------------------------------------------------

# Every target links this library to pick up the flags of the chosen options.
add_library(pp_build_flags INTERFACE)

if(PP_COVERAGE)
    target_compile_options(pp_build_flags INTERFACE --coverage -O0 -g)
    target_link_options(pp_build_flags INTERFACE --coverage)
endif()

if(PP_SANITIZE)
    set(pp_sanitize_flags
        -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
    target_compile_options(pp_build_flags INTERFACE ${pp_sanitize_flags} -g)
    target_link_options(pp_build_flags INTERFACE ${pp_sanitize_flags})
endif()

if(PP_SANITIZE_THREAD)
    target_compile_options(pp_build_flags INTERFACE -fsanitize=thread -g)
    target_link_options(pp_build_flags INTERFACE -fsanitize=thread)
endif()

# --- Unity -----------------------------------------------------------------

include(FetchContent)

# Unity 2.7.0, pinned to its commit. SOURCE_SUBDIR names a directory without a
# CMakeLists.txt, so the sources are only downloaded and the library is built
# here with our own flags.
FetchContent_Declare(
    unity
    GIT_REPOSITORY https://github.com/ThrowTheSwitch/Unity.git
    GIT_TAG b6763fbd9cedfacaa89e2ad9fd00d615a234e355
    SOURCE_SUBDIR docs
)
FetchContent_MakeAvailable(unity)

add_library(unity STATIC ${unity_SOURCE_DIR}/src/unity.c)
target_include_directories(unity SYSTEM PUBLIC ${unity_SOURCE_DIR}/src)
target_link_libraries(unity PRIVATE pp_build_flags)

# --- Firmware components ---------------------------------------------------

# Build components/<name> as the library pp_<name> from its manifest.
function(pp_add_component name)
    string(TOUPPER ${name} upper)
    set(dir ${PP_FIRMWARE_DIR}/components/${name})
    include(${dir}/sources.cmake)

    set(sources ${PP_${upper}_SOURCES})
    list(TRANSFORM sources PREPEND ${dir}/)
    set(requires ${PP_${upper}_REQUIRES})
    list(TRANSFORM requires PREPEND pp_)

    if(sources)
        add_library(pp_${name} STATIC ${sources})
        target_include_directories(pp_${name} PUBLIC ${dir}/include)
        target_link_libraries(pp_${name} PUBLIC ${requires} PRIVATE pp_build_flags)
        pp_target_strict_warnings(pp_${name})
    else()
        add_library(pp_${name} INTERFACE)
        target_include_directories(pp_${name} INTERFACE ${dir}/include)
        target_link_libraries(pp_${name} INTERFACE ${requires})
    endif()
endfunction()

pp_add_component(base)
pp_add_component(proto)
pp_add_component(acq)
pp_add_component(afe)
pp_add_component(app)

# --- Test doubles ----------------------------------------------------------

add_library(pp_test_support STATIC support/fake_afe.c)
target_include_directories(pp_test_support PUBLIC support)
target_link_libraries(pp_test_support PUBLIC pp_afe PRIVATE pp_build_flags)
pp_target_strict_warnings(pp_test_support)

# --- Tests -----------------------------------------------------------------

enable_testing()

# One executable per module: tests/test_<name>.c, registered as test <name>.
function(pp_add_test name)
    add_executable(test_${name} tests/test_${name}.c)
    target_include_directories(test_${name} PRIVATE generated)
    target_link_libraries(test_${name} PRIVATE unity pp_build_flags ${ARGN})
    pp_target_strict_warnings(test_${name})
    add_test(NAME ${name} COMMAND test_${name})
endfunction()

pp_add_test(status pp_base)
pp_add_test(bytes pp_base)
pp_add_test(blockq pp_base)
pp_add_test(crc16 pp_proto)
pp_add_test(frame pp_proto)
pp_add_test(sample pp_proto)
pp_add_test(stream pp_proto)
pp_add_test(command pp_proto)
pp_add_test(range_tracker pp_acq)
pp_add_test(downrange pp_acq)
pp_add_test(fsm pp_app)
pp_add_test(afe_port pp_acq pp_test_support)

# The queue is exercised by two real threads when the platform has them.
set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads)
if(CMAKE_USE_PTHREADS_INIT)
    pp_add_test(blockq_threads pp_base Threads::Threads)
else()
    message(STATUS "POSIX threads not found: the blockq_threads test is skipped")
endif()

# --- Developer targets -----------------------------------------------------

# First-party C files, relative to the firmware directory. The generated
# protocol header is produced by protocol/generate.py and is left alone.
file(GLOB_RECURSE PP_C_FILES CONFIGURE_DEPENDS RELATIVE ${PP_FIRMWARE_DIR}
    ${PP_FIRMWARE_DIR}/components/*.c
    ${PP_FIRMWARE_DIR}/components/*.h
    ${PP_FIRMWARE_DIR}/main/*.c
    ${PP_FIRMWARE_DIR}/main/*.h
    ${CMAKE_CURRENT_SOURCE_DIR}/support/*.c
    ${CMAKE_CURRENT_SOURCE_DIR}/support/*.h
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/*.c
)
list(FILTER PP_C_FILES EXCLUDE REGEX "pp_proto_defs\\.h$")

# The files clang-tidy can analyze: the ones in this compile database.
set(PP_TIDY_FILES ${PP_C_FILES})
list(FILTER PP_TIDY_FILES INCLUDE REGEX "\\.c$")
list(FILTER PP_TIDY_FILES EXCLUDE REGEX "^main/")

find_program(CLANG_FORMAT clang-format)
if(CLANG_FORMAT)
    add_custom_target(format
        COMMAND ${CLANG_FORMAT} -i ${PP_C_FILES}
        WORKING_DIRECTORY ${PP_FIRMWARE_DIR}
        COMMENT "Formatting the C files"
        VERBATIM
    )
    add_custom_target(format-check
        COMMAND ${CLANG_FORMAT} --dry-run --Werror ${PP_C_FILES}
        WORKING_DIRECTORY ${PP_FIRMWARE_DIR}
        COMMENT "Checking the format of the C files"
        VERBATIM
    )
endif()

find_program(CLANG_TIDY clang-tidy)
if(CLANG_TIDY)
    set(pp_tidy_args -p ${CMAKE_BINARY_DIR} --quiet)
    if(WIN32 AND CMAKE_C_COMPILER_ID STREQUAL "GNU")
        # On Windows clang-tidy assumes the Microsoft toolchain. Point it at the
        # target of the compiler in use, so it finds the same headers.
        execute_process(
            COMMAND ${CMAKE_C_COMPILER} -dumpmachine
            OUTPUT_VARIABLE pp_target_triple
            OUTPUT_STRIP_TRAILING_WHITESPACE
        )
        list(APPEND pp_tidy_args --extra-arg=--target=${pp_target_triple})
    endif()
    add_custom_target(tidy
        COMMAND ${CLANG_TIDY} ${pp_tidy_args} ${PP_TIDY_FILES}
        WORKING_DIRECTORY ${PP_FIRMWARE_DIR}
        COMMENT "Running clang-tidy"
        VERBATIM
    )
endif()

find_program(CPPCHECK cppcheck)
if(CPPCHECK)
    # The tests are left to clang-tidy: cppcheck does not expand the Unity
    # macros without help.
    add_custom_target(cppcheck
        COMMAND ${CPPCHECK}
            --enable=warning,style,performance,portability
            --check-level=exhaustive
            --error-exitcode=1
            --inline-suppr
            --std=c11
            --quiet
            -I components/base/include
            -I components/proto/include
            -I components/acq/include
            -I components/afe/include
            -I components/app/include
            -I test/host/support
            components
            main
            test/host/support
        WORKING_DIRECTORY ${PP_FIRMWARE_DIR}
        COMMENT "Running cppcheck"
        VERBATIM
    )
endif()

find_program(GCOVR gcovr)
if(PP_COVERAGE AND GCOVR)
    # Reads firmware/gcovr.cfg: filters, thresholds and the search path.
    add_custom_target(coverage
        COMMAND ${GCOVR} --html-details ${CMAKE_BINARY_DIR}/coverage.html
        WORKING_DIRECTORY ${PP_FIRMWARE_DIR}
        COMMENT "Measuring coverage (run the tests first)"
        VERBATIM
    )
endif()
