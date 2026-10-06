cmake_minimum_required(VERSION 3.21)
file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/release_version.txt" XFILEUNPACKER_VERSION LIMIT_COUNT 1)
project(XFileUnpacker VERSION "${XFILEUNPACKER_VERSION}" DESCRIPTION "C archive unpacker with console, GUI and TUI frontends" LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

set(XFILEUNPACKER_XXFCLIB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/dep/xxfclib" CACHE PATH "xxfclib source directory")
set(XFILEUNPACKER_XXWIDGETS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/dep/xxwidgets" CACHE PATH "xxwidgets source directory")
option(XFILEUNPACKER_BUILD_GUI "Build the native desktop frontend" ON)
option(XFILEUNPACKER_BUILD_TUI "Build the terminal frontend" ON)

if(NOT EXISTS "${XFILEUNPACKER_XXFCLIB_DIR}/samples/unpack/xxfc_readers.c")
    message(FATAL_ERROR "XFILEUNPACKER_XXFCLIB_DIR must point to xxfclib with samples/unpack")
endif()

function(xfu_c_target target)
    target_compile_features(${target} PRIVATE c_std_11)
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4 /utf-8)
        target_compile_definitions(${target} PRIVATE _CRT_SECURE_NO_WARNINGS)
    else()
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic)
    endif()
    if(WIN32)
        target_compile_definitions(${target} PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
    else()
        target_compile_definitions(${target} PRIVATE _POSIX_C_SOURCE=200809L)
    endif()
endfunction()

if(NOT TARGET xxfclib::xxformats)
    include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/xxformats.cmake")
    add_library(xxfclib_formats STATIC ${XXFORMATS_SOURCES})
    add_library(xxfclib::xxformats ALIAS xxfclib_formats)
    target_include_directories(xxfclib_formats
        PUBLIC "${XXFORMATS_INCLUDE_DIR}"
        PRIVATE ${XXFORMATS_INCLUDE_DIRS})
    target_compile_definitions(xxfclib_formats PUBLIC XXFC_STATIC PRIVATE XXFC_FORMATS_ONLY)
    target_link_libraries(xxfclib_formats PUBLIC ${XXFORMATS_LIBRARIES})
    target_compile_features(xxfclib_formats PRIVATE c_std_11)
    set_target_properties(xxfclib_formats PROPERTIES POSITION_INDEPENDENT_CODE ON)
    if(MSVC)
        # MSBuild's --parallel splits projects; /MP also compiles the large
        # reader collection in parallel inside its library project.
        target_compile_options(xxfclib_formats PRIVATE /W4 /utf-8 /MP8)
        target_compile_definitions(xxfclib_formats PRIVATE _CRT_SECURE_NO_WARNINGS)
    else()
        # Some xxfclib readers use standard functions without including their headers.
        target_compile_options(xxfclib_formats PRIVATE -Wall -Wextra -Wpedantic
            "SHELL:-include string.h" "SHELL:-include stdlib.h")
        if(NOT WIN32)
            # The WIM pipe client uses WEP_UNIX where the socket API defines AF_UNIX.
            target_compile_definitions(xxfclib_formats PRIVATE
                _POSIX_C_SOURCE=200809L WEP_UNIX=AF_UNIX)
        endif()
    endif()
    # Third-party code kept as upstream ships it: the SQLite amalgamation,
    # bzip2 (via NSIS), the zlib deflate encoder FEAD carries, and Brotli's
    # dictionary table. Their known warnings are switched off here, file by
    # file and warning by warning, so an update stays a drop-in copy and any
    # other warning they raise still shows.
    set(_xfu_upstream "${XFILEUNPACKER_XXFCLIB_DIR}/src")
    set(_xfu_zlib_encoder deflate trees adler32 crc32 compress)
    list(TRANSFORM _xfu_zlib_encoder PREPEND "${_xfu_upstream}/formats/fead/encoder/")
    list(TRANSFORM _xfu_zlib_encoder APPEND ".c")
    if(MSVC)
        # C4200 flexible array members; C4131 K&R definitions; C4127 constant
        # conditions; C4244 narrowing upstream relies on; C4702 unreachable code.
        set_source_files_properties("${_xfu_upstream}/formats/sqlite_sql/xx_sqlite_amalgamation.c"
            PROPERTIES COMPILE_OPTIONS "/wd4200")
        set_source_files_properties("${_xfu_upstream}/formats/nsis/nsis_bzip2.c"
            PROPERTIES COMPILE_OPTIONS "/wd4127;/wd4244;/wd4702")
        set_source_files_properties(${_xfu_zlib_encoder}
            PROPERTIES COMPILE_OPTIONS "/wd4131;/wd4127;/wd4244")
    else()
        # bzip2's state machine falls through on purpose; the Brotli dictionary
        # is one string longer than ISO C's minimum-supported length.
        set_source_files_properties("${_xfu_upstream}/formats/nsis/nsis_bzip2.c"
            PROPERTIES COMPILE_OPTIONS "-Wno-implicit-fallthrough")
        set_source_files_properties("${_xfu_upstream}/algo/brotli/xx_brotli_data.c"
            PROPERTIES COMPILE_OPTIONS "-Wno-overlength-strings")
        if(CMAKE_C_COMPILER_ID STREQUAL "GNU")
            # GCC-only options: Clang warns about names it does not know.
            # GCC 15 follows a null column name into sqlite3ColumnSetColl's
            # second strlen, a path SQLite never takes once a type is set;
            # GCC 16 counts nIdx's loop increment as no use, and reports its
            # own 8-byte vector stores into bzip2's six-entry selector table.
            set_source_files_properties("${_xfu_upstream}/formats/sqlite_sql/xx_sqlite_amalgamation.c"
                PROPERTIES COMPILE_OPTIONS "-Wno-stringop-overread;-Wno-unused-but-set-variable")
            set_source_files_properties("${_xfu_upstream}/formats/nsis/nsis_bzip2.c"
                PROPERTIES COMPILE_OPTIONS "-Wno-implicit-fallthrough;-Wno-stringop-overflow")
        endif()
    endif()
endif()

add_library(xfileunpacker_core STATIC
    src/core.c src/core.h src/metadata.c src/metadata.h
    src/information.c src/information.h
    src/supported_types.c src/supported_types.h
    "${XFILEUNPACKER_XXFCLIB_DIR}/samples/unpack/xxfc_readers.c")
target_include_directories(xfileunpacker_core PUBLIC src PRIVATE "${XFILEUNPACKER_XXFCLIB_DIR}/samples/unpack")
target_compile_definitions(xfileunpacker_core PRIVATE XXFC_FORMATS_ONLY)
target_link_libraries(xfileunpacker_core PUBLIC xxfclib::xxformats)
xfu_c_target(xfileunpacker_core)

# Offline helper for refreshing xxfclib's static extension detector table.
add_executable(xfileunpacker_dump_extensions EXCLUDE_FROM_ALL
    "${XFILEUNPACKER_XXFCLIB_DIR}/samples/unpack/dump_extensions.c")
target_include_directories(xfileunpacker_dump_extensions PRIVATE
    "${XFILEUNPACKER_XXFCLIB_DIR}/samples/unpack")
target_link_libraries(xfileunpacker_dump_extensions PRIVATE xfileunpacker_core)
xfu_c_target(xfileunpacker_dump_extensions)

add_executable(XFileUnpacker src/cli.c)
set_target_properties(XFileUnpacker PROPERTIES OUTPUT_NAME xfu)
target_link_libraries(XFileUnpacker PRIVATE xfileunpacker_core)
if(WIN32)
    target_link_libraries(XFileUnpacker PRIVATE shell32)
endif()
xfu_c_target(XFileUnpacker)

if(XFILEUNPACKER_BUILD_GUI OR XFILEUNPACKER_BUILD_TUI)
    if(NOT TARGET xxwidgets::xxwidgets)
        set(XXWIDGETS_BUILD_SETTINGS OFF)
        set(XXWIDGETS_XXFCLIB_DIR "${XFILEUNPACKER_XXFCLIB_DIR}")
        add_subdirectory("${XFILEUNPACKER_XXWIDGETS_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/deps/xxwidgets" EXCLUDE_FROM_ALL)
    endif()
    if(NOT TARGET xxwidgets::settings)
        include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/xxsettings.cmake")
        add_library(xfileunpacker_widget_settings STATIC
            "${XFILEUNPACKER_XXWIDGETS_DIR}/src/xxwidgets_settings.c"
            ${XXSETTINGS_SOURCES})
        add_library(xxwidgets::settings ALIAS xfileunpacker_widget_settings)
        set_target_properties(xfileunpacker_widget_settings PROPERTIES POSITION_INDEPENDENT_CODE ON)
        target_include_directories(xfileunpacker_widget_settings PUBLIC
            "${XFILEUNPACKER_XXWIDGETS_DIR}/include"
            "${XXSETTINGS_INCLUDE_DIR}")
        target_compile_definitions(xfileunpacker_widget_settings PUBLIC XXFC_STATIC)
        target_link_libraries(xfileunpacker_widget_settings PUBLIC
            xxwidgets::xxwidgets ${XXSETTINGS_LIBRARIES})
        xfu_c_target(xfileunpacker_widget_settings)
    endif()
    find_package(Threads REQUIRED)
    add_library(xfileunpacker_ui STATIC src/ui.c src/ui.h)
    target_compile_definitions(xfileunpacker_ui PRIVATE XFILEUNPACKER_VERSION="${PROJECT_VERSION}")
    if(WIN32)
        target_sources(xfileunpacker_ui PRIVATE src/native_shell.c src/native_shell.h)
        target_link_libraries(xfileunpacker_ui PRIVATE user32 gdi32 comctl32 shell32 comdlg32 ole32)
    endif()
    target_link_libraries(xfileunpacker_ui PUBLIC xfileunpacker_core xxwidgets::settings Threads::Threads)
    xfu_c_target(xfileunpacker_ui)
    if(XFILEUNPACKER_BUILD_GUI)
        if(XXWIDGETS_NATIVE_BACKEND STREQUAL "none")
            message(FATAL_ERROR "GUI requires a native xxwidgets backend; set XFILEUNPACKER_BUILD_GUI=OFF for a terminal-only build")
        endif()
        add_executable(XFileUnpackerGUI WIN32 src/gui.c)
        set_target_properties(XFileUnpackerGUI PROPERTIES OUTPUT_NAME XFileUnpacker)
        target_link_libraries(XFileUnpackerGUI PRIVATE xfileunpacker_ui)
        if(WIN32)
            target_link_libraries(XFileUnpackerGUI PRIVATE shell32 comdlg32)
        endif()
        if(MINGW)
            target_link_options(XFileUnpackerGUI PRIVATE -municode)
        endif()
        xfu_c_target(XFileUnpackerGUI)
        add_custom_command(TARGET XFileUnpackerGUI POST_BUILD
            COMMAND "${CMAKE_COMMAND}"
                "-DSOURCE=${CMAKE_CURRENT_SOURCE_DIR}/shortcuts.ini"
                "-DDESTINATION=$<TARGET_FILE_DIR:XFileUnpackerGUI>/shortcuts.ini"
                -P "${CMAKE_CURRENT_SOURCE_DIR}/packaging/copy_shortcuts.cmake")
    endif()
    if(XFILEUNPACKER_BUILD_TUI)
        add_executable(XFileUnpackerTUI src/tui.c)
        set_target_properties(XFileUnpackerTUI PROPERTIES OUTPUT_NAME xfut)
        target_link_libraries(XFileUnpackerTUI PRIVATE xfileunpacker_ui)
        if(WIN32)
            target_link_libraries(XFileUnpackerTUI PRIVATE shell32 comdlg32)
        endif()
        xfu_c_target(XFileUnpackerTUI)
    endif()
endif()

include(packaging/icons.cmake)
include(cmake/format_additions.cmake)
include(cmake/uniextract_formats.cmake)
include(cmake/wim_legacy_formats.cmake)

install(TARGETS XFileUnpacker RUNTIME DESTINATION bin)
install(FILES README.md LICENSE DESTINATION share/doc/XFileUnpacker)
if(TARGET XFileUnpackerGUI)
    install(TARGETS XFileUnpackerGUI RUNTIME DESTINATION bin BUNDLE DESTINATION .)
    install(FILES shortcuts.ini DESTINATION bin)
endif()
if(TARGET XFileUnpackerTUI)
    install(TARGETS XFileUnpackerTUI RUNTIME DESTINATION bin)
endif()

if(WIN32)
    if(CMAKE_GENERATOR_PLATFORM)
        string(TOLOWER "${CMAKE_GENERATOR_PLATFORM}" _xfu_package_arch)
    elseif(CMAKE_SIZEOF_VOID_P EQUAL 8)
        set(_xfu_package_arch "x64")
    else()
        set(_xfu_package_arch "win32")
    endif()
    if(_xfu_package_arch STREQUAL "x64")
        set(_xfu_package_suffix "win64")
    elseif(_xfu_package_arch STREQUAL "win32")
        set(_xfu_package_suffix "win32")
    elseif(_xfu_package_arch STREQUAL "arm64")
        set(_xfu_package_suffix "winarm64")
    else()
        set(_xfu_package_suffix "${_xfu_package_arch}")
    endif()
    set(CPACK_PACKAGE_FILE_NAME "xfileunpacker_${_xfu_package_suffix}_portable_${PROJECT_VERSION}")
endif()
set(CPACK_PACKAGE_NAME "xfileunpacker")
set(CPACK_PACKAGE_VERSION "${PROJECT_VERSION}")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "XFileUnpacker console, GUI and TUI archive tools")
set(CPACK_RESOURCE_FILE_LICENSE "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE")
set(CPACK_GENERATOR "ZIP")
include(CPack)
