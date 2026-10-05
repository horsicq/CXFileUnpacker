if(BUILD_TESTING)
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    if(WIN32)
        add_executable(xfileunpacker_archive_codec_pipe_probe tests/archive_codec_pipe_probe.c)
        target_include_directories(xfileunpacker_archive_codec_pipe_probe PRIVATE "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats")
        target_link_libraries(xfileunpacker_archive_codec_pipe_probe PRIVATE xxfclib::xxformats)
        xfu_c_target(xfileunpacker_archive_codec_pipe_probe)
        foreach(_mode stalled echo)
            add_executable(xfileunpacker_archive_codec_${_mode}_helper tests/archive_codec_pipe_probe.c)
            target_compile_definitions(xfileunpacker_archive_codec_${_mode}_helper PRIVATE XFU_AFC_FAKE_HELPER)
            if(_mode STREQUAL "echo")
                target_compile_definitions(xfileunpacker_archive_codec_${_mode}_helper PRIVATE XFU_AFC_ECHO_HELPER)
            endif()
            xfu_c_target(xfileunpacker_archive_codec_${_mode}_helper)
        endforeach()
        add_test(NAME archive_codec_pipe_progress COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/archive_codec_pipe_regression.py"
            --probe "$<TARGET_FILE:xfileunpacker_archive_codec_pipe_probe>"
            --stalled-helper "$<TARGET_FILE:xfileunpacker_archive_codec_stalled_helper>"
            --echo-helper "$<TARGET_FILE:xfileunpacker_archive_codec_echo_helper>"
            --root "${CMAKE_CURRENT_BINARY_DIR}/archive-codec-pipe-tests")
        set_tests_properties(archive_codec_pipe_progress PROPERTIES TIMEOUT 20)
    endif()
    foreach(_probe ue2_documents ue2_games uniextract_archive)
        add_executable(xfileunpacker_${_probe}_probe "tests/${_probe}_probe.c")
        target_link_libraries(xfileunpacker_${_probe}_probe PRIVATE xxfclib::xxformats)
        xfu_c_target(xfileunpacker_${_probe}_probe)
    endforeach()
    add_executable(xfileunpacker_bitrock_probe tests/uniextract_bitrock_probe.c)
    target_link_libraries(xfileunpacker_bitrock_probe PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_bitrock_probe)
    add_test(NAME uniextract_bitrock COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/uniextract_bitrock_regression.py"
        --probe "$<TARGET_FILE:xfileunpacker_bitrock_probe>" --work "${CMAKE_CURRENT_BINARY_DIR}/uniextract-bitrock-tests")
    add_executable(xfileunpacker_smart_install_maker_probe tests/smart_install_maker_probe.c)
    target_link_libraries(xfileunpacker_smart_install_maker_probe PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_smart_install_maker_probe)
    add_test(NAME uniextract_smart_install_maker COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/smart_install_maker_regression.py"
        --probe "$<TARGET_FILE:xfileunpacker_smart_install_maker_probe>" --root "${CMAKE_CURRENT_BINARY_DIR}/uniextract-smart-install-maker-tests")
    set_tests_properties(uniextract_bitrock uniextract_smart_install_maker PROPERTIES TIMEOUT 240)
    add_executable(xfileunpacker_molebox_probe tests/uniextract_molebox_probe.c)
    target_link_libraries(xfileunpacker_molebox_probe PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_molebox_probe)
    add_test(NAME uniextract_molebox COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/uniextract_molebox_regression.py"
        --probe "$<TARGET_FILE:xfileunpacker_molebox_probe>" --work "${CMAKE_CURRENT_BINARY_DIR}/uniextract-molebox-tests"
        --cli "$<TARGET_FILE:XFileUnpacker>")
    set_tests_properties(uniextract_molebox PROPERTIES TIMEOUT 240)
    add_test(NAME uniextract_documents COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/ue2_documents_regression.py"
        --probe "$<TARGET_FILE:xfileunpacker_ue2_documents_probe>" --root "${CMAKE_CURRENT_BINARY_DIR}/uniextract-documents-tests")
    add_test(NAME uniextract_games COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/ue2_games_regression.py"
        --probe "$<TARGET_FILE:xfileunpacker_ue2_games_probe>" --root "${CMAKE_CURRENT_BINARY_DIR}/uniextract-games-tests")
    add_test(NAME uniextract_archives COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/uniextract_archive_regression.py"
        --probe "$<TARGET_FILE:xfileunpacker_uniextract_archive_probe>" --work "${CMAKE_CURRENT_BINARY_DIR}/uniextract-archives-tests")
    set_tests_properties(uniextract_documents uniextract_games uniextract_archives PROPERTIES TIMEOUT 240)
    if(TARGET xfu_convertlit_helper)
        add_dependencies(xfileunpacker_uniextract_archive_probe xfu_convertlit_helper)
        add_test(NAME uniextract_lit COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/uniextract_lit_regression.py"
            --probe "$<TARGET_FILE:xfileunpacker_uniextract_archive_probe>" --work "${CMAKE_CURRENT_BINARY_DIR}/uniextract-lit-tests")
        set_tests_properties(uniextract_lit PROPERTIES TIMEOUT 240)
    endif()
    if(TARGET xfu_document_engine AND TARGET xfu_garbro_engine AND TARGET xfu_media_engine)
        add_test(NAME uniextract_cli COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/uniextract_cli_regression.py"
            --xfu "$<TARGET_FILE:XFileUnpacker>" --root "${CMAKE_CURRENT_BINARY_DIR}/uniextract-cli-tests")
        set_tests_properties(uniextract_cli PROPERTIES TIMEOUT 600)
    endif()
    if(TARGET xfu_garbro_engine)
        add_executable(xfileunpacker_garbro_probe_gate "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/garbro_engine/probe_gate.c")
        target_include_directories(xfileunpacker_garbro_probe_gate PRIVATE "${XFILEUNPACKER_XXFCLIB_DIR}/samples/unpack")
        target_link_libraries(xfileunpacker_garbro_probe_gate PRIVATE xxfclib::xxformats)
        xfu_c_target(xfileunpacker_garbro_probe_gate)
        add_test(NAME uniextract_garbro_gate COMMAND xfileunpacker_garbro_probe_gate)
        set_tests_properties(uniextract_garbro_gate PROPERTIES TIMEOUT 30)
        add_test(NAME uniextract_garbro_fallback COMMAND "${Python3_EXECUTABLE}" "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/garbro_engine/fallback_regression.py"
            --cli "$<TARGET_FILE:XFileUnpacker>" --helper "${XFU_GARBRO_RUNTIME_DIR}/xfu_garbro_helper.exe" --root "${CMAKE_CURRENT_BINARY_DIR}/uniextract-garbro-fallback-tests")
        set_tests_properties(uniextract_garbro_fallback PROPERTIES TIMEOUT 120)
        add_test(NAME uniextract_garbro COMMAND "${Python3_EXECUTABLE}" "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/garbro_engine/regression.py"
            --helper "${XFU_GARBRO_RUNTIME_DIR}/xfu_garbro_helper.exe" --root "${CMAKE_CURRENT_BINARY_DIR}/uniextract-garbro-tests")
        set_tests_properties(uniextract_garbro PROPERTIES TIMEOUT 240)
    endif()
    if(TARGET xfu_upx_engine)
        add_executable(xfileunpacker_upx_probe "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/upx_engine/native_probe.c")
        target_link_libraries(xfileunpacker_upx_probe PRIVATE xxfclib::xxformats)
        add_dependencies(xfileunpacker_upx_probe xfu_upx_runtime)
        xfu_c_target(xfileunpacker_upx_probe)
        add_executable(xfileunpacker_upx_marker_probe "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/upx_engine/marker_probe.c")
        target_link_libraries(xfileunpacker_upx_marker_probe PRIVATE xxfclib::xxformats)
        add_dependencies(xfileunpacker_upx_marker_probe xfu_upx_runtime)
        xfu_c_target(xfileunpacker_upx_marker_probe)
        add_test(NAME uniextract_upx_marker COMMAND xfileunpacker_upx_marker_probe)
        set_tests_properties(uniextract_upx_marker PROPERTIES TIMEOUT 30)
        add_test(NAME uniextract_upx COMMAND "${Python3_EXECUTABLE}" "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/upx_engine/regression.py"
            --helper "${XFU_UPX_RUNTIME_DIR}/xfu_upx_helper.exe"
            --fixtures "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/upx_engine/tests/fixtures"
            --root "${CMAKE_CURRENT_BINARY_DIR}/uniextract-upx-tests"
            --native-probe "$<TARGET_FILE:xfileunpacker_upx_probe>" --cli "$<TARGET_FILE:XFileUnpacker>")
        set_tests_properties(uniextract_upx PROPERTIES TIMEOUT 240)
    endif()
    add_executable(xfileunpacker_fmod_audio_probe tests/fmod_audio_probe.c)
    target_link_libraries(xfileunpacker_fmod_audio_probe PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_fmod_audio_probe)
    add_test(NAME uniextract_fmod_audio COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/fmod_audio_regression.py"
        --probe "$<TARGET_FILE:xfileunpacker_fmod_audio_probe>" --root "${CMAKE_CURRENT_BINARY_DIR}/uniextract-fmod-tests")
    set_tests_properties(uniextract_fmod_audio PROPERTIES TIMEOUT 240)
    if(TARGET xfu_document_engine)
        add_executable(xfileunpacker_document_engine_probe tests/document_engine_probe.c)
        target_link_libraries(xfileunpacker_document_engine_probe PRIVATE xxfclib::xxformats)
        add_dependencies(xfileunpacker_document_engine_probe xfu_document_engine)
        xfu_c_target(xfileunpacker_document_engine_probe)
        add_test(NAME uniextract_pdf COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/document_engine_regression.py"
            --probe "$<TARGET_FILE:xfileunpacker_document_engine_probe>" --root "${CMAKE_CURRENT_BINARY_DIR}/uniextract-pdf-tests")
        set_tests_properties(uniextract_pdf PROPERTIES TIMEOUT 240)
    endif()
    if(TARGET xfu_media_engine)
        add_executable(xfileunpacker_media_engine_probe tests/media_engine_probe.c)
        target_link_libraries(xfileunpacker_media_engine_probe PRIVATE xxfclib::xxformats)
        add_dependencies(xfileunpacker_media_engine_probe xfu_media_engine)
        xfu_c_target(xfileunpacker_media_engine_probe)
        set(XFILEUNPACKER_FFMPEG_REFERENCE "" CACHE FILEPATH "Independent FFmpeg executable for decoded media interoperability tests")
        if(XFILEUNPACKER_FFMPEG_REFERENCE)
            add_test(NAME uniextract_media COMMAND "${Python3_EXECUTABLE}" "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/media_engine/regression.py"
                --helper "$<TARGET_FILE:xfu_media_engine>" --probe "$<TARGET_FILE:xfileunpacker_media_engine_probe>"
                --root "${CMAKE_CURRENT_BINARY_DIR}/uniextract-media-tests" --ffmpeg "${XFILEUNPACKER_FFMPEG_REFERENCE}")
            set_tests_properties(uniextract_media PROPERTIES TIMEOUT 300)
        endif()
    endif()
endif()
install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/sqlite_sql/" DESTINATION share/source/sqlite_sql)
install(FILES "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/sqlite_sql/PROVENANCE.json" DESTINATION share/licenses/sqlite_sql)
foreach(_native bitrock smart_install_maker molebox)
    install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/${_native}/" DESTINATION "share/source/${_native}")
    install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/include/xxfclib/formats/${_native}/" DESTINATION "share/source/${_native}/include")
endforeach()
install(FILES "${XFILEUNPACKER_XXFCLIB_DIR}/docs/smart-install-maker-coverage.json" DESTINATION share/doc/xfileunpacker)
install(FILES "${XFILEUNPACKER_XXFCLIB_DIR}/docs/ue2-upx-coverage.json" DESTINATION share/doc/xfileunpacker)
# Keep relative source/provenance links usable in the installed documentation.
file(READ "${XFILEUNPACKER_XXFCLIB_DIR}/docs/UNIVERSAL_EXTRACTOR_FORMATS.md" _xfu_ue2_install_doc)
string(REPLACE "(../helpers/" "(../../source/" _xfu_ue2_install_doc "${_xfu_ue2_install_doc}")
string(REPLACE "(../src/formats/sqlite_sql/" "(../../source/sqlite_sql/" _xfu_ue2_install_doc "${_xfu_ue2_install_doc}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/UNIVERSAL_EXTRACTOR_FORMATS.md" "${_xfu_ue2_install_doc}")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/UNIVERSAL_EXTRACTOR_FORMATS.md"
    "${XFILEUNPACKER_XXFCLIB_DIR}/docs/uniextract2-coverage.json"
    "${XFILEUNPACKER_XXFCLIB_DIR}/docs/uniextract2-archive-installers-audit.json"
    "${XFILEUNPACKER_XXFCLIB_DIR}/docs/uniextract2-documents-audit.json"
    "${XFILEUNPACKER_XXFCLIB_DIR}/docs/ue2-games-coverage.json"
    "${XFILEUNPACKER_XXFCLIB_DIR}/docs/SEVENZIP_FORMATS.md"
    "${XFILEUNPACKER_XXFCLIB_DIR}/docs/7zip.md"
    DESTINATION share/doc/xfileunpacker)
