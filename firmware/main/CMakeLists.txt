# The main component is the composition root: it creates the adapters and
# hands them to the hardware-independent code. It lists every project
# component, so each one is compiled for the target on every build.
idf_component_register(
    SRCS "app_main.c"
    INCLUDE_DIRS "."
    PRIV_REQUIRES base proto acq afe app esp_app_format
)

target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
