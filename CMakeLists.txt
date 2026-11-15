cmake_minimum_required(VERSION 3.15...3.31)
project(${SKBUILD_PROJECT_NAME} VERSION ${SKBUILD_PROJECT_VERSION} LANGUAGES C)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
# libcui.a is linked into a Python extension, a shared object.
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(CUI_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(CUI_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(CUI_BUILD_SHARED OFF CACHE BOOL "" FORCE)
add_subdirectory(thirdparty/cui EXCLUDE_FROM_ALL)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module ${SKBUILD_SABI_COMPONENT})

set(PYSRC "${CMAKE_CURRENT_SOURCE_DIR}/src/cui")
add_custom_command(
    OUTPUT _core.c
    COMMAND Python::Interpreter -m cython -I "${CMAKE_CURRENT_SOURCE_DIR}/src"
        "${PYSRC}/_core.pyx" --output-file _core.c
    DEPENDS "${PYSRC}/_core.pyx" "${PYSRC}/_gen.pxi" "${PYSRC}/_cui.pxd"
)

# Stable ABI per wheel.py-api; empty on builds that cannot use it (free-threaded).
if(SKBUILD_SABI_VERSION)
    set(CUI_SABI USE_SABI ${SKBUILD_SABI_VERSION})
endif()
python_add_library(_core MODULE _core.c WITH_SOABI ${CUI_SABI})
target_link_libraries(_core PRIVATE cui)

# cui.Pty: a terminal on a pty, emulated by libghostty-vt. Its build runs
# `zig build`, so Zig 0.17 must be on PATH. cuipy_pty is a static library either
# way, so cui-repl's flags and CUI's private headers stay out of _core.
option(CUI_PY_PTY "Build cui.Pty (POSIX only; needs Zig 0.17)" OFF)
if(CUI_PY_PTY)
    if(WIN32)
        message(FATAL_ERROR "CUI_PY_PTY needs a POSIX pty; Windows has none")
    endif()
    if(CMAKE_VERSION VERSION_LESS 3.19)
        message(FATAL_ERROR "CUI_PY_PTY needs CMake 3.19 for libghostty-vt")
    endif()
    # Offline: -DFETCHCONTENT_SOURCE_DIR_GHOSTTY=/path/to/libghostty-vt-1.0.0
    include(FetchContent)
    FetchContent_Declare(ghostty
        URL https://release.files.ghostty.org/libghostty-vt/1.0.0/libghostty-vt-1.0.0.tar.gz
        URL_HASH SHA256=4a6ef758be721923e1969e7b81b443dcc92d8dd3fb5a39600c03a8817a753676
        DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
    FetchContent_MakeAvailable(ghostty)

    set(REPL thirdparty/cui-repl/src)
    add_library(cuipy_pty STATIC csrc/cuipy_pty.c ${REPL}/pty.c ${REPL}/session.c
        ${REPL}/term_view.c ${REPL}/boxdraw.c ${REPL}/cuix.c)
    # cui-repl includes "cui.h"; cuix.c reads CUI's private cui_internal.h.
    target_include_directories(cuipy_pty PRIVATE ${REPL} thirdparty/cui/include/cui thirdparty/cui/src)
    target_compile_options(cuipy_pty PRIVATE -Wall -Wextra -Wshadow -Wstrict-prototypes)
    if(CUI_TEXT_SHAPING)
        target_compile_definitions(cuipy_pty PRIVATE CUI_TEXT_SHAPING)
    endif()
    target_link_libraries(cuipy_pty PRIVATE ghostty-vt-static)
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        # The archive bundles Zig's compiler_rt and ubsan_rt; keep them unexported.
        target_link_options(_core PRIVATE -Wl,--exclude-libs,libghostty-vt.a)
    endif()
    install(FILES "${ghostty_SOURCE_DIR}/LICENSE" DESTINATION cui/licenses
        RENAME libghostty-vt.txt COMPONENT python)
    install(FILES thirdparty/cui-repl/LICENSE DESTINATION cui/licenses
        RENAME cui-repl.txt COMPONENT python)
else()
    add_library(cuipy_pty STATIC csrc/cuipy_pty_stub.c)
endif()
target_include_directories(cuipy_pty PUBLIC csrc)
target_link_libraries(cuipy_pty PRIVATE cui)
target_link_libraries(_core PRIVATE cuipy_pty)

# Only the extension: CUI's own install rules would add libcui.a and its headers.
install(TARGETS _core DESTINATION cui COMPONENT python)
