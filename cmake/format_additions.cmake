# The GPL filesystem implementation is built as a separate executable. The
# MIT library communicates through bounded pipes and never mounts an image.
option(XFILEUNPACKER_BUILD_GRUB_HELPER "Bundle read-only GRUB filesystem helper" ON)
find_package(Python3 COMPONENTS Interpreter QUIET)
if(CMAKE_CONFIGURATION_TYPES)
    set(_xfu_helper_dir "${CMAKE_CURRENT_BINARY_DIR}/$<CONFIG>")
else()
    set(_xfu_helper_dir "${CMAKE_CURRENT_BINARY_DIR}")
endif()
option(XFILEUNPACKER_BUILD_MODERN_FILESYSTEM_HELPER "Bundle separate read-only ReFS filesystem helper" ON)
if(XFILEUNPACKER_BUILD_MODERN_FILESYSTEM_HELPER)
    find_program(XFILEUNPACKER_GRUB_C_COMPILER NAMES clang clang.exe gcc
        HINTS "F:/dev/llvm/22.1.8/bin")
    if(NOT Python3_Interpreter_FOUND OR NOT XFILEUNPACKER_GRUB_C_COMPILER)
        message(FATAL_ERROR "ReFS helper requires Python and clang/gcc; configure its compiler or disable XFILEUNPACKER_BUILD_MODERN_FILESYSTEM_HELPER")
    endif()
    set(XFILEUNPACKER_MODERN_FS_HELPER "${_xfu_helper_dir}/xfu_modern_fs_helper${CMAKE_EXECUTABLE_SUFFIX}")
    set(_xfu_modern_source "${XFILEUNPACKER_XXFCLIB_DIR}/helpers/modern_filesystems")
    file(GLOB_RECURSE _xfu_modern_files CONFIGURE_DEPENDS "${_xfu_modern_source}/*")
    add_custom_command(OUTPUT "${XFILEUNPACKER_MODERN_FS_HELPER}"
        COMMAND "${Python3_EXECUTABLE}" "${_xfu_modern_source}/build.py"
            --cc "${XFILEUNPACKER_GRUB_C_COMPILER}" --output "${XFILEUNPACKER_MODERN_FS_HELPER}"
        DEPENDS ${_xfu_modern_files} VERBATIM)
    add_custom_target(xfileunpacker_modern_fs_helper ALL DEPENDS "${XFILEUNPACKER_MODERN_FS_HELPER}")
    foreach(_xfu_frontend XFileUnpacker XFileUnpackerGUI XFileUnpackerTUI)
        if(TARGET ${_xfu_frontend})
            add_dependencies(${_xfu_frontend} xfileunpacker_modern_fs_helper)
        endif()
    endforeach()
    install(PROGRAMS "${XFILEUNPACKER_MODERN_FS_HELPER}" DESTINATION bin)
    install(DIRECTORY "${_xfu_modern_source}/" DESTINATION share/source/modern_filesystems PATTERN "*.log" EXCLUDE)
endif()
option(XFILEUNPACKER_BUILD_ARCHIVE_CODEC_HELPER "Bundle separate GPL/LGPL archive codec helper" ON)
if(XFILEUNPACKER_BUILD_ARCHIVE_CODEC_HELPER)
    add_subdirectory("${XFILEUNPACKER_XXFCLIB_DIR}/helpers/archive_codecs" "archive_codec_build")
    set_target_properties(xfu_archive_codec_helper PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${_xfu_helper_dir}")
    foreach(_xfu_frontend XFileUnpacker XFileUnpackerGUI XFileUnpackerTUI)
        if(TARGET ${_xfu_frontend})
            add_dependencies(${_xfu_frontend} xfu_archive_codec_helper)
        endif()
    endforeach()
endif()
if(XFILEUNPACKER_BUILD_GRUB_HELPER)
    find_program(XFILEUNPACKER_GRUB_C_COMPILER NAMES clang clang.exe gcc
        HINTS "F:/dev/llvm/22.1.8/bin")
    if(NOT Python3_Interpreter_FOUND OR NOT XFILEUNPACKER_GRUB_C_COMPILER)
        message(FATAL_ERROR "GRUB helper requires Python and clang/gcc; configure its compiler or disable XFILEUNPACKER_BUILD_GRUB_HELPER")
    endif()
    set(XFILEUNPACKER_GRUB_HELPER "${_xfu_helper_dir}/xfu_grub_fs_helper${CMAKE_EXECUTABLE_SUFFIX}")
    file(GLOB_RECURSE _xfu_helper_sources CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/third_party/grub_fs_helper/*")
    add_custom_command(OUTPUT "${XFILEUNPACKER_GRUB_HELPER}"
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/third_party/grub_fs_helper/build.py"
            --cc "${XFILEUNPACKER_GRUB_C_COMPILER}" --output "${XFILEUNPACKER_GRUB_HELPER}"
        DEPENDS ${_xfu_helper_sources} VERBATIM)
    add_custom_target(xfileunpacker_grub_helper ALL DEPENDS "${XFILEUNPACKER_GRUB_HELPER}")
    foreach(_xfu_frontend XFileUnpacker XFileUnpackerGUI XFileUnpackerTUI)
        if(TARGET ${_xfu_frontend})
            add_dependencies(${_xfu_frontend} xfileunpacker_grub_helper)
        endif()
    endforeach()
    install(PROGRAMS "${XFILEUNPACKER_GRUB_HELPER}" DESTINATION bin)
    # Corresponding source and notices accompany every portable package.
    install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/third_party/grub_fs_helper/"
        DESTINATION share/source/grub_fs_helper)
endif()
install(FILES "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/nsis/LICENSE.bzip2"
    DESTINATION share/doc/XFileUnpacker RENAME LICENSE.nsis-bzip2)
if(BUILD_TESTING)
    foreach(_xfu_probe archive_additions disk_wrappers_lifecycle volume_readers_probe volume_sparse_probe grub_backend_probe apple_additions_probe disk_crypto_probe)
        add_executable(xfileunpacker_${_xfu_probe} "tests/${_xfu_probe}.c")
        target_link_libraries(xfileunpacker_${_xfu_probe} PRIVATE xxfclib::xxformats)
        xfu_c_target(xfileunpacker_${_xfu_probe})
    endforeach()
    target_include_directories(xfileunpacker_archive_additions PRIVATE "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats")
    add_executable(xfileunpacker_classic_filesystem_probe "tests/classic_filesystem_probe.c")
    target_link_libraries(xfileunpacker_classic_filesystem_probe PRIVATE xxfclib::xxformats)
    target_include_directories(xfileunpacker_classic_filesystem_probe PRIVATE "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats")
    target_compile_definitions(xfileunpacker_classic_filesystem_probe PRIVATE XXFC_FORMATS_ONLY)
    xfu_c_target(xfileunpacker_classic_filesystem_probe)
    add_executable(xfileunpacker_legacy_filesystems_lifecycle "tests/legacy_filesystems_lifecycle.c")
    target_link_libraries(xfileunpacker_legacy_filesystems_lifecycle PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_legacy_filesystems_lifecycle)
    add_executable(xfileunpacker_modern_filesystems_lifecycle "tests/modern_filesystems_lifecycle.c")
    target_link_libraries(xfileunpacker_modern_filesystems_lifecycle PRIVATE xxfclib::xxformats)
    xfu_c_target(xfileunpacker_modern_filesystems_lifecycle)
    if(TARGET xfileunpacker_modern_fs_helper)
        add_dependencies(xfileunpacker_modern_filesystems_lifecycle xfileunpacker_modern_fs_helper)
        set(_xfu_refs_metadata_control "${_xfu_helper_dir}/xfu_refs_metadata_control${CMAKE_EXECUTABLE_SUFFIX}")
        add_custom_command(OUTPUT "${_xfu_refs_metadata_control}"
            COMMAND "${Python3_EXECUTABLE}" "${_xfu_modern_source}/build.py"
                --cc "${XFILEUNPACKER_GRUB_C_COMPILER}" --metadata-control --output "${_xfu_refs_metadata_control}"
            DEPENDS ${_xfu_modern_files} VERBATIM)
        add_custom_target(xfileunpacker_refs_metadata_control ALL DEPENDS "${_xfu_refs_metadata_control}")
        add_test(NAME refs_fragmented_metadata COMMAND "${Python3_EXECUTABLE}"
            "${_xfu_modern_source}/metadata_read_control.py" --probe "${_xfu_refs_metadata_control}")
        set_tests_properties(refs_fragmented_metadata PROPERTIES TIMEOUT 30)
    endif()
    add_executable(xfileunpacker_zfs_sa_layout_probe "tests/zfs_sa_layout_probe.c")
    xfu_c_target(xfileunpacker_zfs_sa_layout_probe)
    add_test(NAME zfs_sa_layouts COMMAND xfileunpacker_zfs_sa_layout_probe)
    if(WIN32)
        add_executable(xfileunpacker_grub_pipe_fixture "tests/grub_pipe_fixture_helper.c")
        xfu_c_target(xfileunpacker_grub_pipe_fixture)
        add_executable(xfileunpacker_grub_pipe_wait "tests/grub_pipe_wait_probe.c")
        target_link_libraries(xfileunpacker_grub_pipe_wait PRIVATE xxfclib::xxformats)
        xfu_c_target(xfileunpacker_grub_pipe_wait)
        foreach(_xfu_pipe_control RANGE 0 3)
            add_test(NAME grub_pipe_wait_${_xfu_pipe_control}
                COMMAND xfileunpacker_grub_pipe_wait "$<TARGET_FILE:xfileunpacker_grub_pipe_fixture>" ${_xfu_pipe_control})
            set_tests_properties(grub_pipe_wait_${_xfu_pipe_control} PROPERTIES TIMEOUT 90)
        endforeach()
    endif()
    target_include_directories(xfileunpacker_volume_readers_probe PRIVATE "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats")
    target_include_directories(xfileunpacker_apple_additions_probe PRIVATE "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats")
    target_include_directories(xfileunpacker_disk_crypto_probe PRIVATE "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats")
    if(TARGET xfu_archive_codec_helper)
        add_dependencies(xfileunpacker_archive_additions xfu_archive_codec_helper)
    endif()
    if(TARGET xfileunpacker_grub_helper)
        add_dependencies(xfileunpacker_volume_readers_probe xfileunpacker_grub_helper)
        add_dependencies(xfileunpacker_grub_backend_probe xfileunpacker_grub_helper)
    endif()
    if(TARGET xfileunpacker_modern_fs_helper)
        add_dependencies(xfileunpacker_volume_readers_probe xfileunpacker_modern_fs_helper)
    endif()
    add_test(NAME volume_sparse_regions COMMAND xfileunpacker_volume_sparse_probe)
    set_tests_properties(volume_sparse_regions PROPERTIES TIMEOUT 120)
    if(Python3_Interpreter_FOUND)
        add_test(NAME classic_filesystems COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/classic_filesystems_regression.py"
            --probe "$<TARGET_FILE:xfileunpacker_classic_filesystem_probe>" --root "${CMAKE_CURRENT_BINARY_DIR}/classic-filesystem-fixtures")
        add_test(NAME hpfs_filesystems COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/hpfs_filesystems_regression.py"
            --probe "$<TARGET_FILE:xfileunpacker_classic_filesystem_probe>" --root "${CMAKE_CURRENT_BINARY_DIR}/hpfs-filesystem-fixtures"
            --lifecycle-probe "$<TARGET_FILE:xfileunpacker_legacy_filesystems_lifecycle>")
        add_test(NAME legacy_filesystems COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/legacy_filesystems_regression.py"
            --probe "$<TARGET_FILE:xfileunpacker_volume_readers_probe>" --root "${CMAKE_CURRENT_BINARY_DIR}/legacy-filesystem-fixtures"
            --lifecycle-probe "$<TARGET_FILE:xfileunpacker_legacy_filesystems_lifecycle>")
        add_test(NAME modern_filesystems COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/modern_filesystem_additions.py"
            --probe "$<TARGET_FILE:xfileunpacker_volume_readers_probe>" --work "${CMAKE_CURRENT_BINARY_DIR}/modern-filesystem-fixtures"
            --lifecycle-probe "$<TARGET_FILE:xfileunpacker_modern_filesystems_lifecycle>")
        set_tests_properties(classic_filesystems hpfs_filesystems legacy_filesystems modern_filesystems PROPERTIES TIMEOUT 300)
        add_test(NAME filesystem_cli_integration COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/filesystem_cli_integration.py"
            --xfu "$<TARGET_FILE:XFileUnpacker>")
        set_tests_properties(filesystem_cli_integration PROPERTIES TIMEOUT 300)
        add_test(NAME archive_additions COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/archive_additions.py" --probe "$<TARGET_FILE:xfileunpacker_archive_additions>")
        add_test(NAME archive_wrappers COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/archive_wrappers.py"
            --probe "$<TARGET_FILE:xfileunpacker_archive_additions>"
            --work-dir "${CMAKE_CURRENT_BINARY_DIR}/archive-wrapper-fixtures")
        set_tests_properties(archive_wrappers PROPERTIES TIMEOUT 120)
        if(TARGET xfu_archive_codec_helper)
            add_test(NAME archive_secondwave COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/archive_secondwave.py"
                --probe "$<TARGET_FILE:xfileunpacker_archive_additions>"
                --work-dir "${CMAKE_CURRENT_BINARY_DIR}/archive-secondwave-fixtures")
            set_tests_properties(archive_secondwave PROPERTIES TIMEOUT 300)
        endif()
        add_test(NAME disk_wrappers_additions COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/disk_wrappers_regression.py"
            --unpacker "$<TARGET_FILE:XFileUnpacker>" --probe "$<TARGET_FILE:xfileunpacker_probe_readers>"
            --lifecycle-probe "$<TARGET_FILE:xfileunpacker_disk_wrappers_lifecycle>")
        add_test(NAME volume_readers_additions COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/volume_readers_regression.py"
            --probe "$<TARGET_FILE:xfileunpacker_volume_readers_probe>" --root "${CMAKE_CURRENT_BINARY_DIR}/volume-fixtures")
        add_test(NAME apple_format_additions COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/apple_format_additions.py"
            --probe "$<TARGET_FILE:xfileunpacker_apple_additions_probe>")
        add_test(NAME ldm_records COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/ldm_records_regression.py"
            --probe "$<TARGET_FILE:xfileunpacker_volume_readers_probe>")
        set_tests_properties(ldm_records PROPERTIES TIMEOUT 120)
        add_test(NAME encrypted_disk_readers COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/disk_crypto_regression.py"
            --crypto-probe "$<TARGET_FILE:xfileunpacker_disk_crypto_probe>"
            --unpacker "$<TARGET_FILE:XFileUnpacker>")
        set_tests_properties(archive_additions disk_wrappers_additions volume_readers_additions apple_format_additions encrypted_disk_readers PROPERTIES TIMEOUT 300)
        if(TARGET xfileunpacker_grub_helper)
            add_test(NAME grub_filesystems COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/grub_backend_regression.py"
                --helper "${XFILEUNPACKER_GRUB_HELPER}" --backend-probe "$<TARGET_FILE:xfileunpacker_grub_backend_probe>")
            set_tests_properties(grub_filesystems PROPERTIES TIMEOUT 120)
        endif()
    endif()
endif()
