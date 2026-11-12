cmake_minimum_required(VERSION 3.15...3.31)
project(${SKBUILD_PROJECT_NAME} VERSION ${SKBUILD_PROJECT_VERSION} LANGUAGES C)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)

add_custom_command(
    OUTPUT _core.c
    COMMAND Python::Interpreter -m cython
        "${CMAKE_CURRENT_SOURCE_DIR}/src/cui/_core.pyx" --output-file _core.c
    DEPENDS src/cui/_core.pyx
)

python_add_library(_core MODULE _core.c WITH_SOABI)

if(MSVC)
    target_compile_options(_core PRIVATE /W4)
else()
    target_compile_options(_core PRIVATE -Wall -Wextra)
endif()

install(TARGETS _core DESTINATION cui)
