# Format readers, extractors and algorithms, plus their runtime dependencies.
# Define XXFC_STATIC, add XXFORMATS_INCLUDE_DIR publicly and
# XXFORMATS_INCLUDE_DIRS privately, and link XXFORMATS_LIBRARIES.
# The legacy x*.c parsers are part of die_engine and are deliberately excluded.
set(XXFORMATS_INCLUDE_DIR "${XFILEUNPACKER_XXFCLIB_DIR}/include")
file(GLOB_RECURSE XXFORMATS_SOURCES CONFIGURE_DEPENDS
    "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/xx_*.c"
    "${XFILEUNPACKER_XXFCLIB_DIR}/src/algo/xx_*.c"
)
# This includes SHA and BZip2 scalar and CPU-dispatched kernels. Their SIMD
# instructions are isolated inside guarded functions, so no global ISA flag
# is needed for formats-only consumers or non-x86 builds.
# DIE music readers require the separate signature engine and its runtime.
list(FILTER XXFORMATS_SOURCES EXCLUDE REGEX "/src/formats/die_music/")
list(APPEND XXFORMATS_SOURCES
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/rt/xx_rt.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/rt/xx_rt_fp.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/rt/xx_rt_math.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/buf/xx_buf.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/json/xx_json.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/xml/xx_xml.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/global/xx_global.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/global/platforms/xx_global_cpu.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/io/xx_io.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/io/xx_io_file.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/io/xx_io_mem.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/io/xx_io_sub.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/io/xx_io_process.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/memory/xx_memory.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/memory/xx_memory_rt.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/memory/platforms/xx_memory_sse2.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/memory/platforms/xx_memory_avx2.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/strings/xx_string.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/data/xx_pd.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/data/xx_data_raw.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/data/xx_data_io.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/data/platforms/xx_data_sse2.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/data/platforms/xx_data_avx2.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/list/xx_list.c
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/var/xx_var.c
)
if(WIN32)
    list(APPEND XXFORMATS_SOURCES
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/io/platforms/xx_io_windows.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/memory/platforms/xx_memory_windows.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/strings/platforms/xx_string_windows.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/rt/platforms/xx_rt_windows.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/global/platforms/xx_global_windows.c
    )
    set(XXFORMATS_LIBRARIES kernel32)
else()
    list(APPEND XXFORMATS_SOURCES
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/io/platforms/xx_io_posix.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/memory/platforms/xx_memory_posix.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/strings/platforms/xx_string_posix.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/rt/platforms/xx_rt_posix.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/global/platforms/xx_global_posix.c
    )
    find_package(Threads REQUIRED)
    set(XXFORMATS_LIBRARIES Threads::Threads m ${CMAKE_DL_LIBS})
endif()

# Resolve internal headers and the short algorithm header names used by readers.
set(XXFORMATS_INCLUDE_DIRS
    ${XXFORMATS_INCLUDE_DIR}
    ${XXFORMATS_INCLUDE_DIR}/xxfclib
    ${XXFORMATS_INCLUDE_DIR}/xxfclib/formats
    ${XFILEUNPACKER_XXFCLIB_DIR}/src
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/data
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/data/platforms
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/formats
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/tar_common
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/algo/bzip2
    ${XFILEUNPACKER_XXFCLIB_DIR}/src/algo/sha
)
file(GLOB_RECURSE _xxformats_algo_headers CONFIGURE_DEPENDS
    "${XXFORMATS_INCLUDE_DIR}/xxfclib/algo/*.h")
foreach(_xxformats_header IN LISTS _xxformats_algo_headers)
    get_filename_component(_xxformats_dir "${_xxformats_header}" DIRECTORY)
    list(APPEND XXFORMATS_INCLUDE_DIRS "${_xxformats_dir}")
endforeach()
list(REMOVE_DUPLICATES XXFORMATS_INCLUDE_DIRS)

# Private prefix batching is used only by die_engine's literal-search engine.
set_property(SOURCE ${XFILEUNPACKER_XXFCLIB_DIR}/src/data/xx_data_raw.c
    APPEND PROPERTY COMPILE_DEFINITIONS XXFC_FORMATS_ONLY)
# The detection fallback also depends on the excluded DIE music engine.
set_property(SOURCE ${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/xx_format.c
    APPEND PROPERTY COMPILE_DEFINITIONS XXFC_FORMATS_ONLY)

if(MSVC)
    set_source_files_properties(
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/data/platforms/xx_data_avx2.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/memory/platforms/xx_memory_avx2.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/algo/entropy/platforms/xx_entropy_avx2.c
        ${XFILEUNPACKER_XXFCLIB_DIR}/src/algo/lzma/platforms/xx_lzma_avx2.c
        PROPERTIES COMPILE_OPTIONS "/arch:AVX2")
endif()
unset(_xxformats_header)
unset(_xxformats_dir)
unset(_xxformats_algo_headers)
