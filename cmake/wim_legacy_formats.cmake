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

install(DIRECTORY "${XFILEUNPACKER_XXFCLIB_DIR}/src/formats/dgca/" DESTINATION share/source/dgca)
