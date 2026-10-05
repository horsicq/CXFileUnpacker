# WIM compression stays in a separately licensed, pipe-only runtime.
option(XFILEUNPACKER_BUILD_WIM_CODEC_ENGINE "Bundle RAM-only wimlib compression" ON)
if(XFILEUNPACKER_BUILD_WIM_CODEC_ENGINE AND WIN32 AND MSVC AND CMAKE_SIZEOF_VOID_P EQUAL 8)
    enable_language(CXX)
    add_subdirectory("${XFILEUNPACKER_XXFCLIB_DIR}/helpers/wim_codec_engine" "${CMAKE_CURRENT_BINARY_DIR}/deps/wim_codec_engine")
    set_target_properties(xfu_wim_codec_engine PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
    foreach(_frontend XFileUnpacker XFileUnpackerGUI XFileUnpackerTUI)
        if(TARGET ${_frontend})
            add_dependencies(${_frontend} xfu_wim_codec_engine)
        endif()
    endforeach()
endif()
option(XFILEUNPACKER_BUILD_LEGACY_ARCHIVE_ENGINE "Bundle RAM-only UnUHARC compatibility helper" ON)
if(XFILEUNPACKER_BUILD_LEGACY_ARCHIVE_ENGINE AND WIN32 AND MSVC)
    set(_legacy_source "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/legacy_archive_engine")
    set(_legacy_runtime "${CMAKE_CURRENT_BINARY_DIR}/$<CONFIG>")
    file(GLOB_RECURSE _legacy_sources CONFIGURE_DEPENDS "${_legacy_source}/*")
    set(_legacy_outputs)
    foreach(_file xfu_legacy_helper.exe xfu_legacy_io.dll xfu_unuharc06.exe UNUHARC-LICENSE.DOC)
        list(APPEND _legacy_outputs "${_legacy_runtime}/${_file}")
    endforeach()
    add_custom_command(OUTPUT ${_legacy_outputs}
        COMMAND "${CMAKE_COMMAND}" "-DBUILD_DIR=${CMAKE_CURRENT_BINARY_DIR}/deps/legacy_archive_win32"
            "-DOUTPUT_DIR=${_legacy_runtime}" "-DCONFIG=$<CONFIG>" -P "${_legacy_source}/build.cmake"
        DEPENDS ${_legacy_sources} VERBATIM)
    add_custom_target(xfileunpacker_legacy_archive_runtime ALL DEPENDS ${_legacy_outputs})
    foreach(_frontend XFileUnpacker XFileUnpackerGUI XFileUnpackerTUI)
        if(TARGET ${_frontend})
            add_dependencies(${_frontend} xfileunpacker_legacy_archive_runtime)
        endif()
    endforeach()
    install(PROGRAMS "${_legacy_runtime}/xfu_legacy_helper.exe" "${_legacy_runtime}/xfu_legacy_io.dll" "${_legacy_runtime}/xfu_unuharc06.exe" DESTINATION bin)
    install(FILES "${_legacy_runtime}/UNUHARC-LICENSE.DOC" DESTINATION bin)
    install(DIRECTORY "${_legacy_source}/" DESTINATION share/source/legacy_archive_engine)
endif()
if(BUILD_TESTING)
    add_executable(xfileunpacker_superdat_probe tests/superdat_probe.c)
    target_link_libraries(xfileunpacker_superdat_probe PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_superdat_probe)
    add_test(NAME superdat COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/superdat_regression.py"
        --probe "$<TARGET_FILE:xfileunpacker_superdat_probe>" --cli "$<TARGET_FILE:XFileUnpacker>"
        --root "${CMAKE_CURRENT_BINARY_DIR}/superdat-tests"
        --lifecycle-probe "$<TARGET_FILE:xfileunpacker_superdat_lifecycle>")
    set_tests_properties(superdat PROPERTIES TIMEOUT 120)
    add_executable(xfileunpacker_superdat_lifecycle tests/superdat_lifecycle.c)
    target_link_libraries(xfileunpacker_superdat_lifecycle PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_superdat_lifecycle)
    add_executable(xfileunpacker_excelsior_probe "${XFILEUNPACKER_XXFCLIB_DIR}/tests/excelsior/native_probe.c")
    target_link_libraries(xfileunpacker_excelsior_probe PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_excelsior_probe)
    add_test(NAME excelsior COMMAND "${Python3_EXECUTABLE}" "${XFILEUNPACKER_XXFCLIB_DIR}/tests/excelsior/regression.py"
        --native-probe "$<TARGET_FILE:xfileunpacker_excelsior_probe>" --cli "$<TARGET_FILE:XFileUnpacker>"
        --root "${CMAKE_CURRENT_BINARY_DIR}/excelsior-tests")
    set_tests_properties(excelsior PROPERTIES TIMEOUT 180)
    if(TARGET xfileunpacker_legacy_archive_runtime)
        add_test(NAME legacy_archive_engine COMMAND "${Python3_EXECUTABLE}"
            "${_legacy_source}/regression.py" --helper "${_legacy_runtime}/xfu_legacy_helper.exe"
            --root "${CMAKE_CURRENT_BINARY_DIR}/legacy-archive-tests" --cli "$<TARGET_FILE:XFileUnpacker>")
        set_tests_properties(legacy_archive_engine PROPERTIES TIMEOUT 180)
    endif()
    if(TARGET xfu_wim_codec_engine)
        add_executable(xfileunpacker_wim_compression_probe tests/wim_compression_probe.c)
        target_link_libraries(xfileunpacker_wim_compression_probe PRIVATE xxfclib::xxformats)
        add_dependencies(xfileunpacker_wim_compression_probe xfu_wim_codec_engine)
        xfu_c_target(xfileunpacker_wim_compression_probe)
        foreach(_variant pipe_probe stalled_helper)
            add_executable(xfileunpacker_wim_compression_${_variant} tests/wim_compression_pipe_probe.c)
            target_include_directories(xfileunpacker_wim_compression_${_variant} PRIVATE "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/wim")
            target_link_libraries(xfileunpacker_wim_compression_${_variant} PRIVATE xxfclib::xxformats kernel32)
            if(_variant STREQUAL "stalled_helper")
                target_compile_definitions(xfileunpacker_wim_compression_${_variant} PRIVATE XFU_WIM_STALLED_HELPER)
            endif()
            xfu_c_target(xfileunpacker_wim_compression_${_variant})
        endforeach()
        if(XFILEUNPACKER_7ZIP_REFERENCE AND TARGET xfileunpacker_wim_writer_probe)
            add_test(NAME wim_compression COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/wim_compression_regression.py"
                --probe "$<TARGET_FILE:xfileunpacker_wim_compression_probe>"
                --writer-probe "$<TARGET_FILE:xfileunpacker_wim_writer_probe>"
                --pipe-probe "$<TARGET_FILE:xfileunpacker_wim_compression_pipe_probe>"
                --stalled-helper "$<TARGET_FILE:xfileunpacker_wim_compression_stalled_helper>"
                --helper "$<TARGET_FILE:xfu_wim_codec_engine>" --sevenzip "${XFILEUNPACKER_7ZIP_REFERENCE}"
                --root "${CMAKE_CURRENT_BINARY_DIR}/wim-compression-tests")
            set_tests_properties(wim_compression PROPERTIES TIMEOUT 300)
            add_test(NAME wim_cli_compression COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/wim_cli_compression.py"
                --cli "$<TARGET_FILE:XFileUnpacker>" --sevenzip "${XFILEUNPACKER_7ZIP_REFERENCE}"
                --root "${CMAKE_CURRENT_BINARY_DIR}/wim-cli-compression-tests")
            set_tests_properties(wim_cli_compression PROPERTIES TIMEOUT 180)
        endif()
    endif()
endif()
install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/superdat/" DESTINATION share/source/superdat)
install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/include/xxfclib/formats/superdat/" DESTINATION share/source/superdat/include)
install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/excelsior/" DESTINATION share/source/excelsior)
install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/include/xxfclib/formats/excelsior/" DESTINATION share/source/excelsior/include)
install(FILES "${XFILEUNPACKER_XXFCLIB_DIR}/tests/excelsior/FORMAT.md" "${XFILEUNPACKER_XXFCLIB_DIR}/tests/excelsior/provenance.json" DESTINATION share/source/excelsior)

if(BUILD_TESTING)
    add_executable(xfileunpacker_fead_probe "${XFILEUNPACKER_XXFCLIB_DIR}/tests/fead/native_probe.c")
    target_link_libraries(xfileunpacker_fead_probe PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_fead_probe)
    add_test(NAME fead COMMAND "${Python3_EXECUTABLE}" "${XFILEUNPACKER_XXFCLIB_DIR}/tests/fead/regression.py"
        --native-probe "$<TARGET_FILE:xfileunpacker_fead_probe>" --cli "$<TARGET_FILE:XFileUnpacker>"
        --root "${CMAKE_CURRENT_BINARY_DIR}/fead-tests")
    set_tests_properties(fead PROPERTIES TIMEOUT 180)
endif()
install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/fead/" DESTINATION share/source/fead)
install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/include/xxfclib/formats/fead/" DESTINATION share/source/fead/include)
install(FILES "${XFILEUNPACKER_XXFCLIB_DIR}/tests/fead/FORMAT.md" "${XFILEUNPACKER_XXFCLIB_DIR}/tests/fead/provenance.json" DESTINATION share/source/fead)
install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/wim/" DESTINATION share/source/wim)
install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/include/xxfclib/formats/wim/" DESTINATION share/source/wim/include)
install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/legacy_archive_engine/" DESTINATION share/source/legacy_archive_engine/native)
install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/include/xxfclib/formats/legacy_archive_engine/" DESTINATION share/source/legacy_archive_engine/include)

# DGCA uses the native C decoder in all frontends and has no helper runtime.
install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/dgca/" DESTINATION share/source/dgca)
if(BUILD_TESTING)
    add_executable(xfileunpacker_dgca_lifecycle tests/dgca_native_lifecycle.c)
    target_link_libraries(xfileunpacker_dgca_lifecycle PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_dgca_lifecycle)
    add_test(NAME dgca_native COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/dgca_native.py"
        --cli "$<TARGET_FILE:XFileUnpacker>"
        --fixtures "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/legacy_archive_engine/fixtures"
        --root "${CMAKE_CURRENT_BINARY_DIR}/dgca-native-tests")
    set_tests_properties(dgca_native PROPERTIES TIMEOUT 180)
    add_test(NAME dgca_native_lifecycle COMMAND "$<TARGET_FILE:xfileunpacker_dgca_lifecycle>"
        "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/legacy_archive_engine/fixtures/dgca-stored.dgc"
        "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/legacy_archive_engine/fixtures/dgca-password.dgc"
        "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/legacy_archive_engine/fixtures/dgca-unicode-password.dgc")
    set_tests_properties(dgca_native_lifecycle PROPERTIES TIMEOUT 60)
endif()
