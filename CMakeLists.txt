cmake_minimum_required(VERSION 3.21)
file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/release_version.txt" XFILEUNPACKER_VERSION LIMIT_COUNT 1)
project(XFileUnpacker VERSION "${XFILEUNPACKER_VERSION}" DESCRIPTION "C archive unpacker with console, GUI and TUI frontends" LANGUAGES C)

include(CTest)
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
        target_compile_options(xxfclib_formats PRIVATE -Wall -Wextra -Wpedantic)
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

# Offline tool for investigating detection and reader coverage on real corpora.
add_executable(xfileunpacker_probe_readers EXCLUDE_FROM_ALL tests/probe_readers.c)
target_include_directories(xfileunpacker_probe_readers PRIVATE "${XFILEUNPACKER_XXFCLIB_DIR}/samples/unpack")
target_link_libraries(xfileunpacker_probe_readers PRIVATE xfileunpacker_core)
xfu_c_target(xfileunpacker_probe_readers)
add_executable(xfileunpacker_probe_metadata EXCLUDE_FROM_ALL tests/probe_metadata.c)
target_include_directories(xfileunpacker_probe_metadata PRIVATE "${XFILEUNPACKER_XXFCLIB_DIR}/samples/unpack")
target_link_libraries(xfileunpacker_probe_metadata PRIVATE xfileunpacker_core)
if(WIN32)
    target_link_libraries(xfileunpacker_probe_metadata PRIVATE shell32)
endif()
xfu_c_target(xfileunpacker_probe_metadata)

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

if(BUILD_TESTING)
    add_executable(xfileunpacker_archive_test_memory tests/archive_test_memory.c)
    target_link_libraries(xfileunpacker_archive_test_memory PRIVATE xfileunpacker_core)
    xfu_c_target(xfileunpacker_archive_test_memory)
    add_executable(xfileunpacker_hxc_track_lifecycle tests/hxc_track_lifecycle.c)
    target_link_libraries(xfileunpacker_hxc_track_lifecycle PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_hxc_track_lifecycle)
    add_executable(xfileunpacker_hxc_sector_lifecycle tests/hxc_sector_lifecycle.c)
    target_link_libraries(xfileunpacker_hxc_sector_lifecycle PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_hxc_sector_lifecycle)
    add_executable(xfileunpacker_hxc_layout_lifecycle tests/hxc_layout_lifecycle.c)
    target_include_directories(xfileunpacker_hxc_layout_lifecycle PRIVATE "${XFILEUNPACKER_XXFCLIB_DIR}/samples/unpack")
    target_link_libraries(xfileunpacker_hxc_layout_lifecycle PRIVATE xfileunpacker_core)
    xfu_c_target(xfileunpacker_hxc_layout_lifecycle)
    add_test(NAME hxc_layout_lifecycle COMMAND xfileunpacker_hxc_layout_lifecycle)
    set_tests_properties(hxc_layout_lifecycle PROPERTIES TIMEOUT 60)
    add_executable(xfileunpacker_ad01_password_metadata tests/ad01_password_metadata.c)
    target_link_libraries(xfileunpacker_ad01_password_metadata PRIVATE xfileunpacker_core)
    xfu_c_target(xfileunpacker_ad01_password_metadata)
    add_executable(xfileunpacker_core_embedded_password tests/core_embedded_password.c)
    target_link_libraries(xfileunpacker_core_embedded_password PRIVATE xfileunpacker_core)
    xfu_c_target(xfileunpacker_core_embedded_password)
    add_executable(xfileunpacker_demolition_password_lifecycle tests/demolition_password_lifecycle.c)
    target_link_libraries(xfileunpacker_demolition_password_lifecycle PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_demolition_password_lifecycle)
    set_target_properties(xfileunpacker_probe_readers PROPERTIES EXCLUDE_FROM_ALL FALSE)
    find_package(Threads REQUIRED)
    target_link_libraries(xfileunpacker_archive_test_memory PRIVATE Threads::Threads)
    add_executable(xfileunpacker_sfx_gzip_tests tests/sfx_gzip.c)
    target_link_libraries(xfileunpacker_sfx_gzip_tests PRIVATE xfileunpacker_core)
    xfu_c_target(xfileunpacker_sfx_gzip_tests)
    add_test(NAME sfx_gzip_carriers COMMAND xfileunpacker_sfx_gzip_tests)
    set_tests_properties(sfx_gzip_carriers PROPERTIES TIMEOUT 20)
    add_executable(xfileunpacker_inftool_password_lifecycle tests/inftool_password_lifecycle.c)
    target_link_libraries(xfileunpacker_inftool_password_lifecycle PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_inftool_password_lifecycle)
    add_executable(xfileunpacker_hfe_cancellation_tests tests/hfe_cancellation.c)
    target_link_libraries(xfileunpacker_hfe_cancellation_tests PRIVATE xfileunpacker_core)
    xfu_c_target(xfileunpacker_hfe_cancellation_tests)
    find_package(Python3 COMPONENTS Interpreter QUIET)
    if(Python3_Interpreter_FOUND)
        add_test(NAME archive_test_memory COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/archive_test_memory.py"
            "$<TARGET_FILE:XFileUnpacker>" --probe "$<TARGET_FILE:xfileunpacker_archive_test_memory>")
        set_tests_properties(archive_test_memory PROPERTIES TIMEOUT 120)
        add_test(NAME hxc_track_formats COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/hxc_track_formats.py"
            --unpacker "$<TARGET_FILE:XFileUnpacker>" --probe "$<TARGET_FILE:xfileunpacker_probe_readers>"
            --lifecycle-probe "$<TARGET_FILE:xfileunpacker_hxc_track_lifecycle>")
        add_test(NAME hxc_sector_formats COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/hxc_sector_formats.py"
            --helper "$<TARGET_FILE:xfileunpacker_hxc_sector_lifecycle>")
        add_test(NAME hxc_coverage COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/hxc_coverage.py"
            --unpacker "$<TARGET_FILE:XFileUnpacker>" --library "${XFILEUNPACKER_XXFCLIB_DIR}")
        add_test(NAME hxc_layout_formats COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/hxc_layout_formats.py"
            --unpacker "$<TARGET_FILE:XFileUnpacker>")
        set_tests_properties(hxc_track_formats hxc_sector_formats hxc_coverage hxc_layout_formats PROPERTIES TIMEOUT 300)
        add_test(NAME binhex_layout COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/binhex_layout.py" "$<TARGET_FILE:XFileUnpacker>")
        add_test(NAME legacy_archives COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/legacy_archives.py" "$<TARGET_FILE:XFileUnpacker>")
        add_test(NAME reader_compatibility COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/reader_compatibility.py" "$<TARGET_FILE:XFileUnpacker>")
        set_tests_properties(binhex_layout legacy_archives reader_compatibility PROPERTIES TIMEOUT 60)
        add_test(NAME makeself_legacy COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/makeself_legacy_regression.py"
            --unpacker "$<TARGET_FILE:XFileUnpacker>" --probe "$<TARGET_FILE:xfileunpacker_probe_readers>")
        add_test(NAME sfx_spis_pe COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/sfx_spis_pe_regression.py"
            --unpacker "$<TARGET_FILE:XFileUnpacker>" --probe "$<TARGET_FILE:xfileunpacker_probe_readers>")
        add_test(NAME flashjester_legacy COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/flashjester_legacy_regression.py"
            --unpacker "$<TARGET_FILE:XFileUnpacker>" --probe "$<TARGET_FILE:xfileunpacker_probe_readers>")
        add_test(NAME format_research COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/format_research_regressions.py" "$<TARGET_FILE:XFileUnpacker>")
        add_test(NAME corelltec_paths COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/corelltec_paths.py" "$<TARGET_FILE:XFileUnpacker>")
        add_test(NAME vmssaveset_metadata COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/vmssaveset_metadata_regression.py"
            --unpacker "$<TARGET_FILE:XFileUnpacker>" --probe "$<TARGET_FILE:xfileunpacker_probe_readers>")
        add_test(NAME hfe_amiga COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/hfe_amiga.py" "$<TARGET_FILE:XFileUnpacker>"
            --probe "$<TARGET_FILE:xfileunpacker_probe_readers>"
            --cancellation-probe "$<TARGET_FILE:xfileunpacker_hfe_cancellation_tests>")
        add_test(NAME password_options COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/password_options.py" "$<TARGET_FILE:XFileUnpacker>")
        set(_xfu_password_retrieval_args --unpacker "$<TARGET_FILE:XFileUnpacker>")
        if(WIN32 AND TARGET XFileUnpackerGUI)
            list(APPEND _xfu_password_retrieval_args --gui "$<TARGET_FILE:XFileUnpackerGUI>")
        endif()
        if(WIN32 AND TARGET XFileUnpackerTUI)
            list(APPEND _xfu_password_retrieval_args --tui "$<TARGET_FILE:XFileUnpackerTUI>")
        endif()
        add_test(NAME password_retrieval COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/password_retrieval_regression.py" ${_xfu_password_retrieval_args})
        set_tests_properties(password_retrieval PROPERTIES TIMEOUT 120)
        add_test(NAME ad01_encryption COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/ad01_encryption_regression.py"
            --unpacker "$<TARGET_FILE:XFileUnpacker>" --probe "$<TARGET_FILE:xfileunpacker_probe_readers>"
            --metadata-probe "$<TARGET_FILE:xfileunpacker_ad01_password_metadata>")
        set(_xfu_demolition_args
            --unpacker "$<TARGET_FILE:XFileUnpacker>"
            --probe "$<TARGET_FILE:xfileunpacker_probe_readers>"
            --lifecycle-probe "$<TARGET_FILE:xfileunpacker_demolition_password_lifecycle>")
        if(WIN32 AND TARGET XFileUnpackerGUI)
            list(APPEND _xfu_demolition_args --gui "$<TARGET_FILE:XFileUnpackerGUI>")
        endif()
        if(WIN32 AND TARGET XFileUnpackerTUI)
            list(APPEND _xfu_demolition_args --tui "$<TARGET_FILE:XFileUnpackerTUI>")
        endif()
        add_test(NAME demolition_password COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/demolition_password_regression.py" ${_xfu_demolition_args})
        set_tests_properties(demolition_password PROPERTIES TIMEOUT 120)
        add_test(NAME inftool_regression COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/inftool_regression.py"
            --unpacker "$<TARGET_FILE:XFileUnpacker>" --probe "$<TARGET_FILE:xfileunpacker_probe_readers>")
        add_test(NAME inftool_legacy_zip COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/inftool_legacy_zip_regression.py"
            --unpacker "$<TARGET_FILE:XFileUnpacker>" --probe "$<TARGET_FILE:xfileunpacker_probe_readers>"
            --lifecycle-probe "$<TARGET_FILE:xfileunpacker_inftool_password_lifecycle>")
        if(WIN32)
            add_test(NAME windows_long_paths COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/windows_long_paths.py" "$<TARGET_FILE:XFileUnpacker>")
            set_tests_properties(windows_long_paths PROPERTIES TIMEOUT 120)
        endif()
        set_tests_properties(makeself_legacy sfx_spis_pe flashjester_legacy
            format_research corelltec_paths vmssaveset_metadata hfe_amiga password_options ad01_encryption
            inftool_regression inftool_legacy_zip PROPERTIES TIMEOUT 120)
    endif()
    add_executable(xfileunpacker_progress_tests tests/progress_observer.c)
    target_link_libraries(xfileunpacker_progress_tests PRIVATE xfileunpacker_core Threads::Threads)
    xfu_c_target(xfileunpacker_progress_tests)
    add_test(NAME progress_observer COMMAND xfileunpacker_progress_tests)
    set_tests_properties(progress_observer PROPERTIES TIMEOUT 15)
    add_executable(xfileunpacker_core_tests tests/core_api.c)
    target_link_libraries(xfileunpacker_core_tests PRIVATE xfileunpacker_core)
    xfu_c_target(xfileunpacker_core_tests)
    file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/tests/core-api")
    add_test(NAME core_api COMMAND xfileunpacker_core_tests)
    set_tests_properties(core_api PROPERTIES
        WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/tests/core-api" TIMEOUT 30)
    add_executable(xfileunpacker_metadata_tests tests/metadata.c)
    target_link_libraries(xfileunpacker_metadata_tests PRIVATE xfileunpacker_core)
    xfu_c_target(xfileunpacker_metadata_tests)
    file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/tests/metadata")
    add_test(NAME record_metadata COMMAND xfileunpacker_metadata_tests)
    set_tests_properties(record_metadata PROPERTIES
        WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/tests/metadata" TIMEOUT 30)
    add_executable(xfileunpacker_information_tests tests/information.c)
    target_link_libraries(xfileunpacker_information_tests PRIVATE xfileunpacker_core)
    xfu_c_target(xfileunpacker_information_tests)
    add_test(NAME information COMMAND xfileunpacker_information_tests)
    set_tests_properties(information PROPERTIES TIMEOUT 30)
    add_executable(xfileunpacker_selection_tests tests/selection_extract.c)
    target_link_libraries(xfileunpacker_selection_tests PRIVATE xfileunpacker_core)
    xfu_c_target(xfileunpacker_selection_tests)
    file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/tests/selection")
    add_test(NAME selected_extraction COMMAND xfileunpacker_selection_tests)
    set_tests_properties(selected_extraction PROPERTIES
        WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/tests/selection" TIMEOUT 30)
    add_executable(xfileunpacker_file_type_tests tests/file_types.c)
    target_link_libraries(xfileunpacker_file_type_tests PRIVATE xfileunpacker_core)
    xfu_c_target(xfileunpacker_file_type_tests)
    file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/tests/file-types")
    add_test(NAME file_types COMMAND xfileunpacker_file_type_tests)
    set_tests_properties(file_types PROPERTIES
        WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/tests/file-types" TIMEOUT 30)
    add_executable(xfileunpacker_fast_detection_tests tests/fast_detection.c)
    target_link_libraries(xfileunpacker_fast_detection_tests PRIVATE xfileunpacker_core)
    xfu_c_target(xfileunpacker_fast_detection_tests)
    file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/tests/fast-detection")
    add_test(NAME fast_detection COMMAND xfileunpacker_fast_detection_tests)
    set_tests_properties(fast_detection PROPERTIES
        WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/tests/fast-detection" TIMEOUT 30)
    foreach(widget_test IN ITEMS xxwidgets_core_tests xxwidgets_win32_tests
                                 xxwidgets_scan_options_tests xxwidgets_font_options_tests
                                 xxwidgets_context_options_tests xxwidgets_optimization_options_tests
                                 xxwidgets_tui_tests)
        if(TARGET ${widget_test})
            list(APPEND _xfu_widget_tests ${widget_test})
        endif()
    endforeach()
    if(_xfu_widget_tests)
        add_custom_target(xfileunpacker_widget_tests ALL DEPENDS ${_xfu_widget_tests})
    endif()
    add_test(NAME console_help COMMAND XFileUnpacker)
    add_executable(xfileunpacker_supported_types_tests tests/supported_types.c)
    target_link_libraries(xfileunpacker_supported_types_tests PRIVATE xfileunpacker_core)
    xfu_c_target(xfileunpacker_supported_types_tests)
    add_test(NAME supported_types COMMAND xfileunpacker_supported_types_tests)
    add_test(NAME console_formats COMMAND "${CMAKE_COMMAND}"
        "-DUNPACKER=$<TARGET_FILE:XFileUnpacker>"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/supported_types.cmake")
    set_tests_properties(supported_types console_formats PROPERTIES TIMEOUT 20)
    if(TARGET XFileUnpackerGUI)
        add_test(NAME gui_smoke COMMAND XFileUnpackerGUI --smoke-test)
        set_tests_properties(gui_smoke PROPERTIES TIMEOUT 30)
    endif()
    if(TARGET XFileUnpackerTUI AND WIN32)
        add_test(NAME tui_smoke COMMAND XFileUnpackerTUI --smoke-test)
        set_tests_properties(tui_smoke PROPERTIES TIMEOUT 30)
    endif()
    if(WIN32 AND Python3_Interpreter_FOUND AND (TARGET XFileUnpackerGUI OR TARGET XFileUnpackerTUI))
        set(_xfu_password_args
            --callback-probe "$<TARGET_FILE:xfileunpacker_core_embedded_password>")
        if(TARGET XFileUnpackerGUI)
            list(APPEND _xfu_password_args --gui "$<TARGET_FILE:XFileUnpackerGUI>")
        endif()
        if(TARGET XFileUnpackerTUI)
            list(APPEND _xfu_password_args --tui "$<TARGET_FILE:XFileUnpackerTUI>")
        endif()
        add_test(NAME ui_password COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/ui_password_regression.py" ${_xfu_password_args})
        set_tests_properties(ui_password PROPERTIES TIMEOUT 120)
    endif()
    if(TARGET XFileUnpackerGUI AND WIN32)
        set(_xfu_progress_args "-DGUI=$<TARGET_FILE:XFileUnpackerGUI>"
            "-DTEST_ROOT=${CMAKE_CURRENT_BINARY_DIR}/tests/threaded-progress")
        if(TARGET XFileUnpackerTUI)
            list(APPEND _xfu_progress_args "-DTUI=$<TARGET_FILE:XFileUnpackerTUI>")
        endif()
        add_test(NAME threaded_progress COMMAND "${CMAKE_COMMAND}" ${_xfu_progress_args}
            -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/threaded_progress.cmake")
        set_tests_properties(threaded_progress PROPERTIES TIMEOUT 45)
    endif()
    set(_xfu_roundtrip_args
        "-DUNPACKER=$<TARGET_FILE:XFileUnpacker>"
        "-DTEST_ROOT=${CMAKE_CURRENT_BINARY_DIR}/tests/roundtrip")
    if(TARGET XFileUnpackerGUI AND WIN32)
        list(APPEND _xfu_roundtrip_args "-DGUI=$<TARGET_FILE:XFileUnpackerGUI>")
    endif()
    if(TARGET XFileUnpackerTUI AND WIN32)
        list(APPEND _xfu_roundtrip_args "-DTUI=$<TARGET_FILE:XFileUnpackerTUI>")
    endif()
    add_test(NAME console_roundtrip COMMAND "${CMAKE_COMMAND}" ${_xfu_roundtrip_args}
        -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/roundtrip.cmake")
    set_tests_properties(console_roundtrip PROPERTIES TIMEOUT 120)
endif()

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
