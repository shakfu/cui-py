cmake_minimum_required(VERSION 3.15...3.31)
project(${SKBUILD_PROJECT_NAME} VERSION ${SKBUILD_PROJECT_VERSION} LANGUAGES C)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
# libcui.a is linked into a Python extension, a shared object.
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(CUI_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(CUI_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(CUI_BUILD_SHARED OFF CACHE BOOL "" FORCE)
add_subdirectory(thirdparty/cui EXCLUDE_FROM_ALL)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)

set(PYSRC "${CMAKE_CURRENT_SOURCE_DIR}/src/cui")
add_custom_command(
    OUTPUT _core.c
    COMMAND Python::Interpreter -m cython -I "${CMAKE_CURRENT_SOURCE_DIR}/src"
        "${PYSRC}/_core.pyx" --output-file _core.c
    DEPENDS "${PYSRC}/_core.pyx" "${PYSRC}/_gen.pxi" "${PYSRC}/_cui.pxd"
)

python_add_library(_core MODULE _core.c WITH_SOABI)
target_link_libraries(_core PRIVATE cui)

# Only the extension: CUI's own install rules would add libcui.a and its headers.
install(TARGETS _core DESTINATION cui COMPONENT python)
