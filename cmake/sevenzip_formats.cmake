# Full upstream archive engine stays in a separate licensed executable.
option(XFILEUNPACKER_BUILD_SEVENZIP_ENGINE "Bundle the full 7-Zip 26.03 reader engine" ON)
if(XFILEUNPACKER_BUILD_SEVENZIP_ENGINE AND WIN32 AND CMAKE_SIZEOF_VOID_P EQUAL 8)
    enable_language(CXX)
    add_subdirectory("${XFILEUNPACKER_XXFCLIB_DIR}/helpers/sevenzip_engine"
        "${CMAKE_CURRENT_BINARY_DIR}/deps/sevenzip_engine")
    set_target_properties(xfu_sevenzip_engine PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
    foreach(_xfu_frontend XFileUnpacker XFileUnpackerGUI XFileUnpackerTUI)
        if(TARGET ${_xfu_frontend})
            add_dependencies(${_xfu_frontend} xfu_sevenzip_engine)
        endif()
    endforeach()
    if(BUILD_TESTING)
        find_package(Python3 COMPONENTS Interpreter REQUIRED)
        add_executable(xfileunpacker_wim_writer_probe tests/wim_writer_probe.c)
        target_link_libraries(xfileunpacker_wim_writer_probe PRIVATE xxfclib::xxformats)
        xfu_c_target(xfileunpacker_wim_writer_probe)
        add_executable(xfileunpacker_sevenzip_engine_probe tests/sevenzip_engine_probe.c)
        target_link_libraries(xfileunpacker_sevenzip_engine_probe PRIVATE xxfclib::xxformats)
        add_dependencies(xfileunpacker_sevenzip_engine_probe xfu_sevenzip_engine)
        xfu_c_target(xfileunpacker_sevenzip_engine_probe)
        add_test(NAME sevenzip_engine_adapter COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/sevenzip_engine_regression.py"
            --probe "$<TARGET_FILE:xfileunpacker_sevenzip_engine_probe>"
            --root "${CMAKE_CURRENT_BINARY_DIR}/sevenzip-adapter-tests")
        set_tests_properties(sevenzip_engine_adapter PROPERTIES TIMEOUT 180)
        add_executable(xfileunpacker_sevenzip_backend_probe tests/sevenzip_backend_probe.c)
        target_link_libraries(xfileunpacker_sevenzip_backend_probe PRIVATE xxfclib::xxformats)
        add_dependencies(xfileunpacker_sevenzip_backend_probe xfu_sevenzip_engine)
        xfu_c_target(xfileunpacker_sevenzip_backend_probe)
        add_executable(xfileunpacker_sevenzip_stalled_helper tests/sevenzip_backend_probe.c)
        target_compile_definitions(xfileunpacker_sevenzip_stalled_helper PRIVATE XFU_STALLED_HELPER)
        xfu_c_target(xfileunpacker_sevenzip_stalled_helper)
        add_test(NAME sevenzip_backend_progress COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/sevenzip_backend_regression.py"
            --probe "$<TARGET_FILE:xfileunpacker_sevenzip_backend_probe>"
            --stalled-helper "$<TARGET_FILE:xfileunpacker_sevenzip_stalled_helper>"
            --helper "$<TARGET_FILE:xfu_sevenzip_engine>"
            --root "${CMAKE_CURRENT_BINARY_DIR}/sevenzip-backend-tests")
        set_tests_properties(sevenzip_backend_progress PROPERTIES TIMEOUT 180)
        add_executable(xfileunpacker_sevenzip_start_only_probe tests/sevenzip_start_only_probe.c)
        target_link_libraries(xfileunpacker_sevenzip_start_only_probe PRIVATE xxfclib::xxformats)
        add_dependencies(xfileunpacker_sevenzip_start_only_probe xfu_sevenzip_engine)
        xfu_c_target(xfileunpacker_sevenzip_start_only_probe)
        add_test(NAME sevenzip_start_only COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/sevenzip_start_only_regression.py"
            --probe "$<TARGET_FILE:xfileunpacker_sevenzip_start_only_probe>"
            --helper "$<TARGET_FILE:xfu_sevenzip_engine>"
            --root "${CMAKE_CURRENT_BINARY_DIR}/sevenzip-start-only-tests")
        set_tests_properties(sevenzip_start_only PROPERTIES TIMEOUT 180)
        set(XFILEUNPACKER_7ZIP_REFERENCE "" CACHE FILEPATH "Optional independent 7-Zip executable for interoperability tests")
        set(_xfu_7zip_producer_args)
        if(XFILEUNPACKER_7ZIP_REFERENCE)
            add_executable(xfileunpacker_zip_empty_writer_probe tests/zip_empty_writer_probe.c)
            target_link_libraries(xfileunpacker_zip_empty_writer_probe PRIVATE xxfclib::xxformats)
            xfu_c_target(xfileunpacker_zip_empty_writer_probe)
            add_test(NAME sevenzip_zip_empty_writer COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/zip_empty_writer_interop.py"
                --probe "$<TARGET_FILE:xfileunpacker_zip_empty_writer_probe>"
                --sevenzip "${XFILEUNPACKER_7ZIP_REFERENCE}"
                --root "${CMAKE_CURRENT_BINARY_DIR}/sevenzip-zip-empty-tests")
            set_tests_properties(sevenzip_zip_empty_writer PROPERTIES TIMEOUT 180)
            add_executable(xfileunpacker_single_stream_writer_probe tests/single_stream_writer_probe.c)
            target_link_libraries(xfileunpacker_single_stream_writer_probe PRIVATE xxfclib::xxformats)
            xfu_c_target(xfileunpacker_single_stream_writer_probe)
            add_test(NAME sevenzip_single_stream_writers COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/single_stream_writer_interop.py"
                --probe "$<TARGET_FILE:xfileunpacker_single_stream_writer_probe>"
                --sevenzip "${XFILEUNPACKER_7ZIP_REFERENCE}"
                --root "${CMAKE_CURRENT_BINARY_DIR}/sevenzip-single-stream-tests")
            set_tests_properties(sevenzip_single_stream_writers PROPERTIES TIMEOUT 180)
            list(APPEND _xfu_7zip_producer_args --producer "${XFILEUNPACKER_7ZIP_REFERENCE}")
            add_test(NAME sevenzip_wim_writer COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/wim_writer_interop.py"
                --probe "$<TARGET_FILE:xfileunpacker_wim_writer_probe>"
                --sevenzip "${XFILEUNPACKER_7ZIP_REFERENCE}"
                --root "${CMAKE_CURRENT_BINARY_DIR}/sevenzip-wim-tests")
            set_tests_properties(sevenzip_wim_writer PROPERTIES TIMEOUT 180)
            add_test(NAME sevenzip_interoperability COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/sevenzip_interop.py"
                --xfu "$<TARGET_FILE:XFileUnpacker>"
                --sevenzip "${XFILEUNPACKER_7ZIP_REFERENCE}"
                --root "${CMAKE_CURRENT_BINARY_DIR}/sevenzip-interop-tests"
                --engine-probe "$<TARGET_FILE:xfileunpacker_sevenzip_engine_probe>")
            set_tests_properties(sevenzip_interoperability PROPERTIES TIMEOUT 300)
        endif()
        add_test(NAME sevenzip_engine_protocol COMMAND "${Python3_EXECUTABLE}"
            "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/sevenzip_engine/regression.py"
            --helper "$<TARGET_FILE:xfu_sevenzip_engine>" ${_xfu_7zip_producer_args}
            --root "${CMAKE_CURRENT_BINARY_DIR}/sevenzip-protocol-tests")
        set_tests_properties(sevenzip_engine_protocol PROPERTIES TIMEOUT 180)
    endif()
endif()

option(XFILEUNPACKER_BUILD_DOCUMENT_ENGINE "Bundle the memory-only PDF reader" ON)
option(XFILEUNPACKER_BUILD_CONVERTLIT_HELPER "Bundle the memory-only LIT decoder" ON)
if(XFILEUNPACKER_BUILD_CONVERTLIT_HELPER)
    add_subdirectory("${XFILEUNPACKER_XXFCLIB_DIR}/helpers/convertlit" "${CMAKE_CURRENT_BINARY_DIR}/deps/convertlit")
    set_target_properties(xfu_convertlit_helper PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
    foreach(_xfu_frontend XFileUnpacker XFileUnpackerGUI XFileUnpackerTUI)
        if(TARGET ${_xfu_frontend})
            add_dependencies(${_xfu_frontend} xfu_convertlit_helper)
        endif()
    endforeach()
endif()
option(XFILEUNPACKER_BUILD_GARBRO_ENGINE "Bundle the RAM-only GARbro game archive reader" ON)
if(XFILEUNPACKER_BUILD_GARBRO_ENGINE AND WIN32 AND CMAKE_SIZEOF_VOID_P EQUAL 8)
    add_subdirectory("${XFILEUNPACKER_XXFCLIB_DIR}/helpers/garbro_engine" "${CMAKE_CURRENT_BINARY_DIR}/deps/garbro_engine")
    add_custom_target(xfu_garbro_runtime ALL
        COMMAND "${CMAKE_COMMAND}" -E copy_directory "${XFU_GARBRO_RUNTIME_DIR}" "$<TARGET_FILE_DIR:XFileUnpacker>"
        DEPENDS xfu_garbro_engine VERBATIM)
    foreach(_xfu_frontend XFileUnpacker XFileUnpackerGUI XFileUnpackerTUI)
        if(TARGET ${_xfu_frontend})
            add_dependencies(${_xfu_frontend} xfu_garbro_runtime)
        endif()
    endforeach()
endif()
option(XFILEUNPACKER_BUILD_MEDIA_ENGINE "Bundle the memory-only media reader" ON)
option(XFILEUNPACKER_BUILD_UPX_ENGINE "Bundle the memory-only UPX unpacker" ON)
if(XFILEUNPACKER_BUILD_UPX_ENGINE AND WIN32 AND MSVC AND CMAKE_SIZEOF_VOID_P EQUAL 8)
    enable_language(CXX)
    add_subdirectory("${XFILEUNPACKER_XXFCLIB_DIR}/helpers/upx_engine" "${CMAKE_CURRENT_BINARY_DIR}/deps/upx_engine")
    add_custom_target(xfu_upx_runtime ALL
        COMMAND "${CMAKE_COMMAND}" -E copy_directory "${XFU_UPX_RUNTIME_DIR}" "$<TARGET_FILE_DIR:XFileUnpacker>"
        DEPENDS xfu_upx_engine VERBATIM)
    foreach(_xfu_frontend XFileUnpacker XFileUnpackerGUI XFileUnpackerTUI)
        if(TARGET ${_xfu_frontend})
            add_dependencies(${_xfu_frontend} xfu_upx_runtime)
        endif()
    endforeach()
endif()
if(XFILEUNPACKER_BUILD_MEDIA_ENGINE AND WIN32 AND MSVC AND CMAKE_SIZEOF_VOID_P EQUAL 8)
    enable_language(CXX)
    add_subdirectory("${XFILEUNPACKER_XXFCLIB_DIR}/helpers/media_engine" "${CMAKE_CURRENT_BINARY_DIR}/deps/media_engine")
    set_target_properties(xfu_media_engine PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
    foreach(_xfu_frontend XFileUnpacker XFileUnpackerGUI XFileUnpackerTUI)
        if(TARGET ${_xfu_frontend})
            add_dependencies(${_xfu_frontend} xfu_media_engine)
        endif()
    endforeach()
endif()
if(XFILEUNPACKER_BUILD_DOCUMENT_ENGINE AND WIN32 AND CMAKE_SIZEOF_VOID_P EQUAL 8)
    enable_language(CXX)
    add_subdirectory("${XFILEUNPACKER_XXFCLIB_DIR}/helpers/document_engine" "${CMAKE_CURRENT_BINARY_DIR}/deps/document_engine")
    set_target_properties(xfu_document_engine PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
    foreach(_xfu_frontend XFileUnpacker XFileUnpackerGUI XFileUnpackerTUI)
        if(TARGET ${_xfu_frontend})
            add_dependencies(${_xfu_frontend} xfu_document_engine)
        endif()
    endforeach()
endif()
