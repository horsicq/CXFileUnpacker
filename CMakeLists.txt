cmake_minimum_required(VERSION 3.21)
file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/release_version.txt" XFILEUNPACKER_VERSION LIMIT_COUNT 1)
project(XFileUnpacker VERSION "${XFILEUNPACKER_VERSION}" DESCRIPTION "C archive unpacker with console, GUI and TUI frontends" LANGUAGES C)

# Compile only the optional format streams used by this application.
if(NOT TARGET xxfclib::xxfclib)
    set(XXFC_ENABLE_STREAM_DATASTRUCTS OFF)
    set(XXFC_ENABLE_STREAM_IMPORT OFF)
    set(XXFC_ENABLE_STREAM_EXPORT OFF)
    set(XXFC_ENABLE_STREAM_RESOURCES OFF)
    set(XXFC_ENABLE_STREAM_METADATA OFF)
    set(XXFC_ENABLE_STREAM_SYMBOLS OFF)
endif()

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

set(XFILEUNPACKER_XXFCLIB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/dep/xxfclib" CACHE PATH "xxfclib source directory")
set(XFILEUNPACKER_XXWIDGETS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/dep/xxwidgets" CACHE PATH "xxwidgets source directory")
option(XFILEUNPACKER_BUILD_GUI "Build the native desktop frontend" ON)
option(XFILEUNPACKER_BUILD_TUI "Build the terminal frontend" ON)

if(NOT EXISTS "${XFILEUNPACKER_XXFCLIB_DIR}/src/xfileunpacker/xxfc_readers.c")
    message(FATAL_ERROR "XFILEUNPACKER_XXFCLIB_DIR must contain the xxfclib unpacker engine")
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
        if(APPLE)
            # AppKit's system headers use Darwin's BSD networking typedefs.
            target_compile_definitions(${target} PRIVATE _DARWIN_C_SOURCE)
        endif()
    endif()
    get_target_property(_target_type ${target} TYPE)
    if(_target_type STREQUAL "EXECUTABLE")
        if(MINGW)
            target_link_options(${target} PRIVATE $<$<CONFIG:Release>:-s>)
        endif()
    endif()
endfunction()

if(NOT TARGET xxfclib::xxfclib)
    # Codec and archive code belongs to the prepared xxfclib tree. Keep this
    # build independent of package managers, FetchContent and network access.
    set(BUILD_SHARED_LIBS OFF CACHE BOOL "Build static libraries" FORCE)
    set(XXFC_BUILD_BOTH OFF CACHE BOOL "Build one xxfclib variant" FORCE)
    set(XXFC_BUILD_PROFILE formats CACHE STRING
        "Build the self-contained xxfclib formats profile" FORCE)
    add_subdirectory("${XFILEUNPACKER_XXFCLIB_DIR}"
        "${CMAKE_CURRENT_BINARY_DIR}/deps/xxfclib" EXCLUDE_FROM_ALL)
endif()

# The complete archive engine is an xxfclib component.  This application
# directory now contains only the frontends, platform shell integration,
# packaging and tests.
include("${XFILEUNPACKER_XXFCLIB_DIR}/cmake/xxfclib_xfileunpacker.cmake")

# Offline helper for refreshing xxfclib's static extension detector table.
if(EXISTS "${XFILEUNPACKER_XXFCLIB_DIR}/samples/unpack/dump_extensions.c")
    add_executable(xfileunpacker_dump_extensions EXCLUDE_FROM_ALL
        "${XFILEUNPACKER_XXFCLIB_DIR}/samples/unpack/dump_extensions.c")
    target_include_directories(xfileunpacker_dump_extensions PRIVATE
        "${XFILEUNPACKER_XXFCLIB_DIR}/src/xfileunpacker")
    target_link_libraries(xfileunpacker_dump_extensions PRIVATE xxfclib::xfileunpacker_core)
    xfu_c_target(xfileunpacker_dump_extensions)
endif()

add_executable(XFileUnpacker src/cli.c)
set_target_properties(XFileUnpacker PROPERTIES OUTPUT_NAME xfu)
target_compile_definitions(XFileUnpacker PRIVATE
    XFU_APPLICATION_VERSION="${PROJECT_VERSION}")
target_link_libraries(XFileUnpacker PRIVATE xxfclib::xfileunpacker_core)
if(WIN32)
    target_link_libraries(XFileUnpacker PRIVATE shell32)
endif()
xfu_c_target(XFileUnpacker)

if(XFILEUNPACKER_BUILD_GUI OR XFILEUNPACKER_BUILD_TUI)
    if(NOT TARGET xxwidgets::xxwidgets)
        set(XXWIDGETS_BUILD_SETTINGS OFF)
        set(XXWIDGETS_XXFCLIB_DIR "${XFILEUNPACKER_XXFCLIB_DIR}")
        if(XFILEUNPACKER_BUILD_TUI AND NOT XFILEUNPACKER_BUILD_GUI)
            set(XXWIDGETS_NATIVE_BACKEND none CACHE STRING
                "Disable native GUI dependencies for a TUI-only build" FORCE)
        endif()
        add_subdirectory("${XFILEUNPACKER_XXWIDGETS_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/deps/xxwidgets" EXCLUDE_FROM_ALL)
    endif()
    if(NOT TARGET xxwidgets::settings)
        add_library(xfileunpacker_widget_settings STATIC
            "${XFILEUNPACKER_XXWIDGETS_DIR}/src/xxwidgets_settings.c")
        add_library(xxwidgets::settings ALIAS xfileunpacker_widget_settings)
        set_target_properties(xfileunpacker_widget_settings PROPERTIES POSITION_INDEPENDENT_CODE ON)
        target_include_directories(xfileunpacker_widget_settings PUBLIC
            "${XFILEUNPACKER_XXWIDGETS_DIR}/include")
        target_link_libraries(xfileunpacker_widget_settings PUBLIC
            xxwidgets::xxwidgets xxfclib::xxfclib)
        xfu_c_target(xfileunpacker_widget_settings)
    endif()
    find_package(Threads REQUIRED)
    add_library(xfileunpacker_ui STATIC src/ui.c src/ui.h)
    target_compile_definitions(xfileunpacker_ui PRIVATE XFILEUNPACKER_VERSION="${PROJECT_VERSION}")
    if(WIN32)
        target_sources(xfileunpacker_ui PRIVATE src/native_shell.c src/native_shell.h)
        target_link_libraries(xfileunpacker_ui PRIVATE user32 gdi32 comctl32 shell32 comdlg32 ole32)
    endif()
    target_link_libraries(xfileunpacker_ui PUBLIC xxfclib::xfileunpacker_core xxwidgets::settings Threads::Threads)
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
include(cmake/native_container_formats.cmake)

install(TARGETS XFileUnpacker RUNTIME DESTINATION bin)
install(FILES README.md LICENSE DESTINATION share/doc/XFileUnpacker)
install(FILES docs/ARCHIVE_FORMATS.md docs/PEAZIP_FORMATS.md docs/FREEARC_WRITER.md DESTINATION share/doc/XFileUnpacker)
install(FILES docs/LEGACY_CODECS_NOTICE.md docs/SPLIT_FORMAT.md docs/SPECIALIZED_FORMATS.md DESTINATION share/doc/XFileUnpacker)
include(CTest)
if(BUILD_TESTING)
    if(WIN32)
        find_program(XFU_POWERSHELL_EXECUTABLE NAMES powershell pwsh)
        if(XFU_POWERSHELL_EXECUTABLE)
            foreach(_encryption_frontend IN ITEMS XFileUnpackerGUI XFileUnpackerTUI)
                if(TARGET ${_encryption_frontend})
                    add_test(NAME ${_encryption_frontend}_encryption_notice
                        COMMAND "${XFU_POWERSHELL_EXECUTABLE}" -NoProfile -NonInteractive
                            -ExecutionPolicy Bypass -File
                            "${CMAKE_CURRENT_SOURCE_DIR}/tests/run_encryption_ui_smoke.ps1"
                            -Executable "$<TARGET_FILE:${_encryption_frontend}>")
                    set_tests_properties(${_encryption_frontend}_encryption_notice
                        PROPERTIES TIMEOUT 30 RUN_SERIAL TRUE)
                endif()
            endforeach()
        endif()
    endif()
    add_executable(xfu_structured_escape_test tests/test_structured_escape.c)
    target_link_libraries(xfu_structured_escape_test PRIVATE xxfclib::xfileunpacker_core)
    if(WIN32)
        target_link_libraries(xfu_structured_escape_test PRIVATE shell32)
    endif()
    xfu_c_target(xfu_structured_escape_test)
    add_test(NAME xfu_structured_escape COMMAND xfu_structured_escape_test)
    add_executable(xfu_archive_core_test tests/test_archive_core.c)
    target_link_libraries(xfu_archive_core_test PRIVATE xxfclib::xfileunpacker_core)
    xfu_c_target(xfu_archive_core_test)
    add_test(NAME xfu_archive_core COMMAND xfu_archive_core_test
        "${CMAKE_CURRENT_BINARY_DIR}/archive-core-test")
    add_executable(xfu_encryption_notifications_test tests/test_encryption_notifications.c)
    target_link_libraries(xfu_encryption_notifications_test PRIVATE xxfclib::xfileunpacker_core)
    xfu_c_target(xfu_encryption_notifications_test)
    add_test(NAME xfu_encryption_notifications COMMAND xfu_encryption_notifications_test
        "${XFILEUNPACKER_XXFCLIB_DIR}/tests/fixtures/freearc_encrypted"
        "${CMAKE_CURRENT_BINARY_DIR}/encryption-notifications-test")
    add_executable(xfu_native_reader_backend_test tests/test_native_reader_backend.c)
    target_link_libraries(xfu_native_reader_backend_test PRIVATE xxfclib::xfileunpacker_core)
    xfu_c_target(xfu_native_reader_backend_test)
    add_test(NAME xfu_native_reader_backend COMMAND xfu_native_reader_backend_test
        "${CMAKE_CURRENT_BINARY_DIR}/native-reader-test")
    add_executable(xfu_specialized_core_test tests/test_specialized_core.c)
    target_link_libraries(xfu_specialized_core_test PRIVATE xxfclib::xfileunpacker_core)
    xfu_c_target(xfu_specialized_core_test)
    add_test(NAME xfu_specialized_core COMMAND xfu_specialized_core_test
        "${CMAKE_CURRENT_BINARY_DIR}/specialized-core-test")
    foreach(_format_test IN ITEMS scummvm_dxa_native freearc_encrypted_native)
        add_executable(xfu_${_format_test}_test
            "${XFILEUNPACKER_XXFCLIB_DIR}/tests/test_${_format_test}.c")
        target_link_libraries(xfu_${_format_test}_test PRIVATE xxfclib::xxfclib)
        xfu_c_target(xfu_${_format_test}_test)
        if(_format_test STREQUAL "freearc_encrypted_native")
            add_test(NAME xfu_${_format_test} COMMAND xfu_${_format_test}_test
                "${XFILEUNPACKER_XXFCLIB_DIR}/tests/fixtures/freearc_encrypted")
        else()
            add_test(NAME xfu_${_format_test} COMMAND xfu_${_format_test}_test)
        endif()
    endforeach()
    find_package(Python3 COMPONENTS Interpreter QUIET)
    add_executable(xfu_lzip_prefix_test tests/test_lzip_prefix.c)
    target_link_libraries(xfu_lzip_prefix_test PRIVATE xxfclib::xxfclib)
    xfu_c_target(xfu_lzip_prefix_test)
    add_test(NAME xfu_lzip_prefix COMMAND xfu_lzip_prefix_test)
    foreach(_recovery_test IN ITEMS pfx_prefix_native recovery_tail_readers legacy_output_names pftw_new_header_native)
        add_executable(xfu_${_recovery_test}_test
            "${XFILEUNPACKER_XXFCLIB_DIR}/tests/test_${_recovery_test}.c")
        target_link_libraries(xfu_${_recovery_test}_test PRIVATE xxfclib::xxfclib)
        xfu_c_target(xfu_${_recovery_test}_test)
        add_test(NAME xfu_${_recovery_test} COMMAND xfu_${_recovery_test}_test)
    endforeach()
    if(Python3_Interpreter_FOUND)
        add_test(NAME xfu_encryption_notices_cli
            COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_encryption_notices.py"
                "$<TARGET_FILE:XFileUnpacker>"
                "${XFILEUNPACKER_XXFCLIB_DIR}/tests/fixtures/freearc_encrypted")
        add_test(NAME xfu_freearc_encrypted_cli
            COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_freearc_encrypted.py"
                "$<TARGET_FILE:XFileUnpacker>"
                "${XFILEUNPACKER_XXFCLIB_DIR}/tests/fixtures/freearc_encrypted")
        add_test(NAME xfu_arc_recovery_formats
            COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_arc_recovery_formats.py"
                "$<TARGET_FILE:XFileUnpacker>")
        add_executable(xfu_unpack_handle_types_test tests/test_unpack_handle_types.c)
        target_link_libraries(xfu_unpack_handle_types_test PRIVATE xxfclib::xxfclib)
        xfu_c_target(xfu_unpack_handle_types_test)
        add_test(NAME xfu_unpack_handle_fixtures
            COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/create_unpack_handle_fixtures.py"
                "${CMAKE_CURRENT_BINARY_DIR}/unpack-handle-fixtures")
        set_tests_properties(xfu_unpack_handle_fixtures PROPERTIES FIXTURES_SETUP unpack_handle_fixtures)
        add_test(NAME xfu_unpack_handle_types COMMAND xfu_unpack_handle_types_test
            "${CMAKE_CURRENT_BINARY_DIR}/unpack-handle-fixtures")
        set_tests_properties(xfu_unpack_handle_types PROPERTIES FIXTURES_REQUIRED unpack_handle_fixtures)
        add_test(NAME xfu_archive_compat
            COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_archive_compat.py"
                "$<TARGET_FILE:XFileUnpacker>")
        add_test(NAME xfu_archive_feature_contract
            COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_archive_feature_contract.py"
                "$<TARGET_FILE:XFileUnpacker>")
        add_test(NAME xfu_native_writers
            COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_native_writers.py"
                "$<TARGET_FILE:XFileUnpacker>")
        add_test(NAME xfu_pea_compat
            COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_pea_compat.py"
                "$<TARGET_FILE:XFileUnpacker>")
        add_test(NAME xfu_freearc_compat
            COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_freearc_compat.py"
                "$<TARGET_FILE:XFileUnpacker>")
        add_test(NAME xfu_split_compat
            COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_split_compat.py"
                "$<TARGET_FILE:XFileUnpacker>")
        set(_xfu_capability_contract_args "$<TARGET_FILE:XFileUnpacker>")
        if(WIN32 AND XFILEUNPACKER_BUILD_FREEARC_SFX)
            list(APPEND _xfu_capability_contract_args --expect-freearc-sfx)
        endif()
        add_test(NAME xfu_xxfclib_only_capabilities
            COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_xxfclib_only_capabilities.py"
                ${_xfu_capability_contract_args})
        unset(_xfu_capability_contract_args)
        if(WIN32 AND XFILEUNPACKER_BUILD_FREEARC_SFX)
            add_test(NAME xfu_freearc_sfx_compat
                COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_freearc_sfx_compat.py"
                    "$<TARGET_FILE:XFileUnpacker>")
        endif()
    endif()
endif()
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
